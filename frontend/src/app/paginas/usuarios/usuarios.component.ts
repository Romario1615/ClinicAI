/**
 * Usuarios y roles.
 *
 * Organización
 * ------------
 * Tres pestañas con una pregunta cada una:
 *
 * * **Personal**: ¿quién tiene acceso y con qué rol? Lista con búsqueda y
 *   filtro por rol; cada persona se gestiona en una ventana flotante.
 * * **Roles**: ¿qué roles hay y a cuántas personas se aplican? Cada rol abre
 *   sus permisos agrupados por módulo.
 * * **Qué puede hacer cada rol**: la matriz por módulo.
 *
 * Dar acceso, cambiar roles, crear un rol y quitar acceso se hacen en
 * ventanas flotantes: la lista no se mueve y al cerrar se vuelve al mismo
 * punto. Quitar acceso pide confirmación porque cierra las sesiones abiertas.
 *
 * Autorización: cada botón aparece solo con su permiso (`usuario.crear`,
 * `rol.asignar`, `usuario.desactivar`, `usuario.editar`); el backend vuelve a
 * comprobarlo en cada petición.
 */
import { Component, computed, inject, signal } from '@angular/core';
import { DatePipe, NgTemplateOutlet } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { FalloApi } from '../../nucleo/servicios/api.service';
import { OperacionesService } from '../../nucleo/servicios/operaciones.service';
import { PERMISOS } from '../../nucleo/servicios/configuracion';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { IndicadoresService } from '../../nucleo/servicios/indicadores.service';
import { ResumenModuloComponent } from '../../compartido/resumen-modulo.component';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
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

type Pestana = 'personal' | 'roles' | 'matriz';
type Ventana =
  | { tipo: 'alta' }
  | { tipo: 'accesos'; usuario: UsuarioClinica }
  | { tipo: 'rol-nuevo' }
  | { tipo: 'rol-ver'; rol: RolClinica }
  | { tipo: 'quitar'; usuario: UsuarioClinica };

const CATEGORIAS: Record<string, string> = {
  agenda: 'Agenda y citas',
  analitica: 'Panel y reportes',
  auditoria: 'Auditoría',
  clinico: 'Historia clínica',
  comunicacion: 'Mensajes y promociones',
  conocimiento: 'Base de conocimiento',
  organizacion: 'Clínica y catálogo',
  pacientes: 'Pacientes',
  pagos: 'Pagos',
  profesionales: 'Profesionales',
  recetas: 'Recetas y adherencia',
  usuarios: 'Usuarios y roles',
};

