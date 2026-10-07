"""Contratos de configuración del recolector local y sus alertas."""

from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.unitaria

RAIZ = Path(__file__).resolve().parents[3]


def _leer_yaml(ruta: Path) -> dict[str, Any]:
    with ruta.open(encoding="utf-8") as archivo:
        contenido = yaml.safe_load(archivo)
    assert isinstance(contenido, dict)
    return contenido


def test_recolector_local_apunta_al_api_y_carga_reglas() -> None:
    compose = _leer_yaml(RAIZ / "infra/compose/docker-compose.dev.yml")
    prometheus = _leer_yaml(RAIZ / "infra/prometheus/prometheus.yml")
    servicio = compose["services"]["prometheus"]

    assert servicio["profiles"] == ["observabilidad"]
    assert servicio["image"] == "prom/prometheus:v3.15.0"
    assert servicio["ports"] == ["127.0.0.1:9090:9090"]
    assert servicio["extra_hosts"] == [
        "host.docker.internal:${WINDOWS_HOST_IP:?Ejecute infra/wsl/observabilidad.sh para descubrir la puerta de enlace WSL}"
    ]
    assert prometheus["rule_files"] == ["/etc/prometheus/alertas.yml"]
    assert prometheus["scrape_configs"][0]["metrics_path"] == "/metrics"
    assert prometheus["scrape_configs"][0]["static_configs"][0]["targets"] == [
        "host.docker.internal:8000"
    ]


def test_reglas_priorizan_disponibilidad_y_entrega_de_avisos() -> None:
    alertas = _leer_yaml(RAIZ / "infra/prometheus/alertas.yml")
    reglas = alertas["groups"][0]["rules"]
    por_nombre = {regla["alert"]: regla for regla in reglas}

    assert set(por_nombre) == {
        "ClinicAIAPIInaccesible",
        "ClinicAIOutboxFallido",
        "ClinicAIOutboxAtrasado",
        "ClinicAIOutboxNoConsultable",
    }
    assert por_nombre["ClinicAIAPIInaccesible"]["for"] == "2m"
    assert por_nombre["ClinicAIOutboxFallido"]["for"] == "15m"
    assert 'estado="FALLIDO"' in por_nombre["ClinicAIOutboxFallido"]["expr"]
    assert "> 600" in por_nombre["ClinicAIOutboxAtrasado"]["expr"]
