import { Component, DestroyRef, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient, HttpParams } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { catchError } from 'rxjs';
import { CONFIGURACION } from '../../nucleo/servicios/configuracion';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { traducirFallo } from '../../nucleo/servicios/api.service';
import { FondoIAComponent } from '../../compartido/fondo-ia.component';
import { type AnaliticaDashboard } from './analitica.modelos';
import { GraficoKpiComponent } from './grafico-kpi.component';

@Component({selector:'app-analitica',host:{class:'pantalla'},standalone:true,imports:[FormsModule,RouterLink,DatePipe,DecimalPipe,GraficoKpiComponent,FondoIAComponent],templateUrl:'./analitica.component.html',styleUrl:'./analitica.component.scss'})
export class AnaliticaComponent {
  private readonly http=inject(HttpClient);
  private readonly config=inject(CONFIGURACION);
  private readonly catalogo=inject(CatalogoService);
  private readonly destruir=inject(DestroyRef);
  protected readonly datos=signal<AnaliticaDashboard|null>(null);
  protected readonly error=signal('');
  protected readonly ocupado=signal(false);
  protected readonly tab=signal<'descriptivo'|'predictivo'|'prescriptivo'>('descriptivo');
  protected readonly sedes=signal<readonly {id:string;nombre:string}[]>([]);
  protected dias=180;
  protected horizonte=14;
  protected sede='';
  private secuencia=0;
  constructor(){this.catalogo.sedes().pipe(catchError(traducirFallo), takeUntilDestroyed(this.destruir)).subscribe({next:s=>this.sedes.set(s),error:()=>this.sedes.set([])});this.cargar();}
  protected cargar():void {
    const n=++this.secuencia;this.ocupado.set(true);this.error.set('');
    let params=new HttpParams().set('dias',this.dias).set('horizonte',this.horizonte);
    if(this.sede) params=params.set('sede_id',this.sede);
    this.http.get<AnaliticaDashboard>(`${this.config.urlApi}/dashboard/analitica`,{params}).pipe(catchError(traducirFallo), takeUntilDestroyed(this.destruir)).subscribe({
      next:d=>{if(n===this.secuencia){this.datos.set(d);this.ocupado.set(false);}},
      error:e=>{if(n===this.secuencia){this.error.set(e.message);this.ocupado.set(false);this.datos.set(null);}},
    });
  }
  protected estado(valor:string):string {return {insuficiente:'Falta historial',experimental:'En evaluación',validado_localmente:'Evaluado con datos locales'}[valor]??valor;}
}
