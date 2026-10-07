"""Consentimientos de comunicación desde el panel.

* El registro guarda versión y **hash del texto exacto**.
* Sin confirmar la lectura, o con un texto viejo, no se registra.
* Revocar no borra: deja `revocado_en`. Después se puede volver a otorgar.
* Sin `consentimiento.gestionar` no se registra; paciente ajeno → 404.
* Con consentimiento de promociones, la campaña ya cuenta al paciente.
"""

from __future__ import annotations

import hashlib
import uuid

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.modelos import Auditoria
from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.pacientes.consentimientos import TEXTOS
from app.modulos.pacientes.modelos import Consentimiento, Paciente, TipoConsentimiento
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.auditoria import AccionAuditada
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]

VERSION = TEXTOS[TipoConsentimiento.PROMOCIONES].version


async def _cabeceras(
    cliente: AsyncClient,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    *permisos: str,
) -> dict[str, str]:
    await conceder_permisos(sesion, usuario, clinica, *permisos, sedes=(sede.id,))
    return await cabecera_bearer(cliente, usuario, clinica)


async def test_otorgar_revocar_y_volver_a_otorgar(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
) -> None:
    cabeceras = await _cabeceras(
        cliente,
        sesion,
        usuario,
        clinica,
        sede,
        "paciente.leer_administrativo",
        "consentimiento.gestionar",
    )
    ruta = f"{api}/pacientes/{paciente.id}/consentimientos"

    textos = await cliente.get(f"{api}/pacientes/consentimientos/textos", headers=cabeceras)
    assert {t["tipo"] for t in textos.json()} == {
        "COMUNICACION_WHATSAPP",
        "RECORDATORIOS_MEDICACION",
        "PROMOCIONES",
        "DOCUMENTOS_WHATSAPP",
    }

    sin_confirmar = await cliente.post(
        ruta,
        headers=cabeceras,
        json={"tipo": "PROMOCIONES", "version_texto": VERSION, "confirmo_lectura": False},
    )
    assert sin_confirmar.status_code == 422

    viejo = await cliente.post(
        ruta,
        headers=cabeceras,
        json={"tipo": "PROMOCIONES", "version_texto": "2020-v0", "confirmo_lectura": True},
    )
    assert viejo.status_code == 409

    otorgado = await cliente.post(
        ruta,
        headers=cabeceras,
        json={"tipo": "PROMOCIONES", "version_texto": VERSION, "confirmo_lectura": True},
    )
    assert otorgado.status_code == 201, otorgado.text
    assert otorgado.json()["vigente"] is True

    fila = (
        await sesion.execute(
            sa.select(Consentimiento).where(
                Consentimiento.paciente_id == paciente.id,
                Consentimiento.tipo == "PROMOCIONES",
            )
        )
    ).scalar_one()
    esperado = hashlib.sha256(
        TEXTOS[TipoConsentimiento.PROMOCIONES].texto.encode("utf-8")
    ).hexdigest()
    assert fila.texto_hash == esperado

    repetido = await cliente.post(
        ruta,
        headers=cabeceras,
        json={"tipo": "PROMOCIONES", "version_texto": VERSION, "confirmo_lectura": True},
    )
    assert repetido.status_code == 409

    revocado = await cliente.post(f"{ruta}/PROMOCIONES/revocacion", headers=cabeceras)
    assert revocado.status_code == 200
    assert revocado.json()["vigente"] is False

    de_nuevo = await cliente.post(
        ruta,
        headers=cabeceras,
        json={"tipo": "PROMOCIONES", "version_texto": VERSION, "confirmo_lectura": True},
    )
    assert de_nuevo.status_code == 201

    total = await sesion.scalar(
        sa.select(sa.func.count())
        .select_from(Consentimiento)
        .where(Consentimiento.paciente_id == paciente.id)
    )
    assert total == 2  # la revocada se conserva

    estado = await cliente.get(ruta, headers=cabeceras)
    promo = next(c for c in estado.json() if c["tipo"] == "PROMOCIONES")
    assert promo["vigente"] is True

    acciones = set((await sesion.execute(sa.select(Auditoria.accion))).scalars())
    assert {
        AccionAuditada.CONSENTIMIENTO_OTORGADO.value,
        AccionAuditada.CONSENTIMIENTO_REVOCADO.value,
    } <= acciones


async def test_sin_permiso_de_gestion_no_registra(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
) -> None:
    cabeceras = await _cabeceras(
        cliente, sesion, usuario, clinica, sede, "paciente.leer_administrativo"
    )
    respuesta = await cliente.post(
        f"{api}/pacientes/{paciente.id}/consentimientos",
        headers=cabeceras,
        json={"tipo": "PROMOCIONES", "version_texto": VERSION, "confirmo_lectura": True},
    )
    assert respuesta.status_code == 403


async def test_paciente_ajeno_responde_404(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
) -> None:
    cabeceras = await _cabeceras(
        cliente,
        sesion,
        usuario,
        clinica,
        sede,
        "paciente.leer_administrativo",
        "consentimiento.gestionar",
    )
    respuesta = await cliente.get(
        f"{api}/pacientes/{uuid.uuid4()}/consentimientos", headers=cabeceras
    )
    assert respuesta.status_code == 404
