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
}
