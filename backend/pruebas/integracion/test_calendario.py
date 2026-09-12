"""Sincronizacion y reconciliacion del calendario externo.

Los casos que importan de esta integracion no son la creacion del evento: son
los tres que ocurren **porque el sistema no es el unico que escribe en ese
calendario**.

1. El profesional borra el evento desde su telefono. La cita sigue en pie, asi
   que el evento se vuelve a crear (RF-I08).
2. El profesional **mueve** el evento de hora. Eso no se pisa: se marca
   conflicto, porque puede significar que no estara disponible y que hay que
   reprogramar a un paciente.
3. El token caduca. La conexion se marca `TOKEN_VENCIDO` -- distinto de
   `DESCONECTADO` -- y los eventos quedan pendientes, no fallidos.

Ninguno de los tres se puede ejercer esperando a que Google lo produzca. De
ahi los metodos `simular_*` del adaptador sandbox.

Nota sobre nombres: la fixture del catalogo de la conftest se llama `servicio`
(una fila de `servicio`), asi que el servicio de aplicacion de aqui se llama
`servicio_calendario` para no taparla.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita, EstadoCita, OrigenCita
from app.modulos.calendario.adaptadores import (
    AdaptadorSandboxCalendario,
    RegistroCalendarios,
    ResultadoCalendario,
)
from app.modulos.calendario.eventos import TITULO_EVENTO
from app.modulos.calendario.seleccion import PROVEEDOR_GOOGLE
from app.modulos.calendario.servicios import (
    MAXIMO_INTENTOS_EVENTO,
    ServicioCalendario,
)
from app.modulos.organizacion.modelos import Clinica, Consultorio, Sede, Servicio
from app.modulos.pacientes.modelos import Paciente
from app.modulos.profesionales.modelos import (
    CalendarioConexion,
    CalendarioEvento,
    EstadoEventoCalendario,
    EstadoSincronizacion,
    Profesional,
)
from app.nucleo.reloj import RelojFijo
from app.nucleo.seguridad import CifradorDatos

pytestmark = [pytest.mark.integracion, pytest.mark.asyncio]

# Valores sinteticos, solo para estas pruebas (CLAUDE.md, regla 2).
CLAVE_CIFRADO = "clave-sintetica-de-cifrado-para-pruebas"
TOKEN_ACCESO = "acceso-sintetico"
TOKEN_REFRESCO = "refresco-sintetico"


# ---------------------------------------------------------------------------
#  Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def cifrador() -> CifradorDatos:
    return CifradorDatos(CLAVE_CIFRADO)


@pytest.fixture
def proveedor() -> AdaptadorSandboxCalendario:
    return AdaptadorSandboxCalendario()


@pytest.fixture
def proveedores(proveedor: AdaptadorSandboxCalendario) -> RegistroCalendarios:
    registro = RegistroCalendarios()
    registro.registrar(PROVEEDOR_GOOGLE, proveedor)
    return registro


@pytest.fixture
def reloj_fijo(instante: datetime) -> RelojFijo:
    return RelojFijo(instante)


@pytest.fixture
def servicio_calendario(
    sesion: AsyncSession,
    reloj_fijo: RelojFijo,
    cifrador: CifradorDatos,
    proveedores: RegistroCalendarios,
) -> ServicioCalendario:
    return ServicioCalendario(
        sesion,
        reloj_fijo,
        cifrador,
        proveedores,
        url_sistema="https://clinica.example.invalid",
    )


@pytest_asyncio.fixture
async def conexion(
    servicio_calendario: ServicioCalendario,
    profesional: Profesional,
    reloj_fijo: RelojFijo,
) -> CalendarioConexion:
    return await servicio_calendario.conectar(
        profesional_id=profesional.id,
        proveedor=PROVEEDOR_GOOGLE,
        calendar_id="primary",
        token_acceso=TOKEN_ACCESO,
        token_refresco=TOKEN_REFRESCO,
        expira_en=reloj_fijo.ahora() + timedelta(hours=1),
        alcances="https://www.googleapis.com/auth/calendar.events",
    )


@pytest_asyncio.fixture
async def cita(
    sesion: AsyncSession,
    clinica: Clinica,
    sede: Sede,
    consultorio: Consultorio,
    servicio: Servicio,
    profesional: Profesional,
    paciente: Paciente,
    manana: datetime,
) -> Cita:
    registro = Cita(
        clinica_id=clinica.id,
        sede_id=sede.id,
        consultorio_id=consultorio.id,
        profesional_id=profesional.id,
        paciente_id=paciente.id,
        servicio_id=servicio.id,
        inicio=manana,
        duracion_minutos=30,
        estado=EstadoCita.CONFIRMED.value,
        origen=OrigenCita.PANEL.value,
    )
    sesion.add(registro)
    await sesion.flush()
    # `fin` lo rellena un disparador; hay que releerlo.
    await sesion.refresh(registro)
    return registro


# ---------------------------------------------------------------------------
#  Conexion y cifrado de tokens
# ---------------------------------------------------------------------------
async def test_los_tokens_se_guardan_cifrados(
    conexion: CalendarioConexion, sesion: AsyncSession
) -> None:
    """En la base no hay ningun token en claro."""
    fila = (
        await sesion.execute(
            sa.select(
                CalendarioConexion.token_acceso_cifrado,
                CalendarioConexion.token_refresco_cifrado,
            ).where(CalendarioConexion.id == conexion.id)
        )
    ).one()
    assert TOKEN_ACCESO not in (fila[0] or "")
    assert TOKEN_REFRESCO not in (fila[1] or "")
    assert fila[0] and fila[1]


async def test_un_token_copiado_a_otra_conexion_no_descifra(
    conexion: CalendarioConexion,
    sesion: AsyncSession,
    servicio_calendario: ServicioCalendario,
    cifrador: CifradorDatos,
    clinica: Clinica,
    especialidad: object,
    sufijo: str,
) -> None:
    """El contexto del cifrado liga el token a **su** profesional.

    Es lo que convierte un acceso de lectura a la base en algo que no basta
    para usar los tokens de otro: copiar la fila no sirve.
    """
    otro = Profesional(
        clinica_id=clinica.id,
        especialidad_id=especialidad.id,  # type: ignore[attr-defined]
        nombre="Otro",
        apellido="Profesional De Prueba",
        numero_registro_profesional=f"REG-OTRO-{sufijo}",
    )
    sesion.add(otro)
    await sesion.flush()

    robada = CalendarioConexion(
        profesional_id=otro.id,
        proveedor=PROVEEDOR_GOOGLE,
        calendar_id="primary",
        token_acceso_cifrado=conexion.token_acceso_cifrado,
        token_refresco_cifrado=conexion.token_refresco_cifrado,
        estado_sincronizacion=EstadoSincronizacion.CONECTADO.value,
    )
    sesion.add(robada)
    await sesion.flush()

    # El servicio no obtiene credenciales de la fila copiada.
    assert servicio_calendario._credenciales(robada) is None
    # Y de la legitima si.
    assert servicio_calendario._credenciales(conexion) is not None


async def test_conectar_dos_veces_actualiza_la_misma_conexion(
    servicio_calendario: ServicioCalendario,
    profesional: Profesional,
    reloj_fijo: RelojFijo,
    sesion: AsyncSession,
    conexion: CalendarioConexion,
) -> None:
    """Dos conexiones al mismo calendario duplicarian cada evento."""
    de_nuevo = await servicio_calendario.conectar(
        profesional_id=profesional.id,
        proveedor=PROVEEDOR_GOOGLE,
        calendar_id="primary",
        token_acceso="acceso-nuevo",
        token_refresco="refresco-nuevo",
        expira_en=reloj_fijo.ahora() + timedelta(hours=2),
        alcances=None,
    )
    assert de_nuevo.id == conexion.id

    total = await sesion.scalar(
        sa.select(sa.func.count())
        .select_from(CalendarioConexion)
        .where(CalendarioConexion.profesional_id == profesional.id)
    )
    assert total == 1


async def test_desconectar_borra_los_tokens_y_conserva_la_fila(
    servicio_calendario: ServicioCalendario,
    conexion: CalendarioConexion,
    sesion: AsyncSession,
) -> None:
    """Un token que ya no se usa y sigue guardado es superficie de ataque.

    La fila se conserva porque los eventos creados la referencian y hay que
    poder explicar de donde salieron.
    """
    await servicio_calendario.desconectar(
        conexion_id=conexion.id, motivo="El profesional lo pidio."
    )
    fila = await sesion.get(CalendarioConexion, conexion.id, populate_existing=True)
    assert fila is not None
    assert fila.token_acceso_cifrado is None
    assert fila.token_refresco_cifrado is None
    assert fila.estado_sincronizacion == EstadoSincronizacion.DESCONECTADO.value


# ---------------------------------------------------------------------------
#  Reflejo de una cita
# ---------------------------------------------------------------------------
async def test_una_cita_confirmada_se_refleja_en_el_calendario(
    servicio_calendario: ServicioCalendario,
    proveedor: AdaptadorSandboxCalendario,
    conexion: CalendarioConexion,
    cita: Cita,
    sesion: AsyncSession,
) -> None:
    await servicio_calendario.registrar_cita(cita)
    resumen = await servicio_calendario.sincronizar_pendientes()

    assert resumen.creados == 1
    evento = (
        await sesion.execute(sa.select(CalendarioEvento).where(CalendarioEvento.cita_id == cita.id))
    ).scalar_one()
    assert evento.estado == EstadoEventoCalendario.SINCRONIZADO.value
    assert evento.external_event_id is not None
    assert len(proveedor.eventos) == 1


async def test_el_evento_publicado_no_lleva_datos_del_paciente(
    servicio_calendario: ServicioCalendario,
    proveedor: AdaptadorSandboxCalendario,
    conexion: CalendarioConexion,
    cita: Cita,
    paciente: Paciente,
    servicio: Servicio,
) -> None:
    """RF-I09 verificado en el camino real, no solo en la funcion.

    Es la prueba que importa de este archivo: lo que de verdad sale hacia el
    tercero no nombra al paciente ni al servicio.
    """
    await servicio_calendario.registrar_cita(cita)
    await servicio_calendario.sincronizar_pendientes()

    publicado = next(iter(proveedor.eventos.values())).evento
    texto = publicado.texto_completo()
    assert paciente.nombre not in texto
    assert paciente.apellido not in texto
    assert servicio.nombre not in texto
    assert publicado.titulo == TITULO_EVENTO


async def test_registrar_dos_veces_no_duplica_el_evento(
    servicio_calendario: ServicioCalendario,
    conexion: CalendarioConexion,
    cita: Cita,
    sesion: AsyncSession,
) -> None:
    """La restriccion unica `(cita, conexion)` es la garantia real."""
    await servicio_calendario.registrar_cita(cita)
    await servicio_calendario.registrar_cita(cita)

    total = await sesion.scalar(
        sa.select(sa.func.count())
        .select_from(CalendarioEvento)
        .where(CalendarioEvento.cita_id == cita.id)
    )
    assert total == 1


async def test_una_cita_cancelada_se_retira_del_calendario(
    servicio_calendario: ServicioCalendario,
    proveedor: AdaptadorSandboxCalendario,
    conexion: CalendarioConexion,
    cita: Cita,
    sesion: AsyncSession,
) -> None:
    """Dejar el evento haria que el profesional viera ocupado un hueco libre."""
    await servicio_calendario.registrar_cita(cita)
    await servicio_calendario.sincronizar_pendientes()
    identificador = next(iter(proveedor.eventos))

    cita.estado = EstadoCita.CANCELLED.value
    # La restriccion `cancelacion_exige_motivo` lo pide en el motor: una cita
    # cancelada sin motivo deja sin respuesta la pregunta de por que.
    cita.motivo_cancelacion = "El paciente no podra asistir."
    evento = (
        await sesion.execute(sa.select(CalendarioEvento).where(CalendarioEvento.cita_id == cita.id))
    ).scalar_one()
    evento.estado = EstadoEventoCalendario.PENDIENTE.value
    await sesion.flush()

    resumen = await servicio_calendario.sincronizar_pendientes()
    assert resumen.eliminados == 1
    assert proveedor.eventos[identificador].eliminado


async def test_la_deteccion_crea_los_reflejos_que_faltan(
    servicio_calendario: ServicioCalendario,
    conexion: CalendarioConexion,
    cita: Cita,
    sesion: AsyncSession,
) -> None:
    """Cubre las citas anteriores a la conexion.

    Un profesional que conecta su calendario hoy espera ver su agenda de la
    semana que viene, no solo lo que se reserve a partir de ahora.
    """
    detectados = await servicio_calendario.detectar_citas_sin_reflejo()
    assert detectados == 1

    # Idempotente: un segundo barrido no vuelve a crearlos.
    assert await servicio_calendario.detectar_citas_sin_reflejo() == 0


async def test_la_deteccion_ignora_las_citas_pasadas(
    servicio_calendario: ServicioCalendario,
    conexion: CalendarioConexion,
    cita: Cita,
    reloj_fijo: RelojFijo,
) -> None:
    """Reflejar el pasado llena el calendario de historico inutil.

    Y gasta cuota del proveedor en eventos que nadie mirara.
    """
    reloj_fijo.avanzar(days=30)
    assert await servicio_calendario.detectar_citas_sin_reflejo() == 0


# ---------------------------------------------------------------------------
#  El profesional borra el evento a mano
# ---------------------------------------------------------------------------
async def test_un_evento_borrado_externamente_se_vuelve_a_crear(
    servicio_calendario: ServicioCalendario,
    proveedor: AdaptadorSandboxCalendario,
    conexion: CalendarioConexion,
    cita: Cita,
    sesion: AsyncSession,
) -> None:
    """La cita sigue en pie, asi que el reflejo se restablece (RF-I08).

    Borrar el evento en el telefono no cancela la atencion de un paciente.
    """
    await servicio_calendario.registrar_cita(cita)
    await servicio_calendario.sincronizar_pendientes()
    primero = next(iter(proveedor.eventos))

    proveedor.simular_borrado_externo(primero)

    # La reconciliacion lo detecta...
    resumen = await servicio_calendario.reconciliar()
    assert resumen.eliminados == 1
    evento = await sesion.get(
        CalendarioEvento,
        (
            await sesion.execute(
                sa.select(CalendarioEvento.id).where(CalendarioEvento.cita_id == cita.id)
            )
        ).scalar_one(),
        populate_existing=True,
    )
    assert evento is not None
    assert evento.estado == EstadoEventoCalendario.ELIMINADO_EXTERNAMENTE.value

    # ...y el siguiente barrido lo recrea.
    resumen = await servicio_calendario.sincronizar_pendientes()
    assert resumen.recreados == 1
    # `sincronizar_pendientes` no hace `commit` -- el limite transaccional lo
    # decide quien orquesta --, asi que hay que volcar antes de releer.
    await sesion.flush()
    await sesion.refresh(evento)
    assert evento.estado == EstadoEventoCalendario.SINCRONIZADO.value
    assert evento.external_event_id != primero


async def test_la_cita_sobrevive_al_borrado_del_evento(
    servicio_calendario: ServicioCalendario,
    proveedor: AdaptadorSandboxCalendario,
    conexion: CalendarioConexion,
    cita: Cita,
    sesion: AsyncSession,
) -> None:
    """RF-I08 en su forma mas literal: la cita interna no se toca."""
    await servicio_calendario.registrar_cita(cita)
    await servicio_calendario.sincronizar_pendientes()
    proveedor.simular_borrado_externo(next(iter(proveedor.eventos)))
    await servicio_calendario.reconciliar()

    viva = await sesion.get(Cita, cita.id, populate_existing=True)
    assert viva is not None
    assert viva.estado == EstadoCita.CONFIRMED.value


# ---------------------------------------------------------------------------
#  El profesional mueve el evento a mano
# ---------------------------------------------------------------------------
async def test_un_cambio_externo_produce_conflicto_y_no_se_sobrescribe(
    servicio_calendario: ServicioCalendario,
    proveedor: AdaptadorSandboxCalendario,
    conexion: CalendarioConexion,
    cita: Cita,
    sesion: AsyncSession,
) -> None:
    """Pisarlo destruiria una decision del profesional.

    Puede significar que no estara disponible, y resolverlo puede implicar
    reprogramar a un paciente: eso no lo decide una maquina.
    """
    await servicio_calendario.registrar_cita(cita)
    await servicio_calendario.sincronizar_pendientes()
    identificador = next(iter(proveedor.eventos))

    proveedor.simular_cambio_externo(identificador)

    resumen = await servicio_calendario.reconciliar()
    assert resumen.conflictos == 1

    evento = (
        await sesion.execute(sa.select(CalendarioEvento).where(CalendarioEvento.cita_id == cita.id))
    ).scalar_one()
    assert evento.estado == EstadoEventoCalendario.CONFLICTO.value
    assert evento.ultimo_error is not None
    # El evento del proveedor sigue como lo dejo el profesional.
    assert proveedor.eventos[identificador].alterado_fuera


async def test_un_conflicto_no_se_reintenta_en_el_barrido(
    servicio_calendario: ServicioCalendario,
    proveedor: AdaptadorSandboxCalendario,
    conexion: CalendarioConexion,
    cita: Cita,
) -> None:
    """Espera a una persona. Reintentarlo seria sobrescribirlo por la puerta de atras."""
    await servicio_calendario.registrar_cita(cita)
    await servicio_calendario.sincronizar_pendientes()
    proveedor.simular_cambio_externo(next(iter(proveedor.eventos)))
    await servicio_calendario.reconciliar()

    operaciones_antes = len(proveedor.operaciones)
    resumen = await servicio_calendario.sincronizar_pendientes()

    assert resumen.creados == 0
    assert resumen.actualizados == 0
    # No se llamo al proveedor: el estado CONFLICTO no entra en el barrido.
    assert len(proveedor.operaciones) == operaciones_antes


async def test_la_actualizacion_respeta_el_etag(
    servicio_calendario: ServicioCalendario,
    proveedor: AdaptadorSandboxCalendario,
    conexion: CalendarioConexion,
    cita: Cita,
    sesion: AsyncSession,
) -> None:
    """El control optimista es lo que convierte un cambio externo en conflicto.

    Sin `etag`, la actualizacion pisaria el evento sin enterarse.
    """
    await servicio_calendario.registrar_cita(cita)
    await servicio_calendario.sincronizar_pendientes()
    identificador = next(iter(proveedor.eventos))
    proveedor.simular_cambio_externo(identificador, etag="etag-de-otro")

    evento = (
        await sesion.execute(sa.select(CalendarioEvento).where(CalendarioEvento.cita_id == cita.id))
    ).scalar_one()
    evento.estado = EstadoEventoCalendario.PENDIENTE.value
    await sesion.flush()

    resumen = await servicio_calendario.sincronizar_pendientes()
    assert resumen.conflictos == 1


# ---------------------------------------------------------------------------
#  Token vencido
# ---------------------------------------------------------------------------
async def test_un_token_vencido_marca_la_conexion_y_no_pierde_el_evento(
    servicio_calendario: ServicioCalendario,
    proveedor: AdaptadorSandboxCalendario,
    conexion: CalendarioConexion,
    cita: Cita,
    sesion: AsyncSession,
) -> None:
    """`TOKEN_VENCIDO` es distinto de `DESCONECTADO`, y la distincion importa.

    El primero exige que alguien vuelva a autorizar; el segundo no necesita
    accion. Confundirlos deja al profesional desincronizado sin enterarse.
    """
    await servicio_calendario.registrar_cita(cita)
    proveedor.simular_token_vencido()

    resumen = await servicio_calendario.sincronizar_pendientes()
    assert resumen.token_vencido == 1

    fila = await sesion.get(CalendarioConexion, conexion.id, populate_existing=True)
    assert fila is not None
    assert fila.estado_sincronizacion == EstadoSincronizacion.TOKEN_VENCIDO.value
    # El token de refresco se conserva: es con lo que se recupera la conexion.
    assert fila.token_refresco_cifrado is not None

    evento = (
        await sesion.execute(sa.select(CalendarioEvento).where(CalendarioEvento.cita_id == cita.id))
    ).scalar_one()
    assert evento.estado == EstadoEventoCalendario.PENDIENTE.value


async def test_tras_reconectar_el_evento_pendiente_se_publica(
    servicio_calendario: ServicioCalendario,
    proveedor: AdaptadorSandboxCalendario,
    conexion: CalendarioConexion,
    cita: Cita,
    profesional: Profesional,
    reloj_fijo: RelojFijo,
) -> None:
    """Nada se pierde por un token caducado: se publica al volver."""
    await servicio_calendario.registrar_cita(cita)
    proveedor.simular_token_vencido()
    await servicio_calendario.sincronizar_pendientes()

    proveedor.token_vencido = False
    await servicio_calendario.conectar(
        profesional_id=profesional.id,
        proveedor=PROVEEDOR_GOOGLE,
        calendar_id="primary",
        token_acceso="acceso-renovado",
        token_refresco="refresco-renovado",
        expira_en=reloj_fijo.ahora() + timedelta(hours=1),
        alcances=None,
    )

    resumen = await servicio_calendario.sincronizar_pendientes()
    assert resumen.creados == 1


# ---------------------------------------------------------------------------
#  Fallos del proveedor
# ---------------------------------------------------------------------------
async def test_un_fallo_temporal_se_reintenta(
    servicio_calendario: ServicioCalendario,
    proveedor: AdaptadorSandboxCalendario,
    conexion: CalendarioConexion,
    cita: Cita,
    sesion: AsyncSession,
) -> None:
    await servicio_calendario.registrar_cita(cita)
    proveedor.programar_fallo(ResultadoCalendario.FALLO_TEMPORAL)

    resumen = await servicio_calendario.sincronizar_pendientes()
    assert resumen.reintentables == 1

    evento = (
        await sesion.execute(sa.select(CalendarioEvento).where(CalendarioEvento.cita_id == cita.id))
    ).scalar_one()
    assert evento.estado == EstadoEventoCalendario.PENDIENTE.value
    assert evento.intentos == 1

    resumen = await servicio_calendario.sincronizar_pendientes()
    assert resumen.creados == 1


async def test_al_agotar_los_intentos_queda_en_error_visible(
    servicio_calendario: ServicioCalendario,
    proveedor: AdaptadorSandboxCalendario,
    conexion: CalendarioConexion,
    cita: Cita,
    sesion: AsyncSession,
) -> None:
    """Un evento en ERROR significa que una agenda externa esta desincronizada.

    No desaparece: alguien tiene que mirarla.
    """
    await servicio_calendario.registrar_cita(cita)
    for _ in range(MAXIMO_INTENTOS_EVENTO):
        proveedor.programar_fallo(ResultadoCalendario.FALLO_TEMPORAL)
        await servicio_calendario.sincronizar_pendientes()

    evento = (
        await sesion.execute(sa.select(CalendarioEvento).where(CalendarioEvento.cita_id == cita.id))
    ).scalar_one()
    assert evento.estado == EstadoEventoCalendario.ERROR.value
    assert evento.intentos == MAXIMO_INTENTOS_EVENTO
    assert evento.ultimo_error is not None

    fila = await sesion.get(CalendarioConexion, conexion.id, populate_existing=True)
    assert fila is not None
    assert fila.estado_sincronizacion == EstadoSincronizacion.ERROR.value


async def test_un_fallo_permanente_no_se_reintenta(
    servicio_calendario: ServicioCalendario,
    proveedor: AdaptadorSandboxCalendario,
    conexion: CalendarioConexion,
    cita: Cita,
    sesion: AsyncSession,
) -> None:
    await servicio_calendario.registrar_cita(cita)
    proveedor.programar_fallo(ResultadoCalendario.FALLO_PERMANENTE)

    resumen = await servicio_calendario.sincronizar_pendientes()
    assert resumen.errores == 1

    evento = (
        await sesion.execute(sa.select(CalendarioEvento).where(CalendarioEvento.cita_id == cita.id))
    ).scalar_one()
    assert evento.estado == EstadoEventoCalendario.ERROR.value
    assert evento.intentos == 1


async def test_sin_conexion_activa_no_se_registra_reflejo(
    servicio_calendario: ServicioCalendario,
    cita: Cita,
) -> None:
    """Un profesional sin calendario conectado no genera eventos."""
    assert await servicio_calendario.registrar_cita(cita) == []


async def test_una_conexion_desconectada_no_recibe_reflejos(
    servicio_calendario: ServicioCalendario,
    conexion: CalendarioConexion,
    cita: Cita,
) -> None:
    await servicio_calendario.desconectar(
        conexion_id=conexion.id, motivo="El profesional lo pidio."
    )
    assert await servicio_calendario.registrar_cita(cita) == []
