"""Idempotencia de operaciones.

Dos fuentes de peticiones repetidas, con causas distintas y la misma
consecuencia si no se controlan:

* **Clientes.**  El paciente pulsa «Reservar» dos veces, o la red corta la
  respuesta y la aplicacion reintenta.  Sin idempotencia, dos citas.

* **Webhooks.**  Meta reintenta la entrega si no recibe un 200 a tiempo, y
  puede entregar el mismo mensaje varias veces.  Sin idempotencia, el mismo
  «quiero cancelar» se procesa dos veces.

El mecanismo es una clave con el hash de la peticion:

* Misma clave + mismo cuerpo  -> se devuelve la respuesta guardada.
* Misma clave + cuerpo distinto -> 409.  Significa que el cliente reutilizo
  una clave para otra operacion, y adivinar cual quiere seria peor que
  fallar.
* Clave en curso -> 409 con indicacion de reintento.  Evita que dos copias
  simultaneas de la misma peticion se procesen en paralelo.

El registro vive en PostgreSQL, no en Redis: si Redis se vacia, un reintento
de webhook volveria a procesarse y podria duplicar una cita.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any

# Limites de la clave que envia el cliente.  El maximo evita que una clave
# de megabytes se use como vector de agotamiento de almacenamiento; el minimo
# descarta claves tan cortas que colisionarian entre peticiones distintas.
LONGITUD_MINIMA_CLAVE = 8
LONGITUD_MAXIMA_CLAVE = 200


class EstadoIdempotencia(StrEnum):
    EN_CURSO = "EN_CURSO"
    COMPLETADA = "COMPLETADA"
    FALLIDA = "FALLIDA"


# Alcances de clave.  Separarlos impide que una clave de una operacion se
# confunda con la de otra: el cliente podria reutilizar el mismo
# identificador para una reserva y para un pago.
class AlcanceIdempotencia(StrEnum):
    CITA_CREAR = "cita.crear"
    CITA_CANCELAR = "cita.cancelar"
    CITA_REPROGRAMAR = "cita.reprogramar"
    OFERTA_ACEPTAR = "oferta.aceptar"
    PAGO_REGISTRAR = "pago.registrar"
    WEBHOOK_WHATSAPP = "webhook.whatsapp"
    OUTBOX_ENTREGA = "outbox.entrega"
    # El `state` de OAuth de calendario. Se registra aqui, y no en
    # `token_un_uso`, porque esa tabla exige un usuario y restringe su
    # `tipo` por CHECK; esto es exactamente lo que `clave_idempotencia`
    # existe para guardar: «esta operacion ya se proceso», con durabilidad
    # de PostgreSQL y no de Redis.
    CALENDARIO_OAUTH = "calendario.oauth"


def calcular_hash_peticion(cuerpo: Any) -> str:
    """Hash canonico del cuerpo de la peticion.

    Se serializa con claves ordenadas y sin espacios para que dos peticiones
    equivalentes con distinto orden de claves produzcan el mismo hash.  Sin
    la normalizacion, el mismo JSON reenviado por un cliente que reordena
    campos parecerian peticiones distintas y se procesaria dos veces.
    """
    if isinstance(cuerpo, (bytes, bytearray)):
        material = bytes(cuerpo)
    elif isinstance(cuerpo, str):
        material = cuerpo.encode("utf-8")
    else:
        material = json.dumps(
            cuerpo,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def calcular_clave_deduplicacion(*partes: str) -> str:
    """Clave de deduplicacion para el outbox.

    Se construye con las partes que identifican de forma unica la intencion:
    por ejemplo `("recordatorio_24h", str(cita_id))`.  Si la misma intencion
    se registra dos veces, la restriccion unica de la tabla lo rechaza y no
    se envia el mensaje dos veces al paciente.

    Recibir dos recordatorios de la misma cita erosiona la confianza en las
    notificaciones y lleva al paciente a silenciarlas, que es peor que no
    enviarlas.
    """
    material = "|".join(partes)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def validar_clave_cliente(clave: str) -> str:
    """Valida una clave de idempotencia recibida del cliente.

    Se exige longitud y alfabeto acotados.  Sin limite, un cliente podria
    enviar una clave de megabytes y usarla como vector de agotamiento de
    almacenamiento.
    """
    limpia = clave.strip()
    if not LONGITUD_MINIMA_CLAVE <= len(limpia) <= LONGITUD_MAXIMA_CLAVE:
        raise ValueError("La clave de idempotencia debe tener entre 8 y 200 caracteres.")
    if not all(c.isalnum() or c in "-_:." for c in limpia):
        raise ValueError(
            "La clave de idempotencia solo admite letras, numeros y los caracteres - _ : ."
        )
    return limpia
