"""Configuracion de proveedores externos, aislada por clinica.

Las claves se cifran antes de escribirlas en `configuracion_clinica`. Las
respuestas solo incluyen indicadores de presencia; una credencial guardada
nunca vuelve a salir por la API.
"""

from __future__ import annotations

import time
import uuid
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ia.decisiones import ClasificadorJev
from app.ia.proveedores_clinica import contexto_cifrado, descifrar, leer_integracion
from app.ia.resumen_clinico import _url_local
from app.modulos.organizacion.modelos import ConfiguracionClinica
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import Principal
from app.nucleo.bd import tomar_bloqueo_consultivo
from app.nucleo.dependencias import Auditor, CifradorActual, RelojActual, Sesion, exige_permiso
from app.nucleo.errores import DatosInvalidos, RecursoNoEncontrado

enrutador = APIRouter(prefix="/configuracion", tags=["configuracion"])
PuedeConfigurar = Annotated[Principal, Depends(exige_permiso("configuracion.escribir"))]
TOKENS_MINIMOS = 64
TOKENS_MAXIMOS = 32_000
PUERTO_MAXIMO = 65_535
CORREO_MAXIMO = 200
URL_MAXIMA = 500
SECRETO_MAXIMO = 4096


class ActualizarIntegracion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    habilitada: bool
    ajustes: dict[str, Any] = Field(default_factory=dict)
    secretos: dict[str, str] = Field(default_factory=dict)
    eliminar_secretos: list[str] = Field(default_factory=list)


class EstadoSecreto(BaseModel):
    configurado: bool


class IntegracionConfigurada(BaseModel):
    codigo: str
    habilitada: bool
    ajustes: dict[str, Any]
    secretos: dict[str, EstadoSecreto]
    version: int


_CAMPOS_AJUSTES: dict[str, dict[str, str]] = {
    "anthropic": {
        "modelo": "texto",
        "max_tokens": "tokens",
        "temperatura": "temperatura",
    },
    "whatsapp": {
        "id_numero_telefono": "texto",
        "id_cuenta_negocio": "texto",
        "version_api": "version_meta",
        "validar_firma": "booleano",
    },
    "google_calendar": {
        "client_id": "texto",
        "redirect_uri": "url",
        "scopes": "texto_largo",
    },
    "typesafe": {
        "modelo": "texto",
        "tiempo_limite": "segundos",
        "umbral_confianza": "probabilidad",
    },
    "respuestas_ia": {
        "proveedor": "opcion_llm",
        "ollama_url": "url_local",
        "ollama_modelo": "texto",
    },
    # El agente atiende WhatsApp (ADR-0025). Solo un interruptor: apagado por
    # defecto; las reglas de que puede hacer viven en el codigo, no aqui.
    "agente_whatsapp": {},
    "smtp": {
        "host": "texto",
        "puerto": "puerto",
        "usuario": "texto",
        "tls": "booleano",
        "correo_remitente": "correo",
        "nombre_remitente": "texto",
    },
}

_CAMPOS_SECRETOS: dict[str, tuple[str, ...]] = {
    "anthropic": ("api_key",),
    "whatsapp": ("token_acceso", "token_verificacion", "secreto_app"),
    "google_calendar": ("client_secret",),
    "smtp": ("contrasena",),
    "typesafe": ("api_key",),
    "respuestas_ia": (),
    "agente_whatsapp": (),
}

_AJUSTES_POR_DEFECTO: dict[str, dict[str, Any]] = {
    "anthropic": {"modelo": "claude-sonnet-5", "max_tokens": 2048, "temperatura": 0.2},
    "whatsapp": {"version_api": "v21.0", "validar_firma": True},
    "google_calendar": {
        "redirect_uri": "",
        "scopes": "https://www.googleapis.com/auth/calendar.events",
    },
    "smtp": {"puerto": 587, "tls": True, "correo_remitente": "", "nombre_remitente": ""},
    "typesafe": {"modelo": "jev-latest", "tiempo_limite": 3.0, "umbral_confianza": 0.85},
    "respuestas_ia": {"proveedor": "entorno", "ollama_url": "", "ollama_modelo": ""},
    "agente_whatsapp": {},
}
PROVEEDORES_RESPUESTA = frozenset({"entorno", "anthropic", "ollama"})
SEGUNDOS_MINIMOS = 0.2
SEGUNDOS_MAXIMOS = 30.0
UMBRAL_MINIMO = 0.5
UMBRAL_MAXIMO = 0.99
MENSAJE_PRUEBA = "Hola, quiero reservar una cita de limpieza dental para la proxima semana."


def _contexto_cifrado(clinica_id: uuid.UUID, codigo: str, campo: str) -> bytes:
    return contexto_cifrado(clinica_id, codigo, campo)


