"""Validación de los campos estructurados del Formulario 033/2021."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modulos.odontologia.formulario_033_esquemas import Formulario033Datos

pytestmark = pytest.mark.unitaria

REGIONES = (
    "LABIOS",
    "MEJILLAS",
    "MAXILAR_SUPERIOR",
    "MAXILAR_INFERIOR",
    "LENGUA",
    "PALADAR",
    "PISO_DE_LA_BOCA",
    "CARRILLOS",
    "GLANDULAS_SALIVALES",
    "OROFARINGE",
    "ATM",
    "GANGLIOS",
    "OTROS",
)
PIEZAS_SIMPLIFICADO = (16, 17, 55, 11, 21, 51, 26, 27, 65, 36, 37, 75, 31, 41, 71, 46, 47, 85)


def _datos(**cambios: object) -> dict[str, object]:
    datos: dict[str, object] = {
        "motivo_consulta": "Dolor al masticar",
        "constantes_vitales": {},
        "examen_estomatognatico": [
            {"region": region, "hallazgo": "SIN_HALLAZGO"} for region in REGIONES
        ],
        "indicadores_salud_bucal": {"sitios": [{"pieza": pieza} for pieza in PIEZAS_SIMPLIFICADO]},
        "indices_cpo_ceo": {},
    }
    datos.update(cambios)
    return datos


def test_acepta_y_serializa_una_captura_completa() -> None:
    formulario = Formulario033Datos.model_validate(_datos(embarazada=False))

    salida = formulario.model_dump(mode="json")

    assert salida["motivo_consulta"] == "Dolor al masticar"
    assert len(salida["examen_estomatognatico"]) == 13
    assert len(salida["indicadores_salud_bucal"]["sitios"]) == 18
    assert salida["embarazada"] is False


@pytest.mark.parametrize(
    "cambios",
    [
        {"motivo_consulta": " "},
        {"campo_no_permitido": "no debe guardarse"},
        {
            "examen_estomatognatico": [
                {"region": "LABIOS", "hallazgo": "PATOLOGIA"},
                *[{"region": region, "hallazgo": "SIN_HALLAZGO"} for region in REGIONES[1:]],
            ]
        },
        {
            "antecedentes_familiares": [
                {"codigo": "ASMA", "presente": True},
            ]
        },
        {"indices_cpo_ceo": {"permanentes_d": 20, "permanentes_c": 20}},
        {"indicadores_salud_bucal": {"sitios": [{"pieza": 16} for _ in PIEZAS_SIMPLIFICADO]}},
    ],
)
def test_rechaza_datos_ambiguos_o_fuera_del_catalogo(cambios: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Formulario033Datos.model_validate(_datos(**cambios))


def test_una_patologia_requiere_descripcion() -> None:
    examen = [{"region": region, "hallazgo": "SIN_HALLAZGO"} for region in REGIONES[1:]]
    examen.append({"region": "LABIOS", "hallazgo": "PATOLOGIA"})

    with pytest.raises(ValidationError):
        Formulario033Datos.model_validate(_datos(examen_estomatognatico=examen))
