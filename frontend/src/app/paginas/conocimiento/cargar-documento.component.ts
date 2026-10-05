/**
 * Carga de documentos a la base de conocimiento.
 *
 * Dos modos con el mismo formulario
 * ---------------------------------
 * * **Documento nuevo**: crea el documento (nace en `DRAFT`) y sube su primera
 *   version.
 * * **Version nueva** de un documento existente: solo sube el texto. El
 *   estado no cambia; un documento publicado sigue respondiendo con su
 *   version aprobada mientras la nueva se revisa.
 *
 * Lo que esta pantalla no hace
 * ----------------------------
 * **No aprueba.** Subir un archivo no lo pone al alcance del agente: queda en
 * borrador hasta que alguien con `conocimiento.aprobar` lo revise. Quien carga
 * no aprueba, y el backend lo exige aunque esta pantalla se saltara.
 *
 * **No interpreta el archivo.** Se lee como texto plano en el navegador y se
 * envia tal cual; el backend lo fragmenta, lo vectoriza y analiza si contiene
 * algo que parezca una instruccion al sistema (ADR-0014). El texto nunca se
 * inyecta como HTML.
 *
 * Formatos
 * --------
 * Solo texto (`.txt`, `.md`, `.csv`). El endpoint de ingesta recibe texto, no
 * binarios: un PDF o un DOCX necesitan extraccion en el servidor, que todavia
 * no existe. Mientras tanto se puede pegar el texto copiado del documento.
 */
