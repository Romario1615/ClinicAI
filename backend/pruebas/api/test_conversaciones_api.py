"""Acceso, aislamiento y auditoría de la bandeja de conversaciones."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.modelos import Auditoria
from app.modulos.conversaciones.modelos import Conversacion, MensajeEntrante
from app.modulos.organizacion.modelos import Clinica
from app.modulos.usuarios.modelos import AmbitoAsignacion, Usuario, UsuarioRol
from app.nucleo.auditoria import AccionAuditada
from app.nucleo.reloj import RelojFijo
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]


async def _sembrar(sesion: AsyncSession, clinica: Clinica, reloj: RelojFijo) -> Conversacion:
    conversacion = Conversacion(
        clinica_id=clinica.id,
        canal="WHATSAPP",
        telefono="593999000123",
        estado="EN_HANDOFF",
        motivo_handoff="El paciente pide ayuda.",
        ultima_actividad_en=reloj.ahora(),
    )
    sesion.add(conversacion)
    await sesion.flush()
    sesion.add(
        MensajeEntrante(
            conversacion_id=conversacion.id,
            external_id=f"wamid-{uuid.uuid4()}",
            telefono_origen=conversacion.telefono,
            tipo="text",
            texto="Mensaje sintético de prueba",
            intencion="AYUDA",
            recibido_en=reloj.ahora(),
        )
    )
    await sesion.flush()
    return conversacion


async def _conceder_lectura_clinica(
    sesion: AsyncSession, usuario: Usuario, clinica: Clinica
) -> None:
    await conceder_permisos(sesion, usuario, clinica, "conversacion.leer")
    asignacion = await sesion.scalar(
        sa.select(UsuarioRol).where(UsuarioRol.usuario_id == usuario.id)
    )
    assert asignacion is not None
    sesion.add(
        AmbitoAsignacion(
            usuario_rol_id=asignacion.id,
            tipo="TIPO_INFORMACION",
            valor_id=None,
        )
    )
    await sesion.flush()


async def test_leer_bandeja_y_detalle_audita_sin_guardar_texto_en_auditoria(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    reloj: RelojFijo,
) -> None:
    await _conceder_lectura_clinica(sesion, usuario, clinica)
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    conversacion = await _sembrar(sesion, clinica, reloj)

    cuenta = await cliente.get(f"{api}/conversaciones/pendientes/cuenta", headers=cabeceras)
    assert cuenta.status_code == 200 and cuenta.json() == {"cantidad": 1}
    bandeja = await cliente.get(f"{api}/conversaciones", headers=cabeceras)
    assert bandeja.status_code == 200
    assert bandeja.json()["total"] == 1
    assert bandeja.json()["elementos"][0]["id"] == str(conversacion.id)
    assert bandeja.json()["elementos"][0]["ultimo_mensaje"] == "Mensaje sintético de prueba"

    detalle = await cliente.get(f"{api}/conversaciones/{conversacion.id}", headers=cabeceras)
    assert detalle.status_code == 200
    assert detalle.json()["mensajes"][0]["texto"] == "Mensaje sintético de prueba"

    filas = (
        await sesion.scalars(
            sa.select(Auditoria).where(
                Auditoria.accion.in_(
                    [
                        AccionAuditada.CONVERSACION_LEIDA.value,
                        AccionAuditada.CONVERSACION_CONSULTADA.value,
                    ]
                )
            )
        )
    ).all()
    assert {fila.accion for fila in filas} == {
        AccionAuditada.CONVERSACION_LEIDA.value,
        AccionAuditada.CONVERSACION_CONSULTADA.value,
    }
    assert all("texto" not in (fila.metadatos or {}) for fila in filas)


async def test_sin_permiso_no_lee_conversaciones(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
) -> None:
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    respuesta = await cliente.get(f"{api}/conversaciones", headers=cabeceras)
    assert respuesta.status_code == 403


async def test_sin_alcance_clinico_el_texto_no_es_visible(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    reloj: RelojFijo,
) -> None:
    await conceder_permisos(sesion, usuario, clinica, "conversacion.leer")
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    conversacion = await _sembrar(sesion, clinica, reloj)

    listado = await cliente.get(f"{api}/conversaciones", headers=cabeceras)
    detalle = await cliente.get(f"{api}/conversaciones/{conversacion.id}", headers=cabeceras)
    assert listado.status_code == 200 and listado.json()["elementos"] == []
    assert detalle.status_code == 404


async def test_no_expone_conversaciones_de_otra_clinica(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    reloj: RelojFijo,
) -> None:
    otra = Clinica(nombre="Otra clínica sintética", zona_horaria="America/Guayaquil")
    sesion.add(otra)
    await sesion.flush()
    ajena = await _sembrar(sesion, otra, reloj)
    await _conceder_lectura_clinica(sesion, usuario, clinica)
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    detalle = await cliente.get(f"{api}/conversaciones/{ajena.id}", headers=cabeceras)
    assert detalle.status_code == 404
    assert (await cliente.get(f"{api}/conversaciones", headers=cabeceras)).json()["elementos"] == []
