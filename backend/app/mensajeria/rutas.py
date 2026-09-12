"""Webhook de WhatsApp Business Cloud API.

Es el unico endpoint publico sin autenticacion del sistema.  Todo lo que lo
protege esta aqui:

* La firma HMAC-SHA256 sobre el **cuerpo crudo** (`app/mensajeria/firma.py`).
* Deduplicacion por `external_id` en la base de datos.
* Limite de tasa por IP.

Por que devuelve 200 casi siempre
---------------------------------
Meta reintenta las entregas con error y, si persisten, **deshabilita la
suscripcion del webhook**.  Perder la suscripcion significa dejar de recibir
las respuestas de todos los pacientes, y recuperarla es manual.

Asi que un fallo de procesamiento no se convierte en un error HTTP: se acusa
recibo, se registra el fallo en el log a nivel `error` y se deja para revision.
La unica excepcion es la firma invalida, que devuelve 403: esa peticion no
viene de Meta, y Meta nunca la vera.

Nota sobre nombres: `hub.mode`, `hub.challenge` y `X-Hub-Signature-256` son de
la API externa y no se traducen (CLAUDE.md, seccion 2).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Request, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.mensajeria import carga_whatsapp
from app.mensajeria.adaptadores import RegistroCanales
from app.mensajeria.firma import verificar_firma, verificar_reto
from app.mensajeria.servicios import ServicioOutbox
from app.modulos.auditoria.repositorio import RepositorioAuditoria
from app.modulos.conversaciones.servicios import ServicioConversaciones
from app.modulos.organizacion.modelos import ConfiguracionClinica
from app.nucleo.auditoria import AccionAuditada, EntradaAuditoria, ResultadoAuditoria
from app.nucleo.autorizacion import TipoActor
from app.nucleo.dependencias import (
    Auditor,
    ConfiguracionActual,
    Limitador,
    RelojActual,
    Sesion,
)
from app.nucleo.registro import obtener_logger
from app.nucleo.reloj import Reloj

logger = obtener_logger(__name__)

enrutador = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

# Clave de `configuracion_clinica` que asocia el numero de Meta con la
# clinica. Es lo que permite que una instancia atienda a varias clinicas sin
# mezclar sus conversaciones.
CLAVE_NUMERO = "whatsapp.id_numero_telefono"

# Limite por IP. Generoso comparado con el trafico real de Meta, y suficiente
# para que un tercero no pueda usar el endpoint como amplificador de trabajo
# contra la base de datos.
LIMITE_WEBHOOK = 120
VENTANA_WEBHOOK_SEGUNDOS = 60

# Tope del cuerpo. Meta agrupa varios mensajes por peticion, pero no envia
# megabytes; sin tope, un tercero podria mandar un cuerpo enorme y obligar a
# calcular su HMAC.
MAXIMO_BYTES_CUERPO = 1_000_000


@enrutador.get(
    "/webhook",
    response_class=PlainTextResponse,
    summary="Verificacion inicial del webhook",
    responses={403: {"description": "Token de verificacion incorrecto"}},
)
async def verificar_webhook(
    configuracion: ConfiguracionActual,
    modo: Annotated[str | None, Query(alias="hub.mode")] = None,
    token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    reto: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> str:
    """Responde al reto que Meta envia al dar de alta la URL.

    Devuelve el reto en **texto plano**. Si se devolviera JSON, Meta lo
    rechazaria y el webhook quedaria sin registrar, con el sintoma confuso de
    que «el endpoint responde 200 pero no llegan mensajes».
    """
    reto_validado = verificar_reto(
        modo=modo,
        token=token,
        reto=reto,
        token_esperado=configuracion.whatsapp_token_verificacion.get_secret_value(),
    )
    logger.info("whatsapp.webhook_verificado")
    return reto_validado


@enrutador.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
    summary="Recepcion de mensajes y estados de entrega",
    responses={
        403: {"description": "Firma invalida"},
        413: {"description": "Cuerpo demasiado grande"},
    },
)
async def recibir_webhook(
    peticion: Request,
    sesion: Sesion,
    reloj: RelojActual,
    configuracion: ConfiguracionActual,
    limitador: Limitador,
    auditor: Auditor,
    respuesta: Response,
    firma: Annotated[str | None, Header(alias="X-Hub-Signature-256")] = None,
) -> dict[str, Any]:
    ip = peticion.client.host if peticion.client else "desconocida"
    # Fallo abierto: este limite protege de abuso, no es un control de
    # autenticacion. Si Redis cae, es preferible seguir recibiendo los
    # mensajes de los pacientes (ver `limite_tasa.py` y la limitacion E-11).
    await limitador.exigir(
        f"webhook:whatsapp:{ip}",
        limite=LIMITE_WEBHOOK,
        ventana_segundos=VENTANA_WEBHOOK_SEGUNDOS,
        fallar_cerrado=False,
    )

    # El cuerpo CRUDO. Reserializarlo cambiaria los bytes y la firma dejaria
    # de coincidir.
    cuerpo = await peticion.body()
    if len(cuerpo) > MAXIMO_BYTES_CUERPO:
        respuesta.status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        return {"recibido": False}

    if configuracion.whatsapp_validar_firma:
        try:
            verificar_firma(cuerpo, firma, configuracion.whatsapp_secreto_app.get_secret_value())
        except Exception:
            # Se audita en sesion propia: la de la peticion se descarta al
            # propagar el error, y una firma invalida es justo lo que no puede
            # perderse (es una de las acciones con alerta).
            await _auditar_firma_invalida(auditor, reloj, ip)
            await sesion.commit()
            raise
    else:
        # Configuracion prohibida en produccion (`configuracion.py` lo valida
        # al arrancar). Se registra en cada peticion para que no pase
        # inadvertida en un entorno de pruebas expuesto.
        logger.warning("whatsapp.firma_no_verificada", ip=ip)

    try:
        cuerpo_json = await peticion.json()
    except Exception:
        logger.warning("whatsapp.cuerpo_no_json")
        return {"recibido": True}

    carga = carga_whatsapp.interpretar(cuerpo_json)
    if carga.vacia:
        # Meta envia notificaciones sin mensajes ni estados (cambios de
        # plantilla, por ejemplo). No es un error.
        return {"recibido": True, "mensajes": 0, "estados": 0}

    # --- Estados de entrega ------------------------------------------------
    # Se concilian aunque no se resuelva la clinica: la referencia externa
    # identifica el mensaje por si sola.
    servicio_outbox = ServicioOutbox(sesion, reloj, RegistroCanales())
    for estado in carga.estados:
        await servicio_outbox.registrar_estado_entrega(
            referencia_externa=estado.external_id,
            estado_proveedor=estado.estado,
            detalle=estado.detalle,
        )

    # --- Mensajes ----------------------------------------------------------
    resumen = None
    if carga.mensajes:
        clinica_id = await _resolver_clinica(sesion, carga.id_numero_telefono)
        if clinica_id is None:
            # Nivel `error`: hay pacientes escribiendo a un numero que este
            # sistema no sabe a quien pertenece, y sus mensajes no llegan a
            # nadie. Exige intervencion, no una linea informativa.
            logger.error(
                "whatsapp.numero_sin_clinica",
                id_numero_telefono=carga.id_numero_telefono,
                mensajes_descartados=len(carga.mensajes),
            )
        else:
            servicio = ServicioConversaciones(sesion, reloj)
            resumen = await servicio.procesar(carga, clinica_id=clinica_id)

    await sesion.commit()
    return {
        "recibido": True,
        "mensajes": resumen.recibidos if resumen else 0,
        "duplicados": resumen.duplicados if resumen else 0,
        "estados": len(carga.estados),
    }


async def _resolver_clinica(sesion: AsyncSession, id_numero: str | None) -> uuid.UUID | None:
    """Clinica dueña del numero que recibio el mensaje.

    La asociacion vive en `configuracion_clinica` y no en el entorno porque
    una instancia puede atender a varias clinicas, cada una con su propio
    numero, y una variable de entorno solo admite uno.
    """
    if not id_numero:
        return None
    consulta = select(ConfiguracionClinica).where(
        ConfiguracionClinica.clave == CLAVE_NUMERO,
        ConfiguracionClinica.vigente.is_(True),
    )
    for fila in (await sesion.execute(consulta)).scalars().all():
        valor = fila.valor
        if isinstance(valor, dict) and str(valor.get("valor")) == id_numero:
            return fila.clinica_id
    return None


async def _auditar_firma_invalida(auditor: RepositorioAuditoria, reloj: Reloj, ip: str) -> None:
    await auditor.registrar(
        [
            EntradaAuditoria(
                accion=AccionAuditada.WEBHOOK_FIRMA_INVALIDA,
                actor_tipo=TipoActor.SISTEMA,
                actor_id=None,
                resultado=ResultadoAuditoria.DENEGADO,
                ocurrido_en=reloj.ahora(),
                ip=ip,
                metadatos={"canal": "WHATSAPP"},
            )
        ]
    )


__all__ = ["CLAVE_NUMERO", "enrutador"]
