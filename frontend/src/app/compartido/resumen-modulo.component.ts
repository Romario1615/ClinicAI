/**
 * Cabecera de indicadores de un módulo.
 *
 * Se coloca arriba de cada pantalla con `<app-resumen-modulo modulo="pagos" />`.
 * Si el rol no alcanza el módulo, o el panel no responde, no ocupa espacio:
 * un indicador ausente es mejor que un cero que no es verdad.
 */
import { Component, DestroyRef, computed, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { IndicadoresService, type Indicadores } from '../nucleo/servicios/indicadores.service';
import { indicadoresDe, type ModuloIndicadores } from '../nucleo/utilidades/indicadores';
import { TarjetasIndicadoresComponent } from './tarjetas-indicadores.component';

@Component({
  selector: 'app-resumen-modulo',
  standalone: true,
  imports: [TarjetasIndicadoresComponent],
  template: `<app-tarjetas-indicadores [indicadores]="tarjetas()" [titulo]="'Resumen'" />`,
  styles: `:host { display: block; margin-bottom: var(--espacio-4); } :host:empty { display: none; }`,
})
export class ResumenModuloComponent {
  readonly modulo = input.required<ModuloIndicadores>();

  private readonly datos = signal<Indicadores | null>(null);
  protected readonly tarjetas = computed(() => indicadoresDe(this.datos(), this.modulo()));

  constructor() {
    inject(IndicadoresService)
      .obtener()
      .pipe(takeUntilDestroyed(inject(DestroyRef)))
      .subscribe({ next: (datos) => this.datos.set(datos), error: () => this.datos.set(null) });
  }
}
