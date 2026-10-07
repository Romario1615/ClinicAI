import type { Mock } from "vitest";
import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Formulario033Component } from './formulario-033.component';
import { CONFIGURACION, CONFIGURACION_POR_DEFECTO } from '../../nucleo/servicios/configuracion';
import type { Formulario033Api, Nota, Odontograma, RegistroPlaca } from '../../nucleo/servicios/api.service';
import type { Cita } from '../../nucleo/modelos/dominio';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { EspecialidadHistoriaService } from '../../nucleo/servicios/especialidad-historia.service';
import { generarHtmlFormulario033 } from './formulario-033-impresion';

const BASE = CONFIGURACION_POR_DEFECTO.urlApi;
const PACIENTE = 'paciente-sintetico-033';
const permisosSesion = new Set<string>();

describe('Formulario033Component', () => {
    let fixture!: ComponentFixture<Formulario033Component>;
    let http: HttpTestingController;

    beforeEach(async () => {
        permisosSesion.clear();
        await TestBed.configureTestingModule({
            imports: [Formulario033Component],
            providers: [
                provideHttpClient(withXhr()),
                provideHttpClientTesting(),
                { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
                { provide: SesionService, useValue: {
                        tienePermiso: (codigo: string) => permisosSesion.has(codigo),
                        identidad: () => ({ profesional_id: 'profesional-sintetico' }),
                    } },
                { provide: EspecialidadHistoriaService, useValue: {
                        tieneModulo: (modulo: string) => modulo === 'odontograma' || modulo === 'periodoncia',
                    } },
            ],
        }).compileComponents();
        http = TestBed.inject(HttpTestingController);
    });

    function abrir(formularios: readonly Formulario033Api[] = [], puedeEditar = true): void {
        fixture = TestBed.createComponent(Formulario033Component);
        fixture.componentRef.setInput('pacienteId', PACIENTE);
        fixture.componentRef.setInput('puedeEditar', puedeEditar);
        fixture.detectChanges();
        http.expectOne(`${BASE}/catalogo/sedes`).flush([
            { id: 'sede-sintetica', nombre: 'Sede de prueba', direccion: null, telefono: null, zona_horaria: 'America/Guayaquil', minutos_antelacion_minima: 0 },
        ]);
        http.expectOne(`${BASE}/odontologia/pacientes/${PACIENTE}/formularios-033`).flush(formularios);
        fixture.detectChanges();
    }

    afterEach(() => http.verify());

    function botonConTexto(texto: string): HTMLButtonElement {
        const botones = fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>;
        const boton = Array.from(botones).find((elemento) => elemento.textContent?.includes(texto));
        if (!boton)
            throw new Error(`No existe el botón «${texto}».`);
        return boton;
    }

    it('muestra estados vacíos y no abre una captura hasta que el usuario la solicita', () => {
        abrir();
        expect(fixture.nativeElement.textContent).toContain('Aún no hay formularios 033');
        expect(fixture.nativeElement.querySelector('form')).toBeNull();
        botonConTexto('Registrar formulario').click();
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('form')).not.toBeNull();
        expect(fixture.nativeElement.textContent).toContain('Examen estomatognático');
        expect(fixture.nativeElement.textContent).toContain('Índices CPO–ceo');
        expect(fixture.nativeElement.querySelectorAll('[aria-labelledby="examen-estomatognatico"] select').length).toBe(13);
        expect(fixture.nativeElement.querySelectorAll('[aria-labelledby="salud-bucal"] tbody tr').length).toBe(18);
        // La primera compilación del formulario extenso bajo cobertura necesita
        // margen cuando CI comparte CPU con las pruebas API y del navegador.
    }, 10_000);

    it('identifica cada selector clínico de las tablas por región o pieza', () => {
        abrir();
        botonConTexto('Registrar formulario').click();
        fixture.detectChanges();

        const selectores = Array.from(fixture.nativeElement.querySelectorAll(
            '[aria-labelledby="examen-estomatognatico"] select, [aria-labelledby="salud-bucal"] tbody select',
        )) as HTMLSelectElement[];
        const nombres = selectores.map((selector) => selector.getAttribute('aria-label'));
        expect(selectores).toHaveLength(67);
        expect(nombres.every((nombre) => Boolean(nombre?.trim()))).toBe(true);
        expect(new Set(nombres).size).toBe(selectores.length);
        expect(nombres).toContain('Placa en pieza 16');
        expect(nombres).toContain('Cálculo en pieza 16');
        expect(nombres).toContain('Gingivitis en pieza 16');
    });

    it('presenta la captura extensa en una ventana de alto completo con acciones fijas', () => {
        abrir();
        botonConTexto('Registrar formulario').click();
        fixture.detectChanges();

        const dialogo = fixture.nativeElement.querySelector('[role="dialog"]') as HTMLElement;
        const formulario = dialogo.querySelector('form#formulario-033-captura') as HTMLFormElement;
        const guardar = dialogo.querySelector('.ventana__pie button[type="submit"]') as HTMLButtonElement;

        expect(dialogo.getAttribute('aria-modal')).toBe('true');
        expect(dialogo.querySelector('.ventana--alta')).not.toBeNull();
        expect(dialogo.querySelector('.ventana__cuerpo form')).toBe(formulario);
        expect(formulario.querySelector('button[type="submit"]')).toBeNull();
        expect(guardar.form).toBe(formulario);
        expect(dialogo.querySelector('.ventana__pie button[type="button"]')?.textContent).toContain('Cancelar');
    });

    it('mantiene el error de guardado visible dentro de la ventana para poder corregirlo', () => {
        abrir();
        botonConTexto('Registrar formulario').click();
        fixture.detectChanges();

        const motivo = fixture.nativeElement.querySelector('textarea[name="motivo"]') as HTMLTextAreaElement;
        motivo.value = 'Dolor dental al masticar';
        motivo.dispatchEvent(new Event('input', { bubbles: true }));
        (fixture.nativeElement.querySelector('form#formulario-033-captura') as HTMLFormElement)
            .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));

        http.expectOne({ method: 'POST', url: `${BASE}/odontologia/pacientes/${PACIENTE}/formularios-033` })
            .flush({ codigo: 'VALIDACION', mensaje: 'La información requiere una corrección.' }, { status: 422, statusText: 'Unprocessable Entity' });
        fixture.detectChanges();

        const dialogo = fixture.nativeElement.querySelector('[role="dialog"]') as HTMLElement;
        expect(dialogo.querySelector('[role="alert"]')?.textContent).toContain('La información requiere una corrección');
        expect(fixture.nativeElement.querySelector('.formulario-033 > [role="alert"]')).toBeNull();
        expect(dialogo.querySelector('form#formulario-033-captura')).not.toBeNull();

        botonConTexto('Cancelar').click();
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('[role="dialog"]')).toBeNull();
        expect(fixture.nativeElement.querySelector('[role="alert"]')).toBeNull();
    });

    it('vincula campos del navegador y envía las secciones sin datos de identidad editables', () => {
        abrir();
        botonConTexto('Registrar formulario').click();
        fixture.detectChanges();

        const motivo = fixture.nativeElement.querySelector('textarea[name="motivo"]') as HTMLTextAreaElement;
        motivo.value = 'Dolor dental al masticar';
        motivo.dispatchEvent(new Event('input', { bubbles: true }));
        botonConTexto('Guardar formulario').click();
        fixture.detectChanges();

        const solicitud = http.expectOne({ method: 'POST', url: `${BASE}/odontologia/pacientes/${PACIENTE}/formularios-033` });
        expect(solicitud.request.body.sede_id).toBe('sede-sintetica');
        expect(solicitud.request.body.datos.motivo_consulta).toBe('Dolor dental al masticar');
        expect(solicitud.request.body.datos.examen_estomatognatico.length).toBe(13);
        expect(solicitud.request.body.datos.indicadores_salud_bucal.sitios.length).toBe(18);
        expect(solicitud.request.body.nombre).toBeUndefined();
        solicitud.flush(salida());
        http.expectOne(`${BASE}/odontologia/pacientes/${PACIENTE}/formularios-033`).flush([salida()]);
        fixture.detectChanges();
        expect(fixture.nativeElement.textContent).toContain('Formulario 033 registrado como versión 1.');
    });

    it('carga solo fuentes permitidas, deja seleccionar las vinculaciones y prellena únicamente campos vacíos', () => {
        permisosSesion.add('agenda.leer');
        permisosSesion.add('historia_clinica.leer');
        permisosSesion.add('historia_clinica.leer_sensible');
        permisosSesion.add('odontograma.leer');
        abrir();
        botonConTexto('Registrar formulario').click();
        fixture.detectChanges();

        http.expectOne((solicitud) => solicitud.url === `${BASE}/agenda/citas` &&
            solicitud.params.get('paciente_id') === PACIENTE && solicitud.params.get('limite') === '200')
            .flush({ elementos: [
                citaFuente({ id: 'cita-033' }),
                citaFuente({ id: 'cita-ajena', profesional_id: 'otro-profesional' }),
                citaFuente({ id: 'cita-cancelada', estado: 'CANCELLED' }),
            ], total: 3, limite: 200, desplazamiento: 0 });
        http.expectOne(`${BASE}/historia/pacientes/${PACIENTE}/notas`).flush([notaFuente()]);
        http.expectOne(`${BASE}/odontologia/pacientes/${PACIENTE}/odontograma`).flush(odontogramaFuente());
        http.expectOne(`${BASE}/odontologia/pacientes/${PACIENTE}/indice-placa`).flush([placaFuente()]);
        fixture.detectChanges();

        const documento = fixture.nativeElement as HTMLElement;
        expect(documento.querySelector('[name="fuente-cita"] option[value="cita-ajena"]')).toBeNull();
        expect(documento.querySelector('[name="fuente-cita"] option[value="cita-cancelada"]')).toBeNull();
        expect(documento.querySelector('[name="fuente-cita"] option[value="cita-033"]')).not.toBeNull();
        expect(documento.querySelector('[name="fuente-nota"] option[value="nota-033"]')).not.toBeNull();
        expect(documento.querySelector('[name="fuente-odontograma"] option[value="odonto-033"]')).not.toBeNull();
        expect(documento.querySelector('[name="fuente-placa"] option[value="placa-033"]')).not.toBeNull();

        const formulario = fixture.componentInstance as unknown as {
            seleccionarCita(id: string): void;
            seleccionarNota(id: string): void;
            aplicarNota(): void;
            guardar(): void;
            datos: {
                motivo_consulta: string;
                enfermedad_actual: string | null;
            };
            citaId: string;
            notaId: string;
            odontogramaId: string;
            registroPlacaId: string;
        };
        formulario.seleccionarCita('cita-033');
        formulario.seleccionarNota('nota-033');
        formulario.aplicarNota();
        formulario.odontogramaId = 'odonto-033';
        formulario.registroPlacaId = 'placa-033';
        expect(formulario.datos.motivo_consulta).toBe('Dolor dental');
        expect(formulario.datos.enfermedad_actual).toBe('Dolor al masticar');
        formulario.datos.motivo_consulta = 'Motivo ya revisado';
        formulario.aplicarNota();
        expect(formulario.datos.motivo_consulta).toBe('Motivo ya revisado');

        formulario.guardar();
        const solicitud = http.expectOne({ method: 'POST', url: `${BASE}/odontologia/pacientes/${PACIENTE}/formularios-033` });
        expect(solicitud.request.body.cita_id).toBe('cita-033');
        expect(solicitud.request.body.nota_id).toBe('nota-033');
        expect(solicitud.request.body.odontograma_id).toBe('odonto-033');
        expect(solicitud.request.body.registro_placa_id).toBe('placa-033');
        solicitud.flush(salida({ cita_id: 'cita-033', nota_id: 'nota-033', odontograma_id: 'odonto-033', registro_placa_id: 'placa-033' }));
        http.expectOne(`${BASE}/odontologia/pacientes/${PACIENTE}/formularios-033`).flush([]);
    });

    it('no consulta fuentes clínicas cuando el rol no tiene permisos para leerlas', () => {
        abrir();
        botonConTexto('Registrar formulario').click();
        fixture.detectChanges();
        http.expectNone((solicitud) => solicitud.url.includes('/agenda/citas'));
        http.expectNone((solicitud) => solicitud.url.includes('/historia/pacientes/'));
        http.expectNone((solicitud) => solicitud.url.includes('/odontograma'));
        expect((fixture.nativeElement as HTMLElement).querySelector('.fuentes')).toBeNull();
    });

    it('avisa si una fuente falla y permite volver a consultar sin bloquear la captura', () => {
        permisosSesion.add('agenda.leer');
        abrir();
        botonConTexto('Registrar formulario').click();
        fixture.detectChanges();
        http.expectOne((solicitud) => solicitud.url === `${BASE}/agenda/citas`)
            .flush({ codigo: 'TEMPORAL', mensaje: 'Error temporal' }, { status: 503, statusText: 'Unavailable' });
        fixture.detectChanges();
        expect(fixture.nativeElement.textContent).toContain('No se pudieron cargar algunas fuentes clínicas');
        expect(fixture.nativeElement.querySelector('form')).not.toBeNull();

        botonConTexto('Volver a cargar fuentes').click();
        fixture.detectChanges();
        http.expectOne((solicitud) => solicitud.url === `${BASE}/agenda/citas`)
            .flush({ elementos: [], total: 0, limite: 200, desplazamiento: 0 });
        fixture.detectChanges();
        expect(fixture.nativeElement.textContent).not.toContain('No se pudieron cargar algunas fuentes clínicas');
    });

    it('permite leer el historial versionado sin ofrecer corrección al rol de solo lectura', () => {
        abrir([salida({ nota_id: 'nota-ref-033' })], false);
        expect(fixture.nativeElement.textContent).toContain('Motivo de consulta');
        expect(fixture.nativeElement.textContent).not.toContain('Crear corrección');
        (fixture.nativeElement.querySelector('.detalle-completo summary') as HTMLElement).click();
        fixture.detectChanges();
        expect(fixture.nativeElement.textContent).toContain('Identificación congelada al registrar');
        expect(fixture.nativeElement.textContent).toContain('Constantes vitales');
        expect(fixture.nativeElement.textContent).toContain('Fuentes vinculadas');
        expect(fixture.nativeElement.textContent).toContain('nota-ref-033');
        botonConTexto('Ver historial').click();
        fixture.detectChanges();
        http.expectOne(`${BASE}/odontologia/pacientes/${PACIENTE}/formularios-033/raiz-033/versiones`).flush([salida()]);
        fixture.detectChanges();
        expect(fixture.nativeElement.textContent).toContain('Versión 1');
    });

    it('audita antes de presentar la copia imprimible y abre dos páginas A4 seguras', () => {
        const botonImprimir = document.createElement('button');
        const documento = {
            title: '',
            open: vi.fn().mockName('open'),
            write: vi.fn().mockName('write'),
            close: vi.fn().mockName('close'),
            getElementById: vi.fn().mockName('getElementById').mockReturnValue(botonImprimir),
        } as unknown as Document;
        const ventana = {
            document: documento,
            opener: window,
            focus: vi.fn().mockName('focus'),
            print: vi.fn().mockName('print'),
            close: vi.fn().mockName('close'),
        } as unknown as Window;
        vi.spyOn(window, 'open').mockReturnValue(ventana);
        abrir([salida()], false);

        botonConTexto('Imprimir / guardar PDF').click();
        const solicitud = http.expectOne({
            method: 'POST',
            url: `${BASE}/odontologia/pacientes/${PACIENTE}/formularios-033/raiz-033/exportacion?version=1`,
        });
        expect(documento.write).not.toHaveBeenCalled();
        solicitud.flush(null);
        fixture.detectChanges();

        expect(documento.write).toHaveBeenCalledTimes(1);
        const contenido = vi.mocked((documento.write as Mock)).mock.lastCall?.[0] as string;
        expect(contenido).toContain('@page{size:A4 portrait');
        expect(contenido).toContain('Anverso');
        expect(contenido).toContain('Reverso');
        expect(ventana.opener).toBeNull();
        botonImprimir.click();
        expect(ventana.print).toHaveBeenCalled();
        expect(fixture.nativeElement.textContent).toContain('registrada en auditoría');
    });

    it('cierra la vista en blanco si el servidor rechaza la exportación', () => {
        const ventana = {
            document: { title: '' },
            opener: window,
            focus: vi.fn().mockName('focus'),
            print: vi.fn().mockName('print'),
            close: vi.fn().mockName('close'),
        } as unknown as Window;
        vi.spyOn(window, 'open').mockReturnValue(ventana);
        abrir([salida()], false);
        botonConTexto('Imprimir / guardar PDF').click();
        const solicitud = http.expectOne({
            method: 'POST',
            url: `${BASE}/odontologia/pacientes/${PACIENTE}/formularios-033/raiz-033/exportacion?version=1`,
        });
        solicitud.flush({ mensaje: 'Permiso insuficiente.' }, { status: 403, statusText: 'Forbidden' });
        fixture.detectChanges();
        expect(ventana.close).toHaveBeenCalled();
        expect(fixture.nativeElement.querySelector('[role="alert"]').textContent).toContain('Permiso insuficiente');
    });

    it('informa cuando el navegador bloquea la ventana de impresión', () => {
        vi.spyOn(window, 'open').mockReturnValue(null);
        abrir([salida()], false);
        botonConTexto('Imprimir / guardar PDF').click();
        http.expectNone((solicitud) => solicitud.url.includes('/exportacion'));
        fixture.detectChanges();
        expect(fixture.nativeElement.textContent).toContain('El navegador bloqueó la ventana');
    });

    it('escapa campos clínicos antes de construir el documento imprimible', () => {
        const original = salida();
        const html = generarHtmlFormulario033(salida({
            cita_id: 'cita-033', nota_id: 'nota-033', odontograma_id: 'odonto-033', registro_placa_id: 'placa-033',
            contexto_identidad: {
                sede: 'Sede de prueba', profesional: 'Dra. <script>alert(1)</script>',
                nombres: 'Ana <img src=x onerror=alert(1)>', apellidos: 'Prueba',
            },
            datos: {
                ...original.datos,
                motivo_consulta: '<script>alert("motivo")</script>',
                antecedentes_personales: [{ codigo: 'ASMA', presente: true, detalle: 'Controlada' }],
                antecedentes_familiares: [{ codigo: 'CARDIOPATIA', presente: false, detalle: null }],
                examen_estomatognatico: [{ region: 'LABIOS', hallazgo: 'PATOLOGIA', detalle: 'Lesión leve', grado: 1 }],
                indicadores_salud_bucal: {
                    sitios: [{ pieza: 16, placa: 1, calculo: 0, gingivitis: false }],
                    enfermedad_periodontal: 'LEVE', oclusion: 'ANGLE_I', fluorosis: 'SIN_REGISTRO',
                },
                indices_cpo_ceo: { permanentes_d: 1 },
                examenes_complementarios: [{ tipo: 'RAYOS_X', descripcion: 'Control', resultado: 'Sin hallazgos' }],
                diagnosticos: [{ codigo_cie: 'K02.9', descripcion: 'Caries', tipo: 'PRESUNTIVO' }],
                sesiones_tratamiento: [{ numero: 1, fecha: '2026-10-06', diagnostico_complicaciones: null, procedimiento: 'Evaluación', prescripciones: null, proxima_cita: null, alta: false }],
            },
        }));
        expect(html).toContain('&lt;script&gt;alert(&quot;motivo&quot;)&lt;/script&gt;');
        expect(html).toContain('&lt;img src=x onerror=alert(1)&gt;');
        expect(html).not.toContain('<script>alert(');
        expect(html).not.toContain('<img src=x');
        expect(html).toContain('Fuentes vinculadas');
        expect(html).toContain('Sesiones de tratamiento');
    });

    it('corrige una captura con control de versión base y crea una nueva versión', () => {
        abrir([salida({
                cita_id: 'cita-ref', nota_id: 'nota-ref',
                odontograma_id: 'odonto-ref', registro_placa_id: 'placa-ref',
            })]);
        botonConTexto('Crear corrección').click();
        fixture.detectChanges();
        expect(fixture.nativeElement.textContent).toContain('Crear nueva versión');
        (fixture.componentInstance as unknown as {
            motivoCorreccion: string;
        }).motivoCorreccion =
            'Corrección de hallazgo';
        fixture.detectChanges();
        botonConTexto('Guardar nueva versión').click();
        const solicitud = http.expectOne({
            method: 'POST',
            url: `${BASE}/odontologia/pacientes/${PACIENTE}/formularios-033/raiz-033/versiones`,
        });
        expect(solicitud.request.body.version_base).toBe(1);
        expect(solicitud.request.body.motivo).toBe('Corrección de hallazgo');
        expect(solicitud.request.body.cita_id).toBe('cita-ref');
        expect(solicitud.request.body.nota_id).toBe('nota-ref');
        expect(solicitud.request.body.odontograma_id).toBe('odonto-ref');
        expect(solicitud.request.body.registro_placa_id).toBe('placa-ref');
        solicitud.flush(salida({ version: 2, id: 'captura-033-v2' }));
        http.expectOne(`${BASE}/odontologia/pacientes/${PACIENTE}/formularios-033`)
            .flush([salida({ version: 2, id: 'captura-033-v2' })]);
        fixture.detectChanges();
        expect(fixture.nativeElement.textContent).toContain('Formulario 033 corregido como versión 2.');
    });
});

