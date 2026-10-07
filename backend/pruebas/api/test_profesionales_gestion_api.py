"""Gestión de perfiles del equipo, asignaciones de sede y ámbitos."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.modelos import Auditoria
from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.profesionales.modelos import Profesional, ProfesionalSede
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


def _datos(especialidad_id: uuid.UUID, sede_id: uuid.UUID, **cambios: object) -> dict[str, object]:
    return {
        "especialidad_id": str(especialidad_id),
        "nombre": "María",
        "apellido": "Ejemplo",
        "numero_registro_profesional": "OD-TEST-001",
        "telefono_whatsapp": "+593999000111",
        "correo_calendario": "maria@example.invalid",
        "estado_disponibilidad": "DISPONIBLE",
        "acepta_pacientes_nuevos": True,
        "minutos_preparacion_propio": 10,
        "activo": True,
        "sede_ids": [str(sede_id)],
        "sede_principal_id": str(sede_id),
        **cambios,
    }


class TestGestionProfesionales:
    async def _cabeceras_completas(
        self,
        cliente: AsyncClient,
        sesion: AsyncSession,
        usuario,
        clinica: Clinica,
        *sedes: Sede,
    ) -> dict[str, str]:
        await conceder_permisos(
            sesion,
            usuario,
            clinica,
            "profesional.gestionar",
            sedes=tuple(sede.id for sede in sedes),
            todas_las_especialidades=True,
            todos_los_profesionales=True,
            todos_los_pacientes=False,
        )
        return await cabecera_bearer(cliente, usuario, clinica)

    async def test_alta_edicion_y_listado_auditados(
        self,
        cliente: AsyncClient,
        sesion: AsyncSession,
        usuario,
        clinica: Clinica,
        sede: Sede,
        otra_sede: Sede,
        especialidad,
    ) -> None:
        headers = await self._cabeceras_completas(
            cliente, sesion, usuario, clinica, sede, otra_sede
        )
        url = "/api/v1/profesionales/gestion"
        datos = _datos(
            especialidad.id,
            sede.id,
            sede_ids=[str(sede.id), str(otra_sede.id)],
        )
        alta = await cliente.post(url, json=datos, headers=headers)
        assert alta.status_code == 201, alta.text
        perfil = alta.json()
        assert perfil["nombre"] == "María"
        assert set(perfil["sede_ids"]) == {str(sede.id), str(otra_sede.id)}
        assert perfil["sede_principal_id"] == str(sede.id)

        listado = await cliente.get(url, headers=headers)
        assert listado.status_code == 200
        assert [fila["id"] for fila in listado.json()] == [perfil["id"]]

        cambios = _datos(
            especialidad.id,
            otra_sede.id,
            apellido="Actualizada",
            telefono_whatsapp=None,
            acepta_pacientes_nuevos=False,
            minutos_preparacion_propio=20,
            activo=False,
            estado_disponibilidad="DISPONIBLE",
            sede_ids=[str(otra_sede.id)],
        )
        editada = await cliente.put(f"{url}/{perfil['id']}", json=cambios, headers=headers)
        assert editada.status_code == 200, editada.text
        assert editada.json()["apellido"] == "Actualizada"
        assert editada.json()["telefono_whatsapp"] is None
        assert editada.json()["estado_disponibilidad"] == "INACTIVO"
        assert editada.json()["activo"] is False
        assert editada.json()["sede_ids"] == [str(otra_sede.id)]

        acciones = list(
            (
                await sesion.execute(
                    select(Auditoria.accion).where(Auditoria.entidad_id == uuid.UUID(perfil["id"]))
                )
            ).scalars()
        )
        assert "profesional.creado" in acciones
        assert "profesional.modificado" in acciones
        assert "profesional.consultado" in acciones

    async def test_ambito_limitado_no_muestra_ni_modifica_otra_sede(
        self,
        cliente: AsyncClient,
        sesion: AsyncSession,
        usuario,
        clinica: Clinica,
        sede: Sede,
        otra_sede: Sede,
        especialidad,
    ) -> None:
        perfil = Profesional(
            clinica_id=clinica.id,
            especialidad_id=especialidad.id,
            nombre="Alex",
            apellido="Equipo",
            numero_registro_profesional="OD-SCOPED-001",
        )
        sesion.add(perfil)
        await sesion.flush()
        sesion.add_all(
            [
                ProfesionalSede(profesional_id=perfil.id, sede_id=otra_sede.id, principal=True),
                ProfesionalSede(profesional_id=perfil.id, sede_id=sede.id, principal=False),
            ]
        )
        await conceder_permisos(
            sesion,
            usuario,
            clinica,
            "profesional.gestionar",
            sedes=(sede.id,),
            todas_las_especialidades=True,
            todos_los_profesionales=True,
            todos_los_pacientes=False,
        )
        headers = await cabecera_bearer(cliente, usuario, clinica)
        url = "/api/v1/profesionales/gestion"

        listado = await cliente.get(url, headers=headers)
        assert listado.status_code == 200, listado.text
        assert len(listado.json()) == 1
        assert listado.json()[0]["sede_ids"] == [str(sede.id)]
        assert listado.json()[0]["sede_principal_id"] is None
        original = await sesion.get(ProfesionalSede, (perfil.id, otra_sede.id))
        assert original is not None and original.principal is True

        editada = await cliente.put(
            f"{url}/{perfil.id}",
            json=_datos(especialidad.id, sede.id, nombre="Alex actualizado"),
            headers=headers,
        )
        assert editada.status_code == 200, editada.text
        assert editada.json()["sede_ids"] == [str(sede.id)]
        assert editada.json()["sede_principal_id"] is None
        original = await sesion.get(ProfesionalSede, (perfil.id, otra_sede.id))
        assert original is not None and original.principal is True

    async def test_rechaza_sin_permiso_sedes_fuera_de_clinica_y_datos_invalidos(
        self,
        cliente: AsyncClient,
        sesion: AsyncSession,
        usuario,
        clinica: Clinica,
        sede: Sede,
        otra_sede: Sede,
        especialidad,
    ) -> None:
        especialidad_id = especialidad.id
        sede_id = sede.id
        otra_sede_id = otra_sede.id
        headers_lectura = await cabecera_bearer(cliente, usuario, clinica)
        ruta = "/api/v1/profesionales/gestion"
        sin_permiso = await cliente.post(
            ruta,
            json=_datos(especialidad_id, sede_id),
            headers=headers_lectura,
        )
        assert sin_permiso.status_code == 403

        await self._cabeceras_completas(cliente, sesion, usuario, clinica, sede)
        headers = await cabecera_bearer(cliente, usuario, clinica)
        fuera_de_clinica = await cliente.post(
            ruta,
            json=_datos(especialidad_id, otra_sede_id),
            headers=headers,
        )
        assert fuera_de_clinica.status_code == 404

        registro_duplicado = await cliente.post(
            ruta,
            json=_datos(especialidad_id, sede_id, numero_registro_profesional="OD-TEST-001"),
            headers=headers,
        )
        assert registro_duplicado.status_code == 201, registro_duplicado.text
        repetido = await cliente.post(
            ruta,
            json=_datos(especialidad_id, sede_id, apellido="Otro"),
            headers=headers,
        )
        assert repetido.status_code == 409

        invalido = await cliente.post(
            ruta,
            json=_datos(
                especialidad_id,
                sede_id,
                sede_ids=[str(sede_id), str(sede_id)],
            ),
            headers=headers,
        )
        assert invalido.status_code == 422
