"""Gestión de vacaciones, ausencias, mantenimiento y cierres de agenda."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import BloqueoAgenda, Cita
from app.modulos.auditoria.modelos import Auditoria
from app.modulos.organizacion.modelos import Clinica, Sede, Servicio
from app.modulos.pacientes.modelos import Paciente
from app.modulos.profesionales.modelos import Profesional, ProfesionalSede
from app.modulos.usuarios.modelos import AmbitoAsignacion, Usuario, UsuarioRol
from app.nucleo.auditoria import AccionAuditada
from app.nucleo.autorizacion import TipoAmbito
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


def _cuerpo(sede: Sede, **cambios: object) -> dict[str, object]:
    return {
        "sede_id": str(sede.id),
        "tipo": "MANTENIMIENTO",
        "inicio": "2035-04-12T14:00:00Z",
        "fin": "2035-04-12T16:00:00Z",
        "motivo": "Mantenimiento programado",
        **cambios,
    }


async def _cabeceras(
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    cliente: AsyncClient,
) -> dict[str, str]:
    await conceder_permisos(sesion, usuario, clinica, "bloqueo.gestionar", sedes=(sede.id,))
    return await cabecera_bearer(cliente, usuario, clinica)


class TestBloqueosAgenda:
    async def test_crea_lista_edita_y_elimina_bloqueo_con_auditoria(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
    ) -> None:
        headers = await _cabeceras(sesion, usuario, clinica, sede, cliente)
        ruta = f"{api}/agenda/bloqueos"
        creado = await cliente.post(ruta, json=_cuerpo(sede), headers=headers)
        assert creado.status_code == 201, creado.text
        bloqueo = creado.json()
        assert bloqueo["tipo"] == "MANTENIMIENTO"
        assert bloqueo["creado_con_citas_afectadas"] is False

        listado = await cliente.get(
            ruta,
            params={
                "sede_id": str(sede.id),
                "desde": "2035-04-12T00:00:00Z",
                "hasta": "2035-04-13T00:00:00Z",
            },
            headers=headers,
        )
        assert listado.status_code == 200
        assert [fila["id"] for fila in listado.json()] == [bloqueo["id"]]

        actualizado = await cliente.put(
            f"{ruta}/{bloqueo['id']}",
            json=_cuerpo(sede, tipo="CAPACITACION", motivo="Capacitación del equipo"),
            headers=headers,
        )
        assert actualizado.status_code == 200, actualizado.text
        assert actualizado.json()["tipo"] == "CAPACITACION"

        eliminado = await cliente.delete(f"{ruta}/{bloqueo['id']}", headers=headers)
        assert eliminado.status_code == 204
        acciones = list(
            (
                await sesion.execute(
                    select(Auditoria.accion).where(Auditoria.entidad_id == bloqueo["id"])
                )
            ).scalars()
        )
        assert acciones.count(AccionAuditada.BLOQUEO_AGENDA_CREADO.value) == 1
        assert acciones.count(AccionAuditada.BLOQUEO_AGENDA_MODIFICADO.value) == 1
        assert acciones.count(AccionAuditada.BLOQUEO_AGENDA_ELIMINADO.value) == 1

    async def test_advierte_citas_afectadas_y_exige_confirmacion_explicita(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        paciente: Paciente,
        profesional: Profesional,
        servicio: Servicio,
    ) -> None:
        cita = Cita(
            clinica_id=clinica.id,
            sede_id=sede.id,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            servicio_id=servicio.id,
            inicio=datetime(2035, 4, 12, 14, 30, tzinfo=UTC),
            duracion_minutos=30,
            minutos_preparacion=0,
            estado="CONFIRMED",
        )
        sesion.add(cita)
        await sesion.flush()
        headers = await _cabeceras(sesion, usuario, clinica, sede, cliente)
        ruta = f"{api}/agenda/bloqueos"

        advertencia = await cliente.post(ruta, json=_cuerpo(sede), headers=headers)
        assert advertencia.status_code == 409, advertencia.text
        citas = advertencia.json()["detalles"]["citas_afectadas"]
        assert len(citas) == 1
        assert citas[0]["id"] == str(cita.id)
        assert "nombre" not in citas[0]

        confirmado = await cliente.post(
            ruta,
            json=_cuerpo(sede, aceptar_citas_afectadas=True),
            headers=headers,
        )
        assert confirmado.status_code == 201, confirmado.text
        assert confirmado.json()["creado_con_citas_afectadas"] is True
        registro = await sesion.get(BloqueoAgenda, confirmado.json()["id"])
        assert registro is not None
        assert registro.creado_con_citas_afectadas is True

    async def test_fuera_del_ambito_y_entradas_invalidas_se_rechazan(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        otra_sede: Sede,
    ) -> None:
        headers = await _cabeceras(sesion, usuario, clinica, sede, cliente)
        ruta = f"{api}/agenda/bloqueos"
        fuera = await cliente.post(ruta, json=_cuerpo(otra_sede), headers=headers)
        assert fuera.status_code == 404

        sin_zona = await cliente.post(
            ruta,
            json=_cuerpo(sede, inicio="2035-04-12T14:00:00", fin="2035-04-12T16:00:00"),
            headers=headers,
        )
        assert sin_zona.status_code == 422

        sin_recurso = await cliente.post(
            ruta,
            json=_cuerpo(sede, profesional_id="523ba8b4-294d-46f8-9e88-65ee8a165db4"),
            headers=headers,
        )
        assert sin_recurso.status_code == 404

    async def test_no_requiere_cita_crear_para_gestionar_bloqueos(
        self,
        cliente: AsyncClient,
        api: str,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
    ) -> None:
        headers = await cabecera_bearer(cliente, usuario, clinica)
        respuesta = await cliente.post(
            f"{api}/agenda/bloqueos", json=_cuerpo(sede), headers=headers
        )
        assert respuesta.status_code == 403

    async def test_ambito_limitado_solo_permite_bloquear_profesional_asignado(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        profesional: Profesional,
    ) -> None:
        sesion.add(ProfesionalSede(profesional_id=profesional.id, sede_id=sede.id))
        await sesion.flush()
        rol = await conceder_permisos(
            sesion,
            usuario,
            clinica,
            "bloqueo.gestionar",
            sedes=(sede.id,),
            todos_los_profesionales=False,
            todos_los_pacientes=False,
        )
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
        ruta = f"{api}/agenda/bloqueos"

        propio = await cliente.post(
            ruta,
            json=_cuerpo(sede, profesional_id=str(profesional.id)),
            headers=headers,
        )
        assert propio.status_code == 201, propio.text
        sede_completa = await cliente.post(ruta, json=_cuerpo(sede), headers=headers)
        assert sede_completa.status_code == 404
