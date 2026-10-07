"""Contrato HTTP del ciclo de imágenes, permisos y auditoría."""

from __future__ import annotations

import struct
import uuid
import zlib

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.modelos import Auditoria
from app.modulos.imagenes.modelos import ImagenPaciente
from app.modulos.odontologia.modelos import PlanTratamiento, ProcedimientoPlan
from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.pacientes.modelos import Paciente, RelacionAsistencial
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.auditoria import AccionAuditada
from app.nucleo.seguridad import hashear_contrasena
from pruebas.api.conftest import CONTRASENA, cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]

PERMISOS_IMAGENES = (
    "imagen_clinica.leer",
    "imagen_clinica.cargar",
    "paciente.leer_administrativo",
    "paciente.editar",
)


def _trozo(tipo: bytes, contenido: bytes) -> bytes:
    cuerpo = tipo + contenido
    return struct.pack(">I", len(contenido)) + cuerpo + struct.pack(">I", zlib.crc32(cuerpo))


def _png_sintetico() -> bytes:
    cabecera = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    pixeles = zlib.compress(b"\x00\x21\x43\x65\xff")
    return (
        b"\x89PNG\r\n\x1a\n"
        + _trozo(b"IHDR", cabecera)
        + _trozo(b"IDAT", pixeles)
        + _trozo(b"IEND", b"")
    )


def _ruta(api: str, paciente_id: str) -> str:
    return f"{api}/pacientes/{paciente_id}/imagenes"


@pytest_asyncio.fixture
async def relacion_imagen(
    sesion: AsyncSession, paciente: Paciente, profesional: Profesional
) -> RelacionAsistencial:
    relacion = RelacionAsistencial(
        paciente_id=paciente.id, profesional_id=profesional.id, origen="CITA"
    )
    sesion.add(relacion)
    await sesion.flush()
    return relacion


@pytest_asyncio.fixture
async def cabeceras_imagenes(
    cliente: AsyncClient,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    profesional: Profesional,
) -> dict[str, str]:
    await conceder_permisos(sesion, usuario, clinica, *PERMISOS_IMAGENES, sedes=(sede.id,))
    return await cabecera_bearer(cliente, usuario, clinica)


async def test_ciclo_clinico_filtra_descarga_audita_y_anula(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    cabeceras_imagenes: dict[str, str],
    relacion_imagen: RelacionAsistencial,
    paciente: Paciente,
) -> None:
    ruta = _ruta(api, str(paciente.id))
    carga = await cliente.post(
        ruta,
        headers=cabeceras_imagenes,
        data={"tipo": "FOTO_INTRAORAL", "piezas": "36", "descripcion": "Vista oclusal"},
        files={"archivo": ("imagen.png", _png_sintetico(), "image/png")},
    )
    assert carga.status_code == 201, carga.text
    imagen = carga.json()
    assert imagen["tipo"] == "FOTO_INTRAORAL"
    assert imagen["piezas"] == [36]
    assert imagen["antivirus"] == "NO_DISPONIBLE"

    listado = await cliente.get(f"{ruta}?pieza=36", headers=cabeceras_imagenes)
    assert listado.status_code == 200
    assert [fila["id"] for fila in listado.json()] == [imagen["id"]]

    descarga = await cliente.get(imagen["url_contenido"], headers=cabeceras_imagenes)
    assert descarga.status_code == 200
    assert descarga.headers["content-type"] == "image/png"
    assert descarga.headers["cache-control"] == "private, no-store"
    assert descarga.content == _png_sintetico()

    anulacion = await cliente.patch(
        f"{api}/imagenes/{imagen['id']}/anulacion",
        headers=cabeceras_imagenes,
        json={"motivo": "Se cargó la imagen equivocada"},
    )
    assert anulacion.status_code == 200, anulacion.text
    assert anulacion.json()["id"] == imagen["id"]
    assert (await cliente.get(ruta, headers=cabeceras_imagenes)).json() == []
    retirada = await cliente.get(imagen["url_contenido"], headers=cabeceras_imagenes)
    assert retirada.status_code == 404

    acciones = set((await sesion.execute(sa.select(Auditoria.accion))).scalars())
    assert {
        AccionAuditada.IMAGEN_CARGADA.value,
        AccionAuditada.IMAGEN_CONSULTADA.value,
        AccionAuditada.IMAGEN_ANULADA.value,
    } <= acciones
    fila = await sesion.get(ImagenPaciente, imagen["id"])
    assert fila is not None and fila.esta_anulado


