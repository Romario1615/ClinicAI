import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.conocimiento.modelos import KnowledgeDocument
from app.modulos.organizacion.modelos import Clinica, Especialidad, Sede
from app.modulos.pacientes.modelos import Paciente
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Usuario
from pruebas.api.conftest import cabecera_bearer, conceder_permisos
from pruebas.api.test_imagenes_api import _png_sintetico
from pruebas.api.test_periodontograma_api import contenido, preparar

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]


@pytest.mark.parametrize("superadmin", [False, True])
async def test_fotos_de_plataforma_entre_clinicas_solo_para_superadministracion(
    cliente, sesion, api, usuario, clinica, sede, superadmin, configuracion
):
    # Igual que las pruebas del portal de plataforma: aquí se comprueba el
    # ámbito entre clínicas; la autenticación TOTP tiene su batería propia.
    configuracion.roles_con_2fa_obligatorio = ""
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "sede.gestionar",
        "usuario.leer",
        "usuario.editar",
        "paciente.leer_administrativo",
        codigo_rol="superadministrador" if superadmin else None,
        sedes=(sede.id,),
    )
    otra = Clinica(
        nombre="Clínica de plataforma sintética",
        identificacion_fiscal=f"TEST-{uuid.uuid4().hex[:10]}",
    )
    sesion.add(otra)
    await sesion.flush()
    sucursal = Sede(
        clinica_id=otra.id, nombre="Sede sintética de plataforma", direccion="Ubicación sintética"
    )
    personal = Usuario(
        clinica_id=otra.id,
        correo=f"{uuid.uuid4().hex}@example.invalid",
        hash_contrasena=usuario.hash_contrasena,
        nombre="Persona",
        apellido="Sintética",
    )
    ajeno = Paciente(
        clinica_id=otra.id, nombre="Paciente", apellido="Sintético", tipo_documento="SIN_DOCUMENTO"
    )
    sesion.add_all([sucursal, personal, ajeno])
    await sesion.flush()
    h = await cabecera_bearer(cliente, usuario, clinica)
    for tipo, registro in (("sede", sucursal), ("usuario", personal)):
        ruta = f"{api}/fotos-registro/{tipo}/{registro.id}"
        foto = await cliente.post(
            ruta,
            headers=h,
            data={"clave_idempotencia": str(uuid.uuid4())},
            files={"archivo": ("sintetico.png", _png_sintetico(), "image/png")},
        )
        assert foto.status_code == (201 if superadmin else 404), foto.text
        if superadmin:
            assert len((await cliente.get(ruta, headers=h)).json()) == 1
            assert (
                await cliente.get(f"{ruta}/{foto.json()['id']}/contenido", headers=h)
            ).status_code == 200
    assert (
        await cliente.get(f"{api}/fotos-registro/paciente/{ajeno.id}", headers=h)
    ).status_code == 404


async def test_fotos_administrativas_privadas_con_reintento_y_retirada(
    cliente: AsyncClient,
    sesion: AsyncSession,
    api: str,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
) -> None:
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "paciente.leer_administrativo",
        "paciente.editar",
        sedes=(sede.id,),
    )
    h = await cabecera_bearer(cliente, usuario, clinica)
    ruta = f"{api}/fotos-registro/paciente/{paciente.id}"
    clave = str(uuid.uuid4())
    data = {"clave_idempotencia": clave, "descripcion": "Imagen administrativa sintética"}
    files = {"archivo": ("sintetico.png", _png_sintetico(), "image/png")}
    r = await cliente.post(ruta, headers=h, data=data, files=files)
    assert r.status_code == 201, r.text
    assert r.json()["id"] == clave
    repetido = await cliente.post(ruta, headers=h, data=data, files=files)
    assert repetido.status_code == 201
    assert len((await cliente.get(ruta, headers=h)).json()) == 1
    imagen = await cliente.get(f"{ruta}/{clave}/contenido", headers=h)
    assert imagen.status_code == 200 and imagen.content.startswith(b"\x89PNG")
    assert imagen.headers["cache-control"] == "private, no-store"
    assert imagen.headers["x-content-type-options"] == "nosniff"
    assert (
        await cliente.post(ruta, headers=h, data={**data, "descripcion": "Otro texto"}, files=files)
    ).status_code == 409
    assert (
        await cliente.get(
            f"{api}/fotos-registro/paciente/{uuid.uuid4()}/{clave}/contenido", headers=h
        )
    ).status_code == 404
    assert (
        await cliente.post(
            f"{ruta}/{clave}/retirar",
            headers=h,
            json={"motivo": "Retirada sintética de comprobante"},
        )
    ).status_code == 204
    assert not (await cliente.get(ruta, headers=h)).json()
    assert (await cliente.get(f"{ruta}/{clave}/contenido", headers=h)).status_code == 404


async def test_tipo_archivo_falso_y_registro_ajeno(
    cliente: AsyncClient,
    sesion: AsyncSession,
    api: str,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
) -> None:
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "paciente.leer_administrativo",
        "paciente.editar",
        sedes=(sede.id,),
    )
    h = await cabecera_bearer(cliente, usuario, clinica)
    ruta = f"{api}/fotos-registro/paciente/{paciente.id}"
    data = {"clave_idempotencia": str(uuid.uuid4())}
    r = await cliente.post(
        ruta,
        headers=h,
        data=data,
        files={"archivo": ("falso.png", b"<script>contenido falso</script>", "image/png")},
    )
    assert r.status_code == 415, r.text
    ajeno = Paciente(
        clinica_id=uuid.uuid4(),
        nombre="Ajeno",
        apellido="Sintético",
        tipo_documento="SIN_DOCUMENTO",
    )
    # Un UUID desconocido comparte el mismo 404 que un registro fuera de ámbito.
    assert (
        await cliente.get(f"{api}/fotos-registro/paciente/{ajeno.id or uuid.uuid4()}", headers=h)
    ).status_code == 404
    assert (
        await cliente.get(f"{api}/fotos-registro/noexiste/{paciente.id}", headers=h)
    ).status_code == 404


