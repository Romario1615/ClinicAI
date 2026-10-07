import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError } from 'rxjs';

import { CONFIGURACION } from './configuracion';
import { traducirFallo } from './api.service';

export interface Pago {
  id: string; cita_id: string; cargo_id: string | null; importe: string; moneda: string; metodo: string;
  estado: string; referencia: string | null; comentario: string | null;
  validado_en: string | null; total_acordado?: string | null; total_confirmado?: string | null;
  saldo_pendiente?: string | null; saldo_no_asignado?: string | null;
}

export interface CargoPago {
  readonly id: string;
  readonly cita_id: string;
  readonly total_acordado: string | null;
  readonly fecha_vencimiento: string | null;
  readonly vencido: boolean;
  readonly moneda: 'USD';
  readonly origen: 'PACTADO' | 'HISTORICO_SIN_TOTAL';
  readonly creado_en: string;
  readonly paciente: string | null;
  readonly cita_inicio: string | null;
  readonly total_confirmado: string;
  readonly total_comprometido: string;
  readonly saldo_pendiente: string | null;
  readonly saldo_no_asignado: string | null;
}

export interface EventoHistorialPago {
  id: string;
  estado_anterior: string | null;
  estado_nuevo: string;
  comentario: string | null;
  actor_id: string | null;
  ocurrido_en: string;
}

export interface ComprobantePago {
  readonly id: string;
  readonly pago_id: string;
  readonly tipo_mime: 'application/pdf' | 'image/jpeg' | 'image/png' | 'image/webp';
  readonly tamano_bytes: number;
  readonly antivirus: 'LIMPIO' | 'NO_DISPONIBLE';
  readonly cargado_por: string;
  readonly cargado_en: string;
  readonly url_contenido: string;
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
  total_citas: number; pacientes: number; pacientes_nuevos: number | null; pacientes_recurrentes: number | null; citas: Record<string, number>;
  tendencia_diaria: { fecha: string; total: number }[];
  por_hora: { hora: number; total: number }[];
  por_dia_semana: { dia: number; total: number }[];
  espera: {
    promedio_minutos: number | null;
    personas_en_espera: number;
    espera_mayor_15_minutos: number;
  };
  recuperacion_turnos: {
    turnos_liberados: number | null;
    turnos_recuperados: number | null;
    promedio_minutos_para_recuperar: number | null;
  };
  adherencia: {
    tomas_confirmadas: number;
    tomas_omitidas: number;
    porcentaje_registro_positivo: number | null;
    seguimientos_pendientes: number;
  } | null;
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

  /** Cambio parcial (PATCH): anulaciones y transiciones con motivo. */
  cambiar<T>(ruta: string, datos: unknown): Observable<T> {
    return this.http.patch<T>(this.configuracion.urlApi + ruta, datos).pipe(catchError(traducirFallo));
  }

  guardar<T>(ruta: string, datos: unknown, clave: string, editar = false): Observable<T> {
    const opciones = { headers: { 'Idempotency-Key': clave } };
    const url = this.configuracion.urlApi + ruta;
    return (editar ? this.http.put<T>(url, datos, opciones) : this.http.post<T>(url, datos, opciones))
      .pipe(catchError(traducirFallo));
  }

  subirComprobante(pagoId: string, archivo: File): Observable<ComprobantePago> {
    const formulario = new FormData();
    formulario.append('archivo', archivo, archivo.name);
    return this.http
      .post<ComprobantePago>(
        `${this.configuracion.urlApi}/pagos/${pagoId}/comprobantes`,
        formulario,
      )
      .pipe(catchError(traducirFallo));
  }

  descargarComprobante(comprobanteId: string): Observable<Blob> {
    return this.http
      .get(`${this.configuracion.urlApi}/pagos/comprobantes/${comprobanteId}/contenido`, {
        responseType: 'blob',
      })
      .pipe(catchError(traducirFallo));
  }

  descargarReportePagos(desde: string, hasta: string, sedeId?: string): Observable<Blob> {
    const parametros: Record<string, string> = { desde, hasta };
    if (sedeId) parametros['sede_id'] = sedeId;
    return this.http
      .get(`${this.configuracion.urlApi}/pagos/resumen.csv`, {
        params: parametros,
        responseType: 'blob',
      })
      .pipe(catchError(traducirFallo));
  }
}
