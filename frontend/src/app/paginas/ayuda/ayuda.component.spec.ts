/**
 * Pruebas de la pantalla de Ayuda.
 *
 * El contenido lo decide el servidor (y tiene sus propias pruebas); aquí se
 * comprueba que la pantalla muestra exactamente lo recibido: un manual por
 * rol, en pestañas si hay varios, con sus tareas, límites y enlaces, y que
 * cubre los estados de carga, vacío y error.
 */
import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { CONFIGURACION } from '../../nucleo/servicios/configuracion';
import { AyudaComponent } from './ayuda.component';
import type { Manual } from './ayuda.service';

const RECEPCION: Manual = {
  rol_codigo: 'recepcion',
  rol_nombre: 'Recepción',
  tipo: 'SISTEMA',
  titulo: 'Manual de Recepción',
  introduccion: 'Recepción es la puerta de entrada de la clínica.',
  responsabilidades: ['Que cada cita quede reservada.'],
  limites: ['No registra contenido clínico.'],
  secciones: [
    {
      clave: 'recepcion.reservar',
      titulo: 'Reservar una cita en un hueco libre',
      ruta: '/agenda',
      proposito: 'Dar una cita con la disponibilidad real.',
      pasos: ['Elija sede y profesional.', 'Confirme la cita.'],
      limites: ['Un hueco retenido vence solo.'],
      permisos: [{ codigo: 'cita.crear', descripcion: 'Crear citas' }],
    },
    {
      clave: 'recepcion.cobros',
      titulo: 'Registrar abonos y comprobantes',
      ruta: '/pagos',
      proposito: 'Llevar el saldo al día.',
      pasos: ['Registre el abono con su método.'],
      limites: [],
      permisos: [],
    },
  ],
};

const PROPIO: Manual = {
  rol_codigo: 'caja_tarde',
  rol_nombre: 'Caja de la tarde',
  tipo: 'PERSONALIZADO',
  titulo: 'Manual del rol Caja de la tarde',
  introduccion: '«Caja de la tarde» es un rol propio de su clínica.',
  responsabilidades: [],
  limites: ['No registra pagos.'],
  secciones: [],
};

