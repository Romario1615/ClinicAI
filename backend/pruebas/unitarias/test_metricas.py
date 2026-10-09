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


def test_turnos_del_agente_se_cuentan_por_resultado_y_herramienta() -> None:
    """Sin contenido ni paciente: solo el resultado y el nombre de la herramienta."""
    metricas = MetricasAplicacion()

    metricas.registrar_turno_agente(["find_availability"], requiere_humano=False)
    metricas.registrar_turno_agente(["hold_slot", "handoff_to_human"], requiere_humano=True)

    exportado = metricas.exportar().decode()
    assert 'clinicai_agente_turnos_total{resultado="respondido"} 1.0' in exportado
    assert 'clinicai_agente_turnos_total{resultado="derivado"} 1.0' in exportado
    assert 'clinicai_agente_herramientas_total{herramienta="hold_slot"} 1.0' in exportado
    assert 'clinicai_agente_herramientas_total{herramienta="find_availability"} 1.0' in exportado


def test_una_herramienta_fuera_del_catalogo_no_crea_etiquetas_nuevas() -> None:
    """Una etiqueta por valor libre haria crecer las series sin limite."""
    metricas = MetricasAplicacion()

    metricas.registrar_turno_agente(["herramienta_inventada"], requiere_humano=False)

    assert "herramienta_inventada" not in metricas.exportar().decode()