def _validar_ajuste(campo: str, tipo: str, valor: Any) -> Any:  # noqa: PLR0911, PLR0912
    if tipo in {"texto", "texto_largo", "version_meta"}:
        maximo = 2000 if tipo == "texto_largo" else 300
        if not isinstance(valor, str) or len(valor.strip()) > maximo:
            raise DatosInvalidos(f"El campo {campo} debe ser texto de hasta {maximo} caracteres.")
        texto = valor.strip()
        if tipo == "version_meta" and (
            not texto.startswith("v") or not texto[1:].replace(".", "").isdigit()
        ):
            raise DatosInvalidos("La version de WhatsApp debe tener formato vNN.N.")
        return texto
    if tipo == "booleano":
        if type(valor) is not bool:
            raise DatosInvalidos(f"El campo {campo} debe ser verdadero o falso.")
        return valor
    if tipo == "tokens":
        if type(valor) is not int or not TOKENS_MINIMOS <= valor <= TOKENS_MAXIMOS:
            raise DatosInvalidos("max_tokens debe estar entre 64 y 32000.")
        return valor
    if tipo == "temperatura":
        if type(valor) not in {int, float} or not 0 <= float(valor) <= 1:
            raise DatosInvalidos("temperatura debe estar entre 0 y 1.")
        return float(valor)
    if tipo == "puerto":
        if type(valor) is not int or not 1 <= valor <= PUERTO_MAXIMO:
            raise DatosInvalidos("El puerto debe estar entre 1 y 65535.")
        return valor
    if tipo == "correo":
        if not isinstance(valor, str) or len(valor) > CORREO_MAXIMO or (valor and "@" not in valor):
            raise DatosInvalidos("Ingrese un correo remitente valido.")
        return valor.strip()
    if tipo == "url":
        if not isinstance(valor, str) or len(valor) > URL_MAXIMA:
            raise DatosInvalidos("La URL de retorno no es valida.")
        if valor and not valor.startswith(("https://", "http://localhost", "http://127.0.0.1")):
            raise DatosInvalidos("La URL de retorno debe usar HTTPS.")
        return valor.strip()
    return _validar_ajuste_ia(campo, tipo, valor)


def _validar_ajuste_ia(campo: str, tipo: str, valor: Any) -> Any:
    """Ajustes del modelo de decision y del LLM que redacta."""
    numero = type(valor) in {int, float}
    if tipo == "segundos":
        if not numero or not SEGUNDOS_MINIMOS <= float(valor) <= SEGUNDOS_MAXIMOS:
            raise DatosInvalidos("El tiempo maximo debe estar entre 0,2 y 30 segundos.")
        return float(valor)
    if tipo == "probabilidad":
        if not numero or not UMBRAL_MINIMO <= float(valor) <= UMBRAL_MAXIMO:
            raise DatosInvalidos("El umbral de confianza debe estar entre 0,5 y 0,99.")
        return float(valor)
    if tipo == "opcion_llm":
        if valor not in PROVEEDORES_RESPUESTA:
            raise DatosInvalidos("Elija Anthropic, Ollama o el proveedor del servidor.")
        return valor
    if tipo == "url_local":
        if not isinstance(valor, str) or len(valor) > URL_MAXIMA:
            raise DatosInvalidos(f"El campo {campo} no es una URL valida.")
        texto = valor.strip()
        if texto and (not texto.startswith(("http://", "https://")) or not _url_local(texto)):
            raise DatosInvalidos(
                "Ollama solo se admite en la maquina local o en la red privada de la clinica."
            )
        return texto
    raise DatosInvalidos("El tipo de ajuste no esta admitido.")


def _clave(codigo: str) -> str:
    if codigo not in _CAMPOS_AJUSTES:
        raise RecursoNoEncontrado("La integracion solicitada no esta disponible.")
    return f"integracion.{codigo}"


def _estado(codigo: str, fila: ConfiguracionClinica | None) -> IntegracionConfigurada:
    valor = fila.valor if fila is not None and isinstance(fila.valor, dict) else {}
    ajustes = dict(_AJUSTES_POR_DEFECTO[codigo])
    guardados = valor.get("ajustes")
    if isinstance(guardados, dict):
        ajustes.update(guardados)
    secretos_cifrados = valor.get("secretos_cifrados")
    if not isinstance(secretos_cifrados, dict):
        secretos_cifrados = {}
    secretos = {
        campo: EstadoSecreto(configurado=bool(secretos_cifrados.get(campo)))
        for campo in _CAMPOS_SECRETOS[codigo]
    }
    return IntegracionConfigurada(
        codigo=codigo,
        habilitada=bool(valor.get("habilitada", False)),
        ajustes=ajustes,
        secretos=secretos,
        version=fila.version if fila is not None else 0,
    )


