import { TestBed } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';
import { of, Subject, throwError } from 'rxjs';
import { Router } from '@angular/router';
import { AccesoComponent } from './acceso.component';
import { AutenticacionService } from '../../nucleo/servicios/autenticacion.service';
import { BASE, PROVEEDORES_PRUEBA, identidadCon } from '../../nucleo/pruebas/sesion-sintetica';
import { FalloApi } from '../../nucleo/servicios/api.service';

describe('AccesoComponent · especialidades locales', () => {
  const entrar = vi.fn();
  const entrarNormal = vi.fn();
  beforeEach(() => {
    entrar.mockReset().mockReturnValue(of(identidadCon([])));
    entrarNormal.mockReset().mockReturnValue(of(identidadCon([])));
    TestBed.configureTestingModule({ imports: [AccesoComponent], providers: [...PROVEEDORES_PRUEBA, { provide: AutenticacionService, useValue: { iniciarSesionLocal: entrar, iniciarSesion: entrarNormal } }] });
    vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
  });
  afterEach(() => TestBed.inject(HttpTestingController).verify());
  function montar() {
    const f = TestBed.createComponent(AccesoComponent); f.detectChanges();
    TestBed.inject(HttpTestingController).match(`${BASE}/autenticacion/accesos-locales`).forEach(r => r.flush({ habilitado: true, roles: [{ codigo: 'profesional', nombre: 'Profesional de salud', especialidad: 'Odontología' }, { codigo: 'recepcion', nombre: 'Recepción', especialidad: null }], especialidades_profesionales: [{ id: 'odo', nombre: 'Odontología' }, { id: 'est', nombre: 'Salud estética' }] }));
    f.detectChanges(); return f;
  }
  it('muestra especialidades y entra con el perfil elegido', async () => {
    const f = montar(); await f.whenStable();
    const select: HTMLSelectElement = f.nativeElement.querySelector('[name="especialidadLocal"]');
    select.value = 'est'; select.dispatchEvent(new Event('change')); f.detectChanges(); await f.whenStable();
    const boton = [...f.nativeElement.querySelectorAll('button')].find((b: unknown) => (b as HTMLElement).textContent?.includes('Profesional de salud')) as HTMLButtonElement;
    expect(boton.textContent).toContain('Salud estética'); boton.click();
    expect(entrar).toHaveBeenCalledWith('profesional', 'est');
  });
  it('la selección clínica no cambia el ingreso de recepción', () => {
    const f = montar(); f.componentInstance['especialidadLocal'] = 'est'; f.componentInstance['entrarComo']('recepcion');
    expect(entrar).toHaveBeenCalledWith('recepcion');
  });
  it('mantiene el ingreso profesional predeterminado sin seleccionar', () => {
    const f = montar(); f.componentInstance['entrarComo']('profesional');
    expect(entrar).toHaveBeenCalledWith('profesional');
  });
  it('destaca el logo y el nombre de ClinicAI en la portada', () => {
    const f = montar();
    const marca = f.nativeElement.querySelector('.acceso__logo .marca');
    expect(marca.classList.contains('marca--destacada')).toBe(true);
    expect(marca.classList.contains('marca--compacta')).toBe(false);
    expect(marca.querySelector('img').getAttribute('src')).toBe('/images/clinicai-simbolo.webp');
    expect(marca.querySelector('.marca__nombre').textContent).toBe('ClinicAI');
  });
  it('usa fondos adaptables WebP y conserva la fotografía del equipo', () => {
    const f = montar();
    const fondos = [...f.nativeElement.querySelectorAll('.acceso__foto')] as HTMLImageElement[];
    expect(fondos).toHaveLength(4);
    expect(fondos[0].getAttribute('src')).toBe('/images/acceso-equipo.webp');
    expect(fondos[0].getAttribute('srcset')).toContain('acceso-equipo-900.webp 900w');
    expect(fondos[0].getAttribute('srcset')).toContain('acceso-equipo.webp 1881w');
    expect(fondos.every(img => img.alt === '' && img.getAttribute('src')?.endsWith('.webp'))).toBe(true);
    expect(fondos[0].getAttribute('fetchpriority')).toBe('high');
  });
  it('separa el mensaje principal del bloque de inteligencia artificial', () => {
    const f = montar();
    const titular: HTMLElement = f.nativeElement.querySelector('.acceso__titular');
    expect(titular.children).toHaveLength(2);
    expect(titular.querySelector('.acceso__titular-principal')?.textContent).toContain('para cuidar.');
    expect(titular.querySelector('.acceso__titular-ia')?.textContent).toBe('IA para coordinar.');
  });
  it('ajusta la ilustración al alto reservado en la portada', () => {
    const f = montar();
    expect(f.nativeElement.querySelector('.acceso__grafico').classList.contains('ajustada')).toBe(true);
  });
  it('cada rol conserva su etiqueta y recibe un icono WebP decorativo', () => {
    const f = montar();
    const imagenes = [...f.nativeElement.querySelectorAll('.acceso__rol-icono img')] as HTMLImageElement[];
    expect(imagenes.map(img => img.getAttribute('src'))).toEqual(['/images/acceso-icono-profesional.webp', '/images/acceso-icono-recepcion.webp']);
    expect(imagenes.every(img => img.alt === '')).toBe(true);
    expect(f.componentInstance['iconoRol']('rol-personalizado')).toBe('/images/acceso-icono-seguridad.webp');
  });
  it('anuncia la preparación hasta recibir las opciones del servidor', () => {
    const f = TestBed.createComponent(AccesoComponent); f.detectChanges();
    expect(f.nativeElement.querySelector('[role="status"]').textContent).toContain('Verificando');
    expect(f.nativeElement.querySelector('input[type="password"]')).toBeNull();
    const consultas = TestBed.inject(HttpTestingController).match(`${BASE}/autenticacion/accesos-locales`);
    expect(consultas).toHaveLength(2); // Estado global y opciones actualizadas de la portada.
    consultas.forEach(r => r.flush({ habilitado: false, roles: [] }));
    f.detectChanges();
    expect(f.nativeElement.querySelector('h1').textContent).toBe('Iniciar sesión');
    expect(f.nativeElement.querySelector('input[type="password"]')).not.toBeNull();
  });
  it('conserva el formulario normal cuando falla la consulta local', () => {
    const f = TestBed.createComponent(AccesoComponent); f.detectChanges();
    const consultas = TestBed.inject(HttpTestingController).match(`${BASE}/autenticacion/accesos-locales`);
    expect(consultas).toHaveLength(2);
    consultas.forEach(r => r.flush({}, { status: 503, statusText: 'No disponible' }));
    f.detectChanges();
    expect(f.nativeElement.querySelector('h1').textContent).toBe('Iniciar sesión');
  });
  it('bloquea envíos repetidos y vuelve a habilitar los roles ante un error', () => {
    const pendiente = new Subject(); entrar.mockReturnValue(pendiente);
    const f = montar(); f.componentInstance['entrarComo']('profesional'); f.detectChanges();
    f.componentInstance['entrarComo']('recepcion');
    expect(entrar).toHaveBeenCalledTimes(1);
    expect([...f.nativeElement.querySelectorAll('button')].every((b: unknown) => (b as HTMLButtonElement).disabled)).toBe(true);
    pendiente.error(new FalloApi('NO_DISPONIBLE', 'Inténtalo de nuevo.', 503)); f.detectChanges();
    expect(f.nativeElement.querySelector('[role="alert"]').textContent).toContain('Inténtalo de nuevo.');
    expect([...f.nativeElement.querySelectorAll('button')].every((b: unknown) => !(b as HTMLButtonElement).disabled)).toBe(true);
  });
  it('muestra el segundo factor solo cuando se exige y limpia la contraseña', () => {
    const f = montar(); f.componentInstance['modoAccesoLocal'].set(false);
    entrarNormal.mockReturnValue(throwError(() => new FalloApi('SEGUNDO_FACTOR_REQUERIDO', 'Introduce el código.', 401)));
    f.componentInstance['correo'] = 'sintetico@example.invalid'; f.componentInstance['contrasena'] = 'PruebaSintetica';
    f.componentInstance['entrar'](); f.detectChanges();
    expect(f.componentInstance['contrasena']).toBe('');
    expect(f.nativeElement.querySelector('[name="codigo"]').getAttribute('autocomplete')).toBe('one-time-code');
    expect(f.nativeElement.querySelector('[role="alert"]').textContent).toContain('Introduce el código.');
  });
});
