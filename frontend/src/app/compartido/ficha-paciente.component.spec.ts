/**
 * Pruebas de la ficha lateral del paciente.
 *
 * Lo que se verifica y por qué importa
 * ------------------------------------
 * **El nivel de verificación se muestra con su consecuencia.** «TELEFONO» no
 * significa nada para quien atiende; «no basta para cancelar sin comprobar
 * identidad» sí. Es la diferencia entre un dato y una instrucción utilizable.
 *
 * **El límite de ámbito se declara.** La ficha dice que no hay información
 * clínica porque el rol no la alcanza. Sin ese texto, un hueco se interpreta
 * como que el paciente no tiene historial.
 *
 * **Si falla el historial, la ficha sigue sirviendo.** La identidad ya está
 * cargada; convertir la pantalla en un error dejaría a recepción sin el
 * teléfono del paciente por no haber podido listar sus citas.
 */
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { FichaPacienteComponent } from './ficha-paciente.component';
import { CONFIGURACION, CONFIGURACION_POR_DEFECTO } from '../nucleo/servicios/configuracion';
import type { Cita, EstadoCita } from '../nucleo/modelos/dominio';
import { Router } from '@angular/router';
import {
  ESPECIALIDAD_SINTETICA,
  ODONTOLOGIA_SINTETICA,
  PROVEEDORES_PRUEBA,
  iniciarSesionCon,
} from '../nucleo/pruebas/sesion-sintetica';
import { EspecialidadHistoriaService } from '../nucleo/servicios/especialidad-historia.service';

const BASE = CONFIGURACION_POR_DEFECTO.urlApi;

function detalle(extra: Record<string, unknown> = {}) {
  return {
    id: 'pac-1',
    tipo_documento: 'CEDULA',
    numero_documento: '9900000001',
    nombre: 'Reyna',
    apellido: 'Jurado',
    telefono_whatsapp: '+593900000001',
    correo: null,
    fecha_nacimiento: null,
    nivel_verificacion: 'TELEFONO',
    sexo: null,
    direccion: null,
    activo: true,
    ...extra,
  };
}

function cita(estado: EstadoCita, inicio: string, extra: Partial<Cita> = {}): Cita {
  return {
    id: `cita-${inicio}`,
    paciente_id: 'pac-1',
    profesional_id: 'prof-1',
    servicio_id: 'srv-1',
    sede_id: 'sede-1',
    consultorio_id: null,
    inicio,
    fin: inicio,
    duracion_minutos: 30,
    minutos_preparacion: 0,
    estado,
    origen: 'PANEL',
    expira_en: null,
    confirmada_en: null,
    llegada_en: null,
    atencion_iniciada_en: null,
    completada_en: null,
    cancelada_en: null,
    motivo_cancelacion: null,
    ...extra,
  };
}

