"""El webhook de WhatsApp por HTTP, contra la aplicacion real.

Este es el unico endpoint publico sin autenticacion del sistema, asi que estas
pruebas son de seguridad tanto como de funcionalidad.  Se comprueba, en orden
de importancia:

1. Una firma invalida no entra, y queda auditada.
2. Un reintento de Meta no vuelve a producir efecto.
3. Una baja se aplica de inmediato y corta los envios.
4. Nada que cambie el estado de una cita se ejecuta sin una persona.
5. Un cuerpo deforme no rompe el endpoint (perder la suscripcion deja al
   sistema sin recibir las respuestas de ningun paciente).

Los secretos son sinteticos y viven solo en esta prueba (CLAUDE.md, regla 2).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import crear_aplicacion
from app.mensajeria.firma import CABECERA_FIRMA, calcular_firma
from app.mensajeria.rutas import CLAVE_NUMERO
from app.modulos.auditoria.modelos import Auditoria
from app.modulos.conversaciones.agente_whatsapp import INTEGRACION
from app.modulos.conversaciones.modelos import (
    AvisoRevisionTratamiento,
    Conversacion,
    EstadoConversacion,
    IntencionEntrante,
    MensajeEntrante,
)
from app.modulos.organizacion.modelos import Clinica, ConfiguracionClinica
from app.modulos.outbox.modelos import OutboxMensaje
from app.modulos.pacientes.modelos import Consentimiento, Paciente, TipoConsentimiento
from app.nucleo.auditoria import AccionAuditada
from app.nucleo.configuracion import Configuracion
from app.nucleo.dependencias import obtener_sesion
from app.nucleo.reloj import RelojFijo
from pruebas.api.conftest import GestorDeUnaSesion, RedisEnMemoria

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]

# Valores sinteticos. No son ni se parecen a credenciales reales.
SECRETO_APP = "secreto-de-aplicacion-sintetico-para-pruebas"
TOKEN_VERIFICACION = "token-de-verificacion-sintetico"
# El identificador del numero de Meta y el telefono del paciente se generan
# **por prueba**, no son constantes del modulo.
#
# Lo eran, y con valores fijos: `000000000000000` y `593999000111`. Eso acoplaba
# las pruebas al contenido de la base de desarrollo -- basto que un ejercicio
# manual insertara una fila de `configuracion_clinica` con ese mismo
# identificador para que 20 pruebas fallaran, unas por encontrar una clinica
# donde esperaban ninguna y otras por resolver al paciente equivocado.
#
# Con valores unicos por prueba, el resultado no depende de lo que haya en la
# base ni del orden de ejecucion.


@pytest.fixture
def id_numero(sufijo: str) -> str:
    """`phone_number_id` de Meta, unico para esta prueba."""
    return f"9{int(sufijo, 16) % 10**14:014d}"


@pytest.fixture
def telefono(sufijo: str) -> str:
    """El numero **tal como llega del webhook**: solo digitos.

    Es lo que exige y lo que entrega la Cloud API.
    """
    return f"5939{int(sufijo, 16) % 10**8:08d}"


@pytest.fixture
def telefono_guardado(telefono: str) -> str:
    """El mismo numero **tal como lo guarda el panel**: con «+» y espacios.

    La diferencia no es cosmetica. Cuando la fixture guardaba la forma ya
    normalizada, estas pruebas pasaban mientras el sistema real no encontraba al
    paciente, y **un paciente que respondia BAJA seguia recibiendo mensajes**.
    Guardar aqui la forma realista es lo que hace que la prueba sirva.
    """
    return f"+{telefono[:3]} {telefono[3:5]} {telefono[5:8]} {telefono[8:]}"


# ---------------------------------------------------------------------------
#  Aplicacion con los secretos del webhook
# ---------------------------------------------------------------------------
@pytest.fixture
def configuracion_webhook(configuracion: Configuracion, id_numero: str) -> Configuracion:
    """Copia de la configuracion con los secretos del webhook puestos.

    Se copia en lugar de tocar el entorno del proceso: modificar variables de
    entorno en una prueba filtra a las siguientes segun el orden de ejecucion.
    """
    return configuracion.model_copy(
        update={
            "modo_whatsapp": "sandbox",
            "whatsapp_id_numero_telefono": id_numero,
            "whatsapp_secreto_app": SecretStr(SECRETO_APP),
            "whatsapp_token_verificacion": SecretStr(TOKEN_VERIFICACION),
            "whatsapp_validar_firma": True,
        }
    )


@pytest.fixture
def aplicacion_webhook(
    configuracion_webhook: Configuracion,
    sesion: AsyncSession,
    reloj: RelojFijo,
    redis_falso: RedisEnMemoria,
) -> FastAPI:
    app = crear_aplicacion(
        configuracion_webhook,
        reloj=reloj,
        gestor_bd=GestorDeUnaSesion(sesion),
        cliente_redis=redis_falso,
        configurar_logs=False,
    )

    async def _sesion_de_prueba() -> AsyncIterator[AsyncSession]:
        yield sesion

    app.dependency_overrides[obtener_sesion] = _sesion_de_prueba
    return app


@pytest_asyncio.fixture
async def cliente_webhook(aplicacion_webhook: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=aplicacion_webhook),
        base_url="http://pruebas.invalid",
    ) as http:
        yield http


@pytest_asyncio.fixture
async def numero_de_la_clinica(
    sesion: AsyncSession, clinica: Clinica, id_numero: str
) -> ConfiguracionClinica:
    """Asocia el numero de Meta con la clinica.

    Sin esta fila el sistema no sabe a quien pertenece el mensaje, y por diseno
    lo descarta con una alerta en lugar de adivinar.
    """
    registro = ConfiguracionClinica(
        clinica_id=clinica.id,
        clave=CLAVE_NUMERO,
        valor={"valor": id_numero},
        version=1,
        vigente=True,
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


@pytest_asyncio.fixture
async def paciente_con_consentimiento(
    sesion: AsyncSession, clinica: Clinica, sufijo: str, telefono_guardado: str
) -> Paciente:
    registro = Paciente(
        clinica_id=clinica.id,
        tipo_documento="CEDULA",
        numero_documento=f"5{sufijo[:9]}",
        nombre="Paciente Webhook",
        apellido="De Prueba",
        telefono_whatsapp=telefono_guardado,
    )
    sesion.add(registro)
    await sesion.flush()
    for tipo in (
        TipoConsentimiento.COMUNICACION_WHATSAPP,
        TipoConsentimiento.RECORDATORIOS_MEDICACION,
    ):
        sesion.add(
            Consentimiento(
                paciente_id=registro.id,
                tipo=tipo.value,
                otorgado=True,
                version_texto="v1",
                texto_hash="0" * 64,
                canal="PANEL",
            )
        )
    await sesion.flush()
    return registro


# ---------------------------------------------------------------------------
#  Utilidades
# ---------------------------------------------------------------------------
def _cuerpo_mensaje(
    texto: str, *, external_id: str, telefono: str, id_numero: str
) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "0",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "0",
                                "phone_number_id": id_numero,
                            },
                            "messages": [
                                {
                                    "id": external_id,
                                    "from": telefono,
                                    "timestamp": "1776268800",
                                    "type": "text",
                                    "text": {"body": texto},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


async def _enviar(
    cliente: AsyncClient, api: str, cuerpo: dict[str, Any], *, firma: str | None = None
) -> Any:
    # Se serializa una sola vez y se firman esos mismos bytes. Es lo que hace
    # Meta, y lo que obliga a que la ruta lea el cuerpo crudo.
    crudo = json.dumps(cuerpo, separators=(",", ":")).encode("utf-8")
    cabeceras = {
        "Content-Type": "application/json",
        CABECERA_FIRMA: firma if firma is not None else calcular_firma(crudo, SECRETO_APP),
    }
    return await cliente.post(f"{api}/whatsapp/webhook", content=crudo, headers=cabeceras)


# ---------------------------------------------------------------------------
#  Verificacion inicial
# ---------------------------------------------------------------------------
async def test_el_reto_de_verificacion_devuelve_texto_plano(
    cliente_webhook: AsyncClient, api: str
) -> None:
    """Meta exige el reto en texto plano.

    Si se devolviera JSON, el webhook quedaria sin registrar con el sintoma
    confuso de que «responde 200 pero no llegan mensajes».
    """
    respuesta = await cliente_webhook.get(
        f"{api}/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": TOKEN_VERIFICACION,
            "hub.challenge": "1158201444",
        },
    )
    assert respuesta.status_code == 200
    assert respuesta.text == "1158201444"
    assert respuesta.headers["content-type"].startswith("text/plain")


async def test_el_reto_con_token_incorrecto_no_pasa(cliente_webhook: AsyncClient, api: str) -> None:
    respuesta = await cliente_webhook.get(
        f"{api}/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "token-equivocado",
            "hub.challenge": "123",
        },
    )
    assert respuesta.status_code == 403


# ---------------------------------------------------------------------------
#  Firma
# ---------------------------------------------------------------------------
async def test_una_firma_invalida_devuelve_403(
    cliente_webhook: AsyncClient,
    api: str,
    numero_de_la_clinica: ConfiguracionClinica,
    telefono: str,
    id_numero: str,
) -> None:
    """Un tercero podria inyectar cancelaciones que ningun paciente pidio."""
    respuesta = await _enviar(
        cliente_webhook,
        api,
        _cuerpo_mensaje(
            "CANCELAR", external_id="wamid.FALSIFICADO", telefono=telefono, id_numero=id_numero
        ),
        firma="sha256=" + "0" * 64,
    )
    assert respuesta.status_code == 403


async def test_una_firma_invalida_no_produce_ningun_efecto(
    cliente_webhook: AsyncClient,
    api: str,
    sesion: AsyncSession,
    numero_de_la_clinica: ConfiguracionClinica,
    paciente_con_consentimiento: Paciente,
    telefono: str,
    id_numero: str,
) -> None:
    """La comprobacion que de verdad importa: no se escribio nada.

    Un 403 con el mensaje ya guardado seria peor que un 200.
    """
    await _enviar(
        cliente_webhook,
        api,
        _cuerpo_mensaje(
            "BAJA", external_id="wamid.FALSIFICADO2", telefono=telefono, id_numero=id_numero
        ),
        firma="sha256=" + "1" * 64,
    )

    # Se cuenta SOLO el identificador de esta prueba. Contar la tabla entera
    # supondria una base vacia, y la de desarrollo no lo esta: la prueba
    # fallaria por datos ajenos en lugar de por el comportamiento que mide.
    mensajes = await sesion.scalar(
        sa.select(sa.func.count())
        .select_from(MensajeEntrante)
        .where(MensajeEntrante.external_id == "wamid.FALSIFICADO2")
    )
    assert mensajes == 0

    # El consentimiento sigue vigente: la baja falsificada no se aplico.
    vigentes = await sesion.scalar(
        sa.select(sa.func.count())
        .select_from(Consentimiento)
        .where(
            Consentimiento.paciente_id == paciente_con_consentimiento.id,
            Consentimiento.revocado_en.is_(None),
        )
    )
    assert vigentes == 2


async def test_una_firma_invalida_queda_auditada(
    cliente_webhook: AsyncClient,
    api: str,
    sesion: AsyncSession,
    numero_de_la_clinica: ConfiguracionClinica,
    telefono: str,
    id_numero: str,
) -> None:
    """`webhook.firma_invalida` es una de las acciones con alerta.

    Alguien esta intentando inyectar mensajes; detectarlo en una revision
    mensual llega tarde.
    """
    await _enviar(
        cliente_webhook,
        api,
        _cuerpo_mensaje(
            "CANCELAR", external_id="wamid.FALSIFICADO3", telefono=telefono, id_numero=id_numero
        ),
        firma="sha256=" + "2" * 64,
    )

    accion = await sesion.scalar(
        sa.select(Auditoria.accion).where(
            Auditoria.accion == AccionAuditada.WEBHOOK_FIRMA_INVALIDA.value
        )
    )
    assert accion == AccionAuditada.WEBHOOK_FIRMA_INVALIDA.value


async def test_sin_cabecera_de_firma_devuelve_403(
    cliente_webhook: AsyncClient,
    api: str,
    telefono: str,
    id_numero: str,
) -> None:
    respuesta = await cliente_webhook.post(
        f"{api}/whatsapp/webhook",
        json=_cuerpo_mensaje(
            "hola", external_id="wamid.SINFIRMA", telefono=telefono, id_numero=id_numero
        ),
    )
    assert respuesta.status_code == 403


# ---------------------------------------------------------------------------
#  Recepcion
# ---------------------------------------------------------------------------
async def test_un_mensaje_valido_abre_conversacion_y_se_guarda(
    cliente_webhook: AsyncClient,
    api: str,
    sesion: AsyncSession,
    clinica: Clinica,
    numero_de_la_clinica: ConfiguracionClinica,
    paciente_con_consentimiento: Paciente,
    telefono: str,
    id_numero: str,
) -> None:
    respuesta = await _enviar(
        cliente_webhook,
        api,
        _cuerpo_mensaje(
            "Buenas tardes, tengo una duda",
            external_id="wamid.NUEVO1",
            telefono=telefono,
            id_numero=id_numero,
        ),
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["mensajes"] == 1

    conversacion = (
        await sesion.execute(sa.select(Conversacion).where(Conversacion.clinica_id == clinica.id))
    ).scalar_one()
    # Un mensaje que el sistema no interpreta va a una persona.
    assert conversacion.estado == EstadoConversacion.EN_HANDOFF.value
    assert conversacion.motivo_handoff is not None
    # Identidad resuelta: solo un paciente tiene ese numero.
    assert conversacion.paciente_id == paciente_con_consentimiento.id
    # La ventana de 24 horas queda registrada para que el personal sepa si
    # puede responder con texto libre.
    assert conversacion.ventana_expira_en is not None

    mensaje = (
        await sesion.execute(
            sa.select(MensajeEntrante).where(MensajeEntrante.external_id == "wamid.NUEVO1")
        )
    ).scalar_one()
    assert mensaje.intencion == IntencionEntrante.DESCONOCIDA.value


async def test_un_reintento_de_meta_no_duplica_el_efecto(
    cliente_webhook: AsyncClient,
    api: str,
    sesion: AsyncSession,
    numero_de_la_clinica: ConfiguracionClinica,
    paciente_con_consentimiento: Paciente,
    telefono: str,
    id_numero: str,
) -> None:
    """Meta entrega al menos una vez y reintenta ante cualquier duda.

    La restriccion unica sobre `external_id` es lo que lo absorbe.
    """
    cuerpo = _cuerpo_mensaje(
        "Tengo una consulta", external_id="wamid.REINTENTO", telefono=telefono, id_numero=id_numero
    )

    primera = await _enviar(cliente_webhook, api, cuerpo)
    segunda = await _enviar(cliente_webhook, api, cuerpo)

    assert primera.json()["mensajes"] == 1
    assert segunda.json()["mensajes"] == 0
    assert segunda.json()["duplicados"] == 1

    total = await sesion.scalar(
        sa.select(sa.func.count())
        .select_from(MensajeEntrante)
        .where(MensajeEntrante.external_id == "wamid.REINTENTO")
    )
    assert total == 1


async def test_dos_mensajes_del_mismo_numero_comparten_hilo(
    cliente_webhook: AsyncClient,
    api: str,
    sesion: AsyncSession,
    clinica: Clinica,
    numero_de_la_clinica: ConfiguracionClinica,
    paciente_con_consentimiento: Paciente,
    telefono: str,
    id_numero: str,
) -> None:
    """Un hilo partido en dos deja al personal viendo media conversacion."""
    await _enviar(
        cliente_webhook,
        api,
        _cuerpo_mensaje("hola", external_id="wamid.HILO1", telefono=telefono, id_numero=id_numero),
    )
    await _enviar(
        cliente_webhook,
        api,
        _cuerpo_mensaje(
            "sigo aqui", external_id="wamid.HILO2", telefono=telefono, id_numero=id_numero
        ),
    )

    conversaciones = await sesion.scalar(
        sa.select(sa.func.count())
        .select_from(Conversacion)
        .where(Conversacion.clinica_id == clinica.id)
    )
    assert conversaciones == 1


# ---------------------------------------------------------------------------
#  Baja: la unica intencion que se ejecuta sin una persona
# ---------------------------------------------------------------------------
async def test_la_baja_revoca_el_consentimiento_de_inmediato(
    cliente_webhook: AsyncClient,
    api: str,
    sesion: AsyncSession,
    numero_de_la_clinica: ConfiguracionClinica,
    paciente_con_consentimiento: Paciente,
    telefono: str,
    id_numero: str,
) -> None:
    """Si alguien pide que dejen de escribirle, se deja de escribirle ya.

    Esperar a que una persona lo lea el lunes significa seguir escribiendole
    el fin de semana.
    """
    respuesta = await _enviar(
        cliente_webhook,
        api,
        _cuerpo_mensaje("BAJA", external_id="wamid.BAJA1", telefono=telefono, id_numero=id_numero),
    )
    assert respuesta.status_code == 200

    vigentes = await sesion.scalar(
        sa.select(sa.func.count())
        .select_from(Consentimiento)
        .where(
            Consentimiento.paciente_id == paciente_con_consentimiento.id,
            Consentimiento.revocado_en.is_(None),
        )
    )
    assert vigentes == 0


async def test_la_baja_no_borra_el_consentimiento(
    cliente_webhook: AsyncClient,
    api: str,
    sesion: AsyncSession,
    numero_de_la_clinica: ConfiguracionClinica,
    paciente_con_consentimiento: Paciente,
    telefono: str,
    id_numero: str,
) -> None:
    """Hay que poder demostrar que hubo consentimiento mientras se enviaba.

    La revocacion marca `revocado_en`; no borra la fila.
    """
    await _enviar(
        cliente_webhook,
        api,
        _cuerpo_mensaje("STOP", external_id="wamid.BAJA2", telefono=telefono, id_numero=id_numero),
    )

    filas = (
        (
            await sesion.execute(
                sa.select(Consentimiento).where(
                    Consentimiento.paciente_id == paciente_con_consentimiento.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(filas) == 2
    assert all(fila.revocado_en is not None for fila in filas)
    assert all(fila.otorgado for fila in filas)


async def test_la_baja_cierra_el_hilo(
    cliente_webhook: AsyncClient,
    api: str,
    sesion: AsyncSession,
    clinica: Clinica,
    numero_de_la_clinica: ConfiguracionClinica,
    paciente_con_consentimiento: Paciente,
    telefono: str,
    id_numero: str,
) -> None:
    """Dejarlo abierto en la cola del personal invita a responderle."""
    await _enviar(
        cliente_webhook,
        api,
        _cuerpo_mensaje("baja", external_id="wamid.BAJA3", telefono=telefono, id_numero=id_numero),
    )

    conversacion = (
        await sesion.execute(sa.select(Conversacion).where(Conversacion.clinica_id == clinica.id))
    ).scalar_one()
    assert conversacion.estado == EstadoConversacion.CERRADA.value
    assert conversacion.cerrada_en is not None


# ---------------------------------------------------------------------------
#  La frontera clinica
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("texto", "intencion"),
    [
        ("CANCELAR", IntencionEntrante.CANCELAR),
        ("CONFIRMAR", IntencionEntrante.CONFIRMAR),
        ("SI", IntencionEntrante.ACEPTAR_OFERTA),
        ("TOMADA", IntencionEntrante.REGISTRAR_TOMA),
        ("ALTA", IntencionEntrante.ALTA),
    ],
)
async def test_ninguna_intencion_de_estado_se_ejecuta_sin_una_persona(
    cliente_webhook: AsyncClient,
    api: str,
    sesion: AsyncSession,
    clinica: Clinica,
    numero_de_la_clinica: ConfiguracionClinica,
    paciente_con_consentimiento: Paciente,
    texto: str,
    intencion: IntencionEntrante,
    telefono: str,
    id_numero: str,
) -> None:
    """Se reconoce la intencion, se registra, y se deriva.

    Un telefono no identifica a una persona en este sistema: una madre
    gestiona las citas de sus tres hijos desde el mismo numero. Cancelar la
    cita equivocada de una familia es un dano real.
    """
    external_id = f"wamid.ESTADO-{uuid.uuid4().hex[:8]}"
    await _enviar(
        cliente_webhook,
        api,
        _cuerpo_mensaje(texto, external_id=external_id, telefono=telefono, id_numero=id_numero),
    )

    mensaje = (
        await sesion.execute(
            sa.select(MensajeEntrante).where(MensajeEntrante.external_id == external_id)
        )
    ).scalar_one()
    assert mensaje.intencion == intencion.value

    conversacion = (
        await sesion.execute(sa.select(Conversacion).where(Conversacion.clinica_id == clinica.id))
    ).scalar_one()
    assert conversacion.estado == EstadoConversacion.EN_HANDOFF.value


async def test_un_mensaje_clinico_se_deriva_y_no_se_interpreta(
    cliente_webhook: AsyncClient,
    api: str,
    sesion: AsyncSession,
    clinica: Clinica,
    numero_de_la_clinica: ConfiguracionClinica,
    paciente_con_consentimiento: Paciente,
    telefono: str,
    id_numero: str,
) -> None:
    """CLAUDE.md, regla 5, en el camino real.

    «la pastilla me da nauseas» no produce ninguna accion automatica.
    """
    await _enviar(
        cliente_webhook,
        api,
        _cuerpo_mensaje(
            "la pastilla me da nauseas",
            external_id="wamid.CLINICO",
            telefono=telefono,
            id_numero=id_numero,
        ),
    )

    mensaje = (
        await sesion.execute(
            sa.select(MensajeEntrante).where(MensajeEntrante.external_id == "wamid.CLINICO")
        )
    ).scalar_one()
    assert mensaje.intencion == IntencionEntrante.DESCONOCIDA.value

    conversacion = (
        await sesion.execute(sa.select(Conversacion).where(Conversacion.clinica_id == clinica.id))
    ).scalar_one()
    assert conversacion.estado == EstadoConversacion.EN_HANDOFF.value

    # Y el consentimiento sigue intacto: no se confundio con una baja.
    vigentes = await sesion.scalar(
        sa.select(sa.func.count())
        .select_from(Consentimiento)
        .where(
            Consentimiento.paciente_id == paciente_con_consentimiento.id,
            Consentimiento.revocado_en.is_(None),
        )
    )
    assert vigentes == 2


async def test_reporte_explicito_de_problema_se_etiqueta_y_deriva_sin_pedir_identidad(
    cliente_webhook: AsyncClient,
    api: str,
    sesion: AsyncSession,
    clinica: Clinica,
    numero_de_la_clinica: ConfiguracionClinica,
    paciente_con_consentimiento: Paciente,
    telefono: str,
    id_numero: str,
) -> None:
    """El personal recibe la etiqueta sin revelar pacientes de numeros compartidos."""
    segundo_paciente = Paciente(
        clinica_id=clinica.id,
        tipo_documento="CEDULA",
        numero_documento=f"7{uuid.uuid4().int % 10**9:09d}",
        nombre="Familiar",
        apellido="De Prueba",
        telefono_whatsapp=paciente_con_consentimiento.telefono_whatsapp,
    )
    sesion.add(segundo_paciente)
    await sesion.flush()
    external_id = "wamid.REPORTE-TRATAMIENTO"
    respuesta = await _enviar(
        cliente_webhook,
        api,
        _cuerpo_mensaje(
            "tengo un problema con mi medicamento",
            external_id=external_id,
            telefono=telefono,
            id_numero=id_numero,
        ),
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["mensajes"] == 1
    mensaje = (
        await sesion.execute(
            sa.select(MensajeEntrante).where(MensajeEntrante.external_id == external_id)
        )
    ).scalar_one()
    assert mensaje.intencion == IntencionEntrante.PROBLEMA_TRATAMIENTO.value
    conversacion = (
        await sesion.execute(sa.select(Conversacion).where(Conversacion.clinica_id == clinica.id))
    ).scalar_one()
    assert conversacion.estado == EstadoConversacion.EN_HANDOFF.value
    assert conversacion.motivo_handoff.startswith("REVISIÓN CLÍNICA")
    assert conversacion.paciente_id is None
    assert conversacion.seleccion_pendiente is None
    aviso = await sesion.scalar(
        sa.select(AvisoRevisionTratamiento).where(
            AvisoRevisionTratamiento.mensaje_entrante_id == mensaje.id
        )
    )
    assert aviso is not None
    auditado = await sesion.scalar(
        sa.select(sa.func.count())
        .select_from(Auditoria)
        .where(
            Auditoria.accion == AccionAuditada.AVISO_TRATAMIENTO_CREADO.value,
            Auditoria.entidad_id == aviso.id,
        )
    )
    assert auditado == 1


# ---------------------------------------------------------------------------
#  Robustez: no perder la suscripcion
# ---------------------------------------------------------------------------
async def test_un_numero_sin_clinica_no_rompe_el_endpoint(
    cliente_webhook: AsyncClient,
    api: str,
    sesion: AsyncSession,
    telefono: str,
    id_numero: str,
) -> None:
    # No se pide `numero_de_la_clinica`: el objetivo es justo que no exista la
    # fila que asocia el numero con una clinica.
    """Sin la fila de configuracion, el mensaje se descarta con alerta.

    Se responde 200: un 5xx repetido le cuesta al sistema la suscripcion del
    webhook, y entonces no llegan las respuestas de **ningun** paciente.
    """
    respuesta = await _enviar(
        cliente_webhook,
        api,
        _cuerpo_mensaje(
            "hola", external_id="wamid.SINCLINICA", telefono=telefono, id_numero=id_numero
        ),
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["mensajes"] == 0

    total = await sesion.scalar(
        sa.select(sa.func.count())
        .select_from(MensajeEntrante)
        .where(MensajeEntrante.external_id == "wamid.SINCLINICA")
    )
    assert total == 0


@pytest.mark.parametrize(
    "cuerpo",
    [
        {},
        {"object": "whatsapp_business_account"},
        {"entry": None},
        {"entry": [{"changes": [{"value": {"messages": "no es lista"}}]}]},
        {"entry": [{"changes": [{"value": {"statuses": None}}]}]},
    ],
)
async def test_un_cuerpo_deforme_devuelve_200(
    cliente_webhook: AsyncClient, api: str, cuerpo: dict[str, Any]
) -> None:
    respuesta = await _enviar(cliente_webhook, api, cuerpo)
    assert respuesta.status_code == 200


async def test_un_cuerpo_que_no_es_json_devuelve_200(
    cliente_webhook: AsyncClient, api: str
) -> None:
    """Con firma valida pero cuerpo ilegible: se acusa recibo y se registra."""
    crudo = b"esto no es json"
    respuesta = await cliente_webhook.post(
        f"{api}/whatsapp/webhook",
        content=crudo,
        headers={
            "Content-Type": "application/json",
            CABECERA_FIRMA: calcular_firma(crudo, SECRETO_APP),
        },
    )
    assert respuesta.status_code == 200


async def test_el_webhook_no_devuelve_datos_del_paciente(
    cliente_webhook: AsyncClient,
    api: str,
    numero_de_la_clinica: ConfiguracionClinica,
    paciente_con_consentimiento: Paciente,
    telefono: str,
    id_numero: str,
    telefono_guardado: str,
) -> None:
    """La respuesta es un acuse de recibo, no una vista de datos.

    El cuerpo lo lee Meta, no la clinica: cualquier dato ahi sale del sistema
    sin control de acceso.
    """
    respuesta = await _enviar(
        cliente_webhook,
        api,
        _cuerpo_mensaje(
            "hola", external_id="wamid.SINDATOS", telefono=telefono, id_numero=id_numero
        ),
    )
    cuerpo = respuesta.text
    assert telefono not in cuerpo
    assert telefono_guardado not in cuerpo
    assert "Paciente Webhook" not in cuerpo
    assert str(paciente_con_consentimiento.id) not in cuerpo


# ---------------------------------------------------------------------------
#  Regresion: el formato del numero
# ---------------------------------------------------------------------------
# Estas tres pruebas existen por un fallo encontrado **ejerciendo el sistema**
# con las semillas reales, con 891 pruebas en verde. El panel guarda
# «+593 99 900 0111» y el webhook entrega «593999000111»; la comparacion en
# crudo no encontraba a nadie, y un paciente que respondia BAJA seguia
# recibiendo mensajes.
#
# Las fixtures guardaban el numero ya normalizado, asi que la suite no lo veia.
# Vivia en el espacio entre lo que la fixture suponia y lo que los datos reales
# tienen.
async def test_la_identidad_se_resuelve_con_el_numero_en_formato_de_panel(
    cliente_webhook: AsyncClient,
    api: str,
    sesion: AsyncSession,
    clinica: Clinica,
    numero_de_la_clinica: ConfiguracionClinica,
    paciente_con_consentimiento: Paciente,
    telefono: str,
    id_numero: str,
    telefono_guardado: str,
) -> None:
    """El paciente se encuentra aunque su numero esté guardado con «+» y espacios."""
    assert paciente_con_consentimiento.telefono_whatsapp == telefono_guardado

    await _enviar(
        cliente_webhook,
        api,
        _cuerpo_mensaje(
            "hola", external_id="wamid.FORMATO1", telefono=telefono, id_numero=id_numero
        ),
    )

    conversacion = (
        await sesion.execute(sa.select(Conversacion).where(Conversacion.clinica_id == clinica.id))
    ).scalar_one()
    assert conversacion.paciente_id == paciente_con_consentimiento.id


async def test_la_baja_funciona_con_el_numero_en_formato_de_panel(
    cliente_webhook: AsyncClient,
    api: str,
    sesion: AsyncSession,
    numero_de_la_clinica: ConfiguracionClinica,
    paciente_con_consentimiento: Paciente,
    telefono: str,
    id_numero: str,
) -> None:
    """La prueba que el fallo original habria hecho fallar.

    Es la mas importante de este archivo: si la revocacion no encuentra al
    paciente, el sistema sigue escribiendo a quien pidió que pararan.
    """
    await _enviar(
        cliente_webhook,
        api,
        _cuerpo_mensaje(
            "BAJA", external_id="wamid.FORMATO2", telefono=telefono, id_numero=id_numero
        ),
    )

    vigentes = await sesion.scalar(
        sa.select(sa.func.count())
        .select_from(Consentimiento)
        .where(
            Consentimiento.paciente_id == paciente_con_consentimiento.id,
            Consentimiento.revocado_en.is_(None),
        )
    )
    assert vigentes == 0, (
        "La baja no revoco el consentimiento: la comparacion del telefono no "
        "encontro al paciente. El sistema le seguiria escribiendo."
    )


# Los formatos se derivan del numero de la prueba, no son cadenas fijas: con
# `telefono` unico por prueba, una constante no coincidiria con nada.
@pytest.mark.parametrize(
    "formato",
    [
        "{n}",
        "+{n}",
        "+{a} {b} {c} {d}",
        "{a}-{b}-{c}{d}",
        "({a}) {b} {c} {d}",
        " {n} ",
    ],
)
async def test_cualquier_formato_guardado_resuelve_el_mismo_numero(
    cliente_webhook: AsyncClient,
    api: str,
    sesion: AsyncSession,
    clinica: Clinica,
    numero_de_la_clinica: ConfiguracionClinica,
    paciente_con_consentimiento: Paciente,
    telefono: str,
    id_numero: str,
    formato: str,
) -> None:
    """El personal escribe el numero como quiere, y debe encontrarse igual.

    Ninguno de estos formatos es exotico: son los que produce copiar un numero
    de una agenda, de un mensaje o de un documento.
    """
    paciente_con_consentimiento.telefono_whatsapp = formato.format(
        n=telefono,
        a=telefono[:3],
        b=telefono[3:5],
        c=telefono[5:8],
        d=telefono[8:],
    )
    await sesion.flush()

    external_id = f"wamid.FMT-{uuid.uuid4().hex[:8]}"
    await _enviar(
        cliente_webhook,
        api,
        _cuerpo_mensaje("hola", external_id=external_id, telefono=telefono, id_numero=id_numero),
    )

    conversacion = (
        await sesion.execute(sa.select(Conversacion).where(Conversacion.clinica_id == clinica.id))
    ).scalar_one()
    assert conversacion.paciente_id == paciente_con_consentimiento.id, (
        f"El numero guardado como «{paciente_con_consentimiento.telefono_whatsapp}» no se resolvio."
    )


# ---------------------------------------------------------------------------
#  Agente conversacional (ADR-0025)
# ---------------------------------------------------------------------------
async def test_con_el_agente_activo_la_consulta_se_responde_por_el_outbox(
    cliente_webhook: AsyncClient,
    api: str,
    sesion: AsyncSession,
    clinica: Clinica,
    numero_de_la_clinica: ConfiguracionClinica,
    paciente_con_consentimiento: Paciente,
    telefono: str,
    id_numero: str,
) -> None:
    """De punta a punta: firma, recepcion, turno del agente y respuesta encolada."""
    sesion.add(
        ConfiguracionClinica(
            clinica_id=clinica.id,
            clave=f"integracion.{INTEGRACION}",
            valor={"habilitada": True, "ajustes": {}, "secretos_cifrados": {}},
        )
    )
    await sesion.flush()

    respuesta = await _enviar(
        cliente_webhook,
        api,
        _cuerpo_mensaje(
            "mis citas", external_id="wamid.AGENTE1", telefono=telefono, id_numero=id_numero
        ),
    )

    assert respuesta.status_code == 200
    conversacion = (
        await sesion.execute(
            sa.select(Conversacion).where(
                Conversacion.clinica_id == clinica.id, Conversacion.telefono == telefono
            )
        )
    ).scalar_one()
    assert conversacion.estado == EstadoConversacion.ABIERTA.value
    respuestas = (
        (
            await sesion.execute(
                sa.select(OutboxMensaje).where(
                    OutboxMensaje.destino_tipo == "CONVERSACION",
                    OutboxMensaje.destino_id == conversacion.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(respuestas) == 1
    assert respuestas[0].carga_util.get("libre") is True
