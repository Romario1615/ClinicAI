"""Un documento Word (.docx) se carga por la misma ruta que un PDF."""

from __future__ import annotations

import zipfile
from io import BytesIO

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.usuarios.modelos import Usuario
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.rag, pytest.mark.asyncio]

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _docx(*parrafos: str) -> bytes:
    cuerpo = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in parrafos)
    salida = BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as paquete:
        paquete.writestr("[Content_Types].xml", "<Types/>")
        paquete.writestr(
            "word/document.xml",
            f'<w:document xmlns:w="{W}"><w:body>{cuerpo}</w:body></w:document>',
        )
    return salida.getvalue()


async def test_un_docx_se_ingiere_como_texto(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
) -> None:
    await conceder_permisos(
        sesion, usuario, clinica, "conocimiento.leer", "conocimiento.cargar", sedes=(sede.id,)
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    creado = await cliente.post(
        f"{api}/conocimiento/documentos",
        json={"titulo": "Protocolo en Word", "tipo": "PROTOCOLO"},
        headers=cabeceras,
    )
    assert creado.status_code == 201, creado.text

    respuesta = await cliente.post(
        f"{api}/conocimiento/documentos/{creado.json()['id']}/versiones/archivo",
        files={
            "archivo": (
                "protocolo.docx",
                _docx("Protocolo sintético de esterilización.", "Paso uno: lavar."),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        headers=cabeceras,
    )
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["fragmentos"] >= 1

    rechazado = await cliente.post(
        f"{api}/conocimiento/documentos/{creado.json()['id']}/versiones/archivo",
        files={"archivo": ("notas.txt", b"solo texto", "text/plain")},
        headers=cabeceras,
    )
    assert rechazado.status_code in {400, 415, 422}, rechazado.text
