"""Pronóstico local aprendido por KPI, con validación temporal separada.

La selección utiliza siete días; la evaluación otros siete posteriores.
No usa identificadores, datos clínicos individuales ni proveedores externos.
Las bandas son errores empíricos de evaluación, no intervalos probabilísticos.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import pairwise
from statistics import mean

from pydantic import BaseModel

MIN_DIAS = 56
MIN_OBSERVACIONES = 42
MIN_ACTIVIDAD = 14
MIN_VALIDACION = 4
VENTANA_MEDIA = 28
MAX_HORIZONTE = 30


class PuntoSerie(BaseModel):
    fecha: date
    valor: float | None
    muestras: int = 0


class PuntoPronostico(BaseModel):
    fecha: date
    valor: float
    inferior: float
    superior: float


class EvidenciaModelo(BaseModel):
    estado: str
    motivo: str
    algoritmo: str | None = None
    observaciones: int
    dias_historia: int
    dias_seleccion: int = 0
    dias_evaluacion: int = 0
    mae: float | None = None
    mae_base: float | None = None
    mejora_porcentaje: float | None = None
    entrenado_hasta: date | None = None
    evaluacion_desde: date | None = None
    evaluacion_hasta: date | None = None
    banda: str = "± percentil 90 del error absoluto observado; banda empírica, no garantía"


@dataclass
class Modelo:
    nombre: str
    nivel: float
    pendiente: float = 0
    origen: date = date.min
    dias: dict[int, float] | None = None

    def predecir(self, fecha: date) -> float:
        if self.dias is not None:
            return self.dias.get(fecha.weekday(), self.nivel)
        return self.nivel + self.pendiente * (fecha - self.origen).days


def ajustar(nombre: str, serie: list[PuntoSerie]) -> Modelo:
    datos = [p for p in serie if p.valor is not None]
    valores = [float(p.valor) for p in datos if p.valor is not None]
    promedio = mean(valores)
    if nombre == "Media móvil 28 días":
        reciente = [
            p.valor
            for p in datos
            if (datos[-1].fecha - p.fecha).days < VENTANA_MEDIA and p.valor is not None
        ]
        return Modelo(nombre, mean(reciente))
    if nombre == "Patrón semanal aprendido":
        return Modelo(
            nombre,
            promedio,
            dias={
                d: mean([p.valor for p in datos if p.fecha.weekday() == d and p.valor is not None])
                for d in range(7)
                if any(p.fecha.weekday() == d for p in datos)
            },
        )
    if nombre.startswith("Suavizado"):
        alfa = float(nombre.rsplit(" ", 1)[1])
        nivel = valores[0]
        for valor in valores[1:]:
            nivel = alfa * valor + (1 - alfa) * nivel
        return Modelo(nombre, nivel)
    origen = datos[0].fecha
    xs = [(p.fecha - origen).days for p in datos]
    mx = mean(xs)
    denominador = sum((x - mx) ** 2 for x in xs)
    pendiente = (
        sum((x - mx) * (y - promedio) for x, y in zip(xs, valores, strict=True)) / denominador
        if denominador
        else 0
    )
    return Modelo(nombre, promedio - pendiente * mx, pendiente, origen)


def pronosticar(
    serie: list[PuntoSerie], horizonte: int = 14, maximo: float | None = None
) -> tuple[EvidenciaModelo, list[PuntoPronostico]]:
    if not 1 <= horizonte <= MAX_HORIZONTE:
        raise ValueError("Horizonte entre 1 y 30 días.")
    if any(a.fecha >= b.fecha for a, b in pairwise(serie)):
        raise ValueError("La serie debe estar ordenada sin fechas duplicadas.")
    if any(p.valor is not None and not math.isfinite(p.valor) for p in serie):
        raise ValueError("Las observaciones deben ser finitas.")
    validos = [p for p in serie if p.valor is not None]
    dias = (serie[-1].fecha - serie[0].fecha).days + 1 if serie else 0
    evidencia = EvidenciaModelo(
        estado="insuficiente",
        motivo="Se necesitan 56 días, 42 observaciones y actividad en al menos 14 días para validar el aprendizaje.",
        observaciones=len(validos),
        dias_historia=dias,
    )
    if (
        dias < MIN_DIAS
        or len(validos) < MIN_OBSERVACIONES
        or sum(p.valor != 0 for p in validos) < MIN_ACTIVIDAD
    ):
        return evidencia, []
    corte = serie[-1].fecha
    entrenamiento = [p for p in serie if p.fecha <= corte - timedelta(days=14)]
    seleccion = [
        p for p in validos if corte - timedelta(days=14) < p.fecha <= corte - timedelta(days=7)
    ]
    evaluacion = [p for p in validos if p.fecha > corte - timedelta(days=7)]
    if (
        len(seleccion) < MIN_VALIDACION
        or len(evaluacion) < MIN_VALIDACION
        or len([p for p in entrenamiento if p.valor is not None]) < VENTANA_MEDIA
    ):
        evidencia.motivo = (
            "Faltan observaciones en los períodos de selección o evaluación temporal."
        )
        return evidencia, []

    def acotar(v: float) -> float:
        return min(maximo, max(0, v)) if maximo is not None else max(0, v)

    def errores(modelo: Modelo, puntos: list[PuntoSerie]) -> list[float]:
        return [
            abs(acotar(modelo.predecir(p.fecha)) - float(p.valor))
            for p in puntos
            if p.valor is not None
        ]

    candidatos = [
        "Media móvil 28 días",
        "Patrón semanal aprendido",
        "Regresión lineal temporal",
        *[f"Suavizado exponencial {a}" for a in (0.2, 0.4, 0.6, 0.8)],
    ]
    nombre = min(candidatos, key=lambda n: mean(errores(ajustar(n, entrenamiento), seleccion)))
    entreno_evaluacion = [p for p in serie if p.fecha <= corte - timedelta(days=7)]
    residuos = errores(ajustar(nombre, entreno_evaluacion), evaluacion)
    mae = mean(residuos)
    base = mean(errores(ajustar("Media móvil 28 días", entreno_evaluacion), evaluacion))
    mejora = (base - mae) * 100 / base if base > 0 else 0
    evidencia = EvidenciaModelo(
        estado="experimental" if mae > base * 1.05 else "validado_localmente",
        motivo="Evaluación temporal; confirme las decisiones operativas."
        if mae <= base * 1.05
        else "El modelo no supera la referencia en evaluación; revise los datos antes de usarlo.",
        algoritmo=nombre,
        observaciones=len(validos),
        dias_historia=dias,
        dias_seleccion=len(seleccion),
        dias_evaluacion=len(evaluacion),
        mae=round(mae, 4),
        mae_base=round(base, 4),
        mejora_porcentaje=round(mejora, 2),
        entrenado_hasta=corte,
        evaluacion_desde=evaluacion[0].fecha,
        evaluacion_hasta=evaluacion[-1].fecha,
    )
    modelo = ajustar(nombre, serie)
    radio = sorted(residuos)[min(len(residuos) - 1, math.ceil(0.9 * len(residuos)) - 1)]
    salida = []
    for i in range(1, horizonte + 1):
        fecha = corte + timedelta(days=i)
        valor = acotar(modelo.predecir(fecha))
        # Ampliación explícita por horizonte; no se presenta como probabilidad.
        ancho = radio * math.sqrt(1 + i / 7)
        salida.append(
            PuntoPronostico(
                fecha=fecha,
                valor=round(valor, 2),
                inferior=round(acotar(valor - ancho), 2),
                superior=round(acotar(valor + ancho), 2),
            )
        )
    return evidencia, salida
