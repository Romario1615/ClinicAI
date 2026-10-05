"""El worker vence ofertas y continua la cola con PostgreSQL real.

Las sesiones usan la transaccion aislada de las fixtures compartidas. El
outbox solo se encola: ninguna prueba ejecuta un adaptador de envio.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita, EstadoCita
from app.modulos.auditoria.modelos import Auditoria
from app.modulos.lista_espera.modelos import (
    EntradaListaEspera,
    EstadoEspera,
    EstadoOferta,
    OfertaTurno,
    PrioridadEspera,
)
from app.modulos.lista_espera.servicios import ServicioListaEspera
from app.modulos.organizacion.modelos import Clinica, Especialidad, Sede, Servicio
from app.modulos.outbox.modelos import EstadoOutbox, OutboxMensaje, TipoMensajeOutbox
from app.modulos.pacientes.modelos import Consentimiento, Paciente, TipoConsentimiento
from app.modulos.profesionales.modelos import Profesional
from app.nucleo.auditoria import AccionAuditada
from app.nucleo.autorizacion import TipoActor, principal_sistema
from app.nucleo.reloj import RelojFijo
from app.tareas.lista_espera import expirar_ofertas

pytestmark = [pytest.mark.integracion, pytest.mark.asyncio]


class _GestorDeUnaSesion:
    """Conserva el commit del worker dentro del aislamiento de la prueba."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def sesion(self) -> AsyncIterator[AsyncSession]:
        yield self._sesion


@dataclass
class ColaDePrueba:
    turno: Cita
    primera: EntradaListaEspera
    siguiente: EntradaListaEspera
    oferta: OfertaTurno


@pytest_asyncio.fixture
async def cola(
    sesion: AsyncSession,
    reloj: RelojFijo,
    clinica: Clinica,
    sede: Sede,
    especialidad: Especialidad,
    servicio: Servicio,
    profesional: Profesional,
    paciente: Paciente,
    segundo_paciente: Paciente,
) -> ColaDePrueba:
    turno = Cita(
        clinica_id=clinica.id,
        sede_id=sede.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        servicio_id=servicio.id,
        inicio=reloj.ahora() + timedelta(days=2),
        duracion_minutos=30,
        minutos_preparacion=10,
        estado=EstadoCita.CANCELLED.value,
        cancelada_en=reloj.ahora(),
        motivo_cancelacion="Turno sintetico liberado para probar el worker",
    )
    sesion.add(turno)
    for destinatario in (paciente, segundo_paciente):
        sesion.add(
            Consentimiento(
                paciente_id=destinatario.id,
                tipo=TipoConsentimiento.COMUNICACION_WHATSAPP.value,
                otorgado=True,
                version_texto="v1-prueba",
                texto_hash="0" * 64,
                canal="PANEL",
            )
        )
    await sesion.flush()

    servicio_espera = ServicioListaEspera(sesion, reloj)
    principal = principal_sistema(clinica.id)
    primera = await servicio_espera.anotar(
        principal=principal,
        paciente_id=paciente.id,
        sede_id=sede.id,
        especialidad_id=especialidad.id,
        prioridad=PrioridadEspera.ALTA.value,
    )
    siguiente = await servicio_espera.anotar(
        principal=principal,
        paciente_id=segundo_paciente.id,
        sede_id=sede.id,
        especialidad_id=especialidad.id,
    )
    resultado = await servicio_espera.ofrecer_turno(turno, principal=principal)
    assert resultado.oferta is not None
    assert resultado.oferta.lista_espera_id == primera.id
    assert resultado.oferta.aviso_enviado is True
    return ColaDePrueba(turno, primera, siguiente, resultado.oferta)


async def _ejecutar(sesion: AsyncSession, reloj: RelojFijo) -> int:
    return await expirar_ofertas({"gestor_bd": _GestorDeUnaSesion(sesion), "reloj": reloj})


@pytest.mark.parametrize("segundos, vencidas", [(1799, 0), (1800, 1), (1801, 1)])
async def test_respeta_el_limite_exacto_de_vencimiento(
    sesion: AsyncSession, reloj: RelojFijo, cola: ColaDePrueba, segundos: int, vencidas: int
) -> None:
    reloj.avanzar(seconds=segundos)

    assert await _ejecutar(sesion, reloj) == vencidas

    await sesion.refresh(cola.oferta)
    await sesion.refresh(cola.primera)
    assert cola.oferta.estado == (
        EstadoOferta.EXPIRADA.value if vencidas else EstadoOferta.OFRECIDA.value
    )
    assert cola.primera.estado == (
        EstadoEspera.ACTIVA.value if vencidas else EstadoEspera.OFERTADA.value
    )
    assert cola.primera.ofertas_vencidas == vencidas


