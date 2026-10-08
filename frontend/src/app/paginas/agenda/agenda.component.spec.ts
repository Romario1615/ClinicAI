/**
 * Reserva desde la agenda: cita suelta o serie recurrente.
 *
 * Lo que se verifica y por qué importa
 * ------------------------------------
 * **La serie va a su propia ruta, con frecuencia, cantidad y clave.** Sin la
 * clave de idempotencia, una doble pulsación crea dos series enteras.
 *
 * **La cantidad respeta un año en cada frecuencia** (53 semanales, 27
 * quincenales, 13 mensuales). Antes la quincenal admitía 53 citas: dos años.
 *
 * **Un 409 no cierra la ventana.** El servidor dice qué fecha de la serie
 * chocó; cerrar la ventana borraba ese mensaje y todo lo escrito, y la
 * pantalla quedaba sin error y sin aviso de éxito.
 *
 * **Mientras se guarda no se puede cerrar.** La respuesta llegaría a una
 * ventana que ya no existe.
 *
 * Todo con datos sintéticos.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { of } from 'rxjs';

import { AgendaComponent, MAXIMO_CITAS_SERIE } from './agenda.component';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import type {
  Cita,
  Especialidad,
  Paciente,
  Profesional,
  Sede,
  Servicio,
  TurnoDisponible,
} from '../../nucleo/modelos/dominio';
import { BASE, PROVEEDORES_PRUEBA, iniciarSesionCon } from '../../nucleo/pruebas/sesion-sintetica';

const SEDE: Sede = { id: 'sede-1', nombre: 'Sede Norte [SINTETICO]', direccion: null, zona_horaria: 'America/Guayaquil' };
const ESPECIALIDAD: Especialidad = { id: 'esp-1', nombre: 'Odontología' };
const SERVICIO: Servicio = {
  id: 'srv-1',
  especialidad_id: 'esp-1',
  nombre: 'Control [SINTETICO]',
  duracion_minutos: 30,
  minutos_preparacion: 0,
  precio: null,
};
const PROFESIONAL: Profesional = {
  id: 'prof-1',
  especialidad_id: 'esp-1',
  nombre: 'Profesional',
  apellido: 'Sintetico',
  numero_registro_profesional: 'REG-SINTETICO',
};
const PACIENTE: Paciente = {
  id: 'pac-1',
  tipo_documento: 'CEDULA',
  numero_documento: '9900000001',
  nombre: 'Paciente',
  apellido: 'Sintetico',
  telefono_whatsapp: null,
  correo: null,
  fecha_nacimiento: null,
  nivel_verificacion: 'DOCUMENTO',
} as Paciente;

const MENSAJE_SERIE = 'No se puede crear la serie: el horario del 21/01 a las 09:00 no está disponible.';

function cita(inicio: string, extra: Partial<Cita> = {}): Cita {
  return {
    id: `cita-${inicio}`,
    paciente_id: PACIENTE.id,
    profesional_id: PROFESIONAL.id,
    servicio_id: SERVICIO.id,
    sede_id: SEDE.id,
    consultorio_id: null,
    inicio,
    fin: new Date(Date.parse(inicio) + 30 * 60_000).toISOString(),
    duracion_minutos: 30,
    minutos_preparacion: 0,
    estado: 'CONFIRMED',
    origen: 'RECURRENTE',
    expira_en: null,
    confirmada_en: null,
    llegada_en: null,
    atencion_iniciada_en: null,
    cancelada_en: null,
    motivo_cancelacion: null,
    ...extra,
  } as Cita;
}

/** Dos turnos seguidos a las 09:00 y 09:30 locales del día pedido. */
function turnosDe(desde: string): TurnoDisponible[] {
  return [9 * 60, 9 * 60 + 30].map((minutos) => {
    const inicio = new Date(Date.parse(desde) + minutos * 60_000).toISOString();
    const fin = new Date(Date.parse(inicio) + 30 * 60_000).toISOString();
    return { inicio, fin_consulta: fin, fin_bloque: fin, duracion_minutos: 30, minutos_preparacion: 0 };
  });
}

