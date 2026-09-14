import uuid
from typing import Any, cast

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.lista_espera.modelos import EntradaListaEspera, OfertaTurno
from app.modulos.organizacion.repositorio import RepositorioCatalogo
from app.modulos.pacientes.repositorio import RepositorioPacientes
from app.nucleo.autorizacion import Principal
from app.nucleo.errores import RecursoNoEncontrado


class RepositorioListaEspera:
    def __init__(self, sesion: AsyncSession) -> None:
        self.sesion = sesion

    def consulta(self, principal: Principal) -> Select[Any]:
        e = EntradaListaEspera
        consulta = select(e).where(e.clinica_id == (principal.clinica_id or uuid.UUID(int=0)))
        ambito = principal.ambito
        for columna, todos, valores in (
            (e.sede_id, ambito.todas_las_sedes, ambito.sedes),
            (e.especialidad_id, ambito.todas_las_especialidades, ambito.especialidades),
            (e.profesional_id, ambito.todos_los_profesionales, ambito.profesionales),
            (e.paciente_id, ambito.todos_los_pacientes, ambito.pacientes),
        ):
            if not todos:
                consulta = consulta.where(columna.in_(valores))
        return consulta

    async def obtener(self, entrada_id: uuid.UUID, principal: Principal) -> EntradaListaEspera:
        entrada = (
            await self.sesion.execute(
                self.consulta(principal).where(EntradaListaEspera.id == entrada_id)
            )
        ).scalar_one_or_none()
        if entrada is None:
            raise RecursoNoEncontrado("La entrada solicitada no existe.")
        return cast(EntradaListaEspera, entrada)

    async def oferta(self, oferta_id: uuid.UUID, principal: Principal) -> OfertaTurno:
        entradas = self.consulta(principal).subquery()
        oferta = (
            await self.sesion.execute(
                select(OfertaTurno)
                .where(
                    OfertaTurno.id == oferta_id,
                    OfertaTurno.lista_espera_id.in_(select(entradas.c.id)),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if oferta is None:
            raise RecursoNoEncontrado("La oferta solicitada no existe.")
        return oferta

    async def validar_alta(
        self,
        principal: Principal,
        paciente_id: uuid.UUID,
        sede_id: uuid.UUID,
        especialidad_id: uuid.UUID,
        servicio_id: uuid.UUID | None,
        profesional_id: uuid.UUID | None,
    ) -> None:
        catalogo = RepositorioCatalogo(self.sesion)
        if await RepositorioPacientes(self.sesion).obtener(paciente_id, principal) is None:
            raise RecursoNoEncontrado("El paciente solicitado no existe.")
        if sede_id not in {s.id for s in await catalogo.listar_sedes(principal)}:
            raise RecursoNoEncontrado("La sede solicitada no existe.")
        if especialidad_id not in {e.id for e in await catalogo.listar_especialidades(principal)}:
            raise RecursoNoEncontrado("La especialidad solicitada no existe.")
        if servicio_id and servicio_id not in {
            s.id
            for s in await catalogo.listar_servicios(principal, especialidad_id=especialidad_id)
        }:
            raise RecursoNoEncontrado("El servicio solicitado no existe.")
        if not profesional_id and not principal.ambito.todos_los_profesionales:
            raise RecursoNoEncontrado("Seleccione un profesional autorizado.")
        if profesional_id and profesional_id not in {
            p.id
            for p in await catalogo.listar_profesionales(
                principal, especialidad_id=especialidad_id, sede_id=sede_id
            )
        }:
            raise RecursoNoEncontrado("El profesional solicitado no existe.")
