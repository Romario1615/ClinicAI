"""Vocabulario del odontograma: piezas FDI, caras y hallazgos.

Es un catalogo **cerrado** y vive en codigo, no en texto libre. Un hallazgo
escrito a mano («carie», «caries ocl.», «C») hace imposible contar cuantas
piezas cariadas hay o pintar el odontograma de forma consistente.

Notacion FDI (ISO 3950)
-----------------------
Dos digitos: cuadrante y posicion. Permanentes 11-18, 21-28, 31-38, 41-48;
temporales 51-55, 61-65, 71-75, 81-85.

Que es de la pieza y que es de la cara
--------------------------------------
Una caries o una obturacion estan en una **cara**; una corona, una
endodoncia o una ausencia afectan a la **pieza entera**. Separarlos impide
registrar «ausente en la cara mesial», que no significa nada.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

PIEZAS_PERMANENTES: Final[frozenset[int]] = frozenset(
    cuadrante * 10 + posicion for cuadrante in (1, 2, 3, 4) for posicion in range(1, 9)
)
PIEZAS_TEMPORALES: Final[frozenset[int]] = frozenset(
    cuadrante * 10 + posicion for cuadrante in (5, 6, 7, 8) for posicion in range(1, 6)
)
PIEZAS_VALIDAS: Final[frozenset[int]] = PIEZAS_PERMANENTES | PIEZAS_TEMPORALES


class Cara(StrEnum):
    """Caras de una pieza. `O` es oclusal en posteriores e incisal en anteriores."""

    OCLUSAL = "O"
    MESIAL = "M"
    DISTAL = "D"
    VESTIBULAR = "V"
    LINGUAL = "L"


class HallazgoCara(StrEnum):
    CARIES = "CARIES"
    OBTURACION_RESINA = "OBTURACION_RESINA"
    OBTURACION_AMALGAMA = "OBTURACION_AMALGAMA"
    SELLANTE = "SELLANTE"
    FRACTURA = "FRACTURA"


class HallazgoPieza(StrEnum):
    AUSENTE = "AUSENTE"
    A_EXTRAER = "A_EXTRAER"
    CORONA = "CORONA"
    ENDODONCIA = "ENDODONCIA"
    IMPLANTE = "IMPLANTE"
    PROTESIS_FIJA = "PROTESIS_FIJA"
    RESTO_RADICULAR = "RESTO_RADICULAR"


class Denticion(StrEnum):
    PERMANENTE = "PERMANENTE"
    TEMPORAL = "TEMPORAL"
    MIXTA = "MIXTA"


def es_pieza_valida(pieza: int) -> bool:
    return pieza in PIEZAS_VALIDAS


def validar_caras(caras: str) -> str:
    """Normaliza un conjunto de caras («om» -> «MO»). Lanza `ValueError` si no vale."""
    limpias = caras.strip().upper()
    validas = {cara.value for cara in Cara}
    if not limpias or any(letra not in validas for letra in limpias):
        raise ValueError(f"Caras no validas: {caras!r}. Use O, M, D, V, L.")
    if len(set(limpias)) != len(limpias):
        raise ValueError(f"Caras repetidas: {caras!r}.")
    orden = [cara.value for cara in Cara]
    return "".join(sorted(limpias, key=orden.index))


__all__ = [
    "PIEZAS_PERMANENTES",
    "PIEZAS_TEMPORALES",
    "PIEZAS_VALIDAS",
    "Cara",
    "Denticion",
    "HallazgoCara",
    "HallazgoPieza",
    "es_pieza_valida",
    "validar_caras",
]
