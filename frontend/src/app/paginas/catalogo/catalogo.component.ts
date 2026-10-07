import { Component, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { forkJoin, of } from 'rxjs';

import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { ModulosEspecialidadComponent } from './modulos-especialidad.component';
import type { Consultorio, Especialidad, Sede, Servicio, Profesional, TipoConsultorio } from '../../nucleo/modelos/dominio';
import type { DatosServicio, ServicioGestion } from '../../nucleo/servicios/catalogo.service';

const TIPOS: readonly { readonly valor: TipoConsultorio; readonly etiqueta: string }[] = [
  { valor: 'CONSULTA', etiqueta: 'Consulta' },
  { valor: 'PROCEDIMIENTOS', etiqueta: 'Procedimientos' },
  { valor: 'IMAGEN', etiqueta: 'Imagen' },
  { valor: 'LABORATORIO', etiqueta: 'Laboratorio' },
  { valor: 'OTRO', etiqueta: 'Otro' },
];

@Component({
  selector: 'app-catalogo', standalone: true, imports: [FormsModule, ModulosEspecialidadComponent],
  template: `
    <header class="modulo-cabecera"><div class="modulo-cabecera__texto"><p class="ceja">CONFIGURACIÓN</p><h1>Catálogo de la clínica</h1><p>Sedes, consultorios, servicios y profesionales disponibles para su sesión.</p></div><img class="modulo-cabecera__imagen" src="/images/catalogo-clinica.png" alt="" aria-hidden="true" loading="lazy" /></header>
    @if (error()) { <p class="aviso error" role="alert">{{ error() }}</p><button (click)="cargar()" class="boton">Reintentar</button> }
    @if (mensaje()) { <p class="aviso exito" role="status">{{ mensaje() }}</p> }
    @if (cargando()) { <p role="status">Cargando catálogo…</p> }
    <h2>Sedes</h2><div class="rejilla">@for (s of sedes(); track s.id) { <article class="tarjeta"><h3>{{ s.nombre }}</h3><p>{{ s.direccion || 'Dirección no registrada' }}</p><small>{{ s.zona_horaria }}</small></article> }</div>

    <section class="gestion" aria-labelledby="titulo-consultorios">
      <div class="seccion-cabecera"><div><p class="ceja">ESPACIOS DE ATENCIÓN</p><h2 id="titulo-consultorios">Consultorios</h2><p>Administre los espacios disponibles en cada sede.</p></div>
        @if (puedeGestionar()) { <label class="campo sede"><span>Sede</span><select [ngModel]="sedeSeleccionada()" (ngModelChange)="seleccionarSede($event)"><option value="">Seleccione una sede</option>@for (s of sedes(); track s.id) { <option [value]="s.id">{{ s.nombre }}</option> }</select></label> }
      </div>
      @if (!puedeGestionar()) {
        <div class="rejilla">@for (sala of consultorios(); track sala.id) { <article class="tarjeta"><span class="etiqueta">{{ etiquetaTipo(sala.tipo) }}</span><h3>{{ sala.nombre }}</h3><p>Capacidad: {{ sala.capacidad }}</p></article> } @empty { <p>No hay consultorios disponibles.</p> }</div>
      } @else if (sedeSeleccionada()) {
        <div class="panel-gestion">
          <form class="formulario" (ngSubmit)="guardar()">
            <h3>{{ editando() ? 'Editar consultorio' : 'Nuevo consultorio' }}</h3>
            <label class="campo"><span>Nombre</span><input name="nombre" [(ngModel)]="form.nombre" required maxlength="100" placeholder="Ej. Consultorio 1" /></label>
            <label class="campo"><span>Tipo</span><select name="tipo" [(ngModel)]="form.tipo">@for (tipo of tipos; track tipo.valor) { <option [value]="tipo.valor">{{ tipo.etiqueta }}</option> }</select></label>
            <label class="campo"><span>Capacidad</span><input name="capacidad" type="number" [(ngModel)]="form.capacidad" min="1" max="100" required /></label>
            <div class="acciones"><button class="boton primario" type="submit" [disabled]="guardando()">{{ guardando() ? 'Guardando…' : editando() ? 'Guardar cambios' : 'Crear consultorio' }}</button>@if (editando()) { <button class="boton secundario" type="button" (click)="nuevo()">Cancelar</button> }</div>
          </form>
          <div class="tabla-envoltorio"><table class="tabla"><thead><tr><th>Consultorio</th><th>Tipo</th><th>Capacidad</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>
            @for (sala of consultorios(); track sala.id) { <tr><td>{{ sala.nombre }}</td><td>{{ etiquetaTipo(sala.tipo) }}</td><td>{{ sala.capacidad }}</td><td><span class="estado" [class.inactivo]="!sala.activo">{{ sala.activo ? 'Activo' : 'Inactivo' }}</span></td><td class="acciones-fila"><button class="boton compacto" type="button" (click)="editar(sala)">Editar</button><button class="boton compacto" type="button" (click)="cambiarEstado(sala)">{{ sala.activo ? 'Desactivar' : 'Activar' }}</button></td></tr> }
            @empty { <tr><td colspan="5">No hay consultorios registrados en esta sede.</td></tr> }
          </tbody></table></div>
        </div>
      } @else { <p class="ayuda">Seleccione una sede para consultar y administrar sus consultorios.</p> }
    </section>

    @if (puedeGestionarEspecialidades()) {
      <section class="gestion catalogo-admin" aria-labelledby="titulo-especialidades">
        <div class="seccion-cabecera"><div><p class="ceja">ORGANIZACIÓN CLÍNICA</p><h2 id="titulo-especialidades">Especialidades</h2><p>Organice las áreas de atención y mantenga actualizado su catálogo.</p></div></div>
        <div class="panel-gestion">
          <form class="formulario" (ngSubmit)="guardarEspecialidad()">
            <h3>{{ editandoEspecialidad() ? 'Editar especialidad' : 'Nueva especialidad' }}</h3>
            <label class="campo"><span>Nombre</span><input name="especialidad-nombre" [(ngModel)]="formEspecialidad.nombre" maxlength="150" required /></label>
            <label class="campo"><span>Código</span><input name="especialidad-codigo" [(ngModel)]="formEspecialidad.codigo" maxlength="32" /></label>
            <label class="campo"><span>Descripción</span><textarea name="especialidad-descripcion" [(ngModel)]="formEspecialidad.descripcion" rows="3"></textarea></label>
            <div class="acciones"><button class="boton primario" type="submit" [disabled]="guardando()">{{ editandoEspecialidad() ? 'Guardar cambios' : 'Crear especialidad' }}</button>@if (editandoEspecialidad()) { <button class="boton" type="button" (click)="nuevaEspecialidad()">Cancelar</button> }</div>
          </form>
          <div class="tabla-envoltorio"><table class="tabla"><thead><tr><th>Especialidad</th><th>Código</th><th>Estado</th><th></th></tr></thead><tbody>
            @for (esp of especialidadesGestion(); track esp.id) { <tr><td>{{ esp.nombre }}<small class="descripcion">{{ esp.descripcion }}</small></td><td>{{ esp.codigo || '—' }}</td><td><span class="estado" [class.inactivo]="!esp.activa">{{ esp.activa ? 'Activa' : 'Inactiva' }}</span></td><td class="acciones-fila"><button class="boton compacto" type="button" (click)="editarEspecialidad(esp)">Editar</button><button class="boton compacto" type="button" (click)="cambiarEstadoEspecialidad(esp)">{{ esp.activa ? 'Desactivar' : 'Activar' }}</button></td></tr> } @empty { <tr><td colspan="4">Aún no hay especialidades registradas.</td></tr> }
          </tbody></table></div>
        </div>
      </section>
      <app-modulos-especialidad />
    }

    @if (puedeGestionarServicios()) {
      <div class="gestion catalogo-admin">
        <div class="seccion-cabecera"><div><p class="ceja">OFERTA CLÍNICA</p><h2>Servicios</h2><p>Configure duración, preparación, precio y requisitos de agenda.</p></div></div>
        <div class="panel-gestion">
          <form class="formulario" (ngSubmit)="guardarServicio()">
            <h3>{{ editandoServicio() ? 'Editar servicio' : 'Nuevo servicio' }}</h3>
            <label class="campo"><span>Especialidad</span><select name="servicio-especialidad" [(ngModel)]="formServicio.especialidad_id" [disabled]="!!editandoServicio()" required><option value="">Seleccione</option>@for (esp of especialidades(); track esp.id) { <option [value]="esp.id">{{ esp.nombre }}</option> }</select></label>
            <label class="campo"><span>Nombre</span><input name="servicio-nombre" [(ngModel)]="formServicio.nombre" maxlength="200" required /></label>
            <label class="campo"><span>Descripción</span><textarea name="servicio-descripcion" [(ngModel)]="formServicio.descripcion" rows="2"></textarea></label>
            <div class="campos-dos"><label class="campo"><span>Duración (min)</span><input name="servicio-duracion" type="number" [(ngModel)]="formServicio.duracion_minutos" min="1" max="1440" required /></label><label class="campo"><span>Preparación (min)</span><input name="servicio-preparacion" type="number" [(ngModel)]="formServicio.minutos_preparacion" min="0" max="1440" /></label></div>
            <div class="campos-dos"><label class="campo"><span>Precio</span><input name="servicio-precio" type="number" [(ngModel)]="formServicio.precio" min="0" step="0.01" /></label><label class="campo"><span>Moneda</span><input name="servicio-moneda" [(ngModel)]="formServicio.moneda" maxlength="3" required /></label></div>
            <label class="campo"><span>Consultorio requerido</span><select name="servicio-consultorio" [(ngModel)]="formServicio.tipo_consultorio_requerido"><option [ngValue]="null">Sin requisito</option>@for (tipo of tipos; track tipo.valor) { <option [ngValue]="tipo.valor">{{ tipo.etiqueta }}</option> }</select></label>
            <label class="campo"><span class="opcion"><input name="servicio-pago-previo" type="checkbox" [(ngModel)]="formServicio.requiere_pago_previo" /> Requiere pago previo</span></label>
            <label class="campo"><span>Indicaciones de preparación</span><textarea name="servicio-indicaciones" [(ngModel)]="formServicio.instrucciones_preparacion" rows="2"></textarea></label>
            <div class="acciones"><button class="boton primario" type="submit" [disabled]="guardando()">{{ editandoServicio() ? 'Guardar cambios' : 'Crear servicio' }}</button>@if (editandoServicio()) { <button class="boton" type="button" (click)="nuevoServicio()">Cancelar</button> }</div>
          </form>
          <div class="tabla-envoltorio"><table class="tabla"><thead><tr><th>Servicio</th><th>Especialidad</th><th>Duración</th><th>Precio</th><th>Estado</th><th></th></tr></thead><tbody>
            @for (s of serviciosGestion(); track s.id) { <tr><td>{{ s.nombre }}</td><td>{{ nombreEspecialidad(s.especialidad_id) }}</td><td>{{ s.duracion_minutos }} min</td><td>{{ s.precio === null ? 'Consultar' : s.moneda + ' ' + s.precio }}</td><td><span class="estado" [class.inactivo]="!s.activo">{{ s.activo ? 'Activo' : 'Inactivo' }}</span></td><td class="acciones-fila"><button class="boton compacto" type="button" (click)="editarServicio(s)">Editar</button><button class="boton compacto" type="button" (click)="cambiarEstadoServicio(s)">{{ s.activo ? 'Desactivar' : 'Activar' }}</button></td></tr> } @empty { <tr><td colspan="6">Aún no hay servicios registrados.</td></tr> }
          </tbody></table></div>
        </div>
      </div>
    } @else {
      <h2>Servicios</h2><div class="tabla-envoltorio"><table class="tabla"><thead><tr><th>Servicio</th><th>Duración</th><th>Preparación</th><th>Precio</th></tr></thead><tbody>
        @for (s of servicios(); track s.id) { <tr><td>{{ s.nombre }}</td><td>{{ s.duracion_minutos }} min</td><td>{{ s.minutos_preparacion }} min</td><td>{{ s.precio === null ? 'Consultar' : (s.moneda || '$') + ' ' + s.precio }}</td></tr> }
      </tbody></table></div>
    }
    <h2>Profesionales</h2><div class="rejilla">@for (p of profesionales(); track p.id) { <article class="tarjeta"><h3>{{ p.nombre }} {{ p.apellido }}</h3><p>Registro {{ p.numero_registro_profesional || 'no registrado' }}</p></article> }</div>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    h2 { margin-top: 24px; } .gestion { margin-top: 30px; padding: 22px; border: 1px solid var(--borde, #dce5ec); border-radius: 16px; background: var(--superficie, #fff); } .catalogo-admin h2 { margin-top: 4px; }
    .seccion-cabecera { display:flex; align-items:end; justify-content:space-between; gap:20px; margin-bottom:18px; } .seccion-cabecera h2 { margin:4px 0; } .seccion-cabecera p { margin:4px 0; color:var(--texto-secundario, var(--texto-tenue)); }
    .ceja { font-size:.72rem; font-weight:700; letter-spacing:.09em; color:var(--primario, #087e8b); } .sede { min-width:230px; }
    .panel-gestion { display:grid; grid-template-columns:minmax(220px, .72fr) minmax(0, 1.7fr); gap:24px; align-items:start; } .formulario { display:grid; gap:14px; padding:16px; border-radius:12px; background:var(--superficie-suave, #f5f8fa); }
    .formulario h3 { margin:0; } .campo { display:grid; gap:6px; font-size:.88rem; font-weight:600; } .campo input,.campo select,.campo textarea { min-height:42px; padding:8px 10px; border:1px solid #cbd5e1; border-radius:8px; background:white; font:inherit; } .campos-dos { display:grid; grid-template-columns:1fr 1fr; gap:10px; } .opcion { display:flex; align-items:center; gap:8px; } .opcion input { min-height:auto; } .descripcion { display:block; margin-top:4px; color:var(--texto-tenue); font-weight:400; }
    .acciones,.acciones-fila { display:flex; align-items:center; gap:8px; flex-wrap:wrap; } .boton { cursor:pointer; border:1px solid #cbd5e1; border-radius:8px; padding:9px 13px; background:white; font:inherit; } .boton.primario { color:white; border-color:#087e8b; background:#087e8b; } .boton:disabled { opacity:.6; cursor:wait; } .compacto { padding:6px 9px; font-size:.82rem; }
    .estado,.etiqueta { display:inline-block; border-radius:999px; padding:4px 9px; color:#087443; background:#e8f7ef; font-size:.78rem; font-weight:650; } .estado.inactivo { color:var(--texto-tenue); background:#eef2f6; } .etiqueta { color:#176b76; background:#e8f5f6; }
    .aviso { padding:12px 14px; border-radius:9px; } .aviso.error { background:#fff0ef; color:#a12820; } .aviso.exito { background:#e8f7ef; color:#087443; } .ayuda { color:var(--texto-tenue); }
    @media (max-width:850px) { .panel-gestion { grid-template-columns:1fr; } .panel-gestion > *, .formulario, .campo { min-width:0; } .campo input,.campo select,.campo textarea { width:100%; max-width:100%; } .campos-dos { grid-template-columns:1fr; } .seccion-cabecera { align-items:stretch; flex-direction:column; } .tabla-envoltorio { overflow-x:auto; } }
  `,
})
export class CatalogoComponent {
  private readonly catalogo = inject(CatalogoService);
  private readonly sesion = inject(SesionService);
  protected readonly tipos = TIPOS;
  protected readonly puedeGestionar = signal(this.sesion.tienePermiso('sede.gestionar'));
  protected readonly puedeGestionarEspecialidades = signal(this.sesion.tienePermiso('especialidad.gestionar'));
  protected readonly puedeGestionarServicios = signal(this.sesion.tienePermiso('servicio.gestionar'));
  protected readonly sedes = signal<readonly Sede[]>([]);
  protected readonly especialidades = signal<readonly Especialidad[]>([]);
  protected readonly especialidadesGestion = signal<readonly Especialidad[]>([]);
  protected readonly servicios = signal<readonly Servicio[]>([]);
  protected readonly serviciosGestion = signal<readonly ServicioGestion[]>([]);
  protected readonly profesionales = signal<readonly Profesional[]>([]);
  protected readonly consultorios = signal<readonly Consultorio[]>([]);
  protected readonly sedeSeleccionada = signal('');
  protected readonly cargando = signal(true);
  protected readonly guardando = signal(false);
  protected readonly error = signal('');
  protected readonly mensaje = signal('');
  protected readonly editando = signal('');
  protected readonly editandoEspecialidad = signal('');
  protected readonly editandoServicio = signal('');
  protected form: { nombre: string; tipo: TipoConsultorio; capacidad: number } = { nombre: '', tipo: 'CONSULTA', capacidad: 1 };
  protected formEspecialidad = { nombre: '', codigo: '', descripcion: '' };
  protected formServicio: {
    especialidad_id: string; nombre: string; descripcion: string | null; duracion_minutos: number;
    minutos_preparacion: number; precio: number | null; moneda: string; requiere_pago_previo: boolean;
    instrucciones_preparacion: string | null; tipo_consultorio_requerido: TipoConsultorio | null;
  } = this.formularioServicioVacio();

  constructor() { this.cargar(); }

  protected cargar(): void {
    this.error.set(''); this.cargando.set(true);
    forkJoin({ sedes: this.catalogo.sedes(), especialidades: this.catalogo.especialidades(), servicios: this.catalogo.servicios(), profesionales: this.catalogo.profesionales() }).subscribe({
      next: (r) => {
        this.sedes.set(r.sedes); this.especialidades.set(r.especialidades); this.servicios.set(r.servicios); this.profesionales.set(r.profesionales);
        if (!this.puedeGestionar()) {
          this.catalogo.consultorios().subscribe({ next: (items) => this.consultorios.set(items), error: () => this.error.set('No se pudieron cargar los consultorios.') });
        } else if (r.sedes.length === 1) { this.seleccionarSede(r.sedes[0].id); }
        this.cargando.set(false);
        this.cargarInventarios();
      },
      error: () => { this.error.set('No se pudo cargar el catálogo.'); this.cargando.set(false); },
    });
  }

  protected seleccionarSede(id: string): void {
    this.sedeSeleccionada.set(id); this.consultorios.set([]); this.nuevo(); this.error.set(''); this.mensaje.set('');
    if (id) this.catalogo.consultoriosGestion(id).subscribe({ next: (items) => this.consultorios.set(items), error: () => this.error.set('No se pudieron cargar los consultorios de esta sede.') });
  }

  protected guardar(): void {
    if (!this.form.nombre.trim() || !this.sedeSeleccionada()) return;
    this.guardando.set(true); this.error.set(''); this.mensaje.set('');
    const operacion = this.editando()
      ? this.catalogo.actualizarConsultorio(this.editando(), { ...this.form, nombre: this.form.nombre.trim() })
      : this.catalogo.crearConsultorio({ ...this.form, nombre: this.form.nombre.trim(), sede_id: this.sedeSeleccionada() });
    operacion.subscribe({
      next: () => {
        const confirmacion = this.editando() ? 'Consultorio actualizado.' : 'Consultorio creado.';
        this.guardando.set(false); this.seleccionarSede(this.sedeSeleccionada()); this.mensaje.set(confirmacion);
      },
      error: (e: { error?: { mensaje?: string; detail?: string } }) => { this.guardando.set(false); this.error.set(e.error?.mensaje ?? e.error?.detail ?? 'No se pudo guardar el consultorio. Verifique que el nombre no esté repetido.'); },
    });
  }

  protected editar(sala: Consultorio): void {
    this.editando.set(sala.id); this.form = { nombre: sala.nombre, tipo: sala.tipo, capacidad: sala.capacidad }; this.mensaje.set(''); this.error.set('');
  }

  protected nuevo(): void { this.editando.set(''); this.form = { nombre: '', tipo: 'CONSULTA', capacidad: 1 }; }

  protected cambiarEstado(sala: Consultorio): void {
    this.error.set(''); this.mensaje.set('');
    this.catalogo.cambiarEstadoConsultorio(sala.id, !sala.activo).subscribe({
      next: () => {
        const confirmacion = sala.activo ? 'Consultorio desactivado.' : 'Consultorio activado.';
        this.seleccionarSede(this.sedeSeleccionada()); this.mensaje.set(confirmacion);
      },
      error: () => this.error.set('No se pudo cambiar el estado del consultorio.'),
    });
  }

  protected etiquetaTipo(tipo: TipoConsultorio): string { return TIPOS.find((item) => item.valor === tipo)?.etiqueta ?? tipo; }

  protected nombreEspecialidad(id: string): string {
    return this.especialidades().find((item) => item.id === id)?.nombre
      ?? this.especialidadesGestion().find((item) => item.id === id)?.nombre
      ?? 'Especialidad';
  }

  protected guardarEspecialidad(): void {
    const datos = {
      nombre: this.formEspecialidad.nombre.trim(),
      codigo: this.formEspecialidad.codigo.trim() || null,
      descripcion: this.formEspecialidad.descripcion.trim() || null,
    };
    if (!datos.nombre) return;
    this.guardando.set(true); this.error.set(''); this.mensaje.set('');
    const editar = this.editandoEspecialidad();
    const peticion = editar
      ? this.catalogo.actualizarEspecialidad(editar, datos)
      : this.catalogo.crearEspecialidad(datos);
    peticion.subscribe({
      next: () => {
        this.guardando.set(false); this.nuevaEspecialidad(); this.cargarInventarios();
        this.catalogo.especialidades().subscribe({ next: (items) => this.especialidades.set(items) });
        this.mensaje.set(editar ? 'Especialidad actualizada.' : 'Especialidad creada.');
      },
      error: (e: { error?: { mensaje?: string; detail?: string } }) => {
        this.guardando.set(false); this.error.set(e.error?.mensaje ?? e.error?.detail ?? 'No se pudo guardar la especialidad.');
      },
    });
  }

  protected editarEspecialidad(item: Especialidad): void {
    this.editandoEspecialidad.set(item.id);
    this.formEspecialidad = { nombre: item.nombre, codigo: item.codigo ?? '', descripcion: item.descripcion ?? '' };
    this.error.set(''); this.mensaje.set('');
  }

  protected nuevaEspecialidad(): void {
    this.editandoEspecialidad.set(''); this.formEspecialidad = { nombre: '', codigo: '', descripcion: '' };
  }

  protected cambiarEstadoEspecialidad(item: Especialidad): void {
    this.error.set(''); this.mensaje.set('');
    this.catalogo.cambiarEstadoEspecialidad(item.id, !item.activa).subscribe({
      next: () => {
        this.cargarInventarios();
        this.catalogo.especialidades().subscribe({ next: (items) => this.especialidades.set(items) });
        this.mensaje.set(item.activa ? 'Especialidad desactivada.' : 'Especialidad activada.');
      },
      error: (e: { error?: { mensaje?: string; detail?: string } }) => {
        this.error.set(e.error?.mensaje ?? e.error?.detail ?? 'No se pudo cambiar la especialidad. Desactive antes sus servicios activos.');
      },
    });
  }

  protected guardarServicio(): void {
    if (!this.formServicio.nombre.trim() || !this.formServicio.especialidad_id) return;
    this.guardando.set(true); this.error.set(''); this.mensaje.set('');
    const datos: DatosServicio = { ...this.formServicio, nombre: this.formServicio.nombre.trim() };
    const editar = this.editandoServicio();
    const peticion = editar
      ? this.catalogo.actualizarServicio(editar, datos)
      : this.catalogo.crearServicio(datos);
    peticion.subscribe({
      next: () => {
        this.guardando.set(false); this.nuevoServicio(); this.cargarInventarios();
        this.catalogo.servicios().subscribe({ next: (items) => this.servicios.set(items) });
        this.mensaje.set(editar ? 'Servicio actualizado.' : 'Servicio creado.');
      },
      error: (e: { error?: { mensaje?: string; detail?: string } }) => {
        this.guardando.set(false); this.error.set(e.error?.mensaje ?? e.error?.detail ?? 'No se pudo guardar el servicio.');
      },
    });
  }

  protected editarServicio(item: ServicioGestion): void {
    this.editandoServicio.set(item.id);
    this.formServicio = {
      especialidad_id: item.especialidad_id,
      nombre: item.nombre,
      descripcion: item.descripcion ?? null,
      duracion_minutos: item.duracion_minutos,
      minutos_preparacion: item.minutos_preparacion,
      precio: item.precio,
      moneda: item.moneda ?? 'USD',
      requiere_pago_previo: item.requiere_pago_previo,
      instrucciones_preparacion: item.instrucciones_preparacion,
      tipo_consultorio_requerido: item.tipo_consultorio_requerido ?? null,
    };
    this.error.set(''); this.mensaje.set('');
  }

  protected nuevoServicio(): void {
    this.editandoServicio.set(''); this.formServicio = this.formularioServicioVacio();
  }

  protected cambiarEstadoServicio(item: ServicioGestion): void {
    this.error.set(''); this.mensaje.set('');
    this.catalogo.cambiarEstadoServicio(item.id, !item.activo).subscribe({
      next: () => {
        this.cargarInventarios();
        this.catalogo.servicios().subscribe({ next: (items) => this.servicios.set(items) });
        this.mensaje.set(item.activo ? 'Servicio desactivado.' : 'Servicio activado.');
      },
      error: (e: { error?: { mensaje?: string; detail?: string } }) => {
        this.error.set(e.error?.mensaje ?? e.error?.detail ?? 'No se pudo cambiar el estado del servicio.');
      },
    });
  }

  private cargarInventarios(): void {
    if (!this.puedeGestionarEspecialidades() && !this.puedeGestionarServicios()) return;
    forkJoin({
      especialidades: this.puedeGestionarEspecialidades()
        ? this.catalogo.especialidadesGestion() : of<readonly Especialidad[]>([]),
      servicios: this.puedeGestionarServicios()
        ? this.catalogo.serviciosGestion() : of<readonly ServicioGestion[]>([]),
    }).subscribe({
      next: (datos) => {
        this.especialidadesGestion.set(datos.especialidades);
        this.serviciosGestion.set(datos.servicios);
      },
      error: () => this.error.set('No se pudo cargar el inventario clínico.'),
    });
  }

  private formularioServicioVacio(): CatalogoComponent['formServicio'] {
    return {
      especialidad_id: '', nombre: '', descripcion: null, duracion_minutos: 30,
      minutos_preparacion: 0, precio: null, moneda: 'USD', requiere_pago_previo: false,
      instrucciones_preparacion: null, tipo_consultorio_requerido: null,
    };
  }
}
