"""Traduccion de errores de PostgreSQL a errores de dominio.

Por que existe este modulo
--------------------------
La integridad de este sistema se apoya en garantias del motor de base de
datos: restricciones de exclusion, indices unicos parciales y comprobaciones
`CHECK` (ADR-0009).  Eso significa que **una parte del flujo normal llega
como excepcion de base de datos**, no como una comprobacion previa.

Cuando dos pacientes compiten por el mismo turno, el que pierde no recibe un
resultado, recibe un `IntegrityError`.  Si ese error se deja escapar, el
paciente ve un 500 en lugar de «ese turno ya no esta disponible», y el
registro se llena de errores que parecen fallos del sistema sin serlo.

El interbloqueo
---------------
Las pruebas de concurrencia con 50 participantes simultaneos revelaron algo
que no es obvio: **no todos los rechazos llegan como violacion de la
restriccion de exclusion.**  Una parte llega como interbloqueo (SQLSTATE
40P01).

Ocurre porque la segunda transaccion que inserta una fila solapada queda
esperando a que la primera confirme o deshaga; si varias se esperan en
circulo, PostgreSQL aborta una de ellas.  La integridad se mantiene, pero el
codigo de error es distinto.

Tratar solo el 23P01 dejaria una fraccion de las reservas concurrentes
devolviendo un 500 bajo carga: el fallo que menos se detecta en desarrollo,
porque solo aparece cuando hay competencia real.
"""

from __future__ import annotations

from typing import Final

from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError

from app.nucleo.errores import (
    ClaveIdempotenciaConflictiva,
    ConflictoEstado,
    ErrorDominio,
    ReglaNegocioViolada,
    TurnoNoDisponible,
)

# ---------------------------------------------------------------------------
#  Codigos SQLSTATE relevantes
# ---------------------------------------------------------------------------
SQLSTATE_VIOLACION_EXCLUSION: Final = "23P01"
SQLSTATE_VIOLACION_UNICIDAD: Final = "23505"
SQLSTATE_VIOLACION_CHECK: Final = "23514"
SQLSTATE_VIOLACION_CLAVE_EXTERNA: Final = "23503"
SQLSTATE_VIOLACION_NO_NULO: Final = "23502"
SQLSTATE_INTERBLOQUEO: Final = "40P01"
SQLSTATE_FALLO_SERIALIZACION: Final = "40001"

# Errores que significan «otro llego antes» y que merecen reintentarse una
# vez antes de devolver un conflicto.  Un reintento resuelve el caso en que
# el conflicto era transitorio (el competidor deshizo su transaccion), y su
# coste es una sola operacion mas.
SQLSTATES_REINTENTABLES: Final[frozenset[str]] = frozenset(
    {SQLSTATE_INTERBLOQUEO, SQLSTATE_FALLO_SERIALIZACION}
)

# Restricciones cuyo nombre determina el error de dominio.  Se mapean por
# nombre y no por codigo porque un mismo SQLSTATE cubre situaciones muy
# distintas: una violacion de unicidad puede ser una clave de idempotencia
# repetida o un correo duplicado, y el mensaje al usuario debe diferir.
_MENSAJES_POR_RESTRICCION: Final[dict[str, tuple[type[ErrorDominio], str]]] = {
    "cita_sin_solape_profesional": (
        TurnoNoDisponible,
        "Ese horario ya no esta disponible con el profesional seleccionado.",
    ),
    "cita_sin_solape_consultorio": (
        TurnoNoDisponible,
        "El consultorio ya esta ocupado en ese horario.",
    ),
    "ix_cita_idempotencia": (
        ClaveIdempotenciaConflictiva,
        "Esta solicitud ya fue procesada.",
    ),
    "uq_outbox_mensaje_clave_deduplicacion": (
        ConflictoEstado,
        "Este mensaje ya estaba registrado para envio.",
    ),
    "oferta_una_activa_por_slot": (
        ConflictoEstado,
        "Ese turno ya fue ofrecido a otra persona.",
    ),
    "uq_usuario_clinica_id_correo": (
        ReglaNegocioViolada,
        "Ya existe un usuario con ese correo en la clinica.",
    ),
    "ix_paciente_documento": (
        ReglaNegocioViolada,
        "Ya existe un paciente con ese documento de identidad.",
    ),
    "held_exige_expiracion": (
        ReglaNegocioViolada,
        "Un bloqueo temporal necesita una fecha de expiracion.",
    ),
    "cancelacion_exige_motivo": (
        ReglaNegocioViolada,
        "Para cancelar hay que indicar el motivo.",
    ),
    "duracion_positiva": (
        ReglaNegocioViolada,
        "La duracion de la cita debe ser mayor que cero.",
    ),
    "fin_posterior_al_inicio": (
        ReglaNegocioViolada,
        "La hora de fin debe ser posterior a la de inicio.",
    ),
    # Regla de seguridad clinica: un medicamento «cuando sea necesario» no
    # puede llevar horarios fijos.
    "ck_receta_item_prn_sin_horarios": (
        ReglaNegocioViolada,
        "Un medicamento indicado 'cuando sea necesario' no admite horarios "
        "fijos. Requiere confirmacion del profesional.",
    ),
}


