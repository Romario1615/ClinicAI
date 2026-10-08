/**
 * Ventana flotante: el detalle se abre encima, nunca al final de la lista.
 *
 * Por qué encima y no debajo
 * --------------------------
 * Colgar el detalle al final de una lista tiene tres problemas concretos, y
 * los tres se notan en una recepción con prisa:
 *
 * 1. **No se ve.** Con veinte pacientes en la lista, el detalle aparece fuera
 *    de la pantalla y parece que el clic no hizo nada.
 * 2. **Pierde el sitio.** Al desplazarse hasta abajo se deja de ver la fila
 *    que se estaba mirando, y al volver hay que buscarla otra vez.
 * 3. **Mueve todo.** Abrir el detalle empuja el contenido y la fila que estaba
 *    bajo el cursor deja de estarlo: el siguiente clic cae en otra cosa.
 *
 * La ventana flotante resuelve los tres: la lista no se mueve, el detalle está
 * siempre a la vista y cerrarlo devuelve exactamente al mismo punto.
 *
 * Dos formas, una sola pieza
 * --------------------------
 * `lateral` para lo que se consulta junto a la lista (la ficha de un paciente,
 * el detalle de una entrada) y `centrada` para lo que exige una decisión antes
 * de seguir (confirmar una cancelación). La diferencia no es estética: una
 * ventana lateral deja ver el contexto, una centrada lo tapa a propósito.
 *
 * Lo que hace por accesibilidad, y por qué
 * ----------------------------------------
 * * **`Escape` cierra.** Es lo primero que intenta cualquiera.
 * * **El foco entra al abrir y vuelve al cerrar.** Sin esto, quien navega con
 *   teclado abre la ventana y sigue tabulando por la lista de detrás, sin
 *   saber que hay algo abierto.
 * * **El foco no se escapa** mientras está abierta (se cicla dentro).
 * * **`aria-modal` y `role="dialog"`** con su título asociado.
 * * El fondo no se desplaza: sin esto, la rueda del ratón mueve la lista de
 *   detrás y al cerrar nada está donde se dejó.
 * * **El foco vuelve al botón que la abrió** aunque ese botón desaparezca y
 *   reaparezca con la ventana (un «Nueva nota» que se oculta mientras se
 *   escribe): se recuerda qué control se activó y se busca de nuevo al cerrar.
 *
 * Lo que protege
 * --------------
 * * `ocupada`: mientras se guarda no se puede cerrar por ningún camino
 *   (Escape, la X, el fondo, el gesto «atrás» del móvil). Cerrar a mitad de
 *   petición perdía el resultado o lo anunciaba mal.
 * * `cambiosSinGuardar`: cerrar pide confirmación dentro de la propia ventana
 *   antes de descartar lo escrito. Un Escape no debe tirar una nota clínica.
 * * `error`: el error se pinta DENTRO de la ventana. Un <dialog> modal deja
 *   inerte todo lo de detrás: un aviso fuera no se ve ni lo lee el lector de
 *   pantalla.
 */
import {
  Component,
  ElementRef,
  type OnDestroy,
  type AfterViewInit,
  computed,
  inject,
  input,
  output,
  signal,
  viewChild,
  ChangeDetectionStrategy
} from '@angular/core';

import { MovimientoService } from '../nucleo/movimiento/movimiento.service';
import { IconoComponent } from './icono.component';

/** Cómo volver a encontrar un control aunque Angular lo haya recreado. */
interface HuellaDeControl {
  readonly elemento: HTMLElement;
  readonly id: string;
  readonly etiqueta: string;
  readonly etiquetaHtml: string;
}

const SELECTOR_ACTIVABLE = 'button, a[href], input, select, textarea, summary, [role="tab"], [role="button"], [tabindex]';

function huellaDe(elemento: HTMLElement): HuellaDeControl {
  return {
    elemento,
    id: elemento.id,
    etiqueta: (elemento.getAttribute('aria-label') ?? elemento.textContent ?? '').trim().replace(/\s+/g, ' '),
    etiquetaHtml: elemento.tagName,
  };
}

