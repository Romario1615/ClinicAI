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
            providers: [{ provide: CatalogoService, useValue: catalogo }],
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

    it('edita y persiste la configuración de la sede', async () => {
        const editar = fixture.debugElement.query(By.css('.sede__cabecera button'));
        expect(editar).not.toBeNull();
        editar.triggerEventHandler('click');
        fixture.detectChanges();
        await fixture.whenStable();
        fixture.detectChanges();

        const nombre = fixture.nativeElement.querySelector('.sede__formulario input') as HTMLInputElement;
        expect(nombre).not.toBeNull();
        nombre.value = 'Centro Norte';
        nombre.dispatchEvent(new Event('input'));
        const form = fixture.nativeElement.querySelector('form') as HTMLFormElement;
        form.dispatchEvent(new Event('submit'));
        fixture.detectChanges();

        expect(catalogo.actualizarSede).toHaveBeenCalledWith('sede-1', expect.objectContaining({
            nombre: 'Centro Norte',
            zona_horaria: 'America/Guayaquil',
            minutos_antelacion_minima: 60,
        }));
        expect(fixture.nativeElement.textContent).toContain('La información de la sede se actualizó.');
    });

    it('conserva el formulario y muestra el error de API si el guardado falla', async () => {
        catalogo.actualizarSede.mockReturnValue(throwError(() => new Error('fallo')));
        const editar = fixture.debugElement.query(By.css('.sede__cabecera button'));
        expect(editar).not.toBeNull();
        editar.triggerEventHandler('click');
        fixture.detectChanges();
        await fixture.whenStable();
        const form = fixture.nativeElement.querySelector('form') as HTMLFormElement;
        form.dispatchEvent(new Event('submit'));
        fixture.detectChanges();

        expect(fixture.nativeElement.textContent).toContain('No se pudo guardar la sede.');
        expect(fixture.nativeElement.querySelector('form')).not.toBeNull();
    });
});
