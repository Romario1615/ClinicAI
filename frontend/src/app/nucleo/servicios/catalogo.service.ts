/**
 * Catálogo de la clínica, con caché por sesión.
 *
 * Por qué se cachea
 * -----------------
 * Sedes, especialidades, servicios y profesionales cambian rara vez — se
 * administran, no se operan — y la pantalla de agenda los pide en cada carga.
 * Sin caché, cambiar de día en el calendario dispararía cuatro peticiones que
 * devuelven exactamente lo mismo.
 *
 * La caché es **por sesión y en memoria**. No se persiste: un catálogo guardado
 * en `localStorage` sobreviviría a un cambio de permisos y la interfaz seguiría
 * ofreciendo una sede que el backend ya no autoriza. El usuario vería 404 al
 * agendar, sin entender por qué.
 *
 * `shareReplay` hace que varias pantallas pidiéndolo a la vez compartan una
 * única petición en lugar de lanzar una cada una.
 */
import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, map, shareReplay } from 'rxjs';

import { CONFIGURACION } from './configuracion';
import type {
  Consultorio,
  Especialidad,
  Profesional,
  Sede,
  Servicio,
} from '../modelos/dominio';

export interface ClinicaCatalogo {
  readonly id: string;
  readonly nombre: string;
  readonly zona_horaria: string;
  readonly idioma: string;
  readonly moneda: string;
  readonly telefono: string | null;
  readonly correo: string | null;
}

interface RespuestaSede {
  readonly id: string;
  readonly nombre: string;
  readonly direccion: string | null;
  readonly telefono: string | null;
  readonly zona_horaria: string;
  readonly minutos_antelacion_minima: number;
}

export interface SedeGestion {
  readonly id: string;
  readonly nombre: string;
  readonly direccion: string | null;
  readonly telefono: string | null;
  readonly zona_horaria: string;
  readonly minutos_antelacion_minima: number;
}

export type DatosSede = Omit<SedeGestion, 'id'>;

@Injectable({ providedIn: 'root' })
export class CatalogoService {
  private readonly http = inject(HttpClient);
  private readonly configuracion = inject(CONFIGURACION);

  private cacheClinica?: Observable<ClinicaCatalogo>;
  private cacheSedes?: Observable<readonly Sede[]>;
  private cacheEspecialidades?: Observable<readonly Especialidad[]>;
  private readonly cacheServicios = new Map<string, Observable<readonly Servicio[]>>();
  private readonly cacheProfesionales = new Map<string, Observable<readonly Profesional[]>>();
  private readonly cacheConsultorios = new Map<string, Observable<readonly Consultorio[]>>();

  clinica(): Observable<ClinicaCatalogo> {
    this.cacheClinica ??= this.http
      .get<ClinicaCatalogo>(this.url('/catalogo/clinica'))
      .pipe(shareReplay({ bufferSize: 1, refCount: false }));
    return this.cacheClinica;
  }

  sedes(): Observable<readonly Sede[]> {
    this.cacheSedes ??= this.http
      .get<readonly RespuestaSede[]>(this.url('/catalogo/sedes'))
      .pipe(
        map((sedes) =>
          sedes.map((sede) => ({
            id: sede.id,
            nombre: sede.nombre,
            direccion: sede.direccion,
            zona_horaria: sede.zona_horaria,
          })),
        ),
        shareReplay({ bufferSize: 1, refCount: false }),
      );
    return this.cacheSedes;
  }

  sedesGestion(): Observable<readonly SedeGestion[]> {
    return this.http.get<readonly SedeGestion[]>(this.url('/catalogo/sedes/gestion'));
  }

  actualizarSede(id: string, datos: DatosSede): Observable<SedeGestion> {
    return this.http.put<SedeGestion>(this.url(`/catalogo/sedes/${id}`), datos).pipe(
      map((sede) => {
        this.cacheSedes = undefined;
        this.cacheProfesionales.clear();
        this.cacheConsultorios.clear();
        return sede;
      }),
    );
  }