async def test_reofrece_a_otro_paciente_audita_y_no_duplica_al_reintentar(
    sesion: AsyncSession, reloj: RelojFijo, cola: ColaDePrueba
) -> None:
    reloj.avanzar(minutes=31)

    assert await _ejecutar(sesion, reloj) == 1
    assert await _ejecutar(sesion, reloj) == 0

    ofertas = list(
        (
            await sesion.scalars(
                select(OfertaTurno).where(OfertaTurno.cita_liberada_id == cola.turno.id)
            )
        ).all()
    )
    assert len(ofertas) == 2
    nueva = next(oferta for oferta in ofertas if oferta.id != cola.oferta.id)
    assert nueva.estado == EstadoOferta.OFRECIDA.value
    assert nueva.lista_espera_id == cola.siguiente.id
    assert nueva.expira_en == reloj.ahora() + timedelta(minutes=30)
    assert nueva.aviso_enviado is True
    await sesion.refresh(cola.primera)
    await sesion.refresh(cola.siguiente)
    assert cola.primera.ofertas_vencidas == 1
    assert cola.primera.estado == EstadoEspera.ACTIVA.value
    assert cola.siguiente.estado == EstadoEspera.OFERTADA.value
    assert cola.siguiente.ofertas_realizadas == 1

    auditoria = list(
        (
            await sesion.scalars(
                select(Auditoria).where(Auditoria.entidad_id.in_([cola.oferta.id, nueva.id]))
            )
        ).all()
    )
    assert {(entrada.accion, entrada.entidad_id) for entrada in auditoria} == {
        (AccionAuditada.OFERTA_EXPIRADA.value, cola.oferta.id),
        (AccionAuditada.OFERTA_ENVIADA.value, nueva.id),
    }
    assert len(auditoria) == 2
    for entrada in auditoria:
        assert entrada.actor_tipo == TipoActor.SISTEMA.value
        assert entrada.actor_id is None
        assert entrada.origen == "WORKER"
        assert entrada.clinica_id == cola.turno.clinica_id
        assert entrada.ocurrido_en == reloj.ahora()

    avisos = list(
        (
            await sesion.scalars(
                select(OutboxMensaje).where(
                    OutboxMensaje.entidad_origen_id.in_([cola.primera.id, cola.siguiente.id]),
                    OutboxMensaje.tipo == TipoMensajeOutbox.OFERTA_TURNO.value,
                )
            )
        ).all()
    )
    assert len(avisos) == 2
    assert {aviso.destino_id for aviso in avisos} == {
        cola.primera.paciente_id,
        cola.siguiente.paciente_id,
    }
    assert all(aviso.estado == EstadoOutbox.PENDIENTE.value for aviso in avisos)


async def test_no_reofrece_si_otra_reserva_ocupo_el_turno(
    sesion: AsyncSession, reloj: RelojFijo, cola: ColaDePrueba
) -> None:
    sesion.add(
        Cita(
            clinica_id=cola.turno.clinica_id,
            sede_id=cola.turno.sede_id,
            paciente_id=cola.siguiente.paciente_id,
            profesional_id=cola.turno.profesional_id,
            servicio_id=cola.turno.servicio_id,
            inicio=cola.turno.inicio,
            duracion_minutos=cola.turno.duracion_minutos,
            minutos_preparacion=cola.turno.minutos_preparacion,
            estado=EstadoCita.CONFIRMED.value,
            confirmada_en=reloj.ahora(),
        )
    )
    await sesion.flush()
    reloj.avanzar(minutes=31)

    assert await _ejecutar(sesion, reloj) == 1

    await _comprobar_sin_reoferta(sesion, cola)


async def test_sin_otro_candidato_vence_sin_repetir_la_oferta_al_mismo_paciente(
    sesion: AsyncSession, reloj: RelojFijo, cola: ColaDePrueba
) -> None:
    await ServicioListaEspera(sesion, reloj).cancelar(
        cola.siguiente.id, principal=principal_sistema(cola.turno.clinica_id)
    )
    reloj.avanzar(minutes=31)

    assert await _ejecutar(sesion, reloj) == 1

    await _comprobar_sin_reoferta(sesion, cola)


async def test_un_worker_retrasado_no_ofrece_un_turno_que_ya_paso(
    sesion: AsyncSession, reloj: RelojFijo, cola: ColaDePrueba
) -> None:
    reloj.avanzar(days=2, minutes=1)

    assert await _ejecutar(sesion, reloj) == 1

    await _comprobar_sin_reoferta(sesion, cola)


async def _comprobar_sin_reoferta(sesion: AsyncSession, cola: ColaDePrueba) -> None:
    ofertas = list(
        (
            await sesion.scalars(
                select(OfertaTurno).where(OfertaTurno.cita_liberada_id == cola.turno.id)
            )
        ).all()
    )
    assert len(ofertas) == 1
    assert ofertas[0].estado == EstadoOferta.EXPIRADA.value
    await sesion.refresh(cola.primera)
    assert cola.primera.estado == EstadoEspera.ACTIVA.value
    assert cola.primera.ofertas_vencidas == 1
    auditoria = list(
        (
            await sesion.scalars(select(Auditoria).where(Auditoria.entidad_id == cola.oferta.id))
        ).all()
    )
    assert len(auditoria) == 1
    assert auditoria[0].accion == AccionAuditada.OFERTA_EXPIRADA.value
