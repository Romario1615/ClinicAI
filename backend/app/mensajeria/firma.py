"""Verificacion de la firma de los webhooks entrantes.

El webhook de WhatsApp es un endpoint publico sin autenticacion: cualquiera en
internet puede hacerle POST.  Lo unico que distingue un mensaje real de uno
fabricado es la firma HMAC-SHA256 que Meta calcula con el secreto de la
aplicacion.

Sin esta verificacion, un tercero podria inyectar mensajes entrantes falsos y
provocar cancelaciones de citas de pacientes que nunca las pidieron.

Dos detalles que suelen hacerse mal
-----------------------------------
1. **Se firma el cuerpo crudo.**  Hay que calcular el HMAC sobre los bytes tal
   como llegaron, no sobre el JSON reserializado.  `json.dumps` de un cuerpo
   parseado cambia espacios, orden de claves y escapes, y el HMAC deja de
   coincidir.  De ahi que las rutas lean `await peticion.body()` antes de
   parsear.

2. **La comparacion es en tiempo constante.**  Comparar con `==` filtra, por
   el tiempo de respuesta, cuantos bytes iniciales acerto el atacante, y eso
   permite construir la firma byte a byte.  Se usa `hmac.compare_digest`.
"""

from __future__ import annotations

import hashlib
import hmac

from app.nucleo.errores import FirmaInvalida

PREFIJO_FIRMA = "sha256="
CABECERA_FIRMA = "X-Hub-Signature-256"


def calcular_firma(cuerpo: bytes, secreto: str) -> str:
    """Firma de un cuerpo, con el formato que envia Meta.

    Publica porque las pruebas necesitan construir peticiones validas sin
    duplicar el algoritmo: una prueba que reimplementa la firma puede pasar
    con una implementacion equivocada en ambos lados.
    """
    resumen = hmac.new(secreto.encode("utf-8"), cuerpo, hashlib.sha256).hexdigest()
    return f"{PREFIJO_FIRMA}{resumen}"


def verificar_firma(cuerpo: bytes, cabecera: str | None, secreto: str) -> None:
    """Comprueba la firma o lanza `FirmaInvalida`.

    Lanza tambien cuando falta el secreto en la configuracion: un endpoint que
    acepta cualquier cuerpo porque nadie configuro el secreto es peor que uno
    que no responde, porque parece que funciona.  Para trabajar sin secreto
    esta `WHATSAPP_VALIDAR_FIRMA=false`, que es explicito, esta prohibido en
    produccion y queda registrado en el log de arranque.
    """
    if not secreto:
        raise FirmaInvalida(
            "No hay secreto de aplicacion configurado para verificar la firma del webhook."
        )
    if not cabecera:
        raise FirmaInvalida("La peticion no trae la cabecera de firma.")
    if not cabecera.startswith(PREFIJO_FIRMA):
        raise FirmaInvalida("La cabecera de firma no tiene el formato esperado.")

    esperada = calcular_firma(cuerpo, secreto)
    if not hmac.compare_digest(esperada, cabecera):
        raise FirmaInvalida("La firma del webhook no coincide.")


def verificar_reto(
    *,
    modo: str | None,
    token: str | None,
    reto: str | None,
    token_esperado: str,
) -> str:
    """Resuelve el reto de verificacion inicial (`GET` del webhook).

    Meta llama una sola vez al dar de alta la URL, con `hub.mode=subscribe`,
    `hub.verify_token` y `hub.challenge`.  Hay que devolver el reto tal cual y
    en texto plano; cualquier otra respuesta deja el webhook sin registrar.

    El token se compara en tiempo constante por el mismo motivo que la firma.
    """
    if not token_esperado:
        raise FirmaInvalida("No hay token de verificacion configurado.")
    if modo != "subscribe":
        raise FirmaInvalida("Modo de verificacion no soportado.")
    if token is None or not hmac.compare_digest(token, token_esperado):
        raise FirmaInvalida("El token de verificacion no coincide.")
    if not reto:
        raise FirmaInvalida("La verificacion no incluye el reto.")
    return reto


__all__ = [
    "CABECERA_FIRMA",
    "PREFIJO_FIRMA",
    "calcular_firma",
    "verificar_firma",
    "verificar_reto",
]
