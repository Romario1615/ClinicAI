import type { MockedObject } from "vitest";
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { ApiService } from './api.service';
import { PERMISOS } from './configuracion';
import { OperacionesService } from './operaciones.service';
import { PendientesService } from './pendientes.service';
import { SesionService } from './sesion.service';

describe('PendientesService: conteo de notificaciones', () => {
    let api: MockedObject<ApiService>;
    let sesion: MockedObject<SesionService>;
    let operaciones: MockedObject<OperacionesService>;
    let pendientes: PendientesService;

    beforeEach(() => {
        api = {
            cuentaConversacionesPendientes: vi.fn().mockName("ApiService.cuentaConversacionesPendientes"),
            cuentaAvisosTratamientoPendientes: vi.fn().mockName("ApiService.cuentaAvisosTratamientoPendientes")
        } as unknown as MockedObject<ApiService>;
        api.cuentaConversacionesPendientes.mockReturnValue(of({ cantidad: 3 }));
        api.cuentaAvisosTratamientoPendientes.mockReturnValue(of({ cantidad: 2 }));
        operaciones = {
            leer: vi.fn().mockName("OperacionesService.leer")
        } as unknown as MockedObject<OperacionesService>;
        sesion = {
            tienePermiso: vi.fn().mockName("SesionService.tienePermiso")
        } as unknown as MockedObject<SesionService>;
        sesion.tienePermiso.mockImplementation((permiso: string) => permiso === PERMISOS.conversacionLeer);

        TestBed.configureTestingModule({
            providers: [
                { provide: ApiService, useValue: api },
                { provide: OperacionesService, useValue: operaciones },
                { provide: SesionService, useValue: sesion },
            ],
        });
    });

    it('separa conversaciones de reportes clínicos y suma cada aviso una sola vez', () => {
        pendientes = TestBed.inject(PendientesService);
        pendientes.cargar();

        expect(pendientes.conversacionesPendientes()).toBe(3);
        expect(pendientes.avisosTratamientoPendientes()).toBe(2);
        expect(pendientes.notificaciones()).toBe(5);
    });

    it('cuenta cargos vencidos desde el servidor solo con permiso de lectura de pagos', () => {
        pendientes = TestBed.inject(PendientesService);
        sesion.tienePermiso.mockImplementation((permiso: string) => permiso === PERMISOS.pagoLeer);
        operaciones.leer.mockReturnValue(of({ elementos: [], total: 4 }));

        pendientes.cargar();

        expect(operaciones.leer).toHaveBeenCalledWith('/pagos/cargos/', {
            limite: 1,
            desplazamiento: 0,
            vencidos: true,
        });
        expect(pendientes.cargosVencidosPendientes()).toBe(4);
        expect(pendientes.notificaciones()).toBe(4);
    });

    it('limpia el conteo de cobros al perder el permiso y no consulta pagos', () => {
        pendientes = TestBed.inject(PendientesService);
        sesion.tienePermiso.mockReturnValue(false);
        pendientes.refrescarCobrosVencidos();

        expect(operaciones.leer).not.toHaveBeenCalled();
        expect(pendientes.cargosVencidosPendientes()).toBe(0);
    });

    it('refresca la cola de llamadas cada minuto con permiso y conserva el total del servidor', () => {
        vi.useFakeTimers();
        try {
        sesion.tienePermiso.mockImplementation((permiso: string) => permiso === PERMISOS.agendaLeer || permiso === PERMISOS.listaEsperaGestionar);
        operaciones.leer.mockReturnValue(of({
            elementos: [{ id: 'espera-1', oferta_expira_en: null }],
            total: 31,
        }));
        // Se crea dentro de fakeAsync para que el reloj de prueba controle interval().
        pendientes = TestBed.inject(PendientesService);

        vi.advanceTimersByTime(60000);

        expect(operaciones.leer).toHaveBeenCalledWith('/lista-espera/', {
            limite: 25,
            desplazamiento: 0,
            solo_sin_avisar: true,
        });
        expect(pendientes.tareas()[0].titulo).toBe('31 ofertas de lista de espera sin avisar');
        } finally {
            vi.useRealTimers();
        }
    });

    it('no sondea ofertas para una cuenta sin permiso de lista de espera', () => {
        vi.useFakeTimers();
        try {
        sesion.tienePermiso.mockReturnValue(false);
        pendientes = TestBed.inject(PendientesService);
        vi.advanceTimersByTime(60000);

        expect(operaciones.leer).not.toHaveBeenCalled();
        } finally {
            vi.useRealTimers();
        }
    });
});