function salida(cambios: Partial<Formulario033Api> = {}): Formulario033Api {
    return {
        id: 'captura-033',
        raiz_id: 'raiz-033',
        version: 1,
        vigente: true,
        motivo_modificacion: null,
        paciente_id: PACIENTE,
        profesional_id: 'profesional-sintetico',
        sede_id: 'sede-sintetica',
        cita_id: null,
        nota_id: null,
        odontograma_id: null,
        registro_placa_id: null,
        contexto_identidad: { sede: 'Sede de prueba', profesional: 'Profesional de prueba' },
        datos: {
            embarazada: null,
            motivo_consulta: 'Dolor dental al masticar',
            enfermedad_actual: null,
            antecedentes_personales: [],
            antecedentes_familiares: [],
            constantes_vitales: { temperatura_c: null, pulso_minuto: null, frecuencia_respiratoria_minuto: null, presion_sistolica_mmhg: null, presion_diastolica_mmhg: null },
            examen_estomatognatico: [],
            indicadores_salud_bucal: { sitios: [], enfermedad_periodontal: 'SIN_REGISTRO', oclusion: 'SIN_REGISTRO', fluorosis: 'SIN_REGISTRO' },
            indices_cpo_ceo: {},
            examenes_complementarios: [],
            diagnosticos: [],
            sesiones_tratamiento: [],
        },
        creado_en: '2026-10-06T15:00:00Z',
        ...cambios,
    };
}