/**
 * Último control que se activó en la página.
 *
 * Hace falta porque el botón que abre una ventana a menudo desaparece en el
 * mismo ciclo en que ella aparece (`@if (!editando) { Nueva nota }`): cuando la
 * ventana nace, el foco ya está en `<body>` y no queda a quién volver.
 */
let ultimoActivado: HuellaDeControl | null = null;

function registrarActivacion(evento: Event): void {
  const objetivo = (evento.target as Element | null)?.closest?.(SELECTOR_ACTIVABLE);
  if (objetivo instanceof HTMLElement) ultimoActivado = huellaDe(objetivo);
}

if (typeof document !== 'undefined') {
  document.addEventListener('pointerdown', registrarActivacion, true);
  document.addEventListener(
    'keydown',
    (evento) => {
      if (evento.key === 'Enter' || evento.key === ' ') registrarActivacion(evento);
    },
    true,
  );
}

/** El mismo control, o el que lo sustituyó: mismo id, o mismo tipo y nombre. */
function localizar(huella: HuellaDeControl | null): HTMLElement | null {
  if (!huella) return null;
  if (huella.elemento.isConnected) return huella.elemento;
  if (huella.id) {
    const porId = document.getElementById(huella.id);
    if (porId) return porId;
  }
  if (!huella.etiqueta) return null;
  const iguales = Array.from(document.querySelectorAll<HTMLElement>(huella.etiquetaHtml)).filter(
    (candidato) =>
      (candidato.getAttribute('aria-label') ?? candidato.textContent ?? '').trim().replace(/\s+/g, ' ') === huella.etiqueta,
  );
  // Primero el que se ve; si no hay motor de maquetación, el primero conectado.
  return iguales.find((candidato) => candidato.getClientRects().length > 0) ?? iguales[0] ?? null;
}

