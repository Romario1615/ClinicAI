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


@pytest.fixture
def reloj() -> RelojFijo:
    """Reloj fijo en el instante de referencia."""
    return RelojFijo(INSTANTE_REFERENCIA)


@pytest.fixture(autouse=True)
def _entorno_de_pruebas(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Aisla las pruebas del archivo .env y del entorno del desarrollador.

    Sin este aislamiento, una prueba de configuracion pasaria o fallaria
    segun lo que el desarrollador tenga en su .env, y el resultado en CI no
    coincidiria con el local.
    """
    for clave in list(os.environ):
        if clave.startswith(
            (
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
        ):
            monkeypatch.delenv(clave, raising=False)

    # Evita que pydantic-settings lea el .env del proyecto.
    monkeypatch.setenv("ENTORNO", "local")
    yield
