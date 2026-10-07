"""Catálogo de automatizaciones: qué pasa solo, cuándo, y quién lo ve o actúa.

Cada flujo une un **disparador** (algo que ocurre en la clínica) con una
**acción** automática, y declara quién la ve y quién interviene. El catálogo
está en código y no en base de datos a propósito: un flujo nuevo exige
programar su disparador, y una fila que dijera «activo» sin código detrás
sería una promesa falsa. Lo que la clínica decide es si cada flujo está
encendido (`servicios.py`).

Reglas que los flujos no rompen (CLAUDE.md):

* Ningún mensaje lleva diagnóstico, medicamento ni motivo de consulta.
* La IA no decide nada clínico: lo clínico deriva a una persona.
* Los flujos ``obligatorio`` no se apagan: avisar al paciente de que su cita
  cambió y derivar a una persona lo que el asistente no entiende son
  garantías, no preferencias.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.modulos.outbox.modelos import TipoMensajeOutbox


class Fase(StrEnum):
    ANTES = "ANTES_DE_LA_CITA"
    DIA = "DIA_DE_LA_CITA"
    DESPUES = "DESPUES_DE_LA_CITA"
    MEDICACION = "MEDICACION"
    PAGOS = "PAGOS"
    MENSAJES = "MENSAJES"
    EQUIPO = "EQUIPO"


@dataclass(frozen=True, slots=True)
class Flujo:
    codigo: str
    nombre: str
    fase: Fase
    disparador: str
    accion: str
    canal: str
    quien_ve: tuple[str, ...]
    quien_interviene: tuple[str, ...]
    # Tipos de mensaje que genera. Si el flujo está apagado, no se encolan.
    tipos: tuple[TipoMensajeOutbox, ...] = ()
    obligatorio: bool = False
    nota: str | None = None


FLUJOS: tuple[Flujo, ...] = (
    Flujo(
        codigo="confirmacion_cita",
        nombre="Confirmación de la cita",
        fase=Fase.ANTES,
        disparador="Se reserva una cita (recepción, profesional o el propio paciente por WhatsApp).",
        accion="WhatsApp al paciente con fecha, hora y sede, sin motivo de consulta.",
        canal="WhatsApp",
        quien_ve=("Recepción", "Profesional de la cita"),
        quien_interviene=("Paciente (confirma o cancela)",),
        tipos=(TipoMensajeOutbox.CITA_CONFIRMACION,),
    ),
    Flujo(
        codigo="recordatorio_dia_antes",
        nombre="Recordatorio el día anterior",
        fase=Fase.ANTES,
        disparador="Falta un día para la cita.",
        accion="WhatsApp de recordatorio con opción de confirmar o reprogramar.",
        canal="WhatsApp",
        quien_ve=("Recepción",),
        quien_interviene=("Paciente",),
        tipos=(TipoMensajeOutbox.CITA_RECORDATORIO_DIA_ANTES,),
    ),
    Flujo(
        codigo="recordatorio_horas_antes",
        nombre="Recordatorio unas horas antes",
        fase=Fase.ANTES,
        disparador="Faltan pocas horas para la cita.",
        accion="WhatsApp breve con la hora y la sede.",
        canal="WhatsApp",
        quien_ve=("Recepción",),
        quien_interviene=("Paciente",),
        tipos=(TipoMensajeOutbox.CITA_RECORDATORIO_HORAS_ANTES,),
    ),
    Flujo(
        codigo="por_confirmar_a_recepcion",
        nombre="Citas por confirmar a la cola de recepción",
        fase=Fase.ANTES,
        disparador="Una cita sigue pendiente o un turno apartado está por caducar.",
        accion="Aparece en «Lo primero» del panel y en el contador «Por confirmar».",
        canal="Panel",
        quien_ve=("Recepción", "Administración"),
        quien_interviene=("Recepción (llama al paciente)",),
        obligatorio=True,
        nota="Es una vista de trabajo: no envía nada.",
    ),
    Flujo(
        codigo="aviso_cambio_cita",
        nombre="Aviso de cancelación o reprogramación",
        fase=Fase.ANTES,
        disparador="La clínica cancela o mueve una cita.",
        accion="WhatsApp al paciente con el cambio.",
        canal="WhatsApp",
        quien_ve=("Recepción", "Profesional de la cita"),
        quien_interviene=("Paciente",),
        tipos=(TipoMensajeOutbox.CITA_CANCELACION, TipoMensajeOutbox.CITA_REPROGRAMACION),
        obligatorio=True,
        nota="Obligatorio: el paciente no puede enterarse en la puerta de que su cita ya no existe.",
    ),
    Flujo(
        codigo="oferta_lista_espera",
        nombre="Hueco liberado a la lista de espera",
        fase=Fase.ANTES,
        disparador="Se cancela una cita y hay pacientes esperando ese servicio.",
        accion="Oferta por WhatsApp a una persona a la vez, con plazo para responder.",
        canal="WhatsApp",
        quien_ve=("Recepción",),
        quien_interviene=("Paciente (acepta o rechaza)", "Recepción (llama si no tiene WhatsApp)"),
        tipos=(
            TipoMensajeOutbox.OFERTA_TURNO,
            TipoMensajeOutbox.OFERTA_EXPIRADA,
            TipoMensajeOutbox.OFERTA_PERDIDA,
        ),
    ),
    Flujo(
        codigo="sala_de_espera",
        nombre="Llegada y sala de espera",
        fase=Fase.DIA,
        disparador="Recepción registra la llegada del paciente.",
        accion="El profesional ve al paciente «En sala» en su agenda y en su panel.",
        canal="Panel",
        quien_ve=("Profesional de la cita", "Recepción"),
        quien_interviene=("Profesional (inicia la atención)",),
        obligatorio=True,
        nota="Es una vista de trabajo: no envía nada.",
    ),
    Flujo(
        codigo="resumen_diario_profesional",
        nombre="Resumen del día al profesional",
        fase=Fase.DIA,
        disparador="Inicio de la jornada.",
        accion="Mensaje al profesional con cuántas citas tiene y a qué hora empieza.",
        canal="WhatsApp / correo",
        quien_ve=("Profesional",),
        quien_interviene=("Profesional",),
        tipos=(TipoMensajeOutbox.RESUMEN_DIARIO_PROFESIONAL,),
    ),
    Flujo(
        codigo="cambio_agenda_profesional",
        nombre="Aviso de cambios en la agenda del profesional",
        fase=Fase.DIA,
        disparador="Se crea, cancela o mueve una cita del profesional para hoy o mañana.",
        accion="Aviso al profesional, sin datos clínicos.",
        canal="WhatsApp / correo",
        quien_ve=("Profesional",),
        quien_interviene=("Profesional",),
        tipos=(TipoMensajeOutbox.CAMBIO_AGENDA_PROFESIONAL,),
    ),
    Flujo(
        codigo="indicaciones_postconsulta",
        nombre="Indicaciones después de la consulta",
        fase=Fase.DESPUES,
        disparador="El profesional publica las indicaciones de la consulta.",
        accion=(
            "WhatsApp genérico «su profesional dejó indicaciones» con un enlace que caduca; "
            "el paciente verifica su identidad y las lee en una página protegida."
        ),
        canal="WhatsApp + enlace seguro",
        quien_ve=("Paciente (tras verificar identidad)", "Profesional que las escribió"),
        quien_interviene=("Profesional (las redacta)",),
        tipos=(TipoMensajeOutbox.INDICACIONES_DISPONIBLES,),
        nota="El mensaje no incluye ni medicamento ni indicación: solo el aviso y el enlace.",
    ),
    Flujo(
        codigo="seguimiento_tratamiento",
        nombre="Seguimiento del plan de tratamiento",
        fase=Fase.DESPUES,
        disparador="Se cierra una fase del plan y quedan otras pendientes.",
        accion="Recordatorio genérico para agendar la siguiente cita.",
        canal="WhatsApp",
        quien_ve=("Profesional", "Recepción"),
        quien_interviene=("Paciente (agenda)",),
        tipos=(TipoMensajeOutbox.SEGUIMIENTO_TRATAMIENTO,),
    ),
    Flujo(
        codigo="recordatorio_toma",
        nombre="Alarma de cada toma",
        fase=Fase.MEDICACION,
        disparador="Llega la hora de una toma de una receta confirmada.",
        accion=(
            "WhatsApp genérico sin medicamento; si el paciente responde TOMADA, la toma se "
            "registra sola."
        ),
        canal="WhatsApp",
        quien_ve=("Paciente",),
        quien_interviene=("Paciente (responde TOMADA)",),
        tipos=(TipoMensajeOutbox.TOMA_RECORDATORIO,),
        nota="Exige el consentimiento propio de recordatorios de medicación.",
    ),
    Flujo(
        codigo="seguimiento_toma",
        nombre="Seguimiento de una toma sin respuesta",
        fase=Fase.MEDICACION,
        disparador="El paciente no confirmó la toma.",
        accion="Segundo aviso genérico al paciente.",
        canal="WhatsApp",
        quien_ve=("Paciente",),
        quien_interviene=("Paciente",),
        tipos=(TipoMensajeOutbox.TOMA_SEGUIMIENTO,),
    ),
    Flujo(
        codigo="alerta_adherencia",
        nombre="Alerta de adherencia al equipo",
        fase=Fase.MEDICACION,
        disparador="Varias tomas sin confirmar en los últimos días.",
        accion="Alerta en el panel del asistente y del profesional para llamar al paciente.",
        canal="Panel",
        quien_ve=("Asistente", "Profesional que recetó"),
        quien_interviene=("Asistente (llama)", "Profesional (decide)"),
        tipos=(TipoMensajeOutbox.ALERTA_PERSONAL,),
        nota="La alerta no sugiere cambiar la medicación: eso lo decide el profesional.",
    ),
    Flujo(
        codigo="comprobante_pago",
        nombre="Comprobante de pago recibido",
        fase=Fase.PAGOS,
        disparador="El paciente envía la foto del comprobante por WhatsApp.",
        accion=(
            "Si tiene un único pago pendiente, pasa a «Comprobante recibido» y aparece en "
            "«Por validar»; si no, la imagen va a «Atención de mensajes»."
        ),
        canal="Panel",
        quien_ve=("Recepción", "Administración"),
        quien_interviene=("Quien valida pagos (confirma o rechaza)",),
        obligatorio=True,
        nota="Ningún dato de tarjeta pasa por el chat.",
    ),
    Flujo(
        codigo="derivacion_a_persona",
        nombre="Derivación a una persona",
        fase=Fase.MENSAJES,
        disparador="El asistente no entiende con certeza, o la consulta es clínica o urgente.",
        accion="La conversación pasa a «Atención de mensajes» con su motivo.",
        canal="Bandeja",
        quien_ve=("Recepción", "Asistente", "Profesional"),
        quien_interviene=("Quien toma la conversación",),
        obligatorio=True,
        nota="Obligatorio: la IA no responde nada clínico (CLAUDE.md, regla 5).",
    ),
    Flujo(
        codigo="promociones",
        nombre="Campañas de promoción",
        fase=Fase.MENSAJES,
        disparador="Administración aprueba una campaña.",
        accion="WhatsApp con imagen a quienes aceptaron recibir publicidad.",
        canal="WhatsApp",
        quien_ve=("Administración",),
        quien_interviene=("Quien aprueba la campaña",),
        tipos=(TipoMensajeOutbox.PROMOCION,),
    ),
)

FLUJOS += (
    Flujo(
        codigo="documentos",
        nombre="Entrega de documentos",
        fase=Fase.MENSAJES,
        disparador="El profesional solicita compartir un PDF con el paciente.",
        accion="Aviso genérico con enlace privado y temporal; el PDF exige verificación.",
        canal="WhatsApp",
        quien_ve=("Profesional",),
        quien_interviene=("Profesional",),
        tipos=(TipoMensajeOutbox.DOCUMENTO_DISPONIBLE,),
        nota="Exige consentimiento específico para documentos. No comparte N3 ni mapas faciales.",
    ),
)

POR_CODIGO: dict[str, Flujo] = {flujo.codigo: flujo for flujo in FLUJOS}

FLUJO_POR_TIPO: dict[TipoMensajeOutbox, Flujo] = {
    tipo: flujo for flujo in FLUJOS for tipo in flujo.tipos
}

__all__ = ["FLUJOS", "FLUJO_POR_TIPO", "POR_CODIGO", "Fase", "Flujo"]
