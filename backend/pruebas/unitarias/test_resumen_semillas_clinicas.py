"""El resumen incluye las recetas adicionales del escenario de acceso local."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.nucleo.reloj import RelojFijo
from app.semillas import clinico
from pruebas.conftest import INSTANTE_REFERENCIA

pytestmark = [pytest.mark.unitaria, pytest.mark.asyncio]


@pytest.mark.parametrize("ya_sembrado", [True, False])
async def test_resumen_incluye_receta_confirmacion_y_tomas_adicionales(
    monkeypatch: pytest.MonkeyPatch, ya_sembrado: bool
) -> None:
    monkeypatch.setattr(clinico, "_ya_sembrado", AsyncMock(return_value=ya_sembrado))
    monkeypatch.setattr(
        clinico,
        "_asegurar_historico_acceso_local",
        AsyncMock(return_value=clinico.ResumenClinico(notas=1, correcciones=1)),
    )
    monkeypatch.setattr(
        clinico,
        "_sembrar_caso_adherencia",
        AsyncMock(
            return_value=clinico.ResumenClinico(recetas=1, confirmadas=1, suspendidas=1, tomas=5)
        ),
    )
    monkeypatch.setattr(clinico, "_parejas", AsyncMock(return_value=[(uuid.uuid4(), uuid.uuid4())]))
    base = clinico.ResumenClinico(notas=1, recetas=2, confirmadas=1, tomas=7)
    monkeypatch.setattr(clinico, "_sembrar_pareja", AsyncMock(return_value=base))
    resumen = await clinico.cargar_clinico(
        MagicMock(spec=AsyncSession), clinica_id=uuid.uuid4(), reloj=RelojFijo(INSTANTE_REFERENCIA)
    )
    assert resumen == (
        clinico.ResumenClinico(
            notas=1, correcciones=1, recetas=1, confirmadas=1, suspendidas=1, tomas=5
        )
        if ya_sembrado
        else clinico.ResumenClinico(
            notas=2, correcciones=1, recetas=3, confirmadas=2, suspendidas=1, tomas=12
        )
    )
