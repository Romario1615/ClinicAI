/**
 * Pruebas de la ventana flotante.
 *
 * Aquí no se comprueba estética: se comprueba que quien navega con teclado no
 * se queda atrapado ni perdido. Cada una fija una afirmación concreta del
 * componente, y todas son cosas que se rompen sin darse cuenta al refactorizar.
 */
import { Component, signal, ChangeDetectionStrategy } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { MovimientoService } from '../nucleo/movimiento/movimiento.service';
import { VentanaFlotanteComponent } from './ventana-flotante.component';

@Component({
    standalone: true,
    imports: [VentanaFlotanteComponent],
    changeDetection: ChangeDetectionStrategy.Eager,
    template: `
    <button type="button" id="origen" #origen>Abrir</button>
    @if (abierta()) {
      <app-ventana-flotante
        titulo="Ficha de prueba"
        ceja="Paciente"
        [forma]="forma()"
        [cierraAlPulsarFuera]="cierraFuera()"
        [cierraConEscape]="cierraEscape()"
        [ocupada]="ocupada()"
        [cambiosSinGuardar]="sinGuardar()"
        [error]="error()"
        (cerrar)="abierta.set(false)"
      >
        <button type="button" id="primero">Uno</button>
        <button type="button" id="ultimo">Dos</button>
        <div aria-hidden="true"><button type="button" id="oculto-aria">Oculto semánticamente</button></div>
        <button type="button" id="oculto-display" style="display: none">Oculto por display</button>
        <button type="button" id="oculto-visibilidad" style="visibility: hidden">Oculto por visibilidad</button>
      </app-ventana-flotante>
    }
  `,
})
class AnfitrionComponent {
    readonly abierta = signal(false);
    readonly forma = signal<'lateral' | 'centrada'>('lateral');
    readonly cierraFuera = signal(true);
    readonly cierraEscape = signal(true);
    readonly ocupada = signal(false);
    readonly sinGuardar = signal(false);
    readonly error = signal<string | null>(null);
}

/** El botón que abre desaparece mientras la ventana está abierta. */
@Component({
    standalone: true,
    imports: [VentanaFlotanteComponent],
    changeDetection: ChangeDetectionStrategy.Eager,
    template: `
    @if (!abierta()) {
      <button type="button" class="disparador" (click)="abierta.set(true)">Nueva nota</button>
    } @else {
      <app-ventana-flotante titulo="Nota" (cerrar)="abierta.set(false)">
        <button type="button">Dentro</button>
      </app-ventana-flotante>
    }
  `,
})
class DisparadorQueDesapareceComponent {
    readonly abierta = signal(false);
}

