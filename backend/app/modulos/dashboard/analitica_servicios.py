from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from statistics import mean
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.dashboard.analitica_repositorio import RepositorioAnalitica
from app.modulos.dashboard.aprendizaje import (
    EvidenciaModelo,
    PuntoPronostico,
    PuntoSerie,
    pronosticar,
)
from app.modulos.dashboard.capturas import NOMBRES
from app.modulos.dashboard.capturas_repositorio import capturar_y_leer
from app.nucleo.autorizacion import Principal

DEFINICIONES = {
    "citas": (
        "Citas programadas",
        "citas",
        "Conteo por fecha de cita; incluye estados finales y pendientes.",
    ),
    "atenciones": (
        "Atenciones realizadas",
        "atenciones",
        "Citas con estado COMPLETED por fecha de cita.",
    ),
    "inasistencias": ("Inasistencias", "citas", "Citas marcadas NO_SHOW por fecha de cita."),
    "cancelaciones": (
        "Cancelaciones",
        "citas",
        "Citas actualmente CANCELLED por fecha de cita; no fecha de cancelación.",
    ),
    "pendientes": (
        "Citas pendientes",
        "citas",
        "Estado PENDING/HELD en fechas ya transcurridas; revisión de cierres pendientes.",
    ),
    "minutos_atendidos": (
        "Tiempo de atención programado",
        "minutos",
        "Suma de duración programada de citas COMPLETED; no duración real de consulta.",
    ),
    "pacientes_dia": (
        "Pacientes únicos diarios",
        "personas/día",
        "Personas con cita cada día. Una persona puede contarse en varios días.",
    ),
    "espera": (
        "Espera media",
        "minutos",
        "Promedio entre llegada e inicio de atención; días sin mediciones no son cero.",
    ),
    "cobros": (
        "Cobros confirmados",
        "USD",
        "Pagos actualmente confirmados por fecha de validación, dentro del ámbito de citas.",
    ),
    "gastos": (
        "Gastos registrados",
        "USD",
        "Gastos vigentes por fecha de comprobante; omite anulados y respeta sedes.",
    ),
    "registros_pacientes": (
        "Altas de pacientes",
        "personas",
        "Registros administrativos creados por día; no adquisición atribuida a una especialidad.",
    ),
    "tasa_asistencia": (
        "Asistencia entre citas cerradas",
        "%",
        "Atenciones / (atenciones + inasistencias) x 100.",
    ),
    "tasa_inasistencia": (
        "Inasistencia entre citas cerradas",
        "%",
        "Inasistencias / (atenciones + inasistencias) x 100.",
    ),
    "tasa_cancelacion": ("Proporción cancelada", "%", "Cancelaciones / citas programadas x 100."),
    "ingreso_por_atencion": (
        "Cobros por atención del día",
        "USD/atención",
        "Cobros validados / atenciones en la misma fecha; no ticket de tratamiento ni atribución causal.",
    ),
}


class KpiAnalitico(BaseModel):
    clave: str
    nombre: str
    unidad: str
    definicion: str
    total: float | None
    agregacion: str
    historia: list[PuntoSerie]
    evidencia: EvidenciaModelo
    prediccion: list[PuntoPronostico]


class RecomendacionOperativa(BaseModel):
    titulo: str
    motivo: str
    accion: str
    ruta: str
    prioridad: str
    kpis: list[str]
    requiere_revision: bool = True


class AnaliticaDashboard(BaseModel):
    generado_en: datetime
    zona_horaria: str
    desde: date
    hasta: date
    horizonte: int
    kpis: list[KpiAnalitico]
    recomendaciones: list[RecomendacionOperativa]
    limites: list[str]


