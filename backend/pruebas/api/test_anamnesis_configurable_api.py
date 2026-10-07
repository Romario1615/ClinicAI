"""Diseño, versionado y captura clínica de anamnesis por clínica."""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.modelos import Auditoria
from app.modulos.historia.modelos import PlantillaAnamnesis, RespuestaAnamnesis
from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.pacientes.modelos import Paciente, RelacionAsistencial
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Usuario
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def relacion_asistencial(
    sesion: AsyncSession,
    paciente: Paciente,
    profesional: Profesional,
) -> None:
    sesion.add(
        RelacionAsistencial(
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            origen="ASIGNACION",
        )
    )
    await sesion.flush()


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


def _plantilla(nombre: str = "Historia inicial", *, nivel: str = "N2") -> dict[str, Any]:
    return {
        "nombre": nombre,
        "nivel_sensibilidad": nivel,
        "preguntas": [
            {
                "id": "alergias_conocidas",
                "etiqueta": "¿Qué alergias refiere?",
                "tipo": "texto_largo",
                "obligatoria": True,
                "ayuda": "Registre lo que refiere la persona.",
                "opciones": [],
            },
            {
                "id": "tratamiento_activo",
                "etiqueta": "¿Tiene tratamiento activo?",
                "tipo": "booleano",
                "obligatoria": True,
                "ayuda": None,
                "opciones": [],
            },
            {
                "id": "motivo_visita",
                "etiqueta": "Motivo de la visita",
                "tipo": "seleccion",
                "obligatoria": False,
                "ayuda": None,
                "opciones": ["Control", "Dolor", "Otro"],
            },
            {
                "id": "habitos",
                "etiqueta": "Hábitos relevantes",
                "tipo": "seleccion_multiple",
                "obligatoria": False,
                "ayuda": None,
                "opciones": ["Tabaco", "Alcohol", "Ninguno"],
            },
        ],
    }


async def _crear_y_publicar(
    cliente: AsyncClient,
    api: str,
    cabeceras: dict[str, str],
    *,
    nombre: str = "Historia inicial",
    nivel: str = "N2",
) -> dict[str, Any]:
    creada = await cliente.post(
        f"{api}/historia/anamnesis/plantillas",
        headers=cabeceras,
        json=_plantilla(nombre, nivel=nivel),
    )
    assert creada.status_code == 201, creada.text
    plantilla = creada.json()
    publicada = await cliente.post(
        f"{api}/historia/anamnesis/plantillas/{plantilla['id']}/publicacion",
        headers=cabeceras,
    )
    assert publicada.status_code == 200, publicada.text
    return publicada.json()


async def test_versiones_publicadas_son_inmutables_y_se_reemplazan(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
) -> None:
    cabeceras = await _cabeceras(cliente, sesion, usuario, clinica, sede, "configuracion.escribir")
    primera = await _crear_y_publicar(cliente, api, cabeceras)

    cambio_directo = await cliente.patch(
        f"{api}/historia/anamnesis/plantillas/{primera['id']}",
        headers=cabeceras,
        json=_plantilla("Historia editada"),
    )
    assert cambio_directo.status_code == 409

    nueva = await cliente.post(
        f"{api}/historia/anamnesis/plantillas/{primera['id']}/nueva-version",
        headers=cabeceras,
    )
    assert nueva.status_code == 201, nueva.text
    assert nueva.json()["version"] == 2
    assert nueva.json()["estado"] == "BORRADOR"
    payload = _plantilla()
    payload["preguntas"][0]["etiqueta"] = "Alergias referidas actualmente"
    editada = await cliente.patch(
        f"{api}/historia/anamnesis/plantillas/{nueva.json()['id']}",
        headers=cabeceras,
        json=payload,
    )
    assert editada.status_code == 200, editada.text
    assert editada.json()["preguntas"][0]["etiqueta"] == "Alergias referidas actualmente"

    publicada = await cliente.post(
        f"{api}/historia/anamnesis/plantillas/{nueva.json()['id']}/publicacion",
        headers=cabeceras,
    )
    assert publicada.status_code == 200, publicada.text
    versiones = await sesion.scalars(
        select(PlantillaAnamnesis)
        .where(PlantillaAnamnesis.clinica_id == clinica.id)
        .order_by(PlantillaAnamnesis.version)
    )
    assert [(item.version, item.estado) for item in versiones] == [
        (1, "RETIRADA"),
        (2, "PUBLICADA"),
    ]


