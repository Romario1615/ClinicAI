"""Lectura del cuerpo del webhook de WhatsApp Cloud API.

Se hace a mano y no con Pydantic estricto por una razon concreta: Meta anade
campos y tipos de mensaje sin previo aviso.  Un esquema que rechace lo
desconocido haria que el webhook devolviera error, y Meta responde a los
errores repitiendo la entrega y, si persisten, **deshabilitando la
suscripcion**.  Perder la suscripcion significa dejar de recibir las
respuestas de todos los pacientes.

Asi que la regla aqui es: extraer lo que se entiende, ignorar el resto sin
romper, y no dar por buena ninguna forma que no se haya comprobado.

Los nombres de campo son los de la API externa y no se traducen (CLAUDE.md,
seccion 2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# Tipos de mensaje que el sistema procesa. Un audio, una imagen o una
# ubicacion se registran y van a una persona: este modulo no transcribe audio
# ni interpreta imagenes, y fingir que si lo hace produciria decisiones sobre
# contenido que nadie leyo.
TIPOS_CON_TEXTO: frozenset[str] = frozenset({"text", "button", "interactive"})


@dataclass(frozen=True, slots=True)
class MensajeEntranteCrudo:
    external_id: str
    telefono: str
    tipo: str
    texto: str | None
    recibido_en: datetime
    crudo: dict[str, Any]


@dataclass(frozen=True, slots=True)
class EstadoEntregaCrudo:
    external_id: str
    estado: str
    detalle: str | None
    ocurrido_en: datetime


@dataclass(frozen=True, slots=True)
class CargaWebhook:
    mensajes: list[MensajeEntranteCrudo] = field(default_factory=list)
    estados: list[EstadoEntregaCrudo] = field(default_factory=list)
    # Identificador del numero de la clinica que recibio el mensaje. Con
    # varias clinicas en una instancia, es lo que decide a cual pertenece.
    id_numero_telefono: str | None = None

    @property
    def vacia(self) -> bool:
        return not self.mensajes and not self.estados


def interpretar(cuerpo: Any) -> CargaWebhook:
    """Extrae mensajes y estados de entrega de un cuerpo de webhook.

    Nunca lanza por una forma inesperada: devuelve lo que pudo leer.
    """
    if not isinstance(cuerpo, dict):
        return CargaWebhook()

    mensajes: list[MensajeEntranteCrudo] = []
    estados: list[EstadoEntregaCrudo] = []
    id_numero: str | None = None

    for entrada in _lista(cuerpo.get("entry")):
        for cambio in _lista(entrada.get("changes")):
            valor = cambio.get("value")
            if not isinstance(valor, dict):
                continue
            metadatos = valor.get("metadata")
            if isinstance(metadatos, dict):
                candidato = metadatos.get("phone_number_id")
                if isinstance(candidato, str):
                    id_numero = candidato

            for bruto in _lista(valor.get("messages")):
                mensaje = _mensaje(bruto)
                if mensaje is not None:
                    mensajes.append(mensaje)

            for bruto in _lista(valor.get("statuses")):
                estado = _estado(bruto)
                if estado is not None:
                    estados.append(estado)

    return CargaWebhook(mensajes=mensajes, estados=estados, id_numero_telefono=id_numero)


def _lista(valor: Any) -> list[dict[str, Any]]:
    """Elementos de diccionario de un campo que deberia ser una lista.

    Devuelve vacio ante cualquier otra forma. Meta puede enviar `null` donde
    la documentacion dice lista, y un `TypeError` aqui haria que el webhook
    devolviera error y Meta reintentara -- o deshabilitara la suscripcion.
    """
    if not isinstance(valor, list):
        return []
    return [elemento for elemento in valor if isinstance(elemento, dict)]


def _mensaje(bruto: dict[str, Any]) -> MensajeEntranteCrudo | None:
    external_id = bruto.get("id")
    telefono = bruto.get("from")
    if not isinstance(external_id, str) or not isinstance(telefono, str):
        # Sin identificador no hay deduplicacion posible, y procesar un
        # mensaje que no se puede deduplicar es peor que descartarlo.
        return None

    tipo = bruto.get("type")
    tipo = tipo if isinstance(tipo, str) else "desconocido"
    return MensajeEntranteCrudo(
        external_id=external_id,
        telefono=telefono,
        tipo=tipo,
        texto=_texto(bruto, tipo),
        recibido_en=_marca_tiempo(bruto.get("timestamp")),
        crudo=bruto,
    )


def _texto(bruto: dict[str, Any], tipo: str) -> str | None:
    """Texto legible del mensaje, sea cual sea su forma.

    Un boton y una lista interactiva no traen `text.body`: el titulo del boton
    o el identificador de la opcion es lo que el paciente «dijo».  Tratarlos
    como mensajes sin texto haria que un «CONFIRMAR» pulsado en un boton se
    derivara a una persona.
    """
    extractores = {
        "text": _texto_simple,
        "button": _texto_boton,
        "interactive": _texto_interactivo,
    }
    extractor = extractores.get(tipo)
    return extractor(bruto) if extractor is not None else None


def _texto_simple(bruto: dict[str, Any]) -> str | None:
    cuerpo = bruto.get("text")
    if not isinstance(cuerpo, dict):
        return None
    return _cadena(cuerpo, "body")


def _texto_boton(bruto: dict[str, Any]) -> str | None:
    cuerpo = bruto.get("button")
    if not isinstance(cuerpo, dict):
        return None
    return _cadena(cuerpo, "payload", "text")


def _texto_interactivo(bruto: dict[str, Any]) -> str | None:
    cuerpo = bruto.get("interactive")
    if not isinstance(cuerpo, dict):
        return None
    for clave in ("button_reply", "list_reply"):
        respuesta = cuerpo.get(clave)
        if isinstance(respuesta, dict):
            valor = _cadena(respuesta, "id", "title")
            if valor is not None:
                return valor
    return None


def _cadena(origen: dict[str, Any], *claves: str) -> str | None:
    """Primera de esas claves que contenga una cadena."""
    for clave in claves:
        valor = origen.get(clave)
        if isinstance(valor, str):
            return valor
    return None


def _estado(bruto: dict[str, Any]) -> EstadoEntregaCrudo | None:
    external_id = bruto.get("id")
    estado = bruto.get("status")
    if not isinstance(external_id, str) or not isinstance(estado, str):
        return None

    detalle: str | None = None
    errores = bruto.get("errors")
    if isinstance(errores, list) and errores:
        primero = errores[0]
        if isinstance(primero, dict):
            partes = [
                str(primero.get(clave))
                for clave in ("code", "title", "message")
                if primero.get(clave) is not None
            ]
            detalle = " | ".join(partes) or None

    return EstadoEntregaCrudo(
        external_id=external_id,
        estado=estado,
        detalle=detalle,
        ocurrido_en=_marca_tiempo(bruto.get("timestamp")),
    )


def _marca_tiempo(valor: Any) -> datetime:
    """Convierte la marca de tiempo de Meta (epoch en segundos, como cadena).

    Ante un valor ilegible devuelve el epoch en lugar de lanzar: la hora exacta
    de recepcion es informativa, y perder el mensaje entero por una marca mal
    formada seria desproporcionado.  Una fecha de 1970 en la base es
    suficientemente visible como sintoma.
    """
    try:
        return datetime.fromtimestamp(int(valor), tz=UTC)
    except (TypeError, ValueError, OSError, OverflowError):
        return datetime.fromtimestamp(0, tz=UTC)


__all__ = [
    "TIPOS_CON_TEXTO",
    "CargaWebhook",
    "EstadoEntregaCrudo",
    "MensajeEntranteCrudo",
    "interpretar",
]