  especialidades(): Observable<readonly Especialidad[]> {
    this.cacheEspecialidades ??= this.http
      .get<readonly Especialidad[]>(this.url('/catalogo/especialidades'))
      .pipe(shareReplay({ bufferSize: 1, refCount: false }));
    return this.cacheEspecialidades;
  }

  especialidadesGestion(): Observable<readonly Especialidad[]> {
    return this.http.get<readonly Especialidad[]>(this.url('/catalogo/especialidades/gestion'));
  }

  crearEspecialidad(datos: Pick<Especialidad, 'nombre' | 'codigo' | 'descripcion'>): Observable<Especialidad> {
    return this.http.post<Especialidad>(this.url('/catalogo/especialidades'), datos).pipe(
      map((item) => { this.invalidarEspecialidades(); return item; }),
    );
  }

  actualizarEspecialidad(id: string, datos: Pick<Especialidad, 'nombre' | 'codigo' | 'descripcion'>): Observable<Especialidad> {
    return this.http.put<Especialidad>(this.url(`/catalogo/especialidades/${id}`), datos).pipe(
      map((item) => { this.invalidarEspecialidades(); return item; }),
    );
  }

  cambiarEstadoEspecialidad(id: string, activo: boolean): Observable<Especialidad> {
    return this.http.patch<Especialidad>(this.url(`/catalogo/especialidades/${id}/estado`), { activo }).pipe(
      map((item) => { this.invalidarEspecialidades(); return item; }),
    );
  }

  servicios(especialidadId?: string): Observable<readonly Servicio[]> {
    const clave = especialidadId ?? '*';
    let peticion = this.cacheServicios.get(clave);
    if (!peticion) {
      const consulta = especialidadId ? `?especialidad_id=${especialidadId}` : '';
      peticion = this.http
        .get<readonly Servicio[]>(this.url(`/catalogo/servicios${consulta}`))
        .pipe(shareReplay({ bufferSize: 1, refCount: false }));
      this.cacheServicios.set(clave, peticion);
    }
    return peticion;
  }

  profesionales(opciones: {
    especialidadId?: string;
    sedeId?: string;
  } = {}): Observable<readonly Profesional[]> {
    const clave = `${opciones.especialidadId ?? '*'}|${opciones.sedeId ?? '*'}`;
    let peticion = this.cacheProfesionales.get(clave);
    if (!peticion) {
      const parametros = new URLSearchParams();
      if (opciones.especialidadId) {
        parametros.set('especialidad_id', opciones.especialidadId);
      }
      if (opciones.sedeId) {
        parametros.set('sede_id', opciones.sedeId);
      }
      const consulta = parametros.size > 0 ? `?${parametros.toString()}` : '';
      peticion = this.http
        .get<readonly Profesional[]>(this.url(`/catalogo/profesionales${consulta}`))
        .pipe(shareReplay({ bufferSize: 1, refCount: false }));
      this.cacheProfesionales.set(clave, peticion);
    }
    return peticion;
  }

  /** Consultorios de una sede (o de todas las alcanzables). */
  consultorios(sedeId?: string): Observable<readonly Consultorio[]> {
    const clave = sedeId ?? '*';
    let peticion = this.cacheConsultorios.get(clave);
    if (!peticion) {
      const consulta = sedeId ? `?sede_id=${sedeId}` : '';
      peticion = this.http
        .get<readonly Consultorio[]>(this.url(`/catalogo/consultorios${consulta}`))
        .pipe(shareReplay({ bufferSize: 1, refCount: false }));
      this.cacheConsultorios.set(clave, peticion);
    }
    return peticion;
  }

  serviciosGestion(): Observable<readonly ServicioGestion[]> {
    return this.http.get<readonly ServicioGestion[]>(this.url('/catalogo/servicios/gestion'));
  }

