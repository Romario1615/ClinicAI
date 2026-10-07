/**
 * Manuales de ayuda de la sesión.
 *
 * La API devuelve solo los manuales de los roles vigentes de quien consulta,
 * ya filtrados por sus permisos: aquí no se decide qué puede ver nadie.
 */
import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, map } from 'rxjs';

import { traducirFallo } from '../../nucleo/servicios/api.service';
import { CONFIGURACION } from '../../nucleo/servicios/configuracion';

export interface PermisoManual {
  readonly codigo: string;
  readonly descripcion: string;
}

export interface SeccionManual {
  readonly clave: string;
  readonly titulo: string;
  readonly ruta: string | null;
  readonly proposito: string;
  readonly pasos: readonly string[];
  readonly limites: readonly string[];
  readonly permisos: readonly PermisoManual[];
}

export interface Manual {
  readonly rol_codigo: string;
  readonly rol_nombre: string;
  readonly tipo: 'SISTEMA' | 'PERSONALIZADO';
  readonly titulo: string;
  readonly introduccion: string;
  readonly responsabilidades: readonly string[];
  readonly limites: readonly string[];
  readonly secciones: readonly SeccionManual[];
}

@Injectable({ providedIn: 'root' })
export class AyudaService {
  private readonly http = inject(HttpClient);
  private readonly configuracion = inject(CONFIGURACION);

  manuales(): Observable<readonly Manual[]> {
    return this.http
      .get<{ manuales: readonly Manual[] }>(`${this.configuracion.urlApi}/ayuda/manuales`)
      .pipe(
        map((respuesta) => respuesta.manuales),
        catchError(traducirFallo),
      );
  }
}
