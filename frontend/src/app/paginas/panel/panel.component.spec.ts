/**
 * Panel: el tablero muestra solo los grupos que el rol alcanza, en el orden
 * en que se atienden (mi día, la clínica hoy, lo pendiente, la gestión).
 */
import { TestBed } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';
import { of } from 'rxjs';

import { PanelComponent } from './panel.component';
import { IndicadoresService, type Indicadores } from '../../nucleo/servicios/indicadores.service';
import { PROVEEDORES_PRUEBA, iniciarSesionCon } from '../../nucleo/pruebas/sesion-sintetica';

function indicadores(extra: Partial<Indicadores>): Indicadores {
  return {
    agenda: null, mis_citas: null, pacientes: null, lista_espera: null, pagos: null, clinico: null,
    adherencia: null, mensajes: null, conocimiento: null, promociones: null, usuarios: null,
    ...extra,
  };
}

// La primera prueba monta el panel entero (seis vistas con sus tarjetas) y
// paga el arranque del árbol de componentes: menos de 1 s en solitario, pero
// más de 5 s cuando corre junto a las otras 93 especificaciones en paralelo.
// El límite se amplía solo para este bloque; ninguna aserción cambia.
describe('PanelComponent · tablero por rol', { timeout: 15_000 }, () => {
  function montar(datos: Indicadores, permisos: readonly string[]) {
    TestBed.configureTestingModule({
      imports: [PanelComponent],
      providers: [
        ...PROVEEDORES_PRUEBA,
        { provide: IndicadoresService, useValue: { obtener: () => of(datos), refrescar: () => undefined } },
      ],
    });
    iniciarSesionCon(permisos);
    const fixture = TestBed.createComponent(PanelComponent);
    fixture.detectChanges();
    // El resto del panel (carga de hoy, cifras) no es objeto de esta prueba.
    const http = TestBed.inject(HttpTestingController);
    for (const peticion of http.match(() => true)) {
      if (!peticion.cancelled) {
        if (peticion.request.url.endsWith('/profesionales')) {
          peticion.flush([]);
        } else if (peticion.request.url.endsWith('/catalogo/clinica')) {
          peticion.flush({ id: 'clinica-1', nombre: 'Clínica', zona_horaria: 'America/Guayaquil', idioma: 'es', moneda: 'USD', telefono: null, correo: null });
        } else if (/\/catalogo\/(sedes|especialidades|servicios)$/.test(peticion.request.url)) {
          peticion.flush([]);
        } else if (peticion.request.url.endsWith('/dashboard/')) {
          peticion.flush({
            total_citas: 0,
            pacientes: 0,
            pacientes_nuevos: null,
            pacientes_recurrentes: null,
            pacientes_registrados: null,
            pacientes_registrados_sin_cita: null,
            cohortes_registro: null,
            citas: {},
            tendencia_diaria: [],
            por_hora: [],
            por_dia_semana: [],
            espera: { promedio_minutos: null, personas_en_espera: 0, espera_mayor_15_minutos: 0 },
            recuperacion_turnos: { turnos_liberados: null, turnos_recuperados: null, promedio_minutos_para_recuperar: null },
            adherencia: null,
            pagos: null,
          });
        } else {
          peticion.flush({ elementos: [], total: 0, limite: 200, desplazamiento: 0 });
        }
      }
    }
    fixture.detectChanges();
    return fixture;
  }

  it('el profesional ve su día y lo pendiente; no ve gestión', () => {
    const fixture = montar(
      indicadores({
        mis_citas: { citas_hoy: 3, pendientes_hoy: 1, proxima_inicio: null },
        agenda: { citas_hoy: 9, por_confirmar_hoy: 2, en_sala: 0, en_atencion: 1, atendidas_hoy: 4, inasistencias_hoy: 0, citas_proximos_7_dias: 30 },
        clinico: { recetas_por_confirmar: 1, planes_propuestos: 0, planes_en_curso: 2 },
      }),
      ['agenda.leer'],
    );
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const grupos = (fixture.componentInstance as any).tablero().map((g: { titulo: string }) => g.titulo);
    expect(grupos).toEqual(['Mi día', 'La clínica hoy', 'Pendiente de atender']);
    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Mis citas de hoy');
    expect(texto).toContain('Recetas por confirmar');
  });

  it('presenta los siete filtros dentro de una ventana accesible que puede cerrarse con Escape', () => {
    const fixture = montar(indicadores({}), ['dashboard.leer']);
    const elemento = fixture.nativeElement as HTMLElement;
    const abrir = elemento.querySelector<HTMLButtonElement>('button[aria-haspopup="dialog"]');
    expect(abrir?.textContent).toContain('Ajustar filtros');
    abrir?.click();
    fixture.detectChanges();

    const dialogo = elemento.querySelector<HTMLDialogElement>('dialog[open]');
    expect(dialogo?.getAttribute('aria-modal')).toBe('true');
    expect(dialogo?.getAttribute('aria-label')).toBe('Filtros del dashboard');
    expect(dialogo?.querySelectorAll('.filtros-dashboard input, .filtros-dashboard select').length).toBe(7);
    expect(elemento.querySelector('.filtros-dashboard__barra')).not.toBeNull();

    dialogo?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
    fixture.detectChanges();
    expect(elemento.querySelector('dialog[open]')).toBeNull();
  });

  it('cuenta el periodo personalizado y cada filtro aplicado en el resumen de filtros', () => {
    const fixture = montar(indicadores({}), ['dashboard.leer']);
    const componente = fixture.componentInstance as unknown as {
      periodo: { set(valor: string): void };
      sedeId: { set(valor: string): void };
      estadoCita: { set(valor: string): void };
      cantidadFiltrosActivos: () => number;
      hayFiltros: () => boolean;
    };
    expect(componente.cantidadFiltrosActivos()).toBe(0);
    expect(componente.hayFiltros()).toBe(false);
    componente.periodo.set('personalizado');
    componente.sedeId.set('sede-1');
    componente.estadoCita.set('CONFIRMED');
    fixture.detectChanges();
    expect(componente.cantidadFiltrosActivos()).toBe(3);
    expect(componente.hayFiltros()).toBe(true);
    expect((fixture.nativeElement as HTMLElement).querySelector('.filtros-dashboard__contador')?.textContent?.trim()).toBe('3');
  });

  it('administración ve la gestión de la clínica', () => {
    const fixture = montar(
      indicadores({
        usuarios: { activos: 10, inactivos: 0, roles: 5 },
        pagos: { pendientes: 0, por_validar: 1, confirmado_30_dias: '100' },
      }),
      ['usuario.leer'],
    );
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const grupos = (fixture.componentInstance as any).tablero().map((g: { titulo: string }) => g.titulo);
    expect(grupos).toEqual(['Pendiente de atender', 'Gestión de la clínica']);
  });

  it('reparte el panel en pestañas según los permisos y muestra una vista a la vez', () => {
    const fixture = montar(
      indicadores({ usuarios: { activos: 10, inactivos: 0, roles: 5 } }),
      ['agenda.leer', 'dashboard.leer'],
    );
    const elemento = fixture.nativeElement as HTMLElement;
    const pestanas = Array.from(elemento.querySelectorAll<HTMLElement>('[role="tab"]'));
    expect(pestanas.map((p) => p.id)).toEqual([
      'panel-pestana-resumen',
      'panel-pestana-hoy',
      'panel-pestana-cifras',
      'panel-pestana-distribucion',
      'panel-pestana-pacientes',
      'panel-pestana-seguimiento',
    ]);
    const visibles = () =>
      Array.from(elemento.querySelectorAll<HTMLElement>('[role="tabpanel"]')).filter((panel) => !panel.hidden);

    // Al entrar se ve el tablero y nada más.
    expect(visibles().map((panel) => panel.id)).toEqual(['panel-panel-resumen']);

    // Las tres vistas de cifras comparten panel y mandos; cambia lo que se muestra dentro.
    pestanas[3].click();
    fixture.detectChanges();
    expect(visibles().map((panel) => panel.id)).toEqual(['panel-panel-distribucion']);
    expect(visibles()[0].getAttribute('aria-labelledby')).toBe('panel-pestana-distribucion');
    expect(elemento.querySelector<HTMLElement>('.cifras__rejilla')?.hidden).toBe(true);
    expect(elemento.querySelector<HTMLElement>('.panel__graficos')?.hidden).toBe(false);
    expect(elemento.querySelector('.cifras__mandos')?.textContent).toContain('Ajustar filtros');
  });

  it('sin agenda ni métricas no ofrece pestañas y deja el aviso de espacio de trabajo', () => {
    const fixture = montar(indicadores({}), []);
    const elemento = fixture.nativeElement as HTMLElement;
    expect(elemento.querySelectorAll('[role="tab"]').length).toBe(0);
    expect(elemento.textContent).toContain('Su espacio de trabajo');
  });

  it('con una sola vista no pinta la fila de pestañas', () => {
    const fixture = montar(indicadores({}), ['agenda.leer']);
    const elemento = fixture.nativeElement as HTMLElement;
    expect(elemento.querySelector('app-pestanas')).toBeNull();
    expect(elemento.querySelector<HTMLElement>('#panel-panel-hoy')?.hidden).toBe(false);
  });

  it('usa etiquetas ISO y escala los agregados del periodo', () => {
    const fixture = montar(indicadores({}), ['agenda.leer']);
    const componente = fixture.componentInstance as unknown as {
      etiquetaDia(dia: number): string;
      etiquetaFecha(fecha: string): string;
      etiquetaHora(hora: number): string;
      maximoTendencia(items: readonly { total: number }[]): number;
    };
    expect(componente.etiquetaDia(1)).toBe('Lun');
    expect(componente.etiquetaDia(7)).toBe('Dom');
    expect(componente.etiquetaFecha('2026-10-05')).toMatch(/lun/i);
    expect(componente.etiquetaFecha('fecha-invalida')).toBe('fecha-invalida');
    expect(componente.etiquetaHora(8)).toBe('08:00');
    expect(componente.maximoTendencia([{ total: 2 }, { total: 6 }])).toBe(6);
    expect(componente.maximoTendencia([])).toBe(1);
  });

  it('expone las tendencias como listas etiquetadas y conserva el estado vacío', () => {
    const fixture = montar(indicadores({}), ['dashboard.leer']);
    const region = (fixture.nativeElement as HTMLElement).querySelector(
      '[role="group"][aria-label="Distribución de citas en el periodo"]',
    );
    expect(region).not.toBeNull();
    const secciones = Array.from(region?.querySelectorAll('section[aria-labelledby]') ?? []);
    expect(secciones.length).toBe(3);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Citas por día');
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Sin citas en este periodo.');
    expect(region?.querySelector('ul')).toBeNull();
  });

  it('presenta fechas y cantidades en texto junto a las barras visuales', () => {
    const fixture = montar(indicadores({}), ['dashboard.leer']);
    const componente = fixture.componentInstance as unknown as { cambiarPeriodo(clave: string): void };
    componente.cambiarPeriodo('7');
    const http = TestBed.inject(HttpTestingController);
    const peticiones = http.match((solicitud) => solicitud.url.endsWith('/dashboard/'));
    expect(peticiones.length).toBe(2);
    peticiones[0].flush({
      total_citas: 4, pacientes: 3, pacientes_nuevos: 1, pacientes_recurrentes: 2,
      citas: { COMPLETED: 4 }, tendencia_diaria: [{ fecha: '2026-10-06', total: 4 }],
      por_hora: [{ hora: 9, total: 4 }], por_dia_semana: [{ dia: 2, total: 4 }],
      espera: { promedio_minutos: null, personas_en_espera: 0, espera_mayor_15_minutos: 0 },
      recuperacion_turnos: { turnos_liberados: 0, turnos_recuperados: 0, promedio_minutos_para_recuperar: null },
      adherencia: null, pagos: null,
    });
    peticiones[1].flush({
      total_citas: 0, pacientes: 0, pacientes_nuevos: 0, pacientes_recurrentes: 0,
      citas: {}, tendencia_diaria: [], por_hora: [], por_dia_semana: [],
      espera: { promedio_minutos: null, personas_en_espera: 0, espera_mayor_15_minutos: 0 },
      recuperacion_turnos: { turnos_liberados: 0, turnos_recuperados: 0, promedio_minutos_para_recuperar: null },
      adherencia: null, pagos: null,
    });
    fixture.detectChanges();
    const diaria = (fixture.nativeElement as HTMLElement).querySelector('#tendencia-diaria');
    expect(diaria?.parentElement?.querySelector('ul li')?.textContent).toContain('4');
    expect((fixture.nativeElement as HTMLElement).querySelectorAll('.tendencia__pista[aria-hidden="true"]').length).toBe(3);
    http.verify();
  });

  it('muestra la ocupación solo con capacidad real y etiqueta el tiempo utilizado', () => {
    const fixture = montar(indicadores({}), ['dashboard.leer']);
    const componente = fixture.componentInstance as unknown as { cambiarPeriodo(clave: string): void };
    componente.cambiarPeriodo('7');
    const http = TestBed.inject(HttpTestingController);
    const peticiones = http.match((solicitud) => solicitud.url.endsWith('/dashboard/'));
    expect(peticiones.length).toBe(2);
    peticiones[0].flush({
      total_citas: 1, pacientes: 1, pacientes_nuevos: 1, pacientes_recurrentes: 0,
      citas: { CONFIRMED: 1 }, tendencia_diaria: [], por_hora: [], por_dia_semana: [],
      espera: { promedio_minutos: null, personas_en_espera: 0, espera_mayor_15_minutos: 0 },
      recuperacion_turnos: { turnos_liberados: 0, turnos_recuperados: 0, promedio_minutos_para_recuperar: null },
      ocupacion_agenda: {
        minutos_disponibles: 210, minutos_ocupados: 45, porcentaje: 21.4,
        detalle: 'Reservas activas frente al horario disponible; incluye pausas, feriados y bloqueos.',
      },
      adherencia: null, pagos: null,
    });
    peticiones[1].flush({
      total_citas: 0, pacientes: 0, pacientes_nuevos: 0, pacientes_recurrentes: 0,
      citas: {}, tendencia_diaria: [], por_hora: [], por_dia_semana: [],
      espera: { promedio_minutos: null, personas_en_espera: 0, espera_mayor_15_minutos: 0 },
      recuperacion_turnos: { turnos_liberados: 0, turnos_recuperados: 0, promedio_minutos_para_recuperar: null },
      ocupacion_agenda: { minutos_disponibles: 0, minutos_ocupados: 0, porcentaje: null, detalle: 'Sin horario.' },
      adherencia: null, pagos: null,
    });
    fixture.detectChanges();

    const elemento = fixture.nativeElement as HTMLElement;
    expect(elemento.querySelector('.ocupacion-agenda__valor')?.textContent).toContain('21.4');
    expect(elemento.querySelector('progress.ocupacion-agenda__barra')?.getAttribute('aria-label'))
      .toBe('Ocupación de agenda: 21.4 por ciento');
    expect(elemento.querySelector('.ocupacion-agenda__tiempos')?.textContent).toContain('reservados');
    expect(elemento.querySelector('.ocupacion-agenda__detalle')?.textContent)
      .toContain('incluye pausas, feriados y bloqueos');
    http.verify();
  });

  it('no conserva cifras anteriores si falla la carga actual del dashboard', () => {
    const fixture = montar(indicadores({}), ['dashboard.leer']);
    const componente = fixture.componentInstance as unknown as { cambiarPeriodo(clave: string): void; resumen: () => unknown };
    componente.cambiarPeriodo('7');
    const http = TestBed.inject(HttpTestingController);
    const peticiones = http.match((solicitud) => solicitud.url.endsWith('/dashboard/'));
    expect(peticiones.length).toBe(2);
    peticiones[0].flush({ mensaje: 'Fallo temporal del resumen' }, { status: 503, statusText: 'Unavailable' });
    peticiones[1].flush({
      total_citas: 0, pacientes: 0, pacientes_nuevos: 0, pacientes_recurrentes: 0,
      citas: {}, tendencia_diaria: [], por_hora: [], por_dia_semana: [],
      espera: { promedio_minutos: null, personas_en_espera: 0, espera_mayor_15_minutos: 0 },
      recuperacion_turnos: { turnos_liberados: 0, turnos_recuperados: 0, promedio_minutos_para_recuperar: null },
      adherencia: null, pagos: null,
    });
    fixture.detectChanges();
    expect(componente.resumen()).toBeNull();
    expect((fixture.nativeElement as HTMLElement).querySelector('[role="alert"]')).not.toBeNull();
    expect((fixture.nativeElement as HTMLElement).querySelector('#tendencia-diaria')).toBeNull();
    http.verify();
  });

  it('genera un resumen operativo local sin llamar al proveedor de IA', () => {
    const fixture = montar(indicadores({}), ['dashboard.leer']);
    const ilustracion = (fixture.nativeElement as HTMLElement).querySelector(
      'img[src="/images/seguimiento-inteligente-clinica.svg"]',
    );
    expect(ilustracion).not.toBeNull();
    const botones = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    );
    const boton = botones.find((elemento) => elemento.textContent?.includes('Resumen operativo'));
    expect(boton).toBeDefined();
    boton?.click();

    const http = TestBed.inject(HttpTestingController);
    const peticion = http.expectOne((solicitud) => solicitud.url.endsWith('/dashboard/analisis-local'));
    expect(peticion.request.method).toBe('POST');
    peticion.flush({ hallazgos: ['Se registraron 3 citas de 2 pacientes distintos.'] });
    fixture.detectChanges();

    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('RESUMEN OPERATIVO LOCAL');
    expect(texto).toContain('3 citas de 2 pacientes distintos');
    expect((fixture.nativeElement as HTMLElement).querySelector('img[src="/images/seguimiento-inteligente-clinica.svg"]')).toBeNull();
    http.verify();
  });

  it('envía los filtros de catálogo y estado al resumen agregado', () => {
    const fixture = montar(indicadores({}), ['dashboard.leer']);
    const componente = fixture.componentInstance as unknown as {
      sedeId: { set(valor: string): void };
      especialidadId: { set(valor: string): void };
      profesionalId: { set(valor: string): void };
      servicioId: { set(valor: string): void };
      estadoCita: { set(valor: string): void };
      aplicarFiltros(): void;
    };
    componente.sedeId.set('sede-1');
    componente.especialidadId.set('especialidad-1');
    componente.profesionalId.set('profesional-1');
    componente.servicioId.set('servicio-1');
    componente.estadoCita.set('CONFIRMED');
    componente.aplicarFiltros();

    const http = TestBed.inject(HttpTestingController);
    const peticiones = http.match((solicitud) => solicitud.url.endsWith('/dashboard/'));
    expect(peticiones.length).toBe(2);
    const peticion = peticiones[0];
    expect(peticion.request.params.get('sede_id')).toBe('sede-1');
    expect(peticion.request.params.get('especialidad_id')).toBe('especialidad-1');
    expect(peticion.request.params.get('profesional_id')).toBe('profesional-1');
    expect(peticion.request.params.get('servicio_id')).toBe('servicio-1');
    expect(peticion.request.params.get('estado')).toBe('CONFIRMED');
    for (const solicitud of peticiones) {
      solicitud.flush({
        total_citas: 0, pacientes: 0, pacientes_nuevos: null, pacientes_recurrentes: null, citas: {}, tendencia_diaria: [], por_hora: [], por_dia_semana: [],
        espera: { promedio_minutos: null, personas_en_espera: 0, espera_mayor_15_minutos: 0 }, recuperacion_turnos: { turnos_liberados: null, turnos_recuperados: null, promedio_minutos_para_recuperar: null }, adherencia: null, pagos: null,
      });
    }
    http.verify();
  });

  it('aplica fechas locales inclusivas y no consulta rangos inválidos', () => {
    const fixture = montar(indicadores({}), ['dashboard.leer']);
    const componente = fixture.componentInstance as unknown as {
      fechaDesde: { set(valor: string): void };
      fechaHasta: { set(valor: string): void };
      periodo: { set(valor: string): void };
      sedeId: { set(valor: string): void };
      sedes: { set(valor: readonly { id: string; nombre: string; direccion: null; zona_horaria: string }[]): void };
      aplicarFiltros(): void;
      errorFechas: () => string;
    };
    componente.fechaDesde.set('2026-10-01');
    componente.fechaHasta.set('2026-10-03');
    componente.periodo.set('personalizado');
    componente.aplicarFiltros();

    const http = TestBed.inject(HttpTestingController);
    const peticiones = http.match((solicitud) => solicitud.url.endsWith('/dashboard/'));
    expect(peticiones.length).toBe(2);
    expect(peticiones[0].request.params.get('desde')).toBe('2026-10-01T05:00:00.000Z');
    expect(peticiones[0].request.params.get('hasta')).toBe('2026-10-04T05:00:00.000Z');
    for (const solicitud of peticiones) {
      solicitud.flush({
        total_citas: 0, pacientes: 0, pacientes_nuevos: null, pacientes_recurrentes: null, citas: {}, tendencia_diaria: [], por_hora: [], por_dia_semana: [],
        espera: { promedio_minutos: null, personas_en_espera: 0, espera_mayor_15_minutos: 0 }, recuperacion_turnos: { turnos_liberados: null, turnos_recuperados: null, promedio_minutos_para_recuperar: null }, adherencia: null, pagos: null,
      });
    }
    fixture.detectChanges();
    const botonResumen = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    ).find((boton) => boton.textContent?.includes('Resumen operativo'));
    botonResumen?.click();
    const consultaLocal = http.expectOne((solicitud) => solicitud.url.endsWith('/dashboard/analisis-local'));
    expect(consultaLocal.request.params.get('desde')).toBe('2026-10-01T05:00:00.000Z');
    expect(consultaLocal.request.params.get('hasta')).toBe('2026-10-04T05:00:00.000Z');
    consultaLocal.flush({ hallazgos: [] });

    componente.sedes.set([{ id: 'sede-1', nombre: 'Sede Este', direccion: null, zona_horaria: 'Pacific/Kiritimati' }]);
    componente.sedeId.set('sede-1');
    componente.aplicarFiltros();
    const consultasSede = http.match((solicitud) => solicitud.url.endsWith('/dashboard/'));
    expect(consultasSede.length).toBe(2);
    expect(consultasSede[0].request.params.get('sede_id')).toBe('sede-1');
    expect(consultasSede[0].request.params.get('desde')).toBe('2026-09-30T10:00:00.000Z');
    expect(consultasSede[0].request.params.get('hasta')).toBe('2026-10-03T10:00:00.000Z');
    for (const solicitud of consultasSede) {
      solicitud.flush({
        total_citas: 0, pacientes: 0, pacientes_nuevos: null, pacientes_recurrentes: null, citas: {}, tendencia_diaria: [], por_hora: [], por_dia_semana: [],
        espera: { promedio_minutos: null, personas_en_espera: 0, espera_mayor_15_minutos: 0 }, recuperacion_turnos: { turnos_liberados: null, turnos_recuperados: null, promedio_minutos_para_recuperar: null }, adherencia: null, pagos: null,
      });
    }

    componente.fechaDesde.set('2027-01-01');
    componente.fechaHasta.set('2026-12-31');
    componente.aplicarFiltros();
    expect(componente.errorFechas()).toContain('anterior o igual');
    http.expectNone((solicitud) => solicitud.url.endsWith('/dashboard/'));
    http.verify();
  });

  it('muestra pacientes nuevos y recurrentes a partir de atenciones completadas', () => {
    const fixture = montar(indicadores({}), ['dashboard.leer']);
    const componente = fixture.componentInstance as unknown as { cambiarPeriodo(clave: string): void };
    componente.cambiarPeriodo('7');

    const http = TestBed.inject(HttpTestingController);
    const peticiones = http.match((solicitud) => solicitud.url.endsWith('/dashboard/'));
    expect(peticiones.length).toBe(2);
    peticiones[0].flush({
      total_citas: 8, pacientes: 5, pacientes_nuevos: 2, pacientes_recurrentes: 3,
      citas: { COMPLETED: 5 }, tendencia_diaria: [], por_hora: [], por_dia_semana: [],
      espera: { promedio_minutos: null, personas_en_espera: 0, espera_mayor_15_minutos: 0 }, recuperacion_turnos: { turnos_liberados: null, turnos_recuperados: null, promedio_minutos_para_recuperar: null }, adherencia: null, pagos: null,
    });
    peticiones[1].flush({
      total_citas: 4, pacientes: 3, pacientes_nuevos: 1, pacientes_recurrentes: 1,
      citas: { COMPLETED: 3 }, tendencia_diaria: [], por_hora: [], por_dia_semana: [],
      espera: { promedio_minutos: null, personas_en_espera: 0, espera_mayor_15_minutos: 0 }, recuperacion_turnos: { turnos_liberados: null, turnos_recuperados: null, promedio_minutos_para_recuperar: null }, adherencia: null, pagos: null,
    });
    fixture.detectChanges();
    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Pacientes atendidos');
    expect(texto).toContain('Nuevos');
    expect(texto).toContain('Recurrentes');
    expect(texto).toContain('Clasificados por su primera atención completada dentro del filtro.');
    http.verify();
  });

  it('presenta altas por cohorte mensual y las oculta al filtrar por estado', () => {
    const fixture = montar(indicadores({}), ['dashboard.leer']);
    const componente = fixture.componentInstance as unknown as {
      cambiarPeriodo(clave: string): void;
      estadoCita: { set(valor: string): void };
      aplicarFiltros(): void;
    };
    componente.cambiarPeriodo('30');

    const http = TestBed.inject(HttpTestingController);
    const periodo = http.match((solicitud) => solicitud.url.endsWith('/dashboard/'));
    expect(periodo.length).toBe(2);
    const base = {
      total_citas: 14,
      pacientes: 12,
      pacientes_nuevos: 4,
      pacientes_recurrentes: 8,
      pacientes_registrados: 4,
      pacientes_registrados_sin_cita: 2,
      cohortes_registro: [{
        mes: '2026-10-01',
        registrados: 4,
        con_cita_en_filtros: 2,
        sin_cita_en_filtros: 2,
      }],
      demografia: {
        edades: [
          { categoria: '0-17 años', pacientes: null, suprimida: true },
          { categoria: '18-29 años', pacientes: 0, suprimida: false },
          { categoria: '30-44 años', pacientes: 0, suprimida: false },
          { categoria: '45-59 años', pacientes: 5, suprimida: false },
          { categoria: '60 o más', pacientes: 0, suprimida: false },
          { categoria: 'Sin fecha de nacimiento', pacientes: null, suprimida: true },
          { categoria: 'Fecha no válida', pacientes: 0, suprimida: false },
        ],
        sexos: [
          { categoria: 'Femenino', pacientes: null, suprimida: true },
          { categoria: 'Masculino', pacientes: 5, suprimida: false },
          { categoria: 'Otro', pacientes: null, suprimida: true },
          { categoria: 'Sin registrar', pacientes: 0, suprimida: false },
        ],
      },
      retorno_30_dias: {
        pacientes_seguimiento_completo: 12,
        pacientes_que_regresaron: 6,
        porcentaje: 50,
      },
      citas: { COMPLETED: 4 },
      tendencia_diaria: [],
      por_hora: [],
      por_dia_semana: [],
      espera: { promedio_minutos: null, personas_en_espera: 0, espera_mayor_15_minutos: 0 },
      recuperacion_turnos: { turnos_liberados: 0, turnos_recuperados: 0, promedio_minutos_para_recuperar: null },
      adherencia: null,
      pagos: null,
    };
    periodo[0].flush(base);
    periodo[1].flush({ ...base, total_citas: 0, pacientes_registrados: 0, pacientes_registrados_sin_cita: 0, cohortes_registro: [] });
    fixture.detectChanges();

    const elemento = fixture.nativeElement as HTMLElement;
    expect(elemento.querySelector('.altas-pacientes')?.textContent).toContain('Registrados');
    expect(elemento.querySelector('.altas-pacientes')?.textContent).toContain('Sin cita en los filtros');
    expect(elemento.querySelector('.demografia')?.textContent).toContain('Perfil de pacientes');
    expect(elemento.querySelector('.demografia')?.textContent).toContain('Sexo registrado');
    expect(elemento.querySelector('.demografia')?.textContent).toContain('Protegido');
    expect(elemento.querySelectorAll('.demografia__fila').length).toBe(11);
    expect(elemento.querySelector('.retorno-30d')?.textContent).toContain('50%');
    expect(elemento.querySelector('.retorno-30d')?.textContent).toContain('6 de 12 pacientes regresaron');
    const filasProtegidas = Array.from(elemento.querySelectorAll('.demografia__fila'))
      .filter((fila) => fila.textContent?.includes('Protegido'));
    expect(filasProtegidas).toHaveLength(4);
    expect(filasProtegidas.every((fila) => !fila.querySelector('.tendencia__pista span'))).toBe(true);
    expect(elemento.querySelector('.cohortes-registro__tabla tbody tr')?.textContent).toContain('octubre de 2026');
    expect(Array.from(elemento.querySelectorAll('.cohortes-registro__tabla tbody tr td')).map((celda) => celda.textContent?.trim()))
      .toEqual(['4', '2', '2']);

    componente.estadoCita.set('CONFIRMED');
    componente.aplicarFiltros();
    const filtradas = http.match((solicitud) => solicitud.url.endsWith('/dashboard/'));
    expect(filtradas.length).toBe(2);
    const sinCohortes = {
      ...base,
      pacientes_nuevos: null,
      pacientes_recurrentes: null,
      pacientes_registrados: null,
      pacientes_registrados_sin_cita: null,
      cohortes_registro: null,
      retorno_30_dias: null,
    };
    filtradas.forEach((peticion) => peticion.flush(sinCohortes));
    fixture.detectChanges();
    expect(elemento.querySelector('.altas-pacientes')?.textContent).toContain('Elige “Todos los estados”');
    expect(elemento.querySelector('.cohortes-registro')?.textContent).toContain('se oculta al filtrar por estado');
    http.verify();
  });

  it('presenta turnos cancelados, recuperados y tiempo medio de reasignación', () => {
    const fixture = montar(indicadores({}), ['dashboard.leer']);
    const componente = fixture.componentInstance as unknown as { cambiarPeriodo(clave: string): void };
    componente.cambiarPeriodo('7');
    const http = TestBed.inject(HttpTestingController);
    const peticiones = http.match((solicitud) => solicitud.url.endsWith('/dashboard/'));
    for (const peticion of peticiones) {
      peticion.flush({
        total_citas: 0, pacientes: 0, pacientes_nuevos: null, pacientes_recurrentes: null,
        citas: {}, tendencia_diaria: [], por_hora: [], por_dia_semana: [],
        espera: { promedio_minutos: null, personas_en_espera: 0, espera_mayor_15_minutos: 0 },
        recuperacion_turnos: { turnos_liberados: 4, turnos_recuperados: 3, promedio_minutos_para_recuperar: 18 },
        adherencia: { tomas_confirmadas: 8, tomas_omitidas: 2, porcentaje_registro_positivo: 80, seguimientos_pendientes: 1 },
        pagos: null,
      });
    }
    fixture.detectChanges();
    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Recuperación de turnos');
    expect(texto).toContain('Liberados');
    expect(texto).toContain('Recuperados');
    expect(texto).toContain('Media hasta aceptar una oferta: 18 min.');
    expect(texto).toContain('Registro de medicación');
    expect(texto).toContain('80%');
    expect(texto).toContain('Omitidas2');
    expect(texto).toContain('1 seguimiento pendiente actualmente.');
    http.verify();
  });
});