@enrutador.get("/integraciones", response_model=list[IntegracionConfigurada])
async def listar_integraciones(
    principal: PuedeConfigurar, sesion: Sesion
) -> list[IntegracionConfigurada]:
    if principal.clinica_id is None:
        raise RecursoNoEncontrado("La sesion no tiene una clinica asociada.")
    filas = (
        (
            await sesion.execute(
                select(ConfiguracionClinica).where(
                    ConfiguracionClinica.clinica_id == principal.clinica_id,
                    ConfiguracionClinica.clave.in_([_clave(codigo) for codigo in _CAMPOS_AJUSTES]),
                    ConfiguracionClinica.vigente.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    por_clave = {fila.clave: fila for fila in filas}
    return [_estado(codigo, por_clave.get(_clave(codigo))) for codigo in _CAMPOS_AJUSTES]


@enrutador.put("/integraciones/{codigo}", response_model=IntegracionConfigurada)
async def actualizar_integracion(  # noqa: PLR0912
    codigo: str,
    datos: ActualizarIntegracion,
    principal: PuedeConfigurar,
    sesion: Sesion,
    cifrador: CifradorActual,
    reloj: RelojActual,
    auditor: Auditor,
) -> IntegracionConfigurada:
    clinica_id = principal.clinica_id
    if clinica_id is None:
        raise RecursoNoEncontrado("La sesion no tiene una clinica asociada.")
    clave = _clave(codigo)

    desconocidos = set(datos.ajustes) - _CAMPOS_AJUSTES[codigo].keys()
    if desconocidos:
        raise DatosInvalidos(f"Ajustes no admitidos: {sorted(desconocidos)}.")
    secretos_validos = set(_CAMPOS_SECRETOS[codigo])
    if set(datos.secretos) - secretos_validos or set(datos.eliminar_secretos) - secretos_validos:
        raise DatosInvalidos("La integracion contiene un campo de credencial no admitido.")
    if set(datos.secretos) & set(datos.eliminar_secretos):
        raise DatosInvalidos("No puede reemplazar y eliminar la misma credencial en un guardado.")
    for campo, secreto in datos.secretos.items():
        if not secreto.strip() or len(secreto) > SECRETO_MAXIMO:
            raise DatosInvalidos(f"La credencial {campo} esta vacia o supera el limite permitido.")

    await tomar_bloqueo_consultivo(sesion, espacio=8142, clave=f"{clinica_id}:{clave}")
    fila = (
        await sesion.execute(
            select(ConfiguracionClinica)
            .where(
                ConfiguracionClinica.clinica_id == clinica_id,
                ConfiguracionClinica.clave == clave,
                ConfiguracionClinica.vigente.is_(True),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    valor_anterior: dict[str, Any] = (
        fila.valor if fila is not None and isinstance(fila.valor, dict) else {}
    )
    ajustes = dict(_AJUSTES_POR_DEFECTO[codigo])
    existentes = valor_anterior.get("ajustes")
    if isinstance(existentes, dict):
        ajustes.update(existentes)
    for campo, valor in datos.ajustes.items():
        ajustes[campo] = _validar_ajuste(campo, _CAMPOS_AJUSTES[codigo][campo], valor)

    secretos_cifrados = dict(valor_anterior.get("secretos_cifrados", {}))
    for campo in datos.eliminar_secretos:
        secretos_cifrados.pop(campo, None)
    for campo, secreto in datos.secretos.items():
        secretos_cifrados[campo] = cifrador.cifrar(
            secreto.strip(), contexto=_contexto_cifrado(clinica_id, codigo, campo)
        )

    if codigo == "anthropic" and datos.habilitada and "api_key" not in secretos_cifrados:
        raise DatosInvalidos(
            "Guarde la clave API de Anthropic antes de habilitar esta integracion."
        )
    if codigo == "whatsapp" and datos.habilitada:
        necesarios = {"token_acceso", "token_verificacion", "secreto_app"}
        if (
            not necesarios.issubset(secretos_cifrados)
            or not ajustes.get("id_numero_telefono")
            or ajustes.get("validar_firma") is not True
        ):
            raise DatosInvalidos(
                "WhatsApp requiere numero, credenciales completas y validacion de firma habilitada."
            )
    if (
        codigo == "google_calendar"
        and datos.habilitada
        and (not ajustes.get("client_id") or "client_secret" not in secretos_cifrados)
    ):
        raise DatosInvalidos("Google Calendar requiere client ID y client secret.")
    await _validar_habilitacion_ia(
        sesion, clinica_id, codigo, datos.habilitada, ajustes, secretos_cifrados
    )
    if (
        codigo == "smtp"
        and datos.habilitada
        and (not ajustes.get("host") or not ajustes.get("correo_remitente"))
    ):
        raise DatosInvalidos("El correo requiere servidor SMTP y correo remitente.")

    version = fila.version + 1 if fila is not None else 1
    if fila is not None:
        # El historial conserva ajustes, nunca credenciales antiguas: rotar o
        # retirar una clave tambien la elimina de la version que deja de regir.
        valor_historial = dict(fila.valor) if isinstance(fila.valor, dict) else {}
        valor_historial.pop("secretos_cifrados", None)
        fila.valor = valor_historial
        fila.vigente = False
    nueva = ConfiguracionClinica(
        clinica_id=clinica_id,
        clave=clave,
        valor={
            "habilitada": datos.habilitada,
            "ajustes": ajustes,
            "secretos_cifrados": secretos_cifrados,
        },
        version=version,
        vigente=True,
    )
    sesion.add(nueva)
    await sesion.flush()
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.INTEGRACION_CONFIGURADA,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="integracion",
                entidad_id=nueva.id,
                integracion=codigo,
                habilitada=datos.habilitada,
                version=version,
            )
        ]
    )
    await sesion.commit()
    return _estado(codigo, nueva)


async def _validar_habilitacion_ia(
    sesion: AsyncSession,
    clinica_id: uuid.UUID,
    codigo: str,
    habilitada: bool,
    ajustes: dict[str, Any],
    secretos_cifrados: dict[str, Any],
) -> None:
    if not habilitada:
        return
    if codigo == "typesafe" and "api_key" not in secretos_cifrados:
        raise DatosInvalidos("Guarde la clave API de JEV antes de habilitar esta integracion.")
    if codigo != "respuestas_ia":
        return
    if ajustes.get("proveedor") == "ollama" and (
        not ajustes.get("ollama_url") or not ajustes.get("ollama_modelo")
    ):
        raise DatosInvalidos("Para usar Ollama indique su URL local y el modelo.")
    if ajustes.get("proveedor") == "anthropic":
        anthropic = await leer_integracion(sesion, clinica_id, "anthropic")
        if (
            anthropic is None
            or not anthropic.habilitada
            or "api_key" not in anthropic.secretos_cifrados
        ):
            raise DatosInvalidos(
                "Habilite primero la integracion de Anthropic con su clave para usarla aqui."
            )


class PruebaJev(BaseModel):
    respondio: bool
    mensaje: str
    intencion: str
    confianza: float
    pregunta_clinica: float
    urgencia: float
    milisegundos: int


@enrutador.post("/integraciones/typesafe/prueba", response_model=PruebaJev)
async def probar_jev(
    principal: PuedeConfigurar,
    sesion: Sesion,
    cifrador: CifradorActual,
    reloj: RelojActual,
    auditor: Auditor,
) -> PruebaJev:
    """Llama a JEV con un mensaje sintetico, sin datos de pacientes."""
    clinica_id = principal.clinica_id
    if clinica_id is None:
        raise RecursoNoEncontrado("La sesion no tiene una clinica asociada.")
    integ = await leer_integracion(sesion, clinica_id, "typesafe")
    clave = descifrar(cifrador, clinica_id, "typesafe", "api_key", integ) if integ else None
    if integ is None or not clave:
        raise DatosInvalidos("Guarde primero la clave API de JEV.")
    limite = float(integ.ajustes.get("tiempo_limite") or 3.0)
    inicio = time.perf_counter()
    async with httpx.AsyncClient(timeout=limite) as cliente:
        decision = await ClasificadorJev(
            clave=clave, modelo=str(integ.ajustes.get("modelo") or "jev-latest"), cliente=cliente
        ).clasificar(MENSAJE_PRUEBA)
    milisegundos = int((time.perf_counter() - inicio) * 1000)
    respondio = decision.proveedor == "jev"
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.INTEGRACION_PROBADA,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="integracion",
                entidad_id=None,
                integracion="typesafe",
                respondio=respondio,
            )
        ]
    )
    await sesion.commit()
    return PruebaJev(
        respondio=respondio,
        mensaje=(
            "JEV respondio correctamente."
            if respondio
            else "JEV no respondio: revise la clave o la conexion. Mientras tanto el agente usa "
            "las reglas locales."
        ),
        intencion=decision.intencion.value,
        confianza=round(decision.confianza, 3),
        pregunta_clinica=round(decision.pregunta_clinica, 3),
        urgencia=round(decision.urgencia, 3),
        milisegundos=milisegundos,
    )


__all__ = ["enrutador"]
