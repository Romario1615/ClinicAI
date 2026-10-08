import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, catchError, concatMap, defer, from, map, of, tap, toArray } from 'rxjs';
import { CONFIGURACION } from './configuracion';
import { FalloApi, traducirFallo } from './api.service';
import { type FotoSeleccionada } from '../../compartido/captura-fotos.component';

export interface FotoRegistro {id:string;tipo_mime:string;tamano_bytes:number;descripcion:string|null;creado_en:string}
export interface ResultadoFotos<T> {registro:T; fallo:string; pendientes:readonly FotoSeleccionada[]}

/** Un reintento de fotos no vuelve a crear el registro ni una versión clínica. */
export class OperacionConFotos<T extends {id:string}> {
  private registro:T|null=null;
  get guardado():boolean{return this.registro!==null;}
  constructor(private readonly api:FotosRegistroService){}
  reiniciar():void{this.registro=null;}
  guardar(tipo:string,crear:Observable<T>,fotos:readonly FotoSeleccionada[]):Observable<T>{
    return defer(()=>this.registro?of(this.registro):crear).pipe(tap(r=>{this.registro=r;}),concatMap(r=>this.api.finalizar(tipo,r,fotos)),map(resultado=>{
      if(resultado.fallo) throw new FalloApi('FOTOS_PENDIENTES',`El registro ya se guardó. Algunas fotos siguen pendientes: ${resultado.fallo} Reintente Guardar para completar las fotos.`,503);
      return resultado.registro;
    }));
  }
}

@Injectable({providedIn:'root'})
export class FotosRegistroService {
  private readonly http=inject(HttpClient);
  private readonly config=inject(CONFIGURACION);
  private ruta(tipo:string,id:string):string{return `${this.config.urlApi}/fotos-registro/${tipo}/${id}`;}
  operacion<T extends {id:string}>():OperacionConFotos<T>{return new OperacionConFotos<T>(this);}
  listar(tipo:string,id:string):Observable<readonly FotoRegistro[]>{return this.http.get<readonly FotoRegistro[]>(this.ruta(tipo,id)).pipe(catchError(traducirFallo));}
  contenido(tipo:string,id:string,foto:string):Observable<Blob>{return this.http.get(`${this.ruta(tipo,id)}/${foto}/contenido`,{responseType:'blob'}).pipe(catchError(traducirFallo));}
  retirar(tipo:string,id:string,foto:string,motivo:string):Observable<unknown>{return this.http.post(`${this.ruta(tipo,id)}/${foto}/retirar`,{motivo}).pipe(catchError(traducirFallo));}
  subir(tipo:string,id:string,foto:FotoSeleccionada):Observable<unknown>{
    const datos=new FormData();datos.append('archivo',foto.archivo,foto.archivo.name);datos.append('clave_idempotencia',foto.id);if(foto.descripcion) datos.append('descripcion',foto.descripcion);
    // Las fotos de perfil mantienen sus endpoints e identidad ya existentes.
    const ruta=tipo==='perfil_paciente'?`${this.config.urlApi}/pacientes/${id}/foto-perfil`:tipo==='perfil_usuario'?`${this.config.urlApi}/usuarios/${id}/foto`:this.ruta(tipo,id);
    return (tipo==='perfil_usuario'?this.http.put(ruta,datos):this.http.post(ruta,datos)).pipe(catchError(traducirFallo));
  }
  finalizar<T extends {id:string}>(tipo:string,registro:T,fotos:readonly FotoSeleccionada[]):Observable<ResultadoFotos<T>>{
    if(!fotos.length) return of({registro,fallo:'',pendientes:[]});
    return from(fotos).pipe(concatMap(f=>this.subir(tipo,registro.id,f).pipe(map(()=>({foto:f,error:''})),catchError(e=>of({foto:f,error:e.message as string})))),toArray(),map(resultados=>({registro,fallo:resultados.find(r=>r.error)?.error??'',pendientes:resultados.filter(r=>r.error).map(r=>r.foto)})));
  }
}
