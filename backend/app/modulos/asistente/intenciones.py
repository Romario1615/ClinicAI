"""Qué pide el personal al asistente interno.

Reglas, no un modelo: la intención decide qué datos se tocan, y eso tiene que
ser predecible y auditable. Un modelo de lenguaje puede redactar la respuesta
a partir de lo que ya se recuperó, pero nunca elegir a qué datos acceder.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum


class Intencion(StrEnum):
    AYUDA = "AYUDA"
    AGENDA = "AGENDA"
    SIGUIENTE = "SIGUIENTE"
    RESUMEN = "RESUMEN"
    PROLONGACIONES = "PROLONGACIONES"
    BORRADOR_CONOCIMIENTO = "BORRADOR_CONOCIMIENTO"
    BORRADOR_PROMOCION = "BORRADOR_PROMOCION"
    DECISION_CLINICA = "DECISION_CLINICA"
    PREGUNTA = "PREGUNTA"


@dataclass(frozen=True, slots=True)
class Interpretacion:
    intencion: Intencion
    contenido: str = ""


def normalizar(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto.lower())
    return " ".join("".join(c for c in descompuesto if not unicodedata.combining(c)).split())


_DECISION = re.compile(
    r"\b(que (le )?(receto|recetar|recetarle|indico|doy|darle)|cuanto (le )?(doy|receto)"
    r"|diagnostic\w*|deberia (tomar|suspender)|suspendo (el|la)|cambio (la )?dosis)\b"
)
_CONOCIMIENTO = re.compile(
    r"^(agrega|agregar|anade|anadir|anota|guarda|registra|sube)\b.*"
    r"\b(base de conocimiento|conocimiento|preguntas? frecuentes?|faq)\b"
)
_PROMOCION = re.compile(r"^(crea|crear|nueva|arma|haz|prepara|redacta)\b.*\b(promo\w*|campana)\b")


def _despues_de_dos_puntos(original: str) -> str:
    if ":" in original:
        return original.split(":", 1)[1].strip()
    return ""


# En orden: la primera regla que coincide decide. Las de borrador van antes
# que las de lectura («agrega al conocimiento la historia de…» es un borrador).
_REGLAS: tuple[tuple[re.Pattern[str], Intencion], ...] = (
    (_DECISION, Intencion.DECISION_CLINICA),
    (re.compile(r"\b(prolongacion\w*|mas tiempo|prorroga\w*)\b"), Intencion.PROLONGACIONES),
    (
        re.compile(r"\b(quien sigue|siguiente paciente|proximo paciente|quien esta esperando)\b"),
        Intencion.SIGUIENTE,
    ),
    (
        re.compile(
            r"\b(mi agenda|agenda de hoy|mis citas|citas de hoy|pacientes de hoy|a quien tengo)\b"
        ),
        Intencion.AGENDA,
    ),
    (
        re.compile(
            r"\b(resumen|historia|historial|antecedentes|alergias?|medicacion|medicamentos?)\b"
        ),
        Intencion.RESUMEN,
    ),
)


def interpretar(texto: str) -> Interpretacion:
    limpio = normalizar(texto)
    if not limpio or re.search(r"\b(ayuda|que puedes hacer|que sabes hacer)\b", limpio):
        return Interpretacion(Intencion.AYUDA)
    if limpio.startswith("conocimiento:") or _CONOCIMIENTO.search(limpio):
        return Interpretacion(Intencion.BORRADOR_CONOCIMIENTO, _despues_de_dos_puntos(texto))
    if limpio.startswith("promocion:") or _PROMOCION.search(limpio):
        return Interpretacion(Intencion.BORRADOR_PROMOCION, _despues_de_dos_puntos(texto))
    intencion = next((i for patron, i in _REGLAS if patron.search(limpio)), Intencion.PREGUNTA)
    return Interpretacion(intencion, texto.strip() if intencion is Intencion.PREGUNTA else "")


__all__ = ["Intencion", "Interpretacion", "interpretar", "normalizar"]
