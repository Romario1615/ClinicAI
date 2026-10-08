/**
 * Automatizaciones: agrupa por momento de la atención, los obligatorios no
 * tienen interruptor y cambiar uno pide motivo.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { AutomatizacionesComponent, type Automatizacion } from './automatizaciones.component';
import { BASE, PROVEEDORES_PRUEBA, iniciarSesionCon } from '../../nucleo/pruebas/sesion-sintetica';

function flujo(extra: Partial<Automatizacion>): Automatizacion {
    return {
        codigo: 'recordatorio_dia_antes',
        nombre: 'Recordatorio el día anterior',
        fase: 'ANTES_DE_LA_CITA',
        disparador: 'Falta un día.',
        accion: 'WhatsApp.',
        canal: 'WhatsApp',
        quien_ve: ['Recepción'],
        quien_interviene: ['Paciente'],
        obligatorio: false,
        nota: null,
        activo: true,
        ejecuciones_30_dias: 4,
        ...extra,
    };
}

describe('AutomatizacionesComponent', () => {
    let fixture: ComponentFixture<AutomatizacionesComponent>;
    let http: HttpTestingController;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let c: any;

    function montar(permisos: readonly string[]): void {
        iniciarSesionCon(permisos);
        fixture = TestBed.createComponent(AutomatizacionesComponent);
        c = fixture.componentInstance;
        fixture.detectChanges();
        http.expectOne(`${BASE}/automatizaciones`).flush([
            flujo({}),
            flujo({ codigo: 'derivacion_a_persona', nombre: 'Derivación', fase: 'MENSAJES', obligatorio: true, nota: 'Regla 5' }),
        ]);
        fixture.detectChanges();
    }

    beforeEach(() => {
        TestBed.configureTestingModule({ imports: [AutomatizacionesComponent], providers: PROVEEDORES_PRUEBA });
        http = TestBed.inject(HttpTestingController);
    });

    afterEach(() => http.verify());

    it('agrupa por fase y apaga un flujo con motivo', () => {
        montar(['configuracion.escribir']);
        expect(c.grupos().map((g: {
            titulo: string;
        }) => g.titulo)).toEqual(['Antes de la cita', 'Mensajes']);
        const el = fixture.nativeElement as HTMLElement;
        expect(el.querySelectorAll('[role=switch]').length).toBe(1);
        expect(el.textContent).toContain('Siempre activa');

        c.pedirCambio(c.flujos()[0]);
        c.confirmarCambio(c.flujos()[0]);
        expect(c.errorCambio()).toContain('motivo');
        c.motivo = 'Se confirma por llamada';
        c.confirmarCambio(c.flujos()[0]);
        const peticion = http.expectOne({ method: 'PUT', url: `${BASE}/automatizaciones/recordatorio_dia_antes` });
        expect(peticion.request.body).toEqual({ activo: false, motivo: 'Se confirma por llamada' });
        peticion.flush(flujo({ activo: false }));
        expect(c.flujos()[0].activo).toBe(false);
        expect(c.aviso()).toContain('apagada');

        c.pedirCambio(c.flujos()[0]);
        c.motivo = 'Se retoma el aviso';
        c.confirmarCambio(c.flujos()[0]);
        http
            .expectOne({ method: 'PUT', url: `${BASE}/automatizaciones/recordatorio_dia_antes` })
            .flush({ codigo: 'X', mensaje: 'No permitido' }, { status: 403, statusText: 'F' });
        expect(c.errorCambio()).toBe('No permitido');
    });

    it('auditoría solo ve, sin interruptores', () => {
        montar(['auditoria.leer']);
        expect((fixture.nativeElement as HTMLElement).querySelectorAll('[role=switch]').length).toBe(0);
        // El host ya no desplaza: lo hace el marco de cada fase, que es el que
        // necesita foco de teclado.
        expect(fixture.nativeElement.getAttribute('role')).toBe('region');
        expect((fixture.nativeElement as HTMLElement).querySelector('.flujos.desplazable')?.getAttribute('tabindex')).toBe('0');
        expect(fixture.nativeElement.getAttribute('aria-label')).toBe('Automatizaciones de la clínica');
    });

    it('presenta la ilustración de marca sin añadir contenido accesible redundante', () => {
        montar(['configuracion.escribir']);
        const imagen = (fixture.nativeElement as HTMLElement).querySelector<HTMLImageElement>('.encabezado__ilustracion');
        expect(imagen?.getAttribute('src')).toBe('/images/automatizaciones-flujo-clinica.svg');
        expect(imagen?.getAttribute('width')).toBe('640');
        expect(imagen?.getAttribute('height')).toBe('400');
        expect(imagen?.getAttribute('alt')).toBe('');
        expect(imagen?.getAttribute('aria-hidden')).toBe('true');
    });

    it('muestra una fase a la vez y cambia con las pestañas', () => {
        montar(['configuracion.escribir']);
        const el = fixture.nativeElement as HTMLElement;
        const visibles = () => [...el.querySelectorAll<HTMLElement>('[role=tabpanel]')].filter((p) => !p.hidden).map((p) => p.id);
        expect(visibles()).toEqual(['automatizaciones-panel-ANTES_DE_LA_CITA']);
        el.querySelector<HTMLElement>('#automatizaciones-pestana-MENSAJES')?.click();
        fixture.detectChanges();
        expect(visibles()).toEqual(['automatizaciones-panel-MENSAJES']);
    });

    it('muestra el error de carga', () => {
        iniciarSesionCon(['configuracion.escribir']);
        fixture = TestBed.createComponent(AutomatizacionesComponent);
        c = fixture.componentInstance;
        fixture.detectChanges();
        http.expectOne(`${BASE}/automatizaciones`).flush({ codigo: 'X', mensaje: 'Sin acceso' }, { status: 403, statusText: 'F' });
        expect(c.error()).toBe('Sin acceso');
    });
});
