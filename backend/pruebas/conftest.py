"""Fixtures compartidas por toda la suite."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from app.nucleo.reloj import RelojFijo

# Instante de referencia para las pruebas: miercoles 15 de abril de 2026,
# 14:00 UTC (09:00 en America/Guayaquil).  Se elige un miercoles laborable a
# media manana para que caiga dentro de cualquier horario de atencion
# razonable sin tener que ajustar cada prueba.
INSTANTE_REFERENCIA = datetime(2026, 4, 15, 14, 0, 0, tzinfo=UTC)

# Prefijos de variables de entorno que se ocultan a las pruebas unitarias.
_PREFIJOS_AISLADOS = (
    "ENTORNO",
    "POSTGRES_",
    "REDIS_",
    "CLAVE_",
    "PROVEEDOR_",
    "MODO_",
    "WHATSAPP_",
    "GOOGLE_",
    "ANTHROPIC_",
    "RAG_",
    "DEPURACION",
    "FRONTEND_",
)


@pytest.fixture
def reloj() -> RelojFijo:
    """Reloj fijo en el instante de referencia."""
    return RelojFijo(INSTANTE_REFERENCIA)


@pytest.fixture(autouse=True)
def _entorno_de_pruebas(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Aisla las pruebas unitarias del .env y del entorno del desarrollador.

    Sin este aislamiento, una prueba de configuracion pasaria o fallaria segun
    lo que el desarrollador tenga en su `.env`, y el resultado en CI no
    coincidiria con el local.

    **No se aplica a las pruebas que necesitan infraestructura real.**  Las de
    integracion, API, concurrencia y RAG se conectan a PostgreSQL y a Redis, y
    para eso necesitan precisamente la configuracion del entorno.  Ocultarsela
    las haria fallar con errores de conexion desconcertantes.
    """
    marcadores = {marca.name for marca in request.node.iter_markers()}
    necesita_infraestructura = bool(marcadores & {"integracion", "api", "concurrencia", "rag"})

    if not necesita_infraestructura:
        for clave in list(os.environ):
            if clave.startswith(_PREFIJOS_AISLADOS):
                monkeypatch.delenv(clave, raising=False)
        monkeypatch.setenv("ENTORNO", "local")

    yield
