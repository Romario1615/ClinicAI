from __future__ import annotations

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita
from app.modulos.agenda.repositorio import RepositorioAgenda
from app.modulos.odontologia.periodontograma_modelos import Periodontograma
from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.pacientes.modelos import Paciente
from app.modulos.profesionales.ambito_clinico import autores_en_ambito
from app.modulos.profesionales.modelos import Profesional
from app.nucleo.autorizacion import Principal


class RepositorioPeriodontograma:
    def __init__(self, sesion: AsyncSession):
        self.sesion = sesion

    def consulta(
        self, principal: Principal, paciente_id: uuid.UUID
    ) -> Select[tuple[Periodontograma]]:
        consulta = select(Periodontograma).where(
            Periodontograma.clinica_id == principal.clinica_id,
            Periodontograma.paciente_id == paciente_id,
            Periodontograma.profesional_id.in_(autores_en_ambito(principal, "periodoncia")),
        )
        if not principal.tiene_permiso("historia_clinica.leer_sensible"):
            consulta = consulta.where(Periodontograma.nivel_sensibilidad != "N3")
        if not principal.ambito.todas_las_sedes:
            consulta = consulta.where(Periodontograma.sede_id.in_(principal.ambito.sedes))
        return consulta

    async def listar(self, principal: Principal, paciente_id: uuid.UUID) -> list[Periodontograma]:
        return list(
            (
                await self.sesion.scalars(
                    self.consulta(principal, paciente_id)
                    .order_by(
                        Periodontograma.fecha_examen.desc(),
                        Periodontograma.creado_en.desc(),
                        Periodontograma.version.desc(),
                    )
                    .limit(500)
                )
            ).all()
        )

    async def obtener(
        self, principal: Principal, paciente_id: uuid.UUID, id_registro: uuid.UUID
    ) -> Periodontograma | None:
        return (
            await self.sesion.execute(
                self.consulta(principal, paciente_id).where(Periodontograma.id == id_registro)
            )
        ).scalar_one_or_none()

    async def ultima_version(self, raiz_id: uuid.UUID) -> int:
        return int(
            await self.sesion.scalar(
                select(func.max(Periodontograma.version)).where(Periodontograma.raiz_id == raiz_id)
            )
            or 0
        )

    async def bloquear_paciente(self, paciente_id: uuid.UUID) -> None:
        await self.sesion.execute(
            select(Paciente.id).where(Paciente.id == paciente_id).with_for_update()
        )

    async def id_ocupado(self, id_registro: uuid.UUID) -> bool:
        return await self.sesion.get(Periodontograma, id_registro) is not None

    async def agregar(self, fila: Periodontograma) -> None:
        self.sesion.add(fila)
        await self.sesion.flush()

    async def profesional(self, id_registro: uuid.UUID) -> Profesional | None:
        return await self.sesion.get(Profesional, id_registro)

    async def zona(self, clinica_id: uuid.UUID | None) -> str:
        return str(
            await self.sesion.scalar(select(Clinica.zona_horaria).where(Clinica.id == clinica_id))
            or "America/Guayaquil"
        )

    async def sede(self, principal: Principal, id_registro: uuid.UUID) -> Sede | None:
        return (
            await self.sesion.execute(
                select(Sede).where(
                    Sede.id == id_registro,
                    Sede.clinica_id == principal.clinica_id,
                    Sede.anulado_en.is_(None),
                )
            )
        ).scalar_one_or_none()

    async def cita(self, principal: Principal, id_registro: uuid.UUID) -> Cita | None:
        return await RepositorioAgenda(self.sesion).obtener_cita(id_registro, principal=principal)
