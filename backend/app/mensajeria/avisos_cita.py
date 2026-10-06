"""Aviso al paciente cuando su cita se mueve o se cancela.

Un solo camino para el panel, el agente de WhatsApp y la prolongación de otra
atención: si cada uno avisara por su cuenta, uno olvidaría hacerlo y otro lo
haría dos veces. La clave de deduplicación incluye el nuevo horario, así que
mover dos veces la misma cita avisa dos veces, pero repetir la misma petición
no.

Sin datos clínicos (regla 10): fecha, hora, sede y profesional. Si el paciente
no aceptó avisos por WhatsApp, o la clínica apagó el flujo, no se envía y no
es un error.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.mensajeria.adaptadores import RegistroCanales
from app.mensajeria.servicios import ServicioOutbox, SolicitudEnvio
from app.modulos.agenda.modelos import Cita
from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.outbox.modelos import CanalOutbox, TipoMensajeOutbox
from app.modulos.pacientes.modelos import Paciente
from app.modulos.profesionales.modelos import Profesional
from app.nucleo.errores import ConsentimientoRequerido
from app.nucleo.idempotencia import calcular_clave_deduplicacion
from app.nucleo.registro import obtener_logger
from app.nucleo.reloj import Reloj

logger = obtener_logger(__name__)

ZONA_POR_OMISION = "America/Guayaquil"


async def avisar_cambio_de_cita(
    sesion: AsyncSession, reloj: Reloj, cita: Cita, tipo: TipoMensajeOutbox
) -> None:
    """Encola el aviso de reprogramación o cancelación. No hace `commit`."""
    fila = (
        await sesion.execute(
            select(
                Paciente.nombre,
                Sede.nombre,
                Sede.zona_horaria,
                Sede.telefono,
                Clinica.zona_horaria,
                Clinica.telefono,
                Profesional.nombre,
                Profesional.apellido,
            )
            .select_from(Cita)
            .join(Paciente, Paciente.id == Cita.paciente_id)
            .join(Sede, Sede.id == Cita.sede_id)
            .join(Clinica, Clinica.id == Cita.clinica_id)
            .join(Profesional, Profesional.id == Cita.profesional_id)
            .where(Cita.id == cita.id)
        )
    ).first()
    if fila is None:
        return
    nombre, sede, zona_sede, tel_sede, zona_clinica, tel_clinica, prof_nombre, prof_apellido = fila
    local = cita.inicio.astimezone(ZoneInfo(zona_sede or zona_clinica or ZONA_POR_OMISION))
    variables = {
        "nombre": (nombre or "").split(" ")[0],
        "fecha": local.strftime("%d/%m/%Y"),
        "hora": local.strftime("%H:%M"),
        "sede": sede or "",
    }
    if tipo is TipoMensajeOutbox.CITA_REPROGRAMACION:
        variables["profesional"] = f"{prof_nombre} {prof_apellido}".strip()
    else:
        variables["telefono_clinica"] = tel_sede or tel_clinica or "la clínica"
    try:
        await ServicioOutbox(sesion, reloj, RegistroCanales()).encolar(
            SolicitudEnvio(
                tipo=tipo,
                canal=CanalOutbox.WHATSAPP,
                destino_tipo="PACIENTE",
                destino_id=cita.paciente_id,
                clave_deduplicacion=calcular_clave_deduplicacion(
                    tipo.value.lower(), str(cita.id), cita.inicio.isoformat()
                ),
                variables=variables,
                clinica_id=cita.clinica_id,
                entidad_origen_tipo="cita",
                entidad_origen_id=cita.id,
            )
        )
    except ConsentimientoRequerido:
        logger.info("aviso_cita.sin_consentimiento", cita_id=str(cita.id), tipo=tipo.value)


__all__ = ["avisar_cambio_de_cita"]
