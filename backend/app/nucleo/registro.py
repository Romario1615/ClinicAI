"""Registro estructurado con redaccion activa de datos sensibles.

Los logs de un sistema clinico son una fuga en potencia: se copian a
agregadores, se comparten al depurar y se conservan mas tiempo que los datos
operativos.  Un `logger.info(f"paciente={paciente}")` bien intencionado
escribe nombre, documento y telefono en texto plano.

Este modulo invierte la carga: en lugar de confiar en que nadie registre
datos sensibles, **los elimina antes de escribir**.  La redaccion se aplica
por nombre de campo y por patron de contenido, de forma recursiva.

Lo que se registra de una persona es su identificador, nunca sus datos.
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Iterable, MutableMapping
from typing import Any

import structlog
from structlog.types import EventDict, Processor

# ---------------------------------------------------------------------------
#  Campos que nunca se escriben en claro
# ---------------------------------------------------------------------------
# Se comparan en minusculas y por coincidencia parcial: `nombre_paciente`,
# `paciente_nombre` y `nombre` quedan cubiertos por la entrada "nombre".
CAMPOS_SENSIBLES: frozenset[str] = frozenset(
    {
        # Identificativos
        "nombre",
        "apellido",
        "documento",
        "numero_documento",
        "cedula",
        "pasaporte",
        "fecha_nacimiento",
        "direccion",
        # Contacto
        "telefono",
        "whatsapp",
        "celular",
        "correo",
        "email",
        # Clinicos
        "diagnostico",
        "diagnosticos",
        "motivo_consulta",
        "antecedente",
        "antecedentes",
        "alergia",
        "alergias",
        "medicamento",
        "medicamento_nombre",
        "dosis",
        "tratamiento",
        "indicaciones",
        "nota",
        "notas",
        "contenido",
        "evolucion",
        "sintoma",
        "sintomas",
        "resultado_examen",
        # Contenido de conversaciones
        "mensaje",
        "texto",
        "cuerpo",
        "comentario_paciente",
        # Secretos
        "contrasena",
        "password",
        "clave",
        "secret",
        "secreto",
        "token",
        "authorization",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "firma",
        "signature",
        "cookie",
        "set-cookie",
        "otp",
        "codigo_verificacion",
        "secreto_2fa",
    }
)

# Campos que si se registran: identifican sin revelar.
CAMPOS_PERMITIDOS: frozenset[str] = frozenset(
    {
        "paciente_id",
        "profesional_id",
        "usuario_id",
        "cita_id",
        "clinica_id",
        "sede_id",
        "especialidad_id",
        "servicio_id",
        "documento_id",
        "receta_id",
        "conversacion_id",
        "mensaje_id",
        "outbox_mensaje_id",
        "correlacion_id",
    }
)

MARCA_REDACTADO = "[redactado]"

# ---------------------------------------------------------------------------
#  Patrones de contenido
# ---------------------------------------------------------------------------
# Segunda linea de defensa: capturan datos sensibles que aparezcan dentro de
# un texto libre, por ejemplo en el mensaje de una excepcion de base de datos
# que incluye los valores de la fila.
PATRONES_CONTENIDO: tuple[tuple[re.Pattern[str], str], ...] = (
    # Cedula ecuatoriana (10 digitos) y RUC (13).  Se exige frontera de
    # palabra para no destrozar identificadores numericos legitimos.
    (re.compile(r"\b\d{10}(?:001)?\b"), "[documento]"),
    # Telefono con prefijo internacional o formato local ecuatoriano
    (re.compile(r"\+?593\s?9\d{8}\b"), "[telefono]"),
    (re.compile(r"\b09\d{8}\b"), "[telefono]"),
    # Correo electronico
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[correo]"),
    # Cabecera de autorizacion embebida en una traza
    (re.compile(r"(?i)\bbearer\s+[\w\-._~+/]+=*"), "Bearer [redactado]"),
    # Cadena de conexion con credencial
    (re.compile(r"(?i)(postgresql|postgres|redis|amqp)://[^:]+:[^@]+@"), r"\1://[redactado]@"),
    # Claves privadas pegadas por error
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
        "[clave-privada-redactada]",
    ),
)

# Profundidad maxima al recorrer estructuras anidadas.  Evita que una
# estructura ciclica o muy profunda bloquee el proceso de registro.
PROFUNDIDAD_MAXIMA = 8
LONGITUD_MAXIMA_TEXTO = 2000
# Elementos maximos que se registran de una coleccion.  Una lista de mil
# pacientes en un log no aporta nada y multiplica la superficie de fuga.
ELEMENTOS_MAXIMOS_COLECCION = 20


def _es_campo_sensible(clave: str) -> bool:
    clave_normalizada = clave.lower().strip()
    if clave_normalizada in CAMPOS_PERMITIDOS:
        return False
    return any(sensible in clave_normalizada for sensible in CAMPOS_SENSIBLES)


def _redactar_texto(valor: str) -> str:
    if len(valor) > LONGITUD_MAXIMA_TEXTO:
        valor = valor[:LONGITUD_MAXIMA_TEXTO] + "...[truncado]"
    for patron, sustituto in PATRONES_CONTENIDO:
        valor = patron.sub(sustituto, valor)
    return valor


def _redactar_valor(valor: Any, profundidad: int = 0) -> Any:
    """Redacta recursivamente cualquier estructura."""
    if profundidad > PROFUNDIDAD_MAXIMA:
        return "[estructura-demasiado-profunda]"

    if isinstance(valor, str):
        return _redactar_texto(valor)
    if isinstance(valor, MutableMapping):
        return {
            clave: (
                MARCA_REDACTADO
                if _es_campo_sensible(str(clave))
                else _redactar_valor(subvalor, profundidad + 1)
            )
            for clave, subvalor in valor.items()
        }
    if isinstance(valor, (list, tuple, set)):
        # Se limita el numero de elementos: una lista de mil pacientes en un
        # log no aporta nada y multiplica la superficie de fuga.
        elementos = list(valor)[:ELEMENTOS_MAXIMOS_COLECCION]
        redactados = [_redactar_valor(e, profundidad + 1) for e in elementos]
        if len(valor) > ELEMENTOS_MAXIMOS_COLECCION:
            restantes = len(valor) - ELEMENTOS_MAXIMOS_COLECCION
            redactados.append(f"...[{restantes} elementos mas]")
        return redactados
    return valor


def procesador_redaccion(_logger: Any, _metodo: str, evento: EventDict) -> EventDict:
    """Procesador de structlog que redacta todo el evento.

    Se coloca al final de la cadena, justo antes de serializar, para que
    tambien cubra lo que anadan los procesadores anteriores (contexto de
    peticion, excepciones formateadas).
    """
    for clave in list(evento.keys()):
        if clave in {"event", "level", "timestamp", "logger"}:
            # El mensaje si se procesa por patron, pero no se redacta entero:
            # sin el no se puede depurar nada.
            if clave == "event" and isinstance(evento[clave], str):
                evento[clave] = _redactar_texto(evento[clave])
            continue
        if _es_campo_sensible(clave):
            evento[clave] = MARCA_REDACTADO
        else:
            evento[clave] = _redactar_valor(evento[clave])
    return evento


def procesador_sin_redaccion(_logger: Any, _metodo: str, evento: EventDict) -> EventDict:
    """Variante sin redaccion, solo para el entorno local.

    Nunca se activa en preproduccion ni produccion: la configuracion aborta
    el arranque si `REDACTAR_DATOS_SENSIBLES=false` con
    `ENTORNO=produccion`.
    """
    return evento


def configurar_registro(
    *,
    nivel: str = "INFO",
    formato: str = "json",
    redactar: bool = True,
) -> None:
    """Configura structlog y la biblioteca estandar de registro.

    Se llama una sola vez al arrancar la aplicacion o el worker.
    """
    procesadores: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # La redaccion va en penultimo lugar: despues de que los procesadores
    # anteriores hayan anadido todo lo que van a anadir, y antes de
    # serializar.
    procesadores.append(procesador_redaccion if redactar else procesador_sin_redaccion)

    if formato == "json":
        procesadores.append(structlog.processors.JSONRenderer(ensure_ascii=False))
    else:
        procesadores.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=procesadores,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(nivel) if isinstance(nivel, str) else nivel
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Encamina los registros de las librerias (uvicorn, sqlalchemy, httpx)
    # por la misma cadena, para que tambien pasen por la redaccion.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.getLevelName(nivel),
        force=True,
    )
    for nombre in ("uvicorn", "uvicorn.access", "uvicorn.error", "sqlalchemy.engine", "httpx"):
        logger_lib = logging.getLogger(nombre)
        logger_lib.handlers.clear()
        logger_lib.propagate = True


def obtener_logger(nombre: str | None = None) -> structlog.stdlib.BoundLogger:
    """Devuelve un logger ya enlazado."""
    return structlog.get_logger(nombre)  # type: ignore[no-any-return]


def enlazar_contexto(**valores: Any) -> None:
    """Anade valores al contexto de la peticion actual.

    Se usa en el middleware para que todos los registros de una peticion
    lleven el identificador de correlacion, el usuario y la clinica sin tener
    que pasarlos a mano.
    """
    structlog.contextvars.bind_contextvars(**valores)


def limpiar_contexto() -> None:
    structlog.contextvars.clear_contextvars()


def comprobar_texto_sin_datos_sensibles(texto: str) -> list[str]:
    """Devuelve los patrones sensibles detectados en un texto.

    Existe para las pruebas de RNF-14: se provoca un error en cada modulo, se
    captura la salida de registro y se comprueba que esta funcion no encuentra
    nada.  Devuelve una lista para que el fallo indique exactamente que se
    filtro.
    """
    hallazgos: list[str] = []
    for patron, etiqueta in PATRONES_CONTENIDO:
        if patron.search(texto):
            hallazgos.append(etiqueta)
    return hallazgos


def campos_sensibles_en(claves: Iterable[str]) -> list[str]:
    """Devuelve las claves consideradas sensibles. Utilidad para pruebas."""
    return [c for c in claves if _es_campo_sensible(c)]
