"""La tasa de retorno a 30 días se oculta para grupos de menos de cinco pacientes."""

import pytest

from app.modulos.dashboard.repositorio import _retorno_30_dias_protegido

pytestmark = pytest.mark.unitaria


@pytest.mark.parametrize(
    ("cohorte", "retornos"),
    [(4, 2), (12, 3), (12, 9)],
)
def test_oculta_cohortes_o_resultados_de_uno_a_cuatro_pacientes(cohorte, retornos):
    assert _retorno_30_dias_protegido(cohorte, retornos) is None


@pytest.mark.parametrize(
    ("cohorte", "retornos", "porcentaje"),
    [(12, 0, 0.0), (12, 6, 50.0), (5, 5, 100.0)],
)
def test_publica_tasa_solo_cuando_ambos_resultados_se_pueden_mostrar(cohorte, retornos, porcentaje):
    resumen = _retorno_30_dias_protegido(cohorte, retornos)
    assert resumen is not None
    assert resumen.pacientes_seguimiento_completo == cohorte
    assert resumen.pacientes_que_regresaron == retornos
    assert resumen.porcentaje == porcentaje
