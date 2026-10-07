/**
 * Planes de tratamiento en la ficha clínica.
 *
 * Se comprueba el ciclo que ve el profesional: armar el borrador con su
 * presupuesto, proponerlo, registrar la aceptación firmada (sin referencia no
 * se envía), completar un procedimiento con o sin resultado en el odontograma
 * y cancelar con motivo.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';
import { Router } from '@angular/router';

import { PlanesTratamientoComponent } from './planes-tratamiento.component';
import type { PlanTratamiento, ProcedimientoPlan } from '../../nucleo/servicios/api.service';
import { BASE, PROVEEDORES_PRUEBA, iniciarSesionCon } from '../../nucleo/pruebas/sesion-sintetica';

function procedimiento(extra: Partial<ProcedimientoPlan> = {}): ProcedimientoPlan {
    return {
        id: 'proc-1',
        fase: 1,
        orden: 1,
        pieza: 36,
        caras: 'OM',
        servicio_id: null,
        descripcion: 'Restauracion de molar',
        precio: '85.00',
        estado: 'PENDIENTE',
        cita_id: null,
        completado_en: null,
        ...extra,
    };
}

function plan(extra: Partial<PlanTratamiento> = {}): PlanTratamiento {
    return {
        id: 'plan-1',
        paciente_id: 'pac-1',
        profesional_id: 'prof-1',
        titulo: 'Rehabilitacion inferior',
        estado: 'BORRADOR',
        moneda: 'USD',
        observaciones: null,
        nivel_sensibilidad: 'N2',
        propuesto_en: null,
        aceptado_en: null,
        completado_en: null,
        creado_en: '2026-10-05T10:00:00Z',
        procedimientos: [procedimiento()],
        ...extra,
    };
}

describe('PlanesTratamientoComponent', () => {
    let fixture: ComponentFixture<PlanesTratamientoComponent>;
    let http: HttpTestingController;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let c: any;
    const RUTA = `${BASE}/odontologia/pacientes/pac-1/planes-tratamiento`;

    function montar(planes: readonly PlanTratamiento[], puedeEditar = true): void {
        fixture = TestBed.createComponent(PlanesTratamientoComponent);
        c = fixture.componentInstance;
        fixture.componentRef.setInput('pacienteId', 'pac-1');
        fixture.componentRef.setInput('nombrePaciente', 'Ana Paciente');
        fixture.componentRef.setInput('puedeEditar', puedeEditar);
        fixture.detectChanges();
        http.expectOne(RUTA).flush(planes);
        fixture.detectChanges();
    }

    function texto(): string {
        return (fixture.nativeElement as HTMLElement).textContent ?? '';
    }

    beforeEach(() => {
        TestBed.configureTestingModule({
            imports: [PlanesTratamientoComponent],
            providers: PROVEEDORES_PRUEBA,
        });
        http = TestBed.inject(HttpTestingController);
    });

    afterEach(() => http.verify());

    it('muestra el vacío cuando no hay planes', () => {
        montar([]);
        expect(texto()).toContain('Sin planes de tratamiento');
    });

    it('prepara e imprime un presupuesto con los datos del plan y de la clínica', () => {
        montar([plan({ estado: 'PROPUESTO', propuesto_en: '2026-10-05T10:00:00Z' })]);
        const ver = (fixture.nativeElement as HTMLElement).querySelector('.boton--presupuesto') as HTMLButtonElement;
        ver.click();
        fixture.detectChanges();

        const clinica = http.expectOne(`${BASE}/catalogo/clinica`);
        clinica.flush({
            id: 'clinica-1', nombre: 'Clínica Dental', zona_horaria: 'America/Guayaquil',
            idioma: 'es', moneda: 'USD', telefono: '02-555-0101', correo: 'info@clinica.invalid',
        });
        fixture.detectChanges();

        const presupuesto = (fixture.nativeElement as HTMLElement).querySelector('.presupuesto-imprimible');
        expect(presupuesto?.textContent).toContain('Clínica Dental');
        expect(presupuesto?.textContent).toContain('Ana Paciente');
        expect(presupuesto?.textContent).toContain('Restauracion de molar');
        expect(presupuesto?.textContent).toContain('plan-1');
        expect(presupuesto?.textContent).toContain('no es una factura');
        expect(presupuesto?.textContent).toContain('5 de octubre de 2026');

        vi.spyOn(window, 'print').mockReturnValue(undefined);
        const imprimir = (fixture.nativeElement as HTMLElement).querySelector('.presupuesto-imprimible__acciones .boton--principal') as HTMLButtonElement;
        imprimir.click();
        expect(window.print).toHaveBeenCalled();
        expect(document.body.classList.contains('imprimiendo-presupuesto')).toBe(false);
    });

    it('muestra el error de carga', () => {
        fixture = TestBed.createComponent(PlanesTratamientoComponent);
        c = fixture.componentInstance;
        fixture.componentRef.setInput('pacienteId', 'pac-1');
        fixture.componentRef.setInput('nombrePaciente', 'Ana Paciente');
        fixture.detectChanges();
        http.expectOne(RUTA).flush({ codigo: 'X', mensaje: 'Sin acceso' }, { status: 403, statusText: 'F' });
        expect(c.error()).toBeTruthy();
    });

    it('valida y arma el borrador con su total', () => {
        montar([]);
        c.abrirFormulario();
        http.expectOne(`${BASE}/odontologia/plantillas-plan`).flush([]);
        fixture.detectChanges();
        const dialogo = (fixture.nativeElement as HTMLElement).querySelector('dialog[open]');
        expect(dialogo?.getAttribute('aria-modal')).toBe('true');
        expect(dialogo?.getAttribute('aria-label')).toBe('Crear borrador de tratamiento');

        c.descripcionProcedimiento = 'ab';
        c.agregarProcedimiento();
        expect(c.error()).toContain('3 caracteres');

        c.descripcionProcedimiento = 'Restauracion';
        c.pieza = 99;
        c.agregarProcedimiento();
        expect(c.error()).toContain('FDI');

        c.pieza = 36;
        c.precio = '-1';
        c.agregarProcedimiento();
        expect(c.error()).toContain('importe');

        c.precio = '85';
        c.caras = 'om';
        c.agregarProcedimiento();
        c.descripcionProcedimiento = 'Limpieza';
        c.pieza = '';
        c.precio = '15';
        c.agregarProcedimiento();
        expect(c.procedimientos().length).toBe(2);
        expect(c.procedimientos()[0].caras).toBe('OM');
        // Como sugiere el campo: con comas y espacios, sin repetir caras.
        c.descripcionProcedimiento = 'Resina';
        c.caras = 'o, v, o';
        c.precio = '10';
        c.agregarProcedimiento();
        expect(c.procedimientos()[2].caras).toBe('OV');
        c.quitarProcedimiento(2);
        expect(c.procedimientos()[1].orden).toBe(2);
        expect(c.total()).toBe(100);

        c.quitarProcedimiento(0);
        expect(c.procedimientos().length).toBe(1);
        expect(c.procedimientos()[0].orden).toBe(1);

        c.titulo = 'Plan sintetico';
        fixture.detectChanges();
        dialogo?.querySelector<HTMLButtonElement>('button[type="submit"]')?.click();
        const alta = http.expectOne(RUTA);
        expect(alta.request.body.titulo).toBe('Plan sintetico');
        alta.flush(plan());
        fixture.detectChanges();
        expect(c.planes().length).toBe(1);
        expect(c.exito()).toContain('Borrador guardado');
        expect((fixture.nativeElement as HTMLElement).querySelector('dialog[open]')).toBeNull();
    });

    it('propone un borrador', () => {
        montar([plan()]);
        c.proponer(plan());
        http
            .expectOne(`${BASE}/odontologia/planes-tratamiento/plan-1/propuesta`)
            .flush(plan({ estado: 'PROPUESTO', propuesto_en: '2026-10-05T11:00:00Z' }));
        expect(c.planes()[0].estado).toBe('PROPUESTO');
        expect(c.exito()).toContain('registre aquí la aceptación');
    });

    it('no registra la aceptación sin referencia del documento firmado', () => {
        const propuesto = plan({ estado: 'PROPUESTO', propuesto_en: '2026-10-05T11:00:00Z' });
        montar([propuesto]);
        c.abrirAccion({ tipo: 'aceptar', plan: propuesto });
        fixture.detectChanges();
        expect(texto()).toContain('no es una firma digital');
        c.referenciaAceptacion = ' ';
        c.confirmarAccion();
        expect(c.error()).toContain('referencia');
        http.expectNone(`${BASE}/odontologia/planes-tratamiento/plan-1/aceptacion`);

        c.referenciaAceptacion = 'Hoja 2026-0042';
        c.confirmarAccion();
        const aceptacion = http.expectOne(`${BASE}/odontologia/planes-tratamiento/plan-1/aceptacion`);
        expect(aceptacion.request.body).toEqual({
            medio: 'DOCUMENTO_FIRMADO',
            referencia: 'Hoja 2026-0042',
            imagen_id: null,
        });
        aceptacion.flush(plan({
            estado: 'ACEPTADO',
            aceptado_en: '2026-10-05T12:00:00Z',
            aceptacion_referencia: 'Hoja 2026-0042',
        }));
        fixture.detectChanges();
        expect(c.accion()).toBeNull();
        expect(texto()).toContain('Hoja 2026-0042');
    });

    it('completa un procedimiento con resultado en el odontograma', () => {
        const aceptado = plan({ estado: 'ACEPTADO', aceptado_en: '2026-10-05T12:00:00Z' });
        montar([aceptado]);
        const item = aceptado.procedimientos[0];
        expect(c.hallazgosDe(item).length).toBeGreaterThan(5);
        expect(c.hallazgosDe({ ...item, pieza: null })).toEqual([]);
        expect(c.hallazgosDe({ ...item, caras: null }).some((h: {
            valor: string;
        }) => h.valor === 'SELLANTE')).toBe(false);

        c.abrirAccion({ tipo: 'completar', procedimiento: item });
        expect(c.accionEnPlan(aceptado)).not.toBeNull();
        expect(c.accionEnPlan(plan({ id: 'otro', procedimientos: [] }))).toBeNull();
        c.hallazgo = 'OBTURACION_RESINA';
        c.controlRecomendadoEn = '2026-10-10';
        c.confirmarAccion();
        const completado = http.expectOne(`${BASE}/odontologia/procedimientos/proc-1/completado`);
        expect(completado.request.body).toEqual({
            hallazgo_resultante: 'OBTURACION_RESINA',
            control_recomendado_en: '2026-10-10',
        });
        completado.flush(plan({
            estado: 'COMPLETADO',
            procedimientos: [procedimiento({ estado: 'COMPLETADO', completado_en: '2026-10-05T13:00:00Z' })],
        }));
        expect(c.exito()).toContain('versión nueva');
        expect(c.etiquetaEstado('COMPLETADO')).toBe('Completado');
    });

    it('puede crear un plan N3 con permiso y evita convertirlo en plantilla general', () => {
        iniciarSesionCon(['historia_clinica.leer_sensible']);
        montar([]);
        c.nivelSensibilidad = 'N3';
        c.descripcionProcedimiento = 'Restauración sensible';
        c.agregarProcedimiento();
        c.titulo = 'Plan sensible';
        c.guardarBorrador();
        const alta = http.expectOne(RUTA);
        expect(alta.request.body.nivel_sensibilidad).toBe('N3');
        alta.flush(plan({ nivel_sensibilidad: 'N3', titulo: 'Plan sensible' }));
        fixture.detectChanges();
        expect(texto()).toContain('N3 · Clínico sensible');
        expect((fixture.nativeElement as HTMLElement).textContent).not.toContain('Guardar como plantilla');
    });

    it('muestra el control posterior pendiente y registra su atención', () => {
        const conControl = plan({
            estado: 'COMPLETADO',
            procedimientos: [
                procedimiento({
                    estado: 'COMPLETADO',
                    control_recomendado_en: '2026-10-10',
                    control_atendido_en: null,
                }),
            ],
        });
        montar([conControl]);
        expect(texto()).toContain('Control posterior pendiente');
        expect(texto()).toContain('Fecha definida por el profesional');

        c.abrirAccion({ tipo: 'atender-control', procedimiento: conControl.procedimientos[0] });
        c.notaControl = 'Evolución estable';
        c.confirmarAccion();
        const peticion = http.expectOne(`${BASE}/odontologia/procedimientos/proc-1/control/atencion`);
        expect(peticion.request.body).toEqual({ nota: 'Evolución estable' });
        peticion.flush(plan({
            estado: 'COMPLETADO',
            procedimientos: [
                procedimiento({
                    estado: 'COMPLETADO',
                    control_recomendado_en: '2026-10-10',
                    control_atendido_en: '2026-10-10T12:00:00Z',
                    control_nota: 'Evolución estable',
                }),
            ],
        }));
        fixture.detectChanges();
        expect(c.exito()).toContain('Control posterior registrado');
        expect(texto()).toContain('Control posterior atendido');
    });

    it('exige motivo para cancelar y muestra el error del servidor', () => {
        const aceptado = plan({ estado: 'ACEPTADO' });
        montar([aceptado]);
        c.abrirAccion({ tipo: 'cancelar-plan', plan: aceptado });
        c.motivoCancelacion = 'no';
        c.confirmarAccion();
        expect(c.error()).toContain('motivo');

        c.motivoCancelacion = 'El paciente cambia de clinica';
        c.confirmarAccion();
        http
            .expectOne(`${BASE}/odontologia/planes-tratamiento/plan-1/cancelacion`)
            .flush({ codigo: 'CONFLICTO_ESTADO', mensaje: 'El plan ya esta cerrado.' }, { status: 409, statusText: 'C' });
        expect(c.error()).toContain('cerrado');

        c.abrirAccion({ tipo: 'cancelar-procedimiento', procedimiento: aceptado.procedimientos[0] });
        c.motivoCancelacion = 'Se resolvio con otra tecnica';
        c.confirmarAccion();
        http
            .expectOne(`${BASE}/odontologia/procedimientos/proc-1/cancelacion`)
            .flush(plan({ estado: 'ACEPTADO', procedimientos: [procedimiento({ estado: 'CANCELADO', motivo_cancelacion: 'x' })] }));
        expect(c.exito()).toBe('Procedimiento cancelado.');
        c.cerrarAccion();
        expect(c.accion()).toBeNull();
    });

    it('formatea importes y descarta el formulario', () => {
        montar([plan()]);
        expect(c.totalPlan(plan())).toBe('85.00');
        expect(c.dinero('85.00')).toContain('85');
        c.titulo = 'x';
        c.reiniciarFormulario();
        expect(c.titulo).toBe('');
        expect(c.mostrarFormulario()).toBe(false);
    });

    it('carga una plantilla en el borrador y guarda el borrador como plantilla', () => {
        montar([]);
        c.abrirFormulario();
        http.expectOne(`${BASE}/odontologia/plantillas-plan`).flush([
            {
                id: 'pl-1',
                nombre: 'Corona sobre endodoncia',
                descripcion: null,
                procedimientos: [
                    { fase: 1, orden: 1, pieza: null, caras: null, descripcion: 'Endodoncia', precio: '180.00' },
                ],
                creado_en: '2026-10-05T10:00:00Z',
            },
        ]);
        c.usarPlantilla('pl-1');
        expect(c.titulo).toBe('Corona sobre endodoncia');
        expect(c.procedimientos().length).toBe(1);
        c.usarPlantilla('inexistente');
        expect(c.procedimientos().length).toBe(1);

        c.guardarComoPlantilla();
        const alta = http.expectOne({ method: 'POST', url: `${BASE}/odontologia/plantillas-plan` });
        expect(alta.request.body.procedimientos[0].pieza).toBeNull();
        alta.flush({ id: 'pl-2', nombre: 'Corona sobre endodoncia', descripcion: null, procedimientos: [], creado_en: '2026-10-05T11:00:00Z' });
        expect(c.plantillas().length).toBe(2);

        c.titulo = '';
        c.guardarComoPlantilla();
        expect(c.error()).toContain('título');

        c.abrirFormulario();
        c.abrirFormulario();
        // La lista ya estaba cargada: no se vuelve a pedir.
        http.expectNone(`${BASE}/odontologia/plantillas-plan`);
    });

    it('ofrece agendar cada procedimiento pendiente de la siguiente fase', () => {
        iniciarSesionCon(['cita.crear']);
        const aceptado = plan({
            estado: 'ACEPTADO',
            procedimientos: [
                procedimiento({ fase: 1, estado: 'COMPLETADO', completado_en: '2026-10-01T10:00:00Z' }),
                procedimiento({ id: 'proc-2', fase: 2 }),
                procedimiento({ id: 'proc-3', fase: 2, orden: 2 }),
                procedimiento({ id: 'proc-4', fase: 3 }),
            ],
        });
        montar([aceptado]);
        expect(c.siguienteFase(aceptado)).toBe(2);
        expect(c.procedimientosSiguienteFase(aceptado).map((p: ProcedimientoPlan) => p.id)).toEqual([
            'proc-2',
            'proc-3',
        ]);
        expect(c.siguienteFase(plan({ procedimientos: [] }))).toBeNull();
        const router = TestBed.inject(Router);
        const navegar = vi.spyOn(router, 'navigate').mockResolvedValue(true);
        c.agendarProcedimiento(aceptado, aceptado.procedimientos[1]);
        expect(navegar).toHaveBeenCalledWith(['/agenda'], {
            queryParams: { paciente: 'pac-1', procedimiento_plan: 'proc-2' },
        });
    });

    it('identifica una cita vinculada y evita ofrecer una segunda reserva', () => {
        iniciarSesionCon(['cita.crear']);
        const aceptado = plan({
            estado: 'ACEPTADO',
            procedimientos: [procedimiento({ cita_id: 'cita-1' })],
        });
        montar([aceptado]);

        expect(texto()).toContain('Cita agendada para esta fase');
        expect(c.procedimientosSiguienteFase(aceptado)).toEqual([]);
        expect(fixture.nativeElement.querySelectorAll('.plan__siguiente button').length).toBe(0);
    });

    it('despliega las fotos del tratamiento de un procedimiento', () => {
        iniciarSesionCon(['imagen_clinica.leer']);
        montar([plan({ estado: 'ACEPTADO' })]);
        expect(texto()).toContain('Fotos del tratamiento');
        c.fotosDe.set('proc-1');
        fixture.detectChanges();
        const lista = http.expectOne((r) => r.url === `${BASE}/pacientes/pac-1/imagenes`);
        expect(lista.request.params.get('procedimiento_id')).toBe('proc-1');
        lista.flush([]);
        fixture.detectChanges();
        expect(texto()).toContain('Ocultar fotos');
        expect(texto()).toContain('Aún no hay fotos de este procedimiento');
    });
});
