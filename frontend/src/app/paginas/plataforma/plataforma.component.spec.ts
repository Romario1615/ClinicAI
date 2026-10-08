import { PROVEEDORES_PRUEBA } from '../../nucleo/pruebas/sesion-sintetica';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { ApiService, type ClinicaPlataforma, type UsuarioPlataforma } from '../../nucleo/servicios/api.service';
import { PlataformaComponent } from './plataforma.component';

interface PlataformaPrueba {
  form: {
    nombre: string;
    identificacion_fiscal: string | null;
    zona_horaria: string;
    idioma: string;
    moneda: string;
    telefono: string | null;
    correo: string | null;
    sede_nombre: string;
    sede_direccion: string | null;
    administrador_nombre: string;
    administrador_apellido: string;
    administrador_correo: string;
    contrasena_inicial: string;
  };
  formSede: { nombre: string; direccion: string | null; telefono: string | null; zona_horaria: string | null };
  clinicaNuevaUsuarioId: string;
  nuevoUsuario: { nombre: string; apellido: string; correo: string; contrasena_inicial: string };
  todasLasSedesDestino: { set(value: boolean): void };
  cambioClinicaNuevaUsuario(id: string): void;
  alternarRolNuevoUsuario(id: string, activo: boolean): void;
  alternarRolDestino(id: string, activo: boolean): void;
  alternarSedeDestino(id: string, activo: boolean): void;
  crear(): void;
  crearUsuario(): void;
  crearSede(): void;
  guardarAsignacion(usuario: UsuarioPlataforma): void;
}

const clinica = {
  id: 'clinica-1', nombre: 'Clínica Centro', activa: true, correo: null,
  cantidad_sedes: 1, cantidad_usuarios: 1,
} as unknown as ClinicaPlataforma;

const usuario = {
  id: 'usuario-1', nombre: 'Ana', apellido: 'Recepción', correo: 'ana@example.invalid',
  clinica_id: clinica.id, clinica_nombre: clinica.nombre, roles: ['Recepción'],
  profesional_id: null, sedes_ids: [], todas_las_sedes: true,
} as unknown as UsuarioPlataforma;

const rolRecepcion = {
  id: 'rol-recepcion', codigo: 'recepcion', nombre: 'Recepción', descripcion: 'Gestiona la agenda.',
} as const;

const sedeBase = {
  id: 'sede-1', nombre: 'Principal', activa: true, direccion: 'Av. Salud 100', telefono: null,
} as const;

const sedeCreada = {
  ...sedeBase, id: 'sede-2', nombre: 'Sucursal Norte', direccion: 'Av. Norte 200',
} as const;

const usuarioCreado = {
  ...usuario, id: 'usuario-2', nombre: 'Luis', apellido: 'Asistente', correo: 'luis@example.invalid',
} as unknown as UsuarioPlataforma;

const clinicaCreada = {
  ...clinica, id: 'clinica-2', nombre: 'Clínica Nueva',
} as unknown as ClinicaPlataforma;