describe('AyudaComponent', () => {
  let fixture: ComponentFixture<AyudaComponent>;
  let http: HttpTestingController;

  function texto(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  function responder(manuales: readonly Manual[]): void {
    http.expectOne({ method: 'GET', url: '/api/v1/ayuda/manuales' }).flush({ manuales });
    fixture.detectChanges();
  }

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [AyudaComponent],
      providers: [
        provideHttpClient(withXhr()),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: CONFIGURACION, useValue: { urlApi: '/api/v1' } },
      ],
    });
    fixture = TestBed.createComponent(AyudaComponent);
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  it('anuncia la carga y después muestra el manual del único rol, sin pestañas', () => {
    expect(texto()).toContain('Preparando su manual');

    responder([RECEPCION]);

    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.querySelector('[role="tablist"]')).toBeNull();
    expect(raiz.querySelector('h2')?.textContent).toContain('Manual de Recepción');
    expect(texto()).toContain('No registra contenido clínico.');
    expect(raiz.querySelectorAll('.ayuda__tarea')).toHaveLength(2);
    // La primera tarea viene abierta: el manual se lee sin un clic de más.
    expect(raiz.querySelector('.ayuda__tarea details')?.hasAttribute('open')).toBe(true);
    const enlace = raiz.querySelector<HTMLAnchorElement>('.ayuda__tarea a');
    expect(enlace?.getAttribute('href')).toBe('/agenda');
    expect(enlace?.textContent).toContain('Ir a Agenda');
    expect(texto()).toContain('Crear citas');
  });

  it('con varios roles ofrece una pestaña por manual y cambia con las flechas', () => {
    responder([RECEPCION, PROPIO]);
    const raiz = fixture.nativeElement as HTMLElement;
    const pestanas = Array.from(raiz.querySelectorAll<HTMLButtonElement>('[role="tab"]'));

    expect(pestanas.map((p) => p.textContent?.trim())).toEqual(['Recepción', 'Caja de la tarde']);
    expect(pestanas[0].getAttribute('aria-selected')).toBe('true');
    expect(raiz.querySelector('[role="tabpanel"]')?.getAttribute('aria-labelledby')).toBe('pestana-recepcion');

    pestanas[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    fixture.detectChanges();

    expect(pestanas[1].getAttribute('aria-selected')).toBe('true');
    expect(texto()).toContain('ROL DE SU CLÍNICA');
    expect(texto()).toContain('Este rol no tiene tareas habilitadas todavía.');

    pestanas[1].dispatchEvent(new KeyboardEvent('keydown', { key: 'Home', bubbles: true }));
    fixture.detectChanges();
    expect(pestanas[0].getAttribute('aria-selected')).toBe('true');
  });

  it('filtra las tareas sin distinguir tildes ni mayúsculas', () => {
    responder([RECEPCION]);
    const raiz = fixture.nativeElement as HTMLElement;
    const buscador = raiz.querySelector<HTMLInputElement>('input[type="search"]')!;

    buscador.value = 'METODO';
    buscador.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    const titulos = Array.from(raiz.querySelectorAll('.ayuda__titulos strong')).map((t) => t.textContent);
    expect(titulos).toEqual(['Registrar abonos y comprobantes']);

    buscador.value = 'nada que coincida';
    buscador.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    expect(texto()).toContain('Ninguna tarea coincide');
  });

  it('sin roles vigentes lo dice y explica qué hacer', () => {
    responder([]);
    expect(texto()).toContain('Su cuenta no tiene roles vigentes');
  });

  it('muestra el error y permite reintentar', () => {
    http
      .expectOne('/api/v1/ayuda/manuales')
      .flush({ codigo: 'SEGUNDO_FACTOR_REQUERIDO', mensaje: 'Complete el segundo factor.' }, { status: 403, statusText: 'Forbidden' });
    fixture.detectChanges();

    expect(texto()).toContain('No se pudo cargar la ayuda');
    expect(texto()).toContain('Complete el segundo factor.');

    const reintentar = Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Reintentar'),
    );
    reintentar?.click();
    fixture.detectChanges();
    responder([RECEPCION]);
    expect(texto()).toContain('Manual de Recepción');
  });
  it('expande y contrae las tareas sin salir del manual', () => {
    responder([RECEPCION]);
    fixture.componentInstance['alternarTodas'](); fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('details[open]')).toHaveLength(2);
    expect(texto()).toContain('Contraer todas');
    fixture.componentInstance['alternarTodas'](); fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('details[open]')).toHaveLength(0);
    expect(texto()).toContain('Expandir todas');
  });
  it('filtrar abre coincidencias y limpiar devuelve el foco al buscador', () => {
    responder([RECEPCION]);
    const campo: HTMLInputElement = fixture.nativeElement.querySelector('input[type="search"]');
    campo.value = 'METODO'; campo.dispatchEvent(new Event('input')); fixture.detectChanges();
    expect(texto()).toContain('Mostrando 1 de 2 tareas');
    expect(fixture.nativeElement.querySelector('details').open).toBe(true);
    const limpiar = [...fixture.nativeElement.querySelectorAll('button')].find((b: unknown) => (b as HTMLElement).textContent?.includes('Limpiar búsqueda')) as HTMLButtonElement;
    limpiar.click(); fixture.detectChanges();
    expect(campo.value).toBe('');
    expect(document.activeElement).toBe(campo);
    expect(texto()).toContain('Mostrando 2 de 2 tareas');
  });
  it('la apertura masiva afecta solo a las tareas visibles', () => {
    responder([RECEPCION]);
    fixture.componentInstance['filtrar']('comprobantes'); fixture.detectChanges();
    fixture.componentInstance['alternarTodas'](); fixture.detectChanges();
    expect(fixture.componentInstance['abiertas']().has('recepcion.reservar')).toBe(true);
    expect(fixture.componentInstance['abiertas']().has('recepcion.cobros')).toBe(false);
  });
  it('la apertura individual actualiza el control de todas las tareas', () => {
    responder([RECEPCION]);
    const segunda: HTMLDetailsElement = fixture.nativeElement.querySelectorAll('details')[1];
    segunda.open = true; segunda.dispatchEvent(new Event('toggle')); fixture.detectChanges();
    expect(texto()).toContain('Contraer todas');
    segunda.open = false; segunda.dispatchEvent(new Event('toggle')); fixture.detectChanges();
    expect(texto()).toContain('Expandir todas');
  });
  it('cambiar de rol descarta el filtro, la apertura y los eventos del anterior', () => {
    responder([RECEPCION, PROPIO]);
    const anterior: HTMLDetailsElement = fixture.nativeElement.querySelector('details');
    fixture.componentInstance['filtrar']('abonos'); fixture.componentInstance['elegir'](1); fixture.detectChanges();
    anterior.dispatchEvent(new Event('toggle')); fixture.detectChanges();
    expect(fixture.componentInstance['abiertas']().size).toBe(0);
    expect(fixture.componentInstance['filtro']()).toBe('');
    expect(fixture.nativeElement.querySelector('.ayuda__identidad img').getAttribute('src')).toBe('/images/acceso-icono-seguridad.webp');
    expect(texto()).not.toContain('Registrar abonos');
    fixture.componentInstance['elegir'](0); fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('details[open]')).toHaveLength(1);
  });
  it('cambiar manuales conserva la lista textual y no emite NG0956', () => {
    const advertencias = vi.spyOn(console, 'warn');
    try {
      responder([RECEPCION, PROPIO]);
      const elemento = fixture.nativeElement.querySelector('.ayuda__limites li');
      fixture.componentInstance['elegir'](1); fixture.detectChanges();
      expect(fixture.nativeElement.querySelector('.ayuda__limites li')).toBe(elemento);
      expect(elemento.textContent).toBe('No registra pagos.');
      expect(advertencias.mock.calls.some(args => args.some(a => String(a).includes('NG0956')))).toBe(false);
    } finally { advertencias.mockRestore(); }
  });
});
