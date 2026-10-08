/**
 * Pruebas de Gastos y caja.
 *
 * Se comprueba lo que la pantalla decide: qué pide a la API (periodo con
 * `hasta` exclusivo, clave de idempotencia), qué muestra según los permisos
 * (sin `pago.leer` no hay flujo; sin `gasto.registrar` no hay botones) y que
 * un gasto se anula con motivo en lugar de editarse.
 */
import { HttpTestingController } from '@angular/common/http/testing';
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { provideHttpClient, withXhr } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';

import { BASE, identidadCon } from '../../nucleo/pruebas/sesion-sintetica';
import { CONFIGURACION, CONFIGURACION_POR_DEFECTO } from '../../nucleo/servicios/configuracion';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { hoyEnZona, sumarDias } from '../../nucleo/utilidades/fechas';
import { GastosComponent } from './gastos.component';
import type { FlujoCaja, Gasto } from './gastos.service';

const GASTO: Gasto = {
  id: 'g-1',
  sede_id: null,
  fecha: '2026-10-05',
  categoria: 'INSUMOS',
  descripcion: 'Guantes sintéticos',
  proveedor: 'Proveedor ficticio',
  importe: '84.30',
  moneda: 'USD',
  metodo: 'TRANSFERENCIA',
  referencia: 'FAC-1',
  estado: 'REGISTRADO',
  creado_en: '2026-10-05T15:00:00Z',
  anulado_en: null,
  motivo_anulacion: null,
};

const FLUJO: FlujoCaja = {
  desde: '2026-10-01',
  hasta: '2026-10-08',
  moneda: 'USD',
  ingresos: '150.00',
  gastos: '84.30',
  resultado: '65.70',
  margen_porcentaje: '43.8',
  por_dia: [{ fecha: '2026-10-05', ingresos: '150.00', gastos: '84.30', resultado: '65.70' }],
  por_categoria: [{ categoria: 'INSUMOS', total: '84.30', cantidad: 1 }],
  base: 'Base de caja: prueba.',
};

