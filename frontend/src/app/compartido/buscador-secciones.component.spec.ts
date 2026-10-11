import { ComponentFixture, TestBed } from '@angular/core/testing';
import { BuscadorSeccionesComponent, type GrupoSeccionesBuscables } from './buscador-secciones.component';

const GRUPOS: readonly GrupoSeccionesBuscables[] = [
  { id: 'resumen', etiqueta: 'Resumen', enlaces: [
    { ruta: '/analitica', etiqueta: 'Analítica IA', icono: 'panel', demostracion: false },
  ] },
  { id: 'ia', etiqueta: 'Comunicación e IA', enlaces: [
    { ruta: '/agente-demo', etiqueta: 'Agente demo', icono: 'agente', demostracion: true },
  ] },
  { id: 'vacio', etiqueta: 'Sin enlaces', enlaces: [] },
];

describe('BuscadorSeccionesComponent', () => {
  let fixture: ComponentFixture<BuscadorSeccionesComponent>;

  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [BuscadorSeccionesComponent] });
    fixture = TestBed.createComponent(BuscadorSeccionesComponent);
    fixture.componentRef.setInput('grupos', GRUPOS);
    fixture.detectChanges();
  });

  it('omite grupos vacíos y muestra dirección y marca del simulador recibido', () => {
    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.querySelectorAll('h3')).toHaveLength(2);
    expect(raiz.querySelectorAll('a')).toHaveLength(2);
    expect(raiz.querySelector('a[href="/agente-demo"] .secciones-resultados__demo')?.textContent).toBe('demo');
  });

  it('actualiza los resultados al cambiar los enlaces recibidos sin añadir destinos propios', () => {
    const raiz = fixture.nativeElement as HTMLElement;
    const consulta = raiz.querySelector('input')!;
    consulta.value = 'ANALITICA';
    consulta.dispatchEvent(new Event('input', { bubbles: true }));
    fixture.detectChanges();
    expect(raiz.querySelectorAll('a')).toHaveLength(1);
    fixture.componentRef.setInput('grupos', []);
    fixture.detectChanges();
    expect(raiz.querySelectorAll('a')).toHaveLength(0);
    expect(raiz.querySelector('[role="status"]')?.textContent).toContain('0 secciones disponibles');
    expect(consulta.value).toBe('ANALITICA');
  });

  it('transmite destino y gesto originales para que el armazón gestione la navegación', () => {
    const elegir = vi.fn();
    fixture.componentInstance.elegir.subscribe(elegir);
    const evento = new MouseEvent('click', { bubbles: true, cancelable: true });
    // El padre decide si intercepta el enlace; se evita la navegación nativa de jsdom.
    fixture.componentInstance.elegir.subscribe(({ evento: recibido }) => recibido.preventDefault());
    fixture.nativeElement.querySelector('a[href="/analitica"]').dispatchEvent(evento);
    expect(elegir).toHaveBeenCalledWith({ evento, ruta: '/analitica' });
  });

  it('el error queda dentro del diálogo y una navegación pendiente bloquea entrada y cierre', () => {
    const cerrar = vi.fn();
    fixture.componentInstance.cerrar.subscribe(cerrar);
    fixture.componentRef.setInput('error', 'Error sintético de navegación');
    fixture.componentRef.setInput('ocupada', true);
    fixture.detectChanges();
    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.querySelector('dialog [role="alert"]')?.textContent).toBe('Error sintético de navegación');
    expect(raiz.querySelector('input')?.disabled).toBe(true);
    expect(raiz.querySelector('a')?.getAttribute('aria-disabled')).toBe('true');
    raiz.querySelector('dialog')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(cerrar).not.toHaveBeenCalled();
    fixture.componentRef.setInput('ocupada', false);
    fixture.detectChanges();
    raiz.querySelector('dialog')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(cerrar).toHaveBeenCalledOnce();
  });
});
