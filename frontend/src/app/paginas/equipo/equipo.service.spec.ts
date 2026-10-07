import type { MockedObject } from "vitest";
import { TestBed } from '@angular/core/testing';
import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { CONFIGURACION } from '../../nucleo/servicios/configuracion';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { EquipoService, type DatosPerfilProfesional } from './equipo.service';

describe('EquipoService', () => {
    let servicio: EquipoService;
    let http: HttpTestingController;
    let catalogo: MockedObject<CatalogoService>;

    beforeEach(() => {
        catalogo = {
            limpiar: vi.fn().mockName("CatalogoService.limpiar")
        } as unknown as MockedObject<CatalogoService>;
        TestBed.configureTestingModule({
            providers: [
                provideHttpClient(withXhr()),
                provideHttpClientTesting(),
                EquipoService,
                { provide: CONFIGURACION, useValue: { urlApi: '/api/v1' } },
                { provide: CatalogoService, useValue: catalogo },
            ],
        });
        servicio = TestBed.inject(EquipoService);
        http = TestBed.inject(HttpTestingController);
    });

    afterEach(() => http.verify());

    it('lista perfiles desde la API protegida del equipo', () => {
        servicio.listar().subscribe((perfiles) => expect(perfiles.length).toBe(0));
        http.expectOne({ method: 'GET', url: '/api/v1/profesionales/gestion' }).flush([]);
    });

    it('crea y actualiza perfiles en los endpoints de administración', () => {
        const datos: DatosPerfilProfesional = {
            especialidad_id: 'e-1', nombre: 'Ana', apellido: 'Paz', numero_registro_profesional: null,
            telefono_whatsapp: null, correo_calendario: null, estado_disponibilidad: 'DISPONIBLE',
            acepta_pacientes_nuevos: true, minutos_preparacion_propio: 0, activo: true,
            sede_ids: ['s-1'], sede_principal_id: 's-1',
        };
        servicio.crear(datos).subscribe((perfil) => expect(perfil.id).toBe('p-1'));
        http.expectOne({ method: 'POST', url: '/api/v1/profesionales/gestion' }).flush({ id: 'p-1', ...datos });

        servicio.actualizar('p-1', datos).subscribe((perfil) => expect(perfil.id).toBe('p-1'));
        http.expectOne({ method: 'PUT', url: '/api/v1/profesionales/gestion/p-1' }).flush({ id: 'p-1', ...datos });
        servicio.invalidarCatalogo();
        expect(catalogo.limpiar).toHaveBeenCalled();
    });
});
