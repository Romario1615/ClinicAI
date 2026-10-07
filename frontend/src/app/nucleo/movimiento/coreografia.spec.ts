/**
 * Pruebas de la coreografía global.
 *
 * Se prueba con un motor de mentira: lo que importa aquí no es cómo se mueve
 * un elemento (eso es Motion), sino **qué** se decide mover. Cada prueba fija
 * una regla que, rota, se notaría como una interfaz que tiembla, que anima
 * doscientas filas o que anima con el movimiento reducido activado.
 */
import { Coreografia, fueraDeCoreografia, superiores, type MotorCoreografia } from './coreografia';

/** Deja correr las microtareas: el MutationObserver avisa en una. */
async function esperarMutaciones(): Promise<void> {
  await new Promise((resolver) => setTimeout(resolver, 0));
}

function crear(html: string): HTMLElement {
  const plantilla = document.createElement('template');
  plantilla.innerHTML = html.trim();
  return plantilla.content.firstElementChild as HTMLElement;
}

describe('Coreografia', () => {
  let raiz: HTMLElement;
  let motor: {
    entrarEscalonado: ReturnType<typeof vi.fn>;
    crecer: ReturnType<typeof vi.fn>;
    presionar: ReturnType<typeof vi.fn>;
    soltar: ReturnType<typeof vi.fn>;
  };
  let activo: boolean;
  let coreografia: Coreografia;

  beforeEach(() => {
    raiz = document.createElement('main');
    document.body.appendChild(raiz);
    motor = {
      entrarEscalonado: vi.fn(() => Promise.resolve()),
      crecer: vi.fn(() => Promise.resolve()),
      presionar: vi.fn(),
      soltar: vi.fn(),
    };
    activo = true;
    coreografia = new Coreografia({
      documento: document,
      motor: motor as unknown as MotorCoreografia,
      activo: () => activo,
      fueraDeAngular: (funcion) => funcion(),
    });
    coreografia.iniciar(raiz);
  });

  afterEach(() => {
    coreografia.detener();
    raiz.remove();
  });

  it('hace entrar los bloques que llegan, sin repetir los que van dentro de otro', async () => {
    raiz.appendChild(
      crear(`
        <section>
          <header class="modulo-cabecera"><h1>Agenda</h1></header>
          <div class="tarjeta"><div class="tarjeta">anidada</div></div>
        </section>`),
    );
    await esperarMutaciones();

    expect(motor.entrarEscalonado).toHaveBeenCalledTimes(1);
    const [bloques] = motor.entrarEscalonado.mock.calls[0] as [Element[]];
    // La tarjeta anidada se mueve con su madre: animarla aparte se ve como
    // un temblor dentro del panel.
    expect(bloques.map((bloque) => bloque.className)).toEqual(['modulo-cabecera', 'tarjeta']);
  });

  it('no anima nada con el movimiento reducido', async () => {
    activo = false;
    raiz.appendChild(crear('<div class="tarjeta">quieta</div>'));
    await esperarMutaciones();

    expect(motor.entrarEscalonado).not.toHaveBeenCalled();
  });

  it('deja quieto el interior de las ventanas flotantes y lo marcado sin movimiento', async () => {
    raiz.appendChild(crear('<dialog open><div class="tarjeta">ficha</div></dialog>'));
    raiz.appendChild(crear('<div data-sin-movimiento><div class="tarjeta">quieta</div></div>'));
    await esperarMutaciones();

    expect(motor.entrarEscalonado).not.toHaveBeenCalled();
  });

  it('limita las filas por tanda y las mueve con menos recorrido que un bloque', async () => {
    const tabla = crear('<table class="tabla"><tbody></tbody></table>');
    raiz.appendChild(tabla);
    await esperarMutaciones();
    motor.entrarEscalonado.mockClear();

    const cuerpo = tabla.querySelector('tbody')!;
    for (let indice = 0; indice < 40; indice++) {
      cuerpo.appendChild(crear(`<table><tbody><tr><td>${indice}</td></tr></tbody></table>`).querySelector('tr')!);
    }
    await esperarMutaciones();

    expect(motor.entrarEscalonado).toHaveBeenCalledTimes(1);
    const [filas, opciones] = motor.entrarEscalonado.mock.calls[0] as [Element[], { distancia: number; desenfoque: boolean }];
    expect(filas).toHaveLength(18);
    expect(opciones.distancia).toBe(6);
    expect(opciones.desenfoque).toBe(false);
  });

  it('limita los bloques por tanda', async () => {
    const rejilla = crear('<div class="rejilla"></div>');
    for (let indice = 0; indice < 30; indice++) {
      rejilla.appendChild(crear(`<article>${indice}</article>`));
    }
    raiz.appendChild(crear('<section></section>')).appendChild(rejilla);
    await esperarMutaciones();

    const [bloques] = motor.entrarEscalonado.mock.calls.at(-1) as [Element[]];
    expect(bloques).toHaveLength(14);
  });

  it('hace crecer las barras de un gráfico que llega, después de su bloque', async () => {
    raiz.appendChild(
      crear(`
        <section class="tarjeta">
          <span class="tendencia__pista"><span style="width: 40%"></span></span>
          <span class="tendencia__pista"><span style="width: 90%"></span></span>
          <span data-crecer></span>
        </section>`),
    );
    await esperarMutaciones();

    expect(motor.crecer).toHaveBeenCalledTimes(1);
    const [barras, retraso] = motor.crecer.mock.calls[0] as [Element[], number];
    expect(barras).toHaveLength(3);
    expect(retraso).toBeGreaterThan(0);
  });

  it('cede al pulsar un botón y vuelve al soltarlo', () => {
    const boton = crear('<button class="boton" type="button"><span>Guardar</span></button>');
    raiz.appendChild(boton);

    boton.querySelector('span')!.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, button: 0 }));
    document.dispatchEvent(new MouseEvent('pointerup', { bubbles: true }));

    expect(motor.presionar).toHaveBeenCalledWith(boton);
    expect(motor.soltar).toHaveBeenCalledWith(boton);
  });

  it('no reacciona a un botón deshabilitado ni al botón secundario del ratón', () => {
    const deshabilitado = crear('<button class="boton" type="button" disabled>No</button>');
    const normal = crear('<button class="boton" type="button">Sí</button>');
    raiz.append(deshabilitado, normal);

    deshabilitado.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, button: 0 }));
    normal.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, button: 2 }));

    expect(motor.presionar).not.toHaveBeenCalled();
  });

  it('deja de observar al detenerse', async () => {
    coreografia.detener();
    raiz.appendChild(crear('<div class="tarjeta">tarde</div>'));
    await esperarMutaciones();

    expect(motor.entrarEscalonado).not.toHaveBeenCalled();
  });
});

describe('superiores', () => {
  it('conserva solo los elementos que no están dentro de otro de la lista', () => {
    const exterior = crear('<div><p><span></span></p></div>');
    const parrafo = exterior.querySelector('p')!;
    const tramo = exterior.querySelector('span')!;
    const suelto = document.createElement('aside');

    expect(superiores([tramo, parrafo, exterior, suelto, exterior])).toEqual([exterior, suelto]);
  });
});

describe('fueraDeCoreografia', () => {
  it('reconoce el interior de un diálogo y lo marcado como quieto', () => {
    const dialogo = crear('<dialog><p>dentro</p></dialog>');
    const quieto = crear('<div data-sin-movimiento><p>dentro</p></div>');
    const libre = crear('<div><p>fuera</p></div>');

    expect(fueraDeCoreografia(dialogo.querySelector('p')!)).toBe(true);
    expect(fueraDeCoreografia(quieto.querySelector('p')!)).toBe(true);
    expect(fueraDeCoreografia(libre.querySelector('p')!)).toBe(false);
  });
});
