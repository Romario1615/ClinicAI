/**
 * Matriz de accesos: «Gestiona» con algún permiso de escritura, «Consulta»
 * con solo lectura, «Sin acceso» sin permisos del módulo.
 */
import { TestBed } from '@angular/core/testing';

import { MatrizAccesosComponent } from './matriz-accesos.component';

describe('MatrizAccesosComponent', () => {
  it('resume los permisos de cada rol por módulo', () => {
    TestBed.configureTestingModule({ imports: [MatrizAccesosComponent] });
    const fixture = TestBed.createComponent(MatrizAccesosComponent);
    fixture.componentRef.setInput('roles', [
      { id: 'r1', nombre: 'Recepción', permisos: ['agenda.leer', 'cita.crear', 'paciente.leer_administrativo'] },
      { id: 'r2', nombre: 'Auditoría', permisos: ['agenda.leer', 'historia_clinica.leer_metadatos'] },
    ]);
    fixture.detectChanges();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const filas = (fixture.componentInstance as any).filas();
    const nivel = (modulo: string, i: number) =>
      filas.find((f: { modulo: string }) => f.modulo === modulo).celdas[i].nivel;
    expect(nivel('Agenda y citas', 0)).toBe('gestiona');
    expect(nivel('Agenda y citas', 1)).toBe('consulta');
    expect(nivel('Pacientes y consentimientos', 0)).toBe('consulta');
    expect(nivel('Historia clínica', 0)).toBe('ninguno');
    expect(nivel('Historia clínica', 1)).toBe('metadatos');
    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Recepción');
    expect(texto).toContain('Gestiona');
    expect(texto).toContain('Sin acceso');
  });
});
