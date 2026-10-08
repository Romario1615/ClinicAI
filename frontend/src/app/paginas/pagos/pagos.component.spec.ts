/**
 * Pagos: se listan por paciente y fecha, se filtran por estado, se registran y
 * se revisan en una ventana flotante.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { PagosComponent, type PagoListado } from './pagos.component';
import { BASE, PROVEEDORES_PRUEBA, iniciarSesionCon } from '../../nucleo/pruebas/sesion-sintetica';

const PAGO: PagoListado = {
    id: 'pg1',
    cita_id: 'c1',
    cargo_id: 'cg1',
    importe: '35.50',
    moneda: 'USD',
    metodo: 'TRANSFERENCIA',
    estado: 'PROOF_RECEIVED',
    referencia: 'TRF-1',
    comentario: 'Comprobante enviado por WhatsApp',
    validado_en: null,
    paciente: 'Ana Sintética',
    cita_inicio: '2026-10-14T15:15:00Z',
};

const CARGO = {
    id: 'cg1', cita_id: 'c1', total_acordado: '100.00', moneda: 'USD' as const,
    fecha_vencimiento: null, vencido: false,
    origen: 'PACTADO' as const, creado_en: '2026-10-14T15:15:00Z', paciente: 'Ana Sintética',
    cita_inicio: '2026-10-14T15:15:00Z', total_confirmado: '30.00', total_comprometido: '50.00',
    saldo_pendiente: '70.00', saldo_no_asignado: '50.00',
};

const EVENTO_HISTORIAL = {
    id: 'evt1',
    estado_anterior: 'PENDING',
    estado_nuevo: 'PROOF_RECEIVED',
    comentario: 'Se recibió el comprobante',
    actor_id: 'usr1',
    secuencia: 2,
    ocurrido_en: '2026-10-14T15:15:00Z',
};

describe('PagosComponent', () => {
    let fixture: ComponentFixture<PagosComponent>;
    let http: HttpTestingController;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let c: any;

    function montar(permisos: readonly string[]): void {
        iniciarSesionCon(permisos);
        fixture = TestBed.createComponent(PagosComponent);
        c = fixture.componentInstance;
        fixture.detectChanges();
        http.match((r) => r.url === `${BASE}/catalogo/sedes`).forEach((r) => r.flush([
            { id: 's1', nombre: 'Centro', direccion: null, telefono: null, zona_horaria: 'America/Guayaquil' },
        ]));
        http.expectOne((r) => r.url === `${BASE}/pagos/cargos/` && r.params.get('desplazamiento') === '0')
            .flush({ elementos: [CARGO], total: 1 });
        http.expectOne((r) => r.url === `${BASE}/pagos/` && r.params.get('desplazamiento') === '0').flush({ elementos: [PAGO], total: 1 });
        fixture.detectChanges();
    }

    beforeEach(() => {
        TestBed.configureTestingModule({ imports: [PagosComponent], providers: PROVEEDORES_PRUEBA });
        http = TestBed.inject(HttpTestingController);
    });

    afterEach(() => {
        // Resumen del módulo y selector de paciente piden por su cuenta.
        http.match((r) => !r.url.endsWith('/pagos/') && !r.url.includes('/pagos/pg1')).forEach((r) => r.flush({ elementos: [], total: 0 }));
        http.verify();
    });

    it('muestra paciente y fecha, y filtra por estado', () => {
        montar(['pago.leer']);
        const fila = (fixture.nativeElement as HTMLElement).querySelector('.tabla-pagos tbody tr')?.textContent ?? '';
        expect(fila).toContain('Ana Sintética');
        expect(fila).toContain('Comprobante recibido');
        expect((fixture.nativeElement as HTMLElement).textContent).not.toContain('Revisar');

        c.filtrar('CONFIRMED');
        const peticion = http.expectOne((r) => r.url === `${BASE}/pagos/` && r.params.get('estado') === 'CONFIRMED');
        peticion.flush({ elementos: [], total: 0 });
        fixture.detectChanges();
        expect((fixture.nativeElement as HTMLElement).textContent).toContain('No hay pagos con este filtro');
    });

    it('muestra totales y saldos de los cargos registrados', () => {
        montar(['pago.leer']);
        const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
        expect(texto).toContain('Cargos y saldos · 1');
        expect(texto).toContain('Disponible para abonos');
        expect((fixture.nativeElement as HTMLElement).querySelector('.cargos tbody')?.textContent)
            .toContain('$50,00');
        expect((fixture.nativeElement as HTMLElement).querySelector('.cargos tbody')?.textContent)
            .toContain('Sin fecha');
    });

    it('abre el alta de abonos en una ventana flotante y la cancela sin dejar el formulario en la lista', () => {
        montar(['pago.leer', 'pago.registrar']);
        const raiz = fixture.nativeElement as HTMLElement;
        expect(raiz.querySelector('.editor-demo')).toBeNull();
        const abrir = [...raiz.querySelectorAll('button')]
            .find((boton) => boton.textContent?.trim() === 'Registrar un abono');
        expect(abrir).toBeDefined();

        abrir?.click();
        fixture.detectChanges();
        const dialogo = document.querySelector('dialog.capa') as HTMLDialogElement | null;
        expect(dialogo?.open).toBe(true);
        expect(dialogo?.textContent).toContain('Registrar un abono');
        expect(dialogo?.querySelector('app-selector-paciente')).not.toBeNull();

        const cancelar = [...(dialogo?.querySelectorAll('button') ?? [])]
            .find((boton) => boton.textContent?.trim() === 'Cancelar');
        cancelar?.click();
        fixture.detectChanges();
        expect(document.querySelector('dialog.capa')).toBeNull();
        expect(raiz.querySelector('.editor-demo')).toBeNull();
    });

    it('ofrece el reporte solo con permisos y descarga el CSV agregado', () => {
        montar(['pago.leer', 'reporte.exportar']);
        expect((fixture.nativeElement as HTMLElement).textContent).toContain('Exportar movimientos');
        vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:reporte-pagos');
        vi.spyOn(URL, 'revokeObjectURL').mockReturnValue(undefined);

        c.reporteSedeId = 's1';
        c.exportarReporte();

        const solicitud = http.expectOne((r) => r.url === `${BASE}/pagos/resumen.csv`);
        expect(solicitud.request.method).toBe('GET');
        expect(solicitud.request.params.get('desde')).toBe(c.reporteDesde);
        expect(solicitud.request.params.get('hasta')).toBe(c.reporteHasta);
        expect(solicitud.request.params.get('sede_id')).toBe('s1');
        expect(solicitud.request.responseType).toBe('blob');
        solicitud.flush(new Blob(['Fecha local;Estado']));
        expect(c.avisoReporte()).toContain('se descargó');
        expect(URL.createObjectURL).toHaveBeenCalled();
        expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:reporte-pagos');
    });

    it('abre la exportación en una ventana flotante y no ocupa la pantalla de trabajo', () => {
        montar(['pago.leer', 'reporte.exportar']);
        const raiz = fixture.nativeElement as HTMLElement;
        expect(raiz.querySelector('.reporte-pagos__formulario')).toBeNull();
        const abrir = [...raiz.querySelectorAll('button')].find((boton) => boton.textContent?.trim() === 'Exportar movimientos');
        abrir?.click();
        fixture.detectChanges();
        const dialogo = document.querySelector('dialog.capa');
        expect(dialogo?.textContent).toContain('Exportar movimientos');
        expect(dialogo?.querySelector('.reporte-pagos__formulario')).not.toBeNull();
    });

    it('reparte pagos y cargos en pestañas y muestra una sola a la vez', () => {
        montar(['pago.leer']);
        const raiz = fixture.nativeElement as HTMLElement;
        const visibles = () => [...raiz.querySelectorAll<HTMLElement>('[role="tabpanel"]')].filter((panel) => !panel.hidden).map((panel) => panel.id);
        expect(visibles()).toEqual(['pagos-panel-pagos']);
        raiz.querySelector<HTMLElement>('#pagos-pestana-cargos')?.click();
        fixture.detectChanges();
        expect(visibles()).toEqual(['pagos-panel-cargos']);
    });

    it('no ofrece exportación financiera sin el permiso de reportes', () => {
        montar(['pago.leer']);
        expect((fixture.nativeElement as HTMLElement).textContent).not.toContain('Exportar movimientos');
    });

    it('filtra los cargos vencidos desde el servidor', () => {
        montar(['pago.leer']);
        c.filtrarCargos(true);
        const solicitud = http.expectOne((r) => r.url === `${BASE}/pagos/cargos/` && r.params.get('vencidos') === 'true');
        solicitud.flush({ elementos: [CARGO], total: 1 });
        expect(c.soloVencidos()).toBe(true);
    });

    it('permite fijar el vencimiento de un cargo sin fecha y actualiza el listado', () => {
        montar(['pago.leer', 'pago.validar']);
        c.abrirVencimiento(CARGO);
        c.fechaVencimientoConciliacion = '2026-06-15';
        c.fijarVencimiento();
        const guardar = http.expectOne({ method: 'PATCH', url: `${BASE}/pagos/cargos/cg1/vencimiento` });
        expect(guardar.request.body).toEqual({ fecha_vencimiento: '2026-06-15' });
        guardar.flush({ ...CARGO, fecha_vencimiento: '2026-06-15' });
        http.expectOne((r) => r.url === `${BASE}/pagos/cargos/` && r.params.get('desplazamiento') === '0')
            .flush({ elementos: [{ ...CARGO, fecha_vencimiento: '2026-06-15' }], total: 1 });
        http.expectOne((r) => r.url === `${BASE}/pagos/cargos/` && r.params.get('cita_id') === 'c1')
            .flush({ elementos: [{ ...CARGO, fecha_vencimiento: '2026-06-15' }], total: 1 });
        expect(c.cargoVencimiento()).toBeNull();
        expect(c.aviso()).toContain('Fecha de vencimiento fijada');
    });

    it('crea un cargo sin registrar un abono', () => {
        montar(['pago.leer', 'pago.registrar']);
        c.citaId = 'c1';
        c.totalAcordado = 100;
        c.crearCargo();
        const alta = http.expectOne({ method: 'POST', url: `${BASE}/pagos/cargos/` });
        expect(alta.request.body).toEqual({ cita_id: 'c1', total_acordado: 100, fecha_vencimiento: null });
        alta.flush(CARGO);
        http.expectOne((r) => r.url === `${BASE}/pagos/` && r.params.get('desplazamiento') === '0')
            .flush({ elementos: [], total: 0 });
        http.expectOne((r) => r.url === `${BASE}/pagos/cargos/` && r.params.get('desplazamiento') === '0')
            .flush({ elementos: [CARGO], total: 1 });
        fixture.detectChanges();
        expect(c.aviso()).toContain('Cargo registrado sin abono');
    });

    it('permite al perfil de solo lectura consultar el historial inmutable', () => {
        montar(['pago.leer']);
        const boton = (fixture.nativeElement as HTMLElement).querySelector('.tabla-pagos tbody button') as HTMLButtonElement;
        expect(boton.textContent).toContain('Historial');
        boton.click();
        http.expectOne(`${BASE}/pagos/pg1/historial`).flush({ elementos: [EVENTO_HISTORIAL] });
        http.expectOne(`${BASE}/pagos/pg1/comprobantes`).flush({ elementos: [] });
        fixture.detectChanges();
        const modal = document.querySelector('dialog.capa')?.textContent ?? '';
        expect(modal).toContain('Historial de pago');
        expect(modal).toContain('Pendiente → Comprobante recibido');
        expect(modal).toContain('Se recibió el comprobante');
        expect(modal).not.toContain('Nuevo estado');
    });

    it('revisa en ventana flotante y confirma', () => {
        montar(['pago.leer', 'pago.validar']);
        c.abrirCambio(PAGO);
        http.expectOne(`${BASE}/pagos/pg1/historial`).flush({ elementos: [EVENTO_HISTORIAL] });
        http.expectOne(`${BASE}/pagos/pg1/comprobantes`).flush({ elementos: [] });
        fixture.detectChanges();
        expect(document.querySelector('dialog.capa')?.textContent).toContain('Comprobante enviado por WhatsApp');
        expect(c.nuevoEstado).toBe('UNDER_REVIEW');
        const boton = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('.ventana__pie button[form="formulario-revision-pago"]');
        expect(boton?.form?.id).toBe('formulario-revision-pago');
        c.nuevoEstado = 'CONFIRMED';
        c.comentario = 'Transferencia verificada';
        c.cambiar();
        const guardar = http.expectOne({ method: 'POST', url: `${BASE}/pagos/pg1/estado` });
        expect(guardar.request.body).toEqual({ estado: 'CONFIRMED', comentario: 'Transferencia verificada' });
        guardar.flush({ ...PAGO, estado: 'CONFIRMED' });
        http.expectOne((r) => r.url === `${BASE}/pagos/`).flush({ elementos: [{ ...PAGO, estado: 'CONFIRMED' }], total: 1 });
        expect(c.revisando()).toBeNull();
        expect(c.aviso()).toContain('confirmado');
    });

    it('un error al revisar se queda en la ventana; registrar envía la referencia', () => {
        montar(['pago.leer', 'pago.validar', 'pago.registrar']);
        c.abrirCambio(PAGO);
        http.expectOne(`${BASE}/pagos/pg1/historial`).flush({ elementos: [EVENTO_HISTORIAL] });
        http.expectOne(`${BASE}/pagos/pg1/comprobantes`).flush({ elementos: [] });
        c.comentario = 'Revisión';
        c.cambiar();
        http.expectOne(`${BASE}/pagos/pg1/estado`).flush({ codigo: 'X', mensaje: 'Transición no permitida' }, { status: 409, statusText: 'C' });
        expect(c.error()).toBe('Transición no permitida');
        expect(c.revisando()).not.toBeNull();
        c.cerrarRevision();
        expect(c.error()).toBe('');

        c.citaId = 'c1';
        c.importe = 20;
        c.totalAcordado = 100;
        c.referencia = '  REF-9 ';
        c.registrar();
        const alta = http.expectOne({ method: 'POST', url: `${BASE}/pagos/` });
        expect(alta.request.body).toEqual({ cita_id: 'c1', importe: 20, total_acordado: 100, fecha_vencimiento: null, metodo: 'EFECTIVO', referencia: 'REF-9' });
        alta.flush(PAGO);
        http.expectOne((r) => r.url === `${BASE}/pagos/`).flush({ elementos: [], total: 0 });
        http.expectOne((r) => r.url === `${BASE}/pagos/cargos/`).flush({ elementos: [CARGO], total: 1 });
        expect(c.aviso()).toContain('pendiente');
    });

    it('adjunta comprobante desde un pago pendiente y muestra su estado de análisis', () => {
        montar(['pago.leer', 'pago.registrar']);
        c.abrirCambio({ ...PAGO, estado: 'PENDING' });
        http.expectOne(`${BASE}/pagos/pg1/historial`).flush({ elementos: [] });
        http.expectOne(`${BASE}/pagos/pg1/comprobantes`).flush({ elementos: [] });
        const archivo = new File(['imagen'], 'transferencia.png', { type: 'image/png' });
        fixture.detectChanges();
        expect((fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('.ventana__pie button[form="formulario-comprobante-pago"]')?.form?.id).toBe('formulario-comprobante-pago');
        c.archivoComprobante = archivo;
        c.adjuntar({ ...PAGO, estado: 'PENDING' });
        const peticion = http.expectOne({ method: 'POST', url: `${BASE}/pagos/pg1/comprobantes` });
        expect(peticion.request.body instanceof FormData).toBe(true);
        const comprobante = {
            id: 'proof-1', pago_id: 'pg1', tipo_mime: 'image/png', tamano_bytes: 1024,
            sha256: 'a'.repeat(64), antivirus: 'NO_DISPONIBLE', cargado_por: 'usr1',
            cargado_en: '2026-10-14T15:15:00Z', url_contenido: '/api/v1/pagos/comprobantes/proof-1/contenido',
        } as const;
        peticion.flush(comprobante);
        http.expectOne((r) => r.url === `${BASE}/pagos/`).flush({ elementos: [{ ...PAGO, estado: 'PROOF_RECEIVED' }], total: 1 });
        http.expectOne(`${BASE}/pagos/pg1/historial`).flush({ elementos: [EVENTO_HISTORIAL] });
        http.expectOne(`${BASE}/pagos/pg1/comprobantes`).flush({ elementos: [comprobante] });
        fixture.detectChanges();
        expect((document.querySelector('dialog.capa') as HTMLElement).textContent).toContain('Antivirus no disponible al cargar');
        expect((document.querySelector('dialog.capa') as HTMLElement).textContent).toContain('Comprobante cargado');
        expect(c.aviso()).toContain('Comprobante cargado');
    });
});
