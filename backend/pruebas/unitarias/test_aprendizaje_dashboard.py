from datetime import date, timedelta

import pytest

from app.modulos.dashboard.aprendizaje import PuntoSerie, ajustar, pronosticar

pytestmark = pytest.mark.unitaria


def serie(dias: int, tipo: str = "semanal") -> list[PuntoSerie]:
    inicio = date(2026, 1, 1)
    return [
        PuntoSerie(
            fecha=inicio + timedelta(days=i),
            valor=[3, 5, 8, 4, 11, 2, 0][(inicio + timedelta(days=i)).weekday()]
            if tipo == "semanal"
            else 3 + i * 0.2,
            muestras=1,
        )
        for i in range(dias)
    ]


def test_aprende_estacionalidad_y_evalua_dias_posteriores() -> None:
    evidencia, futuro = pronosticar(serie(100))
    assert evidencia.estado == "validado_localmente"
    assert evidencia.algoritmo == "Patrón semanal aprendido"
    assert evidencia.mae == 0
    assert evidencia.mae_base is not None and evidencia.mae_base > 0
    assert evidencia.dias_seleccion == evidencia.dias_evaluacion == 7
    assert len(futuro) == 14
    assert futuro[0].fecha > serie(100)[-1].fecha
    assert all(p.inferior <= p.valor <= p.superior for p in futuro)


def test_aprende_tendencia_con_regresion() -> None:
    evidencia, futuro = pronosticar(serie(100, "tendencia"))
    assert evidencia.algoritmo == "Regresión lineal temporal"
    assert evidencia.mae == 0
    assert futuro[-1].valor > futuro[0].valor


@pytest.mark.parametrize("dias", [0, 1, 30, 55])
def test_no_inventa_entrenamiento(dias: int) -> None:
    evidencia, futuro = pronosticar(serie(dias))
    assert evidencia.estado == "insuficiente"
    assert futuro == []


def test_ceros_no_sustituyen_actividad() -> None:
    datos = [p.model_copy(update={"valor": 0}) for p in serie(100)]
    assert pronosticar(datos)[0].estado == "insuficiente"


def test_observaciones_vacias_en_evaluacion() -> None:
    datos = serie(100)
    for p in datos[-7:]:
        p.valor = None
    evidencia, futuro = pronosticar(datos)
    assert evidencia.estado == "insuficiente"
    assert "evaluación" in evidencia.motivo
    assert not futuro


@pytest.mark.parametrize("horizonte", [0, 31])
def test_horizonte_acotado(horizonte: int) -> None:
    with pytest.raises(ValueError):
        pronosticar(serie(100), horizonte)


def test_rechaza_desorden_y_duplicados_y_no_finitos() -> None:
    with pytest.raises(ValueError):
        pronosticar(serie(100)[::-1])
    with pytest.raises(ValueError):
        pronosticar([serie(1)[0], serie(1)[0]])
    with pytest.raises(ValueError):
        pronosticar([PuntoSerie(fecha=date(2026, 1, 1), valor=float("nan"))])


@pytest.mark.parametrize(
    "nombre",
    [
        "Media móvil 28 días",
        "Patrón semanal aprendido",
        "Regresión lineal temporal",
        "Suavizado exponencial 0.2",
        "Suavizado exponencial 0.8",
    ],
)
def test_candidatos_se_ajustan_a_observaciones(nombre: str) -> None:
    modelo = ajustar(nombre, serie(80))
    assert modelo.nombre == nombre
    assert modelo.predecir(date(2026, 4, 1)) >= 0


def test_porcentajes_tienen_limites_y_ventanas_no_se_solapan() -> None:
    evidencia, futuro = pronosticar(serie(200, "tendencia"), 30, 100)
    assert evidencia.evaluacion_desde is not None
    assert evidencia.evaluacion_desde > serie(200)[-15].fecha
    assert all(0 <= p.inferior <= p.valor <= p.superior <= 100 for p in futuro)
