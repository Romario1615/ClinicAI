"""Modelos de pacientes, contactos, consentimientos y documentos.

Decision central: **el numero de WhatsApp no identifica al paciente para
efectos clinicos.**

Un telefono puede ser familiar (una madre gestiona las citas de tres hijos),
prestado, robado o reasignado por la operadora a otra persona.  Por eso:

* `telefono_whatsapp` tiene indice **no unico**;
* el acceso a informacion clinica exige `nivel_verificacion >= DOCUMENTO`;
* la identidad se puede resolver por telefono para tareas administrativas
  («que citas tengo»), pero no para datos de salud.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ColumnElement,
    Date,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    literal_column,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.nucleo.bd import Base, MezclaAnulacion, MezclaAuditoria, MezclaIdentificador


class TipoDocumento(StrEnum):
    CEDULA = "CEDULA"
    PASAPORTE = "PASAPORTE"
    RUC = "RUC"
    # Para menores sin documento propio o pacientes sin documentacion.
    SIN_DOCUMENTO = "SIN_DOCUMENTO"


class TipoConsentimiento(StrEnum):
    TRATAMIENTO_DATOS = "TRATAMIENTO_DATOS"
    COMUNICACION_WHATSAPP = "COMUNICACION_WHATSAPP"
    RECORDATORIOS_MEDICACION = "RECORDATORIOS_MEDICACION"
    COMPARTIR_CON_TERCEROS = "COMPARTIR_CON_TERCEROS"


class EstadoEscaneoAntivirus(StrEnum):
    PENDIENTE = "PENDIENTE"
    LIMPIO = "LIMPIO"
    INFECTADO = "INFECTADO"
    # El analisis no estuvo disponible.  Se registra de forma explicita en
    # lugar de asumir que el archivo esta limpio: en produccion la carga se
    # rechaza, en desarrollo se deja constancia de la limitacion.
    NO_DISPONIBLE = "NO_DISPONIBLE"


class SeveridadAlergia(StrEnum):
    LEVE = "LEVE"
    MODERADA = "MODERADA"
    GRAVE = "GRAVE"
    ANAFILAXIA = "ANAFILAXIA"


# ---------------------------------------------------------------------------
#  Paciente
# ---------------------------------------------------------------------------
class Paciente(Base, MezclaIdentificador, MezclaAuditoria, MezclaAnulacion):
    __tablename__ = "paciente"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))

    tipo_documento: Mapped[str] = mapped_column(String(16), default=TipoDocumento.CEDULA.value)
    numero_documento: Mapped[str | None] = mapped_column(String(32), default=None)

    nombre: Mapped[str] = mapped_column(String(100))
    apellido: Mapped[str] = mapped_column(String(100))
    fecha_nacimiento: Mapped[date | None] = mapped_column(Date, default=None)
    sexo: Mapped[str | None] = mapped_column(String(16), default=None)

    telefono_whatsapp: Mapped[str | None] = mapped_column(String(32), default=None)
    whatsapp_verificado_en: Mapped[datetime | None] = mapped_column(default=None)
    correo: Mapped[str | None] = mapped_column(String(200), default=None)
    direccion: Mapped[str | None] = mapped_column(Text, default=None)

    # Preferencias para la lista de espera: dias y franjas que le convienen.
    preferencias_horario: Mapped[dict[str, object] | None] = mapped_column(JSONB, default=None)

    # Grado de certeza sobre la identidad.  Es lo que decide si se puede
    # entregar informacion clinica por un canal remoto.
    nivel_verificacion: Mapped[str] = mapped_column(String(16), default="NO_VERIFICADO")
    verificado_por: Mapped[uuid.UUID | None] = mapped_column(default=None)
    verificado_en: Mapped[datetime | None] = mapped_column(default=None)

    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    contactos: Mapped[list[PacienteContacto]] = relationship(
        back_populates="paciente", lazy="raise"
    )
    consentimientos: Mapped[list[Consentimiento]] = relationship(
        back_populates="paciente", lazy="raise"
    )

    __table_args__ = (
        # Unicidad por documento.  Indice PARCIAL: los pacientes sin
        # documento (menores, indocumentados) tendrian numero_documento nulo,
        # y en PostgreSQL los nulos no colisionan, pero la clausula explicita
        # deja la intencion clara y evita un indice inutil sobre nulos.
        Index(
            "ix_paciente_documento",
            "clinica_id",
            "tipo_documento",
            "numero_documento",
            unique=True,
            postgresql_where=text("numero_documento IS NOT NULL"),
        ),
        # Indice NO unico a proposito: un telefono familiar puede
        # corresponder a varias personas.  Hacerlo unico obligaria a inventar
        # numeros para los hijos, que es peor.
        Index("ix_paciente_whatsapp", "clinica_id", "telefono_whatsapp"),
        # =================================================================
        #  Indice FUNCIONAL sobre el numero normalizado.
        #
        #  Existe porque la columna guarda el numero tal como lo escribio el
        #  personal -- «+593 99 900 0333» es lo legible en un panel -- y el
        #  webhook de WhatsApp entrega «593999000333», solo digitos.  Comparar
        #  las dos formas literalmente no encuentra al paciente.
        #
        #  Eso se descubrio ejerciendo el sistema: un paciente que respondia
        #  BAJA no quedaba dado de baja, porque la revocacion no encontraba a
        #  quien revocar, y el sistema le seguia escribiendo.  Era el fallo
        #  exacto que ADR-0017 dice que no puede ocurrir.
        #
        #  Se resuelve normalizando en el `WHERE`, y este indice es lo que
        #  impide que esa normalizacion obligue a recorrer la tabla en cada
        #  mensaje entrante.  `regexp_replace` es IMMUTABLE, asi que se puede
        #  indexar.
        # =================================================================
        Index(
            "ix_paciente_whatsapp_normalizado",
            "clinica_id",
            text(r"regexp_replace(telefono_whatsapp, '\D', '', 'g')"),
            postgresql_where=text("telefono_whatsapp IS NOT NULL"),
        ),
        Index("ix_paciente_apellido", "clinica_id", "apellido", "nombre"),
        CheckConstraint(
            "nivel_verificacion IN ('NO_VERIFICADO', 'TELEFONO', 'DOCUMENTO', 'PRESENCIAL')",
            name="nivel_verificacion_valido",
        ),
        CheckConstraint(
            "tipo_documento IN ('CEDULA', 'PASAPORTE', 'RUC', 'SIN_DOCUMENTO')",
            name="tipo_documento_valido",
        ),
        # Un tipo de documento distinto de SIN_DOCUMENTO exige el numero.
        CheckConstraint(
            "tipo_documento = 'SIN_DOCUMENTO' OR numero_documento IS NOT NULL",
            name="documento_exige_numero",
        ),
        # Una fecha de nacimiento futura es un error de captura.
        CheckConstraint(
            "fecha_nacimiento IS NULL OR fecha_nacimiento <= CURRENT_DATE",
            name="nacimiento_no_futuro",
        ),
        # Un nivel de verificacion por documento exige saber quien lo hizo.
        CheckConstraint(
            "nivel_verificacion IN ('NO_VERIFICADO', 'TELEFONO') OR verificado_en IS NOT NULL",
            name="verificacion_con_trazabilidad",
        ),
    )

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombre} {self.apellido}"


class PacienteContacto(Base, MezclaIdentificador, MezclaAuditoria):
    """Persona de contacto del paciente.

    `autorizado_a_recibir_informacion` es un dato de privacidad, no de
    comodidad: sin el, una llamada de un familiar preguntando por el
    diagnostico deja al personal sin criterio para decidir.
    """

    __tablename__ = "paciente_contacto"

    paciente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paciente.id", ondelete="CASCADE"))
    nombre: Mapped[str] = mapped_column(String(200))
    relacion: Mapped[str | None] = mapped_column(String(50), default=None)
    telefono: Mapped[str | None] = mapped_column(String(32), default=None)
    correo: Mapped[str | None] = mapped_column(String(200), default=None)
    es_emergencia: Mapped[bool] = mapped_column(Boolean, default=False)
    autorizado_a_recibir_informacion: Mapped[bool] = mapped_column(Boolean, default=False)

    paciente: Mapped[Paciente] = relationship(back_populates="contactos", lazy="raise")

    __table_args__ = (
        Index(
            "ix_contacto_emergencia",
            "paciente_id",
            postgresql_where=text("es_emergencia"),
        ),
    )


# ---------------------------------------------------------------------------
#  Consentimientos
# ---------------------------------------------------------------------------
class Consentimiento(Base, MezclaIdentificador, MezclaAuditoria):
    """Consentimiento otorgado o revocado, con evidencia.

    Se guarda el hash del texto que el paciente acepto, no solo su version.
    Ante una reclamacion la pregunta es «que texto exacto acepto», y una
    version sin hash no prueba que el texto no cambiara despues.

    La revocacion **no borra la fila**: se marca `revocado_en`.  Hay que poder
    demostrar que hubo consentimiento durante el periodo en que se enviaron
    los mensajes.
    """

    __tablename__ = "consentimiento"

    paciente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paciente.id", ondelete="CASCADE"))
    tipo: Mapped[str] = mapped_column(String(32))
    otorgado: Mapped[bool] = mapped_column(Boolean)
    version_texto: Mapped[str] = mapped_column(String(32))
    texto_hash: Mapped[str] = mapped_column(String(64))
    canal: Mapped[str] = mapped_column(String(16))
    otorgado_en: Mapped[datetime] = mapped_column(server_default=text("now()"))
    revocado_en: Mapped[datetime | None] = mapped_column(default=None)
    # Evidencia: identificador del mensaje de WhatsApp donde acepto, o del
    # usuario que lo registro en el panel.
    evidencia: Mapped[dict[str, object] | None] = mapped_column(JSONB, default=None)

    paciente: Mapped[Paciente] = relationship(back_populates="consentimientos", lazy="raise")

    __table_args__ = (
        CheckConstraint(
            "tipo IN ('TRATAMIENTO_DATOS', 'COMUNICACION_WHATSAPP', "
            "'RECORDATORIOS_MEDICACION', 'COMPARTIR_CON_TERCEROS')",
            name="tipo_valido",
        ),
        CheckConstraint(
            "canal IN ('PANEL', 'WHATSAPP', 'PRESENCIAL', 'CORREO')",
            name="canal_valido",
        ),
        # Consulta del camino caliente: antes de cada envio proactivo hay que
        # comprobar el consentimiento vigente.  Indice parcial sobre los
        # vigentes, que son los unicos que se consultan.
        Index(
            "ix_consentimiento_vigente",
            "paciente_id",
            "tipo",
            postgresql_where=text("revocado_en IS NULL"),
        ),
    )

    def esta_vigente(self) -> bool:
        return self.otorgado and self.revocado_en is None


# ---------------------------------------------------------------------------
#  Documentos del paciente
# ---------------------------------------------------------------------------
class DocumentoPaciente(Base, MezclaIdentificador, MezclaAuditoria, MezclaAnulacion):
    """Archivo aportado por o para el paciente.

    `hash_sha256` permite detectar duplicados y verificar integridad.
    `tipo_mime` se determina por el **contenido** del archivo, no por su
    extension: renombrar un ejecutable a `.pdf` es el ataque mas basico de
    subida de archivos.
    """

    __tablename__ = "documento_paciente"

    paciente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paciente.id", ondelete="RESTRICT"))
    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    tipo: Mapped[str] = mapped_column(String(32))
    nombre_archivo: Mapped[str] = mapped_column(String(255))
    ruta_almacenamiento: Mapped[str] = mapped_column(String(512))
    tipo_mime: Mapped[str] = mapped_column(String(100))
    tamano_bytes: Mapped[int] = mapped_column(BigInteger)
    hash_sha256: Mapped[str] = mapped_column(String(64))
    subido_por: Mapped[uuid.UUID | None] = mapped_column(default=None)
    escaneo_antivirus: Mapped[str] = mapped_column(String(16), default="PENDIENTE")
    escaneo_en: Mapped[datetime | None] = mapped_column(default=None)
    # Nivel de sensibilidad del contenido; controla quien puede descargarlo.
    nivel_sensibilidad: Mapped[str] = mapped_column(String(4), default="N2")

    __table_args__ = (
        CheckConstraint("tamano_bytes > 0", name="tamano_positivo"),
        CheckConstraint(
            "escaneo_antivirus IN ('PENDIENTE', 'LIMPIO', 'INFECTADO', 'NO_DISPONIBLE')",
            name="escaneo_valido",
        ),
        CheckConstraint("nivel_sensibilidad IN ('N0', 'N1', 'N2', 'N3')", name="nivel_valido"),
        Index("ix_documento_paciente", "paciente_id", "tipo"),
        # Deteccion de duplicados por contenido.
        Index("ix_documento_hash", "clinica_id", "hash_sha256"),
        # Cola de analisis antivirus pendiente.
        Index(
            "ix_documento_escaneo_pendiente",
            "escaneo_antivirus",
            postgresql_where=text("escaneo_antivirus = 'PENDIENTE'"),
        ),
    )


# ---------------------------------------------------------------------------
#  Alergias y antecedentes
# ---------------------------------------------------------------------------
class Alergia(Base, MezclaIdentificador, MezclaAuditoria):
    """Alergia registrada por un profesional.

    No es un campo libre del paciente: una alergia mal registrada puede
    causar dano.  Solo un profesional la crea, y se conserva quien y cuando
    incluso si despues se desactiva.
    """

    __tablename__ = "alergia"

    paciente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paciente.id", ondelete="CASCADE"))
    sustancia: Mapped[str] = mapped_column(String(200))
    tipo_reaccion: Mapped[str | None] = mapped_column(String(200), default=None)
    severidad: Mapped[str] = mapped_column(String(16), default=SeveridadAlergia.LEVE.value)
    registrado_por: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profesional.id", ondelete="RESTRICT")
    )
    registrado_en: Mapped[datetime] = mapped_column(server_default=text("now()"))
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    desactivada_por: Mapped[uuid.UUID | None] = mapped_column(default=None)
    desactivada_en: Mapped[datetime | None] = mapped_column(default=None)
    motivo_desactivacion: Mapped[str | None] = mapped_column(Text, default=None)

    __table_args__ = (
        CheckConstraint(
            "severidad IN ('LEVE', 'MODERADA', 'GRAVE', 'ANAFILAXIA')",
            name="severidad_valida",
        ),
        CheckConstraint(
            "activa OR motivo_desactivacion IS NOT NULL",
            name="desactivacion_con_motivo",
        ),
        Index(
            "ix_alergia_activa",
            "paciente_id",
            postgresql_where=text("activa"),
        ),
    )


class Antecedente(Base, MezclaIdentificador, MezclaAuditoria):
    """Antecedente personal, familiar, quirurgico u otro."""

    __tablename__ = "antecedente"

    paciente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paciente.id", ondelete="CASCADE"))
    categoria: Mapped[str] = mapped_column(String(32))
    descripcion: Mapped[str] = mapped_column(Text)
    registrado_por: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profesional.id", ondelete="RESTRICT")
    )
    registrado_en: Mapped[datetime] = mapped_column(server_default=text("now()"))
    nivel_sensibilidad: Mapped[str] = mapped_column(String(4), default="N2")

    __table_args__ = (
        CheckConstraint(
            "categoria IN ('PERSONAL', 'FAMILIAR', 'QUIRURGICO', "
            "'FARMACOLOGICO', 'HABITOS', 'OTRO')",
            name="categoria_valida",
        ),
        CheckConstraint("nivel_sensibilidad IN ('N0', 'N1', 'N2', 'N3')", name="nivel_valido"),
        Index("ix_antecedente_paciente", "paciente_id", "categoria"),
    )


# ---------------------------------------------------------------------------
#  Relacion asistencial
# ---------------------------------------------------------------------------
class RelacionAsistencial(Base, MezclaIdentificador, MezclaAuditoria):
    """Vinculo entre un profesional y un paciente.

    Es lo que convierte «tengo el permiso de leer historias clinicas» en
    «puedo leer LA historia de ESTE paciente».  Sin esta tabla, cualquier
    profesional de la clinica podria abrir cualquier historia, que es
    exactamente lo que la matriz de permisos pretende evitar.

    Se crea de forma automatica al agendar una cita y se puede crear de forma
    explicita en una derivacion o al asignar un paciente.  El acceso de
    emergencia genera una relacion temporal con caducidad.
    """

    __tablename__ = "relacion_asistencial"

    paciente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paciente.id", ondelete="CASCADE"))
    profesional_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profesional.id", ondelete="CASCADE")
    )
    origen: Mapped[str] = mapped_column(String(24))
    cita_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    # Las relaciones de emergencia caducan; las asistenciales normales no.
    vigente_hasta: Mapped[datetime | None] = mapped_column(default=None)
    # Obligatorio en el acceso de emergencia: sin motivo escrito no se
    # concede, y queda registrado para revision posterior.
    motivo: Mapped[str | None] = mapped_column(Text, default=None)
    revocada_en: Mapped[datetime | None] = mapped_column(default=None)

    __table_args__ = (
        CheckConstraint(
            "origen IN ('CITA', 'ASIGNACION', 'DERIVACION', 'EMERGENCIA')",
            name="origen_valido",
        ),
        # El acceso de emergencia exige motivo y caducidad.  Sin esto, seria
        # una puerta trasera permanente con apariencia de excepcion.
        CheckConstraint(
            "origen <> 'EMERGENCIA' OR (motivo IS NOT NULL AND vigente_hasta IS NOT NULL)",
            name="emergencia_exige_motivo_y_caducidad",
        ),
        # Consulta del camino caliente de toda lectura clinica.
        Index(
            "ix_relacion_vigente",
            "paciente_id",
            "profesional_id",
            postgresql_where=text("revocada_en IS NULL"),
        ),
        Index("ix_relacion_profesional", "profesional_id"),
    )

    def esta_vigente(self, ahora: datetime) -> bool:
        if self.revocada_en is not None:
            return False
        return self.vigente_hasta is None or self.vigente_hasta > ahora


def telefono_normalizado() -> ColumnElement[str]:
    r"""Expresion SQL del numero de WhatsApp reducido a digitos.

    La usan a la vez el indice funcional y las consultas que resuelven un
    numero entrante.  Vive en una sola funcion a proposito: si la expresion
    del indice y la de la consulta divergieran aunque sea en un espacio,
    PostgreSQL dejaria de usar el indice y nadie lo notaria hasta que la
    tabla creciera.

    Los tres argumentos del patron van como `literal_column` y no como
    parametros enlazados, y esto es lo que decide que el indice sirva:
    PostgreSQL empareja una expresion indexada de forma **estructural**, y
    `regexp_replace(col, $1, $2, $3)` no es la misma expresion que
    `regexp_replace(col, '\D', '', 'g')`.  Con parametros, el indice existe y
    no se usa.  No hay riesgo de inyeccion: son constantes del codigo, y el
    valor que se compara si es un parametro enlazado.
    """
    return func.regexp_replace(
        Paciente.telefono_whatsapp,
        literal_column(r"'\D'"),
        literal_column("''"),
        literal_column("'g'"),
    )
