import type { MockedObject } from "vitest";
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';

import { ApiService } from '../../nucleo/servicios/api.service';
import type { DetalleConversacionEntrante } from '../../nucleo/servicios/api.service';
import { IndicadoresService, type Indicadores } from '../../nucleo/servicios/indicadores.service';
import { PERMISOS } from '../../nucleo/servicios/configuracion';
import { PendientesService } from '../../nucleo/servicios/pendientes.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { ConversacionesComponent } from './conversaciones.component';

const aviso = {
    id: 'aviso-1',
    conversacion_id: 'hilo-1',
    creado_en: '2026-10-06T12:00:00Z',
} as const;

const detalle: DetalleConversacionEntrante = {
    id: 'hilo-1',
    telefono: '593999000123',
    paciente_id: null,
    estado: 'EN_HANDOFF',
    motivo_handoff: 'REVISIÓN CLÍNICA · revisión humana',
    ultima_actividad_en: '2026-10-06T12:00:00Z',
    ultimo_mensaje: 'Tengo un problema con mi medicamento',
    ventana_expira_en: new Date(Date.now() + 86_400_000).toISOString(),
    asignado_a_usuario_id: null,
    mensajes: [
        {
            id: 'mensaje-1',
            tipo: 'text',
            texto: 'Tengo un problema con mi medicamento',
            intencion: 'PROBLEMA_TRATAMIENTO',
            recibido_en: '2026-10-06T12:00:00Z',
        },
    ],
    respuestas: [
        { id: 'respuesta-1', texto: 'Le responderá recepción', autor: 'PERSONAL', estado: 'FALLIDO', creado_en: '2026-10-06T12:05:00Z', entregado_en: null, error: 'Ventana vencida' },
    ],
};

