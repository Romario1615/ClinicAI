/**
 * Cliente HTTP de la API.
 *
 * Traduce los errores del backend a un tipo propio antes de que lleguen a
 * las pantallas. El motivo: un componente que recibe `HttpErrorResponse`
 * acaba mostrando "Http failure response for ..." al usuario, que es el
 * mensaje mas inutil posible en una recepcion con pacientes esperando.
 *
 * El `codigo` del backend es el discriminador estable. La interfaz ramifica
 * por el y nunca por el texto del mensaje.
 */
import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, throwError } from 'rxjs';

import { CONFIGURACION } from './configuracion';
import type {
  Cita,
  CitaDetalle,
  Disponibilidad,
  Identidad,
  RespuestaAccesosLocales,
  Paciente,
  PaginaCitas,
  ParTokens,
} from '../modelos/dominio';

/** Error de la API, ya normalizado. */
export class FalloApi extends Error {
  constructor(
    readonly codigo: string,
    mensaje: string,
    readonly estado: number,
    readonly detalles?: Readonly<Record<string, unknown>>,
    readonly correlacionId?: string,
  ) {
    super(mensaje);
    this.name = 'FalloApi';
  }

  /** Cierto si hay que volver a iniciar sesion. */
  get exigeReautenticacion(): boolean {
    return this.estado === 401;
  }

  /** Cierto si el recurso no existe **o esta fuera del ambito**.
   *
   * El backend no los distingue a proposito: un 403 sobre un recurso ajeno
   * confirmaria que existe. La interfaz tampoco puede distinguirlos, y ese es
   * el comportamiento correcto.
   */
  get noEncontrado(): boolean {
    return this.estado === 404;
  }
}

/**
 * Objeto convertible en parametros de consulta.
 *
 * Los filtros se convierten con `aConsulta` antes de pasarlos a `aParametros`.
 * Se hace asi, con una funcion explicita, y no extendiendo los filtros con un
 * indice de cadena: un indice abierto aceptaria cualquier propiedad y una
 * errata en el nombre de un filtro pasaria desapercibida hasta que alguien
 * notara que ese filtro nunca se aplico.
 */
type Consultable = Readonly<Record<string, unknown>>;

function aConsulta(filtro: object): Consultable {
  return filtro as Consultable;
}

export interface FiltroCitas {
  readonly desde?: string;
  readonly hasta?: string;
  readonly profesional_id?: string;
  readonly paciente_id?: string;
  readonly sede_id?: string;
  readonly estado?: readonly string[];
  readonly limite?: number;
  readonly desplazamiento?: number;
}

export interface ConsultaDisponibilidad {
  readonly profesional_id: string;
  readonly servicio_id: string;
  readonly sede_id: string;
  readonly desde: string;
  readonly hasta: string;
  readonly explicar?: boolean;
}

export interface FiltroPacientes {
  readonly termino?: string;
  readonly documento?: string;
  readonly limite?: number;
  readonly desplazamiento?: number;
}

export interface Formulario033AntecedenteApi {
  codigo: string;
  presente: boolean | null;
  detalle: string | null;
}

export interface Formulario033DatosApi {
  embarazada: boolean | null;
  motivo_consulta: string;
  enfermedad_actual: string | null;
  antecedentes_personales: Formulario033AntecedenteApi[];
  antecedentes_familiares: Formulario033AntecedenteApi[];
  constantes_vitales: {
    temperatura_c: number | null;
    pulso_minuto: number | null;
    frecuencia_respiratoria_minuto: number | null;
    presion_sistolica_mmhg: number | null;
    presion_diastolica_mmhg: number | null;
  };
  examen_estomatognatico: { region: string; hallazgo: string; detalle: string | null; grado: number | null }[];
  indicadores_salud_bucal: {
    sitios: { pieza: number; placa: number | null; calculo: number | null; gingivitis: boolean | null }[];
    enfermedad_periodontal: string | null;
    oclusion: string | null;
    fluorosis: string | null;
  };
  indices_cpo_ceo: Record<string, number | null>;
  examenes_complementarios: { tipo: string; descripcion: string; resultado: string | null }[];
  diagnosticos: { codigo_cie: string | null; descripcion: string; tipo: string }[];
  sesiones_tratamiento: {
    numero: number;
    fecha: string;
    diagnostico_complicaciones: string | null;
    procedimiento: string | null;
    prescripciones: string | null;
    proxima_cita: string | null;
    alta: boolean;
  }[];
}

export interface Formulario033EntradaApi {
  sede_id: string;
  cita_id?: string | null;
  nota_id?: string | null;
  odontograma_id?: string | null;
  registro_placa_id?: string | null;
  datos: Formulario033DatosApi;
}

export interface Formulario033Api extends Formulario033EntradaApi {
  id: string;
  raiz_id: string;
  version: number;
  vigente: boolean;
  motivo_modificacion: string | null;
  paciente_id: string;
  profesional_id: string;
  contexto_identidad: Readonly<Record<string, unknown>>;
  creado_en: string;
}

export interface ClinicaPlataforma {
  readonly id: string;
  readonly nombre: string;
  readonly identificacion_fiscal: string | null;
  readonly correo: string | null;
  readonly activa: boolean;
  readonly cantidad_sedes: number;
  readonly cantidad_usuarios: number;
}

export interface UsuarioPlataforma {
  readonly id: string;
  readonly clinica_id: string;
  readonly clinica_nombre: string;
  readonly correo: string;
  readonly nombre: string;
  readonly apellido: string;
  readonly activo: boolean;
  readonly roles: readonly string[];
  readonly profesional_id: string | null;
  readonly sedes_ids: readonly string[];
  readonly todas_las_sedes: boolean;
}

export interface RolPlataforma {
  readonly id: string;
  readonly codigo: string;
  readonly nombre: string;
  readonly descripcion: string | null;
  readonly es_sistema: boolean;
}

export interface ProfesionalPlataforma {
  readonly id: string;
  readonly nombre: string;
  readonly apellido: string;
}

export interface AltaUsuarioPlataforma {
  readonly clinica_id: string;
  readonly correo: string;
  readonly nombre: string;
  readonly apellido: string;
  readonly contrasena_inicial: string;
  readonly roles: readonly string[];
  readonly profesional_id: string | null;
  readonly sedes_ids: readonly string[] | null;
}

export interface AsignacionUsuarioPlataforma {
  readonly clinica_id: string;
  readonly roles: readonly string[];
  readonly profesional_id: string | null;
  readonly sedes_ids: readonly string[] | null;
}

export interface AltaClinicaPlataforma {
  nombre: string;
  identificacion_fiscal: string | null;
  zona_horaria: string;
  idioma: string;
  moneda: string;
  telefono: string | null;
  correo: string | null;
  sede_nombre: string;
  sede_direccion: string | null;
  administrador_nombre: string;
  administrador_apellido: string;
  administrador_correo: string;
  contrasena_inicial: string;
}

export interface SedePlataforma {
  readonly id: string;
  readonly clinica_id: string;
  readonly nombre: string;
  readonly direccion: string | null;
  readonly telefono: string | null;
  readonly zona_horaria: string | null;
  readonly activa: boolean;
}

export interface AltaSedePlataforma {
  readonly nombre: string;
  readonly direccion: string | null;
  readonly telefono: string | null;
  readonly zona_horaria: string | null;
}

