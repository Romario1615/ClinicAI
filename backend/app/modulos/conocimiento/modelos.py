"""Base de conocimiento: las seis tablas `knowledge_*`.

Los nombres de estas tablas y de sus columnas de metadatos estan en **ingles**
por ser normativos (ADR-0015 y CLAUDE.md, seccion 2). Es la unica parte del
esquema donde ocurre, y es deliberado: la especificacion los fija asi.

La desnormalizacion de `knowledge_chunks`
-----------------------------------------
`knowledge_chunks` repite `clinic_id`, `branch_id`, `specialty_id`, `status`,
`effective_from`, `effective_until` y `sensitivity_level`, que ya estan en
`knowledge_documents`. Duplicar datos normalmente es un error; aqui es la
decision que sostiene la seguridad del RAG (ADR-0013).

El motivo: permite que **todo el filtro de autorizacion viva en un unico
`WHERE` sobre una sola tabla**, sin uniones. Una union se puede omitir por
error en una consulta nueva, y esa omision seria una fuga de informacion entre
sedes o entre especialidades. Sin uniones, el filtro es una lista de
condiciones que o estan o no estan, y hay una prueba de arquitectura que
verifica que ningun modulo fuera del repositorio autorizado consulta esta
tabla.

El precio es mantener la copia sincronizada. Se paga en un solo sitio: al
cambiar el estado o la vigencia de un documento, el servicio propaga a sus
fragmentos en la misma transaccion, y hay una prueba que lo comprueba.

Por que el embedding va en su propia tabla
------------------------------------------
`knowledge_embeddings` esta separada de `knowledge_chunks` y no es una columna
mas. Dos razones:

1. Un cambio de modelo de embeddings **no obliga a reescribir los fragmentos**:
   se reindexan los vectores y el texto se queda. La columna `modelo` permite
   convivir con dos modelos durante una migracion.
2. El indice HNSW es grande y se reconstruye a menudo. Tenerlo en una tabla
   aparte deja `knowledge_chunks` -- que es la que se filtra -- ligera.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.nucleo.bd import Base, MezclaAuditoria, MezclaIdentificador

# Dimension del modelo de embeddings por defecto
# (`intfloat/multilingual-e5-small`, ADR-0007). Cambiarla exige migracion y
# reindexado: el tipo `vector(n)` lleva la dimension en el esquema.
DIMENSION_EMBEDDING = 384


class EstadoDocumento(StrEnum):
    """Ciclo de vida de un documento (RF-M03).

    Los valores estan en ingles por ser normativos (CLAUDE.md, seccion 2).

    Solo `APPROVED` y `PUBLISHED` son recuperables por el agente. La
    diferencia entre ambos es de alcance, no de confianza: `APPROVED` esta
    aprobado y disponible para el personal; `PUBLISHED` ademas es material que
    la clinica considera apto para responder a un paciente.
    """

    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


# Los unicos estados que el agente puede recuperar (RF-M05). Vive aqui, junto
# al enum, para que la lista no se reescriba en cada consulta -- y para que
# anadir un estado obligue a pasar por este punto.
ESTADOS_RECUPERABLES: frozenset[str] = frozenset(
    {EstadoDocumento.APPROVED.value, EstadoDocumento.PUBLISHED.value}
)


class TipoDocumentoConocimiento(StrEnum):
    PROTOCOLO = "PROTOCOLO"
    INSTRUCTIVO = "INSTRUCTIVO"
    PREPARACION_EXAMEN = "PREPARACION_EXAMEN"
    POLITICA = "POLITICA"
    PREGUNTA_FRECUENTE = "PREGUNTA_FRECUENTE"
    TARIFARIO = "TARIFARIO"


class EstadoIngesta(StrEnum):
    PENDIENTE = "PENDIENTE"
    EN_PROCESO = "EN_PROCESO"
    COMPLETADA = "COMPLETADA"
    FALLIDA = "FALLIDA"


class PrincipalConocimiento(StrEnum):
    ROL = "ROL"
    USUARIO = "USUARIO"
    ESPECIALIDAD = "ESPECIALIDAD"
    SEDE = "SEDE"


# ---------------------------------------------------------------------------
#  Documento
# ---------------------------------------------------------------------------
class KnowledgeDocument(Base, MezclaIdentificador, MezclaAuditoria):
    """Documento de la base de conocimiento.

    `version_vigente` apunta a la version que se considera actual. No es
    redundante con la ultima fila de `knowledge_versions`: se puede subir una
    version nueva que quede en revision mientras la anterior sigue siendo la
    vigente para el agente.
    """

    __tablename__ = "knowledge_documents"

    clinic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="CASCADE"))
    titulo: Mapped[str] = mapped_column(String(300))
    tipo: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default=EstadoDocumento.DRAFT.value)
    version_vigente: Mapped[int] = mapped_column(Integer, default=0)

    # Quien responde del contenido. No es quien lo subio: un administrativo
    # puede cargar el protocolo que firma un medico, y ante una duda sobre el
    # contenido hay que poder preguntar a quien responde.
    responsable_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    aprobado_por: Mapped[uuid.UUID | None] = mapped_column(default=None)
    aprobado_en: Mapped[datetime | None] = mapped_column(default=None)

    effective_from: Mapped[datetime | None] = mapped_column(default=None)
    effective_until: Mapped[datetime | None] = mapped_column(default=None)
    sensitivity_level: Mapped[str] = mapped_column(String(4), default="N1")
    etiquetas: Mapped[list[str] | None] = mapped_column(ARRAY(Text), default=None)

    # Alcance. Nulo significa «toda la clinica», no «ninguna»: un protocolo
    # general no se limita a una sede.
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sede.id", ondelete="SET NULL"), default=None
    )
    specialty_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("especialidad.id", ondelete="SET NULL"), default=None
    )
    service_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("servicio.id", ondelete="SET NULL"), default=None
    )

    archivado_en: Mapped[datetime | None] = mapped_column(default=None)

    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'PENDING_REVIEW', 'APPROVED', 'PUBLISHED', 'ARCHIVED')",
            name="status_valido",
        ),
        CheckConstraint(
            "sensitivity_level IN ('N0', 'N1', 'N2', 'N3')",
            name="sensitivity_level_valido",
        ),
        # Un documento aprobado sin constancia de quien lo aprobo no permite
        # responder «quien autorizo que el agente diga esto» (RF-M04).
        CheckConstraint(
            "status NOT IN ('APPROVED', 'PUBLISHED') "
            "OR (aprobado_por IS NOT NULL AND aprobado_en IS NOT NULL)",
            name="aprobado_con_responsable",
        ),
        # Un documento recuperable sin version publicada no tiene fragmentos,
        # y aparecerìa como aprobado sin contenido.
        CheckConstraint(
            "status NOT IN ('APPROVED', 'PUBLISHED') OR version_vigente > 0",
            name="aprobado_exige_version",
        ),
        CheckConstraint(
            "effective_until IS NULL OR effective_from IS NULL OR effective_until > effective_from",
            name="vigencia_coherente",
        ),
        CheckConstraint(
            "status <> 'ARCHIVED' OR archivado_en IS NOT NULL",
            name="archivado_con_fecha",
        ),
        Index("ix_knowledge_documents_clinica", "clinic_id", "status"),
        Index("ix_knowledge_documents_alcance", "clinic_id", "branch_id", "specialty_id"),
    )


class KnowledgeVersion(Base, MezclaIdentificador):
    """Una version concreta del contenido de un documento.

    Se conserva el `hash_sha256` del archivo original: permite detectar que se
    volvio a subir el mismo contenido -- y evitar reindexarlo -- y verificar
    integridad ante una duda sobre que se aprobo exactamente.
    """

    __tablename__ = "knowledge_versions"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column(Integer)
    nombre_archivo: Mapped[str | None] = mapped_column(String(255), default=None)
    hash_sha256: Mapped[str] = mapped_column(String(64))
    ruta_almacenamiento: Mapped[str | None] = mapped_column(Text, default=None)
    # Se conserva solo mientras la ingesta este pendiente o haya fallado para
    # poder reintentarla; al completarse se borra el duplicado del contenido.
    contenido_texto: Mapped[str | None] = mapped_column(Text, default=None)
    autor_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    notas_cambio: Mapped[str | None] = mapped_column(Text, default=None)
    creado_en: Mapped[datetime] = mapped_column(server_default=text("now()"))

    # Resultado del analisis de inyeccion de prompt (ADR-0014). Se guarda
    # completo -- que patrones se detectaron y donde -- porque ante un
    # documento rechazado hay que poder explicarle al autor por que, y porque
    # un falso positivo solo se corrige viendo que lo disparo.
    resultado_analisis_inyeccion: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, default=None
    )

    __table_args__ = (
        UniqueConstraint("document_id", "version", name="uq_knowledge_versions_document_version"),
        CheckConstraint("version > 0", name="version_positiva"),
        Index("ix_knowledge_versions_hash", "document_id", "hash_sha256"),
    )


# ---------------------------------------------------------------------------
#  Fragmentos
# ---------------------------------------------------------------------------
class KnowledgeChunk(Base, MezclaIdentificador):
    """Fragmento de texto recuperable, con sus metadatos de autorizacion.

    Esta es la tabla que consulta el RAG, y la unica. Todos los campos que
    deciden si un fragmento es visible estan aqui, sin uniones: ver la nota
    del encabezado del modulo.
    """

    __tablename__ = "knowledge_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column(Integer)
    indice_fragmento: Mapped[int] = mapped_column(Integer)
    contenido: Mapped[str] = mapped_column(Text)

    # Columna generada por el motor con la configuracion `espanol_sin_tildes`,
    # que aplica `unaccent` antes de la derivacion. Generada y no rellenada
    # por la aplicacion: asi no puede quedar desincronizada del contenido, y
    # una consulta directa a la base tampoco la deja inconsistente.
    contenido_tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('espanol_sin_tildes', contenido)", persisted=True),
    )
    tokens: Mapped[int] = mapped_column(SmallInteger, default=0)

    # --- Metadatos desnormalizados: el filtro de autorizacion (RF-N02) ---
    clinic_id: Mapped[uuid.UUID] = mapped_column()
    branch_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    specialty_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    service_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    professional_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(16))
    effective_from: Mapped[datetime | None] = mapped_column(default=None)
    effective_until: Mapped[datetime | None] = mapped_column(default=None)
    sensitivity_level: Mapped[str] = mapped_column(String(4), default="N1")
    # Solo la ultima version seleccionada para recuperacion puede aparecer al
    # agente. Evita que versiones historicas reaparezcan al aprobar el documento.
    vigente: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))

    creado_en: Mapped[datetime] = mapped_column(server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "version",
            "indice_fragmento",
            name="uq_knowledge_chunks_documento_version_indice",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'PENDING_REVIEW', 'APPROVED', 'PUBLISHED', 'ARCHIVED')",
            name="status_valido",
        ),
        CheckConstraint(
            "sensitivity_level IN ('N0', 'N1', 'N2', 'N3')",
            name="sensitivity_level_valido",
        ),
        CheckConstraint("length(contenido) > 0", name="contenido_no_vacio"),
        # =================================================================
        #  El indice del pre-filtro.
        #
        #  Es PARCIAL sobre los estados recuperables, que es lo que el RAG
        #  consulta siempre. La base de conocimiento crece con versiones
        #  antiguas y documentos archivados que nunca se recuperan; un indice
        #  completo cargaria con todos ellos.
        # =================================================================
        Index(
            "ix_knowledge_chunks_recuperables",
            "clinic_id",
            "status",
            "effective_from",
            "effective_until",
            postgresql_where=text("status IN ('APPROVED', 'PUBLISHED')"),
        ),
        Index("ix_knowledge_chunks_documento", "document_id", "version"),
        Index("ix_knowledge_chunks_documento_vigente", "document_id", "vigente", "status"),
        # Busqueda textual. El GIN sobre el `tsvector` es la mitad textual de
        # la busqueda hibrida (ADR-0013).
        Index(
            "ix_knowledge_chunks_tsv",
            "contenido_tsv",
            postgresql_using="gin",
        ),
    )


class KnowledgeEmbedding(Base, MezclaIdentificador):
    """Vector de un fragmento, con el modelo que lo genero.

    `modelo` y `dimension` se guardan explicitamente: un vector sin saber que
    modelo lo produjo es inservible en cuanto se cambie de modelo, y mezclar
    vectores de dos modelos en la misma busqueda da resultados sin sentido que
    **no fallan** -- simplemente son malos, que es peor.
    """

    __tablename__ = "knowledge_embeddings"

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_chunks.id", ondelete="CASCADE")
    )
    modelo: Mapped[str] = mapped_column(String(120))
    dimension: Mapped[int] = mapped_column(SmallInteger, default=DIMENSION_EMBEDDING)
    embedding: Mapped[list[float]] = mapped_column(Vector(DIMENSION_EMBEDDING))
    creado_en: Mapped[datetime] = mapped_column(server_default=text("now()"))

    __table_args__ = (
        # Un fragmento tiene un vector por modelo. Sin esta restriccion, un
        # reindexado a medias dejaria dos vectores del mismo modelo y el
        # fragmento aparecerìa duplicado en los resultados.
        UniqueConstraint("chunk_id", "modelo", name="uq_knowledge_embeddings_chunk_modelo"),
        CheckConstraint("dimension > 0", name="dimension_positiva"),
        # El indice HNSW con distancia coseno (ADR-0013). `m` y
        # `ef_construction` se dejan en los valores por defecto de pgvector:
        # ajustarlos sin medir sobre datos reales seria adivinar.
        Index(
            "ix_knowledge_embeddings_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


# ---------------------------------------------------------------------------
#  Permisos e ingesta
# ---------------------------------------------------------------------------
class KnowledgePermission(Base, MezclaIdentificador):
    """Permiso explicito sobre un documento.

    Separa `puede_leer` de `puede_usar_en_agente` a proposito: que el personal
    pueda consultar un protocolo interno no significa que el agente deba
    citarlo al responder a un paciente.
    """

    __tablename__ = "knowledge_permissions"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE")
    )
    principal_tipo: Mapped[str] = mapped_column(String(16))
    principal_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    puede_leer: Mapped[bool] = mapped_column(default=True)
    puede_usar_en_agente: Mapped[bool] = mapped_column(default=False)
    creado_en: Mapped[datetime] = mapped_column(server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "principal_tipo",
            "principal_id",
            name="uq_knowledge_permissions_documento_principal",
        ),
        CheckConstraint(
            "principal_tipo IN ('ROL', 'USUARIO', 'ESPECIALIDAD', 'SEDE')",
            name="principal_tipo_valido",
        ),
        Index("ix_knowledge_permissions_documento", "document_id"),
    )


class KnowledgeIngestionJob(Base, MezclaIdentificador):
    """Estado de la ingesta de una version.

    Existe como tabla y no como un campo de estado en la version porque la
    ingesta puede fallar a la mitad -- fragmentos generados, embeddings no --
    y hay que poder reanudarla sin volver a empezar ni duplicar fragmentos.
    """

    __tablename__ = "knowledge_ingestion_jobs"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(String(16), default=EstadoIngesta.PENDIENTE.value)
    paso_actual: Mapped[str | None] = mapped_column(String(32), default=None)
    fragmentos_generados: Mapped[int] = mapped_column(Integer, default=0)
    embeddings_generados: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    intentos: Mapped[int] = mapped_column(SmallInteger, default=0)
    creado_en: Mapped[datetime] = mapped_column(server_default=text("now()"))
    finalizado_en: Mapped[datetime | None] = mapped_column(default=None)

    __table_args__ = (
        UniqueConstraint(
            "document_id", "version", name="uq_knowledge_ingestion_jobs_documento_version"
        ),
        CheckConstraint(
            "estado IN ('PENDIENTE', 'EN_PROCESO', 'COMPLETADA', 'FALLIDA')",
            name="estado_valido",
        ),
        CheckConstraint("estado <> 'FALLIDA' OR error IS NOT NULL", name="fallida_con_error"),
        Index(
            "ix_knowledge_ingestion_pendientes",
            "creado_en",
            postgresql_where=text("estado IN ('PENDIENTE', 'EN_PROCESO')"),
        ),
    )


__all__ = [
    "DIMENSION_EMBEDDING",
    "ESTADOS_RECUPERABLES",
    "EstadoDocumento",
    "EstadoIngesta",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "KnowledgeEmbedding",
    "KnowledgeIngestionJob",
    "KnowledgePermission",
    "KnowledgeVersion",
    "PrincipalConocimiento",
    "TipoDocumentoConocimiento",
]