describe('PlataformaComponent', () => {
  let fixture: ComponentFixture<PlataformaComponent>;
  let api: {
    clinicasPlataforma: ReturnType<typeof vi.fn>;
    usuariosPlataforma: ReturnType<typeof vi.fn>;
    sedesPlataforma: ReturnType<typeof vi.fn>;
    rolesPlataforma: ReturnType<typeof vi.fn>;
    profesionalesPlataforma: ReturnType<typeof vi.fn>;
    crearClinicaPlataforma: ReturnType<typeof vi.fn>;
    crearUsuarioPlataforma: ReturnType<typeof vi.fn>;
    crearSedePlataforma: ReturnType<typeof vi.fn>;
    actualizarAsignacionPlataforma: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    api = {
      clinicasPlataforma: vi.fn().mockReturnValue(of([clinica])),
      usuariosPlataforma: vi.fn().mockReturnValue(of([usuario])),
      sedesPlataforma: vi.fn().mockReturnValue(of([sedeBase])),
      rolesPlataforma: vi.fn().mockReturnValue(of([rolRecepcion])),
      profesionalesPlataforma: vi.fn().mockReturnValue(of([])),
      crearClinicaPlataforma: vi.fn().mockReturnValue(of(clinicaCreada)),
      crearUsuarioPlataforma: vi.fn().mockReturnValue(of(usuarioCreado)),
      crearSedePlataforma: vi.fn().mockReturnValue(of(sedeCreada)),
      actualizarAsignacionPlataforma: vi.fn().mockReturnValue(of(usuario)),
    };

    TestBed.configureTestingModule({
      imports: [PlataformaComponent],
      providers: [...PROVEEDORES_PRUEBA,{ provide: ApiService, useValue: api }],
    });
    fixture = TestBed.createComponent(PlataformaComponent);
    fixture.detectChanges();
  });

  function boton(texto: string): HTMLButtonElement {
    const botones = Array.from(fixture.nativeElement.querySelectorAll('button')) as HTMLButtonElement[];
    const encontrado = botones.find((item) => item.textContent?.includes(texto));
    if (!encontrado) throw new Error(`No se encontró el botón ${texto}.`);
    return encontrado;
  }

  it('con listas largas ofrece buscar sin distinguir tildes ni mayúsculas', () => {
    const clinicas = Array.from({ length: 6 }, (_, i) => ({ ...clinica, id: `c-${i}`, nombre: `Clínica Sintética ${i}` }));
    clinicas.push({ ...clinica, id: 'c-medica', nombre: 'Centro Médico Norte' });
    const cuentas = Array.from({ length: 6 }, (_, i) => ({ ...usuario, id: `u-${i}`, nombre: `Persona${i}`, correo: `p${i}@example.invalid` }));
    api.clinicasPlataforma.mockReturnValue(of(clinicas));
    api.usuariosPlataforma.mockReturnValue(of(cuentas));
    fixture = TestBed.createComponent(PlataformaComponent);
    fixture.detectChanges();
    const raiz = fixture.nativeElement as HTMLElement;
    const lista = (nombre: string) => raiz.querySelector(`[aria-label="${nombre}"]`)!.querySelectorAll('article').length;

    const buscarClinica = raiz.querySelector<HTMLInputElement>('input[name="buscarClinica"]')!;
    buscarClinica.value = 'MEDICO';
    buscarClinica.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    expect(lista('Organizaciones registradas')).toBe(1);
    expect(raiz.textContent).toContain('Centro Médico Norte');

    const buscarCuenta = raiz.querySelector<HTMLInputElement>('input[name="buscarCuenta"]')!;
    buscarCuenta.value = 'nadie';
    buscarCuenta.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    expect(lista('Accesos del personal')).toBe(0);
    expect(raiz.textContent).toContain('Ninguna cuenta coincide con «nadie»');
  });

  it('abre y cancela el alta de una clínica sin dejar datos del borrador', () => {
    boton('Registrar clínica').click();
    fixture.detectChanges();
    let dialogo = fixture.nativeElement.querySelector('dialog[open][aria-modal="true"]') as HTMLDialogElement;
    expect(dialogo.getAttribute('aria-label')).toBe('Registrar clínica');

    const nombre = dialogo.querySelector<HTMLInputElement>('input[name="nombre"]');
    expect(nombre).not.toBeNull();
    nombre!.value = 'Borrador de clínica';
    nombre!.dispatchEvent(new Event('input'));
    dialogo.querySelector<HTMLButtonElement>('.ventana__pie button:not([type="submit"])')?.click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('dialog[open]')).toBeNull();
    boton('Registrar clínica').click();
    fixture.detectChanges();
    dialogo = fixture.nativeElement.querySelector('dialog[open]') as HTMLDialogElement;
    expect(dialogo.querySelector<HTMLInputElement>('input[name="nombre"]')?.value).toBe('');
    expect(api.crearClinicaPlataforma).not.toHaveBeenCalled();
  });

  it('abre y cancela el alta de una sede desde la clínica seleccionada', () => {
    boton('Gestionar sedes').click();
    fixture.detectChanges();
    boton('Agregar sucursal').click();
    fixture.detectChanges();

    const dialogo = fixture.nativeElement.querySelector('dialog[open]') as HTMLDialogElement;
    expect(dialogo.getAttribute('aria-label')).toBe('Agregar sede');
    expect(dialogo.querySelector('select[name="zonaSede"]')).not.toBeNull();
    const componente = fixture.componentInstance as unknown as PlataformaPrueba;
    componente.formSede = { nombre: 'Sucursal Norte', direccion: 'Av. Norte 200', telefono: null, zona_horaria: null };
    fixture.detectChanges();
    componente.crearSede();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('dialog[open]')).toBeNull();
    expect(api.crearSedePlataforma).toHaveBeenCalledWith(clinica.id, expect.objectContaining({ nombre: 'Sucursal Norte' }));
    expect(fixture.nativeElement.textContent).toContain('Sede Sucursal Norte creada.');
  });

  it('guarda roles y sedes de una cuenta desde su ventana de asignación', () => {
    boton('Clínica y módulos').click();
    fixture.detectChanges();

    const dialogo = fixture.nativeElement.querySelector('dialog[open]') as HTMLDialogElement;
    expect(dialogo.getAttribute('aria-label')).toBe('Ana Recepción');
    expect(dialogo.textContent).toContain('Ámbito de sedes');
    const componente = fixture.componentInstance as unknown as PlataformaPrueba;
    componente.alternarRolDestino(rolRecepcion.id, false);
    componente.alternarRolDestino(rolRecepcion.id, true);
    componente.todasLasSedesDestino.set(false);
    componente.alternarSedeDestino(sedeBase.id, true);
    fixture.detectChanges();
    componente.guardarAsignacion(usuario);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('dialog[open]')).toBeNull();
    expect(api.actualizarAsignacionPlataforma).toHaveBeenCalledWith(usuario.id, expect.objectContaining({
      clinica_id: clinica.id,
      roles: [rolRecepcion.id],
      sedes_ids: [sedeBase.id],
    }));
    expect(fixture.nativeElement.textContent).toContain('Acceso actualizado para Ana Recepción.');

    boton('Clínica y módulos').click();
    fixture.detectChanges();
    (fixture.nativeElement.querySelector('.ventana__pie button') as HTMLButtonElement | null)?.click();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('dialog[open]')).toBeNull();
  });

  it('crea una cuenta con rol y clínica desde una ventana centrada', () => {
    boton('Dar acceso a una persona').click();
    fixture.detectChanges();
    let dialogo = fixture.nativeElement.querySelector('dialog[open]') as HTMLDialogElement;
    expect(dialogo.getAttribute('aria-label')).toBe('Dar acceso a una persona');
    expect(dialogo.querySelector('input[name="contrasenaUsuario"]')).not.toBeNull();
    const componente = fixture.componentInstance as unknown as PlataformaPrueba;
    componente.clinicaNuevaUsuarioId = clinica.id;
    componente.cambioClinicaNuevaUsuario(clinica.id);
    fixture.detectChanges();

    componente.alternarRolNuevoUsuario(rolRecepcion.id, true);
    componente.nuevoUsuario = { nombre: 'Luis', apellido: 'Asistente', correo: 'luis@example.invalid', contrasena_inicial: 'Temporal!Segura123' };
    fixture.detectChanges();
    componente.crearUsuario();
    fixture.detectChanges();

    expect(api.crearUsuarioPlataforma).toHaveBeenCalledWith(expect.objectContaining({
      clinica_id: clinica.id, nombre: 'Luis', correo: 'luis@example.invalid', roles: [rolRecepcion.id],
    }));
    expect(fixture.nativeElement.querySelector('dialog[open]')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Cuenta creada y vinculada a Clínica Centro.');

    boton('Dar acceso a una persona').click();
    fixture.detectChanges();
    dialogo = fixture.nativeElement.querySelector('dialog[open]') as HTMLDialogElement;
    expect(dialogo.querySelector<HTMLInputElement>('input[name="contrasenaUsuario"]')?.value).toBe('');
    dialogo.querySelector<HTMLButtonElement>('.ventana__pie button')?.click();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('dialog[open]')).toBeNull();
  });

  it('registra la clínica y la sede principal en una sola solicitud', () => {
    boton('Registrar clínica').click();
    fixture.detectChanges();
    const dialogo = fixture.nativeElement.querySelector('dialog[open]') as HTMLDialogElement;
    expect(dialogo.getAttribute('aria-label')).toBe('Registrar clínica');
    const componente = fixture.componentInstance as unknown as PlataformaPrueba;
    componente.form = {
      nombre: 'Clínica Nueva', identificacion_fiscal: null, zona_horaria: 'America/Guayaquil',
      idioma: 'es', moneda: 'USD', telefono: null, correo: null, sede_nombre: 'Sede principal',
      sede_direccion: null, administrador_nombre: 'Sara', administrador_apellido: 'Admin',
      administrador_correo: 'sara@example.invalid', contrasena_inicial: 'Temporal!Segura123',
    };
    fixture.detectChanges();
    componente.crear();
    fixture.detectChanges();

    expect(api.crearClinicaPlataforma).toHaveBeenCalledWith(expect.objectContaining({
      nombre: 'Clínica Nueva', sede_nombre: 'Sede principal', administrador_correo: 'sara@example.invalid',
    }));
    expect(fixture.nativeElement.textContent).toContain('Clínica Clínica Nueva creada con sede y administrador inicial.');
    expect(fixture.nativeElement.querySelector('dialog[open]')).toBeNull();
  });
});
