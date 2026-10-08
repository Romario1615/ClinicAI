import { Component, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { forkJoin, of } from 'rxjs';

import { PestanasComponent, type OpcionPestana } from '../../compartido/pestanas.component';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
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
  selector: 'app-catalogo', standalone: true, imports: [FormsModule, ModulosEspecialidadComponent, VentanaFlotanteComponent, PestanasComponent],
  host: { class: 'pantalla', role: 'region', 'aria-label': 'Catálogo de la clínica' },
  template: `
    <header class="modulo-cabecera pantalla__fijo"><div class="modulo-cabecera__texto"><p class="ceja">CONFIGURACIÓN</p><h1>Catálogo de la clínica</h1><p>Sedes, consultorios, servicios y profesionales disponibles para su sesión.</p></div><img class="modulo-cabecera__imagen" src="/images/catalogo-clinica.png" alt="" aria-hidden="true" loading="lazy" /></header>
    @if (error()) { <div class="aviso-carga pantalla__fijo"><p class="aviso error" role="alert">{{ error() }}</p><button (click)="cargar()" class="boton">Reintentar</button></div> }
    @if (mensaje()) { <p class="aviso exito pantalla__fijo" role="status">{{ mensaje() }}</p> }
    @if (cargando()) { <p class="pantalla__fijo" role="status">Cargando catálogo…</p> }
    <!-- Una parte del catálogo a la vez: apiladas, la pantalla medía 3000 px.
         Las demás se ocultan sin desmontarse. -->
    <app-pestanas class="pantalla__fijo" grupo="catalogo" etiqueta="Partes del catálogo" [opciones]="vistas()" [activa]="vistaActiva()" (activaChange)="vista.set($event)" />

    <div class="pantalla__resto">
      <div class="panel-catalogo pantalla__columnas catalogo__sedes" role="tabpanel" id="catalogo-panel-sedes" aria-labelledby="catalogo-pestana-sedes" [hidden]="vistaActiva() !== 'sedes'">
        <section class="gestion" aria-labelledby="titulo-sedes">
          <div class="seccion-cabecera"><div><p class="ceja">UBICACIONES</p><h2 id="titulo-sedes">Sedes · {{ sedes().length }}</h2></div></div>
          <div class="desplazable" tabindex="0" role="region" aria-labelledby="titulo-sedes">
            <div class="rejilla">@for (s of sedes(); track s.id) { <article class="tarjeta"><h3>{{ s.nombre }}</h3><p>{{ s.direccion || 'Dirección no registrada' }}</p><small>{{ s.zona_horaria }}</small></article> }</div>
          </div>
        </section>

        <section class="gestion" aria-labelledby="titulo-consultorios">
          <div class="seccion-cabecera"><div><p class="ceja">ESPACIOS DE ATENCIÓN</p><h2 id="titulo-consultorios">Consultorios</h2><p>Administre los espacios disponibles en cada sede.</p></div>
            @if (puedeGestionar()) { <div class="acciones-sede"><label class="campo sede"><span>Sede</span><select [ngModel]="sedeSeleccionada()" (ngModelChange)="seleccionarSede($event)"><option value="">Seleccione una sede</option>@for (s of sedes(); track s.id) { <option [value]="s.id">{{ s.nombre }}</option> }</select></label><button class="boton boton--principal" type="button" [disabled]="!sedeSeleccionada()" (click)="abrirNuevoConsultorio()">Nuevo consultorio</button></div> }
          </div>
          @if (!puedeGestionar()) {
            <div class="rejilla desplazable" tabindex="0" role="region" aria-labelledby="titulo-consultorios">@for (sala of consultorios(); track sala.id) { <article class="tarjeta"><span class="etiqueta">{{ etiquetaTipo(sala.tipo) }}</span><h3>{{ sala.nombre }}</h3><p>Capacidad: {{ sala.capacidad }}</p></article> } @empty { <p>No hay consultorios disponibles.</p> }</div>
          } @else if (sedeSeleccionada()) {
            <div class="tabla-envoltorio desplazable" tabindex="0" role="region" aria-labelledby="titulo-consultorios"><table class="tabla"><thead><tr><th>Consultorio</th><th>Tipo</th><th>Capacidad</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>
              @for (sala of consultorios(); track sala.id) { <tr><td>{{ sala.nombre }}</td><td>{{ etiquetaTipo(sala.tipo) }}</td><td>{{ sala.capacidad }}</td><td><span class="estado" [class.inactivo]="!sala.activo">{{ sala.activo ? 'Activo' : 'Inactivo' }}</span></td><td class="acciones-fila"><button class="boton compacto" type="button" (click)="editar(sala)">Editar</button><button class="boton compacto" type="button" (click)="cambiarEstado(sala)">{{ sala.activo ? 'Desactivar' : 'Activar' }}</button></td></tr> }
              @empty { <tr><td colspan="5">No hay consultorios registrados en esta sede.</td></tr> }
            </tbody></table></div>
          } @else { <p class="ayuda">Seleccione una sede para consultar y administrar sus consultorios.</p> }
        </section>
      </div>

      @if (puedeGestionarEspecialidades()) {
        <section class="gestion catalogo-admin panel-catalogo" role="tabpanel" id="catalogo-panel-especialidades" aria-labelledby="catalogo-pestana-especialidades" [hidden]="vistaActiva() !== 'especialidades'">
          <div class="seccion-cabecera"><div><p class="ceja">ORGANIZACIÓN CLÍNICA</p><h2 id="titulo-especialidades">Especialidades</h2><p>Organice las áreas de atención y mantenga actualizado su catálogo.</p></div><button class="boton boton--principal" type="button" (click)="abrirNuevaEspecialidad()">Nueva especialidad</button></div>
          <div class="tabla-envoltorio desplazable" tabindex="0" role="region" aria-labelledby="titulo-especialidades"><table class="tabla"><thead><tr><th>Especialidad</th><th>Código</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>
            @for (esp of especialidadesGestion(); track esp.id) { <tr><td>{{ esp.nombre }}<small class="descripcion">{{ esp.descripcion }}</small></td><td>{{ esp.codigo || '—' }}</td><td><span class="estado" [class.inactivo]="!esp.activa">{{ esp.activa ? 'Activa' : 'Inactiva' }}</span></td><td class="acciones-fila"><button class="boton compacto" type="button" (click)="editarEspecialidad(esp)">Editar</button><button class="boton compacto" type="button" (click)="cambiarEstadoEspecialidad(esp)">{{ esp.activa ? 'Desactivar' : 'Activar' }}</button></td></tr> } @empty { <tr><td colspan="4">Aún no hay especialidades registradas.</td></tr> }
          </tbody></table></div>
        </section>
        <div class="panel-catalogo desplazable" role="tabpanel" tabindex="0" id="catalogo-panel-modulos" aria-labelledby="catalogo-pestana-modulos" [hidden]="vistaActiva() !== 'modulos'">
          <app-modulos-especialidad />
        </div>
      }

      @if (puedeGestionarServicios()) {
        <section class="gestion catalogo-admin panel-catalogo" role="tabpanel" id="catalogo-panel-servicios" aria-labelledby="catalogo-pestana-servicios" [hidden]="vistaActiva() !== 'servicios'">
          <div class="seccion-cabecera"><div><p class="ceja">OFERTA CLÍNICA</p><h2 id="titulo-servicios">Servicios</h2><p>Configure duración, preparación, precio y requisitos de agenda.</p></div><button class="boton boton--principal" type="button" (click)="abrirNuevoServicio()">Nuevo servicio</button></div>
          <div class="tabla-envoltorio desplazable" tabindex="0" role="region" aria-labelledby="titulo-servicios"><table class="tabla"><thead><tr><th>Servicio</th><th>Especialidad</th><th>Duración</th><th>Precio</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>
            @for (s of serviciosGestion(); track s.id) { <tr><td>{{ s.nombre }}</td><td>{{ nombreEspecialidad(s.especialidad_id) }}</td><td>{{ s.duracion_minutos }} min</td><td>{{ s.precio === null ? 'Consultar' : s.moneda + ' ' + s.precio }}</td><td><span class="estado" [class.inactivo]="!s.activo">{{ s.activo ? 'Activo' : 'Inactivo' }}</span></td><td class="acciones-fila"><button class="boton compacto" type="button" (click)="editarServicio(s)">Editar</button><button class="boton compacto" type="button" (click)="cambiarEstadoServicio(s)">{{ s.activo ? 'Desactivar' : 'Activar' }}</button></td></tr> } @empty { <tr><td colspan="6">Aún no hay servicios registrados.</td></tr> }
          </tbody></table></div>
        </section>
      } @else {
        <section class="gestion panel-catalogo" role="tabpanel" id="catalogo-panel-servicios" aria-labelledby="catalogo-pestana-servicios" [hidden]="vistaActiva() !== 'servicios'">
          <div class="seccion-cabecera"><div><p class="ceja">OFERTA CLÍNICA</p><h2 id="titulo-servicios">Servicios</h2></div></div>
          <div class="tabla-envoltorio desplazable" tabindex="0" role="region" aria-labelledby="titulo-servicios"><table class="tabla"><thead><tr><th>Servicio</th><th>Duración</th><th>Preparación</th><th>Precio</th></tr></thead><tbody>
                  @for (s of servicios(); track s.id) { <tr><td>{{ s.nombre }}</td><td>{{ s.duracion_minutos }} min</td><td>{{ s.minutos_preparacion }} min</td><td>{{ s.precio === null ? 'Consultar' : (s.moneda || '$') + ' ' + s.precio }}</td></tr> }
                </tbody></table></div>
        </section>
      }

      <section class="gestion panel-catalogo" role="tabpanel" id="catalogo-panel-profesionales" aria-labelledby="catalogo-pestana-profesionales" [hidden]="vistaActiva() !== 'profesionales'">
        <div class="seccion-cabecera"><div><p class="ceja">EQUIPO</p><h2 id="titulo-profesionales">Profesionales · {{ profesionales().length }}</h2></div></div>
        <div class="desplazable" tabindex="0" role="region" aria-labelledby="titulo-profesionales">
          <div class="rejilla">@for (p of profesionales(); track p.id) { <article class="tarjeta"><h3>{{ p.nombre }} {{ p.apellido }}</h3><p>Registro {{ p.numero_registro_profesional || 'no registrado' }}</p></article> }</div>
        </div>
      </section>
    </div>

    @if (ventanaFormulario() === 'consultorio') {
      <app-ventana-flotante ceja="Espacios de atención" [titulo]="editando() ? 'Editar consultorio' : 'Nuevo consultorio'" forma="centrada" [anchoMaximo]="560" [cierraAlPulsarFuera]="false" [ocupada]="guardando()" (cerrar)="cerrarVentana()">
        @if (error()) { <p class="aviso error" role="alert">{{ error() }}</p> }
        <form id="form-consultorio" class="formulario-modal" (ngSubmit)="guardar()">
          <label class="campo"><span>Nombre</span><input name="nombre" [(ngModel)]="form.nombre" required maxlength="100" placeholder="Ej. Consultorio 1" /></label>
          <label class="campo"><span>Tipo</span><select name="tipo" [(ngModel)]="form.tipo">@for (tipo of tipos; track tipo.valor) { <option [value]="tipo.valor">{{ tipo.etiqueta }}</option> }</select></label>
          <label class="campo"><span>Capacidad</span><input name="capacidad" type="number" [(ngModel)]="form.capacidad" min="1" max="100" required /></label>
        </form>
        <div pie class="acciones"><button class="boton" type="button" (click)="cerrarVentana()" [disabled]="guardando()">Cancelar</button><button class="boton boton--principal" type="submit" form="form-consultorio" [disabled]="guardando()">{{ guardando() ? 'Guardando…' : editando() ? 'Guardar cambios' : 'Crear consultorio' }}</button></div>
      </app-ventana-flotante>
    }
    @if (ventanaFormulario() === 'especialidad') {
      <app-ventana-flotante ceja="Organización clínica" [titulo]="editandoEspecialidad() ? 'Editar especialidad' : 'Nueva especialidad'" forma="centrada" [anchoMaximo]="560" [cierraAlPulsarFuera]="false" [ocupada]="guardando()" (cerrar)="cerrarVentana()">
        @if (error()) { <p class="aviso error" role="alert">{{ error() }}</p> }
        <form id="form-especialidad" class="formulario-modal" (ngSubmit)="guardarEspecialidad()">
          <label class="campo"><span>Nombre</span><input name="especialidad-nombre" [(ngModel)]="formEspecialidad.nombre" maxlength="150" required /></label>
          <label class="campo"><span>Código</span><input name="especialidad-codigo" [(ngModel)]="formEspecialidad.codigo" maxlength="32" /></label>
          <label class="campo"><span>Descripción</span><textarea name="especialidad-descripcion" [(ngModel)]="formEspecialidad.descripcion" rows="3"></textarea></label>
        </form>
        <div pie class="acciones"><button class="boton" type="button" (click)="cerrarVentana()" [disabled]="guardando()">Cancelar</button><button class="boton boton--principal" type="submit" form="form-especialidad" [disabled]="guardando()">{{ guardando() ? 'Guardando…' : editandoEspecialidad() ? 'Guardar cambios' : 'Crear especialidad' }}</button></div>
      </app-ventana-flotante>
    }
    @if (ventanaFormulario() === 'servicio') {
      <app-ventana-flotante ceja="Oferta clínica" [titulo]="editandoServicio() ? 'Editar servicio' : 'Nuevo servicio'" forma="centrada" [anchoMaximo]="680" [cierraAlPulsarFuera]="false" [ocupada]="guardando()" (cerrar)="cerrarVentana()">
        @if (error()) { <p class="aviso error" role="alert">{{ error() }}</p> }
        <form id="form-servicio" class="formulario-modal" (ngSubmit)="guardarServicio()">
          <label class="campo"><span>Especialidad</span><select name="servicio-especialidad" [(ngModel)]="formServicio.especialidad_id" [disabled]="!!editandoServicio()" required><option value="">Seleccione</option>@for (esp of especialidades(); track esp.id) { <option [value]="esp.id">{{ esp.nombre }}</option> }</select></label>
          <label class="campo"><span>Nombre</span><input name="servicio-nombre" [(ngModel)]="formServicio.nombre" maxlength="200" required /></label>
          <label class="campo campo--completo"><span>Descripción</span><textarea name="servicio-descripcion" [(ngModel)]="formServicio.descripcion" rows="2"></textarea></label>
          <div class="campos-dos"><label class="campo"><span>Duración (min)</span><input name="servicio-duracion" type="number" [(ngModel)]="formServicio.duracion_minutos" min="1" max="1440" required /></label><label class="campo"><span>Preparación (min)</span><input name="servicio-preparacion" type="number" [(ngModel)]="formServicio.minutos_preparacion" min="0" max="1440" /></label></div>
          <div class="campos-dos"><label class="campo"><span>Precio</span><input name="servicio-precio" type="number" [(ngModel)]="formServicio.precio" min="0" step="0.01" /></label><label class="campo"><span>Moneda</span><input name="servicio-moneda" [(ngModel)]="formServicio.moneda" maxlength="3" required /></label></div>
          <label class="campo"><span>Consultorio requerido</span><select name="servicio-consultorio" [(ngModel)]="formServicio.tipo_consultorio_requerido"><option [ngValue]="null">Sin requisito</option>@for (tipo of tipos; track tipo.valor) { <option [ngValue]="tipo.valor">{{ tipo.etiqueta }}</option> }</select></label>
          <label class="campo"><span class="opcion"><input name="servicio-pago-previo" type="checkbox" [(ngModel)]="formServicio.requiere_pago_previo" /> Requiere pago previo</span></label>
          <label class="campo campo--completo"><span>Indicaciones de preparación</span><textarea name="servicio-indicaciones" [(ngModel)]="formServicio.instrucciones_preparacion" rows="2"></textarea></label>
        </form>
        <div pie class="acciones"><button class="boton" type="button" (click)="cerrarVentana()" [disabled]="guardando()">Cancelar</button><button class="boton boton--principal" type="submit" form="form-servicio" [disabled]="guardando()">{{ guardando() ? 'Guardando…' : editandoServicio() ? 'Guardar cambios' : 'Crear servicio' }}</button></div>
      </app-ventana-flotante>
    }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    h2 { margin-top: 24px; } .gestion { padding: 22px; border: 1px solid var(--borde); border-radius: var(--radio); background: var(--superficie-elevada); } .catalogo-admin h2 { margin-top: 4px; }
    .seccion-cabecera { display:flex; align-items:end; justify-content:space-between; gap:20px; margin-bottom:18px; } .seccion-cabecera h2 { margin:4px 0; } .seccion-cabecera p { margin:4px 0; color:var(--texto-suave); }
    .acciones-sede { display:flex; align-items:end; gap:10px; } .ceja { font-size:.72rem; font-weight:700; letter-spacing:.09em; color:var(--acento); } .sede { min-width:230px; }
    .formulario-modal { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:var(--espacio-3); } .campo--completo { grid-column:1/-1; }
    .campo { display:grid; gap:6px; font-size:.9rem; font-weight:600; } .campo input,.campo select,.campo textarea { width:100%; min-height:42px; padding:8px 10px; border:1px solid var(--borde-fuerte); border-radius:var(--radio-pequeno); background:var(--superficie-elevada); color:var(--texto); font:inherit; } .campos-dos { display:grid; grid-template-columns:1fr 1fr; gap:10px; } .opcion { display:flex; align-items:center; gap:8px; } .opcion input { min-height:auto; width:auto; } .descripcion { display:block; margin-top:4px; color:var(--texto-suave); font-weight:400; }
    .acciones,.acciones-fila { display:flex; align-items:center; gap:8px; flex-wrap:wrap; } .compacto { padding:6px 9px; font-size:.82rem; }
    .estado,.etiqueta { display:inline-block; border-radius:999px; padding:4px 9px; color:#087443; background:#e8f7ef; font-size:.78rem; font-weight:650; } .estado.inactivo { color:var(--texto-tenue); background:#eef2f6; } .etiqueta { color:#176b76; background:#e8f5f6; }
    .aviso { padding:12px 14px; border-radius:9px; } .aviso.error { background:#fff0ef; color:#a12820; } .aviso.exito { background:#e8f7ef; color:#087443; } .ayuda { color:var(--texto-tenue); }
    /* Pantalla de trabajo: cada pestaña llena el alto y desplaza dentro. */
    .panel-catalogo[hidden] { display: none !important; }
    .gestion { display: flex; flex-direction: column; min-width: 0; min-height: 0; }
    .catalogo__sedes { --pantalla-columnas: minmax(0, 1fr) minmax(0, 1.6fr); }
    @media (min-width: 821px) and (min-height: 600px) {
      .panel-catalogo:not(.pantalla__columnas) { flex: 1 1 0; min-height: 0; }
      .gestion { padding: var(--espacio-4); }
      .seccion-cabecera { flex: none; margin-bottom: var(--espacio-3); }
      .seccion-cabecera h2 { font-size: 1.15rem; }
      .gestion .rejilla { grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: var(--espacio-3); align-content: start; }
    }
    @media (max-width:850px) { .formulario-modal,.campos-dos { grid-template-columns:1fr; } .formulario-modal > *, .campo { min-width:0; } .campo--completo { grid-column:auto; } .seccion-cabecera,.acciones-sede { align-items:stretch; flex-direction:column; } .sede { min-width:0; } .tabla-envoltorio { overflow-x:auto; } }
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
  protected readonly ventanaFormulario = signal<'consultorio' | 'especialidad' | 'servicio' | null>(null);
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

  /** Partes del catálogo que el rol alcanza, una por pestaña. */
  protected readonly vistas = computed<readonly OpcionPestana[]>(() => [
    { clave: 'sedes', etiqueta: 'Sedes y consultorios', cuenta: this.sedes().length },
    ...(this.puedeGestionarEspecialidades()
      ? [
          { clave: 'especialidades', etiqueta: 'Especialidades', cuenta: this.especialidadesGestion().length },
          { clave: 'modulos', etiqueta: 'Módulos de historia' },
        ]
      : []),
    { clave: 'servicios', etiqueta: 'Servicios', cuenta: (this.puedeGestionarServicios() ? this.serviciosGestion() : this.servicios()).length },
    { clave: 'profesionales', etiqueta: 'Profesionales', cuenta: this.profesionales().length },
  ]);
  protected readonly vista = signal('sedes');
  protected readonly vistaActiva = computed(() =>
    this.vistas().some((opcion) => opcion.clave === this.vista()) ? this.vista() : 'sedes',
  );

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

  protected abrirNuevoConsultorio(): void { this.nuevo(); this.error.set(''); this.mensaje.set(''); this.ventanaFormulario.set('consultorio'); }

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
    this.editando.set(sala.id); this.form = { nombre: sala.nombre, tipo: sala.tipo, capacidad: sala.capacidad }; this.mensaje.set(''); this.error.set(''); this.ventanaFormulario.set('consultorio');
  }

  /**
   * Cierra la ventana abierta y limpia su formulario. A mitad del guardado no
   * se cierra: el resultado se perdería o se informaría con la ventana cerrada.
   */
  protected cerrarVentana(): void {
    if (this.guardando()) return;
    const ventana = this.ventanaFormulario();
    if (ventana === 'consultorio') this.nuevo();
    else if (ventana === 'especialidad') this.nuevaEspecialidad();
    else if (ventana === 'servicio') this.nuevoServicio();
  }

  protected nuevo(): void { this.editando.set(''); this.form = { nombre: '', tipo: 'CONSULTA', capacidad: 1 }; this.ventanaFormulario.set(null); }

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

  protected abrirNuevaEspecialidad(): void { this.nuevaEspecialidad(); this.error.set(''); this.mensaje.set(''); this.ventanaFormulario.set('especialidad'); }

  protected editarEspecialidad(item: Especialidad): void {
    this.editandoEspecialidad.set(item.id);
    this.formEspecialidad = { nombre: item.nombre, codigo: item.codigo ?? '', descripcion: item.descripcion ?? '' };
    this.error.set(''); this.mensaje.set(''); this.ventanaFormulario.set('especialidad');
  }

  protected nuevaEspecialidad(): void {
    this.editandoEspecialidad.set(''); this.formEspecialidad = { nombre: '', codigo: '', descripcion: '' }; this.ventanaFormulario.set(null);
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
    this.error.set(''); this.mensaje.set(''); this.ventanaFormulario.set('servicio');
  }

  protected abrirNuevoServicio(): void { this.nuevoServicio(); this.error.set(''); this.mensaje.set(''); this.ventanaFormulario.set('servicio'); }

  protected nuevoServicio(): void {
    this.editandoServicio.set(''); this.formServicio = this.formularioServicioVacio(); this.ventanaFormulario.set(null);
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
