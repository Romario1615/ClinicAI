"""Texto que el agente envia por WhatsApp a partir del resultado de una herramienta.

El mensaje de una herramienta es un titular («Hay 5 horarios disponibles»);
el detalle viaja en `datos`. En la pantalla el detalle se dibuja aparte, pero
por WhatsApp solo llega texto: sin los horarios numerados el paciente no puede
responder «1».

Solo se escribe lo que la herramienta ya devuelve, y las herramientas no
devuelven servicio, especialidad, profesional ni notas: el nombre de un
servicio puede revelar la condicion (CLAUDE.md, regla 10). Aqui solo hay
fechas, horas, estados e importes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.ia.herramientas.contrato import ResultadoHerramienta

_DIAS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
_ESTADOS_CITA = {
    "CONFIRMED": "confirmada",
    "HELD": "apartada, falta confirmar",
    "PENDING": "pendiente",
    "RESCHEDULED": "reprogramada",
}


def _zona(nombre: str | None, respaldo: str) -> ZoneInfo:
    for candidata in (nombre, respaldo):
        if candidata:
            try:
                return ZoneInfo(candidata)
            except ZoneInfoNotFoundError:
                continue
    return ZoneInfo("UTC")


def _fecha(valor: Any, zona: ZoneInfo, *, con_hora: bool = True) -> str:
    try:
        instante = datetime.fromisoformat(str(valor)).astimezone(zona)
    except ValueError:
        return ""
    dia = f"{_DIAS[instante.weekday()]} {instante:%d/%m}"
    return f"{dia} {instante:%H:%M}" if con_hora else dia


def redactar(resultado: ResultadoHerramienta, zona_clinica: str) -> str:
    """El titular de la herramienta mas el detalle legible por WhatsApp."""
    datos = resultado.datos or {}
    zona = _zona(datos.get("zona_horaria"), zona_clinica)
    lineas = [resultado.mensaje] if resultado.mensaje else []

    turnos = datos.get("turnos")
    if isinstance(turnos, list) and turnos:
        lineas += [f"{i}) {_fecha(t.get('inicio'), zona)}" for i, t in enumerate(turnos, 1)]
        lineas.append("Responda con el número del horario que prefiera.")

    citas = datos.get("citas")
    if isinstance(citas, list) and citas:
        lineas += [
            f"• {_fecha(c.get('inicio'), zona)} — "
            f"{_ESTADOS_CITA.get(str(c.get('estado')), str(c.get('estado', '')).lower())}"
            for c in citas
        ]

    pagos = datos.get("pagos")
    if isinstance(pagos, list) and pagos:
        lineas += [
            f"• {p.get('importe')} {p.get('moneda', '')} — {str(p.get('estado', '')).lower()}"
            f" — cita del {_fecha(p.get('cita'), zona, con_hora=False)}"
            for p in pagos
        ]

    # `hold_slot`: el horario apartado y como dejarlo en firme.
    if datos.get("cita_id") and datos.get("inicio") and "turnos" not in datos:
        lineas.append(f"Horario: {_fecha(datos['inicio'], zona)}.")
        if datos.get("expira_en"):
            lineas.append(
                f"Queda apartado hasta las {_fecha(datos['expira_en'], zona)[-5:]}. "
                "Responda «confirmar» para dejarlo en firme."
            )
    return "\n".join(linea for linea in lineas if linea)
