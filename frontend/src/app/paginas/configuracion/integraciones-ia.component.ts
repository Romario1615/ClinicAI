/**
 * JEV (TypeSafe) y el LLM que redacta las respuestas del asistente.
 *
 * JEV decide qué quiere el paciente (opciones cerradas con probabilidad) y si
 * su mensaje es clínico o urgente; con poca confianza el asistente pregunta en
 * lugar de adivinar. El LLM elegido redacta, solo con documentos publicados.
 * Las claves se guardan cifradas y nunca se vuelven a mostrar.
 */
import { Component, OnInit, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';

import { CONFIGURACION } from '../../nucleo/servicios/configuracion';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';

interface Integracion {
  readonly codigo: string;
  readonly habilitada: boolean;
  readonly ajustes: Record<string, string | number | boolean>;
  readonly secretos: Record<string, { configurado: boolean }>;
}

export interface PruebaJev {
  readonly respondio: boolean;
  readonly mensaje: string;
  readonly intencion: string;
  readonly confianza: number;
  readonly pregunta_clinica: number;
  readonly urgencia: number;
  readonly milisegundos: number;
}

const INTENCIONES: Record<string, string> = {
  buscar_horarios: 'reservar una cita',
  consultar_citas: 'consultar sus citas',
  cancelar: 'cancelar',
  reprogramar: 'cambiar una cita',
  informacion: 'pedir información',
  seguimiento_tratamiento: 'saber de su tratamiento',
  baja_promociones: 'darse de baja',
  hablar_con_persona: 'hablar con una persona',
  otro: 'otra cosa',
};

@Component({
  selector: 'app-integraciones-ia',
  standalone: true,
  imports: [FormsModule, VentanaFlotanteComponent],
  template: `
    <div class="ia">
      @if (aviso()) { <p class="ia__aviso" role="status">{{ aviso() }}</p> }
      @if (error()) { <p class="campo__error ia__error" role="alert">{{ error() }}</p> }

      <section class="tarjeta ia__tarjeta" aria-labelledby="titulo-jev">
        <p class="ceja">DECISIONES DEL ASISTENTE</p>
        <h2 id="titulo-jev">JEV · TypeSafe</h2>
        <p class="ia__ayuda">
          Decide qué quiere el paciente y si su mensaje es clínico o urgente, con probabilidad. No genera texto ni
          ejecuta nada: elige entre opciones cerradas. Se envía solo el texto del mensaje, sin nombre ni teléfono.
        </p>
        <div class="ia__estado" role="status">
          <span class="ia__punto" [class.ia__punto--activo]="jev.habilitada" aria-hidden="true"></span>
          <strong>{{ jev.habilitada ? 'JEV está habilitado' : 'Se usan las reglas locales' }}</strong>
        </div>
        <dl class="ia__detalles">
          <div><dt>Modelo</dt><dd>{{ jev.modelo }}</dd></div>
          <div><dt>Clave API</dt><dd>{{ jev.guardada ? 'Configurada y protegida' : 'Sin configurar' }}</dd></div>
          <div><dt>Confianza mínima</dt><dd>{{ porcentaje(jev.umbral) }}</dd></div>
        </dl>
        <p class="ia__ayuda">Con confianza baja, el asistente pide una aclaración en vez de adivinar.</p>
        <div class="ia__acciones">
          <button class="boton boton--principal" type="button" (click)="abrirEditor('jev')">Configurar JEV</button>
          <button class="boton" type="button" [disabled]="ocupado() || !jev.guardada" (click)="probar()">{{ ocupado() ? 'Probando…' : 'Probar conexión' }}</button>
        </div>
        @if (prueba(); as p) {
          <div class="ia__prueba" [class.ia__prueba--mal]="!p.respondio" role="status">
            <strong>{{ p.mensaje }}</strong>
            <span>Mensaje de prueba: «quiero reservar una cita…» → {{ intencion(p.intencion) }} ({{ porcentaje(p.confianza) }} de confianza) · clínico {{ porcentaje(p.pregunta_clinica) }} · urgente {{ porcentaje(p.urgencia) }} · {{ p.milisegundos }} ms</span>
          </div>
        }
      </section>

      <section class="tarjeta ia__tarjeta" aria-labelledby="titulo-respuestas">
        <p class="ceja">REDACCIÓN DE RESPUESTAS</p>
        <h2 id="titulo-respuestas">Respuestas del asistente</h2>
        <p class="ia__ayuda">
          Quién redacta cuando JEV delega una pregunta. Responde solo con documentos publicados de Conocimiento; sin
          LLM, cita el documento tal cual. Nunca diagnostica ni envía datos clínicos por WhatsApp.
        </p>
        <div class="ia__estado" role="status">
          <span class="ia__punto" [class.ia__punto--activo]="respuestas.habilitada" aria-hidden="true"></span>
          <strong>{{ respuestas.habilitada ? 'Respuestas automáticas habilitadas' : 'Respuestas automáticas pausadas' }}</strong>
        </div>
        <dl class="ia__detalles">
          <div><dt>Proveedor</dt><dd>{{ nombreProveedor() }}</dd></div>
          @if (respuestas.proveedor === 'ollama') {
            <div><dt>Modelo local</dt><dd>{{ respuestas.modelo || 'Sin definir' }}</dd></div>
          }
        </dl>
        <p class="ia__ayuda">Las respuestas se basan en documentos aprobados de la base de conocimiento.</p>
        <div class="ia__acciones">
          <button class="boton boton--principal" type="button" (click)="abrirEditor('respuestas')">Configurar respuestas</button>
        </div>
      </section>

      @if (editorAbierto() === 'jev') {
        <app-ventana-flotante ceja="Decisiones del asistente" titulo="Configurar JEV · TypeSafe" forma="centrada" [anchoMaximo]="620" [cierraAlPulsarFuera]="false" (cerrar)="cerrarEditor()">
          <form id="formulario-jev" class="ia__editor" (ngSubmit)="guardarJev()">
            <label class="interruptor"><input type="checkbox" name="jev-habilitada" [(ngModel)]="jev.habilitada" /> Usar JEV en esta clínica</label>
            <label class="campo"><span class="campo__etiqueta">Clave API</span>
              <input class="campo__control" type="password" name="jev-clave" autocomplete="new-password" [(ngModel)]="claveJev" placeholder="Pegue la clave de TypeSafe" />
              <span class="campo__ayuda">La clave se cifra al guardarla y nunca se vuelve a mostrar.</span>
            </label>
            @if (jev.guardada) {
              <label class="ia__quitar"><input type="checkbox" name="jev-quitar" [(ngModel)]="quitarClaveJev" /> Eliminar la clave guardada</label>
            }
            <div class="ia__campos">
              <label class="campo"><span class="campo__etiqueta">Modelo</span>
                <input class="campo__control" name="jev-modelo" [(ngModel)]="jev.modelo" maxlength="100" required />
              </label>
              <label class="campo"><span class="campo__etiqueta">Tiempo máximo (s)</span>
                <input class="campo__control" type="number" name="jev-tiempo" [(ngModel)]="jev.tiempo" min="0.2" max="30" step="0.1" required />
              </label>
              <label class="campo"><span class="campo__etiqueta">Confianza mínima</span>
                <input class="campo__control" type="number" name="jev-umbral" [(ngModel)]="jev.umbral" min="0.5" max="0.99" step="0.01" required />
              </label>
            </div>
            <p class="ia__ayuda">Por debajo de este umbral, el asistente pregunta con opciones en lugar de adivinar.</p>
          </form>
          <div pie class="ia__pie">
            <button class="boton" type="button" [disabled]="ocupado()" (click)="cerrarEditor()">Cancelar</button>
            <button class="boton boton--principal" type="submit" form="formulario-jev" [disabled]="ocupado()">{{ ocupado() ? 'Guardando…' : 'Guardar cambios' }}</button>
          </div>
        </app-ventana-flotante>
      }

      @if (editorAbierto() === 'respuestas') {
        <app-ventana-flotante ceja="Redacción de respuestas" titulo="Configurar respuestas del asistente" forma="centrada" [anchoMaximo]="620" [cierraAlPulsarFuera]="false" (cerrar)="cerrarEditor()">
          <form id="formulario-respuestas" class="ia__editor" (ngSubmit)="guardarRespuestas()">
            <label class="interruptor"><input type="checkbox" name="resp-habilitada" [(ngModel)]="respuestas.habilitada" /> Usar esta configuración</label>
            <fieldset class="ia__opciones">
              <legend class="campo__etiqueta">Proveedor</legend>
              <label><input type="radio" name="resp-proveedor" value="entorno" [(ngModel)]="respuestas.proveedor" /> El del servidor</label>
              <label><input type="radio" name="resp-proveedor" value="anthropic" [(ngModel)]="respuestas.proveedor" /> Anthropic (usa la clave configurada allí)</label>
              <label><input type="radio" name="resp-proveedor" value="ollama" [(ngModel)]="respuestas.proveedor" /> Ollama en la red de la clínica</label>
            </fieldset>
            @if (respuestas.proveedor === 'ollama') {
              <div class="ia__campos">
                <label class="campo"><span class="campo__etiqueta">URL de Ollama</span>
                  <input class="campo__control" name="resp-url" [(ngModel)]="respuestas.url" placeholder="http://127.0.0.1:11434" />
                </label>
                <label class="campo"><span class="campo__etiqueta">Modelo</span>
                  <input class="campo__control" name="resp-modelo" [(ngModel)]="respuestas.modelo" placeholder="llama3.1" />
                </label>
              </div>
              <p class="ia__ayuda">Solo direcciones locales o de red privada: el texto de sus pacientes no sale de la clínica.</p>
            }
          </form>
          <div pie class="ia__pie">
            <button class="boton" type="button" [disabled]="ocupado()" (click)="cerrarEditor()">Cancelar</button>
            <button class="boton boton--principal" type="submit" form="formulario-respuestas" [disabled]="ocupado()">{{ ocupado() ? 'Guardando…' : 'Guardar cambios' }}</button>
          </div>
        </app-ventana-flotante>
      }
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    .ia { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 290px), 1fr)); gap: var(--espacio-4); margin-top: var(--espacio-4); }
    .ia__tarjeta { display: grid; align-content: start; gap: var(--espacio-3); padding: var(--espacio-4); border: 1px solid rgb(255 255 255 / 82%); background: linear-gradient(145deg, rgb(255 255 255 / 88%), rgb(245 251 250 / 76%)); -webkit-backdrop-filter: saturate(150%) blur(18px); backdrop-filter: saturate(150%) blur(18px); box-shadow: var(--cristal-sombra); }
    .ia__tarjeta h2 { margin: 0; }
    .ia__ayuda, .ia__estado { margin: 0; color: var(--texto-suave); font-size: 0.9rem; }
    .ia__estado { display:flex; align-items:center; gap:var(--espacio-2); color:var(--texto); }
    .ia__punto { width:9px; height:9px; flex:0 0 9px; border-radius:50%; background:#98a9aa; }
    .ia__punto--activo { background:#14866f; box-shadow:0 0 0 4px rgb(20 134 111 / 12%); }
    .ia__detalles { display:grid; gap:0; margin:0; border-top:1px solid var(--borde); border-bottom:1px solid var(--borde); }
    .ia__detalles div { display:flex; align-items:center; justify-content:space-between; gap:var(--espacio-3); padding:var(--espacio-2) 0; }
    .ia__detalles div + div { border-top:1px solid rgb(219 231 229 / 70%); }
    .ia__detalles dt { color:var(--texto-suave); font-size:.88rem; }
    .ia__detalles dd { margin:0; color:var(--texto); font-size:.9rem; font-weight:600; text-align:right; overflow-wrap:anywhere; }
    .ia__campos { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: var(--espacio-2); }
    .ia__campos .campo { margin: 0; }
    .ia__acciones { display: flex; flex-wrap: wrap; gap: var(--espacio-2); }
    .ia__opciones { display: grid; gap: 6px; margin: 0; padding: 0; border: 0; }
    .ia__opciones label { display: flex; align-items: center; gap: var(--espacio-2); cursor: pointer; }
    .ia__quitar { display: flex; align-items: center; gap: var(--espacio-2); font-size: 0.9rem; }
    .ia__editor { display:grid; gap:var(--espacio-4); }
    .ia__editor .campo { margin:0; }
    .ia__pie { justify-content:flex-end; flex-wrap:wrap; }
    .ia__prueba { display: grid; gap: 4px; padding: var(--espacio-3); border-radius: var(--radio); background: var(--acento-suave); color: var(--acento-fuerte); font-size: 0.9rem; }
    .ia__prueba--mal { background: #fdf3dc; color: #7a5a10; }
    .ia__aviso, .ia__error { grid-column: 1 / -1; margin: 0; }
    .ia__aviso { padding:var(--espacio-3) var(--espacio-4); border:1px solid rgb(20 134 111 / 20%); border-radius:var(--radio); background:rgb(20 134 111 / 8%); color:var(--acento-fuerte); }
    .interruptor { display: flex; align-items: center; gap: var(--espacio-2); font-weight: 600; }
  `,
})
export class IntegracionesIaComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly base = inject(CONFIGURACION).urlApi + '/configuracion/integraciones';

  protected jev = { habilitada: false, guardada: false, modelo: 'jev-latest', tiempo: 3, umbral: 0.85 };
  protected claveJev = '';
  protected quitarClaveJev = false;
  protected respuestas = { habilitada: false, proveedor: 'entorno', url: '', modelo: '' };

  protected readonly ocupado = signal(false);
  protected readonly aviso = signal('');
  protected readonly error = signal('');
  protected readonly prueba = signal<PruebaJev | null>(null);
  protected readonly editorAbierto = signal<'jev' | 'respuestas' | null>(null);

  protected abrirEditor(editor: 'jev' | 'respuestas'): void {
    this.error.set('');
    this.aviso.set('');
    this.editorAbierto.set(editor);
  }

  protected cerrarEditor(): void {
    if (this.ocupado()) return;
    this.claveJev = '';
    this.quitarClaveJev = false;
    this.editorAbierto.set(null);
  }

  protected nombreProveedor(): string {
    switch (this.respuestas.proveedor) {
      case 'anthropic': return 'Anthropic';
      case 'ollama': return 'Ollama · red local';
      default: return 'Configurado en el servidor';
    }
  }

  ngOnInit(): void {
    this.http.get<readonly Integracion[]>(this.base).subscribe({
      next: (lista) => {
        const t = lista.find((i) => i.codigo === 'typesafe');
        if (t) {
          this.jev = {
            habilitada: t.habilitada,
            guardada: Boolean(t.secretos['api_key']?.configurado),
            modelo: String(t.ajustes['modelo'] ?? 'jev-latest'),
            tiempo: Number(t.ajustes['tiempo_limite'] ?? 3),
            umbral: Number(t.ajustes['umbral_confianza'] ?? 0.85),
          };
        }
        const r = lista.find((i) => i.codigo === 'respuestas_ia');
        if (r) {
          this.respuestas = {
            habilitada: r.habilitada,
            proveedor: String(r.ajustes['proveedor'] ?? 'entorno'),
            url: String(r.ajustes['ollama_url'] ?? ''),
            modelo: String(r.ajustes['ollama_modelo'] ?? ''),
          };
        }
      },
      error: (fallo: HttpErrorResponse) => this.error.set(mensaje(fallo, 'No se pudo cargar la configuración de IA.')),
    });
  }

  protected guardarJev(): void {
    const cuerpo = {
      habilitada: this.jev.habilitada,
      ajustes: { modelo: this.jev.modelo.trim() || 'jev-latest', tiempo_limite: Number(this.jev.tiempo), umbral_confianza: Number(this.jev.umbral) },
      secretos: this.claveJev.trim() ? { api_key: this.claveJev.trim() } : {},
      eliminar_secretos: this.quitarClaveJev && !this.claveJev.trim() ? ['api_key'] : [],
    };
    this.guardar('typesafe', cuerpo, 'JEV guardado.', (respuesta) => {
      this.jev = { ...this.jev, habilitada: respuesta.habilitada, guardada: Boolean(respuesta.secretos['api_key']?.configurado) };
      this.claveJev = '';
      this.quitarClaveJev = false;
    });
  }

  protected guardarRespuestas(): void {
    const cuerpo = {
      habilitada: this.respuestas.habilitada,
      ajustes: { proveedor: this.respuestas.proveedor, ollama_url: this.respuestas.url.trim(), ollama_modelo: this.respuestas.modelo.trim() },
    };
    this.guardar('respuestas_ia', cuerpo, 'Respuestas del asistente guardadas.', () => undefined);
  }

  protected probar(): void {
    this.ocupado.set(true);
    this.error.set('');
    this.prueba.set(null);
    this.http.post<PruebaJev>(`${this.base}/typesafe/prueba`, {}).subscribe({
      next: (resultado) => {
        this.ocupado.set(false);
        this.prueba.set(resultado);
      },
      error: (fallo: HttpErrorResponse) => {
        this.ocupado.set(false);
        this.error.set(mensaje(fallo, 'No se pudo probar JEV.'));
      },
    });
  }

  protected intencion(codigo: string): string {
    return INTENCIONES[codigo] ?? codigo;
  }

  protected porcentaje(valor: number): string {
    return `${Math.round(valor * 100)} %`;
  }

  private guardar(codigo: string, cuerpo: unknown, exito: string, despues: (r: Integracion) => void): void {
    this.ocupado.set(true);
    this.error.set('');
    this.aviso.set('');
    this.http.put<Integracion>(`${this.base}/${codigo}`, cuerpo).subscribe({
      next: (respuesta) => {
        this.ocupado.set(false);
        this.aviso.set(exito);
        despues(respuesta);
        this.editorAbierto.set(null);
      },
      error: (fallo: HttpErrorResponse) => {
        this.ocupado.set(false);
        this.error.set(mensaje(fallo, 'No se pudo guardar.'));
      },
    });
  }
}

function mensaje(fallo: HttpErrorResponse, porDefecto: string): string {
  return (fallo.error as { mensaje?: string } | null)?.mensaje ?? porDefecto;
}
