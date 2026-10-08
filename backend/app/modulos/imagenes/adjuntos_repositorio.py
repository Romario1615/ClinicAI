from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, false, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.ia.recuperador import contexto_desde_principal
from app.modulos.agenda.modelos import Cita
from app.modulos.agenda.repositorio import RepositorioAgenda
from app.modulos.conocimiento.modelos import KnowledgeDocument
from app.modulos.conocimiento.repositorio import condicion_acl_documento
from app.modulos.documentos.modelos import RegistroPaciente
from app.modulos.gastos.modelos import Gasto
from app.modulos.gastos.repositorio import RepositorioGastos
from app.modulos.historia.modelos import (
    NotaEvolucion,
    PlantillaAnamnesis,
    Receta,
    RespuestaAnamnesis,
)
from app.modulos.imagenes.adjuntos_modelos import FotoRegistro
from app.modulos.odontologia.modelos import (
    Formulario033,
    Odontograma,
    PlanTratamiento,
    RegistroPlaca,
)
from app.modulos.odontologia.periodontograma_modelos import Periodontograma
from app.modulos.organizacion.modelos import Clinica, Consultorio, Especialidad, Sede, Servicio
from app.modulos.pacientes.modelos import Paciente
from app.modulos.pacientes.repositorio import RepositorioPacientes
from app.modulos.pagos.modelos import Pago
from app.modulos.profesionales.ambito_clinico import autores_en_ambito
from app.modulos.profesionales.modelos import Profesional
from app.modulos.promociones.modelos import CampanaPromocion
from app.modulos.usuarios.modelos import Rol, Usuario
from app.nucleo.autorizacion import NivelSensibilidad, Principal
from app.nucleo.bd import Base


@dataclass(frozen=True)
class DestinoFoto:
    modelo: type[Base]
    leer: tuple[str, ...]
    escribir: tuple[str, ...]
    modulo: str | None = None
    clinico: bool = False


DESTINOS = {
    "clinica": DestinoFoto(
        Clinica, ("clinica.leer", "configuracion.escribir"), ("clinica.escribir",)
    ),
    "usuario": DestinoFoto(Usuario, ("usuario.leer",), ("usuario.editar", "usuario.crear")),
    "rol": DestinoFoto(Rol, ("usuario.leer",), ("rol.asignar",)),
    "profesional": DestinoFoto(Profesional, ("profesional.gestionar",), ("profesional.gestionar",)),
    "sede": DestinoFoto(Sede, ("sede.gestionar",), ("sede.gestionar",)),
    "especialidad": DestinoFoto(
        Especialidad, ("especialidad.gestionar",), ("especialidad.gestionar",)
    ),
    "servicio": DestinoFoto(Servicio, ("servicio.gestionar",), ("servicio.gestionar",)),
    "consultorio": DestinoFoto(Consultorio, ("sede.gestionar",), ("sede.gestionar",)),
    "gasto": DestinoFoto(Gasto, ("gasto.leer",), ("gasto.registrar",)),
    "pago": DestinoFoto(Pago, ("pago.leer",), ("pago.registrar", "pago.validar")),
    "cita": DestinoFoto(Cita, ("agenda.leer",), ("cita.crear", "cita.reprogramar")),
    "paciente": DestinoFoto(
        Paciente, ("paciente.leer_administrativo",), ("paciente.editar", "paciente.crear")
    ),
    "campana": DestinoFoto(CampanaPromocion, ("promocion.gestionar",), ("promocion.gestionar",)),
    "nota": DestinoFoto(
        NotaEvolucion, ("historia_clinica.leer",), ("historia_clinica.escribir",), clinico=True
    ),
    "receta": DestinoFoto(Receta, ("receta.leer",), ("receta.crear",), clinico=True),
    "anamnesis": DestinoFoto(
        RespuestaAnamnesis, ("historia_clinica.leer",), ("historia_clinica.escribir",), clinico=True
    ),
    "odontograma": DestinoFoto(
        Odontograma, ("odontograma.leer",), ("odontograma.escribir",), "odontograma", True
    ),
    "periodontograma": DestinoFoto(
        Periodontograma, ("odontograma.leer",), ("odontograma.escribir",), "periodoncia", True
    ),
    "placa": DestinoFoto(
        RegistroPlaca, ("odontograma.leer",), ("odontograma.escribir",), "periodoncia", True
    ),
    "formulario033": DestinoFoto(
        Formulario033, ("odontograma.leer",), ("odontograma.escribir",), "odontograma", True
    ),
    "plan": DestinoFoto(
        PlanTratamiento, ("plan_tratamiento.leer",), ("plan_tratamiento.escribir",), "planes", True
    ),
    "registro": DestinoFoto(
        RegistroPaciente, ("historia_clinica.leer",), ("historia_clinica.escribir",), clinico=True
    ),
    "conocimiento": DestinoFoto(
        KnowledgeDocument, ("conocimiento.leer",), ("conocimiento.cargar",)
    ),
}


