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
 * Carga y ciclo de vida
 * ---------------------
 * Con `conocimiento.cargar` se crean documentos, se suben versiones y se
 * envian a revision. Aprobar y publicar aparecen solo con
 * `conocimiento.aprobar`. Esconder botones **no es el control**: el backend
 * revalida cada permiso y cada transicion (CLAUDE.md, regla 7).
 *
 * Lo que todavia no hace: archivar ni fijar vigencias. Archivar es
 * irreversible y necesita su propia pantalla. La revision de riesgo de un
 * documento marcado se hace en `RevisionRiesgoComponent`, que muestra el texto
 * antes de dejar marcarlo como revisado.
 */
import { Component, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { forkJoin } from 'rxjs';

import {
  CargandoComponent,
  ErrorComponent,
  VacioComponent,
} from '../../compartido/estados.component';
import { IconoComponent } from '../../compartido/icono.component';
import {
  ApiService,
  FalloApi,
  type OpcionesPermisosDocumento,
  type PermisoDocumento,
  type TipoPrincipalDocumento,
} from '../../nucleo/servicios/api.service';
import { PERMISOS } from '../../nucleo/servicios/configuracion';
import { OperacionesService } from '../../nucleo/servicios/operaciones.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { CargarDocumentoComponent } from './cargar-documento.component';
import { RevisionRiesgoComponent } from './revision-riesgo.component';
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

/** Accion de ciclo de vida que se ofrece en una fila. */
interface AccionEstado {
  readonly destino: EstadoDocumento;
  readonly texto: string;
  readonly principal: boolean;
}

/**
 * Transiciones que se ofrecen desde cada estado, con el permiso que exigen.
 *
 * Es un subconjunto de `TRANSICIONES` del backend: archivar no se ofrece desde
 * aqui. Si este mapa y el backend divergieran, el backend responde 409 y la
 * pantalla muestra el error; no hay forma de forzar una transicion invalida.
 */
const ACCIONES: Partial<
  Record<EstadoDocumento, readonly (AccionEstado & { readonly aprobar: boolean })[]>
> = {
  DRAFT: [{ destino: 'PENDING_REVIEW', texto: 'Enviar a revisión', principal: true, aprobar: false }],
  PENDING_REVIEW: [
    { destino: 'APPROVED', texto: 'Aprobar', principal: true, aprobar: true },
    { destino: 'DRAFT', texto: 'Devolver a borrador', principal: false, aprobar: false },
  ],
  APPROVED: [
    { destino: 'DRAFT', texto: 'Retirar para corregir', principal: false, aprobar: false },
    { destino: 'PUBLISHED', texto: 'Publicar', principal: true, aprobar: true },
  ],
  PUBLISHED: [{ destino: 'DRAFT', texto: 'Retirar para corregir', principal: false, aprobar: false }],
};

const ORDEN_ESTADOS: readonly EstadoDocumento[] = [
  'DRAFT',
  'PENDING_REVIEW',
  'APPROVED',
  'PUBLISHED',
  'ARCHIVED',
];

const TIPOS_PRINCIPAL: Readonly<Record<TipoPrincipalDocumento, string>> = {
  ROL: 'Rol',
  USUARIO: 'Usuario',
  SEDE: 'Sede',
  ESPECIALIDAD: 'Especialidad',
};

import { ResumenModuloComponent } from '../../compartido/resumen-modulo.component';
@Component({
  selector: 'app-conocimiento',
  standalone: true,
  imports: [ResumenModuloComponent, 
    FormsModule,
    CargandoComponent,
    ErrorComponent,
    VacioComponent,
    IconoComponent,
    CargarDocumentoComponent,
    RevisionRiesgoComponent,
  ],
  templateUrl: './conocimiento.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './conocimiento.component.scss',
})
export class ConocimientoComponent {
  private readonly api = inject(ApiService);
  private readonly operaciones = inject(OperacionesService);
  private readonly sesion = inject(SesionService);

  // --- Carga y ciclo de vida ---
  protected readonly puedeCargar = computed(() =>
    this.sesion.tienePermiso(PERMISOS.conocimientoCargar),
  );
  protected readonly puedeAprobar = computed(() =>
    this.sesion.tienePermiso(PERMISOS.conocimientoAprobar),
  );
  /** `undefined`: dialogo cerrado; `null`: documento nuevo; si no, version nueva. */
  protected readonly dialogo = signal<Documento | null | undefined>(undefined);
  /** Documento cuyo estado se esta cambiando, para deshabilitar su fila. */
  protected readonly cambiando = signal<string | null>(null);
  protected readonly errorAccion = signal<FalloApi | null>(null);
  protected readonly mensajeAccion = signal<string | null>(null);
  /** Documento marcado cuya revisión de riesgo está abierta. */
  protected readonly documentoRiesgo = signal<Documento | null>(null);

  // --- Acceso por documento ---
  protected readonly documentoPermisos = signal<string | null>(null);
  protected readonly permisosDocumento = signal<readonly PermisoDocumento[]>([]);
  protected readonly opcionesPermisos = signal<OpcionesPermisosDocumento | null>(null);
  protected readonly cargandoPermisos = signal(false);
  protected readonly guardandoPermisos = signal(false);
  protected readonly errorPermisos = signal<string | null>(null);
  protected tipoPrincipalNuevo: TipoPrincipalDocumento = 'ROL';
  protected principalNuevo = '';
  protected puedeLeerNuevo = true;
  protected puedeUsarEnAgenteNuevo = false;

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
  //  Carga y ciclo de vida
  // ======================================================================
  protected abrirCarga(documento: Documento | null = null): void {
    this.mensajeAccion.set(null);
    this.errorAccion.set(null);
    this.dialogo.set(documento);
  }

  protected cerrarCarga(): void {
    this.dialogo.set(undefined);
    // Recarga siempre: aunque la ingesta fallara, el documento pudo crearse.
    this.cargar();
  }

  /** Acciones de estado visibles para un documento y este usuario. */
  protected acciones(documento: Documento): readonly AccionEstado[] {
    if (!this.puedeCargar()) {
      return [];
    }
    return (ACCIONES[documento.status] ?? []).filter(
      (accion) => !accion.aprobar || this.puedeAprobar(),
    );
  }

  protected cambiarEstado(documento: Documento, accion: AccionEstado): void {
    this.cambiando.set(documento.id);
    this.errorAccion.set(null);
    this.mensajeAccion.set(null);
    this.api.cambiarEstadoDocumento(documento.id, accion.destino).subscribe({
      next: (actualizado) => {
        this.cambiando.set(null);
        this.mensajeAccion.set(
          `«${actualizado.titulo}» ahora está en estado ${this.estado(actualizado.status).texto.toLowerCase()}.`,
        );
        this.cargar();
      },
      error: (fallo: FalloApi) => {
        this.cambiando.set(null);
        this.errorAccion.set(fallo);
      },
    });
  }

  protected gestionarPermisos(documento: Documento): void {
    if (this.documentoPermisos() === documento.id) {
      this.documentoPermisos.set(null);
      this.errorPermisos.set(null);
      return;
    }
    this.documentoPermisos.set(documento.id);
    this.cargandoPermisos.set(true);
    this.errorPermisos.set(null);
    forkJoin({
      opciones: this.api.opcionesPermisosDocumento(),
      permisos: this.api.permisosDocumento(documento.id),
    }).subscribe({
      next: ({ opciones, permisos }) => {
        this.opcionesPermisos.set(opciones);
        this.permisosDocumento.set([...permisos.permisos]);
        this.cargandoPermisos.set(false);
        this.principalNuevo = '';
      },
      error: (fallo: FalloApi) => {
        this.errorPermisos.set(fallo.message);
        this.cargandoPermisos.set(false);
      },
    });
  }

  protected opcionesTipo(tipo = this.tipoPrincipalNuevo) {
    const opciones = this.opcionesPermisos();
    if (!opciones) return [];
    return {
      ROL: opciones.roles,
      USUARIO: opciones.usuarios,
      SEDE: opciones.sedes,
      ESPECIALIDAD: opciones.especialidades,
    }[tipo];
  }

  protected cambiarTipoPrincipal(tipo: TipoPrincipalDocumento): void {
    this.tipoPrincipalNuevo = tipo;
    this.principalNuevo = '';
  }

  protected agregarPermiso(): void {
    if (!this.principalNuevo) return;
    if (
      this.permisosDocumento().some(
        (permiso) =>
          permiso.principal_tipo === this.tipoPrincipalNuevo &&
          permiso.principal_id === this.principalNuevo,
      )
    ) {
      this.errorPermisos.set('Ese rol o persona ya tiene una regla para este documento.');
      return;
    }
    this.permisosDocumento.update((actuales) => [
      ...actuales,
      {
        principal_tipo: this.tipoPrincipalNuevo,
        principal_id: this.principalNuevo,
        puede_leer: this.puedeLeerNuevo,
        puede_usar_en_agente: this.puedeLeerNuevo && this.puedeUsarEnAgenteNuevo,
      },
    ]);
    this.principalNuevo = '';
    this.errorPermisos.set(null);
  }

  protected quitarPermiso(regla: PermisoDocumento): void {
    this.permisosDocumento.update((actuales) =>
      actuales.filter(
        (permiso) =>
          permiso.principal_tipo !== regla.principal_tipo ||
          permiso.principal_id !== regla.principal_id,
      ),
    );
  }

  protected nombrePrincipal(regla: PermisoDocumento): string {
    const opcion = this.opcionesTipo(regla.principal_tipo).find(
      (actual) => actual.id === regla.principal_id,
    );
    return opcion?.nombre ?? 'Principal desactivado o eliminado';
  }

  protected tipoPrincipal(clave: TipoPrincipalDocumento): string {
    return TIPOS_PRINCIPAL[clave];
  }

  protected guardarPermisos(): void {
    const documentoId = this.documentoPermisos();
    if (!documentoId || this.guardandoPermisos()) return;
    if (
      this.permisosDocumento().length === 0 &&
      !globalThis.confirm(
        'Al quitar todas las reglas, el documento vuelve a usar su alcance general. ¿Desea continuar?',
      )
    ) {
      return;
    }
    this.guardandoPermisos.set(true);
    this.errorPermisos.set(null);
    this.api.reemplazarPermisosDocumento(documentoId, this.permisosDocumento()).subscribe({
      next: (respuesta) => {
        this.permisosDocumento.set([...respuesta.permisos]);
        this.guardandoPermisos.set(false);
        this.mensajeAccion.set('Accesos del documento actualizados y auditados.');
      },
      error: (fallo: FalloApi) => {
        this.guardandoPermisos.set(false);
        this.errorPermisos.set(fallo.message);
      },
    });
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
      return 'Sin límite de vigencia';
    }
    // Fecha corta legible: el instante ISO completo no le dice nada a quien lee.
    const corta = (iso: string) =>
      new Intl.DateTimeFormat('es', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(iso));
    const desde = documento.effective_from ? `Desde ${corta(documento.effective_from)}` : '';
    const hasta = documento.effective_until ? `hasta ${corta(documento.effective_until)}` : '';
    return [desde, hasta].filter(Boolean).join(' ');
  }

  protected riesgoRevisado(mensaje: string): void {
    this.documentoRiesgo.set(null);
    this.mensajeAccion.set(mensaje);
    this.cargar();
  }
}
