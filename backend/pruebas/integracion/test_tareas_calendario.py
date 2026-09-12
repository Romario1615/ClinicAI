"""Los trabajos periodicos del calendario.

Lo que aportan sobre `test_calendario.py`: que el trabajo que de verdad corre
en el worker -- con su contexto y su configuracion -- recorre el camino
completo, incluida la deteccion de citas sin reflejo.

La seleccion de adaptador por entorno se prueba en
`pruebas/unitarias/test_seleccion_calendario.py`, porque no toca la base.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita, EstadoCita, OrigenCita
from app.modulos.calendario.seleccion import PROVEEDOR_GOOGLE
from app.modulos.organizacion.modelos import Clinica, Consultorio, Sede, Servicio
from app.modulos.pacientes.modelos import Paciente
from app.modulos.profesionales.modelos import (
    CalendarioConexion,
    CalendarioEvento,
    EstadoEventoCalendario,
    EstadoSincronizacion,
    Profesional,
)
from app.nucleo.bd import GestorBaseDatos
from app.nucleo.configuracion import Configuracion
from app.nucleo.reloj import RelojFijo
from app.nucleo.seguridad import CifradorDatos
from app.tareas.calendario import reconciliar_calendarios, sincronizar_calendarios

pytestmark = [pytest.mark.integracion, pytest.mark.asyncio]


class GestorDeUnaSesion(GestorBaseDatos):
    """Gestor que entrega siempre la sesion aislada de la prueba."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion_prueba = sesion

    async def sesion(self) -> Any:
        yield self._sesion_prueba

    async def cerrar(self) -> None:
        return None


@pytest.fixture
def reloj_fijo(instante: datetime) -> RelojFijo:
    return RelojFijo(instante)


@pytest.fixture
def configuracion_sandbox(configuracion: Configuracion) -> Configuracion:
    return configuracion.model_copy(update={"modo_calendario": "sandbox"})


@pytest.fixture
def contexto(
    sesion: AsyncSession, reloj_fijo: RelojFijo, configuracion_sandbox: Configuracion
) -> dict[Any, Any]:
    """Contexto equivalente al que construye `al_arrancar` del worker."""
    return {
        "configuracion": configuracion_sandbox,
        "reloj": reloj_fijo,
        "gestor_bd": GestorDeUnaSesion(sesion),
        "job_id": "prueba-worker",
    }


@pytest_asyncio.fixture
async def conexion(
    sesion: AsyncSession,
    profesional: Profesional,
    configuracion_sandbox: Configuracion,
    reloj_fijo: RelojFijo,
) -> CalendarioConexion:
    """Conexion con tokens cifrados con la clave real del entorno.

    Tiene que ser la misma que usa el worker, o el servicio no podria
    descifrarlos -- y la prueba pasaria por el motivo equivocado, contando
    «sin conexion» en lugar de sincronizaciones.
    """
    cifrador = CifradorDatos(configuracion_sandbox.clave_cifrado_datos.get_secret_value())
    contexto_cifrado = f"calendario:{profesional.id}".encode()
    registro = CalendarioConexion(
        profesional_id=profesional.id,
        proveedor=PROVEEDOR_GOOGLE,
        calendar_id="primary",
        token_acceso_cifrado=cifrador.cifrar("acceso", contexto=contexto_cifrado),
        token_refresco_cifrado=cifrador.cifrar("refresco", contexto=contexto_cifrado),
        expira_en=reloj_fijo.ahora() + timedelta(hours=1),
        estado_sincronizacion=EstadoSincronizacion.CONECTADO.value,
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


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
    await sesion.refresh(registro)
    return registro


# ---------------------------------------------------------------------------
#  El trabajo completo
# ---------------------------------------------------------------------------
async def test_el_trabajo_detecta_y_publica_en_la_misma_ejecucion(
    contexto: dict[Any, Any],
    sesion: AsyncSession,
    conexion: CalendarioConexion,
    cita: Cita,
) -> None:
    """Una cita confirmada aparece en el siguiente barrido, no en el de despues.

    Ese es el motivo de que la deteccion y la publicacion vayan juntas.
    """
    publicados = await sincronizar_calendarios(contexto)
    assert publicados == 1

    evento = (
        await sesion.execute(sa.select(CalendarioEvento).where(CalendarioEvento.cita_id == cita.id))
    ).scalar_one()
    assert evento.estado == EstadoEventoCalendario.SINCRONIZADO.value


async def test_el_trabajo_sin_conexiones_no_hace_nada(contexto: dict[Any, Any], cita: Cita) -> None:
    """El caso normal en una clinica donde nadie conecto su calendario."""
    assert await sincronizar_calendarios(contexto) == 0


async def test_el_trabajo_es_idempotente(
    contexto: dict[Any, Any], conexion: CalendarioConexion, cita: Cita
) -> None:
    """Un segundo barrido no vuelve a crear el evento.

    Sin esto, cada ejecucion del cron anadiria un evento duplicado al
    calendario del profesional cada dos minutos.
    """
    assert await sincronizar_calendarios(contexto) == 1
    assert await sincronizar_calendarios(contexto) == 0


async def test_la_reconciliacion_sin_eventos_no_hace_nada(
    contexto: dict[Any, Any],
) -> None:
    assert await reconciliar_calendarios(contexto) == 0
