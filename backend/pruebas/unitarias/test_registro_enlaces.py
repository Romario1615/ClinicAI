"""Enlaces y verificadores sintéticos: nunca deben terminar en un log."""

import logging
from collections.abc import Iterator

import pytest
import structlog

from app.nucleo.registro import configurar_registro, procesador_redaccion

pytestmark = pytest.mark.unitaria

REFERENCIA_SINTETICA = "referencia_qa_sintetica_no_utilizable_123456789"


@pytest.fixture
def registro_aislado() -> Iterator[None]:
    raiz = logging.getLogger()
    manejadores, nivel = list(raiz.handlers), raiz.level
    configuracion = structlog.get_config()
    bibliotecas = [
        logging.getLogger(nombre)
        for nombre in ("uvicorn", "uvicorn.access", "uvicorn.error", "sqlalchemy.engine", "httpx")
    ]
    estados = [(logger, list(logger.handlers), logger.propagate) for logger in bibliotecas]
    try:
        yield
    finally:
        raiz.handlers = manejadores
        raiz.setLevel(nivel)
        structlog.configure(**configuracion)
        for logger, anteriores, propagar in estados:
            logger.handlers = anteriores
            logger.propagate = propagar


@pytest.mark.parametrize(
    "ruta",
    [
        f"/api/v1/publico/documentos/{REFERENCIA_SINTETICA}/acceso",
        f"/api/v1/publico/indicaciones/{REFERENCIA_SINTETICA}/acceso",
        f"https://example.invalid/documentos/{REFERENCIA_SINTETICA}",
        f"https://example.invalid/indicaciones/{REFERENCIA_SINTETICA}",
        f"/api/v1/publico/documentos/{REFERENCIA_SINTETICA}/acceso?token=NO_UTILIZABLE",
    ],
)
def test_oculta_referencia_en_campo_y_mensaje_libre(ruta):
    resultado = procesador_redaccion(
        None,
        "info",
        {"event": f"POST {ruta} HTTP/1.1", "ruta": ruta, "documento_id": "uuid-sintetico"},
    )
    assert REFERENCIA_SINTETICA not in str(resultado)
    assert "[redactado]" in resultado["ruta"]
    assert resultado["documento_id"] == "uuid-sintetico"


@pytest.mark.parametrize(
    "consulta",
    [
        "code=CODIGO_SINTETICO&state=ESTADO_SINTETICO",
        "access_token=VALOR_SINTETICO",
        "busqueda=Paciente%20Sintetico",
        "fecha_nacimiento=1990-01-01",
    ],
)
def test_no_registra_parametros_de_url(consulta):
    resultado = procesador_redaccion(
        None, "info", {"event": f"GET https://example.invalid/api/consulta?{consulta} HTTP/1.1"}
    )
    assert consulta not in resultado["event"]
    assert "/api/consulta?[redactado]" in resultado["event"]


def test_uvicorn_access_pasa_por_la_redaccion_de_texto_libre(capsys, registro_aislado):
    configurar_registro(formato="json", redactar=True)
    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d',
        "127.0.0.1",
        "POST",
        f"/api/v1/publico/documentos/{REFERENCIA_SINTETICA}/acceso?code=CODIGO_SINTETICO",
        "1.1",
        200,
    )
    salida = capsys.readouterr().out
    assert REFERENCIA_SINTETICA not in salida and "CODIGO_SINTETICO" not in salida
    assert "/publico/documentos/[redactado]/acceso?[redactado]" in salida
