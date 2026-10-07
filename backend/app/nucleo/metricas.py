"""Métricas operativas con etiquetas acotadas y sin datos de pacientes."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from re import Pattern

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from sqlalchemy import func, select
from starlette.routing import compile_path

from app.modulos.outbox.modelos import EstadoOutbox, OutboxMensaje
from app.nucleo.bd import GestorBaseDatos
from app.nucleo.registro import obtener_logger
from app.nucleo.reloj import Reloj

LIMITE_LONGITUD_RUTA = 200
_logger = obtener_logger(__name__)


class MetricasAplicacion:
    """Registro aislado por instancia de API, también seguro para pruebas."""

    def __init__(self) -> None:
        self.registro = CollectorRegistry()
        self.solicitudes = Counter(
            "clinicai_http_solicitudes_total",
            "Solicitudes HTTP atendidas por ClinicAI.",
            ("metodo", "ruta", "estado"),
            registry=self.registro,
        )
        self.duracion = Histogram(
            "clinicai_http_duracion_segundos",
            "Duración de las solicitudes HTTP.",
            ("metodo", "ruta"),
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
            registry=self.registro,
        )
        self.mensajes_outbox = Gauge(
            "clinicai_outbox_mensajes",
            "Mensajes del outbox agrupados por estado.",
            ("estado",),
            registry=self.registro,
        )
        self.pendiente_mas_antiguo = Gauge(
            "clinicai_outbox_pendiente_mas_antiguo_segundos",
            "Antigüedad del mensaje PENDIENTE más antiguo.",
            registry=self.registro,
        )
        self.error_lectura_outbox = Gauge(
            "clinicai_outbox_lectura_fallida",
            "Vale 1 si no se pudo consultar el estado del outbox.",
            registry=self.registro,
        )
        self._rutas: list[tuple[Pattern[str], str]] = []

    def configurar_rutas(self, rutas: list[str]) -> None:
        """Prepara plantillas de OpenAPI para reemplazar IDs en URL reales."""
        self._rutas = [(compile_path(ruta)[0], ruta) for ruta in rutas]

    def normalizar_ruta(self, ruta_solicitada: str) -> str:
        for expresion, plantilla in self._rutas:
            if expresion.fullmatch(ruta_solicitada):
                return plantilla if len(plantilla) <= LIMITE_LONGITUD_RUTA else "ruta_desconocida"
        return "no_encontrada"

    def registrar_solicitud(
        self, *, metodo: str, ruta: str, estado: int, duracion_segundos: float
    ) -> None:
        metodos_admitidos = {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}
        metodo_seguro = metodo if metodo in metodos_admitidos else "OTHER"
        ruta_segura = self.normalizar_ruta(ruta)
        self.solicitudes.labels(metodo_seguro, ruta_segura, str(estado)).inc()
        self.duracion.labels(metodo_seguro, ruta_segura).observe(max(0, duracion_segundos))

    def exportar(self) -> bytes:
        return generate_latest(self.registro)


async def actualizar_metricas_outbox(
    metricas: MetricasAplicacion, gestor: GestorBaseDatos, reloj: Reloj
) -> None:
    """Refresca gauges al hacer scrape; no conserva contenido ni clínica."""
    try:
        async for sesion in gestor.sesion():
            conteos = await sesion.execute(
                select(OutboxMensaje.estado, func.count()).group_by(OutboxMensaje.estado)
            )
            por_estado: Mapping[str, int] = {
                str(estado): int(cantidad) for estado, cantidad in conteos.all()
            }
            for estado in EstadoOutbox:
                metricas.mensajes_outbox.labels(estado.value).set(por_estado.get(estado.value, 0))

            mas_antiguo: datetime | None = await sesion.scalar(
                select(func.min(OutboxMensaje.creado_en)).where(
                    OutboxMensaje.estado == EstadoOutbox.PENDIENTE.value
                )
            )
            segundos = (reloj.ahora() - mas_antiguo).total_seconds() if mas_antiguo else 0
            metricas.pendiente_mas_antiguo.set(max(0, segundos))
            metricas.error_lectura_outbox.set(0)
            return
    except Exception:
        _logger.warning("metricas.outbox_lectura_fallida")
        metricas.error_lectura_outbox.set(1)
        return


__all__ = ["MetricasAplicacion", "actualizar_metricas_outbox"]
