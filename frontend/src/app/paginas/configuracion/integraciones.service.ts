import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError } from 'rxjs';

import { CONFIGURACION } from '../../nucleo/servicios/configuracion';
import { traducirFallo } from '../../nucleo/servicios/api.service';

export interface EstadoIntegracion {
  readonly codigo: string;
  readonly habilitada: boolean;
  readonly ajustes: Record<string, string | number | boolean>;
  readonly secretos: Record<string, { readonly configurado: boolean }>;
  readonly version: number;
}

export interface ActualizacionIntegracion {
  readonly habilitada: boolean;
  readonly ajustes: Record<string, string | number | boolean>;
  readonly secretos: Record<string, string>;
  readonly eliminar_secretos: string[];
}

export interface DatosClinica {
  readonly id: string;
  nombre: string;
  identificacion_fiscal: string | null;
  zona_horaria: string;
  idioma: string;
  moneda: string;
  telefono: string | null;
  correo: string | null;
}

export interface DescansoHorario { readonly id?: string; hora_inicio: string; hora_fin: string; motivo: string | null; }
export interface HorarioSede {
  readonly id: string; dia_semana: number; hora_inicio: string; hora_fin: string;
  granularidad_minutos: number; vigente_desde: string | null; vigente_hasta: string | null;
  descansos: DescansoHorario[];
}
export interface FeriadoAgenda {
  readonly id: string; sede_id: string | null; fecha: string; nombre: string;
  recurrente_anual: boolean; hora_inicio: string | null; hora_fin: string | null;
}
export type DatosHorarioSede = Omit<HorarioSede, 'id' | 'descansos'> & { descansos: Omit<DescansoHorario, 'id'>[] };
export type DatosFeriadoAgenda = Omit<FeriadoAgenda, 'id'>;

@Injectable({ providedIn: 'root' })
export class IntegracionesService {
  private readonly http = inject(HttpClient);
  private readonly configuracion = inject(CONFIGURACION);

  clinica(): Observable<DatosClinica> {
    return this.http
      .get<DatosClinica>(`${this.configuracion.urlApi}/catalogo/clinica/configuracion`)
      .pipe(catchError(traducirFallo));
  }

  guardarClinica(datos: Omit<DatosClinica, 'id'>): Observable<DatosClinica> {
    return this.http
      .put<DatosClinica>(`${this.configuracion.urlApi}/catalogo/clinica`, datos)
      .pipe(catchError(traducirFallo));
  }

  listar(): Observable<EstadoIntegracion[]> {
    return this.http
      .get<EstadoIntegracion[]>(`${this.configuracion.urlApi}/configuracion/integraciones`)
      .pipe(catchError(traducirFallo));
  }

  guardar(codigo: string, datos: ActualizacionIntegracion): Observable<EstadoIntegracion> {
    return this.http
      .put<EstadoIntegracion>(
        `${this.configuracion.urlApi}/configuracion/integraciones/${codigo}`,
        datos,
      )
      .pipe(catchError(traducirFallo));
  }

  horarios(sedeId: string): Observable<HorarioSede[]> {
    return this.http.get<HorarioSede[]>(`${this.configuracion.urlApi}/configuracion/agenda/sedes/${encodeURIComponent(sedeId)}/horarios`).pipe(catchError(traducirFallo));
  }
  guardarHorario(sedeId: string, datos: DatosHorarioSede, id?: string): Observable<HorarioSede> {
    const url = id
      ? `${this.configuracion.urlApi}/configuracion/agenda/horarios/${encodeURIComponent(id)}`
      : `${this.configuracion.urlApi}/configuracion/agenda/sedes/${encodeURIComponent(sedeId)}/horarios`;
    return (id ? this.http.put<HorarioSede>(url, datos) : this.http.post<HorarioSede>(url, datos)).pipe(catchError(traducirFallo));
  }
  eliminarHorario(id: string): Observable<void> {
    return this.http.delete<void>(`${this.configuracion.urlApi}/configuracion/agenda/horarios/${encodeURIComponent(id)}`).pipe(catchError(traducirFallo));
  }
  feriados(sedeId: string, desde: string, hasta: string): Observable<FeriadoAgenda[]> {
    const consulta = new URLSearchParams({ sede_id: sedeId, desde, hasta });
    return this.http.get<FeriadoAgenda[]>(`${this.configuracion.urlApi}/configuracion/agenda/feriados?${consulta}`).pipe(catchError(traducirFallo));
  }
  guardarFeriado(datos: DatosFeriadoAgenda, id?: string): Observable<FeriadoAgenda> {
    const url = `${this.configuracion.urlApi}/configuracion/agenda/feriados${id ? `/${encodeURIComponent(id)}` : ''}`;
    return (id ? this.http.put<FeriadoAgenda>(url, datos) : this.http.post<FeriadoAgenda>(url, datos)).pipe(catchError(traducirFallo));
  }
  eliminarFeriado(id: string): Observable<void> {
    return this.http.delete<void>(`${this.configuracion.urlApi}/configuracion/agenda/feriados/${encodeURIComponent(id)}`).pipe(catchError(traducirFallo));
  }
}
