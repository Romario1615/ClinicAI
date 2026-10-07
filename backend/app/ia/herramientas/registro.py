"""El registro de herramientas y el despachador que las ejecuta.

El catalogo es cerrado
----------------------
Ocho herramientas, fijadas por la especificacion.  No hay carga dinamica, no
hay descubrimiento por modulo, no hay forma de anadir una en tiempo de
ejecucion.  Un catalogo que se puede ampliar desde fuera es un catalogo que un
dia contendra algo que nadie reviso, y aqui lo que se revisa es precisamente
que el agente no pueda tocar contenido clinico (CLAUDE.md, regla 5).

Que garantiza el despachador
----------------------------
Toda invocacion pasa por `despachar`, y ahi ocurren cuatro cosas en este
orden:

1. **Se resuelve el nombre contra el catalogo.**  Un nombre que no esta se
   deniega y se audita.  Un modelo puede inventarse `delete_patient`; lo que
   no puede es que exista.
2. **Se validan los argumentos contra el esquema** de la herramienta.  Los
   esquemas no tienen campos de identidad, asi que por aqui no entra un
   `clinica_id` elegido por el modelo.
3. **Se comprueba el permiso** antes de ejecutar.  La capa de servicios lo
   vuelve a comprobar -- es ella la autoridad --, pero fallar aqui produce una
   denegacion auditada con el nombre de la herramienta, que es lo que despues
   se puede investigar.
4. **Se audita el resultado**, sea cual sea.  Exito, denegacion y error
   producen entrada.  `HERRAMIENTA_DENEGADA` esta ademas en la lista de
   acciones que generan alerta.

Sobre la traduccion de errores
------------------------------
Los errores de dominio se convierten en un `ResultadoHerramienta` con texto
apto para el paciente.  Lo que **nunca** sale de aqui es el mensaje interno de
una excepcion inesperada: puede contener nombres de tabla, identificadores o
fragmentos de consulta, y en un canal conversacional eso va directo a alguien
de fuera.  Lo inesperado se registra completo y al paciente se le deriva.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import ValidationError

from app.ia.herramientas.agenda import HERRAMIENTAS_AGENDA
from app.ia.herramientas.contrato import (
    ContextoHerramienta,
    Herramienta,
    ResultadoHerramienta,
)
from app.ia.herramientas.derivacion import HERRAMIENTA_DERIVACION
from app.ia.herramientas.limites import MotivoDerivacion, explicar
from app.ia.herramientas.pagos import HERRAMIENTAS_PAGOS
from app.modulos.auditoria.repositorio import RepositorioAuditoria
from app.nucleo.auditoria import (
    AccionAuditada,
    EntradaAuditoria,
    ResultadoAuditoria,
)
from app.nucleo.errores import (
    BloqueoExpirado,
    ConflictoEstado,
    ErrorDominio,
    PermisoDenegado,
    PoliticaCancelacionViolada,
    RecursoNoEncontrado,
    TurnoNoDisponible,
)
from app.nucleo.registro import obtener_logger

logger = obtener_logger(__name__)


# El catalogo. Los nombres son los que fija la especificacion.
HERRAMIENTAS: Final[dict[str, Herramienta]] = {
    h.nombre: h for h in (*HERRAMIENTAS_AGENDA, *HERRAMIENTAS_PAGOS, HERRAMIENTA_DERIVACION)
}

# Se declara aparte y se compara en una prueba. Si alguien anade o quita una
# herramienta, la prueba falla y obliga a justificar el cambio en lugar de que
# pase inadvertido en una revision.
NOMBRES_ESPERADOS: Final[frozenset[str]] = frozenset(
    {
        "find_availability",
        "hold_slot",
        "confirm_appointment",
        "cancel_appointment",
        "reschedule_appointment",
        "get_patient_appointments",
        # Solo lectura: lo que el paciente debe. Anadida a peticion de la
        # clinica (pagos por WhatsApp); no registra ni cobra nada.
        "get_patient_payments",
        "handoff_to_human",
    }
)


def catalogo_para_modelo() -> list[dict[str, Any]]:
    """Descripcion de las herramientas en la forma que espera un LLM."""
    return [
        {
            "name": h.nombre,
            "description": h.descripcion,
            "input_schema": h.argumentos.model_json_schema(),
        }
        for h in HERRAMIENTAS.values()
    ]


async def despachar(
    nombre: str,
    argumentos_crudos: dict[str, Any],
    contexto: ContextoHerramienta,
) -> ResultadoHerramienta:
    """Ejecuta una herramienta por nombre, con auditoria pase lo que pase.

    `argumentos_crudos` viene del modelo y se trata como entrada no fiable:
    se valida contra el esquema y nada mas se usa de el.
    """
    herramienta = HERRAMIENTAS.get(nombre)
    if herramienta is None:
        await _auditar(
            contexto,
            AccionAuditada.HERRAMIENTA_DENEGADA,
            ResultadoAuditoria.DENEGADO,
            {"herramienta": nombre, "razon": "no_existe"},
        )
        logger.warning("agente.herramienta_inexistente", herramienta=nombre)
        return _derivar("NO_EXISTE")

    try:
        argumentos = herramienta.argumentos.model_validate(argumentos_crudos)
    except ValidationError as exc:
        # No se le devuelve al modelo el detalle completo: incluye los valores
        # que envio, y esos valores pueden ser datos de un paciente.
        await _auditar(
            contexto,
            AccionAuditada.HERRAMIENTA_DENEGADA,
            ResultadoAuditoria.DENEGADO,
            {"herramienta": nombre, "razon": "argumentos_invalidos"},
        )
        logger.info(
            "agente.argumentos_invalidos",
            herramienta=nombre,
            errores=[e["loc"] for e in exc.errors()],
        )
        return _derivar("ARGUMENTOS_INVALIDOS")

    if herramienta.permiso is not None and not contexto.principal.tiene_permiso(
        herramienta.permiso
    ):
        await _auditar(
            contexto,
            AccionAuditada.HERRAMIENTA_DENEGADA,
            ResultadoAuditoria.DENEGADO,
            {"herramienta": nombre, "razon": "sin_permiso", "permiso": herramienta.permiso},
        )
        return _derivar("SIN_PERMISO")

    try:
        resultado = await herramienta.ejecutar(argumentos, contexto)
    except ErrorDominio as exc:
        await _auditar(
            contexto,
            AccionAuditada.HERRAMIENTA_INVOCADA,
            ResultadoAuditoria.ERROR,
            {"herramienta": nombre, "codigo": exc.codigo},
        )
        return _traducir(exc)
    except Exception:
        # Inesperado. Se registra entero para poder investigarlo y al paciente
        # se le pasa con una persona: es la unica respuesta honesta cuando el
        # sistema no sabe que ha pasado.
        logger.exception("agente.herramienta_error_inesperado", herramienta=nombre)
        await _auditar(
            contexto,
            AccionAuditada.HERRAMIENTA_INVOCADA,
            ResultadoAuditoria.ERROR,
            {"herramienta": nombre, "razon": "error_inesperado"},
        )
        return _derivar("ERROR_INTERNO")

    await _auditar(
        contexto,
        AccionAuditada.HERRAMIENTA_INVOCADA,
        ResultadoAuditoria.EXITO if resultado.exito else ResultadoAuditoria.ERROR,
        {"herramienta": nombre, "codigo": resultado.codigo or "OK"},
    )
    return resultado


# ---------------------------------------------------------------------------
#  Traduccion de errores a lenguaje de paciente
# ---------------------------------------------------------------------------
# Cada uno dice que paso y que puede hacer la persona a continuacion. Un
# «error 409» no es una respuesta.
_MENSAJES: Final[dict[type[ErrorDominio], str]] = {
    TurnoNoDisponible: (
        "Ese horario acaba de ocuparse. Puedo buscarle otro, digame que dia le viene bien."
    ),
    BloqueoExpirado: (
        "Se agoto el tiempo para confirmar ese horario. Volvemos a mirar la disponibilidad."
    ),
    RecursoNoEncontrado: (
        "No encuentro esa cita a su nombre. Le paso con el personal de la clinica."
    ),
    PermisoDenegado: ("No puedo hacer esa gestion. Le paso con el personal de la clinica."),
    PoliticaCancelacionViolada: (
        "Falta muy poco para su cita y no puedo cancelarla yo. "
        "Le paso con el personal de la clinica."
    ),
    ConflictoEstado: (
        "Esa cita ya no esta en un estado que yo pueda cambiar. "
        "Le paso con el personal de la clinica."
    ),
}


def _traducir(error: ErrorDominio) -> ResultadoHerramienta:
    """Convierte un error de dominio en algo que se le puede leer al paciente."""
    for tipo, texto in _MENSAJES.items():
        if isinstance(error, tipo):
            # Solo los que ofrecen una alternativa dentro del agente se quedan
            # en el agente. El resto sale a una persona.
            requiere_humano = tipo not in (TurnoNoDisponible, BloqueoExpirado)
            return ResultadoHerramienta(
                exito=False,
                mensaje=texto,
                requiere_humano=requiere_humano,
                codigo=error.codigo,
            )
    return _derivar(error.codigo)


def _derivar(codigo: str) -> ResultadoHerramienta:
    """Resultado que manda la conversacion a una persona."""
    return ResultadoHerramienta(
        exito=False,
        mensaje=explicar(MotivoDerivacion.NO_COMPRENDIDO),
        requiere_humano=True,
        codigo=codigo,
    )


async def _auditar(
    contexto: ContextoHerramienta,
    accion: AccionAuditada,
    resultado: ResultadoAuditoria,
    metadatos: dict[str, Any],
) -> None:
    """Escribe la entrada de auditoria. No confirma la transaccion.

    El limite transaccional lo decide quien orquesta, igual que en el resto
    del sistema: la auditoria de una operacion tiene que confirmarse con la
    operacion o no confirmarse.
    """
    entrada = EntradaAuditoria(
        accion=accion,
        actor_tipo=contexto.principal.actor_tipo,
        actor_id=contexto.principal.actor_id,
        resultado=resultado,
        ocurrido_en=contexto.reloj.ahora(),
        entidad_tipo="conversacion" if contexto.conversacion_id else None,
        entidad_id=contexto.conversacion_id,
        clinica_id=contexto.principal.clinica_id,
        paciente_id=contexto.principal.paciente_id,
        origen=contexto.principal.origen,
        correlacion_id=contexto.correlacion_id,
        metadatos=metadatos,
    )
    await RepositorioAuditoria(contexto.sesion).registrar([entrada])


def herramienta(nombre: str) -> Herramienta | None:
    """Acceso de solo lectura al catalogo, para las pruebas y el orquestador."""
    return HERRAMIENTAS.get(nombre)


def identificadores_declarados(esquema: dict[str, Any]) -> set[str]:
    """Campos del esquema que parecen identidad.

    Lo usa la prueba que verifica que ningun esquema de argumentos permite al
    modelo elegir sobre que clinica o con que permisos opera.
    """
    prohibidos = {"clinica_id", "actor_id", "permisos", "ambito", "principal", "rol", "roles"}
    return set(esquema.get("properties", {})) & prohibidos


__all__ = [
    "HERRAMIENTAS",
    "NOMBRES_ESPERADOS",
    "catalogo_para_modelo",
    "despachar",
    "herramienta",
    "identificadores_declarados",
]
