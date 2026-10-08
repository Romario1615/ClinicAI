import { Component, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { DatePipe, registerLocaleData } from '@angular/common';
import localeEs from '@angular/common/locales/es';

import {
  ApiService,
  type AvisoRevisionTratamiento,
  type ConversacionEntrante,
  type DetalleConversacionEntrante,
} from '../../nucleo/servicios/api.service';
import { IconoComponent } from '../../compartido/icono.component';
import { PERMISOS } from '../../nucleo/servicios/configuracion';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { PendientesService } from '../../nucleo/servicios/pendientes.service';

registerLocaleData(localeEs);

import { ResumenModuloComponent } from '../../compartido/resumen-modulo.component';
@Component({
  selector: 'app-conversaciones',
  standalone: true,
  imports: [ResumenModuloComponent, DatePipe, IconoComponent],
  host: { class: 'pantalla' },
  template: `
    <header class="bandeja__cabecera pantalla__fijo">
      <div>
        <p class="sobrelinea"><app-icono nombre="mensajes-seguros" [tamano]="15" /> COMUNICACIÓN SEGURA</p>
        <h1>Atención de mensajes</h1>
        <p>Conversaciones derivadas que esperan seguimiento del equipo.</p>
      </div>
      <button class="boton boton--secundario" type="button" (click)="cargar()" [disabled]="cargando()">
        <app-icono nombre="reloj" [tamano]="17" /> Actualizar
      </button>
    </header>

    <app-resumen-modulo class="pantalla__fijo" modulo="mensajes" />

    @if (error()) { <div class="aviso aviso--error pantalla__fijo" role="alert">{{ error() }}</div> }

    <div class="bandeja__cuerpo pantalla__columnas">
      <div class="bandeja__columna">
        @if (avisosTratamiento().length > 0 || cargandoAvisos() || errorAvisos()) {
          <section class="avisos-tratamiento tarjeta desplazable" tabindex="0" aria-labelledby="avisos-tratamiento-titulo">
            <header><div><p class="sobrelinea">SEGUIMIENTO CLÍNICO</p><h2 id="avisos-tratamiento-titulo">Reportes de tratamiento por revisar</h2></div><span>{{ avisosTratamiento().length }}</span></header>
            @if (errorAvisos()) { <p class="aviso aviso--error" role="alert">{{ errorAvisos() }}</p> }
            @if (cargandoAvisos() && !avisosTratamiento().length) { <p class="vacio">Cargando reportes…</p> }
            @for (aviso of avisosTratamiento(); track aviso.id) {
              <article class="aviso-tratamiento">
                <div><strong>Requiere revisión del equipo</strong><time>{{ aviso.creado_en | date:'d MMM yyyy, HH:mm':'':'es' }}</time><p>Abra el mensaje antes de confirmar su revisión. El aviso no representa una clasificación de gravedad.</p></div>
                <div class="aviso-tratamiento__acciones">
                  <button class="boton boton--pequeno" type="button" (click)="abrirAviso(aviso)">Abrir mensaje</button>
                  @if (puedeConfirmarRevision()) {
                    <button class="boton boton--pequeno boton--principal" type="button" [disabled]="revisandoAviso() === aviso.id" (click)="confirmarRevision(aviso)">
                      {{ revisandoAviso() === aviso.id ? 'Guardando…' : 'Confirmar revisión' }}
                    </button>
                  }
                </div>
              </article>
            }
            @if (!cargandoAvisos() && !avisosTratamiento().length && !errorAvisos()) { <p class="vacio">No hay reportes pendientes.</p> }
          </section>
        }
      <section class="bandeja__lista tarjeta" aria-label="Conversaciones pendientes">
        <div class="lista__cabecera"><h2>Pendientes</h2><span>{{ conversaciones().length }}</span></div>
        <div class="lista__cuerpo desplazable" tabindex="0" role="region" aria-label="Lista de conversaciones">
        @if (cargando() && !conversaciones().length) { <p class="vacio">Cargando conversaciones…</p> }
        @else if (!conversaciones().length) {
          <div class="vacio vacio--sin-mensajes">
            <img class="vacio__ilustracion" src="/images/bandeja-sin-pendientes.png" alt="" aria-hidden="true" width="144" height="144" />
            <strong>Todo al día</strong>
            <span>No hay mensajes pendientes de atención.</span>
          </div>
        }
        @for (conversacion of conversaciones(); track conversacion.id) {
          <button class="conversacion" [class.conversacion--activa]="seleccionada()?.id === conversacion.id" type="button" (click)="abrir(conversacion)">
            <span class="conversacion__telefono">{{ conversacion.telefono }}</span>
            <span class="conversacion__motivo">{{ conversacion.motivo_handoff || 'Requiere revisión del equipo' }}</span>
            <span class="conversacion__resumen">{{ conversacion.ultimo_mensaje || 'Mensaje sin texto' }}</span>
            <time>{{ conversacion.ultima_actividad_en | date:'d MMM, HH:mm':'':'es' }}</time>
          </button>
        }
        @if (conversaciones().length < total()) {
          <button class="cargar-mas" type="button" (click)="cargarMas()" [disabled]="cargando()">Cargar más conversaciones</button>
        }
        </div>
      </section>
      </div>

      <section class="bandeja__detalle tarjeta" aria-label="Detalle de conversación" aria-live="polite">
        @if (detalle(); as hilo) {
          <header class="detalle__cabecera">
            <div><span class="sobrelinea">WHATSAPP · EN ESPERA</span><h2>{{ hilo.telefono }}</h2></div>
            <span class="estado">Requiere atención</span>
          </header>
          <p class="detalle__motivo">{{ hilo.motivo_handoff }}</p>
          @if (hilo.paciente_id) { <p class="detalle__paciente">Paciente vinculado: {{ hilo.paciente_id }}</p> }
          <div class="mensajes desplazable" tabindex="0" role="region" aria-label="Mensajes de la conversación">
            @for (mensaje of hilo.mensajes; track mensaje.id) {
              <article class="mensaje">
                <p>{{ mensaje.texto || 'Mensaje de tipo ' + mensaje.tipo }}</p>
                <footer><span>{{ mensaje.intencion }}</span><time>{{ mensaje.recibido_en | date:'d MMM yyyy, HH:mm':'':'es' }}</time></footer>
              </article>
            }
          </div>
          <p class="solo-lectura">La lectura queda registrada en la auditoría clínica. La respuesta por WhatsApp se habilitará cuando se configure el proveedor.</p>
        } @else {
          <div class="vacio"><app-icono nombre="agente" [tamano]="24" /><strong>Selecciona una conversación</strong><span>El detalle se carga de forma protegida y cada consulta queda auditada.</span></div>
        }
      </section>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: [`
    :host{color:var(--texto)}
    .bandeja__cabecera{display:flex;align-items:center;justify-content:space-between;gap:20px}
    .bandeja__cabecera h1{margin:4px 0 8px;font-size:clamp(1.7rem,3vw,2.35rem)}
    .bandeja__cabecera p{margin:0;color:var(--texto-suave)}
    .sobrelinea{display:flex;align-items:center;gap:6px;font-size:.72rem;font-weight:750;letter-spacing:.1em;color:var(--acento-fuerte)}
    .bandeja__cuerpo{display:grid;grid-template-columns:minmax(280px,.8fr) minmax(0,1.5fr);gap:20px;min-height:540px}
    .tarjeta{border:1px solid var(--borde);border-radius:var(--radio);background:var(--superficie-elevada);overflow:hidden}
    .lista__cabecera,.detalle__cabecera{display:flex;justify-content:space-between;align-items:center;padding:18px 20px;border-bottom:1px solid var(--borde)}
    .lista__cabecera h2,.detalle__cabecera h2{font-size:1rem;margin:0}.lista__cabecera span{background:var(--superficie-hundida);padding:3px 9px;border-radius:20px;font-weight:700}
    .conversacion{display:grid;width:100%;gap:6px;text-align:left;padding:16px 20px;background:transparent;border:0;border-bottom:1px solid var(--borde);color:inherit;cursor:pointer}
    .conversacion:hover,.conversacion--activa{background:var(--superficie-hundida)}
    .cargar-mas{width:100%;padding:14px;border:0;background:transparent;color:var(--acento-fuerte);font:inherit;font-weight:700;cursor:pointer}.cargar-mas:disabled{opacity:.55;cursor:wait}
    .conversacion__telefono{font-weight:750}.conversacion__motivo{font-size:.82rem;color:var(--aviso)}.conversacion__resumen{font-size:.88rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--texto-suave)}
    .conversacion time,.mensaje time{font-size:.76rem;color:var(--texto-tenue)}
    .detalle__cabecera{align-items:center}.detalle__cabecera h2{font-size:1.3rem;margin-top:5px}.estado{padding:6px 10px;border-radius:20px;background:var(--superficie-hundida);font-size:.8rem;font-weight:700}
    .detalle__motivo,.detalle__paciente{margin:16px 22px 0;color:var(--texto-suave)}.mensajes{display:grid;align-content:start;gap:12px;padding:22px;min-height:260px}
    .mensaje{max-width:90%;padding:14px 16px;border-radius:14px 14px 14px 4px;background:var(--superficie-hundida)}.mensaje p{margin:0 0 10px;white-space:pre-wrap;overflow-wrap:anywhere}.mensaje footer{display:flex;justify-content:space-between;gap:14px}.mensaje footer span{font-size:.75rem;color:var(--texto-suave)}
    .solo-lectura{margin:0 22px 20px;padding:12px 14px;border-left:3px solid var(--acento);background:var(--superficie-hundida);font-size:.84rem;color:var(--texto-suave)}
    .vacio{display:flex;min-height:180px;flex-direction:column;align-items:center;justify-content:center;gap:10px;padding:24px;text-align:center;color:var(--texto-suave)}.vacio strong{color:var(--texto)}
    .vacio--sin-mensajes{min-height:340px;gap:8px}.vacio__ilustracion{display:block;width:144px;height:144px;object-fit:contain;animation:ilustracion-bandeja-flotar 8s ease-in-out infinite;filter:drop-shadow(0 12px 20px rgb(16 42 46 / 9%))}.vacio--sin-mensajes strong{font-size:1.05rem}.vacio--sin-mensajes span{max-width:220px}
    @keyframes ilustracion-bandeja-flotar{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}
    .aviso{margin-bottom:18px;padding:12px 16px;border-radius:10px}.aviso--error{color:var(--error);background:var(--superficie-hundida)}
    .avisos-tratamiento{margin-bottom:20px;padding:18px 20px;border-color:color-mix(in srgb,var(--aviso) 35%,var(--borde))}.avisos-tratamiento>header{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:12px}.avisos-tratamiento h2{margin:2px 0 0;font-size:1.08rem}.avisos-tratamiento>header>span{min-width:30px;padding:4px 9px;border-radius:20px;background:var(--aviso-fondo);color:var(--aviso);font-weight:800;text-align:center}.aviso-tratamiento{display:flex;justify-content:space-between;align-items:center;gap:18px;padding:14px 0;border-top:1px solid var(--borde)}.aviso-tratamiento>div:first-child{display:grid;gap:4px}.aviso-tratamiento time{font-size:.78rem;color:var(--texto-tenue)}.aviso-tratamiento p{margin:2px 0 0;color:var(--texto-suave);font-size:.86rem}.aviso-tratamiento__acciones{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px}
    @media(max-width:800px){.bandeja__cuerpo{grid-template-columns:1fr}.bandeja__lista{max-height:360px;overflow:auto}.bandeja__cabecera{align-items:flex-start;flex-direction:column}}
    @media(prefers-reduced-motion:reduce){.vacio__ilustracion{animation:none}}
    /* Pantalla de trabajo: avisos y pendientes en una columna, el hilo en la
       otra; cada lista desplaza dentro de su tarjeta. */
    .bandeja__columna{display:flex;flex-direction:column;gap:var(--espacio-3);min-width:0;min-height:0}
    .bandeja__lista,.bandeja__detalle{display:flex;flex-direction:column;min-height:0}
    .avisos-tratamiento{margin-bottom:0}
    @media (min-width:821px) and (min-height:600px){
      .bandeja__cuerpo{--pantalla-columnas:minmax(280px,.8fr) minmax(0,1.5fr);min-height:0;gap:var(--espacio-3)}
      .bandeja__cabecera h1{margin:2px 0 4px;font-size:1.45rem}
      /* La tarjeta recorta su contenido; esta tiene que desplazarlo. */
      .avisos-tratamiento{flex:0 1 auto;max-height:42%;overflow:auto}
      .bandeja__lista{flex:1 1 0}
      .bandeja__lista .lista__cabecera,.detalle__cabecera,.detalle__motivo,.detalle__paciente,.solo-lectura{flex:none}
      .mensajes{min-height:0}
      .vacio--sin-mensajes{min-height:0}
    }
  `],
})
export class ConversacionesComponent {
  private readonly api = inject(ApiService);
  private readonly sesion = inject(SesionService);
  private readonly pendientes = inject(PendientesService);
  protected readonly conversaciones = signal<readonly ConversacionEntrante[]>([]);
  protected readonly avisosTratamiento = signal<readonly AvisoRevisionTratamiento[]>([]);
  protected readonly total = signal(0);
  protected readonly seleccionada = signal<ConversacionEntrante | null>(null);
  protected readonly detalle = signal<DetalleConversacionEntrante | null>(null);
  protected readonly cargando = signal(false);
  protected readonly error = signal('');
  protected readonly errorAvisos = signal('');
  protected readonly cargandoAvisos = signal(false);
  protected readonly revisandoAviso = signal<string | null>(null);
  protected readonly puedeConfirmarRevision = computed(() =>
    this.sesion.tienePermiso(PERMISOS.alertaAdherenciaAtender),
  );

  constructor() { this.cargar(); }

  protected cargar(): void {
    this.cargando.set(true);
    this.error.set('');
    this.cargarAvisos();
    this.api.conversacionesPendientes().subscribe({
      next: (pagina) => {
        const filas = pagina.elementos;
        this.conversaciones.set(filas);
        this.total.set(pagina.total);
        this.cargando.set(false);
        const actual = this.seleccionada();
        const siguiente = filas.find((hilo) => hilo.id === actual?.id) ?? filas[0] ?? null;
        if (siguiente) this.abrir(siguiente);
        else { this.seleccionada.set(null); this.detalle.set(null); }
      },
      error: (fallo: Error) => { this.error.set(fallo.message); this.cargando.set(false); },
    });
  }

  protected cargarAvisos(): void {
    this.cargandoAvisos.set(true);
    this.errorAvisos.set('');
    this.api.avisosTratamientoPendientes().subscribe({
      next: (avisos) => { this.avisosTratamiento.set(avisos); this.cargandoAvisos.set(false); },
      error: (fallo: Error) => { this.errorAvisos.set(fallo.message); this.cargandoAvisos.set(false); },
    });
  }

  protected abrirAviso(aviso: AvisoRevisionTratamiento): void {
    this.api.conversacion(aviso.conversacion_id).subscribe({
      next: (detalle) => {
        const hilo: ConversacionEntrante = {
          id: detalle.id,
          telefono: detalle.telefono,
          paciente_id: detalle.paciente_id,
          estado: detalle.estado,
          motivo_handoff: detalle.motivo_handoff,
          ultima_actividad_en: detalle.ultima_actividad_en,
          ultimo_mensaje: detalle.ultimo_mensaje,
        };
        this.seleccionada.set(hilo);
        this.detalle.set(detalle);
      },
      error: (fallo: Error) => this.error.set(fallo.message),
    });
  }

  protected confirmarRevision(aviso: AvisoRevisionTratamiento): void {
    this.revisandoAviso.set(aviso.id);
    this.errorAvisos.set('');
    this.api.confirmarRevisionAvisoTratamiento(aviso.id).subscribe({
      next: () => {
        this.avisosTratamiento.update((lista) => lista.filter((actual) => actual.id !== aviso.id));
        this.revisandoAviso.set(null);
        this.pendientes.cargar();
      },
      error: (fallo: Error) => {
        this.errorAvisos.set(fallo.message);
        this.revisandoAviso.set(null);
      },
    });
  }

  protected cargarMas(): void {
    if (this.cargando()) return;
    this.cargando.set(true);
    const actual = this.conversaciones();
    this.api.conversacionesPendientes(50, actual.length).subscribe({
      next: (pagina) => {
        this.conversaciones.update((filas) => [...filas, ...pagina.elementos]);
        this.total.set(pagina.total);
        this.cargando.set(false);
      },
      error: (fallo: Error) => { this.error.set(fallo.message); this.cargando.set(false); },
    });
  }

  protected abrir(hilo: ConversacionEntrante): void {
    this.seleccionada.set(hilo);
    this.detalle.set(null);
    this.api.conversacion(hilo.id).subscribe({
      next: (detalle) => this.detalle.set(detalle),
      error: (fallo: Error) => this.error.set(fallo.message),
    });
  }
}