@Component({
  selector: 'app-usuarios',
  standalone: true,
  imports: [FormsModule, DatePipe, NgTemplateOutlet, MatrizAccesosComponent, ResumenModuloComponent, VentanaFlotanteComponent],
  template: `
    <header class="encabezado">
      <div>
        <p class="ceja">ADMINISTRACIÓN DE ACCESOS</p>
        <h1>Usuarios y roles</h1>
        <p class="encabezado__sub">Quién entra a la clínica, con qué rol y qué puede hacer cada rol.</p>
      </div>
      <div class="acciones">
        @if (puedeCrearRol()) {
          <button class="boton" type="button" (click)="abrir({ tipo: 'rol-nuevo' })">Crear rol</button>
        }
        @if (puedeDarAcceso()) {
          <button class="boton boton--principal" type="button" (click)="abrir({ tipo: 'alta' })">
            Dar acceso a una persona
          </button>
        }
      </div>
    </header>

    <app-resumen-modulo modulo="usuarios" />

    @if (aviso()) {
      <p class="exito" role="status">{{ aviso() }}</p>
    }
    @if (error() && !ventana()) {
      <p class="aviso-error" role="alert">{{ error() }}</p>
    }

    <div class="pestanas" role="tablist" aria-label="Secciones de usuarios y roles">
      @for (tab of pestanas; track tab.clave) {
        <button
          type="button"
          role="tab"
          class="pestanas__boton"
          [class.pestanas__boton--activa]="pestana() === tab.clave"
          [attr.aria-selected]="pestana() === tab.clave"
          (click)="pestana.set(tab.clave)"
        >
          {{ tab.etiqueta }}
          @if (tab.clave === 'personal') { <span class="cuenta">{{ usuarios().length }}</span> }
          @if (tab.clave === 'roles') { <span class="cuenta">{{ roles().length }}</span> }
        </button>
      }
    </div>

    @switch (pestana()) {
      @case ('personal') {
        <section class="tarjeta seccion" aria-label="Personal con acceso">
          <div class="filtros">
            <label class="campo filtros__buscar">
              <span class="solo-lectores">Buscar persona</span>
              <input class="campo__control" type="search" placeholder="Buscar por nombre o correo" [(ngModel)]="busqueda" />
            </label>
            <label class="campo">
              <span class="solo-lectores">Filtrar por rol</span>
              <select class="campo__control" [(ngModel)]="filtroRol">
                <option value="">Todos los roles</option>
                @for (rol of roles(); track rol.id) { <option [value]="rol.nombre">{{ rol.nombre }}</option> }
              </select>
            </label>
            <label class="filtros__check">
              <input type="checkbox" [(ngModel)]="verInactivos" /> Mostrar cuentas sin acceso
            </label>
          </div>

          @if (cargando()) {
            <p role="status" class="vacio">Cargando cuentas…</p>
          } @else if (personal().length === 0) {
            <p class="vacio">Ninguna persona coincide con la búsqueda.</p>
          } @else {
            <div class="tabla-envoltorio">
              <table class="tabla">
                <thead>
                  <tr>
                    <th scope="col">Persona</th>
                    <th scope="col">Roles</th>
                    <th scope="col">Estado</th>
                    <th scope="col">Último acceso</th>
                    <th scope="col"><span class="solo-lectores">Acciones</span></th>
                  </tr>
                </thead>
                <tbody>
                  @for (usuario of personal(); track usuario.id) {
                    <tr [class.fila--inactiva]="!usuario.activo">
                      <td>
                        <div class="persona">
                          <span class="persona__inicial" aria-hidden="true">{{ usuario.nombre.charAt(0) }}{{ usuario.apellido.charAt(0) }}</span>
                          <span>
                            <strong>{{ usuario.nombre }} {{ usuario.apellido }}</strong>
                            <small>{{ usuario.correo }}</small>
                          </span>
                        </div>
                      </td>
                      <td>
                        <span class="etiquetas">
                          @for (rol of usuario.roles; track rol) { <span class="etiqueta">{{ rol }}</span> }
                        </span>
                      </td>
                      <td>
                        <span class="estado" [class.estado--activo]="usuario.activo">
                          {{ usuario.activo ? 'Con acceso' : 'Sin acceso' }}
                        </span>
                      </td>
                      <td class="numerico">
                        {{ usuario.ultimo_acceso_en ? (usuario.ultimo_acceso_en | date: 'dd/MM/yy HH:mm') : 'Nunca' }}
                      </td>
                      <td class="acciones">
                        @if (puedeAsignar()) {
                          <button class="boton boton--pequeno" type="button" (click)="abrir({ tipo: 'accesos', usuario })">
                            Gestionar accesos
                          </button>
                        }
                        @if (usuario.activo && sesion.tienePermiso('usuario.desactivar')) {
                          <button class="boton boton--pequeno boton--plano" type="button" (click)="abrir({ tipo: 'quitar', usuario })">
                            Quitar acceso
                          </button>
                        }
                        @if (!usuario.activo && sesion.tienePermiso('usuario.editar')) {
                          <button class="boton boton--pequeno" type="button" [disabled]="ocupado()" (click)="cambiarEstado(usuario, true)">
                            Restaurar acceso
                          </button>
                        }
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          }
        </section>
      }

      @case ('roles') {
        <section class="roles" aria-label="Roles de la clínica">
          @for (rol of roles(); track rol.id) {
            <article class="tarjeta rol">
              <div class="rol__cabecera">
                <h2>{{ rol.nombre }}</h2>
                <span class="insignia" [class.insignia--clinica]="!rol.es_sistema">
                  {{ rol.es_sistema ? 'Del sistema' : 'De la clínica' }}
                </span>
              </div>
              <p class="rol__descripcion">{{ rol.descripcion || 'Sin descripción.' }}</p>
              <p class="rol__cifras">
                <strong class="numerico">{{ personasCon(rol) }}</strong> persona(s) ·
                <strong class="numerico">{{ rol.permisos.length }}</strong> permisos
              </p>
              <button class="boton boton--pequeno" type="button" (click)="abrir({ tipo: 'rol-ver', rol })">
                Ver qué puede hacer
              </button>
            </article>
          }
        </section>
      }

      @case ('matriz') {
        <app-matriz-accesos [roles]="roles()" />
      }
    }

    <!-- ======================== Ventanas ======================== -->
    @if (ventana(); as v) {
      @switch (v.tipo) {
        @case ('alta') {
          <app-ventana-flotante ceja="Usuarios" titulo="Dar acceso a una persona" forma="centrada" [anchoMaximo]="720"
                                [cierraAlPulsarFuera]="false" (cerrar)="cerrarVentana()">
            <form id="form-alta" #formAlta="ngForm" (ngSubmit)="crearUsuario(formAlta.invalid ?? true)" novalidate>
              <p class="campo__ayuda">La cuenta queda vinculada a esta clínica. Comparta la contraseña inicial por un canal seguro: se pedirá cambiarla al entrar.</p>
              <h3 class="paso">1. Datos de la persona</h3>
              <div class="rejilla">
                <label class="campo"><span class="campo__etiqueta">Nombre</span>
                  <input class="campo__control" name="nombre" [(ngModel)]="nombre" required maxlength="100" /></label>
                <label class="campo"><span class="campo__etiqueta">Apellido</span>
                  <input class="campo__control" name="apellido" [(ngModel)]="apellido" required maxlength="100" /></label>
                <label class="campo"><span class="campo__etiqueta">Correo</span>
                  <input class="campo__control" name="correo" type="email" email [(ngModel)]="correo" required maxlength="200" /></label>
                <label class="campo"><span class="campo__etiqueta">Contraseña inicial</span>
                  <input class="campo__control" name="contrasena" type="password" [(ngModel)]="contrasenaInicial" required minlength="12" maxlength="128" autocomplete="new-password" />
                  <span class="campo__ayuda">Mínimo 12 caracteres.</span></label>
              </div>
              <h3 class="paso">2. Rol</h3>
              <ng-container *ngTemplateOutlet="eleccionRoles" />
              @if (error()) { <p class="aviso-error" role="alert">{{ error() }}</p> }
            </form>
            <div class="acciones acciones--final" pie>
              <button class="boton" type="button" (click)="cerrarVentana()">Cancelar</button>
              <button class="boton boton--principal" type="submit" form="form-alta" [disabled]="ocupado()">
                {{ ocupado() ? 'Creando…' : 'Crear cuenta y dar acceso' }}
              </button>
            </div>
          </app-ventana-flotante>
        }

        @case ('accesos') {
          <app-ventana-flotante ceja="Gestionar accesos" [titulo]="v.usuario.nombre + ' ' + v.usuario.apellido" forma="centrada"
                                [anchoMaximo]="640" (cerrar)="cerrarVentana()">
            <p class="campo__ayuda">{{ v.usuario.correo }}. Los cambios se aplican en el servidor y actualizan sus permisos en la próxima petición.</p>
            <ng-container *ngTemplateOutlet="eleccionRoles" />
            @if (error()) { <p class="aviso-error" role="alert">{{ error() }}</p> }
            <div class="acciones acciones--final" pie>
              <button class="boton" type="button" (click)="cerrarVentana()">Cancelar</button>
              <button class="boton boton--principal" type="button" [disabled]="ocupado() || rolesSeleccionados().size === 0" (click)="guardarRoles(v.usuario)">
                {{ ocupado() ? 'Guardando…' : 'Guardar accesos' }}
              </button>
            </div>
          </app-ventana-flotante>
        }

        @case ('rol-nuevo') {
          <app-ventana-flotante ceja="Roles" titulo="Crear un rol para la clínica" forma="centrada" [anchoMaximo]="900"
                                [altoCompleto]="true" [cierraAlPulsarFuera]="false" (cerrar)="cerrarVentana()">
            <form id="form-rol" #formRol="ngForm" (ngSubmit)="crearRol(formRol.invalid ?? true)" novalidate>
              <div class="rejilla">
                <label class="campo"><span class="campo__etiqueta">Nombre del rol</span>
                  <input class="campo__control" name="nombreRol" [ngModel]="nombreRol" (ngModelChange)="cambiarNombreRol($event)" required minlength="2" maxlength="100" placeholder="Ej. Coordinación de agenda" /></label>
                <label class="campo"><span class="campo__etiqueta">Código interno</span>
                  <input class="campo__control" name="codigoRol" [(ngModel)]="codigoRol" required pattern="[a-z][a-z0-9_]+" maxlength="50" />
                  <span class="campo__ayuda">Se genera del nombre; solo minúsculas, números y guion bajo.</span></label>
              </div>
              <label class="campo"><span class="campo__etiqueta">Descripción (opcional)</span>
                <input class="campo__control" name="descripcionRol" [(ngModel)]="descripcionRol" maxlength="300" placeholder="Para qué sirve este rol" /></label>

              <div class="permisos__cabecera">
                <h3 class="paso">Permisos</h3>
                <span class="campo__ayuda"><strong class="numerico">{{ permisosSeleccionados().size }}</strong> seleccionados. Solo puede delegar permisos que su cuenta tiene.</span>
              </div>
              @for (grupo of permisosPorCategoria(); track grupo.categoria) {
                <fieldset class="grupo">
                  <legend>
                    <label class="grupo__todos">
                      <input type="checkbox" [checked]="grupoCompleto(grupo.permisos)" (change)="alternarGrupo(grupo.permisos, $any($event.target).checked)" />
                      {{ grupo.nombre }}
                    </label>
                  </legend>
                  <div class="permisos">
                    @for (permiso of grupo.permisos; track permiso.codigo) {
                      <label class="permiso">
                        <input type="checkbox" [checked]="permisosSeleccionados().has(permiso.codigo)" (change)="alternarPermiso(permiso.codigo, $any($event.target).checked)" />
                        <span>{{ permiso.descripcion }}</span>
                      </label>
                    }
                  </div>
                </fieldset>
              }
              @if (error()) { <p class="aviso-error" role="alert">{{ error() }}</p> }
            </form>
            <div class="acciones acciones--final" pie>
              <button class="boton" type="button" (click)="cerrarVentana()">Cancelar</button>
              <button class="boton boton--principal" type="submit" form="form-rol" [disabled]="ocupado()">
                {{ ocupado() ? 'Creando…' : 'Crear rol' }}
              </button>
            </div>
          </app-ventana-flotante>
        }

        @case ('rol-ver') {
          <app-ventana-flotante ceja="Rol" [titulo]="v.rol.nombre" forma="centrada" [anchoMaximo]="720" (cerrar)="cerrarVentana()">
            <p class="campo__ayuda">{{ v.rol.descripcion || 'Sin descripción.' }} · {{ personasCon(v.rol) }} persona(s) con este rol.</p>
            @for (grupo of permisosDeRol(v.rol); track grupo.nombre) {
              <section class="ver-grupo">
                <h3>{{ grupo.nombre }}</h3>
                <ul>
                  @for (permiso of grupo.permisos; track permiso) { <li>{{ permiso }}</li> }
                </ul>
              </section>
            } @empty {
              <p class="vacio">Este rol no tiene permisos.</p>
            }
          </app-ventana-flotante>
        }

        @case ('quitar') {
          <app-ventana-flotante ceja="Confirmar" titulo="Quitar el acceso" forma="centrada" [anchoMaximo]="480" (cerrar)="cerrarVentana()">
            <p><strong>{{ v.usuario.nombre }} {{ v.usuario.apellido }}</strong> dejará de poder entrar y se cerrarán sus sesiones abiertas.</p>
            <p class="campo__ayuda">No se borra nada: su historial y lo que registró se conservan, y el acceso se puede restaurar.</p>
            @if (error()) { <p class="aviso-error" role="alert">{{ error() }}</p> }
            <div class="acciones acciones--final" pie>
              <button class="boton" type="button" (click)="cerrarVentana()">Cancelar</button>
              <button class="boton boton--peligro" type="button" [disabled]="ocupado()" (click)="cambiarEstado(v.usuario, false)">
                Quitar acceso
              </button>
            </div>
          </app-ventana-flotante>
        }
      }
    }

    <ng-template #eleccionRoles>
      <div class="opciones">
        @for (rol of roles(); track rol.id) {
          <label class="opcion" [class.opcion--marcada]="rolesSeleccionados().has(rol.id)">
            <input type="checkbox" [checked]="rolesSeleccionados().has(rol.id)" (change)="alternarRol(rol.id, $any($event.target).checked)" />
            <span><strong>{{ rol.nombre }}</strong><small>{{ rol.descripcion || rol.permisos.length + ' permisos' }}</small></span>
          </label>
        }
      </div>
      @if (requiereProfesional()) {
        <label class="campo"><span class="campo__etiqueta">Perfil profesional</span>
          <select class="campo__control" name="perfilProfesional" [(ngModel)]="profesionalId" required>
            <option value="">Seleccione un profesional</option>
            @for (profesional of profesionales(); track profesional.id) {
              <option [value]="profesional.id">{{ profesional.nombre }} {{ profesional.apellido }}</option>
            }
          </select>
          <span class="campo__ayuda">El rol Profesional se vincula a su ficha de profesional (agenda, firma y relación con pacientes).</span>
        </label>
      }
    </ng-template>
  `,
  styles: `
    :host { display: grid; gap: var(--espacio-4); }
    :host > * { min-width: 0; }
    .encabezado { display: flex; align-items: flex-end; justify-content: space-between; gap: var(--espacio-4); flex-wrap: wrap; }
    .encabezado h1 { margin: 2px 0 4px; }
    .encabezado__sub { margin: 0; color: var(--texto-suave); }
    .ceja { margin: 0; color: var(--acento); font-size: 0.75rem; font-weight: 700; letter-spacing: 0.1em; }

    .pestanas { display: flex; gap: 2px; border-bottom: 1px solid var(--borde); overflow-x: auto; }
    .pestanas__boton { display: inline-flex; align-items: center; gap: 6px; min-height: var(--toque-minimo); padding: 0 var(--espacio-4);
      border: 0; background: transparent; color: var(--texto-suave); font-weight: 650; cursor: pointer; white-space: nowrap; }
    .pestanas__boton:hover { color: var(--texto); }
    .pestanas__boton:focus-visible { outline: 3px solid var(--acento); outline-offset: -3px; }
    .pestanas__boton--activa { color: var(--acento-fuerte); box-shadow: inset 0 -3px 0 var(--acento); }
    .cuenta { padding: 0 7px; border-radius: 999px; background: var(--superficie-hundida); font-size: 0.75rem; }

    .seccion { padding: var(--espacio-4); }
    .filtros { display: flex; flex-wrap: wrap; gap: var(--espacio-3); align-items: center; margin-bottom: var(--espacio-3); }
    .filtros .campo { margin: 0; }
    .filtros__buscar { flex: 1 1 260px; }
    .filtros__check { display: inline-flex; gap: 6px; align-items: center; font-size: 0.88rem; color: var(--texto-suave); }

    .tabla-envoltorio { overflow-x: auto; }
    .tabla { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
    .tabla th { text-align: left; padding: var(--espacio-2) var(--espacio-3); color: var(--texto-suave); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid var(--borde); }
    .tabla td { padding: var(--espacio-3); border-bottom: 1px solid var(--superficie-hundida); vertical-align: middle; }
    .tabla td.acciones { display: table-cell; text-align: right; white-space: nowrap; }
    .tabla td.acciones .boton + .boton { margin-left: var(--espacio-2); }
    .fila--inactiva { opacity: 0.65; }
    .persona { display: flex; align-items: center; gap: var(--espacio-3); }
    .persona span:last-child { display: grid; }
    .persona small { color: var(--texto-suave); overflow-wrap: anywhere; }
    .persona__inicial { display: inline-grid; place-items: center; width: 36px; height: 36px; flex: 0 0 36px; border-radius: 50%;
      background: var(--acento-suave); color: var(--acento-fuerte); font-weight: 700; font-size: 0.8rem; text-transform: uppercase; }
    .etiquetas { display: flex; gap: 4px; flex-wrap: wrap; }
    .etiqueta { padding: 2px 8px; border-radius: 999px; background: var(--acento-suave); color: var(--acento-fuerte); font-size: 0.75rem; font-weight: 600; }
    .estado { font-size: 0.8rem; font-weight: 700; color: var(--texto-tenue); }
    .estado--activo { color: var(--exito); }
    .vacio { color: var(--texto-suave); padding: var(--espacio-3) 0; margin: 0; }

    .roles { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: var(--espacio-3); }
    .rol { display: grid; gap: var(--espacio-2); align-content: start; padding: var(--espacio-4); }
    .rol__cabecera { display: flex; justify-content: space-between; gap: var(--espacio-2); align-items: start; }
    .rol h2 { margin: 0; font-size: 1.05rem; }
    .rol__descripcion { margin: 0; color: var(--texto-suave); font-size: 0.88rem; }
    .rol__cifras { margin: 0; font-size: 0.88rem; }
    .rol .boton { justify-self: start; }
    .insignia { padding: 2px 8px; border-radius: 999px; background: var(--superficie-hundida); color: var(--texto-suave); font-size: 0.72rem; font-weight: 700; white-space: nowrap; }
    .insignia--clinica { background: var(--acento-suave); color: var(--acento-fuerte); }

    .rejilla { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0 var(--espacio-4); }
    .paso { margin: var(--espacio-4) 0 var(--espacio-2); font-size: 0.95rem; }
    .opciones { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--espacio-2); margin-bottom: var(--espacio-3); }
    .opcion { display: flex; align-items: flex-start; gap: var(--espacio-2); padding: var(--espacio-3); border: 1px solid var(--borde); border-radius: var(--radio); cursor: pointer; }
    .opcion--marcada { border-color: var(--acento); background: var(--acento-suave); }
    .opcion span { display: grid; gap: 2px; }
    .opcion small { color: var(--texto-suave); }
    .opcion input, .permiso input, .grupo__todos input { margin-top: 3px; accent-color: var(--acento); }

    .permisos__cabecera { display: flex; align-items: baseline; justify-content: space-between; gap: var(--espacio-3); flex-wrap: wrap; }
    .grupo { margin: 0 0 var(--espacio-3); padding: var(--espacio-2) var(--espacio-3) var(--espacio-3); border: 1px solid var(--borde); border-radius: var(--radio); }
    .grupo legend { padding: 0 6px; }
    .grupo__todos { display: inline-flex; gap: 6px; align-items: center; font-weight: 700; cursor: pointer; }
    .permisos { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 4px var(--espacio-3); }
    .permiso { display: flex; gap: var(--espacio-2); align-items: flex-start; padding: 4px 0; font-size: 0.88rem; cursor: pointer; }

    .ver-grupo h3 { margin: var(--espacio-3) 0 var(--espacio-1); font-size: 0.85rem; color: var(--texto-suave); text-transform: uppercase; letter-spacing: 0.04em; }
    .ver-grupo ul { margin: 0; padding-left: 1.2rem; display: grid; gap: 2px; font-size: 0.9rem; }

    @media (max-width: 700px) {
      .tabla thead { display: none; }
      .tabla tr { display: grid; gap: 6px; padding: var(--espacio-3) 0; border-bottom: 1px solid var(--borde); }
      .tabla td { padding: 0; border: 0; }
      .tabla td.acciones { display: flex; gap: var(--espacio-2); text-align: left; flex-wrap: wrap; }
      .tabla td.acciones .boton + .boton { margin-left: 0; }
    }
  `,
})
export class UsuariosComponent {
  private readonly api = inject(OperacionesService);
  private readonly indicadores = inject(IndicadoresService);
  protected readonly sesion = inject(SesionService);
  protected readonly PERMISOS = PERMISOS;

