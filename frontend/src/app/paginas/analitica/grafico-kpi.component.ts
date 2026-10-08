import { Component, computed, input } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { type KpiAnalitico, rutaSerie } from './analitica.modelos';

@Component({selector:'app-grafico-kpi',standalone:true,imports:[DecimalPipe],template:`
  <figure>
    <figcaption><strong>{{kpi().nombre}}</strong><span>{{kpi().unidad}}</span></figcaption>
    <svg viewBox="0 0 600 220" role="img" [attr.aria-label]="'Serie histórica de '+kpi().nombre + (predictivo() ? ' y pronóstico' : '')">
      <title>{{kpi().definicion}}</title>
      @for(y of [32,81,131,180]; track y) {<line x1="32" x2="568" [attr.y1]="y" [attr.y2]="y" stroke="currentColor" opacity="0.12" />}
      <text x="32" y="20">{{maximo() | number:'1.0-1'}}</text><text x="12" y="184">0</text>
      @if(banda()) {<path [attr.d]="banda()" fill="#925bde" opacity=".16" />}
      <path [attr.d]="historico()" fill="none" stroke="#168a80" stroke-width="2.5" />
      @if(futuro()) {<path [attr.d]="futuro()" fill="none" stroke="#8252c9" stroke-width="2.5" stroke-dasharray="6 4" />}
      <text x="32" y="210">{{primeraFecha()}}</text><text x="568" y="210" text-anchor="end">{{ultimaFecha()}}</text>
    </svg>
    <p class="leyenda"><span>● Histórico</span>@if(predictivo() && kpi().prediccion.length) {<span>┄ Pronóstico · banda de error empírico</span>}</p>
    @if(!kpi().historia.length) {<p>Sin observaciones en este ámbito.</p>}
  </figure>
`,styles:`:host{display:block;min-width:0}figure{margin:0}figcaption{display:flex;justify-content:space-between;gap:1rem;font-size:.9rem}figcaption span{color:var(--texto-suave)}svg{width:100%;display:block;color:var(--texto-suave)}text{fill:currentColor;font-size:11px}.leyenda{display:flex;gap:1rem;flex-wrap:wrap;font-size:.72rem;color:var(--texto-suave);margin:0}`})
export class GraficoKpiComponent {
  readonly kpi=input.required<KpiAnalitico>();
  readonly predictivo=input(false);
  private readonly historia=computed(()=>this.kpi().historia.slice(-60));
  private readonly prediccion=computed(()=>this.predictivo()?this.kpi().prediccion:[]);
  private readonly total=computed(()=>this.historia().length+this.prediccion().length);
  protected readonly maximo=computed(()=>Math.max(1,...this.historia().map(p=>p.valor??0),...this.prediccion().map(p=>p.superior)));
  protected readonly historico=computed(()=>rutaSerie(this.historia().map(p=>p.valor),this.maximo(),0,this.total()));
  protected readonly futuro=computed(()=>rutaSerie(this.prediccion().map(p=>p.valor),this.maximo(),this.historia().length,this.total()));
  protected readonly primeraFecha=computed(()=>this.historia()[0]?.fecha??'');
  protected readonly ultimaFecha=computed(()=>this.prediccion().at(-1)?.fecha??this.historia().at(-1)?.fecha??'');
  protected readonly banda=computed(()=>{
    const p=this.prediccion(); if(!p.length) return '';
    const superior=rutaSerie(p.map(x=>x.superior),this.maximo(),this.historia().length,this.total());
    const puntos=p.map((x,i)=>`${(32+(this.historia().length+i)*536/Math.max(this.total()-1,1)).toFixed(1)},${(180-x.inferior/this.maximo()*148).toFixed(1)}`).reverse();
    return `${superior} L${puntos.join(' L')} Z`;
  });
}
