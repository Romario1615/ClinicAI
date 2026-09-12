"""Reconocimiento de intencion en un mensaje entrante.

Por que coincidencia exacta y no un modelo
------------------------------------------
Aqui no hay ningun modelo de lenguaje, a proposito.  La intencion decide si se
cancela una cita o si se da de baja a un paciente de las notificaciones, y una
interpretacion probabilistica de «no creo que pueda ir» no es base suficiente
para cancelar la cita de nadie.

La regla es deliberadamente rigida: se normaliza el texto y se compara con un
catalogo cerrado de frases.  **Todo lo demas va a una persona.**  El coste es
que el personal atiende mensajes que una maquina podria haber resuelto; el
beneficio es que la maquina nunca resuelve mal uno que no entendio.

Lo que esta explicitamente fuera
--------------------------------
Nada de lo que se reconoce aqui toca contenido clinico.  No hay intencion de
«cambiar mi dosis», «me sienta mal el medicamento» ni nada parecido: eso es
`DESCONOCIDA` y se deriva (CLAUDE.md, regla 5).
"""

from __future__ import annotations

import re
import unicodedata

from app.modulos.conversaciones.modelos import IntencionEntrante

# El catalogo. Una frase entera, normalizada, tiene que coincidir con una de
# estas para que se reconozca la intencion.
FRASES: dict[IntencionEntrante, frozenset[str]] = {
    IntencionEntrante.CONFIRMAR: frozenset(
        {"confirmar", "confirmo", "confirmado", "si confirmo", "asistire"}
    ),
    IntencionEntrante.CANCELAR: frozenset(
        {"cancelar", "cancelo", "cancelar cita", "no puedo asistir", "no asistire"}
    ),
    IntencionEntrante.ACEPTAR_OFERTA: frozenset(
        {"si", "si acepto", "acepto", "lo tomo", "quiero ese turno"}
    ),
    IntencionEntrante.REGISTRAR_TOMA: frozenset({"tomada", "tomado", "ya tome", "listo"}),
    # Retirada del consentimiento. Se aceptan las formas que las guias de
    # WhatsApp consideran estandar, incluida la inglesa: el paciente puede
    # haberla aprendido de otra aplicacion, y no reconocerla equivaldria a
    # ignorar una retirada de consentimiento.
    IntencionEntrante.BAJA: frozenset(
        {"baja", "stop", "no molestar", "dar de baja", "cancelar suscripcion", "unsubscribe"}
    ),
    IntencionEntrante.ALTA: frozenset({"alta", "start", "si acepto recibir mensajes"}),
    IntencionEntrante.AYUDA: frozenset({"ayuda", "help", "menu", "opciones"}),
}

# Indice inverso, construido una vez. Dos intenciones no pueden compartir
# frase: seria ambiguo y el orden de iteracion decidiria, que es la peor forma
# de decidir.
_INDICE: dict[str, IntencionEntrante] = {}
for _intencion, _frases in FRASES.items():
    for _frase in _frases:
        if _frase in _INDICE:
            raise RuntimeError(
                f"La frase «{_frase}» esta asignada a {_INDICE[_frase].value} y a "
                f"{_intencion.value}. Una frase pertenece a una sola intencion."
            )
        _INDICE[_frase] = _intencion

_PUNTUACION = re.compile(r"[^\w\s]", flags=re.UNICODE)
_ESPACIOS = re.compile(r"\s+")

# Un mensaje mas largo que esto no es una palabra clave. El limite evita
# gastar trabajo normalizando un mensaje largo que de todos modos ira a una
# persona.
LONGITUD_MAXIMA_PALABRA_CLAVE = 40


def normalizar(texto: str) -> str:
    """Minusculas, sin tildes, sin puntuacion y con espacios colapsados.

    Se quitan las tildes porque el paciente escribe «asistire» tan a menudo
    como «asistiré», y distinguirlos convertiria un acento en la diferencia
    entre confirmar una cita y no confirmarla.
    """
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    sin_puntuacion = _PUNTUACION.sub(" ", sin_tildes.lower())
    return _ESPACIOS.sub(" ", sin_puntuacion).strip()


def reconocer(texto: str | None) -> IntencionEntrante:
    """Intencion del mensaje, o `DESCONOCIDA`.

    `DESCONOCIDA` no es un fallo: es el resultado correcto para casi todo lo
    que escribe una persona, y lleva el mensaje a alguien que puede leerlo.
    """
    if not texto:
        return IntencionEntrante.DESCONOCIDA
    if len(texto) > LONGITUD_MAXIMA_PALABRA_CLAVE:
        return IntencionEntrante.DESCONOCIDA
    return _INDICE.get(normalizar(texto), IntencionEntrante.DESCONOCIDA)


__all__ = [
    "FRASES",
    "LONGITUD_MAXIMA_PALABRA_CLAVE",
    "IntencionEntrante",
    "normalizar",
    "reconocer",
]
