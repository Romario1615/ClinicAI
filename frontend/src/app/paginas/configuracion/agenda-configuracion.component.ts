import { Component, OnInit, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { FalloApi } from '../../nucleo/servicios/api.service';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import type { Sede } from '../../nucleo/modelos/dominio';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { IntegracionesService, type DatosFeriadoAgenda, type DatosHorarioSede, type FeriadoAgenda, type HorarioSede } from './integraciones.service';

@Component({
  selector: 'app-agenda-configuracion',
  standalone: true,
  imports: [FormsModule],
  template: `
    <section class="intro tarjeta"><div><p class="ceja">OPERACIÓN DE LA SEDE</p><h2>Horarios y feriados</h2><p>Define cuándo se ofrecen citas, las pausas diarias y los días de cierre. La agenda utiliza estos datos al calcular disponibilidad.</p></div>
      <label class="campo"><span class="campo__etiqueta">Sede</span><select class="campo__control" name="agenda-sede" [(ngModel)]="sedeId" (ngModelChange)="cargar()"><option value="">Seleccione una sede</option>@for (sede of sedes(); track sede.id) { <option [value]="sede.id">{{ sede.nombre }}</option> }</select></label>
    </section>
    @if (mensaje()) { <p class="mensaje" [class.error]="esError()" role="status">{{ mensaje() }}</p> }
    @if (cargando()) { <p class="tarjeta" role="status">Cargando horarios y cierres…</p> }
    @if (sedeId) {
      <div class="columnas">
        <section class="tarjeta panel"><div class="cabecera"><div><p class="ceja">DISPONIBILIDAD RECURRENTE</p><h3>{{ horarioEditando ? 'Editar franja' : 'Agregar horario' }}</h3></div></div>
          <form class="formulario" (ngSubmit)="guardarHorario()">
            <label class="campo"><span class="campo__etiqueta">Día</span><select class="campo__control" name="dia" [(ngModel)]="horario.dia_semana">@for (dia of dias; track dia.id) { <option [ngValue]="dia.id">{{ dia.nombre }}</option> }</select></label>
            <label class="campo"><span class="campo__etiqueta">Desde</span><input class="campo__control" type="time" name="inicio" [(ngModel)]="horario.hora_inicio" required /></label>
            <label class="campo"><span class="campo__etiqueta">Hasta</span><input class="campo__control" type="time" name="fin" [(ngModel)]="horario.hora_fin" required /></label>
            <label class="campo"><span class="campo__etiqueta">Duración de citas (min)</span><input class="campo__control" type="number" name="granularidad" min="1" max="60" [(ngModel)]="horario.granularidad_minutos" required /></label>
            <div class="separador"><span>Pausas</span><button class="boton boton--pequeno" type="button" (click)="agregarPausa()">Agregar pausa</button></div>
            @for (pausa of pausas; track $index) {
              <div class="pausa campo--completo"><label class="campo"><span class="campo__etiqueta">Desde</span><input class="campo__control" type="time" [name]="'pausa-inicio-' + $index" [(ngModel)]="pausa.hora_inicio" /></label>
                <label class="campo"><span class="campo__etiqueta">Hasta</span><input class="campo__control" type="time" [name]="'pausa-fin-' + $index" [(ngModel)]="pausa.hora_fin" /></label>
                <label class="campo"><span class="campo__etiqueta">Motivo (opcional)</span><input class="campo__control" [name]="'pausa-motivo-' + $index" maxlength="150" [(ngModel)]="pausa.motivo" placeholder="Almuerzo" /></label>
                <button class="boton boton--pequeno peligro" type="button" (click)="quitarPausa($index)" [attr.aria-label]="'Eliminar pausa ' + ($index + 1)">Quitar</button>
              </div>
            }
            <div class="separador"><span>Vigencia opcional</span></div>
            <label class="campo"><span class="campo__etiqueta">Válido desde</span><input class="campo__control" type="date" name="vigente-desde" [(ngModel)]="horario.vigente_desde" /></label>
            <label class="campo"><span class="campo__etiqueta">Válido hasta</span><input class="campo__control" type="date" name="vigente-hasta" [(ngModel)]="horario.vigente_hasta" /></label>
            <div class="acciones campo--completo"><button class="boton boton--principal" type="submit" [disabled]="guardando()">{{ horarioEditando ? 'Guardar cambios' : 'Agregar horario' }}</button>@if (horarioEditando) { <button class="boton" type="button" (click)="nuevoHorario()">Cancelar</button> }</div>
          </form>
          <div class="lista"><h4>Horarios configurados</h4>
            @if (horarios().length === 0) { <p class="vacio">Aún no hay horarios para esta sede.</p> }
            @for (item of horarios(); track item.id) { <article class="fila"><div><strong>{{ nombreDia(item.dia_semana) }} · {{ horaVisible(item.hora_inicio) }}–{{ horaVisible(item.hora_fin) }}</strong><small>{{ item.granularidad_minutos }} min por cita{{ item.descansos.length ? ' · ' + item.descansos.length + ' pausa(s)' : '' }}{{ item.vigente_desde || item.vigente_hasta ? ' · vigencia ' + (item.vigente_desde ?? 'sin inicio') + ' a ' + (item.vigente_hasta ?? 'sin fin') : '' }}</small></div><div class="acciones"><button class="boton boton--pequeno" type="button" (click)="editarHorario(item)">Editar</button><button class="boton boton--pequeno peligro" type="button" (click)="eliminarHorario(item)">Eliminar</button></div></article> }
          </div>
        </section>
        <section class="tarjeta panel"><div class="cabecera"><div><p class="ceja">CIERRES DE AGENDA</p><h3>{{ feriadoEditando ? 'Editar feriado' : 'Agregar feriado' }}</h3></div></div>
          <form class="formulario" (ngSubmit)="guardarFeriado()">
            <label class="campo campo--completo"><span class="campo__etiqueta">Nombre</span><input class="campo__control" name="feriado-nombre" [(ngModel)]="feriado.nombre" maxlength="150" required placeholder="Feriado nacional" /></label>
            <label class="campo campo--completo"><span class="campo__etiqueta">Fecha</span><input class="campo__control" type="date" name="feriado-fecha" [(ngModel)]="feriado.fecha" required /></label>
            <label class="campo campo--completo"><span class="campo__etiqueta">Aplica a</span><select class="campo__control" name="feriado-alcance" [(ngModel)]="alcanceFeriado"><option value="sede">Solo {{ nombreSede }}</option>@if (puedeGestionarFeriadosGlobales) { <option value="clinica">Toda la clínica</option> }</select></label>
            <label class="interruptor campo--completo"><input type="checkbox" name="feriado-recurrente" [(ngModel)]="feriado.recurrente_anual" /><span><strong>Repetir cada año</strong><small>Se aplicará en el mismo día y mes.</small></span></label>
            <div class="separador"><span>Deja las horas vacías para cerrar todo el día</span></div>
            <label class="campo"><span class="campo__etiqueta">Desde</span><input class="campo__control" type="time" name="feriado-inicio" [(ngModel)]="feriado.hora_inicio" /></label>
            <label class="campo"><span class="campo__etiqueta">Hasta</span><input class="campo__control" type="time" name="feriado-fin" [(ngModel)]="feriado.hora_fin" /></label>
            <div class="acciones campo--completo"><button class="boton boton--principal" type="submit" [disabled]="guardando()">{{ feriadoEditando ? 'Guardar cambios' : 'Agregar feriado' }}</button>@if (feriadoEditando) { <button class="boton" type="button" (click)="nuevoFeriado()">Cancelar</button> }</div>
          </form>
          <div class="lista"><h4>Próximos cierres</h4>@if (feriados().length === 0) { <p class="vacio">No hay feriados en el rango consultado.</p> }
            @for (item of feriados(); track item.id) { <article class="fila"><div><strong>{{ item.nombre }}</strong><small>{{ item.sede_id ? 'Esta sede' : 'Toda la clínica' }} · {{ item.fecha }} · {{ item.hora_inicio ? horaVisible(item.hora_inicio) + '–' + horaVisible(item.hora_fin ?? '') : 'Todo el día' }}{{ item.recurrente_anual ? ' · anual' : '' }}</small></div>@if (item.sede_id || puedeGestionarFeriadosGlobales) { <div class="acciones"><button class="boton boton--pequeno" type="button" (click)="editarFeriado(item)">Editar</button><button class="boton boton--pequeno peligro" type="button" (click)="eliminarFeriado(item)">Eliminar</button></div> }</article> }
          </div>
        </section>
      </div>
    }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    :host{display:block}.intro{display:grid;grid-template-columns:1fr minmax(220px,320px);gap:24px;align-items:center;padding:22px;margin-bottom:16px}.intro h2,.panel h3{margin:0}.intro p:last-child{color:var(--texto-suave);margin-bottom:0}.campo{margin:0}.columnas{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:start}.panel{padding:22px;min-width:0}.cabecera{margin-bottom:18px}.cabecera h3{font-size:1.12rem}.formulario{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.campo--completo{grid-column:1/-1}.separador{grid-column:1/-1;border-bottom:1px solid var(--borde);color:var(--texto-suave);font-size:.82rem;padding:5px 0;display:flex;align-items:center;justify-content:space-between}.pausa{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;align-items:end}.pausa .campo:nth-child(3){grid-column:1/-1}.acciones{display:flex;gap:8px;flex-wrap:wrap}.lista{margin-top:22px}.lista h4{margin:0 0 8px}.fila{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 0;border-top:1px solid var(--borde)}.fila>div:first-child{display:grid;gap:3px;min-width:0}.fila small,.interruptor small{color:var(--texto-suave)}.boton--pequeno{min-height:34px;padding:4px 10px;font-size:.82rem}.peligro{color:var(--peligro)}.vacio{padding:10px 0;color:var(--texto-suave)}.interruptor{display:flex;align-items:center;gap:10px}.interruptor>span{display:grid}.mensaje{padding:12px 16px;background:var(--exito-fondo);color:var(--exito);border-radius:var(--radio)}.mensaje.error{background:var(--peligro-fondo);color:var(--peligro)}
    @media(max-width:950px){.columnas{grid-template-columns:1fr}}@media(max-width:600px){.intro{grid-template-columns:1fr}.formulario{grid-template-columns:1fr}.campo--completo,.separador{grid-column:auto}.fila{align-items:flex-start;flex-direction:column}.acciones{width:100%}}
  `,
})
export class AgendaConfiguracionComponent implements OnInit {
  private readonly api = inject(IntegracionesService);
  private readonly catalogo = inject(CatalogoService);
  private readonly sesion = inject(SesionService);
  protected readonly sedes = signal<readonly Sede[]>([]);
  protected readonly horarios = signal<HorarioSede[]>([]);
  protected readonly feriados = signal<FeriadoAgenda[]>([]);
  protected readonly cargando = signal(false);
  protected readonly guardando = signal(false);
  protected readonly mensaje = signal('');
  protected readonly esError = signal(false);
  protected sedeId = '';
  protected horarioEditando = '';
  protected feriadoEditando = '';
  protected alcanceFeriado: 'sede' | 'clinica' = 'sede';
  protected pausas: { hora_inicio: string; hora_fin: string; motivo: string }[] = [];
  protected readonly dias = [{id:1,nombre:'Lunes'},{id:2,nombre:'Martes'},{id:3,nombre:'Miércoles'},{id:4,nombre:'Jueves'},{id:5,nombre:'Viernes'},{id:6,nombre:'Sábado'},{id:7,nombre:'Domingo'}];
  protected horario = this.horarioVacio();
  protected feriado = this.feriadoVacio();

  ngOnInit(): void {
    this.catalogo.sedes().subscribe({ next: (items) => { this.sedes.set(items); this.sedeId = items[0]?.id ?? ''; this.cargar(); }, error: (e: unknown) => this.fallar(e, 'No se pudieron cargar las sedes.') });
  }
  protected cargar(): void {
    if (!this.sedeId) { this.horarios.set([]); this.feriados.set([]); return; }
    this.cargando.set(true);
    const desde = new Date().toISOString().slice(0,10);
    const hasta = `${desde.slice(0,4)}-12-31`;
    this.api.horarios(this.sedeId).subscribe({ next: (items) => { this.horarios.set(items); this.cargando.set(false); }, error: (e: unknown) => { this.fallar(e, 'No se pudieron cargar los horarios.'); this.cargando.set(false); } });
    this.api.feriados(this.sedeId, desde, hasta).subscribe({ next: (items) => this.feriados.set(items), error: (e: unknown) => this.fallar(e, 'No se pudieron cargar los feriados.') });
  }
  protected nombreDia(dia: number): string { return this.dias.find((item) => item.id === dia)?.nombre ?? 'Día'; }
  protected horaVisible(valor: string): string { return valor.slice(0, 5); }
  protected nuevoHorario(): void { this.horarioEditando=''; this.horario=this.horarioVacio(); this.pausas=[]; }
  protected agregarPausa(): void { if (this.pausas.length < 8) this.pausas.push({ hora_inicio: '', hora_fin: '', motivo: '' }); }
  protected quitarPausa(indice: number): void { this.pausas.splice(indice, 1); }
  protected editarHorario(item: HorarioSede): void { this.horarioEditando=item.id; this.horario={...item,hora_inicio:this.horaCorta(item.hora_inicio) ?? '',hora_fin:this.horaCorta(item.hora_fin) ?? '', descansos:[]}; this.pausas=item.descansos.map((pausa)=>({hora_inicio:this.horaCorta(pausa.hora_inicio) ?? '',hora_fin:this.horaCorta(pausa.hora_fin) ?? '',motivo:pausa.motivo ?? ''})); }
  protected guardarHorario(): void {
    const descansos = this.pausas.filter((pausa)=>pausa.hora_inicio || pausa.hora_fin).map((pausa)=>({...pausa,motivo:pausa.motivo||null}));
    const datos: DatosHorarioSede = {...this.horario, descansos}; this.guardando.set(true); this.mensaje.set('');
    this.api.guardarHorario(this.sedeId, datos, this.horarioEditando || undefined).subscribe({next:()=>{this.guardando.set(false);this.nuevoHorario();this.mostrar('Horario guardado.');this.cargar();},error:(e:unknown)=>{this.guardando.set(false);this.fallar(e,'No se pudo guardar el horario.')}});
  }
  protected eliminarHorario(item: HorarioSede): void { if (!confirm(`¿Eliminar el horario del ${this.nombreDia(item.dia_semana)}?`)) return; this.api.eliminarHorario(item.id).subscribe({next:()=>{this.mostrar('Horario eliminado.');this.cargar();},error:(e:unknown)=>this.fallar(e,'No se pudo eliminar el horario.')}); }
  protected nuevoFeriado(): void { this.feriadoEditando=''; this.alcanceFeriado='sede'; this.feriado=this.feriadoVacio(); }
  protected editarFeriado(item:FeriadoAgenda):void {this.feriadoEditando=item.id;this.alcanceFeriado=item.sede_id?'sede':'clinica';this.feriado={sede_id:item.sede_id,fecha:item.fecha,nombre:item.nombre,recurrente_anual:item.recurrente_anual,hora_inicio:this.horaCorta(item.hora_inicio),hora_fin:this.horaCorta(item.hora_fin)};}
  protected guardarFeriado():void {const datos:DatosFeriadoAgenda={...this.feriado,sede_id:this.alcanceFeriado==='sede'?this.sedeId||null:null,hora_inicio:this.feriado.hora_inicio||null,hora_fin:this.feriado.hora_fin||null};this.guardando.set(true);this.api.guardarFeriado(datos,this.feriadoEditando||undefined).subscribe({next:()=>{this.guardando.set(false);this.nuevoFeriado();this.mostrar('Feriado guardado.');this.cargar();},error:(e:unknown)=>{this.guardando.set(false);this.fallar(e,'No se pudo guardar el feriado.')}});}
  protected eliminarFeriado(item:FeriadoAgenda):void {if(!confirm(`¿Eliminar «${item.nombre}»?`))return;this.api.eliminarFeriado(item.id).subscribe({next:()=>{this.mostrar('Feriado eliminado.');this.cargar();},error:(e:unknown)=>this.fallar(e,'No se pudo eliminar el feriado.')});}
  private horarioVacio(): DatosHorarioSede {return {dia_semana:1,hora_inicio:'08:00',hora_fin:'17:00',granularidad_minutos:15,vigente_desde:null,vigente_hasta:null,descansos:[]};}
  private feriadoVacio(): DatosFeriadoAgenda {return {sede_id:null,fecha:new Date().toISOString().slice(0,10),nombre:'',recurrente_anual:false,hora_inicio:null,hora_fin:null};}
  private horaCorta(valor:string|null|undefined):string|null {return valor ? valor.slice(0,5) : null;}
  protected get nombreSede(): string {return this.sedes().find((sede)=>sede.id===this.sedeId)?.nombre ?? 'esta sede';}
  protected get puedeGestionarFeriadosGlobales(): boolean {return this.sesion.identidad()?.ambito.todas_las_sedes ?? false;}
  private mostrar(texto:string):void {this.esError.set(false);this.mensaje.set(texto);}
  private fallar(error:unknown,respaldo:string):void {this.esError.set(true);this.mensaje.set(error instanceof FalloApi?error.message:respaldo);}
}
