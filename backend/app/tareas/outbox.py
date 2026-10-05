"""Trabajos periodicos del outbox: entrega y recuperacion.

Dos trabajos con cadencias distintas
------------------------------------
* `procesar_outbox` cada minuto.  Es la cadencia que importa: un recordatorio
  de «su cita es en tres horas» programado para las 07:00 debe salir a las
  07:00, no cuando toque el proximo barrido de cinco minutos.

* `recuperar_mensajes_huerfanos` cada diez minutos.  Solo actua cuando un
  worker murio a media entrega, que no es un suceso frecuente, y su ventana de
  deteccion son quince minutos de todas formas.

Donde se elige el adaptador
---------------------------
Aqui, a partir de `MODO_WHATSAPP`.  Con `sandbox` se registra el envio y no
sale nada a la red; con `cloud_api` se habla con la API real.  La eleccion es
por entorno y `configuracion.py` impide arrancar en produccion con `sandbox`
(ADR-0012).

El adaptador sandbox del worker guarda los envios en memoria del proceso, asi
que no sirve para inspeccionarlos desde una prueba de integracion: para eso la
prueba construye su propio `ServicioOutbox`.  Lo que se ejerce aqui es el
recorrido completo del trabajo periodico.
"""

from __future__ import annotations

from typing import Any

from app.mensajeria.adaptadores import (
    AdaptadorSandbox,
    AdaptadorWhatsAppCloud,
    CredencialesWhatsApp,
    RegistroCanales,
)
from app.mensajeria.recordatorios import ServicioRecordatorios
from app.mensajeria.servicios import ServicioOutbox
from app.modulos.outbox.modelos import CanalOutbox
from app.nucleo.bd import GestorBaseDatos
from app.nucleo.configuracion import Configuracion
from app.nucleo.registro import obtener_logger
from app.nucleo.reloj import Reloj

_logger = obtener_logger(__name__)

# Mensajes por ejecucion. El limite existe por la misma razon que en el
# barrido de la agenda: un atasco acumulado no debe producir una transaccion
# enorme ni una rafaga que agote la cuota del proveedor de golpe.
TAMANO_LOTE = 50


def construir_canales(configuracion: Configuracion) -> RegistroCanales:
    """Registro de adaptadores segun el entorno.

    Publica para que las pruebas puedan comprobar que en modo `sandbox` no se
    construye el adaptador real, que es lo que garantiza que una prueba no
    pueda salir a la red por accidente.
    """
    registro = RegistroCanales()

    if configuracion.modo_whatsapp == "cloud_api":
        registro.registrar(
            CanalOutbox.WHATSAPP.value,
            AdaptadorWhatsAppCloud(
                CredencialesWhatsApp(
                    id_numero_telefono=configuracion.whatsapp_id_numero_telefono,
                    token_acceso=configuracion.whatsapp_token_acceso.get_secret_value(),
                    version_api=configuracion.whatsapp_version_api,
                )
            ),
        )
    else:
        registro.registrar(CanalOutbox.WHATSAPP.value, AdaptadorSandbox("whatsapp_sandbox"))
        _logger.warning(
            "outbox.canal_en_sandbox",
            canal=CanalOutbox.WHATSAPP.value,
            nota="Los mensajes no salen a la red. Limitacion E-1.",
        )

    # Correo y calendario todavia no tienen adaptador propio. Se registra el
    # sandbox en su lugar y se avisa: sin entrada, el procesador devolveria
    # esos mensajes a la cola indefinidamente y el log solo diria «no hay
    # adaptador», sin decir que es lo esperado en esta fase.
    registro.registrar(CanalOutbox.CORREO.value, AdaptadorSandbox("correo_sandbox"))
    registro.registrar(CanalOutbox.INTERNO.value, AdaptadorSandbox("interno_sandbox"))

    return registro


async def procesar_outbox(ctx: dict[Any, Any], *_argumentos: Any, **_opciones: Any) -> int:
    """Entrega un lote de mensajes pendientes. Devuelve cuantos se entregaron.

    La firma con `ctx` y argumentos variables la impone el protocolo
    `WorkerCoroutine` de ARQ; es una de las excepciones de nomenclatura
    previstas en CLAUDE.md.
    """
    gestor: GestorBaseDatos = ctx["gestor_bd"]
    reloj: Reloj = ctx["reloj"]
    configuracion: Configuracion = ctx["configuracion"]
    canales = construir_canales(configuracion)

    entregados = 0
    async for sesion in gestor.sesion():
        servicio = ServicioOutbox(
            sesion,
            reloj,
            canales,
            max_intentos=configuracion.outbox_max_intentos,
            retroceso_base_segundos=configuracion.outbox_retroceso_base_segundos,
        )
        resumen = await servicio.procesar_lote(
            tamano=TAMANO_LOTE,
            worker=str(ctx.get("job_id", "worker")),
        )
        entregados = resumen.entregados

        if resumen.tomados:
            _logger.info(
                "outbox.lote_procesado",
                tomados=resumen.tomados,
                entregados=resumen.entregados,
                reintentables=resumen.reintentables,
                fallidos=resumen.fallidos,
                sin_adaptador=resumen.sin_adaptador,
            )
        if resumen.tomados == TAMANO_LOTE:
            # El lote salio lleno: quedan mensajes esperando. Importa saberlo
            # porque un recordatorio que se retrasa deja de ser un
            # recordatorio.
            _logger.warning(
                "outbox.lote_lleno",
                tomados=resumen.tomados,
                nota="Quedan mensajes pendientes hasta la proxima ejecucion.",
            )
    return entregados


async def recuperar_mensajes_huerfanos(
    ctx: dict[Any, Any], *_argumentos: Any, **_opciones: Any
) -> int:
    """Devuelve a la cola los mensajes que quedaron EN_PROCESO."""
    gestor: GestorBaseDatos = ctx["gestor_bd"]
    reloj: Reloj = ctx["reloj"]

    recuperados = 0
    async for sesion in gestor.sesion():
        servicio = ServicioOutbox(sesion, reloj, RegistroCanales())
        recuperados = await servicio.recuperar_huerfanos()
        await sesion.commit()
    return recuperados


async def encolar_recordatorios(ctx: dict[Any, Any], *_argumentos: Any, **_opciones: Any) -> int:
    """Materializa avisos vencidos en el outbox; no contacta proveedores."""
    gestor: GestorBaseDatos = ctx["gestor_bd"]
    reloj: Reloj = ctx["reloj"]
    encolados = 0
    async for sesion in gestor.sesion():
        resumen = await ServicioRecordatorios(
            sesion, reloj, url_aplicacion=ctx["configuracion"].frontend_url
        ).encolar_vencidos(
            tamano=TAMANO_LOTE,
        )
        encolados = resumen.encolados
        if resumen.tomados:
            _logger.info(
                "recordatorios.lote_procesado",
                tomados=resumen.tomados,
                encolados=resumen.encolados,
                omitidos=resumen.omitidos,
            )
        if resumen.tomados == TAMANO_LOTE:
            _logger.warning(
                "recordatorios.lote_lleno",
                tomados=resumen.tomados,
                nota="Quedan recordatorios hasta la proxima ejecucion.",
            )
    return encolados


__all__ = [
    "TAMANO_LOTE",
    "construir_canales",
    "encolar_recordatorios",
    "procesar_outbox",
    "recuperar_mensajes_huerfanos",
]
