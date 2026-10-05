"""Auditoria de acciones y de accesos a datos clinicos.

En un sistema clinico la auditoria no es un registro de depuracion: es la
prueba de quien accedio a la historia de un paciente y cuando.  De ahi tres
propiedades:

* **Se auditan tambien las lecturas.**  Lo habitual es auditar solo
  escrituras, pero la pregunta que importa ante una queja de privacidad es
  «quien vio esto», no «quien lo cambio».

* **Es append-only.**  El rol de base de datos de la aplicacion no tiene
  privilegio de `UPDATE` ni `DELETE` sobre la tabla.  Se aplica en la
  migracion, no por convencion: una convencion se rompe con un `merge`
  descuidado.

* **No guarda datos clinicos.**  Registra que se accedio al recurso X del
  paciente Y, no el contenido.  Si la auditoria guardara el contenido, se
  convertiria en una segunda copia sin las mismas restricciones de acceso, y
  en la mayor fuga del sistema.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.nucleo.autorizacion import NivelSensibilidad, Principal, TipoActor


class AccionAuditada(StrEnum):
    """Catalogo cerrado de acciones auditables.

    Cerrado a proposito: una cadena libre acaba con veinte variantes de la
    misma accion y hace imposible consultar la auditoria de forma fiable.
    """

    # --- Autenticacion ---
    LOGIN_EXITOSO = "login.exitoso"
    LOGIN_ROL_LOCAL = "login.rol_local"
    LOGIN_FALLIDO = "login.fallido"
    # Sigue la convencion recurso.accion igual que el resto del catalogo: un
    # codigo sin punto rompe las consultas de auditoria que agrupan por
    # recurso.
    LOGOUT = "sesion.cerrada"
    TOKEN_REFRESCADO = "token.refrescado"
    TOKEN_REUTILIZADO = "token.reutilizado"
    SESIONES_REVOCADAS = "sesiones.revocadas"
    CUENTA_BLOQUEADA = "cuenta.bloqueada"
    CONTRASENA_CAMBIADA = "contrasena.cambiada"
    CONTRASENA_RECUPERADA = "contrasena.recuperada"
    SEGUNDO_FACTOR_ACTIVADO = "2fa.activado"
    SEGUNDO_FACTOR_FALLIDO = "2fa.fallido"

    # --- Usuarios y permisos ---
    USUARIO_CREADO = "usuario.creado"
    USUARIO_MODIFICADO = "usuario.modificado"
    USUARIO_DESACTIVADO = "usuario.desactivado"
    ROL_ASIGNADO = "rol.asignado"
    ROL_REVOCADO = "rol.revocado"
    ROL_CREADO = "rol.creado"
    AMBITO_MODIFICADO = "ambito.modificado"
    PERMISO_DENEGADO = "permiso.denegado"
    INTEGRACION_CONFIGURADA = "integracion.configurada"
    CLINICA_CREADA = "clinica.creada"
    CLINICA_MODIFICADA = "clinica.modificada"
    SEDE_CREADA = "sede.creada"
    DASHBOARD_ANALISIS_IA = "dashboard.analisis_ia"

    # --- Pacientes ---
    PACIENTE_CREADO = "paciente.creado"
    PACIENTE_MODIFICADO = "paciente.modificado"
    PACIENTE_CONSULTADO = "paciente.consultado"
    IDENTIDAD_VERIFICADA = "identidad.verificada"
    CONSENTIMIENTO_OTORGADO = "consentimiento.otorgado"
    CONSENTIMIENTO_REVOCADO = "consentimiento.revocado"

    # --- Historia clinica ---
    HISTORIA_CONSULTADA = "historia_clinica.consultada"
    RESUMEN_CLINICO_REDACTADO = "historia_clinica.resumen_redactado"
    INDICACION_PUBLICADA = "indicacion_postconsulta.publicada"
    INDICACION_LEIDA = "indicacion_postconsulta.leida"
    INDICACION_ACCESO_FALLIDO = "indicacion_postconsulta.acceso_fallido"
    INDICACION_ANULADA = "indicacion_postconsulta.anulada"
    NOTA_CREADA = "nota_evolucion.creada"
    NOTA_VERSIONADA = "nota_evolucion.versionada"
    NOTA_ANULADA = "nota_evolucion.anulada"
    DIAGNOSTICO_REGISTRADO = "diagnostico.registrado"
    ACCESO_EMERGENCIA = "acceso_emergencia.usado"
    ACCESO_SENSIBLE = "acceso_sensible.usado"

    # --- Imagenes clinicas y odontologia ---
    IMAGEN_CARGADA = "imagen_clinica.cargada"
    IMAGEN_CONSULTADA = "imagen_clinica.consultada"
    IMAGEN_ANULADA = "imagen_clinica.anulada"
    FOTO_PERFIL_ACTUALIZADA = "paciente.foto_actualizada"
    ODONTOGRAMA_CONSULTADO = "odontograma.consultado"
    ODONTOGRAMA_VERSIONADO = "odontograma.versionado"
    PLAN_CONSULTADO = "plan_tratamiento.consultado"
    PLAN_CREADO = "plan_tratamiento.creado"
    PLAN_MODIFICADO = "plan_tratamiento.modificado"
    PLAN_ESTADO_CAMBIADO = "plan_tratamiento.estado_cambiado"
    PROCEDIMIENTO_COMPLETADO = "procedimiento.completado"
    PROCEDIMIENTO_AGENDADO = "procedimiento.agendado"
    PLANTILLA_PLAN_CREADA = "plantilla_plan.creada"
    PLANTILLA_PLAN_RETIRADA = "plantilla_plan.retirada"
    DELEGACION_FIRMA_CREADA = "delegacion_firma.creada"
    DELEGACION_FIRMA_REVOCADA = "delegacion_firma.revocada"

    # --- Promociones ---
    AUTOMATIZACION_CAMBIADA = "automatizacion.cambiada"
    CAMPANA_CREADA = "campana.creada"
    CAMPANA_MODIFICADA = "campana.modificada"
    CAMPANA_IMAGEN = "campana.imagen_actualizada"
    CAMPANA_APROBADA = "campana.aprobada"
    CAMPANA_ENVIADA = "campana.enviada"
    CAMPANA_CANCELADA = "campana.cancelada"

    # --- Agenda ---
    CITA_CREADA = "cita.creada"
    CITA_BLOQUEADA = "cita.bloqueada"
    CITA_CONFIRMADA = "cita.confirmada"
    CITA_LLEGADA_REGISTRADA = "cita.llegada_registrada"
    CITA_ATENCION_INICIADA = "cita.atencion_iniciada"
    CITA_CANCELADA = "cita.cancelada"
    CITA_REPROGRAMADA = "cita.reprogramada"
    CITA_COMPLETADA = "cita.completada"
    CITA_INASISTENCIA = "cita.inasistencia"
    BLOQUEO_CREADO = "bloqueo.creado"
    DOBLE_RESERVA_EVITADA = "cita.doble_reserva_evitada"

    # --- Lista de espera ---
    LISTA_ESPERA_ALTA = "lista_espera.alta"
    SLOT_LIBERADO = "slot.liberado"
    OFERTA_ENVIADA = "oferta.enviada"
    OFERTA_ACEPTADA = "oferta.aceptada"
    OFERTA_RECHAZADA = "oferta.rechazada"
    OFERTA_PERDIDA = "oferta.perdida"
    OFERTA_EXPIRADA = "oferta.expirada"
    OFERTA_PERDIDA_CARRERA = "oferta.perdida_por_carrera"

    # --- Recetas ---
    RECETA_CREADA = "receta.creada"
    RECETA_CONFIRMADA = "receta.confirmada"
    RECETA_MODIFICADA = "receta.modificada"
    RECETA_SUSPENDIDA = "receta.suspendida"
    TOMAS_GENERADAS = "tomas.generadas"
    TOMAS_CANCELADAS = "tomas.canceladas"
    TOMA_REGISTRADA = "toma.registrada"
    ALERTA_ADHERENCIA_CREADA = "alerta_adherencia.creada"
    ALERTA_ADHERENCIA_ATENDIDA = "alerta_adherencia.atendida"
    CONTROL_TRATAMIENTO_ATENDIDO = "control_tratamiento.atendido"

    # --- Conocimiento y RAG ---
    DOCUMENTO_CARGADO = "documento.cargado"
    DOCUMENTO_APROBADO = "documento.aprobado"
    DOCUMENTO_PUBLICADO = "documento.publicado"
    DOCUMENTO_ARCHIVADO = "documento.archivado"
    DOCUMENTO_MARCADO_REVISION = "documento.marcado_para_revision"
    DOCUMENTO_ACL_ACTUALIZADA = "documento.acl_actualizada"
    CONSULTA_RAG = "rag.consulta"
    RAG_SIN_FUENTE = "rag.sin_fuente"
    INYECCION_DETECTADA = "seguridad.inyeccion_detectada"

    # --- Agente e integraciones ---
    HERRAMIENTA_INVOCADA = "agente.herramienta_invocada"
    HERRAMIENTA_DENEGADA = "agente.herramienta_denegada"
    DERIVACION_HUMANO = "agente.derivacion_humano"
    WEBHOOK_RECIBIDO = "webhook.recibido"
    WEBHOOK_FIRMA_INVALIDA = "webhook.firma_invalida"
    WEBHOOK_DUPLICADO = "webhook.duplicado"
    MENSAJE_ENVIADO = "mensaje.enviado"
    MENSAJE_FALLIDO = "mensaje.fallido"
    CONVERSACION_LEIDA = "conversacion.leida"
    CONVERSACION_CONSULTADA = "conversacion.consultada"
    CALENDARIO_CONECTADO = "calendario.conectado"
    CALENDARIO_DESCONECTADO = "calendario.desconectado"
    CALENDARIO_CONFLICTO = "calendario.conflicto"

    # --- Pagos ---
    PAGO_REGISTRADO = "pago.registrado"
    PAGO_VALIDADO = "pago.validado"
    PAGO_RECHAZADO = "pago.rechazado"

    # --- Analitica ---
    PREDICCION_CONSULTADA = "prediccion.consultada"
    REPORTE_EXPORTADO = "reporte.exportado"
    EXPORTACION_TITULAR = "exportacion.titular"


class ResultadoAuditoria(StrEnum):
    EXITO = "EXITO"
    DENEGADO = "DENEGADO"
    ERROR = "ERROR"


# Acciones que representan un hecho relevante para la seguridad y que deben
# generar alerta, no solo quedar registradas.  Detectarlas en una revision
# mensual llega tarde.
ACCIONES_CON_ALERTA: frozenset[AccionAuditada] = frozenset(
    {
        AccionAuditada.TOKEN_REUTILIZADO,
        AccionAuditada.ACCESO_EMERGENCIA,
        AccionAuditada.WEBHOOK_FIRMA_INVALIDA,
        AccionAuditada.INYECCION_DETECTADA,
        AccionAuditada.HERRAMIENTA_DENEGADA,
        AccionAuditada.EXPORTACION_TITULAR,
        AccionAuditada.AMBITO_MODIFICADO,
    }
)

# Claves de metadatos que nunca se admiten en la auditoria.  La auditoria
# registra referencias, no contenido clinico: si guardara el contenido, seria
# una segunda copia de la historia clinica sin sus restricciones de acceso.
CLAVES_PROHIBIDAS_METADATOS: frozenset[str] = frozenset(
    {
        "contenido",
        "nota",
        "notas",
        "diagnostico",
        "diagnosticos",
        "motivo_consulta",
        "medicamento",
        "medicamento_nombre",
        "dosis",
        "indicaciones",
        "antecedentes",
        "alergias",
        "mensaje",
        "texto",
        "contrasena",
        "token",
        "clave",
        "secreto",
    }
)


@dataclass(slots=True)
class EntradaAuditoria:
    """Una entrada de auditoria, ya validada y lista para persistir."""

    accion: AccionAuditada
    actor_tipo: TipoActor
    actor_id: uuid.UUID | None
    resultado: ResultadoAuditoria
    ocurrido_en: datetime
    entidad_tipo: str | None = None
    entidad_id: uuid.UUID | None = None
    clinica_id: uuid.UUID | None = None
    sede_id: uuid.UUID | None = None
    paciente_id: uuid.UUID | None = None
    nivel_sensibilidad: NivelSensibilidad | None = None
    ip: str | None = None
    origen: str = "API"
    correlacion_id: str | None = None
    metadatos: dict[str, Any] = field(default_factory=dict)
    motivo: str | None = None

    @property
    def requiere_alerta(self) -> bool:
        return self.accion in ACCIONES_CON_ALERTA


class ErrorMetadatosAuditoria(ValueError):
    """Se intento auditar contenido clinico o un secreto."""


def validar_metadatos(metadatos: dict[str, Any]) -> None:
    """Rechaza metadatos que contengan contenido clinico o secretos.

    Falla de forma explicita en lugar de redactar en silencio: si un
    desarrollador intenta auditar el contenido de una nota, el error le obliga
    a decidir que referencia registrar en su lugar.  Redactarlo sin avisar
    dejaria una auditoria incompleta y la impresion de que si se guardo.
    """
    prohibidas = [
        clave for clave in metadatos if any(p in clave.lower() for p in CLAVES_PROHIBIDAS_METADATOS)
    ]
    if prohibidas:
        raise ErrorMetadatosAuditoria(
            f"Los metadatos de auditoria no admiten estas claves: {sorted(prohibidas)}. "
            "La auditoria registra referencias (identificadores), no contenido "
            "clinico ni secretos. Registre el identificador del recurso."
        )


def construir_entrada(
    *,
    accion: AccionAuditada,
    principal: Principal,
    ahora: datetime,
    resultado: ResultadoAuditoria = ResultadoAuditoria.EXITO,
    entidad_tipo: str | None = None,
    entidad_id: uuid.UUID | None = None,
    sede_id: uuid.UUID | None = None,
    paciente_id: uuid.UUID | None = None,
    nivel_sensibilidad: NivelSensibilidad | None = None,
    ip: str | None = None,
    correlacion_id: str | None = None,
    motivo: str | None = None,
    **metadatos: Any,
) -> EntradaAuditoria:
    """Construye una entrada de auditoria a partir del principal.

    El actor se toma del principal, nunca de un parametro: si el actor fuera
    un argumento, un error de programacion podria atribuir una accion a otro
    usuario y dejar la auditoria mintiendo, que es peor que no tenerla.
    """
    validar_metadatos(metadatos)
    return EntradaAuditoria(
        accion=accion,
        actor_tipo=principal.actor_tipo,
        actor_id=principal.actor_id,
        resultado=resultado,
        ocurrido_en=ahora,
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        clinica_id=principal.clinica_id,
        sede_id=sede_id,
        paciente_id=paciente_id,
        nivel_sensibilidad=nivel_sensibilidad,
        ip=ip,
        origen=principal.origen,
        correlacion_id=correlacion_id,
        metadatos=metadatos,
        motivo=motivo,
    )
