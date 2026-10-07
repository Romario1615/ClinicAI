"""Punto unico de importacion de todos los modelos.

Existe por dos motivos concretos:

1. **Alembic necesita que todos los modelos esten importados** antes de
   comparar el metadata con la base de datos.  Si falta uno, `autogenerate`
   genera una migracion que **borra** su tabla, porque la ve en la base y no
   en el metadata.  Es la forma mas rapida de perder datos con Alembic.

2. Evita el ciclo de importaciones entre modulos que se referencian por clave
   externa.

Al anadir un modelo, hay que anadirlo aqui **y a `__all__`**.  Una clase
importada pero ausente de `__all__` la elimina `ruff --fix` por considerarla
sin usar, y entonces su tabla desaparece del metadata sin que nadie lo note
hasta que una migracion la borra.  La prueba
`pruebas/unitarias/test_modelos_exportados.py` lo verifica.
"""

from __future__ import annotations

from app.modulos.agenda.modelos import (
    BloqueoAgenda,
    Cita,
    CitaHistorial,
    ClaveIdempotencia,
    EstadoCita,
    OrigenCita,
    TipoBloqueo,
)
from app.modulos.auditoria.modelos import Auditoria
from app.modulos.conocimiento.modelos import (
    EstadoDocumento,
    EstadoIngesta,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeEmbedding,
    KnowledgeIngestionJob,
    KnowledgePermission,
    KnowledgeVersion,
    PrincipalConocimiento,
    TipoDocumentoConocimiento,
)
from app.modulos.conversaciones.demo_modelos import SesionDemo
from app.modulos.conversaciones.modelos import (
    AvisoRevisionTratamiento,
    Conversacion,
    EstadoConversacion,
    IntencionEntrante,
    MensajeEntrante,
)
from app.modulos.historia.modelos import (
    AlertaAdherencia,
    Diagnostico,
    EstadoPlantillaAnamnesis,
    EstadoReceta,
    EstadoToma,
    NotaEvolucion,
    PlantillaAnamnesis,
    Receta,
    RecetaMedicamento,
    RespuestaAnamnesis,
    SeveridadAlerta,
    TipoNota,
    Toma,
    ViaAdministracion,
)
from app.modulos.imagenes.modelos import ImagenPaciente, TipoImagen
from app.modulos.lista_espera.modelos import (
    EntradaListaEspera,
    EstadoEspera,
    EstadoOferta,
    OfertaTurno,
    PrioridadEspera,
)
from app.modulos.odontologia.modelos import (
    EstadoPlan,
    EstadoProcedimiento,
    Formulario033,
    MedioAceptacion,
    Odontograma,
    PlantillaPlan,
    PlanTratamiento,
    ProcedimientoPlan,
    RegistroPlaca,
)
from app.modulos.organizacion.modelos import (
    Clinica,
    ConfiguracionClinica,
    Consultorio,
    Descanso,
    Especialidad,
    Feriado,
    HorarioAtencion,
    Sede,
    Servicio,
    TipoConsultorio,
    TipoPropietarioHorario,
)
from app.modulos.outbox.modelos import (
    CanalOutbox,
    EstadoOutbox,
    OutboxMensaje,
    Recordatorio,
    TipoMensajeOutbox,
)
from app.modulos.pacientes.modelos import (
    Alergia,
    Antecedente,
    AvisoAccesoEmergencia,
    Consentimiento,
    DocumentoPaciente,
    EstadoEscaneoAntivirus,
    Paciente,
    PacienteContacto,
    RelacionAsistencial,
    SeveridadAlergia,
    TipoConsentimiento,
    TipoDocumento,
)
from app.modulos.pagos.modelos import CargoPago, Pago, PagoComprobante, PagoHistorial
from app.modulos.postconsulta.modelos import IndicacionPostconsulta
from app.modulos.profesionales.modelos import (
    AgendaPlantilla,
    CalendarioConexion,
    CalendarioEvento,
    DelegacionFirma,
    EstadoDisponibilidad,
    EstadoEventoCalendario,
    EstadoSincronizacion,
    Profesional,
    ProfesionalSede,
    ProfesionalServicio,
)
from app.modulos.promociones.modelos import CampanaPromocion, EstadoCampana, OrigenImagen
from app.modulos.usuarios.fotos import FotoUsuario
from app.modulos.usuarios.modelos import (
    AmbitoAsignacion,
    CodigoRecuperacion2FA,
    HistorialAcceso,
    MotivoRevocacion,
    Permiso,
    ResultadoAcceso,
    Rol,
    RolPermiso,
    Sesion,
    TokenUnUso,
    Usuario,
    UsuarioRol,
)
from app.nucleo.bd import Base

