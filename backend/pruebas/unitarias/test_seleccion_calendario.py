"""Seleccion del adaptador de calendario segun el entorno (ADR-0012).

La prueba que importa es la primera: es la que garantiza que ninguna prueba de
esta suite pueda hablar con Google, y que un entorno sin credenciales no lo
intente.

Vive en las unitarias y no en las de integracion porque no toca la base de
datos -- y porque los modulos de integracion llevan `pytest.mark.asyncio` a
nivel de modulo, que no admite pruebas sincronas.
"""

from __future__ import annotations

import pytest

from app.modulos.calendario.adaptadores import AdaptadorSandboxCalendario
from app.modulos.calendario.seleccion import PROVEEDOR_GOOGLE, construir_proveedores
from app.nucleo.configuracion import Configuracion

pytestmark = pytest.mark.unitaria


def test_en_modo_sandbox_el_adaptador_no_sale_a_la_red() -> None:
    """Garantia de que ninguna prueba de la suite habla con Google."""
    proveedores = construir_proveedores(Configuracion(modo_calendario="sandbox"))
    assert isinstance(proveedores.obtener(PROVEEDOR_GOOGLE), AdaptadorSandboxCalendario)


def test_el_sandbox_se_registra_bajo_el_nombre_del_proveedor_real() -> None:
    """`calendario_conexion.proveedor` guarda «google», no «sandbox».

    Si el registro usara otra clave, las conexiones creadas en desarrollo
    dejarian de resolver al pasar a produccion.
    """
    proveedores = construir_proveedores(Configuracion(modo_calendario="sandbox"))
    assert proveedores.obtener(PROVEEDOR_GOOGLE) is not None
    assert proveedores.obtener("sandbox") is None


def test_el_modo_google_falla_porque_no_hay_adaptador_real() -> None:
    """Falla explicitamente en lugar de caer al sandbox en silencio.

    Un entorno configurado para hablar con Google que en realidad no sale a la
    red es peor que uno que no arranca, porque parece funcionar.
    """
    with pytest.raises(NotImplementedError, match="Fase 4b"):
        construir_proveedores(Configuracion(modo_calendario="google"))
