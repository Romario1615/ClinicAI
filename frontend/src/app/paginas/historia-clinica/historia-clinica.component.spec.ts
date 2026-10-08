/**
 * Pruebas de la pantalla de historia clinica.
 *
 * Lo que se verifica y por que importa
 * ------------------------------------
 * **El PRN no se presenta como pauta fija.** Un medicamento «cuando sea
 * necesario» no genera horarios, y escribir «cada 8 horas» sobre el convierte
 * una indicacion a demanda en una pauta fija. Es un error de medicacion, no un
 * detalle de presentacion.
 *
 * **Los permisos clinicos no van juntos.** Un asistente tiene `receta.leer`
 * sin `historia_clinica.leer`. La pantalla le muestra la medicacion y le dice
 * que las notas no estan a su alcance, en lugar de pintar un error rojo como
 * si algo se hubiera roto. Un 403 aqui es el control funcionando.
 *
 * **Las versiones antiguas se ven.** La historia clinica se versiona y no se
 * borra; si la interfaz solo mostrara la vigente, esa garantia existiria en la
 * base y no le serviria de nada a quien la audita.
 *
 * **Una receta suspendida sigue visible con su motivo.** Ocultarla daria la
 * impresion de que nunca existio.
 */
import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute } from '@angular/router';

import { HistoriaClinicaComponent } from './historia-clinica.component';
import { CONFIGURACION, CONFIGURACION_POR_DEFECTO } from '../../nucleo/servicios/configuracion';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import type { Medicamento, Nota, Receta } from '../../nucleo/servicios/api.service';
import type { Paciente } from '../../nucleo/modelos/dominio';

const BASE = CONFIGURACION_POR_DEFECTO.urlApi;
const PACIENTE_ID = 'pac-1';

function paciente(): Paciente {
    return {
        id: PACIENTE_ID,
        tipo_documento: 'CEDULA',
        numero_documento: '9900000001',
        nombre: 'Nombre',
        apellido: 'Apellido',
        telefono_whatsapp: null,
        correo: null,
        fecha_nacimiento: null,
        nivel_verificacion: 'DOCUMENTO',
    };
}

function nota(extra: Partial<Nota> = {}): Nota {
    return {
        id: 'nota-1',
        raiz_id: 'raiz-1',
        version: 1,
        vigente: true,
        motivo_modificacion: null,
        paciente_id: PACIENTE_ID,
        profesional_id: 'prof-1',
        cita_id: null,
        tipo: 'EVOLUCION',
        nivel_sensibilidad: 'N2',
        motivo_consulta: 'Control [SINTETICO]',
        subjetivo: 'Texto subjetivo de demostracion',
        objetivo: null,
        analisis: null,
        plan: 'Plan de demostracion',
        signos_vitales: null,
        creado_en: '2026-09-10T14:00:00Z',
        ...extra,
    };
}

function medicamento(extra: Partial<Medicamento> = {}): Medicamento {
    return {
        id: 'med-1',
        nombre: 'Medicamento de ejemplo A',
        concentracion: null,
        forma: null,
        dosis: '1 unidad',
        via: 'ORAL',
        cuando_sea_necesario: false,
        frecuencia_horas: 8,
        duracion_dias: 3,
        hora_primera_toma: null,
        instrucciones: null,
        ...extra,
    };
}

function receta(extra: Partial<Receta> = {}): Receta {
    return {
        puede_gestionar: true,
        id: 'rec-1',
        paciente_id: PACIENTE_ID,
        profesional_id: 'prof-1',
        estado: 'CONFIRMADA',
        confirmada_en: '2026-09-10T15:00:00Z',
        suspendida_en: null,
        motivo_suspension: null,
        receta_anterior_id: null,
        indicaciones_generales: null,
        nivel_sensibilidad: 'N2',
        creado_en: '2026-09-10T14:30:00Z',
        medicamentos: [medicamento()],
        ...extra,
    };
}

