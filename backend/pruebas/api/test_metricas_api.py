"""La exportación operativa no debe revelar rutas con identificadores."""

import uuid
from datetime import timedelta

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.outbox.modelos import CanalOutbox, EstadoOutbox, OutboxMensaje, TipoMensajeOutbox
from pruebas.conftest import INSTANTE_REFERENCIA


@pytest.mark.asyncio
async def test_metricas_exponen_outbox_y_rutas_sin_identificadores(
    cliente: AsyncClient, sesion: AsyncSession
) -> None:
    identificador = str(uuid.uuid4())
    respuesta_404 = await cliente.get(f"/ruta-inexistente/{identificador}")
    assert respuesta_404.status_code == 404
    respuesta_protegida = await cliente.get(f"/api/v1/pacientes/{identificador}")
    assert respuesta_protegida.status_code == 401

    sesion.add(
        OutboxMensaje(
            tipo=TipoMensajeOutbox.CITA_RECORDATORIO_DIA_ANTES.value,
            canal=CanalOutbox.WHATSAPP.value,
            destino_tipo="PACIENTE",
            destino_id=uuid.uuid4(),
            carga_util={},
            clave_deduplicacion=uuid.uuid4().hex,
            estado=EstadoOutbox.FALLIDO.value,
            ultimo_error="Fallo de prueba",
            creado_en=INSTANTE_REFERENCIA,
        )
    )
    sesion.add(
        OutboxMensaje(
            tipo=TipoMensajeOutbox.CITA_RECORDATORIO_DIA_ANTES.value,
            canal=CanalOutbox.WHATSAPP.value,
            destino_tipo="PACIENTE",
            destino_id=uuid.uuid4(),
            carga_util={},
            clave_deduplicacion=uuid.uuid4().hex,
            estado=EstadoOutbox.PENDIENTE.value,
            creado_en=INSTANTE_REFERENCIA - timedelta(minutes=12),
        )
    )
    await sesion.flush()

    respuesta = await cliente.get("/metrics")

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("text/plain")
    assert 'clinicai_outbox_mensajes{estado="FALLIDO"} 1.0' in respuesta.text
    assert "clinicai_outbox_pendiente_mas_antiguo_segundos 720.0" in respuesta.text
    assert 'estado="404"' in respuesta.text
    assert 'ruta="/api/v1/pacientes/{paciente_id}"' in respuesta.text
    assert "/ruta-inexistente/" not in respuesta.text
    assert identificador not in respuesta.text


@pytest.mark.asyncio
async def test_metricas_exigen_bearer_cuando_se_configura(
    cliente: AsyncClient,
) -> None:
    cliente._transport.app.state.configuracion.metricas_token = SecretStr("token-interno-de-prueba")

    sin_token = await cliente.get("/metrics")
    con_token = await cliente.get(
        "/metrics", headers={"Authorization": "Bearer token-interno-de-prueba"}
    )

    assert sin_token.status_code == 401
    assert sin_token.headers["www-authenticate"] == "Bearer"
    assert con_token.status_code == 200
