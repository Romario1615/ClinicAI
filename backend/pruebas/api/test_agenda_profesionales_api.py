"""Administración de horarios individuales del equipo clínico."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.modelos import Auditoria
from app.modulos.organizacion.modelos import Clinica, Sede, Servicio
from app.modulos.profesionales.modelos import Profesional, ProfesionalSede
from app.modulos.usuarios.modelos import AmbitoAsignacion, Usuario, UsuarioRol
from app.nucleo.auditoria import AccionAuditada
from app.nucleo.autorizacion import TipoAmbito
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


def _datos(**cambios: object) -> dict[str, object]:
    return {
        "dia_semana": 1,
        "hora_inicio": "08:00",
        "hora_fin": "12:00",
        "granularidad_minutos": 20,
        "vigente_desde": None,
        "vigente_hasta": None,
        **cambios,
    }


class TestAgendaProfesionales:
    async def _contexto(
        self,
        cliente: AsyncClient,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        profesional: Profesional,
        *,
        alcance_completo: bool = True,
        alcance_especialidad: bool = True,
    ) -> tuple[dict[str, str], str]:
        sesion.add(ProfesionalSede(profesional_id=profesional.id, sede_id=sede.id))
        rol = await conceder_permisos(
            sesion,
            usuario,
            clinica,
            "agenda.configurar",
            "agenda.leer",
            sedes=(sede.id,),
            todas_las_especialidades=alcance_especialidad,
            todos_los_profesionales=alcance_completo,
            todos_los_pacientes=False,
        )
        if not alcance_completo:
            await sesion.flush()
            asignacion = (
                await sesion.execute(
                    select(UsuarioRol).where(
                        UsuarioRol.usuario_id == usuario.id,
                        UsuarioRol.rol_id == rol.id,
                    )
                )
            ).scalar_one()
            sesion.add(
                AmbitoAsignacion(
                    usuario_rol_id=asignacion.id,
                    tipo=TipoAmbito.PROFESIONAL.value,
                    valor_id=profesional.id,
                )
            )
        await sesion.flush()
        headers = await cabecera_bearer(cliente, usuario, clinica)
        return headers, f"/api/v1/profesionales/{profesional.id}/agenda?sede_id={sede.id}"

    async def test_crea_lista_modifica_y_elimina_franjas_auditadas(
        self,
        cliente: AsyncClient,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        profesional: Profesional,
    ) -> None:
        headers, ruta = await self._contexto(cliente, sesion, usuario, clinica, sede, profesional)
        alta = await cliente.post(ruta, json=_datos(), headers=headers)
        assert alta.status_code == 201, alta.text
        plantilla = alta.json()
        assert plantilla["profesional_id"] == str(profesional.id)
        assert plantilla["hora_inicio"] == "08:00:00"

        listado = await cliente.get(ruta, headers=headers)
        assert listado.status_code == 200
        assert [fila["id"] for fila in listado.json()] == [plantilla["id"]]

        editada = await cliente.put(
            f"{ruta.split('?')[0]}/{plantilla['id']}?{ruta.split('?')[1]}",
            json=_datos(hora_inicio="09:00", hora_fin="13:00", granularidad_minutos=30),
            headers=headers,
        )
        assert editada.status_code == 200, editada.text
        assert editada.json()["hora_inicio"] == "09:00:00"
        assert editada.json()["granularidad_minutos"] == 30

        eliminada = await cliente.delete(
            f"{ruta.split('?')[0]}/{plantilla['id']}?{ruta.split('?')[1]}",
            headers=headers,
        )
        assert eliminada.status_code == 204
        acciones = list(
            (
                await sesion.execute(
                    select(Auditoria.accion).where(
                        Auditoria.entidad_id == uuid.UUID(plantilla["id"])
                    )
                )
            ).scalars()
        )
        assert acciones.count(AccionAuditada.AGENDA_PROFESIONAL_MODIFICADA.value) == 3

    async def test_rechaza_solapamientos_vigencias_invalidas_y_sede_ajena(
        self,
        cliente: AsyncClient,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        otra_sede: Sede,
        profesional: Profesional,
    ) -> None:
        headers, ruta = await self._contexto(cliente, sesion, usuario, clinica, sede, profesional)
        assert (await cliente.post(ruta, json=_datos(), headers=headers)).status_code == 201
        solapada = await cliente.post(
            ruta,
            json=_datos(hora_inicio="11:00", hora_fin="14:00"),
            headers=headers,
        )
        assert solapada.status_code == 409
        invalida = await cliente.post(
            ruta,
            json=_datos(hora_inicio="14:00", hora_fin="14:00"),
            headers=headers,
        )
        assert invalida.status_code == 422
        ajena = await cliente.get(ruta.replace(str(sede.id), str(otra_sede.id)), headers=headers)
        assert ajena.status_code == 404

    async def test_el_alcance_limitado_solo_permite_su_profesional(
        self,
        cliente: AsyncClient,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        profesional: Profesional,
    ) -> None:
        headers, ruta = await self._contexto(
            cliente,
            sesion,
            usuario,
            clinica,
            sede,
            profesional,
            alcance_completo=False,
        )
        assert (await cliente.post(ruta, json=_datos(), headers=headers)).status_code == 201

    async def test_tambien_restringe_por_especialidad(
        self,
        cliente: AsyncClient,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        profesional: Profesional,
    ) -> None:
        headers, ruta = await self._contexto(
            cliente,
            sesion,
            usuario,
            clinica,
            sede,
            profesional,
            alcance_completo=False,
            alcance_especialidad=False,
        )
        assert (await cliente.post(ruta, json=_datos(), headers=headers)).status_code == 404

    async def test_la_franga_guardada_se_usa_al_calcular_disponibilidad(
        self,
        cliente: AsyncClient,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        profesional: Profesional,
        servicio: Servicio,
    ) -> None:
        headers, ruta = await self._contexto(cliente, sesion, usuario, clinica, sede, profesional)
        creada = await cliente.post(
            ruta,
            json=_datos(hora_inicio="08:00", hora_fin="12:00", granularidad_minutos=30),
            headers=headers,
        )
        assert creada.status_code == 201, creada.text
        disponibilidad = await cliente.get(
            "/api/v1/agenda/disponibilidad",
            params={
                "profesional_id": str(profesional.id),
                "servicio_id": str(servicio.id),
                "sede_id": str(sede.id),
                "desde": "2035-04-09T13:00:00Z",
                "hasta": "2035-04-09T17:00:00Z",
            },
            headers=headers,
        )
        assert disponibilidad.status_code == 200, disponibilidad.text
        turnos = disponibilidad.json()["turnos"]
        assert turnos
        assert turnos[0]["inicio"] == "2035-04-09T08:00:00-05:00"

    async def test_crear_agenda_no_se_autoriza_solo_con_agenda_leer(
        self,
        cliente: AsyncClient,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        profesional: Profesional,
    ) -> None:
        sesion.add(ProfesionalSede(profesional_id=profesional.id, sede_id=sede.id))
        await conceder_permisos(
            sesion,
            usuario,
            clinica,
            "agenda.leer",
            sedes=(sede.id,),
            todos_los_profesionales=True,
            todos_los_pacientes=False,
        )
        await sesion.flush()
        headers = await cabecera_bearer(cliente, usuario, clinica)
        ruta = f"/api/v1/profesionales/{profesional.id}/agenda?sede_id={sede.id}"
        respuesta = await cliente.post(ruta, json=_datos(), headers=headers)
        assert respuesta.status_code == 403
