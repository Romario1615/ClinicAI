"""Aritmetica pura para medir ocupacion de agenda en minutos."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from app.modulos.agenda.disponibilidad import Intervalo


def unir_intervalos(intervalos: Iterable[Intervalo]) -> list[Intervalo]:
    """Devuelve la union ordenada; una persona no aporta capacidad doble."""
    ordenados = sorted(intervalos, key=lambda intervalo: intervalo.inicio)
    if not ordenados:
        return []

    unidos = [ordenados[0]]
    for actual in ordenados[1:]:
        anterior = unidos[-1]
        if actual.inicio <= anterior.fin:
            if actual.fin > anterior.fin:
                unidos[-1] = Intervalo(anterior.inicio, actual.fin)
        else:
            unidos.append(actual)
    return unidos


def resumir_intervalos_ocupacion(
    disponibles: Iterable[Intervalo], reservas: Iterable[Intervalo]
) -> tuple[int, int, float | None]:
    """Devuelve minutos de capacidad, minutos reservados y ocupacion porcentual.

    Las reservas se recortan a horario disponible. Una cita fuera de horario
    no puede crear una ocupacion superior al 100 % ni capacidad negativa.
    """
    franjas = unir_intervalos(disponibles)
    citas = unir_intervalos(reservas)
    capacidad = sum(_minutos(franja.inicio, franja.fin) for franja in franjas)

    ocupados: list[Intervalo] = []
    indice_cita = 0
    for franja in franjas:
        while indice_cita < len(citas) and citas[indice_cita].fin <= franja.inicio:
            indice_cita += 1
        indice = indice_cita
        while indice < len(citas) and citas[indice].inicio < franja.fin:
            cita = citas[indice]
            inicio = max(franja.inicio, cita.inicio)
            fin = min(franja.fin, cita.fin)
            if fin > inicio:
                ocupados.append(Intervalo(inicio, fin))
            indice += 1

    minutos_ocupados = sum(
        _minutos(franja.inicio, franja.fin) for franja in unir_intervalos(ocupados)
    )
    porcentaje = round(minutos_ocupados * 100 / capacidad, 1) if capacidad else None
    return capacidad, minutos_ocupados, porcentaje


def _minutos(inicio: datetime, fin: datetime) -> int:
    return int((fin - inicio).total_seconds() // 60)
