"""Acceso clínico y ciclo de vida inicial del plan de tratamiento."""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.mensajeria.adaptadores import RegistroCanales
from app.mensajeria.servicios import ServicioOutbox, SolicitudEnvio
from app.modulos.agenda.modelos import Cita
from app.modulos.imagenes.modelos import ImagenPaciente
from app.modulos.odontologia.modelos import (
    EstadoPlan,
    EstadoProcedimiento,
    Odontograma,
    PlantillaPlan,
    PlanTratamiento,
    ProcedimientoPlan,
)
from app.modulos.odontologia.planes_esquemas import (
    AceptacionPlan,
    CompletarProcedimiento,
    PlanNuevo,
    PlantillaNueva,
)
from app.modulos.odontologia.servicios import ServicioOdontograma
from app.modulos.odontologia.vocabulario import HallazgoCara
from app.modulos.organizacion.modelos import Clinica, Servicio
from app.modulos.outbox.modelos import CanalOutbox, TipoMensajeOutbox
from app.modulos.pacientes.acceso_clinico import GuardiaClinica
from app.modulos.pacientes.modelos import Paciente
from app.nucleo.autorizacion import Principal
from app.nucleo.errores import (
    ConflictoEstado,
    ConsentimientoRequerido,
    DatosInvalidos,
    PermisoDenegado,
    RecursoNoEncontrado,
)
from app.nucleo.reloj import Reloj

# Estados desde los que un plan todavia se puede cancelar.
_CANCELABLES = frozenset(
    {EstadoPlan.BORRADOR.value, EstadoPlan.PROPUESTO.value, EstadoPlan.ACEPTADO.value}
)


