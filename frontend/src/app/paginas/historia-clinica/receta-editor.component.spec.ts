/**
 * Editor de recetas: firma propia por defecto, firma por delegación solo si
 * hay una vigente, un PRN no lleva frecuencia y una pauta fija sí.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { RecetaEditorComponent } from './receta-editor.component';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import type { Receta } from '../../nucleo/servicios/api.service';
import { BASE, PROVEEDORES_PRUEBA, identidadCon, iniciarSesionCon, } from '../../nucleo/pruebas/sesion-sintetica';

describe('RecetaEditorComponent', () => {
    let fixture: ComponentFixture<RecetaEditorComponent>;
    let http: HttpTestingController;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let c: any;

    beforeEach(() => {
        TestBed.configureTestingModule({ imports: [RecetaEditorComponent], providers: PROVEEDORES_PRUEBA });
        http = TestBed.inject(HttpTestingController);
        iniciarSesionCon(['receta.crear']);
        TestBed.inject(SesionService).establecerIdentidad({
            ...identidadCon(['receta.crear']),
            profesional_id: 'prof-yo',
        });
        fixture = TestBed.createComponent(RecetaEditorComponent);
        c = fixture.componentInstance;
        fixture.componentRef.setInput('pacienteId', 'pac-1');
        fixture.detectChanges();
        http.expectOne(`${BASE}/profesionales/delegaciones/mias`).flush([
            { id: 'd1', delegante_id: 'prof-adjunto', delegado_id: 'prof-yo', vigente_desde: '', vigente_hasta: '', motivo: 'Residencia', revocada_en: null, vigente: true },
            { id: 'd2', delegante_id: 'prof-otro', delegado_id: 'prof-yo', vigente_desde: '', vigente_hasta: '', motivo: 'Vencida', revocada_en: null, vigente: false },
        ]);
        fixture.detectChanges();
    });

    afterEach(() => {
        c.cerrar();
        fixture.detectChanges();
        http.verify();
        expect(document.body.style.overflow).not.toBe('hidden');
    });

    it('presenta la receta extensa en una ventana con pie de acciones', () => {
        const raiz = fixture.nativeElement as HTMLElement;
        const dialogo = raiz.querySelector<HTMLDialogElement>('dialog[open][aria-modal="true"]');
        expect(dialogo?.getAttribute('aria-label')).toBe('Nueva receta · borrador');
        expect(dialogo?.querySelector('form#form-receta')).not.toBeNull();
        expect(dialogo?.querySelector('.ventana__pie')).not.toBeNull();
    });

    function dialogo(): HTMLDialogElement | null {
        return (fixture.nativeElement as HTMLElement).querySelector<HTMLDialogElement>('dialog[open]');
    }

    function botonPorTexto(texto: string): HTMLButtonElement | undefined {
        return Array.from((fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button')).find(
            (boton) => boton.textContent?.trim() === texto,
        );
    }

    it('recién abierta no tiene cambios: Escape la cierra sin preguntar', () => {
        expect(c.hayCambios()).toBe(false);
        const cancelado = vi.fn();
        c.cancelado.subscribe(cancelado);
        dialogo()!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
        fixture.detectChanges();
        expect(cancelado).toHaveBeenCalledOnce();
    });

    it('con un medicamento escrito, Escape y Cancelar piden confirmación antes de descartar', () => {
        const cancelado = vi.fn();
        c.cancelado.subscribe(cancelado);
        const nombre = dialogo()!.querySelector<HTMLInputElement>('form#form-receta input')!;
        nombre.value = 'Medicamento sintetico';
        nombre.dispatchEvent(new Event('input'));
        fixture.detectChanges();
        expect(c.hayCambios()).toBe(true);

        dialogo()!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
        fixture.detectChanges();
        expect(cancelado).not.toHaveBeenCalled();
        expect(dialogo()?.querySelector('[role="alertdialog"]')?.textContent).toContain('Hay cambios sin guardar');
        botonPorTexto('Seguir editando')!.click();
        fixture.detectChanges();
        expect(c.lineas()[0].nombre).toBe('Medicamento sintetico');

        botonPorTexto('Cancelar')!.click();
        fixture.detectChanges();
        expect(cancelado).not.toHaveBeenCalled();
        botonPorTexto('Descartar cambios')!.click();
        fixture.detectChanges();
        expect(cancelado).toHaveBeenCalledOnce();
        expect(dialogo()).toBeNull();
    });

    it('mientras guarda, ni la X ni Escape la cierran', () => {
        const linea = c.lineas()[0];
        linea.nombre = 'Medicamento sintetico';
        linea.dosis = '1 unidad';
        c.crear();
        fixture.detectChanges();
        const alta = http.expectOne(`${BASE}/historia/recetas`);
        const cancelado = vi.fn();
        c.cancelado.subscribe(cancelado);
        expect(dialogo()!.querySelector<HTMLButtonElement>('.ventana__cerrar')!.disabled).toBe(true);
        dialogo()!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
        fixture.detectChanges();
        expect(cancelado).not.toHaveBeenCalled();
        expect(dialogo()).not.toBeNull();
        alta.flush({ id: 'r-1' });
    });

    it('ofrece firma propia y solo las delegaciones vigentes', () => {
        expect(c.firmante).toBe('prof-yo');
        expect(c.firmantes().map((f: {
            id: string;
        }) => f.id)).toEqual(['prof-yo', 'prof-adjunto']);
    });

    it('valida las líneas y un PRN pierde la frecuencia', () => {
        c.crear();
        expect(c.error()).toContain('nombre y dosis');
        const linea = c.lineas()[0];
        linea.nombre = 'Medicamento sintetico';
        linea.dosis = '1 unidad';
        linea.frecuencia_horas = null;
        c.crear();
        expect(c.error()).toContain('frecuencia');
        c.alternarPrn(linea, true);
        linea.cuando_sea_necesario = true;
        expect(linea.frecuencia_horas).toBeNull();
        c.agregar();
        expect(c.lineas().length).toBe(2);
        c.quitar(1);

        c.firmante = 'prof-adjunto';
        c.crear();
        const alta = http.expectOne(`${BASE}/historia/recetas`);
        expect(alta.request.body.profesional_id).toBe('prof-adjunto');
        expect(alta.request.body.medicamentos[0].cuando_sea_necesario).toBe(true);
        alta.flush({ id: 'r-1' });
    });

    it('muestra el rechazo del servidor', () => {
        const linea = c.lineas()[0];
        linea.nombre = 'Medicamento sintetico';
        linea.dosis = '1 unidad';
        c.crear();
        http
            .expectOne(`${BASE}/historia/recetas`)
            .flush({ codigo: 'PERMISO_DENEGADO', mensaje: 'Sin delegacion vigente.' }, { status: 403, statusText: 'F' });
        expect(c.error()).toBe('Sin delegacion vigente.');
    });

    it.each(['prof-yo', 'prof-adjunto'])('prefija la receta vigente y conserva la firma de %s al sustituirla', (responsable: string) => {
        const receta: Receta = {
            id: 'rec-vigente',
            paciente_id: 'pac-1',
            profesional_id: responsable,
            estado: 'CONFIRMADA',
            confirmada_en: '2026-04-15T14:00:00Z',
            suspendida_en: null,
            motivo_suspension: null,
            receta_anterior_id: null,
            indicaciones_generales: 'Indicaciones actuales',
            nivel_sensibilidad: 'N2',
            creado_en: '2026-04-15T14:00:00Z',
            medicamentos: [{
                    id: 'med-1', nombre: 'Medicamento existente', concentracion: null, forma: null,
                    dosis: '1 comprimido', via: 'ORAL', cuando_sea_necesario: false,
                    frecuencia_horas: 8, duracion_dias: 3, hora_primera_toma: null, instrucciones: 'Con agua',
                }],
        };
        fixture.componentRef.setInput('versionDe', receta);
        fixture.detectChanges();
        expect(c.lineas()[0].nombre).toBe('Medicamento existente');
        expect(c.indicaciones).toBe('Indicaciones actuales');
        // Partir de la receta vigente no es un cambio; escribir el motivo sí.
        expect(c.hayCambios()).toBe(false);
        c.motivoVersion = 'x';
        expect(c.hayCambios()).toBe(true);
        c.motivoVersion = '';
        expect(c.firmante).toBe(responsable);
        expect(fixture.nativeElement.querySelector('select[name="firmante"]')).toBeNull();

        c.crear();
        expect(c.error()).toContain('motivo');
        c.motivoVersion = 'Cambio revisado en consulta';
        c.crear();
        const request = http.expectOne(`${BASE}/historia/recetas/rec-vigente/versiones`);
        expect(request.request.method).toBe('POST');
        expect(request.request.body).toEqual({
            profesional_id: responsable,
            motivo: 'Cambio revisado en consulta',
            indicaciones_generales: 'Indicaciones actuales',
            medicamentos: [{
                    nombre: 'Medicamento existente', concentracion: null, forma: null,
                    dosis: '1 comprimido', via: 'ORAL', cuando_sea_necesario: false,
                    frecuencia_horas: 8, duracion_dias: 3, hora_primera_toma: null, instrucciones: 'Con agua',
                }],
        });
        request.flush({ receta: { ...receta, id: 'rec-nueva', receta_anterior_id: 'rec-vigente' }, tomas_canceladas: 4, tomas_generadas: 6 });
    });
});