  protected readonly pestanas: readonly { clave: Pestana; etiqueta: string }[] = [
    { clave: 'personal', etiqueta: 'Personal' },
    { clave: 'roles', etiqueta: 'Roles' },
    { clave: 'matriz', etiqueta: 'Qué puede hacer cada rol' },
  ];
  protected readonly pestana = signal<Pestana>('personal');
  protected readonly ventana = signal<Ventana | null>(null);

  protected readonly usuarios = signal<UsuarioClinica[]>([]);
  protected readonly roles = signal<RolClinica[]>([]);
  protected readonly permisos = signal<PermisoClinica[]>([]);
  protected readonly profesionales = signal<ProfesionalClinica[]>([]);
  protected readonly rolesSeleccionados = signal<Set<string>>(new Set());
  protected readonly permisosSeleccionados = signal<Set<string>>(new Set());
  protected readonly cargando = signal(false);
  protected readonly ocupado = signal(false);
  protected readonly error = signal('');
  protected readonly aviso = signal('');

  protected readonly busquedaTexto = signal('');
  protected readonly filtroRolTexto = signal('');
  protected readonly verInactivosMarcado = signal(false);
  protected get busqueda(): string { return this.busquedaTexto(); }
  protected set busqueda(valor: string) { this.busquedaTexto.set(valor); }
  protected get filtroRol(): string { return this.filtroRolTexto(); }
  protected set filtroRol(valor: string) { this.filtroRolTexto.set(valor); }
  protected get verInactivos(): boolean { return this.verInactivosMarcado(); }
  protected set verInactivos(valor: boolean) { this.verInactivosMarcado.set(valor); }

