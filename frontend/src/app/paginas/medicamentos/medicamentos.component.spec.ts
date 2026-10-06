/**
 * Pruebas de la pantalla de medicacion.
 *
 * Lo que se verifica y por que importa
 * ------------------------------------
 * **Una toma futura no ofrece el boton de registrar.** Marcar como tomada una
 * dosis que todavia no toca produce un registro de adherencia falso, y ese
 * registro es lo que el profesional mira para decidir. El backend lo rechaza;
 * ofrecer el boton y que falle es peor que no ofrecerlo.
 *
 * **Una toma vencida se distingue de una futura.** Las dos estan en estado
 * `PENDIENTE` y significan cosas opuestas: una es una omision probable y la
 * otra no ha llegado. Mostrarlas igual esconde exactamente lo que hay que ver.
 *
 * **El registro recarga desde el servidor.** Mutar la fila en memoria mostraria
 * un estado que el backend puede no tener.
 */
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { MedicamentosComponent } from './medicamentos.component';
import { CONFIGURACION, CONFIGURACION_POR_DEFECTO } from '../../nucleo/servicios/configuracion';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import type { Toma } from '../../nucleo/servicios/api.service';
import type { Paciente } from '../../nucleo/modelos/dominio';

const BASE = CONFIGURACION_POR_DEFECTO.urlApi;
const PACIENTE_ID = 'pac-1';

/** Instante fijo para que «pasado» y «futuro» no dependan del reloj real. */
const AHORA = new Date('2026-04-15T14:00:00Z').getTime();

function paciente(): Paciente {
  return {
    id: PACIENTE_ID,
    tipo_documento: 'CEDULA',
    numero_documento: '9900000001',
    nombre: 'Nombre',
    apellido: 'Apellido',
    telefono_whatsapp: null,
    correo: null,
    fecha_nacimiento: null,
    nivel_verificacion: 'DOCUMENTO',
  };
}

function toma(extra: Partial<Toma> = {}): Toma {
  return {
    id: 'toma-1',
    receta_medicamento_id: 'med-1',
    medicamento: 'Medicamento de ejemplo A',
    programada_en: '2026-04-15T10:00:00Z',
    estado: 'PENDIENTE',
    registrada_en: null,
    ...extra,
  };
}