async def test_foto_perfil_usa_ruta_y_permisos_administrativos(
    cliente: AsyncClient,
    api: str,
    cabeceras_imagenes: dict[str, str],
    paciente: Paciente,
) -> None:
    ruta = f"{api}/pacientes/{paciente.id}/foto-perfil"
    carga = await cliente.post(
        ruta,
        headers=cabeceras_imagenes,
        files={"archivo": ("perfil.png", _png_sintetico(), "image/png")},
    )
    assert carga.status_code == 201, carga.text
    assert carga.json()["tipo"] == "PERFIL"

    perfil = await cliente.get(ruta, headers=cabeceras_imagenes)
    assert perfil.status_code == 200
    assert perfil.json()["id"] == carga.json()["id"]
    contenido = await cliente.get(perfil.json()["url_contenido"], headers=cabeceras_imagenes)
    assert contenido.status_code == 200
    assert contenido.content == _png_sintetico()


async def test_sin_permiso_clinico_no_lista_imagenes(
    cliente: AsyncClient,
    api: str,
    usuario: Usuario,
    clinica: Clinica,
    paciente: Paciente,
) -> None:
    respuesta = await cliente.get(
        _ruta(api, str(paciente.id)),
        headers=await cabecera_bearer(cliente, usuario, clinica),
    )
    assert respuesta.status_code == 403


async def test_n3_exige_permiso_se_filtra_y_se_audita(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    cabeceras_imagenes: dict[str, str],
    relacion_imagen: RelacionAsistencial,
    paciente: Paciente,
) -> None:
    ruta = _ruta(api, str(paciente.id))
    datos = {"tipo": "RADIOGRAFIA_PANORAMICA", "nivel_sensibilidad": "N3"}
    denegada = await cliente.post(
        ruta,
        headers=cabeceras_imagenes,
        data=datos,
        files={"archivo": ("sensible.png", _png_sintetico(), "image/png")},
    )
    assert denegada.status_code == 403

    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "historia_clinica.leer_sensible",
        sedes=(sede.id,),
    )
    subida = await cliente.post(
        ruta,
        headers=cabeceras_imagenes,
        data=datos,
        files={"archivo": ("sensible.png", _png_sintetico(), "image/png")},
    )
    assert subida.status_code == 201, subida.text
    imagen = subida.json()
    assert imagen["nivel_sensibilidad"] == "N3"

    listado_autorizado = await cliente.get(ruta, headers=cabeceras_imagenes)
    assert [item["id"] for item in listado_autorizado.json()] == [imagen["id"]]
    auditoria = await sesion.scalar(
        sa.select(Auditoria)
        .where(Auditoria.accion == AccionAuditada.IMAGEN_CONSULTADA.value)
        .where(Auditoria.entidad_tipo == "paciente")
        .where(Auditoria.paciente_id == paciente.id)
    )
    assert auditoria is not None and auditoria.nivel_sensibilidad == "N3"

    lector_n2 = Usuario(
        clinica_id=clinica.id,
        correo=f"lector-n2-{uuid.uuid4().hex}@example.invalid",
        hash_contrasena=hashear_contrasena(CONTRASENA),
        nombre="Lector",
        apellido="N2",
    )
    sesion.add(lector_n2)
    await sesion.flush()
    await conceder_permisos(sesion, lector_n2, clinica, "imagen_clinica.leer", sedes=(sede.id,))
    cabeceras_n2 = await cabecera_bearer(cliente, lector_n2, clinica)
    listado_filtrado = await cliente.get(ruta, headers=cabeceras_n2)
    assert listado_filtrado.status_code == 200
    assert listado_filtrado.json() == []
    descarga_filtrada = await cliente.get(imagen["url_contenido"], headers=cabeceras_n2)
    assert descarga_filtrada.status_code == 404


