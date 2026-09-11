"""Primitivas de seguridad: contrasenas, tokens, cifrado y segundo factor.

Este modulo concentra las decisiones criptograficas para que estén en un solo
sitio auditable, y no repartidas por los servicios.

Decisiones y su motivo:

* **Argon2id** para contrasenas.  Es la recomendacion actual de OWASP:
  resistente a ataques con GPU, a diferencia de PBKDF2, y con un modo hibrido
  que cubre los canales laterales de Argon2i y la resistencia de Argon2d.

* **El token de acceso no lleva permisos.**  Lleva el identificador del
  usuario y poco mas.  Los permisos se resuelven en servidor en cada peticion.
  Meterlos en el token permitiria que un permiso revocado siguiera siendo
  valido durante la vida del token, y en datos clinicos eso es inaceptable.

* **Refresco rotativo con deteccion de reutilizacion.**  Cada refresco se usa
  una sola vez.  Reutilizar uno ya rotado significa que alguien tiene una
  copia robada: se revoca toda la familia de sesiones, no solo ese token.

* **AES-GCM** para los tokens OAuth de calendarios.  Cifrado autenticado: si
  alguien altera el texto cifrado en la base de datos, el descifrado falla en
  lugar de devolver basura.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final, Literal

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.nucleo.errores import TokenInvalido

# ---------------------------------------------------------------------------
#  Contrasenas
# ---------------------------------------------------------------------------
# Parametros alineados con la guia de OWASP para Argon2id:
#   memoria >= 19 MiB, iteraciones >= 2, paralelismo 1.
# Se elige memoria mas alta (64 MiB) porque el coste de verificacion solo se
# paga en el inicio de sesion, no en cada peticion.
_hasher: Final = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=2,
    hash_len=32,
    salt_len=16,
)

LONGITUD_MINIMA_CONTRASENA: Final = 12
LONGITUD_MAXIMA_CONTRASENA: Final = 128
# Los codigos TOTP de RFC 6238 con la configuracion habitual son de seis
# digitos.  Se valida la longitud antes de llamar a la libreria para no
# gastar una verificacion criptografica en una entrada obviamente invalida.
LONGITUD_CODIGO_TOTP: Final = 6


def hashear_contrasena(contrasena: str) -> str:
    """Genera el hash Argon2id de una contrasena."""
    if len(contrasena) > LONGITUD_MAXIMA_CONTRASENA:
        # Limite superior explicito: sin el, una entrada de megabytes
        # convierte el hasheo en una denegacion de servicio.
        raise ValueError(f"La contrasena excede {LONGITUD_MAXIMA_CONTRASENA} caracteres.")
    return _hasher.hash(contrasena)


def verificar_contrasena(contrasena: str, hash_almacenado: str) -> bool:
    """Comprueba una contrasena contra su hash.

    Devuelve `False` en lugar de propagar la excepcion para que la ruta de
    inicio de sesion trate igual todos los fallos y no revele por que fallo.
    """
    if len(contrasena) > LONGITUD_MAXIMA_CONTRASENA:
        return False
    try:
        return _hasher.verify(hash_almacenado, contrasena)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def requiere_rehash(hash_almacenado: str) -> bool:
    """Indica si el hash usa parametros antiguos.

    Al endurecer los parametros, los hashes existentes siguen siendo validos.
    Esta funcion permite regenerarlos de forma transparente en el siguiente
    inicio de sesion correcto, cuando la contrasena en claro esta disponible.
    """
    try:
        return _hasher.check_needs_rehash(hash_almacenado)
    except InvalidHashError:
        return True


def validar_politica_contrasena(contrasena: str) -> list[str]:
    """Devuelve la lista de incumplimientos de la politica.

    Se devuelven todos a la vez, no el primero: obligar al usuario a
    descubrirlos de uno en uno produce contrasenas peores, porque acaba
    eligiendo la minima que pasa.
    """
    problemas: list[str] = []
    if len(contrasena) < LONGITUD_MINIMA_CONTRASENA:
        problemas.append(f"Debe tener al menos {LONGITUD_MINIMA_CONTRASENA} caracteres.")
    if len(contrasena) > LONGITUD_MAXIMA_CONTRASENA:
        problemas.append(f"No puede exceder {LONGITUD_MAXIMA_CONTRASENA} caracteres.")
    if not any(c.isupper() for c in contrasena):
        problemas.append("Debe incluir al menos una letra mayuscula.")
    if not any(c.islower() for c in contrasena):
        problemas.append("Debe incluir al menos una letra minuscula.")
    if not any(c.isdigit() for c in contrasena):
        problemas.append("Debe incluir al menos un numero.")
    if contrasena.lower() in _CONTRASENAS_PROHIBIDAS:
        problemas.append("Esta contrasena es demasiado comun.")
    return problemas


# Lista minima incorporada.  La comprobacion contra una lista amplia de
# contrasenas filtradas se resuelve en la Fase 2 con un archivo externo; no se
# incrusta aqui para no inflar el codigo.
_CONTRASENAS_PROHIBIDAS: Final[frozenset[str]] = frozenset(
    {
        "contrasena123",
        "password123",
        "clinica123",
        "administrador",
        "12345678901",
        "qwertyuiop12",
    }
)


# ---------------------------------------------------------------------------
#  Tokens
# ---------------------------------------------------------------------------
TipoToken = Literal["acceso", "refresco", "verificacion_correo", "recuperacion"]


@dataclass(frozen=True, slots=True)
class ContenidoToken:
    """Datos que viaja dentro de un token, ya validados."""

    usuario_id: uuid.UUID
    clinica_id: uuid.UUID | None
    tipo: TipoToken
    jti: str
    # Identificador de la familia de sesiones.  Permite revocar todas las
    # rotaciones descendientes de un mismo inicio de sesion.
    familia: str
    # Si la sesion ya cumplio el segundo factor.  No se deduce del rol: un
    # usuario con 2FA obligatorio puede tener un token emitido antes de
    # completarlo, y ese token no debe dar acceso.
    segundo_factor_cumplido: bool
    emitido_en: datetime
    expira_en: datetime


def _codificar(
    *,
    clave_secreta: str,
    algoritmo: str,
    usuario_id: uuid.UUID,
    clinica_id: uuid.UUID | None,
    tipo: TipoToken,
    familia: str,
    segundo_factor_cumplido: bool,
    ahora: datetime,
    duracion: timedelta,
    jti: str | None = None,
) -> tuple[str, str]:
    """Firma un token. Devuelve (token, jti)."""
    identificador = jti or secrets.token_urlsafe(16)
    expira = ahora + duracion
    carga: dict[str, Any] = {
        "sub": str(usuario_id),
        "cli": str(clinica_id) if clinica_id else None,
        "typ": tipo,
        "jti": identificador,
        "fam": familia,
        "mfa": segundo_factor_cumplido,
        "iat": int(ahora.timestamp()),
        "exp": int(expira.timestamp()),
    }
    token = jwt.encode(carga, clave_secreta, algorithm=algoritmo)
    return token, identificador


def crear_token_acceso(
    *,
    clave_secreta: str,
    algoritmo: str,
    usuario_id: uuid.UUID,
    clinica_id: uuid.UUID | None,
    familia: str,
    segundo_factor_cumplido: bool,
    ahora: datetime,
    minutos: int,
) -> tuple[str, str]:
    """Token de acceso de vida corta.

    No contiene permisos ni roles a proposito: se resuelven en servidor en
    cada peticion, de modo que revocar un permiso surta efecto de inmediato.
    """
    return _codificar(
        clave_secreta=clave_secreta,
        algoritmo=algoritmo,
        usuario_id=usuario_id,
        clinica_id=clinica_id,
        tipo="acceso",
        familia=familia,
        segundo_factor_cumplido=segundo_factor_cumplido,
        ahora=ahora,
        duracion=timedelta(minutes=minutos),
    )


def crear_token_refresco(
    *,
    clave_secreta: str,
    algoritmo: str,
    usuario_id: uuid.UUID,
    clinica_id: uuid.UUID | None,
    familia: str,
    ahora: datetime,
    dias: int,
) -> tuple[str, str]:
    """Token de refresco de un solo uso.

    El `jti` se almacena con hash en la tabla de sesiones.  Al rotarlo, la
    fila anterior se marca como usada; si vuelve a aparecer, se revoca la
    familia completa.
    """
    return _codificar(
        clave_secreta=clave_secreta,
        algoritmo=algoritmo,
        usuario_id=usuario_id,
        clinica_id=clinica_id,
        tipo="refresco",
        familia=familia,
        # El refresco nunca acredita por si mismo el segundo factor: se
        # vuelve a resolver al emitir el token de acceso.
        segundo_factor_cumplido=False,
        ahora=ahora,
        duracion=timedelta(days=dias),
    )


def decodificar_token(
    token: str,
    *,
    clave_secreta: str,
    algoritmo: str,
    tipo_esperado: TipoToken,
    ahora: datetime | None = None,
) -> ContenidoToken:
    """Verifica y decodifica un token.

    Dos decisiones con motivo:

    * **El algoritmo esperado se fija en una lista de uno.**  Aceptar el que
      declara el propio token permite el ataque de confusion de algoritmo,
      incluido `alg: none`.

    * **La caducidad se comprueba contra el reloj inyectado, no contra el de
      PyJWT.**  PyJWT usa `time.time()` internamente, y eso deja la
      verificacion fuera del reloj de la aplicacion: una prueba no podria
      fijar el tiempo para comprobar la expiracion, en contra del ADR-0010.
      Se desactiva su comprobacion de `exp` y `iat` y se hace aqui, con el
      instante que recibe la funcion.  Si no se pasa `ahora`, se usa el
      reloj del sistema.
    """
    # Import local a proposito: `reloj` no importa `seguridad`, pero situar
    # este import arriba crearia un ciclo en cuanto `reloj` necesite
    # cualquier utilidad de este modulo.  Mantenerlo local deja el orden de
    # carga bajo control.
    from app.nucleo.reloj import RelojSistema  # noqa: PLC0415

    instante = ahora if ahora is not None else RelojSistema().ahora()

    try:
        carga = jwt.decode(
            token,
            clave_secreta,
            algorithms=[algoritmo],
            options={
                "require": ["exp", "iat", "sub", "jti"],
                # La caducidad se valida abajo, con el reloj inyectado.
                "verify_exp": False,
                "verify_iat": False,
            },
        )
    except jwt.InvalidTokenError as exc:
        raise TokenInvalido("El token no es valido.") from exc

    tipo = carga.get("typ")
    if tipo != tipo_esperado:
        # Un token de refresco usado como token de acceso, o un token de
        # recuperacion de contrasena usado para acceder a la API, deben
        # rechazarse aunque la firma sea correcta.
        raise TokenInvalido("El tipo de token no corresponde a la operacion.")

    try:
        emitido_en = datetime.fromtimestamp(float(carga["iat"]), tz=UTC)
        expira_en = datetime.fromtimestamp(float(carga["exp"]), tz=UTC)
    except (ValueError, TypeError, OSError, OverflowError) as exc:
        raise TokenInvalido("El token contiene marcas de tiempo invalidas.") from exc

    if instante >= expira_en:
        raise TokenInvalido("El token ha expirado.")

    # Un token emitido en el futuro indica desfase de reloj o manipulacion.
    # Se tolera un minuto para no romper por una diferencia menor entre
    # nodos, pero no mas.
    if emitido_en > instante + timedelta(minutes=1):
        raise TokenInvalido("El token tiene fecha de emision en el futuro.")

    try:
        usuario_id = uuid.UUID(str(carga["sub"]))
        clinica_id = uuid.UUID(str(carga["cli"])) if carga.get("cli") else None
    except (ValueError, KeyError, TypeError) as exc:
        raise TokenInvalido("El token contiene identificadores invalidos.") from exc

    return ContenidoToken(
        usuario_id=usuario_id,
        clinica_id=clinica_id,
        tipo=tipo_esperado,
        jti=str(carga["jti"]),
        familia=str(carga.get("fam", "")),
        segundo_factor_cumplido=bool(carga.get("mfa", False)),
        emitido_en=emitido_en,
        expira_en=expira_en,
    )


def hashear_jti(jti: str) -> str:
    """Hash del identificador de token para almacenarlo.

    La tabla de sesiones guarda el hash, no el `jti`.  Si alguien lee la base
    de datos, no obtiene tokens de refresco utilizables.
    """
    return hashlib.sha256(jti.encode("utf-8")).hexdigest()


def generar_familia_sesion() -> str:
    return secrets.token_urlsafe(16)


def generar_token_un_uso() -> tuple[str, str]:
    """Token para verificar correo o recuperar contrasena.

    Devuelve (token en claro, hash).  Solo el hash se almacena: un volcado de
    la base de datos no permite tomar cuentas.
    """
    token = secrets.token_urlsafe(32)
    return token, hashlib.sha256(token.encode("utf-8")).hexdigest()


def verificar_token_un_uso(token: str, hash_almacenado: str) -> bool:
    """Comparacion en tiempo constante."""
    calculado = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return hmac.compare_digest(calculado, hash_almacenado)


# ---------------------------------------------------------------------------
#  Cifrado de datos en reposo
# ---------------------------------------------------------------------------
_LONGITUD_NONCE: Final = 12  # 96 bits, el recomendado para AES-GCM
# AES-256 requiere una clave de 32 bytes.  Es el tamano que genera
# `Fernet.generate_key()` tras decodificar su base64.
_LONGITUD_CLAVE_AES: Final = 32


class CifradorDatos:
    """Cifra y descifra los tokens de terceros guardados en la base de datos.

    Se usa AES-GCM (cifrado autenticado) en lugar de AES-CBC: si alguien
    modifica el texto cifrado directamente en la base, el descifrado falla de
    forma explicita en vez de devolver datos alterados.

    El nonce se genera al azar en cada operacion y se guarda junto al texto
    cifrado.  Reutilizar un nonce con AES-GCM rompe la confidencialidad, asi
    que nunca se deriva de datos del registro.
    """

    def __init__(self, clave: str) -> None:
        material = self._derivar_clave(clave)
        self._aesgcm = AESGCM(material)

    @staticmethod
    def _derivar_clave(clave: str) -> bytes:
        """Normaliza la clave de configuracion a 32 bytes.

        Acepta tanto una clave en base64 de 32 bytes (lo que genera
        `Fernet.generate_key()`) como una cadena arbitraria, que se deriva con
        SHA-256.  Aceptar cualquier longitud sin derivar produciria errores
        opacos segun el valor que el operador haya puesto en el entorno.
        """
        try:
            bruto = base64.urlsafe_b64decode(clave.encode("utf-8"))
            if len(bruto) == _LONGITUD_CLAVE_AES:
                return bruto
        except (ValueError, TypeError):
            pass
        return hashlib.sha256(clave.encode("utf-8")).digest()

    def cifrar(self, texto: str, *, contexto: bytes | None = None) -> str:
        """Cifra y devuelve base64 de (nonce || texto cifrado || etiqueta).

        `contexto` son datos autenticados pero no cifrados.  Se usa para ligar
        el texto cifrado a su fila: por ejemplo el identificador del
        profesional.  Asi un token copiado de una fila a otra no descifra.
        """
        nonce = secrets.token_bytes(_LONGITUD_NONCE)
        cifrado = self._aesgcm.encrypt(nonce, texto.encode("utf-8"), contexto)
        return base64.urlsafe_b64encode(nonce + cifrado).decode("ascii")

    def descifrar(self, dato: str, *, contexto: bytes | None = None) -> str:
        """Descifra. Lanza `ValueError` si el dato fue alterado."""
        try:
            # Se traduce el alfabeto url-safe y se decodifica con
            # validate=True.
            #
            # `urlsafe_b64decode` no admite `validate`, y `b64decode` sin el
            # descarta en silencio los caracteres no validos: una cadena que
            # no es base64 producia un resultado corto y el mensaje enganoso
            # de "truncado" en lugar de "formato invalido".
            normalizado = dato.encode("ascii").translate(bytes.maketrans(b"-_", b"+/"))
            bruto = base64.b64decode(normalizado, validate=True)
        except (ValueError, TypeError, UnicodeEncodeError) as exc:
            raise ValueError("El dato cifrado no tiene un formato valido.") from exc

        if len(bruto) <= _LONGITUD_NONCE:
            raise ValueError("El dato cifrado esta truncado.")

        nonce, cifrado = bruto[:_LONGITUD_NONCE], bruto[_LONGITUD_NONCE:]
        try:
            return self._aesgcm.decrypt(nonce, cifrado, contexto).decode("utf-8")
        except InvalidTag as exc:
            raise ValueError(
                "El descifrado fallo: el dato fue alterado, el contexto no "
                "corresponde o la clave de cifrado cambio."
            ) from exc


# ---------------------------------------------------------------------------
#  Segundo factor (TOTP)
# ---------------------------------------------------------------------------
def generar_secreto_totp() -> str:
    return pyotp.random_base32()


def verificar_codigo_totp(secreto: str, codigo: str, *, ventana: int = 1) -> bool:
    """Verifica un codigo TOTP.

    `ventana=1` tolera un intervalo de 30 s de desfase de reloj en ambos
    sentidos.  Ampliarla mas facilitaria la reutilizacion de un codigo
    interceptado.
    """
    codigo_limpio = codigo.strip().replace(" ", "")
    if not codigo_limpio.isdigit() or len(codigo_limpio) != LONGITUD_CODIGO_TOTP:
        return False
    try:
        return pyotp.TOTP(secreto).verify(codigo_limpio, valid_window=ventana)
    except (ValueError, TypeError):
        return False


def url_provisionamiento_totp(secreto: str, *, correo: str, emisor: str) -> str:
    """URL `otpauth://` para el codigo QR de la aplicacion de autenticacion."""
    return pyotp.TOTP(secreto).provisioning_uri(name=correo, issuer_name=emisor)


def generar_codigos_recuperacion(cantidad: int = 8) -> list[tuple[str, str]]:
    """Codigos de recuperacion de un solo uso.

    Devuelve pares (codigo en claro, hash).  El claro se muestra una unica vez
    al usuario; solo se almacena el hash.  Sin ellos, perder el telefono con
    2FA obligatorio deja al profesional fuera del sistema.
    """
    codigos: list[tuple[str, str]] = []
    for _ in range(cantidad):
        crudo = secrets.token_hex(5).upper()
        codigo = f"{crudo[:5]}-{crudo[5:]}"
        codigos.append((codigo, hashlib.sha256(codigo.encode("utf-8")).hexdigest()))
    return codigos


# ---------------------------------------------------------------------------
#  Firma de webhooks
# ---------------------------------------------------------------------------
def verificar_firma_hmac_sha256(*, cuerpo: bytes, firma_recibida: str, secreto: str) -> bool:
    """Valida la cabecera `X-Hub-Signature-256` de Meta.

    Puntos que importan:
    * Se calcula sobre el **cuerpo crudo**, no sobre el JSON reserializado:
      cualquier diferencia de espaciado o de orden de claves cambia el hash.
    * Comparacion en tiempo constante, para no filtrar informacion por el
      tiempo de respuesta.
    * Una cabecera ausente o con formato raro devuelve `False`, no una
      excepcion: la ruta del webhook responde 403 igual en todos los casos.
    """
    if not firma_recibida or not secreto:
        return False

    esperado = hmac.new(secreto.encode("utf-8"), cuerpo, hashlib.sha256).hexdigest()

    recibido = firma_recibida.strip()
    if recibido.startswith("sha256="):
        recibido = recibido[len("sha256=") :]

    return hmac.compare_digest(esperado, recibido)


def calcular_firma_hmac_sha256(*, cuerpo: bytes, secreto: str) -> str:
    """Calcula la firma en el formato de Meta.

    La usa el adaptador sandbox de WhatsApp para emitir webhooks simulados con
    firma valida, de modo que la ruta de validacion se ejercite de verdad en
    las pruebas y no se quede sin cubrir (ADR-0012).
    """
    digest = hmac.new(secreto.encode("utf-8"), cuerpo, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def hashear_identificador(valor: str, *, sal: str = "") -> str:
    """Hash de un identificador para almacenarlo sin guardarlo en claro.

    Se usa con el telefono en las conversaciones de pacientes todavia no
    identificados: permite agrupar los mensajes de un mismo numero sin
    conservar el numero.
    """
    return hashlib.sha256(f"{sal}{valor}".encode()).hexdigest()
