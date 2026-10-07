"""Limita la recuperacion a la version vigente del documento."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_026"
down_revision: str | None = "20261006_025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_chunks",
        sa.Column("vigente", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.execute(
        "UPDATE knowledge_chunks AS fragmento "
        "SET vigente = (fragmento.version = documento.version_vigente) "
        "FROM knowledge_documents AS documento "
        "WHERE documento.id = fragmento.document_id"
    )
    op.create_index(
        "ix_knowledge_chunks_documento_vigente",
        "knowledge_chunks",
        ["document_id", "vigente", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_documento_vigente", table_name="knowledge_chunks")
    op.drop_column("knowledge_chunks", "vigente")
