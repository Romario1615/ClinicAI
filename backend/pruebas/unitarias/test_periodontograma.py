import uuid

import pytest
from pydantic import ValidationError

from app.modulos.odontologia.periodontograma_esquemas import (
    MedicionPeriodontal,
    PeriodontogramaNuevo,
    PiezaPeriodontal,
    resumir_piezas,
)

pytestmark = pytest.mark.unitaria


def test_calculos_distinguen_cero_y_sin_evaluar() -> None:
    piezas = {
        "16": PiezaPeriodontal(
            sitios={
                "VM": MedicionPeriodontal(profundidad=4, margen=2, sangrado=True, placa=False),
                "VC": MedicionPeriodontal(profundidad=0, margen=-1, sangrado=False),
                "VD": MedicionPeriodontal(profundidad=6),
                "LC": MedicionPeriodontal(),
            }
        ),
        "18": PiezaPeriodontal(ausente=True),
    }
    r = resumir_piezas(piezas)
    assert r.sitios_posibles == 186
    assert r.sitios_sondados == 3
    assert r.profundidad_media == 3.33
    assert r.insercion_media == 2.5
    assert r.sitios_insercion == 2
    assert r.sangrado_porcentaje == 50
    assert r.sangrado_evaluados == 2
    assert r.placa_porcentaje == 0
    assert r.placa_evaluados == 1
    assert r.sitios_4_5 == r.sitios_6_mas == 1


def test_sin_medidas_no_es_cero() -> None:
    r = resumir_piezas({})
    assert r.profundidad_media is r.sangrado_porcentaje is r.placa_porcentaje is None
    assert r.sitios_sondados == 0
    assert r.sitios_posibles == 192


@pytest.mark.parametrize(
    "datos",
    [
        {"profundidad": -1},
        {"profundidad": 21},
        {"margen": -21},
        {"margen": 21},
        {"profundidad": float("inf")},
        {"profundidad": float("nan")},
        {"desconocido": 3},
    ],
)
def test_mediciones_invalidas(datos: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MedicionPeriodontal.model_validate(datos)


@pytest.mark.parametrize(
    "datos",
    [
        {"ausente": True, "implante": True},
        {"ausente": True, "sitios": {"VM": {"profundidad": 3}}},
        {"implante": True, "movilidad": 0},
        {"implante": True, "furcacion": 0},
        {"movilidad": 4},
        {"movilidad": True},
        {"furcacion": -1},
        {"sitios": {"XX": {"profundidad": 2}}},
    ],
)
def test_pieza_coherente(datos: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PiezaPeriodontal.model_validate(datos)


@pytest.mark.parametrize("pieza", ["0", "01", "19", "55", "1e1", "016"])
def test_solo_fdi_permanentes(pieza: str) -> None:
    with pytest.raises(ValidationError):
        PeriodontogramaNuevo.model_validate(
            {
                "clave_idempotencia": str(uuid.uuid4()),
                "fecha_examen": "2026-04-15",
                "motivo": "Control sintético",
                "piezas": {pieza: {"ausente": True}},
            }
        )


def test_registro_vacio_y_anulacion_sin_base_rechazados() -> None:
    base = {
        "clave_idempotencia": str(uuid.uuid4()),
        "fecha_examen": "2026-04-15",
        "motivo": "Control sintético",
    }
    with pytest.raises(ValidationError):
        PeriodontogramaNuevo.model_validate(base)
    with pytest.raises(ValidationError):
        PeriodontogramaNuevo.model_validate({**base, "anulado": True})
    with pytest.raises(ValidationError):
        PeriodontogramaNuevo.model_validate(
            {**base, "motivo": "        ", "piezas": {"18": {"ausente": True}}}
        )
