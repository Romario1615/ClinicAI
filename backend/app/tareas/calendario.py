"""Trabajos periodicos del calendario externo.

Dos trabajos, con cadencias distintas y por motivos distintos.

`sincronizar_calendarios` cada dos minutos
------------------------------------------
Publica los eventos pendientes. No hace falta que sea cada minuto como el
outbox: un recordatorio de WhatsApp tiene una hora concreta a la que debe
salir, mientras que un reflejo de calendario solo tiene que estar antes de que
el profesional mire su agenda. Dos minutos deja margen sin gastar cuota del
proveedor en barridos vacios.

`reconciliar_calendarios` cada hora
-----------------------------------
Compara lo que el sistema cree sincronizado con lo que el proveedor dice que
hay. Detecta lo que ningun error de escritura revela: que un evento
desaparecio o cambio **mientras el sistema no miraba**.

Es el barrido que hace falta porque el sistema no es el unico que escribe en
ese calendario. El profesional tambien, desde su telefono. Sin esta
reconciliacion, un evento borrado a mano quedaria marcado SINCRONIZADO para
siempre y su agenda externa mostraria como libre un hueco ocupado.

Cada hora y no mas a menudo porque **consume una lectura del proveedor por
evento**: es el trabajo mas caro del sistema en cuota de API, y su ventana de
deteccion aceptable se mide en horas, no en minutos.
"""

from __future__ import annotations

from typing import Any

from app.modulos.calendario.seleccion import construir_proveedores
from app.modulos.calendario.servicios import ServicioCalendario
from app.nucleo.bd import GestorBaseDatos
from app.nucleo.configuracion import Configuracion
from app.nucleo.registro import obtener_logger
from app.nucleo.reloj import Reloj
from app.nucleo.seguridad import CifradorDatos

_logger = obtener_logger(__name__)

# Eventos por ejecucion. Mismo motivo que en los demas barridos: un atasco
# acumulado no debe producir una transaccion enorme ni una rafaga contra el
# proveedor.
TAMANO_LOTE = 50

# La reconciliacion lee del proveedor una vez por evento, asi que su lote es
# mas pequeno: el limite real no es la base de datos, es la cuota de la API.
TAMANO_LOTE_RECONCILIACION = 100


def _servicio(ctx: dict[Any, Any]) -> tuple[GestorBaseDatos, Configuracion, Reloj]:
    gestor: GestorBaseDatos = ctx["gestor_bd"]
    configuracion: Configuracion = ctx["configuracion"]
    reloj: Reloj = ctx["reloj"]
    return gestor, configuracion, reloj


async def sincronizar_calendarios(ctx: dict[Any, Any], *_argumentos: Any, **_opciones: Any) -> int:
    """Publica los eventos pendientes. Devuelve cuantos quedaron sincronizados.

    La firma con `ctx` y argumentos variables la impone el protocolo
    `WorkerCoroutine` de ARQ.
    """
    gestor, configuracion, reloj = _servicio(ctx)
    cifrador = CifradorDatos(configuracion.clave_cifrado_datos.get_secret_value())
    proveedores = construir_proveedores(configuracion)

    total = 0
    async for sesion in gestor.sesion():
        servicio = ServicioCalendario(
            sesion, reloj, cifrador, proveedores, url_sistema=configuracion.api_url
        )
        # Primero se detectan los reflejos que faltan, y luego se publican
        # en la misma ejecucion: asi una cita confirmada aparece en el
        # calendario en el siguiente barrido y no en el de despues.
        detectados = await servicio.detectar_citas_sin_reflejo(limite=TAMANO_LOTE)
        resumen = await servicio.sincronizar_pendientes(limite=TAMANO_LOTE)
        # Se confirma aunque haya conflictos o errores: el estado de cada
        # evento es informacion que hay que conservar, y perderla por un
        # rollback global haria que el siguiente barrido repitiera el trabajo
        # y volviera a gastar cuota.
        await sesion.commit()
        total = resumen.creados + resumen.actualizados + resumen.recreados

        if detectados or any(
            (
                resumen.creados,
                resumen.actualizados,
                resumen.eliminados,
                resumen.recreados,
                resumen.conflictos,
                resumen.errores,
            )
        ):
            _logger.info(
                "calendario.lote_sincronizado",
                creados=resumen.creados,
                actualizados=resumen.actualizados,
                eliminados=resumen.eliminados,
                recreados=resumen.recreados,
                conflictos=resumen.conflictos,
                reintentables=resumen.reintentables,
                errores=resumen.errores,
                token_vencido=resumen.token_vencido,
                detectados=detectados,
            )
        if resumen.conflictos:
            # Un conflicto espera a una persona: el profesional movio el
            # evento y hay que decidir si se reprograma la cita. Si nadie
            # mira, la agenda interna y la externa divergen en silencio.
            _logger.warning(
                "calendario.conflictos_pendientes",
                cantidad=resumen.conflictos,
                nota="Requieren decision humana; pueden implicar reprogramar a un paciente.",
            )
    return total


async def reconciliar_calendarios(ctx: dict[Any, Any], *_argumentos: Any, **_opciones: Any) -> int:
    """Detecta eventos borrados o modificados fuera del sistema.

    Devuelve cuantas diferencias encontro, para que el registro permita ver si
    los profesionales editan sus calendarios a mano con frecuencia -- lo que
    seria una senal de que el reflejo no les sirve tal como esta.
    """
    gestor, configuracion, reloj = _servicio(ctx)
    cifrador = CifradorDatos(configuracion.clave_cifrado_datos.get_secret_value())
    proveedores = construir_proveedores(configuracion)

    diferencias = 0
    async for sesion in gestor.sesion():
        servicio = ServicioCalendario(
            sesion, reloj, cifrador, proveedores, url_sistema=configuracion.api_url
        )
        resumen = await servicio.reconciliar(limite=TAMANO_LOTE_RECONCILIACION)
        await sesion.commit()
        diferencias = resumen.eliminados + resumen.conflictos

        if diferencias:
            _logger.info(
                "calendario.reconciliacion",
                borrados_externamente=resumen.eliminados,
                conflictos=resumen.conflictos,
                sin_conexion=resumen.sin_conexion,
            )
    return diferencias


__all__ = [
    "TAMANO_LOTE",
    "TAMANO_LOTE_RECONCILIACION",
    "reconciliar_calendarios",
    "sincronizar_calendarios",
]