  protected nombre = '';
  protected apellido = '';
  protected correo = '';
  protected contrasenaInicial = '';
  protected nombreRol = '';
  protected codigoRol = '';
  protected descripcionRol = '';
  protected profesionalId = '';

  protected readonly puedeDarAcceso = computed(
    () => this.sesion.tienePermiso(PERMISOS.usuarioCrear) && this.sesion.tienePermiso(PERMISOS.rolAsignar),
  );
  protected readonly puedeAsignar = computed(() => this.sesion.tienePermiso(PERMISOS.rolAsignar));
  protected readonly puedeCrearRol = computed(() => this.sesion.tienePermiso(PERMISOS.rolAsignar));

  /** Personal filtrado por texto, rol y estado, con quien tiene acceso primero. */
  protected readonly personal = computed(() => {
    const texto = this.busquedaTexto().trim().toLowerCase();
    const rol = this.filtroRolTexto();
    return this.usuarios()
      .filter((u) => this.verInactivosMarcado() || u.activo)
      .filter((u) => !rol || u.roles.includes(rol))
      .filter(
        (u) => !texto || `${u.nombre} ${u.apellido} ${u.correo}`.toLowerCase().includes(texto),
      )
      .sort((a, b) => Number(b.activo) - Number(a.activo) || a.apellido.localeCompare(b.apellido));
  });

