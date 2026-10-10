import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';
import { CalendarioProfesionalComponent } from './calendario-profesional.component';
import { CalendarioProfesionalService, type ConexionCalendario } from './calendario-profesional.service';
import { BASE, PROVEEDORES_PRUEBA, iniciarSesionCon } from '../../nucleo/pruebas/sesion-sintetica';

const CONEXION: ConexionCalendario = { id: 'conexion-1', calendar_id: 'primary',
  estado_sincronizacion: 'CONECTADO', ultima_sincronizacion_en: null, expira_en: null, ultimo_error: null };

describe('Mi calendario profesional', () => {
  let fixture: ComponentFixture<CalendarioProfesionalComponent>;
  let componente: CalendarioProfesionalComponent;
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [CalendarioProfesionalComponent], providers: PROVEEDORES_PRUEBA });
    iniciarSesionCon(['profesional.conectar_calendario']);
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(CalendarioProfesionalComponent);
    componente = fixture.componentInstance;
    fixture.detectChanges();
  });
  afterEach(() => http.verify());
  function abrir(): void {
    componente.abrir();
    http.expectOne(`${BASE}/calendario/conexiones`).flush({ elementos: [CONEXION] });
    fixture.detectChanges();
  }
  it('no consulta calendarios al montar la Agenda', () => {
    http.expectNone(`${BASE}/calendario/conexiones`);
    expect(fixture.nativeElement.textContent).toContain('Mi Google Calendar');
  });
  it('oculta el acceso y no consulta sin permiso', () => {
    iniciarSesionCon([]); fixture.detectChanges(); componente.abrir();
    expect(componente.abierta()).toBe(false);
    expect(fixture.nativeElement.textContent).not.toContain('Mi Google Calendar');
  });
  it('abre una ventana y muestra solo las conexiones devueltas', () => {
    abrir();
    expect(fixture.nativeElement.querySelector('[role="dialog"]')).not.toBeNull();
    expect(fixture.nativeElement.textContent).toContain('primary');
    expect(fixture.nativeElement.querySelector('.ventana__pie').textContent).toContain('Actualizar estado');
  });
  it('envía el calendario elegido y bloquea doble envío y cierre', () => {
    abrir(); componente.calendarId = ' calendario@example.invalid ';
    const navegar = vi.spyOn(TestBed.inject(CalendarioProfesionalService), 'validarUrlGoogle');
    componente.conectar(); componente.conectar(); componente.cerrar();
    expect(componente.abierta()).toBe(true);
    const peticion = http.expectOne(`${BASE}/calendario/oauth/inicio`);
    expect(peticion.request.body).toEqual({ calendar_id: 'calendario@example.invalid' });
    peticion.flush({ url_autorizacion: 'https://accounts.google.com/o/oauth2/v2/auth?state=sintetico' });
    expect(navegar).toHaveBeenCalledOnce();
    fixture.detectChanges();
    const enlace = fixture.nativeElement.querySelector('a[target="_blank"]') as HTMLAnchorElement;
    expect(enlace.rel).toBe('noopener noreferrer');
    expect(enlace.href).toContain('https://accounts.google.com/');
    expect(componente.ocupada()).toBe(false);
  });
  it('retiene el calendario y permite reintentar si falta configuración', () => {
    abrir(); componente.calendarId = 'primary'; componente.conectar();
    http.expectOne(`${BASE}/calendario/oauth/inicio`).flush({ mensaje: 'Configure Integraciones' }, { status: 503, statusText: 'Service Unavailable' });
    expect(componente.ocupada()).toBe(false); expect(componente.abierta()).toBe(true);
    expect(componente.calendarId).toBe('primary'); expect(componente.error()).toBe('Configure Integraciones');
  });
  it('sincroniza la conexión elegida y actualiza su estado', () => {
    abrir(); componente.sincronizar(CONEXION); componente.sincronizar(CONEXION);
    const peticion = http.expectOne(`${BASE}/calendario/conexiones/conexion-1/sincronizacion`);
    expect(peticion.request.method).toBe('POST');
    peticion.flush({ creados: 1, actualizados: 0, eliminados: 0, recreados: 0, conflictos: 0, reintentables: 0, errores: 0, sin_conexion: 0, token_vencido: 0 });
    http.expectOne(`${BASE}/calendario/conexiones`).flush({ elementos: [CONEXION] });
    expect(componente.mensaje()).toContain('Creados: 1');
  });
  it('exige motivo y conserva la confirmación ante un rechazo', () => {
    abrir(); componente.prepararDesconexion(CONEXION); componente.motivo = '  '; componente.desconectar();
    http.expectNone(`${BASE}/calendario/conexiones/conexion-1/desconexion`);
    componente.motivo = 'Cambio de cuenta'; componente.desconectar(); componente.desconectar();
    const peticion = http.expectOne(`${BASE}/calendario/conexiones/conexion-1/desconexion`);
    expect(peticion.request.body).toEqual({ motivo: 'Cambio de cuenta' });
    peticion.flush({}, { status: 409, statusText: 'Conflict' });
    expect(componente.confirmando()).toEqual(CONEXION); expect(componente.motivo).toBe('Cambio de cuenta');
    expect(componente.ocupada()).toBe(false);
  });
  it('termina la desconexión y recarga la lista', () => {
    abrir(); componente.prepararDesconexion(CONEXION); componente.motivo = 'Cambio de cuenta'; componente.desconectar();
    http.expectOne(`${BASE}/calendario/conexiones/conexion-1/desconexion`).flush({ ...CONEXION, estado_sincronizacion: 'DESCONECTADO' });
    http.expectOne(`${BASE}/calendario/conexiones`).flush({ elementos: [] });
    expect(componente.confirmando()).toBeNull(); expect(componente.mensaje()).toContain('desconectado');
  });
  it('descarta la respuesta de una ventana ya cerrada', () => {
    componente.abrir(); const antigua = http.expectOne(`${BASE}/calendario/conexiones`);
    componente.cerrar(); componente.abrir();
    http.expectOne(`${BASE}/calendario/conexiones`).flush({ elementos: [] });
    antigua.flush({ elementos: [CONEXION] });
    expect(componente.conexiones()).toEqual([]);
  });
  it.each(['https://malicioso.example.invalid/o/oauth2/v2/auth', 'http://accounts.google.com/o/oauth2/v2/auth',
    'https://usuario@accounts.google.com/o/oauth2/v2/auth', 'https://accounts.google.com/otro'])('rechaza una redirección no autorizada: %s', url => {
    expect(() => TestBed.inject(CalendarioProfesionalService).validarUrlGoogle(url)).toThrow();
  });
});
