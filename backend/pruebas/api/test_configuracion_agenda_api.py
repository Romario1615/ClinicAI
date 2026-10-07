"""Gestión administrativa de horarios, pausas y feriados por sede."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.modelos import Auditoria
from app.modulos.organizacion.modelos import Clinica, Feriado, HorarioAtencion, Sede
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.auditoria import AccionAuditada
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


class TestConfiguracionAgenda:
    async def test_administra_horario_descanso_y_auditoria(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
    ) -> None:
        # La sede de prueba arranca deliberadamente abierta todo el día; deja
        # libre el lunes para probar alta y control de solapamientos.
        await sesion.execute(
            delete(HorarioAtencion).where(
                HorarioAtencion.propietario_tipo == "SEDE",
                HorarioAtencion.propietario_id == sede.id,
                HorarioAtencion.dia_semana == 1,
            )
        )
        await conceder_permisos(sesion, usuario, clinica, "agenda.configurar", sedes=(sede.id,))
        headers = await cabecera_bearer(cliente, usuario, clinica)
        datos = {
            "dia_semana": 1,
            "hora_inicio": "00:00",
            "hora_fin": "03:00",
            "granularidad_minutos": 20,
            "descansos": [{"hora_inicio": "01:00", "hora_fin": "02:00", "motivo": "Pausa"}],
        }

        creado = await cliente.post(
            f"{api}/configuracion/agenda/sedes/{sede.id}/horarios",
            json=datos,
            headers=headers,
        )

        assert creado.status_code == 201, creado.text
        horario = creado.json()
        assert horario["descansos"][0]["motivo"] == "Pausa"
        listado = await cliente.get(
            f"{api}/configuracion/agenda/sedes/{sede.id}/horarios", headers=headers
        )
        assert listado.status_code == 200
        assert horario["id"] in [item["id"] for item in listado.json()]

        actualizado = await cliente.put(
            f"{api}/configuracion/agenda/horarios/{horario['id']}",
            json={**datos, "hora_fin": "04:00", "descansos": []},
            headers=headers,
        )
        assert actualizado.status_code == 200, actualizado.text
        assert actualizado.json()["hora_fin"].startswith("04:00")

        duplicado = await cliente.post(
            f"{api}/configuracion/agenda/sedes/{sede.id}/horarios",
            json=datos,
            headers=headers,
        )
        assert duplicado.status_code == 409

        eliminado = await cliente.delete(
            f"{api}/configuracion/agenda/horarios/{horario['id']}", headers=headers
        )
        assert eliminado.status_code == 204, eliminado.text
        acciones = list(
            (
                await sesion.execute(
                    select(Auditoria.accion).where(Auditoria.entidad_id == uuid.UUID(horario["id"]))
                )
            ).scalars()
        )
        assert acciones.count(AccionAuditada.HORARIO_MODIFICADO.value) == 3

    async def test_falla_si_el_descanso_sale_de_la_franja(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
    ) -> None:
        await conceder_permisos(sesion, usuario, clinica, "agenda.configurar", sedes=(sede.id,))
        headers = await cabecera_bearer(cliente, usuario, clinica)
        respuesta = await cliente.post(
            f"{api}/configuracion/agenda/sedes/{sede.id}/horarios",
            json={
                "dia_semana": 2,
                "hora_inicio": "08:00",
                "hora_fin": "17:00",
                "descansos": [{"hora_inicio": "16:30", "hora_fin": "17:30"}],
            },
            headers=headers,
        )
        assert respuesta.status_code == 422

    async def test_feriados_completos_parciales_y_solapados(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
    ) -> None:
        await conceder_permisos(sesion, usuario, clinica, "agenda.configurar", sedes=(sede.id,))
        headers = await cabecera_bearer(cliente, usuario, clinica)
        ruta = f"{api}/configuracion/agenda/feriados"
        fecha = "2032-08-10"
        primer = await cliente.post(
            ruta,
            json={
                "sede_id": str(sede.id),
                "fecha": fecha,
                "nombre": "Capacitación",
                "hora_inicio": "12:00",
                "hora_fin": "14:00",
            },
            headers=headers,
        )
        assert primer.status_code == 201, primer.text
        duplicado = await cliente.post(
            ruta,
            json={
                "sede_id": str(sede.id),
                "fecha": fecha,
                "nombre": "Otro cierre",
                "hora_inicio": "13:00",
                "hora_fin": "15:00",
            },
            headers=headers,
        )
        assert duplicado.status_code == 409
        listado = await cliente.get(
            ruta, params={"desde": fecha, "hasta": fecha, "sede_id": str(sede.id)}, headers=headers
        )
        assert listado.status_code == 200
        assert len(listado.json()) == 1
        editado = await cliente.put(
            f"{ruta}/{primer.json()['id']}",
            json={
                "sede_id": str(sede.id),
                "fecha": fecha,
                "nombre": "Capacitación anual",
                "recurrente_anual": True,
            },
            headers=headers,
        )
        assert editado.status_code == 200, editado.text
        assert editado.json()["recurrente_anual"] is True
        eliminado = await cliente.delete(f"{ruta}/{primer.json()['id']}", headers=headers)
        assert eliminado.status_code == 204

    async def test_sin_permiso_o_fuera_del_ambito_no_accede(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
    ) -> None:
        headers = await cabecera_bearer(cliente, usuario, clinica)
        denegado = await cliente.get(
            f"{api}/configuracion/agenda/sedes/{sede.id}/horarios", headers=headers
        )
        assert denegado.status_code == 403

        await conceder_permisos(sesion, usuario, clinica, "agenda.configurar")
        fuera = await cliente.get(
            f"{api}/configuracion/agenda/sedes/{sede.id}/horarios", headers=headers
        )
        assert fuera.status_code == 404

    async def test_administra_feriado_de_toda_la_clinica_con_ambito_completo(
        self,
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
            "agenda.configurar",
            todas_las_sedes=True,
        )
        headers = await cabecera_bearer(cliente, usuario, clinica)
        ruta = f"{api}/configuracion/agenda/feriados"
        creado = await cliente.post(
            ruta,
            json={"fecha": "2034-01-01", "nombre": "Año nuevo", "recurrente_anual": True},
            headers=headers,
        )
        assert creado.status_code == 201, creado.text
        eliminado = await cliente.delete(f"{ruta}/{creado.json()['id']}", headers=headers)
        assert eliminado.status_code == 204

    async def test_un_ambito_de_sede_no_puede_borrar_feriado_global(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
    ) -> None:
        feriado = Feriado(
            clinica_id=clinica.id,
            sede_id=None,
            fecha=date(2035, 1, 1),
            nombre="Cierre general",
        )
        sesion.add(feriado)
        await sesion.flush()
        await conceder_permisos(sesion, usuario, clinica, "agenda.configurar", sedes=(sede.id,))
        headers = await cabecera_bearer(cliente, usuario, clinica)
        eliminado = await cliente.delete(
            f"{api}/configuracion/agenda/feriados/{feriado.id}", headers=headers
        )
        assert eliminado.status_code == 404
