import { PROVEEDORES_PRUEBA } from '../../nucleo/pruebas/sesion-sintetica';
import type { MockedObject } from "vitest";
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { of, throwError } from 'rxjs';

import { CatalogoService, type SedeGestion } from '../../nucleo/servicios/catalogo.service';
import { SedesConfiguracionComponent } from './sedes-configuracion.component';

const sede: SedeGestion = {
    id: 'sede-1',
    nombre: 'Centro',
    direccion: 'Av. Salud 100',
    telefono: null,
    zona_horaria: 'America/Guayaquil',
    minutos_antelacion_minima: 60,
};

describe('SedesConfiguracionComponent', () => {
    let fixture: ComponentFixture<SedesConfiguracionComponent>;
    let catalogo: MockedObject<CatalogoService>;

    beforeEach(() => {
        catalogo = {
            sedesGestion: vi.fn().mockName("CatalogoService.sedesGestion"),
            actualizarSede: vi.fn().mockName("CatalogoService.actualizarSede")
        } as unknown as MockedObject<CatalogoService>;
        catalogo.sedesGestion.mockReturnValue(of([sede]));
        catalogo.actualizarSede.mockImplementation((_id, datos) => of({ ...datos, id: sede.id }));

        TestBed.configureTestingModule({
            imports: [SedesConfiguracionComponent],
            providers: [...PROVEEDORES_PRUEBA,{ provide: CatalogoService, useValue: catalogo }],
        });
        fixture = TestBed.createComponent(SedesConfiguracionComponent);
        fixture.detectChanges();
    });

    it('lista los datos operativos de las sedes administrables', () => {
        expect(catalogo.sedesGestion).toHaveBeenCalled();
        expect(fixture.nativeElement.textContent).toContain('Centro');
        expect(fixture.nativeElement.textContent).toContain('Av. Salud 100');
        expect(fixture.nativeElement.textContent).toContain('60 minutos');
    });

    it('edita la sede en una ventana Liquid Glass y persiste los cambios', async () => {
        const editar = fixture.debugElement.query(By.css('.sede__cabecera > button'));
        expect(editar).not.toBeNull();
        editar.triggerEventHandler('click');
        fixture.detectChanges();
        await fixture.whenStable();
        fixture.detectChanges();

        const dialogo = fixture.nativeElement.querySelector('dialog[open][aria-modal="true"]') as HTMLDialogElement;
        expect(dialogo).not.toBeNull();
        expect(dialogo.getAttribute('aria-label')).toContain('Editar sede');

        const nombre = dialogo.querySelector('.sede__formulario input') as HTMLInputElement;
        expect(nombre).not.toBeNull();
        nombre.value = 'Centro Norte';
        nombre.dispatchEvent(new Event('input'));
        const guardar = dialogo.querySelector<HTMLButtonElement>('.ventana__pie button[type="submit"]');
        expect(guardar?.textContent).toContain('Guardar cambios');
        guardar?.click();
        fixture.detectChanges();

        expect(catalogo.actualizarSede).toHaveBeenCalledWith('sede-1', expect.objectContaining({
            nombre: 'Centro Norte',
            zona_horaria: 'America/Guayaquil',
            minutos_antelacion_minima: 60,
        }));
        expect(fixture.nativeElement.textContent).toContain('La información de la sede se actualizó.');
        expect(fixture.nativeElement.querySelector('dialog[open]')).toBeNull();
    });

    it('cierra sin modificar datos cuando se cancela', async () => {
        const editar = fixture.debugElement.query(By.css('.sede__cabecera > button'));
        editar.triggerEventHandler('click');
        fixture.detectChanges();
        await fixture.whenStable();
        fixture.detectChanges();

        const dialogo = fixture.nativeElement.querySelector('dialog[open]') as HTMLDialogElement;
        const cancelar = Array.from(dialogo.querySelectorAll('button')).find((boton) => boton.textContent?.includes('Cancelar'));
        expect(cancelar).toBeDefined();
        cancelar?.click();
        fixture.detectChanges();

        expect(fixture.nativeElement.querySelector('dialog[open]')).toBeNull();
        expect(fixture.nativeElement.querySelector('form')).toBeNull();
        expect(catalogo.actualizarSede).not.toHaveBeenCalled();
    });

    it('conserva el diálogo abierto y muestra el error de API si el guardado falla', async () => {
        catalogo.actualizarSede.mockReturnValue(throwError(() => new Error('fallo')));
        const editar = fixture.debugElement.query(By.css('.sede__cabecera > button'));
        expect(editar).not.toBeNull();
        editar.triggerEventHandler('click');
        fixture.detectChanges();
        await fixture.whenStable();
        const form = fixture.nativeElement.querySelector('dialog form') as HTMLFormElement;
        form.dispatchEvent(new Event('submit'));
        fixture.detectChanges();

        expect(fixture.nativeElement.textContent).toContain('No se pudo guardar la sede.');
        expect(fixture.nativeElement.querySelector('dialog[open] form')).not.toBeNull();
    });
});
