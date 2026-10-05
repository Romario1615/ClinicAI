import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { FalloApi } from '../../nucleo/servicios/api.service';
import { OperacionesService } from '../../nucleo/servicios/operaciones.service';
import { PERMISOS } from '../../nucleo/servicios/configuracion';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { MatrizAccesosComponent } from './matriz-accesos.component';

interface UsuarioClinica {
  readonly id: string;
  readonly correo: string;
  readonly nombre: string;
  readonly apellido: string;
  readonly activo: boolean;
  readonly roles: readonly string[];
  readonly profesional_id: string | null;
  readonly ultimo_acceso_en: string | null;
}

interface RolClinica {
  readonly id: string;
  readonly codigo: string;
  readonly nombre: string;
  readonly descripcion: string | null;
  readonly es_sistema: boolean;
  readonly permisos: readonly string[];
}

interface PermisoClinica {
  readonly codigo: string;
  readonly descripcion: string;
  readonly categoria: string;
}

interface ProfesionalClinica {
  readonly id: string;
  readonly nombre: string;
  readonly apellido: string;
}

@Component({
  selector: 'app-usuarios',
  standalone: true,
  imports: [FormsModule, MatrizAccesosComponent],
  template: `
    <header class="encabezado">
      <div><p class="sobretitulo">Administración de accesos</p><h1>Usuarios y roles</h1>
        <p>Asigna a cada persona los módulos y permisos que necesita dentro de esta clínica.</p></div>
      <img class="modulo-cabecera__imagen" src="/images/usuarios-roles.png" alt="" aria-hidden="true" loading="lazy" />
      <button class="boton" type="button" (click)="cargar()" [disabled]="cargando()">Actualizar</button>
    </header>

    @if (error()) { <p class="mensaje mensaje--error" role="alert">{{ error() }}</p> }
    @if (aviso()) { <p class="mensaje mensaje--bien" role="status">{{ aviso() }}</p> }

    <section class="tarjeta">
      <div class="seccion-titulo"><div><h2>Personal con acceso</h2><p>{{ usuarios().length }} cuentas de esta clínica</p></div></div>
      @if (cargando()) { <p role="status">Cargando cuentas…</p> }
      @if (!cargando() && usuarios().length === 0) { <p class="vacio">Aún no hay usuarios para mostrar.</p> }
      @for (usuario of usuarios(); track usuario.id) {
        <article class="fila">
          <div class="datos"><strong>{{ usuario.nombre }} {{ usuario.apellido }}</strong><span>{{ usuario.correo }}</span>
            <span class="etiquetas">@for (rol of usuario.roles; track rol) { <span class="etiqueta">{{ rol }}</span> }</span>
          </div>
          @if (sesion.tienePermiso(PERMISOS.rolAsignar)) {
            <button class="boton boton--pequeno" type="button" (click)="editar(usuario)">Cambiar roles</button>
          }
          @if (usuario.activo && sesion.tienePermiso('usuario.desactivar')) {
            <button class="boton boton--pequeno" type="button" (click)="cambiarEstado(usuario, false)">Quitar acceso</button>
          }
          @if (!usuario.activo && sesion.tienePermiso('usuario.editar')) {
            <button class="boton boton--pequeno" type="button" (click)="cambiarEstado(usuario, true)">Restaurar acceso</button>
          }
        </article>
      }
    </section>

    @if (usuarioEnEdicion(); as usuario) {
      <section class="tarjeta">
        <h2>Accesos de {{ usuario.nombre }} {{ usuario.apellido }}</h2>
        <p>Los cambios se aplican en el servidor y actualizan los permisos de la cuenta.</p>
        <div class="opciones">
          @for (rol of roles(); track rol.id) {
            <label class="opcion"><input type="checkbox" [checked]="rolesSeleccionados().has(rol.id)" (change)="alternarRol(rol.id, $any($event.target).checked)" />
              <span><strong>{{ rol.nombre }}</strong><small>{{ rol.descripcion || 'Rol disponible en esta clínica' }}</small></span></label>
          }
        </div>
        @if (requiereProfesional()) {
          <label>Perfil profesional<select [value]="profesionalId" (change)="profesionalId = $any($event.target).value" required>
            <option value="">Seleccione un profesional</option>@for (profesional of profesionales(); track profesional.id) { <option [value]="profesional.id">{{ profesional.nombre }} {{ profesional.apellido }}</option> }
          </select></label>
        }
        <div class="acciones"><button class="boton boton--principal" type="button" (click)="guardarRoles(usuario)" [disabled]="ocupado() || rolesSeleccionados().size === 0">Guardar accesos</button>
          <button class="boton" type="button" (click)="usuarioEnEdicion.set(null)">Cancelar</button></div>
      </section>
    }

    @if (sesion.tienePermiso(PERMISOS.rolAsignar)) {
      <section class="tarjeta">
        <h2>Crear un rol para la clínica</h2>
        <p>Selecciona los permisos que puede usar ese grupo. No puedes delegar permisos que tu cuenta no tiene.</p>
        <form (ngSubmit)="crearRol()">
          <div class="campos">
            <label>Nombre del rol<input name="nombreRol" [(ngModel)]="nombreRol" required minlength="2" maxlength="100" placeholder="Ej. Coordinación de agenda" /></label>
            <label>Código interno<input name="codigoRol" [(ngModel)]="codigoRol" required pattern="[a-z][a-z0-9_]+" maxlength="50" placeholder="coordinacion_agenda" /></label>
          </div>
          <div class="permisos">
            @for (permiso of permisos(); track permiso.codigo) {
              <label class="permiso"><input type="checkbox" [checked]="permisosSeleccionados().has(permiso.codigo)" (change)="alternarPermiso(permiso.codigo, $any($event.target).checked)" />
                <span>{{ permiso.descripcion }} <small>{{ permiso.categoria }}</small></span></label>
            }
          </div>
          <button class="boton boton--principal" [disabled]="ocupado() || permisosSeleccionados().size === 0">Crear rol</button>
        </form>
      </section>
    }

    @if (sesion.tienePermiso(PERMISOS.usuarioCrear) && sesion.tienePermiso(PERMISOS.rolAsignar)) {
      <section class="tarjeta">
        <h2>Dar acceso a una persona</h2>
        <p>La cuenta quedará vinculada a tu clínica. Comparte la contraseña inicial de forma segura; se solicitará cambiarla al iniciar sesión.</p>
        <form (ngSubmit)="crearUsuario()">
          <div class="campos">
            <label>Nombre<input name="nombre" [(ngModel)]="nombre" required maxlength="100" /></label>
            <label>Apellido<input name="apellido" [(ngModel)]="apellido" required maxlength="100" /></label>
            <label>Correo<input name="correo" [(ngModel)]="correo" type="email" required maxlength="200" /></label>
            <label>Contraseña inicial<input name="contrasena" [(ngModel)]="contrasenaInicial" type="password" required minlength="12" maxlength="128" autocomplete="new-password" /></label>
          </div>
          <h3>Roles y módulos</h3>
          <div class="opciones">
          @for (rol of roles(); track rol.id) {
            <label class="opcion"><input type="checkbox" [checked]="rolesSeleccionados().has(rol.id)" (change)="alternarRol(rol.id, $any($event.target).checked)" />
              <span><strong>{{ rol.nombre }}</strong><small>{{ rol.permisos.length }} permisos</small></span></label>
          }
        </div>
          @if (requiereProfesional()) {
            <label>Perfil profesional<select name="perfilProfesional" [(ngModel)]="profesionalId" required>
              <option value="">Seleccione un profesional</option>@for (profesional of profesionales(); track profesional.id) { <option [value]="profesional.id">{{ profesional.nombre }} {{ profesional.apellido }}</option> }
            </select></label>
          }
          <button class="boton boton--principal" [disabled]="ocupado() || rolesSeleccionados().size === 0">Crear cuenta y conceder acceso</button>
        </form>
      </section>
    }

    @if (roles().length) {
      <app-matriz-accesos [roles]="roles()" />
    }
  `,
  styles: `
    :host { display: grid; gap: 1rem; max-width: 1100px; margin: 0 auto; }
    .encabezado,.seccion-titulo,.fila,.acciones { display:flex; align-items:center; justify-content:space-between; gap:1rem; }
    .encabezado h1 { margin:.15rem 0 .4rem; } .encabezado p { margin:.25rem 0; color:var(--texto-secundario,#667085); }
    .sobretitulo { color:var(--primario,#2c6e68)!important; font-size:.8rem; font-weight:700; text-transform:uppercase; letter-spacing:.06em; }
    .tarjeta { padding:1.25rem; border:1px solid var(--borde,#e4e7ec); border-radius:14px; background:var(--superficie,#fff); }
    h2 { margin:.1rem 0 .4rem; font-size:1.15rem; } h3 { margin:1rem 0 .5rem; }
    .tarjeta p,.datos span { color:var(--texto-secundario,#667085); }
    .fila { padding:.85rem 0; border-top:1px solid var(--borde,#eaecf0); }
    .datos { display:grid; gap:.25rem; } .etiquetas { display:flex; gap:.35rem; flex-wrap:wrap; }
    .etiqueta { padding:.15rem .5rem; border-radius:999px; background:#edf5f3; color:#245b55!important; font-size:.8rem; }
    .campos { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:.8rem; }
    label { display:grid; gap:.35rem; font-weight:600; font-size:.9rem; }
    input:not([type=checkbox]) { width:100%; padding:.65rem .75rem; border:1px solid var(--borde,#d0d5dd); border-radius:8px; font:inherit; }
    .opciones,.permisos { display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:.5rem; margin:1rem 0; }
    .opcion,.permiso { display:flex; align-items:flex-start; gap:.6rem; padding:.7rem; border:1px solid var(--borde,#eaecf0); border-radius:9px; cursor:pointer; }
    .opcion input,.permiso input { margin-top:.2rem; accent-color:var(--primario,#2c6e68); }
    .opcion span,.permiso span { display:grid; gap:.2rem; } small { color:var(--texto-secundario,#667085); font-weight:400; }
    .acciones { justify-content:flex-start; margin-top:1rem; }
    .mensaje { padding:.8rem 1rem; border-radius:8px; } .mensaje--error { background:#fef3f2; color:#b42318; } .mensaje--bien { background:#ecfdf3; color:#027a48; }
    .vacio { padding:1rem 0; } .boton { cursor:pointer; } .boton:disabled { cursor:wait; opacity:.6; }
    @media (max-width:600px) { .encabezado,.fila { align-items:flex-start; flex-direction:column; } }
  `,
})
export class UsuariosComponent {
  private readonly api = inject(OperacionesService);
  protected readonly sesion = inject(SesionService);
  protected readonly PERMISOS = PERMISOS;
  protected readonly usuarios = signal<UsuarioClinica[]>([]);
  protected readonly roles = signal<RolClinica[]>([]);
  protected readonly permisos = signal<PermisoClinica[]>([]);
  protected readonly profesionales = signal<ProfesionalClinica[]>([]);
  protected readonly rolesSeleccionados = signal<Set<string>>(new Set());
  protected readonly permisosSeleccionados = signal<Set<string>>(new Set());
  protected readonly usuarioEnEdicion = signal<UsuarioClinica | null>(null);
  protected readonly cargando = signal(false);
  protected readonly ocupado = signal(false);
  protected readonly error = signal('');
  protected readonly aviso = signal('');
  protected nombre = '';
  protected apellido = '';
  protected correo = '';
  protected contrasenaInicial = '';
  protected nombreRol = '';
  protected codigoRol = '';
  protected profesionalId = '';