describe('VentanaFlotanteComponent', () => {
    let fixture: ComponentFixture<AnfitrionComponent>;

    function elemento(): HTMLElement {
        return fixture.nativeElement as HTMLElement;
    }

    function abrir(): void {
        elemento().querySelector<HTMLButtonElement>('#origen')?.focus();
        fixture.componentInstance.abierta.set(true);
        fixture.detectChanges();
    }

    beforeEach(() => {
        TestBed.configureTestingModule({ imports: [AnfitrionComponent] });
        fixture = TestBed.createComponent(AnfitrionComponent);
        fixture.detectChanges();
    });

    afterEach(() => {
        // Si una prueba dejara el `overflow` puesto, la siguiente pantalla del
        // navegador de pruebas no se podria desplazar.
        expect(document.body.style.overflow).not.toBe('hidden');
    });

    it('anuncia que es un diálogo modal y con qué título', () => {
        abrir();

        const dialogo = elemento().querySelector('[role="dialog"]');
        expect(dialogo).not.toBeNull();
        expect(dialogo?.getAttribute('aria-modal')).toBe('true');
        expect(dialogo?.getAttribute('aria-label')).toBe('Ficha de prueba');
        fixture.componentInstance.abierta.set(false);
        fixture.detectChanges();
    });

    it('mete el foco dentro al abrir, en el primer elemento enfocable', () => {
        abrir();

        // Sin esto, quien navega con teclado abre la ventana y sigue tabulando por
        // la lista de detrás sin saber que hay algo abierto.
        //
        // El primero es el botón de cerrar de la cabecera, no el contenido, y eso
        // es lo correcto: la salida queda a una pulsación de Enter.
        expect(document.activeElement?.classList.contains('ventana__cerrar')).toBe(true);
        fixture.componentInstance.abierta.set(false);
        fixture.detectChanges();
    });

    it('devuelve el foco a donde estaba al cerrarse', () => {
        abrir();
        fixture.componentInstance.abierta.set(false);
        fixture.detectChanges();

        expect(document.activeElement?.id).toBe('origen');
    });

    it('cierra con Escape', () => {
        abrir();

        elemento()
            .querySelector('[role="dialog"]')
            ?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        fixture.detectChanges();

        expect(fixture.componentInstance.abierta()).toBe(false);
    });

    it('cicla el foco: del último vuelve al primero', () => {
        abrir();
        // `#ultimo` es el último del DOM dentro de la ventana.
        elemento().querySelector<HTMLButtonElement>('#ultimo')?.focus();

        const evento = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
        elemento().querySelector('[role="dialog"]')?.dispatchEvent(evento);
        fixture.detectChanges();

        expect(evento.defaultPrevented).toBe(true);
        // Vuelve al botón de cerrar, que es el primero de la ventana.
        expect(document.activeElement?.classList.contains('ventana__cerrar')).toBe(true);
        fixture.componentInstance.abierta.set(false);
        fixture.detectChanges();
    });

    it('excluye los controles ocultos del ciclo de teclado', () => {
        abrir();
        elemento().querySelector<HTMLButtonElement>('#ultimo')?.focus();

        const evento = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
        elemento().querySelector('[role="dialog"]')?.dispatchEvent(evento);
        fixture.detectChanges();

        expect(evento.defaultPrevented).toBe(true);
        expect(document.activeElement?.classList.contains('ventana__cerrar')).toBe(true);
        fixture.componentInstance.abierta.set(false);
        fixture.detectChanges();
    });

    it('con Shift+Tab en el primero salta al último', () => {
        abrir();
        // El primero es el botón de cerrar; desde él, hacia atrás, se va al final.
        elemento().querySelector<HTMLButtonElement>('.ventana__cerrar')?.focus();

        const evento = new KeyboardEvent('keydown', {
            key: 'Tab',
            shiftKey: true,
            bubbles: true,
            cancelable: true,
        });
        elemento().querySelector('[role="dialog"]')?.dispatchEvent(evento);
        fixture.detectChanges();

        expect(document.activeElement?.id).toBe('ultimo');
        fixture.componentInstance.abierta.set(false);
        fixture.detectChanges();
    });

    it('cierra al pulsar el fondo', () => {
        abrir();

        elemento().querySelector<HTMLElement>('.capa')?.click();
        fixture.detectChanges();

        expect(fixture.componentInstance.abierta()).toBe(false);
    });

    it('permite impedir Escape mientras hay una operación en curso', () => {
        fixture.componentInstance.cierraEscape.set(false);
        abrir();

        const evento = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
        elemento().querySelector('[role="dialog"]')?.dispatchEvent(evento);
        fixture.detectChanges();

        expect(evento.defaultPrevented).toBe(true);
        expect(fixture.componentInstance.abierta()).toBe(true);
        fixture.componentInstance.abierta.set(false);
        fixture.detectChanges();
    });

    it('mientras está ocupada no se cierra ni con Escape, ni con la X, ni por el fondo', () => {
        fixture.componentInstance.ocupada.set(true);
        abrir();
        const cerrar = elemento().querySelector<HTMLButtonElement>('.ventana__cerrar')!;
        expect(cerrar.disabled).toBe(true);

        elemento().querySelector('[role="dialog"]')?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
        elemento().querySelector<HTMLElement>('.capa')?.click();
        fixture.detectChanges();
        expect(fixture.componentInstance.abierta()).toBe(true);

        fixture.componentInstance.ocupada.set(false);
        fixture.detectChanges();
        expect(cerrar.disabled).toBe(false);
        cerrar.click();
        fixture.detectChanges();
        expect(fixture.componentInstance.abierta()).toBe(false);
    });

    it('con cambios sin guardar pide confirmación antes de descartar', async () => {
        fixture.componentInstance.sinGuardar.set(true);
        abrir();

        elemento().querySelector('[role="dialog"]')?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
        fixture.detectChanges();
        expect(fixture.componentInstance.abierta()).toBe(true);
        const aviso = elemento().querySelector('[role="alertdialog"]');
        expect(aviso?.textContent).toContain('Hay cambios sin guardar');
        await new Promise((resolver) => setTimeout(resolver));
        expect(document.activeElement?.textContent?.trim()).toBe('Seguir editando');

        // Escape con la confirmación a la vista equivale a seguir editando.
        elemento().querySelector('[role="dialog"]')?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
        fixture.detectChanges();
        expect(elemento().querySelector('[role="alertdialog"]')).toBeNull();
        expect(fixture.componentInstance.abierta()).toBe(true);

        elemento().querySelector<HTMLButtonElement>('.ventana__cerrar')!.click();
        fixture.detectChanges();
        Array.from(elemento().querySelectorAll<HTMLButtonElement>('[role="alertdialog"] button'))
            .find((boton) => boton.textContent?.includes('Descartar'))!
            .click();
        fixture.detectChanges();
        expect(fixture.componentInstance.abierta()).toBe(false);
    });

    it('muestra el error dentro de la ventana, anunciado', () => {
        fixture.componentInstance.error.set('No se pudo guardar la nota.');
        abrir();

        const alerta = elemento().querySelector('dialog [role="alert"]');
        expect(alerta?.textContent).toContain('No se pudo guardar la nota.');
        fixture.componentInstance.abierta.set(false);
        fixture.detectChanges();
    });

    it('si el navegador la cierra por su cuenta durante un guardado, vuelve a abrirla', () => {
        fixture.componentInstance.ocupada.set(true);
        abrir();
        const dialogo = elemento().querySelector<HTMLDialogElement>('dialog')!;

        dialogo.removeAttribute('open');
        dialogo.dispatchEvent(new Event('close'));
        fixture.detectChanges();

        expect(fixture.componentInstance.abierta()).toBe(true);
        expect(dialogo.hasAttribute('open')).toBe(true);
        fixture.componentInstance.abierta.set(false);
        fixture.detectChanges();
    });

    it('si el navegador la cierra por su cuenta sin nada que proteger, avisa a quien la abrió', () => {
        abrir();

        elemento().querySelector('dialog')!.dispatchEvent(new Event('close'));
        fixture.detectChanges();

        expect(fixture.componentInstance.abierta()).toBe(false);
    });

    it('devuelve el foco al botón que la abrió aunque haya desaparecido y vuelto', async () => {
        const anfitrion = TestBed.createComponent(DisparadorQueDesapareceComponent);
        anfitrion.detectChanges();
        const raiz = anfitrion.nativeElement as HTMLElement;
        const disparador = raiz.querySelector<HTMLButtonElement>('.disparador')!;
        disparador.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
        disparador.click();
        anfitrion.detectChanges();

        anfitrion.componentInstance.abierta.set(false);
        anfitrion.detectChanges();
        await new Promise((resolver) => setTimeout(resolver));

        const nuevo = raiz.querySelector<HTMLButtonElement>('.disparador');
        expect(nuevo).not.toBe(disparador);
        expect(document.activeElement).toBe(nuevo);
    });

    it('tabular en medio de la ventana no la secuestra', () => {
        // Solo se intercepta en los extremos: en medio, el navegador hace su
        // trabajo y forzarlo produciría saltos raros.
        abrir();
        elemento().querySelector<HTMLButtonElement>('#primero')?.focus();

        const evento = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
        elemento().querySelector('[role="dialog"]')?.dispatchEvent(evento);
        fixture.detectChanges();

        expect(evento.defaultPrevented).toBe(false);
        fixture.componentInstance.abierta.set(false);
        fixture.detectChanges();
    });

    it('un clic dentro no la cierra', () => {
        // El clic burbujea hasta el fondo: sin comprobar el origen, soltar el
        // ratón sobre cualquier texto cerraría la ventana.
        abrir();

        elemento().querySelector<HTMLButtonElement>('#primero')?.click();
        fixture.detectChanges();

        expect(fixture.componentInstance.abierta()).toBe(true);
        fixture.componentInstance.abierta.set(false);
        fixture.detectChanges();
    });

    it('no cierra por el fondo cuando hay algo a medio escribir', () => {
        fixture.componentInstance.cierraFuera.set(false);
        abrir();

        elemento().querySelector<HTMLElement>('.capa')?.click();
        fixture.detectChanges();

        expect(fixture.componentInstance.abierta()).toBe(true);
        fixture.componentInstance.abierta.set(false);
        fixture.detectChanges();
    });

    it('bloquea el desplazamiento del fondo mientras está abierta', () => {
        abrir();
        expect(document.body.style.overflow).toBe('hidden');

        fixture.componentInstance.abierta.set(false);
        fixture.detectChanges();
        expect(document.body.style.overflow).toBe('');
    });

    it('la forma centrada tapa el contexto a propósito', () => {
        fixture.componentInstance.forma.set('centrada');
        abrir();

        expect(elemento().querySelector('.capa')?.classList.contains('capa--centrada')).toBe(true);
        fixture.componentInstance.abierta.set(false);
        fixture.detectChanges();
    });
});