describe('ConversacionesComponent: avisos clínicos', () => {
    let fixture: ComponentFixture<ConversacionesComponent>;
    let api: MockedObject<ApiService>;
    let indicadores: MockedObject<IndicadoresService>;
    let sesion: MockedObject<SesionService>;
    let pendientes: MockedObject<Pick<PendientesService, 'cargar'>>;

    beforeEach(async () => {
        api = {
            conversacionesPendientes: vi.fn().mockName("ApiService.conversacionesPendientes"),
            avisosTratamientoPendientes: vi.fn().mockName("ApiService.avisosTratamientoPendientes"),
            conversacion: vi.fn().mockName("ApiService.conversacion"),
            confirmarRevisionAvisoTratamiento: vi.fn().mockName("ApiService.confirmarRevisionAvisoTratamiento")
            ,responderConversacion: vi.fn(), tomarConversacion: vi.fn(), devolverConversacion: vi.fn(), cerrarConversacion: vi.fn()
        } as unknown as MockedObject<ApiService>;
        api.conversacionesPendientes.mockReturnValue(of({ elementos: [], total: 0, limite: 50, desplazamiento: 0 }));
        api.avisosTratamientoPendientes.mockReturnValue(of([aviso]));
        api.conversacion.mockReturnValue(of(detalle));
        api.confirmarRevisionAvisoTratamiento.mockReturnValue(of(void 0));
        api.responderConversacion.mockReturnValue(of({ encolado: true }));
        api.tomarConversacion.mockReturnValue(of(void 0));
        api.devolverConversacion.mockReturnValue(of(void 0));
        api.cerrarConversacion.mockReturnValue(of(void 0));
        sesion = {
            tienePermiso: vi.fn().mockName("SesionService.tienePermiso")
        } as unknown as MockedObject<SesionService>;
        sesion.tienePermiso.mockImplementation((permiso: string) => permiso === PERMISOS.alertaAdherenciaAtender);
        pendientes = {
            cargar: vi.fn().mockName("PendientesService.cargar")
        };
        indicadores = {
            obtener: vi.fn().mockName("IndicadoresService.obtener"),
            refrescar: vi.fn().mockName("IndicadoresService.refrescar")
        } as unknown as MockedObject<IndicadoresService>;
        indicadores.obtener.mockReturnValue(of({} as Indicadores));

        await TestBed.configureTestingModule({
            imports: [ConversacionesComponent],
            providers: [
                { provide: ApiService, useValue: api },
                { provide: SesionService, useValue: sesion },
                { provide: PendientesService, useValue: pendientes },
                { provide: IndicadoresService, useValue: indicadores },
            ],
        }).compileComponents();

        fixture = TestBed.createComponent(ConversacionesComponent);
        fixture.detectChanges();
    });

    it('abre el mensaje asociado y confirma la revisión con el permiso clínico', () => {
        const abrir = Array.from(fixture.nativeElement.querySelectorAll('button')).find((boton) => (boton as HTMLButtonElement).textContent?.includes('Abrir mensaje')) as HTMLButtonElement | undefined;
        expect(fixture.nativeElement.textContent).toContain('Reportes de tratamiento por revisar');
        expect(fixture.nativeElement.textContent).toContain('Confirmar revisión');
        expect(abrir).toBeDefined();
        abrir?.click();
        fixture.detectChanges();
        expect(api.conversacion).toHaveBeenCalledWith('hilo-1');
        expect(fixture.nativeElement.textContent).toContain('Tengo un problema con mi medicamento');

        const confirmar = Array.from(fixture.nativeElement.querySelectorAll('button')).find((boton) => (boton as HTMLButtonElement).textContent?.includes('Confirmar revisión')) as HTMLButtonElement | undefined;
        expect(confirmar).toBeDefined();
        confirmar?.click();
        fixture.detectChanges();

        expect(api.confirmarRevisionAvisoTratamiento).toHaveBeenCalledWith('aviso-1');
        expect(api.avisosTratamientoPendientes).toHaveBeenCalledTimes(1);
        expect(fixture.nativeElement.textContent).not.toContain('Reportes de tratamiento por revisar');
        expect(pendientes.cargar).toHaveBeenCalled();
    });

    it('mantiene visible el aviso si falla el registro de revisión', () => {
        api.confirmarRevisionAvisoTratamiento.mockReturnValue(throwError(() => new Error('No se pudo guardar')));
        const boton = Array.from(fixture.nativeElement.querySelectorAll('button')).find((elemento) => (elemento as HTMLButtonElement).textContent?.includes('Confirmar revisión')) as HTMLButtonElement;
        boton.click();
        fixture.detectChanges();

        expect(fixture.nativeElement.textContent).toContain('No se pudo guardar');
        expect(fixture.nativeElement.textContent).toContain('Reportes de tratamiento por revisar');
    });

    it('filtra por estado y muestra la línea de tiempo con fallo de entrega', () => {
        const filtro = Array.from(fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>).find((b) => b.textContent?.includes('Las atiende el agente')) as HTMLButtonElement;
        filtro.click(); fixture.detectChanges();
        expect(api.conversacionesPendientes).toHaveBeenLastCalledWith(50, 0, 'ABIERTA');
        api.conversacion.mockReturnValue(of(detalle));
        fixture.componentInstance['abrir']({ id: 'hilo-1', telefono: '593999000123', paciente_id: null, estado: 'EN_HANDOFF', motivo_handoff: null, ultima_actividad_en: '', ultimo_mensaje: '' });
        fixture.detectChanges();
        expect(fixture.nativeElement.textContent).toContain('Paciente');
        expect(fixture.nativeElement.textContent).toContain('Personal');
        expect(fixture.nativeElement.textContent).toContain('FALLIDO');
        expect(fixture.nativeElement.textContent).toContain('Ventana vencida');
    });

    it('responde con una Idempotency-Key única y reacciona al conflicto 409', () => {
        fixture.componentInstance['abrir']({ id: 'hilo-1', telefono: '593999000123', paciente_id: null, estado: 'EN_HANDOFF', motivo_handoff: null, ultima_actividad_en: '', ultimo_mensaje: '' });
        fixture.detectChanges();
        fixture.componentInstance['textoRespuesta'].set('Hola');
        fixture.componentInstance['responder']();
        expect(api.responderConversacion).toHaveBeenCalledWith('hilo-1', 'Hola', expect.any(String));
        expect((api.responderConversacion.mock.calls[0] as unknown as string[])[2]).toMatch(/[0-9a-f-]{36}/);
        const primeraClave = (api.responderConversacion.mock.calls[0] as unknown as string[])[2];
        api.responderConversacion.mockReturnValue(throwError(() => new Error('409 ventana 24 h')));
        fixture.componentInstance['abrir']({ id: 'hilo-1', telefono: '593999000123', paciente_id: null, estado: 'EN_HANDOFF', motivo_handoff: null, ultima_actividad_en: '', ultimo_mensaje: '' });
        fixture.componentInstance['textoRespuesta'].set('De nuevo');
        fixture.componentInstance['responder'](); fixture.detectChanges();
        const segundaClave = (api.responderConversacion.mock.calls[1] as unknown as string[])[2];
        expect(segundaClave).not.toBe(primeraClave);
        expect(fixture.nativeElement.textContent).toContain('La ventana de 24 h venció');
    });

    it('ejecuta tomar, devolver y cerrar previa confirmación', () => {
        fixture.componentInstance['abrir']({ id: 'hilo-1', telefono: '593999000123', paciente_id: 'paciente-1', estado: 'EN_HANDOFF', motivo_handoff: null, ultima_actividad_en: '', ultimo_mensaje: '' });
        fixture.componentInstance['accion']('tomar');
        fixture.componentInstance['accion']('devolver');
        const confirmacion = vi.spyOn(window, 'confirm').mockReturnValue(false);
        fixture.componentInstance['accion']('cerrar');
        expect(api.tomarConversacion).toHaveBeenCalledWith('hilo-1');
        expect(api.devolverConversacion).toHaveBeenCalledWith('hilo-1');
        expect(api.cerrarConversacion).not.toHaveBeenCalled();
        confirmacion.mockReturnValue(true);
        fixture.componentInstance['abrir']({ id: 'hilo-1', telefono: '593999000123', paciente_id: 'paciente-1', estado: 'ABIERTA', motivo_handoff: null, ultima_actividad_en: '', ultimo_mensaje: '' });
        fixture.componentInstance['accion']('cerrar');
        expect(api.cerrarConversacion).toHaveBeenCalledWith('hilo-1');
        confirmacion.mockRestore();
    });
});
