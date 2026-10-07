import { TestBed } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { BASE, PROVEEDORES_PRUEBA } from '../../nucleo/pruebas/sesion-sintetica';
import { AgendaProfesionalesService } from './agenda-profesionales.service';

describe('AgendaProfesionalesService', () => {
    let servicio: AgendaProfesionalesService;
    let http: HttpTestingController;
    const ruta = `${BASE}/profesionales/p-1/agenda?sede_id=s-1`;
    const datos = {
        dia_semana: 2, hora_inicio: '09:00', hora_fin: '13:00',
        granularidad_minutos: 20, vigente_desde: null, vigente_hasta: null,
    };

    beforeEach(() => {
        TestBed.configureTestingModule({ providers: PROVEEDORES_PRUEBA });
        servicio = TestBed.inject(AgendaProfesionalesService);
        http = TestBed.inject(HttpTestingController);
    });

    afterEach(() => http.verify());

    it('lista las franjas de un profesional en la sede', () => {
        servicio.listar('p-1', 's-1').subscribe((items) => expect(items.length).toBe(1));
        http.expectOne(ruta).flush([{ id: 'f-1' }]);
    });

    it('crea una franja enviando sus horas locales y vigencia', () => {
        servicio.crear('p-1', 's-1', datos).subscribe((item) => expect(item.id).toBe('f-1'));
        const request = http.expectOne(ruta);
        expect(request.request.method).toBe('POST');
        expect(request.request.body).toEqual(datos);
        request.flush({ id: 'f-1' });
    });

    it('actualiza y elimina la franja con identidad de profesional, sede y registro', () => {
        servicio.actualizar('p-1', 's-1', 'f-1', datos).subscribe((item) => expect(item.id).toBe('f-1'));
        const actualizar = http.expectOne(`${BASE}/profesionales/p-1/agenda/f-1?sede_id=s-1`);
        expect(actualizar.request.method).toBe('PUT');
        actualizar.flush({ id: 'f-1' });
        servicio.eliminar('p-1', 's-1', 'f-1').subscribe();
        const eliminar = http.expectOne(`${BASE}/profesionales/p-1/agenda/f-1?sede_id=s-1`);
        expect(eliminar.request.method).toBe('DELETE');
        eliminar.flush(null);
    });
});
