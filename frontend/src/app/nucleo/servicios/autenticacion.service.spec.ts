/**
 * Pruebas de la sesión, del cliente de API y de la rotación del token.
 *
 * Lo que se verifica y por qué importa:
 *
 * * **Los tokens no se persisten.** Si acabaran en `localStorage`, un XSS se
 *   los llevaría y mantendría la sesión abierta desde fuera indefinidamente
 *   (ADR‑0016). La prueba lo comprueba mirando el almacenamiento de verdad.
 * * **La rotación se comparte.** Varias peticiones caducadas a la vez no
 *   pueden presentar el mismo refresco por separado: el backend lo
 *   interpretaría —con razón— como un token robado y revocaría la familia
 *   completa de sesiones.
 * * **Los errores se traducen.** Un componente que recibe
 *   `HttpErrorResponse` acaba mostrando «Http failure response for…», que es
 *   el mensaje más inútil posible en una recepción con pacientes esperando.
 */
import { HttpClient, provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ApiService, FalloApi } from './api.service';
import { AutenticacionService } from './autenticacion.service';
import { CONFIGURACION, CONFIGURACION_POR_DEFECTO } from './configuracion';
import { SesionService } from './sesion.service';
import type { ParTokens } from '../modelos/dominio';

const BASE = CONFIGURACION_POR_DEFECTO.urlApi;

function tokens(sufijo: string): ParTokens {
    return {
        token_acceso: `acceso-${sufijo}`,
        token_refresco: `refresco-${sufijo}`,
        tipo_token: 'Bearer',
        expira_en: new Date().toISOString(),
        requiere_segundo_factor: false,
    };
}

