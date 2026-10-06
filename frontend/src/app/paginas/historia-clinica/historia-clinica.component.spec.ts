/**
 * Pruebas de la pantalla de historia clinica.
 *
 * Lo que se verifica y por que importa
 * ------------------------------------
 * **El PRN no se presenta como pauta fija.** Un medicamento «cuando sea
 * necesario» no genera horarios, y escribir «cada 8 horas» sobre el convierte
 * una indicacion a demanda en una pauta fija. Es un error de medicacion, no un
 * detalle de presentacion.
 *
 * **Los permisos clinicos no van juntos.** Un asistente tiene `receta.leer`
 * sin `historia_clinica.leer`. La pantalla le muestra la medicacion y le dice
 * que las notas no estan a su alcance, en lugar de pintar un error rojo como
 * si algo se hubiera roto. Un 403 aqui es el control funcionando.
 *
 * **Las versiones antiguas se ven.** La historia clinica se versiona y no se
 * borra; si la interfaz solo mostrara la vigente, esa garantia existiria en la
 * base y no le serviria de nada a quien la audita.
 *
 * **Una receta suspendida sigue visible con su motivo.** Ocultarla daria la
 * impresion de que nunca existio.
 */
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute } from '@angular/router';

import { HistoriaClinicaComponent } from './historia-clinica.component';
import { CONFIGURACION, CONFIGURACION_POR_DEFECTO } from '../../nucleo/servicios/configuracion';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import type { Medicamento, Nota, Receta } from '../../nucleo/servicios/api.service';
import type { Paciente } from '../../nucleo/modelos/dominio';

const BASE = CONFIGURACION_POR_DEFECTO.urlApi;
const PACIENTE_ID = 'pac-1';

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

function nota(extra: Partial<Nota> = {}): Nota {
  return {
    id: 'nota-1',
    raiz_id: 'raiz-1',
    version: 1,
    vigente: true,
    motivo_modificacion: null,
    paciente_id: PACIENTE_ID,
    profesional_id: 'prof-1',
    cita_id: null,
    tipo: 'EVOLUCION',
    motivo_consulta: 'Control [SINTETICO]',
    subjetivo: 'Texto subjetivo de demostracion',
    objetivo: null,
    analisis: null,
    plan: 'Plan de demostracion',
    signos_vitales: null,
    creado_en: '2026-09-10T14:00:00Z',
    ...extra,
  };
}

function medicamento(extra: Partial<Medicamento> = {}): Medicamento {
  return {
    id: 'med-1',
    nombre: 'Medicamento de ejemplo A',
    concentracion: null,
    forma: null,
    dosis: '1 unidad',
    via: 'ORAL',
    cuando_sea_necesario: false,
    frecuencia_horas: 8,
    duracion_dias: 3,
    instrucciones: null,
    ...extra,
  };
}

function receta(extra: Partial<Receta> = {}): Receta {
  return {
    id: 'rec-1',
    paciente_id: PACIENTE_ID,
    profesional_id: 'prof-1',
    estado: 'CONFIRMADA',
    confirmada_en: '2026-09-10T15:00:00Z',
    suspendida_en: null,
    motivo_suspension: null,
    indicaciones_generales: null,
    creado_en: '2026-09-10T14:30:00Z',
    medicamentos: [medicamento()],
    ...extra,
  };
}

