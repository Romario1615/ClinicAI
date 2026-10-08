import { Component, DestroyRef, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

export interface FotoSeleccionada {readonly id:string; readonly archivo:File; readonly url:string; descripcion:string}
export const MAX_FOTO_BYTES=10*1024*1024;
export function validarFoto(archivo:File):string {
  if(!['image/jpeg','image/png','image/webp'].includes(archivo.type)) return 'Seleccione una imagen JPEG, PNG o WebP.';
  if(!archivo.size || archivo.size>MAX_FOTO_BYTES) return 'La imagen debe tener contenido y ocupar hasta 10 MB.';
  return '';
}

@Component({selector:'app-captura-fotos',standalone:true,imports:[FormsModule],template:`
  <fieldset class="captura"><legend>{{titulo()}}</legend><p>Fotografías opcionales. Se guardan con el registro y sus permisos.</p>
    <div class="captura__acciones"><label class="boton"><input class="solo-lectores" type="file" accept="image/jpeg,image/png,image/webp" [disabled]="ocupada()" [multiple]="!perfil()" (change)="seleccionar($event)" />Elegir {{perfil()?'foto':'imágenes'}}</label><label class="boton"><input class="solo-lectores" type="file" accept="image/jpeg,image/png,image/webp" [disabled]="ocupada()" [attr.capture]="perfil()?'user':'environment'" (change)="seleccionar($event)" />Tomar foto</label></div>
    <p class="captura__ayuda">JPEG, PNG o WebP · hasta 10 MB por imagen. La cámara se abre en dispositivos compatibles; en otros puede elegir un archivo.</p>
    @if(error()){<p role="alert">{{error()}}</p>}
    <div class="captura__fotos">@for(f of fotos();track f.id){<article><img [src]="f.url" [alt]="f.descripcion || 'Vista previa de fotografía seleccionada'" /><label>Descripción<input type="text" [ngModel]="f.descripcion" (ngModelChange)="describir(f.id,$event)" [ngModelOptions]="{standalone:true}" maxlength="500" [disabled]="ocupada()" /></label><button type="button" class="boton" (click)="quitar(f.id)" [disabled]="ocupada()">Quitar imagen</button></article>}</div>
  </fieldset>
`,styles:`.captura{border:1px solid var(--borde);border-radius:1rem;padding:1rem;display:grid;gap:.7rem;min-width:0}.captura legend{font-weight:600}.captura p{margin:0;font-size:.8rem;color:var(--texto-suave)}.captura__acciones{display:flex;flex-wrap:wrap;gap:.6rem}.captura__acciones label{cursor:pointer}.captura__acciones label:focus-within{outline:3px solid var(--acento);outline-offset:3px}.captura__fotos{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(180px,100%),1fr));gap:.8rem}.captura__fotos article{min-width:0;display:grid;gap:.5rem}.captura__fotos img{width:100%;height:140px;object-fit:contain;background:var(--superficie-hundida);border-radius:.6rem}.captura__fotos label{display:grid;gap:.3rem;font-size:.8rem}.captura__fotos input{width:100%;box-sizing:border-box}`})
export class CapturaFotosComponent {
  readonly titulo=input('Fotos del registro');
  readonly perfil=input(false);
  readonly ocupada=input(false);
  readonly cambiadas=output<readonly FotoSeleccionada[]>();
  readonly fotos=signal<readonly FotoSeleccionada[]>([]);
  protected readonly error=signal('');
  constructor(){inject(DestroyRef).onDestroy(()=>this.fotos().forEach(f=>URL.revokeObjectURL(f.url)));}
  protected seleccionar(evento:Event):void {
    const campo=evento.target as HTMLInputElement; const archivos=Array.from(campo.files??[]); campo.value='';
    this.error.set('');if(!archivos.length) return;
    for(const archivo of archivos){const fallo=validarFoto(archivo);if(fallo){this.error.set(fallo);return;}}
    if(!this.perfil() && this.fotos().length+archivos.length>20){this.error.set('Puede adjuntar hasta veinte fotografías.');return;}
    if(this.perfil()) this.limpiar();
    const nuevas=(this.perfil()?archivos.slice(0,1):archivos).map(archivo=>({id:crypto.randomUUID(),archivo,url:URL.createObjectURL(archivo),descripcion:''}));
    this.fotos.update(f=>[...f,...nuevas]);this.cambiadas.emit(this.fotos());
  }
  protected describir(id:string,descripcion:string):void{this.fotos.update(f=>f.map(x=>x.id===id?{...x,descripcion}:x));this.cambiadas.emit(this.fotos());}
  protected quitar(id:string):void{const f=this.fotos().find(x=>x.id===id);if(f) URL.revokeObjectURL(f.url);this.fotos.update(f=>f.filter(x=>x.id!==id));this.cambiadas.emit(this.fotos());}
  limpiar():void{this.fotos().forEach(f=>URL.revokeObjectURL(f.url));this.fotos.set([]);this.cambiadas.emit([]);}
}
