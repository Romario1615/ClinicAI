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
from app.modulos.conversaciones.modelos import (
    Conversacion,
    EstadoConversacion,
    IntencionEntrante,
    MensajeEntrante,
)
from app.modulos.historia.modelos import (
    AlertaAdherencia,
    Diagnostico,
    EstadoReceta,
    EstadoToma,
    NotaEvolucion,
    Receta,
    RecetaMedicamento,
    SeveridadAlerta,
    TipoNota,
    Toma,
    ViaAdministracion,
)
from app.modulos.lista_espera.modelos import (
    EntradaListaEspera,
    EstadoEspera,
    EstadoOferta,
    OfertaTurno,
    PrioridadEspera,
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
from app.modulos.profesionales.modelos import (
    AgendaPlantilla,
    CalendarioConexion,
    CalendarioEvento,
    EstadoDisponibilidad,
    EstadoEventoCalendario,
    EstadoSincronizacion,
    Profesional,
    ProfesionalSede,
    ProfesionalServicio,
)
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
    "Base",
    "BloqueoAgenda",
    "CalendarioConexion",
    "CalendarioEvento",
    "CanalOutbox",
    "Cita",
    "CitaHistorial",
    "ClaveIdempotencia",
    "Clinica",
    "CodigoRecuperacion2FA",
    "ConfiguracionClinica",
    "Consentimiento",
    "Consultorio",
    "Conversacion",
    "Descanso",
    "Diagnostico",
    "DocumentoPaciente",
    "EntradaListaEspera",
    "Especialidad",
    "EstadoCita",
    "EstadoConversacion",
    "EstadoDisponibilidad",
    "EstadoEscaneoAntivirus",
    "EstadoEspera",
    "EstadoEventoCalendario",
    "EstadoOferta",
    "EstadoOutbox",
    "EstadoReceta",
    "EstadoSincronizacion",
    "EstadoToma",
    "Feriado",
    "HistorialAcceso",
    "HorarioAtencion",
    "IntencionEntrante",
    "MensajeEntrante",
    "MotivoRevocacion",
    "NotaEvolucion",
    "OfertaTurno",
    "OrigenCita",
    "OutboxMensaje",
    "Paciente",
    "PacienteContacto",
    "Permiso",
    "PrioridadEspera",
    "Profesional",
    "ProfesionalSede",
    "ProfesionalServicio",
    "Receta",
    "RecetaMedicamento",
    "Recordatorio",
    "RelacionAsistencial",
    "ResultadoAcceso",
    "Rol",
    "RolPermiso",
    "Sede",
    "Servicio",
    "Sesion",
    "SeveridadAlergia",
    "SeveridadAlerta",
    "TipoBloqueo",
    "TipoConsentimiento",
    "TipoConsultorio",
    "TipoDocumento",
    "TipoMensajeOutbox",
    "TipoNota",
    "TipoPropietarioHorario",
    "TokenUnUso",
    "Toma",
    "Usuario",
    "UsuarioRol",
    "ViaAdministracion",
]
