import { Component, input, ChangeDetectionStrategy } from '@angular/core';

@Component({
  selector: 'app-marca',
  standalone: true,
  template: `
    <span
      class="marca"
      [class.marca--clara]="fondoClaro()"
      [class.marca--compacta]="compacta()"
    >
      <img class="marca__simbolo" src="/images/clinicai-simbolo.svg" alt="" />
      <span class="marca__texto">
        <span class="marca__nombre">Clinic<span class="marca__ai">AI</span></span>
        @if (!compacta()) {
          <span class="marca__descriptor">Gestión clínica</span>
        }
      </span>
    </span>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    :host { display: inline-flex; min-width: 0; }
    .marca { display: inline-flex; align-items: center; gap: 11px; color: #fff; }
    .marca--clara { color: var(--texto); }
    .marca__simbolo { display: block; width: 44px; height: 44px; flex: 0 0 auto; }
    .marca__texto { display: flex; flex-direction: column; line-height: 1.08; }
    .marca__nombre { font-size: 1.26rem; font-weight: 800; letter-spacing: -0.045em; white-space: nowrap; }
    .marca__ai { color: var(--marca-brillo); }
    .marca--clara .marca__ai { color: var(--acento); }
    .marca__descriptor { margin-top: 4px; color: var(--marca-tenue); font-size: 0.68rem; font-weight: 650; letter-spacing: 0.12em; text-transform: uppercase; }
    .marca--clara .marca__descriptor { color: var(--texto-suave); }
    .marca--compacta .marca__simbolo { width: 36px; height: 36px; }
    .marca--compacta .marca__nombre { font-size: 1.05rem; }
  `,
})
export class MarcaComponent {
  readonly compacta = input(false);
  readonly fondoClaro = input(false);
}
