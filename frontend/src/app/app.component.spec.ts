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
import { computed, signal, type WritableSignal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { AppComponent } from './app.component';
import { AutenticacionService } from './nucleo/servicios/autenticacion.service';
import { CONFIGURACION, CONFIGURACION_POR_DEFECTO, } from './nucleo/servicios/configuracion';
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

describe('AppComponent', () => {
    let fixture: ComponentFixture<AppComponent>;
    let sesion: SesionService;
    let cantidadAvisosTratamiento: WritableSignal<number>;
    let cantidadCobrosVencidos: WritableSignal<number>;

    beforeEach(async () => {
        const tareas = signal<readonly never[]>([]);
        const alertas = signal<readonly never[]>([]);
        const conversaciones = signal(0);
        const avisosEmergencia = signal(0);
        cantidadAvisosTratamiento = signal(0);
        cantidadCobrosVencidos = signal(0);
        const cargando = signal(false);
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
            cargando,
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