import { Component, computed, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { IconoComponent } from '../../compartido/icono.component';
import { ApiService, FalloApi } from '../../nucleo/servicios/api.service';
import type {
  Documento,
  RespuestaIngesta,
  TipoDocumento,
} from '../../nucleo/servicios/api.service';

/** Limite del backend (`SolicitudIngesta.contenido`). */
export const MAXIMO_CARACTERES = 500_000;
/** Tope de tamano de archivo antes de leerlo: evita colgar la pestana. */
const MAXIMO_BYTES = 2 * 1024 * 1024;
const EXTENSIONES = ['.txt', '.md', '.markdown', '.csv'] as const;

export const OPCIONES_TIPO: readonly { valor: TipoDocumento; texto: string }[] = [
  { valor: 'PROTOCOLO', texto: 'Protocolo' },
  { valor: 'INSTRUCTIVO', texto: 'Instructivo' },
  { valor: 'PREPARACION_EXAMEN', texto: 'Preparación de examen' },
  { valor: 'POLITICA', texto: 'Política' },
  { valor: 'PREGUNTA_FRECUENTE', texto: 'Pregunta frecuente' },
  { valor: 'TARIFARIO', texto: 'Tarifario' },
];

const OPCIONES_SENSIBILIDAD = [
  { valor: 'N0', texto: 'N0 · Público (servicios, horarios, preparación de exámenes)' },
  { valor: 'N1', texto: 'N1 · Administrativo (uso interno del personal)' },
  { valor: 'N2', texto: 'N2 · Clínico (solo personal asistencial)' },
  { valor: 'N3', texto: 'N3 · Clínico sensible (acceso restringido)' },
] as const;

type Origen = 'archivo' | 'texto';

@Component({
  selector: 'app-cargar-documento',
  standalone: true,
  imports: [FormsModule, IconoComponent],
  host: { '(document:keydown.escape)': 'cerrar()' },
  template: `
    <div class="dialogo">
      <section
        class="tarjeta dialogo__panel carga"
        role="dialog"
        aria-modal="true"
        aria-labelledby="carga-titulo"
      >
        <header class="carga__cabecera">
          <span class="carga__icono"><app-icono nombre="subir" [tamano]="22" /></span>
          <div>
            <h2 id="carga-titulo">
              {{ documento() ? 'Subir versión nueva' : 'Cargar documento' }}
            </h2>
            <p class="carga__sub">
              @if (documento(); as doc) {
                {{ doc.titulo }} · sigue en su estado actual mientras se revisa.
              } @else {
                Entra como borrador. Responde consultas solo después de aprobarse.
              }
            </p>
          </div>
          <button
            type="button"
            class="boton boton--plano carga__cerrar"
            (click)="cerrar()"
            [disabled]="enviando()"
          >
            <app-icono nombre="cerrar" [tamano]="20" />
            <span class="solo-lectores">Cerrar</span>
          </button>
        </header>

        @if (resultado(); as res) {
          <div class="carga__hecho" role="status">
            <p class="carga__hecho-titulo">
              <app-icono nombre="tic" [tamano]="20" /> Versión {{ res.version }} cargada
            </p>
            <p>
              Se dividió en <strong>{{ res.fragmentos }}</strong> fragmento(s) para la búsqueda.
              {{ documento() ? '' : 'El documento queda en borrador.' }}
            </p>
            @if (res.requiere_revision) {
              <p class="carga__alerta">
                <app-icono nombre="aviso" [tamano]="18" />
                El análisis encontró texto que parece una instrucción al sistema. La aprobación
                queda bloqueada hasta que una persona lo revise.
              </p>
            }
            <div class="acciones acciones--final">
              <button type="button" class="boton boton--principal" (click)="cerrar()">
                Listo
              </button>
            </div>
          </div>
        } @else {
          <form (ngSubmit)="enviar()" #formulario="ngForm" novalidate>
            @if (!documento()) {
              <label class="campo">
                <span class="campo__etiqueta">Título</span>
                <input
                  class="campo__control"
                  name="titulo"
                  required
                  minlength="3"
                  maxlength="300"
                  placeholder="Por ejemplo: Preparación para ecografía abdominal"
                  [(ngModel)]="titulo"
                />
              </label>

              <div class="carga__dos">
                <label class="campo">
                  <span class="campo__etiqueta">Tipo</span>
                  <select class="campo__control" name="tipo" [(ngModel)]="tipo">
                    @for (opcion of opcionesTipo; track opcion.valor) {
                      <option [value]="opcion.valor">{{ opcion.texto }}</option>
                    }
                  </select>
                </label>

                <label class="campo">
                  <span class="campo__etiqueta">Sensibilidad</span>
                  <select class="campo__control" name="sensibilidad" [(ngModel)]="sensibilidad">
                    @for (opcion of opcionesSensibilidad; track opcion.valor) {
                      <option [value]="opcion.valor">{{ opcion.texto }}</option>
                    }
                  </select>
                </label>
              </div>

              <label class="campo">
                <span class="campo__etiqueta">Etiquetas (opcional)</span>
                <input
                  class="campo__control"
                  name="etiquetas"
                  placeholder="ayuno, laboratorio, ecografía"
                  [(ngModel)]="etiquetas"
                />
                <span class="campo__ayuda">Separadas por comas. Máximo 20.</span>
              </label>
            }

            <div class="carga__origen" role="radiogroup" aria-label="Origen del contenido">
              <button
                type="button"
                role="radio"
                class="carga__pestana"
                [attr.aria-checked]="origen() === 'archivo'"
                (click)="origen.set('archivo')"
              >
                Subir archivo
              </button>
              <button
                type="button"
                role="radio"
                class="carga__pestana"
                [attr.aria-checked]="origen() === 'texto'"
                (click)="origen.set('texto')"
              >
                Pegar texto
              </button>
            </div>

            @if (origen() === 'archivo') {
              <label
                class="carga__zona"
                [class.carga__zona--activa]="arrastrando()"
                [class.carga__zona--lista]="nombreArchivo()"
                (dragover)="alArrastrar($event)"
                (dragleave)="arrastrando.set(false)"
                (drop)="alSoltar($event)"
              >
                <input
                  type="file"
                  class="solo-lectores"
                  [accept]="aceptados"
                  (change)="alElegir($event)"
                />
                <app-icono [nombre]="nombreArchivo() ? 'archivo' : 'subir'" [tamano]="28" />
                @if (nombreArchivo(); as nombre) {
                  <strong>{{ nombre }}</strong>
                  <span class="carga__zona-ayuda numerico">
                    {{ contenido().length.toLocaleString('es') }} caracteres · pulse para cambiar
                  </span>
                } @else {
                  <strong>Arrastre un archivo o pulse para elegirlo</strong>
                  <span class="carga__zona-ayuda">Texto plano: .txt, .md o .csv · hasta 2 MB</span>
                }
              </label>
              <p class="campo__ayuda">
                ¿Tiene un PDF o un Word? Copie su texto y use «Pegar texto». La extracción
                automática de esos formatos todavía no está disponible.
              </p>
            } @else {
              <label class="campo">
                <span class="campo__etiqueta">Contenido</span>
                <textarea
                  class="campo__control carga__texto"
                  name="contenido"
                  rows="9"
                  [ngModel]="contenido()"
                  (ngModelChange)="contenido.set($event)"
                ></textarea>
                <span class="campo__ayuda numerico">
                  {{ contenido().length.toLocaleString('es') }} /
                  {{ maximo.toLocaleString('es') }} caracteres
                </span>
              </label>
            }

            <label class="campo">
              <span class="campo__etiqueta">Notas del cambio (opcional)</span>
              <input
                class="campo__control"
                name="notas"
                maxlength="1000"
                placeholder="Qué contiene o qué cambia respecto a la versión anterior"
                [(ngModel)]="notas"
              />
            </label>

            <p class="carga__privacidad">
              <app-icono nombre="escudo" [tamano]="18" />
              Solo documentos de la clínica (protocolos, instructivos, políticas). No incluya
              datos de pacientes: este contenido se usa para responder consultas.
            </p>

            @if (aviso()) {
              <p class="aviso-error" role="alert">{{ aviso() }}</p>
            }
            @if (error(); as fallo) {
              <div class="aviso-error" role="alert">
                <p class="carga__error-titulo">{{ fallo.message }}</p>
                @if (documentoCreadoId()) {
                  <p class="carga__error-detalle">
                    El documento se creó como borrador, pero el contenido no se guardó. Al
                    reintentar solo se sube el contenido.
                  </p>
                }
                @if (fallo.correlacionId) {
                  <p class="carga__error-detalle">Referencia: {{ fallo.correlacionId }}</p>
                }
              </div>
            }

            <div class="acciones acciones--final">
              <button type="button" class="boton" (click)="cerrar()" [disabled]="enviando()">
                Cancelar
              </button>
              <button
                type="submit"
                class="boton boton--principal"
                [disabled]="enviando() || !puedeEnviar() || (!documento() && !formulario.form.valid)"
              >
                <app-icono nombre="subir" [tamano]="18" />
                {{ enviando() ? 'Procesando…' : documento() ? 'Subir versión' : 'Cargar documento' }}
              </button>
            </div>
          </form>
        }
      </section>
    </div>
  `,
  styles: `
    .dialogo {
      overflow-y: auto;
      align-items: flex-start;
      padding-top: 6vh;
    }
    .carga {
      max-width: 620px;
      padding: var(--espacio-5) var(--espacio-6) var(--espacio-6);
      box-shadow: 0 24px 60px rgb(16 42 46 / 25%);
    }
    .carga__cabecera {
      display: flex;
      align-items: flex-start;
      gap: var(--espacio-3);
      margin-bottom: var(--espacio-5);
    }
    .carga__cabecera h2 {
      margin: 0;
    }
    .carga__icono {
      display: inline-grid;
      place-items: center;
      width: 44px;
      height: 44px;
      flex: 0 0 auto;
      border-radius: 12px;
      background: var(--acento-suave);
      color: var(--acento);
    }
    .carga__sub {
      margin: 2px 0 0;
      font-size: 0.9rem;
      color: var(--texto-suave);
    }
    .carga__cerrar {
      margin-left: auto;
      min-width: var(--toque-minimo);
      padding: 0;
    }
    .carga__dos {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: var(--espacio-4);
    }
    .carga__origen {
      display: inline-flex;
      gap: 4px;
      padding: 4px;
      margin-bottom: var(--espacio-3);
      border-radius: 999px;
      background: var(--superficie-hundida);
    }
    .carga__pestana {
      min-height: 36px;
      padding: 0 var(--espacio-4);
      border: 0;
      border-radius: 999px;
      background: transparent;
      color: var(--texto-suave);
      font-weight: 600;
      cursor: pointer;
    }
    .carga__pestana[aria-checked='true'] {
      background: var(--superficie-elevada);
      color: var(--acento-fuerte);
      box-shadow: var(--sombra-1);
    }
    .carga__zona {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: var(--espacio-2);
      padding: var(--espacio-6) var(--espacio-4);
      border: 2px dashed var(--borde-fuerte);
      border-radius: 14px;
      background: #f8fbfb;
      color: var(--acento);
      text-align: center;
      cursor: pointer;
      transition: border-color 140ms ease, background-color 140ms ease;
    }
    .carga__zona strong {
      color: var(--texto);
    }
    .carga__zona:hover,
    .carga__zona--activa {
      border-color: var(--acento);
      background: var(--acento-suave);
    }
    .carga__zona:focus-within {
      outline: 3px solid var(--acento);
      outline-offset: 2px;
    }
    .carga__zona--lista {
      border-style: solid;
      border-color: var(--acento);
    }
    .carga__zona-ayuda {
      font-size: 0.85rem;
      color: var(--texto-suave);
    }
    .carga__texto {
      font-family: var(--fuente-mono);
      font-size: 0.88rem;
    }
    .carga__privacidad {
      display: flex;
      gap: var(--espacio-2);
      align-items: flex-start;
      margin: var(--espacio-4) 0;
      padding: var(--espacio-3) var(--espacio-4);
      border-radius: var(--radio);
      background: var(--info-fondo);
      color: var(--info);
      font-size: 0.88rem;
    }
    .carga__error-titulo {
      margin: 0;
      font-weight: 650;
    }
    .carga__error-detalle {
      margin: var(--espacio-1) 0 0;
      font-size: 0.88rem;
    }
    .carga__hecho-titulo {
      display: flex;
      align-items: center;
      gap: var(--espacio-2);
      font-size: 1.1rem;
      font-weight: 700;
      color: var(--exito);
    }
    .carga__alerta {
      display: flex;
      gap: var(--espacio-2);
      padding: var(--espacio-3) var(--espacio-4);
      border: 1px solid var(--aviso);
      border-radius: var(--radio);
      background: var(--aviso-fondo);
      color: var(--aviso);
    }
    @media (max-width: 560px) {
      .carga {
        padding: var(--espacio-4);
      }
      .carga__dos {
        grid-template-columns: 1fr;
      }
    }
  `,
})
export class CargarDocumentoComponent {
  private readonly api = inject(ApiService);

  /** Documento existente: si llega, el dialogo sube una version nueva. */
  readonly documento = input<Documento | null>(null);
  readonly cerrado = output<void>();
  /** Se emite al terminar la carga, para que el listado se recargue. */
  readonly cargado = output<RespuestaIngesta>();

  protected readonly opcionesTipo = OPCIONES_TIPO;
  protected readonly opcionesSensibilidad = OPCIONES_SENSIBILIDAD;
  protected readonly aceptados = EXTENSIONES.join(',');
  protected readonly maximo = MAXIMO_CARACTERES;

  protected titulo = '';
  protected tipo: TipoDocumento = 'PROTOCOLO';
  /** N0 por defecto: es lo que el agente puede citar a pacientes. */
  protected sensibilidad = 'N0';
  protected etiquetas = '';
  protected notas = '';

  protected readonly origen = signal<Origen>('archivo');
  protected readonly contenido = signal('');
  protected readonly nombreArchivo = signal<string | null>(null);
  protected readonly arrastrando = signal(false);
  protected readonly enviando = signal(false);
  protected readonly aviso = signal<string | null>(null);
  protected readonly error = signal<FalloApi | null>(null);
  protected readonly resultado = signal<RespuestaIngesta | null>(null);

  /**
   * Documento ya creado en un intento anterior cuya ingesta fallo.
   *
   * Reintentar no puede crear un segundo documento con el mismo titulo: solo
   * vuelve a subir el contenido al que ya existe.
   */
  protected readonly documentoCreadoId = signal<string | null>(null);

  protected readonly puedeEnviar = computed(() => {
    const largo = this.contenido().trim().length;
    return largo > 0 && largo <= MAXIMO_CARACTERES;
  });

  // ----- Archivo -----
  protected alArrastrar(evento: DragEvent): void {
    evento.preventDefault();
    this.arrastrando.set(true);
  }

  protected alSoltar(evento: DragEvent): void {
    evento.preventDefault();
    this.arrastrando.set(false);
    const archivo = evento.dataTransfer?.files?.[0];
    if (archivo) {
      void this.leer(archivo);
    }
  }

  protected alElegir(evento: Event): void {
    const campo = evento.target as HTMLInputElement;
    const archivo = campo.files?.[0];
    if (archivo) {
      void this.leer(archivo);
    }
    // Permite volver a elegir el mismo archivo tras corregirlo.
    campo.value = '';
  }

  private async leer(archivo: File): Promise<void> {
    this.aviso.set(null);
    const nombre = archivo.name.toLowerCase();
    if (!EXTENSIONES.some((extension) => nombre.endsWith(extension))) {
      this.aviso.set(
        'Ese formato no se puede leer como texto. Use .txt, .md o .csv, o pegue el texto del documento.',
      );
      return;
    }
    if (archivo.size > MAXIMO_BYTES) {
      this.aviso.set('El archivo supera 2 MB. Divídalo en documentos más pequeños.');
      return;
    }
    const texto = await archivo.text();
    if (texto.trim().length === 0) {
      this.aviso.set('El archivo está vacío.');
      return;
    }
    if (texto.length > MAXIMO_CARACTERES) {
      this.aviso.set(
        `El archivo tiene ${texto.length.toLocaleString('es')} caracteres; el máximo es ${MAXIMO_CARACTERES.toLocaleString('es')}.`,
      );
      return;
    }
    this.contenido.set(texto);
    this.nombreArchivo.set(archivo.name);
    if (!this.documento() && !this.titulo.trim()) {
      // Sugerencia de titulo a partir del nombre del archivo.
      this.titulo = archivo.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').trim();
    }
  }

  // ----- Envio -----
  protected enviar(): void {
    if (!this.puedeEnviar() || this.enviando()) {
      return;
    }
    this.enviando.set(true);
    this.error.set(null);

    const existente = this.documento()?.id ?? this.documentoCreadoId();
    if (existente) {
      this.subirContenido(existente);
      return;
    }

    const etiquetas = this.etiquetas
      .split(',')
      .map((etiqueta) => etiqueta.trim())
      .filter(Boolean)
      .slice(0, 20);

    this.api
      .crearDocumento({
        titulo: this.titulo.trim(),
        tipo: this.tipo,
        sensibilidad: this.sensibilidad,
        etiquetas: etiquetas.length > 0 ? etiquetas : null,
      })
      .subscribe({
        next: (documento) => {
          this.documentoCreadoId.set(documento.id);
          this.subirContenido(documento.id);
        },
        error: (fallo: FalloApi) => {
          this.error.set(fallo);
          this.enviando.set(false);
        },
      });
  }

  private subirContenido(documentoId: string): void {
    this.api
      .ingerirVersion(documentoId, {
        contenido: this.contenido(),
        nombre_archivo: this.origen() === 'archivo' ? this.nombreArchivo() : null,
        notas_cambio: this.notas.trim() || null,
      })
      .subscribe({
        next: (respuesta) => {
          this.resultado.set(respuesta);
          this.enviando.set(false);
          this.cargado.emit(respuesta);
        },
        error: (fallo: FalloApi) => {
          this.error.set(fallo);
          this.enviando.set(false);
        },
      });
  }

  protected cerrar(): void {
    if (this.enviando()) {
      return;
    }
    // Un documento creado cuya ingesta fallo ya existe en el listado: se
    // avisa al padre para que lo muestre aunque no haya `cargado`.
    this.cerrado.emit();
  }
}