export interface PaginaPacientes {
  readonly elementos: readonly Paciente[];
  readonly total: number;
  readonly limite: number;
  readonly desplazamiento: number;
  /**
   * Cierto cuando el termino era demasiado corto y el backend lo ignoro.
   *
   * Sin este campo, la interfaz mostraria «sin resultados» y el usuario
   * creeria que ese paciente no existe, cuando en realidad nunca se busco.
   */
  readonly termino_ignorado: boolean;
}

export interface PacienteDetalle extends Paciente {
  readonly sexo: string | null;
  readonly direccion: string | null;
  readonly activo: boolean;
}

export interface DatosReserva {
  readonly paciente_id: string;
  readonly profesional_id: string;
  readonly servicio_id: string;
  readonly sede_id: string;
  readonly inicio: string;
  readonly consultorio_id?: string | null;
  readonly procedimiento_plan_id?: string | null;
  readonly notas_recepcion?: string | null;
}

export type FrecuenciaSerieCitas = 'SEMANAL' | 'QUINCENAL' | 'MENSUAL';

export interface DatosSerieReserva extends DatosReserva {
  readonly frecuencia: FrecuenciaSerieCitas;
  readonly cantidad: number;
}

export interface RespuestaSerieCitas {
  readonly serie_id: string;
  readonly frecuencia: FrecuenciaSerieCitas;
  readonly cantidad: number;
  readonly citas: readonly Cita[];
}

// ---------------------------------------------------------------------------
//  Conocimiento
// ---------------------------------------------------------------------------
export type EstadoDocumento =
  | 'DRAFT'
  | 'PENDING_REVIEW'
  | 'APPROVED'
  | 'PUBLISHED'
  | 'ARCHIVED';

export type TipoDocumento =
  | 'PROTOCOLO'
  | 'INSTRUCTIVO'
  | 'PREPARACION_EXAMEN'
  | 'POLITICA'
  | 'PREGUNTA_FRECUENTE'
  | 'TARIFARIO';

export interface Documento {
  readonly id: string;
  readonly titulo: string;
  readonly tipo: TipoDocumento;
  readonly status: EstadoDocumento;
  readonly version_vigente: number | null;
  readonly sensitivity_level: string;
  readonly branch_id: string | null;
  readonly specialty_id: string | null;
  readonly service_id: string | null;
  readonly etiquetas: readonly string[];
  readonly effective_from: string | null;
  readonly effective_until: string | null;
  readonly aprobado_por: string | null;
  readonly aprobado_en: string | null;
  readonly archivado_en: string | null;
  /**
   * Cierto cuando la ingesta detecto un intento de inyeccion en el texto.
   *
   * Bloquea la aprobacion hasta que una persona lo revise. En la interfaz se
   * muestra siempre: un documento marcado y aprobado sin mirar es como entra
   * una instruccion hostil en el corpus (ADR-0014).
   */
  readonly requiere_revision?: boolean;
}

export interface PaginaDocumentos {
  readonly elementos: readonly Documento[];
  readonly total: number;
}

export type TipoPrincipalDocumento = 'ROL' | 'USUARIO' | 'SEDE' | 'ESPECIALIDAD';

export interface PermisoDocumento {
  readonly principal_tipo: TipoPrincipalDocumento;
  readonly principal_id: string;
  readonly puede_leer: boolean;
  readonly puede_usar_en_agente: boolean;
}

export interface OpcionPrincipalDocumento {
  readonly id: string;
  readonly nombre: string;
  readonly codigo: string | null;
}

export interface OpcionesPermisosDocumento {
  readonly roles: readonly OpcionPrincipalDocumento[];
  readonly usuarios: readonly OpcionPrincipalDocumento[];
  readonly sedes: readonly OpcionPrincipalDocumento[];
  readonly especialidades: readonly OpcionPrincipalDocumento[];
}

export interface RespuestaPermisosDocumento {
  readonly document_id: string;
  readonly permisos: readonly PermisoDocumento[];
}

export interface FiltroDocumentos {
  readonly estado?: EstadoDocumento;
  readonly limite?: number;
  readonly desplazamiento?: number;
}

/** Alta de un documento. Nace siempre en `DRAFT`. */
export interface DatosDocumento {
  readonly titulo: string;
  readonly tipo: TipoDocumento;
  /** `N0`..`N3`. */
  readonly sensibilidad: string;
  readonly etiquetas?: readonly string[] | null;
  readonly effective_from?: string | null;
  readonly effective_until?: string | null;
}

/** Texto de una version nueva. El backend lo fragmenta y vectoriza. */
export interface DatosIngesta {
  readonly contenido: string;
  readonly nombre_archivo?: string | null;
  readonly notas_cambio?: string | null;
}

export interface RespuestaIngesta {
  readonly document_id: string;
  readonly version: number;
  readonly fragmentos: number;
  readonly embeddings: number;
  readonly riesgo_inyeccion: string;
  /** Cierto si la ingesta detecto texto que parece una instruccion. */
  readonly requiere_revision: boolean;
  readonly escaneo_antivirus: 'LIMPIO' | 'NO_DISPONIBLE' | 'NO_APLICA';
}

// ---------------------------------------------------------------------------
//  Consentimientos de comunicacion
// ---------------------------------------------------------------------------
export interface TextoConsentimiento {
  readonly tipo: string;
  readonly version: string;
  readonly titulo: string;
  readonly texto: string;
}

export interface EstadoConsentimiento {
  readonly tipo: string;
  readonly titulo: string;
  readonly vigente: boolean;
  readonly version_texto: string | null;
  readonly otorgado_en: string | null;
  readonly revocado_en: string | null;
  readonly canal: string | null;
}

// ---------------------------------------------------------------------------
//  Promociones
// ---------------------------------------------------------------------------
export type EstadoCampana = 'BORRADOR' | 'APROBADA' | 'ENVIADA' | 'CANCELADA';

export interface SegmentoCampana {
  readonly sede_id?: string | null;
  readonly sin_visita_hace_dias?: number | null;
  readonly visita_en_ultimos_dias?: number | null;
}

export interface Campana {
  readonly id: string;
  readonly nombre: string;
  readonly texto: string;
  readonly plantilla_meta: string;
  readonly estado: EstadoCampana;
  readonly segmento: SegmentoCampana;
  readonly tiene_imagen: boolean;
  readonly imagen_origen: 'SUBIDA' | 'GENERADA' | null;
  readonly imagen_proveedor: string | null;
  readonly imagen_prompt: string | null;
  readonly aprobada_en: string | null;
  readonly programada_para: string | null;
  readonly enviada_en: string | null;
  readonly encolados: number;
  readonly omitidos: number;
  readonly cancelada_en: string | null;
  readonly motivo_cancelacion: string | null;
  readonly creado_en: string;
  /** El mensaje tal como lo verá un paciente de ejemplo. */
  readonly vista_previa: string;
}

export interface CampanaNueva {
  readonly nombre: string;
  readonly texto: string;
  readonly plantilla_meta?: string;
  readonly segmento?: SegmentoCampana;
}

export interface ResultadoBusqueda {
  readonly document_id: string;
  readonly version: number;
  readonly indice_fragmento: number;
  /** Titulo y ubicacion del fragmento, para poder citarlo. */
  readonly referencia: string;
  readonly extracto: string;
  readonly puntuacion: number;
  /** Posicion en la rama vectorial de la fusion RRF. `null` si no aparecio. */
  readonly posicion_vectorial: number | null;
  /** Posicion en la rama textual. `null` si no aparecio. */
  readonly posicion_textual: number | null;
}