import { ESPECIALIDAD_SINTETICA, INDICADORES_VACIOS } from '../../nucleo/pruebas/sesion-sintetica';
describe('HistoriaClinicaComponent', () => {
  let fixture: ComponentFixture<HistoriaClinicaComponent>;
  let http: HttpTestingController;
  let sesion: SesionService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HistoriaClinicaComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
        INDICADORES_VACIOS,
        ESPECIALIDAD_SINTETICA,
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { queryParamMap: { get: () => null } } },
        },
      ],
    });
    fixture = TestBed.createComponent(HistoriaClinicaComponent);
    http = TestBed.inject(HttpTestingController);
    sesion = TestBed.inject(SesionService);
  });

  afterEach(() => {
    // El resumen clínico tiene su propia prueba; aquí solo se responde.
    http.match((p) => p.url.endsWith('/resumen-clinico')).forEach((p) => p.flush({ codigo: 'X', mensaje: 'x' }, { status: 403, statusText: 'F' }));
    // La cabecera pide la foto de perfil; aquí no se prueba la foto.
    http.match((p) => p.url.endsWith('/foto-perfil')).forEach((p) => p.flush(null));
    http.verify();
  });

  /** Fija los permisos del principal, que es de donde la pantalla los lee. */
  function conPermisos(...codigos: readonly string[]): void {
    spyOn(sesion, 'tienePermiso').and.callFake((codigo: string) => codigos.includes(codigo));
  }

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

  /** Abre la historia y resuelve las peticiones que correspondan al rol. */
  function abrir(opciones: {
    notas?: readonly Nota[] | 'denegado';
    recetas?: readonly Receta[];
  }): void {
    fixture.componentInstance['abrir'](paciente());
    http.expectOne(`${BASE}/pacientes/${PACIENTE_ID}`).flush({
      ...paciente(),
      sexo: null,
      direccion: null,
      activo: true,
    });
    fixture.detectChanges();

    if (opciones.notas === 'denegado') {
      http
        .expectOne((p) => p.url.includes('/notas'))
        .flush(
          { codigo: 'PERMISO_DENEGADO', mensaje: 'Sin permiso.' },
          { status: 403, statusText: 'Forbidden' },
        );
    } else if (opciones.notas !== undefined) {
      http.expectOne((p) => p.url.includes('/notas')).flush(opciones.notas);
    }

    if (opciones.recetas !== undefined) {
      http.expectOne((p) => p.url.includes('/recetas')).flush(opciones.recetas);
    }
    fixture.detectChanges();
  }

  /**
   * Texto de las pestañas de evolución y de recetas: las pruebas afirman lo
   * que la historia muestra, esté en la pestaña que esté.
   */
  function texto(): string {
    const componente = fixture.componentInstance as unknown as {
      pestana: { set(valor: string): void; (): string };
    };
    const actual = componente.pestana();
    let todo = '';
    for (const pestana of ['evolucion', 'recetas']) {
      componente.pestana.set(pestana);
      fixture.detectChanges();
      todo += (fixture.nativeElement as HTMLElement).textContent ?? '';
    }
    componente.pestana.set(actual);
    fixture.detectChanges();
    return todo;
  }

  describe('medicacion', () => {
    beforeEach(() => conPermisos('historia_clinica.leer', 'receta.leer'));

    it('un PRN se enuncia como tal y NO se le calcula frecuencia', () => {
      listar();
      abrir({
        notas: [],
        recetas: [
          receta({
            medicamentos: [
              medicamento({
                nombre: 'Medicamento de ejemplo C',
                cuando_sea_necesario: true,
                frecuencia_horas: null,
                duracion_dias: null,
              }),
            ],
          }),
        ],
      });

      expect(texto()).toContain('cuando sea necesario');
      expect(texto()).toContain('Sin horario fijo');
      // Presentar un PRN con horas es convertir una indicacion a demanda en
      // una pauta fija.
      expect(texto()).not.toContain('cada 8 h');
    });

    it('una pauta fija si muestra su frecuencia y duracion', () => {
      listar();
      abrir({ notas: [], recetas: [receta()] });

      expect(texto()).toContain('cada 8 h');
      expect(texto()).toContain('durante 3 dias');
      expect(texto()).not.toContain('Sin horario fijo');
    });

    it('un borrador declara que no genera recordatorios', () => {
      listar();
      abrir({ notas: [], recetas: [receta({ estado: 'BORRADOR', confirmada_en: null })] });

      expect(texto()).toContain('Borrador');
      expect(texto()).toContain('No genera recordatorios');
    });

    it('una receta suspendida sigue visible, con su motivo', () => {
      listar();
      abrir({
        notas: [],
        recetas: [
          receta({
            estado: 'SUSPENDIDA',
            suspendida_en: '2026-09-11T10:00:00Z',
            motivo_suspension: 'Motivo de demostracion.',
          }),
        ],
      });

      // Ocultarla daria la impresion de que nunca existio.
      expect(texto()).toContain('Suspendida');
      expect(texto()).toContain('Motivo de demostracion.');
      expect(texto()).toContain('Medicamento de ejemplo A');
    });
  });

  describe('versionado', () => {
    beforeEach(() => conPermisos('historia_clinica.leer', 'receta.leer'));

    it('muestra la version vigente con su motivo de correccion', () => {
      listar();
      abrir({
        notas: [nota({ version: 2, motivo_modificacion: 'Se completo el registro.' })],
        recetas: [],
      });

      expect(texto()).toContain('versión 2');
      expect(texto()).toContain('Se completo el registro.');
    });

    it('las versiones anteriores se conservan y se pueden ver', () => {
      listar();
      abrir({
        notas: [
          nota({ id: 'n2', version: 2, motivo_modificacion: 'Correccion.' }),
          nota({ id: 'n1', version: 1, vigente: false, subjetivo: 'Texto original' }),
        ],
        recetas: [],
      });

      expect(texto()).toContain('1 versión(es) anterior(es) conservada(s)');
      expect(texto()).toContain('Texto original');
    });
  });

  describe('degradacion por rol', () => {
    it('un asistente ve las recetas y no pide las notas', () => {
      // `receta.leer` sin `historia_clinica.leer`: es el caso real del rol
      // asistente, y la pantalla no puede fallar entera por ello.
      conPermisos('receta.leer');
      listar();
      abrir({ recetas: [receta()] });

      expect(texto()).toContain('no están a su alcance');
      expect(texto()).toContain('historia_clinica.leer');
      expect(texto()).toContain('Medicamento de ejemplo A');
      // Y no se pinta como avería: no hay mensaje de error.
      expect(texto()).not.toContain('No se pudo cargar la historia');
    });

    it('un 403 en las notas no tumba la carga de las recetas', () => {
      // El permiso esta en el principal pero el backend lo niega igualmente
      // -- por relacion asistencial, por ejemplo. Es el control funcionando.
      conPermisos('historia_clinica.leer', 'receta.leer');
      listar();
      abrir({ notas: 'denegado', recetas: [receta()] });

      expect(texto()).toContain('no están a su alcance');
      expect(texto()).toContain('Medicamento de ejemplo A');
      expect(texto()).not.toContain('No se pudo cargar la historia');
    });

    it('sin permiso de recetas lo dice, sin revelar cuantas hay', () => {
      conPermisos('historia_clinica.leer');
      listar();
      abrir({ notas: [nota()] });

      expect(texto()).toContain('Las recetas no están a su alcance');
      expect(texto()).toContain('receta.leer');
    });
  });

  it('volver al listado limpia la historia mostrada', () => {
    conPermisos('historia_clinica.leer', 'receta.leer');
    listar();
    abrir({ notas: [nota()], recetas: [receta()] });
    expect(texto()).toContain('Medicamento de ejemplo A');

    fixture.componentInstance['cerrar']();
    fixture.detectChanges();

    // Dejar la historia del paciente anterior en pantalla al volver es como
    // alguien acaba leyendo la nota de otra persona.
    expect(texto()).not.toContain('Medicamento de ejemplo A');
    expect(texto()).toContain('Buscar paciente');
  });
});
