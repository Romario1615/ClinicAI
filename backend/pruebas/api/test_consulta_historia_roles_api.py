"""Nueva política: historial N2 compartido, escritura clínica por especialidad."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.modelos import Auditoria
from app.modulos.historia.modelos import NotaEvolucion
from app.modulos.organizacion.modelos import Clinica, Especialidad, Sede
from app.modulos.pacientes.modelos import Paciente, RelacionAsistencial
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.auditoria import AccionAuditada
from app.nucleo.autorizacion import PERMISOS_POR_ROL
from pruebas.api.conftest import cabecera_bearer, conceder_permisos
from pruebas.api.test_especialidades_historia_api import _dermatologia

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]


@pytest.mark.parametrize("rol", tuple(PERMISOS_POR_ROL))
async def test_todos_consultan_paciente_nuevo_sin_relacion_y_no_generan_registros(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
    rol: str,
    especialidad: Especialidad,
) -> None:
    especialidad.nombre = "Odontología sintética"
    especialidad.codigo = "ODO"
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        *PERMISOS_POR_ROL[rol],
        sedes=(sede.id,),
        todas_las_especialidades=True,
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    acceso = await cliente.get(f"{api}/pacientes/{paciente.id}/acceso-clinico", headers=cabeceras)
    assert acceso.status_code == 200
    assert acceso.json()["acceso_clinico"] is True
    resumen = await cliente.get(
        f"{api}/historia/pacientes/{paciente.id}/resumen-clinico", headers=cabeceras
    )
    assert resumen.status_code == 200, (rol, resumen.text)
    for ruta in (
        f"/historia/pacientes/{paciente.id}/notas",
        f"/historia/pacientes/{paciente.id}/recetas",
        f"/historia/pacientes/{paciente.id}/anamnesis/respuestas",
        f"/odontologia/pacientes/{paciente.id}/periodontogramas",
        f"/odontologia/pacientes/{paciente.id}/odontograma/versiones",
        f"/odontologia/pacientes/{paciente.id}/planes-tratamiento",
        f"/pacientes/{paciente.id}/imagenes",
    ):
        lectura = await cliente.get(api + ruta, headers=cabeceras)
        assert lectura.status_code == 200, (rol, ruta, lectura.text)
        assert lectura.json() == [], (rol, ruta)
    fuera = await cliente.get(
        f"{api}/historia/pacientes/00000000-0000-0000-0000-000000000001/notas", headers=cabeceras
    )
    assert fuera.status_code == 404
    if rol != "profesional":
        for ruta in (
            "/historia/notas",
            "/historia/recetas",
            f"/odontologia/pacientes/{paciente.id}/odontograma",
            f"/historia/tomas/{uuid.uuid4()}/registro",
            f"/historia/adherencia/alertas/{uuid.uuid4()}/atencion",
        ):
            intento = await cliente.post(api + ruta, headers=cabeceras, json={})
            assert intento.status_code == 403, (rol, ruta, intento.text)


async def test_especialista_consulta_herramientas_ajenas_pero_no_las_escribe(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
    sufijo: str,
    profesional: Profesional,
) -> None:

    dermatologia, colega = await _dermatologia(sesion, clinica, sufijo)
    profesional.especialidad_id = dermatologia.id
    sesion.add(
        NotaEvolucion(
            clinica_id=clinica.id,
            paciente_id=paciente.id,
            profesional_id=colega.id,
            tipo="EVOLUCION",
            motivo_consulta="Observación compartida sintética",
        )
    )
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        *PERMISOS_POR_ROL["profesional"],
        sedes=(sede.id,),
        todas_las_especialidades=True,
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    areas = await cliente.get(f"{api}/historia/especialidades", headers=cabeceras)
    assert areas.status_code == 200
    assert any("odontograma" in e["modulos"] and not e["propia"] for e in areas.json())
    dental = await cliente.get(
        f"{api}/odontologia/pacientes/{paciente.id}/odontograma/versiones", headers=cabeceras
    )
    assert dental.status_code == 200
    notas = await cliente.get(
        f"{api}/historia/pacientes/{paciente.id}/notas",
        params={"especialidad_id": str(dermatologia.id)},
        headers=cabeceras,
    )
    assert notas.status_code == 200
    assert [nota["motivo_consulta"] for nota in notas.json()] == [
        "Observación compartida sintética"
    ]
    intento = await cliente.post(
        f"{api}/odontologia/pacientes/{paciente.id}/odontograma", headers=cabeceras, json={}
    )
    assert intento.status_code == 403


async def test_consulta_compartida_no_cruza_clinica(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
    sufijo: str,
    especialidad: Especialidad,
) -> None:
    # Catálogo dental explícito para que el control de módulo no oculte el IDOR.
    especialidad.codigo = "ODO"
    ajena = Clinica(
        nombre=f"Clínica ajena sintética {sufijo}",
        identificacion_fiscal=f"AJ-{sufijo}",
        zona_horaria="America/Guayaquil",
    )
    sesion.add(ajena)
    await sesion.flush()
    externo = Paciente(
        clinica_id=ajena.id,
        tipo_documento="PASAPORTE",
        numero_documento=f"AJ-{sufijo}",
        nombre="Paciente",
        apellido="Sintético ajeno",
    )
    sesion.add(externo)
    await sesion.flush()
    await conceder_permisos(
        sesion, usuario, clinica, *PERMISOS_POR_ROL["recepcion"], sedes=(sede.id,)
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    for ruta in (
        f"/historia/pacientes/{externo.id}/notas",
        f"/odontologia/pacientes/{externo.id}/periodontogramas",
        f"/pacientes/{externo.id}/acceso-clinico",
    ):
        respuesta = await cliente.get(api + ruta, headers=cabeceras)
        assert respuesta.status_code == 404, (ruta, respuesta.text)


async def test_inicio_sin_cita_es_explicito_idempotente_y_solo_profesional(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
    profesional: Profesional,
) -> None:

    ruta = f"{api}/pacientes/{paciente.id}/atencion-profesional"
    datos = {"motivo": "Atención presencial sintética sin cita"}
    assert (await cliente.post(ruta, json=datos)).status_code == 401
    await conceder_permisos(
        sesion, usuario, clinica, *PERMISOS_POR_ROL["recepcion"], sedes=(sede.id,)
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    assert (
        await cliente.post(
            ruta, headers={**cabeceras, "Idempotency-Key": str(uuid.uuid4())}, json=datos
        )
    ).status_code == 403
    await conceder_permisos(
        sesion, usuario, clinica, *PERMISOS_POR_ROL["profesional"], sedes=(sede.id,)
    )
    cabeceras = {
        **(await cabecera_bearer(cliente, usuario, clinica)),
        "Idempotency-Key": str(uuid.uuid4()),
    }
    assert (await cliente.post(ruta, headers=cabeceras, json={"motivo": "x"})).status_code == 422
    for _ in range(2):
        inicio = await cliente.post(ruta, headers=cabeceras, json=datos)
        assert inicio.status_code == 204, inicio.text
    relaciones = list(
        await sesion.scalars(
            select(RelacionAsistencial).where(
                RelacionAsistencial.paciente_id == paciente.id,
                RelacionAsistencial.profesional_id == profesional.id,
            )
        )
    )
    assert len(relaciones) == 1
    assert relaciones[0].origen == "ASIGNACION"
    fuera = await cliente.post(
        f"{api}/pacientes/{uuid.uuid4()}/atencion-profesional",
        headers={**cabeceras, "Idempotency-Key": str(uuid.uuid4())},
        json=datos,
    )
    assert fuera.status_code == 404


@pytest.mark.parametrize(
    "rol", ("recepcion", "asistente", "administrador_clinica", "auditor", "superadministrador")
)
async def test_consulta_con_contenido_n2_auditada_no_concede_n3(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
    profesional: Profesional,
    rol: str,
) -> None:
    for nivel in ("N2", "N3"):
        sesion.add(
            NotaEvolucion(
                clinica_id=clinica.id,
                paciente_id=paciente.id,
                profesional_id=profesional.id,
                tipo="EVOLUCION",
                nivel_sensibilidad=nivel,
                motivo_consulta=f"Observación sintética {nivel}",
            )
        )
    await conceder_permisos(sesion, usuario, clinica, *PERMISOS_POR_ROL[rol], sedes=(sede.id,))
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    lectura = await cliente.get(f"{api}/historia/pacientes/{paciente.id}/notas", headers=cabeceras)
    assert lectura.status_code == 200, lectura.text
    assert [n["motivo_consulta"] for n in lectura.json()] == ["Observación sintética N2"]
    auditoria = await sesion.scalar(
        select(Auditoria.id).where(
            Auditoria.paciente_id == paciente.id,
            Auditoria.actor_id == usuario.id,
            Auditoria.accion == AccionAuditada.HISTORIA_CONSULTADA.value,
        )
    )
    assert auditoria is not None


async def test_consulta_no_abre_pacientes_de_la_clinica_fuera_del_ambito(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
) -> None:
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        *PERMISOS_POR_ROL["recepcion"],
        sedes=(sede.id,),
        todos_los_pacientes=False,
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    for ruta in (
        f"/historia/pacientes/{paciente.id}/notas",
        f"/pacientes/{paciente.id}/acceso-clinico",
    ):
        assert (await cliente.get(api + ruta, headers=cabeceras)).status_code == 404


async def test_ambito_parcial_conserva_area_propia_sin_abrir_otra(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
    especialidad: Especialidad,
    profesional: Profesional,
    sufijo: str,
) -> None:
    dermatologia, colega = await _dermatologia(sesion, clinica, sufijo)
    for autor, texto in (
        (profesional, "Nota propia sintética"),
        (colega, "Nota de otra área sintética"),
    ):
        sesion.add(
            NotaEvolucion(
                clinica_id=clinica.id,
                paciente_id=paciente.id,
                profesional_id=autor.id,
                tipo="EVOLUCION",
                motivo_consulta=texto,
            )
        )
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        *PERMISOS_POR_ROL["profesional"],
        sedes=(sede.id,),
        todas_las_especialidades=False,
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    areas = await cliente.get(f"{api}/historia/especialidades", headers=cabeceras)
    assert [area["id"] for area in areas.json()] == [str(especialidad.id)]
    propias = await cliente.get(f"{api}/historia/pacientes/{paciente.id}/notas", headers=cabeceras)
    assert propias.status_code == 200
    assert [nota["motivo_consulta"] for nota in propias.json()] == ["Nota propia sintética"]
    fuera = await cliente.get(
        f"{api}/historia/pacientes/{paciente.id}/notas",
        params={"especialidad_id": str(dermatologia.id)},
        headers=cabeceras,
    )
    assert fuera.status_code == 403
