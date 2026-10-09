import { Component, DestroyRef, computed, effect, inject, input, output, signal, untracked } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { catchError } from 'rxjs';
import { CONFIGURACION, PERMISOS } from '../nucleo/servicios/configuracion';
import { traducirFallo } from '../nucleo/servicios/api.service';
import { SesionService } from '../nucleo/servicios/sesion.service';
import { CatalogoService } from '../nucleo/servicios/catalogo.service';
import { type Especialidad, type Profesional, type Sede, type Servicio } from '../nucleo/modelos/dominio';
import { formatearFechaHora, instanteLocal } from '../nucleo/utilidades/fechas';
import { VentanaFlotanteComponent } from './ventana-flotante.component';
import { ChatConversacionalComponent } from './chat-conversacional.component';

interface PropuestaAgente {id:string;titulo:string;nombre:string;argumentos:Record<string,unknown>;expira_en:string}
interface RespuestaAgente {sesion_id:string;paciente_id:string;expira_en:string;texto:string;datos:Record<string,unknown>;requiere_humano:boolean;modo:'local'|'configurado';propuesta:PropuestaAgente|null}
interface MensajeAgente {autor:'usted'|'agente';texto:string}
interface CitaAgente {cita_id:string;inicio:string;estado:string}
interface TurnoAgente {inicio:string;fin?:string}
interface PagoAgente {importe:string;moneda:string;estado:string;cita:string}
interface ElementoAgente {titulo:string;detalle:string|null}

@Component({selector:'app-agente-paciente',standalone:true,imports:[FormsModule, VentanaFlotanteComponent, ChatConversacionalComponent],templateUrl:'./agente-paciente.component.html',styleUrl:'./agente-paciente.component.scss'})
export class AgentePacienteComponent {
  readonly pacienteId=input.required<string>();
  readonly nombre=input('Paciente');
  readonly citaId=input<string|null>(null);
  readonly zona=input('America/Guayaquil');
  readonly cerrar=output<void>();
  readonly actualizado=output<void>();
  private readonly http=inject(HttpClient);
  private readonly config=inject(CONFIGURACION);
  private readonly sesion=inject(SesionService);
  private readonly destruir=inject(DestroyRef);
  private readonly catalogo=inject(CatalogoService);
  protected readonly ocupado=signal(false);
  protected readonly error=signal('');
  protected readonly mensajes=signal<readonly MensajeAgente[]>([]);
  protected readonly respuesta=signal<RespuestaAgente|null>(null);
  protected readonly citas=computed(()=>this.respuesta()?.datos['citas'] as readonly CitaAgente[]|undefined??[]);
  protected readonly turnos=computed(()=>this.respuesta()?.datos['turnos'] as readonly TurnoAgente[]|undefined??[]);
  protected readonly pagos=computed(()=>this.respuesta()?.datos['pagos'] as readonly PagoAgente[]|undefined??[]);
  protected readonly elementos=computed(()=>this.respuesta()?.datos['elementos'] as readonly ElementoAgente[]|undefined??[]);
  protected readonly puedeAgenda=computed(()=>this.sesion.tienePermiso(PERMISOS.agendaLeer));
  protected readonly puedeCrear=computed(()=>this.sesion.tienePermiso(PERMISOS.citaCrear));
  protected readonly puedeReprogramar=computed(()=>this.sesion.tienePermiso(PERMISOS.citaReprogramar));
  protected readonly puedeCancelar=computed(()=>this.sesion.tienePermiso(PERMISOS.citaCancelar));
  protected readonly sugerencias=computed(()=>[
    ...(this.puedeAgenda()?['Mis citas','Buscar horarios']:[]),
    ...(this.sesion.tienePermiso(PERMISOS.pagoLeer)?['Mis pagos']:[]),
    ...(this.sesion.tienePermiso(PERMISOS.historiaLeer)?['Resumen clínico']:[]),
    ...(this.sesion.tienePermiso(PERMISOS.conocimientoLeer)?['Protocolos de la clínica']:[]),
    ...(this.sesion.tienePermiso(PERMISOS.conversacionResponder)?['Hablar con una persona']:[]),
  ]);
  protected texto='';
  protected motivo='';
  protected readonly configurando=signal(false);
  protected readonly sedes=signal<readonly Sede[]>([]);
  protected readonly especialidades=signal<readonly Especialidad[]>([]);
  protected readonly servicios=signal<readonly Servicio[]>([]);
  protected readonly profesionales=signal<readonly Profesional[]>([]);
  protected sede='';protected especialidad='';protected servicio='';protected profesional='';protected desde='';protected hasta='';
  private secuencia=0;
  private cuerpoAnterior='';private clave=crypto.randomUUID();
  private ultimaSolicitud:{ruta:string;datos:unknown;alTerminar?:()=>void}|null=null;

