import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { of, throwError } from 'rxjs';

import { ListaEsperaComponent } from './lista-espera.component';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { OperacionesService } from '../../nucleo/servicios/operaciones.service';
import { PendientesService } from '../../nucleo/servicios/pendientes.service';
import type { EntradaEspera } from '../../nucleo/servicios/operaciones.service';
import type { Paciente } from '../../nucleo/modelos/dominio';

describe('ListaEsperaComponent', () => {
    let fixture: ComponentFixture<ListaEsperaComponent>;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let c: any;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let api: any;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let catalogo: any;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let pendientes: any;

    beforeEach(() => {
        api = {
            leer: vi.fn().mockName("OperacionesService.leer"),
            guardar: vi.fn().mockName("OperacionesService.guardar")
        };
        api.leer.mockImplementation((ruta: string) => of(ruta === '/lista-espera/' ? { elementos: [], total: 0 } : []));
        api.guardar.mockReturnValue(of({}));
        catalogo = {
            sedes: vi.fn().mockName("CatalogoService.sedes"),
            servicios: vi.fn().mockName("CatalogoService.servicios"),
            profesionales: vi.fn().mockName("CatalogoService.profesionales")
        };
        catalogo.sedes.mockReturnValue(of([]));
        catalogo.servicios.mockReturnValue(of([]));
        catalogo.profesionales.mockReturnValue(of([]));
        pendientes = {
            cargar: vi.fn().mockName("PendientesService.cargar")
        };

        TestBed.configureTestingModule({
            imports: [ListaEsperaComponent],
            providers: [
                { provide: OperacionesService, useValue: api },
                { provide: CatalogoService, useValue: catalogo },
                { provide: PendientesService, useValue: pendientes },
            ],
        });
        fixture = TestBed.createComponent(ListaEsperaComponent);
        c = fixture.componentInstance;
        fixture.detectChanges();
    });

    it('presenta una ilustración accesible cuando la cola está vacía', () => {
        const raiz = fixture.nativeElement as HTMLElement;
        const vacio = raiz.querySelector('.vacio-espera');
        const imagen = vacio?.querySelector('img');

        expect(vacio?.getAttribute('role')).toBe('status');
        expect(imagen?.getAttribute('src')).toBe('/images/lista-espera-vacia.svg');
        expect(imagen?.getAttribute('alt')).toBe('');
        expect(vacio?.textContent).toContain('Todavía no hay pacientes en lista de espera');
    });

    it('valida datos mínimos, rangos horarios y fechas antes de anotar', () => {
        expect(c.puedeAnotar()).toBe(false);
        expect(c.faltaParaAnotar()).toBe('Elija primero al paciente.');
        c.paciente.set({ id: 'p-1' } as Paciente);
        expect(c.faltaParaAnotar()).toBe('Elija la sede.');
        c.sedeId.set('s-1');
        expect(c.faltaParaAnotar()).toBe('Elija el servicio.');
        c.servicioId.set('srv-1');
        c.horaDesde.set('10:00');
        expect(c.franjaCoherente()).toBe(false);
        expect(c.faltaParaAnotar()).toBe('Revise la franja horaria.');
        c.horaHasta.set('09:00');
        expect(c.franjaCoherente()).toBe(false);
        c.horaHasta.set('11:00');
        c.disponibleDesde.set('2026-10-10');
        c.disponibleHasta.set('2026-10-09');
        expect(c.fechasCoherentes()).toBe(false);
        expect(c.faltaParaAnotar()).toBe('Revise las fechas.');
        c.disponibleHasta.set('2026-10-10');
        expect(c.puedeAnotar()).toBe(true);
        expect(c.faltaParaAnotar()).toBe('');
    });

    it('prepara el formulario y abre y cierra los detalles', () => {
        c.sedes.set([{ id: 's-1' }]);
        c.diasPreferidos.set([2]);
        c.abrirAlta();
        expect(c.altaAbierta()).toBe(true);
        expect(c.sedeId()).toBe('s-1');
        expect(c.diasPreferidos()).toEqual([]);
        c.cerrarAlta();
        expect(c.altaAbierta()).toBe(false);
        const entrada = { id: 'e-1' } as EntradaEspera;
        c.abrirDetalle(entrada);
        expect(c.entradaElegida()).toBe(entrada);
    });

    it('mantiene días preferidos ordenados, sin duplicados, y los muestra en español', () => {
        c.alternarDia(4, true);
        c.alternarDia(1, true);
        c.alternarDia(4, true);
        expect(c.diasPreferidos()).toEqual([1, 4]);
        expect(c.nombresDias([1, 4, 99])).toBe('Martes, Viernes');
        c.alternarDia(1, false);
        expect(c.diasPreferidos()).toEqual([4]);
    });

    it('consulta citas futuras compatibles y deja informar si el servicio falla', () => {
        const futuro = new Date(Date.now() + 86400000).toISOString();
        const pasado = new Date(Date.now() - 86400000).toISOString();
        api.leer.mockImplementation((ruta: string) => of(ruta === '/agenda/citas' ? { elementos: [
                { servicio_id: 'srv-1', estado: 'CONFIRMED', inicio: futuro },
                { servicio_id: 'srv-1', estado: 'CONFIRMED', inicio: pasado },
                { servicio_id: 'otro', estado: 'CONFIRMED', inicio: futuro },
                { servicio_id: 'srv-1', estado: 'CANCELLED', inicio: futuro },
            ] } : { elementos: [], total: 0 }));
        c.sedeId.set('s-1');
        c.servicioId.set('srv-1');
        c.seleccionarPaciente({ id: 'p-1' } as Paciente);
        expect(c.citasPrevias().length).toBe(1);
        expect(c.buscandoCitas()).toBe(false);

        api.leer.mockReturnValue(throwError(() => ({ message: 'fallo' })));
        c.seleccionarPaciente({ id: 'p-2' } as Paciente);
        expect(c.error()).toContain('No se pudieron consultar las citas');
        expect(c.buscandoCitas()).toBe(false);
    });

    it('recarga la cola y nombres, y conserva un identificador si no puede leer la ficha', () => {
        const entrada = { id: 'e-1', paciente_id: 'paciente-largo-123', servicio_id: 'srv-1' } as EntradaEspera;
        api.leer.mockImplementation((ruta: string) => ruta === '/lista-espera/'
            ? of({ elementos: [entrada], total: 1 })
            : throwError(() => new Error('sin permiso')));
        c.cargar();
        expect(c.entradas()).toEqual([entrada]);
        expect(c.total()).toBe(1);
        expect(c.nombre(entrada.paciente_id)).toBe('Paciente paciente');
        expect(c.nombreServicio('srv-desconocido')).toBe('Servicio');
        expect(c.presentacion('ESTADO_NUEVO')).toEqual({ etiqueta: 'ESTADO_NUEVO', clase: 'neutra' });
    });

    it('anota preferencias, resuelve entradas, y refresca el indicador al completar', () => {
        catalogo.servicios.mockReturnValue(of([{ id: 'srv-1', especialidad_id: 'esp-1', nombre: 'Control' }]));
        fixture.destroy();
        fixture = TestBed.createComponent(ListaEsperaComponent);
        c = fixture.componentInstance;
        fixture.detectChanges();
        c.paciente.set({ id: 'p-1' } as Paciente);
        c.sedeId.set('s-1');
        c.servicioId.set('srv-1');
        c.horaDesde.set('09:00');
        c.horaHasta.set('11:00');
        c.alternarDia(0, true);
        c.anotar();
        expect(api.guardar).toHaveBeenCalledWith('/lista-espera/', expect.objectContaining({
            preferencias: { dias_semana: [0], hora_desde: '09:00', hora_hasta: '11:00' },
        }), expect.any(String));
        expect(c.aviso()).toBe('Lista de espera actualizada.');
        expect(c.altaAbierta()).toBe(false);
        expect(pendientes.cargar).toHaveBeenCalled();

        api.guardar.mockReturnValue(throwError(() => ({ message: 'No se guardó.' })));
        c.resolver({ id: 'e-1' } as EntradaEspera, 'RETIRAR');
        expect(api.guardar).toHaveBeenCalledWith('/lista-espera/e-1/resolver', { accion: 'RETIRAR' }, expect.any(String));
        expect(c.error()).toBe('No se guardó.');
    });

    it('limpia el estado al filtrar, pagina y formatea fechas según la sede local', () => {
        c.alternarPendientes(true);
        expect(c.soloSinAvisar()).toBe(true);
        c.pagina.set(2);
        c.mover(-1);
        expect(c.pagina()).toBe(1);
        expect(c.fecha(null)).toBe('—');
        expect(c.fecha('2026-10-06T15:00:00Z')).toContain('2026');
        expect(c.presentacion('ACTIVA')).toEqual({ etiqueta: 'En espera', clase: 'neutra' });
    });
});