class RepositorioFotosRegistro:
    def __init__(self, sesion: AsyncSession, ahora: datetime):
        self.sesion = sesion
        self.ahora = ahora

    async def destino(
        self, tipo: str, id_registro: uuid.UUID, principal: Principal, bloquear: bool = False
    ) -> Any:
        destino = DESTINOS[tipo]
        modelo: Any = destino.modelo
        if tipo == "cita":
            consulta = (
                RepositorioAgenda(self.sesion)
                .consulta_autorizada(principal)
                .where(Cita.id == id_registro)
            )
        elif tipo == "gasto":
            consulta = (
                RepositorioGastos(self.sesion)
                .consulta(principal, incluir_anulados=True)
                .where(Gasto.id == id_registro)
            )
        elif tipo == "paciente":
            consulta = (
                RepositorioPacientes(self.sesion)
                .consulta_autorizada(principal)
                .where(Paciente.id == id_registro)
            )
        elif tipo == "conocimiento":
            consulta = self.consulta_conocimiento(principal).where(
                KnowledgeDocument.id == id_registro
            )
        else:
            consulta = self.consulta_general(tipo, principal).where(modelo.id == id_registro)
            if destino.clinico:
                consulta = self.filtrar_clinico(consulta, modelo, tipo, principal)
            if hasattr(modelo, "sede_id") and not principal.ambito.todas_las_sedes:
                consulta = consulta.where(modelo.sede_id.in_(principal.ambito.sedes))
            if tipo == "sede" and not principal.ambito.todas_las_sedes:
                consulta = consulta.where(Sede.id.in_(principal.ambito.sedes))
            if tipo == "pago":
                consulta = consulta.where(
                    Pago.cita_id.in_(
                        RepositorioAgenda(self.sesion)
                        .consulta_autorizada(principal)
                        .with_only_columns(Cita.id)
                    )
                )
        if bloquear:
            consulta = consulta.with_for_update()
        return (await self.sesion.execute(consulta)).scalar_one_or_none()

    @staticmethod
    def consulta_general(tipo: str, principal: Principal) -> Any:
        modelo: Any = DESTINOS[tipo].modelo
        consulta = select(modelo)
        if tipo == "clinica":
            if "superadministrador" not in principal.roles:
                consulta = consulta.where(Clinica.id == principal.clinica_id)
        else:
            consulta = consulta.where(modelo.clinica_id == principal.clinica_id)
        return consulta

    async def periodontograma_vigente(self, fila: Periodontograma) -> bool:
        ultima = await self.sesion.scalar(
            select(func.max(Periodontograma.version)).where(
                Periodontograma.raiz_id == fila.raiz_id,
                Periodontograma.clinica_id == fila.clinica_id,
            )
        )
        return ultima == fila.version

    def consulta_conocimiento(self, principal: Principal) -> Select[tuple[KnowledgeDocument]]:
        contexto = contexto_desde_principal(principal, ahora=self.ahora)
        consulta = select(KnowledgeDocument).where(
            KnowledgeDocument.clinic_id == principal.clinica_id,
            KnowledgeDocument.sensitivity_level.in_(
                [n.value for n in NivelSensibilidad if contexto.nivel_maximo.cubre(n)]
            ),
            condicion_acl_documento(KnowledgeDocument.id, contexto),
        )
        for permitidas, columna in (
            (contexto.sedes, KnowledgeDocument.branch_id),
            (contexto.especialidades, KnowledgeDocument.specialty_id),
        ):
            if permitidas is not None:
                consulta = consulta.where(
                    or_(columna.is_(None), columna.in_(permitidas)) if permitidas else false()
                )
        return consulta

    def filtrar_clinico(self, consulta: Any, modelo: Any, tipo: str, principal: Principal) -> Any:
        destino = DESTINOS[tipo]
        consulta = consulta.where(
            modelo.profesional_id.in_(autores_en_ambito(principal, destino.modulo))
        )
        if hasattr(modelo, "nivel_sensibilidad") and not principal.tiene_permiso(
            "historia_clinica.leer_sensible"
        ):
            consulta = consulta.where(modelo.nivel_sensibilidad != "N3")
        if tipo == "formulario033" and not principal.tiene_permiso(
            "historia_clinica.leer_sensible"
        ):
            consulta = consulta.where(False)
        if tipo == "anamnesis":
            consulta = consulta.join(
                PlantillaAnamnesis, PlantillaAnamnesis.id == RespuestaAnamnesis.plantilla_id
            ).where(PlantillaAnamnesis.clinica_id == principal.clinica_id)
            if not principal.tiene_permiso("historia_clinica.leer_sensible"):
                consulta = consulta.where(PlantillaAnamnesis.nivel_sensibilidad != "N3")
        return consulta

    async def nivel_anamnesis(self, plantilla_id: uuid.UUID) -> str:
        return str(
            await self.sesion.scalar(
                select(PlantillaAnamnesis.nivel_sensibilidad).where(
                    PlantillaAnamnesis.id == plantilla_id
                )
            )
            or "N3"
        )

    async def listar(
        self,
        tipo: str,
        id_registro: uuid.UUID,
        clinica_id: uuid.UUID,
        niveles: tuple[str, ...] | None = None,
    ) -> list[FotoRegistro]:
        return list(
            (
                await self.sesion.scalars(
                    select(FotoRegistro)
                    .where(
                        FotoRegistro.tipo_registro == tipo,
                        FotoRegistro.registro_id == id_registro,
                        FotoRegistro.clinica_id == clinica_id,
                        FotoRegistro.anulado_en.is_(None),
                        FotoRegistro.nivel_sensibilidad.in_(niveles)
                        if niveles is not None
                        else true(),
                    )
                    .order_by(FotoRegistro.creado_en.desc())
                    .limit(20)
                )
            ).all()
        )

    async def obtener(self, id_foto: uuid.UUID, clinica_id: uuid.UUID) -> FotoRegistro | None:
        return (
            await self.sesion.execute(
                select(FotoRegistro).where(
                    FotoRegistro.id == id_foto,
                    FotoRegistro.clinica_id == clinica_id,
                    FotoRegistro.anulado_en.is_(None),
                )
            )
        ).scalar_one_or_none()

    async def por_id(self, id_foto: uuid.UUID) -> FotoRegistro | None:
        return await self.sesion.get(FotoRegistro, id_foto)

    async def agregar(self, fila: FotoRegistro) -> None:
        self.sesion.add(fila)
        await self.sesion.flush()
