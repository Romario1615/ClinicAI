"""El aviso de un turno liberado, y a quien puede penalizar su vencimiento.

El fallo que estas pruebas impiden que vuelva
--------------------------------------------
La oferta se creaba y **nadie le decia nada al paciente**: la plantilla
`OFERTA_TURNO` existia y ningun codigo la encolaba. Quince minutos despues la
oferta vencia sola, sumaba una a `ofertas_vencidas`, y a la tercera la entrada
pasaba a `EXPIRADA`.

El resultado era que un paciente que no hizo nada mal desaparecia de la lista
de espera tras tres turnos de los que nunca se entero. Nada fallaba, nadie veia
un error, y el comentario del codigo decia «a quien nunca responde se le deja
de ofrecer» -- como si la culpa fuera suya.

La tarea periodica del worker lo convirtio de latente en seguro: antes solo
vencian las ofertas si alguien abria el panel; ahora vencen cada minuto.

Las dos mitades de la solucion, una prueba por cada una:

1. **Se encola el aviso** al crear la oferta, con la plantilla aprobada y
   pasando por el consentimiento.
2. **Una oferta que no se pudo comunicar no cuenta en contra** al vencer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita, EstadoCita
from app.modulos.lista_espera.modelos import EstadoEspera, EstadoOferta
from app.modulos.lista_espera.panel import listar_espera
from app.modulos.lista_espera.servicios import (
    MAXIMO_OFERTAS_VENCIDAS,
    ServicioListaEspera,
)
from app.modulos.outbox.modelos import OutboxMensaje, TipoMensajeOutbox
from app.modulos.pacientes.modelos import Consentimiento, TipoConsentimiento
from app.modulos.profesionales.modelos import ProfesionalSede
from app.nucleo.autorizacion import Ambito, Principal, TipoActor, principal_sistema
from app.nucleo.reloj import RelojFijo

pytestmark = [pytest.mark.integracion, pytest.mark.asyncio]

AHORA = datetime(2026, 4, 15, 14, 0, tzinfo=UTC)
MINUTOS_OFERTA = 30


@pytest.fixture
def reloj_fijo() -> RelojFijo:
    return RelojFijo(AHORA)


@pytest.fixture
def servicio_espera(sesion: AsyncSession, reloj_fijo: RelojFijo) -> ServicioListaEspera:
    return ServicioListaEspera(sesion, reloj_fijo, minutos_vigencia_oferta=MINUTOS_OFERTA)


@pytest.fixture
def principal(clinica, sede) -> Principal:  # type: ignore[no-untyped-def]
    return Principal(
        actor_tipo=TipoActor.USUARIO,
        actor_id=uuid.uuid4(),
        clinica_id=clinica.id,
        permisos=frozenset({"lista_espera.gestionar", "agenda.leer"}),
        ambito=Ambito(
            clinica_id=clinica.id,
            sedes=frozenset({sede.id}),
            todas_las_especialidades=True,
            todos_los_profesionales=True,
            todos_los_pacientes=True,
        ),
    )


@pytest_asyncio.fixture
async def turno_liberado(
    sesion: AsyncSession,
    clinica,  # type: ignore[no-untyped-def]
    sede,  # type: ignore[no-untyped-def]
    paciente,  # type: ignore[no-untyped-def]
    profesional,  # type: ignore[no-untyped-def]
    servicio,  # type: ignore[no-untyped-def]
) -> Cita:
    sesion.add(ProfesionalSede(profesional_id=profesional.id, sede_id=sede.id))
    cita = Cita(
        clinica_id=clinica.id,
        sede_id=sede.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        servicio_id=servicio.id,
        inicio=AHORA + timedelta(days=2),
        duracion_minutos=30,
        minutos_preparacion=15,
        estado=EstadoCita.CANCELLED.value,
        motivo_cancelacion="Liberada para la prueba",
        cancelada_en=AHORA,
    )
    sesion.add(cita)
    await sesion.flush()
    return cita


@pytest.fixture
def servicio_catalogo(servicio_espera):  # type: ignore[no-untyped-def]
    """Alias: `servicio_espera` es el del catalogo y aqui el nombre ya esta tomado."""
    return servicio_espera


async def _consentir(sesion: AsyncSession, paciente_id: uuid.UUID) -> None:
    sesion.add(
        Consentimiento(
            paciente_id=paciente_id,
            tipo=TipoConsentimiento.COMUNICACION_WHATSAPP.value,
            otorgado=True,
            version_texto="v1",
            texto_hash="0" * 64,
            canal="PANEL",
        )
    )
    await sesion.flush()


async def _anotar(
    servicio_espera: ServicioListaEspera,
    principal: Principal,
    paciente_id: uuid.UUID,
    sede_id: uuid.UUID,
    especialidad_id: uuid.UUID,
):  # type: ignore[no-untyped-def]
    return await servicio_espera.anotar(
        principal=principal,
        paciente_id=paciente_id,
        sede_id=sede_id,
        especialidad_id=especialidad_id,
    )


async def _mensajes_de_oferta(sesion: AsyncSession) -> list[OutboxMensaje]:
    return list(
        (
            await sesion.execute(
                sa.select(OutboxMensaje).where(
                    OutboxMensaje.tipo == TipoMensajeOutbox.OFERTA_TURNO.value
                )
            )
        ).scalars()
    )


# ===========================================================================
#  El aviso
# ===========================================================================
class TestAviso:
    async def test_ofrecer_un_turno_encola_el_aviso(
        self,
        sesion: AsyncSession,
        servicio_espera: ServicioListaEspera,
        principal: Principal,
        turno_liberado: Cita,
        segundo_paciente,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
    ) -> None:
        """Sin esto, la oferta es un registro que nadie conoce."""
        await _consentir(sesion, segundo_paciente.id)
        await _anotar(servicio_espera, principal, segundo_paciente.id, sede.id, especialidad.id)
        antes = len(await _mensajes_de_oferta(sesion))

        resultado = await servicio_espera.ofrecer_turno(turno_liberado, principal=principal)
        await sesion.flush()

        assert resultado.oferta is not None
        assert resultado.oferta.aviso_enviado is True
        assert len(await _mensajes_de_oferta(sesion)) == antes + 1

    async def test_el_aviso_no_contiene_ningun_dato_clinico(
        self,
        sesion: AsyncSession,
        servicio_espera: ServicioListaEspera,
        principal: Principal,
        turno_liberado: Cita,
        segundo_paciente,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
    ) -> None:
        """Regla 10: se lee en una pantalla de bloqueo.

        Lleva fecha, hora, sede y profesional. **No** el servicio_espera: el nombre de
        un servicio_espera revela la especialidad, y la especialidad revela la
        condicion de quien lo recibe.
        """
        await _consentir(sesion, segundo_paciente.id)
        await _anotar(servicio_espera, principal, segundo_paciente.id, sede.id, especialidad.id)

        await servicio_espera.ofrecer_turno(turno_liberado, principal=principal)
        await sesion.flush()

        mensajes = await _mensajes_de_oferta(sesion)
        assert mensajes
        texto = str(mensajes[-1].carga_util).lower()
        for prohibida in ("diagnostic", "medicament", "dosis", "receta", "motivo"):
            assert prohibida not in texto

    async def test_sin_consentimiento_la_oferta_se_crea_pero_sin_aviso(
        self,
        sesion: AsyncSession,
        servicio_espera: ServicioListaEspera,
        principal: Principal,
        turno_liberado: Cita,
        segundo_paciente,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
    ) -> None:
        """Bloquear la oferta dejaria a ese paciente fuera para siempre.

        Recepcion todavia puede llamarle por telefono. Lo que no puede pasar es
        que el vencimiento cuente en su contra.
        """
        await _anotar(servicio_espera, principal, segundo_paciente.id, sede.id, especialidad.id)
        antes = len(await _mensajes_de_oferta(sesion))

        resultado = await servicio_espera.ofrecer_turno(turno_liberado, principal=principal)
        await sesion.flush()

        assert resultado.oferta is not None, "La oferta se crea igualmente."
        assert resultado.oferta.aviso_enviado is False
        assert len(await _mensajes_de_oferta(sesion)) == antes, "No sale ningun mensaje."


# ===========================================================================
#  A quien penaliza el vencimiento
# ===========================================================================
class TestPenalizacion:
    async def test_una_oferta_avisada_que_vence_si_cuenta(
        self,
        sesion: AsyncSession,
        servicio_espera: ServicioListaEspera,
        principal: Principal,
        turno_liberado: Cita,
        segundo_paciente,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
        reloj_fijo: RelojFijo,
    ) -> None:
        """Quien recibio el aviso y no respondio si retiene el turno en vano."""
        await _consentir(sesion, segundo_paciente.id)
        entrada = await _anotar(
            servicio_espera, principal, segundo_paciente.id, sede.id, especialidad.id
        )
        await servicio_espera.ofrecer_turno(turno_liberado, principal=principal)
        await sesion.flush()

        reloj_fijo.avanzar(minutes=MINUTOS_OFERTA + 1)
        await servicio_espera.expirar_ofertas_vencidas(principal=principal_sistema())
        await sesion.refresh(entrada)

        assert entrada.ofertas_vencidas == 1

    async def test_una_oferta_no_avisada_que_vence_no_cuenta(
        self,
        sesion: AsyncSession,
        servicio_espera: ServicioListaEspera,
        principal: Principal,
        turno_liberado: Cita,
        segundo_paciente,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
        reloj_fijo: RelojFijo,
    ) -> None:
        """**La prueba que impide que el fallo vuelva.**

        Nadie puede responder a un mensaje que no recibio. Si esto contara,
        tres turnos liberados bastarian para sacar de la lista de espera a un
        paciente que nunca supo de ninguno.
        """
        entrada = await _anotar(
            servicio_espera, principal, segundo_paciente.id, sede.id, especialidad.id
        )
        oferta = (await servicio_espera.ofrecer_turno(turno_liberado, principal=principal)).oferta
        await sesion.flush()
        assert oferta is not None
        assert oferta.aviso_enviado is False

        reloj_fijo.avanzar(minutes=MINUTOS_OFERTA + 1)
        await servicio_espera.expirar_ofertas_vencidas(principal=principal_sistema())
        await sesion.refresh(entrada)
        await sesion.refresh(oferta)

        assert oferta.estado == EstadoOferta.EXPIRADA.value, "El turno vuelve a la cola."
        assert entrada.ofertas_vencidas == 0, "Pero no cuenta en contra del paciente."
        assert entrada.estado == EstadoEspera.ACTIVA.value, "Y sigue en la lista."

    async def test_ni_siquiera_tras_muchas_ofertas_sin_avisar(
        self,
        sesion: AsyncSession,
        servicio_espera: ServicioListaEspera,
        principal: Principal,
        turno_liberado: Cita,
        segundo_paciente,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
        reloj_fijo: RelojFijo,
    ) -> None:
        """El caso exacto que sacaba al paciente de la lista."""
        entrada = await _anotar(
            servicio_espera, principal, segundo_paciente.id, sede.id, especialidad.id
        )

        for _ in range(MAXIMO_OFERTAS_VENCIDAS + 1):
            await servicio_espera.ofrecer_turno(turno_liberado, principal=principal)
            await sesion.flush()
            reloj_fijo.avanzar(minutes=MINUTOS_OFERTA + 1)
            await servicio_espera.expirar_ofertas_vencidas(principal=principal_sistema())

        await sesion.refresh(entrada)
        assert entrada.ofertas_vencidas == 0
        assert entrada.estado == EstadoEspera.ACTIVA.value


# ===========================================================================
#  La cola de llamadas pendientes
# ===========================================================================
class TestColaSinAvisar:
    """El filtro que convierte una oferta invisible en trabajo accionable.

    Sin el, una oferta que no se pudo comunicar retiene el turno hasta que
    vence y **nadie sabe que hay que llamar** (E-27).
    """

    async def test_una_oferta_sin_avisar_aparece_en_la_cola(
        self,
        sesion: AsyncSession,
        servicio_espera: ServicioListaEspera,
        principal: Principal,
        turno_liberado: Cita,
        segundo_paciente,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
    ) -> None:
        entrada = await _anotar(
            servicio_espera, principal, segundo_paciente.id, sede.id, especialidad.id
        )
        await servicio_espera.ofrecer_turno(turno_liberado, principal=principal)
        await sesion.flush()

        pagina = await listar_espera(sesion, principal, 50, 0, solo_sin_avisar=True)

        identificadores = [e.id for e in pagina.elementos]
        assert entrada.id in identificadores
        fila = next(e for e in pagina.elementos if e.id == entrada.id)
        assert fila.oferta_avisada is False
        assert fila.oferta_inicio is not None, "Hace falta la hora para poder llamar."

    async def test_una_oferta_avisada_no_aparece(
        self,
        sesion: AsyncSession,
        servicio_espera: ServicioListaEspera,
        principal: Principal,
        turno_liberado: Cita,
        segundo_paciente,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
    ) -> None:
        """A quien ya recibio el mensaje no hay que llamarle."""
        await _consentir(sesion, segundo_paciente.id)
        entrada = await _anotar(
            servicio_espera, principal, segundo_paciente.id, sede.id, especialidad.id
        )
        await servicio_espera.ofrecer_turno(turno_liberado, principal=principal)
        await sesion.flush()

        pagina = await listar_espera(sesion, principal, 50, 0, solo_sin_avisar=True)

        assert entrada.id not in [e.id for e in pagina.elementos]

    async def test_el_listado_completo_marca_cuales_no_se_avisaron(
        self,
        sesion: AsyncSession,
        servicio_espera: ServicioListaEspera,
        principal: Principal,
        turno_liberado: Cita,
        segundo_paciente,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
    ) -> None:
        """El filtro es una comodidad; la marca tiene que estar siempre."""
        entrada = await _anotar(
            servicio_espera, principal, segundo_paciente.id, sede.id, especialidad.id
        )
        await servicio_espera.ofrecer_turno(turno_liberado, principal=principal)
        await sesion.flush()

        pagina = await listar_espera(sesion, principal, 50, 0)

        fila = next(e for e in pagina.elementos if e.id == entrada.id)
        assert fila.oferta_avisada is False

    async def test_una_entrada_sin_oferta_no_dice_nada_del_aviso(
        self,
        sesion: AsyncSession,
        servicio_espera: ServicioListaEspera,
        principal: Principal,
        segundo_paciente,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
    ) -> None:
        """`None` y no `False`: no hay oferta, asi que no hay nada que avisar.

        Devolver `False` la pondria en la cola de llamadas pendientes sin que
        haya ningun turno que ofrecer.
        """
        entrada = await _anotar(
            servicio_espera, principal, segundo_paciente.id, sede.id, especialidad.id
        )
        await sesion.flush()

        pagina = await listar_espera(sesion, principal, 50, 0)

        fila = next(e for e in pagina.elementos if e.id == entrada.id)
        assert fila.oferta_avisada is None
