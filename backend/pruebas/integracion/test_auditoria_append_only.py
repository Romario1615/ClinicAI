"""La tabla de auditoría rechaza cambios SQL directos en PostgreSQL."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.integracion, pytest.mark.asyncio]


async def _insertar_evento(sesion: AsyncSession) -> uuid.UUID:
    resultado = await sesion.execute(
        sa.text(
            "INSERT INTO auditoria (accion, actor_tipo, resultado, origen) "
            "VALUES (:accion, 'USUARIO', 'EXITO', 'API') RETURNING id"
        ),
        {"accion": f"prueba.append_only.{uuid.uuid4().hex}"},
    )
    return resultado.scalar_one()


def _afirmar_denegacion_por_trigger(error: DBAPIError) -> None:
    assert getattr(error.orig, "sqlstate", None) == "42501"
    assert "solo insercion" in str(error.orig)


async def test_postgresql_impide_actualizar_auditoria_con_sql_directo(
    sesion: AsyncSession,
) -> None:
    identificador = await _insertar_evento(sesion)

    with pytest.raises(DBAPIError) as error:
        await sesion.execute(
            sa.text("UPDATE auditoria SET resultado = 'DENEGADO' WHERE id = :id"),
            {"id": identificador},
        )

    _afirmar_denegacion_por_trigger(error.value)


async def test_postgresql_impide_borrar_auditoria_con_sql_directo(
    sesion: AsyncSession,
) -> None:
    identificador = await _insertar_evento(sesion)

    with pytest.raises(DBAPIError) as error:
        await sesion.execute(sa.text("DELETE FROM auditoria WHERE id = :id"), {"id": identificador})

    _afirmar_denegacion_por_trigger(error.value)


async def test_postgresql_impide_vaciar_auditoria_con_truncate(
    sesion: AsyncSession,
) -> None:
    with pytest.raises(DBAPIError) as error:
        await sesion.execute(sa.text("TRUNCATE TABLE auditoria"))

    _afirmar_denegacion_por_trigger(error.value)