  constructor() { this.cargar(); }

  protected cargar(): void {
    this.cargando.set(true);
    this.error.set('');
    this.api.leer<UsuarioClinica[]>('/usuarios').subscribe({
      next: (datos) => { this.usuarios.set(datos); this.cargando.set(false); },
      error: (error: FalloApi) => { this.mostrarError(error); this.cargando.set(false); },
    });
    this.api.leer<RolClinica[]>('/usuarios/roles').subscribe({
      next: (datos) => this.roles.set(datos), error: (error: FalloApi) => this.mostrarError(error),
    });
    if (this.sesion.tienePermiso(PERMISOS.rolAsignar)) {
      this.api.leer<PermisoClinica[]>('/usuarios/permisos').subscribe({
        next: (datos) => this.permisos.set(datos), error: (error: FalloApi) => this.mostrarError(error),
      });
      this.api.leer<ProfesionalClinica[]>('/usuarios/profesionales').subscribe({
        next: (datos) => this.profesionales.set(datos), error: (error: FalloApi) => this.mostrarError(error),
      });
    }
  }

  protected editar(usuario: UsuarioClinica): void {
    this.usuarioEnEdicion.set(usuario);
    this.profesionalId = usuario.profesional_id ?? '';
    this.rolesSeleccionados.set(new Set(this.roles().filter((rol) => usuario.roles.includes(rol.nombre)).map((rol) => rol.id)));
    this.api.leer<ProfesionalClinica[]>('/usuarios/profesionales', { usuario_id: usuario.id }).subscribe({
      next: (datos) => this.profesionales.set(datos), error: (error: FalloApi) => this.mostrarError(error),
    });
  }

