import type { MockedObject } from "vitest";
import { provideHttpClient, withXhr } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { CONFIGURACION, CONFIGURACION_POR_DEFECTO } from '../../nucleo/servicios/configuracion';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { CatalogoComponent } from './catalogo.component';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import type { Consultorio, Especialidad, Sede } from '../../nucleo/modelos/dominio';

const SEDE: Sede = { id: 'sede-1', nombre: 'Centro', direccion: null, zona_horaria: 'America/Guayaquil' };
const CONSULTORIO: Consultorio = {
    id: 'consultorio-1', sede_id: SEDE.id, nombre: 'Sala de imagen', tipo: 'IMAGEN', capacidad: 2, activo: true,
};
const ESPECIALIDAD: Especialidad = { id: 'e1', nombre: 'Ortodoncia', codigo: 'ORT', descripcion: 'Alineación dental', activa: true };
const SERVICIO = {
    id: 'servicio-1', especialidad_id: 'e1', nombre: 'Revisión', descripcion: null,
    duracion_minutos: 30, minutos_preparacion: 0, precio: null, moneda: 'USD', activo: true,
    requiere_pago_previo: false, instrucciones_preparacion: null, tipo_consultorio_requerido: null,
};

describe('CatalogoComponent', () => {
    let fixture: ComponentFixture<CatalogoComponent>;
    let catalogo: MockedObject<CatalogoService>;
    let sesion: MockedObject<SesionService>;

    beforeEach(() => {
        catalogo = {
            sedes: vi.fn().mockName("CatalogoService.sedes"),
            especialidades: vi.fn().mockName("CatalogoService.especialidades"),
            especialidadesGestion: vi.fn().mockName("CatalogoService.especialidadesGestion"),
            crearEspecialidad: vi.fn().mockName("CatalogoService.crearEspecialidad"),
            actualizarEspecialidad: vi.fn().mockName("CatalogoService.actualizarEspecialidad"),
            cambiarEstadoEspecialidad: vi.fn().mockName("CatalogoService.cambiarEstadoEspecialidad"),
            servicios: vi.fn().mockName("CatalogoService.servicios"),
            serviciosGestion: vi.fn().mockName("CatalogoService.serviciosGestion"),
            crearServicio: vi.fn().mockName("CatalogoService.crearServicio"),
            actualizarServicio: vi.fn().mockName("CatalogoService.actualizarServicio"),
            cambiarEstadoServicio: vi.fn().mockName("CatalogoService.cambiarEstadoServicio"),
            profesionales: vi.fn().mockName("CatalogoService.profesionales"),
            consultorios: vi.fn().mockName("CatalogoService.consultorios"),
            consultoriosGestion: vi.fn().mockName("CatalogoService.consultoriosGestion"),
            crearConsultorio: vi.fn().mockName("CatalogoService.crearConsultorio"),
            actualizarConsultorio: vi.fn().mockName("CatalogoService.actualizarConsultorio"),
            cambiarEstadoConsultorio: vi.fn().mockName("CatalogoService.cambiarEstadoConsultorio")
        } as unknown as MockedObject<CatalogoService>;
        catalogo.sedes.mockReturnValue(of([SEDE]));
        catalogo.especialidades.mockReturnValue(of([]));
        catalogo.especialidadesGestion.mockReturnValue(of([]));
        catalogo.crearEspecialidad.mockReturnValue(of(ESPECIALIDAD));
        catalogo.actualizarEspecialidad.mockReturnValue(of(ESPECIALIDAD));
        catalogo.cambiarEstadoEspecialidad.mockReturnValue(of({ ...ESPECIALIDAD, activa: false }));
        catalogo.servicios.mockReturnValue(of([]));
        catalogo.serviciosGestion.mockReturnValue(of([]));
        catalogo.crearServicio.mockReturnValue(of(SERVICIO));
        catalogo.actualizarServicio.mockReturnValue(of(SERVICIO));
        catalogo.cambiarEstadoServicio.mockReturnValue(of({ ...SERVICIO, activo: false }));
        catalogo.profesionales.mockReturnValue(of([]));
        catalogo.consultorios.mockReturnValue(of([]));
        catalogo.consultoriosGestion.mockReturnValue(of([]));
        catalogo.crearConsultorio.mockReturnValue(of(CONSULTORIO));
        catalogo.actualizarConsultorio.mockReturnValue(of(CONSULTORIO));
        catalogo.cambiarEstadoConsultorio.mockReturnValue(of(CONSULTORIO));
        sesion = {
            tienePermiso: vi.fn().mockName("SesionService.tienePermiso")
        } as unknown as MockedObject<SesionService>;
        sesion.tienePermiso.mockReturnValue(true);

        TestBed.configureTestingModule({
            imports: [CatalogoComponent],
            providers: [
                { provide: CatalogoService, useValue: catalogo },
                { provide: SesionService, useValue: sesion },
                // Módulos por especialidad pide su configuración al API; aquí no se prueba.
                provideHttpClient(withXhr()),
                provideHttpClientTesting(),
                { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
            ],
        });
        fixture = TestBed.createComponent(CatalogoComponent);
        fixture.detectChanges();
    });

    it('crea el consultorio de la sede seleccionada y confirma el resultado', () => {
        const component = fixture.componentInstance as unknown as {
            form: {
                nombre: string;
                tipo: 'CONSULTA' | 'PROCEDIMIENTOS' | 'IMAGEN' | 'LABORATORIO' | 'OTRO';
                capacidad: number;
            };
            guardar(): void;
        };
        component.form = { nombre: '  Sala de imagen  ', tipo: 'IMAGEN', capacidad: 2 };
        component.guardar();
        fixture.detectChanges();

        expect(catalogo.crearConsultorio).toHaveBeenCalledWith({
            sede_id: SEDE.id, nombre: 'Sala de imagen', tipo: 'IMAGEN', capacidad: 2,
        });
        expect(fixture.nativeElement.textContent).toContain('Consultorio creado.');
    });

    it('abre los formularios de catálogo en ventanas modales accesibles', () => {
        const boton = (texto: string): HTMLButtonElement => {
            const encontrado = Array.from(
                (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
            ).find((elemento) => elemento.textContent?.trim() === texto);
            if (!encontrado) throw new Error(`No se encontró el botón ${texto}.`);
            return encontrado as HTMLButtonElement;
        };

        boton('Nuevo consultorio').click();
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('dialog[open][aria-label="Nuevo consultorio"]')).not.toBeNull();
        expect(fixture.nativeElement.querySelector('#form-consultorio')).not.toBeNull();
        const dialogoConsultorio = fixture.nativeElement.querySelector('dialog[open]');
        dialogoConsultorio.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('dialog[open]')).toBeNull();

        boton('Nueva especialidad').click();
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('dialog[open][aria-label="Nueva especialidad"]')).not.toBeNull();
        boton('Cancelar').click();
        fixture.detectChanges();

        boton('Nuevo servicio').click();
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('dialog[open][aria-label="Nuevo servicio"]')).not.toBeNull();
    });

    it('edita, reactiva y permite limpiar el formulario', () => {
        const component = fixture.componentInstance as unknown as {
            form: {
                nombre: string;
                tipo: 'CONSULTA' | 'PROCEDIMIENTOS' | 'IMAGEN' | 'LABORATORIO' | 'OTRO';
                capacidad: number;
            };
            editar(sala: Consultorio): void;
            guardar(): void;
            nuevo(): void;
            cambiarEstado(sala: Consultorio): void;
            etiquetaTipo(tipo: Consultorio['tipo']): string;
        };
        component.editar(CONSULTORIO);
        component.form.nombre = 'Sala radiológica';
        component.guardar();
        component.nuevo();
        component.cambiarEstado({ ...CONSULTORIO, activo: false });

        expect(catalogo.actualizarConsultorio).toHaveBeenCalledWith(CONSULTORIO.id, {
            nombre: 'Sala radiológica', tipo: 'IMAGEN', capacidad: 2,
        });
        expect(catalogo.cambiarEstadoConsultorio).toHaveBeenCalledWith(CONSULTORIO.id, true);
        expect(component.form.nombre).toBe('');
        expect(component.etiquetaTipo('IMAGEN')).toBe('Imagen');
    });

    it('administra especialidades y servicios desde sus catálogos', () => {
        const component = fixture.componentInstance as unknown as {
            formEspecialidad: {
                nombre: string;
                codigo: string;
                descripcion: string;
            };
            guardarEspecialidad(): void;
            editarEspecialidad(item: Especialidad): void;
            cambiarEstadoEspecialidad(item: Especialidad): void;
            formServicio: {
                especialidad_id: string;
                nombre: string;
                descripcion: string | null;
                duracion_minutos: number;
                minutos_preparacion: number;
                precio: number | null;
                moneda: string;
                requiere_pago_previo: boolean;
                instrucciones_preparacion: string | null;
                tipo_consultorio_requerido: 'CONSULTA' | 'PROCEDIMIENTOS' | 'IMAGEN' | 'LABORATORIO' | 'OTRO' | null;
            };
            guardarServicio(): void;
            editarServicio(item: typeof SERVICIO): void;
            cambiarEstadoServicio(item: typeof SERVICIO): void;
        };
        component.formEspecialidad = { nombre: 'Ortodoncia', codigo: 'ort', descripcion: 'Alineación dental' };
        component.guardarEspecialidad();
        component.editarEspecialidad(ESPECIALIDAD);
        component.formEspecialidad.nombre = 'Ortodoncia clínica';
        component.guardarEspecialidad();
        component.cambiarEstadoEspecialidad(ESPECIALIDAD);

        component.formServicio = {
            especialidad_id: 'e1', nombre: 'Revisión', descripcion: null, duracion_minutos: 30,
            minutos_preparacion: 0, precio: null, moneda: 'USD', requiere_pago_previo: false,
            instrucciones_preparacion: null, tipo_consultorio_requerido: null,
        };
        component.guardarServicio();
        component.editarServicio(SERVICIO);
        component.formServicio.nombre = 'Revisión inicial';
        component.guardarServicio();
        component.cambiarEstadoServicio(SERVICIO);

        expect(catalogo.crearEspecialidad).toHaveBeenCalledWith({ nombre: 'Ortodoncia', codigo: 'ort', descripcion: 'Alineación dental' });
        expect(catalogo.actualizarEspecialidad).toHaveBeenCalledWith(ESPECIALIDAD.id, { nombre: 'Ortodoncia clínica', codigo: 'ORT', descripcion: 'Alineación dental' });
        expect(catalogo.cambiarEstadoEspecialidad).toHaveBeenCalledWith(ESPECIALIDAD.id, false);
        expect(catalogo.crearServicio).toHaveBeenCalledWith(expect.objectContaining({ nombre: 'Revisión', especialidad_id: 'e1' }));
        expect(catalogo.actualizarServicio).toHaveBeenCalledWith(SERVICIO.id, expect.objectContaining({ nombre: 'Revisión inicial', especialidad_id: 'e1' }));
        expect(catalogo.cambiarEstadoServicio).toHaveBeenCalledWith(SERVICIO.id, false);
    });

    it('no muestra acciones de administración sin el permiso de sede', () => {
        sesion.tienePermiso.mockReturnValue(false);
        fixture.destroy();
        fixture = TestBed.createComponent(CatalogoComponent);
        fixture.detectChanges();

        expect(fixture.nativeElement.textContent).not.toContain('Crear consultorio');
        expect(catalogo.consultorios).toHaveBeenCalled();
        // El host ya no desplaza: lo hacen los marcos de cada pestaña, que son
        // los que necesitan el foco de teclado.
        expect(fixture.nativeElement.getAttribute('role')).toBe('region');
        expect(fixture.nativeElement.getAttribute('aria-label')).toBe('Catálogo de la clínica');
        expect((fixture.nativeElement as HTMLElement).querySelector('#catalogo-panel-sedes .desplazable')?.getAttribute('tabindex')).toBe('0');
        // Sin gestión de especialidades no se ofrecen sus pestañas.
        const pestanas = Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('[role="tab"]')).map((p) => p.id);
        expect(pestanas).toEqual(['catalogo-pestana-sedes', 'catalogo-pestana-servicios', 'catalogo-pestana-profesionales']);
    });

    it('muestra una parte del catálogo a la vez', () => {
        const raiz = fixture.nativeElement as HTMLElement;
        const visibles = () => Array.from(raiz.querySelectorAll<HTMLElement>('[role="tabpanel"]')).filter((p) => !p.hidden).map((p) => p.id);
        expect(visibles()).toEqual(['catalogo-panel-sedes']);
        raiz.querySelector<HTMLElement>('#catalogo-pestana-servicios')?.click();
        fixture.detectChanges();
        expect(visibles()).toEqual(['catalogo-panel-servicios']);
    });

    it('no cierra la ventana mientras se guarda', () => {
        const c = fixture.componentInstance as unknown as {
            abrirNuevoServicio(): void;
            cerrarVentana(): void;
            guardando: { set(valor: boolean): void };
            ventanaFormulario(): string | null;
        };
        c.abrirNuevoServicio();
        c.guardando.set(true);
        c.cerrarVentana();
        expect(c.ventanaFormulario()).toBe('servicio');
        c.guardando.set(false);
        c.cerrarVentana();
        expect(c.ventanaFormulario()).toBeNull();
    });
});