async def test_captura_validada_auditada_y_versionada(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
    profesional: Profesional,
    relacion_asistencial: None,
) -> None:
    cabeceras = await _cabeceras(
        cliente,
        sesion,
        usuario,
        clinica,
        sede,
        "configuracion.escribir",
        "historia_clinica.leer",
        "historia_clinica.escribir",
    )
    plantilla = await _crear_y_publicar(cliente, api, cabeceras)
    ruta = f"{api}/historia/pacientes/{paciente.id}/anamnesis"

    activa = await cliente.get(f"{ruta}/plantillas-activas", headers=cabeceras)
    assert activa.status_code == 200, activa.text
    assert [item["id"] for item in activa.json()] == [plantilla["id"]]
    assert activa.json()[0]["preguntas"][0]["etiqueta"] == "¿Qué alergias refiere?"

    invalida = await cliente.post(
        f"{ruta}/respuestas",
        headers=cabeceras,
        json={
            "plantilla_id": plantilla["id"],
            "respuestas": {
                "alergias_conocidas": "Ninguna",
                "tratamiento_activo": "sí",
                "desconocida": "dato",
            },
        },
    )
    assert invalida.status_code == 422

    guardada = await cliente.post(
        f"{ruta}/respuestas",
        headers=cabeceras,
        json={
            "plantilla_id": plantilla["id"],
            "respuestas": {
                "alergias_conocidas": "  Ninguna conocida  ",
                "tratamiento_activo": False,
                "motivo_visita": "Control",
                "habitos": ["Ninguno"],
            },
        },
    )
    assert guardada.status_code == 201, guardada.text
    assert guardada.json()["respuestas"]["alergias_conocidas"] == "Ninguna conocida"
    assert guardada.json()["version_plantilla"] == 1
    assert guardada.json()["respuestas"]["tratamiento_activo"] is False

    historial = await cliente.get(f"{ruta}/respuestas", headers=cabeceras)
    assert historial.status_code == 200, historial.text
    assert len(historial.json()) == 1
    assert historial.json()[0]["preguntas"][0]["etiqueta"] == "¿Qué alergias refiere?"

    n3_headers = await _cabeceras(
        cliente,
        sesion,
        usuario,
        clinica,
        sede,
        "configuracion.escribir",
        "historia_clinica.leer",
        "historia_clinica.escribir",
        "historia_clinica.leer_sensible",
    )
    otra = await _crear_y_publicar(cliente, api, n3_headers, nombre="Datos sensibles", nivel="N3")
    respuesta_n3 = await cliente.post(
        f"{ruta}/respuestas",
        headers=n3_headers,
        json={
            "plantilla_id": otra["id"],
            "respuestas": {"alergias_conocidas": "Dato N3", "tratamiento_activo": True},
        },
    )
    assert respuesta_n3.status_code == 201, respuesta_n3.text
    capturas_db = await sesion.scalars(
        select(RespuestaAnamnesis).where(RespuestaAnamnesis.paciente_id == paciente.id)
    )
    assert len(list(capturas_db)) == 2
    eventos = list(
        await sesion.scalars(
            select(Auditoria).where(
                Auditoria.accion == "anamnesis.registrada",
                Auditoria.paciente_id == paciente.id,
            )
        )
    )
    assert len(eventos) == 2
    assert all("Ninguna conocida" not in str(evento.metadatos) for evento in eventos)
    assert all("Dato N3" not in str(evento.metadatos) for evento in eventos)


async def test_n3_y_relacion_asistencial_se_controlan_en_servidor(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
    profesional: Profesional,
) -> None:
    cabeceras = await _cabeceras(
        cliente,
        sesion,
        usuario,
        clinica,
        sede,
        "configuracion.escribir",
        "historia_clinica.leer",
        "historia_clinica.escribir",
    )
    plantilla = await _crear_y_publicar(cliente, api, cabeceras, nivel="N3")
    ruta = f"{api}/historia/pacientes/{paciente.id}/anamnesis"
    sin_relacion = await cliente.get(f"{ruta}/plantillas-activas", headers=cabeceras)
    assert sin_relacion.status_code == 404

    sesion.add(
        RelacionAsistencial(
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            origen="ASIGNACION",
        )
    )
    await sesion.flush()
    activa = await cliente.get(f"{ruta}/plantillas-activas", headers=cabeceras)
    assert activa.status_code == 200, activa.text
    assert activa.json() == []
    denegada = await cliente.post(
        f"{ruta}/respuestas",
        headers=cabeceras,
        json={
            "plantilla_id": plantilla["id"],
            "respuestas": {"alergias_conocidas": "Dato reservado", "tratamiento_activo": True},
        },
    )
    assert denegada.status_code == 403
