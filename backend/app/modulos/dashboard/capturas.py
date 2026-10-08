"""Series de estados operativos capturados, privadas por actor y ámbito.

No se reconstruye el pasado a partir del estado actual. Cada fecha conserva
la última captura disponible; días sin consulta son desconocidos, nunca cero.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import ForeignKey, String, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.modulos.dashboard.indicadores import calcular
from app.nucleo.autorizacion import Principal
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


def huella_ambito(principal: Principal) -> str:
    ambito = principal.ambito
    datos: dict[str, Any] = {
        "permisos": sorted(principal.permisos),
        "roles": sorted(str(r) for r in principal.role_ids),
        "profesional": str(principal.profesional_id),
        "nivel_maximo": ambito.nivel_maximo.value,
        "version": 1,
    }
    for dimension, comodin in (
        ("sedes", "todas_las_sedes"),
        ("especialidades", "todas_las_especialidades"),
        ("profesionales", "todos_los_profesionales"),
        ("pacientes", "todos_los_pacientes"),
    ):
        datos[dimension] = sorted(str(v) for v in getattr(ambito, dimension))
        datos[comodin] = getattr(ambito, comodin)
    return hashlib.sha256(json.dumps(datos, sort_keys=True).encode()).hexdigest()


async def capturar_y_leer(
    sesion: AsyncSession, principal: Principal, ahora: datetime, zona: str, dias: int
) -> tuple[dict[str, float], list[CapturaIndicadores]]:
    if principal.actor_id is None or principal.clinica_id is None:
        return {}, []
    hoy = ahora.astimezone(ZoneInfo(zona)).date()
    desde = datetime.combine(hoy, time.min, ZoneInfo(zona))
    indicadores = await calcular(sesion, principal, desde, desde + timedelta(days=1))
    valores: dict[str, float] = {}
    for grupo, campos in indicadores.model_dump().items():
        if not isinstance(campos, dict):
            continue
        for campo, valor in campos.items():
            clave = f"{grupo}.{campo}"
            if clave in NOMBRES and isinstance(valor, (int, float, Decimal)):
                valores[clave] = float(valor)
    huella = huella_ambito(principal)
    stmt = insert(CapturaIndicadores).values(
        id=uuid.uuid4(),
        clinica_id=principal.clinica_id,
        actor_id=principal.actor_id,
        ambito_hash=huella,
        fecha=hoy,
        capturado_en=ahora,
        valores=valores,
    )
    await sesion.execute(
        stmt.on_conflict_do_update(
            constraint="uq_captura_indicadores_clinica_id",
            set_={"capturado_en": ahora, "valores": valores},
            where=CapturaIndicadores.capturado_en <= ahora,
        )
    )
    filas = list(
        (
            await sesion.scalars(
                select(CapturaIndicadores)
                .where(
                    CapturaIndicadores.clinica_id == principal.clinica_id,
                    CapturaIndicadores.actor_id == principal.actor_id,
                    CapturaIndicadores.ambito_hash == huella,
                    CapturaIndicadores.fecha >= hoy - timedelta(days=dias),
                    CapturaIndicadores.fecha < hoy,
                )
                .order_by(CapturaIndicadores.fecha)
            )
        ).all()
    )
    return valores, filas
