/**
 * Resumen de módulo e indicadores: una sola petición compartida por día,
 * tarjetas con enlace y nada si el rol no alcanza el módulo.
 */
import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';

import { ResumenModuloComponent } from './resumen-modulo.component';
import { TarjetasIndicadoresComponent } from './tarjetas-indicadores.component';
import { IndicadoresService } from '../nucleo/servicios/indicadores.service';
import { CONFIGURACION, CONFIGURACION_POR_DEFECTO } from '../nucleo/servicios/configuracion';
import { iniciarSesionCon } from '../nucleo/pruebas/sesion-sintetica';

const BASE = CONFIGURACION_POR_DEFECTO.urlApi;

describe('ResumenModuloComponent e IndicadoresService', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [ResumenModuloComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    iniciarSesionCon(['pago.leer']);
  });

  afterEach(() => http.verify());

  it('pinta las tarjetas del módulo y comparte la petición', () => {
    const fixture = TestBed.createComponent(ResumenModuloComponent);
    fixture.componentRef.setInput('modulo', 'pagos');
    fixture.detectChanges();
    // Una segunda suscripción del mismo día no repite la petición.
    TestBed.inject(IndicadoresService).obtener().subscribe();
    const peticion = http.expectOne((r) => r.url === `${BASE}/dashboard/indicadores`);
    expect(peticion.request.params.get('desde')).toBeTruthy();
    peticion.flush({
      agenda: null, mis_citas: null, pacientes: null, lista_espera: null, clinico: null, adherencia: null,
      mensajes: null, conocimiento: null, promociones: null, usuarios: null,
      pagos: { pendientes: 1, por_validar: 0, confirmado_30_dias: '10' },
    });
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelectorAll('.indicador').length).toBe(3);
    expect(el.textContent).toContain('Pagos pendientes');
    expect(el.querySelector('a.indicador')?.getAttribute('href')).toBe('/pagos');
  });

  it('si la petición falla no pinta nada y refrescar vuelve a pedir', () => {
    const fixture = TestBed.createComponent(ResumenModuloComponent);
    fixture.componentRef.setInput('modulo', 'usuarios');
    fixture.detectChanges();
    http.expectOne((r) => r.url === `${BASE}/dashboard/indicadores`).flush({}, { status: 500, statusText: 'E' });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelectorAll('.indicador').length).toBe(0);
    const servicio = TestBed.inject(IndicadoresService);
    servicio.refrescar();
    servicio.obtener().subscribe();
    http.expectOne((r) => r.url === `${BASE}/dashboard/indicadores`).flush(null);
  });

  it('las tarjetas sin enlace son bloques simples', () => {
    const fixture = TestBed.createComponent(TarjetasIndicadoresComponent);
    fixture.componentRef.setInput('indicadores', [{ etiqueta: 'Sin enlace', valor: 3, detalle: 'Detalle', tono: 'alerta' }]);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('div.indicador--alerta')).not.toBeNull();
    expect(el.textContent).toContain('Detalle');
  });
});
