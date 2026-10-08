import type { MockedObject } from "vitest";
import type { WritableSignal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { of, throwError } from 'rxjs';

import type { Especialidad, PerfilProfesional, Sede } from '../../nucleo/modelos/dominio';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { EquipoComponent } from './equipo.component';
import { EquipoService } from './equipo.service';

const SEDE: Sede = { id: 's-1', nombre: 'Centro', direccion: null, zona_horaria: 'America/Guayaquil' };
const SEDE_2: Sede = { id: 's-2', nombre: 'Norte', direccion: null, zona_horaria: 'America/Guayaquil' };
const ESPECIALIDAD: Especialidad = { id: 'e-1', nombre: 'Odontología' };

const PERFIL: PerfilProfesional = {
    id: 'p-1', especialidad_id: 'e-1', nombre: 'Ana', apellido: 'Paz', numero_registro_profesional: 'R-1',
    telefono_whatsapp: null, correo_calendario: null, estado_disponibilidad: 'DISPONIBLE',
    acepta_pacientes_nuevos: true, minutos_preparacion_propio: 10, activo: true,
    sede_ids: ['s-1'], sede_principal_id: 's-1',
};

describe('EquipoComponent', () => {
    let fixture: ComponentFixture<EquipoComponent>;
    let catalogo: MockedObject<CatalogoService>;
    let equipo: MockedObject<EquipoService>;

    beforeEach(() => {
        catalogo = {
            sedes: vi.fn().mockName("CatalogoService.sedes"),
            especialidades: vi.fn().mockName("CatalogoService.especialidades")
        } as unknown as MockedObject<CatalogoService>;
        catalogo.sedes.mockReturnValue(of([SEDE, SEDE_2]));
        catalogo.especialidades.mockReturnValue(of([ESPECIALIDAD]));
        equipo = {
            listar: vi.fn().mockName("EquipoService.listar"),
            crear: vi.fn().mockName("EquipoService.crear"),
            actualizar: vi.fn().mockName("EquipoService.actualizar"),
            invalidarCatalogo: vi.fn().mockName("EquipoService.invalidarCatalogo")
        } as unknown as MockedObject<EquipoService>;
        equipo.listar.mockReturnValue(of([PERFIL]));
        equipo.crear.mockReturnValue(of(PERFIL));
        equipo.actualizar.mockReturnValue(of(PERFIL));
        TestBed.configureTestingModule({
            imports: [EquipoComponent],
            providers: [
                { provide: CatalogoService, useValue: catalogo },
                { provide: EquipoService, useValue: equipo },
            ],
        });
        fixture = TestBed.createComponent(EquipoComponent);
        fixture.detectChanges();
    });

    interface Controles {
        cambiarSede(id: string, marcada: boolean): void;
        guardar(): void;
        editar(perfil: PerfilProfesional): void;
        abrirNuevo(): void;
        nuevo(): void;
        nombreSede(id: string): string;
        etiquetasSedes(ids: readonly string[]): string;
        nombreEspecialidad(id: string): string;
        etiquetaEstado(estado: PerfilProfesional['estado_disponibilidad']): string;
        cancelarFormulario(): void;
        mensaje: () => string;
        error: () => string;
        cargando: () => boolean;
        formularioAbierto: () => boolean;
        guardando: WritableSignal<boolean>;
        form: {
            nombre: string;
            apellido: string;
            especialidad_id: string;
            numero_registro_profesional: string;
            telefono_whatsapp: string;
            correo_calendario: string;
            estado_disponibilidad: 'DISPONIBLE' | 'AGENDA_COMPLETA' | 'AUSENTE';
            acepta_pacientes_nuevos: boolean;
            minutos_preparacion_propio: number;
            activo: boolean;
            sede_ids: string[];
            sede_principal_id: string;
        };
        perfiles: () => readonly PerfilProfesional[];
    }
    const vm = (): Controles => fixture.componentInstance as unknown as Controles;

    it('carga sedes, especialidades y perfiles para la clínica', () => {
        expect(equipo.listar).toHaveBeenCalled();
        expect(vm().perfiles()).toEqual([PERFIL]);
        expect(fixture.nativeElement.textContent).toContain('Ana Paz');
        expect(fixture.nativeElement.textContent).toContain('Centro');
        expect(vm().cargando()).toBe(false);
    });

    it('abre el alta en una ventana accesible y conserva el listado como contexto', () => {
        const elemento = fixture.nativeElement as HTMLElement;
        expect(elemento.querySelector('dialog[open]')).toBeNull();
        elemento.querySelector<HTMLButtonElement>('.lista__agregar')?.click();
        fixture.detectChanges();

        const dialogo = elemento.querySelector<HTMLDialogElement>('dialog[open]');
        expect(dialogo?.getAttribute('aria-modal')).toBe('true');
        expect(dialogo?.getAttribute('aria-label')).toBe('Agregar profesional');
        expect(dialogo?.querySelector('#form-equipo')).not.toBeNull();
        expect(elemento.querySelector('.lista')?.textContent).toContain('Ana Paz');

        dialogo?.querySelector<HTMLButtonElement>('.ventana__pie button[type="button"]')?.click();
        fixture.detectChanges();
        expect(elemento.querySelector('dialog[open]')).toBeNull();
        expect(vm().form.nombre).toBe('');
    });

    it('abre la edición con los datos del profesional y restablece el formulario al cancelar con Escape', async () => {
        const elemento = fixture.nativeElement as HTMLElement;
        elemento.querySelector<HTMLButtonElement>('.fila button')?.click();
        fixture.detectChanges();
        await fixture.whenStable();
        fixture.detectChanges();

        const dialogo = elemento.querySelector<HTMLDialogElement>('dialog[open]');
        expect(dialogo?.getAttribute('aria-label')).toBe('Editar perfil profesional');
        expect(dialogo?.querySelector<HTMLInputElement>('input[name="nombre"]')?.value).toBe('Ana');
        dialogo?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
        fixture.detectChanges();
        expect(elemento.querySelector('dialog[open]')).toBeNull();
        expect(vm().form.nombre).toBe('');
    });

    it('valida los campos obligatorios y permite marcar y desmarcar sedes', () => {
        vm().guardar();
        expect(vm().error()).toContain('Complete nombre');
        expect(equipo.crear).not.toHaveBeenCalled();
        vm().cambiarSede('s-1', true);
        vm().cambiarSede('s-2', true);
        expect(vm().form.sede_ids).toEqual(['s-1', 's-2']);
        expect(vm().form.sede_principal_id).toBe('s-1');
        vm().cambiarSede('s-1', false);
        expect(vm().form.sede_principal_id).toBe('s-2');
        vm().cambiarSede('s-2', false);
        expect(vm().form.sede_principal_id).toBe('');
    });

    it('crea el perfil, normaliza valores opcionales y refresca catálogos', () => {
        Object.assign(vm().form, {
            especialidad_id: 'e-1', nombre: '  Lina ', apellido: ' Sol ', sede_ids: ['s-1'], sede_principal_id: 's-1',
            numero_registro_profesional: ' ', telefono_whatsapp: '', correo_calendario: ' ',
        });
        vm().guardar();
        expect(equipo.crear).toHaveBeenCalledWith(expect.objectContaining({
            nombre: 'Lina', apellido: 'Sol', numero_registro_profesional: null,
            telefono_whatsapp: null, correo_calendario: null,
        }));
        expect(equipo.invalidarCatalogo).toHaveBeenCalled();
        expect(vm().mensaje()).toBe('Profesional agregado al equipo.');
        expect(vm().form.nombre).toBe('');
    });

    it('edita el perfil y cambia su disponibilidad y asignación', () => {
        const inactivo = { ...PERFIL, activo: false, estado_disponibilidad: 'INACTIVO' } as PerfilProfesional;
        vm().editar(inactivo);
        expect(vm().form.estado_disponibilidad).toBe('DISPONIBLE');
        vm().form.nombre = 'Ana María';
        vm().form.sede_ids = ['s-2'];
        vm().form.sede_principal_id = 's-2';
        vm().form.activo = true;
        vm().guardar();
        expect(equipo.actualizar).toHaveBeenCalledWith('p-1', expect.objectContaining({ nombre: 'Ana María', sede_ids: ['s-2'], activo: true }));
        expect(vm().mensaje()).toBe('Perfil profesional actualizado.');
    });

    it('no cierra la ventana mientras se guarda: el resultado no se pierde', () => {
        vm().editar(PERFIL);
        vm().guardando.set(true);
        vm().cancelarFormulario();
        expect(vm().formularioAbierto()).toBe(true);
        vm().guardando.set(false);
        vm().cancelarFormulario();
        expect(vm().formularioAbierto()).toBe(false);
    });

    it('cancela la edición y resuelve etiquetas ausentes sin fallar', () => {
        vm().editar(PERFIL);
        vm().nuevo();
        expect(vm().form.nombre).toBe('');
        expect(vm().nombreSede('ausente')).toBe('Sede');
        expect(vm().etiquetasSedes(['s-1', 'ausente'])).toBe('Centro · Sede');
        expect(vm().nombreEspecialidad('ausente')).toBe('Especialidad');
        expect(vm().etiquetaEstado('INACTIVO')).toBe('INACTIVO');
    });

    it('muestra errores HTTP del servidor y errores inesperados al guardar', () => {
        vm().abrirNuevo();
        equipo.crear.mockReturnValue(throwError(() => new HttpErrorResponse({ status: 409, error: { mensaje: 'Registro duplicado.' } })));
        Object.assign(vm().form, { especialidad_id: 'e-1', nombre: 'Lina', apellido: 'Sol', sede_ids: ['s-1'], sede_principal_id: 's-1' });
        vm().guardar();
        fixture.detectChanges();
        expect(vm().error()).toBe('Registro duplicado.');
        expect((fixture.nativeElement as HTMLElement).querySelector('dialog[open] [role="alert"]')?.textContent).toContain('Registro duplicado.');
        equipo.crear.mockReturnValue(throwError(() => new Error('red')));
        vm().guardar();
        fixture.detectChanges();
        expect(vm().error()).toBe('No se pudo guardar el perfil profesional.');
        expect((fixture.nativeElement as HTMLElement).querySelector('dialog[open] [role="alert"]')?.textContent).toContain('No se pudo guardar');
    });

    it('presenta errores independientes de carga para catálogos y equipo', () => {
        catalogo.sedes.mockReturnValue(throwError(() => new Error('red')));
        const sinSedes = TestBed.createComponent(EquipoComponent);
        sinSedes.detectChanges();
        expect((sinSedes.componentInstance as unknown as Controles).error()).toBe('No se pudieron cargar las sedes.');

        catalogo.sedes.mockReturnValue(of([SEDE]));
        catalogo.especialidades.mockReturnValue(throwError(() => new Error('red')));
        const sinEspecialidades = TestBed.createComponent(EquipoComponent);
        sinEspecialidades.detectChanges();
        expect((sinEspecialidades.componentInstance as unknown as Controles).error()).toBe('No se pudieron cargar las especialidades.');

        catalogo.especialidades.mockReturnValue(of([ESPECIALIDAD]));
        equipo.listar.mockReturnValue(throwError(() => new Error('red')));
        const sinEquipo = TestBed.createComponent(EquipoComponent);
        sinEquipo.detectChanges();
        expect((sinEquipo.componentInstance as unknown as Controles).error()).toBe('No se pudo cargar el equipo profesional.');
    });
});