  crearServicio(datos: DatosServicio): Observable<ServicioGestion> {
    return this.http.post<ServicioGestion>(this.url('/catalogo/servicios'), datos).pipe(
      map((item) => { this.invalidarServicios(); return item; }),
    );
  }

  actualizarServicio(id: string, datos: DatosServicio): Observable<ServicioGestion> {
    return this.http.put<ServicioGestion>(this.url(`/catalogo/servicios/${id}`), datos).pipe(
      map((item) => { this.invalidarServicios(); return item; }),
    );
  }

  cambiarEstadoServicio(id: string, activo: boolean): Observable<ServicioGestion> {
    return this.http.patch<ServicioGestion>(this.url(`/catalogo/servicios/${id}/estado`), { activo }).pipe(
      map((item) => { this.invalidarServicios(); return item; }),
    );
  }

  consultoriosGestion(sedeId: string): Observable<readonly Consultorio[]> {
    return this.http.get<readonly Consultorio[]>(
      this.url(`/catalogo/consultorios/gestion?sede_id=${encodeURIComponent(sedeId)}`),
    );
  }

  crearConsultorio(datos: {
    sede_id: string;
    nombre: string;
    tipo: Consultorio['tipo'];
    capacidad: number;
  }): Observable<Consultorio> {
    return this.http.post<Consultorio>(this.url('/catalogo/consultorios'), datos).pipe(
      map((consultorio) => {
        this.invalidarConsultorios();
        return consultorio;
      }),
    );
  }

  actualizarConsultorio(
    id: string,
    datos: { nombre: string; tipo: Consultorio['tipo']; capacidad: number },
  ): Observable<Consultorio> {
    return this.http.put<Consultorio>(this.url(`/catalogo/consultorios/${id}`), datos).pipe(
      map((consultorio) => {
        this.invalidarConsultorios();
        return consultorio;
      }),
    );
  }

  cambiarEstadoConsultorio(id: string, activo: boolean): Observable<Consultorio> {
    return this.http.patch<Consultorio>(this.url(`/catalogo/consultorios/${id}/estado`), { activo }).pipe(
      map((consultorio) => {
        this.invalidarConsultorios();
        return consultorio;
      }),
    );
  }

  private invalidarConsultorios(): void {
    this.cacheConsultorios.clear();
  }

  private invalidarEspecialidades(): void {
    this.cacheEspecialidades = undefined;
  }

  private invalidarServicios(): void {
    this.cacheServicios.clear();
  }

  /**
   * Vacía la caché.
   *
   * Se llama al cerrar sesión. Sin esto, quien entre después en el mismo
   * navegador vería el catálogo del usuario anterior hasta la primera
   * recarga, y con él las sedes que su propio ámbito no autoriza.
   */
  limpiar(): void {
    this.cacheClinica = undefined;
    this.cacheSedes = undefined;
    this.cacheEspecialidades = undefined;
    this.cacheServicios.clear();
    this.cacheProfesionales.clear();
    this.cacheConsultorios.clear();
  }

  private url(ruta: string): string {
    return `${this.configuracion.urlApi}${ruta}`;
  }
}

export type ServicioGestion = Servicio & {
  readonly activo: boolean;
  readonly requiere_pago_previo: boolean;
  readonly instrucciones_preparacion: string | null;
  readonly tipo_consultorio_requerido: Servicio['tipo_consultorio_requerido'];
};

export interface DatosServicio {
  readonly especialidad_id: string;
  readonly nombre: string;
  readonly descripcion: string | null;
  readonly duracion_minutos: number;
  readonly minutos_preparacion: number;
  readonly precio: number | null;
  readonly moneda: string;
  readonly requiere_pago_previo: boolean;
  readonly instrucciones_preparacion: string | null;
  readonly tipo_consultorio_requerido: Servicio['tipo_consultorio_requerido'];
}