export interface RespuestaBusqueda {
  /**
   * Falso cuando no hay ningun documento aprobado que responda.
   *
   * Es el campo que impide que la interfaz improvise: sin fuente no se
   * responde, se ofrece derivar a una persona.
   */
  readonly hay_fuente: boolean;
  /** Texto a mostrar cuando no hay fuente. `null` cuando si la hay. */
  readonly mensaje: string | null;
  readonly resultados: readonly ResultadoBusqueda[];
  readonly documentos_citados: readonly string[];
}

// ---------------------------------------------------------------------------
//  Historia clinica
// ---------------------------------------------------------------------------
export interface Nota {
  readonly id: string;
  /** Identificador estable de la nota a traves de sus versiones. */
  readonly raiz_id: string;
  readonly version: number;
  /** Falso en las versiones antiguas, que se conservan y no se borran. */
  readonly vigente: boolean;
  readonly motivo_modificacion: string | null;
  readonly paciente_id: string;
  readonly profesional_id: string;
  readonly cita_id: string | null;
  readonly tipo: string;
  readonly nivel_sensibilidad: 'N2' | 'N3';
  readonly motivo_consulta: string | null;
  readonly subjetivo: string | null;
  readonly objetivo: string | null;
  readonly analisis: string | null;
  readonly plan: string | null;
  readonly signos_vitales: Readonly<Record<string, unknown>> | null;
  readonly creado_en: string;
}

/** Nota nueva. El autor no se envía: lo fija el servidor desde la sesión. */
export interface NotaNueva {
  readonly cita_id?: string | null;
  readonly paciente_id: string;
  readonly tipo: 'EVOLUCION' | 'ENFERMERIA' | 'INTERCONSULTA' | 'PROCEDIMIENTO';
  readonly nivel_sensibilidad: 'N2' | 'N3';
  readonly motivo_consulta: string | null;
  readonly subjetivo: string | null;
  readonly objetivo: string | null;
  readonly analisis: string | null;
  readonly plan: string | null;
  readonly signos_vitales: Readonly<Record<string, number>> | null;
}

/** Control del índice de placa de O'Leary. */
export interface RegistroPlaca {
  readonly id: string;
  readonly paciente_id: string;
  readonly profesional_id: string;
  readonly piezas_evaluadas: readonly number[];
  readonly superficies_con_placa: Readonly<Record<string, readonly string[]>>;
  readonly total_superficies: number;
  readonly total_con_placa: number;
  readonly porcentaje: string;
  readonly observacion: string | null;
  readonly creado_en: string;
}

export interface ImagenPacienteApi {
  readonly id: string;
  readonly paciente_id: string;
  readonly tipo: string;
  readonly nivel_sensibilidad: 'N1' | 'N2' | 'N3';
  readonly piezas: readonly number[];
  readonly tomada_en: string | null;
  readonly descripcion: string | null;
  readonly procedimiento_id?: string | null;
  readonly tipo_mime: string;
  readonly tamano_bytes: number;
  readonly antivirus: 'LIMPIO' | 'NO_DISPONIBLE';
  readonly creado_en: string;
  readonly url_contenido: string;
}

export interface DatosImagenClinica {
  readonly tipo: Exclude<ImagenPacienteApi['tipo'], 'PERFIL'>;
  readonly nivel_sensibilidad?: 'N2' | 'N3';
  readonly piezas?: readonly number[];
  readonly tomada_en?: string | null;
  readonly descripcion?: string | null;
  readonly cita_id?: string | null;
  readonly procedimiento_id?: string | null;
}

export type Denticion = 'PERMANENTE' | 'TEMPORAL' | 'MIXTA';
export type HallazgoPieza =
  | 'AUSENTE'
  | 'A_EXTRAER'
  | 'CORONA'
  | 'ENDODONCIA'
  | 'IMPLANTE'
  | 'PROTESIS_FIJA'
  | 'RESTO_RADICULAR';
export type HallazgoCara =
  | 'CARIES'
  | 'OBTURACION_RESINA'
  | 'OBTURACION_AMALGAMA'
  | 'SELLANTE'
  | 'FRACTURA';
export type CaraOdontologica = 'O' | 'M' | 'D' | 'V' | 'L';

export interface EstadoPiezaOdontograma {
  readonly pieza: HallazgoPieza | null;
  readonly caras: Readonly<Partial<Record<CaraOdontologica, HallazgoCara>>>;
  readonly nota: string | null;
}

export interface Odontograma {
  readonly id: string;
  readonly paciente_id: string;
  readonly profesional_id: string;
  readonly version: number;
  readonly vigente: boolean;
  readonly motivo_modificacion: string | null;
  readonly procedimiento_id: string | null;
  readonly creado_en: string;
  readonly nivel_sensibilidad: 'N2' | 'N3';
  readonly denticion: Denticion;
  readonly piezas: Readonly<Record<string, EstadoPiezaOdontograma>>;
}

export interface ContenidoOdontograma {
  readonly denticion: Denticion;
  readonly piezas: Readonly<Record<string, EstadoPiezaOdontograma>>;
}

export type EstadoPlanTratamiento = 'BORRADOR' | 'PROPUESTO' | 'ACEPTADO' | 'COMPLETADO' | 'CANCELADO';
export type EstadoProcedimientoPlan = 'PENDIENTE' | 'COMPLETADO' | 'CANCELADO';

export interface ProcedimientoPlan {
  readonly id: string;
  readonly fase: number;
  readonly orden: number;
  readonly pieza: number | null;
  readonly caras: string | null;
  readonly servicio_id: string | null;
  readonly descripcion: string;
  readonly precio: string;
  readonly estado: EstadoProcedimientoPlan;
  readonly hallazgo_resultante?: string | null;
  readonly cita_id: string | null;
  readonly completado_en: string | null;
  readonly control_recomendado_en?: string | null;
  readonly control_atendido_en?: string | null;
  readonly control_nota?: string | null;
  readonly cancelado_en?: string | null;
  readonly motivo_cancelacion?: string | null;
}

/** Hallazgos que un procedimiento completado deja en el odontograma. */
export type HallazgoResultante =
  | 'CARIES'
  | 'OBTURACION_RESINA'
  | 'OBTURACION_AMALGAMA'
  | 'SELLANTE'
  | 'FRACTURA'
  | 'AUSENTE'
  | 'A_EXTRAER'
  | 'CORONA'
  | 'ENDODONCIA'
  | 'IMPLANTE'
  | 'PROTESIS_FIJA'
  | 'RESTO_RADICULAR';

export interface PlanTratamiento {
  readonly id: string;
  readonly paciente_id: string;
  readonly profesional_id: string;
  readonly titulo: string;
  readonly estado: EstadoPlanTratamiento;
  readonly moneda: string;
  readonly observaciones: string | null;
  readonly nivel_sensibilidad: 'N2' | 'N3';
  readonly propuesto_en: string | null;
  readonly aceptado_en: string | null;
  readonly aceptacion_medio?: string | null;
  readonly aceptacion_referencia?: string | null;
  readonly completado_en: string | null;
  readonly cancelado_en?: string | null;
  readonly motivo_cancelacion?: string | null;
  readonly creado_en: string;
  readonly procedimientos: readonly ProcedimientoPlan[];
}