describe('SesionService', () => {
    let sesion: SesionService;

    beforeEach(() => {
        localStorage.clear();
        TestBed.configureTestingModule({});
        sesion = TestBed.inject(SesionService);
    });

    it('empieza sin sesión', () => {
        expect(sesion.autenticado()).toBe(false);
        expect(sesion.tokenAcceso()).toBeNull();
    });

    it('NO guarda los tokens en el almacenamiento del navegador', () => {
        sesion.establecerTokens(tokens('1'));

        // La comprobación mira el almacenamiento entero, no una clave concreta:
        // el riesgo es que alguien los guarde con otro nombre.
        const todo = JSON.stringify({
            local: { ...localStorage },
            sesion: { ...sessionStorage },
        });
        expect(todo).not.toContain('acceso-1');
        expect(todo).not.toContain('refresco-1');
    });

    it('recuerda el correo, que no es una credencial', () => {
        sesion.recordarCorreo('  Persona@Example.Invalid  ');
        expect(sesion.correoRecordado()).toBe('persona@example.invalid');
        expect(localStorage.getItem('clinica.correo')).toBe('persona@example.invalid');
    });

    it('limpiar borra tokens e identidad', () => {
        sesion.establecerTokens(tokens('1'));
        sesion.limpiar();
        expect(sesion.autenticado()).toBe(false);
        expect(sesion.identidad()).toBeNull();
    });

    it('los permisos solo sirven para decidir qué mostrar', () => {
        expect(sesion.tienePermiso('agenda.leer')).toBe(false);
        sesion.establecerIdentidad({
            usuario_id: 'u',
            correo: 'p@example.invalid',
            nombre: 'A',
            apellido: 'B',
            clinica_id: 'c',
            roles: ['recepcion'],
            permisos: ['agenda.leer'],
            ambito: {
                clinica_id: 'c',
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
        });

        expect(sesion.tienePermiso('agenda.leer')).toBe(true);
        expect(sesion.tienePermiso('historia_clinica.leer')).toBe(false);
        expect(sesion.tieneAlgunPermiso('historia_clinica.leer', 'agenda.leer')).toBe(true);
        expect(sesion.nombreCompleto()).toBe('A B');
    });

    it('marca el segundo factor pendiente cuando el rol lo exige', () => {
        sesion.establecerTokens({ ...tokens('1'), requiere_segundo_factor: true });
        expect(sesion.segundoFactorPendiente()).toBe(true);
    });
});

describe('ApiService: traducción de errores', () => {
    let api: ApiService;
    let http: HttpTestingController;

    beforeEach(() => {
        TestBed.configureTestingModule({
            providers: [
                provideHttpClient(withXhr()),
                provideHttpClientTesting(),
                { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
            ],
        });
        api = TestBed.inject(ApiService);
        http = TestBed.inject(HttpTestingController);
    });

    afterEach(() => http.verify());

    it('traduce el cuerpo de error del backend', async () => {
        api.citas().subscribe({
            error: (fallo: FalloApi) => {
                expect(fallo).toBeInstanceOf(FalloApi);
                expect(fallo.codigo).toBe('PERMISO_DENEGADO');
                expect(fallo.message).toBe('No tiene permiso.');
                expect(fallo.estado).toBe(403);
                expect(fallo.correlacionId).toBe('abc123');
                ;
            },
        });

        http.expectOne((peticion) => peticion.url === `${BASE}/agenda/citas`).flush({ codigo: 'PERMISO_DENEGADO', mensaje: 'No tiene permiso.', correlacion_id: 'abc123' }, { status: 403, statusText: 'Forbidden' });
    });

    it('distingue el servidor inalcanzable de un error del servidor', async () => {
        api.citas().subscribe({
            error: (fallo: FalloApi) => {
                // Estado 0: la petición no salió o no volvió. Decirlo así evita el
                // error vacío que no explica nada.
                expect(fallo.codigo).toBe('SIN_CONEXION');
                expect(fallo.estado).toBe(0);
                ;
            },
        });

        http
            .expectOne((peticion) => peticion.url === `${BASE}/agenda/citas`)
            .error(new ProgressEvent('error'), { status: 0 });
    });

    it('marca como no encontrado el 404, que también cubre lo fuera de ámbito', async () => {
        api.cita('x').subscribe({
            error: (fallo: FalloApi) => {
                expect(fallo.noEncontrado).toBe(true);
                ;
            },
        });

        http
            .expectOne(`${BASE}/agenda/citas/x`)
            .flush({ codigo: 'RECURSO_NO_ENCONTRADO', mensaje: 'No existe.' }, { status: 404, statusText: 'Not Found' });
    });

    it('repite la clave en los parámetros de lista, no los une con comas', () => {
        api.citas({ estado: ['CONFIRMED', 'HELD'] }).subscribe();

        const peticion = http.expectOne((p) => p.url === `${BASE}/agenda/citas` && p.params.getAll('estado')?.length === 2);
        // Unirlos con comas produciría un 422: «CONFIRMED,HELD» no está en el
        // literal de estados que acepta el backend.
        expect(peticion.request.params.getAll('estado')).toEqual(['CONFIRMED', 'HELD']);
        peticion.flush({ elementos: [], total: 0, limite: 50, desplazamiento: 0 });
    });

    it('omite los parámetros vacíos', () => {
        api.citas({ sede_id: '', profesional_id: undefined, limite: 10 }).subscribe();

        const peticion = http.expectOne((p) => p.url === `${BASE}/agenda/citas`);
        expect(peticion.request.params.has('sede_id')).toBe(false);
        expect(peticion.request.params.has('profesional_id')).toBe(false);
        expect(peticion.request.params.get('limite')).toBe('10');
        peticion.flush({ elementos: [], total: 0, limite: 10, desplazamiento: 0 });
    });

    it('envía la clave de idempotencia como cabecera', () => {
        api
            .crearCita({
            paciente_id: 'p',
            profesional_id: 'pr',
            servicio_id: 's',
            sede_id: 'se',
            inicio: '2026-04-16T14:00:00Z',
        }, 'reserva-123')
            .subscribe();

        const peticion = http.expectOne(`${BASE}/agenda/citas`);
        expect(peticion.request.headers.get('Idempotency-Key')).toBe('reserva-123');
        peticion.flush({});
    });
});

describe('ApiService: rutas de la agenda', () => {
    let api: ApiService;
    let http: HttpTestingController;

    beforeEach(() => {
        TestBed.configureTestingModule({
            providers: [
                provideHttpClient(withXhr()),
                provideHttpClientTesting(),
                { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
            ],
        });
        api = TestBed.inject(ApiService);
        http = TestBed.inject(HttpTestingController);
    });

    afterEach(() => http.verify());

    // Estas comprobaciones fijan la URL y el método de cada operación. Parecen
    // triviales y no lo son: una ruta mal escrita no falla al compilar, falla
    // en producción como un 404 que la interfaz muestra como «no se pudo
    // completar la operación», sin pista de por qué.
    const RESERVA = {
        paciente_id: 'p',
        profesional_id: 'pr',
        servicio_id: 's',
        sede_id: 'se',
        inicio: '2026-04-16T14:00:00Z',
    };

    it('disponibilidad', () => {
        api
            .disponibilidad({
            profesional_id: 'pr',
            servicio_id: 's',
            sede_id: 'se',
            desde: '2026-04-16T05:00:00Z',
            hasta: '2026-04-17T05:00:00Z',
            explicar: true,
        })
            .subscribe();
        const peticion = http.expectOne((p) => p.url === `${BASE}/agenda/disponibilidad`);
        expect(peticion.request.method).toBe('GET');
        expect(peticion.request.params.get('explicar')).toBe('true');
        peticion.flush({});
    });

    it('bloquear turno', () => {
        api.bloquearTurno(RESERVA, 'clave-1').subscribe();
        const peticion = http.expectOne(`${BASE}/agenda/citas/bloqueos`);
        expect(peticion.request.method).toBe('POST');
        expect(peticion.request.headers.get('Idempotency-Key')).toBe('clave-1');
        peticion.flush({});
    });

    it('confirmar', () => {
        api.confirmarCita('c1').subscribe();
        const peticion = http.expectOne(`${BASE}/agenda/citas/c1/confirmacion`);
        expect(peticion.request.method).toBe('POST');
        expect(peticion.request.body).toBeNull();
        peticion.flush({});
    });

    it('cancelar envía el motivo', () => {
        api.cancelarCita('c1', 'El paciente lo pidio', 24).subscribe();
        const peticion = http.expectOne(`${BASE}/agenda/citas/c1/cancelacion`);
        expect(peticion.request.body).toEqual({
            motivo: 'El paciente lo pidio',
            horas_antelacion_minima: 24,
        });
        peticion.flush({});
    });

    it('reprogramar', () => {
        api
            .reprogramarCita('c1', { nuevo_inicio: '2026-04-20T14:00:00Z', motivo: 'Cambio' })
            .subscribe();
        const peticion = http.expectOne(`${BASE}/agenda/citas/c1/reprogramacion`);
        expect(peticion.request.method).toBe('POST');
        expect(peticion.request.body).toEqual({
            nuevo_inicio: '2026-04-20T14:00:00Z',
            motivo: 'Cambio',
        });
        peticion.flush({});
    });

    it('completar', () => {
        api.completarCita('c1').subscribe();
        const peticion = http.expectOne(`${BASE}/agenda/citas/c1/completado`);
        expect(peticion.request.method).toBe('POST');
        expect(peticion.request.body).toBeNull();
        peticion.flush({});
    });

    it('marcar inasistencia', () => {
        api.marcarInasistencia('c1').subscribe();
        const peticion = http.expectOne(`${BASE}/agenda/citas/c1/inasistencia`);
        expect(peticion.request.method).toBe('POST');
        expect(peticion.request.body).toBeNull();
        peticion.flush({});
    });

    it('registrar llegada', () => {
        api.registrarLlegadaCita('c1').subscribe();
        const peticion = http.expectOne(`${BASE}/agenda/citas/c1/llegada`);
        expect(peticion.request.method).toBe('POST');
        peticion.flush({});
    });

    it('iniciar atención', () => {
        api.iniciarAtencionCita('c1').subscribe();
        const peticion = http.expectOne(`${BASE}/agenda/citas/c1/inicio-atencion`);
        expect(peticion.request.method).toBe('POST');
        peticion.flush({});
    });

    it('identidad', () => {
        api.identidad().subscribe();
        const peticion = http.expectOne(`${BASE}/autenticacion/yo`);
        expect(peticion.request.method).toBe('GET');
        peticion.flush({});
    });

    it('buscar pacientes', () => {
        api.pacientes({ termino: 'Prueba', limite: 25 }).subscribe();
        const peticion = http.expectOne((p) => p.url === `${BASE}/pacientes/`);
        expect(peticion.request.params.get('termino')).toBe('Prueba');
        peticion.flush({ elementos: [], total: 0, limite: 25, desplazamiento: 0, termino_ignorado: false });
    });

    it('ficha de paciente', () => {
        api.paciente('p1').subscribe();
        const peticion = http.expectOne(`${BASE}/pacientes/p1`);
        expect(peticion.request.method).toBe('GET');
        peticion.flush({});
    });
});

describe('AutenticacionService: inicio de sesión', () => {
    let autenticacion: AutenticacionService;
    let sesion: SesionService;
    let http: HttpTestingController;

    beforeEach(() => {
        localStorage.clear();
        TestBed.configureTestingModule({
            providers: [
                provideHttpClient(withXhr()),
                provideHttpClientTesting(),
                { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
            ],
        });
        autenticacion = TestBed.inject(AutenticacionService);
        sesion = TestBed.inject(SesionService);
        http = TestBed.inject(HttpTestingController);
    });

    afterEach(() => http.verify());

    it('guarda los tokens y carga la identidad', () => {
        autenticacion
            .iniciarSesion({
            correo: '  Persona@Example.Invalid ',
            contrasena: 'x',
            recordarCorreo: true,
        })
            .subscribe();

        const acceso = http.expectOne(`${BASE}/autenticacion/sesion`);
        // El correo se envía sin espacios sobrantes: un espacio final al pegarlo
        // desde otro sitio produciría un 401 desconcertante.
        expect((acceso.request.body as {
            correo: string;
        }).correo).toBe('Persona@Example.Invalid');
        acceso.flush(tokens('1'));

        http.expectOne(`${BASE}/autenticacion/yo`).flush({
            usuario_id: 'u',
            correo: 'p@example.invalid',
            nombre: 'A',
            apellido: 'B',
            clinica_id: 'c-1',
            roles: [],
            permisos: [],
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
        });

        expect(sesion.autenticado()).toBe(true);
        expect(sesion.correoRecordado()).toBe('persona@example.invalid');
    });

    it('envía el código de segundo factor solo si lo hay', () => {
        autenticacion
            .iniciarSesion({ correo: 'a@b.invalid', contrasena: 'x', codigo2fa: '  ' })
            .subscribe({ error: () => undefined });

        const peticion = http.expectOne(`${BASE}/autenticacion/sesion`);
        // Un código de solo espacios se envía como null, no como cadena vacía:
        // el backend distingue «no lo mandó» de «mandó algo inválido».
        expect((peticion.request.body as {
            codigo_2fa: string | null;
        }).codigo_2fa).toBeNull();
        peticion.flush({}, { status: 401, statusText: 'x' });
    });
});

describe('AutenticacionService: rotación del token', () => {
    let autenticacion: AutenticacionService;
    let sesion: SesionService;
    let http: HttpTestingController;

    beforeEach(() => {
        localStorage.clear();
        TestBed.configureTestingModule({
            providers: [
                provideHttpClient(withXhr()),
                provideHttpClientTesting(),
                { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
            ],
        });
        autenticacion = TestBed.inject(AutenticacionService);
        sesion = TestBed.inject(SesionService);
        http = TestBed.inject(HttpTestingController);
    });

    afterEach(() => http.verify());

    it('comparte una única rotación entre varias peticiones', () => {
        // Es la prueba que evita el peor fallo de esta capa: sin compartirla,
        // varias peticiones caducadas presentarían el MISMO refresco por
        // separado, y el backend revocaría la familia completa de sesiones por
        // sospecha de robo. Correctamente, porque desde fuera es
        // indistinguible.
        sesion.establecerTokens(tokens('viejo'));

        const resultados: string[] = [];
        autenticacion.rotarToken().subscribe((par) => resultados.push(par.token_acceso));
        autenticacion.rotarToken().subscribe((par) => resultados.push(par.token_acceso));
        autenticacion.rotarToken().subscribe((par) => resultados.push(par.token_acceso));

        // Una sola petición, no tres.
        const peticion = http.expectOne(`${BASE}/autenticacion/refresco`);
        peticion.flush(tokens('nuevo'));

        expect(resultados).toEqual(['acceso-nuevo', 'acceso-nuevo', 'acceso-nuevo']);
        expect(sesion.tokenAcceso()).toBe('acceso-nuevo');
    });

    it('cierra la sesión si la rotación falla', () => {
        // El refresco estaba usado, revocado o caducado: la sesión no se puede
        // recuperar y reintentar solo empeoraría las cosas.
        sesion.establecerTokens(tokens('viejo'));

        let fallo: unknown = null;
        autenticacion.rotarToken().subscribe({ error: (error: unknown) => (fallo = error) });

        http
            .expectOne(`${BASE}/autenticacion/refresco`)
            .flush({ codigo: 'TOKEN_INVALIDO', mensaje: 'La sesion fue revocada.' }, { status: 401, statusText: 'Unauthorized' });

        expect(fallo).toBeInstanceOf(FalloApi);
        expect(sesion.autenticado()).toBe(false);
    });

    it('sin refresco no intenta rotar', async () => {
        autenticacion.rotarToken().subscribe({
            error: (fallo: FalloApi) => {
                expect(fallo.codigo).toBe('NO_AUTENTICADO');
                ;
            },
        });
    });

    it('cerrar sesión limpia el estado aunque el backend falle', () => {
        // Dejar al usuario dentro porque no se pudo avisar al servidor sería lo
        // contrario de lo que pidió; el refresco, sin rotar, caduca solo.
        sesion.establecerTokens(tokens('1'));

        autenticacion.cerrarSesion().subscribe();
        http
            .expectOne(`${BASE}/autenticacion/cierre`)
            .error(new ProgressEvent('error'), { status: 500 });

        expect(sesion.autenticado()).toBe(false);
    });

    it('cerrar sesión sin refresco no llama al backend', () => {
        autenticacion.cerrarSesion().subscribe();
        expect(sesion.autenticado()).toBe(false);
    });
});

describe('Interceptor de token', () => {
    let http: HttpTestingController;
    let cliente: HttpClient;
    let sesion: SesionService;

    beforeEach(async () => {
        localStorage.clear();
        const { tokenInterceptor } = await import('../interceptores/token.interceptor');
        const { withInterceptors } = await import('@angular/common/http');

        TestBed.configureTestingModule({
            providers: [
                provideHttpClient(withXhr(), withInterceptors([tokenInterceptor])),
                provideHttpClientTesting(),
                { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
            ],
        });
        http = TestBed.inject(HttpTestingController);
        cliente = TestBed.inject(HttpClient);
        sesion = TestBed.inject(SesionService);
    });

    afterEach(() => http.verify());

    it('adjunta el token de acceso', () => {
        sesion.establecerTokens(tokens('1'));
        cliente.get(`${BASE}/agenda/citas`).subscribe();

        const peticion = http.expectOne(`${BASE}/agenda/citas`);
        expect(peticion.request.headers.get('Authorization')).toBe('Bearer acceso-1');
        peticion.flush({});
    });

    it('NO adjunta el token a las rutas de autenticación', () => {
        // Sin esta exclusión, un 401 de credenciales incorrectas dispararía una
        // rotación, que fallaría, y el usuario vería «la sesión expiró» en lugar
        // de «contraseña incorrecta».
        sesion.establecerTokens(tokens('1'));
        cliente.post(`${BASE}/autenticacion/sesion`, {}).subscribe();

        const peticion = http.expectOne(`${BASE}/autenticacion/sesion`);
        expect(peticion.request.headers.has('Authorization')).toBe(false);
        peticion.flush({});
    });

    it('rota y reintenta una sola vez ante un 401', () => {
        sesion.establecerTokens(tokens('viejo'));

        let respuesta: unknown = null;
        cliente.get(`${BASE}/agenda/citas`).subscribe((datos) => (respuesta = datos));

        // 1) La petición original recibe 401.
        http
            .expectOne((p) => p.url === `${BASE}/agenda/citas` && p.headers.get('Authorization') === 'Bearer acceso-viejo')
            .flush({ codigo: 'TOKEN_INVALIDO', mensaje: 'caducado' }, { status: 401, statusText: 'x' });

        // 2) Se rota.
        http.expectOne(`${BASE}/autenticacion/refresco`).flush(tokens('nuevo'));

        // 3) Se reintenta con el token nuevo.
        http
            .expectOne((p) => p.url === `${BASE}/agenda/citas` && p.headers.get('Authorization') === 'Bearer acceso-nuevo')
            .flush({ ok: true });

        expect(respuesta).toEqual({ ok: true } as never);
    });

    it('sin sesión no intenta rotar ante un 401', () => {
        let fallo: unknown = null;
        cliente.get(`${BASE}/agenda/citas`).subscribe({ error: (error: unknown) => (fallo = error) });

        http.expectOne(`${BASE}/agenda/citas`).flush({}, { status: 401, statusText: 'x' });

        expect(fallo).toBeTruthy();
        // Ninguna petición de rotación: `http.verify()` lo confirma.
    });
});
