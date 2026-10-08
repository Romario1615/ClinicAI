import { TestBed } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';
import { of } from 'rxjs';
import { Router } from '@angular/router';
import { AccesoComponent } from './acceso.component';
import { AutenticacionService } from '../../nucleo/servicios/autenticacion.service';
import { BASE, PROVEEDORES_PRUEBA, identidadCon } from '../../nucleo/pruebas/sesion-sintetica';

describe('AccesoComponent · especialidades locales', () => {
  const entrar = vi.fn();
  beforeEach(() => {
    entrar.mockReset().mockReturnValue(of(identidadCon([])));
    TestBed.configureTestingModule({ imports: [AccesoComponent], providers: [...PROVEEDORES_PRUEBA, { provide: AutenticacionService, useValue: { iniciarSesionLocal: entrar } }] });
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
});
