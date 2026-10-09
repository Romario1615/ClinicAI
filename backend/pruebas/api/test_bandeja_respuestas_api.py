"""Bandeja bidireccional: responder, tomar, devolver al agente y cerrar (ADR-0025).

Cada accion se prueba con rol autorizado, rol sin permiso, ambito ajeno
(otra clinica), entrada invalida y sin autenticacion (CLAUDE.md, seccion 5).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.modelos import Auditoria
from app.modulos.conversaciones.agente_whatsapp import INTEGRACION
from app.modulos.conversaciones.modelos import Conversacion, MensajeEntrante
from app.modulos.organizacion.modelos import Clinica, ConfiguracionClinica
from app.modulos.outbox.modelos import OutboxMensaje
from app.modulos.pacientes.modelos import Paciente
from app.modulos.usuarios.modelos import AmbitoAsignacion, Usuario, UsuarioRol
from app.nucleo.auditoria import AccionAuditada
from app.nucleo.reloj import RelojFijo
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]


async def _acceso(
    cliente: AsyncClient,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    *permisos: str,
) -> dict[str, str]:
    await conceder_permisos(sesion, usuario, clinica, *permisos)
    asignacion = await sesion.scalar(
        sa.select(UsuarioRol).where(UsuarioRol.usuario_id == usuario.id)
    )
    assert asignacion is not None
    # La bandeja contiene datos sensibles: hace falta el nivel clinico.
    sesion.add(
        AmbitoAsignacion(usuario_rol_id=asignacion.id, tipo="TIPO_INFORMACION", valor_id=None)
    )
    await sesion.flush()
    return await cabecera_bearer(cliente, usuario, clinica)


async def _conversacion(
    sesion: AsyncSession,
    clinica: Clinica,
    reloj: RelojFijo,
    paciente: Paciente | None = None,
    *,
    estado: str = "EN_HANDOFF",
    ventana_horas: int = 20,
) -> Conversacion:
    conversacion = Conversacion(
        clinica_id=clinica.id,
        canal="WHATSAPP",
        telefono=f"5939{uuid.uuid4().int % 10**8:08d}",
        paciente_id=paciente.id if paciente else None,
        estado=estado,
        motivo_handoff="El paciente pide ayuda.",
        ultima_actividad_en=reloj.ahora(),
        ventana_expira_en=reloj.ahora() + timedelta(hours=ventana_horas),
    )
    sesion.add(conversacion)
    await sesion.flush()
    sesion.add(
        MensajeEntrante(
            conversacion_id=conversacion.id,
            external_id=f"wamid-{uuid.uuid4()}",
            telefono_origen=conversacion.telefono,
            tipo="text",
            texto="Quisiera cambiar mi cita",
            intencion="AYUDA",
            recibido_en=reloj.ahora(),
        )
    )
    await sesion.flush()
    return conversacion


async def _salientes(sesion: AsyncSession, conversacion: Conversacion) -> list[OutboxMensaje]:
    return list(
        (
            await sesion.scalars(
                sa.select(OutboxMensaje).where(
                    OutboxMensaje.destino_tipo == "CONVERSACION",
                    OutboxMensaje.destino_id == conversacion.id,
                )
            )
        ).all()
    )


# ===========================================================================
#  Responder
# ===========================================================================
async def test_responder_encola_texto_libre_asigna_y_audita(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    paciente: Paciente,
    reloj: RelojFijo,
) -> None:
    cabeceras = await _acceso(
        cliente, sesion, usuario, clinica, "conversacion.leer", "conversacion.responder"
    )
    conversacion = await _conversacion(sesion, clinica, reloj, paciente)

    r = await cliente.post(
        f"{api}/conversaciones/{conversacion.id}/respuestas",
        json={"texto": "Hola, le escribe recepción. ¿Qué día le viene bien?"},
        headers={**cabeceras, "Idempotency-Key": "respuesta-1"},
    )

    assert r.status_code == 202, r.text
    salientes = await _salientes(sesion, conversacion)
    assert len(salientes) == 1
    assert salientes[0].carga_util["libre"] is True
    assert salientes[0].entidad_origen_tipo == "usuario"
    assert conversacion.asignado_a_usuario_id == usuario.id
    detalle = (
        await cliente.get(f"{api}/conversaciones/{conversacion.id}", headers=cabeceras)
    ).json()
    assert detalle["respuestas"][0]["autor"] == "PERSONAL"
    assert detalle["respuestas"][0]["texto"].startswith("Hola, le escribe")
    acciones = set(
        (
            await sesion.scalars(
                sa.select(Auditoria.accion).where(Auditoria.entidad_id == conversacion.id)
            )
        ).all()
    )
    assert AccionAuditada.CONVERSACION_RESPONDIDA.value in acciones


async def test_responder_es_idempotente_con_la_misma_clave(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    paciente: Paciente,
    reloj: RelojFijo,
) -> None:
    cabeceras = await _acceso(
        cliente, sesion, usuario, clinica, "conversacion.leer", "conversacion.responder"
    )
    conversacion = await _conversacion(sesion, clinica, reloj, paciente)
    cuerpo = {"texto": "Le confirmo que recibimos su mensaje."}
    for _ in range(2):
        r = await cliente.post(
            f"{api}/conversaciones/{conversacion.id}/respuestas",
            json=cuerpo,
            headers={**cabeceras, "Idempotency-Key": "doble-clic"},
        )
        assert r.status_code == 202, r.text

    assert len(await _salientes(sesion, conversacion)) == 1


async def test_fuera_de_la_ventana_de_24_horas_no_se_puede_responder(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    paciente: Paciente,
    reloj: RelojFijo,
) -> None:
    cabeceras = await _acceso(
        cliente, sesion, usuario, clinica, "conversacion.leer", "conversacion.responder"
    )
    conversacion = await _conversacion(sesion, clinica, reloj, paciente, ventana_horas=-1)

    r = await cliente.post(
        f"{api}/conversaciones/{conversacion.id}/respuestas",
        json={"texto": "Hola"},
        headers={**cabeceras, "Idempotency-Key": "tarde-24h"},
    )

    assert r.status_code == 409
    assert "24" in r.json()["mensaje"]
    assert await _salientes(sesion, conversacion) == []


@pytest.mark.parametrize("texto", ["", "   ", "x" * 1001])
async def test_responder_rechaza_texto_invalido(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    paciente: Paciente,
    reloj: RelojFijo,
    texto: str,
) -> None:
    cabeceras = await _acceso(
        cliente, sesion, usuario, clinica, "conversacion.leer", "conversacion.responder"
    )
    conversacion = await _conversacion(sesion, clinica, reloj, paciente)

    r = await cliente.post(
        f"{api}/conversaciones/{conversacion.id}/respuestas",
        json={"texto": texto},
        headers={**cabeceras, "Idempotency-Key": f"invalido-{len(texto)}"},
    )

    assert r.status_code == 422


# ===========================================================================
#  Tomar, devolver al agente, cerrar
# ===========================================================================
async def test_tomar_una_conversacion_del_agente_la_pasa_a_una_persona(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    paciente: Paciente,
    reloj: RelojFijo,
) -> None:
    cabeceras = await _acceso(
        cliente, sesion, usuario, clinica, "conversacion.leer", "conversacion.tomar"
    )
    conversacion = await _conversacion(sesion, clinica, reloj, paciente, estado="ABIERTA")

    r = await cliente.post(f"{api}/conversaciones/{conversacion.id}/toma", headers=cabeceras)

    assert r.status_code == 204, r.text
    assert conversacion.estado == "EN_HANDOFF"
    assert conversacion.asignado_a_usuario_id == usuario.id


async def test_devolver_al_agente_exige_que_la_clinica_lo_tenga_activo(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    paciente: Paciente,
    reloj: RelojFijo,
) -> None:
    cabeceras = await _acceso(
        cliente, sesion, usuario, clinica, "conversacion.leer", "conversacion.tomar"
    )
    conversacion = await _conversacion(sesion, clinica, reloj, paciente)

    sin_agente = await cliente.post(
        f"{api}/conversaciones/{conversacion.id}/devolucion", headers=cabeceras
    )
    assert sin_agente.status_code == 409

    sesion.add(
        ConfiguracionClinica(
            clinica_id=clinica.id,
            clave=f"integracion.{INTEGRACION}",
            valor={"habilitada": True, "ajustes": {}, "secretos_cifrados": {}},
        )
    )
    await sesion.flush()
    con_agente = await cliente.post(
        f"{api}/conversaciones/{conversacion.id}/devolucion", headers=cabeceras
    )

    assert con_agente.status_code == 204, con_agente.text
    assert conversacion.estado == "ABIERTA"
    assert conversacion.asignado_a_usuario_id is None


async def test_devolver_sin_paciente_identificado_no_se_permite(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    reloj: RelojFijo,
) -> None:
    cabeceras = await _acceso(
        cliente, sesion, usuario, clinica, "conversacion.leer", "conversacion.tomar"
    )
    sesion.add(
        ConfiguracionClinica(
            clinica_id=clinica.id,
            clave=f"integracion.{INTEGRACION}",
            valor={"habilitada": True, "ajustes": {}, "secretos_cifrados": {}},
        )
    )
    conversacion = await _conversacion(sesion, clinica, reloj, None)

    r = await cliente.post(f"{api}/conversaciones/{conversacion.id}/devolucion", headers=cabeceras)

    assert r.status_code == 409


async def test_cerrar_deja_la_conversacion_cerrada_y_ya_no_admite_respuestas(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    paciente: Paciente,
    reloj: RelojFijo,
) -> None:
    cabeceras = await _acceso(
        cliente, sesion, usuario, clinica, "conversacion.leer", "conversacion.responder"
    )
    conversacion = await _conversacion(sesion, clinica, reloj, paciente)

    r = await cliente.post(f"{api}/conversaciones/{conversacion.id}/cierre", headers=cabeceras)
    assert r.status_code == 204, r.text
    assert conversacion.estado == "CERRADA"
    assert conversacion.cerrada_en is not None

    respuesta = await cliente.post(
        f"{api}/conversaciones/{conversacion.id}/respuestas",
        json={"texto": "Hola"},
        headers={**cabeceras, "Idempotency-Key": "tras-cierre"},
    )
    assert respuesta.status_code == 409


# ===========================================================================
#  Seguridad: permiso, ambito ajeno y autenticacion
# ===========================================================================
ACCIONES = [
    ("respuestas", {"texto": "Hola"}),
    ("toma", None),
    ("devolucion", None),
    ("cierre", None),
]


@pytest.mark.parametrize(("accion", "cuerpo"), ACCIONES)
async def test_sin_permiso_de_escritura_devuelve_403(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    paciente: Paciente,
    reloj: RelojFijo,
    accion: str,
    cuerpo: dict[str, str] | None,
) -> None:
    # Un auditor lee la bandeja pero no actua sobre ella.
    cabeceras = await _acceso(cliente, sesion, usuario, clinica, "conversacion.leer")
    conversacion = await _conversacion(sesion, clinica, reloj, paciente)

    r = await cliente.post(
        f"{api}/conversaciones/{conversacion.id}/{accion}",
        json=cuerpo,
        headers={**cabeceras, "Idempotency-Key": f"sin-permiso-{accion}"},
    )

    assert r.status_code == 403
    assert conversacion.estado == "EN_HANDOFF"


@pytest.mark.parametrize(("accion", "cuerpo"), ACCIONES)
async def test_conversacion_de_otra_clinica_devuelve_404(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    reloj: RelojFijo,
    sufijo: str,
    accion: str,
    cuerpo: dict[str, str] | None,
) -> None:
    cabeceras = await _acceso(
        cliente,
        sesion,
        usuario,
        clinica,
        "conversacion.leer",
        "conversacion.responder",
        "conversacion.tomar",
    )
    otra = Clinica(nombre=f"Otra clinica {sufijo} [SINTETICO]", zona_horaria="America/Guayaquil")
    sesion.add(otra)
    await sesion.flush()
    ajena = await _conversacion(sesion, otra, reloj, None)

    r = await cliente.post(
        f"{api}/conversaciones/{ajena.id}/{accion}",
        json=cuerpo,
        headers={**cabeceras, "Idempotency-Key": f"ajena-{accion}"},
    )

    assert r.status_code == 404
    assert ajena.estado == "EN_HANDOFF"


@pytest.mark.parametrize(("accion", "cuerpo"), ACCIONES)
async def test_sin_autenticacion_devuelve_401(
    cliente: AsyncClient,
    api: str,
    accion: str,
    cuerpo: dict[str, str] | None,
) -> None:
    r = await cliente.post(f"{api}/conversaciones/{uuid.uuid4()}/{accion}", json=cuerpo)

    assert r.status_code == 401
