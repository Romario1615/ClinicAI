"""Seleccion del adaptador de calendario segun el entorno (ADR-0012).

Vive aparte de las rutas y del worker porque los dos la necesitan, y porque
una prueba tiene que poder comprobar que en modo `sandbox` **no** se construye
el adaptador real. Esa comprobacion es lo que garantiza que ninguna prueba de
la suite pueda salir a la red.
"""

from __future__ import annotations

from app.modulos.calendario.adaptadores import (
    AdaptadorSandboxCalendario,
    RegistroCalendarios,
)
from app.modulos.calendario.google import AdaptadorGoogleCalendario
from app.nucleo.configuracion import Configuracion
from app.nucleo.registro import obtener_logger

logger = obtener_logger(__name__)

PROVEEDOR_GOOGLE = "google"


def construir_proveedores(configuracion: Configuracion) -> RegistroCalendarios:
    """Registro de adaptadores de calendario.

    En modo `sandbox` se registra el adaptador en memoria **bajo el nombre del
    proveedor real** (`google`), no bajo «sandbox». El motivo es que la
    columna `calendario_conexion.proveedor` guarda el proveedor de negocio, y
    si el registro usara otra clave, las conexiones creadas en desarrollo
    dejarian de resolver al pasar a produccion -- o al contrario.

    `MODO_CALENDARIO` decide entre HTTP real y memoria. Construir el adaptador
    no hace llamadas; sin autorizacion no se publican eventos.
    """
    registro = RegistroCalendarios()

    if configuracion.modo_calendario == "google":
        registro.registrar(PROVEEDOR_GOOGLE, AdaptadorGoogleCalendario())
        return registro

    registro.registrar(PROVEEDOR_GOOGLE, AdaptadorSandboxCalendario())
    logger.warning(
        "calendario.en_sandbox",
        proveedor=PROVEEDOR_GOOGLE,
        nota="Los eventos no salen a ningun calendario real. Limitacion E-1.",
    )
    return registro


__all__ = ["PROVEEDOR_GOOGLE", "construir_proveedores"]
