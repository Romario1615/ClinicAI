import type { MockedObject } from "vitest";
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';
import { of } from 'rxjs';

import { CONFIGURACION_POR_DEFECTO } from '../../nucleo/servicios/configuracion';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { PROVEEDORES_PRUEBA } from '../../nucleo/pruebas/sesion-sintetica';
import { BloqueosAgendaComponent } from './bloqueos-agenda.component';

describe('BloqueosAgendaComponent', () => {
    let fixture: ComponentFixture<BloqueosAgendaComponent>;
    let http: HttpTestingController;
    let catalogo: MockedObject<CatalogoService>;
    const sede = { id: 's-1', nombre: 'Centro', direccion: null, zona_horaria: 'America/Guayaquil' };

    beforeEach(() => {
        catalogo = {
            sedes: vi.fn().mockName("CatalogoService.sedes"),
            profesionales: vi.fn().mockName("CatalogoService.profesionales"),
            consultorios: vi.fn().mockName("CatalogoService.consultorios")
        } as unknown as MockedObject<CatalogoService>;
        catalogo.sedes.mockReturnValue(of([sede]));
        catalogo.profesionales.mockReturnValue(of([{ id: 'p-1', nombre: 'Ana', apellido: 'Paz', especialidad_id: 'e-1', numero_registro_profesional: 'R-1' }]));
        catalogo.consultorios.mockReturnValue(of([{ id: 'c-1', sede_id: 's-1', nombre: 'Sala 1', tipo: 'CONSULTA', capacidad: 1 }]));
        TestBed.configureTestingModule({ imports: [BloqueosAgendaComponent], providers: [...PROVEEDORES_PRUEBA, { provide: CatalogoService, useValue: catalogo }] });
        fixture = TestBed.createComponent(BloqueosAgendaComponent);
        http = TestBed.inject(HttpTestingController);
        fixture.detectChanges();
    });

    afterEach(() => http.verify());

    function cargarLista(): void {
        http.expectOne((r) => r.url === `${CONFIGURACION_POR_DEFECTO.urlApi}/agenda/bloqueos`).flush([]);
        fixture.detectChanges();
    }

    it('carga la sede y muestra la administración de bloqueos', () => {
        cargarLista();
        expect(fixture.nativeElement.textContent).toContain('Bloqueos registrados');
        expect(catalogo.profesionales).toHaveBeenCalledWith({ sedeId: 's-1' });
        expect(catalogo.consultorios).toHaveBeenCalledWith('s-1');
    });

    it('abre la captura en una ventana flotante accesible', () => {
        cargarLista();
        const boton = Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('button'))
            .find((elemento) => elemento.textContent?.trim() === 'Nuevo bloqueo');
        boton?.click();
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('dialog[open][aria-label="Nuevo bloqueo"]')).not.toBeNull();
        expect(fixture.nativeElement.querySelector('#form-bloqueo')).not.toBeNull();
    });

    it('convierte el horario local de la sede a un instante UTC', () => {
        cargarLista();
        const control = fixture.componentInstance as unknown as {
            aIso: (valor: string) => string;
        };
        expect(control.aIso('2026-01-15T09:30')).toBe('2026-01-15T14:30:00.000Z');
    });

    it('presenta el tipo de bloqueo con su etiqueta clínica', () => {
        cargarLista();
        const control = fixture.componentInstance as unknown as {
            nombreTipo: (tipo: string) => string;
        };
        expect(control.nombreTipo('VACACIONES')).toBe('Vacaciones');
    });

    it('pide confirmación sin mostrar datos de pacientes y guarda las citas afectadas', async () => {
        cargarLista();
        const componente = fixture.componentInstance as unknown as {
            guardar: () => Promise<void>;
            confirmarCitasAfectadas(): void;
            form: {
                tipo: string;
                motivo: string;
            };
            formInicio: string;
            formFin: string;
        };
        componente.form.tipo = 'AUSENCIA';
        componente.form.motivo = 'Ausencia médica';
        componente.formInicio = '2026-01-15T09:30';
        componente.formFin = '2026-01-15T10:30';
        const guardar = componente.guardar();
        const primera = http.expectOne(`${CONFIGURACION_POR_DEFECTO.urlApi}/agenda/bloqueos`);
        expect(primera.request.body.inicio).toBe('2026-01-15T14:30:00.000Z');
        primera.flush({ codigo: 'CONFLICTO_ESTADO', mensaje: 'Citas afectadas', detalles: { citas_afectadas: [{ id: 'cita-1' }] } }, { status: 409, statusText: 'Conflict' });
        await Promise.resolve();
        fixture.detectChanges();
        const confirmacion = fixture.nativeElement.querySelector('dialog[open][aria-label="Confirmar el bloqueo"]');
        expect(confirmacion?.textContent).toContain('1 cita activa');
        expect(confirmacion?.textContent).toContain('No se muestran datos de pacientes');
        const confirmacionGuardada = componente.confirmarCitasAfectadas();
        const segunda = http.expectOne(`${CONFIGURACION_POR_DEFECTO.urlApi}/agenda/bloqueos`);
        expect(segunda.request.body.aceptar_citas_afectadas).toBe(true);
        segunda.flush({ id: 'b-1', sede_id: 's-1', profesional_id: null, consultorio_id: null, tipo: 'AUSENCIA', inicio: '2026-01-15T14:30:00Z', fin: '2026-01-15T15:30:00Z', motivo: 'Ausencia médica', creado_con_citas_afectadas: true });
        await confirmacionGuardada;
        fixture.detectChanges();
        http.expectOne((r) => r.url === `${CONFIGURACION_POR_DEFECTO.urlApi}/agenda/bloqueos`).flush([]);
        await guardar;
    });
});
