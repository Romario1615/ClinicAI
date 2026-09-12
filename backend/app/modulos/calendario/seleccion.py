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

    El adaptador real de Google todavia no existe: solo el sandbox. Cuando se
    escriba, se registra aqui bajo la misma clave y `MODO_CALENDARIO` decide
    cual. `configuracion.py` ya impide arrancar en produccion con `sandbox`.
    """
    registro = RegistroCalendarios()

    if configuracion.modo_calendario == "google":
        # No hay adaptador real todavia. Se falla de forma explicita en lugar
        # de caer al sandbox en silencio: un entorno configurado para hablar
        # con Google que en realidad no sale a la red es peor que uno que no
        # arranca, porque parece funcionar.
        raise NotImplementedError(
            "El adaptador real de Google Calendar no esta implementado (Fase 4b). "
            "Use MODO_CALENDARIO=sandbox hasta que exista y haya credenciales."
        )

    registro.registrar(PROVEEDOR_GOOGLE, AdaptadorSandboxCalendario())
    logger.warning(
        "calendario.en_sandbox",
        proveedor=PROVEEDOR_GOOGLE,
        nota="Los eventos no salen a ningun calendario real. Limitacion E-1.",
    )
    return registro


__all__ = ["PROVEEDOR_GOOGLE", "construir_proveedores"]
