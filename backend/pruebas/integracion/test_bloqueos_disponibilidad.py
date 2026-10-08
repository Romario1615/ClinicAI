"""A quien afecta un bloqueo de agenda, segun el motor de disponibilidad.

La ruta de bloqueos guarda siempre la sede, tambien en un bloqueo de sala.
Si el motor tratara ese bloqueo como cierre de sede, cerrar un consultorio
para mantenimiento dejaria sin turnos a todos los profesionales de la sede,
aunque las demas salas sigan atendiendo.  El panel de ocupacion aplica la
misma regla (`condicion_bloqueos_aplicables`); estas pruebas fijan la del
motor.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.disponibilidad import Intervalo, MotivoNoDisponible
from app.modulos.agenda.modelos import BloqueoAgenda
from app.modulos.agenda.repositorio import RepositorioAgenda
from app.modulos.agenda.servicios import ServicioAgenda
from app.nucleo.autorizacion import Ambito, Principal, TipoActor
from app.nucleo.reloj import RelojFijo

pytestmark = [pytest.mark.integracion, pytest.mark.asyncio]

# Miercoles 15 de abril de 2026, 14:00 UTC = 09:00 en Guayaquil.
AHORA = datetime(2026, 4, 15, 14, 0, tzinfo=UTC)
# Ventana consultada: el dia siguiente, de 09:00 a 13:00 locales.
DESDE = datetime(2026, 4, 16, 14, 0, tzinfo=UTC)
HASTA = datetime(2026, 4, 16, 18, 0, tzinfo=UTC)
# Bloqueo de 10:00 a 11:00 locales.
BLOQUEO = Intervalo(
    datetime(2026, 4, 16, 15, 0, tzinfo=UTC), datetime(2026, 4, 16, 16, 0, tzinfo=UTC)
)


@pytest.fixture
def principal(clinica, sede) -> Principal:
    return Principal(
        actor_tipo=TipoActor.USUARIO,
        actor_id=uuid.uuid4(),
        clinica_id=clinica.id,
        permisos=frozenset({"agenda.leer"}),
        ambito=Ambito(
            clinica_id=clinica.id,
            sedes=frozenset({sede.id}),
            todas_las_especialidades=True,
            todos_los_profesionales=True,
            todos_los_pacientes=True,
        ),
        origen="WEB",
    )


@pytest.fixture
async def servicio_agenda(sesion: AsyncSession, sede) -> ServicioAgenda:
    for dia in range(1, 8):
        await sesion.execute(
            sa.text(
                "INSERT INTO horario_atencion (propietario_tipo, propietario_id, "
                "dia_semana, hora_inicio, hora_fin, granularidad_minutos) "
                "VALUES ('SEDE', :sede, :dia, '00:00', '23:59', 15)"
            ),
            {"sede": sede.id, "dia": dia},
        )
    await sesion.flush()
    return ServicioAgenda(sesion, RepositorioAgenda(sesion), RelojFijo(AHORA))


async def _turnos(
    servicio_agenda: ServicioAgenda,
    principal: Principal,
    *,
    profesional,
    servicio,
    sede,
    consultorio_id: uuid.UUID | None,
) -> list[Intervalo]:
    resultado = await servicio_agenda.consultar_disponibilidad(
        principal=principal,
        profesional_id=profesional.id,
        servicio_id=servicio.id,
        sede_id=sede.id,
        desde=DESDE,
        hasta=HASTA,
        consultorio_id=consultorio_id,
    )
    return [turno.intervalo for turno in resultado.turnos]


def _alguno_solapa(turnos: list[Intervalo]) -> bool:
    return any(turno.se_solapa_con(BLOQUEO) for turno in turnos)


async def test_un_bloqueo_de_consultorio_solo_afecta_cuando_se_pide_esa_sala(
    sesion: AsyncSession,
    servicio_agenda: ServicioAgenda,
    principal: Principal,
    clinica,
    sede,
    consultorio,
    profesional,
    servicio,
) -> None:
    sesion.add(
        BloqueoAgenda(
            clinica_id=clinica.id,
            sede_id=sede.id,
            consultorio_id=consultorio.id,
            tipo="MANTENIMIENTO",
            inicio=BLOQUEO.inicio,
            fin=BLOQUEO.fin,
            motivo="Mantenimiento sintetico de sala",
        )
    )
    await sesion.flush()

    sin_sala = await _turnos(
        servicio_agenda,
        principal,
        profesional=profesional,
        servicio=servicio,
        sede=sede,
        consultorio_id=None,
    )
    en_la_sala = await _turnos(
        servicio_agenda,
        principal,
        profesional=profesional,
        servicio=servicio,
        sede=sede,
        consultorio_id=consultorio.id,
    )

    assert _alguno_solapa(sin_sala), "Sin sala concreta, la sede sigue atendiendo."
    assert en_la_sala, "Fuera del bloqueo la sala tiene turnos."
    assert not _alguno_solapa(en_la_sala), "La sala bloqueada no ofrece turnos en el bloqueo."


async def test_un_bloqueo_de_sede_afecta_con_y_sin_consultorio(
    sesion: AsyncSession,
    servicio_agenda: ServicioAgenda,
    principal: Principal,
    clinica,
    sede,
    consultorio,
    profesional,
    servicio,
) -> None:
    sesion.add(
        BloqueoAgenda(
            clinica_id=clinica.id,
            sede_id=sede.id,
            tipo="MANTENIMIENTO",
            inicio=BLOQUEO.inicio,
            fin=BLOQUEO.fin,
            motivo="Corte de luz sintetico",
        )
    )
    await sesion.flush()

    for consultorio_id in (None, consultorio.id):
        turnos = await _turnos(
            servicio_agenda,
            principal,
            profesional=profesional,
            servicio=servicio,
            sede=sede,
            consultorio_id=consultorio_id,
        )
        assert turnos
        assert not _alguno_solapa(turnos)


async def test_las_ocupaciones_del_repositorio_distinguen_sala_y_sede(
    sesion: AsyncSession,
    clinica,
    sede,
    consultorio,
    profesional,
) -> None:
    de_sala = BloqueoAgenda(
        clinica_id=clinica.id,
        sede_id=sede.id,
        consultorio_id=consultorio.id,
        tipo="MANTENIMIENTO",
        inicio=BLOQUEO.inicio,
        fin=BLOQUEO.fin,
    )
    de_profesional = BloqueoAgenda(
        clinica_id=clinica.id,
        sede_id=sede.id,
        profesional_id=profesional.id,
        tipo="AUSENCIA",
        inicio=BLOQUEO.inicio + timedelta(hours=1),
        fin=BLOQUEO.fin + timedelta(hours=1),
    )
    sesion.add_all([de_sala, de_profesional])
    await sesion.flush()
    repositorio = RepositorioAgenda(sesion)

    async def _bloqueos(consultorio_id: uuid.UUID | None) -> set[uuid.UUID | None]:
        ocupaciones = await repositorio.obtener_ocupaciones(
            profesional_id=profesional.id,
            sede_id=sede.id,
            desde=DESDE,
            hasta=HASTA,
            consultorio_id=consultorio_id,
        )
        return {
            ocupacion.referencia_id
            for ocupacion in ocupaciones
            if ocupacion.motivo is MotivoNoDisponible.BLOQUEO
        }

    assert await _bloqueos(None) == {de_profesional.id}
    assert await _bloqueos(consultorio.id) == {de_profesional.id, de_sala.id}
