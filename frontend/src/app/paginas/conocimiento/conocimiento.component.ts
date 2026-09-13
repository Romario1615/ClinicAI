/**
 * Base de conocimiento. Conectada al backend real.
 *
 * Lo que esta pantalla tiene que hacer bien
 * -----------------------------------------
 * **No puede improvisar cuando no hay fuente.** Es lo unico que de verdad
 * importa aqui. Si no hay documento aprobado que responda, el backend lo dice
 * en `hay_fuente` y la pantalla muestra ese mensaje tal cual, sin rellenar el
 * hueco con los resultados mas parecidos. Un extracto «casi relacionado»
 * mostrado como respuesta es exactamente como alguien acaba repitiendole a un
 * paciente algo que la clinica nunca aprobo.
 *
 * **Tiene que mostrar de donde sale cada cosa.** Todo extracto lleva su
 * referencia y su version. Quien atiende necesita poder abrir el documento y
 * comprobarlo antes de repetirlo por telefono.
 *
 * **El texto del documento es dato, nunca instruccion.** Se interpola como
 * texto —Angular escapa por defecto— y en ningun caso se inyecta como HTML.
 * Un `innerHTML` aqui convertiria un documento subido por cualquiera en
 * ejecucion de codigo en la sesion de quien lo lee (ADR-0014).
 *
 * **Un documento marcado para revision se ve como tal.** `requiere_revision`
 * significa que la ingesta detecto un intento de inyeccion. Mostrarlo igual
 * que los demas es como una instruccion hostil acaba aprobada sin que nadie
 * la mire.
 *
 * Lo que todavia no hace
 * ----------------------
 * Crear documentos, ingerir versiones, cambiar estado ni resolver la revision
 * de riesgo. Esos endpoints existen y estan probados, pero son escritura sobre
 * el corpus que alimenta al agente, y esta pantalla se queda de momento en
 * lectura y busqueda.
 */
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  CargandoComponent,
  ErrorComponent,
  VacioComponent,
} from '../../compartido/estados.component';
import { ApiService, FalloApi } from '../../nucleo/servicios/api.service';
import type {
  Documento,
  EstadoDocumento,
  RespuestaBusqueda,
} from '../../nucleo/servicios/api.service';

/** Longitud minima de consulta, para no lanzar una busqueda por una letra. */
const MINIMO_CONSULTA = 3;

/**
 * Como se lee cada estado, y que implica para la recuperacion.
 *
 * `recuperable` es el dato operativo: solo `APPROVED` y `PUBLISHED` vigentes
 * llegan al buscador y al agente. Un borrador excelente no responde a nadie, y
 * quien lo escribio necesita verlo.
 */
const ESTADOS: Record<
  EstadoDocumento,
  { texto: string; tono: string; recuperable: boolean; detalle: string }
> = {
  DRAFT: {
    texto: 'Borrador',
    tono: 'neutro',
    recuperable: false,
    detalle: 'En elaboracion. No responde a ninguna consulta todavia.',
  },
  PENDING_REVIEW: {
    texto: 'En revision',
    tono: 'aviso',
    recuperable: false,
    detalle: 'Esperando aprobacion. Aun no responde a consultas.',
  },
  APPROVED: {
    texto: 'Aprobado',
    tono: 'exito',
    recuperable: true,
    detalle: 'Aprobado y recuperable dentro de su vigencia.',
  },
  PUBLISHED: {
    texto: 'Publicado',
    tono: 'exito',
    recuperable: true,
    detalle: 'Publicado y recuperable dentro de su vigencia.',
  },
  ARCHIVED: {
    texto: 'Archivado',
    tono: 'neutro',
    recuperable: false,
    detalle: 'Retirado. No vuelve a recuperarse aunque su texto coincida.',
  },
};

const TIPOS: Record<string, string> = {
  PROTOCOLO: 'Protocolo',
  INSTRUCTIVO: 'Instructivo',
  PREPARACION_EXAMEN: 'Preparacion de examen',
  POLITICA: 'Politica',
  PREGUNTA_FRECUENTE: 'Pregunta frecuente',
  TARIFARIO: 'Tarifario',
};

const ORDEN_ESTADOS: readonly EstadoDocumento[] = [
  'DRAFT',
  'PENDING_REVIEW',
  'APPROVED',
  'PUBLISHED',
  'ARCHIVED',
];

@Component({
  selector: 'app-conocimiento',
  standalone: true,
  imports: [FormsModule, CargandoComponent, ErrorComponent, VacioComponent],
  templateUrl: './conocimiento.component.html',
  styleUrl: './conocimiento.component.scss',
})
export class ConocimientoComponent {
  private readonly api = inject(ApiService);

  // --- Busqueda ---
  protected consulta = '';
  protected readonly consultaAplicada = signal('');
  protected readonly respuesta = signal<RespuestaBusqueda | null>(null);
  protected readonly buscando = signal(false);
  protected readonly errorBusqueda = signal<FalloApi | null>(null);

  // --- Listado ---
  protected readonly documentos = signal<readonly Documento[]>([]);
  protected readonly total = signal(0);
  protected readonly filtroEstado = signal<EstadoDocumento | ''>('');
  protected readonly cargando = signal(true);
  protected readonly error = signal<FalloApi | null>(null);