export interface ProcedimientoPlanNuevo {
  readonly fase: number;
  readonly orden: number;
  readonly pieza: number | null;
  readonly caras: string | null;
  readonly descripcion: string;
  readonly precio: string;
}

/** Lista de procedimientos reutilizable de la clínica. */
export interface PlantillaPlan {
  readonly id: string;
  readonly nombre: string;
  readonly descripcion: string | null;
  readonly procedimientos: readonly ProcedimientoPlanNuevo[];
  readonly creado_en: string;
}

export interface PlanTratamientoNuevo {
  readonly titulo: string;
  readonly moneda: string;
  readonly observaciones: string | null;
  readonly nivel_sensibilidad: 'N2' | 'N3';
  readonly procedimientos: readonly ProcedimientoPlanNuevo[];
}

export interface Medicamento {
  readonly id: string;
  readonly nombre: string;
  readonly concentracion: string | null;
  readonly forma: string | null;
  readonly dosis: string;
  readonly via: string;
  /**
   * «Cuando sea necesario». Un PRN **no** genera horarios fijos, y la
   * interfaz tiene que distinguirlo: convertirlo en pauta fija es un error
   * de medicacion.
   */
  readonly cuando_sea_necesario: boolean;
  readonly frecuencia_horas: number | null;
  readonly duracion_dias: number | null;
  readonly hora_primera_toma: string | null;
  readonly instrucciones: string | null;
}

export interface Receta {
  readonly id: string;
  readonly paciente_id: string;
  readonly profesional_id: string;
  readonly estado: string;
  readonly confirmada_en: string | null;
  readonly suspendida_en: string | null;
  readonly motivo_suspension: string | null;
  readonly receta_anterior_id: string | null;
  readonly indicaciones_generales: string | null;
  readonly nivel_sensibilidad: 'N2' | 'N3';
  readonly creado_en: string;
  readonly medicamentos: readonly Medicamento[];
}

export interface MedicamentoNuevo {
  nombre: string;
  dosis: string;
  via: string;
  concentracion: string | null;
  forma: string | null;
  cuando_sea_necesario: boolean;
  frecuencia_horas: number | null;
  duracion_dias: number | null;
  hora_primera_toma: string | null;
  instrucciones: string | null;
}

/** Autorización para firmar recetas por otro profesional. */
export interface DelegacionFirma {
  readonly id: string;
  readonly delegante_id: string;
  readonly delegado_id: string;
  readonly vigente_desde: string;
  readonly vigente_hasta: string;
  readonly motivo: string;
  readonly revocada_en: string | null;
  readonly vigente: boolean;
}

export interface Toma {
  readonly id: string;
  readonly receta_medicamento_id: string;
  readonly medicamento: string;
  readonly programada_en: string;
  readonly estado: string;
  readonly registrada_en: string | null;
}

export interface AlertaAdherencia {
  readonly id: string;
  readonly paciente_id: string;
  readonly receta_id: string;
  readonly profesional_id: string;
  readonly severidad: 'INFORMATIVA' | 'ATENCION' | 'URGENTE';
  readonly tomas_omitidas: number;
  readonly tomas_esperadas: number;
  readonly periodo_desde: string;
  readonly periodo_hasta: string;
  readonly creado_en: string;
}

export interface Adherencia {
  readonly alerta: Readonly<Record<string, unknown>> | null;
  readonly motivo: string | null;
}

export interface ConversacionEntrante {
  readonly id: string;
  readonly telefono: string;
  readonly paciente_id: string | null;
  readonly estado: string;
  readonly motivo_handoff: string | null;
  readonly ultima_actividad_en: string;
  readonly ultimo_mensaje: string | null;
}

export interface PaginaConversaciones {
  readonly elementos: readonly ConversacionEntrante[];
  readonly total: number;
  readonly limite: number;
  readonly desplazamiento: number;
}

export interface DetalleConversacionEntrante extends ConversacionEntrante {
  readonly ventana_expira_en: string | null;
  readonly mensajes: readonly {
    readonly id: string;
    readonly tipo: string;
    readonly texto: string | null;
    readonly intencion: string;
    readonly recibido_en: string;
  }[];
}

export interface AvisoRevisionTratamiento {
  readonly id: string;
  readonly conversacion_id: string;
  readonly creado_en: string;
}

export interface AvisoAccesoEmergencia {
  readonly id: string;
  readonly profesional: string;
  readonly creado_en: string;
  readonly vence_en: string;
}

/**
 * Convierte lo que alguien escribe en el buscador en el filtro correcto.
 *
 * El backend tiene dos parametros distintos: `termino` busca por nombre y
 * apellido, y `documento` busca por numero de documento. Enviar siempre
 * `termino` hacia que buscar una cedula no devolviera nada, aunque la etiqueta
 * del campo prometiera lo contrario -- y dar una cedula es justo lo que hace un
 * paciente cuando llega al mostrador.
 *
 * La heuristica es deliberadamente simple: si lo escrito son solo digitos, es
 * un documento. Un nombre no se escribe con digitos, y un documento no lleva
 * letras en los tipos que el sistema admite.
 */
