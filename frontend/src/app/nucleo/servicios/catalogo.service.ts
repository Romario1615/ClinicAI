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
  Especialidad,
  Profesional,
  Sede,
  Servicio,
} from '../modelos/dominio';

interface RespuestaClinica {
  readonly id: string;
  readonly nombre: string;
  readonly zona_horaria: string;
  readonly idioma: string;
  readonly moneda: string;
}

interface RespuestaSede {
  readonly id: string;
  readonly nombre: string;
  readonly direccion: string | null;
  readonly telefono: string | null;
  readonly zona_horaria: string;
  readonly minutos_antelacion_minima: number;
}

@Injectable({ providedIn: 'root' })
export class CatalogoService {
  private readonly http = inject(HttpClient);
  private readonly configuracion = inject(CONFIGURACION);

  private cacheClinica?: Observable<RespuestaClinica>;
  private cacheSedes?: Observable<readonly Sede[]>;
  private cacheEspecialidades?: Observable<readonly Especialidad[]>;
  private readonly cacheServicios = new Map<string, Observable<readonly Servicio[]>>();
  private readonly cacheProfesionales = new Map<string, Observable<readonly Profesional[]>>();

  clinica(): Observable<RespuestaClinica> {
    this.cacheClinica ??= this.http
      .get<RespuestaClinica>(this.url('/catalogo/clinica'))
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

  especialidades(): Observable<readonly Especialidad[]> {
    this.cacheEspecialidades ??= this.http
      .get<readonly Especialidad[]>(this.url('/catalogo/especialidades'))
      .pipe(shareReplay({ bufferSize: 1, refCount: false }));
    return this.cacheEspecialidades;
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
  }

  private url(ruta: string): string {
    return `${this.configuracion.urlApi}${ruta}`;
  }
}
