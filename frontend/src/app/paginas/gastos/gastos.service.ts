/**
 * Libro de gastos y flujo de caja.
 *
 * El servidor aplica el permiso y el ámbito; aquí solo se habla con la API.
 * El alta lleva clave de idempotencia: un doble clic no puede duplicar un
 * egreso.
 */
import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError } from 'rxjs';

import { traducirFallo } from '../../nucleo/servicios/api.service';
import { CONFIGURACION } from '../../nucleo/servicios/configuracion';

export const CATEGORIAS_GASTO = [
  { codigo: 'INSUMOS', etiqueta: 'Insumos' },
  { codigo: 'LABORATORIO', etiqueta: 'Laboratorio' },
  { codigo: 'NOMINA', etiqueta: 'Nómina' },
  { codigo: 'HONORARIOS', etiqueta: 'Honorarios' },
  { codigo: 'ARRIENDO', etiqueta: 'Arriendo' },
  { codigo: 'SERVICIOS_BASICOS', etiqueta: 'Servicios básicos' },
  { codigo: 'MANTENIMIENTO', etiqueta: 'Mantenimiento' },
  { codigo: 'EQUIPAMIENTO', etiqueta: 'Equipamiento' },
  { codigo: 'MARKETING', etiqueta: 'Marketing' },
  { codigo: 'IMPUESTOS', etiqueta: 'Impuestos' },
  { codigo: 'OTROS', etiqueta: 'Otros' },
] as const;

export type CategoriaGasto = (typeof CATEGORIAS_GASTO)[number]['codigo'];
export type MetodoGasto = 'EFECTIVO' | 'TRANSFERENCIA' | 'TARJETA';

export interface Gasto {
  readonly id: string;
  readonly sede_id: string | null;
  readonly fecha: string;
  readonly categoria: CategoriaGasto;
  readonly descripcion: string;
  readonly proveedor: string | null;
  readonly importe: string;
  readonly moneda: string;
  readonly metodo: MetodoGasto;
  readonly referencia: string | null;
  readonly estado: 'REGISTRADO' | 'ANULADO';
  readonly creado_en: string;
  readonly anulado_en: string | null;
  readonly motivo_anulacion: string | null;
}

export interface PaginaGastos {
  readonly elementos: readonly Gasto[];
  readonly total: number;
  readonly importe_total: string;
}

export interface DatosGasto {
  readonly sede_id: string | null;
  readonly fecha: string;
  readonly categoria: CategoriaGasto;
  readonly descripcion: string;
  readonly proveedor: string | null;
  readonly importe: string;
  readonly metodo: MetodoGasto;
  readonly referencia: string | null;
}

export interface FlujoCaja {
  readonly desde: string;
  readonly hasta: string;
  readonly moneda: string;
  readonly ingresos: string;
  readonly gastos: string;
  readonly resultado: string;
  readonly margen_porcentaje: string | null;
  readonly por_dia: readonly { fecha: string; ingresos: string; gastos: string; resultado: string }[];
  readonly por_categoria: readonly { categoria: CategoriaGasto; total: string; cantidad: number }[];
  readonly base: string;
}

export interface FiltroGastos {
  readonly desde: string;
  /** Exclusivo, como en el resto de reportes financieros. */
  readonly hasta: string;
  readonly sede_id?: string | null;
  readonly categoria?: CategoriaGasto | null;
  readonly incluir_anulados?: boolean;
  readonly limite?: number;
  readonly desplazamiento?: number;
}

function parametros(filtro: FiltroGastos): HttpParams {
  let params = new HttpParams().set('desde', filtro.desde).set('hasta', filtro.hasta);
  if (filtro.sede_id) params = params.set('sede_id', filtro.sede_id);
  if (filtro.categoria) params = params.set('categoria', filtro.categoria);
  if (filtro.incluir_anulados) params = params.set('incluir_anulados', 'true');
  if (filtro.limite) params = params.set('limite', String(filtro.limite));
  if (filtro.desplazamiento) params = params.set('desplazamiento', String(filtro.desplazamiento));
  return params;
}

@Injectable({ providedIn: 'root' })
export class GastosService {
  private readonly http = inject(HttpClient);
  private readonly base = `${inject(CONFIGURACION).urlApi}/gastos`;

  listar(filtro: FiltroGastos): Observable<PaginaGastos> {
    return this.http.get<PaginaGastos>(this.base, { params: parametros(filtro) }).pipe(catchError(traducirFallo));
  }

  flujo(filtro: Pick<FiltroGastos, 'desde' | 'hasta' | 'sede_id'>): Observable<FlujoCaja> {
    return this.http
      .get<FlujoCaja>(`${this.base}/flujo`, { params: parametros(filtro) })
      .pipe(catchError(traducirFallo));
  }

  registrar(datos: DatosGasto, clave: string): Observable<Gasto> {
    return this.http
      .post<Gasto>(this.base, datos, { headers: { 'Idempotency-Key': clave } })
      .pipe(catchError(traducirFallo));
  }

  anular(id: string, motivo: string): Observable<Gasto> {
    return this.http
      .post<Gasto>(`${this.base}/${encodeURIComponent(id)}/anulacion`, { motivo })
      .pipe(catchError(traducirFallo));
  }
}
