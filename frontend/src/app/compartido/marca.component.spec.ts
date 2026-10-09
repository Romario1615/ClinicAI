import { TestBed } from '@angular/core/testing';
import { MarcaComponent } from './marca.component';

describe('MarcaComponent · identidad ClinicAI', () => {
  beforeEach(() => TestBed.configureTestingModule({ imports: [MarcaComponent] }));

  it('presenta la marca como una imagen accesible sin repetir el nombre', () => {
    const f = TestBed.createComponent(MarcaComponent);
    f.detectChanges();
    const marca: HTMLElement = f.nativeElement.querySelector('.marca');
    const simbolo = marca.querySelector('img')!;
    expect(marca.getAttribute('role')).toBe('img');
    expect(marca.getAttribute('aria-label')).toBe('ClinicAI · Gestión clínica con inteligencia artificial');
    expect(simbolo.getAttribute('src')).toBe('/images/clinicai-simbolo.svg');
    expect(simbolo.getAttribute('alt')).toBe('');
    expect(simbolo.getAttribute('width')).toBe('96');
    expect(simbolo.getAttribute('height')).toBe('96');
    expect(marca.querySelector('.marca__texto')?.getAttribute('aria-hidden')).toBe('true');
    expect(marca.querySelector('.marca__nombre')?.textContent).toBe('ClinicAI');
    expect(marca.querySelector('.marca__descriptor')?.textContent).toBe('Gestión clínica con IA');
  });

  it('usa el modo compacto sin descriptor en la cabecera móvil', () => {
    const f = TestBed.createComponent(MarcaComponent);
    f.componentRef.setInput('compacta', true);
    f.componentRef.setInput('fondoClaro', true);
    f.detectChanges();
    const marca: HTMLElement = f.nativeElement.querySelector('.marca');
    expect(marca.classList.contains('marca--compacta')).toBe(true);
    expect(marca.classList.contains('marca--clara')).toBe(true);
    expect(marca.querySelector('.marca__descriptor')).toBeNull();
    expect(marca.querySelector('.marca__nombre')?.textContent).toBe('ClinicAI');
  });

  it('destaca el logo de portada y conserva el descriptor', () => {
    const f = TestBed.createComponent(MarcaComponent);
    f.componentRef.setInput('destacada', true);
    f.detectChanges();
    expect(f.nativeElement.querySelector('.marca--destacada')).not.toBeNull();
    expect(f.nativeElement.querySelector('.marca__descriptor')).not.toBeNull();
  });

  it('restaura el descriptor al salir del modo compacto', () => {
    const f = TestBed.createComponent(MarcaComponent);
    f.componentRef.setInput('compacta', true);
    f.detectChanges();
    expect(f.nativeElement.querySelector('.marca__descriptor')).toBeNull();
    f.componentRef.setInput('compacta', false);
    f.detectChanges();
    expect(f.nativeElement.querySelector('.marca__descriptor')?.textContent).toBe('Gestión clínica con IA');
  });
});
