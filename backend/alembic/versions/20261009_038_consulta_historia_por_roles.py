"""Consulta clínica compartida N2 para los roles base, sin escritura.

Conserva las asignaciones anteriores para una reversión exacta. Los roles
personalizados y la lectura sensible N3 mantienen sus permisos existentes.
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261009_038"
down_revision: str | None = "20261009_037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COMPARTIDA = "historia_clinica.consultar_compartida"
LECTURAS = (
    COMPARTIDA,
    "historia_clinica.leer",
    "historia_clinica.leer_metadatos",
    "receta.leer",
    "imagen_clinica.leer",
    "odontograma.leer",
    "plan_tratamiento.leer",
)
ROLES = (
    "superadministrador",
    "administrador_clinica",
    "recepcion",
    "profesional",
    "asistente",
    "auditor",
)
RESPALDO = "respaldo_consulta_roles_20261009"


def upgrade() -> None:
    conexion = op.get_bind()
    conexion.execute(
        sa.text("""
        INSERT INTO permiso (id, codigo, descripcion, categoria,
                             requiere_relacion_asistencial, nivel_sensibilidad)
        VALUES (:id, :codigo, :descripcion, 'clinico', false, 'N2')
        ON CONFLICT (codigo) DO NOTHING
    """),
        {
            "id": uuid.uuid4(),
            "codigo": COMPARTIDA,
            "descripcion": "Consultar historia N2 y herramientas de las especialidades autorizadas",
        },
    )
    op.create_table(
        RESPALDO,
        sa.Column("rol_id", sa.Uuid(), primary_key=True),
        sa.Column("permiso_id", sa.Uuid(), primary_key=True),
        sa.Column("existia", sa.Boolean(), nullable=False),
    )
    consulta = sa.text("""
        INSERT INTO respaldo_consulta_roles_20261009 (rol_id, permiso_id, existia)
        SELECT r.id, p.id, rp.rol_id IS NOT NULL
        FROM rol r CROSS JOIN permiso p
        LEFT JOIN rol_permiso rp ON rp.rol_id = r.id AND rp.permiso_id = p.id
        WHERE r.es_sistema AND r.clinica_id IS NULL AND r.codigo IN :roles
          AND (p.codigo IN :lecturas OR (r.codigo = 'asistente' AND p.codigo = 'imagen_clinica.cargar'))
    """).bindparams(sa.bindparam("roles", expanding=True), sa.bindparam("lecturas", expanding=True))
    conexion.execute(consulta, {"roles": ROLES, "lecturas": LECTURAS})
    conexion.execute(
        sa.text("""
        INSERT INTO rol_permiso (rol_id, permiso_id)
        SELECT b.rol_id, b.permiso_id FROM respaldo_consulta_roles_20261009 b
        JOIN permiso p ON p.id = b.permiso_id WHERE p.codigo != 'imagen_clinica.cargar'
        ON CONFLICT DO NOTHING
    """)
    )
    conexion.execute(
        sa.text("""
        DELETE FROM rol_permiso rp USING respaldo_consulta_roles_20261009 b, permiso p
        WHERE rp.rol_id = b.rol_id AND rp.permiso_id = b.permiso_id
          AND p.id = b.permiso_id AND p.codigo = 'imagen_clinica.cargar'
    """)
    )


def downgrade() -> None:
    conexion = op.get_bind()
    conexion.execute(
        sa.text("""
        DELETE FROM rol_permiso rp USING respaldo_consulta_roles_20261009 b
        WHERE rp.rol_id = b.rol_id AND rp.permiso_id = b.permiso_id
    """)
    )
    conexion.execute(
        sa.text("""
        INSERT INTO rol_permiso (rol_id, permiso_id)
        SELECT rol_id, permiso_id FROM respaldo_consulta_roles_20261009 WHERE existia
        ON CONFLICT DO NOTHING
    """)
    )
    op.drop_table(RESPALDO)
    conexion.execute(
        sa.text("""
        DELETE FROM permiso p WHERE p.codigo = :codigo
          AND NOT EXISTS (SELECT 1 FROM rol_permiso rp WHERE rp.permiso_id = p.id)
    """),
        {"codigo": COMPARTIDA},
    )
