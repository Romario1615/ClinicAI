/**
 * Pruebas del formulario de alta y edicion de pacientes.
 *
 * Lo que se verifica y por que importa
 * ------------------------------------
 * **Un doble clic no crea dos pacientes.** La clave de idempotencia se genera
 * al abrir el formulario, no al enviarlo: si se generara al enviar, dos
 * pulsaciones rapidas producirian dos claves y con ellas dos fichas del mismo
 * paciente. Duplicar una ficha no es cosmetico -- la historia clinica queda
 * partida entre dos registros y nadie ve la mitad que falta.
 *
 * **Corregir un dato y reenviar si genera una clave nueva.** Reutilizarla
 * haria que el servidor devolviera la respuesta anterior y la correccion se
 * perderia en silencio, que es peor que un error.
 *
 * **`SIN_DOCUMENTO` envia `null`, no cadena vacia.** El motor exige numero
 * para cualquier otro tipo, y una cadena vacia no es un numero.
 *
 * **El error del backend se muestra y el formulario se puede reintentar.**
 */
import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { EditorPacienteComponent } from './editor-paciente.component';
import { CONFIGURACION, CONFIGURACION_POR_DEFECTO } from '../../nucleo/servicios/configuracion';
import type { Paciente } from '../../nucleo/modelos/dominio';

const BASE = CONFIGURACION_POR_DEFECTO.urlApi;

function paciente(extra: Partial<Paciente> = {}): Paciente {
  return {
    id: 'pac-1',
    tipo_documento: 'CEDULA',
    numero_documento: '9900000001',
    nombre: 'Nombre',
    apellido: 'Apellido',
    telefono_whatsapp: null,
    correo: null,
    fecha_nacimiento: null,
    nivel_verificacion: 'NO_VERIFICADO',
    ...extra,
  };
}

