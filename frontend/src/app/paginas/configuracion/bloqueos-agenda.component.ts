import { Component, OnInit, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

import { CONFIGURACION } from '../../nucleo/servicios/configuracion';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import type { Consultorio, Profesional, Sede } from '../../nucleo/modelos/dominio';

interface Bloqueo {
  readonly id: string; readonly sede_id: string; readonly profesional_id: string | null;
  readonly consultorio_id: string | null; readonly tipo: TipoBloqueo; readonly inicio: string;
  readonly fin: string; readonly motivo: string | null; readonly creado_con_citas_afectadas: boolean;
}
type TipoBloqueo = 'VACACIONES' | 'AUSENCIA' | 'CAPACITACION' | 'MANTENIMIENTO' | 'OTRO';
interface DatosBloqueo {
  sede_id: string; profesional_id: string | null; consultorio_id: string | null;
  tipo: TipoBloqueo; inicio: string; fin: string; motivo: string; aceptar_citas_afectadas: boolean;
}

@Component({
  selector: 'app-bloqueos-agenda', standalone: true, imports: [FormsModule],
  template: `
    <section class="intro tarjeta"><div><p class="ceja">EXCEPCIONES DE DISPONIBILIDAD</p><h2>Bloqueos y ausencias</h2><p>Registra vacaciones, ausencias, capacitaciones y cierres de consultorio. Las citas coincidentes requieren confirmación antes de guardar.</p></div>
      <label class="campo"><span class="campo__etiqueta">Sede</span><select class="campo__control" name="bloqueo-sede" [(ngModel)]="sedeId" (ngModelChange)="cargar()"><option value="">Seleccione una sede</option>@for (s of sedes(); track s.id) { <option [value]="s.id">{{ s.nombre }}</option> }</select></label>
    </section>
    @if (mensaje()) { <p class="mensaje" [class.error]="esError()" role="status">{{ mensaje() }}</p> }
    @if (sedeId) { <div class="columnas">
      <section class="tarjeta panel"><div class="cabecera"><p class="ceja">GESTIÓN DE AGENDA</p><h3>{{ editando ? 'Editar bloqueo' : 'Nuevo bloqueo' }}</h3></div>
        <form class="formulario" (ngSubmit)="guardar()">
          <label class="campo"><span class="campo__etiqueta">Tipo</span><select class="campo__control" name="tipo" [(ngModel)]="form.tipo">@for (t of tipos; track t.id) { <option [value]="t.id">{{ t.nombre }}</option> }</select></label>
          <label class="campo"><span class="campo__etiqueta">Afecta a</span><select class="campo__control" name="destino" [(ngModel)]="destino" (ngModelChange)="cambiarDestino()">@if (ambitoCompleto()) { <option value="sede">Toda la sede</option> }<option value="profesional">Profesional</option>@if (ambitoCompleto()) { <option value="consultorio">Consultorio</option> }</select></label>
          @if (destino === 'profesional') { <label class="campo campo--completo"><span class="campo__etiqueta">Profesional</span><select class="campo__control" name="profesional" [(ngModel)]="form.profesional_id" required><option value="">Seleccione</option>@for (p of profesionales(); track p.id) { <option [value]="p.id">{{ p.nombre }} {{ p.apellido }}</option> }</select></label> }
          @if (destino === 'consultorio') { <label class="campo campo--completo"><span class="campo__etiqueta">Consultorio</span><select class="campo__control" name="consultorio" [(ngModel)]="form.consultorio_id" required><option value="">Seleccione</option>@for (c of consultorios(); track c.id) { <option [value]="c.id">{{ c.nombre }}</option> }</select></label> }
          <label class="campo"><span class="campo__etiqueta">Inicio</span><input class="campo__control" type="datetime-local" name="inicio" [(ngModel)]="formInicio" required /></label>
          <label class="campo"><span class="campo__etiqueta">Fin</span><input class="campo__control" type="datetime-local" name="fin" [(ngModel)]="formFin" required /></label>
          <label class="campo campo--completo"><span class="campo__etiqueta">Motivo (opcional)</span><input class="campo__control" name="motivo" maxlength="300" [(ngModel)]="form.motivo" placeholder="Vacaciones, mantenimiento…" /></label>
          <div class="acciones campo--completo"><button class="boton boton--principal" type="submit" [disabled]="guardando()">{{ editando ? 'Guardar cambios' : 'Crear bloqueo' }}</button>@if (editando) { <button class="boton" type="button" (click)="nuevo()">Cancelar</button> }</div>
        </form>
      </section>
      <section class="tarjeta panel"><div class="cabecera"><p class="ceja">{{ cargando() ? 'ACTUALIZANDO' : 'SEDE SELECCIONADA' }}</p><h3>Bloqueos registrados</h3></div>
        @if (!bloqueos().length) { <p class="vacio">No hay bloqueos en el periodo próximo de 12 meses.</p> }
        @for (b of bloqueos(); track b.id) { <article class="fila"><div><strong>{{ nombreTipo(b.tipo) }} · {{ etiquetaDestino(b) }}</strong><small>{{ fecha(b.inicio) }} — {{ fecha(b.fin) }}</small>@if (b.motivo) { <small>{{ b.motivo }}</small> }@if (b.creado_con_citas_afectadas) { <small class="afectadas">Se guardó tras confirmar citas coincidentes.</small> }</div><div class="acciones"><button class="boton boton--pequeno" type="button" (click)="editar(b)">Editar</button><button class="boton boton--pequeno peligro" type="button" (click)="eliminar(b)">Eliminar</button></div></article> }
      </section>
    </div> }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: [`:host{display:block}.intro{display:grid;grid-template-columns:1fr minmax(220px,320px);gap:24px;align-items:center;padding:22px;margin-bottom:16px}.intro h2,.panel h3{margin:0}.intro p:last-child{color:var(--texto-suave);margin-bottom:0}.columnas{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:start}.panel{padding:22px;min-width:0}.cabecera{margin-bottom:18px}.formulario{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.campo{margin:0}.campo--completo{grid-column:1/-1}.acciones{display:flex;gap:8px;flex-wrap:wrap}.fila{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 0;border-top:1px solid var(--borde)}.fila>div:first-child{display:grid;gap:4px;min-width:0}.fila small,.vacio{color:var(--texto-suave)}.boton--pequeno{min-height:34px;padding:4px 10px;font-size:.82rem}.peligro{color:var(--peligro)}.mensaje{padding:12px 16px;background:var(--exito-fondo);color:var(--exito);border-radius:var(--radio)}.mensaje.error,.afectadas{color:var(--peligro)}@media(max-width:950px){.columnas{grid-template-columns:1fr}}@media(max-width:600px){.intro{grid-template-columns:1fr}.formulario{grid-template-columns:1fr}.campo--completo{grid-column:auto}.fila{align-items:flex-start;flex-direction:column}}`],
})
export class BloqueosAgendaComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly config = inject(CONFIGURACION);
  private readonly catalogo = inject(CatalogoService);
  private readonly sesion = inject(SesionService);
  protected readonly sedes = signal<readonly Sede[]>([]);
  protected readonly profesionales = signal<readonly Profesional[]>([]);
  protected readonly consultorios = signal<readonly Consultorio[]>([]);
  protected readonly bloqueos = signal<readonly Bloqueo[]>([]);
  protected readonly cargando = signal(false); protected readonly guardando = signal(false);
  protected readonly mensaje = signal(''); protected readonly esError = signal(false);
  protected sedeId = ''; protected editando = ''; protected destino: 'sede' | 'profesional' | 'consultorio' = 'sede';
  protected formInicio = ''; protected formFin = '';
  protected form: DatosBloqueo = this.vacio();
  protected readonly tipos = [{id:'VACACIONES',nombre:'Vacaciones'},{id:'AUSENCIA',nombre:'Ausencia'},{id:'CAPACITACION',nombre:'Capacitación'},{id:'MANTENIMIENTO',nombre:'Mantenimiento'},{id:'OTRO',nombre:'Otro'}] as const;
  ngOnInit(): void { this.catalogo.sedes().subscribe({next: s => { this.sedes.set(s); this.sedeId=s[0]?.id??''; this.cargar(); }, error: () => this.fallar('No se pudieron cargar las sedes.')}); }
  protected cargar(): void {
    if (!this.sedeId) { this.bloqueos.set([]); return; }
    this.form.sede_id=this.sedeId; this.cargando.set(true);
    this.catalogo.profesionales({sedeId:this.sedeId}).subscribe({next:x=>{ const identidad=this.sesion.identidad(); const permitidos=identidad?.ambito.profesionales??[]; const lista=identidad?.ambito.todos_los_profesionales?x:x.filter(p=>permitidos.includes(p.id)); this.profesionales.set(lista); if(!identidad?.ambito.todos_los_profesionales){this.destino='profesional';this.form.profesional_id=identidad?.profesional_id&&lista.some(p=>p.id===identidad.profesional_id)?identidad.profesional_id:lista[0]?.id??null;} },error:()=>this.profesionales.set([])});
    this.catalogo.consultorios(this.sedeId).subscribe({next:x=>this.consultorios.set(x),error:()=>this.consultorios.set([])});
    const ahora=new Date(), desde=new Date(Date.UTC(ahora.getUTCFullYear(),ahora.getUTCMonth(),ahora.getUTCDate())).toISOString(), hasta=new Date(Date.now()+365*86400000).toISOString();
    this.http.get<Bloqueo[]>(`${this.config.urlApi}/agenda/bloqueos`,{params:{sede_id:this.sedeId,desde,hasta}}).subscribe({next:x=>{this.bloqueos.set(x);this.cargando.set(false)},error:()=>{this.fallar('No se pudieron cargar los bloqueos.');this.cargando.set(false)}});
  }
  protected cambiarDestino(): void { this.form.profesional_id=null; this.form.consultorio_id=null; }
  protected ambitoCompleto(): boolean { return this.sesion.identidad()?.ambito.todos_los_profesionales ?? false; }
  protected async guardar(): Promise<void> {
    if (!this.sedeId || !this.formInicio || !this.formFin) return;
    this.guardando.set(true); this.form.sede_id=this.sedeId; this.form.profesional_id=this.destino==='profesional'?this.form.profesional_id:null; this.form.consultorio_id=this.destino==='consultorio'?this.form.consultorio_id:null;
    const payload={...this.form,inicio:this.aIso(this.formInicio),fin:this.aIso(this.formFin),aceptar_citas_afectadas:false};
    const url=`${this.config.urlApi}/agenda/bloqueos${this.editando?'/'+this.editando:''}`;
    try {
      await firstValueFrom(this.http.request(this.editando?'PUT':'POST',url,{body:payload}));
      this.mensaje.set('Bloqueo guardado.'); this.esError.set(false); this.nuevo(); this.cargar();
    } catch (e) {
      const error=e as HttpErrorResponse, detalles=error.error?.detalles as {citas_afectadas?:unknown[]} | undefined;
      if (error.status===409 && detalles?.citas_afectadas?.length && window.confirm(`Este bloqueo coincide con ${detalles.citas_afectadas.length} cita(s) activa(s). ¿Desea confirmar y guardar? No se mostrarán datos de pacientes.`)) {
        try { await firstValueFrom(this.http.request(this.editando?'PUT':'POST',url,{body:{...payload,aceptar_citas_afectadas:true}})); this.mensaje.set('Bloqueo guardado tras confirmar las citas coincidentes.'); this.esError.set(false); this.nuevo(); this.cargar(); }
        catch { this.fallar('No se pudo guardar el bloqueo confirmado.'); }
      } else this.fallar(error.error?.mensaje??'No se pudo guardar el bloqueo.');
    } finally { this.guardando.set(false); }
  }
  protected editar(b: Bloqueo): void { this.editando=b.id; this.form={sede_id:b.sede_id,profesional_id:b.profesional_id,consultorio_id:b.consultorio_id,tipo:b.tipo,inicio:b.inicio,fin:b.fin,motivo:b.motivo??'',aceptar_citas_afectadas:false}; this.destino=b.profesional_id?'profesional':b.consultorio_id?'consultorio':'sede'; this.formInicio=this.deIso(b.inicio); this.formFin=this.deIso(b.fin); }
  protected nuevo(): void { this.editando='';this.form=this.vacio();this.form.sede_id=this.sedeId;this.destino='sede';this.formInicio='';this.formFin=''; }
  protected eliminar(b: Bloqueo): void { if(!window.confirm(`¿Eliminar el bloqueo de ${this.nombreTipo(b.tipo).toLowerCase()}?`))return; this.http.delete(`${this.config.urlApi}/agenda/bloqueos/${b.id}`).subscribe({next:()=>{this.mensaje.set('Bloqueo eliminado.');this.esError.set(false);this.cargar()},error:()=>this.fallar('No se pudo eliminar el bloqueo.')}); }
  protected nombreTipo(t: TipoBloqueo): string { return this.tipos.find(x=>x.id===t)?.nombre??t; }
  protected etiquetaDestino(b: Bloqueo): string { return b.profesional_id?`${this.profesionales().find(x=>x.id===b.profesional_id)?.nombre??'Profesional'} ${this.profesionales().find(x=>x.id===b.profesional_id)?.apellido??''}`.trim():b.consultorio_id?this.consultorios().find(x=>x.id===b.consultorio_id)?.nombre??'Consultorio':'Toda la sede'; }
  protected fecha(value: string): string { return new Intl.DateTimeFormat('es-EC',{dateStyle:'medium',timeStyle:'short',timeZone:this.sedes().find(s=>s.id===this.sedeId)?.zona_horaria??this.config.zonaHorariaPorDefecto}).format(new Date(value)); }
  private vacio(): DatosBloqueo { return {sede_id:'',profesional_id:null,consultorio_id:null,tipo:'OTRO',inicio:'',fin:'',motivo:'',aceptar_citas_afectadas:false}; }
  private fallar(texto: string): void { this.mensaje.set(texto);this.esError.set(true); }
  private aIso(value: string): string { const zone=this.sedes().find(s=>s.id===this.sedeId)?.zona_horaria??this.config.zonaHorariaPorDefecto; const [date,time]=value.split('T'),[y,m,d]=date.split('-').map(Number),[h,min]=time.split(':').map(Number); const guess=Date.UTC(y,m-1,d,h,min), parts=new Intl.DateTimeFormat('en-CA',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(guess)); const get=(k:string)=>Number(parts.find(p=>p.type===k)?.value); const offset=(Date.UTC(get('year'),get('month')-1,get('day'),get('hour'),get('minute'))-guess)/60000; return new Date(guess-offset*60000).toISOString(); }
  private deIso(value: string): string { const parts=new Intl.DateTimeFormat('en-CA',{timeZone:this.sedes().find(s=>s.id===this.sedeId)?.zona_horaria??this.config.zonaHorariaPorDefecto,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(value)); const get=(k:string)=>parts.find(p=>p.type===k)?.value??'00'; return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`; }
}
