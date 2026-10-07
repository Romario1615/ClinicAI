import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
import type { Profesional, Sede } from '../../nucleo/modelos/dominio';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { AgendaProfesionalesService, type DatosFranjaProfesional, type FranjaProfesional } from './agenda-profesionales.service';

@Component({
  selector: 'app-agenda-profesionales',
  standalone: true,
  imports: [FormsModule, VentanaFlotanteComponent],
  template: `
    <section class="intro tarjeta">
      <div><p class="ceja">EQUIPO CLÍNICO</p><h2>Disponibilidad profesional</h2><p>Define las franjas semanales de cada profesional en la hora local de la sede. Si no hay una agenda individual, se utiliza el horario de atención de la sede.</p></div>
      <div class="selectores">
        <label class="campo"><span class="campo__etiqueta">Sede</span><select class="campo__control" name="agenda-prof-sede" [(ngModel)]="sedeId" (ngModelChange)="cargarProfesionales()"><option value="">Seleccione una sede</option>@for (s of sedes(); track s.id) { <option [value]="s.id">{{ s.nombre }}</option> }</select></label>
        <label class="campo"><span class="campo__etiqueta">Profesional</span><select class="campo__control" name="agenda-profesional" [(ngModel)]="profesionalId" (ngModelChange)="cargarFranjas()" [disabled]="!sedeId"><option value="">Seleccione un profesional</option>@for (p of profesionales(); track p.id) { <option [value]="p.id">{{ p.nombre }} {{ p.apellido }}</option> }</select></label>
      </div>
    </section>
    @if (mensaje()) { <p class="mensaje" [class.error]="esError()" role="status">{{ mensaje() }}</p> }
    @if (cargando()) { <p class="tarjeta" role="status">Cargando disponibilidad…</p> }
    @if (sedeId && profesionalId) {
      <section class="tarjeta panel">
        <div class="cabecera"><div><p class="ceja">{{ etiquetaProfesional() }}</p><h3>Horario individual</h3></div><button class="boton boton--principal" type="button" (click)="abrirNueva()">Nueva franja</button></div>
        @if (!franjas().length) { <p class="vacio">Sin franjas individuales. Este profesional utiliza el horario de la sede.</p> }
        @for (f of franjas(); track f.id) { <article class="fila"><div><strong>{{ nombreDia(f.dia_semana) }} · {{ f.hora_inicio.slice(0,5) }}–{{ f.hora_fin.slice(0,5) }}</strong><small>{{ f.granularidad_minutos }} min por cita{{ f.vigente_desde || f.vigente_hasta ? ' · vigente ' + (f.vigente_desde ?? 'sin inicio') + ' a ' + (f.vigente_hasta ?? 'sin fin') : '' }}</small></div><div class="acciones"><button class="boton boton--pequeno" type="button" (click)="editar(f)">Editar</button><button class="boton boton--pequeno peligro" type="button" (click)="eliminar(f)">Eliminar</button></div></article> }
      </section>
      @if (ventanaFormulario()) {
        <app-ventana-flotante ceja="Disponibilidad del equipo" [titulo]="editando ? 'Editar franja' : 'Nueva franja'" forma="centrada" [anchoMaximo]="600" [cierraAlPulsarFuera]="false" (cerrar)="nueva()">
          <p class="campo__ayuda">{{ etiquetaProfesional() }} · {{ nombreSede() }}</p>
          @if (esError()) { <p class="mensaje error" role="alert">{{ mensaje() }}</p> }
          <form id="form-franja-profesional" class="formulario" (ngSubmit)="guardar()">
            <label class="campo"><span class="campo__etiqueta">Día</span><select class="campo__control" name="dia" [(ngModel)]="form.dia_semana">@for (d of dias; track d.id) { <option [ngValue]="d.id">{{ d.nombre }}</option> }</select></label>
            <label class="campo"><span class="campo__etiqueta">Duración de citas (minutos)</span><input class="campo__control" type="number" name="granularidad" min="1" max="240" [(ngModel)]="form.granularidad_minutos" required /></label>
            <label class="campo"><span class="campo__etiqueta">Inicio</span><input class="campo__control" type="time" name="inicio" [(ngModel)]="form.hora_inicio" required /></label>
            <label class="campo"><span class="campo__etiqueta">Fin</span><input class="campo__control" type="time" name="fin" [(ngModel)]="form.hora_fin" required /></label>
            <div class="separador campo--completo">Vigencia opcional para horarios temporales</div>
            <label class="campo"><span class="campo__etiqueta">Desde</span><input class="campo__control" type="date" name="vigente-desde" [(ngModel)]="form.vigente_desde" /></label>
            <label class="campo"><span class="campo__etiqueta">Hasta</span><input class="campo__control" type="date" name="vigente-hasta" [(ngModel)]="form.vigente_hasta" /></label>
          </form>
          <div pie class="acciones"><button class="boton" type="button" (click)="nueva()">Cancelar</button><button class="boton boton--principal" type="submit" form="form-franja-profesional" [disabled]="guardando()">{{ guardando() ? 'Guardando…' : editando ? 'Guardar cambios' : 'Agregar franja' }}</button></div>
        </app-ventana-flotante>
      }
      @if (confirmacionEliminar(); as franja) {
        <app-ventana-flotante ceja="Confirmar eliminación" titulo="Eliminar franja" forma="centrada" [anchoMaximo]="500" [cierraAlPulsarFuera]="false" (cerrar)="cancelarEliminacion()">
          <p>¿Eliminar el horario del {{ nombreDia(franja.dia_semana).toLowerCase() }}? Si no quedan otras franjas, el profesional usará el horario de la sede.</p>
          <div pie class="acciones"><button class="boton" type="button" (click)="cancelarEliminacion()">Cancelar</button><button class="boton boton--peligro" type="button" (click)="confirmarEliminacion()" [disabled]="guardando()">Eliminar franja</button></div>
        </app-ventana-flotante>
      }
    }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: [`:host{display:block}.intro{display:grid;grid-template-columns:1fr minmax(350px,520px);gap:24px;align-items:center;padding:22px;margin-bottom:16px}.intro h2,.panel h3{margin:0}.intro p:last-child{color:var(--texto-suave);margin-bottom:0}.selectores{display:grid;grid-template-columns:1fr 1fr;gap:12px}.campo{margin:0}.panel{padding:22px;min-width:0}.cabecera{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:18px}.cabecera h3{font-size:1.08rem}.formulario{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.campo--completo{grid-column:1/-1}.separador{border-bottom:1px solid var(--borde);color:var(--texto-suave);font-size:.84rem;padding:5px 0}.acciones{display:flex;gap:8px;flex-wrap:wrap}.fila{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 0;border-top:1px solid var(--borde)}.fila>div:first-child{display:grid;gap:4px;min-width:0}.fila small,.vacio{color:var(--texto-suave)}.boton--pequeno{min-height:34px;padding:4px 10px;font-size:.82rem}.peligro{color:var(--peligro)}.mensaje{padding:12px 16px;background:var(--exito-fondo);color:var(--exito);border-radius:var(--radio)}.mensaje.error{background:var(--peligro-fondo);color:var(--peligro)}@media(max-width:950px){.intro{grid-template-columns:1fr}.selectores{grid-template-columns:1fr 1fr}}@media(max-width:650px){.selectores,.formulario{grid-template-columns:1fr}.campo--completo{grid-column:auto}.fila{align-items:flex-start;flex-direction:column}.cabecera{align-items:flex-start;flex-direction:column}}`],
})
export class AgendaProfesionalesComponent implements OnInit {
  private readonly catalogo = inject(CatalogoService);
  private readonly agenda = inject(AgendaProfesionalesService);
  protected readonly sedes = signal<readonly Sede[]>([]);
  protected readonly profesionales = signal<readonly Profesional[]>([]);
  protected readonly franjas = signal<readonly FranjaProfesional[]>([]);
  protected readonly cargando = signal(false);
  protected readonly guardando = signal(false);
  protected readonly mensaje = signal('');
  protected readonly esError = signal(false);
  protected readonly ventanaFormulario = signal(false);
  protected readonly confirmacionEliminar = signal<FranjaProfesional | null>(null);
  protected sedeId = '';
  protected profesionalId = '';
  protected editando = '';
  protected form = this.vacio();
  protected readonly dias = [{id:1,nombre:'Lunes'},{id:2,nombre:'Martes'},{id:3,nombre:'Miércoles'},{id:4,nombre:'Jueves'},{id:5,nombre:'Viernes'},{id:6,nombre:'Sábado'},{id:7,nombre:'Domingo'}];

  ngOnInit(): void {
    this.catalogo.sedes().subscribe({
      next: (items) => { this.sedes.set(items); this.sedeId=items[0]?.id??''; this.cargarProfesionales(); },
      error: () => this.fallar('No se pudieron cargar las sedes.'),
    });
  }

  protected cargarProfesionales(): void {
    this.profesionalId=''; this.profesionales.set([]); this.franjas.set([]);
    if (!this.sedeId) return;
    this.catalogo.profesionales({sedeId:this.sedeId}).subscribe({
      next: (items) => { this.profesionales.set(items); this.profesionalId=items[0]?.id??''; this.cargarFranjas(); },
      error: () => this.fallar('No se pudieron cargar los profesionales de la sede.'),
    });
  }

  protected cargarFranjas(): void {
    this.franjas.set([]);
    if (!this.sedeId || !this.profesionalId) return;
    this.cargando.set(true);
    this.agenda.listar(this.profesionalId,this.sedeId).subscribe({
      next: (items) => { this.franjas.set(items); this.cargando.set(false); },
      error: (e: unknown) => { this.fallar(this.mensajeError(e,'No se pudo cargar la agenda individual.')); this.cargando.set(false); },
    });
  }

  protected guardar(): void {
    if (!this.sedeId || !this.profesionalId) return;
    this.guardando.set(true);
    const datos: DatosFranjaProfesional={...this.form, vigente_desde:this.form.vigente_desde||null, vigente_hasta:this.form.vigente_hasta||null};
    const peticion=this.editando?this.agenda.actualizar(this.profesionalId,this.sedeId,this.editando,datos):this.agenda.crear(this.profesionalId,this.sedeId,datos);
    peticion.subscribe({
      next: () => { this.mostrar('Disponibilidad guardada.');this.nueva();this.cargarFranjas();this.guardando.set(false); },
      error: (e: unknown) => { this.fallar(this.mensajeError(e,'No se pudo guardar la disponibilidad.'));this.guardando.set(false); },
    });
  }

  protected abrirNueva(): void { this.nueva(); this.mensaje.set(''); this.ventanaFormulario.set(true); }

  protected editar(f: FranjaProfesional): void {
    this.editando=f.id;this.form={dia_semana:f.dia_semana,hora_inicio:f.hora_inicio.slice(0,5),hora_fin:f.hora_fin.slice(0,5),granularidad_minutos:f.granularidad_minutos,vigente_desde:f.vigente_desde??'',vigente_hasta:f.vigente_hasta??''};this.ventanaFormulario.set(true);
  }

  protected nueva(): void { this.editando='';this.form=this.vacio();this.ventanaFormulario.set(false); }

  protected eliminar(f: FranjaProfesional): void { this.confirmacionEliminar.set(f); }
  protected cancelarEliminacion(): void { if (!this.guardando()) this.confirmacionEliminar.set(null); }
  protected confirmarEliminacion(): void {
    const franja = this.confirmacionEliminar();
    if (!franja || this.guardando()) return;
    this.guardando.set(true);
    this.agenda.eliminar(this.profesionalId,this.sedeId,franja.id).subscribe({
      next: () => { this.guardando.set(false);this.confirmacionEliminar.set(null);this.mostrar('Franja eliminada.');this.cargarFranjas(); },
      error: (e: unknown) => { this.guardando.set(false);this.fallar(this.mensajeError(e,'No se pudo eliminar la franja.')); },
    });
  }

  protected nombreDia(id: number): string { return this.dias.find((d)=>d.id===id)?.nombre??'Día'; }
  protected etiquetaProfesional(): string { const p=this.profesionales().find((x)=>x.id===this.profesionalId);return p?`${p.nombre} ${p.apellido}`:'PROFESIONAL'; }
  protected nombreSede(): string { return this.sedes().find((s)=>s.id===this.sedeId)?.nombre??'Sede seleccionada'; }
  private vacio(): DatosFranjaProfesional { return {dia_semana:1,hora_inicio:'08:00',hora_fin:'17:00',granularidad_minutos:15,vigente_desde:'',vigente_hasta:''}; }
  private mostrar(texto:string):void { this.mensaje.set(texto);this.esError.set(false); }
  private fallar(texto:string):void { this.mensaje.set(texto);this.esError.set(true); }
  private mensajeError(error:unknown,alternativo:string):string { return error instanceof HttpErrorResponse&&typeof error.error?.mensaje==='string'?error.error.mensaje:alternativo; }
}
