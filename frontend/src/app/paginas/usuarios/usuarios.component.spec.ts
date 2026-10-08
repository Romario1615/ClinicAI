/**
 * Usuarios y roles: filtros del personal, ventanas de alta, accesos, rol nuevo
 * y confirmación antes de quitar el acceso. Sin permiso, sin botones.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { UsuariosComponent } from './usuarios.component';
import { BASE, PROVEEDORES_PRUEBA, iniciarSesionCon } from '../../nucleo/pruebas/sesion-sintetica';

const USUARIOS = [
    { id: 'u1', correo: 'ana@example.invalid', nombre: 'Ana', apellido: 'Uno', activo: true, roles: ['Recepcion'], profesional_id: null, ultimo_acceso_en: null },
    { id: 'u2', correo: 'beto@example.invalid', nombre: 'Beto', apellido: 'Dos', activo: false, roles: ['Profesional'], profesional_id: 'p1', especialidad: 'Odontología', ultimo_acceso_en: '2026-10-05T10:00:00Z' },
];
const ROLES = [
    { id: 'r1', codigo: 'recepcion', nombre: 'Recepcion', descripcion: 'Agenda', es_sistema: true, permisos: ['agenda.leer', 'cita.crear'] },
    { id: 'r2', codigo: 'profesional', nombre: 'Profesional', descripcion: null, es_sistema: true, permisos: ['agenda.leer', 'otro.permiso'] },
];
const PERMISOS = [
    { codigo: 'agenda.leer', descripcion: 'Ver la agenda', categoria: 'agenda' },
    { codigo: 'cita.crear', descripcion: 'Crear citas', categoria: 'agenda' },
    { codigo: 'pago.leer', descripcion: 'Ver pagos', categoria: 'pagos' },
];

describe('UsuariosComponent', () => {
    let fixture: ComponentFixture<UsuariosComponent>;
    let http: HttpTestingController;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let c: any;

    function montar(permisos: readonly string[]): void {
        iniciarSesionCon(permisos);
        fixture = TestBed.createComponent(UsuariosComponent);
        c = fixture.componentInstance;
        fixture.detectChanges();
        http.expectOne(`${BASE}/usuarios`).flush(USUARIOS);
        http.expectOne(`${BASE}/usuarios/roles`).flush(ROLES);
        if (permisos.includes('rol.asignar')) {
            http.expectOne(`${BASE}/usuarios/permisos`).flush(PERMISOS);
            http.expectOne((r) => r.url === `${BASE}/usuarios/profesionales`).flush([{ id: 'p1', nombre: 'Pro', apellido: 'Fe' }]);
        }
        fixture.detectChanges();
    }

    beforeEach(() => {
        TestBed.configureTestingModule({ imports: [UsuariosComponent], providers: PROVEEDORES_PRUEBA });
        http = TestBed.inject(HttpTestingController);
    });

    afterEach(() => {
        // Las fotos del equipo tienen su propia prueba.
        http.match((p) => p.url.endsWith('/foto')).forEach((p) => p.flush(null, { status: 204, statusText: 'No Content' }));
        http.verify();
    });

    it('filtra el personal por texto, rol y estado', () => {
        montar(['usuario.leer']);
        expect(c.personal().map((u: {
            id: string;
        }) => u.id)).toEqual(['u1']);
        c.verInactivos = true;
        expect(c.personal().length).toBe(2);
        c.filtroRol = 'Profesional';
        expect(c.personal().map((u: {
            id: string;
        }) => u.id)).toEqual(['u2']);
        c.filtroRol = '';
        c.busqueda = 'beto@';
        expect(c.personal().length).toBe(1);
        expect(c.personasCon(ROLES[0])).toBe(1);
        const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
        expect(texto).not.toContain('Dar acceso a una persona');
        expect(texto).not.toContain('Crear rol');
        c.pestana.set('roles');
        fixture.detectChanges();
        expect((fixture.nativeElement as HTMLElement).textContent).toContain('Del sistema');
        c.pestana.set('matriz');
        fixture.detectChanges();
    });

    it('muestra el área o especialidad y permite buscar por ella', () => {
        montar(['usuario.leer']);
        expect(c.especialidadUsuario(USUARIOS[0])).toBe('Área: Recepción y agenda');
        expect(c.especialidadUsuario(USUARIOS[1])).toBe('Especialidad: Odontología');
        c.verInactivos = true;
        c.busqueda = 'odontología';
        fixture.detectChanges();
        expect(c.personal().map((u: { id: string }) => u.id)).toEqual(['u2']);
        expect((fixture.nativeElement as HTMLElement).textContent).toContain('Especialidad: Odontología');
        expect(c.especialidadesRol(ROLES[1])).toContain('Sin especialidad asignada');
        c.usuarios.set(USUARIOS.map(u => ({ ...u, activo: true })));
        expect(c.especialidadesRol(ROLES[1])).toBe('Especialidades del equipo: Odontología');
    });

    it('da acceso a una persona validando datos, rol y perfil profesional', () => {
        montar(['usuario.leer', 'usuario.crear', 'rol.asignar']);
        c.abrir({ tipo: 'alta' });
        fixture.detectChanges();
        c.crearUsuario(true);
        expect(c.error()).toContain('Revise los datos');
        c.crearUsuario(false);
        expect(c.error()).toContain('al menos un rol');
        c.alternarRol('r2', true);
        expect(c.requiereProfesional()).toBe(true);
        c.crearUsuario(false);
        expect(c.error()).toContain('perfil profesional');
        c.profesionalId = 'p1';
        c.nombre = 'Nueva';
        c.apellido = 'Persona';
        c.correo = 'NUEVA@example.invalid';
        c.contrasenaInicial = 'contrasena-sintetica-larga';
        c.crearUsuario(false);
        const alta = http.expectOne({ method: 'POST', url: `${BASE}/usuarios` });
        expect(alta.request.body.correo).toBe('nueva@example.invalid');
        expect(alta.request.body.profesional_id).toBe('p1');
        alta.flush({});
        expect(c.ventana()).toBeNull();
        expect(c.aviso()).toContain('Cuenta creada');
        http.expectOne(`${BASE}/usuarios`).flush(USUARIOS);
        http.expectOne(`${BASE}/usuarios/roles`).flush(ROLES);
        http.expectOne(`${BASE}/usuarios/permisos`).flush(PERMISOS);
        http.expectOne((r) => r.url === `${BASE}/usuarios/profesionales`).flush([]);
    });

    it('gestiona accesos, crea un rol y pide confirmar antes de quitar el acceso', () => {
        montar(['usuario.leer', 'usuario.crear', 'rol.asignar', 'usuario.desactivar', 'usuario.editar']);
        c.abrir({ tipo: 'accesos', usuario: USUARIOS[0] });
        http.expectOne((r) => r.url === `${BASE}/usuarios/profesionales`).flush([]);
        fixture.detectChanges();
        expect(c.rolesSeleccionados().has('r1')).toBe(true);
        c.guardarRoles(USUARIOS[0]);
        http.expectOne({ method: 'PUT', url: `${BASE}/usuarios/u1/roles` }).flush({ codigo: 'X', mensaje: 'Sin permiso' }, { status: 403, statusText: 'F' });
        expect(c.error()).toBe('Sin permiso');

        c.abrir({ tipo: 'rol-nuevo' });
        fixture.detectChanges();
        c.cambiarNombreRol('Coordinación de agenda');
        expect(c.codigoRol).toBe('coordinacion_de_agenda');
        c.codigoRol = 'manual';
        c.cambiarNombreRol('Otro nombre');
        expect(c.codigoRol).toBe('manual');
        c.crearRol(true);
        expect(c.error()).toContain('código válido');
        c.crearRol(false);
        expect(c.error()).toContain('al menos un permiso');
        const agenda = c.permisosPorCategoria().find((g: {
            categoria: string;
        }) => g.categoria === 'agenda');
        c.alternarGrupo(agenda.permisos, true);
        expect(c.grupoCompleto(agenda.permisos)).toBe(true);
        c.descripcionRol = 'Para recepción';
        c.crearRol(false);
        const rol = http.expectOne({ method: 'POST', url: `${BASE}/usuarios/roles` });
        expect(rol.request.body.permisos).toEqual(['agenda.leer', 'cita.crear']);
        rol.flush({});
        expect(c.pestana()).toBe('roles');
        http.expectOne(`${BASE}/usuarios`).flush(USUARIOS);
        http.expectOne(`${BASE}/usuarios/roles`).flush(ROLES);
        http.expectOne(`${BASE}/usuarios/permisos`).flush(PERMISOS);
        http.expectOne((r) => r.url === `${BASE}/usuarios/profesionales`).flush([]);

        c.abrir({ tipo: 'rol-ver', rol: ROLES[1] });
        fixture.detectChanges();
        const grupos = c.permisosDeRol(ROLES[1]);
        expect(grupos.map((g: {
            nombre: string;
        }) => g.nombre)).toEqual(['Agenda y citas', 'Otros']);

        c.abrir({ tipo: 'quitar', usuario: USUARIOS[0] });
        fixture.detectChanges();
        expect(document.body.textContent).toContain('dejará de poder entrar');
        c.cambiarEstado(USUARIOS[0], false);
        http.expectOne({ method: 'PUT', url: `${BASE}/usuarios/u1/estado` }).flush({});
        expect(c.aviso()).toContain('Acceso quitado');
        http.expectOne(`${BASE}/usuarios`).flush(USUARIOS);
        http.expectOne(`${BASE}/usuarios/roles`).flush(ROLES);
        http.expectOne(`${BASE}/usuarios/permisos`).flush(PERMISOS);
        http.expectOne((r) => r.url === `${BASE}/usuarios/profesionales`).flush([]);
        c.cerrarVentana();
    });
});
