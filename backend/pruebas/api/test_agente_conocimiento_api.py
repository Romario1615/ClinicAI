"""El agente responde preguntas de información con documentos publicados.

Un documento publicado responde; uno en borrador no, aunque diga exactamente
lo que se pregunta. Sin fuente, el agente lo dice en lugar de improvisar.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.conocimiento.modelos import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgePermission,
)
from app.modulos.organizacion.modelos import Clinica, Sede, Servicio
from app.modulos.pacientes.modelos import Paciente
from app.modulos.profesionales.modelos import Profesional, ProfesionalSede
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.reloj import RelojFijo
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.rag, pytest.mark.asyncio]

PERMISOS = (
    "agenda.leer",
    "cita.crear",
    "conversacion.responder",
    "conocimiento.leer",
    "conocimiento.cargar",
)


async def test_agente_cita_lo_publicado_y_no_el_borrador(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    servicio: Servicio,
    profesional: Profesional,
    paciente: Paciente,
    reloj: RelojFijo,
) -> None:
    await conceder_permisos(sesion, usuario, clinica, *PERMISOS, sedes=(sede.id,))
    sesion.add(ProfesionalSede(profesional_id=profesional.id, sede_id=sede.id))
    await sesion.flush()
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    abierta = await cliente.post(
        f"{api}/agente-demo/sesiones",
        json={
            "paciente_id": str(paciente.id),
            "sede_id": str(sede.id),
            "servicio_id": str(servicio.id),
            "profesional_id": str(profesional.id),
            "desde": (reloj.ahora() + timedelta(days=2)).isoformat(),
            "hasta": (reloj.ahora() + timedelta(days=3)).isoformat(),
        },
        headers={**cabeceras, "Idempotency-Key": "agente-conocimiento-0"},
    )
    assert abierta.status_code == 201, abierta.text
    ruta = f"{api}/agente-demo/sesiones/{abierta.json()['sesion_id']}/mensajes"

    async def preguntar(clave: str) -> dict[str, object]:
        respuesta = await cliente.post(
            ruta,
            json={"texto": "¿A qué hora atienden los sábados?"},
            headers={**cabeceras, "Idempotency-Key": clave},
        )
        assert respuesta.status_code == 200, respuesta.text
        cuerpo: dict[str, object] = respuesta.json()
        return cuerpo

    # Borrador: no responde.
    documento = await cliente.post(
        f"{api}/conocimiento/documentos",
        json={"titulo": "Horario de sabados", "tipo": "PREGUNTA_FRECUENTE", "sensibilidad": "N1"},
        headers=cabeceras,
    )
    assert documento.status_code == 201, documento.text
    doc_id = documento.json()["id"]
    version = await cliente.post(
        f"{api}/conocimiento/documentos/{doc_id}/versiones",
        json={"contenido": "Los sabados atendemos de 8:00 a 13:00. Los domingos no hay atencion."},
        headers=cabeceras,
    )
    assert version.status_code == 201, version.text
    sin_publicar = await preguntar("agente-conocimiento-1")
    assert "No tengo informacion aprobada" in str(sin_publicar["mensaje"])

    # Publicado (aprobarlo exige otra persona; aquí se publica directamente).
    fila = await sesion.get(KnowledgeDocument, uuid.UUID(doc_id))
    assert fila is not None
    fila.status = "PUBLISHED"
    fila.version_vigente = 1
    fila.aprobado_por = usuario.id
    fila.aprobado_en = reloj.ahora()
    await sesion.execute(
        sa.update(KnowledgeChunk)
        .where(KnowledgeChunk.document_id == fila.id)
        .values(status="PUBLISHED")
    )
    # Y su ACL lo habilita para el agente (pestaña «Accesos» en Conocimiento).
    sesion.add(
        KnowledgePermission(
            document_id=fila.id,
            principal_tipo="SEDE",
            principal_id=sede.id,
            puede_leer=True,
            puede_usar_en_agente=True,
        )
    )
    await sesion.flush()
    publicado = await preguntar("agente-conocimiento-2")
    assert "Horario de sabados" in str(publicado["mensaje"])
    assert "8:00 a 13:00" in str(publicado["mensaje"])
