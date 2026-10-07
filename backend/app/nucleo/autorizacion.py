"""Autorizacion: permisos, ambito y principal.

El modelo tiene **dos dimensiones que se evaluan siempre las dos**:

* **Permiso** — que accion: `cita.crear`, `historia_clinica.leer`.
* **Ambito** — sobre que datos: clinica, sede, especialidad, profesional,
  paciente y tipo de informacion.

Tener el permiso `historia_clinica.leer` no da acceso a todas las historias
clinicas: da acceso a las que caen dentro del ambito del principal y con las
que existe relacion asistencial.  Comprobar solo el permiso es el error que
convierte un sistema con roles en un sistema sin control de acceso real.

Tres reglas de diseno:

1. **Ambito vacio significa ningun acceso, no acceso total.**  El valor por
   defecto es el mas restrictivo.  Un `usuario_rol` al que se olvido asignar
   ambito no debe convertirse en superusuario por omision.

2. **Fuera de ambito se responde 404, nunca 403.**  Un 403 confirmaria que el
   identificador existe, y eso permite enumerar pacientes.

3. **El principal nunca se construye a partir de texto del usuario ni de la
   salida de un modelo de lenguaje.**  Se resuelve del token o del canal
   verificado.  Es lo que hace que una inyeccion de prompt no pueda escalar
   privilegios (ADR-0014).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final


class TipoAmbito(StrEnum):
    """Dimensiones sobre las que se puede limitar un permiso."""

    CLINICA = "CLINICA"
    SEDE = "SEDE"
    ESPECIALIDAD = "ESPECIALIDAD"
    PROFESIONAL = "PROFESIONAL"
    PACIENTE = "PACIENTE"
    TIPO_INFORMACION = "TIPO_INFORMACION"


class NivelSensibilidad(StrEnum):
    """Clasificacion de la informacion. Ver docs/security.md, seccion 1."""

    PUBLICO = "N0"
    ADMINISTRATIVO = "N1"
    CLINICO = "N2"
    CLINICO_SENSIBLE = "N3"

    @property
    def orden(self) -> int:
        return {"N0": 0, "N1": 1, "N2": 2, "N3": 3}[self.value]

    def cubre(self, otro: NivelSensibilidad) -> bool:
        """Indica si este nivel de acceso alcanza al nivel solicitado."""
        return self.orden >= otro.orden


class TipoActor(StrEnum):
    """Quien realiza la accion.

    `AGENTE_IA` existe como tipo propio para que la auditoria distinga lo que
    hizo una persona de lo que hizo el agente.  No otorga ningun privilegio:
    el agente opera con el ambito del solicitante.
    """

    USUARIO = "USUARIO"
    SISTEMA = "SISTEMA"
    AGENTE_IA = "AGENTE_IA"
    PACIENTE = "PACIENTE"


class NivelVerificacion(StrEnum):
    """Grado de certeza sobre la identidad de un paciente.

    Es la pieza que impide que un numero de WhatsApp de acceso a datos
    clinicos: un telefono puede ser familiar, prestado, robado o reasignado.
    """

    NO_VERIFICADO = "NO_VERIFICADO"
    TELEFONO = "TELEFONO"
    DOCUMENTO = "DOCUMENTO"
    PRESENCIAL = "PRESENCIAL"

    @property
    def orden(self) -> int:
        return {
            "NO_VERIFICADO": 0,
            "TELEFONO": 1,
            "DOCUMENTO": 2,
            "PRESENCIAL": 3,
        }[self.value]

    def alcanza(self, minimo: NivelVerificacion) -> bool:
        return self.orden >= minimo.orden


# ---------------------------------------------------------------------------
#  Catalogo de permisos
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class DefinicionPermiso:
    codigo: str
    descripcion: str
    categoria: str
    # Si es cierto, tener el permiso no basta: hace falta vinculo
    # asistencial con el paciente concreto.
    requiere_relacion_asistencial: bool = False
    # Nivel maximo de informacion que habilita este permiso.
    nivel: NivelSensibilidad = NivelSensibilidad.ADMINISTRATIVO


def _p(
    codigo: str,
    descripcion: str,
    categoria: str,
    *,
    relacion: bool = False,
    nivel: NivelSensibilidad = NivelSensibilidad.ADMINISTRATIVO,
) -> DefinicionPermiso:
    return DefinicionPermiso(codigo, descripcion, categoria, relacion, nivel)


CATALOGO_PERMISOS: Final[tuple[DefinicionPermiso, ...]] = (
    # --- Organizacion ---
    _p("clinica.leer", "Ver datos de la clinica", "organizacion"),
    _p("clinica.escribir", "Modificar datos de la clinica", "organizacion"),
    _p("sede.gestionar", "Crear y modificar sedes y consultorios", "organizacion"),
    _p("especialidad.gestionar", "Crear y modificar especialidades", "organizacion"),
    _p("servicio.gestionar", "Crear y modificar servicios y precios", "organizacion"),
    _p("agenda.configurar", "Configurar horarios semanales y feriados", "agenda"),
    _p("configuracion.escribir", "Modificar la configuracion de la clinica", "organizacion"),
    # --- Usuarios ---
    _p("usuario.leer", "Ver usuarios", "usuarios"),
    _p("usuario.crear", "Crear usuarios", "usuarios"),
    _p("usuario.editar", "Modificar usuarios", "usuarios"),
    _p("usuario.desactivar", "Desactivar usuarios", "usuarios"),
    _p("rol.asignar", "Asignar roles y ambitos", "usuarios"),
    # --- Profesionales ---
    _p("profesional.leer", "Ver profesionales", "profesionales"),
    _p("profesional.gestionar", "Crear y modificar profesionales", "profesionales"),
    _p("profesional.conectar_calendario", "Conectar el calendario propio", "profesionales"),
    # --- Agenda ---
    _p("agenda.leer", "Ver la agenda y la disponibilidad", "agenda"),
    _p("cita.crear", "Crear citas", "agenda"),
    _p("cita.reprogramar", "Reprogramar citas", "agenda"),
    _p("cita.cancelar", "Cancelar citas", "agenda"),
    _p("cita.marcar_inasistencia", "Marcar inasistencia", "agenda"),
    _p("cita.registrar_llegada", "Registrar llegada del paciente", "agenda"),
    _p("cita.iniciar_atencion", "Iniciar atención de una cita", "agenda"),
    _p("cita.completar", "Marcar una cita como completada", "agenda"),
    _p("bloqueo.gestionar", "Crear bloqueos, vacaciones y ausencias", "agenda"),
    # --- Pacientes ---
    _p("paciente.leer_administrativo", "Ver datos administrativos del paciente", "pacientes"),
    _p("paciente.crear", "Registrar pacientes", "pacientes"),
    _p("paciente.editar", "Modificar datos del paciente", "pacientes"),
    _p("paciente.verificar_identidad", "Elevar el nivel de verificacion", "pacientes"),
    _p("consentimiento.gestionar", "Registrar y revocar consentimientos", "pacientes"),
    # --- Historia clinica ---
    _p(
        "historia_clinica.leer",
        "Leer la historia clinica",
        "clinico",
        relacion=True,
        nivel=NivelSensibilidad.CLINICO,
    ),
    _p(
        "historia_clinica.escribir",
        "Escribir notas de evolucion",
        "clinico",
        relacion=True,
        nivel=NivelSensibilidad.CLINICO,
    ),
    _p(
        "historia_clinica.leer_sensible",
        "Leer informacion clinica de sensibilidad alta",
        "clinico",
        relacion=True,
        nivel=NivelSensibilidad.CLINICO_SENSIBLE,
    ),
    _p(
        "historia_clinica.leer_metadatos",
        "Ver que registros existen, sin su contenido",
        "clinico",
        nivel=NivelSensibilidad.ADMINISTRATIVO,
    ),
    _p(
        "diagnostico.registrar",
        "Registrar diagnosticos",
        "clinico",
        relacion=True,
        nivel=NivelSensibilidad.CLINICO,
    ),
    _p("acceso_emergencia.solicitar", "Solicitar acceso clinico de emergencia", "clinico"),
    # --- Recetas ---
    _p(
        "receta.crear",
        "Crear recetas",
        "recetas",
        relacion=True,
        nivel=NivelSensibilidad.CLINICO,
    ),
    _p(
        "receta.confirmar",
        "Confirmar una receta y generar el calendario de tomas",
        "recetas",
        relacion=True,
        nivel=NivelSensibilidad.CLINICO,
    ),
    _p(
        "receta.leer",
        "Leer recetas",
        "recetas",
        relacion=True,
        nivel=NivelSensibilidad.CLINICO,
    ),
    _p("adherencia.leer", "Ver el seguimiento de adherencia", "recetas"),
    # --- Imagenes clinicas y odontologia ---
    # La foto de perfil NO entra aqui: es identificacion administrativa y se
    # gestiona con `paciente.leer_administrativo` y `paciente.editar`.
    _p(
        "imagen_clinica.leer",
        "Ver radiografias y fotos clinicas",
        "clinico",
        relacion=True,
        nivel=NivelSensibilidad.CLINICO,
    ),
    _p(
        "imagen_clinica.cargar",
        "Subir radiografias y fotos clinicas",
        "clinico",
        relacion=True,
        nivel=NivelSensibilidad.CLINICO,
    ),
    _p(
        "odontograma.leer",
        "Ver el odontograma",
        "clinico",
        relacion=True,
        nivel=NivelSensibilidad.CLINICO,
    ),
    _p(
        "odontograma.escribir",
        "Registrar hallazgos en el odontograma",
        "clinico",
        relacion=True,
        nivel=NivelSensibilidad.CLINICO,
    ),
    _p(
        "plan_tratamiento.leer",
        "Ver planes de tratamiento y su presupuesto",
        "clinico",
        relacion=True,
        nivel=NivelSensibilidad.CLINICO,
    ),
    _p(
        "plan_tratamiento.escribir",
        "Crear y modificar planes de tratamiento",
        "clinico",
        relacion=True,
        nivel=NivelSensibilidad.CLINICO,
    ),
    _p("alerta_adherencia.atender", "Atender alertas de adherencia", "recetas"),
    # --- Lista de espera ---
    _p("lista_espera.gestionar", "Gestionar la lista de espera", "agenda"),
    # --- Conversaciones ---
    _p(
        "conversacion.leer",
        "Leer conversaciones de WhatsApp, cuyo texto puede ser clinico",
        "comunicacion",
        nivel=NivelSensibilidad.CLINICO,
    ),
    _p("conversacion.responder", "Responder conversaciones", "comunicacion"),
    _p("conversacion.tomar", "Tomar una conversacion derivada a humano", "comunicacion"),
    # --- Conocimiento ---
    _p("conocimiento.leer", "Ver documentos de la base de conocimiento", "conocimiento"),
    _p("conocimiento.cargar", "Cargar documentos", "conocimiento"),
    _p("conocimiento.aprobar", "Aprobar y publicar documentos", "conocimiento"),
    _p("conocimiento.archivar", "Archivar documentos", "conocimiento"),
    # --- Promociones ---
    # Separados como en conocimiento: quien redacta la campana no es
    # necesariamente quien autoriza que salga a los pacientes.
    _p("promocion.gestionar", "Crear campanas de promociones y sus imagenes", "comunicacion"),
    _p("promocion.aprobar", "Aprobar y enviar campanas de promociones", "comunicacion"),
    # --- Pagos ---
    _p("pago.leer", "Ver pagos", "pagos"),
    _p("pago.registrar", "Registrar pagos y comprobantes", "pagos"),
    _p("pago.validar", "Validar o rechazar un comprobante", "pagos"),
    # --- Gastos y caja ---
    # Separado de pagos: quien cobra en el mostrador no es quien lleva el
    # libro de egresos de la clinica (ADR-0021).
    _p("gasto.leer", "Ver gastos y el flujo de caja", "pagos"),
    _p("gasto.registrar", "Registrar y anular gastos", "pagos"),
    # --- Analitica ---
    _p("dashboard.leer", "Ver el panel de metricas", "analitica"),
    _p("prediccion.consultar", "Consultar predicciones operativas", "analitica"),
    _p("reporte.exportar", "Exportar reportes", "analitica"),
    # --- Auditoria ---
    _p("auditoria.leer", "Leer la pista de auditoria", "auditoria"),
    _p("exportacion.solicitar", "Solicitar exportacion de datos de un titular", "auditoria"),
)

PERMISOS_POR_CODIGO: Final[dict[str, DefinicionPermiso]] = {p.codigo: p for p in CATALOGO_PERMISOS}

# Permisos que, por diseno, ningun rol administrativo puede tener.
# Separar la administracion tecnica del acceso clinico evita que una cuenta
# tecnica comprometida exponga historias clinicas.
PERMISOS_SOLO_ASISTENCIALES: Final[frozenset[str]] = frozenset(
    {
        "historia_clinica.leer",
        "historia_clinica.escribir",
        "historia_clinica.leer_sensible",
        "diagnostico.registrar",
        "receta.crear",
        "receta.confirmar",
        "receta.leer",
        "imagen_clinica.leer",
        "imagen_clinica.cargar",
        "odontograma.leer",
        "odontograma.escribir",
        "plan_tratamiento.leer",
        "plan_tratamiento.escribir",
    }
)


# ---------------------------------------------------------------------------
#  Ambito
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Ambito:
    """Conjunto de datos sobre los que un principal puede actuar.

    Un conjunto vacio significa **ningun acceso**.  `todas_las_sedes` y
    equivalentes son explicitos: hay que concederlos, no se deducen de la
    ausencia de restricciones.
    """

    clinica_id: uuid.UUID | None = None
    sedes: frozenset[uuid.UUID] = field(default_factory=frozenset)
    todas_las_sedes: bool = False
    especialidades: frozenset[uuid.UUID] = field(default_factory=frozenset)
    todas_las_especialidades: bool = False
    profesionales: frozenset[uuid.UUID] = field(default_factory=frozenset)
    todos_los_profesionales: bool = False
    pacientes: frozenset[uuid.UUID] = field(default_factory=frozenset)
    todos_los_pacientes: bool = False
    nivel_maximo: NivelSensibilidad = NivelSensibilidad.ADMINISTRATIVO

    def cubre_sede(self, sede_id: uuid.UUID | None) -> bool:
        if sede_id is None:
            return True
        return self.todas_las_sedes or sede_id in self.sedes

    def cubre_especialidad(self, especialidad_id: uuid.UUID | None) -> bool:
        if especialidad_id is None:
            return True
        return self.todas_las_especialidades or especialidad_id in self.especialidades

    def cubre_profesional(self, profesional_id: uuid.UUID | None) -> bool:
        if profesional_id is None:
            return True
        return self.todos_los_profesionales or profesional_id in self.profesionales

    def cubre_paciente(self, paciente_id: uuid.UUID | None) -> bool:
        if paciente_id is None:
            return True
        return self.todos_los_pacientes or paciente_id in self.pacientes

    def cubre_nivel(self, nivel: NivelSensibilidad) -> bool:
        return self.nivel_maximo.cubre(nivel)

    @property
    def esta_vacio(self) -> bool:
        """Un ambito vacio no da acceso a nada."""
        return not (
            self.todas_las_sedes
            or self.sedes
            or self.todos_los_profesionales
            or self.profesionales
            or self.todos_los_pacientes
            or self.pacientes
        )


# ---------------------------------------------------------------------------
#  Principal
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Principal:
    """Quien actua, con que permisos y sobre que datos.

    Se construye **solo** a partir de un token validado o de un canal
    verificado.  Nunca a partir de parametros de la peticion, del cuerpo de un
    mensaje de WhatsApp ni de la salida de un modelo de lenguaje.
    """

    actor_tipo: TipoActor
    actor_id: uuid.UUID | None
    clinica_id: uuid.UUID | None
    permisos: frozenset[str]
    ambito: Ambito
    # Solo para pacientes que escriben por un canal externo.
    nivel_verificacion: NivelVerificacion = NivelVerificacion.NO_VERIFICADO
    segundo_factor_cumplido: bool = False
    requiere_segundo_factor: bool = False
    # Identificador del profesional, si el usuario lo es.  Necesario para
    # resolver la relacion asistencial y los permisos sobre datos propios.
    profesional_id: uuid.UUID | None = None
    # Identificador del paciente, cuando el principal es el propio paciente.
    paciente_id: uuid.UUID | None = None
    roles: frozenset[str] = field(default_factory=frozenset)
    # IDs concretos de roles vigentes. Los códigos son útiles para la
    # interfaz; una ACL debe distinguir el rol local del rol del sistema.
    role_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    # Origen de la peticion. Se registra en auditoria.
    origen: str = "API"

    def tiene_permiso(self, codigo: str) -> bool:
        return codigo in self.permisos

    @property
    def es_sistema(self) -> bool:
        return self.actor_tipo is TipoActor.SISTEMA

    @property
    def es_agente(self) -> bool:
        return self.actor_tipo is TipoActor.AGENTE_IA

    @property
    def cumple_segundo_factor(self) -> bool:
        """El segundo factor esta satisfecho para este principal."""
        if not self.requiere_segundo_factor:
            return True
        return self.segundo_factor_cumplido


def principal_sistema(clinica_id: uuid.UUID | None = None) -> Principal:
    """Principal para tareas en segundo plano.

    Tiene los permisos que necesita el worker para operar la agenda y la
    comunicacion, pero **no** los permisos clinicos: un trabajo programado no
    escribe notas ni confirma recetas.  Esa restriccion es deliberada y se
    verifica con una prueba.
    """
    permisos = frozenset(
        {
            "agenda.leer",
            "cita.cancelar",
            "cita.reprogramar",
            "cita.marcar_inasistencia",
            "lista_espera.gestionar",
            "conversacion.leer",
            "conversacion.responder",
            "adherencia.leer",
            "conocimiento.leer",
            "paciente.leer_administrativo",
        }
    )
    assert not (permisos & PERMISOS_SOLO_ASISTENCIALES), (
        "El principal del sistema no puede tener permisos clinicos."
    )
    return Principal(
        actor_tipo=TipoActor.SISTEMA,
        actor_id=None,
        clinica_id=clinica_id,
        permisos=permisos,
        ambito=Ambito(
            clinica_id=clinica_id,
            todas_las_sedes=True,
            todas_las_especialidades=True,
            todos_los_profesionales=True,
            todos_los_pacientes=True,
            nivel_maximo=NivelSensibilidad.ADMINISTRATIVO,
        ),
        origen="WORKER",
    )


def principal_anonimo() -> Principal:
    """Principal sin permiso alguno. Es el valor por defecto seguro."""
    return Principal(
        actor_tipo=TipoActor.USUARIO,
        actor_id=None,
        clinica_id=None,
        permisos=frozenset(),
        ambito=Ambito(),
    )


# ---------------------------------------------------------------------------
#  Definicion de los roles base
# ---------------------------------------------------------------------------
# Corresponde a la matriz de docs/security.md, seccion 2.  Se define en codigo
# para que exista una prueba parametrizada que compruebe que la matriz
# documentada y la implementada coinciden: una discrepancia entre ambas es
# como se cuelan los agujeros de autorizacion.
PERMISOS_POR_ROL: Final[dict[str, frozenset[str]]] = {
    "superadministrador": frozenset(
        {
            "clinica.leer",
            "clinica.escribir",
            "sede.gestionar",
            "especialidad.gestionar",
            "servicio.gestionar",
            "configuracion.escribir",
            "usuario.leer",
            "usuario.crear",
            "usuario.editar",
            "usuario.desactivar",
            "rol.asignar",
            "profesional.leer",
            "profesional.gestionar",
            "agenda.leer",
            "agenda.configurar",
            "cita.crear",
            "cita.reprogramar",
            "cita.cancelar",
            "cita.marcar_inasistencia",
            "cita.registrar_llegada",
            "cita.iniciar_atencion",
            "cita.completar",
            "bloqueo.gestionar",
            "paciente.leer_administrativo",
            "paciente.crear",
            "paciente.editar",
            "paciente.verificar_identidad",
            "consentimiento.gestionar",
            "lista_espera.gestionar",
            "conversacion.leer",
            "conversacion.responder",
            "conversacion.tomar",
            "conocimiento.leer",
            "conocimiento.cargar",
            "conocimiento.aprobar",
            "conocimiento.archivar",
            "promocion.gestionar",
            "promocion.aprobar",
            "pago.leer",
            "pago.registrar",
            "pago.validar",
            "gasto.leer",
            "gasto.registrar",
            "dashboard.leer",
            "prediccion.consultar",
            "reporte.exportar",
            "auditoria.leer",
            "exportacion.solicitar",
        }
    ),
    "administrador_clinica": frozenset(
        {
            "clinica.leer",
            "clinica.escribir",
            "sede.gestionar",
            "especialidad.gestionar",
            "servicio.gestionar",
            "configuracion.escribir",
            "usuario.leer",
            "usuario.crear",
            "usuario.editar",
            "usuario.desactivar",
            "rol.asignar",
            "profesional.leer",
            "profesional.gestionar",
            "agenda.leer",
            "agenda.configurar",
            "cita.crear",
            "cita.reprogramar",
            "cita.cancelar",
            "cita.marcar_inasistencia",
            "cita.registrar_llegada",
            "cita.iniciar_atencion",
            "cita.completar",
            "bloqueo.gestionar",
            "paciente.leer_administrativo",
            "paciente.crear",
            "paciente.editar",
            "paciente.verificar_identidad",
            "consentimiento.gestionar",
            "historia_clinica.leer_metadatos",
            "adherencia.leer",
            "alerta_adherencia.atender",
            "lista_espera.gestionar",
            "conversacion.leer",
            "conversacion.responder",
            "conversacion.tomar",
            "conocimiento.leer",
            "conocimiento.cargar",
            "conocimiento.aprobar",
            "conocimiento.archivar",
            "promocion.gestionar",
            "promocion.aprobar",
            "pago.leer",
            "pago.registrar",
            "pago.validar",
            "gasto.leer",
            "gasto.registrar",
            "dashboard.leer",
            "prediccion.consultar",
            "reporte.exportar",
            "auditoria.leer",
            "exportacion.solicitar",
        }
    ),
    "recepcion": frozenset(
        {
            "clinica.leer",
            "profesional.leer",
            "agenda.leer",
            "cita.crear",
            "cita.reprogramar",
            "cita.cancelar",
            "cita.marcar_inasistencia",
            "cita.registrar_llegada",
            "bloqueo.gestionar",
            "paciente.leer_administrativo",
            "paciente.crear",
            "paciente.editar",
            "consentimiento.gestionar",
            "lista_espera.gestionar",
            "conversacion.leer",
            "conversacion.responder",
            "conversacion.tomar",
            "conocimiento.leer",
            "pago.leer",
            "pago.registrar",
            "pago.validar",
            "dashboard.leer",
            # Exportacion de conteos agregados; el CSV no incluye pacientes.
            "reporte.exportar",
        }
    ),
    "profesional": frozenset(
        {
            "clinica.leer",
            "profesional.leer",
            "profesional.conectar_calendario",
            "agenda.leer",
            "cita.crear",
            "cita.reprogramar",
            "cita.cancelar",
            "cita.marcar_inasistencia",
            "cita.registrar_llegada",
            "cita.iniciar_atencion",
            "cita.completar",
            "bloqueo.gestionar",
            "paciente.leer_administrativo",
            "paciente.crear",
            "paciente.editar",
            "historia_clinica.leer",
            "historia_clinica.escribir",
            "historia_clinica.leer_sensible",
            "historia_clinica.leer_metadatos",
            "diagnostico.registrar",
            "acceso_emergencia.solicitar",
            "receta.crear",
            "receta.confirmar",
            "receta.leer",
            "imagen_clinica.leer",
            "imagen_clinica.cargar",
            "odontograma.leer",
            "odontograma.escribir",
            "plan_tratamiento.leer",
            "plan_tratamiento.escribir",
            "adherencia.leer",
            "alerta_adherencia.atender",
            "lista_espera.gestionar",
            "conversacion.leer",
            "conversacion.responder",
            "conversacion.tomar",
            "conocimiento.leer",
            "conocimiento.cargar",
            "conocimiento.aprobar",
            "conocimiento.archivar",
            "dashboard.leer",
            "prediccion.consultar",
        }
    ),
    "asistente": frozenset(
        {
            "clinica.leer",
            "profesional.leer",
            "agenda.leer",
            "cita.crear",
            "cita.reprogramar",
            "cita.cancelar",
            "cita.marcar_inasistencia",
            "cita.registrar_llegada",
            "cita.iniciar_atencion",
            "cita.completar",
            "paciente.leer_administrativo",
            "paciente.crear",
            "paciente.editar",
            "historia_clinica.leer_metadatos",
            "receta.leer",
            # El asistente dental toma radiografias y fotos, y consulta el
            # odontograma y el plan para preparar el sillon. No los modifica.
            "imagen_clinica.leer",
            "imagen_clinica.cargar",
            "odontograma.leer",
            "plan_tratamiento.leer",
            "adherencia.leer",
            "alerta_adherencia.atender",
            "lista_espera.gestionar",
            "conversacion.leer",
            "conversacion.responder",
            "conversacion.tomar",
            "conocimiento.leer",
        }
    ),
    "auditor": frozenset(
        {
            "clinica.leer",
            "usuario.leer",
            "profesional.leer",
            "agenda.leer",
            "paciente.leer_administrativo",
            # Ve que registros existen y quien los consulto, pero no su
            # contenido clinico: puede verificar sin ver.
            "historia_clinica.leer_metadatos",
            "adherencia.leer",
            "conversacion.leer",
            "conocimiento.leer",
            "pago.leer",
            "gasto.leer",
            "dashboard.leer",
            "prediccion.consultar",
            "reporte.exportar",
            "auditoria.leer",
            "exportacion.solicitar",
        }
    ),
}


def validar_catalogo() -> list[str]:
    """Comprueba la coherencia interna del modelo de autorizacion.

    Se ejecuta como prueba unitaria.  Detecta los errores que de otro modo
    solo se descubren en produccion:

    * Un rol con un permiso que no existe (una errata en el codigo del
      permiso deja el permiso sin efecto y nadie se da cuenta).
    * Un rol administrativo con permisos clinicos.
    """
    problemas: list[str] = []

    for rol, permisos in PERMISOS_POR_ROL.items():
        desconocidos = permisos - set(PERMISOS_POR_CODIGO)
        if desconocidos:
            problemas.append(
                f"El rol '{rol}' referencia permisos inexistentes: {sorted(desconocidos)}"
            )

    for rol in ("superadministrador", "recepcion", "auditor"):
        clinicos = PERMISOS_POR_ROL[rol] & PERMISOS_SOLO_ASISTENCIALES
        if clinicos:
            problemas.append(
                f"El rol '{rol}' no debe tener permisos clinicos: {sorted(clinicos)}. "
                "Separar la administracion del acceso clinico es una decision "
                "de diseno (docs/security.md, seccion 2)."
            )

    return problemas
