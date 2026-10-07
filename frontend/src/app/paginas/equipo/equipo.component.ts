import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { IconoComponent } from '../../compartido/icono.component';
import type { EstadoDisponibilidadProfesional, Especialidad, PerfilProfesional, Sede } from '../../nucleo/modelos/dominio';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { EquipoService, type DatosPerfilProfesional } from './equipo.service';

interface FormularioEquipo {
  especialidad_id: string;
  nombre: string;
  apellido: string;
  numero_registro_profesional: string;
  telefono_whatsapp: string;
  correo_calendario: string;
  estado_disponibilidad: Exclude<EstadoDisponibilidadProfesional, 'INACTIVO'>;
  acepta_pacientes_nuevos: boolean;
  minutos_preparacion_propio: number;
  activo: boolean;
  sede_ids: string[];
  sede_principal_id: string;
}

const ESTADOS: readonly { codigo: FormularioEquipo['estado_disponibilidad']; etiqueta: string }[] = [
  { codigo: 'DISPONIBLE', etiqueta: 'Disponible' },
  { codigo: 'AGENDA_COMPLETA', etiqueta: 'Agenda completa' },
  { codigo: 'AUSENTE', etiqueta: 'Ausente' },
];

@Component({
  selector: 'app-equipo',
  standalone: true,
  imports: [FormsModule, IconoComponent],
  template: `
    <header class="encabezado">
      <div class="encabezado__texto"><p class="ceja"><app-icono nombre="equipo" [tamano]="16" /> PERSONAL DE LA CLÍNICA</p><h1>Equipo clínico</h1><p>Administre perfiles profesionales y sus sedes de atención.</p></div>
      <img src="/images/equipo-clinica-colaboracion.jpg" alt="" aria-hidden="true" fetchpriority="low" />
    </header>
    @if (error()) { <p class="aviso error" role="alert">{{ error() }}</p> }
    @if (mensaje()) { <p class="aviso" role="status">{{ mensaje() }}</p> }
    @if (cargando()) { <p class="tarjeta" role="status">Cargando equipo…</p> }
    <div class="contenido">
      <section class="tarjeta formulario-panel" aria-labelledby="titulo-formulario">
        <p class="ceja">FICHA PROFESIONAL</p><h2 id="titulo-formulario">{{ editando() ? 'Editar perfil' : 'Agregar profesional' }}</h2>
        @if (!especialidades().length || !sedes().length) { <p class="ayuda">Para registrar un profesional, primero configure al menos una especialidad activa y una sede en su ámbito.</p> }
        <form (ngSubmit)="guardar()">
          <div class="campos">
            <label><span>Nombres</span><input name="nombre" [(ngModel)]="form.nombre" maxlength="100" required autocomplete="given-name" /></label>
            <label><span>Apellidos</span><input name="apellido" [(ngModel)]="form.apellido" maxlength="100" required autocomplete="family-name" /></label>
            <label><span>Especialidad</span><select name="especialidad" [(ngModel)]="form.especialidad_id" required><option value="">Seleccione</option>@for (item of especialidades(); track item.id) { <option [value]="item.id">{{ item.nombre }}</option> }</select></label>
            <label><span>Registro profesional</span><input name="registro" [(ngModel)]="form.numero_registro_profesional" maxlength="64" /></label>
            <label><span>Teléfono de contacto</span><input name="telefono" [(ngModel)]="form.telefono_whatsapp" maxlength="32" autocomplete="tel" /></label>
            <label><span>Correo de calendario</span><input name="correo" type="email" [(ngModel)]="form.correo_calendario" maxlength="200" autocomplete="email" /></label>
            <label><span>Disponibilidad</span><select name="estado" [(ngModel)]="form.estado_disponibilidad">@for (estado of estados; track estado.codigo) { <option [value]="estado.codigo">{{ estado.etiqueta }}</option> }</select></label>
            <label><span>Preparación entre citas (min)</span><input name="preparacion" type="number" min="0" max="240" [(ngModel)]="form.minutos_preparacion_propio" required /></label>
          </div>
          <fieldset><legend>Sedes de atención</legend>
            @for (sede of sedes(); track sede.id) { <label class="sede-opcion"><input type="checkbox" [checked]="form.sede_ids.includes(sede.id)" (change)="cambiarSede(sede.id, $any($event.target).checked)" />{{ sede.nombre }}</label> }
          </fieldset>
          <label class="principal"><span>Sede principal</span><select name="sede-principal" [(ngModel)]="form.sede_principal_id" [disabled]="!form.sede_ids.length" required><option value="">Seleccione</option>@for (id of form.sede_ids; track id) { <option [value]="id">{{ nombreSede(id) }}</option> }</select></label>
          <label class="check"><input type="checkbox" name="acepta-pacientes" [(ngModel)]="form.acepta_pacientes_nuevos" /> Acepta pacientes nuevos</label>
          @if (editando()) { <label class="check"><input type="checkbox" name="activo" [(ngModel)]="form.activo" /> Perfil activo</label> }
          <div class="acciones"><button class="boton primario" type="submit" [disabled]="cargando() || guardando() || !sedes().length || !especialidades().length">{{ cargando() ? 'Cargando equipo…' : guardando() ? 'Guardando…' : editando() ? 'Guardar cambios' : 'Crear perfil' }}</button>@if (editando()) { <button class="boton" type="button" (click)="nuevo()">Cancelar</button> }</div>
        </form>
        <p class="nota">El acceso de usuario y sus roles se administran por separado en Usuarios y roles. El perfil no crea credenciales.</p>
      </section>
      <section class="tarjeta lista" aria-labelledby="titulo-equipo">
        <p class="ceja">PERSONAL REGISTRADO</p><h2 id="titulo-equipo">Equipo</h2>
        @for (perfil of perfiles(); track perfil.id) {
          <article class="fila"><div class="datos"><div class="titulo"><h3>{{ perfil.nombre }} {{ perfil.apellido }}</h3><span class="estado" [class.inactivo]="!perfil.activo">{{ perfil.activo ? etiquetaEstado(perfil.estado_disponibilidad) : 'Inactivo' }}</span></div><p>{{ nombreEspecialidad(perfil.especialidad_id) }} · {{ perfil.numero_registro_profesional || 'Sin registro profesional' }}</p><small>{{ etiquetasSedes(perfil.sede_ids) }}</small></div><button class="boton" type="button" (click)="editar(perfil)">Editar</button></article>
        } @empty { @if (!cargando()) { <p class="vacio">No hay profesionales registrados en las sedes visibles.</p> } }
      </section>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  // `--acento` y no `--primario`: este último no existe entre los tokens y el
  // botón principal quedaba con fondo transparente y texto blanco (axe, 1,08:1).
  styles: [`
    :host{display:block;padding:clamp(16px,3vw,32px);color:var(--texto)}.encabezado{position:relative;isolation:isolate;display:flex;align-items:center;min-height:clamp(170px,20vw,230px);overflow:hidden;padding:clamp(20px,3vw,32px);margin-bottom:20px;border:1px solid var(--borde);border-radius:var(--radio);background:linear-gradient(105deg,#f8fcfb 0%,#edf7f5 62%,#e3f1ef 100%)}.encabezado__texto{position:relative;z-index:2;max-width:560px}.encabezado h1,.tarjeta h2{margin:0}.encabezado p:last-child,.ayuda,.nota,.fila p,.fila small,.vacio{color:var(--texto-suave)}.encabezado img{position:absolute;z-index:0;inset:0 0 0 auto;width:min(62%,760px);height:100%;object-fit:cover;object-position:center 51%;mask-image:linear-gradient(90deg,transparent 0%,#000 32%);transform-origin:70% center;animation:equipo-ilustracion 24s ease-in-out infinite alternate}.encabezado::after{content:"";position:absolute;z-index:1;inset:-60%;pointer-events:none;background:radial-gradient(ellipse at 82% 46%,rgb(95 209 196 / 17%),transparent 34%);animation:equipo-halo 20s ease-in-out infinite alternate}.encabezado .ceja{display:flex;align-items:center;gap:var(--espacio-2)}@keyframes equipo-ilustracion{from{transform:translate3d(0,2px,0) scale(1)}to{transform:translate3d(0,-3px,0) scale(1.018)}}@keyframes equipo-halo{from{transform:translate3d(-1%,1%,0) scale(.98);opacity:.55}to{transform:translate3d(2%,-1%,0) scale(1.04);opacity:1}}.contenido{display:grid;grid-template-columns:minmax(340px,.9fr) minmax(0,1.1fr);gap:18px;align-items:start}.tarjeta{background:var(--superficie);border:1px solid var(--borde);border-radius:var(--radio);padding:22px;box-shadow:var(--sombra-tarjeta,0 8px 28px #0b1f3510)}.ceja{font-size:.72rem;font-weight:750;letter-spacing:.11em;color:var(--acento);margin:0 0 7px}.campos{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:18px 0}.campos label,.principal{display:grid;gap:6px;min-width:0}.campos label span,.principal span,legend{font-size:.83rem;font-weight:650}.campos input,.campos select,.principal select{width:100%;min-width:0;border:1px solid var(--borde);border-radius:9px;padding:10px;background:var(--superficie);color:var(--texto);font:inherit}fieldset{border:1px solid var(--borde);border-radius:10px;padding:12px;margin:14px 0}.sede-opcion{display:inline-flex;gap:8px;align-items:center;margin:6px 12px 6px 0;font-size:.9rem}.principal{max-width:300px;margin:12px 0}.principal select{margin-top:5px}.check{display:flex;gap:8px;align-items:center;margin:12px 0;font-size:.9rem}.acciones{display:flex;gap:8px;margin-top:16px}.boton{border:1px solid var(--borde);border-radius:9px;padding:9px 13px;background:var(--superficie);color:var(--texto);cursor:pointer;font:inherit}.boton.primario{background:var(--acento);border-color:var(--acento);color:white}.boton:disabled{opacity:.55;cursor:not-allowed}.nota{font-size:.8rem;line-height:1.5;margin:16px 0 0}.fila{display:flex;justify-content:space-between;gap:14px;align-items:center;padding:15px 0;border-top:1px solid var(--borde)}.datos{min-width:0}.titulo{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.fila h3{margin:0;font-size:1rem}.fila p{margin:5px 0}.fila small{display:block;overflow-wrap:anywhere}.estado{border-radius:100px;padding:3px 9px;background:var(--exito-fondo,#e9f7ef);color:var(--exito,#11784a);font-size:.74rem;font-weight:700}.estado.inactivo{background:var(--peligro-fondo,#fff0ef);color:var(--peligro,#a12820)}.aviso{padding:12px 16px;border-radius:9px;background:var(--exito-fondo,#e9f7ef);color:var(--exito,#11784a)}.aviso.error{background:var(--peligro-fondo,#fff0ef);color:var(--peligro,#a12820)}
    @media(max-width:950px){.contenido{grid-template-columns:1fr}}@media(max-width:600px){:host{padding:14px}.encabezado{min-height:190px;align-items:flex-start;padding:20px}.encabezado img{width:76%;opacity:.58;mask-image:linear-gradient(90deg,transparent 0%,#000 42%)}.campos{grid-template-columns:1fr}.tarjeta{padding:17px}.fila{align-items:flex-start;flex-direction:column}.fila>button{align-self:flex-end}}@media(prefers-reduced-motion:reduce){.encabezado img,.encabezado::after{animation:none}}
  `],
})
export class EquipoComponent implements OnInit {
  private readonly catalogo = inject(CatalogoService);
  private readonly equipo = inject(EquipoService);
  protected readonly sedes = signal<readonly Sede[]>([]);
  protected readonly especialidades = signal<readonly Especialidad[]>([]);
  protected readonly perfiles = signal<readonly PerfilProfesional[]>([]);
  protected readonly estados = ESTADOS;
  protected readonly cargando = signal(false);
  protected readonly guardando = signal(false);
  protected readonly error = signal('');
  protected readonly mensaje = signal('');
  protected readonly editando = signal('');
  protected form = this.vacio();
  private cargasInicialesPendientes = 3;

  ngOnInit(): void {
    this.cargando.set(true);
    this.catalogo.sedes().subscribe({
      next: (sedes) => { this.sedes.set(sedes); this.completarCargaInicial(); },
      error: () => { this.fallar('No se pudieron cargar las sedes.'); this.completarCargaInicial(); },
    });
    this.catalogo.especialidades().subscribe({
      next: (items) => { this.especialidades.set(items); this.completarCargaInicial(); },
      error: () => { this.fallar('No se pudieron cargar las especialidades.'); this.completarCargaInicial(); },
    });
    this.equipo.listar().subscribe({
      next: (items) => { this.perfiles.set(items); this.completarCargaInicial(); },
      error: () => { this.fallar('No se pudo cargar el equipo profesional.'); this.completarCargaInicial(); },
    });
  }

  private completarCargaInicial(): void {
    this.cargasInicialesPendientes -= 1;
    if (this.cargasInicialesPendientes === 0) this.cargando.set(false);
  }

  protected cambiarSede(id: string, marcada: boolean): void {
    const sedes = marcada ? [...new Set([...this.form.sede_ids, id])] : this.form.sede_ids.filter((actual) => actual !== id);
    this.form.sede_ids = sedes;
    if (!sedes.includes(this.form.sede_principal_id)) this.form.sede_principal_id = sedes[0] ?? '';
  }

  protected guardar(): void {
    if (!this.form.nombre.trim() || !this.form.apellido.trim() || !this.form.especialidad_id || !this.form.sede_ids.length || !this.form.sede_principal_id) {
      this.fallar('Complete nombre, apellido, especialidad y al menos una sede.');
      return;
    }
    this.guardando.set(true); this.error.set(''); this.mensaje.set('');
    const datos: DatosPerfilProfesional = {
      ...this.form,
      nombre: this.form.nombre.trim(),
      apellido: this.form.apellido.trim(),
      numero_registro_profesional: this.form.numero_registro_profesional.trim() || null,
      telefono_whatsapp: this.form.telefono_whatsapp.trim() || null,
      correo_calendario: this.form.correo_calendario.trim() || null,
    };
    const operacion = this.editando() ? this.equipo.actualizar(this.editando(), datos) : this.equipo.crear(datos);
    operacion.subscribe({
      next: (perfil) => {
        this.mensaje.set(this.editando() ? 'Perfil profesional actualizado.' : 'Profesional agregado al equipo.');
        this.guardando.set(false); this.nuevo(); this.equipo.invalidarCatalogo();
        this.perfiles.update((lista) => [perfil, ...lista.filter((item) => item.id !== perfil.id)]);
      },
      error: (fallo: unknown) => { this.fallar(this.mensajeError(fallo, 'No se pudo guardar el perfil profesional.')); this.guardando.set(false); },
    });
  }

  protected editar(perfil: PerfilProfesional): void {
    this.editando.set(perfil.id);
    this.form = {
      especialidad_id: perfil.especialidad_id, nombre: perfil.nombre, apellido: perfil.apellido,
      numero_registro_profesional: perfil.numero_registro_profesional ?? '', telefono_whatsapp: perfil.telefono_whatsapp ?? '',
      correo_calendario: perfil.correo_calendario ?? '', estado_disponibilidad: perfil.estado_disponibilidad === 'INACTIVO' ? 'DISPONIBLE' : perfil.estado_disponibilidad,
      acepta_pacientes_nuevos: perfil.acepta_pacientes_nuevos, minutos_preparacion_propio: perfil.minutos_preparacion_propio,
      activo: perfil.activo, sede_ids: [...perfil.sede_ids], sede_principal_id: perfil.sede_principal_id ?? perfil.sede_ids[0] ?? '',
    };
    this.mensaje.set(''); this.error.set('');
  }

  protected nuevo(): void { this.editando.set(''); this.form = this.vacio(); }
  protected nombreSede(id: string): string { return this.sedes().find((sede) => sede.id === id)?.nombre ?? 'Sede'; }
  protected etiquetasSedes(ids: readonly string[]): string { return ids.map((id) => this.nombreSede(id)).join(' · '); }
  protected nombreEspecialidad(id: string): string { return this.especialidades().find((item) => item.id === id)?.nombre ?? 'Especialidad'; }
  protected etiquetaEstado(estado: EstadoDisponibilidadProfesional): string { return ESTADOS.find((item) => item.codigo === estado)?.etiqueta ?? estado; }

  private vacio(): FormularioEquipo { return { especialidad_id: '', nombre: '', apellido: '', numero_registro_profesional: '', telefono_whatsapp: '', correo_calendario: '', estado_disponibilidad: 'DISPONIBLE', acepta_pacientes_nuevos: true, minutos_preparacion_propio: 0, activo: true, sede_ids: [], sede_principal_id: '' }; }
  private fallar(texto: string): void { this.error.set(texto); }
  private mensajeError(error: unknown, alternativo: string): string { return error instanceof HttpErrorResponse && typeof error.error?.mensaje === 'string' ? error.error.mensaje : alternativo; }
}