@Component({
  selector: 'app-ventana-flotante',
  standalone: true,
  imports: [IconoComponent],
  template: `
    <!-- El fondo cierra al pulsarlo, y eso es una comodidad de raton: el
         camino de teclado es la tecla Escape, que atiende la propia ventana. -->
    <dialog
      class="capa"
      [class.capa--centrada]="forma() === 'centrada'"
      role="dialog"
      aria-modal="true"
      [attr.aria-label]="titulo()"
      #capa
      (click)="alPulsarFondo($event)"
      (keydown)="alTeclear($event)"
      (cancel)="alCancelar($event)"
      (close)="alCerrarseSola()"
    >
      <div
        class="ventana"
        [class.ventana--centrada]="forma() === 'centrada'"
        [class.ventana--alta]="altoCompleto()"
        [style.max-width.px]="anchoMaximo()"
        tabindex="-1"
        #ventana
      >
        <header class="ventana__cabecera">
          <div class="ventana__titulos">
            <p class="ventana__ceja">{{ ceja() }}</p>
            <h2 class="ventana__titulo">{{ titulo() }}</h2>
          </div>
          <button
            type="button"
            class="boton boton--plano ventana__cerrar"
            (click)="solicitarCierre()"
            [disabled]="cierreBloqueado()"
            [attr.aria-label]="'Cerrar ' + titulo()"
          >
            <app-icono nombre="cerrar" [tamano]="18" />
          </button>
        </header>
        @if (confirmandoDescarte()) {
          <!-- Confirmación en la propia ventana, no un window.confirm: se lee
               con el mismo vidrio y el lector de pantalla la anuncia. -->
          <div class="ventana__descarte" role="alertdialog" aria-labelledby="ventana-descarte-texto">
            <p id="ventana-descarte-texto">Hay cambios sin guardar. ¿Quiere descartarlos?</p>
            <div class="ventana__descarte-acciones">
              <button type="button" class="boton boton--pequeno" #botonSeguir (click)="seguirEditando()">
                Seguir editando
              </button>
              <button type="button" class="boton boton--pequeno boton--peligro" (click)="descartar()">
                Descartar cambios
              </button>
            </div>
          </div>
        }
        <div class="ventana__cuerpo">
          @if (error()) {
            <p class="ventana__error" role="alert">{{ error() }}</p>
          }
          <ng-content />
        </div>
        <footer class="ventana__pie">
          <ng-content select="[pie]" />
        </footer>
      </div>
    </dialog>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    /* <dialog> abierto con showModal(): se pinta en la capa superior del
       navegador, por encima de la cabecera aunque el contenido cree su propio
       contexto de apilamiento (isolation, transform, z-index). Un z-index
       alto no basta para eso. Se anulan los estilos por defecto del dialog. */
    .capa {
      position: fixed;
      inset: 0;
      z-index: 60;
      width: 100%;
      height: 100%;
      height: 100dvh;
      max-width: none;
      max-height: none;
      margin: 0;
      border: 0;
      color: inherit;
      box-sizing: border-box;
      /* Se ajusta al contenido en lugar de estirarse: una ficha corta en una
         ventana de alto completo deja medio panel vacio, y eso se lee como si
         faltara algo por cargar. Con contenido largo crece hasta el tope y el
         cuerpo se desplaza. */
      align-items: flex-start;
      justify-content: flex-end;
      padding: var(--espacio-4);
      /* Velo de vidrio: oscurece y desenfoca lo de detrás. El contexto sigue
         reconocible, pero deja de competir con la ventana. */
      background: var(--velo-fondo, rgb(22 32 46 / 38%));
      backdrop-filter: var(--velo-desenfoque, none);
      -webkit-backdrop-filter: var(--velo-desenfoque, none);
      /* Sin esto, la rueda del ratón desplaza la lista de detrás y al cerrar
         nada está donde se dejó. */
      overscroll-behavior: contain;
      animation: aparecer 140ms ease-out;
    }

    .capa[open] {
      display: flex;
    }

    /* El oscurecido lo pone la propia capa, con la misma animación. */
    .capa::backdrop {
      background: transparent;
    }

    .capa--centrada {
      align-items: center;
      justify-content: center;
    }

    .ventana {
      display: flex;
      flex-direction: column;
      width: 100%;
      max-height: 100%;
      min-height: 0;
      border: 1px solid var(--vidrio-borde, var(--borde));
      border-radius: var(--radio-vidrio, var(--radio));
      /* Vidrio denso: una ficha se lee durante minutos, así que el panel es
         casi opaco. El desenfoque y el canto iluminado dicen «flota encima»
         sin restar contraste al texto clínico. */
      background: var(--vidrio-ventana, var(--superficie-elevada));
      backdrop-filter: var(--vidrio-desenfoque-fuerte, none);
      -webkit-backdrop-filter: var(--vidrio-desenfoque-fuerte, none);
      box-shadow: var(--vidrio-canto, 0 0 0 transparent), var(--sombra-2), 0 24px 48px rgb(22 32 46 / 18%);
      overflow: hidden;
      animation: entrar-lateral 160ms cubic-bezier(0.2, 0.8, 0.3, 1);
    }

    /* Motion toma el relevo con resortes: la animación CSS queda solo como
       respaldo para navegadores sin WAAPI. */
    :host-context(.movimiento-activo) .capa,
    :host-context(.movimiento-activo) .ventana {
      animation: none;
    }

    /* Alto fijo: al cambiar de pestana la ventana no salta de tamano. */
    .ventana--alta {
      height: 100%;
    }

    .ventana--centrada {
      animation: entrar-centrada 160ms cubic-bezier(0.2, 0.8, 0.3, 1);
    }

    .ventana__cabecera {
      display: flex;
      flex: 0 0 auto;
      align-items: flex-start;
      gap: var(--espacio-3);
      padding: var(--espacio-4);
      border-bottom: 1px solid var(--vidrio-separador, var(--borde));
      background: transparent;
    }

    .ventana__titulos {
      flex: 1 1 auto;
      min-width: 0;
    }

    .ventana__ceja {
      margin: 0;
      color: var(--acento);
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }

    .ventana__titulo {
      margin: 2px 0 0;
      font-size: 1.2rem;
      line-height: 1.25;
    }

    .ventana__cerrar {
      min-width: 36px;
      min-height: 36px;
      padding: 0;
    }

    .ventana__cuerpo {
      flex: 1 1 auto;
      min-height: 0;
      overflow-y: auto;
      padding: var(--espacio-4);
    }

    .ventana__pie {
      display: flex;
      flex: 0 0 auto;
      flex-wrap: wrap;
      gap: var(--espacio-3);
      padding: var(--espacio-3) var(--espacio-4);
      border-top: 1px solid var(--vidrio-separador, var(--borde));
      background: var(--vidrio-pie, var(--superficie));
    }

    /* Sin nada proyectado no hay pie. Se resuelve por CSS y no con un bloque
       condicional: un condicional alrededor de un ng-content con selector no
       oculta el pie, hace DESAPARECER lo proyectado, porque el selector ya lo
       ha sacado de la ranura por defecto y se queda sin sitio donde ir. */
    .ventana__pie:empty {
      display: none;
    }

    .ventana__error {
      margin: 0 0 var(--espacio-3);
      padding: var(--espacio-3) var(--espacio-4);
      border: 1px solid color-mix(in srgb, var(--peligro) 45%, transparent);
      border-left-width: 4px;
      border-radius: var(--radio-pequeno, 8px);
      background: var(--peligro-fondo);
      color: var(--peligro);
      font-weight: 600;
    }

    .ventana__descarte {
      display: flex;
      flex: 0 0 auto;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: var(--espacio-2) var(--espacio-3);
      padding: var(--espacio-3) var(--espacio-4);
      border-bottom: 1px solid color-mix(in srgb, var(--aviso) 40%, transparent);
      background: var(--aviso-fondo);
      color: var(--aviso);
    }

    .ventana__descarte p {
      margin: 0;
      font-weight: 650;
    }

    .ventana__descarte-acciones {
      display: flex;
      flex-wrap: wrap;
      gap: var(--espacio-2);
    }

    @keyframes aparecer {
      from {
        opacity: 0;
      }
    }

    @keyframes entrar-lateral {
      from {
        transform: translateX(16px);
        opacity: 0;
      }
    }

    @keyframes entrar-centrada {
      from {
        transform: scale(0.98);
        opacity: 0;
      }
    }

    @media (prefers-reduced-motion: reduce) {
      .capa,
      .ventana {
        animation: none;
      }
    }

    /* En pantalla estrecha ocupa todo: una ventana lateral de 440 px en una
       tableta de 600 no deja ver ni el contexto ni el detalle. */
    @media (max-width: 720px) {
      .capa {
        padding: 0;
      }

      .ventana {
        max-width: none !important;
        border-radius: 0;
        height: 100%;
      }
    }
  `,
})
export class VentanaFlotanteComponent implements AfterViewInit, OnDestroy {
  private readonly anfitrion = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly movimiento = inject(MovimientoService);
  /** Hay una salida animada en curso: un segundo Escape no la repite. */
  private cerrando = false;
  private destruida = false;

