"""Division de un documento en fragmentos recuperables.

Por que el tamano y el solape importan
--------------------------------------
Un fragmento demasiado grande diluye el parecido: el vector promedia varios
temas y deja de parecerse a una pregunta concreta. Uno demasiado pequeno
pierde el contexto y recupera frases sueltas que no responden nada.

El solape existe por un motivo concreto: **una instruccion puede quedar
partida por la mitad**. «No comer nada desde las 22:00. / Puede beber agua» en
dos fragmentos sin solape produce un fragmento que dice que no coma nada y
otro que dice que beba agua, y recuperar solo el primero da una respuesta
incompleta sobre una preparacion de examen.

Donde se corta
--------------
Se prefiere cortar en limites naturales, en este orden: parrafo, luego frase,
y solo si no hay mas remedio, a mitad de frase. Cortar por numero de
caracteres sin mirar el texto parte palabras y produce fragmentos que empiezan
a media frase, que es tanto peor para la busqueda textual como para lo que lee
una persona al revisar por que el agente respondio algo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise

# Se corta por estos separadores, de mayor a menor preferencia.
_PARRAFO = re.compile(r"\n\s*\n")
_FRASE = re.compile(r"(?<=[.!?:;])\s+")
_ESPACIOS = re.compile(r"[ \t]+")

# Un fragmento mas corto que esto casi nunca aporta contexto: suele ser un
# titulo suelto o una linea de tabla. Se fusiona con el siguiente.
MINIMO_UTIL = 80

# Con un solo fragmento no hay nada con lo que solapar.
_MINIMO_PARA_SOLAPAR = 2


@dataclass(frozen=True, slots=True)
class Fragmento:
    indice: int
    contenido: str

    @property
    def tokens_aproximados(self) -> int:
        """Estimacion barata del tamano en tokens.

        No se usa un tokenizador real: cargarlo costaria mas que el beneficio,
        y este numero solo sirve para dar una idea del tamano en el panel y
        para acotar el contexto. La regla de ~4 caracteres por token es
        razonable en espanol.
        """
        return max(len(self.contenido) // 4, 1)


def normalizar_texto(texto: str) -> str:
    """Limpia el texto antes de fragmentar.

    Los PDF producen saltos de linea en medio de las frases y espacios
    multiples. Dejarlos hace que el corte por frase falle y que la busqueda
    textual indexe palabras partidas.
    """
    # Se conservan los saltos dobles: marcan parrafo, que es el mejor punto de
    # corte que hay.
    sin_retornos = texto.replace("\r\n", "\n").replace("\r", "\n")
    # Un salto simple dentro de un parrafo casi siempre es un artefacto del
    # PDF, no una separacion real.
    sin_saltos_sueltos = re.sub(r"(?<!\n)\n(?!\n)", " ", sin_retornos)
    return _ESPACIOS.sub(" ", sin_saltos_sueltos).strip()


def fragmentar(texto: str, *, tamano: int = 900, solape: int = 150) -> list[Fragmento]:
    """Divide el texto en fragmentos con solape.

    `tamano` y `solape` se miden en caracteres, no en tokens: es lo que se
    puede contar sin cargar un tokenizador, y la proporcion entre ambos es lo
    que importa.
    """
    if tamano <= 0:
        raise ValueError("El tamano del fragmento debe ser positivo.")
    if solape < 0 or solape >= tamano:
        # Un solape igual o mayor que el tamano no avanza: el bucle no
        # terminaria. Se rechaza en lugar de corregirlo en silencio.
        raise ValueError("El solape debe ser menor que el tamano y no negativo.")

    limpio = normalizar_texto(texto)
    if not limpio:
        return []

    piezas = _dividir(limpio, tamano)
    piezas = _fusionar_cortos(piezas)
    con_solape = _aplicar_solape(piezas, solape)
    return [Fragmento(indice=i, contenido=p) for i, p in enumerate(con_solape)]


def _dividir(texto: str, tamano: int) -> list[str]:
    """Corta por parrafo, luego por frase, y en ultimo caso por longitud."""
    piezas: list[str] = []
    for bruto in _PARRAFO.split(texto):
        parrafo = bruto.strip()
        if not parrafo:
            continue
        if len(parrafo) <= tamano:
            piezas.append(parrafo)
            continue
        piezas.extend(_dividir_parrafo(parrafo, tamano))
    return piezas


def _dividir_parrafo(parrafo: str, tamano: int) -> list[str]:
    """Divide un parrafo largo acumulando frases hasta llenar el tamano."""
    piezas: list[str] = []
    actual = ""
    for frase in _FRASE.split(parrafo):
        if not frase:
            continue
        if len(actual) + len(frase) + 1 <= tamano:
            actual = f"{actual} {frase}".strip()
            continue
        if actual:
            piezas.append(actual)
        if len(frase) <= tamano:
            actual = frase
        else:
            # Una frase mas larga que el tamano. Ocurre con tablas y listas
            # pegadas de un PDF. Aqui si hay que cortar a lo bruto.
            piezas.extend(frase[i : i + tamano] for i in range(0, len(frase), tamano))
            actual = piezas.pop() if piezas else ""
    if actual:
        piezas.append(actual)
    return piezas


def _fusionar_cortos(piezas: list[str]) -> list[str]:
    """Une los fragmentos demasiado cortos con el siguiente.

    Un titulo suelto («## Preparacion») recuperado por si solo no responde
    nada; unido al parrafo que encabeza, si.
    """
    if not piezas:
        return []
    resultado: list[str] = []
    pendiente = ""
    for pieza in piezas:
        candidato = f"{pendiente} {pieza}".strip() if pendiente else pieza
        if len(candidato) < MINIMO_UTIL:
            pendiente = candidato
            continue
        resultado.append(candidato)
        pendiente = ""
    if pendiente:
        # El ultimo trozo corto se pega al anterior en lugar de quedar suelto.
        if resultado:
            resultado[-1] = f"{resultado[-1]} {pendiente}".strip()
        else:
            resultado.append(pendiente)
    return resultado


def _aplicar_solape(piezas: list[str], solape: int) -> list[str]:
    """Antepone a cada fragmento el final del anterior.

    Es lo que evita que una instruccion partida por la mitad quede
    irrecuperable: el fragmento que empieza con «Puede beber agua» lleva
    delante el «No comer nada desde las 22:00» que le daba sentido.
    """
    if solape == 0 or len(piezas) < _MINIMO_PARA_SOLAPAR:
        return piezas

    resultado = [piezas[0]]
    for anterior, pieza in pairwise(piezas):
        cola = anterior[-solape:].lstrip()
        # Se busca un limite de palabra para no empezar el solape a mitad de
        # una: un fragmento que empieza por «…iones previas» confunde tanto a
        # la busqueda textual como a quien lo lee.
        espacio = cola.find(" ")
        if espacio > 0:
            cola = cola[espacio + 1 :]
        resultado.append(f"{cola} {pieza}".strip() if cola else pieza)
    return resultado


__all__ = ["MINIMO_UTIL", "Fragmento", "fragmentar", "normalizar_texto"]
