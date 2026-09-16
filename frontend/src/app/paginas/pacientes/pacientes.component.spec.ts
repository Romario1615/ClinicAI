/**
 * Pruebas de la pantalla de pacientes.
 *
 * Lo que se verifica y por que importa
 * ------------------------------------
 * **Los tres vacios son distintos y no se pueden confundir.** «No se busco»,
 * «no hay coincidencias» y «su ambito esta vacio» significan cosas diferentes
 * y llevan a decisiones diferentes. Mostrar el mensaje equivocado hace que
 * quien atiende concluya que un paciente no esta registrado cuando en realidad
 * nunca se le busco, y a partir de ahi le crea una ficha duplicada.
 *
 * Esto no es hipotetico: la primera version de esta pantalla decia «lo que ve
 * debajo es el listado completo» cuando el termino se ignoraba, y el backend
 * en ese caso devuelve **cero elementos**. Las dos afirmaciones eran falsas a
 * la vez.
 *
 * **El nivel de verificacion se muestra en la fila.** Un telefono sin
 * verificar no basta para dar informacion por WhatsApp, y quien atiende tiene
 * que verlo antes de hablar, no despues de abrir la ficha.
 *
 * **La paginacion no pide el listado entero.**
 */
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { PacientesComponent } from './pacientes.component';
import { CONFIGURACION, CONFIGURACION_POR_DEFECTO } from '../../nucleo/servicios/configuracion';
import type { Paciente } from '../../nucleo/modelos/dominio';

const BASE = CONFIGURACION_POR_DEFECTO.urlApi;

function paciente(sufijo: string, nivel = 'NO_VERIFICADO'): Paciente {
  return {
    id: `id-${sufijo}`,
    tipo_documento: 'CEDULA',
    numero_documento: `99000000${sufijo}`,
    nombre: `Nombre${sufijo}`,
    apellido: `Apellido${sufijo}`,
    telefono_whatsapp: '+593 99 900 0000',
    correo: null,
    fecha_nacimiento: '1990-05-12',
    nivel_verificacion: nivel,
  };
}

function pagina(elementos: readonly Paciente[], extra: Record<string, unknown> = {}) {
  return {
    elementos,
    total: elementos.length,
    limite: 25,
    desplazamiento: 0,
    termino_ignorado: false,
    ...extra,
  };
}

