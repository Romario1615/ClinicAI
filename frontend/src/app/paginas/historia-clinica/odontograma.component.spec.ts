/**
 * Odontograma: carga de versiones, edición por pieza y cara, primera versión
 * sin motivo, versiones siguientes con motivo obligatorio y conflicto 409
 * cuando otra persona guardó antes.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { denticionSugeridaPorEdad, OdontogramaComponent } from './odontograma.component';
import type { Odontograma } from '../../nucleo/servicios/api.service';
import { BASE, PROVEEDORES_PRUEBA, iniciarSesionCon } from '../../nucleo/pruebas/sesion-sintetica';

function version(numero: number, vigente: boolean): Odontograma {
    return {
        id: `odo-${numero}`,
        paciente_id: 'pac-1',
        profesional_id: 'prof-1',
        version: numero,
        vigente,
        denticion: 'PERMANENTE',
        piezas: { '36': { pieza: null, caras: { O: 'CARIES' }, nota: null } },
        motivo_modificacion: numero > 1 ? 'Control semestral' : null,
        procedimiento_id: null,
        creado_en: '2026-10-05T10:00:00Z',
        nivel_sensibilidad: 'N2',
    } as Odontograma;
}

describe('OdontogramaComponent', () => {
    let fixture: ComponentFixture<OdontogramaComponent>;
    let http: HttpTestingController;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let c: any;
    const VERSIONES = `${BASE}/odontologia/pacientes/pac-1/odontograma/versiones`;

    function montar(permisos: readonly string[], versiones: readonly Odontograma[], edad: number | null = null): void {
        iniciarSesionCon(permisos);
        fixture = TestBed.createComponent(OdontogramaComponent);
        c = fixture.componentInstance;
        fixture.componentRef.setInput('pacienteId', 'pac-1');
        fixture.componentRef.setInput('edadPaciente', edad);
        fixture.detectChanges();
        http.expectOne({ method: 'GET', url: VERSIONES }).flush(versiones);
        fixture.detectChanges();
    }

    beforeEach(() => {
        TestBed.configureTestingModule({ imports: [OdontogramaComponent], providers: PROVEEDORES_PRUEBA });
        http = TestBed.inject(HttpTestingController);
    });

    afterEach(() => http.verify());

    it('sugiere dentición temporal antes de 6, mixta de 6 a 12 y permanente desde 13', () => {
        expect([5, 6, 12, 13].map(denticionSugeridaPorEdad)).toEqual([
            'TEMPORAL', 'MIXTA', 'MIXTA', 'PERMANENTE',
        ]);
        expect(denticionSugeridaPorEdad(null)).toBe('PERMANENTE');
    });

    it('usa la edad como valor inicial, pero conserva la dentición guardada', () => {
        montar(['odontograma.leer', 'odontograma.escribir'], [], 5);
        expect(c.denticion()).toBe('TEMPORAL');
    });

    it('la versión guardada prevalece sobre la propuesta por edad', () => {
        montar(['odontograma.leer', 'odontograma.escribir'], [version(1, true)], 5);
        expect(c.denticion()).toBe('PERMANENTE');
    });

    it('crea la primera versión sin motivo', () => {
        montar(['odontograma.leer', 'odontograma.escribir'], []);
        c.cambiarDenticion('MIXTA');
        expect(c.denticion()).toBe('MIXTA');
        c.cambiarDenticion('INVENTADA');
        expect(c.denticion()).toBe('MIXTA');

        c.elegirPieza(16);
        c.cambiarHallazgoPieza('CORONA');
        c.alternarCara('O', true);
        c.cambiarHallazgoCara('O', 'OBTURACION_RESINA');
        c.cambiarNota('Control');
        expect(c.leyendaPieza(16)).toContain('Corona');
        expect(c.tieneHallazgoPieza(16)).toBe(true);

        c.guardar();
        const alta = http.expectOne({ method: 'POST', url: `${BASE}/odontologia/pacientes/pac-1/odontograma` });
        expect(alta.request.body.piezas['16']).toEqual({
            pieza: 'CORONA',
            caras: { O: 'OBTURACION_RESINA' },
            nota: 'Control',
        });
        alta.flush(version(1, true));
        http.expectOne({ method: 'GET', url: VERSIONES }).flush([version(1, true)]);
        expect(c.aviso()).toContain('nueva versión');
    });

    it('permite marcar N3 solo con permiso sensible y lo envía al servidor', () => {
        montar(['odontograma.leer', 'odontograma.escribir', 'historia_clinica.leer_sensible'], []);
        c.nivelSensibilidad.set('N3');
        c.guardar();
        const alta = http.expectOne({ method: 'POST', url: `${BASE}/odontologia/pacientes/pac-1/odontograma` });
        expect(alta.request.body.nivel_sensibilidad).toBe('N3');
        alta.flush({ ...version(1, true), nivel_sensibilidad: 'N3' });
        http.expectOne({ method: 'GET', url: VERSIONES }).flush([{ ...version(1, true), nivel_sensibilidad: 'N3' }]);
    });

    it('exige motivo para una versión nueva y muestra el conflicto 409', () => {
        montar(['odontograma.leer', 'odontograma.escribir'], [version(1, true)]);
        expect(c.leyendaPieza(36)).toContain('Caries');
        c.elegirPieza(36);
        c.alternarCara('O', false);
        c.alternarCara('M', true);
        c.cambiarHallazgoPieza('AUSENTE');
        expect(c.estadoSeleccionado().caras).toEqual({});
        c.guardar();
        expect(c.errorTexto()).toContain('motivo');

        c.motivo.set('Extraccion realizada');
        c.guardar();
        const nueva = http.expectOne(`${BASE}/odontologia/pacientes/pac-1/odontograma/versiones`);
        expect(nueva.request.method).toBe('POST');
        nueva.flush({ codigo: 'CONFLICTO_ESTADO', mensaje: 'Recargue' }, { status: 409, statusText: 'C' });
        expect(c.conflicto()).toBe(true);
    });

    it('una versión histórica es de solo lectura', () => {
        montar(['odontograma.leer', 'odontograma.escribir'], [version(2, true), version(1, false)]);
        c.seleccionarVersion('1');
        expect(c.actual().version).toBe(1);
        expect(c.puedeGuardar()).toBe(false);
        c.elegirPieza(36);
        c.cambiarHallazgoPieza('IMPLANTE');
        expect(c.leyendaPieza(36)).not.toContain('Implante');
        c.seleccionarVersion('99');
        expect(c.actual().version).toBe(1);
    });

    it('sin permiso de escritura no edita', () => {
        montar(['odontograma.leer'], [version(1, true)]);
        expect(c.puedeGuardar()).toBe(false);
        expect(c.nombreHallazgo('CARIES')).toBe('Caries');
    });

    it('muestra el error de carga', () => {
        iniciarSesionCon(['odontograma.leer']);
        fixture = TestBed.createComponent(OdontogramaComponent);
        c = fixture.componentInstance;
        fixture.componentRef.setInput('pacienteId', 'pac-1');
        fixture.detectChanges();
        http.expectOne(VERSIONES).flush({ codigo: 'X', mensaje: 'Sin relacion' }, { status: 403, statusText: 'F' });
        expect(c.errorTexto()).toContain('Sin relacion');
    });

    it('revisa el guardado en una ventana y volver conserva las piezas y el motivo', () => {
        montar(['odontograma.leer', 'odontograma.escribir'], [version(1, true)]);
        c.elegirHerramienta('CARIES');
        c.clicRegion(16, 'centro');
        c.motivo.set('Consulta de control');
        c.abrirGuardado();
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('dialog')?.textContent).toContain('Guardar odontograma');
        http.expectNone({ method: 'POST', url: VERSIONES });
        c.cerrarGuardado();
        expect(c.guardadoAbierto()).toBe(false);
        expect(c.borrador()['16'].caras.O).toBe('CARIES');
        expect(c.motivo()).toBe('Consulta de control');
    });

    it('un envío en curso bloquea el cierre y un segundo guardado', () => {
        montar(['odontograma.leer', 'odontograma.escribir'], []);
        c.abrirGuardado();
        c.guardar();
        c.cerrarGuardado();
        c.guardar();
        expect(c.guardadoAbierto()).toBe(true);
        const alta = http.expectOne({ method: 'POST', url: `${BASE}/odontologia/pacientes/pac-1/odontograma` });
        alta.flush(version(1, true));
        http.expectOne({ method: 'GET', url: VERSIONES }).flush([version(1, true)]);
        expect(c.guardadoAbierto()).toBe(false);
    });

    it('un fallo del servidor conserva la ventana y permite reintentar', () => {
        montar(['odontograma.leer', 'odontograma.escribir'], []);
        c.abrirGuardado();
        c.guardar();
        http.expectOne(`${BASE}/odontologia/pacientes/pac-1/odontograma`).flush(
            { codigo: 'SIN_RELACION', mensaje: 'Inicie la atención' }, { status: 403, statusText: 'F' },
        );
        fixture.detectChanges();
        expect(c.guardadoAbierto()).toBe(true);
        expect(c.guardando()).toBe(false);
        expect(fixture.nativeElement.querySelector('dialog')?.textContent).toContain('Inicie la atención');
    });

    it('cerrar después de un fallo de fotografías conserva y recarga la versión creada', () => {
        montar(['odontograma.leer', 'odontograma.escribir'], []);
        c.abrirGuardado();
        c.fotos = [{ id: 'foto-1', archivo: new File(['foto'], 'foto.png', { type: 'image/png' }), url: '', descripcion: '' }];
        c.guardar();
        http.expectOne(`${BASE}/odontologia/pacientes/pac-1/odontograma`).flush(version(1, true));
        http.expectOne(`${BASE}/fotos-registro/odontograma/odo-1`).flush(
            { codigo: 'X', mensaje: 'Foto pendiente' }, { status: 503, statusText: 'F' },
        );
        expect(c.operacionFotos.guardado).toBe(true);
        c.cerrarGuardado();
        http.expectOne({ method: 'GET', url: VERSIONES }).flush([version(1, true)]);
        expect(c.actual().version).toBe(1);
        expect(c.operacionFotos.guardado).toBe(false);
        expect(c.aviso()).toContain('versión se conserva');
    });

    it('la revisión de guardado no se abre en consulta ni en una versión histórica', () => {
        montar(['odontograma.leer'], [version(1, true)]);
        c.abrirGuardado();
        expect(c.guardadoAbierto()).toBe(false);
        c.guardar();
        http.expectNone({ method: 'POST', url: VERSIONES });
    });
});

describe('OdontogramaComponent interactivo', () => {
    let fixture: ComponentFixture<OdontogramaComponent>;
    let http: HttpTestingController;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let c: any;
    const VERSIONES = `${BASE}/odontologia/pacientes/pac-1/odontograma/versiones`;

    beforeEach(() => {
        TestBed.configureTestingModule({ imports: [OdontogramaComponent], providers: PROVEEDORES_PRUEBA });
        http = TestBed.inject(HttpTestingController);
        iniciarSesionCon(['odontograma.leer', 'odontograma.escribir', 'plan_tratamiento.leer']);
        fixture = TestBed.createComponent(OdontogramaComponent);
        c = fixture.componentInstance;
        fixture.componentRef.setInput('pacienteId', 'pac-1');
        fixture.detectChanges();
        http.expectOne({ method: 'GET', url: VERSIONES }).flush([version(1, true)]);
        http.expectOne(`${BASE}/odontologia/pacientes/pac-1/planes-tratamiento`).flush([]);
        fixture.detectChanges();
    });

    afterEach(() => http.verify());

    it('pinta caras con el pincel, alterna y borra', () => {
        c.clicRegion(16, 'centro');
        expect(c.seleccionada()).toBe(16);
        expect(c.cambiadas().size).toBe(0);

        c.elegirHerramienta('CARIES');
        c.clicRegion(16, 'derecha');
        expect(c.borrador()['16'].caras).toEqual({ M: 'CARIES' });
        expect(c.claseRegion(16, 'derecha')).toBe('cara cara--caries');
        expect(c.tituloRegion(16, 'derecha')).toContain('Mesial: Caries');
        expect(c.tituloRegion(16, 'centro')).toBe('16 · Oclusal o incisal');
        expect(c.cambiadas().has(16)).toBe(true);
        c.clicRegion(16, 'derecha');
        expect(c.borrador()['16'].caras).toEqual({});

        c.clicRegion(16, 'arriba');
        c.elegirHerramienta('BORRAR');
        c.clicRegion(16, 'arriba');
        expect(c.borrador()['16'].caras).toEqual({});
        fixture.detectChanges();
    });

    it('permite recorrer y registrar superficies con el teclado', () => {
        const elemento = fixture.nativeElement as HTMLElement;
        const centro = elemento.querySelector<SVGPolygonElement>('[data-pieza="16"] [data-region="centro"]')!;
        const derecha = elemento.querySelector<SVGPolygonElement>('[data-pieza="16"] [data-region="derecha"]')!;
        expect(centro.tabIndex).toBe(-1);

        c.elegirPieza(16);
        c.elegirHerramienta('CARIES');
        fixture.detectChanges();
        expect(centro.tabIndex).toBe(0);
        expect(centro.getAttribute('role')).toBe('button');
        expect(centro.getAttribute('aria-label')).toContain('Oclusal');

        centro.focus();
        centro.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
        expect(document.activeElement).toBe(derecha);
        derecha.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        expect(Object.values(c.borrador()['16'].caras)).toEqual(['CARIES']);
    });

    it('aplica hallazgos de pieza y bloquea caras de una ausente', () => {
        c.elegirHerramienta('AUSENTE');
        c.clicPieza(21);
        expect(c.hallazgoDePieza(21)).toBe('AUSENTE');
        fixture.detectChanges();
        expect((fixture.nativeElement as HTMLElement).querySelector('.marca-pieza--ausente')).not.toBeNull();

        c.elegirHerramienta('CARIES');
        c.clicRegion(21, 'centro');
        expect(c.errorTexto()).toContain('ausente');

        c.elegirHerramienta('CORONA');
        c.clicRegion(11, 'centro');
        expect(c.hallazgoDePieza(11)).toBe('CORONA');
        c.clicPieza(11);
        expect(c.hallazgoDePieza(11)).toBeNull();

        c.elegirHerramienta('BORRAR');
        c.clicPieza(21);
        expect(c.hallazgoDePieza(21)).toBeNull();

        c.elegirHerramienta('SELECCIONAR');
        c.clicPieza(12);
        expect(c.seleccionada()).toBe(12);
    });

    it('dibuja marcas y nota, deshace una pieza y guarda solo piezas con datos', () => {
        const marcas = [
            [11, 'ENDODONCIA'],
            [12, 'PROTESIS_FIJA'],
            [13, 'IMPLANTE'],
            [14, 'RESTO_RADICULAR'],
            [15, 'A_EXTRAER'],
            [17, 'CORONA'],
        ] as const;
        for (const [pieza, hallazgo] of marcas) {
            c.elegirHerramienta(hallazgo);
            c.clicPieza(pieza);
        }
        c.elegirPieza(36);
        c.cambiarNota('Sensibilidad');
        expect(c.tieneNota(36)).toBe(true);
        fixture.detectChanges();
        const el = fixture.nativeElement as HTMLElement;
        expect(el.querySelectorAll('.marca-pieza-texto').length).toBe(2);
        expect(el.textContent).toContain('Historial de la pieza 36');

        c.deshacerPieza();
        expect(c.borrador()['36'].nota).toBeNull();
        c.elegirPieza(17);
        c.deshacerPieza();
        expect(c.borrador()['17']).toBeUndefined();
        c.elegirHerramienta('CARIES');
        c.clicRegion(18, 'centro');
        c.clicRegion(18, 'centro');
        c.seleccionada.set(null);
        c.deshacerPieza();

        c.motivo.set('Hallazgos del control');
        c.guardar();
        const nueva = http.expectOne({ method: 'POST', url: VERSIONES });
        expect(nueva.request.body.piezas['13']).toEqual({ pieza: 'IMPLANTE', caras: {}, nota: null });
        expect(nueva.request.body.piezas['18']).toBeUndefined();
        nueva.flush(version(2, true));
        http.expectOne({ method: 'GET', url: VERSIONES }).flush([version(2, true), version(1, false)]);
    });
});