  constructor(){effect(()=>{const id=this.pacienteId();untracked(()=>this.abrir(id,this.citaId()));});}
  protected fecha(valor:unknown):string{return typeof valor==='string' ? formatearFechaHora(valor,this.respuesta()?.datos['zona_horaria'] as string ?? this.zona()) : '';}
  protected estado(valor:string):string{return ({HELD:'Apartada',PENDING:'Pendiente',CONFIRMED:'Confirmada',RESCHEDULED:'Reprogramada',CANCELLED:'Cancelada',COMPLETED:'Atendida',NO_SHOW:'No asistió',PROOF_RECEIVED:'Comprobante recibido',UNDER_REVIEW:'En revisión',REJECTED:'Rechazado'} as Record<string,string>)[valor] ?? valor;}
  protected motivoReprogramacion='';
  protected reprogramar(indice:number):void { if(this.motivoReprogramacion.trim())this.enviar(`reprogramar: ${indice+1}: ${this.motivoReprogramacion.trim()}`); }
  private base(id=this.pacienteId()):string{return `${this.config.urlApi}/asistente/pacientes/${id}`;}
  private solicitar(ruta:string,datos:unknown,alTerminar?:()=>void):void{
    if(this.ocupado())return;
    this.ultimaSolicitud={ruta,datos,alTerminar};
    const cuerpo=JSON.stringify({ruta,datos});if(cuerpo!==this.cuerpoAnterior){this.clave=crypto.randomUUID();this.cuerpoAnterior=cuerpo;}
    const n=++this.secuencia;this.ocupado.set(true);this.error.set('');
    this.http.post<RespuestaAgente>(ruta,datos,{headers:new HttpHeaders({'Idempotency-Key':this.clave})}).pipe(catchError(traducirFallo),takeUntilDestroyed(this.destruir)).subscribe({
      next:r=>{if(n!==this.secuencia)return;this.ocupado.set(false);this.respuesta.set(r);if(r.texto)this.mensajes.update(m=>[...m,{autor:'agente',texto:r.texto}]);this.cuerpoAnterior='';alTerminar?.();},
      error:e=>{if(n===this.secuencia){this.ocupado.set(false);this.error.set(e.message);}},
    });
  }
  protected reintentar():void{const anterior=this.ultimaSolicitud;if(anterior)this.solicitar(anterior.ruta,anterior.datos,anterior.alTerminar);}
  protected abrir(id=this.pacienteId(),cita=this.citaId()):void{
    this.secuencia++;this.ocupado.set(false);this.respuesta.set(null);this.mensajes.set([]);this.texto='';this.motivo='';this.configurando.set(false);
    this.solicitar(`${this.base(id)}/sesiones`,{cita_id:this.puedeAgenda()?cita:null});
  }
  protected enviar(texto=this.texto):void{
    const r=this.respuesta();texto=texto.trim();if(!r||!texto||this.ocupado()||r.propuesta)return;
    this.mensajes.update(m=>[...m,{autor:'usted',texto}]);this.texto='';
    this.solicitar(`${this.base()}/sesiones/${r.sesion_id}/mensajes`,{texto});
  }
  protected confirmar(aceptar:boolean):void{
    const r=this.respuesta();if(!r?.propuesta)return;
    this.solicitar(`${this.base()}/sesiones/${r.sesion_id}/confirmar`,{propuesta_id:r.propuesta.id,aceptar},()=>{if(aceptar)this.actualizado.emit();});
  }
  protected elegir(cita:string):void{const r=this.respuesta();if(r)this.solicitar(`${this.base()}/sesiones/${r.sesion_id}/cita`,{cita_id:cita});}
  protected cancelarCita():void{if(this.motivo.trim())this.enviar(`cancelar: ${this.motivo.trim()}`);}
  protected configurar():void{
    if(this.ocupado() || this.respuesta()?.propuesta)return;
    this.error.set('');this.configurando.set(true);
    this.catalogo.sedes().pipe(takeUntilDestroyed(this.destruir)).subscribe({next:s=>this.sedes.set(s),error:e=>this.error.set(e.message)});
    this.catalogo.especialidades().pipe(takeUntilDestroyed(this.destruir)).subscribe({next:e=>this.especialidades.set(e),error:e=>this.error.set(e.message)});
  }
  protected cerrarContexto():void{if(!this.ocupado())this.configurando.set(false);}
  protected cambiarEspecialidad():void{
    this.servicio='';this.profesional='';this.servicios.set([]);this.profesionales.set([]);if(!this.especialidad)return;
    const especialidad=this.especialidad,sede=this.sede;
    const vigente=()=>this.especialidad===especialidad && this.sede===sede;
    this.catalogo.servicios(especialidad).pipe(takeUntilDestroyed(this.destruir)).subscribe({next:s=>{if(vigente())this.servicios.set(s);},error:e=>{if(vigente())this.error.set(e.message);}});
    this.catalogo.profesionales({especialidadId:especialidad,sedeId:sede||undefined}).pipe(takeUntilDestroyed(this.destruir)).subscribe({next:p=>{if(vigente())this.profesionales.set(p);},error:e=>{if(vigente())this.error.set(e.message);}});
  }
  protected guardarContexto():void{
    const r=this.respuesta();if(!r||!this.sede||!this.servicio||!this.profesional||!this.desde||!this.hasta)return;
    const zona=this.sedes().find(s=>s.id===this.sede)?.zona_horaria ?? this.zona();
    this.solicitar(`${this.base()}/sesiones/${r.sesion_id}/contexto`,{sede_id:this.sede,servicio_id:this.servicio,profesional_id:this.profesional,desde:instanteLocal(this.desde.slice(0,10),this.desde.slice(11),zona),hasta:instanteLocal(this.hasta.slice(0,10),this.hasta.slice(11),zona)},()=>this.configurando.set(false));
  }
}
