import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.odontologia.periodontograma_modelos import Periodontograma
from app.modulos.organizacion.modelos import Clinica, Especialidad, Sede
from app.modulos.pacientes.modelos import Paciente, RelacionAsistencial
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Usuario
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]


async def preparar(
    cliente: AsyncClient,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    profesional: Profesional,
    especialidad: Especialidad,
    paciente: Paciente,
    sensible: bool = False,
) -> dict[str, str]:
    especialidad.codigo = "ODO"
    especialidad.nombre = "Odontología sintética"
    sesion.add(
        RelacionAsistencial(paciente_id=paciente.id, profesional_id=profesional.id, origen="CITA")
    )
    await sesion.flush()
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "odontograma.leer",
        "odontograma.escribir",
        "imagen_clinica.leer",
        "imagen_clinica.cargar",
        *(("historia_clinica.leer_sensible",) if sensible else ()),
        sedes=(sede.id,),
    )
    return await cabecera_bearer(cliente, usuario, clinica)


def contenido(sede: Sede, **extra: object) -> dict[str, object]:
    return {
        "clave_idempotencia": str(uuid.uuid4()),
        "fecha_examen": "2026-04-15",
        "sede_id": str(sede.id),
        "motivo": "Control periodontal sintético",
        "piezas": {
            "16": {
                "sitios": {
                    "VM": {"profundidad": 4, "margen": 2, "sangrado": True},
                    "VC": {"profundidad": 3, "sangrado": False},
                }
            }
        },
        **extra,
    }


async def test_crud_historico_pdf_y_conflictos(
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
    ruta = f"{api}/odontologia/pacientes/{paciente.id}/periodontogramas"
    datos = contenido(sede)
    inicial = await cliente.post(ruta, headers=h, json=datos)
    assert inicial.status_code == 201, inicial.text
    r = inicial.json()
    assert r["resumen"]["sangrado_porcentaje"] == 50
    assert r["resumen"]["insercion_media"] == 6
    assert r["puede_editar"]
    repetido = await cliente.post(ruta, headers=h, json=datos)
    assert repetido.status_code == 201 and repetido.json()["id"] == r["id"]
    alterado = await cliente.post(
        ruta, headers=h, json={**datos, "motivo": "Otro motivo sintético"}
    )
    assert alterado.status_code == 409
    corregido = await cliente.post(
        ruta,
        headers=h,
        json=contenido(
            sede, version_anterior_id=r["id"], piezas={"16": {"sitios": {"VM": {"profundidad": 3}}}}
        ),
    )
    assert corregido.status_code == 201, corregido.text
    r2 = corregido.json()
    assert r2["version"] == 2 and r2["raiz_id"] == r["raiz_id"]
    obsoleto = await cliente.post(
        ruta, headers=h, json=contenido(sede, version_anterior_id=r["id"])
    )
    assert obsoleto.status_code == 409
    historia = (await cliente.get(ruta, headers=h)).json()
    assert len(historia) == 2
    assert not next(f for f in historia if f["id"] == r["id"])["vigente"]
    pdf = await cliente.get(f"{ruta}/{r2['id']}/pdf", headers=h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    assert pdf.headers["cache-control"] == "private, no-store"
    anulado = await cliente.post(
        ruta, headers=h, json=contenido(sede, version_anterior_id=r2["id"], anulado=True, piezas={})
    )
    assert anulado.status_code == 201 and anulado.json()["anulado"]
    assert not anulado.json()["puede_editar"]
    assert (await cliente.delete(f"{ruta}/{r['id']}", headers=h)).status_code in {404, 405}


async def test_sensible_y_fecha_futura(
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
    ruta = f"{api}/odontologia/pacientes/{paciente.id}/periodontogramas"
    assert (
        await cliente.post(ruta, headers=h, json=contenido(sede, nivel_sensibilidad="N3"))
    ).status_code == 403
    assert (
        await cliente.post(ruta, headers=h, json=contenido(sede, fecha_examen="2030-01-01"))
    ).status_code == 422
    assert (
        await cliente.post(ruta, headers=h, json=contenido(sede, sede_id=str(uuid.uuid4())))
    ).status_code == 404


async def test_postgres_impide_alterar_o_borrar(
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
    id_registro = uuid.UUID(r.json()["id"])
    for sentencia in [
        "UPDATE periodontograma SET motivo='Manipulación sintética' WHERE id=:id",
        "DELETE FROM periodontograma WHERE id=:id",
    ]:
        with pytest.raises(DBAPIError):
            async with sesion.begin_nested():
                await sesion.execute(text(sentencia), {"id": id_registro})
    assert (
        await sesion.execute(select(Periodontograma.id).where(Periodontograma.id == id_registro))
    ).scalar_one() == id_registro
