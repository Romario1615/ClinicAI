import { FotosRegistroComponent } from '../../compartido/fotos-registro.component';
/**
 * Historia clinica. Conectada al backend real.
 *
 * Lo que esta pantalla tiene que hacer bien
 * -----------------------------------------
 * **Tiene que degradar por rol, sin filtrar que existe lo que no se puede
 * ver.** Los permisos clinicos no van juntos: un asistente tiene `receta.leer`
 * y `adherencia.leer` pero **no** `historia_clinica.leer`. Esta pantalla le
 * muestra las recetas y le dice que las notas no estan a su alcance, en lugar
 * de enviar una peticion que devolvera 403 y pintar un error rojo como si algo
 * se hubiera roto.
 *
 * **No puede presentar una pauta «cuando sea necesario» como pauta fija.** Un
 * PRN no genera horarios, y confundirlos es un error de medicacion. Se marca
 * de forma explicita, no por omision del campo de frecuencia.
 *
 * **Tiene que enseñar que la historia no se borra.** Las versiones antiguas se
 * conservan con su autor, su fecha y el motivo del cambio. Si la interfaz solo
 * mostrara la version vigente, la garantia append-only existiria en la base y
 * no serviria de nada a quien tiene que auditarla.
 *
 * **Una receta suspendida sigue visible, con su motivo.** Ocultarla daria la
 * impresion de que nunca existio, y lo que se necesita saber es justo lo
 * contrario: que existio y por que se retiro.
 *
 * Las recetas se crean como borrador, se confirman por el profesional y se
 * pueden sustituir por una versión firmada que conserva el historial y
 * cancela las tomas futuras de la pauta anterior.
 */