  readonly titulo = input.required<string>();
  readonly ceja = input('');
  readonly forma = input<'lateral' | 'centrada'>('lateral');
  readonly anchoMaximo = input(460);
  /** Ocupa todo el alto disponible (fichas con pestanas de distinto largo). */
  readonly altoCompleto = input(false);
  /** Impide descartar el diálogo por Escape mientras hay un guardado en curso. */
  readonly cierraConEscape = input(true);
  /** Hay una operación en curso: no se cierra por ningún camino hasta que acabe. */
  readonly ocupada = input(false);
  /** Lo escrito no está guardado: cerrar pide confirmación antes de descartarlo. */
  readonly cambiosSinGuardar = input(false);
  /** Error que la ventana muestra en su cuerpo, a la vista y anunciado. */
  readonly error = input<string | null | undefined>(null);
  /**
   * Si pulsar el fondo cierra.
   *
   * Falso cuando la ventana contiene un formulario a medio rellenar: cerrar
   * por un clic fuera de sitio pierde lo escrito, y eso se paga en una
   * recepción con prisa.
   */
  readonly cierraAlPulsarFuera = input(true);

  readonly cerrar = output<void>();

  protected readonly cierreBloqueado = computed(() => this.ocupada() || !this.cierraConEscape());
  protected readonly confirmandoDescarte = signal(false);

