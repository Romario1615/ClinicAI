"""Especialidad desde la que se revisa una historia.

* El profesional revisa desde la suya: no ve las notas de otra especialidad
  aunque su rol tenga el comodín «todas las especialidades».
* Los módulos (odontograma, placa, planes, imágenes) se niegan en el backend
  a quien revisa desde una especialidad que no los usa.
* Administración configura los módulos de cada especialidad, con motivo,
  versionado y auditoría, sin cruzar clínicas.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.modelos import Auditoria
from app.modulos.historia.modelos import NotaEvolucion
from app.modulos.organizacion.modelos import Clinica, ConfiguracionClinica, Especialidad, Sede
from app.modulos.pacientes.modelos import Paciente, RelacionAsistencial
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import AmbitoAsignacion, Usuario, UsuarioRol
from app.nucleo.auditoria import AccionAuditada
from app.nucleo.autorizacion import TipoAmbito
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]


async def _dermatologia(
    sesion: AsyncSession, clinica: Clinica, sufijo: str
) -> tuple[Especialidad, Profesional]:
    especialidad = Especialidad(
        clinica_id=clinica.id, nombre=f"Dermatologia {sufijo}", codigo="DERM"
    )
    sesion.add(especialidad)
    await sesion.flush()
    profesional = Profesional(
        clinica_id=clinica.id,
        especialidad_id=especialidad.id,
        nombre="Dermatologa",
        apellido="Sintetica",
        numero_registro_profesional=f"DERM-{sufijo}",
    )
    sesion.add(profesional)
    await sesion.flush()
    return especialidad, profesional


async def _nota(sesion: AsyncSession, paciente: Paciente, autor: Profesional, texto: str) -> None:
    sesion.add(
        NotaEvolucion(
            clinica_id=paciente.clinica_id,
            paciente_id=paciente.id,
            profesional_id=autor.id,
            tipo="EVOLUCION",
            motivo_consulta=texto,
            creado_por=None,
        )
    )
    await sesion.flush()


async def test_el_odontologo_revisa_desde_su_especialidad(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    especialidad: Especialidad,
    profesional: Profesional,
    paciente: Paciente,
    sufijo: str,
) -> None:
    dermatologia, dermatologa = await _dermatologia(sesion, clinica, sufijo)
    sesion.add(
        RelacionAsistencial(paciente_id=paciente.id, profesional_id=profesional.id, origen="CITA")
    )
    await _nota(sesion, paciente, profesional, "Control dental sintetico")
    await _nota(sesion, paciente, dermatologa, "Control de piel sintetico")
    # Comodín de especialidades, como los roles habituales: no debe abrir las ajenas.
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "historia_clinica.leer",
        "odontograma.leer",
        sedes=(sede.id,),
        todas_las_especialidades=True,
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    propias = await cliente.get(f"{api}/historia/especialidades", headers=cabeceras)
    assert propias.status_code == 200
    assert propias.json() == [
        {
            "id": str(especialidad.id),
            "nombre": especialidad.nombre,
            "modulos": ["odontograma", "periodoncia", "planes", "imagenes"],
            "propia": True,
        }
    ]

    historia = await cliente.get(f"{api}/historia/pacientes/{paciente.id}/notas", headers=cabeceras)
    assert historia.status_code == 200
    assert [n["motivo_consulta"] for n in historia.json()] == ["Control dental sintetico"]

    ajena = await cliente.get(
        f"{api}/historia/pacientes/{paciente.id}/notas",
        params={"especialidad_id": str(dermatologia.id)},
        headers=cabeceras,
    )
    assert ajena.status_code == 403

    lectura = (
        await sesion.execute(
            sa.select(Auditoria)
            .where(
                Auditoria.accion == AccionAuditada.HISTORIA_CONSULTADA.value,
                Auditoria.paciente_id == paciente.id,
            )
            .order_by(Auditoria.ocurrido_en.desc())
            .limit(1)
        )
    ).scalar_one()
    assert (lectura.metadatos or {})["especialidades_revisadas"] == [str(especialidad.id)]


async def test_los_modulos_dentales_se_niegan_a_otra_especialidad(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    profesional: Profesional,
    paciente: Paciente,
    sufijo: str,
) -> None:
    dermatologia, _ = await _dermatologia(sesion, clinica, sufijo)
    # El usuario de las pruebas pasa a ser de dermatología.
    profesional.especialidad_id = dermatologia.id
    sesion.add(
        RelacionAsistencial(paciente_id=paciente.id, profesional_id=profesional.id, origen="CITA")
    )
    await sesion.flush()
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "odontograma.leer",
        "plan_tratamiento.leer",
        "imagen_clinica.leer",
        sedes=(sede.id,),
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    odontograma = await cliente.get(
        f"{api}/odontologia/pacientes/{paciente.id}/odontograma", headers=cabeceras
    )
    assert odontograma.status_code == 403
    assert "Odontograma" in odontograma.json()["mensaje"]
    planes = await cliente.get(
        f"{api}/odontologia/pacientes/{paciente.id}/planes-tratamiento", headers=cabeceras
    )
    assert planes.status_code == 403
    # Imágenes sí: por omisión todas las especialidades las usan.
    imagenes = await cliente.get(f"{api}/pacientes/{paciente.id}/imagenes", headers=cabeceras)
    assert imagenes.status_code == 200


async def test_administracion_configura_los_modulos_de_cada_especialidad(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    especialidad: Especialidad,
    sufijo: str,
) -> None:
    dermatologia, _ = await _dermatologia(sesion, clinica, sufijo)
    ruta = f"{api}/catalogo/especialidades/{dermatologia.id}/modulos-historia"
    sin_sesion = await cliente.put(ruta, json={"modulos": [], "motivo": "Sin sesion"})
    assert sin_sesion.status_code == 401

    await conceder_permisos(sesion, usuario, clinica, "historia_clinica.leer", sedes=(sede.id,))
    sin_permiso = await cliente.put(
        ruta,
        headers=await cabecera_bearer(cliente, usuario, clinica),
        json={"modulos": [], "motivo": "Sin permiso"},
    )
    assert sin_permiso.status_code == 403

    await conceder_permisos(sesion, usuario, clinica, "especialidad.gestionar", sedes=(sede.id,))
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    vista = await cliente.get(f"{api}/catalogo/especialidades/modulos-historia", headers=cabeceras)
    assert vista.status_code == 200
    por_id = {e["id"]: e["modulos"] for e in vista.json()["especialidades"]}
    assert por_id[str(especialidad.id)] == ["odontograma", "periodoncia", "planes", "imagenes"]
    assert por_id[str(dermatologia.id)] == ["faciograma", "imagenes"]

    invalido = await cliente.put(
        ruta, headers=cabeceras, json={"modulos": ["recetas"], "motivo": "Modulo inexistente"}
    )
    assert invalido.status_code == 422
    sin_motivo = await cliente.put(ruta, headers=cabeceras, json={"modulos": []})
    assert sin_motivo.status_code == 422

    for modulos in (["imagenes", "faciograma", "imagenes"], []):
        cambio = await cliente.put(
            ruta, headers=cabeceras, json={"modulos": modulos, "motivo": "Ajuste sintetico"}
        )
        assert cambio.status_code == 200, cambio.text
    assert cambio.json()["modulos"] == []
    versiones = (
        await sesion.execute(
            sa.select(ConfiguracionClinica.version, ConfiguracionClinica.vigente)
            .where(
                ConfiguracionClinica.clinica_id == clinica.id,
                ConfiguracionClinica.clave == "modulos_historia",
            )
            .order_by(ConfiguracionClinica.version)
        )
    ).all()
    assert [tuple(v) for v in versiones] == [(1, False), (2, True)]
    auditado = (
        await sesion.execute(
            sa.select(sa.func.count()).where(
                Auditoria.accion == AccionAuditada.ESPECIALIDAD_MODULOS_CAMBIADOS.value,
                Auditoria.entidad_id == dermatologia.id,
            )
        )
    ).scalar_one()
    assert auditado == 2

    ajena = Clinica(nombre="Clinica ajena sintetica", identificacion_fiscal=uuid.uuid4().hex[:12])
    sesion.add(ajena)
    await sesion.flush()
    de_otra = Especialidad(clinica_id=ajena.id, nombre="Otra")
    sesion.add(de_otra)
    await sesion.flush()
    cruzada = await cliente.put(
        f"{api}/catalogo/especialidades/{de_otra.id}/modulos-historia",
        headers=cabeceras,
        json={"modulos": [], "motivo": "Intento cruzado"},
    )
    assert cruzada.status_code == 404


async def test_configuracion_antigua_no_habilita_faciograma_al_odontologo(
    cliente,
    api,
    sesion,
    usuario,
    clinica,
    sede,
    especialidad,
    profesional,
    paciente,
):
    sesion.add(
        ConfiguracionClinica(
            clinica_id=clinica.id,
            clave="modulos_historia",
            valor={str(especialidad.id): ["odontograma", "periodoncia", "faciograma"]},
            vigente=True,
            version=1,
        )
    )
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
        "especialidad.gestionar",
        sedes=(sede.id,),
    )
    headers = await cabecera_bearer(cliente, usuario, clinica)
    areas = await cliente.get(f"{api}/historia/especialidades", headers=headers)
    assert areas.status_code == 200
    assert areas.json()[0]["modulos"] == ["odontograma", "periodoncia"]
    assert (
        await cliente.get(f"{api}/historia/faciograma/zonas", headers=headers)
    ).status_code == 403
    cambio = await cliente.put(
        f"{api}/catalogo/especialidades/{especialidad.id}/modulos-historia",
        headers=headers,
        json={"modulos": ["faciograma"], "motivo": "Intento de herramienta ajena"},
    )
    assert cambio.status_code == 422
    facial = await cliente.post(
        f"{api}/historia/pacientes/{paciente.id}/registros",
        headers=headers,
        json={
            "clave_idempotencia": str(uuid.uuid4()),
            "tipo": "FACIOGRAMA",
            "titulo": "Evaluación sintética",
            "especialidad_id": str(especialidad.id),
            "sede_id": str(sede.id),
            "motivo": "Registro inicial",
            "zonas": [{"zona": "menton", "observacion": "Observación sintética"}],
        },
    )
    assert facial.status_code == 404


async def test_conceder_consulta_de_otra_area_no_acredita_sus_herramientas(
    cliente,
    api,
    sesion,
    usuario,
    clinica,
    sede,
    especialidad,
    profesional,
    sufijo,
):
    derm, _ = await _dermatologia(sesion, clinica, sufijo)
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "historia_clinica.leer",
        "odontograma.leer",
        sedes=(sede.id,),
    )
    asignacion = await sesion.scalar(
        sa.select(UsuarioRol).where(UsuarioRol.usuario_id == usuario.id)
    )
    assert asignacion is not None
    sesion.add(
        AmbitoAsignacion(
            usuario_rol_id=asignacion.id, tipo=TipoAmbito.ESPECIALIDAD.value, valor_id=derm.id
        )
    )
    await sesion.flush()
    headers = await cabecera_bearer(cliente, usuario, clinica)
    areas = await cliente.get(f"{api}/historia/especialidades", headers=headers)
    assert areas.status_code == 200
    por_id = {e["id"]: e for e in areas.json()}
    assert "odontograma" in por_id[str(especialidad.id)]["modulos"]
    assert por_id[str(derm.id)]["modulos"] == ["imagenes"]
    assert (
        await cliente.get(f"{api}/historia/faciograma/zonas", headers=headers)
    ).status_code == 403