async def analizar(
    sesion: AsyncSession,
    principal: Principal,
    ahora: datetime,
    dias: int,
    horizonte: int,
    sede_id: uuid.UUID | None = None,
    profesional_id: uuid.UUID | None = None,
    especialidad_id: uuid.UUID | None = None,
    servicio_id: uuid.UUID | None = None,
) -> AnaliticaDashboard:
    repo = RepositorioAnalitica(sesion)
    zona = await repo.zona(principal)
    hasta = ahora.astimezone(ZoneInfo(zona)).date()
    desde = hasta - timedelta(days=dias)
    datos = await repo.series(
        principal, desde, hasta, zona, sede_id, profesional_id, especialidad_id, servicio_id
    )
    for clave, num, den in (
        ("tasa_asistencia", "atenciones", "cerradas"),
        ("tasa_inasistencia", "inasistencias", "cerradas"),
        ("tasa_cancelacion", "cancelaciones", "citas"),
        ("ingreso_por_atencion", "cobros", "atenciones"),
    ):
        if num not in datos or (den != "cerradas" and den not in datos):
            continue
        cocientes = {}
        for i in range(dias):
            dia = desde + timedelta(days=i)
            divisor = (
                sum(datos[k].get(dia, (0, 0))[0] for k in ("atenciones", "inasistencias"))
                if den == "cerradas"
                else datos[den].get(dia, (0, 0))[0]
            )
            if divisor:
                cocientes[dia] = (
                    datos[num].get(dia, (0, 0))[0]
                    / divisor
                    * (1 if clave == "ingreso_por_atencion" else 100),
                    int(divisor),
                )
        datos[clave] = cocientes
    kpis = []
    fechas_actividad = sorted(
        {
            d
            for k, v in datos.items()
            if not k.startswith("tasa_") and k != "ingreso_por_atencion"
            for d in v
        }
    )
    primer_dato = max(desde, fechas_actividad[0]) if fechas_actividad else hasta
    for clave, valores in datos.items():
        nombre, unidad, definicion = DEFINICIONES[clave]
        media = clave in {
            "espera",
            "tasa_asistencia",
            "tasa_inasistencia",
            "tasa_cancelacion",
            "ingreso_por_atencion",
        }
        # Nunca rellenar ceros antes del primer evento observado en el ámbito.
        primer_kpi = max(primer_dato, min(valores) if valores else hasta)
        historia = [
            PuntoSerie(
                fecha=d,
                valor=valores[d][0] if d in valores else None if media else 0,
                muestras=valores[d][1] if d in valores else 0,
            )
            for d in (
                primer_kpi + timedelta(days=i) for i in range(max(0, (hasta - primer_kpi).days))
            )
        ]
        evidencia, futuro = pronosticar(historia, horizonte, 100 if unidad == "%" else None)
        observados = [p for p in historia if p.valor is not None]
        if media:
            divisor = sum(p.muestras for p in observados)
            total = (
                sum(float(p.valor) * p.muestras for p in observados if p.valor is not None)
                / divisor
                if divisor
                else None
            )
        else:
            total = sum(float(p.valor) for p in observados if p.valor is not None)
        kpis.append(
            KpiAnalitico(
                clave=clave,
                nombre=nombre,
                unidad=unidad,
                definicion=definicion,
                total=round(total, 2) if total is not None else None,
                agregacion="media ponderada por observaciones" if media else "suma del período",
                historia=historia,
                evidencia=evidencia,
                prediccion=futuro,
            )
        )
    if not any((sede_id, profesional_id, especialidad_id, servicio_id)):
        actuales, capturas = await capturar_y_leer(sesion, principal, ahora, zona, dias)
        for clave, valor in actuales.items():
            por_dia = {c.fecha: c.valores[clave] for c in capturas if clave in c.valores}
            primero = min(por_dia) if por_dia else hasta
            historia = [
                PuntoSerie(fecha=d, valor=por_dia.get(d), muestras=1 if d in por_dia else 0)
                for d in (primero + timedelta(days=i) for i in range((hasta - primero).days))
            ]
            evidencia, futuro = pronosticar(historia, horizonte)
            kpis.append(
                KpiAnalitico(
                    clave="estado." + clave,
                    nombre=NOMBRES[clave],
                    unidad="USD" if clave == "pagos.confirmado_30_dias" else "registros",
                    definicion="Estado actual. La serie utiliza la última captura de cada día en este mismo ámbito; días sin captura quedan sin evaluar.",
                    total=valor,
                    agregacion="captura actual",
                    historia=historia,
                    evidencia=evidencia,
                    prediccion=futuro,
                )
            )
    await sesion.commit()
    return AnaliticaDashboard(
        generado_en=ahora,
        zona_horaria=zona,
        desde=desde,
        hasta=hasta - timedelta(days=1),
        horizonte=horizonte,
        kpis=kpis,
        recomendaciones=recomendar(kpis, principal),
        limites=[
            "Solo días completos en la zona de la clínica. Los filtros reducen también el entrenamiento.",
            "Los estados e importes reflejan los registros actuales; una corrección puede modificar series pasadas.",
            "Selección temporal de 7 días y evaluación posterior de 7 días. Reajuste local al consultar datos nuevos.",
            "Aprendizaje estadístico local, sin API externa. Bandas empíricas de error, sin garantía de resultados.",
            "Los indicadores de estado acumulan capturas al abrir o actualizar la analítica; no reconstruyen estados anteriores. Cambiar permisos o ámbito inicia otra serie privada.",
            "Las recomendaciones son administrativas y requieren revisión humana; no diagnostican ni prescriben tratamientos.",
        ],
    )


def recomendar(kpis: list[KpiAnalitico], principal: Principal) -> list[RecomendacionOperativa]:
    salida = []
    por_clave = {k.clave: k for k in kpis}
    for clave, umbral, titulo, accion, ruta, permiso in (
        (
            "tasa_inasistencia",
            10,
            "Revisar confirmaciones",
            "Revise confirmaciones y ofrezca los huecos a la lista de espera.",
            "/agenda",
            "agenda.leer",
        ),
        (
            "espera",
            15,
            "Revisar carga de recepción",
            "Revise horarios de llegada y capacidad del equipo antes de reasignar turnos.",
            "/agenda",
            "agenda.leer",
        ),
        (
            "pendientes",
            0,
            "Completar cierres de agenda",
            "Compruebe las citas pasadas pendientes y registre su estado real.",
            "/agenda",
            "agenda.leer",
        ),
    ):
        k = por_clave.get(clave)
        if k is None or not principal.tiene_permiso(permiso):
            continue
        reciente = [p.valor for p in k.historia[-14:] if p.valor is not None]
        futuros = (
            [p.valor for p in k.prediccion] if k.evidencia.estado == "validado_localmente" else []
        )
        indicador = mean(futuros or reciente) if futuros or reciente else 0
        if indicador > umbral:
            salida.append(
                RecomendacionOperativa(
                    titulo=titulo,
                    motivo=f"{'Pronóstico evaluado' if futuros else 'Histórico reciente'}: {indicador:.1f} {k.unidad}; umbral de revisión operativa.",
                    accion=accion,
                    ruta=ruta,
                    prioridad="alta" if clave == "pendientes" else "media",
                    kpis=[clave],
                )
            )
    if not salida:
        salida.append(
            RecomendacionOperativa(
                titulo="Revisar la calidad de los datos",
                motivo="El aprendizaje depende de mediciones consistentes y cierres completos.",
                accion="Revise los indicadores y sus observaciones antes de adoptar medidas.",
                ruta="/analitica",
                prioridad="informativa",
                kpis=[],
            )
        )
    return salida