  private readonly ventana = viewChild<ElementRef<HTMLElement>>('ventana');
  private readonly capa = viewChild<ElementRef<HTMLDialogElement>>('capa');
  private readonly botonSeguir = viewChild<ElementRef<HTMLButtonElement>>('botonSeguir');
  /**
   * A dónde devolver el foco al cerrar: donde estaba antes de abrir o, si ya
   * estaba en `<body>` porque el botón que la abrió desapareció, el último
   * control activado.
   */
  private readonly origenDelFoco: HuellaDeControl | null = (() => {
    const activo = document.activeElement;
    if (activo instanceof HTMLElement && activo !== document.body) return huellaDe(activo);
    return ultimoActivado;
  })();

  ngAfterViewInit(): void {
    const capa = this.capa()?.nativeElement;
    if (capa && !capa.open) {
      // Fuera del documento showModal() lanza; entonces se abre sin capa superior.
      if (capa.isConnected && typeof capa.showModal === 'function') capa.showModal();
      else capa.setAttribute('open', '');
    }
    document.body.style.overflow = 'hidden';
    // Al primer elemento enfocable, y si no hay ninguno a la propia ventana:
    // quien navega con teclado tiene que aterrizar dentro.
    const enfocables = this.enfocables();
    (enfocables[0] ?? this.ventana()?.nativeElement)?.focus();
    this.animarEntrada();
  }

  ngOnDestroy(): void {
    this.destruida = true;
    const capa = this.capa()?.nativeElement;
    if (capa?.open && typeof capa.close === 'function') capa.close();
    document.body.style.overflow = '';
    const origen = this.origenDelFoco;
    if (origen?.elemento.isConnected) {
      origen.elemento.focus();
      return;
    }
    // El botón de origen se está recreando en este mismo ciclo: se busca su
    // sustituto cuando Angular termina de pintar, salvo que el foco ya esté en
    // otro sitio (no se le roba a quien siguió trabajando).
    setTimeout(() => {
      const activo = document.activeElement;
      if (activo && activo !== document.body && activo.isConnected) return;
      localizar(origen)?.focus();
    });
  }

  protected alPulsarFondo(evento: MouseEvent): void {
    if (!this.cierraAlPulsarFuera() || this.cierreBloqueado()) {
      return;
    }
    // Solo el fondo. Un clic dentro burbujea hasta aquí y cerraría la ventana
    // al soltar el ratón sobre cualquier texto.
    if (evento.target === evento.currentTarget) {
      this.solicitarCierre();
    }
  }

  /** Escape nativo del dialog: lo cierra quien abrió la ventana, no el navegador. */
  protected alCancelar(evento: Event): void {
    evento.preventDefault();
    if (!this.cierreBloqueado()) this.solicitarCierre();
  }

  /**
   * El navegador cerró el <dialog> por su cuenta.
   *
   * Pasa con el segundo gesto «atrás» de Android: ese `cancel` no se puede
   * cancelar. Si no se podía cerrar (guardado en curso, cambios sin guardar)
   * se vuelve a abrir; si se podía, se avisa a quien la abrió para que su
   * estado no siga creyendo que está abierta.
   */
  protected alCerrarseSola(): void {
    if (this.destruida || this.cerrando) {
      return;
    }
    const capa = this.capa()?.nativeElement;
    if (this.cierreBloqueado() || this.cambiosSinGuardar()) {
      if (capa && !capa.open) {
        if (capa.isConnected && typeof capa.showModal === 'function') capa.showModal();
        else capa.setAttribute('open', '');
      }
      if (this.cambiosSinGuardar() && !this.cierreBloqueado()) this.pedirConfirmacion();
      return;
    }
    this.cerrar.emit();
  }

  protected seguirEditando(): void {
    this.confirmandoDescarte.set(false);
    (this.enfocables().find((elemento) => !elemento.classList.contains('ventana__cerrar')) ?? this.ventana()?.nativeElement)?.focus();
  }

  protected descartar(): void {
    this.confirmandoDescarte.set(false);
    this.solicitarCierre(true);
  }

  private pedirConfirmacion(): void {
    this.confirmandoDescarte.set(true);
    // El botón aparece en el siguiente pintado.
    setTimeout(() => this.botonSeguir()?.nativeElement.focus());
  }

