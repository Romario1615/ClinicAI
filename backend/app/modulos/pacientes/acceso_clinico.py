"""Guardia comun para los modulos clinicos nuevos (imagenes, odontologia).

Las tres capas de `historia/rutas.py`, en un solo sitio
-------------------------------------------------------
1. **Quien**: el agente de IA nunca pasa (CLAUDE.md, regla 5), aunque alguien
   le anadiera una herramienta por error. Despues, el permiso.
2. **Sobre quien**: el paciente tiene que existir dentro del ambito del
   principal. Fuera de ambito responde 404, igual que si no existiera.
3. **Con que vinculo**: si el principal es profesional, hace falta una
   relacion asistencial vigente con ESE paciente.

Se repite el criterio de `ServicioHistoria._exigir_relacion`: la relacion se
exige al profesional; el resto del personal clinico (asistente) queda
acotado por permiso, ambito y auditoria.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.pacientes.modelos import Paciente, RelacionAsistencial
from app.modulos.pacientes.repositorio import RepositorioPacientes
from app.nucleo.autorizacion import Principal
from app.nucleo.errores import (
    OperacionClinicaNoPermitida,
    PermisoDenegado,
    RecursoNoEncontrado,
    RelacionAsistencialRequerida,
)


class GuardiaClinica:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion
        self._pacientes = RepositorioPacientes(sesion)

    @staticmethod
    def exigir(principal: Principal, permiso: str) -> None:
        if principal.es_agente:
            raise OperacionClinicaNoPermitida(
                "El asistente automatico no accede a informacion clinica."
            )
        if not principal.tiene_permiso(permiso):
            raise PermisoDenegado("No tiene permiso para esta operacion.")

    async def paciente(self, principal: Principal, paciente_id: uuid.UUID) -> Paciente:
        paciente = await self._pacientes.obtener(paciente_id, principal)
        if paciente is None:
            raise RecursoNoEncontrado("El paciente solicitado no existe.")
        return paciente

    async def exigir_relacion(
        self, principal: Principal, paciente_id: uuid.UUID, ahora: datetime
    ) -> None:
        if principal.profesional_id is None:
            return
        consulta = select(literal(1)).where(
            RelacionAsistencial.paciente_id == paciente_id,
            RelacionAsistencial.profesional_id == principal.profesional_id,
            RelacionAsistencial.revocada_en.is_(None),
            or_(
                RelacionAsistencial.vigente_hasta.is_(None),
                RelacionAsistencial.vigente_hasta > ahora,
            ),
        )
        if (await self._sesion.execute(consulta.limit(1))).first() is None:
            raise RelacionAsistencialRequerida(
                "No tiene una relacion asistencial vigente con este paciente."
            )

    async def acceso_clinico(
        self, principal: Principal, paciente_id: uuid.UUID, permiso: str, ahora: datetime
    ) -> Paciente:
        """Las tres capas en orden. Devuelve el paciente."""
        self.exigir(principal, permiso)
        paciente = await self.paciente(principal, paciente_id)
        await self.exigir_relacion(principal, paciente_id, ahora)
        return paciente


__all__ = ["GuardiaClinica"]
