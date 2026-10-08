"""Series de estados operativos capturados, privadas por actor y ámbito.

No se reconstruye el pasado a partir del estado actual. Cada fecha conserva
la última captura disponible; días sin consulta son desconocidos, nunca cero.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.nucleo.bd import Base, MezclaIdentificador


class CapturaIndicadores(Base, MezclaIdentificador):
    __tablename__ = "captura_indicadores"
    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    actor_id: Mapped[uuid.UUID] = mapped_column()
    ambito_hash: Mapped[str] = mapped_column(String(64))
    fecha: Mapped[date] = mapped_column()
    capturado_en: Mapped[datetime] = mapped_column()
    valores: Mapped[dict[str, float]] = mapped_column(JSONB)
    __table_args__ = (UniqueConstraint("clinica_id", "actor_id", "ambito_hash", "fecha"),)


NOMBRES = {
    "agenda.citas_hoy": "Citas del día",
    "agenda.por_confirmar_hoy": "Citas por confirmar",
    "agenda.en_sala": "Personas en sala",
    "agenda.en_atencion": "Consultas en curso",
    "agenda.atendidas_hoy": "Citas atendidas hoy",
    "agenda.inasistencias_hoy": "Inasistencias del día",
    "agenda.citas_proximos_7_dias": "Reservas de los próximos 7 días",
    "mis_citas.citas_hoy": "Mis citas de hoy",
    "mis_citas.pendientes_hoy": "Mis citas pendientes",
    "pacientes.total": "Pacientes visibles",
    "pacientes.nuevos_30_dias": "Pacientes registrados en 30 días",
    "pacientes.sin_verificar": "Pacientes por verificar",
    "pacientes.sin_whatsapp": "Pacientes sin contacto WhatsApp",
    "lista_espera.en_espera": "Personas en lista de espera",
    "lista_espera.con_oferta": "Ofertas de turno activas",
    "pagos.pendientes": "Pagos pendientes",
    "pagos.por_validar": "Pagos por validar",
    "pagos.confirmado_30_dias": "Cobros de los últimos 30 días",
    "clinico.recetas_por_confirmar": "Recetas pendientes de confirmar",
    "clinico.planes_propuestos": "Planes propuestos",
    "clinico.planes_en_curso": "Planes en curso",
    "adherencia.alertas_abiertas": "Alertas de seguimiento abiertas",
    "mensajes.derivadas_a_persona": "Conversaciones por atender",
    "mensajes.abiertas": "Conversaciones abiertas",
    "conocimiento.borradores": "Documentos en borrador",
    "conocimiento.en_revision": "Documentos en revisión",
    "conocimiento.vigentes": "Documentos vigentes",
    "promociones.borradores": "Campañas en borrador",
    "promociones.aprobadas_sin_enviar": "Campañas aprobadas sin envío",
    "promociones.enviadas_30_dias": "Campañas enviadas en 30 días",
    "usuarios.activos": "Usuarios activos",
    "usuarios.inactivos": "Usuarios inactivos",
    "usuarios.roles": "Roles disponibles",
}
