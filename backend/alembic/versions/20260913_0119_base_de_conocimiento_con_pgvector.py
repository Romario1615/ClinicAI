"""Base de conocimiento: las seis tablas `knowledge_*` con pgvector.

Nombres en ingles por ser normativos (ADR-0015). Es la unica parte del esquema
donde ocurre.

Las tres cosas que esta migracion crea y que no son obvias
-----------------------------------------------------------
1. **`contenido_tsv` es una columna GENERADA** por el motor, con la
   configuracion `espanol_sin_tildes` que creo la migracion inicial (aplica
   `unaccent` antes de derivar). Generada y no rellenada por la aplicacion:
   asi no puede quedar desincronizada del contenido, ni siquiera si alguien
   escribe directamente en la base.

2. **El indice HNSW con `vector_cosine_ops`** es la mitad semantica de la
   busqueda hibrida (ADR-0013). `m=16` y `ef_construction=64` son los valores
   por defecto de pgvector: ajustarlos sin medir sobre datos reales seria
   adivinar.

3. **`ix_knowledge_chunks_recuperables` es PARCIAL** sobre `APPROVED` y
   `PUBLISHED`. La base de conocimiento crece con versiones antiguas y
   documentos archivados que el agente nunca recupera; un indice completo
   cargaria con todos ellos y se degradaria con el historico.

La desnormalizacion de `knowledge_chunks` -- repite `clinic_id`, `status`,
vigencia y `sensitivity_level` -- es deliberada y es lo que sostiene la
seguridad del RAG: permite que todo el filtro de autorizacion viva en un unico
`WHERE` sobre una sola tabla, sin uniones que se puedan omitir por error en
una consulta nueva.



Revision ID: 36c3ea203e25
Revises: c8c4f1a49870
Fecha: 2026-09-13 01:19:15.405954+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "36c3ea203e25"
down_revision: str | None = "c8c4f1a49870"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("titulo", sa.String(length=300), nullable=False),
        sa.Column("tipo", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("version_vigente", sa.Integer(), nullable=False),
        sa.Column("responsable_id", sa.Uuid(), nullable=True),
        sa.Column("aprobado_por", sa.Uuid(), nullable=True),
        sa.Column("aprobado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sensitivity_level", sa.String(length=4), nullable=False),
        sa.Column("etiquetas", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("specialty_id", sa.Uuid(), nullable=True),
        sa.Column("service_id", sa.Uuid(), nullable=True),
        sa.Column("archivado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "sensitivity_level IN ('N0', 'N1', 'N2', 'N3')",
            name=op.f("ck_knowledge_documents_sensitivity_level_valido"),
        ),
        sa.CheckConstraint(
            "status <> 'ARCHIVED' OR archivado_en IS NOT NULL",
            name=op.f("ck_knowledge_documents_archivado_con_fecha"),
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PENDING_REVIEW', 'APPROVED', 'PUBLISHED', 'ARCHIVED')",
            name=op.f("ck_knowledge_documents_status_valido"),
        ),
        sa.CheckConstraint(
            "status NOT IN ('APPROVED', 'PUBLISHED') OR (aprobado_por IS NOT NULL AND aprobado_en IS NOT NULL)",
            name=op.f("ck_knowledge_documents_aprobado_con_responsable"),
        ),
        sa.CheckConstraint(
            "status NOT IN ('APPROVED', 'PUBLISHED') OR version_vigente > 0",
            name=op.f("ck_knowledge_documents_aprobado_exige_version"),
        ),
        sa.CheckConstraint(
            "effective_until IS NULL OR effective_from IS NULL OR effective_until > effective_from",
            name=op.f("ck_knowledge_documents_vigencia_coherente"),
        ),
        sa.ForeignKeyConstraint(
            ["branch_id"],
            ["sede.id"],
            name=op.f("fk_knowledge_documents_branch_id_sede"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinica.id"],
            name=op.f("fk_knowledge_documents_clinic_id_clinica"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["servicio.id"],
            name=op.f("fk_knowledge_documents_service_id_servicio"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["specialty_id"],
            ["especialidad.id"],
            name=op.f("fk_knowledge_documents_specialty_id_especialidad"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_documents")),
    )
    op.create_index(
        "ix_knowledge_documents_alcance",
        "knowledge_documents",
        ["clinic_id", "branch_id", "specialty_id"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_documents_clinica",
        "knowledge_documents",
        ["clinic_id", "status"],
        unique=False,
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("indice_fragmento", sa.Integer(), nullable=False),
        sa.Column("contenido", sa.Text(), nullable=False),
        sa.Column(
            "contenido_tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('espanol_sin_tildes', contenido)", persisted=True),
            nullable=False,
        ),
        sa.Column("tokens", sa.SmallInteger(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("specialty_id", sa.Uuid(), nullable=True),
        sa.Column("service_id", sa.Uuid(), nullable=True),
        sa.Column("professional_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sensitivity_level", sa.String(length=4), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "sensitivity_level IN ('N0', 'N1', 'N2', 'N3')",
            name=op.f("ck_knowledge_chunks_sensitivity_level_valido"),
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PENDING_REVIEW', 'APPROVED', 'PUBLISHED', 'ARCHIVED')",
            name=op.f("ck_knowledge_chunks_status_valido"),
        ),
        sa.CheckConstraint(
            "length(contenido) > 0", name=op.f("ck_knowledge_chunks_contenido_no_vacio")
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name=op.f("fk_knowledge_chunks_document_id_knowledge_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_chunks")),
        sa.UniqueConstraint(
            "document_id",
            "version",
            "indice_fragmento",
            name="uq_knowledge_chunks_documento_version_indice",
        ),
    )
    op.create_index(
        "ix_knowledge_chunks_documento",
        "knowledge_chunks",
        ["document_id", "version"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_chunks_recuperables",
        "knowledge_chunks",
        ["clinic_id", "status", "effective_from", "effective_until"],
        unique=False,
        postgresql_where=sa.text("status IN ('APPROVED', 'PUBLISHED')"),
    )
    op.create_index(
        "ix_knowledge_chunks_tsv",
        "knowledge_chunks",
        ["contenido_tsv"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_table(
        "knowledge_ingestion_jobs",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(length=16), nullable=False),
        sa.Column("paso_actual", sa.String(length=32), nullable=True),
        sa.Column("fragmentos_generados", sa.Integer(), nullable=False),
        sa.Column("embeddings_generados", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("intentos", sa.SmallInteger(), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("finalizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "estado <> 'FALLIDA' OR error IS NOT NULL",
            name=op.f("ck_knowledge_ingestion_jobs_fallida_con_error"),
        ),
        sa.CheckConstraint(
            "estado IN ('PENDIENTE', 'EN_PROCESO', 'COMPLETADA', 'FALLIDA')",
            name=op.f("ck_knowledge_ingestion_jobs_estado_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name=op.f("fk_knowledge_ingestion_jobs_document_id_knowledge_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_ingestion_jobs")),
        sa.UniqueConstraint(
            "document_id", "version", name="uq_knowledge_ingestion_jobs_documento_version"
        ),
    )
    op.create_index(
        "ix_knowledge_ingestion_pendientes",
        "knowledge_ingestion_jobs",
        ["creado_en"],
        unique=False,
        postgresql_where=sa.text("estado IN ('PENDIENTE', 'EN_PROCESO')"),
    )
    op.create_table(
        "knowledge_permissions",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("principal_tipo", sa.String(length=16), nullable=False),
        sa.Column("principal_id", sa.Uuid(), nullable=True),
        sa.Column("puede_leer", sa.Boolean(), nullable=False),
        sa.Column("puede_usar_en_agente", sa.Boolean(), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "principal_tipo IN ('ROL', 'USUARIO', 'ESPECIALIDAD', 'SEDE')",
            name=op.f("ck_knowledge_permissions_principal_tipo_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name=op.f("fk_knowledge_permissions_document_id_knowledge_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_permissions")),
        sa.UniqueConstraint(
            "document_id",
            "principal_tipo",
            "principal_id",
            name="uq_knowledge_permissions_documento_principal",
        ),
    )
    op.create_index(
        "ix_knowledge_permissions_documento", "knowledge_permissions", ["document_id"], unique=False
    )
    op.create_table(
        "knowledge_versions",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("nombre_archivo", sa.String(length=255), nullable=True),
        sa.Column("hash_sha256", sa.String(length=64), nullable=False),
        sa.Column("ruta_almacenamiento", sa.Text(), nullable=True),
        sa.Column("autor_id", sa.Uuid(), nullable=True),
        sa.Column("notas_cambio", sa.Text(), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "resultado_analisis_inyeccion", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint("version > 0", name=op.f("ck_knowledge_versions_version_positiva")),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name=op.f("fk_knowledge_versions_document_id_knowledge_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_versions")),
        sa.UniqueConstraint(
            "document_id", "version", name="uq_knowledge_versions_document_version"
        ),
    )
    op.create_index(
        "ix_knowledge_versions_hash",
        "knowledge_versions",
        ["document_id", "hash_sha256"],
        unique=False,
    )
    op.create_table(
        "knowledge_embeddings",
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("modelo", sa.String(length=120), nullable=False),
        sa.Column("dimension", sa.SmallInteger(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "dimension > 0", name=op.f("ck_knowledge_embeddings_dimension_positiva")
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["knowledge_chunks.id"],
            name=op.f("fk_knowledge_embeddings_chunk_id_knowledge_chunks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_embeddings")),
        sa.UniqueConstraint("chunk_id", "modelo", name="uq_knowledge_embeddings_chunk_modelo"),
    )
    op.create_index(
        "ix_knowledge_embeddings_hnsw",
        "knowledge_embeddings",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_embeddings_hnsw",
        table_name="knowledge_embeddings",
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_table("knowledge_embeddings")
    op.drop_index("ix_knowledge_versions_hash", table_name="knowledge_versions")
    op.drop_table("knowledge_versions")
    op.drop_index("ix_knowledge_permissions_documento", table_name="knowledge_permissions")
    op.drop_table("knowledge_permissions")
    op.drop_index(
        "ix_knowledge_ingestion_pendientes",
        table_name="knowledge_ingestion_jobs",
        postgresql_where=sa.text("estado IN ('PENDIENTE', 'EN_PROCESO')"),
    )
    op.drop_table("knowledge_ingestion_jobs")
    op.drop_index("ix_knowledge_chunks_tsv", table_name="knowledge_chunks", postgresql_using="gin")
    op.drop_index(
        "ix_knowledge_chunks_recuperables",
        table_name="knowledge_chunks",
        postgresql_where=sa.text("status IN ('APPROVED', 'PUBLISHED')"),
    )
    op.drop_index("ix_knowledge_chunks_documento", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index("ix_knowledge_documents_clinica", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_alcance", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
