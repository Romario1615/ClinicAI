"""Decisiones tipadas sobre el mensaje del paciente, antes del LLM.

Que resuelve
------------
Un LLM genera texto; muchas decisiones del canal no necesitan texto, sino una
respuesta cerrada: ¿que quiere esta persona?, ¿pregunta algo clinico?, ¿es
urgente? Para eso se usa un modelo de decision (Jev, de TypeSafe AI) que
devuelve una opcion de un conjunto **definido aqui** con su probabilidad. No
puede responder fuera del esquema: no hay texto que sanear ni herramienta que
inventar.

Que NO hace
-----------
* **No ejecuta nada.** Decide; el codigo de servicios ejecuta, con permisos,
  validacion y auditoria (CLAUDE.md, regla 4). Jev nunca ve la base de datos.
* **No sustituye a los limites por reglas** (`herramientas/limites.py`). Se
  evaluan antes y siguen siendo la primera barrera; esto es la segunda.
* **No relaja nada.** La probabilidad clinica solo puede *anadir* una
  derivacion a humano, nunca quitarla.

Datos que salen del sistema
---------------------------
Con `PROVEEDOR_DECISIONES=jev` el **texto del mensaje** se envia a TypeSafe
AI, igual que con `PROVEEDOR_LLM=anthropic` se envia a Anthropic. No se envian
identificadores, nombre ni telefono del paciente. Antes de activarlo con datos
reales hace falta el acuerdo de encargo de tratamiento con el proveedor
(docs/known-limitations.md).

Sin credencial
--------------
`ClasificadorReglas` es el adaptador sandbox: palabras clave, sin red. Se usa
por defecto y como respaldo cuando Jev falla o tarda: el chat no se cae
porque el clasificador externo no responda.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

import httpx
import structlog

from app.ia.saneamiento import normalizar
from app.nucleo.configuracion import Configuracion

logger = structlog.get_logger(__name__)

URL_JEV = "https://api.typesafe.ai/v1/systemone"


class Intencion(StrEnum):
    BUSCAR_HORARIOS = "buscar_horarios"
    CONSULTAR_CITAS = "consultar_citas"
    CANCELAR = "cancelar"
    REPROGRAMAR = "reprogramar"
    INFORMACION = "informacion"
    SEGUIMIENTO_TRATAMIENTO = "seguimiento_tratamiento"
    BAJA_PROMOCIONES = "baja_promociones"
    HABLAR_CON_PERSONA = "hablar_con_persona"
    OTRO = "otro"


# Criterios en lenguaje natural para Jev. Las claves son el esquema cerrado.
CRITERIOS_INTENCION: dict[Intencion, str] = {
    Intencion.BUSCAR_HORARIOS: "Quiere reservar o ver horarios disponibles para una cita",
    Intencion.CONSULTAR_CITAS: "Pregunta por sus citas ya agendadas",
    Intencion.CANCELAR: "Quiere cancelar una cita",
    Intencion.REPROGRAMAR: "Quiere cambiar la fecha u hora de una cita",
    Intencion.INFORMACION: "Pregunta por horarios de atencion, precios, direccion o preparacion",
    Intencion.SEGUIMIENTO_TRATAMIENTO: (
        "Pregunta en que va su tratamiento o cual es la siguiente sesion o fase"
    ),
    Intencion.BAJA_PROMOCIONES: "Pide dejar de recibir promociones o publicidad",
    Intencion.HABLAR_CON_PERSONA: "Pide hablar con una persona del personal",
    Intencion.OTRO: "Saludo u otra cosa distinta de las anteriores",
}


@dataclass(frozen=True, slots=True)
class DecisionTipada:
    intencion: Intencion
    confianza: float
    # Probabilidad de que el mensaje pida una valoracion clinica (sintoma,
    # dolor, medicacion, resultado). Solo sirve para derivar.
    pregunta_clinica: float
    urgencia: float
    proveedor: str


class ClasificadorIntencion(Protocol):
    @property
    def nombre(self) -> str: ...

    async def clasificar(self, texto: str) -> DecisionTipada: ...


# ---------------------------------------------------------------------------
#  Sandbox por reglas
# ---------------------------------------------------------------------------
_PALABRAS: tuple[tuple[Intencion, tuple[str, ...]], ...] = (
    (Intencion.BAJA_PROMOCIONES, ("baja", "no quiero promociones", "dejar de recibir", "stop")),
    (Intencion.HABLAR_CON_PERSONA, ("humano", "persona", "asesor", "recepcion")),
    (Intencion.CANCELAR, ("cancelar", "anular")),
    (Intencion.REPROGRAMAR, ("reprogramar", "cambiar la cita", "mover la cita", "otro dia")),
    (Intencion.CONSULTAR_CITAS, ("mis citas", "ver citas", "consultar citas", "tengo cita")),
    (
        Intencion.SEGUIMIENTO_TRATAMIENTO,
        ("mi tratamiento", "siguiente fase", "proxima sesion", "como va mi"),
    ),
    (Intencion.BUSCAR_HORARIOS, ("reservar", "agendar", "horario", "disponibilidad", "cita")),
    (Intencion.INFORMACION, ("precio", "cuanto cuesta", "direccion", "donde queda", "atienden")),
)
_CLINICAS = ("duele", "dolor", "sangra", "inflam", "hinchad", "pastilla", "medicamento", "fiebre")
_URGENTES = ("urgente", "emergencia", "no puedo respirar", "accidente")


class ClasificadorReglas:
    """Adaptador sandbox: sin red, determinista, conservador."""

    nombre = "reglas"

    async def clasificar(self, texto: str) -> DecisionTipada:
        limpio = normalizar(texto)
        intencion, confianza = Intencion.OTRO, 0.5
        for candidata, palabras in _PALABRAS:
            if any(palabra in limpio for palabra in palabras):
                intencion, confianza = candidata, 0.9
                break
        clinica = 1.0 if any(palabra in limpio for palabra in _CLINICAS) else 0.0
        urgente = 1.0 if any(palabra in limpio for palabra in _URGENTES) else 0.0
        return DecisionTipada(intencion, confianza, clinica, urgente, self.nombre)


# ---------------------------------------------------------------------------
#  Jev (TypeSafe AI)
# ---------------------------------------------------------------------------
class ClasificadorJev:
    """Cliente del endpoint `systemone` de TypeSafe AI.

    Una sola llamada con tres preguntas: `choice` para la intencion y dos
    `noul` (probabilidad de que una afirmacion sea cierta). Ante cualquier
    fallo responde el respaldo por reglas y se registra el motivo.
    """

    nombre = "jev"

    def __init__(
        self,
        *,
        clave: str,
        modelo: str = "jev-latest",
        url: str = URL_JEV,
        tiempo_limite: float = 3.0,
        cliente: httpx.AsyncClient | None = None,
        respaldo: ClasificadorIntencion | None = None,
    ) -> None:
        if not clave:
            raise ValueError("Jev necesita TYPESAFE_API_KEY.")
        self._clave = clave
        self._modelo = modelo
        self._url = url
        self._cliente = cliente or httpx.AsyncClient(timeout=tiempo_limite)
        self._respaldo = respaldo or ClasificadorReglas()

    def _cuerpo(self, texto: str) -> dict[str, Any]:
        return {
            "model": self._modelo,
            # El texto es dato del paciente; las instrucciones son nuestras y
            # fijas. Jev no ejecuta nada de lo que diga el texto: solo elige
            # entre las opciones de `criteria`.
            "state": texto[:2000],
            "questions": {
                "intencion": {
                    "type": "choice",
                    "instructions": (
                        "Que quiere conseguir el paciente con este mensaje a una clinica"
                    ),
                    "criteria": {i.value: criterio for i, criterio in CRITERIOS_INTENCION.items()},
                },
                "pregunta_clinica": {
                    "type": "noul",
                    "instructions": (
                        "El mensaje describe un sintoma, dolor, medicacion o pide una "
                        "valoracion clinica"
                    ),
                },
                "urgencia": {
                    "type": "noul",
                    "instructions": "El mensaje describe una situacion de salud urgente",
                },
            },
        }

    @staticmethod
    def _interpretar(cuerpo: dict[str, Any]) -> DecisionTipada:
        respuestas = cuerpo["answers"]
        eleccion = respuestas["intencion"]
        intencion = Intencion(eleccion["choice"])
        confianza = float(eleccion.get("confidence", 0.0))
        clinica = float(respuestas["pregunta_clinica"]["noul"])
        urgencia = float(respuestas["urgencia"]["noul"])
        for valor in (confianza, clinica, urgencia):
            if not 0.0 <= valor <= 1.0:
                raise ValueError("Probabilidad fuera de rango.")
        return DecisionTipada(intencion, confianza, clinica, urgencia, "jev")

    async def clasificar(self, texto: str) -> DecisionTipada:
        try:
            respuesta = await self._cliente.post(
                self._url,
                json=self._cuerpo(texto),
                headers={"Authorization": f"Bearer {self._clave}"},
            )
            respuesta.raise_for_status()
            return self._interpretar(respuesta.json())
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            # El motivo se registra sin el texto del paciente.
            logger.warning("decisiones.jev_fallo", error=type(exc).__name__)
            return await self._respaldo.clasificar(texto)


def construir_clasificador(configuracion: Configuracion) -> ClasificadorIntencion:
    if configuracion.proveedor_decisiones == "jev":
        logger.info("decisiones.proveedor", proveedor="jev", modelo=configuracion.typesafe_modelo)
        return ClasificadorJev(
            clave=configuracion.typesafe_api_key.get_secret_value(),
            modelo=configuracion.typesafe_modelo,
            tiempo_limite=configuracion.typesafe_timeout_segundos,
        )
    logger.info("decisiones.proveedor", proveedor="reglas")
    return ClasificadorReglas()


__all__ = [
    "CRITERIOS_INTENCION",
    "ClasificadorIntencion",
    "ClasificadorJev",
    "ClasificadorReglas",
    "DecisionTipada",
    "Intencion",
    "construir_clasificador",
]