import { Component, DestroyRef, computed, effect, inject, input, OnInit, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { forkJoin, of } from 'rxjs';
import { catchError, map, switchMap } from 'rxjs/operators';

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
import type {
  Medicamento,
  Nota,
  PacienteDetalle,
  Receta,
} from '../../nucleo/servicios/api.service';
import { PERMISOS } from '../../nucleo/servicios/configuracion';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import {
  EspecialidadHistoriaService,
  type ModuloHistoria,
} from '../../nucleo/servicios/especialidad-historia.service';
import { SelectorEspecialidadComponent } from '../../compartido/selector-especialidad.component';
import { FotoPerfilComponent } from '../../compartido/foto-perfil.component';
import { GaleriaImagenesComponent } from '../../compartido/galeria-imagenes.component';
import { IndicePlacaComponent } from './indice-placa.component';
import { NotaEditorComponent } from './nota-editor.component';
import { RecetaEditorComponent } from './receta-editor.component';
import { OdontogramaComponent } from './odontograma.component';
import { PlanesTratamientoComponent } from './planes-tratamiento.component';
import { Formulario033Component } from './formulario-033.component';
import { PestanasComponent, type OpcionPestana } from '../../compartido/pestanas.component';
import type { Paciente } from '../../nucleo/modelos/dominio';
import { formatearFechaLarga, formatearHora } from '../../nucleo/utilidades/fechas';

/** Zona de presentacion. La real viene de la sede; esta es la de la clinica. */
const ZONA = 'America/Guayaquil';

/**
 * Por encima de este tamaño la pantalla es de trabajo fija (no se desplaza el
 * documento). Es la misma consulta que usa la base común en `styles.scss`.
 */
const CONSULTA_PANTALLA_FIJA = '(min-width: 821px) and (min-height: 600px)';

const SEVERIDADES: Record<string, string> = {
  LEVE: 'leve',
  MODERADA: 'moderada',
  GRAVE: 'grave',
  ANAFILAXIA: 'anafilaxia',
};

/** Como se lee cada estado de receta, y que implica. */
const ESTADOS_RECETA: Record<string, { texto: string; tono: string; detalle: string }> = {
  BORRADOR: {
    texto: 'Borrador',
    tono: 'neutro',
    detalle: 'Sin confirmar. No genera recordatorios ni cuenta como indicacion vigente.',
  },
  CONFIRMADA: {
    texto: 'Confirmada',
    tono: 'exito',
    detalle: 'Confirmada por el profesional. Es la unica que genera calendario de tomas.',
  },
  SUSPENDIDA: {
    texto: 'Suspendida',
    tono: 'peligro',
    detalle: 'Retirada. Se conserva con su motivo: el historial no se borra.',
  },
};

const VIAS: Record<string, string> = {
  ORAL: 'via oral',
  TOPICA: 'via topica',
  INHALATORIA: 'via inhalatoria',
  OFTALMICA: 'via oftalmica',
  OTICA: 'via otica',
  NASAL: 'via nasal',
  RECTAL: 'via rectal',
  SUBCUTANEA: 'via subcutanea',
  INTRAMUSCULAR: 'via intramuscular',
  INTRAVENOSA: 'via intravenosa',
};

type Pestana =
  | 'evolucion'
  | 'odontograma'
  | 'formulario033'
  | 'periodoncia'
  | 'imagenes'
  | 'planes'
  | 'recetas'
  | 'indicaciones'
  | 'faciograma'
  | 'documentos';

import { TipoDocumentoPipe } from '../../compartido/tipo-documento.pipe';
import { ResumenModuloComponent } from '../../compartido/resumen-modulo.component';
import { IconoComponent } from '../../compartido/icono.component';
import { ResumenClinicoComponent, type AlergiaResumen } from './resumen-clinico.component';
import { IndicacionesPacienteComponent } from './indicaciones-paciente.component';
import { OperacionesService } from '../../nucleo/servicios/operaciones.service';
import { RegistrosPacienteComponent } from '../../compartido/registros-paciente.component';
@Component({
  selector: 'app-historia-clinica',
  standalone: true,
  imports: [FotosRegistroComponent,
    RegistrosPacienteComponent,
    ResumenModuloComponent,
    IconoComponent,
    ResumenClinicoComponent,
    IndicacionesPacienteComponent,
    FormsModule,
    TipoDocumentoPipe,
    CargandoComponent,
    ErrorComponent,
    VacioComponent,
    OdontogramaComponent,
    PlanesTratamientoComponent,
    Formulario033Component,
    FotoPerfilComponent,
    GaleriaImagenesComponent,
    IndicePlacaComponent,
    NotaEditorComponent,
    RecetaEditorComponent,
    SelectorEspecialidadComponent,
    PestanasComponent,
  ],
  templateUrl: './historia-clinica.component.html',
  // Pantalla de trabajo: en escritorio la sección ocupa el alto disponible y
  // solo desplazan las listas, cada una en su marco.
  host: { class: 'pantalla historia' },
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './historia-clinica.component.scss',
})
export class HistoriaClinicaComponent implements OnInit {
  readonly pacienteInicial = input<string | null>(null);
  readonly citaContexto = input<string | null>(null);
  readonly sedeContexto = input<string | null>(null);
  readonly embebida = input(false);
  readonly moduloInicial = input<'faciograma' | 'documentos' | null>(null);
  private readonly ruta = inject(ActivatedRoute, { optional: true });
  private readonly destroyRef = inject(DestroyRef);
  private readonly api = inject(ApiService);
  private readonly operaciones = inject(OperacionesService);
  protected readonly sesion = inject(SesionService);
  protected readonly especialidades = inject(EspecialidadHistoriaService);

  // --- Seleccion de paciente ---
  protected termino = '';
  protected readonly pacientes = signal<readonly Paciente[]>([]);
  /** Total del ámbito según el servidor; el listado muestra hasta 50. */
  protected readonly totalPacientes = signal(0);
  protected readonly cargandoPacientes = signal(true);
  protected readonly errorPacientes = signal<FalloApi | null>(null);
  protected readonly paciente = signal<PacienteDetalle | null>(null);

  // --- Historia ---
  protected readonly notas = signal<readonly Nota[]>([]);
  protected readonly puedeLeerFotos = computed(() => this.sesion.tienePermiso(PERMISOS.imagenClinicaLeer));
  protected readonly recetas = signal<readonly Receta[]>([]);
  protected readonly incluirHistorico = signal(false);
  protected readonly cargandoHistoria = signal(false);
  protected readonly errorHistoria = signal<FalloApi | null>(null);
  /** Cierto cuando el backend nego las notas por permiso, no por un fallo. */
  protected readonly notasDenegadas = signal(false);
  /** El 403 fue por falta de vinculo con ESTE paciente, no por el rol. */
  protected readonly accesoNoDisponible = signal(false);
  protected readonly motivoAccesoEmergencia = signal('');
  protected readonly solicitandoAccesoEmergencia = signal(false);
  protected readonly avisoAccesoEmergencia = signal('');
  protected readonly errorAccesoEmergencia = signal('');
  private readonly accesosEmergenciaVigentes = new Map<string, number>();
  /**
   * Alergias del resumen clínico, para la cabecera del paciente. `null`
   * mientras no se conocen (o si el rol no ve el resumen): no se dice «sin
   * alergias» de lo que no se ha consultado.
   */
  protected readonly alergias = signal<readonly AlergiaResumen[] | null>(null);
  protected readonly hayAlergiaGrave = computed(() =>
    (this.alergias() ?? []).some((a) => a.severidad === 'GRAVE' || a.severidad === 'ANAFILAXIA'),
  );
  /** Escritorio con pantalla fija: la foto va compacta en la cabecera. */
  protected readonly pantallaFija = signal(false);
  private temporizadorAccesoEmergencia: ReturnType<typeof setTimeout> | null = null;

  // --- Permisos ---
  // Se leen del principal, no se adivinan: el backend es la autoridad y
  // ocultar lo que no se puede pedir evita peticiones que van a dar 403.
  protected readonly puedeLeerNotas = computed(() =>
    this.sesion.tienePermiso(PERMISOS.historiaLeer),
  );
  protected readonly puedeLeerRecetas = computed(() =>
    this.sesion.tienePermiso(PERMISOS.recetaLeer),
  );
  protected readonly puedeLeerOdontograma = computed(() =>
    this.sesion.tienePermiso(PERMISOS.odontogramaLeer),
  );
  protected readonly puedeLeerFormulario033 = computed(() =>
    this.sesion.tienePermiso(PERMISOS.historiaLeer) &&
    this.sesion.tienePermiso(PERMISOS.historiaLeerSensible),
  );
  protected readonly puedeEditarFormulario033 = computed(() =>
    this.sesion.tienePermiso(PERMISOS.historiaEscribir) &&
    this.sesion.tienePermiso(PERMISOS.historiaLeerSensible),
  );
  protected readonly puedeLeerPlanes = computed(() =>
    this.sesion.tieneAlgunPermiso(
      PERMISOS.planTratamientoLeer,
      PERMISOS.planTratamientoEscribir,
    ),
  );
  protected readonly puedeEditarPlanes = computed(() =>
    this.sesion.tienePermiso(PERMISOS.planTratamientoEscribir),
  );

  protected readonly puedeEscribirNotas = computed(() =>
    this.sesion.tienePermiso(PERMISOS.historiaEscribir),
  );
  protected readonly puedeSolicitarAccesoEmergencia = computed(() =>
    this.sesion.tienePermiso(PERMISOS.accesoEmergenciaSolicitar),
  );
  protected readonly puedeEditarFoto = computed(() =>
    this.sesion.tienePermiso(PERMISOS.pacienteEditar),
  );

  /** Pestaña visible. Solo se ofrecen las que el rol puede leer. */
  protected readonly pestana = signal<Pestana>('evolucion');
  protected readonly pestanas = computed(() => {
    // Primero lo clínico común a toda especialidad (evolución, recetas,
    // indicaciones); después los módulos propios de la especialidad. Si en una
    // pantalla estrecha la fila no cabe entera, lo que queda al final es lo
    // menos frecuente, nunca las recetas con borradores pendientes.
    const lista: { clave: Pestana; texto: string }[] = [
      { clave: 'evolucion', texto: 'Evolución' },
      { clave: 'recetas', texto: 'Recetas' },
    ];
    if (this.puedeLeerNotas()) lista.push({ clave: 'indicaciones', texto: 'Indicaciones' });
    if (this.puedeLeerNotas() && !this.accesoNoDisponible()) lista.push({ clave: 'documentos', texto: 'Documentos' });
    if (this.puedeLeerNotas() && !this.accesoNoDisponible() && this.especialidades.tieneModulo('faciograma')) lista.push({ clave: 'faciograma', texto: 'Faciograma' });
    // Permiso del rol **y** módulo de la especialidad desde la que se revisa.
    // Sin acceso clínico a este paciente, los módulos solo darían «no disponible».
    const modulo = (m: ModuloHistoria) => this.especialidades.tieneModulo(m) && !this.accesoNoDisponible();
    if (this.puedeLeerOdontograma() && modulo('odontograma')) {
      lista.push({ clave: 'odontograma', texto: 'Odontograma' });
    }
    if (this.puedeLeerFormulario033() && modulo('odontograma')) {
      lista.push({ clave: 'formulario033', texto: 'Formulario 033' });
    }
    if (this.puedeLeerOdontograma() && modulo('periodoncia')) {
      lista.push({ clave: 'periodoncia', texto: 'Periodoncia' });
    }
    if (this.sesion.tienePermiso(PERMISOS.imagenClinicaLeer) && modulo('imagenes')) {
      lista.push({ clave: 'imagenes', texto: 'Imágenes' });
    }
    if (this.puedeLeerPlanes() && modulo('planes')) {
      lista.push({ clave: 'planes', texto: 'Planes' });
    }
    return lista;
  });

  /**
   * Opciones para la fila de pestañas. Los nombres son cortos para que las
   * ocho quepan en una fila de escritorio desde 1280 px de ancho. «Recetas» lleva la cuenta de
   * borradores: es trabajo pendiente del profesional (sin su confirmación no
   * hay calendario de tomas).
   */
  protected readonly opcionesPestanas = computed<readonly OpcionPestana[]>(() => {
    const borradores = this.recetas().filter((r) => r.estado === 'BORRADOR').length;
    return this.pestanas().map((opcion) => ({
      clave: opcion.clave,
      etiqueta: opcion.texto,
      cuenta: opcion.clave === 'recetas' ? borradores : null,
    }));
  });

  /** «Evolución» con resumen se reparte en dos columnas: resumen y notas. */
  protected readonly conResumen = computed(
    () => this.pestana() === 'evolucion' && this.puedeLeerNotas() && !this.accesoNoDisponible(),
  );

  protected readonly puedeEscribirHistoria = computed(() =>
    this.sesion.tienePermiso(PERMISOS.historiaEscribir),
  );

  /** Recetas confirmadas, para adjuntarlas a las indicaciones. */
  protected readonly recetasConfirmadas = computed(() =>
    this.recetas()
      .filter((r) => r.estado === 'CONFIRMADA')
      .map((r) => ({
        id: r.id,
        etiqueta: `${new Date(r.confirmada_en ?? r.creado_en).toLocaleDateString('es')} · ${r.medicamentos.map((m) => m.nombre).join(', ') || 'Receta'}`,
      })),
  );

  protected readonly puedeCrearRecetas = computed(() =>
    this.sesion.tienePermiso(PERMISOS.recetaCrear),
  );
  protected readonly puedeConfirmarRecetas = computed(() =>
    this.sesion.tienePermiso(PERMISOS.recetaConfirmar),
  );
  protected readonly creandoReceta = signal(false);
  protected readonly versionandoReceta = signal<Receta | null>(null);
  protected readonly confirmando = signal(false);
  protected readonly avisoReceta = signal('');

  protected alGuardarReceta(): void {
    const fueVersion = this.versionandoReceta() !== null;
    this.creandoReceta.set(false);
    this.versionandoReceta.set(null);
    this.avisoReceta.set(
      fueVersion
        ? 'Nueva versión firmada. Las tomas futuras de la receta anterior se cancelaron y se generó el calendario actualizado.'
        : 'Receta guardada como borrador. Confírmela para generar las tomas.',
    );
    this.cargarHistoria();
  }

  protected cerrarEditorReceta(): void {
    this.creandoReceta.set(false);
    this.versionandoReceta.set(null);
  }

  /**
   * Confirma con la misma firma del borrador: el servidor acepta la propia o
   * una delegación vigente y lo audita.
   */
  protected confirmarReceta(receta: Receta): void {
    if (this.confirmando() || !this.puedeConfirmarRecetas() || !receta.puede_gestionar) return;
    this.confirmando.set(true);
    this.api.confirmarReceta(receta.id, receta.profesional_id).subscribe({
      next: () => {
        this.confirmando.set(false);
        this.avisoReceta.set('Receta confirmada. Se generó el calendario de tomas.');
        this.cargarHistoria();
      },
      error: (fallo: FalloApi) => {
        this.confirmando.set(false);
        this.avisoReceta.set('');
        this.errorHistoria.set(fallo);
      },
    });
  }

  /** `undefined`: sin editor; `null`: nota nueva; una nota: su corrección. */
  protected readonly editando = signal<Nota | null | undefined>(undefined);

  protected puedeCorregirNota(nota: Nota): boolean {
    return this.puedeEscribirNotas() && nota.profesional_id === this.sesion.identidad()?.profesional_id;
  }

  protected readonly hayPaciente = computed(() => this.paciente() !== null);

  /** Notas agrupadas por su raiz, con la vigente primero. */
  protected readonly historias = computed(() => {
    const porRaiz = new Map<string, Nota[]>();
    for (const nota of this.notas()) {
      const grupo = porRaiz.get(nota.raiz_id) ?? [];
      grupo.push(nota);
      porRaiz.set(nota.raiz_id, grupo);
    }
    return [...porRaiz.values()]
      .map((versiones) => {
        const ordenadas = [...versiones].sort((a, b) => b.version - a.version);
        return {
          raizId: ordenadas[0].raiz_id,
          vigente: ordenadas.find((n) => n.vigente) ?? ordenadas[0],
          anteriores: ordenadas.filter((n) => !n.vigente),
        };
      })
      .sort(
        (a, b) =>
          new Date(b.vigente.creado_en).getTime() - new Date(a.vigente.creado_en).getTime(),
      );
  });

  constructor() {
    effect(() => {
      const modulo = this.moduloInicial();
      if (modulo && this.pestanas().some(p => p.clave === modulo)) this.pestana.set(modulo);
    });
    this.destroyRef.onDestroy(() => this.limpiarTemporizadorAccesoEmergencia());
    this.vigilarPantallaFija();
  }

  ngOnInit(): void {
    if (!this.embebida()) this.cargarPacientes();
    this.especialidades.cargar();
    // «Abrir historia completa» desde la ficha llega con ?paciente=<id>.
    const pacienteId = this.pacienteInicial() ?? this.ruta?.snapshot.queryParamMap.get('paciente');
    if (pacienteId) {
      this.abrir({ id: pacienteId } as Paciente);
    }
  }

  // ======================================================================
  //  Pacientes
  // ======================================================================
  protected cargarPacientes(): void {
    this.cargandoPacientes.set(true);
    this.errorPacientes.set(null);

    const termino = this.termino.trim();
    this.api.pacientes({ ...filtroBusquedaPaciente(termino), limite: 50 }).subscribe({
      next: (pagina) => {
        this.pacientes.set(pagina.elementos);
        this.totalPacientes.set(pagina.total);
        this.cargandoPacientes.set(false);
      },
      error: (fallo: FalloApi) => {
        this.errorPacientes.set(fallo);
        this.cargandoPacientes.set(false);
      },
    });
  }

  protected abrir(paciente: Paciente): void {
    this.limpiarTemporizadorAccesoEmergencia();
    this.cargandoHistoria.set(true);
    this.errorHistoria.set(null);
    this.notasDenegadas.set(false);
    this.accesoNoDisponible.set(false);
    this.notas.set([]);
    this.recetas.set([]);
    this.alergias.set(null);

    this.api.paciente(paciente.id).subscribe({
      next: (detalle) => {
        this.paciente.set(detalle);
        this.programarCaducidadAccesoEmergencia(paciente.id);
        this.cargarHistoria();
      },
      error: (fallo: FalloApi) => {
        this.errorHistoria.set(fallo);
        this.cargandoHistoria.set(false);
      },
    });
  }

  protected alGuardarNota(): void {
    this.editando.set(undefined);
    this.cargarHistoria();
  }

  protected cerrar(): void {
    this.limpiarTemporizadorAccesoEmergencia();
    this.pestana.set('evolucion');
    this.editando.set(undefined);
    this.paciente.set(null);
    this.notas.set([]);
    this.recetas.set([]);
    this.alergias.set(null);
    this.errorHistoria.set(null);
    this.notasDenegadas.set(false);
    this.accesoNoDisponible.set(false);
    this.motivoAccesoEmergencia.set('');
    this.avisoAccesoEmergencia.set('');
    this.errorAccesoEmergencia.set('');
  }

  // ======================================================================
  //  Historia
  // ======================================================================
  /**
   * Carga notas y recetas a la vez.
   *
   * Cada rama absorbe su propio 403 en lugar de tumbar la carga entera: un
   * asistente puede ver las recetas y no las notas, y fallar del todo le
   * dejaria sin lo que si tiene derecho a consultar. Un 403 aqui no es un
   * error del sistema, es el control funcionando.
   */
  protected cargarHistoria(): void {
    const paciente = this.paciente();
    if (!paciente) {
      return;
    }

    this.cargandoHistoria.set(true);
    this.errorHistoria.set(null);

    // Primero se pregunta si hay acceso clínico (200 sí/no): sin relación
    // asistencial no se piden las notas, que solo darían 404.
    const acceso$ = this.puedeLeerNotas()
      ? this.operaciones
          .leer<{ acceso_clinico: boolean }>(`/pacientes/${paciente.id}/acceso-clinico`)
          .pipe(
            map((r) => r.acceso_clinico),
            catchError(() => of(null)),
          )
      : of(null);

    acceso$
      .pipe(
        switchMap((acceso) => {
          if (acceso === false) {
            this.notasDenegadas.set(true);
            this.accesoNoDisponible.set(true);
          }
          return forkJoin({
            notas:
              this.puedeLeerNotas() && acceso !== false
                ? this.api
                    .notas(paciente.id, this.incluirHistorico(), this.especialidades.elegida()?.id ?? null)
                    .pipe(
                      catchError((fallo: FalloApi) => {
                        if (fallo.estado === 403 || fallo.estado === 404) {
                          this.notasDenegadas.set(true);
                          this.accesoNoDisponible.set(fallo.estado === 404);
                          return of([] as readonly Nota[]);
                        }
                        throw fallo;
                      }),
                    )
                : of([] as readonly Nota[]),
            recetas: this.puedeLeerRecetas()
              ? this.api.recetas(paciente.id).pipe(catchError(() => of([] as readonly Receta[])))
              : of([] as readonly Receta[]),
          });
        }),
      )
      .subscribe({
        next: (datos) => {
          this.notas.set(datos.notas);
          this.recetas.set(datos.recetas);
          this.cargandoHistoria.set(false);
        },
        error: (fallo: FalloApi) => {
          this.errorHistoria.set(fallo);
          this.cargandoHistoria.set(false);
        },
      });
  }

  protected solicitarAccesoEmergencia(): void {
    const paciente = this.paciente();
    const motivo = this.motivoAccesoEmergencia().trim();
    if (!paciente || motivo.length < 12 || this.solicitandoAccesoEmergencia()) return;
    this.solicitandoAccesoEmergencia.set(true);
    this.avisoAccesoEmergencia.set('');
    this.errorAccesoEmergencia.set('');
    this.api.solicitarAccesoEmergencia(paciente.id, motivo).subscribe({
      next: ({ vence_en }) => {
        this.solicitandoAccesoEmergencia.set(false);
        this.motivoAccesoEmergencia.set('');
        this.notasDenegadas.set(false);
        this.accesoNoDisponible.set(false);
        const venceMs = new Date(vence_en).getTime();
        this.accesosEmergenciaVigentes.set(paciente.id, venceMs);
        this.avisoAccesoEmergencia.set(
          `Acceso temporal concedido hasta ${new Date(vence_en).toLocaleTimeString('es-EC', { hour: '2-digit', minute: '2-digit' })}. La administración recibió un aviso.`,
        );
        this.programarCaducidadAccesoEmergencia(paciente.id);
        this.cargarHistoria();
      },
      error: (fallo: unknown) => {
        this.solicitandoAccesoEmergencia.set(false);
        this.errorAccesoEmergencia.set(
          fallo instanceof FalloApi ? fallo.message : 'No se pudo solicitar el acceso temporal.',
        );
      },
    });
  }

  private programarCaducidadAccesoEmergencia(pacienteId: string): void {
    this.limpiarTemporizadorAccesoEmergencia();
    const venceEn = this.accesosEmergenciaVigentes.get(pacienteId);
    if (venceEn === undefined) return;
    const demora = venceEn - Date.now();
    if (demora <= 0) {
      this.accesosEmergenciaVigentes.delete(pacienteId);
      return;
    }
    this.temporizadorAccesoEmergencia = setTimeout(() => {
      this.accesosEmergenciaVigentes.delete(pacienteId);
      this.temporizadorAccesoEmergencia = null;
      if (this.paciente()?.id === pacienteId) {
        this.cerrar();
        this.avisoAccesoEmergencia.set('El acceso temporal expiró. La historia se cerró.');
      }
    }, demora);
  }

  private limpiarTemporizadorAccesoEmergencia(): void {
    if (this.temporizadorAccesoEmergencia !== null) {
      clearTimeout(this.temporizadorAccesoEmergencia);
      this.temporizadorAccesoEmergencia = null;
    }
  }

  /** Otra especialidad: otras notas y otros módulos. */
  protected cambiarEspecialidad(): void {
    if (!this.pestanas().some((opcion) => opcion.clave === this.pestana())) {
      this.pestana.set('evolucion');
    }
    this.cargarHistoria();
  }

  /** La fila de pestañas solo ofrece claves válidas; se comprueban igual. */
  protected elegirPestana(clave: string): void {
    const opcion = this.pestanas().find((o) => o.clave === clave);
    if (opcion) this.pestana.set(opcion.clave);
  }

  protected alternarHistorico(): void {
    this.incluirHistorico.update((valor) => !valor);
    this.cargarHistoria();
  }

  // ======================================================================
  //  Presentacion
  // ======================================================================
  protected estadoReceta(clave: string): { texto: string; tono: string; detalle: string } {
    return (
      ESTADOS_RECETA[clave] ?? {
        texto: clave,
        tono: 'neutro',
        detalle: 'Estado desconocido.',
      }
    );
  }

  /**
   * Como se lee la pauta de un medicamento.
   *
   * El PRN se enuncia de forma explicita y nunca se le calcula una frecuencia.
   * Escribir «cada 8 horas» sobre algo que el paciente solo debe tomar si lo
   * necesita es convertir una indicacion a demanda en una pauta fija.
   */
  protected pauta(medicamento: Medicamento): string {
    if (medicamento.cuando_sea_necesario) {
      return 'Solo cuando sea necesario. Sin horario fijo.';
    }
    const partes: string[] = [];
    if (medicamento.frecuencia_horas) {
      partes.push(`cada ${medicamento.frecuencia_horas} h`);
    }
    if (medicamento.duracion_dias) {
      partes.push(`durante ${medicamento.duracion_dias} dias`);
    }
    return partes.length > 0 ? partes.join(', ') : 'Sin pauta registrada';
  }

  protected via(clave: string): string {
    return VIAS[clave] ?? clave.toLowerCase();
  }

  protected fecha(valor: string | null): string {
    if (!valor) {
      return '—';
    }
    return `${formatearFechaLarga(valor, ZONA)}, ${formatearHora(valor, ZONA)}`;
  }

  protected nombreCompleto(paciente: PacienteDetalle): string {
    return `${paciente.nombre} ${paciente.apellido}`;
  }

  protected severidad(valor: string): string {
    return SEVERIDADES[valor] ?? valor.toLowerCase();
  }

  /**
   * Sigue si la ventana es de escritorio con pantalla fija. Sin `matchMedia`
   * (pruebas sin motor de maquetación) se queda en el modo de documento que
   * desplaza, que es el que conserva los botones con texto de la foto.
   */
  private vigilarPantallaFija(): void {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const consulta = window.matchMedia(CONSULTA_PANTALLA_FIJA);
    this.pantallaFija.set(consulta.matches);
    const alCambiar = (evento: MediaQueryListEvent) => this.pantallaFija.set(evento.matches);
    consulta.addEventListener?.('change', alCambiar);
    this.destroyRef.onDestroy(() => consulta.removeEventListener?.('change', alCambiar));
  }
}
