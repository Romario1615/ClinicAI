"""Servicio del outbox: encolar, entregar y conciliar (ADR-0008).

Reparto de responsabilidades
----------------------------
* `encolar` se llama **dentro de la transaccion de negocio**.  Escribe la
  intencion de enviar en la misma transaccion que confirma la cita.  No hace
  `commit`: si la cita se revierte, el mensaje desaparece con ella.  Esa es
  toda la gracia del patron.

* `procesar_pendientes` corre en el worker, en **su propia** transaccion, y no
  sabe nada del negocio.  Entrega y actualiza estado.

Por que `ON CONFLICT DO NOTHING` en el encolado
-----------------------------------------------
La clave de deduplicacion tiene restriccion unica.  Si `encolar` dejara subir
la violacion, abortaria la transaccion **de negocio**: un segundo intento de
confirmar la misma cita fallaria entero por un recordatorio duplicado.  El
duplicado no es un error del usuario, es exactamente lo que la clave debe
absorber en silencio.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as insert_pg
from sqlalchemy.ext.asyncio import AsyncSession

from app.mensajeria import plantillas as catalogo_plantillas
from app.mensajeria.adaptadores import (
    MensajeSaliente,
    RegistroCanales,
    ResultadoEnvio,
)
from app.mensajeria.destinatarios import DestinatarioNoResoluble, ResolutorContacto
from app.modulos.automatizaciones import servicios as automatizaciones
from app.modulos.outbox.modelos import (
    CanalOutbox,
    EstadoOutbox,
    OutboxMensaje,
    Recordatorio,
    TipoMensajeOutbox,
)
from app.modulos.pacientes.modelos import Consentimiento, TipoConsentimiento
from app.nucleo.bd import ejecutar_escritura
from app.nucleo.errores import ConsentimientoRequerido
from app.nucleo.registro import obtener_logger
from app.nucleo.reloj import Reloj

logger = obtener_logger(__name__)

# Tope del retroceso exponencial. Sin tope, el sexto intento caeria a horas de
# distancia y un recordatorio de cita de manana llegaria pasado manana.
RETROCESO_MAXIMO_SEGUNDOS = 3600

# Un mensaje EN_PROCESO mas tiempo que esto se considera huerfano: el worker
# que lo tomo murio entre marcarlo y entregarlo.
MINUTOS_HUERFANO = 15

# Tipos que van dirigidos a un paciente y **inician** la conversacion. Son los
# unicos que exigen consentimiento: responder a un mensaje que el paciente
# acaba de enviar no lo necesita.
TIPOS_PROACTIVOS_A_PACIENTE: frozenset[TipoMensajeOutbox] = frozenset(
    {
        TipoMensajeOutbox.CITA_CONFIRMACION,
        TipoMensajeOutbox.CITA_RECORDATORIO_DIA_ANTES,
        TipoMensajeOutbox.CITA_RECORDATORIO_HORAS_ANTES,
        TipoMensajeOutbox.CITA_CANCELACION,
        TipoMensajeOutbox.CITA_REPROGRAMACION,
        TipoMensajeOutbox.OFERTA_TURNO,
        TipoMensajeOutbox.OFERTA_EXPIRADA,
        TipoMensajeOutbox.OFERTA_PERDIDA,
        TipoMensajeOutbox.TOMA_RECORDATORIO,
        TipoMensajeOutbox.TOMA_SEGUIMIENTO,
        TipoMensajeOutbox.PROMOCION,
        TipoMensajeOutbox.SEGUIMIENTO_TRATAMIENTO,
        TipoMensajeOutbox.INDICACIONES_DISPONIBLES,
    }
)

# Que consentimiento exige cada tipo. Los recordatorios de medicacion piden
# uno propio: aceptar recordatorios de cita no es aceptar que le escriban
# sobre su medicacion.
CONSENTIMIENTO_POR_TIPO: dict[TipoMensajeOutbox, TipoConsentimiento] = {
    TipoMensajeOutbox.TOMA_RECORDATORIO: TipoConsentimiento.RECORDATORIOS_MEDICACION,
    TipoMensajeOutbox.TOMA_SEGUIMIENTO: TipoConsentimiento.RECORDATORIOS_MEDICACION,
    # Publicidad exige su consentimiento propio, no el de recordatorios.
    TipoMensajeOutbox.PROMOCION: TipoConsentimiento.PROMOCIONES,
}
CONSENTIMIENTO_POR_DEFECTO = TipoConsentimiento.COMUNICACION_WHATSAPP


@dataclass(frozen=True, slots=True)
class SolicitudEnvio:
    """Peticion de encolado. Pydantic no: esto no cruza la frontera HTTP."""

    tipo: TipoMensajeOutbox
    canal: CanalOutbox
    destino_tipo: str
    destino_id: uuid.UUID
    clave_deduplicacion: str
    variables: dict[str, str]
    clinica_id: uuid.UUID | None = None
    entidad_origen_tipo: str | None = None
    entidad_origen_id: uuid.UUID | None = None
    programado_para: datetime | None = None
    # Plantilla aprobada en Meta distinta de la del catalogo (campanas) y
    # media id de la imagen de cabecera, si la plantilla la lleva.
    plantilla_meta: str | None = None
    imagen_cabecera: str | None = None


@dataclass(frozen=True, slots=True)
class ResumenProceso:
    tomados: int = 0
    entregados: int = 0
    reintentables: int = 0
    fallidos: int = 0
    sin_adaptador: int = 0


class ServicioOutbox:
    """Encolado y entrega de mensajes salientes."""

    def __init__(
        self,
        sesion: AsyncSession,
        reloj: Reloj,
        canales: RegistroCanales,
        *,
        resolutor: ResolutorContacto | None = None,
        max_intentos: int = 6,
        retroceso_base_segundos: int = 30,
    ) -> None:
        self._sesion = sesion
        self._reloj = reloj
        self._canales = canales
        self._resolutor = resolutor or ResolutorContacto(sesion)
        self._max_intentos = max_intentos
        self._retroceso_base = retroceso_base_segundos

    # ------------------------------------------------------------------
    #  Encolado
    # ------------------------------------------------------------------
    async def encolar(self, solicitud: SolicitudEnvio) -> uuid.UUID | None:
        """Registra la intencion de enviar. No hace `commit`.

        Devuelve el identificador del mensaje, o `None` si la clave de
        deduplicacion ya existia: el mensaje ya estaba encolado y no se
        duplica.

        La plantilla se valida **aqui**, no en el worker.  Un fallo de
        plantilla es un error de programacion, y descubrirlo en el worker
        significa descubrirlo cuando el paciente ya no recibio el mensaje;
        aqui rompe la operacion que lo encola, que es donde se puede corregir.
        """
        # Un flujo apagado por la clinica no encola. Se registra y se devuelve
        # `None`, como un duplicado: quien encola no tiene que tratarlo aparte.
        if not await automatizaciones.tipo_permitido(
            self._sesion, solicitud.clinica_id, solicitud.tipo
        ):
            logger.info(
                "outbox.flujo_apagado",
                tipo=solicitud.tipo.value,
                clinica_id=str(solicitud.clinica_id),
            )
            return None

        plantilla = catalogo_plantillas.obtener(solicitud.tipo)
        # Redactar valida los huecos y, sobre todo, que no se este colando una
        # variable clinica en la carga util.
        texto = plantilla.redactar(**solicitud.variables)

        if solicitud.destino_tipo == "PACIENTE" and solicitud.tipo in TIPOS_PROACTIVOS_A_PACIENTE:
            await self._exigir_consentimiento(solicitud)

        ahora = self._reloj.ahora()
        identificador = uuid.uuid4()
        sentencia = (
            insert_pg(OutboxMensaje)
            .values(
                id=identificador,
                tipo=solicitud.tipo.value,
                canal=solicitud.canal.value,
                clinica_id=solicitud.clinica_id,
                destino_tipo=solicitud.destino_tipo,
                destino_id=solicitud.destino_id,
                carga_util={
                    "plantilla": solicitud.plantilla_meta
                    or plantilla.nombre_meta
                    or plantilla.tipo.value,
                    "variables": dict(solicitud.variables),
                    "texto": texto,
                    **(
                        {"imagen_cabecera": solicitud.imagen_cabecera}
                        if solicitud.imagen_cabecera
                        else {}
                    ),
                },
                clave_deduplicacion=solicitud.clave_deduplicacion,
                estado=EstadoOutbox.PENDIENTE.value,
                intentos=0,
                max_intentos=self._max_intentos,
                proximo_intento_en=solicitud.programado_para or ahora,
                entidad_origen_tipo=solicitud.entidad_origen_tipo,
                entidad_origen_id=solicitud.entidad_origen_id,
                creado_en=ahora,
            )
            .on_conflict_do_nothing(constraint="uq_outbox_mensaje_clave_deduplicacion")
            .returning(OutboxMensaje.id)
        )
        resultado = await self._sesion.execute(sentencia)
        creado = resultado.scalar_one_or_none()
        if creado is None:
            logger.info(
                "outbox.duplicado_absorbido",
                tipo=solicitud.tipo.value,
                clave_deduplicacion=solicitud.clave_deduplicacion,
            )
        return creado

    async def _exigir_consentimiento(self, solicitud: SolicitudEnvio) -> None:
        """Comprueba el consentimiento vigente del paciente.

        Se comprueba al **encolar** y no al entregar por una razon practica:
        si se comprobara al entregar, la operacion de negocio parecera haber
        avisado al paciente y el aviso se descartaria en silencio horas
        despues.  Aqui, quien confirma la cita ve en el acto que ese paciente
        no acepto recibir mensajes.
        """
        tipo_requerido = CONSENTIMIENTO_POR_TIPO.get(solicitud.tipo, CONSENTIMIENTO_POR_DEFECTO)
        consulta = select(Consentimiento).where(
            Consentimiento.paciente_id == solicitud.destino_id,
            Consentimiento.tipo == tipo_requerido.value,
            Consentimiento.revocado_en.is_(None),
        )
        vigente = (await self._sesion.execute(consulta)).scalars().first()
        if vigente is None or not vigente.otorgado:
            raise ConsentimientoRequerido(
                "El paciente no tiene consentimiento vigente para recibir este tipo de mensaje.",
                detalles={"consentimiento": tipo_requerido.value},
            )

    async def cancelar_recordatorios(
        self, *, entidad_tipo: str, entidad_id: uuid.UUID, motivo: str
    ) -> int:
        """Cancela los recordatorios programados de una entidad.

        Se usa al cancelar una cita o modificar una receta (RF-K03, RF-L09).
        Solo toca los `PROGRAMADO`: un recordatorio ya encolado puede estar
        entregandose en este instante, y marcarlo cancelado aqui daria por
        cancelado algo que el paciente ya recibio.  Para ese caso esta
        `descartar_pendientes`.
        """
        sentencia = (
            update(Recordatorio)
            .where(
                Recordatorio.entidad_tipo == entidad_tipo,
                Recordatorio.entidad_id == entidad_id,
                Recordatorio.estado == "PROGRAMADO",
            )
            .values(
                estado="CANCELADO",
                cancelado_en=self._reloj.ahora(),
                motivo_cancelacion=motivo,
            )
        )
        return await ejecutar_escritura(self._sesion, sentencia)

    async def descartar_pendientes(
        self, *, entidad_tipo: str, entidad_id: uuid.UUID, motivo: str
    ) -> int:
        """Descarta mensajes aun no entregados de una entidad.

        Solo los `PENDIENTE`.  Los `EN_PROCESO` se dejan: estan en manos de un
        worker y cambiarlos por debajo produciria un mensaje entregado y
        marcado como descartado.
        """
        sentencia = (
            update(OutboxMensaje)
            .where(
                OutboxMensaje.entidad_origen_tipo == entidad_tipo,
                OutboxMensaje.entidad_origen_id == entidad_id,
                OutboxMensaje.estado == EstadoOutbox.PENDIENTE.value,
            )
            .values(
                estado=EstadoOutbox.DESCARTADO.value,
                ultimo_error=motivo,
                actualizado_en=self._reloj.ahora(),
            )
        )
        return await ejecutar_escritura(self._sesion, sentencia)

    # ------------------------------------------------------------------
    #  Entrega
    # ------------------------------------------------------------------
    async def tomar_lote(self, *, tamano: int, worker: str) -> list[OutboxMensaje]:
        """Reserva mensajes para este worker.

        `FOR UPDATE SKIP LOCKED` es lo que permite varios workers en paralelo
        sin que dos tomen el mismo mensaje y el paciente lo reciba dos veces.
        Sin `SKIP LOCKED` los workers se bloquearian en fila y el paralelismo
        seria aparente.
        """
        ahora = self._reloj.ahora()
        consulta = (
            select(OutboxMensaje)
            .where(
                OutboxMensaje.estado == EstadoOutbox.PENDIENTE.value,
                OutboxMensaje.proximo_intento_en <= ahora,
            )
            .order_by(OutboxMensaje.proximo_intento_en)
            .limit(tamano)
            .with_for_update(skip_locked=True)
        )
        mensajes = list((await self._sesion.execute(consulta)).scalars().all())
        for mensaje in mensajes:
            mensaje.estado = EstadoOutbox.EN_PROCESO.value
            mensaje.tomado_por = worker
            mensaje.tomado_en = ahora
        await self._sesion.flush()
        return mensajes

    async def procesar_lote(self, *, tamano: int = 20, worker: str = "worker") -> ResumenProceso:
        """Toma un lote y lo entrega. Confirma la transaccion al final.

        El `commit` esta aqui y no en el llamador porque el estado del outbox
        debe persistir aunque el siguiente mensaje del lote falle: si todo el
        lote compartiera desenlace, un fallo al final desharia entregas ya
        realizadas y esos mensajes se reenviarian.
        """
        mensajes = await self.tomar_lote(tamano=tamano, worker=worker)
        # Se confirma la toma antes de salir a la red. Si el proceso muere
        # durante el envio, los mensajes quedan EN_PROCESO y los recupera
        # `recuperar_huerfanos`; sin este commit quedarian PENDIENTE y otro
        # worker podria enviarlos mientras este sigue vivo.
        await self._sesion.commit()

        resumen = ResumenProceso(tomados=len(mensajes))
        for mensaje in mensajes:
            resumen = await self._entregar(mensaje, resumen)
        await self._sesion.commit()
        return resumen

    async def _entregar(self, mensaje: OutboxMensaje, resumen: ResumenProceso) -> ResumenProceso:
        adaptador = self._canales.obtener(mensaje.canal)
        if adaptador is None:
            # Se devuelve a PENDIENTE con retroceso, no se marca FALLIDO: la
            # ausencia de adaptador es un problema de despliegue, y descartar
            # los mensajes por una configuracion incompleta perderia avisos
            # que se entregarian en cuanto se corrija.
            self._reprogramar(mensaje, f"No hay adaptador para el canal {mensaje.canal}.")
            return _con(resumen, sin_adaptador=resumen.sin_adaptador + 1)

        try:
            contacto = await self._resolutor.resolver(
                destino_tipo=mensaje.destino_tipo,
                destino_id=mensaje.destino_id,
                canal=CanalOutbox(mensaje.canal),
            )
        except (DestinatarioNoResoluble, ValueError) as exc:
            # Un destinatario sin dato de contacto no mejora reintentando. Se
            # marca FALLIDO para que aparezca en la cola de revision: alguien
            # tiene que pedirle el numero al paciente.
            mensaje.intentos += 1
            mensaje.actualizado_en = self._reloj.ahora()
            mensaje.estado = EstadoOutbox.FALLIDO.value
            mensaje.ultimo_error = str(exc)
            logger.error(
                "outbox.destinatario_no_resoluble",
                mensaje_id=str(mensaje.id),
                tipo=mensaje.tipo,
                motivo=str(exc),
            )
            return _con(resumen, fallidos=resumen.fallidos + 1)

        carga = mensaje.carga_util if isinstance(mensaje.carga_util, dict) else {}
        saliente = MensajeSaliente(
            destino=contacto.valor,
            nombre_plantilla=str(carga.get("plantilla", mensaje.tipo)),
            variables=_ordenar_variables(carga.get("variables")),
            texto=str(carga.get("texto", "")),
            imagen_cabecera=(
                str(carga["imagen_cabecera"]) if carga.get("imagen_cabecera") else None
            ),
        )
        respuesta = await adaptador.enviar(saliente)
        ahora = self._reloj.ahora()
        mensaje.intentos += 1
        mensaje.actualizado_en = ahora

        if respuesta.resultado is ResultadoEnvio.ENTREGADO:
            mensaje.estado = EstadoOutbox.ENTREGADO.value
            mensaje.entregado_en = ahora
            mensaje.referencia_externa = respuesta.referencia_externa
            mensaje.ultimo_error = None
            logger.info(
                "outbox.entregado",
                mensaje_id=str(mensaje.id),
                tipo=mensaje.tipo,
                canal=mensaje.canal,
                intentos=mensaje.intentos,
            )
            return _con(resumen, entregados=resumen.entregados + 1)

        detalle = respuesta.detalle or "sin detalle"
        if respuesta.resultado is ResultadoEnvio.FALLO_PERMANENTE or mensaje.agoto_intentos:
            mensaje.estado = EstadoOutbox.FALLIDO.value
            mensaje.ultimo_error = detalle
            # Nivel `error`: un FALLIDO significa que alguien creyo avisar a un
            # paciente y no ocurrio. Requiere que una persona lo vea.
            logger.error(
                "outbox.fallido",
                mensaje_id=str(mensaje.id),
                tipo=mensaje.tipo,
                canal=mensaje.canal,
                intentos=mensaje.intentos,
                motivo=detalle,
            )
            return _con(resumen, fallidos=resumen.fallidos + 1)

        self._reprogramar(mensaje, detalle)
        return _con(resumen, reintentables=resumen.reintentables + 1)

    def _reprogramar(self, mensaje: OutboxMensaje, motivo: str) -> None:
        """Devuelve el mensaje a la cola con retroceso exponencial."""
        espera = min(
            self._retroceso_base * (2 ** max(mensaje.intentos - 1, 0)),
            RETROCESO_MAXIMO_SEGUNDOS,
        )
        mensaje.estado = EstadoOutbox.PENDIENTE.value
        mensaje.proximo_intento_en = self._reloj.ahora() + timedelta(seconds=espera)
        mensaje.ultimo_error = motivo
        mensaje.tomado_por = None
        mensaje.tomado_en = None
        logger.warning(
            "outbox.reintento_programado",
            mensaje_id=str(mensaje.id),
            intentos=mensaje.intentos,
            espera_segundos=espera,
            motivo=motivo,
        )

    async def recuperar_huerfanos(self, *, minutos: int = MINUTOS_HUERFANO) -> int:
        """Devuelve a la cola los mensajes que quedaron EN_PROCESO.

        Ocurre cuando el worker muere entre tomar el mensaje y registrar el
        desenlace.  Sin esta recuperacion se quedarian atascados para siempre,
        que es la forma silenciosa de perder un recordatorio.

        Puede provocar un envio duplicado si el worker murio **despues** de
        entregar.  Es la eleccion deliberada: ante la duda, se prefiere que el
        paciente reciba dos veces un recordatorio a que no lo reciba.  Queda
        declarado en `docs/known-limitations.md`.
        """
        limite = self._reloj.ahora() - timedelta(minutes=minutos)
        sentencia = (
            update(OutboxMensaje)
            .where(
                OutboxMensaje.estado == EstadoOutbox.EN_PROCESO.value,
                OutboxMensaje.tomado_en < limite,
            )
            .values(
                estado=EstadoOutbox.PENDIENTE.value,
                tomado_por=None,
                tomado_en=None,
                proximo_intento_en=self._reloj.ahora(),
                ultimo_error="Recuperado: el worker no registro el desenlace.",
            )
        )
        recuperados = await ejecutar_escritura(self._sesion, sentencia)
        if recuperados:
            logger.warning("outbox.huerfanos_recuperados", cantidad=recuperados)
        return recuperados

    # ------------------------------------------------------------------
    #  Conciliacion de estados de entrega
    # ------------------------------------------------------------------
    async def registrar_estado_entrega(
        self, *, referencia_externa: str, estado_proveedor: str, detalle: str | None = None
    ) -> bool:
        """Aplica un estado de entrega llegado por webhook.

        El proveedor informa `sent`, `delivered`, `read` y `failed` de forma
        asincrona y **desordenada**: un `sent` puede llegar despues de un
        `delivered`.  Por eso solo se actua sobre `failed`, que es el unico
        que cambia lo que el sistema debe hacer; los demas se registran en el
        log y no retroceden el estado.
        """
        consulta = select(OutboxMensaje).where(
            OutboxMensaje.referencia_externa == referencia_externa
        )
        mensaje = (await self._sesion.execute(consulta)).scalars().first()
        if mensaje is None:
            logger.info("outbox.estado_de_mensaje_desconocido", referencia=referencia_externa)
            return False

        if estado_proveedor != "failed":
            logger.info(
                "outbox.estado_entrega",
                mensaje_id=str(mensaje.id),
                estado_proveedor=estado_proveedor,
            )
            return True

        mensaje.estado = EstadoOutbox.FALLIDO.value
        mensaje.ultimo_error = detalle or "El proveedor reporto fallo de entrega."
        mensaje.actualizado_en = self._reloj.ahora()
        logger.error(
            "outbox.entrega_fallida_reportada",
            mensaje_id=str(mensaje.id),
            tipo=mensaje.tipo,
        )
        return True


def _ordenar_variables(variables: Any) -> tuple[str, ...]:
    """Ordena las variables de forma estable para la plantilla del proveedor.

    La Cloud API recibe los parametros **posicionalmente**, y la carga util se
    guardo como diccionario.  Un orden que dependa de la insercion haria que
    el mismo mensaje reencolado tras un reintento llevara los valores
    cambiados de sitio.  Orden alfabetico por nombre de variable: arbitrario,
    pero identico en cada intento y en cada proceso.
    """
    if not isinstance(variables, dict):
        return ()
    return tuple(str(variables[clave]) for clave in sorted(variables))


def _con(resumen: ResumenProceso, **cambios: int) -> ResumenProceso:
    datos = {
        "tomados": resumen.tomados,
        "entregados": resumen.entregados,
        "reintentables": resumen.reintentables,
        "fallidos": resumen.fallidos,
        "sin_adaptador": resumen.sin_adaptador,
    }
    datos.update(cambios)
    return ResumenProceso(**datos)


__all__ = [
    "CONSENTIMIENTO_POR_TIPO",
    "MINUTOS_HUERFANO",
    "RETROCESO_MAXIMO_SEGUNDOS",
    "TIPOS_PROACTIVOS_A_PACIENTE",
    "ResumenProceso",
    "ServicioOutbox",
    "SolicitudEnvio",
]