/**
 * Con movimiento activo la ventana se retira antes de avisar, como
 * `AnimatePresence`. Se usa un servicio de movimiento de mentira: aquí se
 * comprueba el orden (primero la salida, después `cerrar`), no la animación.
 */
describe('VentanaFlotanteComponent con movimiento', () => {
    let fixture: ComponentFixture<AnfitrionComponent>;
    let salidaPendiente: (() => void) | null;
    const movimiento = {
        activo: () => true,
        entrar: vi.fn(() => Promise.resolve()),
        fundir: vi.fn(() => Promise.resolve()),
        limpiar: vi.fn(),
        salir: vi.fn(
            () =>
                new Promise<void>((resolver) => {
                    salidaPendiente = resolver;
                }),
        ),
    };

    beforeEach(() => {
        salidaPendiente = null;
        vi.clearAllMocks();
        TestBed.configureTestingModule({
            imports: [AnfitrionComponent],
            providers: [{ provide: MovimientoService, useValue: movimiento }],
        });
        fixture = TestBed.createComponent(AnfitrionComponent);
        fixture.detectChanges();
        fixture.componentInstance.abierta.set(true);
        fixture.detectChanges();
    });

    it('entra con resorte y avisa del cierre solo cuando la salida ha terminado', async () => {
        expect(movimiento.entrar).toHaveBeenCalledTimes(1);

        const dialogo = (fixture.nativeElement as HTMLElement).querySelector('[role="dialog"]');
        dialogo?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        // Un segundo Escape durante la salida no la repite.
        dialogo?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        fixture.detectChanges();

        expect(movimiento.salir).toHaveBeenCalledTimes(1);
        expect(fixture.componentInstance.abierta()).toBe(true);

        salidaPendiente?.();
        await fixture.whenStable();
        fixture.detectChanges();

        expect(fixture.componentInstance.abierta()).toBe(false);
    });

    it('vuelve a mostrarse si quien la abrió decide no cerrarla', async () => {
        vi.useFakeTimers();
        try {
            // El anfitrión ignora el aviso: la ventana sigue viva.
            fixture.componentInstance.abierta.set(true);
            const ventana = fixture.debugElement.children
                .map((hijo) => hijo.componentInstance)
                .find((instancia): instancia is VentanaFlotanteComponent => instancia instanceof VentanaFlotanteComponent);
            ventana!.cerrar.subscribe(() => fixture.componentInstance.abierta.set(true));

            ventana!.solicitarCierre();
            salidaPendiente?.();
            await vi.runAllTimersAsync();

            expect(movimiento.limpiar).toHaveBeenCalledTimes(2);
            expect(fixture.componentInstance.abierta()).toBe(true);
        } finally {
            vi.useRealTimers();
            fixture.componentInstance.abierta.set(false);
            fixture.detectChanges();
        }
    });
});