describe('PacientesComponent', () => {
  let fixture: ComponentFixture<PacientesComponent>;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [PacientesComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
      ],
    });
    fixture = TestBed.createComponent(PacientesComponent);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  /** Resuelve la carga inicial que dispara el constructor. */
  function responderCargaInicial(cuerpo: object): void {
    fixture.detectChanges();
    http.expectOne((peticion) => peticion.url === `${BASE}/pacientes/`).flush(cuerpo);
    fixture.detectChanges();
  }

  function texto(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  it('pide la primera pagina al abrirse, no el listado entero', () => {
    fixture.detectChanges();
    const peticion = http.expectOne((p) => p.url === `${BASE}/pacientes/`);
    expect(peticion.request.params.get('limite')).toBe('25');
    peticion.flush(pagina([paciente('1')]));
  });

  it('muestra el listado con el nivel de verificacion de cada fila', () => {
    responderCargaInicial(pagina([paciente('1', 'NO_VERIFICADO')]));

    expect(texto()).toContain('Apellido1, Nombre1');
    // El texto legible, no el codigo: «NO_VERIFICADO» no le dice nada a
    // quien atiende el mostrador.
    expect(texto()).toContain('Sin verificar');
  });

  describe('los tres vacios', () => {
    it('cuando el termino se ignoro dice que NO se busco, no que no haya nadie', () => {
      responderCargaInicial(pagina([], { termino_ignorado: true }));

      expect(texto()).toContain('no llegó a hacerse');
      expect(texto()).toContain('La búsqueda no se realizó');
      // Lo que no debe decir bajo ningun concepto:
      expect(texto()).not.toContain('No hay pacientes en su ámbito');
      expect(texto()).not.toContain('Sin coincidencias');
    });

    it('cuando se busco y no hay coincidencias lo dice como tal', () => {
      responderCargaInicial(pagina([paciente('1')]));

      fixture.componentInstance['termino'] = 'perez';
      fixture.componentInstance['buscar']();
      http
        .expectOne((p) => p.url === `${BASE}/pacientes/`)
        .flush(pagina([], { termino_ignorado: false }));
      fixture.detectChanges();

      expect(texto()).toContain('Sin coincidencias');
      expect(texto()).toContain('perez');
      expect(texto()).not.toContain('La búsqueda no se realizó');
    });

    it('sin termino y sin resultados es que el ambito esta vacio', () => {
      responderCargaInicial(pagina([]));

      expect(texto()).toContain('No hay pacientes en su ámbito');
      expect(texto()).not.toContain('Sin coincidencias');
      expect(texto()).not.toContain('La búsqueda no se realizó');
    });
  });

  it('una busqueda nueva vuelve a la primera pagina', () => {
    responderCargaInicial(pagina([paciente('1')], { total: 60 }));

    fixture.componentInstance['siguiente']();
    const segunda = http.expectOne((p) => p.url === `${BASE}/pacientes/`);
    expect(segunda.request.params.get('desplazamiento')).toBe('25');
    segunda.flush(pagina([paciente('2')], { total: 60, desplazamiento: 25 }));
    fixture.detectChanges();

    fixture.componentInstance['termino'] = 'lopez';
    fixture.componentInstance['buscar']();
    const busqueda = http.expectOne((p) => p.url === `${BASE}/pacientes/`);
    // Si conservara el desplazamiento, la primera busqueda saltaria los 25
    // primeros resultados y pareceria que faltan pacientes.
    expect(busqueda.request.params.get('desplazamiento')).toBe('0');
    expect(busqueda.request.params.get('termino')).toBe('lopez');
    busqueda.flush(pagina([]));
  });

  it('la ficha se pide al backend y no se arma con la fila del listado', () => {
    responderCargaInicial(pagina([paciente('1')]));

    fixture.componentInstance['abrir'](paciente('1'));
    fixture.detectChanges();

    // Cada lectura de una ficha queda auditada; reutilizar la fila ahorraria
    // la peticion y perderia el registro de quien consulto a quien.
    //
    // La peticion la hace ahora la ficha compartida al montarse dentro de la
    // ventana flotante, no esta pantalla. Lo que importa se conserva: hay una
    // peticion por ficha abierta, asi que la lectura sigue quedando registrada.
    const detalle = http.expectOne(`${BASE}/pacientes/id-1`);
    detalle.flush({ ...paciente('1'), sexo: 'F', direccion: 'Calle sintetica', activo: true });
    fixture.detectChanges();

    // La ficha trae ademas el historial de citas del paciente.
    http
      .expectOne((p) => p.url === `${BASE}/agenda/citas`)
      .flush({ elementos: [], total: 0, limite: 50, desplazamiento: 0 });
    fixture.detectChanges();

    // Se abre encima, no al final de la tabla.
    expect(
      (fixture.nativeElement as HTMLElement).querySelector('[role="dialog"]'),
    ).not.toBeNull();
    // Y declara su limite de ambito en la propia pantalla.
    expect(texto()).toContain('administrativo');
  });

  it('un error al cargar se muestra con su codigo, sin dejar la tabla a medias', () => {
    fixture.detectChanges();
    http
      .expectOne((p) => p.url === `${BASE}/pacientes/`)
      .flush(
        { codigo: 'LIMITE_TASA_EXCEDIDO', mensaje: 'Demasiadas peticiones.' },
        { status: 429, statusText: 'Too Many Requests' },
      );
    fixture.detectChanges();

    expect(texto()).toContain('No se pudo cargar el listado');
    expect(texto()).toContain('LIMITE_TASA_EXCEDIDO');
  });
});