describe('EditorPacienteComponent', () => {
  let fixture: ComponentFixture<EditorPacienteComponent>;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [EditorPacienteComponent],
      providers: [
        provideHttpClient(withXhr()),
        provideHttpClientTesting(),
        { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
      ],
    });
    fixture = TestBed.createComponent(EditorPacienteComponent);
  http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  /** Abre el formulario en alta o en edicion. */
  function abrir(destino: Paciente | null = null): void {
    fixture.componentInstance.paciente = destino;
    fixture.componentInstance.ngOnChanges();
    fixture.detectChanges();
  }

  function escribir(campos: Record<string, string>): void {
    const instancia = fixture.componentInstance as unknown as Record<string, string>;
    for (const [campo, valor] of Object.entries(campos)) {
      instancia[campo] = valor;
    }
  }

  function guardar(): void {
    (fixture.componentInstance as unknown as { guardar(): void }).guardar();
  }

  describe('alta', () => {
    it('envia POST con el cuerpo limpio de espacios', () => {
      abrir();
      escribir({ nombre: '  Ana  ', apellido: ' Perez ', tipo: 'CEDULA', numero: ' 9900000002 ' });
      guardar();

      const peticion = http.expectOne(`${BASE}/pacientes/`);
      expect(peticion.request.method).toBe('POST');
      expect(peticion.request.body.nombre).toBe('Ana');
      expect(peticion.request.body.apellido).toBe('Perez');
      expect(peticion.request.body.numero_documento).toBe('9900000002');
      peticion.flush(paciente());
    });

    it('SIN_DOCUMENTO envia null y no una cadena vacia', () => {
      abrir();
      escribir({ nombre: 'Ana', apellido: 'Perez', tipo: 'SIN_DOCUMENTO', numero: '' });
      guardar();

      const peticion = http.expectOne(`${BASE}/pacientes/`);
      // El motor exige numero para cualquier tipo distinto de SIN_DOCUMENTO,
      // y una cadena vacia no es un numero.
      expect(peticion.request.body.numero_documento).toBeNull();
      peticion.flush(paciente());
    });

    it('los campos opcionales vacios viajan como null', () => {
      abrir();
      escribir({ nombre: 'Ana', apellido: 'Perez', tipo: 'SIN_DOCUMENTO' });
      guardar();

      const cuerpo = http.expectOne(`${BASE}/pacientes/`).request.body;
      expect(cuerpo.telefono_whatsapp).toBeNull();
      expect(cuerpo.correo).toBeNull();
      expect(cuerpo.direccion).toBeNull();
      expect(cuerpo.fecha_nacimiento).toBeNull();
      http.expectNone(`${BASE}/pacientes/`);
    });

    it('emite el paciente creado', () => {
      abrir();
      escribir({ nombre: 'Ana', apellido: 'Perez', tipo: 'SIN_DOCUMENTO' });
      const emitido: Paciente[] = [];
      fixture.componentInstance.guardado.subscribe((p) => emitido.push(p));

      guardar();
      http.expectOne(`${BASE}/pacientes/`).flush(paciente({ nombre: 'Ana' }));

      expect(emitido.length).toBe(1);
      expect(emitido[0].nombre).toBe('Ana');
    });
  });

  describe('idempotencia', () => {
    it('dos envios del mismo cuerpo comparten clave', () => {
      abrir();
      escribir({ nombre: 'Ana', apellido: 'Perez', tipo: 'SIN_DOCUMENTO' });

      guardar();
      const primera = http.expectOne(`${BASE}/pacientes/`);
      const clave = primera.request.headers.get('Idempotency-Key');
      primera.flush(paciente());

      guardar();
      const segunda = http.expectOne(`${BASE}/pacientes/`);
      // Misma clave: el servidor devuelve la ficha ya creada en lugar de
      // crear una segunda. Duplicar una ficha parte la historia clinica entre
      // dos registros y nadie ve la mitad que falta.
      expect(segunda.request.headers.get('Idempotency-Key')).toBe(clave);
      segunda.flush(paciente());
    });

    it('corregir un dato antes de reenviar genera una clave nueva', () => {
      abrir();
      escribir({ nombre: 'Ana', apellido: 'Perez', tipo: 'SIN_DOCUMENTO' });

      guardar();
      const primera = http.expectOne(`${BASE}/pacientes/`);
      const clave = primera.request.headers.get('Idempotency-Key');
      primera.flush(paciente());

      escribir({ nombre: 'Ana Maria' });
      guardar();
      const segunda = http.expectOne(`${BASE}/pacientes/`);
      // Reutilizar la clave haria que el servidor devolviera la respuesta
      // anterior y la correccion se perderia en silencio.
      expect(segunda.request.headers.get('Idempotency-Key')).not.toBe(clave);
      segunda.flush(paciente());
    });

    it('reabrir el formulario empieza con una clave nueva', () => {
      abrir();
      escribir({ nombre: 'Ana', apellido: 'Perez', tipo: 'SIN_DOCUMENTO' });
      guardar();
      const primera = http.expectOne(`${BASE}/pacientes/`);
      const clave = primera.request.headers.get('Idempotency-Key');
      primera.flush(paciente());

      abrir();
      escribir({ nombre: 'Ana', apellido: 'Perez', tipo: 'SIN_DOCUMENTO' });
      guardar();
      const segunda = http.expectOne(`${BASE}/pacientes/`);
      expect(segunda.request.headers.get('Idempotency-Key')).not.toBe(clave);
      segunda.flush(paciente());
    });
  });

  describe('edicion', () => {
    it('precarga los datos y envia PUT a la ficha', () => {
      abrir(paciente({ nombre: 'Ana', telefono_whatsapp: '+593 99 900 0001' }));

      const instancia = fixture.componentInstance as unknown as Record<string, string>;
      expect(instancia['nombre']).toBe('Ana');
      expect(instancia['telefono']).toBe('+593 99 900 0001');

      guardar();
      const peticion = http.expectOne(`${BASE}/pacientes/pac-1`);
      expect(peticion.request.method).toBe('PUT');
      peticion.flush(paciente());
    });
  });

  describe('errores', () => {
    it('muestra el mensaje del backend y libera el formulario', () => {
      abrir();
      escribir({ nombre: 'Ana', apellido: 'Perez', tipo: 'SIN_DOCUMENTO' });
      guardar();

      http
        .expectOne(`${BASE}/pacientes/`)
        .flush(
          { codigo: 'CONFLICTO_ESTADO', mensaje: 'Ya existe un paciente con ese documento.' },
          { status: 409, statusText: 'Conflict' },
        );
      fixture.detectChanges();

      const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
      expect(texto).toContain('Ya existe un paciente con ese documento.');

      // El formulario queda libre: si `ocupado` no se soltara, quien atiende
      // se quedaria con un boton muerto y tendria que recargar.
      guardar();
      http.expectOne(`${BASE}/pacientes/`).flush(paciente());
    });

    it('no envia dos veces mientras una peticion esta en curso', () => {
      abrir();
      escribir({ nombre: 'Ana', apellido: 'Perez', tipo: 'SIN_DOCUMENTO' });

      guardar();
      guardar();

      // Una sola peticion: la segunda pulsacion se ignora mientras la primera
      // sigue viva.
      const peticiones = http.match(`${BASE}/pacientes/`);
      expect(peticiones.length).toBe(1);
      peticiones[0].flush(paciente());
    });
  });
});