  protected requiereProfesional(): boolean {
    return this.roles().some((rol) => rol.codigo === 'profesional' && this.rolesSeleccionados().has(rol.id));
  }

  protected alternarRol(id: string, marcado: boolean): void {
    this.rolesSeleccionados.update((actuales) => {
      const nuevos = new Set(actuales);
      if (marcado) nuevos.add(id);
      else nuevos.delete(id);
      return nuevos;
    });
  }

  protected alternarPermiso(codigo: string, marcado: boolean): void {
    this.permisosSeleccionados.update((actuales) => {
      const nuevos = new Set(actuales);
      if (marcado) nuevos.add(codigo);
      else nuevos.delete(codigo);
      return nuevos;
    });
  }

  protected crearRol(): void {
    this.enviar('/usuarios/roles', {
      codigo: this.codigoRol.trim().toLowerCase(), nombre: this.nombreRol.trim(), descripcion: null,
      permisos: [...this.permisosSeleccionados()],
    }, false, 'Rol creado.', () => { this.nombreRol = ''; this.codigoRol = ''; this.permisosSeleccionados.set(new Set()); this.cargar(); });
  }

  protected crearUsuario(): void {
    this.enviar('/usuarios', {
      nombre: this.nombre.trim(), apellido: this.apellido.trim(), correo: this.correo.trim().toLowerCase(),
      contrasena_inicial: this.contrasenaInicial, roles: [...this.rolesSeleccionados()],
      profesional_id: this.requiereProfesional() ? this.profesionalId || null : null,
    }, false, 'Cuenta creada y acceso concedido.', () => {
      this.nombre = ''; this.apellido = ''; this.correo = ''; this.contrasenaInicial = '';
      this.rolesSeleccionados.set(new Set()); this.cargar();
    });
  }

