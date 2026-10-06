"""Consultas del recorrido del paciente, la derivación y la prolongación.

Hereda de `RepositorioAgenda` para usar **el mismo** filtro de ámbito que el
resto de la agenda: un recorrido es una vista de citas, y si tuviera su propio
filtro bastaría un descuido para que alguien viera el recorrido de pacientes
de una sede que no le corresponde.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.modulos.agenda.modelos import _ESTADOS_QUE_OCUPAN, Cita, CitaHistorial
from app.modulos.agenda.repositorio import RepositorioAgenda
from app.modulos.organizacion.modelos import Consultorio, Especialidad, Sede, Servicio
from app.modulos.pacientes.modelos import Paciente, RelacionAsistencial
from app.modulos.profesionales.modelos import Profesional, ProfesionalSede, ProfesionalServicio
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.autorizacion import Principal

ESTADOS_ACTIVOS = tuple(estado.value for estado in _ESTADOS_QUE_OCUPAN)


class RepositorioRecorrido(RepositorioAgenda):
    async def historial_de_paciente(
        self,
        paciente_id: uuid.UUID,
        *,
        principal: Principal,
        desde: datetime | None = None,
        limite: int = 300,
    ) -> list[tuple[CitaHistorial, Cita]]:
        """Eventos de todas las citas del paciente, en orden, dentro del ámbito."""
        consulta = (
            select(CitaHistorial, Cita)
            .join(Cita, Cita.id == CitaHistorial.cita_id)
            .where(Cita.paciente_id == paciente_id)
        )
        if desde is not None:
            consulta = consulta.where(CitaHistorial.ocurrido_en >= desde)
        consulta = self._filtrar_por_ambito(consulta, principal)
        consulta = consulta.order_by(CitaHistorial.ocurrido_en, CitaHistorial.id).limit(limite)
        return [(fila[0], fila[1]) for fila in (await self._sesion.execute(consulta)).all()]

    async def citas_que_chocan(self, cita: Cita, minutos: int) -> list[Cita]:
        """Citas activas que pisaría alargar `cita` `minutos` más.

        Se mira el mismo profesional y el mismo consultorio: son las dos
        restricciones de exclusión de la base de datos, y cualquiera de las
        dos rechazaría la prolongación.
        """
        nuevo_fin = cita.fin + timedelta(minutes=minutos)
        mismo_recurso = Cita.profesional_id == cita.profesional_id
        if cita.consultorio_id is not None:
            mismo_recurso = mismo_recurso | (Cita.consultorio_id == cita.consultorio_id)
        consulta = (
            select(Cita)
            .where(
                Cita.id != cita.id,
                Cita.clinica_id == cita.clinica_id,
                Cita.estado.in_(ESTADOS_ACTIVOS),
                Cita.inicio < nuevo_fin,
                Cita.fin > cita.fin,
                mismo_recurso,
            )
            .order_by(Cita.inicio)
        )
        return list((await self._sesion.execute(consulta)).scalars())

    async def profesionales_del_servicio(
        self, servicio_id: uuid.UUID, sede_id: uuid.UUID, clinica_id: uuid.UUID
    ) -> list[Profesional]:
        """Profesionales activos que prestan el servicio en la sede."""
        consulta = (
            select(Profesional)
            .join(ProfesionalServicio, ProfesionalServicio.profesional_id == Profesional.id)
            .join(ProfesionalSede, ProfesionalSede.profesional_id == Profesional.id)
            .where(
                ProfesionalServicio.servicio_id == servicio_id,
                ProfesionalSede.sede_id == sede_id,
                Profesional.clinica_id == clinica_id,
                Profesional.activo.is_(True),
            )
            .order_by(Profesional.apellido, Profesional.nombre)
        )
        return list((await self._sesion.execute(consulta)).scalars().unique())

    async def servicios_de_sede(
        self, sede_id: uuid.UUID, clinica_id: uuid.UUID
    ) -> list[tuple[Servicio, str]]:
        """Servicios que alguien presta en la sede, con su especialidad."""
        consulta = (
            select(Servicio, Especialidad.nombre)
            .join(Especialidad, Especialidad.id == Servicio.especialidad_id)
            .join(ProfesionalServicio, ProfesionalServicio.servicio_id == Servicio.id)
            .join(
                ProfesionalSede,
                ProfesionalSede.profesional_id == ProfesionalServicio.profesional_id,
            )
            .where(
                ProfesionalSede.sede_id == sede_id,
                Servicio.clinica_id == clinica_id,
                Servicio.activo.is_(True),
            )
            .distinct()
            .order_by(Especialidad.nombre, Servicio.nombre)
        )
        return [(fila[0], fila[1]) for fila in (await self._sesion.execute(consulta)).all()]

    async def nombres(
        self,
        *,
        profesionales: set[uuid.UUID],
        consultorios: set[uuid.UUID],
        sedes: set[uuid.UUID],
        servicios: set[uuid.UUID],
        usuarios: set[uuid.UUID],
    ) -> dict[uuid.UUID, str]:
        """Nombres legibles para pintar el recorrido, en pocas consultas."""
        nombres: dict[uuid.UUID, str] = {}
        if profesionales:
            filas = await self._sesion.execute(
                select(Profesional.id, Profesional.nombre, Profesional.apellido).where(
                    Profesional.id.in_(profesionales)
                )
            )
            nombres.update({i: f"{n} {a}".strip() for i, n, a in filas.all()})
        if usuarios:
            filas = await self._sesion.execute(
                select(Usuario.id, Usuario.nombre, Usuario.apellido).where(Usuario.id.in_(usuarios))
            )
            nombres.update({i: f"{n} {a}".strip() for i, n, a in filas.all()})
        for modelo, ids in ((Consultorio, consultorios), (Sede, sedes), (Servicio, servicios)):
            if ids:
                filas = await self._sesion.execute(
                    select(modelo.id, modelo.nombre).where(modelo.id.in_(ids))
                )
                nombres.update({fila[0]: str(fila[1]) for fila in filas.all()})
        return nombres

    async def especialidad_de_servicio(self, servicio_id: uuid.UUID) -> str | None:
        return (
            await self._sesion.execute(
                select(Especialidad.nombre)
                .join(Servicio, Servicio.especialidad_id == Especialidad.id)
                .where(Servicio.id == servicio_id)
            )
        ).scalar_one_or_none()

    async def nombre_de_paciente(self, paciente_id: uuid.UUID) -> str:
        fila = (
            await self._sesion.execute(
                select(Paciente.nombre, Paciente.apellido).where(Paciente.id == paciente_id)
            )
        ).first()
        return f"{fila[0]} {fila[1]}".strip() if fila else ""

    async def relacion_vigente(
        self, paciente_id: uuid.UUID, profesional_id: uuid.UUID, ahora: datetime
    ) -> bool:
        cantidad = (
            await self._sesion.execute(
                select(func.count()).where(
                    RelacionAsistencial.paciente_id == paciente_id,
                    RelacionAsistencial.profesional_id == profesional_id,
                    RelacionAsistencial.revocada_en.is_(None),
                    (RelacionAsistencial.vigente_hasta.is_(None))
                    | (RelacionAsistencial.vigente_hasta > ahora),
                )
            )
        ).scalar_one()
        return bool(cantidad)

    async def datos_aviso(self, cita: Cita) -> tuple[str, str, str, str] | None:
        """Nombre del paciente, sede, zona horaria y profesional para un aviso."""
        fila = (
            await self._sesion.execute(
                select(
                    Paciente.nombre,
                    Sede.nombre,
                    Sede.zona_horaria,
                    Profesional.nombre,
                    Profesional.apellido,
                )
                .select_from(Cita)
                .join(Paciente, Paciente.id == Cita.paciente_id)
                .join(Sede, Sede.id == Cita.sede_id)
                .join(Profesional, Profesional.id == Cita.profesional_id)
                .where(Cita.id == cita.id)
            )
        ).first()
        if fila is None:
            return None
        nombre, sede, zona, prof_nombre, prof_apellido = fila
        return (
            nombre or "",
            sede or "",
            zona or "America/Guayaquil",
            f"{prof_nombre} {prof_apellido}".strip(),
        )

    async def eventos_de_cita(self, cita_id: uuid.UUID) -> list[CitaHistorial]:
        return list(
            (
                await self._sesion.execute(
                    select(CitaHistorial)
                    .where(CitaHistorial.cita_id == cita_id)
                    .order_by(CitaHistorial.ocurrido_en, CitaHistorial.id)
                )
            ).scalars()
        )

    async def solicitudes_de_prolongacion(
        self, *, principal: Principal, desde: datetime
    ) -> list[tuple[CitaHistorial, Cita]]:
        """Solicitudes de prolongación recientes (se filtran las resueltas después)."""
        consulta = (
            select(CitaHistorial, Cita)
            .join(Cita, Cita.id == CitaHistorial.cita_id)
            .where(
                CitaHistorial.ocurrido_en >= desde,
                CitaHistorial.metadatos["evento"].astext.in_(
                    ("PROLONGACION_SOLICITADA", "PROLONGACION_APLICADA", "PROLONGACION_RECHAZADA")
                ),
            )
        )
        consulta = self._filtrar_por_ambito(consulta, principal).order_by(CitaHistorial.ocurrido_en)
        return [(fila[0], fila[1]) for fila in (await self._sesion.execute(consulta)).all()]


__all__ = ["ESTADOS_ACTIVOS", "RepositorioRecorrido"]
