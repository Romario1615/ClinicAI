/**
 * Pantalla de pacientes. Conectada al backend real.
 *
 * Lo que esta pantalla tiene que hacer bien
 * -----------------------------------------
 * **No puede decir «sin resultados» cuando no ha buscado.** El backend ignora
 * los terminos de menos de tres caracteres —una busqueda de una letra
 * devolveria media clinica— y lo declara en `termino_ignorado`. Sin mostrarlo,
 * quien atiende concluiria que el paciente no existe cuando en realidad nunca
 * se le busco. Es el fallo mas facil de cometer aqui y el mas silencioso.
 *
 * **Tiene que mostrar el nivel de verificacion antes de hablar.** Un telefono
 * no verificado no basta para dar informacion por WhatsApp: puede ser
 * familiar, prestado o reasignado. Quien atiende necesita verlo en la fila, no
 * despues de abrir la ficha.
 *
 * **No puede pedir el listado entero.** El ambito ya recorta, pero una clinica
 * con anos de historia tiene decenas de miles de fichas. Se pagina.
 *
 * **No muestra nada clinico.** Este listado es administrativo: documento,
 * contacto y verificacion. Ni diagnosticos, ni medicacion, ni motivo de
 * consulta. El backend tampoco los devuelve por este endpoint, y esa es la
 * garantia real; esto solo evita pedirlos.
 *
 * Lo que todavia no hace
 * ----------------------
 * Crear ni editar pacientes: el backend aun no expone escritura (Fase 2). El
 * boton no existe en lugar de existir deshabilitado, para no prometer algo que
 * no esta.
 */
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  CargandoComponent,
  ErrorComponent,
  VacioComponent,
} from '../../compartido/estados.component';
import {
  ApiService,
  FalloApi,
  filtroBusquedaPaciente,
} from '../../nucleo/servicios/api.service';
import type { PacienteDetalle } from '../../nucleo/servicios/api.service';
import type { Paciente } from '../../nucleo/modelos/dominio';
import { formatearFechaLarga } from '../../nucleo/utilidades/fechas';
import { EditorPacienteComponent } from './editor-paciente.component';
import { FichaPacienteComponent } from '../../compartido/ficha-paciente.component';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
import { SesionService } from '../../nucleo/servicios/sesion.service';

/** Cuantas fichas por pagina. */
const POR_PAGINA = 25;

/**
 * Longitud minima que el backend exige para buscar.
 *
 * Se duplica aqui solo para redactar la ayuda del campo; la decision la toma
 * el backend y se detecta por `termino_ignorado`, nunca contando caracteres
 * en el navegador.
 */
const MINIMO_TERMINO = 3;

/** Como se lee cada nivel de verificacion, y que implica. */
const VERIFICACION: Record<string, { texto: string; detalle: string; tono: string }> = {
  NO_VERIFICADO: {
    texto: 'Sin verificar',
    detalle: 'No se le puede dar informacion por WhatsApp.',
    tono: 'peligro',
  },
  TELEFONO: {
    texto: 'Telefono',
    detalle: 'Verificado por codigo al telefono.',
    tono: 'aviso',
  },
  DOCUMENTO: {
    texto: 'Documento',
    detalle: 'Identidad verificada con documento.',
    tono: 'exito',
  },
  PRESENCIAL: {
    texto: 'Presencial',
    detalle: 'Identidad verificada en la clinica.',
    tono: 'exito',
  },
};

import { TipoDocumentoPipe } from '../../compartido/tipo-documento.pipe';
@Component({
  selector: 'app-pacientes',
  standalone: true,
  imports: [
    FormsModule,
    TipoDocumentoPipe,
    CargandoComponent,
    ErrorComponent,
    VacioComponent,
    EditorPacienteComponent,
    FichaPacienteComponent,
    VentanaFlotanteComponent,
  ],
  templateUrl: './pacientes.component.html',
  styleUrl: './pacientes.component.scss',
})
export class PacientesComponent {
  private readonly api = inject(ApiService);
  protected readonly sesion = inject(SesionService);
  protected readonly editando = signal(false);
  protected readonly paraEditar = signal<PacienteDetalle | null>(null);
  protected readonly avisoGuardado = signal('');

  protected nuevoPaciente(): void { this.paraEditar.set(null); this.editando.set(true); this.avisoGuardado.set(''); }
  protected editarPaciente(paciente: Paciente): void {
    // Se pide el detalle completo: el editor necesita `direccion` y `sexo`,
    // que el listado no devuelve.
    this.api.paciente(paciente.id).subscribe({
      next: (detalle) => {
        this.paraEditar.set(detalle);
        this.pacienteEnFicha.set(null);
        this.editando.set(true);
        this.avisoGuardado.set('');
      },
      error: () => this.avisoGuardado.set('No se pudo abrir el formulario de edicion.'),
    });
  }
  protected pacienteGuardado(): void { this.editando.set(false); this.pacienteEnFicha.set(null); this.avisoGuardado.set('Paciente guardado correctamente.'); this.cargar(); }