async def test_foto_clinica_respeta_herramienta(
    cliente: AsyncClient,
    sesion: AsyncSession,
    api: str,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    profesional: Profesional,
    especialidad: Especialidad,
    paciente: Paciente,
) -> None:
    h = await preparar(cliente, sesion, usuario, clinica, sede, profesional, especialidad, paciente)
    r = await cliente.post(
        f"{api}/odontologia/pacientes/{paciente.id}/periodontogramas",
        headers=h,
        json=contenido(sede),
    )
    assert r.status_code == 201, r.text
    id_registro = r.json()["id"]
    ruta = f"{api}/fotos-registro/periodontograma/{id_registro}"
    r = await cliente.post(
        ruta,
        headers=h,
        data={"clave_idempotencia": str(uuid.uuid4())},
        files={"archivo": ("sintetico.png", _png_sintetico(), "image/png")},
    )
    assert r.status_code == 201, r.text
    lista = await cliente.get(ruta, headers=h)
    assert lista.status_code == 200 and len(lista.json()) == 1
    foto = await cliente.get(f"{ruta}/{r.json()['id']}/contenido", headers=h)
    assert foto.status_code == 200 and foto.content.startswith(b"\x89PNG")
    control = (
        await cliente.get(f"{api}/odontologia/pacientes/{paciente.id}/periodontogramas", headers=h)
    ).json()[0]
    correccion = await cliente.post(
        f"{api}/odontologia/pacientes/{paciente.id}/periodontogramas",
        headers=h,
        json=contenido(sede, version_anterior_id=control["id"]),
    )
    assert correccion.status_code == 201, correccion.text
    historica = await cliente.post(
        ruta,
        headers=h,
        data={"clave_idempotencia": str(uuid.uuid4())},
        files={"archivo": ("sintetico.png", _png_sintetico(), "image/png")},
    )
    assert historica.status_code == 409
    especialidad.codigo = "DERM"
    especialidad.nombre = "Dermatología sintética"
    await sesion.flush()
    assert (await cliente.get(ruta, headers=h)).status_code in {403, 404}


async def test_fotos_de_conocimiento_conservan_nivel_y_sede(
    cliente: AsyncClient,
    sesion: AsyncSession,
    api: str,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    otra_sede: Sede,
) -> None:
    await conceder_permisos(
        sesion, usuario, clinica, "conocimiento.leer", "conocimiento.cargar", sedes=(sede.id,)
    )
    h = await cabecera_bearer(cliente, usuario, clinica)
    r = await cliente.post(
        f"{api}/conocimiento/documentos",
        headers=h,
        json={"titulo": "Guía administrativa sintética", "tipo": "INSTRUCTIVO"},
    )
    assert r.status_code == 201, r.text
    id_documento = uuid.UUID(r.json()["id"])
    doc = (
        await sesion.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == id_documento))
    ).scalar_one()
    doc.sensitivity_level = "N0"
    await sesion.flush()
    ruta = f"{api}/fotos-registro/conocimiento/{id_documento}"
    r = await cliente.post(
        ruta,
        headers=h,
        data={"clave_idempotencia": str(uuid.uuid4())},
        files={"archivo": ("sintetico.png", _png_sintetico(), "image/png")},
    )
    assert r.status_code == 201, r.text
    id_foto = r.json()["id"]
    assert (await cliente.get(f"{ruta}/{id_foto}/contenido", headers=h)).status_code == 200
    doc.branch_id = otra_sede.id
    await sesion.flush()
    assert (await cliente.get(ruta, headers=h)).status_code == 404
    assert (await cliente.get(f"{ruta}/{id_foto}/contenido", headers=h)).status_code == 404


async def test_foto_administrativa_no_cruza_clinicas(
    cliente: AsyncClient,
    sesion: AsyncSession,
    api: str,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
) -> None:
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "paciente.leer_administrativo",
        "paciente.editar",
        sedes=(sede.id,),
    )
    h = await cabecera_bearer(cliente, usuario, clinica)
    otra = Clinica(
        nombre="Organización sintética ajena", identificacion_fiscal=f"TEST-{uuid.uuid4().hex[:10]}"
    )
    sesion.add(otra)
    await sesion.flush()
    ajeno = Paciente(
        clinica_id=otra.id, nombre="Persona", apellido="Sintética", tipo_documento="SIN_DOCUMENTO"
    )
    sesion.add(ajeno)
    await sesion.flush()
    for identificador in (ajeno.id, uuid.uuid4()):
        ruta = f"{api}/fotos-registro/paciente/{identificador}"
        assert (await cliente.get(ruta, headers=h)).status_code == 404
        assert (
            await cliente.post(
                ruta,
                headers=h,
                data={"clave_idempotencia": str(uuid.uuid4())},
                files={"archivo": ("sintetico.png", _png_sintetico(), "image/png")},
            )
        ).status_code == 404
