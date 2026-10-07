"""Indicaciones postconsulta: publicar con aviso genérico, leer con identidad
verificada, bloqueo tras intentos fallidos, caducidad y anulación."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.historia.modelos import Receta, RecetaMedicamento
from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.outbox.modelos import OutboxMensaje
from app.modulos.pacientes.modelos import Consentimiento, Paciente, RelacionAsistencial
from app.modulos.postconsulta.modelos import IndicacionPostconsulta
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.reloj import RelojFijo
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]

NACIMIENTO = date(1990, 4, 12)


@pytest_asyncio.fixture
async def cabeceras_profesional(
    cliente: AsyncClient,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
    profesional: Profesional,
) -> dict[str, str]:
    paciente.fecha_nacimiento = NACIMIENTO
    sesion.add(
        RelacionAsistencial(paciente_id=paciente.id, profesional_id=profesional.id, origen="CITA")
    )
    await sesion.flush()
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "historia_clinica.leer",
        "historia_clinica.escribir",
        sedes=(sede.id,),
    )
    return await cabecera_bearer(cliente, usuario, clinica)


async def _receta(
    sesion: AsyncSession,
    clinica: Clinica,
    paciente: Paciente,
    profesional: Profesional,
    reloj: RelojFijo,
) -> Receta:
    receta = Receta(
        clinica_id=clinica.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        estado="BORRADOR",
    )
    sesion.add(receta)
    await sesion.flush()
    sesion.add(
        RecetaMedicamento(
            receta_id=receta.id,
            nombre="Medicamento sintético",
            dosis="1 unidad",
            via="ORAL",
            frecuencia_horas=8,
            duracion_dias=5,
        )
    )
    await sesion.flush()
    receta.estado = "CONFIRMADA"
    receta.confirmada_en = reloj.ahora()
    receta.confirmada_por = profesional.id
    await sesion.flush()
    return receta


async def test_publica_avisa_sin_datos_clinicos_y_el_paciente_lee_con_su_fecha(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    clinica: Clinica,
    paciente: Paciente,
    profesional: Profesional,
    reloj: RelojFijo,
    cabeceras_profesional: dict[str, str],
) -> None:
    sesion.add(
        Consentimiento(
            paciente_id=paciente.id,
            tipo="COMUNICACION_WHATSAPP",
            otorgado=True,
            version_texto="v1",
            texto_hash="0" * 64,
            canal="PRESENCIAL",
        )
    )
    await sesion.flush()
    receta = await _receta(sesion, clinica, paciente, profesional, reloj)
    respuesta = await cliente.post(
        f"{api}/historia/pacientes/{paciente.id}/indicaciones",
        json={
            "texto": "Reposo relativo dos días y control en una semana.",
            "receta_id": str(receta.id),
        },
        headers=cabeceras_profesional,
    )
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["aviso_enviado"] is True
    token = cuerpo["enlace"].rsplit("/", 1)[1]

    mensaje = (
        await sesion.execute(
            sa.select(OutboxMensaje).where(
                OutboxMensaje.tipo == "INDICACIONES_DISPONIBLES",
                OutboxMensaje.entidad_origen_tipo == "indicacion_postconsulta",
                OutboxMensaje.entidad_origen_id == cuerpo["id"],
            )
        )
    ).scalar_one()
    texto = str(mensaje.carga_util["texto"])
    assert "Medicamento sintético" not in texto
    assert "Reposo" not in texto
    assert token in texto

    fila = await sesion.get(IndicacionPostconsulta, cuerpo["id"])
    assert fila is not None and fila.token_hash != token

    mal = await cliente.post(
        f"{api}/publico/indicaciones/{token}/acceso", json={"fecha_nacimiento": "2000-01-01"}
    )
    assert mal.status_code == 401
    assert mal.json()["detalles"]["intentos_restantes"] == 4

    bien = await cliente.post(
        f"{api}/publico/indicaciones/{token}/acceso",
        json={"fecha_nacimiento": NACIMIENTO.isoformat()},
    )
    assert bien.status_code == 200, bien.text
    leida = bien.json()
    assert leida["texto"].startswith("Reposo")
    assert leida["medicamentos"][0]["nombre"] == "Medicamento sintético"
    assert leida["nombre_paciente"] == paciente.nombre

    listado = await cliente.get(
        f"{api}/historia/pacientes/{paciente.id}/indicaciones", headers=cabeceras_profesional
    )
    assert listado.json()[0]["lecturas"] == 1

    anulada = await cliente.patch(
        f"{api}/historia/indicaciones/{cuerpo['id']}/anulacion",
        json={"motivo": "Se corrigió la indicación"},
        headers=cabeceras_profesional,
    )
    assert anulada.status_code == 200
    despues = await cliente.post(
        f"{api}/publico/indicaciones/{token}/acceso",
        json={"fecha_nacimiento": NACIMIENTO.isoformat()},
    )
    assert despues.status_code == 404


async def test_sin_consentimiento_se_guarda_y_lo_dice(
    cliente: AsyncClient, api: str, paciente: Paciente, cabeceras_profesional: dict[str, str]
) -> None:
    respuesta = await cliente.post(
        f"{api}/historia/pacientes/{paciente.id}/indicaciones",
        json={"texto": "Aplicar frío local veinte minutos."},
        headers=cabeceras_profesional,
    )
    assert respuesta.status_code == 201
    assert respuesta.json()["aviso_enviado"] is False
    assert "en mano" in respuesta.json()["motivo_sin_aviso"]


async def test_cinco_intentos_bloquean_y_un_enlace_caducado_no_abre(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    paciente: Paciente,
    reloj: RelojFijo,
    cabeceras_profesional: dict[str, str],
) -> None:
    creada = (
        await cliente.post(
            f"{api}/historia/pacientes/{paciente.id}/indicaciones",
            json={"texto": "Control de herida en tres días.", "dias_validez": 1},
            headers=cabeceras_profesional,
        )
    ).json()
    token = creada["enlace"].rsplit("/", 1)[1]
    for _ in range(5):
        await cliente.post(
            f"{api}/publico/indicaciones/{token}/acceso", json={"fecha_nacimiento": "2001-02-03"}
        )
    bloqueada = await cliente.post(
        f"{api}/publico/indicaciones/{token}/acceso",
        json={"fecha_nacimiento": NACIMIENTO.isoformat()},
    )
    assert bloqueada.status_code == 409
    assert bloqueada.json()["codigo"] == "ENLACE_BLOQUEADO"

    otra = (
        await cliente.post(
            f"{api}/historia/pacientes/{paciente.id}/indicaciones",
            json={"texto": "Indicación que caduca pronto."},
            headers=cabeceras_profesional,
        )
    ).json()
    fila = await sesion.get(IndicacionPostconsulta, otra["id"])
    assert fila is not None
    fila.expira_en = reloj.ahora() - timedelta(minutes=1)
    await sesion.flush()
    token_otra = otra["enlace"].rsplit("/", 1)[1]
    caducada = await cliente.post(
        f"{api}/publico/indicaciones/{token_otra}/acceso",
        json={"fecha_nacimiento": NACIMIENTO.isoformat()},
    )
    assert caducada.status_code == 404
    inexistente = await cliente.post(
        f"{api}/publico/indicaciones/{'x' * 43}/acceso",
        json={"fecha_nacimiento": NACIMIENTO.isoformat()},
    )
    assert inexistente.status_code == 404
    vacia = await cliente.post(f"{api}/publico/indicaciones/{token_otra}/acceso", json={})
    assert vacia.status_code == 422


async def test_sin_permiso_de_escritura_no_publica(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
) -> None:
    await conceder_permisos(sesion, usuario, clinica, "historia_clinica.leer", sedes=(sede.id,))
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    respuesta = await cliente.post(
        f"{api}/historia/pacientes/{paciente.id}/indicaciones",
        json={"texto": "Texto de indicación de prueba."},
        headers=cabeceras,
    )
    assert respuesta.status_code == 403