import { ESPECIALIDAD_SINTETICA, INDICADORES_VACIOS } from '../../nucleo/pruebas/sesion-sintetica';
describe('HistoriaClinicaComponent', () => {
    let fixture: ComponentFixture<HistoriaClinicaComponent>;
    let http: HttpTestingController;
    let sesion: SesionService;

    beforeEach(() => {
        TestBed.configureTestingModule({
            imports: [HistoriaClinicaComponent],
            providers: [
                provideHttpClient(withXhr()),
                provideHttpClientTesting(),
                { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
                INDICADORES_VACIOS,
                ESPECIALIDAD_SINTETICA,
                {
                    provide: ActivatedRoute,
                    useValue: { snapshot: { queryParamMap: { get: () => null } } },
                },
            ],
        });
        fixture = TestBed.createComponent(HistoriaClinicaComponent);
        http = TestBed.inject(HttpTestingController);
        sesion = TestBed.inject(SesionService);
    });

    afterEach(() => {
        // El resumen clínico tiene su propia prueba; aquí solo se responde.
        http.match((p) => p.url.endsWith('/resumen-clinico')).forEach((p) => p.flush({ codigo: 'X', mensaje: 'x' }, { status: 403, statusText: 'F' }));
        // La cabecera pide la foto de perfil; aquí no se prueba la foto.
        http.match((p) => p.url.endsWith('/foto-perfil')).forEach((p) => p.flush(null));
        http.verify();
    });

    /** Fija los permisos del principal, que es de donde la pantalla los lee. */
    function conPermisos(...codigos: readonly string[]): void {
        vi.spyOn(sesion, 'identidad').mockReturnValue({ profesional_id: 'prof-1' } as ReturnType<SesionService['identidad']>);
        vi.spyOn(sesion, 'tienePermiso').mockImplementation((codigo: string) => codigos.includes(codigo));
    }

    function listar(): void {
        fixture.detectChanges();
        http
            .expectOne((p) => p.url === `${BASE}/pacientes/`)
            .flush({
            elementos: [paciente()],
            total: 1,
            limite: 50,
            desplazamiento: 0,
            termino_ignorado: false,
        });
        fixture.detectChanges();
    }

    /** Abre la historia y resuelve las peticiones que correspondan al rol. */
    function abrir(opciones: {
        notas?: readonly Nota[] | 'denegado' | 'sin-relacion';
        recetas?: readonly Receta[];
    }): void {
        fixture.componentInstance['abrir'](paciente());
        http.expectOne(`${BASE}/pacientes/${PACIENTE_ID}`).flush({
            ...paciente(),
            sexo: null,
            direccion: null,
            activo: true,
        });
        fixture.detectChanges();

        // Quien puede leer notas pregunta antes si tiene acceso clínico al paciente.
        const consultaAcceso = http.match(`${BASE}/pacientes/${PACIENTE_ID}/acceso-clinico`);
        consultaAcceso.forEach((p) => p.flush({ acceso_clinico: opciones.notas !== 'sin-relacion' }));

        if (opciones.notas === 'sin-relacion') {
            // Sin relación asistencial las notas ni se piden: no hay 404 que absorber.
            http.expectNone((p) => p.url.includes('/notas'));
        }
        else if (opciones.notas === 'denegado') {
            http
                .expectOne((p) => p.url.includes('/notas'))
                .flush({ codigo: 'PERMISO_DENEGADO', mensaje: 'No disponible.' }, { status: 403, statusText: 'Forbidden' });
        }
        else if (opciones.notas !== undefined) {
            http.expectOne((p) => p.url.includes('/notas')).flush(opciones.notas);
        }

        if (opciones.recetas !== undefined) {
            http.expectOne((p) => p.url.includes('/recetas')).flush(opciones.recetas);
        }
        fixture.detectChanges();
    }

    /**
     * Texto de las pestañas de evolución y de recetas: las pruebas afirman lo
     * que la historia muestra, esté en la pestaña que esté.
     */
    function texto(): string {
        const componente = fixture.componentInstance as unknown as {
            pestana: {
                set(valor: string): void;
                (): string;
            };
        };
        const actual = componente.pestana();
        let todo = '';
        for (const pestana of ['evolucion', 'recetas']) {
            componente.pestana.set(pestana);
            fixture.detectChanges();
            todo += (fixture.nativeElement as HTMLElement).textContent ?? '';
        }
        componente.pestana.set(actual);
        fixture.detectChanges();
        return todo;
    }

    describe('medicacion', () => {
        beforeEach(() => conPermisos('historia_clinica.leer', 'receta.leer'));

        it('un PRN se enuncia como tal y NO se le calcula frecuencia', () => {
            listar();
            abrir({
                notas: [],
                recetas: [
                    receta({
                        medicamentos: [
                            medicamento({
                                nombre: 'Medicamento de ejemplo C',
                                cuando_sea_necesario: true,
                                frecuencia_horas: null,
                                duracion_dias: null,
                            }),
                        ],
                    }),
                ],
            });

            expect(texto()).toContain('cuando sea necesario');
            expect(texto()).toContain('Sin horario fijo');
            // Presentar un PRN con horas es convertir una indicacion a demanda en
            // una pauta fija.
            expect(texto()).not.toContain('cada 8 h');
        });

        it('una pauta fija si muestra su frecuencia y duracion', () => {
            listar();
            abrir({ notas: [], recetas: [receta()] });

            expect(texto()).toContain('cada 8 h');
            expect(texto()).toContain('durante 3 dias');
            expect(texto()).not.toContain('Sin horario fijo');
        });

        it('un borrador declara que no genera recordatorios', () => {
            listar();
            abrir({ notas: [], recetas: [receta({ estado: 'BORRADOR', confirmada_en: null })] });

            expect(texto()).toContain('Borrador');
            expect(texto()).toContain('No genera recordatorios');
        });

        it('una receta suspendida sigue visible, con su motivo', () => {
            listar();
            abrir({
                notas: [],
                recetas: [
                    receta({
                        estado: 'SUSPENDIDA',
                        suspendida_en: '2026-09-11T10:00:00Z',
                        motivo_suspension: 'Motivo de demostracion.',
                    }),
                ],
            });

            // Ocultarla daria la impresion de que nunca existio.
            expect(texto()).toContain('Suspendida');
            expect(texto()).toContain('Motivo de demostracion.');
            expect(texto()).toContain('Medicamento de ejemplo A');
        });
    });

    it('cierra la historia cuando caduca el acceso temporal de emergencia', () => {
        vi.useFakeTimers();
        try {
        conPermisos('historia_clinica.leer', 'receta.leer', 'acceso_emergencia.solicitar');
        listar();
        abrir({ notas: 'sin-relacion', recetas: [] });

        fixture.componentInstance['motivoAccesoEmergencia'].set('Cobertura clínica urgente durante ausencia del profesional asignado.');
        fixture.detectChanges();
        const solicitar = Array.from(fixture.nativeElement.querySelectorAll('button')).find((boton) => (boton as HTMLButtonElement).textContent?.includes('Solicitar acceso temporal')) as HTMLButtonElement;
        solicitar.click();
        const venceEn = new Date(Date.now() + 30 * 60 * 1000).toISOString();
        http.expectOne(`${BASE}/historia/pacientes/${PACIENTE_ID}/acceso-emergencia`).flush({
            relacion_id: 'rel-emergencia',
            vence_en: venceEn,
            duracion_minutos: 30,
        });
        http.expectOne(`${BASE}/pacientes/${PACIENTE_ID}/acceso-clinico`).flush({ acceso_clinico: true });
        http.expectOne((p) => p.url.includes('/notas')).flush([nota()]);
        http.expectOne((p) => p.url.includes('/recetas')).flush([]);
        fixture.detectChanges();
        expect(texto()).toContain('Acceso temporal concedido');

        vi.advanceTimersByTime(30 * 60 * 1000);
        fixture.detectChanges();
        expect(fixture.nativeElement.textContent).toContain('El acceso temporal expiró. La historia se cerró.');
        expect(fixture.nativeElement.textContent).not.toContain('Texto subjetivo de demostracion');
        } finally {
            vi.useRealTimers();
        }
    });

    describe('versionado', () => {
        beforeEach(() => conPermisos('historia_clinica.leer', 'receta.leer'));

        it('muestra la version vigente con su motivo de correccion', () => {
            listar();
            abrir({
                notas: [nota({ version: 2, motivo_modificacion: 'Se completo el registro.' })],
                recetas: [],
            });

            expect(texto()).toContain('versión 2');
            expect(texto()).toContain('Se completo el registro.');
        });

        it('las versiones anteriores se conservan y se pueden ver', () => {
            listar();
            abrir({
                notas: [
                    nota({ id: 'n2', version: 2, motivo_modificacion: 'Correccion.' }),
                    nota({ id: 'n1', version: 1, vigente: false, subjetivo: 'Texto original' }),
                ],
                recetas: [],
            });

            expect(texto()).toContain('1 versión(es) anterior(es) conservada(s)');
            expect(texto()).toContain('Texto original');
        });
    });

    describe('degradacion por rol', () => {
        it('permite corregir solo notas propias aunque pueda leer las del colega', () => {
            conPermisos('historia_clinica.leer', 'historia_clinica.escribir');
            listar();
            abrir({ notas: [nota(), nota({ id: 'nota-ajena', raiz_id: 'raiz-ajena', profesional_id: 'colega' })] });
            expect(fixture.componentInstance['puedeCorregirNota'](nota())).toBe(true);
            expect(fixture.componentInstance['puedeCorregirNota'](nota({ profesional_id: 'colega' }))).toBe(false);
            fixture.componentInstance['pestana'].set('evolucion');
            fixture.detectChanges();
            expect(fixture.nativeElement.querySelectorAll('.nota__corregir').length).toBe(1);
        });

        it('muestra medicación ajena sin botones para firmarla o sustituirla', () => {
            conPermisos('receta.leer', 'receta.crear', 'receta.confirmar');
            listar();
            const ajena = receta({ profesional_id: 'colega', puede_gestionar: false });
            abrir({ recetas: [ajena] });
            fixture.componentInstance['pestana'].set('recetas');
            fixture.detectChanges();
            const botones = Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('button')).map(b => b.textContent);
            expect(botones.some(b => b?.includes('Nueva versión'))).toBe(false);
            fixture.componentInstance['confirmarReceta'](ajena);
            http.expectNone(p => p.url.includes('/confirmacion'));
            expect(texto()).toContain('Medicamento de ejemplo A');
        });

        it('una confirmación delegada mantiene la firma del responsable', () => {
            conPermisos('receta.leer', 'receta.confirmar');
            listar();
            const delegada = receta({ estado: 'BORRADOR', profesional_id: 'responsable', puede_gestionar: true });
            abrir({ recetas: [delegada] });
            fixture.componentInstance['confirmarReceta'](delegada);
            const solicitud = http.expectOne(`${BASE}/historia/recetas/rec-1/confirmacion`);
            expect(solicitud.request.body).toEqual({ profesional_id: 'responsable' });
            solicitud.flush({ codigo: 'PERMISO_DENEGADO', mensaje: 'Delegación revocada.' }, { status: 403, statusText: 'Forbidden' });
            expect(fixture.componentInstance['errorHistoria']()?.message).toBe('Delegación revocada.');
        });

        it('un asistente ve las recetas y no pide las notas', () => {
            // `receta.leer` sin `historia_clinica.leer`: es el caso real del rol
            // asistente, y la pantalla no puede fallar entera por ello.
            conPermisos('receta.leer');
            listar();
            abrir({ recetas: [receta()] });

            expect(texto()).toContain('no están a su alcance');
            expect(texto()).toContain('historia_clinica.leer');
            expect(texto()).toContain('Medicamento de ejemplo A');
            // Y no se pinta como avería: no hay mensaje de error.
            expect(texto()).not.toContain('No se pudo cargar la historia');
        });

        it('un 403 en las notas no tumba la carga de las recetas', () => {
            // El permiso esta en el principal pero el backend lo niega igualmente
            // -- por relacion asistencial, por ejemplo. Es el control funcionando.
            conPermisos('historia_clinica.leer', 'receta.leer');
            listar();
            abrir({ notas: 'denegado', recetas: [receta()] });

            expect(texto()).toContain('no están a su alcance');
            expect(texto()).toContain('Medicamento de ejemplo A');
            expect(texto()).not.toContain('No se pudo cargar la historia');
        });

        it('sin permiso de recetas lo dice, sin revelar cuantas hay', () => {
            conPermisos('historia_clinica.leer');
            listar();
            abrir({ notas: [nota()] });

            expect(texto()).toContain('Las recetas no están a su alcance');
            expect(texto()).toContain('receta.leer');
        });
    });

    describe('foco al cerrar los editores (WCAG 2.4.3)', () => {
        beforeEach(() =>
            conPermisos('historia_clinica.leer', 'historia_clinica.escribir', 'receta.leer', 'receta.crear', 'receta.confirmar'),
        );

        function raiz(): HTMLElement {
            return fixture.nativeElement as HTMLElement;
        }

        /** Pulsa como lo haría una persona: el puntero baja y después llega el clic. */
        function pulsar(selector: string): void {
            const boton = raiz().querySelector<HTMLButtonElement>(selector);
            expect(boton, selector).not.toBeNull();
            boton!.focus();
            boton!.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
            boton!.click();
            fixture.detectChanges();
        }

        async function cerrarConEscape(): Promise<void> {
            const dialogo = raiz().querySelector('dialog[open]');
            expect(dialogo).not.toBeNull();
            dialogo!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
            fixture.detectChanges();
            // La ventana busca el botón recreado cuando Angular termina de pintar.
            await new Promise((resolver) => setTimeout(resolver));
            expect(raiz().querySelector('dialog[open]')).toBeNull();
        }

        it('«Nueva nota» y «Corregir» de una nota concreta recuperan el foco', async () => {
            listar();
            abrir({
                notas: [
                    nota({ id: 'n-a', raiz_id: 'raiz-a', motivo_consulta: 'Primera [SINTETICO]' }),
                    nota({ id: 'n-b', raiz_id: 'raiz-b', motivo_consulta: 'Segunda [SINTETICO]', creado_en: '2026-09-11T14:00:00Z' }),
                ],
                recetas: [],
            });

            pulsar('#historia-nueva-nota');
            expect(raiz().querySelector('dialog[open]')?.getAttribute('aria-label')).toBe('Nueva nota de evolución');
            await cerrarConEscape();
            expect(document.activeElement?.id).toBe('historia-nueva-nota');

            // Hay dos «Corregir» con el mismo texto: el foco vuelve al de ESA nota.
            pulsar('#historia-corregir-raiz-b');
            expect(raiz().querySelector('dialog[open]')?.getAttribute('aria-label')).toBe('Corregir nota · versión nueva');
            await cerrarConEscape();
            expect(document.activeElement?.id).toBe('historia-corregir-raiz-b');
        });

        it('«Nueva receta» y «Crear nueva versión» recuperan el foco', async () => {
            listar();
            abrir({ notas: [], recetas: [receta()] });
            const componente = fixture.componentInstance as unknown as { pestana: { set(valor: string): void } };
            componente.pestana.set('recetas');
            fixture.detectChanges();

            pulsar('#historia-nueva-receta');
            http.expectOne(`${BASE}/profesionales/delegaciones/mias`).flush([]);
            fixture.detectChanges();
            expect(raiz().querySelector('dialog[open]')?.getAttribute('aria-label')).toBe('Nueva receta · borrador');
            await cerrarConEscape();
            expect(document.activeElement?.id).toBe('historia-nueva-receta');

            pulsar('#historia-version-receta-rec-1');
            http.expectOne(`${BASE}/profesionales/delegaciones/mias`).flush([]);
            fixture.detectChanges();
            expect(raiz().querySelector('dialog[open]')?.getAttribute('aria-label')).toBe('Nueva versión de receta');
            await cerrarConEscape();
            expect(document.activeElement?.id).toBe('historia-version-receta-rec-1');
        });
    });

    it('volver al listado limpia la historia mostrada', () => {
        conPermisos('historia_clinica.leer', 'receta.leer');
        listar();
        abrir({ notas: [nota()], recetas: [receta()] });
        expect(texto()).toContain('Medicamento de ejemplo A');

        fixture.componentInstance['cerrar']();
        fixture.detectChanges();

        // Dejar la historia del paciente anterior en pantalla al volver es como
        // alguien acaba leyendo la nota de otra persona.
        expect(texto()).not.toContain('Medicamento de ejemplo A');
        expect(texto()).toContain('Buscar paciente');
    });
});