describe('máximo de citas por serie', () => {
  it('es un año en cada frecuencia, igual que en el servidor', () => {
    expect(MAXIMO_CITAS_SERIE).toEqual({ SEMANAL: 53, QUINCENAL: 27, MENSUAL: 13 });
  });
});

// La primera prueba monta la agenda entera (calendario incluido) y con la
// máquina cargada pasa de los 5 s por defecto sin que nada vaya mal.
describe('AgendaComponent · reserva y series', { timeout: 20_000 }, () => {
  let fixture: ComponentFixture<AgendaComponent>;
  let http: HttpTestingController;
  let turnos: TurnoDisponible[] = [];

  function montar(consulta: Record<string, string> = { paciente: PACIENTE.id }): void {
    TestBed.configureTestingModule({
      imports: [AgendaComponent],
      providers: [
        ...PROVEEDORES_PRUEBA,
        {
          provide: CatalogoService,
          useValue: {
            sedes: () => of([SEDE]),
            especialidades: () => of([ESPECIALIDAD]),
            servicios: () => of([SERVICIO]),
            profesionales: () => of([PROFESIONAL]),
            consultorios: () => of([]),
          },
        },
        {
          provide: ActivatedRoute,
          // La agenda escucha `queryParamMap` (abrir una cita desde otra
          // pantalla) y también lee la instantánea al arrancar.
          useValue: {
            snapshot: { queryParamMap: convertToParamMap(consulta) },
            queryParamMap: of(convertToParamMap(consulta)),
          },
        },
      ],
    });
    iniciarSesionCon(['cita.crear', 'agenda.leer']);
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(AgendaComponent);
    fixture.detectChanges();
    http
      .expectOne((p) => p.url === `${BASE}/pacientes/`)
      .flush({ elementos: [PACIENTE], total: 1, limite: 100, desplazamiento: 0, termino_ignorado: false });
    responderDia();
  }

  /** Responde la carga del día: sin citas y con los turnos que toquen. */
  function responderDia(quitar: readonly string[] = []): void {
    http
      .expectOne((p) => p.method === 'GET' && p.url === `${BASE}/agenda/citas`)
      .flush({ elementos: [], total: 0, limite: 200, desplazamiento: 0 });
    const disponibilidad = http.expectOne((p) => p.url === `${BASE}/agenda/disponibilidad`);
    const desde = disponibilidad.request.params.get('desde') ?? '';
    turnos = turnosDe(desde).filter((turno) => !quitar.includes(turno.inicio));
    disponibilidad.flush({
      profesional_id: PROFESIONAL.id,
      servicio_id: SERVICIO.id,
      sede_id: SEDE.id,
      zona_horaria: SEDE.zona_horaria,
      desde,
      hasta: desde,
      turnos,
      motivos_sin_turno: {},
    });
    fixture.detectChanges();
  }

  function raiz(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function dialogo(): HTMLDialogElement | null {
    return raiz().querySelector<HTMLDialogElement>('dialog[open][aria-label="Reservar cita"]');
  }

  function boton(texto: string | RegExp, dentro: ParentNode = raiz()): HTMLButtonElement | undefined {
    return Array.from(dentro.querySelectorAll<HTMLButtonElement>('button')).find((elemento) => {
      const etiqueta = elemento.textContent?.replace(/\s+/g, ' ').trim() ?? '';
      return typeof texto === 'string' ? etiqueta === texto : texto.test(etiqueta);
    });
  }

  function botonGuardar(): HTMLButtonElement {
    return dialogo()!.querySelector<HTMLButtonElement>('button[type="submit"]')!;
  }

  async function abrirNuevaCita(): Promise<void> {
    boton(/Nueva cita/)!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  /** Marca «Repetir esta cita» y elige frecuencia y cantidad desde el DOM. */
  async function repetir(frecuencia: string, cantidad: number): Promise<void> {
    const ventana = dialogo()!;
    const casilla = ventana.querySelector<HTMLInputElement>('input[name="serie-recurrente"]')!;
    if (!casilla.checked) {
      casilla.click();
      fixture.detectChanges();
      await fixture.whenStable();
      fixture.detectChanges();
    }
    const selector = ventana.querySelector<HTMLSelectElement>('select[name="frecuencia-serie"]')!;
    selector.value = frecuencia;
    selector.dispatchEvent(new Event('change'));
    const campo = ventana.querySelector<HTMLInputElement>('input[name="cantidad-serie"]')!;
    campo.value = String(cantidad);
    campo.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  function alertas(): string[] {
    return Array.from(dialogo()?.querySelectorAll('[role="alert"]') ?? []).map(
      (elemento) => elemento.textContent?.trim() ?? '',
    );
  }

  afterEach(() => {
    // El calendario pide la foto de cada profesional; aquí no se prueba.
    http.match((p) => p.url.endsWith('/foto')).forEach((p) => p.flush(null, { status: 404, statusText: 'Not Found' }));
    http.verify();
  });

  it('envía la serie a su ruta con frecuencia, cantidad y clave de idempotencia', async () => {
    montar();
    await abrirNuevaCita();
    expect(dialogo()).not.toBeNull();
    await repetir('QUINCENAL', 3);
    expect(botonGuardar().textContent).toContain('Crear serie de 3 citas');

    botonGuardar().click();
    fixture.detectChanges();
    const peticion = http.expectOne(`${BASE}/agenda/citas/series`);
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toEqual(
      expect.objectContaining({
        paciente_id: PACIENTE.id,
        profesional_id: PROFESIONAL.id,
        servicio_id: SERVICIO.id,
        sede_id: SEDE.id,
        inicio: turnos[0].inicio,
        frecuencia: 'QUINCENAL',
        cantidad: 3,
        procedimiento_plan_id: null,
      }),
    );
    expect(peticion.request.headers.get('Idempotency-Key')).toMatch(/^reserva-/);
    http.expectNone(`${BASE}/agenda/citas`);

    peticion.flush({
      serie_id: 'serie-1',
      frecuencia: 'QUINCENAL',
      cantidad: 3,
      citas: [cita(turnos[0].inicio), cita('2030-01-21T14:00:00Z'), cita('2030-02-04T14:00:00Z')],
    });
    responderDia();
    expect(dialogo()).toBeNull();
    expect(raiz().querySelector('.exito[role="status"]')?.textContent).toContain('Serie de 3 citas creada');
  });

  it('una cita suelta va a la ruta de citas y no a la de series', async () => {
    montar();
    await abrirNuevaCita();
    expect(botonGuardar().textContent?.trim()).toBe('Confirmar cita');
    botonGuardar().click();
    const peticion = http.expectOne((p) => p.method === 'POST' && p.url === `${BASE}/agenda/citas`);
    expect(peticion.request.body.frecuencia).toBeUndefined();
    expect(peticion.request.headers.get('Idempotency-Key')).toMatch(/^reserva-/);
    http.expectNone(`${BASE}/agenda/citas/series`);
    peticion.flush(cita(turnos[0].inicio));
    responderDia();
    expect(dialogo()).toBeNull();
  });

  it('fuera del máximo de cada frecuencia el botón se desactiva y lo dice', async () => {
    montar();
    await abrirNuevaCita();
    for (const [frecuencia, maximo] of Object.entries(MAXIMO_CITAS_SERIE)) {
      await repetir(frecuencia, maximo + 1);
      expect(botonGuardar().disabled).toBe(true);
      expect(alertas()).toContain(`Indique una cantidad entre 2 y ${maximo}.`);
      expect(dialogo()!.querySelector('input[name="cantidad-serie"]')?.getAttribute('max')).toBe(String(maximo));

      await repetir(frecuencia, maximo);
      expect(botonGuardar().disabled).toBe(false);
      expect(alertas()).toEqual([]);
    }
    // Y por abajo: una serie de una cita no es una serie.
    await repetir('SEMANAL', 1);
    expect(botonGuardar().disabled).toBe(true);
    http.expectNone(`${BASE}/agenda/citas/series`);
  });

  it('con un procedimiento de plan no se ofrece la serie', async () => {
    montar({ paciente: PACIENTE.id, procedimiento_plan: 'proc-1' });
    await abrirNuevaCita();
    const casilla = dialogo()!.querySelector<HTMLInputElement>('input[name="serie-recurrente"]')!;
    expect(casilla.disabled).toBe(true);
    expect(dialogo()!.textContent).toContain('se reservan individualmente');
  });

  it('un 409 de la serie deja la ventana abierta con el mensaje del servidor y lo escrito', async () => {
    montar();
    await abrirNuevaCita();
    await repetir('SEMANAL', 3);
    botonGuardar().click();
    http
      .expectOne(`${BASE}/agenda/citas/series`)
      .flush({ codigo: 'TURNO_NO_DISPONIBLE', mensaje: MENSAJE_SERIE }, { status: 409, statusText: 'Conflict' });
    // Se recarga el día para dejar de ofrecer lo ocupado…
    responderDia();
    await fixture.whenStable();
    fixture.detectChanges();

    // …pero la ventana sigue ahí, con el porqué y con la serie tal como estaba.
    expect(dialogo()).not.toBeNull();
    expect(alertas()).toContain(MENSAJE_SERIE);
    expect(dialogo()!.querySelector<HTMLInputElement>('input[name="serie-recurrente"]')!.checked).toBe(true);
    expect(dialogo()!.querySelector<HTMLInputElement>('input[name="cantidad-serie"]')!.value).toBe('3');
    expect(botonGuardar().disabled).toBe(false);
    expect(raiz().querySelector('.exito[role="status"]')).toBeNull();

    // Se puede corregir y reintentar sin volver a empezar.
    await repetir('SEMANAL', 2);
    botonGuardar().click();
    const reintento = http.expectOne(`${BASE}/agenda/citas/series`);
    expect(reintento.request.body.cantidad).toBe(2);
    reintento.flush({ serie_id: 's', frecuencia: 'SEMANAL', cantidad: 2, citas: [cita(turnos[0].inicio), cita('2030-01-14T14:00:00Z')] });
    responderDia();
    expect(dialogo()).toBeNull();
  });

  it('un 409 de una cita suelta quita la hora ocupada y pide elegir otra sin cerrar', async () => {
    montar();
    await abrirNuevaCita();
    const ocupada = turnos[0];
    botonGuardar().click();
    http
      .expectOne((p) => p.method === 'POST' && p.url === `${BASE}/agenda/citas`)
      .flush({ codigo: 'TURNO_NO_DISPONIBLE', mensaje: 'El turno ya no está disponible.' }, { status: 409, statusText: 'Conflict' });
    responderDia([ocupada.inicio]);

    expect(dialogo()).not.toBeNull();
    expect(alertas()).toContain('Ese turno acaba de ocuparse. La lista se ha actualizado; elija otro.');
    const horas = Array.from(dialogo()!.querySelectorAll('.arranques__lista button')).map((b) => b.textContent?.trim());
    expect(horas).toHaveLength(1);
    // Sin hora elegida no se puede confirmar.
    expect(botonGuardar().disabled).toBe(true);
  });

  it('mientras se guarda no se cierra por Escape, la X ni Descartar', async () => {
    montar();
    await abrirNuevaCita();
    botonGuardar().click();
    fixture.detectChanges();
    const peticion = http.expectOne((p) => p.method === 'POST' && p.url === `${BASE}/agenda/citas`);

    const ventana = dialogo()!;
    const equis = ventana.querySelector<HTMLButtonElement>('.ventana__cerrar')!;
    expect(equis.disabled).toBe(true);
    expect(boton('Descartar', ventana)!.disabled).toBe(true);
    ventana.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
    fixture.detectChanges();
    expect(dialogo()).not.toBeNull();

    peticion.flush(cita(turnos[0].inicio));
    responderDia();
    expect(dialogo()).toBeNull();
    expect(raiz().querySelector('.exito[role="status"]')?.textContent).toContain('Cita creada para Paciente Sintetico');
  });
});
