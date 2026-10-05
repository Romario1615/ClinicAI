/**
 * Indicadores del panel y de cada módulo.
 *
 * El backend devuelve solo los bloques que el rol alcanza (`null` en los
 * demás). Se piden una vez por día y zona y se comparten entre el panel y
 * las cabeceras de los módulos, para no repetir la consulta en cada pantalla.
 * `refrescar()` fuerza una lectura nueva tras una acción que los cambia.
 */
import { Injectable, inject } from '@angular/core';
import { Observable, shareReplay } from 'rxjs';

import { OperacionesService } from './operaciones.service';
import { rangoDelDia, hoyEnZona } from '../utilidades/fechas';

export interface Indicadores {
  readonly agenda: {
    citas_hoy: number;
    por_confirmar_hoy: number;
    en_sala: number;
    en_atencion: number;
    atendidas_hoy: number;
    inasistencias_hoy: number;
    citas_proximos_7_dias: number;
  } | null;
  readonly mis_citas: { citas_hoy: number; pendientes_hoy: number; proxima_inicio: string | null } | null;
  readonly pacientes: { total: number; nuevos_30_dias: number; sin_verificar: number; sin_whatsapp: number } | null;
  readonly lista_espera: { en_espera: number; con_oferta: number } | null;
  readonly pagos: { pendientes: number; por_validar: number; confirmado_30_dias: string } | null;
  readonly clinico: { recetas_por_confirmar: number; planes_propuestos: number; planes_en_curso: number } | null;
  readonly adherencia: { alertas_abiertas: number } | null;
  readonly mensajes: { derivadas_a_persona: number; abiertas: number } | null;
  readonly conocimiento: { borradores: number; en_revision: number; vigentes: number } | null;
  readonly promociones: { borradores: number; aprobadas_sin_enviar: number; enviadas_30_dias: number } | null;
  readonly usuarios: { activos: number; inactivos: number; roles: number } | null;
}

@Injectable({ providedIn: 'root' })
export class IndicadoresService {
  private readonly operaciones = inject(OperacionesService);
  private cache: { clave: string; datos: Observable<Indicadores> } | null = null;

  obtener(zona = 'America/Guayaquil'): Observable<Indicadores> {
    const { desde, hasta } = rangoDelDia(hoyEnZona(zona), zona);
    const clave = `${desde}|${hasta}`;
    if (!this.cache || this.cache.clave !== clave) {
      this.cache = {
        clave,
        datos: this.operaciones
          .leer<Indicadores>('/dashboard/indicadores', { desde, hasta })
          .pipe(shareReplay({ bufferSize: 1, refCount: false })),
      };
    }
    return this.cache.datos;
  }

  refrescar(): void {
    this.cache = null;
  }
}