  protected guardarRoles(usuario: UsuarioClinica): void {
    this.enviar(`/usuarios/${usuario.id}/roles`, {
      roles: [...this.rolesSeleccionados()],
      profesional_id: this.requiereProfesional() ? this.profesionalId || null : null,
    }, true,
      'Accesos actualizados.', () => { this.usuarioEnEdicion.set(null); this.rolesSeleccionados.set(new Set()); this.cargar(); });
  }

  protected cambiarEstado(usuario: UsuarioClinica, activo: boolean): void {
    this.enviar(`/usuarios/${usuario.id}/estado`, { activo }, true,
      activo ? 'Acceso restaurado.' : 'Acceso quitado y sesiones cerradas.', () => this.cargar());
  }

  private enviar(ruta: string, datos: unknown, editar: boolean, mensaje: string, alGuardar: () => void): void {
    this.ocupado.set(true); this.error.set(''); this.aviso.set('');
    this.api.guardar(ruta, datos, crypto.randomUUID(), editar).subscribe({
      next: () => { this.ocupado.set(false); this.aviso.set(mensaje); alGuardar(); },
      error: (error: FalloApi) => { this.ocupado.set(false); this.mostrarError(error); },
    });
  }

  private mostrarError(error: FalloApi): void { this.error.set(error.message); }
}