describe('FichaPacienteComponent', () => {
  let fixture: ComponentFixture<FichaPacienteComponent>;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [FichaPacienteComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
        ESPECIALIDAD_SINTETICA,
      ],
    });
    fixture = TestBed.createComponent(FichaPacienteComponent);
    fixture.componentRef.setInput('pacienteId', 'pac-1');
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    // La pestaña de contacto carga los consentimientos; aquí no se prueban.
    http.match((p) => p.url.endsWith('/consentimientos')).forEach((p) => p.flush([]));
    http.verify();
  });

  /** Arranca el panel y responde identidad, foto de perfil e historial. */
  function montar(
    paciente: Record<string, unknown> = detalle(),
    citas: readonly Cita[] = [],
  ): void {
    fixture.detectChanges();
    http.expectOne(`${BASE}/pacientes/pac-1/foto-perfil`).flush(null);
    http.expectOne(`${BASE}/pacientes/pac-1`).flush(paciente);
    fixture.detectChanges();
    const peticion = http.expectOne((r) => r.url === `${BASE}/agenda/citas`);
    peticion.flush({ elementos: citas, total: citas.length, limite: 50, desplazamiento: 0 });
    fixture.detectChanges();
  }

  it('carga en ngOnInit y no en el constructor', () => {
    // Leer una entrada obligatoria en el constructor lanza NG0950 y el panel
    // no llega a pintarse. Que esta prueba llegue a `flush` lo demuestra.
    fixture.detectChanges();
    http.expectOne(`${BASE}/pacientes/pac-1/foto-perfil`).flush(null);
    http.expectOne(`${BASE}/pacientes/pac-1`).flush(detalle());
    fixture.detectChanges();
    http.expectOne((r) => r.url === `${BASE}/agenda/citas`).flush({
      elementos: [],
      total: 0,
      limite: 50,
      desplazamiento: 0,
    });
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Reyna Jurado');
  });

  it('muestra el documento completo: es como se verifica identidad en el mostrador', () => {
    montar();

    expect((fixture.nativeElement as HTMLElement).textContent).toContain('9900000001');
  });

  it('traduce el nivel de verificación a lo que se puede hacer con él', () => {
    montar();

    const aviso = (fixture.nativeElement as HTMLElement).querySelector('.ficha__verificacion');
    expect(aviso?.textContent).toContain('Teléfono verificado');
    expect(aviso?.textContent).toContain('No basta para cancelar');
    expect(aviso?.classList.contains('ficha__verificacion--alerta')).toBeTrue();
  });

  it('no alerta cuando la identidad está comprobada en persona', () => {
    montar(detalle({ nivel_verificacion: 'PRESENCIAL' }));

    expect(
      (fixture.nativeElement as HTMLElement)
        .querySelector('.ficha__verificacion')
        ?.classList.contains('ficha__verificacion--alerta'),
    ).toBeFalse();
  });

  it('avisa de un nivel desconocido en lugar de callar', () => {
    // Un valor nuevo en el backend no puede degradar en silencio a «todo bien».
    montar(detalle({ nivel_verificacion: 'INVENTADO' }));

    expect(
      (fixture.nativeElement as HTMLElement).querySelector('.ficha__verificacion')?.textContent,
    ).toContain('desconocido');
  });

  it('declara que no hay datos clínicos y por qué', () => {
    montar();

    const limite = (fixture.nativeElement as HTMLElement).querySelector('.ficha__limite');
    expect(limite?.textContent).toContain('Sin información clínica');
    expect(limite?.textContent).toContain('su rol no los alcanza');
  });

  it('elige como próxima cita la primera futura que todavía cuenta', () => {
    const futuro = new Date(Date.now() + 86_400_000).toISOString();
    const masFuturo = new Date(Date.now() + 172_800_000).toISOString();
    const pasado = new Date(Date.now() - 86_400_000).toISOString();

    montar(detalle(), [
      cita('COMPLETED', pasado),
      cita('CONFIRMED', masFuturo),
      cita('CONFIRMED', futuro),
      // Una cancelada futura no es la próxima cita de nadie.
      cita('CANCELLED', futuro),
    ]);

    const proxima = fixture.componentInstance['proxima']();
    expect(proxima?.inicio).toBe(futuro);
    expect(proxima?.estado).toBe('CONFIRMED');
  });

  it('avisa del turno apartado que puede caducar', () => {
    const futuro = new Date(Date.now() + 3_600_000).toISOString();
    montar(detalle(), [cita('HELD', futuro, { expira_en: futuro })]);

    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Turno apartado sin confirmar');
  });

  it('destaca la reincidencia en inasistencias, que cambia cómo se confirma', () => {
    const pasado = new Date(Date.now() - 86_400_000).toISOString();
    const masPasado = new Date(Date.now() - 172_800_000).toISOString();
    montar(detalle(), [cita('NO_SHOW', pasado), cita('NO_SHOW', masPasado)]);

    const banderas = (fixture.nativeElement as HTMLElement).querySelector('.ficha__banderas');
    expect(banderas?.textContent).toContain('2 inasistencias');
  });

  it('avisa cuando no hay teléfono: ese paciente no recibe nada automático', () => {
    montar(detalle({ telefono_whatsapp: null }));

    expect(
      (fixture.nativeElement as HTMLElement).querySelector('.ficha__banderas')?.textContent,
    ).toContain('Sin teléfono de WhatsApp');
  });

  it('si falla el historial, la ficha sigue sirviendo', () => {
    fixture.detectChanges();
    http.expectOne(`${BASE}/pacientes/pac-1`).flush(detalle());
    fixture.detectChanges();
    http.expectOne(`${BASE}/pacientes/pac-1/foto-perfil`).flush(null);
    http
      .expectOne((r) => r.url === `${BASE}/agenda/citas`)
      .flush({ codigo: 'PERMISO_DENEGADO', mensaje: 'No' }, { status: 403, statusText: 'Forbidden' });
    fixture.detectChanges();

    const elemento = fixture.nativeElement as HTMLElement;
    // No se convierte en pantalla de error: la identidad ya estaba cargada.
    expect(elemento.querySelector('.ficha__error')).toBeNull();
    expect(elemento.textContent).toContain('Reyna Jurado');
  });

  it('si falla la identidad, lo dice en lugar de mostrar una ficha vacía', () => {
    fixture.detectChanges();
    http.expectOne(`${BASE}/pacientes/pac-1/foto-perfil`).flush(null);
    http
      .expectOne(`${BASE}/pacientes/pac-1`)
      .flush({ codigo: 'NO_ENCONTRADO', mensaje: 'No existe' }, { status: 404, statusText: 'NF' });
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).querySelector('.ficha__error')).not.toBeNull();
  });

  it('cambia de pestaña sin volver a pedir nada', () => {
    const pasado = new Date(Date.now() - 86_400_000).toISOString();
    montar(detalle(), [cita('COMPLETED', pasado)]);

    const pestanas = (fixture.nativeElement as HTMLElement).querySelectorAll(
      '.ficha__pestana',
    ) as NodeListOf<HTMLButtonElement>;
    pestanas[2].click();
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).textContent).toContain('WhatsApp');
    // `http.verify()` en afterEach falla si se hubiera pedido algo más.
  });

  it('emite el cierre en lugar de navegar', () => {
    montar();

    let cerrado = false;
    fixture.componentInstance.cerrar.subscribe(() => (cerrado = true));
    ((fixture.nativeElement as HTMLElement).querySelector('.ficha__cerrar') as HTMLButtonElement).click();

    expect(cerrado).toBeTrue();
  });
});