  protected readonly permisosPorCategoria = computed(() => {
    const grupos = new Map<string, PermisoClinica[]>();
    for (const permiso of this.permisos()) {
      const lista = grupos.get(permiso.categoria) ?? [];
      lista.push(permiso);
      grupos.set(permiso.categoria, lista);
    }
    return [...grupos.entries()]
      .map(([categoria, permisos]) => ({ categoria, nombre: CATEGORIAS[categoria] ?? categoria, permisos }))
      .sort((a, b) => a.nombre.localeCompare(b.nombre));
  });

  constructor() {
    this.cargar();
  }

  protected cargar(): void {
    this.cargando.set(true);
    this.api.leer<UsuarioClinica[]>('/usuarios').subscribe({
      next: (datos) => {
        this.usuarios.set(datos);
        this.cargando.set(false);
      },
      error: (error: FalloApi) => {
        this.mostrarError(error);
        this.cargando.set(false);
      },
    });
    this.api.leer<RolClinica[]>('/usuarios/roles').subscribe({
      next: (datos) => this.roles.set(datos),
      error: (error: FalloApi) => this.mostrarError(error),
    });
    if (this.sesion.tienePermiso(PERMISOS.rolAsignar)) {
      this.api.leer<PermisoClinica[]>('/usuarios/permisos').subscribe({
        next: (datos) => this.permisos.set(datos),
        error: (error: FalloApi) => this.mostrarError(error),
      });
      this.api.leer<ProfesionalClinica[]>('/usuarios/profesionales').subscribe({
        next: (datos) => this.profesionales.set(datos),
        error: (error: FalloApi) => this.mostrarError(error),
      });
    }
  }

