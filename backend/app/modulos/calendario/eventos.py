"""Construccion del evento que se publica en el calendario externo.

La regla que gobierna este modulo
---------------------------------
**El evento externo no contiene datos clinicos ni identifica al paciente**
(RF-I09, y CLAUDE.md regla 10 por extension).

El motivo es que el calendario de Google es un tercero. Lo que se escribe ahi
sale del sistema: deja de estar bajo su control de acceso, su auditoria y su
politica de retencion, y queda en la cuenta personal del profesional, en su
telefono y en cualquier dispositivo donde la tenga sincronizada.

Un evento titulado «Consulta oncologia — Maria Torres» exporta a Google que
esa persona tiene cancer. Y el nombre del servicio basta por si solo: la
especialidad **es** informacion de salud.

Que lleva entonces el evento
----------------------------
Lo justo para que cumpla su funcion, que es **evitar que el profesional se
reserve encima**: un titulo neutro, el consultorio, el rango de horas y un
enlace al sistema. Quien necesite saber de quien es la cita entra al sistema,
que si tiene control de acceso.

Esto hace el calendario externo menos util de lo que un usuario espera, y es
deliberado. Esta razonado en ADR-0018.

Como se hace cumplir
--------------------
Igual que con las plantillas de mensajeria: el evento se construye **solo**
desde esta funcion, con un conjunto cerrado de campos, y hay pruebas que
intentan colar el nombre del paciente, el servicio y la especialidad y
comprueban que no aparecen.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime

# Titulo fijo. No se parametriza a proposito: en el momento en que admita una
# variable, alguien pondra ahi el servicio.
TITULO_EVENTO = "Cita reservada"

# Texto del cuerpo. Explica al profesional por que no ve mas y donde mirar;
# sin esa explicacion, el primero que abra su calendario pensara que el
# sistema esta roto.
PLANTILLA_DESCRIPCION = (
    "Reservado desde el sistema de la clinica.\n\n"
    "Por proteccion de datos, este evento no incluye el paciente ni el motivo "
    "de la consulta. El detalle esta en:\n{enlace}\n\n"
    "Referencia interna: {referencia}"
)

# Palabras que no pueden aparecer en ningun campo del evento. La prueba las
# busca en el resultado completo, no en los argumentos: es lo que detecta que
# alguien las haya concatenado por otra via.
PALABRAS_PROHIBIDAS: frozenset[str] = frozenset(
    {
        "diagnostico",
        "medicamento",
        "dosis",
        "tratamiento",
        "receta",
        "motivo",
        "sintoma",
        "alergia",
        "especialidad",
        "paciente",
    }
)

_NO_PERMITIDO_EN_UBICACION = re.compile(r"[\r\n]+")


class ContenidoNoPermitido(ValueError):
    """Se intento publicar contenido clinico o identificable en el evento."""


@dataclass(frozen=True, slots=True)
class EventoExterno:
    """Evento listo para el proveedor, con los campos que se permiten.

    Es un conjunto **cerrado**. No admite «campos extra» ni un diccionario
    libre: ahi es donde acabaria el dato que este modulo existe para impedir.
    """

    titulo: str
    descripcion: str
    inicio: datetime
    fin: datetime
    ubicacion: str | None
    # Identificador propio que viaja al proveedor. Permite reconciliar sin
    # depender de que el proveedor conserve nada nuestro.
    referencia_interna: str
    # Marca que distingue nuestros eventos de los que el profesional creo a
    # mano. Sin ella, la reconciliacion no sabria cuales le corresponden.
    etiqueta_origen: str = "sistema-clinica"

    def texto_completo(self) -> str:
        """Todo el texto que se enviara al proveedor, junto.

        Existe para que una prueba pueda inspeccionarlo de una vez, sin
        enumerar campos -- y para que un campo nuevo quede cubierto sin tocar
        la prueba.
        """
        return "\n".join(
            parte for parte in (self.titulo, self.descripcion, self.ubicacion or "") if parte
        )


def construir_evento(
    *,
    cita_id: uuid.UUID,
    inicio: datetime,
    fin: datetime,
    consultorio: str | None,
    sede: str | None,
    url_sistema: str,
) -> EventoExterno:
    """Construye el evento neutro de una cita.

    Los parametros son deliberadamente pocos. No recibe el paciente, ni el
    servicio, ni la especialidad, ni el motivo: no se puede filtrar lo que no
    llega.

    `consultorio` y `sede` son datos de ubicacion fisica, no clinicos. Pero
    una sede puede llamarse «Centro Oncologico», asi que se validan contra las
    palabras prohibidas antes de publicarlas -- es el unico campo de texto
    libre que el operador controla.
    """
    if inicio.tzinfo is None or fin.tzinfo is None:
        raise ValueError("El evento exige instantes con zona horaria (ADR-0010).")
    if fin <= inicio:
        raise ValueError("El fin del evento debe ser posterior a su inicio.")

    ubicacion = " · ".join(parte for parte in (sede, consultorio) if parte) or None
    if ubicacion is not None:
        ubicacion = _NO_PERMITIDO_EN_UBICACION.sub(" ", ubicacion).strip()

    referencia = f"cita:{cita_id}"
    evento = EventoExterno(
        titulo=TITULO_EVENTO,
        descripcion=PLANTILLA_DESCRIPCION.format(
            enlace=f"{url_sistema.rstrip('/')}/agenda/citas/{cita_id}",
            referencia=referencia,
        ),
        inicio=inicio,
        fin=fin,
        ubicacion=ubicacion,
        referencia_interna=referencia,
    )
    verificar(evento)
    return evento


def verificar(evento: EventoExterno) -> None:
    """Rechaza un evento que contenga contenido prohibido.

    Se ejecuta en `construir_evento` y tambien puede llamarse desde el
    adaptador, justo antes de publicar. Es la ultima barrera: si alguien
    construye un `EventoExterno` a mano -- por ejemplo para una prueba, o en
    un modulo futuro --, esta comprobacion sigue aplicandose.
    """
    texto = evento.texto_completo().lower()
    # La descripcion menciona «motivo de la consulta» para explicar que NO
    # esta, y «paciente» por lo mismo. Se excluye esa frase concreta antes de
    # buscar, en lugar de relajar la lista.
    texto = texto.replace("no incluye el paciente ni el motivo de la consulta", "")

    encontradas = sorted(palabra for palabra in PALABRAS_PROHIBIDAS if palabra in texto)
    if encontradas:
        raise ContenidoNoPermitido(
            f"El evento externo no puede contener {encontradas}. El calendario del "
            "profesional es un tercero: lo que se escribe ahi sale del control de "
            "acceso del sistema (RF-I09)."
        )


__all__ = [
    "PALABRAS_PROHIBIDAS",
    "PLANTILLA_DESCRIPCION",
    "TITULO_EVENTO",
    "ContenidoNoPermitido",
    "EventoExterno",
    "construir_evento",
    "verificar",
]
