import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { CONFIGURACION } from '../../nucleo/servicios/configuracion';

export interface FranjaProfesional {
  readonly id: string;
  readonly profesional_id: string;
  readonly sede_id: string;
  readonly dia_semana: number;
  readonly hora_inicio: string;
  readonly hora_fin: string;
  readonly granularidad_minutos: number;
  readonly vigente_desde: string | null;
  readonly vigente_hasta: string | null;
}

export interface DatosFranjaProfesional {
  readonly dia_semana: number;
  readonly hora_inicio: string;
  readonly hora_fin: string;
  readonly granularidad_minutos: number;
  readonly vigente_desde: string | null;
  readonly vigente_hasta: string | null;
}

@Injectable({ providedIn: 'root' })
export class AgendaProfesionalesService {
  private readonly http = inject(HttpClient);
  private readonly config = inject(CONFIGURACION);

  listar(profesionalId: string, sedeId: string): Observable<readonly FranjaProfesional[]> {
    return this.http.get<readonly FranjaProfesional[]>(this.url(profesionalId, sedeId));
  }

  crear(profesionalId: string, sedeId: string, datos: DatosFranjaProfesional): Observable<FranjaProfesional> {
    return this.http.post<FranjaProfesional>(this.url(profesionalId, sedeId), datos);
  }

  actualizar(profesionalId: string, sedeId: string, id: string, datos: DatosFranjaProfesional): Observable<FranjaProfesional> {
    return this.http.put<FranjaProfesional>(this.url(profesionalId, sedeId, id), datos);
  }

  eliminar(profesionalId: string, sedeId: string, id: string): Observable<void> {
    return this.http.delete<void>(this.url(profesionalId, sedeId, id));
  }

  private url(profesionalId: string, sedeId: string, franjaId?: string): string {
    const segmento = franjaId ? `/${encodeURIComponent(franjaId)}` : '';
    return `${this.config.urlApi}/profesionales/${encodeURIComponent(profesionalId)}/agenda${segmento}?sede_id=${encodeURIComponent(sedeId)}`;
  }
}
