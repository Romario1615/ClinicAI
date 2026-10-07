/**
 * «Revisando como»: una sola especialidad se muestra como etiqueta; con
 * varias se elige y se avisa para recargar.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';

import { SelectorEspecialidadComponent } from './selector-especialidad.component';
import { ODONTOLOGIA_SINTETICA, PROVEEDORES_PRUEBA } from '../nucleo/pruebas/sesion-sintetica';
import { EspecialidadHistoriaService } from '../nucleo/servicios/especialidad-historia.service';

describe('SelectorEspecialidadComponent', () => {
    let fixture: ComponentFixture<SelectorEspecialidadComponent>;
    let servicio: EspecialidadHistoriaService;
    let el: HTMLElement;

    beforeEach(() => {
        TestBed.configureTestingModule({ imports: [SelectorEspecialidadComponent], providers: PROVEEDORES_PRUEBA });
        servicio = TestBed.inject(EspecialidadHistoriaService);
        fixture = TestBed.createComponent(SelectorEspecialidadComponent);
        el = fixture.nativeElement as HTMLElement;
    });

    it('con una sola especialidad la muestra sin botones y avisa de lo compartido', () => {
        fixture.detectChanges();
        expect(el.querySelector('.contexto__unica')?.textContent).toContain('Odontología');
        expect(el.querySelectorAll('button').length).toBe(0);
        expect(el.textContent).toContain('Alergias, medicamentos y recetas se comparten');
    });

    it('con varias, elegir otra la marca y avisa; repetir la misma no', () => {
        servicio.disponibles.set([
            ODONTOLOGIA_SINTETICA,
            { id: 'esp-derm', nombre: 'Dermatología', modulos: ['imagenes'], propia: false },
        ]);
        const avisos: string[] = [];
        fixture.componentInstance.cambio.subscribe((id) => avisos.push(id));
        fixture.detectChanges();

        const botones = Array.from(el.querySelectorAll('button'));
        expect(botones.map((b) => b.getAttribute('aria-pressed'))).toEqual(['true', 'false']);
        expect(botones[0].textContent).toContain('la suya');

        botones[0].click();
        botones[1].click();
        fixture.detectChanges();
        expect(avisos).toEqual(['esp-derm']);
        expect(botones[1].getAttribute('aria-pressed')).toBe('true');
    });

    it('sin especialidades no muestra nada', () => {
        servicio.disponibles.set([]);
        fixture.detectChanges();
        expect(el.textContent?.trim()).toBe('');
    });
});