export function filtroBusquedaPaciente(termino: string): FiltroPacientes {
  const limpio = termino.trim();
  if (!limpio) {
    return {};
  }
  return /^\d+$/.test(limpio) ? { documento: limpio } : { termino: limpio };
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly configuracion = inject(CONFIGURACION);

  // --- Autenticacion ---
  iniciarSesion(datos: {
    correo: string;
    contrasena: string;
    codigo_2fa?: string | null;
  }): Observable<ParTokens> {
    return this.post<ParTokens>('/autenticacion/sesion', datos);
  }

  accesosLocales(): Observable<RespuestaAccesosLocales> {
    return this.get<RespuestaAccesosLocales>(
      '/autenticacion/accesos-locales',
    );
  }

  iniciarSesionLocal(codigoRol: string): Observable<ParTokens> {
    return this.post<ParTokens>('/autenticacion/sesion-local', { codigo_rol: codigoRol });
  }

  clinicasPlataforma(): Observable<readonly ClinicaPlataforma[]> {
    return this.get<readonly ClinicaPlataforma[]>('/plataforma/clinicas');
  }

  crearClinicaPlataforma(datos: AltaClinicaPlataforma): Observable<ClinicaPlataforma> {
    return this.post<ClinicaPlataforma>('/plataforma/clinicas', datos);
  }

  sedesPlataforma(clinicaId: string): Observable<readonly SedePlataforma[]> {
    return this.get<readonly SedePlataforma[]>(`/plataforma/clinicas/${clinicaId}/sedes`);
  }

  crearSedePlataforma(clinicaId: string, datos: AltaSedePlataforma): Observable<SedePlataforma> {
    return this.post<SedePlataforma>(`/plataforma/clinicas/${clinicaId}/sedes`, datos);
  }

  usuariosPlataforma(): Observable<readonly UsuarioPlataforma[]> {
    return this.get<readonly UsuarioPlataforma[]>('/plataforma/clinicas/usuarios');
  }

  rolesPlataforma(clinicaId: string): Observable<readonly RolPlataforma[]> {
    return this.get<readonly RolPlataforma[]>('/plataforma/clinicas/roles', { clinica_id: clinicaId });
  }

  profesionalesPlataforma(clinicaId: string, usuarioId?: string): Observable<readonly ProfesionalPlataforma[]> {
    return this.get<readonly ProfesionalPlataforma[]>('/plataforma/clinicas/profesionales', {
      clinica_id: clinicaId,
      usuario_id: usuarioId,
    });
  }

  crearUsuarioPlataforma(datos: AltaUsuarioPlataforma): Observable<UsuarioPlataforma> {
    return this.post<UsuarioPlataforma>('/plataforma/clinicas/usuarios', datos);
  }

  actualizarAsignacionPlataforma(usuarioId: string, datos: AsignacionUsuarioPlataforma): Observable<UsuarioPlataforma> {
    return this.put<UsuarioPlataforma>(`/plataforma/clinicas/usuarios/${usuarioId}/asignacion`, datos);
  }

  refrescar(tokenRefresco: string): Observable<ParTokens> {
    return this.post<ParTokens>('/autenticacion/refresco', { token_refresco: tokenRefresco });
  }

  cerrarSesion(tokenRefresco: string, todosLosDispositivos = false): Observable<void> {
    return this.post<void>('/autenticacion/cierre', {
      token_refresco: tokenRefresco,
      todos_los_dispositivos: todosLosDispositivos,
    });
  }

  identidad(): Observable<Identidad> {
    return this.get<Identidad>('/autenticacion/yo');
  }

  conversacionesPendientes(limite = 50, desplazamiento = 0): Observable<PaginaConversaciones> {
    return this.get<PaginaConversaciones>('/conversaciones', { limite, desplazamiento });
  }

  cuentaConversacionesPendientes(): Observable<{ readonly cantidad: number }> {
    return this.get<{ readonly cantidad: number }>('/conversaciones/pendientes/cuenta');
  }

  avisosTratamientoPendientes(): Observable<readonly AvisoRevisionTratamiento[]> {
    return this.get<readonly AvisoRevisionTratamiento[]>('/conversaciones/avisos-tratamiento');
  }

  cuentaAvisosTratamientoPendientes(): Observable<{ readonly cantidad: number }> {
    return this.get<{ readonly cantidad: number }>(
      '/conversaciones/avisos-tratamiento/cuenta',
    );
  }

  confirmarRevisionAvisoTratamiento(id: string): Observable<void> {
    return this.post<void>(`/conversaciones/avisos-tratamiento/${id}/revision`, null);
  }

  solicitarAccesoEmergencia(pacienteId: string, motivo: string): Observable<{ readonly vence_en: string }> {
    return this.post<{ readonly vence_en: string }>(
      `/historia/pacientes/${pacienteId}/acceso-emergencia`,
      { motivo },
    );
  }

  avisosAccesoEmergencia(): Observable<readonly AvisoAccesoEmergencia[]> {
    return this.get<readonly AvisoAccesoEmergencia[]>('/historia/avisos-acceso-emergencia');
  }

  cuentaAvisosAccesoEmergencia(): Observable<{ readonly cantidad: number }> {
    return this.get<{ readonly cantidad: number }>('/historia/avisos-acceso-emergencia/cuenta');
  }

  revisarAvisoAccesoEmergencia(id: string): Observable<void> {
    return this.post<void>(`/historia/avisos-acceso-emergencia/${id}/revision`, null);
  }

  conversacion(id: string): Observable<DetalleConversacionEntrante> {
    return this.get<DetalleConversacionEntrante>(`/conversaciones/${id}`);
  }

  // --- Agenda ---
  disponibilidad(consulta: ConsultaDisponibilidad): Observable<Disponibilidad> {
    return this.get<Disponibilidad>('/agenda/disponibilidad', aConsulta(consulta));
  }

  citas(filtro: FiltroCitas = {}): Observable<PaginaCitas> {
    return this.get<PaginaCitas>('/agenda/citas', aConsulta(filtro));
  }

  exportarResumenAgenda(filtro: {
    readonly desde: string;
    readonly hasta: string;
    readonly sede_id?: string;
    readonly profesional_id?: string;
    readonly servicio_id?: string;
  }): Observable<Blob> {
    return this.http
      .get(this.url('/agenda/resumen.csv'), {
        params: aParametros(aConsulta(filtro)),
        responseType: 'blob',
      })
      .pipe(catchError(traducirFallo));
  }

  cita(id: string): Observable<CitaDetalle> {
    return this.get<CitaDetalle>(`/agenda/citas/${id}`);
  }

  crearCita(datos: DatosReserva, claveIdempotencia?: string): Observable<Cita> {
    return this.post<Cita>('/agenda/citas', datos, claveIdempotencia);
  }

  crearSerieCitas(
    datos: DatosSerieReserva,
    claveIdempotencia?: string,
  ): Observable<RespuestaSerieCitas> {
    return this.post<RespuestaSerieCitas>('/agenda/citas/series', datos, claveIdempotencia);
  }

  bloquearTurno(datos: DatosReserva, claveIdempotencia?: string): Observable<Cita> {
    return this.post<Cita>('/agenda/citas/bloqueos', datos, claveIdempotencia);
  }

  confirmarCita(id: string): Observable<Cita> {
    return this.post<Cita>(`/agenda/citas/${id}/confirmacion`, null);
  }

  registrarLlegadaCita(id: string): Observable<Cita> {
    return this.post<Cita>(`/agenda/citas/${id}/llegada`, null);
  }

  iniciarAtencionCita(id: string): Observable<Cita> {
    return this.post<Cita>(`/agenda/citas/${id}/inicio-atencion`, null);
  }

  cancelarCita(id: string, motivo: string, horasAntelacionMinima = 0): Observable<Cita> {
    return this.post<Cita>(`/agenda/citas/${id}/cancelacion`, {
      motivo,
      horas_antelacion_minima: horasAntelacionMinima,
    });
  }

  reprogramarCita(
    id: string,
    datos: {
      nuevo_inicio: string;
      motivo: string;
      nuevo_profesional_id?: string | null;
      nuevo_consultorio_id?: string | null;
    },
    claveIdempotencia?: string,
  ): Observable<Cita> {
    return this.post<Cita>(`/agenda/citas/${id}/reprogramacion`, datos, claveIdempotencia);
  }

  completarCita(id: string): Observable<Cita> {
    return this.post<Cita>(`/agenda/citas/${id}/completado`, null);
  }

  marcarInasistencia(id: string): Observable<Cita> {
    return this.post<Cita>(`/agenda/citas/${id}/inasistencia`, null);
  }

  // --- Pacientes ---
  pacientes(filtro: FiltroPacientes = {}): Observable<PaginaPacientes> {
    return this.get<PaginaPacientes>('/pacientes/', aConsulta(filtro));
  }

  paciente(id: string): Observable<PacienteDetalle> {
    return this.get<PacienteDetalle>(`/pacientes/${id}`);
  }

  imagenesClinicas(
    pacienteId: string,
    filtro: { tipo?: string; pieza?: number; procedimiento_id?: string } = {},
  ) {
    return this.get<readonly ImagenPacienteApi[]>(
      `/pacientes/${pacienteId}/imagenes`,
      aConsulta(filtro),
    );
  }

  subirImagenClinica(
    pacienteId: string,
    archivo: File,
    datos: DatosImagenClinica,
  ): Observable<ImagenPacienteApi> {
    const formulario = new FormData();
    formulario.append('archivo', archivo, archivo.name);
    formulario.append('tipo', datos.tipo);
    formulario.append('nivel_sensibilidad', datos.nivel_sensibilidad ?? 'N2');
    for (const pieza of datos.piezas ?? []) formulario.append('piezas', String(pieza));
    if (datos.tomada_en) formulario.append('tomada_en', datos.tomada_en);
    if (datos.descripcion) formulario.append('descripcion', datos.descripcion);
    if (datos.cita_id) formulario.append('cita_id', datos.cita_id);
    if (datos.procedimiento_id) formulario.append('procedimiento_id', datos.procedimiento_id);
    return this.http
      .post<ImagenPacienteApi>(this.url(`/pacientes/${pacienteId}/imagenes`), formulario)
      .pipe(catchError(traducirFallo));
  }

  /** Foto de perfil vigente, o `null` si el paciente no tiene. */
  fotoPerfil(pacienteId: string): Observable<ImagenPacienteApi | null> {
    return this.get<ImagenPacienteApi | null>(`/pacientes/${pacienteId}/foto-perfil`);
  }

  subirFotoPerfil(pacienteId: string, archivo: File): Observable<ImagenPacienteApi> {
    const formulario = new FormData();
    formulario.append('archivo', archivo, archivo.name);
    return this.http
      .post<ImagenPacienteApi>(this.url(`/pacientes/${pacienteId}/foto-perfil`), formulario)
      .pipe(catchError(traducirFallo));
  }

  contenidoImagen(imagenId: string): Observable<Blob> {
    return this.http
      .get(this.url(`/imagenes/${imagenId}/contenido`), { responseType: 'blob' })
      .pipe(catchError(traducirFallo));
  }

  anularImagen(imagenId: string, motivo: string): Observable<ImagenPacienteApi> {
    return this.http
      .patch<ImagenPacienteApi>(this.url(`/imagenes/${imagenId}/anulacion`), { motivo })
      .pipe(catchError(traducirFallo));
  }

  // --- Historia clinica ---
  crearReceta(datos: {
    paciente_id: string;
    profesional_id: string;
    indicaciones_generales: string | null;
    nivel_sensibilidad: 'N2' | 'N3';
    medicamentos: readonly MedicamentoNuevo[];
  }): Observable<Receta> {
    return this.post<Receta>('/historia/recetas', datos);
  }

  /** Sustituye una receta confirmada y su calendario en una operación firmada. */
  versionarReceta(
    recetaId: string,
    datos: {
      profesional_id: string;
      motivo: string;
      indicaciones_generales: string | null;
      medicamentos: readonly MedicamentoNuevo[];
    },
  ): Observable<{ receta: Receta; tomas_canceladas: number; tomas_generadas: number }> {
    return this.post<{ receta: Receta; tomas_canceladas: number; tomas_generadas: number }>(
      `/historia/recetas/${recetaId}/versiones`,
      datos,
    );
  }

  /** Confirma la receta y genera las tomas. `firmante`: propio o por delegación. */
  confirmarReceta(recetaId: string, firmante: string): Observable<unknown> {
    return this.post<unknown>(`/historia/recetas/${recetaId}/confirmacion`, {
      profesional_id: firmante,
    });
  }

  delegacionesMias(): Observable<readonly DelegacionFirma[]> {
    return this.get<readonly DelegacionFirma[]>('/profesionales/delegaciones/mias');
  }

  delegaciones(): Observable<readonly DelegacionFirma[]> {
    return this.get<readonly DelegacionFirma[]>('/profesionales/delegaciones');
  }

  crearDelegacion(datos: {
    delegante_id: string;
    delegado_id: string;
    vigente_desde: string;
    vigente_hasta: string;
    motivo: string;
  }): Observable<DelegacionFirma> {
    return this.post<DelegacionFirma>('/profesionales/delegaciones', datos);
  }

  revocarDelegacion(id: string): Observable<DelegacionFirma> {
    return this.post<DelegacionFirma>(`/profesionales/delegaciones/${id}/revocacion`, {});
  }

  crearNota(datos: NotaNueva): Observable<Nota> {
    return this.post<Nota>('/historia/notas', datos);
  }

  /** Crea la versión siguiente; la anterior se conserva. Exige motivo. */
  corregirNota(raizId: string, datos: NotaNueva & { readonly motivo: string }): Observable<Nota> {
    return this.post<Nota>(`/historia/notas/${raizId}/correccion`, datos);
  }

  indicePlaca(pacienteId: string): Observable<readonly RegistroPlaca[]> {
    return this.get<readonly RegistroPlaca[]>(`/odontologia/pacientes/${pacienteId}/indice-placa`);
  }

  registrarIndicePlaca(
    pacienteId: string,
    datos: {
      piezas_evaluadas: readonly number[];
      superficies_con_placa: Readonly<Record<string, readonly string[]>>;
      observacion: string | null;
    },
  ): Observable<RegistroPlaca> {
    return this.post<RegistroPlaca>(`/odontologia/pacientes/${pacienteId}/indice-placa`, datos);
  }

  formularios033(pacienteId: string): Observable<readonly Formulario033Api[]> {
    return this.get<readonly Formulario033Api[]>(
      `/odontologia/pacientes/${pacienteId}/formularios-033`,
    );
  }

  versionesFormulario033(
    pacienteId: string,
    raizId: string,
  ): Observable<readonly Formulario033Api[]> {
    return this.get<readonly Formulario033Api[]>(
      `/odontologia/pacientes/${pacienteId}/formularios-033/${raizId}/versiones`,
    );
  }

  auditarExportacionFormulario033(
    pacienteId: string,
    raizId: string,
    version: number,
  ): Observable<void> {
    return this.post<void>(
      `/odontologia/pacientes/${pacienteId}/formularios-033/${raizId}/exportacion?version=${version}`,
      {},
    );
  }

  crearFormulario033(pacienteId: string, datos: Formulario033EntradaApi): Observable<Formulario033Api> {
    return this.post<Formulario033Api>(
      `/odontologia/pacientes/${pacienteId}/formularios-033`,
      datos,
    );
  }

  versionarFormulario033(
    pacienteId: string,
    raizId: string,
    datos: Formulario033EntradaApi & { version_base: number; motivo: string },
  ): Observable<Formulario033Api> {
    return this.post<Formulario033Api>(
      `/odontologia/pacientes/${pacienteId}/formularios-033/${raizId}/versiones`,
      datos,
    );
  }

  /** Sin `especialidadId`, el backend usa la especialidad propia del profesional. */
  notas(
    pacienteId: string,
    incluirHistorico = false,
    especialidadId: string | null = null,
  ): Observable<readonly Nota[]> {
    const filtros: Record<string, string | boolean> = {};
    if (incluirHistorico) filtros['incluir_historico'] = true;
    if (especialidadId) filtros['especialidad_id'] = especialidadId;
    return this.get<readonly Nota[]>(
      `/historia/pacientes/${pacienteId}/notas`,
      Object.keys(filtros).length > 0 ? filtros : undefined,
    );
  }

  recetas(pacienteId: string): Observable<readonly Receta[]> {
    return this.get<readonly Receta[]>(`/historia/pacientes/${pacienteId}/recetas`);
  }

  odontograma(pacienteId: string, version?: number): Observable<Odontograma | null> {
    return this.get<Odontograma | null>(
      `/odontologia/pacientes/${pacienteId}/odontograma`,
      version === undefined ? undefined : { version },
    );
  }

  versionesOdontograma(pacienteId: string): Observable<readonly Odontograma[]> {
    return this.get<readonly Odontograma[]>(
      `/odontologia/pacientes/${pacienteId}/odontograma/versiones`,
    );
  }

  crearOdontograma(
    pacienteId: string,
    contenido: ContenidoOdontograma,
    nivelSensibilidad: 'N2' | 'N3' = 'N2',
  ): Observable<Odontograma> {
    return this.post<Odontograma>(`/odontologia/pacientes/${pacienteId}/odontograma`, {
      ...contenido,
      nivel_sensibilidad: nivelSensibilidad,
    });
  }

  versionarOdontograma(
    pacienteId: string,
    contenido: ContenidoOdontograma,
    versionBase: number,
    motivo: string,
    nivelSensibilidad: 'N2' | 'N3' = 'N2',
  ): Observable<Odontograma> {
    return this.post<Odontograma>(`/odontologia/pacientes/${pacienteId}/odontograma/versiones`, {
      ...contenido,
      version_base: versionBase,
      motivo,
      nivel_sensibilidad: nivelSensibilidad,
    });
  }

  planesTratamiento(pacienteId: string): Observable<readonly PlanTratamiento[]> {
    return this.get<readonly PlanTratamiento[]>(
      `/odontologia/pacientes/${pacienteId}/planes-tratamiento`,
    );
  }

  crearPlanTratamiento(
    pacienteId: string,
    datos: PlanTratamientoNuevo,
  ): Observable<PlanTratamiento> {
    return this.post<PlanTratamiento>(
      `/odontologia/pacientes/${pacienteId}/planes-tratamiento`,
      datos,
    );
  }

  plantillasPlan(): Observable<readonly PlantillaPlan[]> {
    return this.get<readonly PlantillaPlan[]>('/odontologia/plantillas-plan');
  }

  crearPlantillaPlan(datos: {
    nombre: string;
    descripcion?: string | null;
    procedimientos: readonly ProcedimientoPlanNuevo[];
  }): Observable<PlantillaPlan> {
    return this.post<PlantillaPlan>('/odontologia/plantillas-plan', datos);
  }

  proponerPlanTratamiento(planId: string): Observable<PlanTratamiento> {
    return this.post<PlanTratamiento>(
      `/odontologia/planes-tratamiento/${planId}/propuesta`,
      {},
    );
  }

  /**
   * Registra la constancia de que el paciente acepto el plan.
   *
   * Es un registro de algo que ocurrio fuera del sistema (documento firmado
   * en la clinica), no una firma digital del paciente.
   */
  aceptarPlanTratamiento(
    planId: string,
    referencia: string,
    imagenId?: string | null,
  ): Observable<PlanTratamiento> {
    return this.post<PlanTratamiento>(`/odontologia/planes-tratamiento/${planId}/aceptacion`, {
      medio: 'DOCUMENTO_FIRMADO',
      referencia,
      imagen_id: imagenId ?? null,
    });
  }

  cancelarPlanTratamiento(planId: string, motivo: string): Observable<PlanTratamiento> {
    return this.post<PlanTratamiento>(`/odontologia/planes-tratamiento/${planId}/cancelacion`, {
      motivo,
    });
  }

  /** Completa un procedimiento; con hallazgo crea una version nueva del odontograma. */
  completarProcedimiento(
    procedimientoId: string,
    hallazgo: HallazgoResultante | null,
    controlRecomendadoEn: string | null = null,
  ): Observable<PlanTratamiento> {
    return this.post<PlanTratamiento>(`/odontologia/procedimientos/${procedimientoId}/completado`, {
      hallazgo_resultante: hallazgo,
      control_recomendado_en: controlRecomendadoEn,
    });
  }

  atenderControlTratamiento(
    procedimientoId: string,
    nota: string | null,
  ): Observable<PlanTratamiento> {
    return this.post<PlanTratamiento>(
      `/odontologia/procedimientos/${procedimientoId}/control/atencion`,
      { nota },
    );
  }

  cancelarProcedimiento(procedimientoId: string, motivo: string): Observable<PlanTratamiento> {
    return this.post<PlanTratamiento>(
      `/odontologia/procedimientos/${procedimientoId}/cancelacion`,
      { motivo },
    );
  }

  /**
   * Calendario de tomas alrededor de hoy.
   *
   * La ventana se centra en el momento actual y no empieza en el: lo que
   * quedo atras sin registrar es justo lo que mide la adherencia.
   */
  tomas(pacienteId: string, dias = 7): Observable<readonly Toma[]> {
    return this.get<readonly Toma[]>(`/historia/pacientes/${pacienteId}/tomas`, { dias });
  }

  /** Registra que una toma se hizo o se omitio. Devuelve 204. */
  registrarToma(tomaId: string, tomada: boolean, nota?: string): Observable<void> {
    return this.post<void>(`/historia/tomas/${tomaId}/registro`, {
      tomada,
      nota_paciente: nota ?? null,
    });
  }

  adherencia(recetaId: string): Observable<Adherencia> {
    return this.get<Adherencia>(`/historia/recetas/${recetaId}/adherencia`);
  }

  alertasAdherencia(): Observable<readonly AlertaAdherencia[]> {
    return this.get<readonly AlertaAdherencia[]>('/historia/adherencia/alertas');
  }

  atenderAlertaAdherencia(alertaId: string, nota?: string): Observable<void> {
    return this.post<void>(`/historia/adherencia/alertas/${alertaId}/atencion`, {
      nota_profesional: nota ?? null,
    });
  }

  // --- Conocimiento ---
  documentos(filtro: FiltroDocumentos = {}): Observable<PaginaDocumentos> {
    return this.get<PaginaDocumentos>('/conocimiento/documentos', aConsulta(filtro));
  }

  /**
   * Busca en la base de conocimiento.
   *
   * Es `POST` y no `GET` a proposito: la consulta de un paciente puede
   * contener informacion sensible, y una cadena de consulta acaba en los
   * registros del servidor y en el historial del navegador.
   */
  buscarConocimiento(consulta: string, limite?: number): Observable<RespuestaBusqueda> {
    return this.post<RespuestaBusqueda>('/conocimiento/busqueda', { consulta, limite });
  }

  opcionesPermisosDocumento(): Observable<OpcionesPermisosDocumento> {
    return this.get<OpcionesPermisosDocumento>('/conocimiento/permisos/opciones');
  }

  permisosDocumento(documentoId: string): Observable<RespuestaPermisosDocumento> {
    return this.get<RespuestaPermisosDocumento>(`/conocimiento/documentos/${documentoId}/permisos`);
  }

  reemplazarPermisosDocumento(
    documentoId: string,
    permisos: readonly PermisoDocumento[],
  ): Observable<RespuestaPermisosDocumento> {
    return this.http
      .put<RespuestaPermisosDocumento>(
        this.url(`/conocimiento/documentos/${documentoId}/permisos`),
        { permisos },
      )
      .pipe(catchError(traducirFallo));
  }

  /** Crea un documento en `DRAFT`. Exige `conocimiento.cargar`. */
  crearDocumento(datos: DatosDocumento): Observable<Documento> {
    return this.post<Documento>('/conocimiento/documentos', datos);
  }

  /**
   * Sube una version nueva de un documento.
   *
   * No cambia su estado: un documento publicado sigue respondiendo con su
   * version aprobada mientras la nueva se revisa.
   */
  ingerirVersion(documentoId: string, datos: DatosIngesta): Observable<RespuestaIngesta> {
    return this.post<RespuestaIngesta>(`/conocimiento/documentos/${documentoId}/versiones`, datos);
  }

  /** Sube un PDF para que el servidor lo analice, extraiga e ingiera. */
  ingerirArchivoPdf(
    documentoId: string,
    archivo: File,
    notasCambio?: string | null,
  ): Observable<RespuestaIngesta> {
    const formulario = new FormData();
    formulario.append('archivo', archivo, archivo.name);
    if (notasCambio?.trim()) {
      formulario.append('notas_cambio', notasCambio.trim());
    }
    return this.http
      .post<RespuestaIngesta>(this.url(`/conocimiento/documentos/${documentoId}/versiones/archivo`), formulario)
      .pipe(catchError(traducirFallo));
  }

  /**
   * Cambia el estado de un documento.
   *
   * Aprobar y publicar exigen `conocimiento.aprobar` en el backend; esta
   * llamada no lo comprueba porque el permiso real se valida alli.
   */
  cambiarEstadoDocumento(
    documentoId: string,
    nuevoEstado: EstadoDocumento,
    motivo?: string,
  ): Observable<Documento> {
    return this.post<Documento>(`/conocimiento/documentos/${documentoId}/estado`, {
      nuevo_estado: nuevoEstado,
      motivo: motivo ?? null,
    });
  }

  // --- Consentimientos de comunicacion ---
  textosConsentimiento(): Observable<readonly TextoConsentimiento[]> {
    return this.get<readonly TextoConsentimiento[]>('/pacientes/consentimientos/textos');
  }

  consentimientos(pacienteId: string): Observable<readonly EstadoConsentimiento[]> {
    return this.get<readonly EstadoConsentimiento[]>(`/pacientes/${pacienteId}/consentimientos`);
  }

  otorgarConsentimiento(
    pacienteId: string,
    tipo: string,
    versionTexto: string,
  ): Observable<EstadoConsentimiento> {
    return this.post<EstadoConsentimiento>(`/pacientes/${pacienteId}/consentimientos`, {
      tipo,
      version_texto: versionTexto,
      canal: 'PRESENCIAL',
      confirmo_lectura: true,
    });
  }

  revocarConsentimiento(pacienteId: string, tipo: string): Observable<EstadoConsentimiento> {
    return this.post<EstadoConsentimiento>(
      `/pacientes/${pacienteId}/consentimientos/${tipo}/revocacion`,
      {},
    );
  }

  // --- Promociones ---
  campanas(): Observable<readonly Campana[]> {
    return this.get<readonly Campana[]>('/promociones/campanas');
  }

  crearCampana(datos: CampanaNueva): Observable<Campana> {
    return this.post<Campana>('/promociones/campanas', datos);
  }

  subirImagenCampana(campanaId: string, archivo: File): Observable<Campana> {
    const formulario = new FormData();
    formulario.append('archivo', archivo, archivo.name);
    return this.http
      .post<Campana>(this.url(`/promociones/campanas/${campanaId}/imagen`), formulario)
      .pipe(catchError(traducirFallo));
  }

  /** Pide al modelo de generacion una imagen. Queda como propuesta del borrador. */
  generarImagenCampana(campanaId: string, descripcion: string): Observable<Campana> {
    return this.post<Campana>(`/promociones/campanas/${campanaId}/imagen-generada`, {
      descripcion,
    });
  }

  imagenCampana(campanaId: string): Observable<Blob> {
    return this.http
      .get(this.url(`/promociones/campanas/${campanaId}/imagen`), { responseType: 'blob' })
      .pipe(catchError(traducirFallo));
  }

  audienciaCampana(campanaId: string): Observable<{ readonly con_consentimiento: number }> {
    return this.get<{ readonly con_consentimiento: number }>(
      `/promociones/campanas/${campanaId}/audiencia`,
    );
  }

  aprobarCampana(campanaId: string): Observable<Campana> {
    return this.post<Campana>(`/promociones/campanas/${campanaId}/aprobacion`, {});
  }

  enviarCampana(campanaId: string, programadaPara: string | null): Observable<Campana> {
    return this.post<Campana>(`/promociones/campanas/${campanaId}/envio`, {
      programada_para: programadaPara,
    });
  }

  cancelarCampana(campanaId: string, motivo: string): Observable<Campana> {
    return this.post<Campana>(`/promociones/campanas/${campanaId}/cancelacion`, { motivo });
  }

  // --- Plomeria ---
  private get<T>(ruta: string, consulta?: Readonly<Record<string, unknown>>): Observable<T> {
    return this.http
      .get<T>(this.url(ruta), { params: aParametros(consulta) })
      .pipe(catchError(traducirFallo));
  }

  private post<T>(
    ruta: string,
    cuerpo: unknown,
    claveIdempotencia?: string,
  ): Observable<T> {
    const cabeceras: Record<string, string> = {};
    if (claveIdempotencia) {
      cabeceras['Idempotency-Key'] = claveIdempotencia;
    }
    return this.http
      .post<T>(this.url(ruta), cuerpo, { headers: cabeceras })
      .pipe(catchError(traducirFallo));
  }

  private put<T>(ruta: string, cuerpo: unknown): Observable<T> {
    return this.http.put<T>(this.url(ruta), cuerpo).pipe(catchError(traducirFallo));
  }

  private url(ruta: string): string {
    return `${this.configuracion.urlApi}${ruta}`;
  }
}

