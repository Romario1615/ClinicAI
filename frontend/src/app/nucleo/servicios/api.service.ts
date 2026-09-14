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
  readonly notas_recepcion?: string | null;
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

export interface FiltroDocumentos {
  readonly estado?: EstadoDocumento;
  readonly limite?: number;
  readonly desplazamiento?: number;
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
  readonly motivo_consulta: string | null;
  readonly subjetivo: string | null;
  readonly objetivo: string | null;
  readonly analisis: string | null;
  readonly plan: string | null;
  readonly signos_vitales: Readonly<Record<string, unknown>> | null;
  readonly creado_en: string;
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
  readonly indicaciones_generales: string | null;
  readonly creado_en: string;
  readonly medicamentos: readonly Medicamento[];
}

export interface Toma {
  readonly id: string;
  readonly receta_medicamento_id: string;
  readonly medicamento: string;
  readonly programada_en: string;
  readonly estado: string;
  readonly registrada_en: string | null;
}

export interface Adherencia {
  readonly alerta: Readonly<Record<string, unknown>> | null;
  readonly motivo: string | null;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly configuracion = inject(CONFIGURACION);

  // --- Autenticacion ---
  iniciarSesion(datos: {
    correo: string;
    contrasena: string;
    clinica_id: string;
    codigo_2fa?: string | null;
  }): Observable<ParTokens> {
    return this.post<ParTokens>('/autenticacion/sesion', datos);
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

  // --- Agenda ---
  disponibilidad(consulta: ConsultaDisponibilidad): Observable<Disponibilidad> {
    return this.get<Disponibilidad>('/agenda/disponibilidad', aConsulta(consulta));
  }

  citas(filtro: FiltroCitas = {}): Observable<PaginaCitas> {
    return this.get<PaginaCitas>('/agenda/citas', aConsulta(filtro));
  }

  cita(id: string): Observable<CitaDetalle> {
    return this.get<CitaDetalle>(`/agenda/citas/${id}`);
  }

  crearCita(datos: DatosReserva, claveIdempotencia?: string): Observable<Cita> {
    return this.post<Cita>('/agenda/citas', datos, claveIdempotencia);
  }

  bloquearTurno(datos: DatosReserva, claveIdempotencia?: string): Observable<Cita> {
    return this.post<Cita>('/agenda/citas/bloqueos', datos, claveIdempotencia);
  }

  confirmarCita(id: string): Observable<Cita> {
    return this.post<Cita>(`/agenda/citas/${id}/confirmacion`, null);
  }

  cancelarCita(id: string, motivo: string, horasAntelacionMinima = 0): Observable<Cita> {
    return this.post<Cita>(`/agenda/citas/${id}/cancelacion`, {
      motivo,
      horas_antelacion_minima: horasAntelacionMinima,
    });
  }

  reprogramarCita(
    id: string,
    datos: { nuevo_inicio: string; motivo: string; nuevo_profesional_id?: string | null },
  ): Observable<Cita> {
    return this.post<Cita>(`/agenda/citas/${id}/reprogramacion`, datos);
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

  // --- Historia clinica ---
  notas(pacienteId: string, incluirHistorico = false): Observable<readonly Nota[]> {
    return this.get<readonly Nota[]>(
      `/historia/pacientes/${pacienteId}/notas`,
      incluirHistorico ? { incluir_historico: true } : undefined,
    );
  }

  recetas(pacienteId: string): Observable<readonly Receta[]> {
    return this.get<readonly Receta[]>(`/historia/pacientes/${pacienteId}/recetas`);
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