  protected abrir(ventana: Ventana): void {
    this.error.set('');
    this.aviso.set('');
    if (ventana.tipo === 'alta') {
      this.nombre = '';
      this.apellido = '';
      this.correo = '';
      this.contrasenaInicial = '';
      this.profesionalId = '';
      this.rolesSeleccionados.set(new Set());
    }
    if (ventana.tipo === 'rol-nuevo') {
      this.nombreRol = '';
      this.codigoRol = '';
      this.descripcionRol = '';
      this.permisosSeleccionados.set(new Set());
    }
    if (ventana.tipo === 'accesos') {
      this.editar(ventana.usuario);
    }
    this.ventana.set(ventana);
  }

  protected cerrarVentana(): void {
    this.ventana.set(null);
    this.error.set('');
  }

  protected editar(usuario: UsuarioClinica): void {
    this.profesionalId = usuario.profesional_id ?? '';
    this.rolesSeleccionados.set(
      new Set(this.roles().filter((rol) => usuario.roles.includes(rol.nombre)).map((rol) => rol.id)),
    );
    this.api.leer<ProfesionalClinica[]>('/usuarios/profesionales', { usuario_id: usuario.id }).subscribe({
      next: (datos) => this.profesionales.set(datos),
      error: (error: FalloApi) => this.mostrarError(error),
    });
  }