describe('GastosComponent', () => {
  let fixture: ComponentFixture<GastosComponent>;
  let http: HttpTestingController;

  function iniciar(permisos: readonly string[]): void {
    TestBed.configureTestingModule({
      imports: [GastosComponent],
      providers: [
        provideHttpClient(withXhr()),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
      ],
    });
    TestBed.inject(SesionService).establecerIdentidad(identidadCon(permisos));
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(GastosComponent);
    fixture.detectChanges();
    http.expectOne(`${BASE}/catalogo/sedes`).flush([{ id: 's-1', nombre: 'Sede Centro', direccion: null, zona_horaria: 'America/Guayaquil' }]);
    http.expectOne(`${BASE}/catalogo/clinica`).flush({
      id: 'c-1',
      nombre: 'Clínica sintética',
      zona_horaria: 'America/Guayaquil',
      idioma: 'es',
      moneda: 'USD',
      telefono: null,
      correo: null,
    });
  }

  function texto(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  afterEach(() => http.verify());

  it('pide el mes en curso con hasta exclusivo y muestra flujo, gráficos y libro', () => {
    iniciar(['gasto.leer', 'gasto.registrar', 'pago.leer']);
    const hoy = hoyEnZona('America/Guayaquil');

    const libro = http.expectOne((peticion) => peticion.url === `${BASE}/gastos`);
    expect(libro.request.params.get('desde')).toBe(`${hoy.slice(0, 8)}01`);
    expect(libro.request.params.get('hasta')).toBe(sumarDias(hoy, 1));
    libro.flush({ elementos: [GASTO], total: 1, importe_total: '84.30' });
    http.expectOne((peticion) => peticion.url === `${BASE}/gastos/flujo`).flush(FLUJO);
    fixture.detectChanges();

    expect(texto()).toContain('Resultado de caja');
    expect(texto()).toContain('Guantes sintéticos');
    expect(texto()).toContain('Gastos por categoría');
    expect((fixture.nativeElement as HTMLElement).querySelectorAll('[data-crecer]').length).toBeGreaterThan(0);
    expect(texto()).toContain('Base de caja: prueba.');
    expect(texto()).toContain('Anular');
  });

  it('en escritorio estrecho deja el ancho al libro y abre los movimientos en una ventana', () => {
    // jsdom no implementa matchMedia: se simula una pantalla de 1024 px.
    const original = window.matchMedia;
    window.matchMedia = ((consulta: string) => ({
      matches: true, media: consulta, addEventListener: () => undefined, removeEventListener: () => undefined,
    })) as unknown as typeof window.matchMedia;
    try {
      iniciar(['gasto.leer', 'gasto.registrar', 'pago.leer']);
      http.expectOne((peticion) => peticion.url === `${BASE}/gastos`).flush({ elementos: [GASTO], total: 1, importe_total: '84.30' });
      http.expectOne((peticion) => peticion.url === `${BASE}/gastos/flujo`).flush(FLUJO);
      fixture.detectChanges();

      const raiz = fixture.nativeElement as HTMLElement;
      expect(raiz.querySelector('.gastos__flujo')).toBeNull();
      expect(texto()).not.toContain('Gastos por categoría');
      Array.from(raiz.querySelectorAll('button')).find((b) => b.textContent?.includes('Movimientos del periodo'))!.click();
      fixture.detectChanges();

      const ventana = raiz.querySelector('app-ventana-flotante') as HTMLElement;
      expect(ventana.textContent).toContain('Gastos por categoría');
      expect(ventana.textContent).toContain('Resultado de caja');
      expect(raiz.querySelectorAll('#titulo-categorias').length).toBe(1);
    } finally {
      window.matchMedia = original;
    }
  });

  it('sin pago.leer no calcula el flujo y sin gasto.registrar no ofrece escribir', () => {
    iniciar(['gasto.leer']);

    http.expectOne((peticion) => peticion.url === `${BASE}/gastos`).flush({ elementos: [GASTO], total: 1, importe_total: '84.30' });
    http.expectNone((peticion) => peticion.url === `${BASE}/gastos/flujo`);
    fixture.detectChanges();

    expect(texto()).not.toContain('Resultado de caja');
    expect(texto()).not.toContain('Registrar gasto');
    expect(texto()).not.toContain('Anular');
  });

  it('registra con clave de idempotencia y recarga libro y flujo', async () => {
    iniciar(['gasto.leer', 'gasto.registrar', 'pago.leer']);
    http.expectOne((peticion) => peticion.url === `${BASE}/gastos`).flush({ elementos: [], total: 0, importe_total: '0' });
    http.expectOne((peticion) => peticion.url === `${BASE}/gastos/flujo`).flush({ ...FLUJO, por_dia: [], por_categoria: [] });
    fixture.detectChanges();
    expect(texto()).toContain('Sin gastos en este periodo');

    const raiz = fixture.nativeElement as HTMLElement;
    Array.from(raiz.querySelectorAll('button')).find((b) => b.textContent?.includes('Registrar gasto'))!.click();
    fixture.detectChanges();
    // ngModel registra sus controles en una microtarea: hasta entonces no
    // escucha lo que se escribe.
    await fixture.whenStable();
    const ventana = raiz.querySelector('app-ventana-flotante') as HTMLElement;
    expect(ventana.querySelector<HTMLButtonElement>('.ventana__pie button[type="submit"]')?.form?.id).toBe('formulario-gasto');
    const escribir = (nombre: string, valor: string) => {
      const campo = ventana.querySelector<HTMLInputElement>(`[name="${nombre}"]`)!;
      campo.value = valor;
      campo.dispatchEvent(new Event('input'));
    };
    escribir('importe', '12.5');
    escribir('descripcion', 'Material de limpieza');
    fixture.detectChanges();
    ventana.querySelector('form')!.dispatchEvent(new Event('submit'));
    fixture.detectChanges();

    const alta = http.expectOne((peticion) => peticion.method === 'POST' && peticion.url === `${BASE}/gastos`);
    expect(alta.request.headers.get('Idempotency-Key')).toMatch(/^gasto-/);
    expect(alta.request.body).toEqual(
      expect.objectContaining({ importe: '12.50', descripcion: 'Material de limpieza', categoria: 'INSUMOS', sede_id: null }),
    );
    alta.flush({ ...GASTO, descripcion: 'Material de limpieza', importe: '12.50' });
    fixture.detectChanges();

    http.expectOne((peticion) => peticion.method === 'GET' && peticion.url === `${BASE}/gastos`).flush({ elementos: [], total: 0, importe_total: '0' });
    http.expectOne((peticion) => peticion.url === `${BASE}/gastos/flujo`).flush(FLUJO);
    fixture.detectChanges();
    expect(texto()).toContain('Gasto registrado: Material de limpieza');
  });

  it('anula con motivo y muestra el error del servidor si falla', async () => {
    iniciar(['gasto.leer', 'gasto.registrar']);
    http.expectOne((peticion) => peticion.url === `${BASE}/gastos`).flush({ elementos: [GASTO], total: 1, importe_total: '84.30' });
    fixture.detectChanges();

    const raiz = fixture.nativeElement as HTMLElement;
    Array.from(raiz.querySelectorAll('button')).find((b) => b.textContent?.trim() === 'Anular')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    const motivo = raiz.querySelector<HTMLTextAreaElement>('textarea[name="motivo"]')!;
    motivo.value = 'Registrado dos veces';
    motivo.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    raiz.querySelector('app-ventana-flotante form')!.dispatchEvent(new Event('submit'));

    const anulacion = http.expectOne(`${BASE}/gastos/g-1/anulacion`);
    expect(anulacion.request.body).toEqual({ motivo: 'Registrado dos veces' });
    anulacion.flush({ codigo: 'CONFLICTO_ESTADO', mensaje: 'El gasto ya estaba anulado.' }, { status: 409, statusText: 'Conflict' });
    fixture.detectChanges();

    expect(texto()).toContain('El gasto ya estaba anulado.');
  });

  it('pagina el libro de veinticinco en veinticinco', () => {
    iniciar(['gasto.leer']);
    http.expectOne((peticion) => peticion.url === `${BASE}/gastos`).flush({ elementos: [GASTO], total: 60, importe_total: '84.30' });
    fixture.detectChanges();
    expect(texto()).toContain('Página 1 de 3');

    const raiz = fixture.nativeElement as HTMLElement;
    Array.from(raiz.querySelectorAll('button')).find((b) => b.textContent?.includes('Siguiente'))!.click();
    const siguiente = http.expectOne((peticion) => peticion.url === `${BASE}/gastos`);
    expect(siguiente.request.params.get('desplazamiento')).toBe('25');
    siguiente.flush({ elementos: [GASTO], total: 60, importe_total: '84.30' });
    fixture.detectChanges();
    expect(texto()).toContain('Página 2 de 3');
  });
});
