import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { Subject } from 'rxjs';
import { CambiarContrasenaComponent } from './cambiar-contrasena.component';
import { OperacionesService } from '../../nucleo/servicios/operaciones.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { FalloApi } from '../../nucleo/servicios/api.service';

describe('Cambio de contraseña', () => {
  let respuesta: Subject<void>;
  let guardar: ReturnType<typeof vi.fn>;
  let limpiar: ReturnType<typeof vi.fn>;
  let navegar: ReturnType<typeof vi.fn>;
  let componente: { actual: string; nueva: string; confirmacion: string; guardar(): void };

  beforeEach(() => {
    respuesta = new Subject<void>();
    guardar = vi.fn().mockReturnValue(respuesta);
    limpiar = vi.fn();
    navegar = vi.fn().mockResolvedValue(true);
    TestBed.configureTestingModule({
      imports: [CambiarContrasenaComponent],
      providers: [
        { provide: OperacionesService, useValue: { guardar } },
        { provide: SesionService, useValue: { limpiar } },
        { provide: Router, useValue: { navigate: navegar } },
      ],
    });
    componente = TestBed.createComponent(CambiarContrasenaComponent).componentInstance as unknown as typeof componente;
    componente.actual = 'InicialSintetica123';
    componente.nueva = 'PersonalSintetica123';
    componente.confirmacion = componente.nueva;
  });

  it.each(['', 'corta', 'x'.repeat(129)])('rechaza una nueva contraseña inválida sin llamar a la API: %s', nueva => {
    componente.nueva = nueva;
    componente.confirmacion = nueva;
    componente.guardar();
    expect(guardar).not.toHaveBeenCalled();
    expect(limpiar).not.toHaveBeenCalled();
  });

  it('rechaza la falta de contraseña inicial y la confirmación diferente', () => {
    componente.actual = '';
    componente.guardar();
    componente.actual = 'InicialSintetica123';
    componente.confirmacion = 'ConfirmacionDiferente123';
    componente.guardar();
    expect(guardar).not.toHaveBeenCalled();
  });

  it('envía una sola petición mientras está pendiente y cierra la sesión al guardar', () => {
    componente.guardar();
    componente.guardar();
    expect(guardar).toHaveBeenCalledTimes(1);
    expect(guardar).toHaveBeenCalledWith('/autenticacion/cambio-contrasena', {
      contrasena_actual: componente.actual, contrasena_nueva: componente.nueva,
    }, expect.any(String));
    expect(limpiar).not.toHaveBeenCalled();
    respuesta.next();
    expect(limpiar).toHaveBeenCalledOnce();
    expect(navegar).toHaveBeenCalledWith(['/acceso']);
  });

  it('permite corregir y reintentar un rechazo sin cerrar la sesión', () => {
    componente.guardar();
    respuesta.error(new FalloApi('DATOS_INVALIDOS', 'No coincide la contraseña inicial.', 422));
    respuesta = new Subject<void>();
    guardar.mockReturnValue(respuesta);
    componente.guardar();
    expect(guardar).toHaveBeenCalledTimes(2);
    expect(limpiar).not.toHaveBeenCalled();
  });
});
