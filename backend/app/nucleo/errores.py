"""Errores de dominio y su traduccion a respuestas HTTP.

Dos decisiones de diseno que afectan a la seguridad:

1. **Codigo estable en ingles, mensaje en espanol.**  El cliente programatico
   reacciona al codigo (`TURNO_NO_DISPONIBLE`), que no cambia nunca; la
   persona lee el mensaje.  Traducir el codigo romperia los clientes; dejar
   el mensaje en ingles dejaria a los usuarios sin entenderlo.

2. **Un recurso fuera de ambito devuelve 404, no 403.**  Un 403 confirmaria
   que el identificador existe, y eso permite enumerar pacientes probando
   identificadores.  El error `RecursoNoEncontrado` se usa tanto cuando el
   recurso no existe como cuando existe pero el solicitante no tiene alcance
   sobre el: desde fuera son indistinguibles, que es justo el objetivo.
"""

from __future__ import annotations

from typing import Any


class ErrorDominio(Exception):
    """Base de los errores de negocio.

    Un `ErrorDominio` es un resultado esperado, no un fallo del sistema: se
    traduce a una respuesta HTTP con su codigo y no se registra como
    excepcion no controlada.
    """

    codigo: str = "ERROR_DOMINIO"
    estado_http: int = 400

    def __init__(
        self,
        mensaje: str,
        *,
        detalles: dict[str, Any] | None = None,
        codigo: str | None = None,
    ) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.detalles = detalles or {}
        if codigo:
            self.codigo = codigo

    def a_dict(self) -> dict[str, Any]:
        cuerpo: dict[str, Any] = {"codigo": self.codigo, "mensaje": self.mensaje}
        if self.detalles:
            cuerpo["detalles"] = self.detalles
        return cuerpo


# ---------------------------------------------------------------------------
#  Autenticacion y autorizacion
# ---------------------------------------------------------------------------
class NoAutenticado(ErrorDominio):
    codigo = "NO_AUTENTICADO"
    estado_http = 401


class CredencialesInvalidas(ErrorDominio):
    """Credenciales incorrectas.

    El mensaje es deliberadamente igual tanto si el correo no existe como si
    la contrasena es incorrecta: distinguirlos permitiria enumerar cuentas.
    """

    codigo = "CREDENCIALES_INVALIDAS"
    estado_http = 401


class CuentaBloqueada(ErrorDominio):
    codigo = "CUENTA_BLOQUEADA"
    estado_http = 401


class SegundoFactorRequerido(ErrorDominio):
    """El rol exige segundo factor y la sesion no lo ha cumplido."""

    codigo = "SEGUNDO_FACTOR_REQUERIDO"
    estado_http = 403


class SegundoFactorInvalido(ErrorDominio):
    codigo = "SEGUNDO_FACTOR_INVALIDO"
    estado_http = 401


class TokenInvalido(ErrorDominio):
    codigo = "TOKEN_INVALIDO"
    estado_http = 401


class TokenRevocado(ErrorDominio):
    codigo = "TOKEN_REVOCADO"
    estado_http = 401


class PermisoDenegado(ErrorDominio):
    """El principal esta autenticado pero le falta el permiso.

    Se usa solo cuando negar la accion no revela la existencia de un recurso
    concreto.  Para recursos fuera de ambito se usa `RecursoNoEncontrado`.
    """

    codigo = "PERMISO_DENEGADO"
    estado_http = 403


class VerificacionAdicionalRequerida(ErrorDominio):
    """Se pide informacion clinica sin verificacion suficiente de identidad.

    Es el caso del paciente que escribe por WhatsApp: el numero de telefono
    no es identificacion suficiente para datos clinicos.
    """

    codigo = "VERIFICACION_ADICIONAL_REQUERIDA"
    estado_http = 403


class RelacionAsistencialRequerida(ErrorDominio):
    """Un profesional pide datos de un paciente con el que no tiene vinculo."""

    codigo = "RELACION_ASISTENCIAL_REQUERIDA"
    estado_http = 403


# ---------------------------------------------------------------------------
#  Recursos
# ---------------------------------------------------------------------------
class RecursoNoEncontrado(ErrorDominio):
    """El recurso no existe, o existe fuera del ambito del solicitante.

    Ambos casos devuelven lo mismo a proposito (proteccion contra IDOR por
    enumeracion).  El motivo real queda en la auditoria, no en la respuesta.
    """

    codigo = "RECURSO_NO_ENCONTRADO"
    estado_http = 404


class ConflictoEstado(ErrorDominio):
    codigo = "CONFLICTO_ESTADO"
    estado_http = 409


class ReglaNegocioViolada(ErrorDominio):
    codigo = "REGLA_NEGOCIO_VIOLADA"
    estado_http = 422


class DatosInvalidos(ErrorDominio):
    codigo = "DATOS_INVALIDOS"
    estado_http = 422


# ---------------------------------------------------------------------------
#  Agenda
# ---------------------------------------------------------------------------
class TurnoNoDisponible(ErrorDominio):
    """El turno se ocupo entre la consulta y el intento de reserva.

    Es el error que traduce una violacion de la restriccion de exclusion de
    PostgreSQL (ADR-0009).  No es un fallo: es el mecanismo normal de
    resolucion de la carrera entre dos pacientes.
    """

    codigo = "TURNO_NO_DISPONIBLE"
    estado_http = 409


