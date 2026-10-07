import { Component, OnInit, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { FalloApi } from '../../nucleo/servicios/api.service';
import { PERMISOS } from '../../nucleo/servicios/configuracion';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { IconoComponent } from '../../compartido/icono.component';
import { AgendaConfiguracionComponent } from './agenda-configuracion.component';
import { AgendaProfesionalesComponent } from './agenda-profesionales.component';
import { BloqueosAgendaComponent } from './bloqueos-agenda.component';
import { SedesConfiguracionComponent } from './sedes-configuracion.component';
import {
  IntegracionesService,
  type ActualizacionIntegracion,
  type EstadoIntegracion,
  type DatosClinica,
} from './integraciones.service';

interface FormularioIntegracion {
  habilitada: boolean;
  ajustes: Record<string, string | number | boolean>;
  secretos: Record<string, string>;
  eliminar: Record<string, boolean>;
  guardados: Record<string, boolean>;
}

const formularioVacio = (ajustes: FormularioIntegracion['ajustes'], secretos: string[]) => ({
  habilitada: false,
  ajustes,
  secretos: Object.fromEntries(secretos.map((campo) => [campo, ''])) as Record<string, string>,
  eliminar: Object.fromEntries(secretos.map((campo) => [campo, false])) as Record<string, boolean>,
  guardados: Object.fromEntries(secretos.map((campo) => [campo, false])) as Record<string, boolean>,
});

import { IntegracionesIaComponent } from './integraciones-ia.component';
import { AnamnesisConfiguracionComponent } from './anamnesis-configuracion.component';

@Component({
  selector: 'app-configuracion',
  standalone: true,
  imports: [FormsModule, RouterLink, IconoComponent, AgendaConfiguracionComponent, AgendaProfesionalesComponent, BloqueosAgendaComponent, SedesConfiguracionComponent, IntegracionesIaComponent, AnamnesisConfiguracionComponent],
  template: `
    <header class="pagina-cabecera">
      <div>
        <p class="ceja">ADMINISTRACIÓN DE LA CLÍNICA</p>
        <h1>Administración de la clínica</h1>
        <p>Datos institucionales, servicios conectados y accesos del equipo.</p>
      </div>
      <button class="boton" type="button" (click)="cargar()" [disabled]="cargando() || guardando()">
        Actualizar
      </button>
    </header>

    <nav class="pestanas" aria-label="Administración">
      <button type="button" [class.pestanas__activa]="seccion() === 'clinica'" (click)="seccion.set('clinica')">Datos de la clínica</button>
      @if (sesion.tienePermiso(PERMISOS.sedeGestionar)) { <button type="button" [class.pestanas__activa]="seccion() === 'sedes'" (click)="seccion.set('sedes')">Sedes</button> }
      <button type="button" [class.pestanas__activa]="seccion() === 'integraciones'" (click)="seccion.set('integraciones')">Integraciones</button>
      @if (sesion.tienePermiso(PERMISOS.agendaConfigurar)) { <button type="button" [class.pestanas__activa]="seccion() === 'agenda'" (click)="seccion.set('agenda')">Agenda y feriados</button> }
      @if (sesion.tieneAlgunPermiso(PERMISOS.agendaConfigurar, PERMISOS.profesionalGestionar)) { <button type="button" [class.pestanas__activa]="seccion() === 'equipo'" (click)="seccion.set('equipo')">Disponibilidad del equipo</button> }
      @if (sesion.tienePermiso(PERMISOS.bloqueoGestionar)) { <button type="button" [class.pestanas__activa]="seccion() === 'bloqueos'" (click)="seccion.set('bloqueos')">Bloqueos</button> }
      @if (sesion.tienePermiso(PERMISOS.configuracionEscribir)) { <button type="button" [class.pestanas__activa]="seccion() === 'anamnesis'" (click)="seccion.set('anamnesis')">Anamnesis</button> }
      <a routerLink="/usuarios">Usuarios y roles <span aria-hidden="true">↗</span></a>
    </nav>

    @if (seccion() === 'clinica') {
      <section class="tarjeta ficha-clinica">
        <div class="ficha-clinica__intro"><p class="ceja">PERFIL INSTITUCIONAL</p><h2>Información de la clínica</h2><p>Estos datos se aplican a la clínica de tu sesión. El acceso se controla con el permiso de clínica.</p></div>
        @if (cargandoClinica()) { <p role="status">Cargando datos…</p> }
        @if (errorClinica()) { <p class="mensaje mensaje--error" role="alert">{{ errorClinica() }}</p> }
        @if (avisoClinica()) { <p class="mensaje mensaje--bien" role="status">{{ avisoClinica() }}</p> }
        @if (clinica(); as datos) {
          <form class="form-clinica" (ngSubmit)="guardarClinica()">
            <label class="campo"><span class="campo__etiqueta">Nombre de la clínica</span><input class="campo__control" name="clinica-nombre" [(ngModel)]="datos.nombre" maxlength="200" required [disabled]="!sesion.tienePermiso(PERMISOS.clinicaEscribir)" /></label>
            <label class="campo"><span class="campo__etiqueta">Identificación fiscal</span><input class="campo__control" name="clinica-ruc" [(ngModel)]="datos.identificacion_fiscal" maxlength="50" [disabled]="!sesion.tienePermiso(PERMISOS.clinicaEscribir)" /></label>
            <label class="campo"><span class="campo__etiqueta">Teléfono</span><input class="campo__control" name="clinica-telefono" [(ngModel)]="datos.telefono" maxlength="32" [disabled]="!sesion.tienePermiso(PERMISOS.clinicaEscribir)" /></label>
            <label class="campo"><span class="campo__etiqueta">Correo institucional</span><input class="campo__control" name="clinica-correo" type="email" [(ngModel)]="datos.correo" maxlength="200" [disabled]="!sesion.tienePermiso(PERMISOS.clinicaEscribir)" /></label>
            <label class="campo"><span class="campo__etiqueta">Zona horaria (IANA)</span><input class="campo__control" name="clinica-zona" [(ngModel)]="datos.zona_horaria" placeholder="America/Guayaquil" required [disabled]="!sesion.tienePermiso(PERMISOS.clinicaEscribir)" /></label>
            <label class="campo"><span class="campo__etiqueta">Idioma</span><input class="campo__control" name="clinica-idioma" [(ngModel)]="datos.idioma" maxlength="8" required [disabled]="!sesion.tienePermiso(PERMISOS.clinicaEscribir)" /></label>
            <label class="campo"><span class="campo__etiqueta">Moneda</span><input class="campo__control" name="clinica-moneda" [(ngModel)]="datos.moneda" maxlength="3" required [disabled]="!sesion.tienePermiso(PERMISOS.clinicaEscribir)" /></label>
            @if (sesion.tienePermiso(PERMISOS.clinicaEscribir)) { <button class="boton boton--principal" type="submit" [disabled]="guardandoClinica()">{{ guardandoClinica() ? 'Guardando…' : 'Guardar información' }}</button> }
            @else { <p class="campo__ayuda">Tienes acceso de lectura. Solicita el permiso «clinica.escribir» para modificar estos datos.</p> }
          </form>
        }
      </section>
    }

    @if (seccion() === 'anamnesis' && sesion.tienePermiso(PERMISOS.configuracionEscribir)) {
      <app-anamnesis-configuracion />
    }

    @if (seccion() === 'integraciones') {

    <section class="integraciones-banner" aria-label="Integraciones de la clínica">
      <div class="integraciones-banner__texto">
        <p class="ceja"><app-icono nombre="conexiones" [tamano]="16" /> CONECTIVIDAD SEGURA</p>
        <h2>Los servicios de tu clínica, en un solo lugar</h2>
        <p>Configura conexiones y credenciales por clínica cuando tengas tus cuentas de proveedor.</p>
      </div>
      <img src="/images/integraciones-clinicai-banner.png" alt="" aria-hidden="true" loading="lazy" fetchpriority="low" />
    </section>

    <section class="aviso-seguridad" aria-label="Seguridad de las credenciales">
      <span class="aviso-seguridad__icono"><app-icono nombre="conexion-segura" [tamano]="19" /></span>
      <p>
        Las claves se cifran al guardarse. Solo verás si hay una credencial registrada; su
        contenido nunca se vuelve a mostrar. Cada configuración pertenece a esta clínica.
      </p>
    </section>

    @if (aviso()) { <p class="mensaje mensaje--bien" role="status">{{ aviso() }}</p> }
    @if (error()) { <p class="mensaje mensaje--error" role="alert">{{ error() }}</p> }
    @if (cargando()) { <p class="tarjeta" role="status">Cargando configuración…</p> }

    @if (cargada()) {
    <div class="integraciones">
      <section class="tarjeta integracion">
        <header class="integracion__cabecera">
          <span class="integracion__simbolo"><app-icono nombre="ia" [tamano]="22" /></span>
          <div><p class="ceja">INTELIGENCIA ARTIFICIAL</p><h2>Anthropic</h2>
            <p>Credenciales y límites del modelo conversacional.</p></div>
        </header>
        <form (ngSubmit)="guardar('anthropic')">
          <label class="interruptor"><input type="checkbox" name="anthropic-habilitada" [(ngModel)]="anthropic.habilitada" />
            <span><strong>Integración habilitada</strong><small>Usar la cuenta de Anthropic de esta clínica.</small></span></label>
          <label class="campo"><span class="campo__etiqueta"><app-icono nombre="llave-api" [tamano]="15" /> Clave API</span>
            <input class="campo__control" type="password" name="anthropic-api-key" autocomplete="new-password" [(ngModel)]="anthropic.secretos['api_key']" placeholder="sk-ant-…" />
          </label>
          @if (anthropic.guardados['api_key']) {
            <label class="quitar-secreto"><input type="checkbox" name="anthropic-quitar-key" [(ngModel)]="anthropic.eliminar['api_key']" /> Eliminar clave guardada</label>
          }
          <div class="campos-dos">
            <label class="campo"><span class="campo__etiqueta">Modelo</span>
              <input class="campo__control" name="anthropic-modelo" [(ngModel)]="anthropic.ajustes['modelo']" maxlength="120" required />
            </label>
            <label class="campo"><span class="campo__etiqueta">Tokens máximos</span>
              <input class="campo__control" type="number" name="anthropic-tokens" [(ngModel)]="anthropic.ajustes['max_tokens']" min="64" max="32000" required />
            </label>
          </div>
          <label class="campo"><span class="campo__etiqueta">Temperatura</span>
            <input class="campo__control" type="number" name="anthropic-temperatura" [(ngModel)]="anthropic.ajustes['temperatura']" min="0" max="1" step="0.1" required />
          </label>
          <button class="boton boton--principal" type="submit" [disabled]="guardando()">Guardar Anthropic</button>
          <p class="estado-credencial">{{ estadoSecreto(anthropic, 'api_key') }}</p>
        </form>
      </section>

      <section class="tarjeta integracion">
        <header class="integracion__cabecera">
          <span class="integracion__simbolo integracion__simbolo--whatsapp"><app-icono nombre="telefono" [tamano]="22" /></span>
          <div><p class="ceja">MENSAJERÍA</p><h2>WhatsApp Cloud API</h2>
            <p>Datos del número de Meta y validación de webhooks.</p></div>
        </header>
        <form (ngSubmit)="guardar('whatsapp')">
          <label class="interruptor"><input type="checkbox" name="whatsapp-habilitada" [(ngModel)]="whatsapp.habilitada" />
            <span><strong>Integración habilitada</strong><small>Conectar el número de WhatsApp de esta clínica.</small></span></label>
          <label class="campo"><span class="campo__etiqueta">ID del número de teléfono</span>
            <input class="campo__control" name="whatsapp-numero-id" [(ngModel)]="whatsapp.ajustes['id_numero_telefono']" />
          </label>
          <label class="campo"><span class="campo__etiqueta">ID de la cuenta de negocio</span>
            <input class="campo__control" name="whatsapp-cuenta-id" [(ngModel)]="whatsapp.ajustes['id_cuenta_negocio']" />
          </label>
          <div class="campos-dos">
            <label class="campo"><span class="campo__etiqueta">Versión de API</span>
              <input class="campo__control" name="whatsapp-version" [(ngModel)]="whatsapp.ajustes['version_api']" placeholder="v21.0" />
            </label>
            <label class="interruptor interruptor--campo"><input type="checkbox" name="whatsapp-validar-firma" [(ngModel)]="whatsapp.ajustes['validar_firma']" /> Validar firma de Meta</label>
          </div>
          @for (campo of camposWhatsApp; track campo.clave) {
            <label class="campo"><span class="campo__etiqueta">{{ campo.etiqueta }}</span>
              <input class="campo__control" type="password" [name]="'whatsapp-' + campo.clave" autocomplete="new-password" [(ngModel)]="whatsapp.secretos[campo.clave]" [placeholder]="campo.placeholder" />
            </label>
            @if (whatsapp.guardados[campo.clave]) {
              <label class="quitar-secreto"><input type="checkbox" [name]="'whatsapp-quitar-' + campo.clave" [(ngModel)]="whatsapp.eliminar[campo.clave]" /> Eliminar {{ campo.etiqueta.toLowerCase() }} guardado</label>
            }
          }
          <button class="boton boton--principal" type="submit" [disabled]="guardando()">Guardar WhatsApp</button>
        </form>
      </section>

      <section class="tarjeta integracion">
        <header class="integracion__cabecera">
          <span class="integracion__simbolo integracion__simbolo--calendario"><app-icono nombre="agenda" [tamano]="22" /></span>
          <div><p class="ceja">CALENDARIOS</p><h2>Google Calendar</h2>
            <p>Credenciales OAuth para vincular calendarios profesionales.</p></div>
        </header>
        <form (ngSubmit)="guardar('google_calendar')">
          <label class="interruptor"><input type="checkbox" name="google-habilitada" [(ngModel)]="google.habilitada" />
            <span><strong>Integración habilitada</strong><small>Permitir conexiones de calendario para esta clínica.</small></span></label>
          <label class="campo"><span class="campo__etiqueta">Client ID</span>
            <input class="campo__control" name="google-client-id" [(ngModel)]="google.ajustes['client_id']" />
          </label>
          <label class="campo"><span class="campo__etiqueta">Client secret</span>
            <input class="campo__control" type="password" name="google-client-secret" autocomplete="new-password" [(ngModel)]="google.secretos['client_secret']" />
          </label>
          @if (google.guardados['client_secret']) {
            <label class="quitar-secreto"><input type="checkbox" name="google-quitar-secret" [(ngModel)]="google.eliminar['client_secret']" /> Eliminar client secret guardado</label>
          }
          <label class="campo"><span class="campo__etiqueta">URI de retorno OAuth</span>
            <input class="campo__control" name="google-redirect" [(ngModel)]="google.ajustes['redirect_uri']" placeholder="https://…" />
          </label>
          <label class="campo"><span class="campo__etiqueta">Permisos OAuth</span>
            <input class="campo__control" name="google-scopes" [(ngModel)]="google.ajustes['scopes']" />
          </label>
          <button class="boton boton--principal" type="submit" [disabled]="guardando()">Guardar Google Calendar</button>
          <p class="estado-credencial">{{ estadoSecreto(google, 'client_secret') }}</p>
        </form>
      </section>

      <section class="tarjeta integracion">
        <header class="integracion__cabecera">
          <span class="integracion__simbolo integracion__simbolo--correo"><app-icono nombre="correo" [tamano]="22" /></span>
          <div><p class="ceja">CORREO ELECTRÓNICO</p><h2>Servidor SMTP</h2>
            <p>Cuenta para enviar mensajes operativos de la clínica.</p></div>
        </header>
        <form (ngSubmit)="guardar('smtp')">
          <label class="interruptor"><input type="checkbox" name="smtp-habilitada" [(ngModel)]="smtp.habilitada" />
            <span><strong>Integración habilitada</strong><small>Enviar correo con el servidor configurado.</small></span></label>
          <div class="campos-dos">
            <label class="campo"><span class="campo__etiqueta">Servidor</span>
              <input class="campo__control" name="smtp-host" [(ngModel)]="smtp.ajustes['host']" />
            </label>
            <label class="campo"><span class="campo__etiqueta">Puerto</span>
              <input class="campo__control" type="number" name="smtp-puerto" [(ngModel)]="smtp.ajustes['puerto']" min="1" max="65535" />
            </label>
          </div>
          <label class="campo"><span class="campo__etiqueta">Usuario</span>
            <input class="campo__control" name="smtp-usuario" [(ngModel)]="smtp.ajustes['usuario']" autocomplete="username" />
          </label>
          <label class="campo"><span class="campo__etiqueta">Contraseña SMTP</span>
            <input class="campo__control" type="password" name="smtp-contrasena" [(ngModel)]="smtp.secretos['contrasena']" autocomplete="new-password" />
          </label>
          @if (smtp.guardados['contrasena']) {
            <label class="quitar-secreto"><input type="checkbox" name="smtp-quitar-password" [(ngModel)]="smtp.eliminar['contrasena']" /> Eliminar contraseña guardada</label>
          }
          <div class="campos-dos">
            <label class="campo"><span class="campo__etiqueta">Correo remitente</span>
              <input class="campo__control" type="email" name="smtp-remitente" [(ngModel)]="smtp.ajustes['correo_remitente']" />
            </label>
            <label class="campo"><span class="campo__etiqueta">Nombre remitente</span>
              <input class="campo__control" name="smtp-nombre" [(ngModel)]="smtp.ajustes['nombre_remitente']" />
            </label>
          </div>
          <label class="interruptor interruptor--campo"><input type="checkbox" name="smtp-tls" [(ngModel)]="smtp.ajustes['tls']" /> Usar conexión TLS</label>
          <button class="boton boton--principal" type="submit" [disabled]="guardando()">Guardar SMTP</button>
          <p class="estado-credencial">{{ estadoSecreto(smtp, 'contrasena') }}</p>
        </form>
      </section>
    </div>
    <app-integraciones-ia />
    }

    }

    @if (seccion() === 'agenda' && sesion.tienePermiso(PERMISOS.agendaConfigurar)) {
      <app-agenda-configuracion />
    }
    @if (seccion() === 'sedes' && sesion.tienePermiso(PERMISOS.sedeGestionar)) {
      <app-sedes-configuracion />
    }
    @if (seccion() === 'equipo' && sesion.tieneAlgunPermiso(PERMISOS.agendaConfigurar, PERMISOS.profesionalGestionar)) {
      <app-agenda-profesionales />
    }
    @if (seccion() === 'bloqueos' && sesion.tienePermiso(PERMISOS.bloqueoGestionar)) {
      <app-bloqueos-agenda />
    }

    <p class="nota-configuracion">
      Los parámetros se guardan cifrados para la clínica de la sesión. El acceso a esta pantalla
      requiere el permiso «configuracion.escribir» y las modificaciones quedan auditadas. La
      aplicación efectiva de cada proveedor requiere que su adaptador del servidor consuma esta
      configuración por clínica.
    </p>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    .pagina-cabecera { display:flex; align-items:center; justify-content:space-between; gap:var(--espacio-4); margin-bottom:var(--espacio-4); }
    .pestanas { display:flex; gap:var(--espacio-2); align-items:center; margin-bottom:var(--espacio-4); border-bottom:1px solid var(--borde); }
    .pestanas button,.pestanas a { display:inline-flex; align-items:center; min-height:44px; padding:0 var(--espacio-3); border:0; border-bottom:2px solid transparent; background:transparent; color:var(--texto-suave); font:inherit; font-weight:650; text-decoration:none; cursor:pointer; }
    .pestanas .pestanas__activa { color:var(--acento-fuerte); border-bottom-color:var(--acento); }
    .ficha-clinica { padding:var(--espacio-5); }
    .ficha-clinica__intro h2 { margin:0; }
    .ficha-clinica__intro p:last-child { color:var(--texto-suave); }
    .form-clinica { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:var(--espacio-4); }
    .form-clinica .campo { margin:0; }
    .form-clinica .boton,.form-clinica .campo__ayuda { grid-column:1/-1; justify-self:start; }
    .pagina-cabecera h1 { margin:0; }
    .pagina-cabecera p:last-child { margin:var(--espacio-2) 0 0; color:var(--texto-suave); }
    .integraciones-banner { position:relative; display:flex; align-items:center; min-height:190px; overflow:hidden; padding:var(--espacio-5); margin-bottom:var(--espacio-4); border:1px solid #193c49; border-radius:calc(var(--radio) + 4px); background:linear-gradient(105deg,#071c2b 0%,#0b2b39 62%,#123b43 100%); isolation:isolate; color:#fff; }
    .integraciones-banner::after { content:''; position:absolute; z-index:-1; inset:-45%; background:radial-gradient(ellipse at 78% 48%,rgb(95 209 196 / 24%),transparent 34%); animation:ambiente-integraciones 18s ease-in-out infinite alternate; }
    .integraciones-banner__texto { position:relative; z-index:1; max-width:510px; }
    .integraciones-banner__texto .ceja { display:flex; align-items:center; gap:7px; margin:0 0 var(--espacio-2); color:#a8f3e5; }
    .integraciones-banner__texto h2 { margin:0 0 var(--espacio-2); color:#fff; font-size:clamp(1.2rem,2vw,1.6rem); }
    .integraciones-banner__texto p:last-child { max-width:440px; margin:0; color:#d0e4e7; }
    .integraciones-banner img { position:absolute; z-index:0; top:0; right:0; width:min(70%,900px); height:100%; object-fit:cover; object-position:center 54%; mask-image:linear-gradient(90deg,transparent 0%,#000 20%); transform-origin:center; animation:integraciones-ilustracion 24s ease-in-out infinite alternate; }
    @keyframes ambiente-integraciones { from { transform:translate3d(-2%,1%,0) scale(.96); opacity:.55; } to { transform:translate3d(2%,-1%,0) scale(1.06); opacity:1; } }
    @keyframes integraciones-ilustracion { from { transform:translate3d(0,2px,0) scale(1); } to { transform:translate3d(0,-3px,0) scale(1.018); } }
    .aviso-seguridad { display:flex; align-items:flex-start; gap:var(--espacio-3); padding:var(--espacio-3) var(--espacio-4); margin-bottom:var(--espacio-4); border:1px solid var(--borde); border-radius:var(--radio); background:var(--acento-suave); color:var(--texto); }
    .aviso-seguridad p { margin:0; }
    .aviso-seguridad__icono { display:grid; place-items:center; color:var(--acento); }
    .integraciones { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:var(--espacio-4); align-items:start; }
    .integracion { min-width:0; padding:var(--espacio-5); }
    .integracion__cabecera { display:flex; align-items:center; gap:var(--espacio-3); padding-bottom:var(--espacio-4); margin-bottom:var(--espacio-4); border-bottom:1px solid var(--borde); }
    .integracion__cabecera h2 { margin:0; font-size:1.15rem; }
    .integracion__cabecera p:last-child { margin:var(--espacio-1) 0 0; color:var(--texto-suave); font-size:.88rem; }
    .integracion__cabecera .ceja { margin:0 0 2px; font-size:.65rem; }
    .integracion__simbolo { display:grid; flex:0 0 44px; width:44px; height:44px; place-items:center; border-radius:13px; background:var(--acento-suave); color:var(--acento-fuerte); }
    .integracion__simbolo--whatsapp { background:#e3f2ea; color:#1c6b45; }
    .integracion__simbolo--calendario { background:#e7effa; color:#1e5081; }
    .integracion__simbolo--correo { background:#fdf3e0; color:#8a5800; }
    .integracion form { display:grid; gap:var(--espacio-3); }
    .integracion .campo { margin:0; }
    .integracion .campo__etiqueta:has(app-icono) { display:flex; align-items:center; gap:6px; }
    .interruptor { display:flex; align-items:center; gap:var(--espacio-3); min-height:48px; padding:var(--espacio-2) 0; cursor:pointer; }
    .interruptor > span { display:grid; gap:2px; }
    .interruptor small { color:var(--texto-suave); }
    .interruptor--campo { margin:0; }
    .campos-dos { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:var(--espacio-3); }
    .quitar-secreto { display:flex; align-items:center; gap:var(--espacio-2); color:var(--peligro); font-size:.86rem; cursor:pointer; }
    .estado-credencial { margin:0; color:var(--texto-tenue); font-size:.82rem; }
    .nota-configuracion { margin:var(--espacio-4) 0 0; color:var(--texto-tenue); font-size:.85rem; }
    .mensaje { padding:var(--espacio-3) var(--espacio-4); border-radius:var(--radio); }
    .mensaje--bien { color:var(--exito); background:var(--exito-fondo); }
    .mensaje--error { color:var(--peligro); background:var(--peligro-fondo); }
    @media (max-width:900px) { .integraciones { grid-template-columns:1fr; } }
    @media (max-width:560px) { .pagina-cabecera { align-items:flex-start; } .campos-dos,.form-clinica { grid-template-columns:1fr; } .integracion { padding:var(--espacio-4); } .pestanas { overflow:auto; } .integraciones-banner { min-height:210px; align-items:flex-start; padding:var(--espacio-4); } .integraciones-banner__texto { max-width:78%; } .integraciones-banner img { width:80%; opacity:.72; mask-image:linear-gradient(90deg,transparent 0%,#000 38%); } }
    @media (prefers-reduced-motion: reduce) { .integraciones-banner::after,.integraciones-banner img { animation:none; } }
  `,
})
export class ConfiguracionComponent implements OnInit {
  private readonly servicio = inject(IntegracionesService);
  private readonly catalogo = inject(CatalogoService);
  protected readonly sesion = inject(SesionService);
  protected readonly PERMISOS = PERMISOS;
  protected readonly cargando = signal(false);
  protected readonly cargada = signal(false);
  protected readonly guardando = signal(false);
  protected readonly error = signal('');
  protected readonly aviso = signal('');
  protected readonly seccion = signal<'clinica' | 'sedes' | 'integraciones' | 'agenda' | 'equipo' | 'bloqueos' | 'anamnesis'>('clinica');
  protected readonly clinica = signal<DatosClinica | null>(null);
  protected readonly cargandoClinica = signal(false);
  protected readonly guardandoClinica = signal(false);
  protected readonly errorClinica = signal('');
  protected readonly avisoClinica = signal('');
  private readonly estados = signal(new Map<string, EstadoIntegracion>());

  protected readonly camposWhatsApp = [
    { clave: 'token_acceso', etiqueta: 'Token de acceso', placeholder: 'Token permanente de Meta' },
    { clave: 'token_verificacion', etiqueta: 'Token de verificación', placeholder: 'Token del webhook' },
    { clave: 'secreto_app', etiqueta: 'Secreto de la app', placeholder: 'App secret de Meta' },
  ];

  protected readonly anthropic: FormularioIntegracion = formularioVacio(
    { modelo: 'claude-sonnet-5', max_tokens: 2048, temperatura: 0.2 },
    ['api_key'],
  );
  protected readonly whatsapp: FormularioIntegracion = formularioVacio(
    { id_numero_telefono: '', id_cuenta_negocio: '', version_api: 'v21.0', validar_firma: true },
    ['token_acceso', 'token_verificacion', 'secreto_app'],
  );
  protected readonly google: FormularioIntegracion = formularioVacio(
    { client_id: '', redirect_uri: '', scopes: 'https://www.googleapis.com/auth/calendar.events' },
    ['client_secret'],
  );
  protected readonly smtp: FormularioIntegracion = formularioVacio(
    { host: '', puerto: 587, usuario: '', tls: true, correo_remitente: '', nombre_remitente: '' },
    ['contrasena'],
  );

  ngOnInit(): void { this.cargar(); this.cargarClinica(); }

  private cargarClinica(): void {
    this.cargandoClinica.set(true);
    this.servicio.clinica().subscribe({
      next: (datos) => { this.clinica.set(datos); this.cargandoClinica.set(false); },
      error: (fallo: unknown) => { this.errorClinica.set(fallo instanceof FalloApi ? fallo.message : 'No se pudo cargar la clínica.'); this.cargandoClinica.set(false); },
    });
  }

  protected guardarClinica(): void {
    const datos = this.clinica();
    if (!datos) return;
    const { id, ...cambios } = datos;
    if (!id) return;
    this.guardandoClinica.set(true);
    this.errorClinica.set('');
    this.avisoClinica.set('');
    this.servicio.guardarClinica(cambios).subscribe({
      next: (actualizada) => { this.clinica.set(actualizada); this.catalogo.limpiar(); this.avisoClinica.set('Información de la clínica actualizada.'); this.guardandoClinica.set(false); },
      error: (fallo: unknown) => { this.errorClinica.set(fallo instanceof FalloApi ? fallo.message : 'No se pudo guardar la clínica.'); this.guardandoClinica.set(false); },
    });
  }

  protected cargar(): void {
    this.cargando.set(true);
    this.error.set('');
    this.servicio.listar().subscribe({
      next: (integraciones) => {
        const estados = new Map(integraciones.map((integracion) => [integracion.codigo, integracion]));
        this.estados.set(estados);
        this.hidratar('anthropic', this.anthropic);
        this.hidratar('whatsapp', this.whatsapp);
        this.hidratar('google_calendar', this.google);
        this.hidratar('smtp', this.smtp);
        this.cargada.set(true);
        this.cargando.set(false);
      },
      error: (fallo: unknown) => {
        this.error.set(fallo instanceof FalloApi ? fallo.message : 'No se pudo cargar la configuración.');
        this.cargando.set(false);
      },
    });
  }

  protected guardar(codigo: 'anthropic' | 'whatsapp' | 'google_calendar' | 'smtp'): void {
    const formulario = this.formulario(codigo);
    const secretos = Object.fromEntries(
      Object.entries(formulario.secretos).filter(([, valor]) => valor.trim().length > 0),
    );
    const eliminar_secretos = Object.entries(formulario.eliminar)
      .filter(([campo, eliminar]) => eliminar && !formulario.secretos[campo]?.trim())
      .map(([campo]) => campo);
    const datos: ActualizacionIntegracion = {
      habilitada: formulario.habilitada,
      ajustes: formulario.ajustes,
      secretos,
      eliminar_secretos,
    };
    this.guardando.set(true);
    this.error.set('');
    this.aviso.set('');
    this.servicio.guardar(codigo, datos).subscribe({
      next: (estado) => {
        this.estados.update((actuales) => new Map(actuales).set(codigo, estado));
        this.hidratar(codigo, formulario);
        for (const clave of Object.keys(formulario.secretos)) formulario.secretos[clave] = '';
        for (const clave of Object.keys(formulario.eliminar)) formulario.eliminar[clave] = false;
        this.aviso.set('Configuración guardada. Las credenciales quedaron cifradas en el servidor.');
        this.guardando.set(false);
      },
      error: (fallo: unknown) => {
        this.error.set(fallo instanceof FalloApi ? fallo.message : 'No se pudo guardar la configuración.');
        this.guardando.set(false);
      },
    });
  }

  protected estadoSecreto(formulario: FormularioIntegracion, campo: string): string {
    return formulario.guardados[campo] ? 'Hay una credencial cifrada guardada.' : 'No hay credencial guardada.';
  }

  private formulario(codigo: string): FormularioIntegracion {
    if (codigo === 'anthropic') return this.anthropic;
    if (codigo === 'whatsapp') return this.whatsapp;
    if (codigo === 'google_calendar') return this.google;
    return this.smtp;
  }

  private hidratar(codigo: string, formulario: FormularioIntegracion): void {
    const estado = this.estados().get(codigo);
    if (!estado) return;
    formulario.habilitada = estado.habilitada;
    Object.assign(formulario.ajustes, estado.ajustes);
    for (const campo of Object.keys(formulario.guardados)) {
      formulario.guardados[campo] = estado.secretos[campo]?.configurado ?? false;
    }
  }
}
