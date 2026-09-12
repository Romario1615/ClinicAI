/**
 * Tipos del dominio, alineados con los esquemas del backend.
 *
 * Se escriben a mano en lugar de generarlos del OpenAPI. El motivo no es
 * pereza: generarlos ataria el frontend a la version exacta del backend y
 * haria que un cambio de campo rompiera la compilacion en lugar de aparecer
 * como un dato ausente. Aqui interesa lo contrario -- que la interfaz
 * degrade, no que se caiga -- porque una recepcionista con la agenda a medias
 * sigue pudiendo atender, y con la aplicacion sin arrancar, no.
 *
 * Contrapartida declarada: si el backend renombra un campo, aqui hay que
 * cambiarlo a mano. Las pruebas de API del backend fijan el contrato, y esta
 * es la copia del cliente.
 *
 * Convencion de idioma: identificadores en espanol sin diacriticos; los
 * estados van en ingles porque la especificacion los fija de forma normativa
 * (ADR-0015).
 */

/** Estados de una cita. No se traducen: ver ADR-0015. */
export type EstadoCita =
  | 'PENDING'
  | 'HELD'
  | 'CONFIRMED'
  | 'RESCHEDULED'
  | 'CANCELLED'
  | 'COMPLETED'
  | 'NO_SHOW';

export type OrigenCita = 'PANEL' | 'WHATSAPP' | 'LISTA_ESPERA' | 'RECURRENTE';

/** Nivel de sensibilidad de la informacion. Ver docs/security.md, seccion 1. */
export type NivelSensibilidad = 'N0' | 'N1' | 'N2' | 'N3';

// ---------------------------------------------------------------------------
//  Identidad
// ---------------------------------------------------------------------------
export interface ParTokens {
  readonly token_acceso: string;
  readonly token_refresco: string;
  readonly tipo_token: string;
  readonly expira_en: string;
  readonly requiere_segundo_factor: boolean;
}

export interface ResumenAmbito {
  readonly clinica_id: string | null;
  readonly sedes: readonly string[];
  readonly todas_las_sedes: boolean;
  readonly especialidades: readonly string[];
  readonly todas_las_especialidades: boolean;
  readonly profesionales: readonly string[];
  readonly todos_los_profesionales: boolean;
  readonly todos_los_pacientes: boolean;
  readonly nivel_maximo: NivelSensibilidad;
}

export interface Identidad {
  readonly usuario_id: string;
  readonly correo: string;
  readonly nombre: string;
  readonly apellido: string;
  readonly clinica_id: string | null;
  readonly roles: readonly string[];
  readonly permisos: readonly string[];
  readonly ambito: ResumenAmbito;
  readonly requiere_segundo_factor: boolean;
  readonly segundo_factor_cumplido: boolean;
  readonly dosfa_habilitado: boolean;
  readonly debe_cambiar_contrasena: boolean;
  readonly ultimo_acceso_en: string | null;
}

// ---------------------------------------------------------------------------
//  Agenda
// ---------------------------------------------------------------------------
export interface TurnoDisponible {
  readonly inicio: string;
  readonly fin_consulta: string;
  readonly fin_bloque: string;
  readonly duracion_minutos: number;
  readonly minutos_preparacion: number;
}

export interface Disponibilidad {
  readonly profesional_id: string;
  readonly servicio_id: string;
  readonly sede_id: string;
  readonly zona_horaria: string;
  readonly desde: string;
  readonly hasta: string;
  readonly turnos: readonly TurnoDisponible[];
  readonly motivos_sin_turno: Readonly<Record<string, number>>;
}

export interface Cita {
  readonly id: string;
  readonly paciente_id: string;
  readonly profesional_id: string;
  readonly servicio_id: string;
  readonly sede_id: string;
  readonly consultorio_id: string | null;
  readonly inicio: string;
  readonly fin: string;
  readonly duracion_minutos: number;
  readonly minutos_preparacion: number;
  readonly estado: EstadoCita;
  readonly origen: OrigenCita;
  readonly expira_en: string | null;
  readonly confirmada_en: string | null;
  readonly cancelada_en: string | null;
  readonly motivo_cancelacion: string | null;
}

export interface CitaDetalle extends Cita {
  readonly notas_recepcion: string | null;
}

export interface PaginaCitas {
  readonly elementos: readonly Cita[];
  readonly total: number;
  readonly limite: number;
  readonly desplazamiento: number;
}

// ---------------------------------------------------------------------------
//  Catalogo y personas
// ---------------------------------------------------------------------------
export interface Sede {
  readonly id: string;
  readonly nombre: string;
  readonly direccion: string | null;
  readonly zona_horaria: string;
}

export interface Especialidad {
  readonly id: string;
  readonly nombre: string;
}

export interface Servicio {
  readonly id: string;
  readonly especialidad_id: string;
  readonly nombre: string;
  readonly duracion_minutos: number;
  readonly minutos_preparacion: number;
  readonly precio: number | null;
}

export interface Profesional {
  readonly id: string;
  readonly especialidad_id: string;
  readonly nombre: string;
  readonly apellido: string;
  readonly numero_registro_profesional: string;
}

export interface Paciente {
  readonly id: string;
  readonly tipo_documento: string;
  readonly numero_documento: string;
  readonly nombre: string;
  readonly apellido: string;
  readonly telefono_whatsapp: string | null;
  readonly correo: string | null;
  readonly fecha_nacimiento: string | null;
  /**
   * Nivel de verificacion de identidad.
   *
   * Importa en la interfaz y no es decorativo: un telefono NO verificado no
   * basta para dar informacion por WhatsApp, y quien atiende tiene que verlo
   * antes de hablar.
   */
  readonly nivel_verificacion: string;
}

// ---------------------------------------------------------------------------
//  Errores
// ---------------------------------------------------------------------------
/**
 * Forma del cuerpo de error del backend.
 *
 * `codigo` es el discriminador estable del contrato: la interfaz ramifica por
 * el y nunca por el texto de `mensaje`, que cambia al reescribirlo.
 */
export interface ErrorApi {
  readonly codigo: string;
  readonly mensaje: string;
  readonly detalles?: Readonly<Record<string, unknown>>;
  readonly correlacion_id?: string;
}
