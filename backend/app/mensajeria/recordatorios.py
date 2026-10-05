"""Programación durable y encolado de recordatorios de citas y tomas.

La reserva solo crea filas locales en `recordatorio`; este módulo nunca
contacta proveedores. Cuando vence el horario, un worker convierte la fila en
una intención del outbox dentro de la misma transacción. El procesador del
outbox conserva la elección de adaptador por entorno.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final, cast
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.mensajeria.adaptadores import RegistroCanales
from app.mensajeria.servicios import ServicioOutbox, SolicitudEnvio
from app.modulos.agenda.modelos import Cita, EstadoCita
from app.modulos.historia.modelos import (
    EstadoReceta,
    EstadoToma,
    Receta,
    RecetaMedicamento,
    Toma,
)
from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.outbox.modelos import (
    CanalOutbox,
    EstadoOutbox,
    OutboxMensaje,
    Recordatorio,
    TipoMensajeOutbox,
)
from app.modulos.pacientes.modelos import Paciente
from app.modulos.profesionales.modelos import Profesional
from app.nucleo.errores import ConsentimientoRequerido
from app.nucleo.registro import obtener_logger
from app.nucleo.reloj import Reloj

logger = obtener_logger(__name__)

ENTIDAD_CITA: Final[str] = "CITA"
ENTIDAD_TOMA: Final[str] = "TOMA"
ESTADO_PROGRAMADO: Final[str] = "PROGRAMADO"
ESTADO_ENCOLADO: Final[str] = "ENCOLADO"
ESTADO_CANCELADO: Final[str] = "CANCELADO"
ESTADO_OMITIDO: Final[str] = "OMITIDO"
TAMANO_LOTE_RECORDATORIOS: Final[int] = 50


@dataclass(frozen=True, slots=True)
class ResumenRecordatorios:
    tomados: int = 0
    encolados: int = 0
    omitidos: int = 0


class ServicioRecordatorios:
    """Crea, cancela y materializa avisos clínicos genéricos sin usar la red."""

    def __init__(
        self,
        sesion: AsyncSession,
        reloj: Reloj,
        *,
        url_aplicacion: str = "http://localhost:4200",
    ) -> None:
        self._sesion = sesion
        self._reloj = reloj
        self._url_aplicacion = url_aplicacion.rstrip("/")

    async def programar_cita(
        self,
        cita: Cita,
        *,
        horas_antes_1: int = 24,
        horas_antes_2: int = 3,
    ) -> int:
        """Guarda avisos futuros para una cita confirmada.

        Los avisos cuyo instante ya pasó se omiten: no se envía un «aviso de
        mañana» cuando la cita es en veinte minutos.
        """
        if cita.estado not in (EstadoCita.CONFIRMED.value, EstadoCita.RESCHEDULED.value):
            return 0

        ahora = self._reloj.ahora()
        horarios = (
            (TipoMensajeOutbox.CITA_RECORDATORIO_DIA_ANTES, horas_antes_1),
            (TipoMensajeOutbox.CITA_RECORDATORIO_HORAS_ANTES, horas_antes_2),
        )
        cantidad = 0
        for tipo, horas in horarios:
            programado = cita.inicio - timedelta(hours=horas)
            if programado <= ahora:
                continue
            self._sesion.add(
                Recordatorio(
                    tipo=tipo.value,
                    clinica_id=cita.clinica_id,
                    entidad_tipo=ENTIDAD_CITA,
                    entidad_id=cita.id,
                    destinatario_tipo="PACIENTE",
                    destinatario_id=cita.paciente_id,
                    programado_para=programado,
                    estado=ESTADO_PROGRAMADO,
                )
            )
            cantidad += 1
        if cantidad:
            await self._sesion.flush()
        return cantidad

    async def programar_tomas(self, receta_id: uuid.UUID) -> int:
        """Programa avisos solo para tomas pendientes de una receta vigente."""
        ahora = self._reloj.ahora()
        consulta = (
            select(Toma, Receta)
            .join(RecetaMedicamento, RecetaMedicamento.id == Toma.receta_medicamento_id)
            .join(Receta, Receta.id == RecetaMedicamento.receta_id)
            .where(
                Receta.id == receta_id,
                Receta.estado == EstadoReceta.CONFIRMADA.value,
                Toma.estado == EstadoToma.PENDIENTE.value,
                Toma.programada_en > ahora,
            )
        )
        filas = (await self._sesion.execute(consulta)).all()
        for toma, receta in filas:
            self._sesion.add(
                Recordatorio(
                    tipo=TipoMensajeOutbox.TOMA_RECORDATORIO.value,
                    clinica_id=receta.clinica_id,
                    entidad_tipo=ENTIDAD_TOMA,
                    entidad_id=toma.id,
                    destinatario_tipo="PACIENTE",
                    destinatario_id=toma.paciente_id,
                    programado_para=toma.programada_en,
                    estado=ESTADO_PROGRAMADO,
                )
            )
        if filas:
            await self._sesion.flush()
        return len(filas)

    async def cancelar_cita(self, cita_id: uuid.UUID, *, motivo: str) -> int:
        """Cancela filas futuras y descarta avisos que aún no salieron."""
        return await self._cancelar_entidad(ENTIDAD_CITA, cita_id, motivo)

    async def cancelar_toma(self, toma_id: uuid.UUID, *, motivo: str) -> int:
        """Invalida el aviso de una toma que ya se registró."""
        return await self._cancelar_entidad(ENTIDAD_TOMA, toma_id, motivo)

    async def cancelar_tomas_receta(self, receta_id: uuid.UUID, *, motivo: str) -> int:
        """Invalida avisos aún no entregados al suspender una receta."""
        toma_ids = (
            select(Toma.id)
            .join(RecetaMedicamento, RecetaMedicamento.id == Toma.receta_medicamento_id)
            .where(RecetaMedicamento.receta_id == receta_id)
        )
        ahora = self._reloj.ahora()
        resultado = await self._sesion.execute(
            update(Recordatorio)
            .where(
                Recordatorio.entidad_tipo == ENTIDAD_TOMA,
                Recordatorio.entidad_id.in_(toma_ids),
                Recordatorio.estado == ESTADO_PROGRAMADO,
            )
            .values(
                estado=ESTADO_CANCELADO,
                cancelado_en=ahora,
                motivo_cancelacion=motivo.strip() or "Receta suspendida",
            )
        )
        await self._sesion.execute(
            update(OutboxMensaje)
            .where(
                OutboxMensaje.entidad_origen_tipo == ENTIDAD_TOMA,
                OutboxMensaje.entidad_origen_id.in_(toma_ids),
                OutboxMensaje.estado == EstadoOutbox.PENDIENTE.value,
            )
            .values(
                estado=EstadoOutbox.DESCARTADO.value,
                ultimo_error=motivo.strip() or "Receta suspendida",
                actualizado_en=ahora,
            )
        )
        return cast(Any, resultado).rowcount or 0

    async def _cancelar_entidad(self, entidad_tipo: str, entidad_id: uuid.UUID, motivo: str) -> int:
        """Cancela avisos programados y descarta su outbox pendiente."""
        ahora = self._reloj.ahora()
        filas = await self._sesion.execute(
            update(Recordatorio)
            .where(
                Recordatorio.entidad_tipo == entidad_tipo,
                Recordatorio.entidad_id == entidad_id,
                Recordatorio.estado == ESTADO_PROGRAMADO,
            )
            .values(
                estado=ESTADO_CANCELADO,
                cancelado_en=ahora,
                motivo_cancelacion=motivo.strip() or "Cita modificada",
            )
        )
        await self._sesion.execute(
            update(OutboxMensaje)
            .where(
                OutboxMensaje.entidad_origen_tipo == entidad_tipo,
                OutboxMensaje.entidad_origen_id == entidad_id,
                OutboxMensaje.estado == EstadoOutbox.PENDIENTE.value,
            )
            .values(
                estado=EstadoOutbox.DESCARTADO.value,
                ultimo_error=motivo.strip() or "Cita modificada",
                actualizado_en=ahora,
            )
        )
        return cast(Any, filas).rowcount or 0

    async def encolar_vencidos(
        self, *, tamano: int = TAMANO_LOTE_RECORDATORIOS
    ) -> ResumenRecordatorios:
        """Convierte recordatorios vencidos en mensajes del outbox.

        `FOR UPDATE SKIP LOCKED` permite varias réplicas sin duplicar avisos.
        La fila se confirma junto con el outbox, por lo que una caída no deja
        un recordatorio marcado como encolado sin su mensaje durable.
        """
        ahora = self._reloj.ahora()
        consulta = (
            select(Recordatorio)
            .where(
                Recordatorio.entidad_tipo.in_((ENTIDAD_CITA, ENTIDAD_TOMA)),
                Recordatorio.estado == ESTADO_PROGRAMADO,
                Recordatorio.programado_para <= ahora,
            )
            .order_by(Recordatorio.programado_para)
            .limit(max(1, min(tamano, 500)))
            .with_for_update(skip_locked=True)
        )
        recordatorios = list((await self._sesion.execute(consulta)).scalars())
        servicio_outbox = ServicioOutbox(self._sesion, self._reloj, RegistroCanales())
        encolados = 0
        omitidos = 0
        for recordatorio in recordatorios:
            fue_encolado = await self._encolar_un_recordatorio(
                recordatorio, servicio_outbox, ahora=ahora
            )
            encolados += fue_encolado
            omitidos += not fue_encolado

        if recordatorios:
            await self._sesion.commit()
        return ResumenRecordatorios(
            tomados=len(recordatorios), encolados=encolados, omitidos=omitidos
        )

    async def _encolar_un_recordatorio(
        self,
        recordatorio: Recordatorio,
        servicio_outbox: ServicioOutbox,
        *,
        ahora: datetime,
    ) -> bool:
        """Resuelve entidad, valida estado/consentimiento y escribe el outbox."""
        solicitud: SolicitudEnvio | None = None
        entidad_tipo = recordatorio.entidad_tipo
        if recordatorio.entidad_tipo == ENTIDAD_CITA:
            datos_cita = await self._datos_cita(recordatorio.entidad_id)
            if datos_cita is not None:
                cita, paciente, sede, profesional, clinica = datos_cita
                cita_valida = (
                    cita.estado in (EstadoCita.CONFIRMED.value, EstadoCita.RESCHEDULED.value)
                    and cita.inicio > ahora
                    and recordatorio.clinica_id == cita.clinica_id
                    and recordatorio.destinatario_id == paciente.id
                )
                try:
                    tipo = TipoMensajeOutbox(recordatorio.tipo)
                except ValueError:
                    tipo = None
                if cita_valida and tipo in {
                    TipoMensajeOutbox.CITA_RECORDATORIO_DIA_ANTES,
                    TipoMensajeOutbox.CITA_RECORDATORIO_HORAS_ANTES,
                }:
                    solicitud = SolicitudEnvio(
                        tipo=tipo,
                        canal=CanalOutbox.WHATSAPP,
                        destino_tipo="PACIENTE",
                        destino_id=paciente.id,
                        clave_deduplicacion=f"recordatorio:{recordatorio.id}",
                        variables=self._variables(tipo, cita, paciente, sede, profesional, clinica),
                        clinica_id=cita.clinica_id,
                        entidad_origen_tipo=ENTIDAD_CITA,
                        entidad_origen_id=cita.id,
                    )
        elif recordatorio.entidad_tipo == ENTIDAD_TOMA:
            datos_toma = await self._datos_toma(recordatorio.entidad_id)
            if (
                datos_toma is not None
                and recordatorio.tipo == TipoMensajeOutbox.TOMA_RECORDATORIO.value
            ):
                toma, receta, paciente = datos_toma
                if (
                    recordatorio.clinica_id == receta.clinica_id
                    and recordatorio.destinatario_id == paciente.id
                ):
                    solicitud = SolicitudEnvio(
                        tipo=TipoMensajeOutbox.TOMA_RECORDATORIO,
                        canal=CanalOutbox.WHATSAPP,
                        destino_tipo="PACIENTE",
                        destino_id=paciente.id,
                        clave_deduplicacion=f"recordatorio:{recordatorio.id}",
                        variables={
                            "nombre": paciente.nombre,
                            "enlace": f"{self._url_aplicacion}/acceso",
                        },
                        clinica_id=receta.clinica_id,
                        entidad_origen_tipo=ENTIDAD_TOMA,
                        entidad_origen_id=toma.id,
                    )
        if solicitud is None:
            return self._omitir(recordatorio)

        try:
            mensaje_id = await servicio_outbox.encolar(solicitud)
        except ConsentimientoRequerido:
            logger.info(
                "recordatorio.omitido_sin_consentimiento",
                recordatorio_id=str(recordatorio.id),
                entidad_tipo=entidad_tipo,
            )
            return self._omitir(recordatorio)

        if mensaje_id is None:
            mensaje_id = (
                await self._sesion.execute(
                    select(OutboxMensaje.id).where(
                        OutboxMensaje.clave_deduplicacion == f"recordatorio:{recordatorio.id}"
                    )
                )
            ).scalar_one_or_none()
        recordatorio.estado = ESTADO_ENCOLADO
        recordatorio.outbox_mensaje_id = mensaje_id
        return True

    @staticmethod
    def _omitir(recordatorio: Recordatorio) -> bool:
        recordatorio.estado = ESTADO_OMITIDO
        return False

    async def _datos_cita(
        self, cita_id: uuid.UUID
    ) -> tuple[Cita, Paciente, Sede, Profesional, Clinica] | None:
        consulta = (
            select(Cita, Paciente, Sede, Profesional, Clinica)
            .join(Paciente, Paciente.id == Cita.paciente_id)
            .join(Sede, Sede.id == Cita.sede_id)
            .join(Profesional, Profesional.id == Cita.profesional_id)
            .join(Clinica, Clinica.id == Cita.clinica_id)
            .where(Cita.id == cita_id)
        )
        fila = (await self._sesion.execute(consulta)).one_or_none()
        return tuple(fila) if fila is not None else None

    async def _datos_toma(self, toma_id: uuid.UUID) -> tuple[Toma, Receta, Paciente] | None:
        consulta = (
            select(Toma, Receta, Paciente)
            .join(RecetaMedicamento, RecetaMedicamento.id == Toma.receta_medicamento_id)
            .join(Receta, Receta.id == RecetaMedicamento.receta_id)
            .join(Paciente, Paciente.id == Toma.paciente_id)
            .where(
                Toma.id == toma_id,
                Toma.estado == EstadoToma.PENDIENTE.value,
                Receta.estado == EstadoReceta.CONFIRMADA.value,
                Paciente.clinica_id == Receta.clinica_id,
            )
        )
        fila = (await self._sesion.execute(consulta)).one_or_none()
        return tuple(fila) if fila is not None else None

    @staticmethod
    def _variables(
        tipo: TipoMensajeOutbox,
        cita: Cita,
        paciente: Paciente,
        sede: Sede,
        profesional: Profesional,
        clinica: Clinica,
    ) -> dict[str, str]:
        zona = ZoneInfo(clinica.zona_horaria)
        inicio = cita.inicio.astimezone(zona)
        comunes = {
            "nombre": paciente.nombre,
            "fecha": inicio.strftime("%d/%m/%Y"),
            "hora": inicio.strftime("%H:%M"),
            "sede": sede.nombre,
            "profesional": f"{profesional.nombre} {profesional.apellido}".strip(),
        }
        if tipo is TipoMensajeOutbox.CITA_RECORDATORIO_DIA_ANTES:
            return comunes
        if tipo is TipoMensajeOutbox.CITA_RECORDATORIO_HORAS_ANTES:
            return {"nombre": comunes["nombre"], "hora": comunes["hora"], "sede": comunes["sede"]}
        raise ValueError(f"Tipo de recordatorio de cita no admitido: {tipo.value}.")


__all__ = ["ResumenRecordatorios", "ServicioRecordatorios"]
