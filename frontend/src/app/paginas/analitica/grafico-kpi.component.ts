import { Component, computed, input } from '@angular/core';
import { DatePipe, DecimalPipe, registerLocaleData } from '@angular/common';
import localeEs from '@angular/common/locales/es';
import { type KpiAnalitico, rutaSerie } from './analitica.modelos';

registerLocaleData(localeEs);

@Component({
  selector: 'app-grafico-kpi', standalone: true, imports: [DatePipe, DecimalPipe],
  template: `
    <figure>
      @if(mostrarTitulo()) {<figcaption><strong>{{kpi().nombre}}</strong><span>{{kpi().unidad}}</span></figcaption>}
      @if(hayObservaciones() || prediccion().length) {
        <svg viewBox="0 0 600 220" role="img" [attr.aria-label]="'Serie histórica de ' + kpi().nombre + (predictivo() ? ' y pronóstico' : '')">
          <title>{{kpi().definicion}}</title>
          @for(y of [32,81,131,180]; track y) {<line x1="32" x2="568" [attr.y1]="y" [attr.y2]="y" stroke="currentColor" opacity="0.13" stroke-dasharray="3 5" />}
          <text x="32" y="20">{{maximo() | number:'1.0-1'}}</text><text x="8" y="184">0</text>
          @if(banda()) {<path [attr.d]="banda()" fill="#7852b8" opacity=".14" />}
          @if(predictivo() && prediccion().length) {<line [attr.x1]="inicioPronostico()" [attr.x2]="inicioPronostico()" y1="32" y2="180" stroke="#7852b8" opacity=".45" stroke-dasharray="3 5" />}
          <path [attr.d]="historico()" fill="none" stroke="#177d77" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
          @for(p of puntosVisibles(); track p.indice) {<circle [attr.cx]="p.x" [attr.cy]="p.y" r="4" fill="#177d77"><title>{{p.fecha}} · {{p.valor}} {{kpi().unidad}}</title></circle>}
          @if(futuro()) {<path [attr.d]="futuro()" fill="none" stroke="#7852b8" stroke-width="3" stroke-dasharray="6 5" stroke-linecap="round" />}
          @if(ultimoPronostico(); as p) {<circle [attr.cx]="p.x" [attr.cy]="p.y" r="4" fill="#7852b8" />}
          <text x="32" y="210">{{primeraFecha() | date:'d MMM':'UTC':'es'}}</text><text x="568" y="210" text-anchor="end">{{ultimaFecha() | date:'d MMM':'UTC':'es'}}</text>
        </svg>
        <p class="leyenda"><span><i class="leyenda__historico" aria-hidden="true"></i>Histórico</span>@if(predictivo() && prediccion().length) {<span><i class="leyenda__pronostico" aria-hidden="true"></i>Pronóstico</span><span><i class="leyenda__banda" aria-hidden="true"></i>Banda empírica</span>}@if(kpi().historia.length > 60){<span>Últimos 60 días del historial</span>}</p>
      } @else {
        <div class="grafico-vacio"><span aria-hidden="true">—</span><p>Sin observaciones en este ámbito.</p><small>Los días sin mediciones no se representan como cero.</small></div>
      }
    </figure>
  `,
  styles: `
    :host{display:block;min-width:0}figure{margin:0}figcaption{display:flex;justify-content:space-between;gap:16px;margin-bottom:12px;font-size:.85rem}figcaption span{color:var(--texto-suave)}
    svg{width:100%;display:block;color:var(--texto-suave)}text{fill:currentColor;font-size:15px;font-variant-numeric:tabular-nums}
    .leyenda{display:flex;align-items:center;gap:8px 14px;flex-wrap:wrap;font-size:.65rem;color:var(--texto-suave);margin:8px 0 0;line-height:1.5}
    .leyenda span{display:inline-flex;align-items:center;gap:5px}.leyenda i{display:inline-block;width:14px;flex:none}.leyenda__historico{border-top:2px solid #177d77}.leyenda__pronostico{border-top:2px dashed #7852b8}.leyenda__banda{height:7px;border:1px solid #7852b8;border-radius:2px;background:#7852b830}
    .grafico-vacio{display:grid;align-content:center;justify-items:center;min-height:124px;gap:8px;padding:16px;border-radius:10px;border:1px dashed var(--borde-fuerte);background:var(--superficie);color:var(--texto-suave);text-align:center}.grafico-vacio span{font-size:1.3rem}.grafico-vacio p{margin:0;font-size:.75rem}.grafico-vacio small{font-size:.66rem}
  `,
})
export class GraficoKpiComponent {
  readonly kpi = input.required<KpiAnalitico>();
  readonly predictivo = input(false);
  readonly mostrarTitulo = input(true);
  private readonly historia = computed(() => this.kpi().historia.slice(-60));
  protected readonly prediccion = computed(() => this.predictivo() ? this.kpi().prediccion : []);
  private readonly total = computed(() => this.historia().length + this.prediccion().length);
  protected readonly hayObservaciones = computed(() => this.historia().some(p => p.valor !== null));
  protected readonly maximo = computed(() => Math.max(1, ...this.historia().map(p => p.valor ?? 0), ...this.prediccion().map(p => p.superior)));
  protected readonly historico = computed(() => rutaSerie(this.historia().map(p => p.valor), this.maximo(), 0, this.total()));
  protected readonly futuro = computed(() => {
    if (!this.prediccion().length) return '';
    // Conecta solo con el último día histórico si fue observado; conserva huecos.
    const ultimo = this.historia().at(-1);
    return ultimo ? rutaSerie([ultimo.valor, ...this.prediccion().map(p => p.valor)], this.maximo(), this.historia().length - 1, this.total())
      : rutaSerie(this.prediccion().map(p => p.valor), this.maximo(), 0, this.total());
  });
  protected readonly primeraFecha = computed(() => this.historia()[0]?.fecha ?? this.prediccion()[0]?.fecha ?? '');
  protected readonly ultimaFecha = computed(() => this.prediccion().at(-1)?.fecha ?? this.historia().at(-1)?.fecha ?? '');
  protected readonly inicioPronostico = computed(() => this.x(this.historia().length));
  protected readonly puntosVisibles = computed(() => this.historia().flatMap((p, i, historia) =>
    p.valor !== null && (i === historia.length - 1 ||
      ((i === 0 || historia[i - 1].valor === null) && (i === historia.length - 1 || historia[i + 1].valor === null)))
      ? [{ indice: i, fecha: p.fecha, valor: p.valor, x: this.x(i), y: this.y(p.valor) }] : []));
  protected readonly ultimoPronostico = computed(() => {
    const p = this.prediccion().at(-1);
    return p ? { x: this.x(this.total() - 1), y: this.y(p.valor) } : null;
  });
  protected readonly banda = computed(() => {
    const p = this.prediccion();
    if (!p.length) return '';
    const superior = rutaSerie(p.map(x => x.superior), this.maximo(), this.historia().length, this.total());
    const puntos = p.map((x, i) => `${this.x(this.historia().length + i).toFixed(1)},${this.y(x.inferior).toFixed(1)}`).reverse();
    return `${superior} L${puntos.join(' L')} Z`;
  });
  private x(indice: number): number { return 32 + indice * 536 / Math.max(this.total() - 1, 1); }
  private y(valor: number): number { return 180 - valor / this.maximo() * 148; }
}
