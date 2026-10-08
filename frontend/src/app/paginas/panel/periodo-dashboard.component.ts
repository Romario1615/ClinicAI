import { Component, input, output } from '@angular/core';

@Component({
  selector: 'app-periodo-dashboard', standalone: true,
  template: `<div class="periodos" role="group" aria-label="Periodo">
    @for (opcion of opciones; track opcion.clave) {
      <button type="button" class="periodos__boton" [class.periodos__boton--activo]="periodo()===opcion.clave"
        [attr.aria-pressed]="periodo()===opcion.clave" (click)="cambiado.emit(opcion.clave)">{{opcion.etiqueta}}</button>
    }
  </div>`,
  styles: `:host{display:block}.periodos{display:flex;gap:var(--espacio-1);padding:3px;border:1px solid var(--borde);border-radius:var(--radio);background:var(--superficie-elevada)}
  .periodos__boton{white-space:nowrap;min-height:34px;padding:0 var(--espacio-3);border:0;border-radius:var(--radio-pequeno);background:transparent;color:var(--texto-suave);font-weight:600;font-size:.9rem;cursor:pointer}
  .periodos__boton--activo{background:var(--acento);color:var(--acento-texto)}`,
})
export class PeriodoDashboardComponent {
  readonly periodo = input('hoy');
  readonly cambiado = output<string>();
  protected readonly opciones = [
    { clave: 'hoy', etiqueta: 'Hoy' }, { clave: '7', etiqueta: '7 días' }, { clave: '30', etiqueta: '30 días' },
  ];
}