class ServicioPlanesTratamiento:
    def __init__(self, sesion: AsyncSession, reloj: Reloj) -> None:
        self._sesion = sesion
        self._reloj = reloj
        self._guardia = GuardiaClinica(sesion)

    async def listar(
        self, paciente_id: uuid.UUID, *, principal: Principal
    ) -> list[tuple[PlanTratamiento, list[ProcedimientoPlan]]]:
        await self._guardia.acceso_clinico(
            principal, paciente_id, "plan_tratamiento.leer", self._reloj.ahora()
        )
        planes = list(
            (
                await self._sesion.execute(
                    select(PlanTratamiento)
                    .where(
                        PlanTratamiento.paciente_id == paciente_id,
                        PlanTratamiento.clinica_id == principal.clinica_id,
                    )
                    .order_by(PlanTratamiento.creado_en.desc())
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
        if not planes:
            return []
        procedimientos = list(
            (
                await self._sesion.execute(
                    select(ProcedimientoPlan)
                    .where(ProcedimientoPlan.plan_id.in_([plan.id for plan in planes]))
                    .order_by(
                        ProcedimientoPlan.plan_id, ProcedimientoPlan.fase, ProcedimientoPlan.orden
                    )
                )
            )
            .scalars()
            .all()
        )
        agrupados: dict[uuid.UUID, list[ProcedimientoPlan]] = {}
        for procedimiento in procedimientos:
            agrupados.setdefault(procedimiento.plan_id, []).append(procedimiento)
        return [(plan, agrupados.get(plan.id, [])) for plan in planes]

    async def crear(
        self, paciente_id: uuid.UUID, datos: PlanNuevo, *, principal: Principal
    ) -> tuple[PlanTratamiento, list[ProcedimientoPlan]]:
        paciente = await self._guardia.acceso_clinico(
            principal, paciente_id, "plan_tratamiento.escribir", self._reloj.ahora()
        )
        profesional_id = principal.profesional_id
        if profesional_id is None:
            raise PermisoDenegado("Solo una cuenta profesional puede crear un plan clínico.")

        servicio_ids = {item.servicio_id for item in datos.procedimientos if item.servicio_id}
        if servicio_ids:
            encontrados = set(
                (
                    await self._sesion.execute(
                        select(Servicio.id).where(
                            Servicio.id.in_(servicio_ids),
                            Servicio.clinica_id == principal.clinica_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            if encontrados != servicio_ids:
                raise RecursoNoEncontrado("Uno de los servicios solicitados no existe.")

        plan = PlanTratamiento(
            clinica_id=paciente.clinica_id,
            paciente_id=paciente.id,
            profesional_id=profesional_id,
            titulo=datos.titulo.strip(),
            estado=EstadoPlan.BORRADOR.value,
            moneda=datos.moneda,
            observaciones=datos.observaciones,
            creado_por=principal.actor_id,
        )
        self._sesion.add(plan)
        await self._sesion.flush()
        procedimientos = [
            ProcedimientoPlan(
                plan_id=plan.id,
                fase=item.fase,
                orden=item.orden,
                pieza=item.pieza,
                caras=item.caras,
                servicio_id=item.servicio_id,
                descripcion=item.descripcion,
                precio=item.precio,
                creado_por=principal.actor_id,
            )
            for item in datos.procedimientos
        ]
        self._sesion.add_all(procedimientos)
        await self._sesion.flush()
        return plan, procedimientos

    async def proponer(
        self, plan_id: uuid.UUID, *, principal: Principal
    ) -> tuple[PlanTratamiento, list[ProcedimientoPlan]]:
        plan = await self._obtener(plan_id, principal, "plan_tratamiento.escribir", bloquear=True)
        if principal.profesional_id is None or plan.profesional_id != principal.profesional_id:
            raise PermisoDenegado("Solo el profesional responsable puede proponer este plan.")
        if plan.estado != EstadoPlan.BORRADOR.value:
            raise DatosInvalidos("Solo se puede proponer un plan en borrador.")
        plan.estado = EstadoPlan.PROPUESTO.value
        plan.propuesto_en = self._reloj.ahora()
        plan.actualizado_por = principal.actor_id
        await self._sesion.flush()
        return plan, await self._procedimientos(plan.id)

    # ------------------------------------------------------------------
    #  Plantillas
    # ------------------------------------------------------------------
    async def plantillas(self, *, principal: Principal) -> list[PlantillaPlan]:
        GuardiaClinica.exigir(principal, "plan_tratamiento.leer")
        consulta = (
            select(PlantillaPlan)
            .where(
                PlantillaPlan.clinica_id == principal.clinica_id,
                PlantillaPlan.anulado_en.is_(None),
            )
            .order_by(PlantillaPlan.nombre)
            .limit(200)
        )
        return list((await self._sesion.execute(consulta)).scalars().all())

    async def crear_plantilla(
        self, datos: PlantillaNueva, *, principal: Principal
    ) -> PlantillaPlan:
        GuardiaClinica.exigir(principal, "plan_tratamiento.escribir")
        if principal.clinica_id is None:
            raise PermisoDenegado("La cuenta no tiene clinica asignada.")
        existente = (
            await self._sesion.execute(
                select(PlantillaPlan.id).where(
                    PlantillaPlan.clinica_id == principal.clinica_id,
                    PlantillaPlan.nombre == datos.nombre,
                    PlantillaPlan.anulado_en.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existente is not None:
            raise ConflictoEstado("Ya existe una plantilla con ese nombre.")
        plantilla = PlantillaPlan(
            clinica_id=principal.clinica_id,
            nombre=datos.nombre,
            descripcion=(datos.descripcion or "").strip() or None,
            procedimientos=[item.model_dump(mode="json") for item in datos.procedimientos],
            creado_por=principal.actor_id,
        )
        self._sesion.add(plantilla)
        await self._sesion.flush()
        return plantilla

    async def retirar_plantilla(
        self, plantilla_id: uuid.UUID, motivo: str, *, principal: Principal
    ) -> PlantillaPlan:
        GuardiaClinica.exigir(principal, "plan_tratamiento.escribir")
        plantilla = (
            await self._sesion.execute(
                select(PlantillaPlan).where(
                    PlantillaPlan.id == plantilla_id,
                    PlantillaPlan.clinica_id == principal.clinica_id,
                    PlantillaPlan.anulado_en.is_(None),
                )
            )
        ).scalar_one_or_none()
        if plantilla is None:
            raise RecursoNoEncontrado("La plantilla solicitada no existe.")
        plantilla.anulado_en = self._reloj.ahora()
        plantilla.anulado_por = principal.actor_id
        plantilla.motivo_anulacion = motivo
        await self._sesion.flush()
        return plantilla

    # ------------------------------------------------------------------
    #  Aceptacion, ejecucion y cancelacion
    # ------------------------------------------------------------------
    async def aceptar(
        self, plan_id: uuid.UUID, datos: AceptacionPlan, *, principal: Principal
    ) -> tuple[PlanTratamiento, list[ProcedimientoPlan]]:
        """Registra la constancia de aceptacion. PROPUESTO -> ACEPTADO."""
        plan = await self._obtener(plan_id, principal, "plan_tratamiento.escribir", bloquear=True)
        self._exigir_responsable(plan, principal)
        if plan.estado != EstadoPlan.PROPUESTO.value:
            raise ConflictoEstado("Solo se registra la aceptacion de un plan propuesto.")
        if datos.imagen_id is not None:
            imagen = (
                await self._sesion.execute(
                    select(ImagenPaciente.id).where(
                        ImagenPaciente.id == datos.imagen_id,
                        ImagenPaciente.paciente_id == plan.paciente_id,
                        ImagenPaciente.clinica_id == principal.clinica_id,
                        ImagenPaciente.anulado_en.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if imagen is None:
                raise RecursoNoEncontrado("La imagen del documento no existe para este paciente.")
        plan.estado = EstadoPlan.ACEPTADO.value
        plan.aceptado_en = self._reloj.ahora()
        plan.aceptacion_medio = datos.medio.value
        plan.aceptacion_referencia = datos.referencia
        plan.aceptacion_imagen_id = datos.imagen_id
        plan.aceptacion_registrada_por = principal.actor_id
        plan.actualizado_por = principal.actor_id
        await self._sesion.flush()
        return plan, await self._procedimientos(plan.id)

    async def completar_procedimiento(
        self,
        procedimiento_id: uuid.UUID,
        datos: CompletarProcedimiento,
        *,
        principal: Principal,
    ) -> tuple[PlanTratamiento, list[ProcedimientoPlan], Odontograma | None]:
        """Cierra un procedimiento de un plan aceptado.

        Con `hallazgo_resultante` y pieza, crea una version nueva del
        odontograma ligada al procedimiento: el plan y el registro clinico
        no divergen. Si era el ultimo pendiente, el plan pasa a COMPLETADO.
        """
        plan, procedimiento = await self._procedimiento(procedimiento_id, principal)
        if plan.estado != EstadoPlan.ACEPTADO.value:
            raise ConflictoEstado(
                "Solo se completan procedimientos de un plan aceptado por el paciente."
            )
        if procedimiento.estado != EstadoProcedimiento.PENDIENTE.value:
            raise ConflictoEstado("El procedimiento ya no esta pendiente.")
        if principal.profesional_id is None:
            raise PermisoDenegado("Solo una cuenta profesional completa procedimientos.")

        hallazgo = datos.hallazgo_resultante
        if hallazgo is not None and procedimiento.pieza is None:
            raise DatosInvalidos("Un procedimiento sin pieza no se refleja en el odontograma.")
        if isinstance(hallazgo, HallazgoCara) and not procedimiento.caras:
            raise DatosInvalidos("Un hallazgo por cara exige que el procedimiento tenga caras.")
        if datos.cita_id is not None:
            cita = (
                await self._sesion.execute(
                    select(Cita.id).where(
                        Cita.id == datos.cita_id,
                        Cita.paciente_id == plan.paciente_id,
                        Cita.clinica_id == principal.clinica_id,
                    )
                )
            ).scalar_one_or_none()
            if cita is None:
                raise RecursoNoEncontrado("La cita indicada no existe para este paciente.")

        ahora = self._reloj.ahora()
        if datos.control_recomendado_en is not None:
            zona = await self._sesion.scalar(
                select(Clinica.zona_horaria).where(Clinica.id == plan.clinica_id)
            )
            hoy = self._reloj.hoy_en(zona or "America/Guayaquil")
            if datos.control_recomendado_en < hoy:
                raise DatosInvalidos("La fecha del control no puede estar en el pasado.")
        procedimiento.estado = EstadoProcedimiento.COMPLETADO.value
        procedimiento.completado_en = ahora
        procedimiento.completado_por = principal.actor_id
        procedimiento.control_recomendado_en = datos.control_recomendado_en
        procedimiento.control_atendido_en = None
        procedimiento.control_atendido_por = None
        procedimiento.control_nota = None
        procedimiento.hallazgo_resultante = hallazgo.value if hallazgo else None
        procedimiento.cita_id = datos.cita_id or procedimiento.cita_id
        procedimiento.actualizado_por = principal.actor_id
        await self._sesion.flush()

        version = None
        if hallazgo is not None and procedimiento.pieza is not None:
            version = await ServicioOdontograma(self._sesion, self._reloj).aplicar_hallazgo(
                plan.paciente_id,
                pieza=procedimiento.pieza,
                caras=procedimiento.caras,
                hallazgo=hallazgo,
                procedimiento_id=procedimiento.id,
                motivo=f"Procedimiento completado del plan «{plan.titulo}»",
                principal=principal,
            )

        procedimientos = await self._procedimientos(plan.id)
        if all(item.estado != EstadoProcedimiento.PENDIENTE.value for item in procedimientos):
            plan.estado = EstadoPlan.COMPLETADO.value
            plan.completado_en = ahora
            plan.actualizado_por = principal.actor_id
            await self._sesion.flush()
        else:
            await self._avisar_siguiente_fase(plan, procedimiento.fase, procedimientos)
        return plan, procedimientos, version

    async def atender_control(
        self,
        procedimiento_id: uuid.UUID,
        nota: str | None,
        *,
        principal: Principal,
    ) -> tuple[PlanTratamiento, list[ProcedimientoPlan]]:
        """Cierra el control posterior con marca de tiempo y profesional responsable."""
        plan, procedimiento = await self._procedimiento(procedimiento_id, principal)
        self._exigir_responsable(plan, principal)
        if procedimiento.estado != EstadoProcedimiento.COMPLETADO.value:
            raise ConflictoEstado("El procedimiento debe estar completado para atender su control.")
        if procedimiento.control_recomendado_en is None:
            raise ConflictoEstado("Este procedimiento no tiene un control posterior programado.")
        if procedimiento.control_atendido_en is not None:
            raise ConflictoEstado("El control de este procedimiento ya fue atendido.")

        procedimiento.control_atendido_en = self._reloj.ahora()
        procedimiento.control_atendido_por = principal.actor_id
        procedimiento.control_nota = nota
        procedimiento.actualizado_por = principal.actor_id
        await self._sesion.flush()
        return plan, await self._procedimientos(plan.id)

    async def _avisar_siguiente_fase(
        self,
        plan: PlanTratamiento,
        fase: int,
        procedimientos: list[ProcedimientoPlan],
    ) -> bool:
        """Encola el recordatorio de agendar cuando una fase termina y quedan otras.

        Deterministico, sin IA. El mensaje no nombra tratamiento ni pieza. Si
        el paciente no acepto comunicaciones por WhatsApp, no se envia nada y
        el procedimiento se completa igual: un aviso nunca bloquea un acto
        clinico. Una sola vez por fase (clave de deduplicacion).
        """
        pendiente_en_fase = any(
            item.fase == fase and item.estado == EstadoProcedimiento.PENDIENTE.value
            for item in procedimientos
        )
        hay_siguiente = any(
            item.fase > fase and item.estado == EstadoProcedimiento.PENDIENTE.value
            for item in procedimientos
        )
        if pendiente_en_fase or not hay_siguiente:
            return False
        fila = (
            await self._sesion.execute(
                select(Paciente.nombre, Clinica.nombre)
                .join(Clinica, Clinica.id == Paciente.clinica_id)
                .where(Paciente.id == plan.paciente_id)
            )
        ).one_or_none()
        if fila is None:
            return False
        huella = hashlib.sha256(f"{plan.id}:{fase}".encode()).hexdigest()
        try:
            async with self._sesion.begin_nested():
                await ServicioOutbox(self._sesion, self._reloj, RegistroCanales()).encolar(
                    SolicitudEnvio(
                        tipo=TipoMensajeOutbox.SEGUIMIENTO_TRATAMIENTO,
                        canal=CanalOutbox.WHATSAPP,
                        destino_tipo="PACIENTE",
                        destino_id=plan.paciente_id,
                        clave_deduplicacion=f"seguim:{huella[:57]}",
                        variables={"nombre": fila[0], "clinica": fila[1]},
                        clinica_id=plan.clinica_id,
                        entidad_origen_tipo="plan_tratamiento",
                        entidad_origen_id=plan.id,
                    )
                )
        except ConsentimientoRequerido:
            return False
        return True

    async def cancelar_procedimiento(
        self, procedimiento_id: uuid.UUID, motivo: str, *, principal: Principal
    ) -> tuple[PlanTratamiento, list[ProcedimientoPlan]]:
        plan, procedimiento = await self._procedimiento(procedimiento_id, principal)
        if plan.estado not in _CANCELABLES:
            raise ConflictoEstado("El plan ya esta cerrado.")
        if procedimiento.estado != EstadoProcedimiento.PENDIENTE.value:
            raise ConflictoEstado("Solo se cancela un procedimiento pendiente.")
        ahora = self._reloj.ahora()
        procedimiento.estado = EstadoProcedimiento.CANCELADO.value
        procedimiento.cancelado_en = ahora
        procedimiento.motivo_cancelacion = motivo
        procedimiento.actualizado_por = principal.actor_id
        await self._sesion.flush()

        procedimientos = await self._procedimientos(plan.id)
        pendientes = [p for p in procedimientos if p.estado == EstadoProcedimiento.PENDIENTE.value]
        completados = [
            p for p in procedimientos if p.estado == EstadoProcedimiento.COMPLETADO.value
        ]
        # Plan aceptado sin nada pendiente: se cierra como completado si algo
        # se hizo. Si no se hizo nada, se queda abierto y se cancela de forma
        # explicita, con su motivo.
        if plan.estado == EstadoPlan.ACEPTADO.value and not pendientes and completados:
            plan.estado = EstadoPlan.COMPLETADO.value
            plan.completado_en = ahora
            await self._sesion.flush()
        return plan, procedimientos

    async def cancelar(
        self, plan_id: uuid.UUID, motivo: str, *, principal: Principal
    ) -> tuple[PlanTratamiento, list[ProcedimientoPlan]]:
        """Cancela el plan y sus procedimientos pendientes. Lo hecho se conserva."""
        plan = await self._obtener(plan_id, principal, "plan_tratamiento.escribir", bloquear=True)
        self._exigir_responsable(plan, principal)
        if plan.estado not in _CANCELABLES:
            raise ConflictoEstado("El plan ya esta cerrado.")
        ahora = self._reloj.ahora()
        for procedimiento in await self._procedimientos(plan.id):
            if procedimiento.estado == EstadoProcedimiento.PENDIENTE.value:
                procedimiento.estado = EstadoProcedimiento.CANCELADO.value
                procedimiento.cancelado_en = ahora
                procedimiento.motivo_cancelacion = motivo
                procedimiento.actualizado_por = principal.actor_id
        plan.estado = EstadoPlan.CANCELADO.value
        plan.cancelado_en = ahora
        plan.motivo_cancelacion = motivo
        plan.actualizado_por = principal.actor_id
        await self._sesion.flush()
        return plan, await self._procedimientos(plan.id)

    @staticmethod
    def _exigir_responsable(plan: PlanTratamiento, principal: Principal) -> None:
        if principal.profesional_id is None or plan.profesional_id != principal.profesional_id:
            raise PermisoDenegado("Solo el profesional responsable puede cambiar este plan.")

    async def _procedimiento(
        self, procedimiento_id: uuid.UUID, principal: Principal
    ) -> tuple[PlanTratamiento, ProcedimientoPlan]:
        procedimiento = (
            await self._sesion.execute(
                # Solo procedimientos de planes de la propia clinica: no se
                # bloquea una fila ajena aunque luego se responda 404.
                select(ProcedimientoPlan)
                .join(PlanTratamiento, PlanTratamiento.id == ProcedimientoPlan.plan_id)
                .where(
                    ProcedimientoPlan.id == procedimiento_id,
                    PlanTratamiento.clinica_id == principal.clinica_id,
                )
                .with_for_update(of=ProcedimientoPlan)
            )
        ).scalar_one_or_none()
        if procedimiento is None:
            raise RecursoNoEncontrado("El procedimiento solicitado no existe.")
        # El alcance sale del plan real del procedimiento: cierra el IDOR.
        plan = await self._obtener(
            procedimiento.plan_id, principal, "plan_tratamiento.escribir", bloquear=True
        )
        return plan, procedimiento

    async def _obtener(
        self,
        plan_id: uuid.UUID,
        principal: Principal,
        permiso: str,
        *,
        bloquear: bool = False,
    ) -> PlanTratamiento:
        consulta = select(PlanTratamiento).where(
            PlanTratamiento.id == plan_id,
            PlanTratamiento.clinica_id == principal.clinica_id,
        )
        if bloquear:
            consulta = consulta.with_for_update()
        plan = (await self._sesion.execute(consulta)).scalar_one_or_none()
        if plan is None:
            raise RecursoNoEncontrado("El plan de tratamiento solicitado no existe.")
        await self._guardia.acceso_clinico(
            principal, plan.paciente_id, permiso, self._reloj.ahora()
        )
        return plan

    async def _procedimientos(self, plan_id: uuid.UUID) -> list[ProcedimientoPlan]:
        return list(
            (
                await self._sesion.execute(
                    select(ProcedimientoPlan)
                    .where(ProcedimientoPlan.plan_id == plan_id)
                    .order_by(ProcedimientoPlan.fase, ProcedimientoPlan.orden)
                )
            )
            .scalars()
            .all()
        )


__all__ = ["ServicioPlanesTratamiento"]