import { INDICADORES_VACIOS } from '../../nucleo/pruebas/sesion-sintetica';
describe('MedicamentosComponent', () => {
  let fixture: ComponentFixture<MedicamentosComponent>;
  let http: HttpTestingController;
  let sesion: SesionService;

  beforeEach(() => {
    jasmine.clock().install();
    jasmine.clock().mockDate(new Date(AHORA));

    TestBed.configureTestingModule({
      imports: [MedicamentosComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
        INDICADORES_VACIOS,
      ],
    });
    fixture = TestBed.createComponent(MedicamentosComponent);
    http = TestBed.inject(HttpTestingController);
    sesion = TestBed.inject(SesionService);
    spyOn(sesion, 'tienePermiso').and.returnValue(true);
  });

  afterEach(() => {
    http.verify();
    jasmine.clock().uninstall();
  });

  function listar(): void {
    fixture.detectChanges();
    http
      .expectOne((p) => p.url === `${BASE}/pacientes/`)
      .flush({
        elementos: [paciente()],
        total: 1,
        limite: 50,
        desplazamiento: 0,
        termino_ignorado: false,
      });
    fixture.detectChanges();
  }

  function abrir(tomas: readonly Toma[]): void {
    fixture.componentInstance['abrir'](paciente());
    http.expectOne(`${BASE}/pacientes/${PACIENTE_ID}`).flush({
      ...paciente(),
      sexo: null,
      direccion: null,
      activo: true,
    });
    fixture.detectChanges();
    http.expectOne((p) => p.url.includes('/tomas')).flush(tomas);
    if ((sesion.tienePermiso as jasmine.Spy)('adherencia.leer')) {
      http.expectOne(`${BASE}/historia/adherencia/alertas`).flush([]);
    }
    fixture.detectChanges();
  }

  function texto(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  function botones(): readonly string[] {
    return Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('tbody button'),
    ).map((b) => b.textContent?.trim() ?? '');
  }

  it('cada alerta dice de que receta es', () => {
    listar();
    fixture.componentInstance['abrir'](paciente());
    http.expectOne(`${BASE}/pacientes/${PACIENTE_ID}`).flush({ ...paciente(), sexo: null, direccion: null, activo: true });
    fixture.detectChanges();
    http.expectOne((p) => p.url.includes('/tomas')).flush([toma()]);
    http.expectOne(`${BASE}/historia/adherencia/alertas`).flush([
      {
        id: 'al-1', paciente_id: PACIENTE_ID, receta_id: 'rec-1', profesional_id: 'pr',
        severidad: 'ATENCION', tomas_omitidas: 2, tomas_esperadas: 7,
        periodo_desde: '2026-01-01T00:00:00Z', periodo_hasta: '2026-01-08T00:00:00Z', creado_en: '2026-01-08T00:00:00Z',
      },
    ]);
    http.expectOne(`${BASE}/historia/pacientes/${PACIENTE_ID}/recetas`).flush([
      { id: 'rec-1', medicamentos: [{ nombre: 'Medicamento de ejemplo A' }] },
    ]);
    fixture.detectChanges();

    expect(texto()).toContain('Receta: Medicamento de ejemplo A');
  });

  it('pide la ventana de tomas alrededor de hoy', () => {
    listar();
    fixture.componentInstance['abrir'](paciente());
    http.expectOne(`${BASE}/pacientes/${PACIENTE_ID}`).flush({
      ...paciente(),
      sexo: null,
      direccion: null,
      activo: true,
    });
    fixture.detectChanges();
    const peticion = http.expectOne((p) => p.url.includes('/tomas'));
    expect(peticion.request.params.get('dias')).toBe('7');
    peticion.flush([]);
    http.expectOne(`${BASE}/historia/adherencia/alertas`).flush([]);
  });

  describe('una toma futura', () => {
    it('no ofrece el boton de registrar', () => {
      listar();
      abrir([toma({ programada_en: '2026-04-16T10:00:00Z' })]);

      expect(texto()).toContain('aún no toca');
      expect(botones()).not.toContain('Tomada');
      expect(botones()).not.toContain('Omitida');
    });

    it('no se cuenta como sin registrar', () => {
      listar();
      abrir([toma({ programada_en: '2026-04-16T10:00:00Z' })]);

      expect(texto()).not.toContain('toma(s) sin registrar');
    });
  });

  describe('una toma vencida', () => {
    it('se destaca y si ofrece registrar', () => {
      listar();
      abrir([toma({ programada_en: '2026-04-15T10:00:00Z' })]);

      expect(texto()).toContain('1 toma(s) sin registrar');
      expect(texto()).toContain('sin registrar');
      expect(botones()).toContain('Tomada');
      expect(botones()).toContain('Omitida');
    });

    it('registrar recarga desde el servidor en lugar de mutar la fila', () => {
      listar();
      const vencida = toma({ programada_en: '2026-04-15T10:00:00Z' });
      abrir([vencida]);

      fixture.componentInstance['registrar'](vencida, true);
      const registro = http.expectOne(`${BASE}/historia/tomas/${vencida.id}/registro`);
      expect(registro.request.body.tomada).toBeTrue();
      registro.flush(null, { status: 204, statusText: 'No Content' });

      // El backend puede haber rechazado por una razon que la interfaz no
      // conoce; mostrar un estado que el servidor no tiene es peor que
      // esperar medio segundo.
      http
        .expectOne((p) => p.url.includes('/tomas'))
        .flush([{ ...vencida, estado: 'TOMADA', registrada_en: '2026-04-15T14:00:00Z' }]);
      http.expectOne(`${BASE}/historia/adherencia/alertas`).flush([]);
      fixture.detectChanges();

      expect(texto()).toContain('Tomada');
      expect(botones()).toEqual([]);
    });
  });

  it('sin permiso no ofrece registrar, y lo dice', () => {
    (sesion.tienePermiso as jasmine.Spy).and.returnValue(false);
    listar();
    abrir([toma({ programada_en: '2026-04-15T10:00:00Z' })]);

    expect(texto()).toContain('sin permiso');
    expect(botones()).toEqual([]);
  });

  it('sin tomas explica que solo una receta confirmada las genera', () => {
    listar();
    abrir([]);

    // Es la duda que tiene quien mira la pantalla vacia: si falta algo o si
    // el paciente no tiene pauta.
    expect(texto()).toContain('Sin tomas programadas');
    expect(texto()).toContain('receta confirmada');
    expect(texto()).toContain('cuando sea necesario');
  });

  it('un error al registrar se muestra sin perder el listado', () => {
    listar();
    const vencida = toma({ programada_en: '2026-04-15T10:00:00Z' });
    abrir([vencida]);

    fixture.componentInstance['registrar'](vencida, true);
    http
      .expectOne(`${BASE}/historia/tomas/${vencida.id}/registro`)
      .flush(
        { codigo: 'CONFLICTO_ESTADO', mensaje: 'La toma ya se registro.' },
        { status: 409, statusText: 'Conflict' },
      );
    fixture.detectChanges();

    expect(texto()).toContain('No se pudo registrar la toma');
    expect(texto()).toContain('CONFLICTO_ESTADO');
    expect(texto()).toContain('Medicamento de ejemplo A');
  });
});