function citaFuente(cambios: Partial<Cita> = {}): Cita {
    return {
        id: 'cita-033',
        paciente_id: PACIENTE,
        profesional_id: 'profesional-sintetico',
        servicio_id: 'servicio-sintetico',
        sede_id: 'sede-sintetica',
        consultorio_id: null,
        inicio: '2026-10-06T10:00:00-05:00',
        fin: '2026-10-06T10:30:00-05:00',
        duracion_minutos: 30,
        minutos_preparacion: 0,
        estado: 'COMPLETED',
        origen: 'PANEL',
        expira_en: null,
        confirmada_en: null,
        llegada_en: null,
        atencion_iniciada_en: null,
        completada_en: '2026-10-06T10:30:00-05:00',
        cancelada_en: null,
        motivo_cancelacion: null,
        ...cambios,
    };
}

function notaFuente(cambios: Partial<Nota> = {}): Nota {
    return {
        id: 'nota-033',
        raiz_id: 'nota-033',
        version: 1,
        vigente: true,
        motivo_modificacion: null,
        paciente_id: PACIENTE,
        profesional_id: 'profesional-sintetico',
        cita_id: 'cita-033',
        tipo: 'EVOLUCION',
        nivel_sensibilidad: 'N2',
        motivo_consulta: 'Dolor dental',
        subjetivo: 'Dolor al masticar',
        objetivo: 'Observación clínica de ejemplo',
        analisis: null,
        plan: null,
        signos_vitales: null,
        creado_en: '2026-10-06T15:00:00Z',
        ...cambios,
    };
}

function odontogramaFuente(): Odontograma {
    return {
        id: 'odonto-033',
        paciente_id: PACIENTE,
        profesional_id: 'profesional-sintetico',
        version: 2,
        vigente: true,
        motivo_modificacion: null,
        procedimiento_id: null,
        creado_en: '2026-10-06T15:00:00Z',
        denticion: 'PERMANENTE',
        nivel_sensibilidad: 'N2',
        piezas: {},
    };
}

function placaFuente(): RegistroPlaca {
    return {
        id: 'placa-033',
        paciente_id: PACIENTE,
        profesional_id: 'profesional-sintetico',
        piezas_evaluadas: [16, 17],
        superficies_con_placa: {},
        total_superficies: 8,
        total_con_placa: 2,
        porcentaje: '25.00',
        observacion: 'Control de ejemplo',
        creado_en: '2026-10-06T15:00:00Z',
    };
}