__all__ = [
    "AgendaPlantilla",
    "Alergia",
    "AlertaAdherencia",
    "AmbitoAsignacion",
    "Antecedente",
    "Auditoria",
    "AvisoAccesoEmergencia",
    "AvisoRevisionTratamiento",
    "Base",
    "BloqueoAgenda",
    "CalendarioConexion",
    "CalendarioEvento",
    "CampanaPromocion",
    "CanalOutbox",
    "CargoPago",
    "Cita",
    "CitaHistorial",
    "ClaveIdempotencia",
    "Clinica",
    "CodigoRecuperacion2FA",
    "ConfiguracionClinica",
    "Consentimiento",
    "Consultorio",
    "Conversacion",
    "DelegacionFirma",
    "Descanso",
    "Diagnostico",
    "DocumentoPaciente",
    "EntradaListaEspera",
    "Especialidad",
    "EstadoCampana",
    "EstadoCita",
    "EstadoConversacion",
    "EstadoDisponibilidad",
    "EstadoDocumento",
    "EstadoEscaneoAntivirus",
    "EstadoEspera",
    "EstadoEventoCalendario",
    "EstadoIngesta",
    "EstadoOferta",
    "EstadoOutbox",
    "EstadoPlan",
    "EstadoPlantillaAnamnesis",
    "EstadoProcedimiento",
    "EstadoReceta",
    "EstadoSincronizacion",
    "EstadoToma",
    "Feriado",
    "Formulario033",
    "FotoUsuario",
    "HistorialAcceso",
    "HorarioAtencion",
    "ImagenPaciente",
    "IndicacionPostconsulta",
    "IntencionEntrante",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "KnowledgeEmbedding",
    "KnowledgeIngestionJob",
    "KnowledgePermission",
    "KnowledgeVersion",
    "MedioAceptacion",
    "MensajeEntrante",
    "MotivoRevocacion",
    "NotaEvolucion",
    "Odontograma",
    "OfertaTurno",
    "OrigenCita",
    "OrigenImagen",
    "OutboxMensaje",
    "Paciente",
    "PacienteContacto",
    "Pago",
    "PagoComprobante",
    "PagoHistorial",
    "Permiso",
    "PlanTratamiento",
    "PlantillaAnamnesis",
    "PlantillaPlan",
    "PrincipalConocimiento",
    "PrioridadEspera",
    "ProcedimientoPlan",
    "Profesional",
    "ProfesionalSede",
    "ProfesionalServicio",
    "Receta",
    "RecetaMedicamento",
    "Recordatorio",
    "RegistroPlaca",
    "RelacionAsistencial",
    "RespuestaAnamnesis",
    "ResultadoAcceso",
    "Rol",
    "RolPermiso",
    "Sede",
    "Servicio",
    "Sesion",
    "SesionDemo",
    "SeveridadAlergia",
    "SeveridadAlerta",
    "TipoBloqueo",
    "TipoConsentimiento",
    "TipoConsultorio",
    "TipoDocumento",
    "TipoDocumentoConocimiento",
    "TipoImagen",
    "TipoMensajeOutbox",
    "TipoNota",
    "TipoPropietarioHorario",
    "TokenUnUso",
    "Toma",
    "Usuario",
    "UsuarioRol",
    "ViaAdministracion",
]
