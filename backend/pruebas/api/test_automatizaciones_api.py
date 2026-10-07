"""Automatizaciones: catálogo visible, interruptor por clínica auditado y
mensajes de un flujo apagado que no se encolan."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.mensajeria.servicios import ServicioOutbox, SolicitudEnvio
from app.modulos.auditoria.modelos import Auditoria
from app.modulos.automatizaciones import servicios as automatizaciones
from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.outbox.modelos import CanalOutbox, TipoMensajeOutbox
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.reloj import RelojFijo
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]


async def test_sin_permiso_no_ve_ni_cambia(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
) -> None:
    await conceder_permisos(sesion, usuario, clinica, "agenda.leer", sedes=(sede.id,))
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    assert (await cliente.get(f"{api}/automatizaciones", headers=cabeceras)).status_code == 403
    cambio = await cliente.put(
        f"{api}/automatizaciones/promociones",
        json={"activo": False, "motivo": "Pausa de campañas"},
        headers=cabeceras,
    )
    assert cambio.status_code == 403
    assert (await cliente.get(f"{api}/automatizaciones")).status_code == 401


async def test_lista_apaga_y_audita_y_respeta_obligatorios(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
) -> None:
    await conceder_permisos(sesion, usuario, clinica, "configuracion.escribir", sedes=(sede.id,))
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    lista = (await cliente.get(f"{api}/automatizaciones", headers=cabeceras)).json()
    codigos = {f["codigo"]: f for f in lista}
    assert codigos["recordatorio_dia_antes"]["activo"] is True
    assert codigos["derivacion_a_persona"]["obligatorio"] is True
    assert "quien_ve" in codigos["recordatorio_toma"]

    apagado = await cliente.put(
        f"{api}/automatizaciones/recordatorio_dia_antes",
        json={"activo": False, "motivo": "La clínica llama por teléfono"},
        headers=cabeceras,
    )
    assert apagado.status_code == 200, apagado.text
    assert apagado.json()["activo"] is False
    estados = await automatizaciones.estados(sesion, clinica.id)
    assert estados["recordatorio_dia_antes"] is False

    # Un segundo cambio crea otra versión y conserva la anterior.
    encendido = await cliente.put(
        f"{api}/automatizaciones/recordatorio_dia_antes",
        json={"activo": True, "motivo": "Se retoma el recordatorio"},
        headers=cabeceras,
    )
    assert encendido.json()["activo"] is True

    obligatorio = await cliente.put(
        f"{api}/automatizaciones/aviso_cambio_cita",
        json={"activo": False, "motivo": "Intento de apagar"},
        headers=cabeceras,
    )
    assert obligatorio.status_code == 422
    inexistente = await cliente.put(
        f"{api}/automatizaciones/no_existe",
        json={"activo": False, "motivo": "Prueba de inexistente"},
        headers=cabeceras,
    )
    assert inexistente.status_code == 404
    corto = await cliente.put(
        f"{api}/automatizaciones/promociones",
        json={"activo": False, "motivo": "x"},
        headers=cabeceras,
    )
    assert corto.status_code == 422

    acciones = (
        await sesion.execute(
            sa.select(sa.func.count()).where(
                Auditoria.accion == "automatizacion.cambiada", Auditoria.clinica_id == clinica.id
            )
        )
    ).scalar_one()
    assert acciones == 2


async def test_el_estado_de_automatizaciones_no_se_cruza_entre_clinicas(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    sufijo: str,
) -> None:
    """Una clínica no puede leer ni cambiar las preferencias de otra."""
    otra_clinica = Clinica(
        nombre=f"Clínica aislada {sufijo}",
        identificacion_fiscal=f"AISLADA-{sufijo[:12]}",
        zona_horaria="America/Guayaquil",
    )
    sesion.add(otra_clinica)
    await sesion.flush()
    otro_usuario = Usuario(
        clinica_id=otra_clinica.id,
        correo=f"aislamiento-{sufijo}@example.invalid",
        hash_contrasena=usuario.hash_contrasena,
        nombre="Usuario",
        apellido="Otra clínica",
    )
    sesion.add(otro_usuario)
    await sesion.flush()

    await conceder_permisos(sesion, usuario, clinica, "configuracion.escribir", sedes=(sede.id,))
    await conceder_permisos(
        sesion, otro_usuario, otra_clinica, "configuracion.escribir", todas_las_sedes=True
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    cabeceras_ajenas = await cabecera_bearer(cliente, otro_usuario, otra_clinica)

    flujo = "promociones"
    estado_propio = await cliente.get(f"{api}/automatizaciones", headers=cabeceras)
    estado_ajeno = await cliente.get(f"{api}/automatizaciones", headers=cabeceras_ajenas)
    assert estado_propio.status_code == estado_ajeno.status_code == 200
    assert next(item for item in estado_propio.json() if item["codigo"] == flujo)["activo"] is True
    assert next(item for item in estado_ajeno.json() if item["codigo"] == flujo)["activo"] is True

    cambio = await cliente.put(
        f"{api}/automatizaciones/{flujo}",
        json={"activo": False, "motivo": "Pausa exclusiva de esta clínica"},
        headers=cabeceras,
    )
    assert cambio.status_code == 200, cambio.text

    estado_propio = await cliente.get(f"{api}/automatizaciones", headers=cabeceras)
    estado_ajeno = await cliente.get(f"{api}/automatizaciones", headers=cabeceras_ajenas)
    assert next(item for item in estado_propio.json() if item["codigo"] == flujo)["activo"] is False
    assert next(item for item in estado_ajeno.json() if item["codigo"] == flujo)["activo"] is True


async def test_un_flujo_apagado_no_encola(
    sesion: AsyncSession, clinica: Clinica, reloj: RelojFijo
) -> None:
    from app.mensajeria.adaptadores import RegistroCanales  # noqa: PLC0415

    assert await automatizaciones.tipo_permitido(sesion, clinica.id, TipoMensajeOutbox.PROMOCION)
    from app.modulos.organizacion.modelos import ConfiguracionClinica  # noqa: PLC0415

    sesion.add(
        ConfiguracionClinica(
            clinica_id=clinica.id,
            clave="automatizaciones",
            valor={"resumen_diario_profesional": False},
        )
    )
    await sesion.flush()
    assert not await automatizaciones.tipo_permitido(
        sesion, clinica.id, TipoMensajeOutbox.RESUMEN_DIARIO_PROFESIONAL
    )
    # Sin flujo asociado, siempre se permite.
    assert await automatizaciones.tipo_permitido(
        sesion, clinica.id, TipoMensajeOutbox.VERIFICACION_CORREO
    )
    servicio = ServicioOutbox(sesion, reloj, RegistroCanales())
    resultado = await servicio.encolar(
        SolicitudEnvio(
            tipo=TipoMensajeOutbox.RESUMEN_DIARIO_PROFESIONAL,
            canal=CanalOutbox.WHATSAPP,
            destino_tipo="PROFESIONAL",
            destino_id=uuid.uuid4(),
            clave_deduplicacion=f"prueba:{uuid.uuid4().hex[:20]}",
            variables={},
            clinica_id=clinica.id,
        )
    )
    assert resultado is None
