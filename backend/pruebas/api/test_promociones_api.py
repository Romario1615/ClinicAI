"""Pruebas HTTP de las campanas de promociones.

Lo que importa y se comprueba
-----------------------------
* **Consentimiento propio.** Un paciente que solo acepto recordatorios de
  cita no recibe publicidad.
* **Una persona aprueba.** Sin imagen no se aprueba; sin aprobacion no se
  envia; quien solo gestiona no puede aprobar.
* **Sin duplicados.** Un segundo envio de la misma campana se rechaza.
* **Nada sale a la red.** Generador de imagenes y WhatsApp en sandbox.
* Datos sinteticos: telefonos de la serie ficticia y nombres genericos.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.modelos import Auditoria
from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.outbox.modelos import OutboxMensaje
from app.modulos.pacientes.modelos import Consentimiento, Paciente
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.auditoria import AccionAuditada
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]

GESTIONAR = "promocion.gestionar"
APROBAR = "promocion.aprobar"


def _ruta(api: str, sufijo: str = "") -> str:
    return f"{api}/promociones/campanas{sufijo}"


async def _paciente(
    sesion: AsyncSession, clinica: Clinica, *, telefono: str, consentimientos: tuple[str, ...]
) -> Paciente:
    paciente = Paciente(
        clinica_id=clinica.id,
        tipo_documento="CEDULA",
        numero_documento=f"8{uuid.uuid4().int % 10**9:09d}",
        nombre="Persona",
        apellido="Sintetica",
        telefono_whatsapp=telefono,
    )
    sesion.add(paciente)
    await sesion.flush()
    for tipo in consentimientos:
        sesion.add(
            Consentimiento(
                paciente_id=paciente.id,
                tipo=tipo,
                otorgado=True,
                version_texto="v1",
                texto_hash="0" * 64,
                canal="PRESENCIAL",
            )
        )
    await sesion.flush()
    return paciente


@pytest_asyncio.fixture
async def gestor(
    cliente: AsyncClient, sesion: AsyncSession, usuario: Usuario, clinica: Clinica, sede: Sede
) -> dict[str, str]:
    await conceder_permisos(sesion, usuario, clinica, GESTIONAR, APROBAR, sedes=(sede.id,))
    return await cabecera_bearer(cliente, usuario, clinica)


async def _campana(cliente: AsyncClient, api: str, cabeceras: dict[str, str]) -> dict[str, object]:
    respuesta = await cliente.post(
        _ruta(api),
        headers=cabeceras,
        json={
            "nombre": "Limpieza de octubre",
            "texto": "Este mes la limpieza dental tiene 20 % de descuento. Agende por este chat.",
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    cuerpo: dict[str, object] = respuesta.json()
    return cuerpo


async def test_sin_permiso_no_ve_campanas(
    cliente: AsyncClient, api: str, usuario: Usuario, clinica: Clinica
) -> None:
    respuesta = await cliente.get(
        _ruta(api), headers=await cabecera_bearer(cliente, usuario, clinica)
    )
    assert respuesta.status_code == 403


async def test_quien_solo_gestiona_no_aprueba(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
) -> None:
    await conceder_permisos(sesion, usuario, clinica, GESTIONAR, sedes=(sede.id,))
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    campana = await _campana(cliente, api, cabeceras)
    respuesta = await cliente.post(_ruta(api, f"/{campana['id']}/aprobacion"), headers=cabeceras)
    assert respuesta.status_code == 403


async def test_texto_con_llaves_y_prompt_con_cifras_se_rechazan(
    cliente: AsyncClient, api: str, gestor: dict[str, str]
) -> None:
    con_llaves = await cliente.post(
        _ruta(api),
        headers=gestor,
        json={"nombre": "Prueba", "texto": "Hola {nombre_paciente}, tenemos oferta"},
    )
    assert con_llaves.status_code == 422

    campana = await _campana(cliente, api, gestor)
    con_cifras = await cliente.post(
        _ruta(api, f"/{campana['id']}/imagen-generada"),
        headers=gestor,
        json={"descripcion": "Sonrisa luminosa, llame al 0991234567 para agendar"},
    )
    assert con_cifras.status_code == 422


async def test_sin_imagen_no_se_aprueba(
    cliente: AsyncClient, api: str, gestor: dict[str, str]
) -> None:
    campana = await _campana(cliente, api, gestor)
    respuesta = await cliente.post(_ruta(api, f"/{campana['id']}/aprobacion"), headers=gestor)
    assert respuesta.status_code == 409


async def test_ciclo_completo_solo_llega_a_quien_acepto_promociones(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    clinica: Clinica,
    gestor: dict[str, str],
) -> None:
    acepta = await _paciente(
        sesion,
        clinica,
        telefono="+593 99 900 0101",
        consentimientos=("COMUNICACION_WHATSAPP", "PROMOCIONES"),
    )
    solo_recordatorios = await _paciente(
        sesion, clinica, telefono="+593 99 900 0102", consentimientos=("COMUNICACION_WHATSAPP",)
    )
    campana = await _campana(cliente, api, gestor)
    identificador = campana["id"]

    generada = await cliente.post(
        _ruta(api, f"/{identificador}/imagen-generada"),
        headers=gestor,
        json={"descripcion": "Sonrisa luminosa con tonos verde azulado y fondo limpio"},
    )
    assert generada.status_code == 200, generada.text
    assert generada.json()["tiene_imagen"] is True
    assert generada.json()["imagen_origen"] == "GENERADA"
    assert generada.json()["imagen_proveedor"] == "sandbox"

    imagen = await cliente.get(_ruta(api, f"/{identificador}/imagen"), headers=gestor)
    assert imagen.status_code == 200
    assert imagen.headers["content-type"] == "image/png"
    assert imagen.content.startswith(b"\x89PNG")

    audiencia = await cliente.get(_ruta(api, f"/{identificador}/audiencia"), headers=gestor)
    assert audiencia.json() == {"con_consentimiento": 1}

    aprobada = await cliente.post(_ruta(api, f"/{identificador}/aprobacion"), headers=gestor)
    assert aprobada.status_code == 200, aprobada.text
    assert aprobada.json()["estado"] == "APROBADA"

    enviada = await cliente.post(_ruta(api, f"/{identificador}/envio"), headers=gestor, json={})
    assert enviada.status_code == 200, enviada.text
    assert enviada.json()["estado"] == "ENVIADA"
    assert enviada.json()["encolados"] == 1

    mensajes = list(
        (
            await sesion.execute(
                sa.select(OutboxMensaje).where(
                    OutboxMensaje.entidad_origen_id == uuid.UUID(str(identificador))
                )
            )
        )
        .scalars()
        .all()
    )
    assert [m.destino_id for m in mensajes] == [acepta.id]
    assert solo_recordatorios.id not in {m.destino_id for m in mensajes}
    carga = mensajes[0].carga_util
    assert carga["plantilla"] == "promocion_clinica"
    assert str(carga["imagen_cabecera"]).startswith("sandbox-media-")
    assert carga["variables"] == {
        "nombre": "Persona",
        "texto_promocion": campana["texto"],
    }

    otra_vez = await cliente.post(_ruta(api, f"/{identificador}/envio"), headers=gestor, json={})
    assert otra_vez.status_code == 409

    acciones = set((await sesion.execute(sa.select(Auditoria.accion))).scalars())
    assert {
        AccionAuditada.CAMPANA_CREADA.value,
        AccionAuditada.CAMPANA_IMAGEN.value,
        AccionAuditada.CAMPANA_APROBADA.value,
        AccionAuditada.CAMPANA_ENVIADA.value,
    } <= acciones


async def test_campana_de_otra_clinica_responde_404(
    cliente: AsyncClient, api: str, gestor: dict[str, str]
) -> None:
    respuesta = await cliente.get(_ruta(api, f"/{uuid.uuid4()}"), headers=gestor)
    assert respuesta.status_code == 404


async def test_cancelar_borrador_exige_motivo(
    cliente: AsyncClient, api: str, gestor: dict[str, str]
) -> None:
    campana = await _campana(cliente, api, gestor)
    sin_motivo = await cliente.post(
        _ruta(api, f"/{campana['id']}/cancelacion"), headers=gestor, json={"motivo": ""}
    )
    assert sin_motivo.status_code == 422
    cancelada = await cliente.post(
        _ruta(api, f"/{campana['id']}/cancelacion"),
        headers=gestor,
        json={"motivo": "Se pospone la oferta"},
    )
    assert cancelada.status_code == 200
    assert cancelada.json()["estado"] == "CANCELADA"
