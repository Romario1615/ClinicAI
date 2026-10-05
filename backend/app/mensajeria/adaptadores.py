"""Adaptadores de canal saliente (ADR-0012).

Por que hay dos implementaciones de cada canal
----------------------------------------------
No existen credenciales de WhatsApp Cloud API ni de Google Calendar para este
proyecto, y no se inventan (CLAUDE.md, regla 3).  La alternativa habitual --
dejar la integracion sin escribir hasta que lleguen las credenciales -- deja
sin probar todo lo que hay *alrededor* del envio: el outbox, los reintentos,
la deduplicacion, la conciliacion de estados de entrega.  Eso es la mayor
parte del riesgo.

Asi que cada canal tiene dos adaptadores tras un mismo protocolo:

* `AdaptadorSandbox...` registra el envio en memoria y devuelve una respuesta
  con la misma forma que la del proveedor.  Permite ejercer el flujo entero.
* `AdaptadorWhatsAppCloud` habla con la API real.

Lo que esto **no** demuestra
----------------------------
Que el camino real funcione.  El sandbox valida el contrato tal como esta
escrito aqui, no tal como lo implementa Meta.  Cualquier divergencia -- un
campo renombrado, un codigo de error distinto, una plantilla rechazada -- solo
aparece contra el proveedor real.  Queda declarado en `docs/known-limitations.md`
como E-1 y no debe presentarse como verificado.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

import httpx

from app.nucleo.errores import ProveedorExternoNoDisponible
from app.nucleo.registro import obtener_logger

logger = obtener_logger(__name__)


class ResultadoEnvio(StrEnum):
    """Desenlace de un intento de entrega.

    La distincion entre `FALLO_TEMPORAL` y `FALLO_PERMANENTE` es la que
    decide si se reintenta.  Reintentar un fallo permanente -- un numero que
    no existe, una plantilla no aprobada -- gasta la cuota del proveedor y
    retrasa los mensajes que si podrian entregarse.
    """

    ENTREGADO = "ENTREGADO"
    FALLO_TEMPORAL = "FALLO_TEMPORAL"
    FALLO_PERMANENTE = "FALLO_PERMANENTE"


@dataclass(frozen=True, slots=True)
class RespuestaEnvio:
    resultado: ResultadoEnvio
    # Identificador del proveedor. Permite conciliar los estados de entrega
    # que llegan despues por webhook.
    referencia_externa: str | None = None
    detalle: str | None = None

    @property
    def es_reintentable(self) -> bool:
        return self.resultado is ResultadoEnvio.FALLO_TEMPORAL


@dataclass(frozen=True, slots=True)
class MensajeSaliente:
    """Lo que se entrega a un adaptador.

    Lleva el texto ya redactado y tambien el nombre de la plantilla con sus
    variables, porque la Cloud API no acepta texto libre para iniciar una
    conversacion: exige la plantilla aprobada y sus parametros posicionales.
    """

    destino: str
    nombre_plantilla: str
    variables: tuple[str, ...]
    texto: str
    idioma: str = "es"
    # Media id de Meta para la cabecera de imagen (plantillas de marketing).
    imagen_cabecera: str | None = None


# ---------------------------------------------------------------------------
#  Protocolo
# ---------------------------------------------------------------------------
@runtime_checkable
class AdaptadorCanal(Protocol):
    """Contrato que cumple todo canal saliente."""

    nombre: str

    async def enviar(self, mensaje: MensajeSaliente) -> RespuestaEnvio:
        """Intenta entregar el mensaje.

        No lanza por un fallo del proveedor: devuelve `FALLO_TEMPORAL` o
        `FALLO_PERMANENTE`.  El que decide si se reintenta es el procesador
        del outbox, que es quien conoce los intentos ya gastados.
        """
        ...


# ---------------------------------------------------------------------------
#  Sandbox
# ---------------------------------------------------------------------------
@dataclass
class EnvioRegistrado:
    mensaje: MensajeSaliente
    referencia_externa: str


class AdaptadorSandbox:
    """Canal que no sale a la red.

    Guarda los envios en memoria para que una prueba pueda afirmar que se
    envio lo que se esperaba, y -- mas importante -- que **no** se envio lo
    que no se esperaba.

    `fallos_programados` permite ejercer los caminos de reintento sin
    depender de que el proveedor falle: se encolan respuestas y el adaptador
    las va consumiendo en orden.
    """

    def __init__(self, nombre: str = "sandbox") -> None:
        self.nombre = nombre
        self.enviados: list[EnvioRegistrado] = []
        self.fallos_programados: list[RespuestaEnvio] = []

    async def enviar(self, mensaje: MensajeSaliente) -> RespuestaEnvio:
        if self.fallos_programados:
            respuesta = self.fallos_programados.pop(0)
            logger.info(
                "sandbox.envio_fallido_programado",
                canal=self.nombre,
                resultado=respuesta.resultado.value,
            )
            return respuesta

        referencia = f"sandbox-{uuid.uuid4().hex[:16]}"
        self.enviados.append(EnvioRegistrado(mensaje=mensaje, referencia_externa=referencia))
        # El destino no se registra en el log: es un numero de telefono, y un
        # log de aplicacion no es el sitio de un dato de contacto.
        logger.info(
            "sandbox.envio",
            canal=self.nombre,
            plantilla=mensaje.nombre_plantilla,
            referencia_externa=referencia,
        )
        return RespuestaEnvio(
            resultado=ResultadoEnvio.ENTREGADO,
            referencia_externa=referencia,
            detalle="Entregado por el adaptador sandbox. No salio a la red.",
        )

    async def subir_medio(self, datos: bytes, tipo_mime: str) -> str:
        """Simula la subida de un medio: devuelve un id estable por contenido."""
        del tipo_mime
        return f"sandbox-media-{hashlib.sha256(datos).hexdigest()[:16]}"

    def programar_fallo(self, resultado: ResultadoEnvio, detalle: str = "fallo simulado") -> None:
        self.fallos_programados.append(RespuestaEnvio(resultado=resultado, detalle=detalle))

    def limpiar(self) -> None:
        self.enviados.clear()
        self.fallos_programados.clear()


# ---------------------------------------------------------------------------
#  WhatsApp Business Cloud API
# ---------------------------------------------------------------------------
# Codigos de error de Meta que no mejoran reintentando.  La lista es corta a
# proposito: ante un codigo desconocido se reintenta, porque descartar un
# recordatorio por un error que era temporal es peor que un reintento de mas.
#
# Referencia: Cloud API, «Error Codes».
CODIGOS_PERMANENTES: frozenset[int] = frozenset(
    {
        131_026,  # El destinatario no puede recibir el mensaje.
        131_047,  # Fuera de la ventana de 24 h y sin plantilla valida.
        131_051,  # Tipo de mensaje no soportado.
        132_000,  # Numero de parametros de la plantilla incorrecto.
        132_001,  # La plantilla no existe o no esta aprobada.
        132_005,  # Texto traducido demasiado largo.
        132_007,  # Formato del parametro invalido.
        133_010,  # Numero no registrado.
        190,  # Token de acceso invalido o caducado: reintentar no lo arregla.
    }
)


# Umbrales de estado HTTP, con nombre para que la intencion se lea sin
# consultar la tabla de codigos.
HTTP_REDIRECCION = 300
HTTP_DEMASIADAS_PETICIONES = 429
HTTP_ERROR_SERVIDOR = 500


@dataclass(frozen=True, slots=True)
class CredencialesWhatsApp:
    id_numero_telefono: str
    token_acceso: str
    version_api: str = "v21.0"
    url_base: str = "https://graph.facebook.com"

    def url_mensajes(self) -> str:
        return f"{self.url_base}/{self.version_api}/{self.id_numero_telefono}/messages"


class AdaptadorWhatsAppCloud:
    """Canal WhatsApp sobre la Business Cloud API.

    **Sin verificar contra el proveedor.**  Este codigo esta escrito contra la
    documentacion publica de la Cloud API; no se ha ejecutado un solo envio
    real porque no hay credenciales (limitacion E-1).  No se debe dar por
    funcional hasta que la clinica aporte una cuenta y se repita la suite
    contra el entorno de pruebas de Meta.

    Nunca se usa WhatsApp Web ni automatizacion del cliente (regla 9): solo
    esta API.
    """

    nombre = "whatsapp_cloud"

    def __init__(
        self,
        credenciales: CredencialesWhatsApp,
        *,
        cliente: httpx.AsyncClient | None = None,
        timeout_segundos: float = 15.0,
    ) -> None:
        if not credenciales.id_numero_telefono or not credenciales.token_acceso:
            # Falla al construirlo, no al primer envio.  Arrancar con el
            # adaptador real mal configurado significa descubrirlo cuando un
            # paciente no recibio su recordatorio.
            raise ProveedorExternoNoDisponible(
                "El adaptador de WhatsApp Cloud API exige WHATSAPP_ID_NUMERO_TELEFONO y "
                "WHATSAPP_TOKEN_ACCESO. Para trabajar sin credenciales use MODO_WHATSAPP=sandbox."
            )
        self._credenciales = credenciales
        self._cliente = cliente
        self._timeout = timeout_segundos

    async def enviar(self, mensaje: MensajeSaliente) -> RespuestaEnvio:
        cuerpo = self._construir_cuerpo(mensaje)
        cabeceras = {
            "Authorization": f"Bearer {self._credenciales.token_acceso}",
            "Content-Type": "application/json",
        }
        cliente = self._cliente or httpx.AsyncClient(timeout=self._timeout)
        propio = self._cliente is None
        try:
            respuesta = await cliente.post(
                self._credenciales.url_mensajes(), json=cuerpo, headers=cabeceras
            )
        except httpx.TimeoutException:
            # Un timeout es ambiguo: el mensaje pudo entregarse. Se reintenta,
            # y la deduplicacion del outbox evita el duplicado.
            return RespuestaEnvio(
                resultado=ResultadoEnvio.FALLO_TEMPORAL,
                detalle="Tiempo de espera agotado contra la Cloud API.",
            )
        except httpx.HTTPError as exc:
            return RespuestaEnvio(
                resultado=ResultadoEnvio.FALLO_TEMPORAL,
                detalle=f"Error de red contra la Cloud API: {type(exc).__name__}",
            )
        finally:
            if propio:
                await cliente.aclose()

        return self._interpretar(respuesta)

    async def subir_medio(self, datos: bytes, tipo_mime: str) -> str:
        """Sube una imagen a la Cloud API y devuelve su media id.

        Se sube una vez por campana, no por destinatario: el id se reutiliza
        en cada envio de la plantilla. **Sin verificar contra el proveedor**
        (limitacion E-1), igual que `enviar`.
        """
        url = (
            f"{self._credenciales.url_base}/{self._credenciales.version_api}/"
            f"{self._credenciales.id_numero_telefono}/media"
        )
        cliente = self._cliente or httpx.AsyncClient(timeout=self._timeout)
        propio = self._cliente is None
        try:
            respuesta = await cliente.post(
                url,
                data={"messaging_product": "whatsapp", "type": tipo_mime},
                files={"file": ("imagen", datos, tipo_mime)},
                headers={"Authorization": f"Bearer {self._credenciales.token_acceso}"},
            )
        except httpx.HTTPError as exc:
            raise ProveedorExternoNoDisponible(
                f"No se pudo subir la imagen a WhatsApp: {type(exc).__name__}"
            ) from exc
        finally:
            if propio:
                await cliente.aclose()
        if respuesta.status_code >= HTTP_REDIRECCION:
            raise ProveedorExternoNoDisponible(
                f"WhatsApp rechazo la imagen ({respuesta.status_code})."
            )
        return str(respuesta.json()["id"])

    def _construir_cuerpo(self, mensaje: MensajeSaliente) -> dict[str, object]:
        # Nombres impuestos por la API externa: no se traducen (CLAUDE.md,
        # seccion 2, excepcion de APIs externas).
        componentes: list[dict[str, object]] = []
        if mensaje.imagen_cabecera:
            componentes.append(
                {
                    "type": "header",
                    "parameters": [{"type": "image", "image": {"id": mensaje.imagen_cabecera}}],
                }
            )
        componentes.append(
            {
                "type": "body",
                "parameters": [{"type": "text", "text": valor} for valor in mensaje.variables],
            }
        )
        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": mensaje.destino,
            "type": "template",
            "template": {
                "name": mensaje.nombre_plantilla,
                "language": {"code": mensaje.idioma},
                "components": componentes,
            },
        }

    def _interpretar(self, respuesta: httpx.Response) -> RespuestaEnvio:
        if respuesta.status_code < HTTP_REDIRECCION:
            try:
                datos = respuesta.json()
                referencia = str(datos["messages"][0]["id"])
            except (ValueError, KeyError, IndexError, TypeError):
                # Respondio 2xx con una forma inesperada. Se considera
                # entregado -- el proveedor lo acepto -- pero sin referencia
                # no habra conciliacion de estado de entrega.
                logger.warning("whatsapp.respuesta_sin_identificador")
                return RespuestaEnvio(
                    resultado=ResultadoEnvio.ENTREGADO,
                    detalle="Aceptado sin identificador de mensaje.",
                )
            return RespuestaEnvio(resultado=ResultadoEnvio.ENTREGADO, referencia_externa=referencia)

        codigo = self._codigo_de_error(respuesta)
        if (
            respuesta.status_code == HTTP_DEMASIADAS_PETICIONES
            or respuesta.status_code >= HTTP_ERROR_SERVIDOR
        ):
            return RespuestaEnvio(
                resultado=ResultadoEnvio.FALLO_TEMPORAL,
                detalle=f"HTTP {respuesta.status_code} de la Cloud API (codigo {codigo}).",
            )
        if codigo is not None and codigo in CODIGOS_PERMANENTES:
            return RespuestaEnvio(
                resultado=ResultadoEnvio.FALLO_PERMANENTE,
                detalle=f"La Cloud API rechazo el mensaje de forma definitiva (codigo {codigo}).",
            )
        # 4xx desconocido: se reintenta. Ver comentario de CODIGOS_PERMANENTES.
        return RespuestaEnvio(
            resultado=ResultadoEnvio.FALLO_TEMPORAL,
            detalle=f"HTTP {respuesta.status_code} de la Cloud API (codigo {codigo}).",
        )

    @staticmethod
    def _codigo_de_error(respuesta: httpx.Response) -> int | None:
        try:
            cuerpo = respuesta.json()
        except ValueError:
            return None
        if not isinstance(cuerpo, dict):
            return None
        error = cuerpo.get("error")
        if not isinstance(error, dict):
            return None
        codigo = error.get("code")
        return codigo if isinstance(codigo, int) else None


# ---------------------------------------------------------------------------
#  Registro de canales
# ---------------------------------------------------------------------------
@dataclass
class RegistroCanales:
    """Adaptador por canal del outbox.

    Un canal sin adaptador no es un error de arranque: el mensaje queda
    PENDIENTE y el procesador lo marca con su motivo.  Arrancar la aplicacion
    exigiendo los cuatro canales impediria levantar el backend para trabajar
    en la agenda.
    """

    canales: dict[str, AdaptadorCanal] = field(default_factory=dict)

    def registrar(self, canal: str, adaptador: AdaptadorCanal) -> None:
        self.canales[canal] = adaptador

    def obtener(self, canal: str) -> AdaptadorCanal | None:
        return self.canales.get(canal)


__all__ = [
    "CODIGOS_PERMANENTES",
    "HTTP_DEMASIADAS_PETICIONES",
    "HTTP_ERROR_SERVIDOR",
    "HTTP_REDIRECCION",
    "AdaptadorCanal",
    "AdaptadorSandbox",
    "AdaptadorWhatsAppCloud",
    "CredencialesWhatsApp",
    "EnvioRegistrado",
    "MensajeSaliente",
    "RegistroCanales",
    "RespuestaEnvio",
    "ResultadoEnvio",
]