/** Convierte un objeto en parametros, omitiendo lo vacio. */
function aParametros(consulta?: Readonly<Record<string, unknown>>): HttpParams {
  let params = new HttpParams();
  if (!consulta) {
    return params;
  }
  for (const [clave, valor] of Object.entries(consulta)) {
    if (valor === undefined || valor === null || valor === '') {
      continue;
    }
    if (Array.isArray(valor)) {
      // Repetir la clave y no unir con comas: es lo que espera FastAPI para
      // un parametro de lista, y unirlas produciria un 422 por un valor que
      // no esta en el literal de estados permitidos.
      for (const elemento of valor) {
        params = params.append(clave, String(elemento));
      }
    } else {
      params = params.set(clave, String(valor));
    }
  }
  return params;
}

export function traducirFallo(error: unknown): Observable<never> {
  if (!(error instanceof HttpErrorResponse)) {
    return throwError(() => error);
  }

  // Estado 0: la peticion no llego a salir o no volvio. Casi siempre es el
  // backend caido o un problema de CORS, y conviene decirlo asi en lugar de
  // mostrar un error vacio.
  if (error.status === 0) {
    return throwError(
      () =>
        new FalloApi(
          'SIN_CONEXION',
          'No se pudo contactar con el servidor. Compruebe su conexion.',
          0,
        ),
    );
  }

  const cuerpo = error.error as
    | { codigo?: string; mensaje?: string; detalles?: Record<string, unknown>; correlacion_id?: string }
    | null
    | undefined;

  return throwError(
    () =>
      new FalloApi(
        cuerpo?.codigo ?? 'ERROR_DESCONOCIDO',
        cuerpo?.mensaje ?? 'Ocurrio un error inesperado.',
        error.status,
        cuerpo?.detalles,
        cuerpo?.correlacion_id,
      ),
  );
}