class BloqueoExpirado(ErrorDominio):
    """El bloqueo temporal (HELD) vencio antes de confirmarse."""

    codigo = "BLOQUEO_EXPIRADO"
    estado_http = 409


class TransicionEstadoInvalida(ErrorDominio):
    codigo = "TRANSICION_ESTADO_INVALIDA"
    estado_http = 409


class FueraDeHorario(ErrorDominio):
    codigo = "FUERA_DE_HORARIO"
    estado_http = 422


class PoliticaCancelacionViolada(ErrorDominio):
    codigo = "POLITICA_CANCELACION_VIOLADA"
    estado_http = 422


# ---------------------------------------------------------------------------
#  Lista de espera
# ---------------------------------------------------------------------------
class OfertaExpirada(ErrorDominio):
    codigo = "OFERTA_EXPIRADA"
    estado_http = 409


class OfertaYaResuelta(ErrorDominio):
    """Otro paciente acepto primero.

    Es el resultado esperado cuando dos personas aceptan la misma oferta a la
    vez: uno gana y el otro recibe este error con un mensaje comprensible.
    """

    codigo = "OFERTA_YA_RESUELTA"
    estado_http = 409


# ---------------------------------------------------------------------------
#  Historia clinica y recetas
# ---------------------------------------------------------------------------
class MotivoModificacionRequerido(ErrorDominio):
    """Editar una nota clinica exige indicar por que."""

    codigo = "MOTIVO_MODIFICACION_REQUERIDO"
    estado_http = 422


class RecetaNoConfirmada(ErrorDominio):
    """Solo una receta confirmada por el profesional genera tomas."""

    codigo = "RECETA_NO_CONFIRMADA"
    estado_http = 409


class OperacionClinicaNoPermitida(ErrorDominio):
    """La operacion solicitada requiere decision de un profesional.

    Se usa cuando el agente de IA, o cualquier canal automatizado, intenta
    algo que solo puede decidir una persona con criterio clinico: cambiar una
    dosis, suspender medicacion o interpretar una reaccion adversa.  No es un
    permiso configurable: es un limite del sistema.
    """

    codigo = "OPERACION_CLINICA_NO_PERMITIDA"
    estado_http = 403


# ---------------------------------------------------------------------------
#  Conocimiento y RAG
# ---------------------------------------------------------------------------
class DocumentoNoAprobado(ErrorDominio):
    codigo = "DOCUMENTO_NO_APROBADO"
    estado_http = 409


class IngestaNoDisponible(ErrorDominio):
    """No se pudo completar la indexacion; el trabajo puede reintentarse."""

    codigo = "INGESTA_NO_DISPONIBLE"
    estado_http = 503


class SinFuenteAprobada(ErrorDominio):
    """No hay documento aprobado y vigente que responda la consulta.

    Provoca la respuesta honesta del agente y la oferta de derivar a una
    persona, en lugar de una respuesta inventada.
    """

    codigo = "SIN_FUENTE_APROBADA"
    estado_http = 200


class ArchivoNoPermitido(ErrorDominio):
    codigo = "ARCHIVO_NO_PERMITIDO"
    estado_http = 415


class ArchivoDemasiadoGrande(ErrorDominio):
    codigo = "ARCHIVO_DEMASIADO_GRANDE"
    estado_http = 413


class DestinoNoPermitido(ErrorDominio):
    """URL de ingesta fuera de la lista blanca (proteccion contra SSRF)."""

    codigo = "DESTINO_NO_PERMITIDO"
    estado_http = 400


# ---------------------------------------------------------------------------
#  Integraciones e infraestructura
# ---------------------------------------------------------------------------
class ClaveIdempotenciaConflictiva(ErrorDominio):
    """Misma clave de idempotencia con un cuerpo distinto."""

    codigo = "CLAVE_IDEMPOTENCIA_CONFLICTIVA"
    estado_http = 409


class LimiteTasaExcedido(ErrorDominio):
    codigo = "LIMITE_TASA_EXCEDIDO"
    estado_http = 429

    def __init__(self, mensaje: str, *, reintentar_en_segundos: int) -> None:
        super().__init__(mensaje, detalles={"reintentar_en_segundos": reintentar_en_segundos})
        self.reintentar_en_segundos = reintentar_en_segundos


class FirmaInvalida(ErrorDominio):
    """Webhook con firma HMAC que no valida."""

    codigo = "FIRMA_INVALIDA"
    estado_http = 403


class ProveedorExternoNoDisponible(ErrorDominio):
    """Fallo temporal de WhatsApp, del calendario o del proveedor de LLM.

    No cancela la operacion de negocio: se registra en el outbox y se
    reintenta.  Ver ADR-0008.
    """

    codigo = "PROVEEDOR_EXTERNO_NO_DISPONIBLE"
    estado_http = 503


class ConsentimientoRequerido(ErrorDominio):
    """Envio proactivo a un paciente que no dio consentimiento, o lo revoco."""

    codigo = "CONSENTIMIENTO_REQUERIDO"
    estado_http = 403
