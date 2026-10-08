import { TestBed } from '@angular/core/testing';
import { PROVEEDORES_PRUEBA } from '../../nucleo/pruebas/sesion-sintetica';
import { PortadaPanelComponent } from './portada-panel.component';

describe('PortadaPanelComponent', () => {
  it('presenta el contexto horario y conserva el acceso a la agenda', () => {
    TestBed.configureTestingModule({ imports: [PortadaPanelComponent], providers: PROVEEDORES_PRUEBA });
    const f = TestBed.createComponent(PortadaPanelComponent);
    f.componentRef.setInput('fecha', 'jueves 8 de octubre');
    f.componentRef.setInput('zona', 'America/Guayaquil');
    f.detectChanges();
    const e = f.nativeElement as HTMLElement;
    expect(e.textContent).toContain('jueves 8 de octubre');
    expect(e.textContent).toContain('America/Guayaquil');
    expect(e.querySelector('a')?.getAttribute('href')).toBe('/agenda');
    expect(e.querySelector('app-fondo-ia')).not.toBeNull();
  });
});