async def test_rechaza_html_disfrazado_de_imagen(
    cliente: AsyncClient,
    api: str,
    cabeceras_imagenes: dict[str, str],
    relacion_imagen: RelacionAsistencial,
    paciente: Paciente,
) -> None:
    respuesta = await cliente.post(
        _ruta(api, str(paciente.id)),
        headers=cabeceras_imagenes,
        data={"tipo": "FOTO_INTRAORAL"},
        files={"archivo": ("imagen.jpg", b"<script>alert(1)</script>", "image/jpeg")},
    )
    assert respuesta.status_code == 415


async def test_no_asocia_la_imagen_a_una_cita_ajena_o_inexistente(
    cliente: AsyncClient,
    api: str,
    cabeceras_imagenes: dict[str, str],
    relacion_imagen: RelacionAsistencial,
    paciente: Paciente,
) -> None:
    respuesta = await cliente.post(
        _ruta(api, str(paciente.id)),
        headers=cabeceras_imagenes,
        data={"tipo": "FOTO_INTRAORAL", "cita_id": str(uuid.uuid4())},
        files={"archivo": ("imagen.png", _png_sintetico(), "image/png")},
    )
    assert respuesta.status_code == 404


async def _procedimiento_de(
    sesion: AsyncSession, clinica: Clinica, paciente_id: uuid.UUID, profesional: Profesional
) -> ProcedimientoPlan:
    plan = PlanTratamiento(
        clinica_id=clinica.id,
        paciente_id=paciente_id,
        profesional_id=profesional.id,
        titulo="Plan sintético",
    )
    sesion.add(plan)
    await sesion.flush()
    procedimiento = ProcedimientoPlan(plan_id=plan.id, pieza=36, descripcion="Restauración")
    sesion.add(procedimiento)
    await sesion.flush()
    return procedimiento


async def test_foto_ligada_a_procedimiento_se_filtra_por_el(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    cabeceras_imagenes: dict[str, str],
    relacion_imagen: RelacionAsistencial,
    paciente: Paciente,
    clinica: Clinica,
    profesional: Profesional,
) -> None:
    procedimiento = await _procedimiento_de(sesion, clinica, paciente.id, profesional)
    ruta = _ruta(api, str(paciente.id))
    carga = await cliente.post(
        ruta,
        headers=cabeceras_imagenes,
        data={
            "tipo": "FOTO_INTRAORAL",
            "piezas": "36",
            "procedimiento_id": str(procedimiento.id),
        },
        files={"archivo": ("imagen.png", _png_sintetico(), "image/png")},
    )
    assert carga.status_code == 201, carga.text
    assert carga.json()["procedimiento_id"] == str(procedimiento.id)
    suelta = await cliente.post(
        ruta,
        headers=cabeceras_imagenes,
        data={"tipo": "FOTO_INTRAORAL", "piezas": "36"},
        files={"archivo": ("imagen.png", _png_sintetico(), "image/png")},
    )
    assert suelta.status_code == 201
    assert suelta.json()["procedimiento_id"] is None

    filtrado = await cliente.get(
        f"{ruta}?procedimiento_id={procedimiento.id}", headers=cabeceras_imagenes
    )
    assert [fila["id"] for fila in filtrado.json()] == [carga.json()["id"]]


async def test_no_liga_la_foto_a_un_procedimiento_de_otro_paciente(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    cabeceras_imagenes: dict[str, str],
    relacion_imagen: RelacionAsistencial,
    paciente: Paciente,
    clinica: Clinica,
    profesional: Profesional,
    sufijo: str,
) -> None:
    otro = Paciente(
        clinica_id=clinica.id,
        tipo_documento="CEDULA",
        # Documento sintetico: no corresponde a ninguna cedula real.
        numero_documento=f"8{sufijo[:9]}",
        nombre="Otro",
        apellido="Sintetico",
    )
    sesion.add(otro)
    await sesion.flush()
    ajeno = await _procedimiento_de(sesion, clinica, otro.id, profesional)
    for procedimiento_id in (ajeno.id, uuid.uuid4()):
        respuesta = await cliente.post(
            _ruta(api, str(paciente.id)),
            headers=cabeceras_imagenes,
            data={"tipo": "FOTO_INTRAORAL", "procedimiento_id": str(procedimiento_id)},
            files={"archivo": ("imagen.png", _png_sintetico(), "image/png")},
        )
        assert respuesta.status_code == 404
