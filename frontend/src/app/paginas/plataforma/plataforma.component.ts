import { Component, OnInit, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CapturaFotosComponent, type FotoSeleccionada } from '../../compartido/captura-fotos.component';
import { FotosRegistroService } from '../../nucleo/servicios/fotos-registro.service';
import { FotosRegistroComponent } from '../../compartido/fotos-registro.component';

import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
import { EditorRegistroComponent } from '../../compartido/editor-registro.component';
import {
  ApiService,
  FalloApi,
  type AltaClinicaPlataforma,
  type AltaUsuarioPlataforma,
  type AsignacionUsuarioPlataforma,
  type AltaSedePlataforma,
  type ClinicaPlataforma,
  type ProfesionalPlataforma,
  type RolPlataforma,
  type SedePlataforma,
  type UsuarioPlataforma,
} from '../../nucleo/servicios/api.service';

@Component({
  selector: 'app-plataforma',
  standalone: true,
  imports: [FormsModule, VentanaFlotanteComponent, EditorRegistroComponent, CapturaFotosComponent, FotosRegistroComponent],
  host: { class: 'pantalla' },
  template: `
    <header class="encabezado pantalla__fijo">
      <div><p class="sobretitulo">Administración global</p><h1>Clínicas</h1>
        <p>Provisiona cada organización con su sede inicial y su administrador responsable.</p></div>
      <div class="acciones-clinica">
        <button class="boton" type="button" (click)="cargar()" [disabled]="cargando()">Actualizar</button>
        <button class="boton boton--principal" type="button" (click)="abrirNuevoUsuario()" [disabled]="!tieneClinicasActivas()" title="La cuenta se vincula a una clínica, recibe los módulos seleccionados y deberá cambiar su contraseña temporal.">Dar acceso a una persona</button>
      </div>
    </header>

    @if (error()) { <p class="mensaje mensaje--error pantalla__fijo" role="alert">{{ error() }}</p> }
    @if (aviso()) { <p class="mensaje mensaje--bien pantalla__fijo" role="status">{{ aviso() }}</p> }

    <!-- Dos listas lado a lado: organizaciones (y sus sedes) y accesos del
         personal. Cada una desplaza dentro de su tarjeta. -->
    <div class="pantalla__columnas plataforma__columnas">
    <div class="plataforma__columna">
    <section class="tarjeta tarjeta--llena">
      <div class="seccion-titulo"><div><h2>Organizaciones registradas</h2>
        <p>{{ clinicas().length }} clínicas en la plataforma</p></div>
        <button class="boton boton--principal" type="button" (click)="abrirNuevaClinica()">Registrar clínica</button></div>
      @if (cargando()) { <p role="status">Cargando clínicas…</p> }
      @if (!cargando() && clinicas().length === 0) { <p class="vacio">Todavía no se han registrado clínicas.</p> }
      <div class="desplazable" tabindex="0" role="region" aria-label="Organizaciones registradas">
      @for (clinica of clinicas(); track clinica.id) {
        <article class="fila">
          <div class="datos"><strong>{{ clinica.nombre }}</strong><app-fotos-registro tipo="clinica" [registroId]="clinica.id" [puedeEditar]="true" />
            <span>{{ clinica.correo || 'Sin correo institucional' }}</span>
            <span>{{ clinica.cantidad_sedes }} sedes · {{ clinica.cantidad_usuarios }} cuentas</span>
          </div>
          <div class="acciones-clinica"><span class="etiqueta">{{ clinica.activa ? 'Activa' : 'Inactiva' }}</span>
            <button class="boton boton--pequeno" type="button" (click)="registro.set({ tipo: 'clinica', fila: clinica, estado: null })">Editar clínica</button>
            <button class="boton boton--pequeno" type="button" (click)="registro.set({ tipo: 'clinica', fila: clinica, estado: !clinica.activa })">{{ clinica.activa ? 'Desactivar clínica' : 'Reactivar clínica' }}</button>
            @if (clinica.activa) { <button class="boton boton--pequeno" type="button" (click)="alternarSedes(clinica)">{{ clinicaSedesId() === clinica.id ? 'Cerrar sedes' : 'Gestionar sedes' }}</button> }
          </div>
        </article>
      }
      </div>
    </section>

    @if (clinicaSedesId()) {
      <section class="tarjeta tarjeta--llena plataforma__sedes">
        <div class="seccion-titulo"><div><h2>Sedes de {{ nombreClinicaSedes() }}</h2>
          <p>Administra las sucursales que pertenecen a esta clínica.</p></div>
          <div class="acciones-clinica"><button class="boton boton--principal" type="button" (click)="abrirNuevaSede()">Agregar sucursal</button><button class="boton" type="button" (click)="cargarSedes()" [disabled]="cargandoSedes()">Actualizar sedes</button></div></div>
        @if (errorSedes()) { <p class="mensaje mensaje--error" role="alert">{{ errorSedes() }}</p> }
        @if (avisoSede()) { <p class="mensaje mensaje--bien" role="status">{{ avisoSede() }}</p> }
        @if (cargandoSedes()) { <p role="status">Cargando sedes…</p> }
        <div class="desplazable" tabindex="0" role="region" [attr.aria-label]="'Sedes de ' + nombreClinicaSedes()">
        @for (sede of sedes(); track sede.id) {
          <article class="fila"><div class="datos"><strong>{{ sede.nombre }}</strong><app-fotos-registro tipo="sede" [registroId]="sede.id" [puedeEditar]="true" />
            <span>{{ sede.direccion || 'Dirección no registrada' }} · {{ sede.zona_horaria || 'Zona horaria heredada' }}</span>
            @if (sede.telefono) { <span>{{ sede.telefono }}</span> }
          </div><span class="etiqueta">{{ sede.activa ? 'Activa' : 'Inactiva' }}</span></article>
        }
        </div>
      </section>
    }
    </div>

    @if (nuevaSedeAbierta()) {
      <app-ventana-flotante ceja="{{ nombreClinicaSedes() }}" titulo="Agregar sede" forma="centrada" [anchoMaximo]="600" [cierraAlPulsarFuera]="false" (cerrar)="cerrarNuevaSede()">
        @if (errorSedes()) { <p class="mensaje mensaje--error" role="alert">{{ errorSedes() }}</p> }
        <p>Si no indicas otra zona horaria, la sede heredará la de la clínica.</p>
        <form id="formulario-sede-plataforma" (ngSubmit)="crearSede()">
          <fieldset [disabled]="ocupadoSede() || !!operacionFotosSede.guardado" style="border:0;padding:0;margin:0">
          <div class="campos">
            <label>Nombre de la sede<input name="nombreSede" [(ngModel)]="formSede.nombre" required maxlength="200" /></label>
            <label>Dirección<input name="direccionSede" [(ngModel)]="formSede.direccion" maxlength="500" /></label>
            <label>Teléfono<input name="telefonoSede" [(ngModel)]="formSede.telefono" maxlength="32" /></label>
            <label>Zona horaria<select name="zonaSede" [(ngModel)]="formSede.zona_horaria">
              <option [ngValue]="null">Heredar zona de la clínica</option><option value="America/Guayaquil">Ecuador · Guayaquil</option>
              <option value="America/Bogota">Colombia · Bogotá</option><option value="America/Lima">Perú · Lima</option>
              <option value="America/Mexico_City">México · Ciudad de México</option><option value="America/Santiago">Chile · Santiago</option>
              <option value="Europe/Madrid">España · Madrid</option>
            </select></label>
          </div>
        </fieldset><app-captura-fotos titulo="Fotografías de la sede" [ocupada]="ocupadoSede()" (cambiadas)="fotosSede=$event" /></form>
        <div pie class="acciones"><button class="boton" type="button" (click)="cerrarNuevaSede()" [disabled]="ocupadoSede()">Cancelar</button><button class="boton boton--principal" type="submit" form="formulario-sede-plataforma" [disabled]="ocupadoSede() || !formSede.nombre.trim()">{{ ocupadoSede() ? 'Guardando…' : operacionFotosSede.guardado ? 'Completar fotos' : 'Crear sede' }}</button></div>
      </app-ventana-flotante>
    }

    <section class="tarjeta tarjeta--llena">
      <div class="seccion-titulo"><div><h2>Accesos del personal</h2>
        <p>Asigna a cada cuenta una clínica y los módulos habilitados para su función.</p></div>
        <button class="boton" type="button" (click)="cargarUsuarios()" [disabled]="cargandoUsuarios()">Actualizar cuentas</button></div>
      @if (errorUsuarios()) { <p class="mensaje mensaje--error" role="alert">{{ errorUsuarios() }}</p> }
      @if (avisoUsuario()) { <p class="mensaje mensaje--bien" role="status">{{ avisoUsuario() }}</p> }
      @if (cargandoUsuarios()) { <p role="status">Cargando cuentas…</p> }
      @if (!cargandoUsuarios() && usuarios().length === 0) { <p class="vacio">No hay cuentas de personal registradas.</p> }
      <div class="desplazable" tabindex="0" role="region" aria-label="Accesos del personal">
      @for (usuario of usuarios(); track usuario.id) {
        <article class="fila">
          <div class="datos"><strong>{{ usuario.nombre }} {{ usuario.apellido }}</strong>@if(usuario.clinica_id){<app-fotos-registro tipo="usuario" [registroId]="usuario.id" [puedeEditar]="true" />}
            <span>{{ usuario.correo }} · {{ usuario.clinica_nombre }}</span>
            <span class="etiquetas">{{ usuario.roles.join(' · ') || 'Sin roles' }}</span>
            @if (!usuario.roles.includes('Superadministrador')) { <span>{{ resumenSedes(usuario) }}</span> }
          </div>
          @if (!usuario.roles.includes('Superadministrador')) {
            <button class="boton boton--pequeno" type="button" (click)="registro.set({ tipo: 'usuario', fila: usuario, estado: null })">Editar usuario</button>
            <button class="boton boton--pequeno" type="button" (click)="registro.set({ tipo: 'usuario', fila: usuario, estado: !usuario.activo })">{{ usuario.activo ? 'Desactivar usuario' : 'Reactivar usuario' }}</button>
            <button class="boton boton--pequeno" type="button" (click)="editarAsignacion(usuario)">Clínica y módulos</button>
          }
        </article>
      }
      </div>
    </section>
    </div>

    @if (registro(); as r) {
      <app-editor-registro [tipo]="r.tipo" [ruta]="'/plataforma/clinicas/' + (r.tipo === 'usuario' ? 'usuarios/' : '') + r.fila.id" [inicial]="r.fila" [estado]="r.estado" [titulo]="(r.estado === null ? 'Editar ' : r.estado ? 'Reactivar ' : 'Desactivar ') + r.fila.nombre" (cerrar)="registro.set(null)" (guardado)="registro.set(null); cargar(); cargarUsuarios()" />
    }
    @if (usuarioEditando(); as usuario) {
      <app-ventana-flotante ceja="Acceso a la clínica y módulos" [titulo]="usuario.nombre + ' ' + usuario.apellido" forma="centrada" [anchoMaximo]="720" [altoCompleto]="true" [cierraAlPulsarFuera]="false" (cerrar)="cerrarEdicionAsignacion()">
        <p>Guardar cambios revoca sesiones abiertas, reemplaza los roles y actualiza las sedes habilitadas.</p>
        @if (errorUsuarios()) { <p class="mensaje mensaje--error" role="alert">{{ errorUsuarios() }}</p> }
        <label>Clínica<select name="clinicaDestino" [(ngModel)]="clinicaDestinoId" (ngModelChange)="cambioClinicaDestino($event)">
          @for (clinica of clinicas(); track clinica.id) { @if (clinica.activa) { <option [value]="clinica.id">{{ clinica.nombre }}</option> } }
        </select></label>
        <h3>Módulos y roles</h3>
        <div class="opciones">
          @for (rol of rolesDestino(); track rol.id) {
            <label class="opcion"><input type="checkbox" [checked]="rolesDestinoSeleccionados().has(rol.id)" (change)="alternarRolDestino(rol.id, $any($event.target).checked)" />
              <span><strong>{{ rol.nombre }}</strong><small>{{ rol.descripcion || 'Permisos disponibles en esta clínica' }}</small></span></label>
          }
        </div>
        @if (requiereProfesionalDestino()) {
          <label>Perfil profesional<select name="profesionalDestino" [(ngModel)]="profesionalDestinoId" required>
            <option value="">Seleccione un profesional</option>@for (profesional of profesionalesDestino(); track profesional.id) { <option [value]="profesional.id">{{ profesional.nombre }} {{ profesional.apellido }}</option> }
          </select></label>
        }
        <h3>Ámbito de sedes</h3>
        <label class="opcion"><input type="checkbox" [checked]="todasLasSedesDestino()" (change)="todasLasSedesDestino.set($any($event.target).checked)" />
          <span><strong>Acceso a todas las sedes de {{ nombreClinicaDestino() }}</strong><small>Al desactivarlo, la cuenta solo podrá usar las sedes marcadas.</small></span></label>
        @if (!todasLasSedesDestino()) {
          <div class="opciones">
            @for (sede of sedesDestino(); track sede.id) {
              <label class="opcion"><input type="checkbox" [checked]="sedesDestinoSeleccionadas().has(sede.id)" (change)="alternarSedeDestino(sede.id, $any($event.target).checked)" />
                <span><strong>{{ sede.nombre }}</strong><small>{{ sede.direccion || 'Dirección no registrada' }}</small></span></label>
            }
          </div>
          @if (!cargandoSedesDestino() && sedesDestinoSeleccionadas().size === 0) { <p class="mensaje mensaje--error" role="alert">Selecciona al menos una sede para guardar el acceso.</p> }
        }
        <div pie class="acciones"><button class="boton" type="button" (click)="cerrarEdicionAsignacion()" [disabled]="ocupadoUsuario()">Cancelar</button><button class="boton boton--principal" type="button" (click)="guardarAsignacion(usuario)" [disabled]="ocupadoUsuario() || rolesDestinoSeleccionados().size === 0 || cargandoSedesDestino() || (!todasLasSedesDestino() && sedesDestinoSeleccionadas().size === 0)">Guardar accesos</button></div>
      </app-ventana-flotante>
    }


    @if (nuevoUsuarioAbierto()) {
      <app-ventana-flotante ceja="Roles, módulos y sedes" titulo="Dar acceso a una persona" forma="centrada" [anchoMaximo]="720" [altoCompleto]="true" [cierraAlPulsarFuera]="false" (cerrar)="cerrarNuevoUsuario()">
        @if (errorUsuarios()) { <p class="mensaje mensaje--error" role="alert">{{ errorUsuarios() }}</p> }
        <form id="formulario-nuevo-usuario-plataforma" (ngSubmit)="crearUsuario()">
        <div class="campos">
          <label>Clínica<select name="clinicaNuevaUsuario" [(ngModel)]="clinicaNuevaUsuarioId" (ngModelChange)="cambioClinicaNuevaUsuario($event)" required>
            <option value="">Seleccione una clínica</option>@for (clinica of clinicas(); track clinica.id) { @if (clinica.activa) { <option [value]="clinica.id">{{ clinica.nombre }}</option> } }
          </select></label>
          <label>Nombre<input name="nombreUsuario" [(ngModel)]="nuevoUsuario.nombre" required maxlength="100" /></label>
          <label>Apellido<input name="apellidoUsuario" [(ngModel)]="nuevoUsuario.apellido" required maxlength="100" /></label>
          <label>Correo de acceso<input name="correoUsuario" [(ngModel)]="nuevoUsuario.correo" type="email" required maxlength="200" /></label>
          <label>Contraseña temporal<input name="contrasenaUsuario" [(ngModel)]="nuevoUsuario.contrasena_inicial" type="password" required minlength="12" maxlength="128" autocomplete="new-password" /></label>
        </div>
        @if (clinicaNuevaUsuarioId) {
          <h3>Módulos y roles</h3>
          <div class="opciones">
            @for (rol of rolesNuevoUsuario(); track rol.id) {
              <label class="opcion"><input type="checkbox" [checked]="rolesNuevoUsuarioSeleccionados().has(rol.id)" (change)="alternarRolNuevoUsuario(rol.id, $any($event.target).checked)" />
                <span><strong>{{ rol.nombre }}</strong><small>{{ rol.descripcion || 'Permisos disponibles en esta clínica' }}</small></span></label>
            }
          </div>
          @if (requiereProfesionalNuevoUsuario()) {
            <label>Perfil profesional<select name="profesionalNuevo" [(ngModel)]="profesionalNuevoId" required>
              <option value="">Seleccione un profesional</option>@for (profesional of profesionalesNuevoUsuario(); track profesional.id) { <option [value]="profesional.id">{{ profesional.nombre }} {{ profesional.apellido }}</option> }
            </select></label>
          }
          <h3>Ámbito de sedes</h3>
          <label class="opcion"><input type="checkbox" [checked]="todasLasSedesNuevoUsuario()" (change)="todasLasSedesNuevoUsuario.set($any($event.target).checked)" />
            <span><strong>Acceso a todas las sedes de la clínica</strong><small>Desactívalo para elegir sedes concretas.</small></span></label>
          @if (!todasLasSedesNuevoUsuario()) {
            <div class="opciones">
              @for (sede of sedesNuevoUsuario(); track sede.id) {
                <label class="opcion"><input type="checkbox" [checked]="sedesNuevoUsuarioSeleccionadas().has(sede.id)" (change)="alternarSedeNuevoUsuario(sede.id, $any($event.target).checked)" />
                  <span><strong>{{ sede.nombre }}</strong><small>{{ sede.direccion || 'Dirección no registrada' }}</small></span></label>
              }
            </div>
            @if (!cargandoSedesNuevoUsuario() && sedesNuevoUsuarioSeleccionadas().size === 0) { <p class="mensaje mensaje--error" role="alert">Selecciona al menos una sede para crear la cuenta.</p> }
          }
        }
        <app-captura-fotos titulo="Fotografía del personal" [perfil]="true" [ocupada]="ocupadoUsuario()" (cambiadas)="fotosUsuario=$event" /></form>
        <div pie class="acciones"><button class="boton" type="button" (click)="cerrarNuevoUsuario()" [disabled]="ocupadoUsuario()">Cancelar</button><button class="boton boton--principal" type="submit" form="formulario-nuevo-usuario-plataforma" [disabled]="ocupadoUsuario() || !clinicaNuevaUsuarioId || rolesNuevoUsuarioSeleccionados().size === 0 || (!todasLasSedesNuevoUsuario() && sedesNuevoUsuarioSeleccionadas().size === 0)">{{ ocupadoUsuario() ? 'Guardando…' : 'Crear cuenta y asignar módulos' }}</button></div>
      </app-ventana-flotante>
    }

    @if (nuevaClinicaAbierta()) {
      <app-ventana-flotante ceja="Administración global" titulo="Registrar clínica" forma="centrada" [anchoMaximo]="760" [altoCompleto]="true" [cierraAlPulsarFuera]="false" (cerrar)="cerrarNuevaClinica()">
        @if (error()) { <p class="mensaje mensaje--error" role="alert">{{ error() }}</p> }
        <form id="formulario-clinica-plataforma" (ngSubmit)="crear()">
        <h3>Datos de la clínica</h3>
        <div class="campos">
          <label>Nombre de la clínica<input name="nombre" [(ngModel)]="form.nombre" required maxlength="200" /></label>
          <label>Identificación fiscal<input name="identificacion" [(ngModel)]="form.identificacion_fiscal" maxlength="50" /></label>
          <label>Correo institucional<input name="correoClinica" [(ngModel)]="form.correo" type="email" maxlength="200" /></label>
          <label>Teléfono<input name="telefono" [(ngModel)]="form.telefono" maxlength="32" /></label>
          <label>Zona horaria<select name="zona" [(ngModel)]="form.zona_horaria">
            <option value="America/Guayaquil">Ecuador · Guayaquil</option><option value="America/Bogota">Colombia · Bogotá</option>
            <option value="America/Lima">Perú · Lima</option><option value="America/Mexico_City">México · Ciudad de México</option>
            <option value="America/Santiago">Chile · Santiago</option><option value="Europe/Madrid">España · Madrid</option>
          </select></label>
          <label>Moneda<input name="moneda" [(ngModel)]="form.moneda" required minlength="3" maxlength="3" /></label>
          <label>Idioma<input name="idioma" [(ngModel)]="form.idioma" required minlength="2" maxlength="8" /></label>
        </div>
        <h3>Sede principal</h3>
        <div class="campos">
          <label>Nombre de la sede<input name="sede" [(ngModel)]="form.sede_nombre" required maxlength="200" /></label>
          <label>Dirección<input name="direccion" [(ngModel)]="form.sede_direccion" maxlength="500" /></label>
        </div>
        <h3>Administrador inicial</h3>
        <p>Su cuenta recibirá el rol de administrador de clínica y deberá cambiar la contraseña al ingresar.</p>
        <div class="campos">
          <label>Nombre<input name="nombreAdmin" [(ngModel)]="form.administrador_nombre" required maxlength="100" /></label>
          <label>Apellido<input name="apellidoAdmin" [(ngModel)]="form.administrador_apellido" required maxlength="100" /></label>
          <label>Correo de acceso<input name="correoAdmin" [(ngModel)]="form.administrador_correo" type="email" required maxlength="200" /></label>
          <label>Contraseña temporal<input name="contrasena" [(ngModel)]="form.contrasena_inicial" type="password" required minlength="12" maxlength="128" autocomplete="new-password" /></label>
        </div>
        <app-captura-fotos titulo="Logo y fotografías de la clínica" [ocupada]="ocupado()" (cambiadas)="fotos=$event" />
        </form>
        <div pie class="acciones"><button class="boton" type="button" (click)="cerrarNuevaClinica()" [disabled]="ocupado()">Cancelar</button><button class="boton boton--principal" type="submit" form="formulario-clinica-plataforma" [disabled]="ocupado()">{{ ocupado() ? 'Registrando…' : 'Crear clínica y administrador' }}</button></div>
      </app-ventana-flotante>
    }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: [`
    .encabezado { display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; }
    .tarjeta { background:var(--superficie, #fff); border:1px solid var(--borde, #dce5ed); border-radius:1rem; padding:clamp(1rem, 2.5vw, 1.5rem); }
    .seccion-titulo { margin-bottom:1rem; }
    .seccion-titulo h2, h3 { margin:0 0 .4rem; }
    .seccion-titulo p, form>p { color:var(--texto-secundario, #5d6b79); margin:.25rem 0 1rem; }
    .fila { display:flex; align-items:center; justify-content:space-between; gap:1rem; padding:.9rem 0; border-top:1px solid var(--borde, #dce5ed); }
    /* Tres botones y la etiqueta: en pantallas estrechas saltan de línea en
       lugar de ensanchar la página. */
    .acciones-clinica { display:flex; flex-wrap:wrap; align-items:center; gap:.6rem; }
    .datos { display:grid; gap:.25rem; }.datos span { color:var(--texto-secundario, #5d6b79); font-size:.9rem; }
  .campos { display:grid; grid-template-columns:repeat(auto-fit, minmax(min(100%, 14rem), 1fr)); gap:1rem; margin:1rem 0 1.4rem; }
    .opciones { display:grid; grid-template-columns:repeat(auto-fit, minmax(min(100%, 17rem), 1fr)); gap:.7rem; margin:1rem 0; }
    .opcion { display:flex; align-items:flex-start; gap:.7rem; padding:.85rem; border:1px solid var(--borde, #dce5ed); border-radius:.65rem; }
    .opcion input { width:auto; min-height:auto; margin-top:.2rem; }.opcion span { display:grid; gap:.2rem; }.opcion small { color:var(--texto-secundario, #5d6b79); }
    .acciones { display:flex; gap:.75rem; margin-top:1rem; }
    label { display:grid; gap:.4rem; font-weight:600; font-size:.92rem; }
    input, select { width:100%; min-height:2.75rem; padding:.6rem .75rem; border:1px solid var(--borde, #cbd5df); border-radius:.55rem; color:inherit; background:var(--superficie, #fff); font:inherit; }
    h3 { margin-top:1.5rem; }
    .mensaje { padding:.8rem 1rem; border-radius:.6rem; }.mensaje--error { background:#fff0ef; color:#a32720; }.mensaje--bien { background:#eaf8f1; color:#126644; }
    .vacio { color:var(--texto-secundario, #5d6b79); }
    @media (max-width:600px) { .encabezado { flex-direction:column; } }
    /* Pantalla de trabajo: cada lista desplaza dentro de su tarjeta. */
    .plataforma__columna { display:flex; flex-direction:column; gap:var(--espacio-3); min-width:0; min-height:0; }
    .tarjeta--llena > :not(.desplazable) { flex:none; }
    .fila { flex-wrap:wrap; }
    .fila .datos { flex:1 1 16rem; min-width:0; }
    .datos span { overflow-wrap:anywhere; }
    @media (min-width:821px) and (min-height:600px) {
      .plataforma__columnas { --pantalla-columnas: minmax(0, 1fr) minmax(0, 1.15fr); }
      .tarjeta { padding:var(--espacio-4); }
      .seccion-titulo { display:flex; flex-wrap:wrap; align-items:flex-start; justify-content:space-between; gap:var(--espacio-2); margin-bottom:var(--espacio-2); }
      .seccion-titulo h2 { font-size:1.1rem; }
      /* Las sedes suelen ser pocas: toman su alto, como mucho la mitad larga
         de la columna, y las organizaciones el resto. */
      .plataforma__sedes { flex:0 1 auto; max-height:55%; }
      .plataforma__sedes > .desplazable { flex:1 1 auto; min-height:3rem; }
      .seccion-titulo p { margin:2px 0 0; }
      .encabezado h1 { margin:0; font-size:1.45rem; }
      .encabezado p { margin:2px 0 0; }
    }
  `],
})
export class PlataformaComponent implements OnInit {
  protected readonly operacionFotosSede=inject(FotosRegistroService).operacion<SedePlataforma>();
  protected readonly operacionFotosUsuario=inject(FotosRegistroService).operacion<UsuarioPlataforma>();
  protected fotosSede:readonly FotoSeleccionada[]=[];
  protected fotosUsuario:readonly FotoSeleccionada[]=[];
  protected readonly operacionFotos = inject(FotosRegistroService).operacion<ClinicaPlataforma>();
  protected fotos: readonly FotoSeleccionada[] = [];
  private readonly api = inject(ApiService);
  protected readonly registro = signal<{ tipo: 'clinica' | 'usuario'; fila: ClinicaPlataforma | UsuarioPlataforma; estado: boolean | null } | null>(null);
  protected readonly clinicas = signal<readonly ClinicaPlataforma[]>([]);
  protected readonly cargando = signal(false);
  protected readonly ocupado = signal(false);
  protected readonly error = signal('');
  protected readonly aviso = signal('');
  protected readonly nuevaClinicaAbierta = signal(false);
  protected readonly clinicaSedesId = signal('');
  protected readonly sedes = signal<readonly SedePlataforma[]>([]);
  protected readonly cargandoSedes = signal(false);
  protected readonly ocupadoSede = signal(false);
  protected readonly errorSedes = signal('');
  protected readonly avisoSede = signal('');
  protected readonly nuevaSedeAbierta = signal(false);
  protected formSede: AltaSedePlataforma = this.formularioSedeVacio();
  protected form: AltaClinicaPlataforma = this.formularioVacio();
  protected readonly usuarios = signal<readonly UsuarioPlataforma[]>([]);
  protected readonly cargandoUsuarios = signal(false);
  protected readonly ocupadoUsuario = signal(false);
  protected readonly errorUsuarios = signal('');
  protected readonly avisoUsuario = signal('');
  protected readonly usuarioEditando = signal<UsuarioPlataforma | null>(null);
  protected readonly nuevoUsuarioAbierto = signal(false);
  protected readonly rolesDestino = signal<readonly RolPlataforma[]>([]);
  protected readonly profesionalesDestino = signal<readonly ProfesionalPlataforma[]>([]);
  protected readonly rolesDestinoSeleccionados = signal<ReadonlySet<string>>(new Set());
  protected readonly sedesDestino = signal<readonly SedePlataforma[]>([]);
  protected readonly sedesDestinoSeleccionadas = signal<ReadonlySet<string>>(new Set());
  protected readonly todasLasSedesDestino = signal(true);
  protected readonly cargandoSedesDestino = signal(false);
  protected readonly rolesNuevoUsuario = signal<readonly RolPlataforma[]>([]);
  protected readonly profesionalesNuevoUsuario = signal<readonly ProfesionalPlataforma[]>([]);
  protected readonly rolesNuevoUsuarioSeleccionados = signal<ReadonlySet<string>>(new Set());
  protected readonly sedesNuevoUsuario = signal<readonly SedePlataforma[]>([]);
  protected readonly sedesNuevoUsuarioSeleccionadas = signal<ReadonlySet<string>>(new Set());
  protected readonly todasLasSedesNuevoUsuario = signal(true);
  protected readonly cargandoSedesNuevoUsuario = signal(false);
  protected clinicaDestinoId = '';
  protected clinicaNuevaUsuarioId = '';
  protected profesionalDestinoId = '';
  protected profesionalNuevoId = '';
  protected nuevoUsuario = { nombre: '', apellido: '', correo: '', contrasena_inicial: '' };

  ngOnInit(): void { this.cargar(); }

  protected abrirNuevaClinica(): void {
    this.operacionFotos.reiniciar(); this.fotos=[];
    this.error.set(''); this.aviso.set('');
    this.form = this.formularioVacio();
    this.nuevaClinicaAbierta.set(true);
  }

  protected cerrarNuevaClinica(): void {
    if (this.ocupado()) return;
    this.nuevaClinicaAbierta.set(false);
    this.form = this.formularioVacio();
    this.error.set('');
  }

  protected abrirNuevaSede(): void {
    this.operacionFotosSede.reiniciar(); this.fotosSede=[];
    if (!this.clinicaSedesId()) return;
    this.errorSedes.set(''); this.avisoSede.set('');
    this.formSede = this.formularioSedeVacio();
    this.nuevaSedeAbierta.set(true);
  }

  protected cerrarNuevaSede(): void {
    if (this.ocupadoSede()) return;
    this.nuevaSedeAbierta.set(false);
    this.formSede = this.formularioSedeVacio();
    this.errorSedes.set('');
  }

  protected abrirNuevoUsuario(): void {
    this.operacionFotosUsuario.reiniciar(); this.fotosUsuario=[];
    if (!this.tieneClinicasActivas()) return;
    this.errorUsuarios.set(''); this.avisoUsuario.set('');
    this.nuevoUsuario = { nombre: '', apellido: '', correo: '', contrasena_inicial: '' };
    this.clinicaNuevaUsuarioId = ''; this.profesionalNuevoId = '';
    this.rolesNuevoUsuario.set([]); this.profesionalesNuevoUsuario.set([]); this.sedesNuevoUsuario.set([]);
    this.rolesNuevoUsuarioSeleccionados.set(new Set()); this.sedesNuevoUsuarioSeleccionadas.set(new Set());
    this.todasLasSedesNuevoUsuario.set(true);
    this.nuevoUsuarioAbierto.set(true);
  }

  protected cerrarNuevoUsuario(): void {
    if (this.ocupadoUsuario()) return;
    this.nuevoUsuarioAbierto.set(false);
    this.nuevoUsuario = { nombre: '', apellido: '', correo: '', contrasena_inicial: '' };
    this.clinicaNuevaUsuarioId = ''; this.profesionalNuevoId = '';
    this.rolesNuevoUsuario.set([]); this.profesionalesNuevoUsuario.set([]); this.sedesNuevoUsuario.set([]);
    this.rolesNuevoUsuarioSeleccionados.set(new Set()); this.sedesNuevoUsuarioSeleccionadas.set(new Set());
    this.errorUsuarios.set('');
  }

  protected cerrarEdicionAsignacion(): void {
    if (this.ocupadoUsuario()) return;
    this.usuarioEditando.set(null);
    this.errorUsuarios.set('');
  }

  protected tieneClinicasActivas(): boolean {
    return this.clinicas().some((clinica) => clinica.activa);
  }

  protected cargar(): void {
    this.cargando.set(true);
    this.api.clinicasPlataforma().subscribe({
      next: (respuesta) => { this.clinicas.set(respuesta); this.cargando.set(false); this.cargarUsuarios(); },
      error: (fallo: FalloApi) => { this.error.set(fallo.message); this.cargando.set(false); },
    });
  }

  protected cargarUsuarios(): void {
    this.cargandoUsuarios.set(true);
    this.api.usuariosPlataforma().subscribe({
      next: (respuesta) => { this.usuarios.set(respuesta); this.cargandoUsuarios.set(false); },
      error: (fallo: FalloApi) => { this.errorUsuarios.set(fallo.message); this.cargandoUsuarios.set(false); },
    });
  }

  protected alternarSedes(clinica: ClinicaPlataforma): void {
    this.errorSedes.set(''); this.avisoSede.set('');
    if (this.clinicaSedesId() === clinica.id) {
      this.clinicaSedesId.set(''); this.sedes.set([]); return;
    }
    this.clinicaSedesId.set(clinica.id);
    this.formSede = this.formularioSedeVacio();
    this.cargarSedes();
  }

  protected nombreClinicaSedes(): string {
    return this.clinicas().find((clinica) => clinica.id === this.clinicaSedesId())?.nombre ?? 'clínica';
  }

  protected cargarSedes(): void {
    const clinicaId = this.clinicaSedesId();
    if (!clinicaId) return;
    this.cargandoSedes.set(true); this.errorSedes.set('');
    this.api.sedesPlataforma(clinicaId).subscribe({
      next: (sedes) => { this.sedes.set(sedes); this.cargandoSedes.set(false); },
      error: (fallo: FalloApi) => { this.errorSedes.set(fallo.message); this.cargandoSedes.set(false); },
    });
  }

  protected crearSede(): void {
    const clinicaId = this.clinicaSedesId();
    if (!clinicaId || this.ocupadoSede() || !this.formSede.nombre.trim()) return;
    this.ocupadoSede.set(true); this.errorSedes.set(''); this.avisoSede.set('');
    const datos: AltaSedePlataforma = {
      nombre: this.formSede.nombre.trim(),
      direccion: this.formSede.direccion?.trim() || null,
      telefono: this.formSede.telefono?.trim() || null,
      zona_horaria: this.formSede.zona_horaria,
    };
    this.operacionFotosSede.guardar('sede',this.api.crearSedePlataforma(clinicaId, datos),this.fotosSede).subscribe({
      next: (sede) => {
        this.sedes.update((actuales) => [...actuales, sede].sort((a, b) => a.nombre.localeCompare(b.nombre)));
        this.clinicas.update((actuales) => actuales.map((clinica) => clinica.id === clinicaId
          ? { ...clinica, cantidad_sedes: clinica.cantidad_sedes + 1 }
          : clinica));
        this.formSede = this.formularioSedeVacio();
        this.nuevaSedeAbierta.set(false);
        this.avisoSede.set(`Sede ${sede.nombre} creada.`); this.ocupadoSede.set(false);
      },
      error: (fallo: FalloApi) => { this.errorSedes.set(fallo.message); this.ocupadoSede.set(false); },
    });
  }

  protected cambioClinicaDestino(clinicaId: string): void {
    const usuario = this.usuarioEditando();
    const usuarioId = usuario?.id;
    if (!usuarioId) return;
    const mismaClinica = clinicaId === usuario.clinica_id;
    this.todasLasSedesDestino.set(mismaClinica && usuario.todas_las_sedes);
    this.sedesDestinoSeleccionadas.set(new Set(mismaClinica ? usuario.sedes_ids : []));
    this.api.rolesPlataforma(clinicaId).subscribe({
      next: (roles) => {
        this.rolesDestino.set(roles);
        const actuales = this.usuarioEditando()?.roles ?? [];
        this.rolesDestinoSeleccionados.set(new Set(roles.filter((rol) => actuales.includes(rol.nombre)).map((rol) => rol.id)));
      },
      error: (fallo: FalloApi) => this.errorUsuarios.set(fallo.message),
    });
    this.api.profesionalesPlataforma(clinicaId, usuarioId).subscribe({
      next: (profesionales) => this.profesionalesDestino.set(profesionales),
      error: (fallo: FalloApi) => this.errorUsuarios.set(fallo.message),
    });
    this.cargandoSedesDestino.set(true);
    this.api.sedesPlataforma(clinicaId).subscribe({
      next: (sedes) => { this.sedesDestino.set(sedes.filter((sede) => sede.activa)); this.cargandoSedesDestino.set(false); },
      error: (fallo: FalloApi) => { this.errorUsuarios.set(fallo.message); this.cargandoSedesDestino.set(false); },
    });
    this.profesionalDestinoId = clinicaId === usuario.clinica_id ? usuario.profesional_id ?? '' : '';
  }

  protected cambioClinicaNuevaUsuario(clinicaId: string): void {
    this.rolesNuevoUsuarioSeleccionados.set(new Set());
    this.sedesNuevoUsuarioSeleccionadas.set(new Set());
    this.todasLasSedesNuevoUsuario.set(true);
    this.profesionalNuevoId = '';
    if (!clinicaId) { this.rolesNuevoUsuario.set([]); this.profesionalesNuevoUsuario.set([]); this.sedesNuevoUsuario.set([]); return; }
    this.api.rolesPlataforma(clinicaId).subscribe({
      next: (roles) => this.rolesNuevoUsuario.set(roles),
      error: (fallo: FalloApi) => this.errorUsuarios.set(fallo.message),
    });
    this.api.profesionalesPlataforma(clinicaId).subscribe({
      next: (profesionales) => this.profesionalesNuevoUsuario.set(profesionales),
      error: (fallo: FalloApi) => this.errorUsuarios.set(fallo.message),
    });
    this.cargandoSedesNuevoUsuario.set(true);
    this.api.sedesPlataforma(clinicaId).subscribe({
      next: (sedes) => { this.sedesNuevoUsuario.set(sedes.filter((sede) => sede.activa)); this.cargandoSedesNuevoUsuario.set(false); },
      error: (fallo: FalloApi) => { this.errorUsuarios.set(fallo.message); this.cargandoSedesNuevoUsuario.set(false); },
    });
  }

  protected editarAsignacion(usuario: UsuarioPlataforma): void {
    this.errorUsuarios.set(''); this.avisoUsuario.set('');
    this.usuarioEditando.set(usuario);
    this.clinicaDestinoId = usuario.clinica_id;
    this.profesionalDestinoId = usuario.profesional_id ?? '';
    this.cambioClinicaDestino(usuario.clinica_id);
  }

  protected alternarRolDestino(id: string, activo: boolean): void {
    this.rolesDestinoSeleccionados.update((actuales) => {
      const siguiente = new Set(actuales);
      if (activo) siguiente.add(id); else siguiente.delete(id);
      return siguiente;
    });
  }

  protected alternarRolNuevoUsuario(id: string, activo: boolean): void {
    this.rolesNuevoUsuarioSeleccionados.update((actuales) => {
      const siguiente = new Set(actuales);
      if (activo) siguiente.add(id); else siguiente.delete(id);
      return siguiente;
    });
  }

  protected requiereProfesionalDestino(): boolean {
    return this.rolesDestino().some((rol) => rol.codigo === 'profesional' && this.rolesDestinoSeleccionados().has(rol.id));
  }

  protected requiereProfesionalNuevoUsuario(): boolean {
    return this.rolesNuevoUsuario().some((rol) => rol.codigo === 'profesional' && this.rolesNuevoUsuarioSeleccionados().has(rol.id));
  }

  protected nombreClinicaDestino(): string {
    return this.clinicas().find((clinica) => clinica.id === this.clinicaDestinoId)?.nombre ?? 'la clínica';
  }

  protected resumenSedes(usuario: UsuarioPlataforma): string {
    if (usuario.todas_las_sedes) return 'Acceso a todas las sedes';
    return usuario.sedes_ids.length === 1
      ? 'Acceso limitado a 1 sede'
      : `Acceso limitado a ${usuario.sedes_ids.length} sedes`;
  }

  protected alternarSedeDestino(id: string, activo: boolean): void {
    this.sedesDestinoSeleccionadas.update((actuales) => actualizarConjunto(actuales, id, activo));
  }

  protected alternarSedeNuevoUsuario(id: string, activo: boolean): void {
    this.sedesNuevoUsuarioSeleccionadas.update((actuales) => actualizarConjunto(actuales, id, activo));
  }

  protected guardarAsignacion(usuario: UsuarioPlataforma): void {
    if (this.ocupadoUsuario()) return;
    this.ocupadoUsuario.set(true); this.errorUsuarios.set(''); this.avisoUsuario.set('');
    const datos: AsignacionUsuarioPlataforma = {
      clinica_id: this.clinicaDestinoId,
      roles: [...this.rolesDestinoSeleccionados()],
      profesional_id: this.requiereProfesionalDestino() ? this.profesionalDestinoId || null : null,
      sedes_ids: this.todasLasSedesDestino() ? null : [...this.sedesDestinoSeleccionadas()],
    };
    if (datos.sedes_ids !== null && datos.sedes_ids.length === 0) {
      this.errorUsuarios.set('Selecciona al menos una sede para guardar el acceso.');
      this.ocupadoUsuario.set(false);
      return;
    }
    this.api.actualizarAsignacionPlataforma(usuario.id, datos).subscribe({
      next: (actualizado) => {
        if (usuario.clinica_id !== actualizado.clinica_id) {
          this.clinicas.update((actuales) => actuales.map((clinica) => ({
            ...clinica,
            cantidad_usuarios: Math.max(0, clinica.cantidad_usuarios + (clinica.id === actualizado.clinica_id ? 1 : clinica.id === usuario.clinica_id ? -1 : 0)),
          })));
        }
        this.reemplazarUsuario(actualizado);
        this.usuarioEditando.set(null); this.avisoUsuario.set(`Acceso actualizado para ${actualizado.nombre} ${actualizado.apellido}.`);
        this.ocupadoUsuario.set(false);
      },
      error: (fallo: FalloApi) => { this.errorUsuarios.set(fallo.message); this.ocupadoUsuario.set(false); },
    });
  }

  protected crearUsuario(): void {
    if (this.ocupadoUsuario() || !this.clinicaNuevaUsuarioId) return;
    this.ocupadoUsuario.set(true); this.errorUsuarios.set(''); this.avisoUsuario.set('');
    const datos: AltaUsuarioPlataforma = {
      ...this.nuevoUsuario,
      correo: this.nuevoUsuario.correo.trim(),
      clinica_id: this.clinicaNuevaUsuarioId,
      roles: [...this.rolesNuevoUsuarioSeleccionados()],
      profesional_id: this.requiereProfesionalNuevoUsuario() ? this.profesionalNuevoId || null : null,
      sedes_ids: this.todasLasSedesNuevoUsuario() ? null : [...this.sedesNuevoUsuarioSeleccionadas()],
    };
    if (datos.sedes_ids !== null && datos.sedes_ids.length === 0) {
      this.errorUsuarios.set('Selecciona al menos una sede para crear la cuenta.');
      this.ocupadoUsuario.set(false);
      return;
    }
    this.operacionFotosUsuario.guardar('usuario',this.api.crearUsuarioPlataforma(datos),this.fotosUsuario).subscribe({
      next: (creado) => {
        this.usuarios.update((actuales) => [...actuales, creado].sort((a, b) => a.clinica_nombre.localeCompare(b.clinica_nombre) || a.apellido.localeCompare(b.apellido)));
        this.clinicas.update((actuales) => actuales.map((clinica) => clinica.id === creado.clinica_id
          ? { ...clinica, cantidad_usuarios: clinica.cantidad_usuarios + 1 }
          : clinica));
        this.nuevoUsuario = { nombre: '', apellido: '', correo: '', contrasena_inicial: '' };
        this.nuevoUsuarioAbierto.set(false); this.clinicaNuevaUsuarioId = ''; this.profesionalNuevoId = '';
        this.rolesNuevoUsuarioSeleccionados.set(new Set()); this.avisoUsuario.set(`Cuenta creada y vinculada a ${creado.clinica_nombre}.`);
        this.ocupadoUsuario.set(false);
      },
      error: (fallo: FalloApi) => { this.errorUsuarios.set(fallo.message); this.ocupadoUsuario.set(false); },
    });
  }

  private reemplazarUsuario(usuario: UsuarioPlataforma): void {
    this.usuarios.update((actuales) => actuales.map((actual) => actual.id === usuario.id ? usuario : actual));
  }

  protected crear(): void {
    if (this.ocupado()) return;
    this.error.set(''); this.aviso.set(''); this.ocupado.set(true);
    this.operacionFotos.guardar('clinica',this.api.crearClinicaPlataforma({
      ...this.form,
      nombre: this.form.nombre.trim(),
      correo: this.form.correo?.trim() || null,
      telefono: this.form.telefono?.trim() || null,
      identificacion_fiscal: this.form.identificacion_fiscal?.trim() || null,
      sede_direccion: this.form.sede_direccion?.trim() || null,
      administrador_correo: this.form.administrador_correo.trim(),
    }),this.fotos).subscribe({
      next: (clinica) => {
        this.clinicas.update((actuales) => [...actuales, clinica].sort((a, b) => a.nombre.localeCompare(b.nombre)));
        this.form = this.formularioVacio();
        this.nuevaClinicaAbierta.set(false);
        this.aviso.set(`Clínica ${clinica.nombre} creada con sede y administrador inicial.`);
        this.ocupado.set(false);
      },
      error: (fallo: FalloApi) => { this.error.set(fallo.message); this.ocupado.set(false); },
    });
  }

  private formularioVacio(): AltaClinicaPlataforma {
    return {
      nombre: '', identificacion_fiscal: null, zona_horaria: 'America/Guayaquil', idioma: 'es', moneda: 'USD',
      telefono: null, correo: null, sede_nombre: 'Sede principal', sede_direccion: null,
      administrador_nombre: '', administrador_apellido: '', administrador_correo: '', contrasena_inicial: '',
    };
  }

  private formularioSedeVacio(): AltaSedePlataforma {
    return { nombre: '', direccion: null, telefono: null, zona_horaria: null };
  }
}

function actualizarConjunto(actual: ReadonlySet<string>, id: string, activo: boolean): ReadonlySet<string> {
  const siguiente = new Set(actual);
  if (activo) siguiente.add(id); else siguiente.delete(id);
  return siguiente;
}