  /**
   * Cierra con salida animada y después avisa a quien abrió la ventana.
   *
   * Es lo que en React hace `AnimatePresence`: Angular quita el componente en
   * cuanto el padre cambia su condición, así que la ventana se retira antes de
   * pedirlo. Sin movimiento (preferencia del sistema o navegador sin WAAPI)
   * avisa en el acto, sin esperar a nada.
   */
  solicitarCierre(descartarCambios = false): void {
    if (this.cerrando || this.cierreBloqueado()) {
      return;
    }
    if (this.cambiosSinGuardar() && !descartarCambios) {
      this.pedirConfirmacion();
      return;
    }
    if (!this.movimiento.activo()) {
      this.cerrar.emit();
      return;
    }
    this.cerrando = true;
    const capa = this.capa()?.nativeElement;
    const ventana = this.ventana()?.nativeElement;
    const salidas: Promise<void>[] = [];
    if (ventana) {
      salidas.push(this.movimiento.salir(ventana, this.forma() === 'centrada' ? 'escala' : 'derecha', 28));
    }
    if (capa) {
      salidas.push(this.movimiento.fundir(capa, 0, 0.2));
    }
    void Promise.all(salidas).then(() => {
      this.cerrar.emit();
      // Quien abrió puede decidir no cerrar (un cambio sin guardar, por
      // ejemplo). Si la ventana sigue viva, vuelve a mostrarse.
      setTimeout(() => this.restaurarSiSigueAbierta(), 80);
    });
  }

  private animarEntrada(): void {
    if (!this.movimiento.activo()) {
      return;
    }
    const capa = this.capa()?.nativeElement;
    const ventana = this.ventana()?.nativeElement;
    if (capa) {
      void this.movimiento.fundir(capa, 1, 0.22);
    }
    if (ventana) {
      void this.movimiento.entrar(ventana, {
        desde: this.forma() === 'centrada' ? 'escala' : 'derecha',
        distancia: 36,
        desenfoque: false,
      });
    }
  }

  private restaurarSiSigueAbierta(): void {
    if (this.destruida) {
      return;
    }
    this.cerrando = false;
    const capa = this.capa()?.nativeElement;
    const ventana = this.ventana()?.nativeElement;
    if (capa) this.movimiento.limpiar(capa);
    if (ventana) this.movimiento.limpiar(ventana);
  }

  protected alTeclear(evento: KeyboardEvent): void {
    if (evento.key === 'Escape') {
      // Sin preventDefault el navegador dispararía también `cancel`.
      evento.preventDefault();
      evento.stopPropagation();
      // Con la confirmación a la vista, Escape es «seguir editando».
      if (this.confirmandoDescarte()) this.seguirEditando();
      else if (!this.cierreBloqueado()) this.solicitarCierre();
      return;
    }
    if (evento.key !== 'Tab') {
      return;
    }
    // El foco se cicla dentro: sin esto se escapa a la lista de detrás y
    // quien navega con teclado deja de saber dónde está.
    const enfocables = this.enfocables();
    if (enfocables.length === 0) {
      return;
    }
    const primero = enfocables[0];
    const ultimo = enfocables[enfocables.length - 1];
    const activo = document.activeElement;
    if (evento.shiftKey && activo === primero) {
      evento.preventDefault();
      ultimo.focus();
    } else if (!evento.shiftKey && activo === ultimo) {
      evento.preventDefault();
      primero.focus();
    }
  }

  private enfocables(): HTMLElement[] {
    const raiz = this.ventana()?.nativeElement ?? this.anfitrion.nativeElement;
    // Se descarta lo que no puede recibir foco. `getClientRects` distingue lo
    // oculto por CSS en navegador; la conexión al documento conserva la
    // navegación de teclado en pruebas sin motor de layout.
    return Array.from(
      raiz.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex^="-"])',
      ),
    ).filter((elemento) => {
      if (elemento.closest('[hidden], [inert], [aria-hidden="true"]')) return false;
      const estilos = elemento.ownerDocument.defaultView?.getComputedStyle(elemento);
      if (
        estilos &&
        (estilos.display === 'none' || estilos.visibility === 'hidden' || estilos.visibility === 'collapse')
      ) {
        return false;
      }
      return elemento.getClientRects().length > 0 || elemento.isConnected;
    });
  }
}