def extraer_sqlstate(excepcion: BaseException) -> str | None:
    """Devuelve el SQLSTATE de una excepcion de base de datos, si lo tiene.

    Se consulta tanto la excepcion de SQLAlchemy como la original del driver:
    `asyncpg` la expone en `sqlstate` y `psycopg` en `pgcode`, y SQLAlchemy
    no siempre la propaga.
    """
    for candidato in (excepcion, getattr(excepcion, "orig", None)):
        if candidato is None:
            continue
        codigo = getattr(candidato, "sqlstate", None) or getattr(candidato, "pgcode", None)
        if codigo:
            return str(codigo)
    return None


def extraer_nombre_restriccion(excepcion: BaseException) -> str | None:
    """Devuelve el nombre de la restriccion violada.

    Los drivers lo exponen de formas distintas y no siempre lo exponen, asi
    que como ultimo recurso se busca en el texto del mensaje.  Buscar en el
    texto es fragil, pero el alternativo -- devolver un error genarico -- deja
    al usuario sin saber que corregir.
    """
    for candidato in (getattr(excepcion, "orig", None), excepcion):
        if candidato is None:
            continue
        nombre = getattr(candidato, "constraint_name", None)
        if nombre:
            return str(nombre)
        # asyncpg guarda los detalles en atributos propios.
        nombre = getattr(candidato, "constraint", None)
        if nombre:
            return str(nombre)

    texto = str(excepcion)
    for conocida in _MENSAJES_POR_RESTRICCION:
        if conocida in texto:
            return conocida
    return None


def es_reintentable(excepcion: BaseException) -> bool:
    """Indica si merece la pena reintentar la operacion una vez.

    Solo el interbloqueo y el fallo de serializacion: son conflictos
    transitorios entre transacciones, no errores de los datos.  Reintentar una
    violacion de unicidad seria inutil, porque el estado que la provoca no va
    a cambiar.
    """
    codigo = extraer_sqlstate(excepcion)
    return codigo in SQLSTATES_REINTENTABLES


def traducir(excepcion: SQLAlchemyError) -> ErrorDominio | None:
    """Traduce un error de base de datos a un error de dominio.

    Devuelve `None` si la excepcion no corresponde a una garantia conocida.
    En ese caso el llamante debe propagarla: un error inesperado de base de
    datos es un fallo real y convertirlo en un mensaje amable lo ocultaria.
    """
    codigo = extraer_sqlstate(excepcion)
    if codigo is None:
        return None

    nombre = extraer_nombre_restriccion(excepcion)

    # 1. Por nombre de restriccion: el caso mas informativo.
    if nombre and nombre in _MENSAJES_POR_RESTRICCION:
        clase, mensaje = _MENSAJES_POR_RESTRICCION[nombre]
        return clase(mensaje, detalles={"restriccion": nombre})

    # 2. Interbloqueo y fallo de serializacion.
    #
    #    Se traducen a `TurnoNoDisponible` porque, en este sistema, la unica
    #    fuente realista de interbloqueo es la competencia por el mismo turno:
    #    es la consecuencia directa de la restriccion de exclusion sobre
    #    `cita.rango`.  Devolver un error tecnico al paciente por algo que
    #    significa «alguien llego antes» seria incorrecto.
    if codigo in SQLSTATES_REINTENTABLES:
        return TurnoNoDisponible(
            "Ese horario acaba de ser ocupado. Elija otro, por favor.",
            detalles={"sqlstate": codigo, "reintentable": True},
        )

    # 3. Por codigo, sin nombre de restriccion reconocible.
    return _traducir_por_codigo(codigo, nombre)


def _traducir_por_codigo(codigo: str, nombre: str | None) -> ErrorDominio | None:
    """Traduccion de respaldo cuando no se reconoce la restriccion.

    Los mensajes son necesariamente genericos: sin saber cual se violo no se
    puede decir al usuario que corregir.  Se incluye el SQLSTATE en los
    detalles para que el registro permita diagnosticarlo.
    """
    if codigo == SQLSTATE_VIOLACION_EXCLUSION:
        return TurnoNoDisponible(
            "Ese horario ya no esta disponible.",
            detalles={"sqlstate": codigo},
        )
    if codigo == SQLSTATE_VIOLACION_UNICIDAD:
        return ConflictoEstado(
            "El registro que intenta crear ya existe.",
            detalles={"sqlstate": codigo, "restriccion": nombre},
        )
    if codigo in (
        SQLSTATE_VIOLACION_CHECK,
        SQLSTATE_VIOLACION_NO_NULO,
        SQLSTATE_VIOLACION_CLAVE_EXTERNA,
    ):
        return ReglaNegocioViolada(
            "Los datos enviados no cumplen una regla del sistema.",
            detalles={"sqlstate": codigo, "restriccion": nombre},
        )
    return None


def traducir_o_propagar(excepcion: SQLAlchemyError) -> ErrorDominio:
    """Traduce, y si no reconoce el error, lo propaga.

    Es la forma que usan los servicios:

        try:
            ...
        except SQLAlchemyError as exc:
            raise traducir_o_propagar(exc) from exc

    Un error de base de datos que no corresponde a ninguna garantia conocida
    es un fallo real -- un problema de conexion, una tabla ausente, un error
    de programacion -- y debe llegar al registro como tal.  Convertirlo en un
    mensaje amable ocultaria averias.
    """
    traducido = traducir(excepcion)
    if traducido is not None:
        return traducido
    raise excepcion


__all__ = [
    "SQLSTATES_REINTENTABLES",
    "DBAPIError",
    "IntegrityError",
    "es_reintentable",
    "extraer_nombre_restriccion",
    "extraer_sqlstate",
    "traducir",
    "traducir_o_propagar",
]