describe('FichaPacienteComponent con permisos clínicos', () => {
  let fixture: ComponentFixture<FichaPacienteComponent>;
  let http: HttpTestingController;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let c: any;

  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [FichaPacienteComponent], providers: PROVEEDORES_PRUEBA });
    http = TestBed.inject(HttpTestingController);
    iniciarSesionCon(['historia_clinica.leer', 'receta.leer', 'odontograma.leer', 'plan_tratamiento.leer']);
    fixture = TestBed.createComponent(FichaPacienteComponent);
    c = fixture.componentInstance;
    fixture.componentRef.setInput('pacienteId', 'pac-1');
    fixture.componentRef.setInput('sinCabecera', true);
    fixture.detectChanges();
    http.expectOne(`${BASE}/pacientes/pac-1/foto-perfil`).flush(null);
    http.expectOne(`${BASE}/pacientes/pac-1`).flush(detalle());
    http.expectOne((r) => r.url === `${BASE}/agenda/citas`).flush({ elementos: [], total: 0, limite: 50, desplazamiento: 0 });
    fixture.detectChanges();
  });

  afterEach(() => {
    http.match((p) => p.url.endsWith('/resumen-clinico')).forEach((p) => p.flush({ codigo: 'X', mensaje: 'x' }, { status: 403, statusText: 'F' }));
    http.verify();
  });

  it('muestra pestañas y atajos clínicos según permisos y pide lo clínico al abrirlo', () => {
    const claves = c.pestanas().map((p: { clave: string }) => p.clave);
    expect(claves).toEqual(['resumen', 'citas', 'contacto', 'historia', 'odontograma', 'planes']);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Información clínica');
    expect((fixture.nativeElement as HTMLElement).textContent).not.toContain('su rol no los alcanza');

    c.elegir('historia');
    http.expectOne((r) => r.url === `${BASE}/historia/pacientes/pac-1/notas` && r.params.get('especialidad_id') === 'esp-odo').flush([
      { id: 'n1', tipo: 'EVOLUCION', motivo_consulta: 'Control sintético', creado_en: '2026-10-01T10:00:00Z' },
      { id: 'n2', tipo: 'EVOLUCION', motivo_consulta: null, creado_en: '2026-10-03T10:00:00Z' },
    ]);
    http.expectOne(`${BASE}/historia/pacientes/pac-1/recetas`).flush([
      { id: 'r1', estado: 'CONFIRMADA', creado_en: '2026-10-02T10:00:00Z', medicamentos: [{ nombre: 'Sintético', dosis: '1 unidad' }] },
      { id: 'r2', estado: 'OTRO', creado_en: '2026-10-02T10:00:00Z', medicamentos: [] },
    ]);
    fixture.detectChanges();
    expect(c.notas()[0].id).toBe('n2');
    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Control sintético');
    expect(texto).toContain('Confirmada');
    expect(texto).toContain('Sintético 1 unidad');
    expect(texto).toContain('Sin medicamentos');

    // Volver a la pestaña no repite la lectura auditada.
    c.elegir('resumen');
    c.elegir('historia');

    const navegar = spyOn(TestBed.inject(Router), 'navigate').and.resolveTo(true);
    let cerrado = false;
    c.cerrar.subscribe(() => (cerrado = true));
    c.abrirHistoria();
    expect(navegar).toHaveBeenCalledWith(['/historia-clinica'], { queryParams: { paciente: 'pac-1' } });
    expect(cerrado).toBeTrue();
  });

  it('al revisar desde otra especialidad cambia sus módulos y vuelve a pedir las notas', () => {
    const especialidades = TestBed.inject(EspecialidadHistoriaService);
    especialidades.disponibles.set([
      ODONTOLOGIA_SINTETICA,
      { id: 'esp-derm', nombre: 'Dermatología', modulos: ['imagenes'], propia: false },
    ]);
    // Sin pintar: aquí no se prueba el odontograma, solo que su pestaña se cierra.
    c.elegir('odontograma');

    especialidades.elegir('esp-derm');
    c.cambiarEspecialidad();
    // Sin odontograma ni planes en dermatología; la pestaña abierta se cierra.
    expect(c.pestanas().map((p: { clave: string }) => p.clave)).toEqual(['resumen', 'citas', 'contacto', 'historia']);
    expect(c.pestana()).toBe('resumen');

    c.elegir('historia');
    http
      .expectOne((r) => r.url.endsWith('/notas') && r.params.get('especialidad_id') === 'esp-derm')
      .flush([]);
    http.expectOne(`${BASE}/historia/pacientes/pac-1/recetas`).flush([]);
    c.cambiarEspecialidad();
    http
      .expectOne((r) => r.url.endsWith('/notas') && r.params.get('especialidad_id') === 'esp-derm')
      .flush([]);
    http.expectOne(`${BASE}/historia/pacientes/pac-1/recetas`).flush([]);
  });

  it('explica la falta de relación asistencial', () => {
    c.elegir('historia');
    http
      .expectOne((r) => r.url === `${BASE}/historia/pacientes/pac-1/notas`)
      .flush({ codigo: 'RELACION_ASISTENCIAL_REQUERIDA', mensaje: 'x' }, { status: 403, statusText: 'F' });
    http
      .expectOne(`${BASE}/historia/pacientes/pac-1/recetas`)
      .flush({ codigo: 'X', mensaje: 'Sin acceso a recetas' }, { status: 403, statusText: 'F' });
    expect(c.avisoClinico()).toBe('Sin acceso a recetas');
    expect(c.cargandoClinico()).toBeFalse();
  });
});
