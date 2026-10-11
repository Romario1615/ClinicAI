/**
 * Pruebas del armazon.
 *
 * Lo que se comprueba no es cosmetico: **que la navegacion refleje los
 * permisos**. Un enlace visible a una seccion a la que el backend va a
 * responder 403 en cada llamada no es un fallo de seguridad -- el backend
 * revalida siempre --, pero si una interfaz que miente sobre lo que se puede
 * hacer.
 */
import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, computed, signal, type WritableSignal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { AppComponent } from './app.component';
import { AutenticacionService } from './nucleo/servicios/autenticacion.service';
import { CONFIGURACION, CONFIGURACION_POR_DEFECTO, PERMISOS } from './nucleo/servicios/configuracion';
import { SesionService } from './nucleo/servicios/sesion.service';
import { PendientesService } from './nucleo/servicios/pendientes.service';
import type { Identidad } from './nucleo/modelos/dominio';
import { of } from 'rxjs';

function identidadCon(permisos: readonly string[]): Identidad {
    return {
        usuario_id: 'u-1',
        correo: 'prueba@example.invalid',
        nombre: 'Persona',
        apellido: 'De Prueba',
        clinica_id: 'c-1',
        roles: ['recepcion'],
        permisos,
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

@Component({ template: '' })
class PaginaPruebaComponent {}

describe('AppComponent', () => {
    let fixture: ComponentFixture<AppComponent>;
    let sesion: SesionService;
    let cantidadAvisosTratamiento: WritableSignal<number>;
    let cantidadCobrosVencidos: WritableSignal<number>;
    let cargandoAvisos: WritableSignal<boolean>;

    beforeEach(async () => {
        const tareas = signal<readonly never[]>([]);
        const alertas = signal<readonly never[]>([]);
        const conversaciones = signal(0);
        const avisosEmergencia = signal(0);
        cantidadAvisosTratamiento = signal(0);
        cantidadCobrosVencidos = signal(0);
        cargandoAvisos = signal(false);
        const cuenta = computed(() => tareas().length);
        const notificaciones = computed(() => cuenta() + alertas().length + conversaciones() + cantidadAvisosTratamiento() + avisosEmergencia() + cantidadCobrosVencidos());
        const pendientesFalsos = {
            cargar: vi.fn().mockName('cargar'),
            limpiar: vi.fn().mockName('limpiar'),
            refrescarCobrosVencidos: vi.fn().mockName('refrescarCobrosVencidos'),
            refrescarOfertasSinAvisar: vi.fn().mockName('refrescarOfertasSinAvisar'),
            tareas,
            alertasAbiertas: alertas,
            conversacionesPendientes: conversaciones,
            avisosTratamientoPendientes: cantidadAvisosTratamiento,
            avisosEmergenciaPendientes: avisosEmergencia,
            cargosVencidosPendientes: cantidadCobrosVencidos,
            cargando: cargandoAvisos,
            cuenta,
            notificaciones,
        } as unknown as PendientesService;
        await TestBed.configureTestingModule({
            imports: [AppComponent],
            providers: [
                provideRouter([]),
                provideHttpClient(withXhr()),
                provideHttpClientTesting(),
                { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
                { provide: PendientesService, useValue: pendientesFalsos },
            ],
        }).compileComponents();

        fixture = TestBed.createComponent(AppComponent);
        sesion = TestBed.inject(SesionService);
    });

    it('sin sesion no muestra la navegacion', () => {
        fixture.detectChanges();
        const nav = fixture.nativeElement.querySelector('nav');
        expect(nav).toBeNull();
    });

    it('muestra la especialidad del profesional en la cabecera y en Mi perfil', () => {
        sesion.establecerTokens({ token_acceso: 't', token_refresco: 'r', tipo_token: 'Bearer', expira_en: new Date().toISOString(), requiere_segundo_factor: false });
        sesion.establecerIdentidad({ ...identidadCon([]), roles: ['profesional'], especialidad: 'Dermatología' });
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('.cabecera__especialidad').textContent).toBe('Especialidad: Dermatología');
        (fixture.componentInstance as unknown as { miFotoAbierta: WritableSignal<boolean> }).miFotoAbierta.set(true);
        fixture.detectChanges();
        expect(document.body.textContent).toContain('Especialidad: Dermatología');
    });

    it('con sesion muestra el nombre del usuario', () => {
        sesion.establecerTokens({
            token_acceso: 't',
            token_refresco: 'r',
            tipo_token: 'Bearer',
            expira_en: new Date().toISOString(),
            requiere_segundo_factor: false,
        });
        sesion.establecerIdentidad(identidadCon(['agenda.leer']));
        fixture.detectChanges();

        const texto = fixture.nativeElement.textContent as string;
        expect(texto).toContain('Persona De Prueba');
    });

    it('oculta los enlaces cuyos permisos faltan', () => {
        sesion.establecerTokens({
            token_acceso: 't',
            token_refresco: 'r',
            tipo_token: 'Bearer',
            expira_en: new Date().toISOString(),
            requiere_segundo_factor: false,
        });
        // Sin `paciente.leer_administrativo` ni `historia_clinica.leer`.
        sesion.establecerIdentidad(identidadCon(['agenda.leer']));
        fixture.detectChanges();

        const enlaces = Array.from(fixture.nativeElement.querySelectorAll('nav a')).map((enlace) => (enlace as HTMLElement).textContent?.trim() ?? '');

        expect(enlaces.some((texto) => texto.includes('Agenda'))).toBe(true);
        expect(enlaces.some((texto) => texto.includes('Pacientes'))).toBe(false);
        expect(enlaces.some((texto) => texto.includes('Historia'))).toBe(false);
    });

    function iniciar(permisos: readonly string[]): void {
        sesion.establecerTokens({
            token_acceso: 't', token_refresco: 'r', tipo_token: 'Bearer',
            expira_en: new Date().toISOString(), requiere_segundo_factor: false,
        });
        sesion.establecerIdentidad(identidadCon(permisos));
        fixture.detectChanges();
    }

    function abrirBuscador(): HTMLElement {
        const boton = fixture.nativeElement.querySelector('#buscar-seccion') as HTMLButtonElement;
        boton.focus();
        boton.click();
        fixture.detectChanges();
        return fixture.nativeElement.querySelector('dialog') as HTMLElement;
    }

    function buscar(texto: string): void {
        const consulta = fixture.nativeElement.querySelector('#consulta-secciones') as HTMLInputElement;
        consulta.value = texto;
        consulta.dispatchEvent(new Event('input', { bubbles: true }));
        fixture.detectChanges();
    }

    it('el buscador muestra exactamente los enlaces autorizados, incluidos Ayuda y el simulador local', () => {
        TestBed.inject(HttpTestingController).expectOne(`${CONFIGURACION_POR_DEFECTO.urlApi}/autenticacion/accesos-locales`)
            .flush({ habilitado: true, roles: [] });
        const permisos = [...Object.values(PERMISOS), 'pago.leer'];
        iniciar(permisos);
        sesion.establecerIdentidad({ ...identidadCon(permisos), roles: ['superadministrador'] });
        fixture.detectChanges();
        const destinos = [...fixture.nativeElement.querySelectorAll('nav a')].map((a) => (a as HTMLAnchorElement).getAttribute('href'));
        const modal = abrirBuscador();
        const resultados = [...modal.querySelectorAll('.secciones-resultados a')].map((a) => a.getAttribute('href'));
        expect(resultados.sort()).toEqual(destinos.sort());
        expect(resultados).toHaveLength(23);
        expect(modal.querySelector('#resumen-secciones')?.textContent).toContain('23 secciones disponibles');
        expect(modal.querySelector('.secciones-resultados__demo')).not.toBeNull();
    });

    it('buscar no revela secciones sin permiso ni el simulador cuando la API no confirma local', () => {
        iniciar(['agenda.leer', PERMISOS.conversacionResponder]);
        const modal = abrirBuscador();
        expect(modal.querySelector('a[href="/agenda"]')).not.toBeNull();
        for (const ruta of ['/pacientes', '/usuarios', '/plataforma/clinicas', '/agente-demo']) {
            expect(modal.querySelector(`a[href="${ruta}"]`)).toBeNull();
        }
    });

    it('busca por nombre y categoría sin depender de tildes, mayúsculas u orden de palabras', () => {
        iniciar([PERMISOS.metricasLeer, PERMISOS.historiaLeer, 'pago.leer']);
        const modal = abrirBuscador();
        buscar('  IA ANALITICA  ');
        expect(modal.querySelectorAll('.secciones-resultados a')).toHaveLength(1);
        expect(modal.querySelector('.secciones-resultados a')?.getAttribute('href')).toBe('/analitica');
        buscar('finanzas');
        expect(modal.querySelector('.secciones-resultados a')?.getAttribute('href')).toBe('/pagos');
        buscar('clinica historia');
        expect(modal.querySelector('.secciones-resultados a')?.getAttribute('href')).toBe('/historia-clinica');
        buscar('sin coincidencia');
        expect(modal.querySelectorAll('.secciones-resultados a')).toHaveLength(0);
        expect(modal.textContent).toContain('No se encontraron secciones');
        buscar('ayuda');
        expect(modal.querySelector('#resumen-secciones')?.textContent).toContain('1 sección disponible');
    });

    it('al abrir enfoca la consulta y cerrar devuelve el foco al buscador sin conservar el texto', async () => {
        iniciar(['agenda.leer']);
        const modal = abrirBuscador();
        await fixture.whenStable();
        expect(document.activeElement?.id).toBe('consulta-secciones');
        buscar('agenda');
        modal.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        await fixture.whenStable();
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('dialog')).toBeNull();
        expect(document.activeElement?.id).toBe('buscar-seccion');
        abrirBuscador();
        expect((fixture.nativeElement.querySelector('#consulta-secciones') as HTMLInputElement).value).toBe('');
    });

    it('la búsqueda conserva el cajón al pulsar dentro y Escape cierra solo la ventana', () => {
        iniciar(['agenda.leer']);
        (fixture.nativeElement.querySelector('.cabecera__menu') as HTMLButtonElement).click();
        fixture.detectChanges();
        const modal = abrirBuscador();
        (modal.querySelector('input') as HTMLInputElement).click();
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('.navegacion--abierta')).not.toBeNull();
        modal.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('.navegacion--abierta')).not.toBeNull();
    });

    it('elegir una sección abre su ruta, cierra las capas y enfoca el contenido', async () => {
        const router = TestBed.inject(Router);
        router.resetConfig([{ path: 'agenda', component: PaginaPruebaComponent }]);
        iniciar(['agenda.leer']);
        // El cambio de ruta y el cierre se producen tras resolver la promesa;
        // el foco se comprueba con el render automático que usa la aplicación.
        fixture.autoDetectChanges();
        const modal = abrirBuscador();
        (modal.querySelector('a[href="/agenda"]') as HTMLAnchorElement).click();
        await fixture.whenStable();
        fixture.detectChanges();
        expect(router.url).toBe('/agenda');
        expect(fixture.nativeElement.querySelector('dialog')).toBeNull();
        expect(document.activeElement?.id).toBe('contenido');
        // Una navegación a la misma dirección se omite, pero la elección sigue funcionando.
        const siguiente = abrirBuscador();
        (siguiente.querySelector('a[href="/agenda"]') as HTMLAnchorElement).click();
        await fixture.whenStable();
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('dialog')).toBeNull();
        expect(document.activeElement?.id).toBe('contenido');
    });

    it('un rechazo o error de navegación se explica en la ventana y permite repetir la elección', async () => {
        iniciar(['agenda.leer']);
        const router = TestBed.inject(Router);
        const navegar = vi.spyOn(router, 'navigateByUrl').mockResolvedValueOnce(false).mockRejectedValueOnce(new Error('fallo sintético'));
        const modal = abrirBuscador();
        const enlace = modal.querySelector('a[href="/agenda"]') as HTMLAnchorElement;
        enlace.click();
        await fixture.whenStable();
        fixture.detectChanges();
        expect(modal.querySelector('[role="alert"]')?.textContent).toContain('No se pudo abrir la sección');
        expect(modal.querySelector('input')?.disabled).toBe(false);
        enlace.click();
        await fixture.whenStable();
        fixture.detectChanges();
        expect(navegar).toHaveBeenCalledTimes(2);
        expect(modal.querySelector('[role="alert"]')?.textContent).toContain('Vuelva a intentarlo');
    });

    it('no duplica la navegación y descarta su resultado si cambia la identidad', async () => {
        iniciar(['agenda.leer']);
        let resolver!: (abierta: boolean) => void;
        const navegar = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockReturnValue(new Promise<boolean>((resolucion) => { resolver = resolucion; }));
        const modal = abrirBuscador();
        const enlace = modal.querySelector('a[href="/agenda"]') as HTMLAnchorElement;
        enlace.click();
        enlace.click();
        fixture.detectChanges();
        expect(navegar).toHaveBeenCalledTimes(1);
        expect(modal.querySelector('input')?.disabled).toBe(true);
        sesion.establecerIdentidad({ ...identidadCon([]), usuario_id: 'otra-persona-sintetica' });
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('dialog')).toBeNull();
        resolver(false);
        await fixture.whenStable();
        fixture.detectChanges();
        abrirBuscador();
        expect(fixture.nativeElement.querySelector('[role="alert"]')).toBeNull();
        expect(fixture.nativeElement.querySelector('.secciones-resultados a[href="/agenda"]')).toBeNull();
    });

    it('un cambio de parámetros también revela la categoría del destino', async () => {
        const router = TestBed.inject(Router);
        router.resetConfig([{ path: 'pagos', component: PaginaPruebaComponent }]);
        iniciar(['agenda.leer', 'pago.leer']);
        await router.navigateByUrl('/pagos?paciente=uno');
        fixture.detectChanges();
        (fixture.nativeElement.querySelector('#categoria-clinica') as HTMLButtonElement).click();
        fixture.detectChanges();
        await router.navigateByUrl('/pagos?paciente=dos');
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('#categoria-finanzas').getAttribute('aria-expanded')).toBe('true');
    });

    it('mantiene los gestos de nueva pestaña y rechaza destinos fuera de los enlaces autorizados', async () => {
        iniciar(['agenda.leer']);
        abrirBuscador();
        const navegar = vi.spyOn(TestBed.inject(Router), 'navigateByUrl');
        const vm = fixture.componentInstance as unknown as { elegirSeccion(evento: MouseEvent, ruta: string): Promise<void> };
        const nuevaPestana = new MouseEvent('click', { ctrlKey: true, cancelable: true });
        await vm.elegirSeccion(nuevaPestana, '/agenda');
        expect(nuevaPestana.defaultPrevented).toBe(false);
        const ajeno = new MouseEvent('click', { cancelable: true });
        await vm.elegirSeccion(ajeno, '/usuarios');
        expect(ajeno.defaultPrevented).toBe(true);
        expect(navegar).not.toHaveBeenCalled();
    });

    it('un enlace móvil a la ruta actual cierra el cajón y enfoca el contenido aunque se omita la navegación', async () => {
        const router = TestBed.inject(Router);
        router.resetConfig([{ path: 'agenda', component: PaginaPruebaComponent }]);
        iniciar(['agenda.leer']);
        fixture.autoDetectChanges();
        const vm = fixture.componentInstance as unknown as { pantallaEstrecha: WritableSignal<boolean> };
        vm.pantallaEstrecha.set(true);
        await router.navigateByUrl('/agenda');
        await fixture.whenStable();
        const raiz = fixture.nativeElement as HTMLElement;
        const boton = raiz.querySelector('.cabecera__menu') as HTMLButtonElement;
        boton.style.display = 'inline-flex';
        boton.click();
        await fixture.whenStable();
        const enlace = raiz.querySelector('nav a[href="/agenda"]') as HTMLAnchorElement;
        enlace.focus();
        enlace.click();
        await fixture.whenStable();
        expect(raiz.querySelector('.navegacion--abierta')).toBeNull();
        expect(raiz.querySelector('#contenido')?.hasAttribute('inert')).toBe(false);
        expect(document.activeElement?.id).toBe('contenido');
    });

    it('sin permisos adicionales solo ofrece Resumen y Ayuda, sin categorías vacías', () => {
        iniciar([]);
        const botones = fixture.nativeElement.querySelectorAll('.navegacion__desplegar') as NodeListOf<HTMLButtonElement>;
        expect([...botones].map((boton) => boton.textContent?.trim())).toEqual(['Resumen']);
        expect(botones[0].getAttribute('aria-expanded')).toBe('true');
        expect(fixture.nativeElement.querySelector('.navegacion__ayuda').getAttribute('href')).toBe('/ayuda');
    });

    it('abre una sola categoría y permite cerrarla sin perder sus enlaces autorizados', () => {
        iniciar(['agenda.leer', 'pago.leer']);
        const raiz = fixture.nativeElement as HTMLElement;
        const clinica = raiz.querySelector<HTMLButtonElement>('#categoria-clinica')!;
        const finanzas = raiz.querySelector<HTMLButtonElement>('#categoria-finanzas')!;
        clinica.click();
        fixture.detectChanges();
        expect(raiz.querySelector('#categoria-resumen')?.getAttribute('aria-expanded')).toBe('false');
        expect(clinica.getAttribute('aria-expanded')).toBe('true');
        expect(raiz.querySelector('#secciones-clinica')?.hasAttribute('hidden')).toBe(false);
        expect(clinica.getAttribute('aria-controls')).toBe('secciones-clinica');
        expect(raiz.querySelector('#secciones-clinica')?.getAttribute('aria-labelledby')).toBe('categoria-clinica');
        finanzas.click();
        fixture.detectChanges();
        expect(clinica.getAttribute('aria-expanded')).toBe('false');
        expect(raiz.querySelector('#secciones-clinica')?.hasAttribute('hidden')).toBe(true);
        expect(raiz.querySelector('#secciones-clinica a[href="/agenda"]')).not.toBeNull();
        finanzas.click();
        fixture.detectChanges();
        expect(raiz.querySelectorAll('.navegacion__desplegar[aria-expanded="true"]')).toHaveLength(0);
        expect(raiz.querySelector('.navegacion__ayuda')?.closest('[hidden]')).toBeNull();
    });

    it('cada sección autorizada pertenece a una sola categoría o al acceso de Ayuda', () => {
        TestBed.inject(HttpTestingController).expectOne(`${CONFIGURACION_POR_DEFECTO.urlApi}/autenticacion/accesos-locales`)
            .flush({ habilitado: true, roles: [] });
        const permisos = [...Object.values(PERMISOS), 'pago.leer'];
        iniciar(permisos);
        sesion.establecerIdentidad({ ...identidadCon(permisos), roles: ['superadministrador'] });
        fixture.detectChanges();
        const raiz = fixture.nativeElement as HTMLElement;
        const enlaces = [...raiz.querySelectorAll('nav a')].map((enlace) => enlace.getAttribute('href'));
        expect(enlaces).toHaveLength(23);
        expect(new Set(enlaces).size).toBe(enlaces.length);
        expect(raiz.querySelectorAll('.navegacion__categoria')).toHaveLength(5);
        expect(raiz.querySelector('#secciones-administracion a[href="/plataforma/clinicas"]')).not.toBeNull();
        expect(raiz.querySelector('#secciones-ia a[href="/agente-demo"]')).not.toBeNull();
        expect(raiz.querySelector('#secciones-clinica a[href="/historia-clinica"]')).not.toBeNull();
    });

    it('un acceso directo con parámetros y una ruta anidada revelan la categoría actual', async () => {
        const router = TestBed.inject(Router);
        router.resetConfig([
            { path: 'pagos', component: PaginaPruebaComponent },
            { path: 'pacientes/:id', component: PaginaPruebaComponent },
        ]);
        iniciar(['agenda.leer', 'pago.leer', PERMISOS.pacienteLeer]);
        await router.navigateByUrl('/pagos?paciente=prueba#detalle');
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('#categoria-finanzas').getAttribute('aria-expanded')).toBe('true');
        expect(fixture.nativeElement.querySelector('#categoria-finanzas').textContent).toContain('Contiene la sección actual');
        await router.navigateByUrl('/pacientes/paciente-sintetico');
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('#categoria-clinica').getAttribute('aria-expanded')).toBe('true');
        expect(fixture.nativeElement.querySelector('#categoria-finanzas').getAttribute('aria-expanded')).toBe('false');
    });

    it('no confunde una ruta de nombre parecido con una sección del menú', async () => {
        const router = TestBed.inject(Router);
        router.resetConfig([{ path: 'pagos-externos', component: PaginaPruebaComponent }]);
        iniciar(['pago.leer']);
        await router.navigateByUrl('/pagos-externos');
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('.navegacion__categoria--actual')).toBeNull();
        expect(fixture.nativeElement.querySelector('#categoria-resumen').getAttribute('aria-expanded')).toBe('true');
    });

    it('Ayuda sigue accesible con todas las categorías cerradas y cierra el cajón', async () => {
        const router = TestBed.inject(Router);
        router.resetConfig([{ path: 'ayuda', component: PaginaPruebaComponent }]);
        iniciar(['agenda.leer']);
        (fixture.nativeElement.querySelector('.cabecera__menu') as HTMLButtonElement).click();
        fixture.detectChanges();
        (fixture.nativeElement.querySelector('.navegacion__ayuda') as HTMLAnchorElement).click();
        await fixture.whenStable();
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('.navegacion--abierta')).toBeNull();
        expect(fixture.nativeElement.querySelectorAll('.navegacion__desplegar[aria-expanded="true"]')).toHaveLength(0);
        expect(fixture.nativeElement.querySelector('.navegacion__ayuda').getAttribute('aria-current')).toBe('page');
    });

    it('al cambiar los permisos desaparece la categoría que ya no corresponde y se restablece la apertura', () => {
        iniciar(['pago.leer']);
        (fixture.nativeElement.querySelector('#categoria-finanzas') as HTMLButtonElement).click();
        fixture.detectChanges();
        sesion.establecerIdentidad(identidadCon([]));
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('#categoria-finanzas')).toBeNull();
        expect(fixture.nativeElement.querySelector('nav a[href="/pagos"]')).toBeNull();
        expect(fixture.nativeElement.querySelector('#categoria-resumen').getAttribute('aria-expanded')).toBe('true');
    });

    it('los pendientes de enlaces autorizados se ven en su categoría cerrada y se actualizan sin abrirla', () => {
        iniciar([PERMISOS.conversacionLeer]);
        const conversaciones = TestBed.inject(PendientesService).conversacionesPendientes as WritableSignal<number>;
        const emergencias = TestBed.inject(PendientesService).avisosEmergenciaPendientes as WritableSignal<number>;
        conversaciones.set(3);
        emergencias.set(8);
        fixture.detectChanges();
        const raiz = fixture.nativeElement as HTMLElement;
        const categoria = raiz.querySelector('#categoria-ia')!;
        expect(categoria.querySelector('.navegacion__pendientes')?.textContent?.trim()).toBe('3');
        expect(categoria.getAttribute('aria-expanded')).toBe('false');
        expect(raiz.querySelector('#categoria-administracion')).toBeNull();
        conversaciones.set(0);
        fixture.detectChanges();
        expect(categoria.querySelector('.navegacion__pendientes')).toBeNull();
        expect(categoria.getAttribute('aria-expanded')).toBe('false');
    });

    it('no anuncia como demostracion ninguna seccion que ya usa datos reales', () => {
        sesion.establecerTokens({
            token_acceso: 't',
            token_refresco: 'r',
            tipo_token: 'Bearer',
            expira_en: new Date().toISOString(),
            requiere_segundo_factor: false,
        });
        sesion.establecerIdentidad(identidadCon(['agenda.leer']));
        fixture.detectChanges();

        // Todas las secciones de la navegacion estan conectadas al backend, asi
        // que no debe aparecer ninguna marca. La comprobacion no es trivial: una
        // marca olvidada en una pantalla ya real le dice a quien atiende que los
        // datos que ve son inventados, y dejaria de fiarse de ellos.
        //
        // El mecanismo de la marca sigue en la plantilla a proposito: la Fase 8 y
        // la 9 traeran pantallas nuevas, y algunas naceran con datos sinteticos.
        const marcas = fixture.nativeElement.querySelectorAll('.navegacion__demo');
        expect(marcas.length).toBe(0);
    });

    it('ofrece la gestión del equipo al rol autorizado y cierra la sesión desde el armazón', () => {
        sesion.establecerTokens({
            token_acceso: 't', token_refresco: 'r', tipo_token: 'Bearer',
            expira_en: new Date().toISOString(), requiere_segundo_factor: false,
        });
        sesion.establecerIdentidad(identidadCon(['profesional.gestionar']));
        fixture.detectChanges();
        const enlaces = Array.from(fixture.nativeElement.querySelectorAll('nav a')) as HTMLAnchorElement[];
        expect(enlaces.some((enlace) => enlace.getAttribute('href') === '/equipo')).toBe(true);

        const vm = fixture.componentInstance as unknown as {
            alternarMenu(): void;
            alternarNotificaciones(): void;
            cerrarMenu(): void;
            cerrarNotificaciones(): void;
            cerrarSesion(): void;
            menuAbierto(): boolean;
            notificacionesAbiertas(): boolean;
        };
        vm.alternarMenu();
        expect(vm.menuAbierto()).toBe(true);
        vm.alternarMenu();
        expect(vm.menuAbierto()).toBe(false);
        vm.alternarNotificaciones();
        expect(vm.notificacionesAbiertas()).toBe(true);
        vm.cerrarNotificaciones();
        expect(vm.notificacionesAbiertas()).toBe(false);
        vm.alternarMenu();
        vm.cerrarMenu();
        expect(vm.menuAbierto()).toBe(false);

        vi.spyOn(TestBed.inject(AutenticacionService), 'cerrarSesion').mockReturnValue(of(void 0));
        const router = TestBed.inject(Router);
        vi.spyOn(router, 'navigate').mockResolvedValue(true);
        vm.cerrarSesion();
        expect(router.navigate).toHaveBeenCalledWith(['/acceso']);
    });

    it('anuncia el panel de notificaciones y lo cierra con Escape o al pulsar fuera', () => {
        sesion.establecerTokens({
            token_acceso: 't', token_refresco: 'r', tipo_token: 'Bearer',
            expira_en: new Date().toISOString(), requiere_segundo_factor: false,
        });
        sesion.establecerIdentidad(identidadCon(['agenda.leer']));
        fixture.detectChanges();

        const boton = fixture.nativeElement.querySelector('.campana') as HTMLButtonElement;
        expect(boton.getAttribute('aria-controls')).toBe('panel-notificaciones');
        expect(boton.getAttribute('aria-haspopup')).toBe('dialog');
        boton.click();
        fixture.detectChanges();
        const panel = fixture.nativeElement.querySelector('#panel-notificaciones') as HTMLElement;
        expect(panel.getAttribute('role')).toBe('dialog');
        expect(panel.getAttribute('aria-modal')).toBe('false');

        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('#panel-notificaciones')).toBeNull();

        boton.click();
        fixture.detectChanges();
        document.body.dispatchEvent(new MouseEvent('click', { bubbles: true }));
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('#panel-notificaciones')).toBeNull();
    });

    it('al cerrar los avisos con Escape devuelve el foco a la campana', () => {
        sesion.establecerTokens({
            token_acceso: 't', token_refresco: 'r', tipo_token: 'Bearer',
            expira_en: new Date().toISOString(), requiere_segundo_factor: false,
        });
        sesion.establecerIdentidad(identidadCon(['agenda.leer']));
        fixture.detectChanges();

        const campana = fixture.nativeElement.querySelector('.campana') as HTMLButtonElement;
        campana.click();
        fixture.detectChanges();
        (fixture.nativeElement.querySelector('#panel-notificaciones a') as HTMLElement).focus();

        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        fixture.detectChanges();

        expect(fixture.nativeElement.querySelector('#panel-notificaciones')).toBeNull();
        expect(document.activeElement).toBe(campana);
    });

    it('el cierre de notificaciones devuelve el foco sin cambiar de sección', () => {
        iniciar(['agenda.leer']);
        const campana = fixture.nativeElement.querySelector('.campana') as HTMLButtonElement;
        const router = TestBed.inject(Router);
        vi.spyOn(router, 'navigate').mockResolvedValue(true);
        campana.click();
        fixture.detectChanges();
        const cerrar = fixture.nativeElement.querySelector('[aria-label="Cerrar notificaciones"]') as HTMLButtonElement;
        cerrar.focus();
        cerrar.click();
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('#panel-notificaciones')).toBeNull();
        expect(campana.getAttribute('aria-expanded')).toBe('false');
        expect(document.activeElement).toBe(campana);
        expect(router.navigate).not.toHaveBeenCalled();
    });

    it('la lista de avisos mantiene cabecera y enlace final fuera del marco desplazable', () => {
        iniciar(['pago.leer']);
        cantidadCobrosVencidos.set(4);
        (fixture.nativeElement.querySelector('.campana') as HTMLButtonElement).click();
        fixture.detectChanges();
        const panel = fixture.nativeElement.querySelector('#panel-notificaciones') as HTMLElement;
        const contenido = panel.querySelector('.notificaciones__contenido')!;
        expect(contenido.querySelector('.notificaciones__item')?.textContent).toContain('4 cargo(s)');
        expect(contenido.querySelector('header')).toBeNull();
        expect(contenido.querySelector('.notificaciones__todo')).toBeNull();
        expect(panel.querySelector('.notificaciones__todo')?.getAttribute('href')).toBe('/panel');
    });

    it('durante la carga conserva el cierre y no anuncia un vacío definitivo', () => {
        iniciar(['agenda.leer']);
        cargandoAvisos.set(true);
        (fixture.nativeElement.querySelector('.campana') as HTMLButtonElement).click();
        fixture.detectChanges();
        const panel = fixture.nativeElement.querySelector('#panel-notificaciones') as HTMLElement;
        expect(panel.textContent).toContain('Actualizando avisos…');
        expect(panel.textContent).not.toContain('Todo al día');
        expect(panel.querySelector('[aria-label="Cerrar notificaciones"]')).not.toBeNull();
        cargandoAvisos.set(false);
        fixture.detectChanges();
        expect(panel.textContent).toContain('Todo al día');
    });

    it('la insignia compacta conserva el total de avisos en la descripción accesible', () => {
        iniciar(['pago.leer']);
        cantidadCobrosVencidos.set(12345);
        fixture.detectChanges();
        const campana = fixture.nativeElement.querySelector('.campana') as HTMLButtonElement;
        const cuenta = fixture.nativeElement.querySelector('#cuenta-notificaciones') as HTMLElement;
        expect(campana.getAttribute('aria-describedby')).toBe(cuenta.id);
        expect(cuenta.textContent).toBe('99+');
        expect(cuenta.getAttribute('aria-label')).toBe('12345 avisos pendientes');
        campana.click();
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('#panel-notificaciones header span').textContent).toBe('12345');
        cantidadCobrosVencidos.set(0);
        fixture.detectChanges();
        expect(campana.getAttribute('aria-describedby')).toBeNull();
    });

    it('en pantalla estrecha el cajón deja inerte el contenido y Escape devuelve el foco al botón', () => {
        const original = window.matchMedia;
        window.matchMedia = ((consulta: string) => ({
            matches: consulta === '(max-width: 820px)',
            media: consulta,
            addEventListener: () => undefined,
            removeEventListener: () => undefined,
        })) as unknown as typeof window.matchMedia;
        try {
            const estrecho = TestBed.createComponent(AppComponent);
            sesion.establecerTokens({
                token_acceso: 't', token_refresco: 'r', tipo_token: 'Bearer',
                expira_en: new Date().toISOString(), requiere_segundo_factor: false,
            });
            sesion.establecerIdentidad(identidadCon(['agenda.leer']));
            estrecho.detectChanges();
            const raiz = estrecho.nativeElement as HTMLElement;
            const main = raiz.querySelector('main#contenido')!;
            expect(main.hasAttribute('inert')).toBe(false);

            const botonMenu = raiz.querySelector('.cabecera__menu') as HTMLButtonElement;
            // jsdom no evalúa las consultas de medios: el botón del cajón, oculto
            // en escritorio, se muestra a mano como lo haría la hoja de estilos.
            botonMenu.style.display = 'inline-flex';
            botonMenu.click();
            estrecho.detectChanges();
            expect(main.hasAttribute('inert')).toBe(true);

            (raiz.querySelector('#navegacion-principal a') as HTMLElement).focus();
            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
            estrecho.detectChanges();
            expect(main.hasAttribute('inert')).toBe(false);
            expect(document.activeElement).toBe(botonMenu);
            estrecho.destroy();
        } finally {
            window.matchMedia = original;
        }
    });

    it('despliega la navegación móvil con estado accesible y se cierra desde el fondo', () => {
        sesion.establecerTokens({
            token_acceso: 't', token_refresco: 'r', tipo_token: 'Bearer',
            expira_en: new Date().toISOString(), requiere_segundo_factor: false,
        });
        sesion.establecerIdentidad(identidadCon(['agenda.leer']));
        fixture.detectChanges();

        const boton = fixture.nativeElement.querySelector('.cabecera__menu') as HTMLButtonElement;
        expect(boton.getAttribute('aria-controls')).toBe('navegacion-principal');
        boton.click();
        fixture.detectChanges();
        expect(boton.getAttribute('aria-expanded')).toBe('true');
        expect(fixture.nativeElement.querySelector('.navegacion--abierta')).not.toBeNull();

        (fixture.nativeElement.querySelector('.navegacion__fondo') as HTMLButtonElement).click();
        fixture.detectChanges();
        expect(boton.getAttribute('aria-expanded')).toBe('false');
        expect(fixture.nativeElement.querySelector('.navegacion--abierta')).toBeNull();

        boton.click();
        fixture.detectChanges();
        (fixture.nativeElement.querySelector('.campana') as HTMLButtonElement).click();
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('.navegacion--abierta')).toBeNull();
        expect(fixture.nativeElement.querySelector('#panel-notificaciones')).not.toBeNull();
    });

    it('no anuncia que todo está al día si queda un reporte clínico por revisar', () => {
        sesion.establecerTokens({
            token_acceso: 't', token_refresco: 'r', tipo_token: 'Bearer',
            expira_en: new Date().toISOString(), requiere_segundo_factor: false,
        });
        sesion.establecerIdentidad(identidadCon(['agenda.leer']));
        cantidadAvisosTratamiento.set(1);
        fixture.detectChanges();

        const vm = fixture.componentInstance as unknown as {
            alternarNotificaciones(): void;
        };
        vm.alternarNotificaciones();
        fixture.detectChanges();

        expect(fixture.nativeElement.textContent).toContain('1 reporte(s) de tratamiento pendiente(s)');
        expect(fixture.nativeElement.querySelector('.notificaciones__vacio')).toBeNull();

        cantidadAvisosTratamiento.set(0);
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('.notificaciones__vacio')).not.toBeNull();
    });

    it('muestra los cobros vencidos y permite abrir Pagos desde la campana', () => {
        sesion.establecerTokens({
            token_acceso: 't', token_refresco: 'r', tipo_token: 'Bearer',
            expira_en: new Date().toISOString(), requiere_segundo_factor: false,
        });
        sesion.establecerIdentidad(identidadCon(['pago.leer']));
        cantidadCobrosVencidos.set(2);
        fixture.detectChanges();

        const vm = fixture.componentInstance as unknown as {
            alternarNotificaciones(): void;
        };
        vm.alternarNotificaciones();
        fixture.detectChanges();

        const aviso = Array.from(fixture.nativeElement.querySelectorAll('.notificaciones__item'))
            .find((elemento) => (elemento as HTMLElement).textContent?.includes('cargo(s) con saldo vencido')) as HTMLAnchorElement | undefined;
        expect(aviso?.textContent).toContain('2 cargo(s) con saldo vencido');
        expect(aviso?.getAttribute('href')).toBe('/pagos');
    });

    it('ofrece el simulador local con el permiso correcto solo cuando la API declara modo local', () => {
        const http = TestBed.inject(HttpTestingController);
        const entorno = http.expectOne(`${CONFIGURACION_POR_DEFECTO.urlApi}/autenticacion/accesos-locales`);
        entorno.flush({ habilitado: true, roles: [] });
        sesion.establecerTokens({
            token_acceso: 't', token_refresco: 'r', tipo_token: 'Bearer',
            expira_en: new Date().toISOString(), requiere_segundo_factor: false,
        });
        sesion.establecerIdentidad(identidadCon(['conversacion.responder']));
        fixture.detectChanges();

        const enlace = fixture.nativeElement.querySelector('a[href="/agente-demo"]') as HTMLAnchorElement | null;
        expect(enlace).not.toBeNull();

        const guardia = TestBed.inject(HttpTestingController);
        // La foto de la cabecera tiene su propia prueba.
        guardia.match((p) => p.url.endsWith('/foto')).forEach((p) => p.flush(null, { status: 204, statusText: 'No Content' }));
        guardia.verify();
    });
});
