import type { MockedObject } from "vitest";
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withXhr } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { CONFIGURACION, CONFIGURACION_POR_DEFECTO } from '../../nucleo/servicios/configuracion';
import { of, throwError } from 'rxjs';

import { ConfiguracionComponent } from './configuracion.component';
import { type DatosClinica, type EstadoIntegracion, IntegracionesService } from './integraciones.service';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';

function clinica(): DatosClinica {
    return {
        id: 'clinica-1',
        nombre: 'Clínica de prueba',
        identificacion_fiscal: null,
        zona_horaria: 'America/Guayaquil',
        idioma: 'es',
        moneda: 'USD',
        telefono: null,
        correo: null,
    };
}

function integraciones(): EstadoIntegracion[] {
    return [
        {
            codigo: 'anthropic',
            habilitada: false,
            ajustes: { modelo: 'claude-sonnet-5', max_tokens: 2048, temperatura: 0.2 },
            secretos: { api_key: { configurado: true } },
            version: 2,
        },
        {
            codigo: 'whatsapp',
            habilitada: false,
            ajustes: { id_numero_telefono: '', id_cuenta_negocio: '', version_api: 'v21.0', validar_firma: true },
            secretos: {
                token_acceso: { configurado: false },
                token_verificacion: { configurado: false },
                secreto_app: { configurado: false },
            },
            version: 0,
        },
        {
            codigo: 'google_calendar',
            habilitada: false,
            ajustes: { client_id: '', redirect_uri: '', scopes: 'calendar.events' },
            secretos: { client_secret: { configurado: false } },
            version: 0,
        },
        {
            codigo: 'smtp',
            habilitada: false,
            ajustes: { host: '', puerto: 587, usuario: '', tls: true, correo_remitente: '', nombre_remitente: '' },
            secretos: { contrasena: { configurado: false } },
            version: 0,
        },
    ];
}

describe('ConfiguracionComponent', () => {
    let fixture: ComponentFixture<ConfiguracionComponent>;
    let servicio: MockedObject<IntegracionesService>;

    beforeEach(() => {
        servicio = {
            clinica: vi.fn().mockName("IntegracionesService.clinica"),
            guardarClinica: vi.fn().mockName("IntegracionesService.guardarClinica"),
            listar: vi.fn().mockName("IntegracionesService.listar"),
            guardar: vi.fn().mockName("IntegracionesService.guardar")
        } as unknown as MockedObject<IntegracionesService>;
        servicio.clinica.mockReturnValue(of(clinica()));
        servicio.listar.mockReturnValue(of(integraciones()));
        servicio.guardarClinica.mockReturnValue(of(clinica()));
        servicio.guardar.mockImplementation((codigo, datos) => of({
            ...integraciones().find((estado) => estado.codigo === codigo)!,
            habilitada: datos.habilitada,
        }));

        TestBed.configureTestingModule({
            imports: [ConfiguracionComponent],
            providers: [
                provideRouter([]),
                // Las tarjetas de IA (JEV y respuestas) piden su configuración por su cuenta.
                provideHttpClient(withXhr()),
                provideHttpClientTesting(),
                { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
                { provide: IntegracionesService, useValue: servicio },
                { provide: CatalogoService, useValue: { limpiar: vi.fn().mockName('limpiar') } },
                {
                    provide: SesionService,
                    useValue: {
                        tienePermiso: () => true,
                        tieneAlgunPermiso: () => true,
                    },
                },
            ],
        });
        fixture = TestBed.createComponent(ConfiguracionComponent);
        fixture.detectChanges();
    });

    function abrirIntegraciones(): void {
        const botones = Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('button')) as HTMLButtonElement[];
        const boton = botones.find((elemento) => elemento.textContent?.includes('Integraciones') ?? false) as HTMLButtonElement | undefined;
        if (!boton)
            throw new Error('No se encontró la pestaña de integraciones.');
        boton.click();
        fixture.detectChanges();
    }

    function guardarAnthropic(): void {
        const botones = Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('button')) as HTMLButtonElement[];
        const boton = botones.find((elemento) => elemento.textContent?.includes('Guardar Anthropic') ?? false) as HTMLButtonElement | undefined;
        if (!boton)
            throw new Error('No se encontró el botón de guardado de Anthropic.');
        boton.click();
        fixture.detectChanges();
    }

    it('muestra que existe una clave guardada sin rellenar su valor', () => {
        abrirIntegraciones();

        const entrada = fixture.nativeElement.querySelector('input[name="anthropic-api-key"]') as HTMLInputElement;
        expect(entrada.type).toBe('password');
        expect(entrada.value).toBe('');
        expect(fixture.nativeElement.textContent).toContain('Hay una credencial cifrada guardada.');
    });

    it('no vuelve a enviar una clave vacía y conserva el estado guardado', () => {
        abrirIntegraciones();
        guardarAnthropic();

        expect(servicio.guardar).toHaveBeenCalledWith('anthropic', expect.objectContaining({ secretos: {}, eliminar_secretos: [] }));
        expect(fixture.nativeElement.textContent).toContain('Hay una credencial cifrada guardada.');
        expect((fixture.nativeElement.querySelector('input[name="anthropic-api-key"]') as HTMLInputElement).value).toBe('');
    });

    it('presenta los errores al cargar y guardar la configuración y la clínica', () => {
        const componente = fixture.componentInstance as unknown as {
            cargarClinica(): void;
            guardarClinica(): void;
            cargar(): void;
            guardar(codigo: 'anthropic'): void;
            errorClinica(): string;
            error(): string;
        };
        servicio.clinica.mockReturnValue(throwError(() => new Error('fallo clínica')));
        componente.cargarClinica();
        expect(componente.errorClinica()).toBe('No se pudo cargar la clínica.');

        servicio.guardarClinica.mockReturnValue(throwError(() => new Error('fallo clínica')));
        componente.guardarClinica();
        expect(componente.errorClinica()).toBe('No se pudo guardar la clínica.');

        servicio.listar.mockReturnValue(throwError(() => new Error('fallo integraciones')));
        componente.cargar();
        expect(componente.error()).toBe('No se pudo cargar la configuración.');

        servicio.guardar.mockReturnValue(throwError(() => new Error('fallo guardado')));
        componente.guardar('anthropic');
        expect(componente.error()).toBe('No se pudo guardar la configuración.');
    });
});
