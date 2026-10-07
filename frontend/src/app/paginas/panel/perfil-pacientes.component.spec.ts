import { TestBed } from '@angular/core/testing';

import type { ResumenPanel } from '../../nucleo/servicios/operaciones.service';
import { PerfilPacientesComponent } from './perfil-pacientes.component';

describe('PerfilPacientesComponent', () => {
  function montar(demografia: ResumenPanel['demografia'] = null) {
    TestBed.configureTestingModule({ imports: [PerfilPacientesComponent] });
    const fixture = TestBed.createComponent(PerfilPacientesComponent);
    fixture.componentRef.setInput('demografia', demografia);
    fixture.detectChanges();
    return fixture;
  }

  it('explica la protección del desglose cuando no hay datos publicables', () => {
    const fixture = montar();
    const elemento = fixture.nativeElement as HTMLElement;
    expect(elemento.querySelector('[role="status"]')?.textContent).toContain('menos de 5 pacientes');
    expect(elemento.querySelector('.demografia__rejilla')).toBeNull();
  });

  it('separa categoría, barra y valor y conserva ocultas las celdas protegidas', () => {
    const fixture = montar({
      edades: [
        { categoria: 'Sin fecha de nacimiento', pacientes: null, suprimida: true },
        { categoria: '18-29 años', pacientes: 5, suprimida: false },
        { categoria: '30-44 años', pacientes: 10, suprimida: false },
      ],
      sexos: [{ categoria: 'Sin registrar', pacientes: null, suprimida: true }],
    });
    const elemento = fixture.nativeElement as HTMLElement;
    const filas = Array.from(elemento.querySelectorAll('.demografia__fila'));
    expect(filas).toHaveLength(4);
    for (const fila of filas) {
      expect(fila.querySelector('.demografia__categoria')).not.toBeNull();
      expect(fila.querySelector('.demografia__pista')?.getAttribute('aria-hidden')).toBe('true');
      expect(fila.querySelector('.demografia__valor')).not.toBeNull();
    }
    expect(elemento.querySelectorAll('.demografia__valor--protegido')).toHaveLength(2);
    expect(filas[0].querySelector('.demografia__pista > span')).toBeNull();
    expect(filas[3].querySelector('.demografia__pista > span')).toBeNull();
    expect(filas[1].querySelector<HTMLElement>('.demografia__pista > span')?.style.width).toBe('50%');
    expect(filas[2].querySelector<HTMLElement>('.demografia__pista > span')?.style.width).toBe('100%');
    expect(elemento.querySelectorAll('h4.cifra__titulo')).toHaveLength(2);
  });

  it('actualiza las filas con los filtros y retira el desglose al quedar protegido', () => {
    const fixture = montar({
      edades: [{ categoria: '18-29 años', pacientes: 10, suprimida: false }],
      sexos: [],
    });
    fixture.componentRef.setInput('demografia', {
      edades: [{ categoria: '60 o más', pacientes: 20, suprimida: false }],
      sexos: [],
    });
    fixture.detectChanges();
    const elemento = fixture.nativeElement as HTMLElement;
    expect(elemento.querySelector('.demografia__categoria')?.textContent).toBe('60 o más');
    expect(elemento.querySelector('.demografia__valor')?.textContent).toBe('20');
    expect(elemento.textContent).not.toContain('18-29 años');
    fixture.componentRef.setInput('demografia', null);
    fixture.detectChanges();
    expect(elemento.querySelectorAll('.demografia__fila')).toHaveLength(0);
    expect(elemento.querySelector('[role="status"]')).not.toBeNull();
  });

  it('muestra ceros sin pintar barras ni producir porcentajes inválidos', () => {
    const fixture = montar({
      edades: [{ categoria: 'Fecha no válida', pacientes: 0, suprimida: false }],
      sexos: [{ categoria: 'Sin registrar', pacientes: 0, suprimida: false }],
    });
    const elemento = fixture.nativeElement as HTMLElement;
    expect(elemento.querySelectorAll('.demografia__pista > span')).toHaveLength(0);
    expect(Array.from(elemento.querySelectorAll('.demografia__valor')).map((valor) => valor.textContent)).toEqual(['0', '0']);
  });
});
