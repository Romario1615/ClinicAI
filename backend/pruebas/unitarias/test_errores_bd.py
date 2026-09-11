"""Clasificacion de errores de base de datos.

Pruebas puras: no necesitan PostgreSQL.  La contraparte de integracion, que
provoca violaciones reales y comprueba que el nombre de la restriccion y el
SQLSTATE que el driver expone de verdad sean los que el traductor reconoce,
esta en `pruebas/integracion/test_traduccion_errores_bd.py`.

Ambas hacen falta: aqui se verifica la logica de clasificacion, alli que los
codigos reales coincidan con los esperados.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.nucleo.errores import TurnoNoDisponible
from app.nucleo.errores_bd import (
    _MENSAJES_POR_RESTRICCION,
    SQLSTATE_INTERBLOQUEO,
    SQLSTATE_VIOLACION_EXCLUSION,
    SQLSTATE_VIOLACION_UNICIDAD,
    es_reintentable,
    extraer_nombre_restriccion,
    extraer_sqlstate,
    traducir,
    traducir_o_propagar,
)

pytestmark = [pytest.mark.unitaria, pytest.mark.seguridad]


def _error_con_sqlstate(codigo: str, mensaje: str = "error") -> SQLAlchemyError:
    """Construye una excepcion que imita la forma real del driver.

    `asyncpg` expone el codigo en `sqlstate` y SQLAlchemy envuelve la
    excepcion original en `.orig`.  Se replica esa estructura.
    """

    class ErrorDelDriver(Exception):
        sqlstate = codigo

    envoltorio = SQLAlchemyError(mensaje)
    envoltorio.orig = ErrorDelDriver(mensaje)  # type: ignore[attr-defined]
    return envoltorio


class TestExtraccion:
    def test_se_extrae_el_sqlstate_del_driver(self) -> None:
        assert extraer_sqlstate(_error_con_sqlstate(SQLSTATE_INTERBLOQUEO)) == SQLSTATE_INTERBLOQUEO

    def test_sin_codigo_devuelve_none(self) -> None:
        assert extraer_sqlstate(SQLAlchemyError("sin codigo")) is None

    def test_el_nombre_de_restriccion_se_busca_en_el_texto(self) -> None:
        """Ultimo recurso cuando el driver no lo expone.

        Buscar en el texto es fragil, pero la alternativa -- devolver un error
        genarico -- deja al usuario sin saber que corregir.
        """
        error = _error_con_sqlstate(
            SQLSTATE_VIOLACION_EXCLUSION,
            'conflicting key value violates exclusion constraint "cita_sin_solape_profesional"',
        )
        assert extraer_nombre_restriccion(error) == "cita_sin_solape_profesional"


class TestReintentos:
    def test_el_interbloqueo_es_reintentable(self) -> None:
        """Un interbloqueo es un conflicto transitorio entre transacciones."""
        assert es_reintentable(_error_con_sqlstate(SQLSTATE_INTERBLOQUEO))

    def test_la_violacion_de_exclusion_no_es_reintentable(self) -> None:
        """Reintentar no cambiaria nada: el turno seguira ocupado."""
        assert not es_reintentable(_error_con_sqlstate(SQLSTATE_VIOLACION_EXCLUSION))

    def test_la_violacion_de_unicidad_no_es_reintentable(self) -> None:
        assert not es_reintentable(_error_con_sqlstate(SQLSTATE_VIOLACION_UNICIDAD))


class TestTraduccion:
    def test_el_interbloqueo_se_traduce_a_turno_no_disponible(self) -> None:
        """Es el hallazgo de las pruebas de concurrencia.

        Bajo competencia real, una parte de los rechazos llega como
        interbloqueo y no como violacion de exclusion.  Si solo se tradujera
        el 23P01, una fraccion de las reservas concurrentes devolveria un 500
        bajo carga: el fallo que menos se detecta en desarrollo, porque solo
        aparece cuando hay competencia de verdad.
        """
        traducido = traducir(_error_con_sqlstate(SQLSTATE_INTERBLOQUEO, "deadlock detected"))
        assert isinstance(traducido, TurnoNoDisponible)
        assert traducido.detalles.get("reintentable") is True
        # El mensaje es para el paciente: nada de jerga del motor.
        assert "deadlock" not in traducido.mensaje.lower()
        assert "interbloqueo" not in traducido.mensaje.lower()

    def test_la_exclusion_por_nombre_da_el_mensaje_especifico(self) -> None:
        traducido = traducir(
            _error_con_sqlstate(
                SQLSTATE_VIOLACION_EXCLUSION,
                'violates exclusion constraint "cita_sin_solape_consultorio"',
            )
        )
        assert isinstance(traducido, TurnoNoDisponible)
        assert "consultorio" in traducido.mensaje.lower()

    def test_un_error_desconocido_no_se_traduce(self) -> None:
        assert traducir(SQLAlchemyError("algo inesperado sin sqlstate")) is None

    def test_traducir_o_propagar_propaga_lo_desconocido(self) -> None:
        """Un fallo real no debe disfrazarse de mensaje amable.

        Una tabla ausente, una conexion caida o un error de programacion
        tienen que llegar al registro como averias.  Traducirlos a «intente de
        nuevo» ocultaria el problema y haria imposible diagnosticarlo.
        """
        excepcion = SQLAlchemyError("relation does not exist")
        with pytest.raises(SQLAlchemyError, match="relation does not exist"):
            raise traducir_o_propagar(excepcion)

    def test_traducir_o_propagar_devuelve_lo_conocido(self) -> None:
        resultado = traducir_o_propagar(
            _error_con_sqlstate(
                SQLSTATE_VIOLACION_EXCLUSION,
                'violates exclusion constraint "cita_sin_solape_profesional"',
            )
        )
        assert isinstance(resultado, TurnoNoDisponible)

    def test_ningun_mensaje_traducido_filtra_jerga_tecnica(self) -> None:
        """Los mensajes van al paciente: no deben exponer detalles internos.

        Un mensaje con el nombre de la restriccion o con `gist` no le dice
        nada al paciente y revela la estructura de la base de datos.

        Se comparan PALABRAS completas, no subcadenas.  Buscar "gist" como
        subcadena da un falso positivo con "registrado", y una prueba que
        falla por algo asi acaba desactivada, que es peor que no tenerla.
        """
        jerga = {
            "gist",
            "constraint",
            "sqlstate",
            "postgres",
            "postgresql",
            "tstzrange",
            "exclusion",
            "deadlock",
            "rollback",
        }
        for nombre, (_clase, mensaje) in _MENSAJES_POR_RESTRICCION.items():
            palabras = set(re.findall(r"[a-z]+", mensaje.lower()))
            encontrada = palabras & jerga
            assert not encontrada, (
                f"El mensaje de '{nombre}' contiene jerga tecnica ({sorted(encontrada)}): {mensaje}"
            )
            # Y debe ser una frase, no un codigo.
            assert len(mensaje) > 20, f"El mensaje de '{nombre}' es demasiado escueto."
