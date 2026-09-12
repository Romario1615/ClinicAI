"""Adaptadores de calendario externo (ADR-0012).

Igual que con WhatsApp: adaptador real y adaptador sandbox tras un mismo
protocolo, seleccionables por entorno. No hay credenciales de Google y no se
inventan (CLAUDE.md, regla 3).

Lo que el sandbox si demuestra
------------------------------
Que la maquinaria alrededor funciona: la creacion idempotente, la
actualizacion, el borrado, y sobre todo la **reconciliacion** -- que es donde
estan los casos interesantes y donde el sandbox puede simular lo que un
proveedor real haria de vez en cuando: que el profesional borre el evento a
mano, que lo mueva de hora, o que el token caduque.

Esos tres casos son los que la suite ejerce, y no se podrian ejercer esperando
a que Google los produzca.

Lo que no demuestra
-------------------
Que la API de Google Calendar se comporte como este codigo supone. Queda
declarado en `docs/known-limitations.md` (E-1).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from app.modulos.calendario.eventos import EventoExterno, verificar
from app.nucleo.registro import obtener_logger

logger = obtener_logger(__name__)


class ResultadoCalendario(StrEnum):
    OK = "OK"
    # El evento ya no existe en el proveedor. No es un error: el profesional
    # pudo borrarlo a mano, y la respuesta correcta es volver a crearlo --
    # la agenda interna es la fuente de verdad (RF-I08).
    NO_ENCONTRADO = "NO_ENCONTRADO"
    # El evento cambio fuera del sistema. **No se sobrescribe**: se marca
    # conflicto para que lo resuelva una persona. Pisarlo destruiria un cambio
    # que el profesional hizo a proposito.
    CONFLICTO = "CONFLICTO"
    # Es el nombre de un estado, no una credencial: significa que el token
    # caduco y que hay que volver a autorizar. La excepcion de lint esta
    # en la propia linea.
    TOKEN_VENCIDO = "TOKEN_VENCIDO"  # noqa: S105
    FALLO_TEMPORAL = "FALLO_TEMPORAL"
    FALLO_PERMANENTE = "FALLO_PERMANENTE"


@dataclass(frozen=True, slots=True)
class RespuestaCalendario:
    resultado: ResultadoCalendario
    external_event_id: str | None = None
    etag: str | None = None
    detalle: str | None = None

    @property
    def es_reintentable(self) -> bool:
        return self.resultado in (
            ResultadoCalendario.FALLO_TEMPORAL,
            ResultadoCalendario.TOKEN_VENCIDO,
        )


@dataclass(frozen=True, slots=True)
class Credenciales:
    """Tokens ya descifrados. Nunca se registran en el log."""

    token_acceso: str
    token_refresco: str
    calendar_id: str

    def __repr__(self) -> str:
        # Evita que un `repr` accidental -- en un traceback, en un log de
        # depuracion -- vuelque el token en texto claro.
        return f"Credenciales(calendar_id={self.calendar_id!r}, tokens=<oculto>)"


@dataclass(frozen=True, slots=True)
class EstadoRemoto:
    """Lo que el proveedor dice que hay ahora mismo en ese evento."""

    existe: bool
    etag: str | None = None
    inicio: datetime | None = None
    fin: datetime | None = None
    # Cierto si el evento sigue llevando nuestra marca de origen. Si el
    # profesional lo edito tanto que la perdio, deja de ser nuestro reflejo.
    es_nuestro: bool = True


@runtime_checkable
class AdaptadorCalendario(Protocol):
    """Contrato de un proveedor de calendario."""

    nombre: str

    async def crear(
        self, credenciales: Credenciales, evento: EventoExterno
    ) -> RespuestaCalendario: ...

    async def actualizar(
        self,
        credenciales: Credenciales,
        external_event_id: str,
        evento: EventoExterno,
        *,
        etag: str | None,
    ) -> RespuestaCalendario: ...

    async def eliminar(
        self, credenciales: Credenciales, external_event_id: str
    ) -> RespuestaCalendario: ...

    async def consultar(
        self, credenciales: Credenciales, external_event_id: str
    ) -> EstadoRemoto: ...


# ---------------------------------------------------------------------------
#  Sandbox
# ---------------------------------------------------------------------------
@dataclass
class EventoSandbox:
    external_event_id: str
    etag: str
    evento: EventoExterno
    eliminado: bool = False
    # Cierto cuando la prueba simula que el profesional lo movio a mano.
    alterado_fuera: bool = False


class AdaptadorSandboxCalendario:
    """Calendario en memoria, con los fallos del mundo real simulables.

    Los tres metodos `simular_*` existen porque los casos que importan de esta
    integracion -- borrado externo, cambio externo, token vencido -- no se
    pueden provocar esperando a que el proveedor los produzca.
    """

    nombre = "sandbox"

    def __init__(self) -> None:
        self.eventos: dict[str, EventoSandbox] = {}
        self.token_vencido = False
        self.fallos_programados: list[ResultadoCalendario] = []
        # Historial de operaciones, para que una prueba pueda afirmar que NO
        # se llamo al proveedor cuando no debia.
        self.operaciones: list[tuple[str, str]] = []

    # --- simulacion -----------------------------------------------------
    def simular_borrado_externo(self, external_event_id: str) -> None:
        """El profesional borro el evento desde su telefono."""
        if external_event_id in self.eventos:
            self.eventos[external_event_id].eliminado = True

    def simular_cambio_externo(self, external_event_id: str, *, etag: str = "etag-externo") -> None:
        """El profesional movio el evento de hora a mano."""
        if external_event_id in self.eventos:
            self.eventos[external_event_id].alterado_fuera = True
            self.eventos[external_event_id].etag = etag

    def simular_token_vencido(self) -> None:
        self.token_vencido = True

    def programar_fallo(self, resultado: ResultadoCalendario) -> None:
        self.fallos_programados.append(resultado)

    def _interceptar(self) -> RespuestaCalendario | None:
        if self.token_vencido:
            return RespuestaCalendario(
                resultado=ResultadoCalendario.TOKEN_VENCIDO,
                detalle="El token de acceso caduco (simulado).",
            )
        if self.fallos_programados:
            return RespuestaCalendario(
                resultado=self.fallos_programados.pop(0), detalle="fallo simulado"
            )
        return None

    # --- protocolo ------------------------------------------------------
    async def crear(
        self, _credenciales: Credenciales, evento: EventoExterno
    ) -> RespuestaCalendario:
        # `_credenciales` no se usa: el sandbox no sale a la red. El protocolo
        # las exige porque el adaptador real si las necesita.
        self.operaciones.append(("crear", evento.referencia_interna))
        if (intercepcion := self._interceptar()) is not None:
            return intercepcion

        # Se verifica tambien aqui, no solo al construir: es la ultima barrera
        # antes de que el dato salga del sistema.
        verificar(evento)

        identificador = f"ev-{uuid.uuid4().hex[:16]}"
        self.eventos[identificador] = EventoSandbox(
            external_event_id=identificador, etag="etag-1", evento=evento
        )
        logger.info(
            "calendario.sandbox.evento_creado",
            external_event_id=identificador,
            referencia=evento.referencia_interna,
        )
        return RespuestaCalendario(
            resultado=ResultadoCalendario.OK,
            external_event_id=identificador,
            etag="etag-1",
        )

    async def actualizar(
        self,
        _credenciales: Credenciales,
        external_event_id: str,
        evento: EventoExterno,
        *,
        etag: str | None,
    ) -> RespuestaCalendario:
        self.operaciones.append(("actualizar", external_event_id))
        if (intercepcion := self._interceptar()) is not None:
            return intercepcion

        guardado = self.eventos.get(external_event_id)
        if guardado is None or guardado.eliminado:
            return RespuestaCalendario(resultado=ResultadoCalendario.NO_ENCONTRADO)

        # Control de concurrencia optimista, como el `If-Match` de Google. Es
        # lo que impide pisar un cambio que el profesional acaba de hacer.
        if etag is not None and guardado.etag != etag:
            return RespuestaCalendario(
                resultado=ResultadoCalendario.CONFLICTO,
                etag=guardado.etag,
                detalle="El evento cambio en el proveedor desde la ultima sincronizacion.",
            )

        verificar(evento)
        guardado.evento = evento
        guardado.alterado_fuera = False
        guardado.etag = f"etag-{uuid.uuid4().hex[:8]}"
        return RespuestaCalendario(
            resultado=ResultadoCalendario.OK,
            external_event_id=external_event_id,
            etag=guardado.etag,
        )

    async def eliminar(
        self, _credenciales: Credenciales, external_event_id: str
    ) -> RespuestaCalendario:
        self.operaciones.append(("eliminar", external_event_id))
        if (intercepcion := self._interceptar()) is not None:
            return intercepcion

        guardado = self.eventos.get(external_event_id)
        if guardado is None or guardado.eliminado:
            # Borrar algo que ya no esta es el resultado deseado, no un error.
            # Tratarlo como fallo haria que el reintento nunca terminara.
            return RespuestaCalendario(resultado=ResultadoCalendario.OK)

        guardado.eliminado = True
        return RespuestaCalendario(resultado=ResultadoCalendario.OK)

    async def consultar(self, _credenciales: Credenciales, external_event_id: str) -> EstadoRemoto:
        self.operaciones.append(("consultar", external_event_id))
        guardado = self.eventos.get(external_event_id)
        if guardado is None or guardado.eliminado:
            return EstadoRemoto(existe=False)
        return EstadoRemoto(
            existe=True,
            etag=guardado.etag,
            inicio=guardado.evento.inicio,
            fin=guardado.evento.fin,
            es_nuestro=True,
        )

    def limpiar(self) -> None:
        self.eventos.clear()
        self.operaciones.clear()
        self.fallos_programados.clear()
        self.token_vencido = False


@dataclass
class RegistroCalendarios:
    """Adaptador por proveedor."""

    proveedores: dict[str, AdaptadorCalendario] = field(default_factory=dict)

    def registrar(self, proveedor: str, adaptador: AdaptadorCalendario) -> None:
        self.proveedores[proveedor] = adaptador

    def obtener(self, proveedor: str) -> AdaptadorCalendario | None:
        return self.proveedores.get(proveedor)


__all__ = [
    "AdaptadorCalendario",
    "AdaptadorSandboxCalendario",
    "Credenciales",
    "EstadoRemoto",
    "EventoSandbox",
    "RegistroCalendarios",
    "RespuestaCalendario",
    "ResultadoCalendario",
]
