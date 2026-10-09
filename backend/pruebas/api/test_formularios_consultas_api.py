"""Entradas limite, persistencia y paginacion de formularios administrativos."""

import uuid

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.organizacion.modelos import Clinica, Especialidad, Servicio
from app.modulos.pacientes.modelos import Paciente
from app.modulos.usuarios.modelos import Usuario
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


@pytest.mark.parametrize(
    "cambio",
    [
        {"nombre": "   "},
        {"nombre": "x" * 201},
        {"duracion_minutos": 0},
        {"duracion_minutos": 1441},
        {"duracion_minutos": 1.5},
        {"minutos_preparacion": -1},
        {"minutos_preparacion": 1441},
        {"precio": "-0.01"},
        {"precio": "1.234"},
        {"precio": "NaN"},
        {"precio": "Infinity"},
        {"moneda": "US"},
        {"moneda": "U1D"},
        {"tipo_consultorio_requerido": "INEXISTENTE"},
    ],
)
async def test_servicio_invalido_no_persiste(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    especialidad: Especialidad,
    cambio: dict,
) -> None:
    await conceder_permisos(sesion, usuario, clinica, "servicio.gestionar", todas_las_sedes=True)
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    datos = {
        "especialidad_id": str(especialidad.id),
        "nombre": "Servicio sintético",
        "duracion_minutos": 30,
        "minutos_preparacion": 0,
        "precio": "12.34",
        "moneda": "USD",
    }
    consulta = (
        sa.select(sa.func.count()).select_from(Servicio).where(Servicio.clinica_id == clinica.id)
    )
    antes = (await sesion.execute(consulta)).scalar_one()
    respuesta = await cliente.post(
        f"{api}/catalogo/servicios", headers=cabeceras, json=datos | cambio
    )
    assert respuesta.status_code == 422, respuesta.text
    assert (await sesion.execute(consulta)).scalar_one() == antes


@pytest.mark.parametrize(
    "cambio",
    [
        {"nombre": "   "},
        {"apellido": ""},
        {"correo": "sin-arroba"},
        {"telefono_whatsapp": "telefono"},
        {"fecha_nacimiento": "2026-02-30"},
        {"tipo_documento": "CEDULA", "numero_documento": None},
        {"tipo_documento": "SIN_DOCUMENTO", "numero_documento": "12345"},
        {"nombre": "x" * 101},
        {"nivel_verificacion": "DOCUMENTO_VALIDADO"},
    ],
)
async def test_paciente_invalido_no_crea_ficha(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    cambio: dict,
) -> None:
    await conceder_permisos(sesion, usuario, clinica, "paciente.crear")
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    cabeceras["Idempotency-Key"] = str(uuid.uuid4())
    datos = {"nombre": "Paciente", "apellido": "Sintético", "tipo_documento": "SIN_DOCUMENTO"}
    consulta = (
        sa.select(sa.func.count()).select_from(Paciente).where(Paciente.clinica_id == clinica.id)
    )
    antes = (await sesion.execute(consulta)).scalar_one()
    respuesta = await cliente.post(f"{api}/pacientes/", headers=cabeceras, json=datos | cambio)
    assert respuesta.status_code == 422, respuesta.text
    assert (await sesion.execute(consulta)).scalar_one() == antes


async def test_paciente_guardado_se_consulta_y_edicion_invalida_conserva_ficha(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
) -> None:
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "paciente.crear",
        "paciente.editar",
        "paciente.leer_administrativo",
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    cabeceras["Idempotency-Key"] = str(uuid.uuid4())
    datos = {
        "nombre": "  Ficha  ",
        "apellido": "  Sintética  ",
        "tipo_documento": "SIN_DOCUMENTO",
        "correo": "ficha@example.invalid",
    }
    creada = await cliente.post(f"{api}/pacientes/", headers=cabeceras, json=datos)
    assert creada.status_code == 201, creada.text
    paciente_id = creada.json()["id"]
    repetida = await cliente.post(f"{api}/pacientes/", headers=cabeceras, json=datos)
    assert repetida.status_code == 201
    assert repetida.json()["id"] == paciente_id
    consultada = await cliente.get(f"{api}/pacientes/{paciente_id}", headers=cabeceras)
    assert consultada.status_code == 200
    assert consultada.json()["nombre"] == "Ficha"
    assert consultada.json()["correo"] == datos["correo"]
    cabeceras["Idempotency-Key"] = str(uuid.uuid4())
    rechazo = await cliente.put(
        f"{api}/pacientes/{paciente_id}", headers=cabeceras, json=datos | {"correo": "inválido"}
    )
    assert rechazo.status_code == 422
    posterior = await cliente.get(f"{api}/pacientes/{paciente_id}", headers=cabeceras)
    assert posterior.json() == consultada.json()


async def test_paginar_busqueda_sin_repetir_ni_incluir_otra_clinica(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    paciente_ajeno: Paciente,
) -> None:
    prefijo = "Paginacion" + uuid.uuid4().hex[:8]
    propios = [
        Paciente(
            clinica_id=clinica.id,
            nombre=prefijo,
            apellido=f"Sintético {n}",
            tipo_documento="SIN_DOCUMENTO",
        )
        for n in range(7)
    ]
    paciente_ajeno.nombre = prefijo
    paciente_ajeno.apellido = "Ajeno"
    sesion.add_all(propios)
    await sesion.flush()
    await conceder_permisos(sesion, usuario, clinica, "paciente.leer_administrativo")
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    recibidos: list[str] = []
    for desplazamiento in range(0, 9, 3):
        pagina = await cliente.get(
            f"{api}/pacientes/",
            headers=cabeceras,
            params={"termino": prefijo, "limite": 3, "desplazamiento": desplazamiento},
        )
        assert pagina.status_code == 200
        cuerpo = pagina.json()
        assert cuerpo["total"] == 7
        assert cuerpo["desplazamiento"] == desplazamiento
        recibidos.extend(fila["id"] for fila in cuerpo["elementos"])
    assert len(recibidos) == len(set(recibidos)) == 7
    assert set(recibidos) == {str(p.id) for p in propios}
    vacia = await cliente.get(
        f"{api}/pacientes/",
        headers=cabeceras,
        params={"termino": prefijo, "limite": 3, "desplazamiento": 9},
    )
    assert vacia.json()["total"] == 7 and vacia.json()["elementos"] == []


@pytest.mark.parametrize(
    "parametros", [{"limite": 0}, {"limite": 101}, {"desplazamiento": -1}, {"limite": "texto"}]
)
async def test_limites_de_consulta_invalidos(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    parametros: dict,
) -> None:
    await conceder_permisos(sesion, usuario, clinica, "paciente.leer_administrativo")
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    respuesta = await cliente.get(f"{api}/pacientes/", headers=cabeceras, params=parametros)
    assert respuesta.status_code == 422
