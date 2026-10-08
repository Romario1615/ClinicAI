import { TestBed } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';
import { RegistrosPacienteComponent } from './registros-paciente.component';
import { BASE, PROVEEDORES_PRUEBA, iniciarSesionCon, identidadCon } from '../nucleo/pruebas/sesion-sintetica';
import { SesionService } from '../nucleo/servicios/sesion.service';
import { EspecialidadHistoriaService } from '../nucleo/servicios/especialidad-historia.service';
import type { RegistroPaciente } from '../nucleo/servicios/registros-paciente.service';

describe('RegistrosPacienteComponent', () => {
  beforeEach(() => TestBed.configureTestingModule({ imports: [RegistrosPacienteComponent], providers: PROVEEDORES_PRUEBA }));
  afterEach(() => TestBed.inject(HttpTestingController).verify());

  const registro: RegistroPaciente = { id: 'r-1', raiz_id: 'r-1', version: 1, titulo: 'Documento sintético', tipo: 'PRESUPUESTO', vigente: true, anulado: false, motivo: 'Registro inicial', creado_en: '2026-10-07T15:00:00Z', profesional_id: 'prof-1', especialidad_id: 'esp-odo', cita_id: null, sede_id: 'sede-1', nivel_sensibilidad: 'N2', contenido: { zonas: [], partidas: [{ descripcion: 'Consulta', cantidad: 2, precio_unitario: 12.35 }], moneda: 'USD', valido_hasta: null, paciente: 'Paciente sintético', clinica: 'Clínica sintética', profesional: 'Profesional sintético', sede: 'Sede sintética', observaciones: '' } };
  function montar(escribir = true, facial = false, registros: RegistroPaciente[] = []) {
    const permisos = escribir ? ['historia_clinica.leer', 'historia_clinica.escribir'] : ['historia_clinica.leer'];
    iniciarSesionCon(permisos); TestBed.inject(SesionService).establecerIdentidad({ ...identidadCon(permisos), profesional_id: 'prof-1' });
    TestBed.inject(EspecialidadHistoriaService).elegir('esp-odo');
    const f = TestBed.createComponent(RegistrosPacienteComponent);
    f.componentRef.setInput('pacienteId', 'pac-1'); f.componentRef.setInput('citaId', 'cita-1'); f.componentRef.setInput('sedeId', 'sede-1'); f.componentRef.setInput('facial', facial); f.detectChanges();
    const http = TestBed.inject(HttpTestingController);
    http.expectOne(`${BASE}/catalogo/sedes`).flush([{ id: 'sede-1', nombre: 'Sede sintética' }]);
    const carga = http.expectOne(r => r.url.endsWith('/pac-1/registros'));
    expect(carga.request.params.get('grupo')).toBe(facial ? 'facial' : 'documentos'); carga.flush(registros);
    if (facial) http.expectOne(`${BASE}/historia/faciograma/zonas`).flush([{ codigo: 'menton', nombre: 'Mentón', x: 160, y: 280 }]);
    f.detectChanges(); return f;
  }

  it('solo ofrece emisión a un profesional con permiso de escritura', () => {
    const f = montar(false);
    expect(f.nativeElement.textContent).not.toContain('Crear documento');
    expect(f.nativeElement.textContent).toContain('Todavía no hay documentos');
  });

  it('abre el documento en ventana y conserva sede y cita al guardar', async () => {
    const f = montar();
    const boton = [...f.nativeElement.querySelectorAll('button')].find((b: unknown) => (b as HTMLElement).textContent?.includes('Crear documento')) as HTMLButtonElement;
    boton.click(); f.detectChanges(); await f.whenStable();
    const concepto: HTMLInputElement = f.nativeElement.querySelector('[name="descripcion0"]'); concepto.value = 'Consulta sintética'; concepto.dispatchEvent(new Event('input')); await f.whenStable();
    f.nativeElement.querySelector('#registro-paciente').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    const http = TestBed.inject(HttpTestingController); const solicitud = http.expectOne(r => r.method === 'POST' && r.url.endsWith('/registros'));
    expect(solicitud.request.body).toMatchObject({ cita_id: 'cita-1', sede_id: 'sede-1', tipo: 'PRESUPUESTO', version_base: 0 });
    expect(solicitud.request.body.partidas[0].descripcion).toBe('Consulta sintética');
    solicitud.flush({ id: 'r-1' }); http.expectOne(r => r.method === 'GET' && r.url.endsWith('/registros')).flush([]); f.detectChanges();
    expect(f.nativeElement.textContent).toContain('Versión guardada');
  });

  it('presenta mapa y campos para observaciones manuales', async () => {
    const f = montar(true, true);
    expect(f.nativeElement.querySelector('svg')).toBeTruthy();
    ([...f.nativeElement.querySelectorAll('button')].find((b: unknown) => (b as HTMLElement).textContent?.includes('Nuevo registro facial')) as HTMLButtonElement).click(); f.detectChanges(); await f.whenStable();
    const puntos = f.nativeElement.querySelectorAll('g[role="button"]'); (puntos[puntos.length - 1] as SVGGElement).dispatchEvent(new MouseEvent('click', { bubbles: true })); f.detectChanges();
    expect(f.nativeElement.querySelector('[name="observacionZona"]')).toBeTruthy();
    expect(f.nativeElement.textContent).toContain('Procedimiento registrado por el especialista');
  });

  it('la corrección mantiene el tipo y la cita original incluso si era nula', async () => {
    const f = montar(true, false, [registro]); f.componentInstance['editar'](registro); f.detectChanges(); await f.whenStable();
    expect(f.nativeElement.querySelector('[name="tipo"]').disabled).toBe(true);
    f.componentInstance['motivo'] = 'Corrección sintética'; f.componentInstance['guardar']();
    const http = TestBed.inject(HttpTestingController); const peticion = http.expectOne(r => r.method === 'POST');
    expect(peticion.request.body).toMatchObject({ raiz_id: 'r-1', version_base: 1, cita_id: null, tipo: 'PRESUPUESTO' });
    peticion.flush({}, { status: 409, statusText: 'Conflict' }); f.detectChanges();
    expect(f.nativeElement.querySelector('[role="alert"]')).toBeTruthy(); f.componentInstance['cerrarEditor']();
  });
  it('anula con motivo y recarga el historial', () => {
    const f = montar(true, false, [registro]); f.componentInstance['pedirAnulacion'](registro); f.componentInstance['motivo'] = 'Anulación sintética'; f.componentInstance['anular']();
    const http = TestBed.inject(HttpTestingController); const peticion = http.expectOne(`${BASE}/historia/pacientes/pac-1/registros/r-1/anulacion`);
    expect(peticion.request.body.motivo).toBe('Anulación sintética'); peticion.flush({});
    http.expectOne(r => r.method === 'GET' && r.url.endsWith('/registros')).flush([]); f.detectChanges(); expect(f.nativeElement.textContent).toContain('Registro anulado');
  });
  it('registra el envío sandbox después de comprobar el destinatario', () => {
    const f = montar(true, false, [registro]); f.componentInstance['pedirEnvio'](registro); f.componentInstance['enviar']();
    const http = TestBed.inject(HttpTestingController); http.expectNone(r => r.method === 'POST');
    f.componentInstance['confirmoDestinatario'] = true; f.componentInstance['enviar']();
    const peticion = http.expectOne(`${BASE}/historia/pacientes/pac-1/registros/r-1/whatsapp`);
    expect(peticion.request.body.identidad_destinatario_confirmada).toBe(true); peticion.flush({ modo: 'sandbox', estado: 'PENDIENTE' }); f.detectChanges();
    expect(f.nativeElement.textContent).toContain('WhatsApp sandbox');
  });
  it('muestra el estado real de la solicitud configurada y un error de entrega', () => {
    const f = montar(true, false, [registro]); const http = TestBed.inject(HttpTestingController);
    f.componentInstance['pedirEnvio'](registro); f.componentInstance['confirmoDestinatario'] = true; f.componentInstance['enviar']();
    http.expectOne(r => r.method === 'POST').flush({ modo: 'cloud_api', estado: 'PENDIENTE' }); f.detectChanges(); expect(f.nativeElement.textContent).toContain('Envío registrado: PENDIENTE');
    f.componentInstance['pedirEnvio'](registro); f.componentInstance['confirmoDestinatario'] = true; f.componentInstance['enviar']();
    http.expectOne(r => r.method === 'POST').flush({}, { status: 403, statusText: 'Forbidden' }); f.detectChanges(); expect(f.nativeElement.querySelector('[role="alert"]')).toBeTruthy();
  });
  it('amplía la lista sin perder las versiones anteriores', () => {
    const registros = Array.from({ length: 50 }, (_, i) => ({ ...registro, id: `r-${i}` }));
    const f = montar(true, false, registros); f.componentInstance['cargar'](true);
    const peticion = TestBed.inject(HttpTestingController).expectOne(r => r.url.endsWith('/registros'));
    expect(peticion.request.params.get('desplazamiento')).toBe('50'); peticion.flush([{ ...registro, id: 'siguiente' }]); f.detectChanges();
    expect(f.nativeElement.querySelectorAll('article.registro').length).toBe(51);
  });
  it('las zonas se agregan, actualizan y retiran dentro de la nueva versión', () => {
    const f = montar(true, true); const c = f.componentInstance;
    c['editar'](); c['elegirZona']('menton'); c['zonaObservacion'] = 'Evaluación sintética'; c['registrarZona']();
    expect(c['zonas']).toHaveLength(1); expect(c['nombreZona']('menton')).toBe('Mentón');
    c['elegirZona']('menton'); expect(c['zonaObservacion']).toBe('Evaluación sintética'); c['quitarZona']('menton'); expect(c['zonas']).toHaveLength(0);
    c['agregarPartida'](); c['quitarPartida'](0); expect(c['partidas']).toHaveLength(1);
    c['cerrarEditor']();
  });
  it('pulsar el punto abre su evaluación y guarda la corrección como versión', async () => {
    const facial: RegistroPaciente = { ...registro, tipo: 'FACIOGRAMA', contenido: { ...registro.contenido, partidas: [], zonas: [{ zona: 'menton', estado: 'PLANIFICADO', observacion: 'Evaluación previa sintética', procedimiento: null }] } };
    const f = montar(true, true, [facial]);
    f.nativeElement.querySelector('g[role="button"]').dispatchEvent(new MouseEvent('click', { bubbles: true }));
    f.detectChanges(); await f.whenStable();
    expect(f.nativeElement.querySelector('[name="observacionZona"]').value).toBe('Evaluación previa sintética');
    f.componentInstance['zonaObservacion'] = 'Control actualizado sintético';
    f.componentInstance['motivo'] = 'Corrección de la evaluación';
    f.componentInstance['guardar']();
    const http = TestBed.inject(HttpTestingController);
    const post = http.expectOne(r => r.method === 'POST');
    expect(post.request.body).toMatchObject({ raiz_id: 'r-1', version_base: 1, tipo: 'FACIOGRAMA', zonas: [{ zona: 'menton', observacion: 'Control actualizado sintético' }] });
    post.flush({}); http.expectOne(r => r.method === 'GET' && r.url.endsWith('/registros')).flush([]);
    http.expectOne(`${BASE}/historia/faciograma/zonas`).flush([]);
  });
  it('consultar el punto de un colega o sin escritura conserva el registro', () => {
    const facial: RegistroPaciente = { ...registro, profesional_id: 'colega', tipo: 'FACIOGRAMA' };
    const f = montar(true, true, [facial]);
    f.componentInstance['abrirPunto']('menton'); f.detectChanges();
    expect(f.componentInstance['detalleZona']()).toBe('menton');
    expect(f.nativeElement.querySelector('#registro-paciente')).toBeNull();
    expect(f.componentInstance['editor']()).toBe(false);
    TestBed.inject(HttpTestingController).expectNone(r => r.method === 'POST');
  });
  it('redondea cada concepto igual que el PDF, incluso con cantidades fraccionarias', () => {
    const f = montar();
    expect(f.componentInstance['total']([{ descripcion: 'Sintético', cantidad: '0.29', precio_unitario: '0.50' }])).toBe(0.15);
    expect(f.componentInstance['total']([{ descripcion: 'Sintético', cantidad: 1.1, precio_unitario: 0.05 }, { descripcion: 'Sintético 2', cantidad: 2, precio_unitario: 12.35 }])).toBe(24.76);
  });
});
