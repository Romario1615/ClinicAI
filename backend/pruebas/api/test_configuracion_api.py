"""Pruebas del almacenamiento seguro de credenciales por clínica."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.modelos import Auditoria
from app.modulos.organizacion.modelos import Clinica, ConfiguracionClinica
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.auditoria import AccionAuditada
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]


@pytest.fixture
def ruta(api: str) -> str:
    return f"{api}/configuracion/integraciones"


async def test_clave_se_cifra_no_se_devuelve_y_no_se_copia_al_historial(
    cliente: AsyncClient,
    api: str,
    ruta: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    aplicacion,
) -> None:
    await conceder_permisos(sesion, usuario, clinica, "configuracion.escribir")
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    secreto = "sk-ant-clave-sintetica-de-prueba-que-no-debe-filtrarse"
    payload = {
        "habilitada": True,
        "ajustes": {"modelo": "claude-sonnet-5", "max_tokens": 1024},
        "secretos": {"api_key": secreto},
    }

    respuesta = await cliente.put(f"{ruta}/anthropic", json=payload, headers=cabeceras)

    assert respuesta.status_code == 200, respuesta.text
    assert secreto not in respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["habilitada"] is True
    assert cuerpo["secretos"]["api_key"]["configurado"] is True
    assert cuerpo["ajustes"]["max_tokens"] == 1024

    fila = (
        await sesion.execute(
            sa.select(ConfiguracionClinica).where(
                ConfiguracionClinica.clinica_id == clinica.id,
                ConfiguracionClinica.clave == "integracion.anthropic",
                ConfiguracionClinica.vigente.is_(True),
            )
        )
    ).scalar_one()
    cifrado = fila.valor["secretos_cifrados"]["api_key"]
    assert cifrado != secreto
    descifrado = aplicacion.state.cifrador.descifrar(
        cifrado,
        contexto=b"integracion:" + clinica.id.bytes + b":anthropic:api_key",
    )
    assert descifrado == secreto

    auditoria = (
        (
            await sesion.execute(
                sa.select(Auditoria).where(
                    Auditoria.accion == AccionAuditada.INTEGRACION_CONFIGURADA
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(auditoria) == 1
    assert secreto not in str(auditoria[0].metadatos)

    reemplazo = "sk-ant-otra-clave-sintetica-de-rotacion"
    respuesta_reemplazo = await cliente.put(
        f"{ruta}/anthropic",
        json={"habilitada": False, "secretos": {"api_key": reemplazo}},
        headers=cabeceras,
    )
    assert respuesta_reemplazo.status_code == 200, respuesta_reemplazo.text
    assert reemplazo not in respuesta_reemplazo.text
    historial = (
        (
            await sesion.execute(
                sa.select(ConfiguracionClinica).where(
                    ConfiguracionClinica.clinica_id == clinica.id,
                    ConfiguracionClinica.clave == "integracion.anthropic",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(historial) == 2
    assert historial[0].vigente is False
    assert "secretos_cifrados" not in historial[0].valor
    assert historial[1].valor["secretos_cifrados"]["api_key"] != reemplazo


async def test_no_habilita_anthropic_si_no_hay_clave_guardada(
    cliente: AsyncClient,
    ruta: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
) -> None:
    await conceder_permisos(sesion, usuario, clinica, "configuracion.escribir")
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    respuesta = await cliente.put(f"{ruta}/anthropic", json={"habilitada": True}, headers=cabeceras)

    assert respuesta.status_code == 422
    assert "Guarde la clave API" in respuesta.json()["mensaje"]
    guardada = await sesion.scalar(
        sa.select(sa.func.count())
        .select_from(ConfiguracionClinica)
        .where(ConfiguracionClinica.clave == "integracion.anthropic")
    )
    assert guardada == 0


async def test_integraciones_exigen_permiso_de_configuracion(
    cliente: AsyncClient,
    ruta: str,
    usuario: Usuario,
    clinica: Clinica,
) -> None:
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    lectura = await cliente.get(ruta, headers=cabeceras)
    escritura = await cliente.put(
        f"{ruta}/anthropic",
        json={"habilitada": False},
        headers=cabeceras,
    )

    assert lectura.status_code == escritura.status_code == 403


async def test_no_se_aceptan_campos_secretos_ni_ajustes_desconocidos(
    cliente: AsyncClient,
    ruta: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
) -> None:
    await conceder_permisos(sesion, usuario, clinica, "configuracion.escribir")
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    secreto_desconocido = await cliente.put(
        f"{ruta}/anthropic",
        json={"habilitada": False, "secretos": {"clave_global": "secreto"}},
        headers=cabeceras,
    )
    ajuste_desconocido = await cliente.put(
        f"{ruta}/anthropic",
        json={"habilitada": False, "ajustes": {"url_arbitraria": "https://evil.invalid"}},
        headers=cabeceras,
    )

    assert secreto_desconocido.status_code == ajuste_desconocido.status_code == 422


async def test_get_muestra_estado_sin_revelar_valores_de_credenciales(
    cliente: AsyncClient,
    ruta: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
) -> None:
    await conceder_permisos(sesion, usuario, clinica, "configuracion.escribir")
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    respuesta = await cliente.get(ruta, headers=cabeceras)

    assert respuesta.status_code == 200
    integraciones = {fila["codigo"]: fila for fila in respuesta.json()}
    assert set(integraciones) == {"anthropic", "whatsapp", "google_calendar", "smtp"}
    assert integraciones["anthropic"]["habilitada"] is False
    assert integraciones["anthropic"]["secretos"]["api_key"]["configurado"] is False
    assert "valor" not in respuesta.text
