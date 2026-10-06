"""Asistente interno: actúa con los permisos de quien escribe y solo crea borradores.

* Agenda y «quién sigue» del propio profesional.
* Resumen de la historia solo con relación asistencial, y se audita.
* No toma decisiones clínicas.
* «Agrega al conocimiento» crea un documento en DRAFT; «crea una promoción»,
  una campaña en borrador. Ninguno queda disponible sin aprobación.
* Sin fuente aprobada lo dice; sin permiso, lo dice; sin sesión, 401.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita
from app.modulos.auditoria.modelos import Auditoria
from app.modulos.conocimiento.modelos import KnowledgeDocument
from app.modulos.organizacion.modelos import Clinica, Sede, Servicio
from app.modulos.pacientes.modelos import Paciente, RelacionAsistencial
from app.modulos.profesionales.modelos import Profesional
from app.modulos.promociones.modelos import CampanaPromocion
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.auditoria import AccionAuditada
from pruebas.api.conftest import cabecera_bearer, conceder_permisos
from pruebas.conftest import INSTANTE_REFERENCIA

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]


async def _decir(
    cliente: AsyncClient, api: str, cabeceras: dict[str, str], texto: str, **extra: str
) -> dict[str, object]:
    respuesta = await cliente.post(
        f"{api}/asistente/mensajes", headers=cabeceras, json={"texto": texto, **extra}
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo: dict[str, object] = respuesta.json()
    return cuerpo


async def test_agenda_siguiente_y_resumen_del_profesional(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    servicio: Servicio,
    profesional: Profesional,
    paciente: Paciente,
) -> None:
    inicio = INSTANTE_REFERENCIA + timedelta(minutes=30)
    sesion.add(
        Cita(
            clinica_id=clinica.id,
            sede_id=sede.id,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            servicio_id=servicio.id,
            inicio=inicio,
            duracion_minutos=30,
            minutos_preparacion=0,
            estado="CONFIRMED",
            origen="PANEL",
            confirmada_en=inicio - timedelta(days=1),
            llegada_en=INSTANTE_REFERENCIA,
        )
    )
    await sesion.flush()
    await conceder_permisos(
        sesion, usuario, clinica, "agenda.leer", "historia_clinica.leer", sedes=(sede.id,)
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    assert (
        await cliente.post(f"{api}/asistente/mensajes", json={"texto": "hola"})
    ).status_code == 401

    agenda = await _decir(cliente, api, cabeceras, "Mi agenda de hoy")
    assert agenda["intencion"] == "AGENDA"
    assert len(agenda["elementos"]) == 1  # type: ignore[arg-type]

    siguiente = await _decir(cliente, api, cabeceras, "¿Quién sigue?")
    assert "ya llegó" in str(siguiente["texto"])

    sin_paciente = await _decir(cliente, api, cabeceras, "Resumen")
    assert "Elija primero el paciente" in str(sin_paciente["texto"])

    sin_relacion = await cliente.post(
        f"{api}/asistente/mensajes",
        headers=cabeceras,
        json={"texto": "Resumen", "paciente_id": str(paciente.id)},
    )
    assert sin_relacion.status_code == 403

    sesion.add(
        RelacionAsistencial(paciente_id=paciente.id, profesional_id=profesional.id, origen="CITA")
    )
    await sesion.flush()
    resumen = await _decir(cliente, api, cabeceras, "Resumen", paciente_id=str(paciente.id))
    titulos = [e["titulo"] for e in resumen["elementos"]]  # type: ignore[union-attr]
    assert titulos[:2] == ["Alergias", "Medicación activa"]
    auditado = (
        await sesion.execute(
            sa.select(sa.func.count()).where(
                Auditoria.accion == AccionAuditada.HISTORIA_CONSULTADA.value,
                Auditoria.paciente_id == paciente.id,
            )
        )
    ).scalar_one()
    assert auditado >= 1

    clinica_respuesta = await _decir(cliente, api, cabeceras, "¿Qué le receto?")
    assert clinica_respuesta["intencion"] == "DECISION_CLINICA"
    assert "decisión clínica" in str(clinica_respuesta["texto"])


async def test_borradores_de_conocimiento_y_promocion(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
) -> None:
    await conceder_permisos(sesion, usuario, clinica, "agenda.leer", sedes=(sede.id,))
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    sin_permiso = await _decir(
        cliente, api, cabeceras, "Agrega al conocimiento: los sábados abrimos a las 8"
    )
    assert "no tiene acceso" in str(sin_permiso["texto"])

    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "conocimiento.leer",
        "conocimiento.cargar",
        "promocion.gestionar",
        sedes=(sede.id,),
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    corto = await _decir(cliente, api, cabeceras, "Agrega al conocimiento: hola")
    assert "después de dos puntos" in str(corto["texto"])

    conocimiento = await _decir(
        cliente,
        api,
        cabeceras,
        "Agrega al conocimiento: los sábados atendemos de 8:00 a 13:00 en la sede norte",
    )
    assert conocimiento["intencion"] == "BORRADOR_CONOCIMIENTO"
    assert conocimiento["enlace"] == "/conocimiento"
    documento = (
        await sesion.execute(
            sa.select(KnowledgeDocument).where(KnowledgeDocument.clinic_id == clinica.id)
        )
    ).scalar_one()
    assert documento.status == "DRAFT"

    promocion = await _decir(
        cliente, api, cabeceras, "Crea una promoción: limpieza dental con 20 % de descuento"
    )
    assert promocion["intencion"] == "BORRADOR_PROMOCION"
    campana = (
        await sesion.execute(
            sa.select(CampanaPromocion).where(CampanaPromocion.clinica_id == clinica.id)
        )
    ).scalar_one()
    assert campana.estado == "BORRADOR"

    # El borrador no responde preguntas: no hay fuente aprobada.
    pregunta = await _decir(cliente, api, cabeceras, "¿A qué hora abren los sábados?")
    assert pregunta["intencion"] == "PREGUNTA"
    assert "No hay información aprobada" in str(pregunta["texto"])

    sugerencias = await cliente.get(f"{api}/asistente/sugerencias", headers=cabeceras)
    assert "Crea una promoción: …" in sugerencias.json()
