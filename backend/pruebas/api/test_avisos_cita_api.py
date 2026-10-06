"""Al mover o cancelar una cita se avisa al paciente, sin datos clínicos.

Antes el flujo «cancelación y reprogramación» figuraba en Automatizaciones
pero nada encolaba esos mensajes. Sin consentimiento de WhatsApp no se envía.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita
from app.modulos.organizacion.modelos import Clinica, Sede, Servicio
from app.modulos.outbox.modelos import OutboxMensaje
from app.modulos.pacientes.modelos import Consentimiento, Paciente
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Usuario
from pruebas.api.conftest import cabecera_bearer, conceder_permisos
from pruebas.conftest import INSTANTE_REFERENCIA

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


async def _cita(
    sesion: AsyncSession,
    clinica: Clinica,
    sede: Sede,
    servicio: Servicio,
    profesional: Profesional,
    paciente: Paciente,
    horas: int,
) -> Cita:
    inicio = INSTANTE_REFERENCIA + timedelta(days=3, hours=horas)
    cita = Cita(
        clinica_id=clinica.id,
        sede_id=sede.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        servicio_id=servicio.id,
        inicio=inicio,
        duracion_minutos=30,
        minutos_preparacion=0,
        estado="CONFIRMED",
        origen="PANEL",
        confirmada_en=INSTANTE_REFERENCIA,
    )
    sesion.add(cita)
    await sesion.flush()
    return cita


async def _tipos(sesion: AsyncSession, cita: Cita) -> list[str]:
    filas = await sesion.execute(
        sa.select(OutboxMensaje.tipo).where(OutboxMensaje.entidad_origen_id == cita.id)
    )
    return sorted(str(t) for t in filas.scalars())


async def test_reprogramar_y_cancelar_avisan_con_consentimiento(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    servicio: Servicio,
    profesional: Profesional,
    paciente: Paciente,
) -> None:
    sesion.add(
        Consentimiento(
            paciente_id=paciente.id,
            tipo="COMUNICACION_WHATSAPP",
            otorgado=True,
            version_texto="v1",
            texto_hash="0" * 64,
            canal="PRESENCIAL",
        )
    )
    reprogramable = await _cita(sesion, clinica, sede, servicio, profesional, paciente, 0)
    cancelable = await _cita(sesion, clinica, sede, servicio, profesional, paciente, 2)
    await conceder_permisos(
        sesion, usuario, clinica, "cita.reprogramar", "cita.cancelar", sedes=(sede.id,)
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    nuevo = (reprogramable.inicio + timedelta(hours=5)).isoformat()
    movida = await cliente.post(
        f"{api}/agenda/citas/{reprogramable.id}/reprogramacion",
        headers=cabeceras,
        json={"nuevo_inicio": nuevo, "motivo": "Pidió más tarde"},
    )
    assert movida.status_code == 200, movida.text
    assert "CITA_REPROGRAMACION" in await _tipos(sesion, reprogramable)

    cancelada = await cliente.post(
        f"{api}/agenda/citas/{cancelable.id}/cancelacion",
        headers=cabeceras,
        json={"motivo": "No puede asistir"},
    )
    assert cancelada.status_code == 200, cancelada.text
    assert "CITA_CANCELACION" in await _tipos(sesion, cancelable)

    # El mensaje no lleva nada clínico: ni el servicio ni el profesional.
    carga = (
        await sesion.execute(
            sa.select(OutboxMensaje.carga_util).where(
                OutboxMensaje.entidad_origen_id == cancelable.id,
                OutboxMensaje.tipo == "CITA_CANCELACION",
            )
        )
    ).scalar_one()
    volcado = json.dumps(carga, ensure_ascii=False)
    assert servicio.nombre not in volcado
    assert sede.nombre in volcado


async def test_sin_consentimiento_no_se_avisa(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    servicio: Servicio,
    profesional: Profesional,
    paciente: Paciente,
) -> None:
    cita = await _cita(sesion, clinica, sede, servicio, profesional, paciente, 0)
    await conceder_permisos(sesion, usuario, clinica, "cita.cancelar", sedes=(sede.id,))
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    cancelada = await cliente.post(
        f"{api}/agenda/citas/{cita.id}/cancelacion",
        headers=cabeceras,
        json={"motivo": "No puede asistir"},
    )
    assert cancelada.status_code == 200, cancelada.text
    assert "CITA_CANCELACION" not in await _tipos(sesion, cita)
