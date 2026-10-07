"""El outbox transaccional contra PostgreSQL real (ADR-0008).

Lo que se verifica aqui son garantias del motor, no del codigo Python:

* La restriccion unica sobre `clave_deduplicacion` es lo que impide que un
  paciente reciba el mismo recordatorio dos veces.
* El `ON CONFLICT DO NOTHING` es lo que impide que ese duplicado aborte la
  transaccion **de negocio** que lo encolo.
* El rollback de la transaccion de negocio se lleva el mensaje con ella.

Un doble de prueba no tiene ninguna de las tres.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.mensajeria.adaptadores import (
    AdaptadorSandbox,
    RegistroCanales,
    ResultadoEnvio,
)
from app.mensajeria.servicios import (
    RETROCESO_MAXIMO_SEGUNDOS,
    ServicioOutbox,
    SolicitudEnvio,
)
from app.modelos import Clinica, Consentimiento, Paciente
from app.modulos.outbox.modelos import (
    CanalOutbox,
    EstadoOutbox,
    OutboxMensaje,
    Recordatorio,
    TipoMensajeOutbox,
)
from app.modulos.pacientes.modelos import TipoConsentimiento
from app.nucleo.errores import ConsentimientoRequerido
from app.nucleo.reloj import RelojFijo

pytestmark = [pytest.mark.integracion, pytest.mark.asyncio]

TELEFONO_SINTETICO = "593999000111"


# ---------------------------------------------------------------------------
#  Fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def paciente_con_whatsapp(sesion: AsyncSession, clinica: Clinica, sufijo: str) -> Paciente:
    """Paciente con numero y consentimiento vigente.

    El numero es sintetico y con formato de panel (con espacios y «+») a
    proposito: asi la prueba ejerce tambien la normalizacion que la Cloud API
    exige.
    """
    registro = Paciente(
        clinica_id=clinica.id,
        tipo_documento="CEDULA",
        numero_documento=f"7{sufijo[:9]}",
        nombre="Paciente Con WhatsApp",
        apellido="De Prueba",
        telefono_whatsapp=f"+{TELEFONO_SINTETICO}",
    )
    sesion.add(registro)
    await sesion.flush()

    sesion.add(
        Consentimiento(
            paciente_id=registro.id,
            tipo=TipoConsentimiento.COMUNICACION_WHATSAPP.value,
            otorgado=True,
            version_texto="v1",
            texto_hash="0" * 64,
            canal="PANEL",
        )
    )
    await sesion.flush()
    return registro


@pytest.fixture
def canal() -> AdaptadorSandbox:
    return AdaptadorSandbox("whatsapp_sandbox")


@pytest.fixture
def canales(canal: AdaptadorSandbox) -> RegistroCanales:
    registro = RegistroCanales()
    registro.registrar(CanalOutbox.WHATSAPP.value, canal)
    return registro


@pytest.fixture
def reloj_fijo(instante: datetime) -> RelojFijo:
    return RelojFijo(instante)


@pytest.fixture
def servicio(
    sesion: AsyncSession, reloj_fijo: RelojFijo, canales: RegistroCanales
) -> ServicioOutbox:
    return ServicioOutbox(sesion, reloj_fijo, canales, max_intentos=3, retroceso_base_segundos=30)


def _solicitud(paciente: Paciente, clinica: Clinica, *, clave: str) -> SolicitudEnvio:
    return SolicitudEnvio(
        tipo=TipoMensajeOutbox.CITA_RECORDATORIO_DIA_ANTES,
        canal=CanalOutbox.WHATSAPP,
        destino_tipo="PACIENTE",
        destino_id=paciente.id,
        clave_deduplicacion=clave,
        variables={
            "nombre": "Paciente",
            "fecha": "16 de abril",
            "hora": "09:30",
            "sede": "Sede de Prueba",
            "profesional": "Profesional De Prueba",
        },
        clinica_id=clinica.id,
        entidad_origen_tipo="cita",
        entidad_origen_id=uuid.uuid4(),
    )


# ---------------------------------------------------------------------------
#  Encolado y deduplicacion
# ---------------------------------------------------------------------------
async def test_encolar_escribe_el_mensaje_pendiente(
    servicio: ServicioOutbox,
    sesion: AsyncSession,
    paciente_con_whatsapp: Paciente,
    clinica: Clinica,
    sufijo: str,
) -> None:
    identificador = await servicio.encolar(
        _solicitud(paciente_con_whatsapp, clinica, clave=f"dedup-{sufijo}")
    )
    assert identificador is not None

    mensaje = await sesion.get(OutboxMensaje, identificador)
    assert mensaje is not None
    assert mensaje.estado == EstadoOutbox.PENDIENTE.value
    assert mensaje.intentos == 0
    assert mensaje.canal == CanalOutbox.WHATSAPP.value


async def test_la_misma_clave_no_encola_dos_veces(
    servicio: ServicioOutbox,
    sesion: AsyncSession,
    paciente_con_whatsapp: Paciente,
    clinica: Clinica,
    sufijo: str,
) -> None:
    """Recibir dos recordatorios de la misma cita lleva a silenciar el canal.

    Lo que es peor que no enviarlos.
    """
    clave = f"dedup-unica-{sufijo}"
    primero = await servicio.encolar(_solicitud(paciente_con_whatsapp, clinica, clave=clave))
    segundo = await servicio.encolar(_solicitud(paciente_con_whatsapp, clinica, clave=clave))

    assert primero is not None
    assert segundo is None

    total = await sesion.scalar(
        sa.select(sa.func.count())
        .select_from(OutboxMensaje)
        .where(OutboxMensaje.clave_deduplicacion == clave)
    )
    assert total == 1


async def test_el_duplicado_no_aborta_la_transaccion_de_negocio(
    servicio: ServicioOutbox,
    sesion: AsyncSession,
    paciente_con_whatsapp: Paciente,
    clinica: Clinica,
    sufijo: str,
) -> None:
    """Es la razon de `ON CONFLICT DO NOTHING`, y no es cosmetica.

    Si la violacion de la clave unica subiera, un segundo intento de confirmar
    la misma cita fallaria entero por un recordatorio duplicado.  Aqui se
    comprueba que despues del duplicado la sesion sigue utilizable.
    """
    clave = f"dedup-no-aborta-{sufijo}"
    await servicio.encolar(_solicitud(paciente_con_whatsapp, clinica, clave=clave))
    await servicio.encolar(_solicitud(paciente_con_whatsapp, clinica, clave=clave))

    # La sesion sigue viva: se puede seguir escribiendo despues del conflicto.
    otro = await servicio.encolar(
        _solicitud(paciente_con_whatsapp, clinica, clave=f"{clave}-distinta")
    )
    assert otro is not None


async def test_encolar_no_confirma_la_transaccion(
    servicio: ServicioOutbox,
    sesion: AsyncSession,
    paciente_con_whatsapp: Paciente,
    clinica: Clinica,
    sufijo: str,
) -> None:
    """Si la operacion de negocio se revierte, el mensaje se va con ella.

    Es toda la gracia del patron: no puede quedar un recordatorio de una cita
    que nunca existio.
    """
    clave = f"dedup-rollback-{sufijo}"
    await servicio.encolar(_solicitud(paciente_con_whatsapp, clinica, clave=clave))
    await sesion.rollback()

    total = await sesion.scalar(
        sa.select(sa.func.count())
        .select_from(OutboxMensaje)
        .where(OutboxMensaje.clave_deduplicacion == clave)
    )
    assert total == 0


# ---------------------------------------------------------------------------
#  Consentimiento
# ---------------------------------------------------------------------------
async def test_sin_consentimiento_no_se_encola(
    servicio: ServicioOutbox,
    paciente: Paciente,
    clinica: Clinica,
    sufijo: str,
) -> None:
    """El paciente base de las fixtures no tiene consentimiento."""
    with pytest.raises(ConsentimientoRequerido):
        await servicio.encolar(_solicitud(paciente, clinica, clave=f"sin-consent-{sufijo}"))


async def test_el_consentimiento_revocado_impide_el_envio(
    servicio: ServicioOutbox,
    sesion: AsyncSession,
    paciente_con_whatsapp: Paciente,
    clinica: Clinica,
    reloj_fijo: RelojFijo,
    sufijo: str,
) -> None:
    """Una baja aplicada corta los envios proactivos de inmediato."""
    await sesion.execute(
        sa.update(Consentimiento)
        .where(Consentimiento.paciente_id == paciente_con_whatsapp.id)
        .values(revocado_en=reloj_fijo.ahora())
    )
    await sesion.flush()

    with pytest.raises(ConsentimientoRequerido):
        await servicio.encolar(
            _solicitud(paciente_con_whatsapp, clinica, clave=f"revocado-{sufijo}")
        )


async def test_revocar_despues_de_encolar_impide_la_entrega(
    servicio: ServicioOutbox,
    sesion: AsyncSession,
    canal: AdaptadorSandbox,
    paciente_con_whatsapp: Paciente,
    clinica: Clinica,
    reloj_fijo: RelojFijo,
    sufijo: str,
) -> None:
    """Una baja posterior al encolado debe detener el envío pendiente."""
    identificador = await servicio.encolar(
        _solicitud(paciente_con_whatsapp, clinica, clave=f"revocado-pendiente-{sufijo}")
    )
    assert identificador is not None

    await sesion.execute(
        sa.update(Consentimiento)
        .where(Consentimiento.paciente_id == paciente_con_whatsapp.id)
        .values(revocado_en=reloj_fijo.ahora())
    )
    await sesion.flush()

    resumen = await servicio.procesar_lote(tamano=10, worker="prueba-revocacion")

    mensaje = await sesion.get(OutboxMensaje, identificador)
    assert mensaje is not None
    assert mensaje.estado == EstadoOutbox.DESCARTADO.value
    assert resumen.entregados == 0
    assert resumen.descartados == 1
    assert canal.enviados == []


async def test_el_recordatorio_de_toma_exige_su_propio_consentimiento(
    servicio: ServicioOutbox,
    paciente_con_whatsapp: Paciente,
    clinica: Clinica,
    sufijo: str,
) -> None:
    """Aceptar avisos de cita no es aceptar avisos sobre la medicacion.

    El paciente de la fixture tiene COMUNICACION_WHATSAPP pero no
    RECORDATORIOS_MEDICACION.
    """
    solicitud = SolicitudEnvio(
        tipo=TipoMensajeOutbox.TOMA_RECORDATORIO,
        canal=CanalOutbox.WHATSAPP,
        destino_tipo="PACIENTE",
        destino_id=paciente_con_whatsapp.id,
        clave_deduplicacion=f"toma-{sufijo}",
        variables={"nombre": "Paciente", "enlace": "https://ejemplo.invalid/t"},
        clinica_id=clinica.id,
    )
    with pytest.raises(ConsentimientoRequerido) as fallo:
        await servicio.encolar(solicitud)

    # El tipo exacto viaja en los detalles, no en el mensaje: es lo que
    # permite al panel decir que consentimiento hay que pedir.
    assert fallo.value.detalles["consentimiento"] == (
        TipoConsentimiento.RECORDATORIOS_MEDICACION.value
    )


# ---------------------------------------------------------------------------
#  Entrega
# ---------------------------------------------------------------------------
async def test_un_mensaje_pendiente_se_entrega_y_se_marca(
    servicio: ServicioOutbox,
    sesion: AsyncSession,
    canal: AdaptadorSandbox,
    paciente_con_whatsapp: Paciente,
    clinica: Clinica,
    sufijo: str,
) -> None:
    identificador = await servicio.encolar(
        _solicitud(paciente_con_whatsapp, clinica, clave=f"entrega-{sufijo}")
    )
    assert identificador is not None

    resumen = await servicio.procesar_lote(tamano=10, worker="prueba")
    assert resumen.entregados >= 1

    mensaje = await sesion.get(OutboxMensaje, identificador, populate_existing=True)
    assert mensaje is not None
    assert mensaje.estado == EstadoOutbox.ENTREGADO.value
    assert mensaje.intentos == 1
    assert mensaje.entregado_en is not None
    # La referencia externa es lo que permite conciliar despues el estado de
    # entrega que llega por webhook.
    assert mensaje.referencia_externa is not None


async def test_el_telefono_se_normaliza_al_entregar(
    servicio: ServicioOutbox,
    canal: AdaptadorSandbox,
    paciente_con_whatsapp: Paciente,
    clinica: Clinica,
    sufijo: str,
) -> None:
    """La Cloud API exige solo digitos; el panel guarda «+593 99...».

    Un numero con formato se rechaza en el proveedor, y ese rechazo aparece
    como fallo de entrega sin explicacion util.
    """
    await servicio.encolar(_solicitud(paciente_con_whatsapp, clinica, clave=f"normaliza-{sufijo}"))
    await servicio.procesar_lote(tamano=10, worker="prueba")

    assert canal.enviados
    assert canal.enviados[-1].mensaje.destino == TELEFONO_SINTETICO


async def test_el_telefono_no_se_guarda_en_el_outbox(
    servicio: ServicioOutbox,
    sesion: AsyncSession,
    paciente_con_whatsapp: Paciente,
    clinica: Clinica,
    sufijo: str,
) -> None:
    """Minimizacion: el historico del outbox no es un registro de contactos.

    Se resuelve al entregar. Si se copiara al encolar, un cambio de numero
    entre el encolado y la entrega mandaria el mensaje al antiguo -- que puede
    pertenecer ya a otra persona.
    """
    identificador = await servicio.encolar(
        _solicitud(paciente_con_whatsapp, clinica, clave=f"sin-telefono-{sufijo}")
    )
    assert identificador is not None

    mensaje = await sesion.get(OutboxMensaje, identificador)
    assert mensaje is not None
    assert TELEFONO_SINTETICO not in str(mensaje.carga_util)


async def test_un_fallo_temporal_se_reprograma_con_retroceso(
    servicio: ServicioOutbox,
    sesion: AsyncSession,
    canal: AdaptadorSandbox,
    paciente_con_whatsapp: Paciente,
    clinica: Clinica,
    reloj_fijo: RelojFijo,
    sufijo: str,
) -> None:
    canal.programar_fallo(ResultadoEnvio.FALLO_TEMPORAL, "proveedor caido")
    identificador = await servicio.encolar(
        _solicitud(paciente_con_whatsapp, clinica, clave=f"temporal-{sufijo}")
    )
    assert identificador is not None

    resumen = await servicio.procesar_lote(tamano=10, worker="prueba")
    assert resumen.reintentables == 1

    mensaje = await sesion.get(OutboxMensaje, identificador, populate_existing=True)
    assert mensaje is not None
    assert mensaje.estado == EstadoOutbox.PENDIENTE.value
    assert mensaje.intentos == 1
    # Primer reintento: base x 2^0 = 30 s.
    assert mensaje.proximo_intento_en == reloj_fijo.ahora() + timedelta(seconds=30)
    assert mensaje.ultimo_error == "proveedor caido"
    # No se ha enviado nada de verdad.
    assert canal.enviados == []


async def test_un_fallo_permanente_no_se_reintenta(
    servicio: ServicioOutbox,
    sesion: AsyncSession,
    canal: AdaptadorSandbox,
    paciente_con_whatsapp: Paciente,
    clinica: Clinica,
    sufijo: str,
) -> None:
    """Reintentar un numero que no existe gasta cuota y retrasa lo demas."""
    canal.programar_fallo(ResultadoEnvio.FALLO_PERMANENTE, "numero no registrado")
    identificador = await servicio.encolar(
        _solicitud(paciente_con_whatsapp, clinica, clave=f"permanente-{sufijo}")
    )
    assert identificador is not None

    resumen = await servicio.procesar_lote(tamano=10, worker="prueba")
    assert resumen.fallidos == 1

    mensaje = await sesion.get(OutboxMensaje, identificador, populate_existing=True)
    assert mensaje is not None
    assert mensaje.estado == EstadoOutbox.FALLIDO.value
    # La restriccion `fallido_con_error` exige el motivo, y aqui se comprueba
    # que hay algo accionable y no una cadena vacia.
    assert mensaje.ultimo_error == "numero no registrado"


async def test_al_agotar_los_intentos_queda_fallido_y_visible(
    servicio: ServicioOutbox,
    sesion: AsyncSession,
    canal: AdaptadorSandbox,
    paciente_con_whatsapp: Paciente,
    clinica: Clinica,
    reloj_fijo: RelojFijo,
    sufijo: str,
) -> None:
    """Un FALLIDO no desaparece: alguien creyo avisar y no ocurrio.

    El servicio se construye con `max_intentos=3`, asi que tres fallos
    temporales seguidos lo agotan.
    """
    identificador = await servicio.encolar(
        _solicitud(paciente_con_whatsapp, clinica, clave=f"agotado-{sufijo}")
    )
    assert identificador is not None

    for _ in range(3):
        canal.programar_fallo(ResultadoEnvio.FALLO_TEMPORAL, "sigue caido")
        # El reloj avanza mas que el retroceso para que el mensaje vuelva a
        # estar elegible en el siguiente barrido.
        await servicio.procesar_lote(tamano=10, worker="prueba")
        reloj_fijo.avanzar(hours=2)

    mensaje = await sesion.get(OutboxMensaje, identificador, populate_existing=True)
    assert mensaje is not None
    assert mensaje.estado == EstadoOutbox.FALLIDO.value
    assert mensaje.intentos == 3


async def test_el_retroceso_tiene_tope(
    servicio: ServicioOutbox,
    sesion: AsyncSession,
    canal: AdaptadorSandbox,
    paciente_con_whatsapp: Paciente,
    clinica: Clinica,
    reloj_fijo: RelojFijo,
    sufijo: str,
) -> None:
    """Sin tope, el enesimo intento caeria a horas de distancia.

    Un recordatorio de la cita de manana llegaria pasado manana.
    """
    identificador = await servicio.encolar(
        _solicitud(paciente_con_whatsapp, clinica, clave=f"tope-{sufijo}")
    )
    assert identificador is not None

    # Se fuerza un numero alto de intentos ya gastados.
    await sesion.execute(
        sa.update(OutboxMensaje)
        .where(OutboxMensaje.id == identificador)
        .values(intentos=20, max_intentos=40)
    )
    await sesion.flush()

    canal.programar_fallo(ResultadoEnvio.FALLO_TEMPORAL, "sigue caido")
    await servicio.procesar_lote(tamano=10, worker="prueba")

    mensaje = await sesion.get(OutboxMensaje, identificador, populate_existing=True)
    assert mensaje is not None
    espera = (mensaje.proximo_intento_en - reloj_fijo.ahora()).total_seconds()
    assert espera == RETROCESO_MAXIMO_SEGUNDOS


async def test_un_mensaje_programado_al_futuro_no_se_toma(
    servicio: ServicioOutbox,
    canal: AdaptadorSandbox,
    paciente_con_whatsapp: Paciente,
    clinica: Clinica,
    reloj_fijo: RelojFijo,
    sufijo: str,
) -> None:
    """Un recordatorio de 24 horas no se envia al crearlo."""
    solicitud = _solicitud(paciente_con_whatsapp, clinica, clave=f"futuro-{sufijo}")
    programada = SolicitudEnvio(
        **{
            **{campo: getattr(solicitud, campo) for campo in solicitud.__slots__},
            "programado_para": reloj_fijo.ahora() + timedelta(hours=24),
        }
    )
    await servicio.encolar(programada)

    resumen = await servicio.procesar_lote(tamano=10, worker="prueba")
    assert resumen.tomados == 0
    assert canal.enviados == []

    reloj_fijo.avanzar(hours=25)
    resumen = await servicio.procesar_lote(tamano=10, worker="prueba")
    assert resumen.entregados == 1


async def test_un_destinatario_sin_numero_queda_fallido(
    servicio: ServicioOutbox,
    sesion: AsyncSession,
    clinica: Clinica,
    sufijo: str,
) -> None:
    """No mejora reintentando: alguien tiene que pedirle el numero.

    Queda FALLIDO para que aparezca en la cola de revision.
    """
    sin_numero = Paciente(
        clinica_id=clinica.id,
        tipo_documento="CEDULA",
        numero_documento=f"6{sufijo[:9]}",
        nombre="Sin Numero",
        apellido="De Prueba",
    )
    sesion.add(sin_numero)
    await sesion.flush()
    sesion.add(
        Consentimiento(
            paciente_id=sin_numero.id,
            tipo=TipoConsentimiento.COMUNICACION_WHATSAPP.value,
            otorgado=True,
            version_texto="v1",
            texto_hash="0" * 64,
            canal="PANEL",
        )
    )
    await sesion.flush()

    identificador = await servicio.encolar(
        _solicitud(sin_numero, clinica, clave=f"sin-numero-{sufijo}")
    )
    assert identificador is not None

    resumen = await servicio.procesar_lote(tamano=10, worker="prueba")
    assert resumen.fallidos == 1

    mensaje = await sesion.get(OutboxMensaje, identificador, populate_existing=True)
    assert mensaje is not None
    assert mensaje.estado == EstadoOutbox.FALLIDO.value
    assert "WhatsApp" in (mensaje.ultimo_error or "")


async def test_un_canal_sin_adaptador_vuelve_a_la_cola(
    sesion: AsyncSession,
    reloj_fijo: RelojFijo,
    paciente_con_whatsapp: Paciente,
    clinica: Clinica,
    sufijo: str,
) -> None:
    """La falta de adaptador es un problema de despliegue, no del mensaje.

    Descartarlo perderia avisos que se entregarian en cuanto se corrija.
    """
    sin_canales = ServicioOutbox(sesion, reloj_fijo, RegistroCanales())
    identificador = await sin_canales.encolar(
        _solicitud(paciente_con_whatsapp, clinica, clave=f"sin-canal-{sufijo}")
    )
    assert identificador is not None

    resumen = await sin_canales.procesar_lote(tamano=10, worker="prueba")
    assert resumen.sin_adaptador == 1

    mensaje = await sesion.get(OutboxMensaje, identificador, populate_existing=True)
    assert mensaje is not None
    assert mensaje.estado == EstadoOutbox.PENDIENTE.value


# ---------------------------------------------------------------------------
#  Recuperacion y conciliacion
# ---------------------------------------------------------------------------
async def test_un_mensaje_huerfano_vuelve_a_la_cola(
    servicio: ServicioOutbox,
    sesion: AsyncSession,
    paciente_con_whatsapp: Paciente,
    clinica: Clinica,
    reloj_fijo: RelojFijo,
    sufijo: str,
) -> None:
    """El worker murio entre tomar el mensaje y registrar el desenlace.

    Sin recuperacion se quedaria EN_PROCESO para siempre, que es la forma
    silenciosa de perder un recordatorio.
    """
    identificador = await servicio.encolar(
        _solicitud(paciente_con_whatsapp, clinica, clave=f"huerfano-{sufijo}")
    )
    assert identificador is not None

    tomados = await servicio.tomar_lote(tamano=10, worker="worker-que-muere")
    assert len(tomados) == 1
    assert tomados[0].estado == EstadoOutbox.EN_PROCESO.value

    # Antes de la ventana: no se toca. Un worker puede estar entregandolo.
    reloj_fijo.avanzar(minutes=5)
    assert await servicio.recuperar_huerfanos() == 0

    reloj_fijo.avanzar(minutes=20)
    assert await servicio.recuperar_huerfanos() == 1

    mensaje = await sesion.get(OutboxMensaje, identificador, populate_existing=True)
    assert mensaje is not None
    assert mensaje.estado == EstadoOutbox.PENDIENTE.value
    assert mensaje.tomado_por is None


async def test_un_fallo_reportado_por_el_proveedor_marca_el_mensaje(
    servicio: ServicioOutbox,
    sesion: AsyncSession,
    paciente_con_whatsapp: Paciente,
    clinica: Clinica,
    sufijo: str,
) -> None:
    """El proveedor acepta el mensaje y lo reporta fallido despues.

    Sin esta conciliacion, el sistema creeria que el paciente fue avisado.
    """
    identificador = await servicio.encolar(
        _solicitud(paciente_con_whatsapp, clinica, clave=f"conciliar-{sufijo}")
    )
    assert identificador is not None
    await servicio.procesar_lote(tamano=10, worker="prueba")

    mensaje = await sesion.get(OutboxMensaje, identificador, populate_existing=True)
    assert mensaje is not None
    referencia = mensaje.referencia_externa
    assert referencia is not None

    aplicado = await servicio.registrar_estado_entrega(
        referencia_externa=referencia,
        estado_proveedor="failed",
        detalle="131026 | Message undeliverable",
    )
    assert aplicado

    mensaje = await sesion.get(OutboxMensaje, identificador, populate_existing=True)
    assert mensaje is not None
    assert mensaje.estado == EstadoOutbox.FALLIDO.value


async def test_un_estado_intermedio_no_retrocede_el_mensaje(
    servicio: ServicioOutbox,
    sesion: AsyncSession,
    paciente_con_whatsapp: Paciente,
    clinica: Clinica,
    sufijo: str,
) -> None:
    """Los estados del proveedor llegan desordenados.

    Un `sent` puede llegar despues de un `delivered`; actuar sobre ellos haria
    que el estado del mensaje oscilara.
    """
    identificador = await servicio.encolar(
        _solicitud(paciente_con_whatsapp, clinica, clave=f"desordenado-{sufijo}")
    )
    assert identificador is not None
    await servicio.procesar_lote(tamano=10, worker="prueba")

    mensaje = await sesion.get(OutboxMensaje, identificador, populate_existing=True)
    assert mensaje is not None
    referencia = mensaje.referencia_externa
    assert referencia is not None

    for estado in ("sent", "delivered", "read", "sent"):
        await servicio.registrar_estado_entrega(
            referencia_externa=referencia, estado_proveedor=estado
        )

    mensaje = await sesion.get(OutboxMensaje, identificador, populate_existing=True)
    assert mensaje is not None
    assert mensaje.estado == EstadoOutbox.ENTREGADO.value


async def test_un_estado_de_referencia_desconocida_no_falla(
    servicio: ServicioOutbox,
) -> None:
    """Meta puede informar de un mensaje que este sistema no envio.

    No es un error: se registra y se sigue.
    """
    assert not await servicio.registrar_estado_entrega(
        referencia_externa="wamid.QUE_NO_EXISTE", estado_proveedor="delivered"
    )


async def test_descartar_pendientes_no_toca_los_entregados(
    servicio: ServicioOutbox,
    sesion: AsyncSession,
    paciente_con_whatsapp: Paciente,
    clinica: Clinica,
    sufijo: str,
) -> None:
    """Al cancelar una cita se descartan sus avisos aun no enviados.

    Los ya entregados se conservan: el paciente los recibio, y marcarlos
    descartados haria creer que no.
    """
    origen = uuid.uuid4()
    base = _solicitud(paciente_con_whatsapp, clinica, clave=f"descartar-a-{sufijo}")
    campos = {campo: getattr(base, campo) for campo in base.__slots__}

    entregado = SolicitudEnvio(**{**campos, "entidad_origen_id": origen})
    await servicio.encolar(entregado)
    await servicio.procesar_lote(tamano=10, worker="prueba")

    pendiente = SolicitudEnvio(
        **{
            **campos,
            "clave_deduplicacion": f"descartar-b-{sufijo}",
            "entidad_origen_id": origen,
        }
    )
    identificador_pendiente = await servicio.encolar(pendiente)
    assert identificador_pendiente is not None

    descartados = await servicio.descartar_pendientes(
        entidad_tipo="cita", entidad_id=origen, motivo="La cita se cancelo."
    )
    assert descartados == 1

    estados = (
        (
            await sesion.execute(
                sa.select(OutboxMensaje.estado).where(OutboxMensaje.entidad_origen_id == origen)
            )
        )
        .scalars()
        .all()
    )
    assert sorted(estados) == [EstadoOutbox.DESCARTADO.value, EstadoOutbox.ENTREGADO.value]


# ---------------------------------------------------------------------------
#  Cancelacion de recordatorios programados
# ---------------------------------------------------------------------------
async def test_cancelar_recordatorios_solo_toca_los_programados(
    servicio: ServicioOutbox,
    sesion: AsyncSession,
    paciente_con_whatsapp: Paciente,
    clinica: Clinica,
    reloj_fijo: RelojFijo,
) -> None:
    """Al cancelar una cita se cancelan sus recordatorios futuros (RF-K03).

    Los que ya se encolaron NO se tocan: pueden estar entregandose en este
    instante, y marcarlos cancelados daria por cancelado algo que el paciente
    ya recibio.
    """
    cita_id = uuid.uuid4()
    for estado in ("PROGRAMADO", "PROGRAMADO", "ENCOLADO"):
        sesion.add(
            Recordatorio(
                tipo=TipoMensajeOutbox.CITA_RECORDATORIO_DIA_ANTES.value,
                clinica_id=clinica.id,
                entidad_tipo="cita",
                entidad_id=cita_id,
                destinatario_tipo="PACIENTE",
                destinatario_id=paciente_con_whatsapp.id,
                programado_para=reloj_fijo.ahora() + timedelta(hours=24),
                estado=estado,
            )
        )
    await sesion.flush()

    cancelados = await servicio.cancelar_recordatorios(
        entidad_tipo="cita", entidad_id=cita_id, motivo="La cita se cancelo."
    )
    assert cancelados == 2

    estados = sorted(
        (
            await sesion.execute(
                sa.select(Recordatorio.estado).where(Recordatorio.entidad_id == cita_id)
            )
        )
        .scalars()
        .all()
    )
    assert estados == ["CANCELADO", "CANCELADO", "ENCOLADO"]


async def test_la_cancelacion_registra_su_motivo(
    servicio: ServicioOutbox,
    sesion: AsyncSession,
    paciente_con_whatsapp: Paciente,
    clinica: Clinica,
    reloj_fijo: RelojFijo,
) -> None:
    """La restriccion `cancelacion_con_motivo` lo exige en el motor.

    Un recordatorio cancelado sin motivo deja sin respuesta la pregunta de por
    que el paciente no recibio su aviso.
    """
    receta_id = uuid.uuid4()
    sesion.add(
        Recordatorio(
            tipo=TipoMensajeOutbox.TOMA_RECORDATORIO.value,
            clinica_id=clinica.id,
            entidad_tipo="receta",
            entidad_id=receta_id,
            destinatario_tipo="PACIENTE",
            destinatario_id=paciente_con_whatsapp.id,
            programado_para=reloj_fijo.ahora() + timedelta(hours=8),
            estado="PROGRAMADO",
        )
    )
    await sesion.flush()

    await servicio.cancelar_recordatorios(
        entidad_tipo="receta",
        entidad_id=receta_id,
        motivo="La receta se modifico y exige confirmacion profesional.",
    )

    registro = (
        await sesion.execute(sa.select(Recordatorio).where(Recordatorio.entidad_id == receta_id))
    ).scalar_one()
    assert registro.estado == "CANCELADO"
    assert registro.cancelado_en == reloj_fijo.ahora()
    assert registro.motivo_cancelacion is not None


async def test_cancelar_recordatorios_de_otra_entidad_no_afecta(
    servicio: ServicioOutbox,
) -> None:
    """Sin filas de esa entidad no se cancela nada, y no es un error."""
    assert (
        await servicio.cancelar_recordatorios(
            entidad_tipo="cita", entidad_id=uuid.uuid4(), motivo="nada que cancelar"
        )
        == 0
    )
