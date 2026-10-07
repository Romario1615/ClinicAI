/**
 * Pruebas de la pantalla de conocimiento.
 *
 * Lo que se verifica y por que importa
 * ------------------------------------
 * **Sin fuente no se muestran resultados parecidos.** Es la unica propiedad
 * que de verdad importa aqui. Si el backend dice `hay_fuente: false`, la
 * pantalla no puede rellenar el hueco con los extractos mas proximos: alguien
 * los leeria en voz alta a un paciente y estaria repitiendo algo que la
 * clinica nunca aprobo. La prueba envia una respuesta sin fuente **que ademas
 * trae resultados** —el caso que un descuido dejaria pasar— y comprueba que no
 * se pintan.
 *
 * **El texto del documento se escapa.** Un documento puede contener marcado, y
 * si acabara como HTML vivo un PDF subido por cualquiera seria ejecucion de
 * codigo en la sesion de quien lo lee (ADR-0014).
 *
 * **Los documentos marcados por la deteccion de inyeccion se ven.** Aprobar
 * uno sin mirarlo es como una instruccion hostil entra en el corpus que
 * alimenta al agente.
 *
 * **Una consulta de una letra no se envia.**
 */
import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ConocimientoComponent } from './conocimiento.component';
import { CONFIGURACION, CONFIGURACION_POR_DEFECTO } from '../../nucleo/servicios/configuracion';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import type { Documento, PermisoDocumento, RespuestaBusqueda, } from '../../nucleo/servicios/api.service';
import type { Identidad } from '../../nucleo/modelos/dominio';

const BASE = CONFIGURACION_POR_DEFECTO.urlApi;

function documento(sufijo: string, extra: Partial<Documento> = {}): Documento {
    return {
        id: `doc-${sufijo}`,
        titulo: `Documento ${sufijo}`,
        tipo: 'PROTOCOLO',
        status: 'PUBLISHED',
        version_vigente: 1,
        sensitivity_level: 'N0',
        branch_id: null,
        specialty_id: null,
        service_id: null,
        etiquetas: [],
        effective_from: null,
        effective_until: null,
        aprobado_por: null,
        aprobado_en: null,
        archivado_en: null,
        ...extra,
    };
}

function resultado(sufijo: string, extracto: string) {
    return {
        document_id: `doc-${sufijo}`,
        version: 1,
        indice_fragmento: 0,
        referencia: `Documento ${sufijo} · fragmento 1`,
        extracto,
        puntuacion: 0.9,
        posicion_vectorial: 1,
        posicion_textual: 2,
    };
}

function identidadAprobadora(): Identidad {
    return {
        usuario_id: 'u-aprobador',
        correo: 'aprobador@example.invalid',
        nombre: 'Revisor',
        apellido: 'Conocimiento',
        clinica_id: 'c-1',
        roles: ['administrador_clinica'],
        permisos: ['conocimiento.leer', 'conocimiento.aprobar'],
        ambito: {
            clinica_id: 'c-1',
            sedes: [],
            todas_las_sedes: true,
            especialidades: [],
            todas_las_especialidades: true,
            profesionales: [],
            todos_los_profesionales: true,
            todos_los_pacientes: true,
            nivel_maximo: 'N1',
        },
        requiere_segundo_factor: false,
        segundo_factor_cumplido: false,
        dosfa_habilitado: false,
        debe_cambiar_contrasena: false,
        ultimo_acceso_en: null,
    };
}

