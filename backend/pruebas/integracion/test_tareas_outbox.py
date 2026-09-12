"""Los trabajos periodicos del outbox.

Lo que aportan estas pruebas sobre las de `test_outbox.py`: que el trabajo que
de verdad corre en el worker -- con su contexto, su configuracion y su
seleccion de adaptador -- recorre el camino completo.

La seleccion de adaptador segun el entorno -- la garantia de que en modo
sandbox no se construye el adaptador real -- se prueba en
`pruebas/unitarias/test_adaptadores_whatsapp.py`, porque no toca la base de
datos.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.mensajeria.adaptadores import RegistroCanales
from app.mensajeria.servicios import ServicioOutbox, SolicitudEnvio
from app.modelos import Clinica, Consentimiento, Paciente
from app.modulos.outbox.modelos import (
    CanalOutbox,
    EstadoOutbox,
    OutboxMensaje,
    TipoMensajeOutbox,
)
from app.modulos.pacientes.modelos import TipoConsentimiento
from app.nucleo.bd import GestorBaseDatos
from app.nucleo.configuracion import Configuracion
from app.nucleo.reloj import RelojFijo
from app.tareas.outbox import procesar_outbox, recuperar_mensajes_huerfanos

pytestmark = [pytest.mark.integracion, pytest.mark.asyncio]

TELEFONO_SINTETICO = "593999000222"


class GestorDeUnaSesion(GestorBaseDatos):
    """Gestor que entrega siempre la sesion aislada de la prueba."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion_prueba = sesion

    async def sesion(self) -> Any:
        yield self._sesion_prueba

    async def cerrar(self) -> None:
        return None


@pytest_asyncio.fixture
async def paciente_contactable(sesion: AsyncSession, clinica: Clinica, sufijo: str) -> Paciente:
    registro = Paciente(
        clinica_id=clinica.id,
        tipo_documento="CEDULA",
        numero_documento=f"4{sufijo[:9]}",
        nombre="Paciente Tareas",
        apellido="De Prueba",
        telefono_whatsapp=TELEFONO_SINTETICO,
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
def reloj_fijo(instante: datetime) -> RelojFijo:
    return RelojFijo(instante)


@pytest.fixture
def contexto(
    sesion: AsyncSession, reloj_fijo: RelojFijo, configuracion: Configuracion
) -> dict[Any, Any]:
    """Contexto equivalente al que construye `al_arrancar` del worker."""
    return {
        "configuracion": configuracion.model_copy(update={"modo_whatsapp": "sandbox"}),
        "reloj": reloj_fijo,
        "gestor_bd": GestorDeUnaSesion(sesion),
        "job_id": "prueba-worker",
    }


async def _encolar(
    sesion: AsyncSession,
    reloj: RelojFijo,
    paciente: Paciente,
    clinica: Clinica,
    clave: str,
) -> uuid.UUID:
    servicio = ServicioOutbox(sesion, reloj, RegistroCanales())
    identificador = await servicio.encolar(
        SolicitudEnvio(
            tipo=TipoMensajeOutbox.CITA_RECORDATORIO_HORAS_ANTES,
            canal=CanalOutbox.WHATSAPP,
            destino_tipo="PACIENTE",
            destino_id=paciente.id,
            clave_deduplicacion=clave,
            variables={"nombre": "Paciente", "hora": "09:30", "sede": "Sede de Prueba"},
            clinica_id=clinica.id,
        )
    )
    assert identificador is not None
    await sesion.flush()
    return identificador


# ---------------------------------------------------------------------------
#  El trabajo completo
# ---------------------------------------------------------------------------
async def test_procesar_outbox_entrega_los_pendientes(
    contexto: dict[Any, Any],
    sesion: AsyncSession,
    reloj_fijo: RelojFijo,
    paciente_contactable: Paciente,
    clinica: Clinica,
    sufijo: str,
) -> None:
    identificador = await _encolar(
        sesion, reloj_fijo, paciente_contactable, clinica, f"tarea-{sufijo}"
    )

    entregados = await procesar_outbox(contexto)
    assert entregados == 1

    mensaje = await sesion.get(OutboxMensaje, identificador, populate_existing=True)
    assert mensaje is not None
    assert mensaje.estado == EstadoOutbox.ENTREGADO.value


async def test_procesar_outbox_sin_pendientes_no_hace_nada(
    contexto: dict[Any, Any],
) -> None:
    """El caso normal: el barrido corre cada minuto y casi siempre esta vacio.

    La consulta usa un indice parcial sobre los pendientes, asi que no se
    degrada con el historico.
    """
    assert await procesar_outbox(contexto) == 0


async def test_recuperar_huerfanos_como_trabajo(
    contexto: dict[Any, Any],
    sesion: AsyncSession,
    reloj_fijo: RelojFijo,
    paciente_contactable: Paciente,
    clinica: Clinica,
    sufijo: str,
) -> None:
    """Un mensaje que quedo EN_PROCESO porque el worker murio."""
    identificador = await _encolar(
        sesion, reloj_fijo, paciente_contactable, clinica, f"huerfano-tarea-{sufijo}"
    )
    await sesion.execute(
        sa.update(OutboxMensaje)
        .where(OutboxMensaje.id == identificador)
        .values(
            estado=EstadoOutbox.EN_PROCESO.value,
            tomado_por="worker-muerto",
            tomado_en=reloj_fijo.ahora(),
        )
    )
    await sesion.flush()

    reloj_fijo.avanzar(minutes=30)
    assert await recuperar_mensajes_huerfanos(contexto) == 1

    mensaje = await sesion.get(OutboxMensaje, identificador, populate_existing=True)
    assert mensaje is not None
    assert mensaje.estado == EstadoOutbox.PENDIENTE.value