  /**
   * Titulo de cada documento, sin filtrar.
   *
   * Existe aparte del listado porque el listado se filtra por estado y los
   * resultados de busqueda no. Resolver el titulo contra el listado filtrado
   * funciona mientras no se filtre y, en cuanto alguien elige «Borrador»,
   * convierte los encabezados de los resultados en identificadores internos
   * del tipo `doc:uuid#v1:0`, que no le dicen nada a nadie.
   */
  private readonly titulos = signal<ReadonlyMap<string, string>>(new Map());

  protected readonly minimoConsulta = MINIMO_CONSULTA;
  protected readonly ordenEstados = ORDEN_ESTADOS;

  /** Cierto cuando la consulta escrita es demasiado corta para buscar. */
  protected readonly consultaCorta = computed(
    () => this.consulta.trim().length > 0 && this.consulta.trim().length < MINIMO_CONSULTA,
  );

  /** Cuantos documentos hay por estado, para la barra de resumen. */
  protected readonly resumen = computed(() => {
    const cuenta = new Map<EstadoDocumento, number>();
    for (const documento of this.documentos()) {
      cuenta.set(documento.status, (cuenta.get(documento.status) ?? 0) + 1);
    }
    return ORDEN_ESTADOS.filter((estado) => cuenta.has(estado)).map((estado) => ({
      estado,
      etiqueta: ESTADOS[estado].texto,
      cantidad: cuenta.get(estado) ?? 0,
      recuperable: ESTADOS[estado].recuperable,
    }));
  });

  /** Documentos marcados por la deteccion de inyeccion. Se muestran arriba. */
  protected readonly marcados = computed(() =>
    this.documentos().filter((documento) => documento.requiere_revision === true),
  );

  constructor() {
    this.cargar();
  }

  // ======================================================================
  //  Listado
  // ======================================================================
  protected cargar(): void {
    this.cargando.set(true);
    this.error.set(null);

    const estado = this.filtroEstado();
    this.api.documentos({ estado: estado || undefined, limite: 100 }).subscribe({
      next: (pagina) => {
        this.documentos.set(pagina.elementos);
        this.total.set(pagina.total);
        // El indice de titulos se acumula y nunca se vacia: un documento visto
        // sin filtro sigue teniendo nombre despues de filtrar por otro estado.
        this.titulos.update((previo) => {
          const mapa = new Map(previo);
          for (const documento of pagina.elementos) {
            mapa.set(documento.id, documento.titulo);
          }
          return mapa;
        });
        this.cargando.set(false);
      },
      error: (fallo: FalloApi) => {
        this.error.set(fallo);
        this.cargando.set(false);
      },
    });
  }

  protected cambiarFiltro(estado: string): void {
    this.filtroEstado.set(estado as EstadoDocumento | '');
    this.cargar();
  }

  // ======================================================================
  //  Busqueda
  // ======================================================================
  protected buscar(): void {
    const consulta = this.consulta.trim();
    if (consulta.length < MINIMO_CONSULTA) {
      return;
    }

    this.buscando.set(true);
    this.errorBusqueda.set(null);
    this.respuesta.set(null);

    this.api.buscarConocimiento(consulta).subscribe({
      next: (respuesta) => {
        this.respuesta.set(respuesta);
        this.consultaAplicada.set(consulta);
        this.buscando.set(false);
      },
      error: (fallo: FalloApi) => {
        this.errorBusqueda.set(fallo);
        this.buscando.set(false);
      },
    });
  }

  protected limpiarBusqueda(): void {
    this.consulta = '';
    this.consultaAplicada.set('');
    this.respuesta.set(null);
    this.errorBusqueda.set(null);
  }

  // ======================================================================
  //  Presentacion
  // ======================================================================
  protected estado(clave: EstadoDocumento): (typeof ESTADOS)[EstadoDocumento] {
    return (
      ESTADOS[clave] ?? {
        texto: clave,
        tono: 'neutro',
        recuperable: false,
        detalle: 'Estado desconocido.',
      }
    );
  }

  protected tipo(clave: string): string {
    return TIPOS[clave] ?? clave;
  }

  /**
   * Titulo del documento citado en un resultado.
   *
   * Se resuelve contra el indice sin filtrar. El respaldo no es la referencia
   * del backend —que es un identificador interno, `doc:uuid#v1:0`, y no le
   * dice nada a quien atiende— sino un texto que al menos se entiende.
   */
  protected tituloDe(documentId: string): string {
    return this.titulos().get(documentId) ?? 'Documento de la base de conocimiento';
  }

  /** De que rama de la busqueda hibrida vino el resultado. */
  protected origen(resultado: {
    posicion_vectorial: number | null;
    posicion_textual: number | null;
  }): string {
    const vectorial = resultado.posicion_vectorial !== null;
    const textual = resultado.posicion_textual !== null;
    if (vectorial && textual) {
      return 'por significado y por palabras';
    }
    if (vectorial) {
      return 'por significado';
    }
    if (textual) {
      return 'por palabras';
    }
    return '';
  }

  protected vigencia(documento: Documento): string {
    if (!documento.effective_from && !documento.effective_until) {
      return 'Sin limite de vigencia';
    }
    const desde = documento.effective_from ? `desde ${documento.effective_from}` : '';
    const hasta = documento.effective_until ? `hasta ${documento.effective_until}` : '';
    return [desde, hasta].filter(Boolean).join(' ');
  }
}