  protected personasCon(rol: RolClinica): number {
    return this.usuarios().filter((u) => u.activo && u.roles.includes(rol.nombre)).length;
  }

  /** Permisos de un rol, con su descripción, agrupados por módulo. */
  protected permisosDeRol(rol: RolClinica): { nombre: string; permisos: string[] }[] {
    const descripciones = new Map(this.permisos().map((p) => [p.codigo, p]));
    const grupos = new Map<string, string[]>();
    for (const codigo of rol.permisos) {
      const permiso = descripciones.get(codigo);
      const categoria = permiso ? (CATEGORIAS[permiso.categoria] ?? permiso.categoria) : 'Otros';
      const lista = grupos.get(categoria) ?? [];
      lista.push(permiso?.descripcion ?? codigo);
      grupos.set(categoria, lista);
    }
    return [...grupos.entries()]
      .map(([nombre, permisos]) => ({ nombre, permisos }))
      .sort((a, b) => a.nombre.localeCompare(b.nombre));
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

  protected grupoCompleto(permisos: readonly PermisoClinica[]): boolean {
    return permisos.every((p) => this.permisosSeleccionados().has(p.codigo));
  }

  protected alternarGrupo(permisos: readonly PermisoClinica[], marcado: boolean): void {
    for (const permiso of permisos) this.alternarPermiso(permiso.codigo, marcado);
  }

  /** El código se propone a partir del nombre mientras nadie lo haya escrito a mano. */
  protected cambiarNombreRol(valor: string): void {
    const propuesto = this.codigoDe(this.nombreRol);
    this.nombreRol = valor;
    if (!this.codigoRol || this.codigoRol === propuesto) {
      this.codigoRol = this.codigoDe(valor);
    }
  }

  private codigoDe(nombre: string): string {
    const base = nombre
      .normalize('NFD')
      .replace(/[̀-ͯ]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '')
      .slice(0, 50);
    return /^[a-z]/.test(base) ? base : base ? `rol_${base}`.slice(0, 50) : '';
  }

  protected crearRol(invalido: boolean): void {
    if (invalido) {
      this.error.set('Complete el nombre y un código válido (minúsculas, números y guion bajo).');
      return;
    }
    if (this.permisosSeleccionados().size === 0) {
      this.error.set('Elija al menos un permiso para el rol.');
      return;
    }
    this.enviar(
      '/usuarios/roles',
      {
        codigo: this.codigoRol.trim().toLowerCase(),
        nombre: this.nombreRol.trim(),
        descripcion: this.descripcionRol.trim() || null,
        permisos: [...this.permisosSeleccionados()],
      },
      false,
      'Rol creado.',
      () => {
        this.pestana.set('roles');
        this.cargar();
      },
    );
  }

  protected crearUsuario(invalido: boolean): void {
    if (invalido) {
      this.error.set('Revise los datos: nombre, apellido, un correo válido y una contraseña de al menos 12 caracteres.');
      return;
    }
    if (this.rolesSeleccionados().size === 0) {
      this.error.set('Elija al menos un rol.');
      return;
    }
    if (this.requiereProfesional() && !this.profesionalId) {
      this.error.set('Elija el perfil profesional al que se vincula la cuenta.');
      return;
    }
    this.enviar(
      '/usuarios',
      {
        nombre: this.nombre.trim(),
        apellido: this.apellido.trim(),
        correo: this.correo.trim().toLowerCase(),
        contrasena_inicial: this.contrasenaInicial,
        roles: [...this.rolesSeleccionados()],
        profesional_id: this.requiereProfesional() ? this.profesionalId || null : null,
      },
      false,
      'Cuenta creada y acceso concedido.',
      () => this.cargar(),
    );
  }

  protected guardarRoles(usuario: UsuarioClinica): void {
    if (this.requiereProfesional() && !this.profesionalId) {
      this.error.set('Elija el perfil profesional al que se vincula la cuenta.');
      return;
    }
    this.enviar(
      `/usuarios/${usuario.id}/roles`,
      {
        roles: [...this.rolesSeleccionados()],
        profesional_id: this.requiereProfesional() ? this.profesionalId || null : null,
      },
      true,
      'Accesos actualizados.',
      () => this.cargar(),
    );
  }

  protected cambiarEstado(usuario: UsuarioClinica, activo: boolean): void {
    this.enviar(
      `/usuarios/${usuario.id}/estado`,
      { activo },
      true,
      activo ? 'Acceso restaurado.' : 'Acceso quitado y sesiones cerradas.',
      () => this.cargar(),
    );
  }

  private enviar(ruta: string, datos: unknown, editar: boolean, mensaje: string, alGuardar: () => void): void {
    this.ocupado.set(true);
    this.error.set('');
    this.aviso.set('');
    this.api.guardar(ruta, datos, crypto.randomUUID(), editar).subscribe({
      next: () => {
        this.ocupado.set(false);
        this.ventana.set(null);
        this.aviso.set(mensaje);
        this.indicadores.refrescar();
        alGuardar();
      },
      error: (error: FalloApi) => {
        this.ocupado.set(false);
        this.mostrarError(error);
      },
    });
  }

  private mostrarError(error: FalloApi): void {
    this.error.set(error.message);
  }
}