import { INDICADORES_VACIOS } from '../../nucleo/pruebas/sesion-sintetica';
describe('ConocimientoComponent', () => {
    let fixture: ComponentFixture<ConocimientoComponent>;
    let http: HttpTestingController;

    beforeEach(() => {
        TestBed.configureTestingModule({
            imports: [ConocimientoComponent],
            providers: [
                provideHttpClient(withXhr()),
                provideHttpClientTesting(),
                { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
                INDICADORES_VACIOS,
            ],
        });
        fixture = TestBed.createComponent(ConocimientoComponent);
        http = TestBed.inject(HttpTestingController);
    });

    afterEach(() => http.verify());

    function cargar(elementos: readonly Documento[] = []): void {
        fixture.detectChanges();
        http
            .expectOne((p) => p.url === `${BASE}/conocimiento/documentos`)
            .flush({ elementos, total: elementos.length });
        fixture.detectChanges();
    }

    function buscar(respuesta: RespuestaBusqueda, consulta = 'horas de ayuno'): void {
        fixture.componentInstance['consulta'] = consulta;
        fixture.componentInstance['buscar']();
        http.expectOne(`${BASE}/conocimiento/busqueda`).flush(respuesta);
        fixture.detectChanges();
    }

    function texto(): string {
        return (fixture.nativeElement as HTMLElement).textContent ?? '';
    }

    it('carga el listado de documentos al abrirse', () => {
        cargar([documento('1')]);
        expect(texto()).toContain('Documento 1');
    });

    describe('cuando no hay fuente aprobada', () => {
        it('muestra el mensaje del backend y NO pinta resultados parecidos', () => {
            cargar([documento('1')]);

            // El caso que un descuido dejaria pasar: sin fuente, pero con
            // resultados en el cuerpo. Ramificar por `resultados.length` en lugar
            // de por `hay_fuente` los mostraria.
            buscar({
                hay_fuente: false,
                mensaje: 'No tengo informacion aprobada sobre eso.',
                resultados: [resultado('1', 'Un extracto solo parecido, que no responde.')],
                documentos_citados: [],
            });

            expect(texto()).toContain('No hay información aprobada');
            expect(texto()).toContain('No tengo informacion aprobada sobre eso.');
            expect(texto()).not.toContain('Un extracto solo parecido');
        });

        it('explica por que no se muestran aproximaciones', () => {
            cargar();
            buscar({
                hay_fuente: false,
                mensaje: 'No tengo informacion aprobada sobre eso.',
                resultados: [],
                documentos_citados: [],
            });

            expect(texto()).toContain('Derive la consulta a un profesional');
        });
    });

    describe('cuando hay fuente', () => {
        it('muestra el extracto con su referencia y version', () => {
            cargar([documento('1')]);
            buscar({
                hay_fuente: true,
                mensaje: null,
                resultados: [resultado('1', 'Debe mantener ayuno de doce horas.')],
                documentos_citados: ['doc-1'],
            });

            expect(texto()).toContain('Debe mantener ayuno de doce horas.');
            expect(texto()).toContain('versión 1');
            expect(texto()).toContain('Documento 1 · fragmento 1');
        });

        it('escapa el texto del documento en lugar de interpretarlo', () => {
            cargar([documento('1')]);
            buscar({
                hay_fuente: true,
                mensaje: null,
                resultados: [resultado('1', '<img src=x onerror="alert(1)"> texto del documento')],
                documentos_citados: ['doc-1'],
            });

            const raiz = fixture.nativeElement as HTMLElement;
            // Ni una etiqueta viva: el texto de un documento es dato citado.
            expect(raiz.querySelector('blockquote img')).toBeNull();
            expect(texto()).toContain('<img src=x onerror="alert(1)">');
        });
    });

    it('no envia una consulta demasiado corta', () => {
        cargar();
        fixture.componentInstance['consulta'] = 'a';
        fixture.componentInstance['buscar']();
        // http.verify() en afterEach falla si se hubiera enviado algo.
        expect(fixture.componentInstance['respuesta']()).toBeNull();
    });

    it('destaca los documentos marcados por la deteccion de inyeccion', () => {
        cargar([documento('1'), documento('2', { requiere_revision: true, titulo: 'Instructivo raro' })]);

        expect(texto()).toContain('esperan revisión de seguridad');
        expect(texto()).toContain('Instructivo raro');
        expect(texto()).toContain('revisión pendiente');
    });

    it('distingue los estados que responden consultas de los que no', () => {
        cargar([
            documento('1', { status: 'PUBLISHED' }),
            documento('2', { status: 'DRAFT' }),
            documento('3', { status: 'ARCHIVED' }),
        ]);

        // Un borrador excelente no responde a nadie, y quien lo escribio necesita
        // verlo de un vistazo.
        expect(texto()).toContain('responde consultas');
        expect(texto()).toContain('no responde');
        expect(texto()).toContain('Borrador');
        expect(texto()).toContain('Archivado');
    });

    it('exige retirar a borrador un documento publicado antes de cargar otra versión', () => {
        const identidad = identidadAprobadora();
        TestBed.inject(SesionService).establecerIdentidad({
            ...identidad,
            permisos: [...identidad.permisos, 'conocimiento.cargar'],
        });
        const publicado = documento('publicado', { status: 'PUBLISHED' });
        cargar([publicado]);

        expect(texto()).toContain('Retirar para corregir');
        expect(texto()).toContain('deberá revisarse y aprobarse de nuevo');
        expect(texto()).not.toContain('Versión nueva');

        const retirar = Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('button'))
            .find((boton) => boton.textContent?.includes('Retirar para corregir'));
        expect(retirar).toBeDefined();
        retirar?.click();
        const cambio = http.expectOne(`${BASE}/conocimiento/documentos/${publicado.id}/estado`);
        expect(cambio.request.method).toBe('POST');
        expect(cambio.request.body).toEqual({ nuevo_estado: 'DRAFT', motivo: null });
        cambio.flush(documento('publicado', { status: 'DRAFT' }));
        http.expectOne((p) => p.url === `${BASE}/conocimiento/documentos`).flush({
            elementos: [documento('publicado', { status: 'DRAFT' })],
            total: 1,
        });
        fixture.detectChanges();
        expect(texto()).toContain('Versión nueva');
    });

    it('permite asignar y guardar una regla de acceso para un rol', () => {
        TestBed.inject(SesionService).establecerIdentidad(identidadAprobadora());
        const doc = documento('acl');
        cargar([doc]);

        fixture.componentInstance['gestionarPermisos'](doc);
        http
            .expectOne(`${BASE}/conocimiento/permisos/opciones`)
            .flush({
            roles: [{ id: 'rol-1', nombre: 'Recepción', codigo: 'recepcion' }],
            usuarios: [],
            sedes: [],
            especialidades: [],
        });
        http
            .expectOne(`${BASE}/conocimiento/documentos/${doc.id}/permisos`)
            .flush({ document_id: doc.id, permisos: [] });
        fixture.detectChanges();

        fixture.componentInstance['principalNuevo'] = 'rol-1';
        fixture.componentInstance['puedeUsarEnAgenteNuevo'] = true;
        fixture.componentInstance['agregarPermiso']();
        fixture.detectChanges();
        expect(texto()).toContain('Recepción');
        expect(texto()).toContain('Agente puede citar');

        fixture.componentInstance['guardarPermisos']();
        const solicitud = http.expectOne(`${BASE}/conocimiento/documentos/${doc.id}/permisos`);
        expect(solicitud.request.method).toBe('PUT');
        const permisos = solicitud.request.body['permisos'] as readonly PermisoDocumento[];
        expect(permisos).toEqual([
            {
                principal_tipo: 'ROL',
                principal_id: 'rol-1',
                puede_leer: true,
                puede_usar_en_agente: true,
            },
        ]);
        solicitud.flush({ document_id: doc.id, permisos });
        fixture.detectChanges();
        expect(texto()).toContain('Accesos del documento actualizados y auditados.');
    });

    it('filtrar por estado vuelve a pedir el listado con ese filtro', () => {
        cargar([documento('1')]);

        fixture.componentInstance['cambiarFiltro']('DRAFT');
        const peticion = http.expectOne((p) => p.url === `${BASE}/conocimiento/documentos`);
        expect(peticion.request.params.get('estado')).toBe('DRAFT');
        peticion.flush({ elementos: [], total: 0 });
    });

    it('el titulo del resultado sobrevive a filtrar el listado por otro estado', () => {
        cargar([documento('1', { titulo: 'Preparacion de examenes' })]);

        // Se filtra por borradores: el documento publicado desaparece del listado.
        fixture.componentInstance['cambiarFiltro']('DRAFT');
        http
            .expectOne((p) => p.url === `${BASE}/conocimiento/documentos`)
            .flush({ elementos: [], total: 0 });
        fixture.detectChanges();

        buscar({
            hay_fuente: true,
            mensaje: null,
            resultados: [resultado('1', 'Ayuno de doce horas.')],
            documentos_citados: ['doc-1'],
        });

        // Resolver el titulo contra el listado filtrado lo convertiria en el
        // identificador interno `doc:uuid#v1:0`, que no le dice nada a nadie.
        expect(texto()).toContain('Preparacion de examenes');
        expect(texto()).not.toContain('Documento de la base de conocimiento');
    });

    it('un error de busqueda se muestra con su codigo', () => {
        cargar();
        fixture.componentInstance['consulta'] = 'ayuno';
        fixture.componentInstance['buscar']();
        http
            .expectOne(`${BASE}/conocimiento/busqueda`)
            .flush({ codigo: 'PERMISO_DENEGADO', mensaje: 'No tiene permiso.' }, { status: 403, statusText: 'Forbidden' });
        fixture.detectChanges();

        expect(texto()).toContain('No se pudo completar la búsqueda');
        expect(texto()).toContain('PERMISO_DENEGADO');
    });
});
