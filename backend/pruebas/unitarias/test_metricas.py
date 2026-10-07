"""Normalización de etiquetas HTTP sin datos ni identificadores."""

import pytest

from app.nucleo.metricas import MetricasAplicacion

pytestmark = pytest.mark.unitaria


def test_ruta_estatica_prevalece_sobre_identificador() -> None:
    metricas = MetricasAplicacion()
    metricas.configurar_rutas(["/citas/{cita_id}", "/citas/series"])
    assert metricas.normalizar_ruta("/citas/series") == "/citas/series"
    assert metricas.normalizar_ruta("/citas/id-sintetico") == "/citas/{cita_id}"


def test_prefijo_especifico_prevalece_sobre_dos_identificadores() -> None:
    metricas = MetricasAplicacion()
    metricas.configurar_rutas(["/citas/{cita_id}/{accion}", "/citas/series/{serie_id}"])
    assert metricas.normalizar_ruta("/citas/series/id-sintetico") == "/citas/series/{serie_id}"


def test_rutas_ajenas_no_se_publican() -> None:
    metricas = MetricasAplicacion()
    metricas.configurar_rutas(["/citas/{cita_id}"])
    assert metricas.normalizar_ruta("/ruta-ajena/id-sintetico") == "no_encontrada"
