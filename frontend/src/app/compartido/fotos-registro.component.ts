import { Component, DestroyRef, effect, inject, input, signal, untracked, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { FotosRegistroService, type FotoRegistro } from '../nucleo/servicios/fotos-registro.service';
import { CapturaFotosComponent, type FotoSeleccionada } from './captura-fotos.component';
import { VentanaFlotanteComponent } from './ventana-flotante.component';

@Component({selector:'app-fotos-registro',standalone:true,imports:[FormsModule,CapturaFotosComponent,VentanaFlotanteComponent],template:`
  <button class="boton boton--pequeno" type="button" (click)="abierta.set(true)">Fotos y adjuntos</button>
  @if(abierta()){<app-ventana-flotante titulo="Fotos del registro" [ocupada]="ocupado()" (cerrar)="abierta.set(false)">
  <section aria-label="Fotografías del registro"><h3>Fotografías y adjuntos visuales</h3>
    @if(error()){<p role="alert">{{error()}}</p>}
    <div class="fotos-registro">@for(f of fotos();track f.id){<figure>@if(urls().get(f.id);as url){<a [href]="url" target="_blank" rel="noopener" [attr.aria-label]="'Ampliar '+(f.descripcion || 'fotografía')"><img [src]="url" [alt]="f.descripcion || 'Fotografía del registro'" /></a>}<figcaption>{{f.descripcion || 'Sin descripción'}}</figcaption>@if(puedeEditar()){<button class="boton" type="button" (click)="retirando.set(f.id)" [disabled]="ocupado()">Retirar con motivo</button>}</figure>}@empty{<p>Aún no hay fotos adjuntas.</p>}</div>
    @if(retirando()){<label>Motivo para retirar<input [(ngModel)]="motivo" [ngModelOptions]="{standalone:true}" minlength="8" maxlength="500" /></label><button type="button" class="boton" [disabled]="ocupado() || motivo.trim().length<8" (click)="retirar()">Confirmar retirada</button><button type="button" class="boton" (click)="retirando.set(null)">Cancelar</button>}
    @if(puedeEditar()){<app-captura-fotos [ocupada]="ocupado()" (cambiadas)="pendientes=$event" /><button type="button" class="boton" [disabled]="ocupado() || !pendientes.length" (click)="guardar()">{{ocupado()?'Guardando…':'Guardar fotos'}}</button>}
  </section>
  </app-ventana-flotante>}
`,styles:`:host{display:block;min-width:0}section{display:grid;gap:.8rem}.fotos-registro{display:flex;gap:.8rem;flex-wrap:wrap}.fotos-registro figure{margin:0;display:grid;gap:.4rem;max-width:200px}.fotos-registro img{width:160px;height:120px;object-fit:contain;background:var(--superficie-hundida);border-radius:.7rem}.fotos-registro figcaption{font-size:.8rem;overflow-wrap:anywhere}label{display:grid;gap:.4rem}`})
export class FotosRegistroComponent {
  private readonly api=inject(FotosRegistroService);
  private readonly destruir=inject(DestroyRef);
  readonly tipo=input.required<string>();readonly registroId=input.required<string>();readonly puedeEditar=input(false);
  protected readonly abierta=signal(false);
  private readonly captura=viewChild(CapturaFotosComponent);
  protected readonly fotos=signal<readonly FotoRegistro[]>([]);protected readonly urls=signal<ReadonlyMap<string,string>>(new Map());protected readonly error=signal('');protected readonly ocupado=signal(false);protected readonly retirando=signal<string|null>(null);
  protected pendientes:readonly FotoSeleccionada[]=[];protected motivo='';private secuencia=0;
  constructor(){effect(()=>{const tipo=this.tipo(),id=this.registroId(), abierta=this.abierta();untracked(()=>{this.secuencia++;this.liberar();this.pendientes=[];this.retirando.set(null);if(abierta)this.cargar(tipo,id);});});this.destruir.onDestroy(()=>this.liberar());}
  private liberar():void{this.urls().forEach(u=>URL.revokeObjectURL(u));this.urls.set(new Map());}
  private cargar(tipo=this.tipo(),id=this.registroId()):void{
    const n=++this.secuencia;this.liberar();this.error.set('');this.fotos.set([]);
    this.api.listar(tipo,id).pipe(takeUntilDestroyed(this.destruir)).subscribe({next:f=>{if(n!==this.secuencia)return;this.fotos.set(f);f.forEach(x=>this.api.contenido(tipo,id,x.id).pipe(takeUntilDestroyed(this.destruir)).subscribe({next:b=>{if(n!==this.secuencia)return;const m=new Map(this.urls());m.set(x.id,URL.createObjectURL(b));this.urls.set(m);},error:e=>{if(n===this.secuencia)this.error.set(e.message);}}));},error:e=>{if(n===this.secuencia)this.error.set(e.message);}});
  }
  protected guardar():void{if(this.ocupado())return;this.ocupado.set(true);this.api.finalizar(this.tipo(),{id:this.registroId()},this.pendientes).pipe(takeUntilDestroyed(this.destruir)).subscribe(r=>{this.ocupado.set(false);this.pendientes=r.pendientes;if(!r.fallo){this.captura()?.limpiar();this.cargar();}else this.error.set(r.fallo);});}
  protected retirar():void{const id=this.retirando();if(!id||this.ocupado())return;this.ocupado.set(true);this.api.retirar(this.tipo(),this.registroId(),id,this.motivo.trim()).pipe(takeUntilDestroyed(this.destruir)).subscribe({next:()=>{this.ocupado.set(false);this.retirando.set(null);this.motivo='';this.cargar();},error:e=>{this.ocupado.set(false);this.error.set(e.message);}});}
}
