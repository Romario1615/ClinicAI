import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError } from 'rxjs';

import { CONFIGURACION } from './configuracion';
import { traducirFallo } from './api.service';

export interface Pago {
  id: string; cita_id: string; importe: string; moneda: string; metodo: string;
  estado: string; referencia: string | null; comentario: string | null;
  validado_en: string | null;
}

export interface EntradaEspera {
  id: string; paciente_id: string; sede_id: string; especialidad_id: string; servicio_id: string;
  profesional_id: string | null; prioridad: string; estado: string;
  horas_antelacion_minima: number; disponible_desde: string | null; disponible_hasta: string | null;
  preferencias: { dias_semana: number[]; hora_desde: string | null; hora_hasta: string | null } | null;
  cita_previa_id: string | null; cita_resultante_id: string | null;
  oferta_id: string | null;
  oferta_inicio: string | null; oferta_expira_en: string | null;
  /**
   * Si al paciente se le pudo avisar del turno por un canal automatico.
   *
   * `null` cuando no hay oferta activa. `false` significa que hay un turno
   * reservado para el que **no sabe nada**: alguien tiene que llamarle antes
   * de que la oferta venza y el hueco vuelva a la cola.
   */
  oferta_avisada: boolean | null;
}

export interface ResumenPanel {
  total_citas: number; pacientes: number; citas: Record<string, number>;
  espera: {
    promedio_minutos: number | null;
    personas_en_espera: number;
    espera_mayor_15_minutos: number;
  };
  pagos: Record<string, string> | null;
}

export interface Pagina<T> { elementos: T[]; total: number }

@Injectable({ providedIn: 'root' })
export class OperacionesService {
  private readonly http = inject(HttpClient);
  private readonly configuracion = inject(CONFIGURACION);

  leer<T>(ruta: string, parametros: Record<string, string | number | boolean> = {}): Observable<T> {
    return this.http.get<T>(this.configuracion.urlApi + ruta, { params: parametros })
      .pipe(catchError(traducirFallo));
  }

  analizar<T>(ruta: string, parametros: Record<string, string | number | boolean> = {}): Observable<T> {
    return this.http.post<T>(this.configuracion.urlApi + ruta, null, { params: parametros })
      .pipe(catchError(traducirFallo));
  }

  guardar<T>(ruta: string, datos: unknown, clave: string, editar = false): Observable<T> {
    const opciones = { headers: { 'Idempotency-Key': clave } };
    const url = this.configuracion.urlApi + ruta;
    return (editar ? this.http.put<T>(url, datos, opciones) : this.http.post<T>(url, datos, opciones))
      .pipe(catchError(traducirFallo));
  }
}
