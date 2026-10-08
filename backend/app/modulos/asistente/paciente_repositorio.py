import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita
from app.modulos.agenda.repositorio import RepositorioAgenda
from app.modulos.asistente.paciente_modelos import SesionAgentePaciente
from app.modulos.pacientes.modelos import Paciente
from app.modulos.pacientes.repositorio import RepositorioPacientes
from app.nucleo.autorizacion import Principal


class RepositorioAgentePaciente:
    def __init__(self, sesion: AsyncSession):
        self.sesion = sesion

    async def paciente(self, principal: Principal, id_paciente: uuid.UUID) -> Paciente | None:
        return await RepositorioPacientes(self.sesion).obtener(id_paciente, principal)

    async def hilo(
        self, principal: Principal, paciente_id: uuid.UUID, id_hilo: uuid.UUID, ahora: datetime
    ) -> SesionAgentePaciente | None:
        return (
            await self.sesion.execute(
                select(SesionAgentePaciente)
                .where(
                    SesionAgentePaciente.id == id_hilo,
                    SesionAgentePaciente.clinica_id == principal.clinica_id,
                    SesionAgentePaciente.usuario_id == principal.actor_id,
                    SesionAgentePaciente.paciente_id == paciente_id,
                    SesionAgentePaciente.expira_en > ahora,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    async def cita(
        self, principal: Principal, paciente_id: uuid.UUID, cita_id: uuid.UUID
    ) -> Cita | None:
        return (
            await self.sesion.execute(
                RepositorioAgenda(self.sesion)
                .consulta_autorizada(principal)
                .where(
                    Cita.id == cita_id,
                    Cita.paciente_id == paciente_id,
                )
            )
        ).scalar_one_or_none()

    async def agregar(self, fila: SesionAgentePaciente) -> None:
        self.sesion.add(fila)
        await self.sesion.flush()

    async def zona(self, sede_id: uuid.UUID) -> str:
        return await RepositorioAgenda(self.sesion).obtener_zona_horaria(sede_id)