  // --- Busqueda ---
  protected termino = '';
  /** Termino con el que se hizo la consulta que se esta mostrando. */
  protected readonly terminoAplicado = signal('');
  protected readonly terminoIgnorado = signal(false);

  // --- Listado ---
  protected readonly pacientes = signal<readonly Paciente[]>([]);
  protected readonly total = signal(0);
  protected readonly pagina = signal(0);
  protected readonly cargando = signal(true);
  protected readonly error = signal<FalloApi | null>(null);

  // --- Ficha ---
  /** A quien se le esta viendo la ficha, si a alguien. */
  protected readonly pacienteEnFicha = signal<Paciente | null>(null);

  protected readonly desde = computed(() => this.pagina() * POR_PAGINA);
  protected readonly hasta = computed(() =>
    Math.min(this.desde() + POR_PAGINA, this.total()),
  );
  protected readonly hayAnterior = computed(() => this.pagina() > 0);
  protected readonly haySiguiente = computed(() => this.hasta() < this.total());
  protected readonly minimoTermino = MINIMO_TERMINO;

  constructor() {
    this.cargar();
  }

  // ======================================================================
  //  Carga
  // ======================================================================
  protected cargar(): void {
    this.cargando.set(true);
    this.error.set(null);

    const termino = this.termino.trim();
    this.api
      .pacientes({
        ...filtroBusquedaPaciente(termino),
        limite: POR_PAGINA,
        desplazamiento: this.desde(),
      })
      .subscribe({
        next: (pagina) => {
          this.pacientes.set(pagina.elementos);
          this.total.set(pagina.total);
          this.terminoAplicado.set(termino);
          // Lo dice el backend, no se deduce contando caracteres aqui: la
          // regla es suya y puede cambiar sin que esta pantalla se entere.
          this.terminoIgnorado.set(pagina.termino_ignorado);
          this.cargando.set(false);
        },
        error: (fallo: FalloApi) => {
          this.error.set(fallo);
          this.cargando.set(false);
        },
      });
  }

  /** Una busqueda nueva siempre vuelve a la primera pagina. */
  protected buscar(): void {
    this.pagina.set(0);
    this.pacienteEnFicha.set(null);
    this.cargar();
  }

  protected limpiar(): void {
    this.termino = '';
    this.buscar();
  }

  protected anterior(): void {
    if (!this.hayAnterior()) {
      return;
    }
    this.pagina.update((valor) => valor - 1);
    this.cargar();
  }

  protected siguiente(): void {
    if (!this.haySiguiente()) {
      return;
    }
    this.pagina.update((valor) => valor + 1);
    this.cargar();
  }

  // ======================================================================
  //  Ficha
  // ======================================================================
  /**
   * Abre la ficha completa.
   *
   * Se pide al backend en lugar de reutilizar la fila del listado: el detalle
   * trae campos que el listado no devuelve, y cada lectura de una ficha queda
   * auditada. Reutilizar la fila ahorraria una peticion y perderia el registro
   * de quien consulto a quien.
   */
  protected abrir(paciente: Paciente): void {
    // Solo se guarda a quien mirar. La peticion del detalle la hace la ficha
    // compartida al montarse, que es donde vive el manejo de su carga y de su
    // error; la lectura sigue quedando auditada igual, porque sigue habiendo
    // una peticion por ficha abierta.
    this.pacienteEnFicha.set(paciente);
  }

  protected cerrarFicha(): void {
    this.pacienteEnFicha.set(null);
  }

  // ======================================================================
  //  Presentacion
  // ======================================================================
  protected verificacion(nivel: string): { texto: string; detalle: string; tono: string } {
    return (
      VERIFICACION[nivel] ?? {
        texto: nivel,
        detalle: 'Nivel de verificacion desconocido.',
        tono: 'aviso',
      }
    );
  }

  /**
   * Fecha de nacimiento legible.
   *
   * Se formatea en la zona de la clinica y no en la del equipo: una fecha de
   * nacimiento desplazada un dia por el huso es un dato incorrecto en una
   * ficha clinica.
   */
  protected nacimiento(valor: string | null): string {
    if (!valor) {
      return 'No registrada';
    }
    return formatearFechaLarga(`${valor}T12:00:00Z`, 'America/Guayaquil');
  }

  protected contacto(paciente: Paciente): string {
    return paciente.telefono_whatsapp ?? paciente.correo ?? 'Sin contacto registrado';
  }
}
