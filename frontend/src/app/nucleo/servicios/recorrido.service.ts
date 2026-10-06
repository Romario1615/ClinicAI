/**
 * Recorrido del paciente en la clínica, derivación interna y prolongación.
 *
 * El backend decide y audita; aquí solo se llaman sus rutas y se traducen
 * los errores a un mensaje para la persona.
 */
import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, catchError, throwError } from 'rxjs';

import { CONFIGURACION } from './configuracion';
import type { Cita } from '../modelos/dominio';

export interface PasoRecorrido {
  readonly ocurrido_en: string;
  readonly evento: string;
  readonly titulo: string;
  readonly detalle: string | null;
  readonly cita_id: string;
  readonly servicio: string | null;
  readonly profesional: string | null;
  readonly consultorio: string | null;
  readonly sede: string | null;
  readonly registrado_por: string | null;
}

export interface OpcionDerivacion {
  readonly profesional_id: string;
  readonly profesional: string;
  readonly servicio_id: string;
  readonly servicio: string;
  readonly especialidad: string;
  readonly libre_ahora: boolean;
  readonly proximo_turno: string | null;
}

export interface AlternativaTurno {
  readonly profesional_id: string;
  readonly profesional: string;
  readonly inicio: string;
  readonly mismo_profesional: boolean;
}

export interface CitaAfectada {
  readonly cita_id: string;
  readonly paciente: string;
  readonly inicio: string;
  readonly llego: boolean;
  readonly alternativas: readonly AlternativaTurno[];
}

export interface ResultadoProlongacion {
  readonly cita_id: string;
  readonly aplicada: boolean;
  readonly minutos: number;
  readonly fin: string;
  readonly conflictos: readonly CitaAfectada[];
}

export interface PeticionTiempo {
  readonly cita_id: string;
  readonly paciente: string;
  readonly profesional: string;
  readonly minutos: number;
  readonly solicitada_en: string;
  readonly fin_actual: string;
  readonly conflictos: readonly CitaAfectada[];
}

export interface DecisionAfectada {
  readonly cita_id: string;
  readonly inicio: string;
  readonly profesional_id: string | null;
}

/** Error del API reducido a lo que se muestra. */
export class FalloRecorrido extends Error {}

@Injectable({ providedIn: 'root' })
export class RecorridoService {
  private readonly http = inject(HttpClient);
  private readonly base = inject(CONFIGURACION).urlApi + '/agenda';

  recorrido(pacienteId: string): Observable<readonly PasoRecorrido[]> {
    return this.con(this.http.get<readonly PasoRecorrido[]>(`${this.base}/pacientes/${pacienteId}/recorrido`));
  }

  ingresoConsultorio(citaId: string, consultorioId: string): Observable<Cita> {
    return this.con(this.http.post<Cita>(`${this.base}/citas/${citaId}/consultorio`, { consultorio_id: consultorioId }));
  }

  salida(citaId: string): Observable<Cita> {
    return this.con(this.http.post<Cita>(`${this.base}/citas/${citaId}/salida`, {}));
  }

  opcionesDerivacion(citaId: string): Observable<readonly OpcionDerivacion[]> {
    return this.con(this.http.get<readonly OpcionDerivacion[]>(`${this.base}/citas/${citaId}/derivacion/opciones`));
  }

  derivar(citaId: string, opcion: { profesional_id: string; servicio_id: string; inicio: string | null }): Observable<Cita> {
    return this.con(this.http.post<Cita>(`${this.base}/citas/${citaId}/derivacion`, opcion));
  }

  pedirTiempo(citaId: string, minutos: number): Observable<ResultadoProlongacion> {
    return this.con(this.http.post<ResultadoProlongacion>(`${this.base}/citas/${citaId}/prolongacion`, { minutos }));
  }

  pendientes(): Observable<readonly PeticionTiempo[]> {
    return this.con(this.http.get<readonly PeticionTiempo[]>(`${this.base}/prolongaciones`));
  }

  opcionesTiempo(citaId: string): Observable<PeticionTiempo> {
    return this.con(this.http.get<PeticionTiempo>(`${this.base}/citas/${citaId}/prolongacion/opciones`));
  }

  resolver(
    citaId: string,
    cuerpo: { aprobar: boolean; resoluciones?: readonly DecisionAfectada[]; motivo_rechazo?: string },
  ): Observable<ResultadoProlongacion> {
    return this.con(this.http.post<ResultadoProlongacion>(`${this.base}/citas/${citaId}/prolongacion/resolucion`, cuerpo));
  }

  private con<T>(peticion: Observable<T>): Observable<T> {
    return peticion.pipe(
      catchError((fallo: HttpErrorResponse) =>
        throwError(
          () => new FalloRecorrido((fallo.error as { mensaje?: string } | null)?.mensaje ?? 'No se pudo completar la acción.'),
        ),
      ),
    );
  }
}
