import { CommonModule } from '@angular/common';
import { Component, effect, inject, input, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { FotosRegistroComponent } from '../../compartido/fotos-registro.component';
import { CapturaFotosComponent, type FotoSeleccionada } from '../../compartido/captura-fotos.component';
import { FotosRegistroService } from '../../nucleo/servicios/fotos-registro.service';
import { catchError, forkJoin, of, type Observable, type OperatorFunction } from 'rxjs';

import { CargandoComponent } from '../../compartido/estados.component';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
import { ApiService, FalloApi, type Formulario033Api, type Formulario033DatosApi, type Formulario033EntradaApi, type Nota, type Odontograma, type RegistroPlaca } from '../../nucleo/servicios/api.service';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import type { Cita, PaginaCitas, Sede } from '../../nucleo/modelos/dominio';
import { PERMISOS } from '../../nucleo/servicios/configuracion';
import { EspecialidadHistoriaService } from '../../nucleo/servicios/especialidad-historia.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { generarHtmlFormulario033 } from './formulario-033-impresion';

const REGIONES = [
  'LABIOS', 'MEJILLAS', 'MAXILAR_SUPERIOR', 'MAXILAR_INFERIOR', 'LENGUA', 'PALADAR',
  'PISO_DE_LA_BOCA', 'CARRILLOS', 'GLANDULAS_SALIVALES', 'OROFARINGE', 'ATM', 'GANGLIOS', 'OTROS',
];
const PIEZAS_INDICE = [16, 17, 55, 11, 21, 51, 26, 27, 65, 36, 37, 75, 31, 41, 71, 46, 47, 85];
const PERSONALES = [
  'ALERGIA_ANTIBIOTICO', 'ALERGIA_ANESTESIA', 'HEMORRAGIA', 'VIH_SIDA', 'TUBERCULOSIS', 'ASMA',
  'DIABETES', 'HIPERTENSION_ARTERIAL', 'ENFERMEDAD_CARDIACA', 'OTRO',
];
const FAMILIARES = [
  'CARDIOPATIA', 'HIPERTENSION_ARTERIAL', 'ENFERMEDAD_CEREBROVASCULAR', 'ENDOCRINO_METABOLICO',
  'CANCER', 'TUBERCULOSIS', 'ENFERMEDAD_MENTAL', 'ENFERMEDAD_INFECCIOSA', 'MALFORMACION', 'OTRO',
];

function fechaLocalActual(): string {
  const ahora = new Date();
  const mes = String(ahora.getMonth() + 1).padStart(2, '0');
  const dia = String(ahora.getDate()).padStart(2, '0');
  return `${ahora.getFullYear()}-${mes}-${dia}`;
}

export function nuevoFormulario033(): Formulario033DatosApi {
  return {
    embarazada: null,
    motivo_consulta: '',
    enfermedad_actual: '',
    antecedentes_personales: PERSONALES.map((codigo) => ({ codigo, presente: null, detalle: null })),
    antecedentes_familiares: FAMILIARES.map((codigo) => ({ codigo, presente: null, detalle: null })),
    constantes_vitales: {
      temperatura_c: null,
      pulso_minuto: null,
      frecuencia_respiratoria_minuto: null,
      presion_sistolica_mmhg: null,
      presion_diastolica_mmhg: null,
    },
    examen_estomatognatico: REGIONES.map((region) => ({ region, hallazgo: 'NO_EVALUADO', detalle: null, grado: null })),
    indicadores_salud_bucal: {
      sitios: PIEZAS_INDICE.map((pieza) => ({ pieza, placa: null, calculo: null, gingivitis: null })),
      enfermedad_periodontal: 'SIN_REGISTRO',
      oclusion: 'SIN_REGISTRO',
      fluorosis: 'SIN_REGISTRO',
    },
    indices_cpo_ceo: {
      permanentes_d: null, permanentes_c: null, permanentes_p: null, permanentes_o: null,
      temporales_d: null, temporales_c: null, temporales_e: null, temporales_o: null,
    },
    examenes_complementarios: [],
    diagnosticos: [],
    sesiones_tratamiento: [],
  };
}

@Component({
  selector: 'app-formulario-033',
  standalone: true,
  imports: [FotosRegistroComponent,CapturaFotosComponent,CommonModule, FormsModule, CargandoComponent, VentanaFlotanteComponent],
  templateUrl: './formulario-033.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './formulario-033.component.scss',
})
export class Formulario033Component {
  protected puedeLeerFotos():boolean {return this.sesion.tienePermiso(PERMISOS.imagenClinicaLeer);}
  protected puedeCargarFotos():boolean {return this.sesion.tienePermiso(PERMISOS.imagenClinicaCargar);}

  protected readonly operacionFotos = inject(FotosRegistroService).operacion<Formulario033Api>();
  protected fotos: readonly FotoSeleccionada[] = [];
  readonly pacienteId = input.required<string>();
  readonly puedeEditar = input(false);

  private readonly api = inject(ApiService);
  private readonly catalogo = inject(CatalogoService);
  private readonly sesion = inject(SesionService);
  private readonly especialidades = inject(EspecialidadHistoriaService);
  protected readonly formularios = signal<readonly Formulario033Api[]>([]);
  protected readonly versiones = signal<readonly Formulario033Api[]>([]);
  protected readonly sedes = signal<readonly Sede[]>([]);
  protected readonly citas = signal<readonly Cita[]>([]);
  protected readonly notas = signal<readonly Nota[]>([]);
  protected readonly odontograma = signal<Odontograma | null>(null);
  protected readonly registrosPlaca = signal<readonly RegistroPlaca[]>([]);
  protected readonly cargando = signal(true);
  protected readonly cargandoFuentes = signal(false);
  protected readonly errorFuentes = signal('');
  protected readonly guardando = signal(false);
  protected readonly exportando = signal('');
  protected readonly error = signal('');
  protected readonly exito = signal('');
  protected readonly avisoFuentes = signal('');
  protected readonly raizHistorial = signal('');
  protected readonly seleccionado = signal<Formulario033Api | null>(null);
  protected readonly creando = signal(false);
  protected sedeId = '';
  protected citaId = '';
  protected notaId = '';
  protected odontogramaId = '';
  protected registroPlacaId = '';
  protected motivoCorreccion = '';
  protected datos = nuevoFormulario033();
  /** Lo que había al abrir la captura: con eso se sabe si cerrar perdería algo. */
  private huellaInicial = '';
  protected readonly puedeLeerCitas = this.sesion.tienePermiso(PERMISOS.agendaLeer);
  protected readonly puedeLeerNotas = this.sesion.tienePermiso(PERMISOS.historiaLeer) &&
    this.sesion.tienePermiso(PERMISOS.historiaLeerSensible);
  protected readonly puedeLeerOdontogramas = this.sesion.tienePermiso(PERMISOS.odontogramaLeer) &&
    this.especialidades.tieneModulo('odontograma');
  protected readonly puedeLeerRegistrosPlaca = this.sesion.tienePermiso(PERMISOS.odontogramaLeer) &&
    this.especialidades.tieneModulo('periodoncia');
  protected readonly cpoCampos = [
    { clave: 'permanentes_d', etiqueta: 'Permanentes · D', maximo: 32 },
    { clave: 'permanentes_c', etiqueta: 'Permanentes · C', maximo: 32 },
    { clave: 'permanentes_p', etiqueta: 'Permanentes · P', maximo: 32 },
    { clave: 'permanentes_o', etiqueta: 'Permanentes · O', maximo: 32 },
    { clave: 'temporales_d', etiqueta: 'Temporales · d', maximo: 20 },
    { clave: 'temporales_c', etiqueta: 'Temporales · c', maximo: 20 },
    { clave: 'temporales_e', etiqueta: 'Temporales · e', maximo: 20 },
    { clave: 'temporales_o', etiqueta: 'Temporales · o', maximo: 20 },
  ];
  protected readonly examenVacio = () => ({ tipo: 'RAYOS_X', descripcion: '', resultado: null });
  protected readonly diagnosticoVacio = () => ({ codigo_cie: null, descripcion: '', tipo: 'PRESUNTIVO' });
  protected readonly sesionVacia = () => ({ numero: this.datos.sesiones_tratamiento.length + 1, fecha: fechaLocalActual(), diagnostico_complicaciones: null, procedimiento: null, prescripciones: null, proxima_cita: null, alta: false });

  constructor() {
    let pacienteAnterior = '';
    effect(() => {
      const pacienteId = this.pacienteId();
      if (!pacienteId || pacienteAnterior === pacienteId) return;
      pacienteAnterior = pacienteId;
      this.cancelar();
      this.formularios.set([]);
      this.versiones.set([]);
      this.limpiarFuentes();
      this.raizHistorial.set('');
      this.cargar(pacienteId);
    });
    this.catalogo.sedes().subscribe({ next: (sedes) => { this.sedes.set(sedes); if (!this.sedeId) this.sedeId = sedes[0]?.id ?? ''; } });
  }

  protected cargar(pacienteId = this.pacienteId()): void {
    this.cargando.set(true);
    this.error.set('');
    this.api.formularios033(pacienteId).subscribe({
      next: (formularios) => { this.formularios.set(formularios); this.cargando.set(false); },
      error: (fallo: unknown) => { this.error.set(this.mensajeError(fallo)); this.cargando.set(false); },
    });
  }

  protected nuevo(): void {
    this.operacionFotos.reiniciar(); this.fotos=[];
    this.creando.set(true);
    this.seleccionado.set(null);
    this.datos = nuevoFormulario033();
    this.motivoCorreccion = '';
    this.limpiarVinculos();
    this.exito.set('');
    this.error.set('');
    this.huellaInicial = this.huella();
    this.cargarFuentes();
  }

  protected corregir(formulario: Formulario033Api): void {
    this.operacionFotos.reiniciar(); this.fotos=[];
    if (!this.puedeCorregir(formulario)) return;
    this.creando.set(false);
    this.seleccionado.set(formulario);
    this.datos = structuredClone(formulario.datos);
    this.sedeId = formulario.sede_id;
    this.citaId = formulario.cita_id ?? '';
    this.notaId = formulario.nota_id ?? '';
    this.odontogramaId = formulario.odontograma_id ?? '';
    this.registroPlacaId = formulario.registro_placa_id ?? '';
    this.motivoCorreccion = '';
    this.exito.set('');
    this.error.set('');
    this.huellaInicial = this.huella();
    this.cargarFuentes();
  }

  /** Hay algo escrito o vinculado en la captura abierta que cerrar perdería. */
  protected hayCambios(): boolean {
    return (this.creando() || this.seleccionado() !== null) && this.huella() !== this.huellaInicial;
  }

  /**
   * La captura en una cadena comparable. La sede no cuenta: la preselecciona
   * la pantalla al cargar las sedes, no la escribe quien atiende.
   */
  private huella(): string {
    return JSON.stringify({
      datos: this.datos,
      cita: this.citaId,
      nota: this.notaId,
      odontograma: this.odontogramaId,
      placa: this.registroPlacaId,
      motivo: this.motivoCorreccion.trim(),
    });
  }

  /**
   * Cierre ya confirmado por la ventana. A mitad de guardado no se cierra:
   * si el envío fallara después, lo escrito ya se habría borrado.
   */
  protected cerrarCaptura(): void {
    if (this.guardando()) return;
    this.cancelar();
  }

  protected puedeCorregir(formulario: Formulario033Api): boolean {
    return this.puedeEditar() && formulario.profesional_id === this.sesion.identidad()?.profesional_id;
  }

  protected guardar(): void {
    if (this.guardando()) return;
    const seleccionado = this.seleccionado();
    if (!this.sedeId) { this.error.set('Seleccione la sede donde se realizó la atención.'); return; }
    if (seleccionado && this.motivoCorreccion.trim().length < 8) {
      this.error.set('Explique el motivo de la corrección con al menos 8 caracteres.'); return;
    }
    this.guardando.set(true);
    this.error.set('');
    this.exito.set('');
    const datos: Formulario033EntradaApi = {
      sede_id: this.sedeId,
      cita_id: this.citaId || null,
      nota_id: this.notaId || null,
      odontograma_id: this.odontogramaId || null,
      registro_placa_id: this.registroPlacaId || null,
      datos: structuredClone(this.datos),
    };
    const solicitud = seleccionado
      ? this.api.versionarFormulario033(this.pacienteId(), seleccionado.raiz_id, {
          ...datos, version_base: seleccionado.version, motivo: this.motivoCorreccion.trim(),
        })
      : this.api.crearFormulario033(this.pacienteId(), datos);
    this.operacionFotos.guardar('formulario033',solicitud,this.fotos).subscribe({
      next: (creado) => {
        this.guardando.set(false);
        this.seleccionado.set(null);
        this.creando.set(false);
        this.exito.set(`Formulario 033 ${seleccionado ? 'corregido' : 'registrado'} como versión ${creado.version}.`);
        this.cargar();
      },
      error: (fallo: unknown) => { this.error.set(this.mensajeError(fallo)); this.guardando.set(false); },
    });
  }

  protected verVersiones(formulario: Formulario033Api): void {
    const raiz = formulario.raiz_id;
    this.raizHistorial.set(this.raizHistorial() === raiz ? '' : raiz);
    if (this.raizHistorial() !== raiz) return;
    this.api.versionesFormulario033(this.pacienteId(), raiz).subscribe({
      next: (versiones) => { if (this.raizHistorial() === raiz) this.versiones.set(versiones); },
      error: (fallo: unknown) => this.error.set(this.mensajeError(fallo)),
    });
  }

  protected exportar(formulario: Formulario033Api): void {
    const ventana = window.open('', '_blank', 'popup,width=960,height=850');
    if (!ventana) {
      this.error.set('El navegador bloqueó la ventana. Permita ventanas emergentes para imprimir el formulario.');
      return;
    }
    ventana.opener = null;
    ventana.document.title = 'Preparando copia clínica…';
    this.exportando.set(formulario.raiz_id);
    this.error.set('');
    this.exito.set('');
    this.api.auditarExportacionFormulario033(
      this.pacienteId(), formulario.raiz_id, formulario.version,
    ).subscribe({
      next: () => {
        ventana.document.open();
        ventana.document.write(generarHtmlFormulario033(formulario));
        ventana.document.close();
        ventana.document.getElementById('imprimir')?.addEventListener('click', () => ventana.print());
        ventana.focus();
        this.exportando.set('');
        this.exito.set('La copia quedó registrada en auditoría. Revísela e imprima a doble cara si corresponde.');
      },
      error: (fallo: unknown) => {
        ventana.close();
        this.exportando.set('');
        this.error.set(this.mensajeError(fallo));
      },
    });
  }

  protected cancelar(): void {
    this.seleccionado.set(null);
    this.creando.set(false);
    this.datos = nuevoFormulario033();
    this.limpiarVinculos();
    this.error.set('');
    this.errorFuentes.set('');
    this.exito.set('');
  }

  protected seleccionarCita(citaId: string): void {
    this.citaId = citaId;
    this.avisoFuentes.set('');
    const cita = this.citas().find((elemento) => elemento.id === citaId);
    if (cita) this.sedeId = cita.sede_id;
    const nota = this.notas().find((elemento) => elemento.id === this.notaId);
    if (citaId && nota?.cita_id && nota.cita_id !== citaId) {
      this.notaId = '';
      this.avisoFuentes.set('Se quitó la nota vinculada a otra cita para evitar asociar atenciones distintas.');
    }
  }

  protected seleccionarNota(notaId: string): void {
    this.notaId = notaId;
    this.avisoFuentes.set('');
    const nota = this.notas().find((elemento) => elemento.id === notaId);
    if (nota?.cita_id && this.citaId && nota.cita_id !== this.citaId) {
      this.citaId = '';
      this.avisoFuentes.set('La cita seleccionada se quitó porque la nota pertenece a otra atención.');
    }
  }

  protected recargarFuentes(): void { this.cargarFuentes(); }

  protected aplicarNota(): void {
    const nota = this.notas().find((elemento) => elemento.id === this.notaId);
    if (!nota) return;
    let camposAplicados = 0;
    if (!this.datos.motivo_consulta.trim() && nota.motivo_consulta?.trim()) {
      this.datos.motivo_consulta = nota.motivo_consulta;
      camposAplicados++;
    }
    if (!this.datos.enfermedad_actual?.trim() && nota.subjetivo?.trim()) {
      this.datos.enfermedad_actual = nota.subjetivo;
      camposAplicados++;
    }
    this.exito.set(camposAplicados
      ? `Se completaron ${camposAplicados} campo(s) vacío(s) desde la nota. Revise su contenido antes de guardar.`
      : 'No hay campos vacíos compatibles; no se modificó ningún dato clínico.');
  }

  private cargarFuentes(pacienteId = this.pacienteId()): void {
    this.cargandoFuentes.set(true);
    this.errorFuentes.set('');
    const citasVacias: PaginaCitas = { elementos: [], total: 0, limite: 50, desplazamiento: 0 };
    const citas$ = this.puedeLeerCitas
      ? this.api.citas({ paciente_id: pacienteId, limite: 200 }).pipe(this.alFallarFuente(citasVacias))
      : of(citasVacias);
    const notas$ = this.puedeLeerNotas
      ? this.api.notas(pacienteId).pipe(this.alFallarFuente([] as readonly Nota[]))
      : of([] as readonly Nota[]);
    const odontograma$ = this.puedeLeerOdontogramas
      ? this.api.odontograma(pacienteId).pipe(this.alFallarFuente<Odontograma | null>(null))
      : of(null);
    const registrosPlaca$ = this.puedeLeerRegistrosPlaca
      ? this.api.indicePlaca(pacienteId).pipe(this.alFallarFuente([] as readonly RegistroPlaca[]))
      : of([] as readonly RegistroPlaca[]);

    forkJoin({ citas: citas$, notas: notas$, odontograma: odontograma$, registrosPlaca: registrosPlaca$ })
      .subscribe((fuentes) => {
        if (this.pacienteId() !== pacienteId) return;
        const profesionalId = this.sesion.identidad()?.profesional_id;
        this.citas.set(fuentes.citas.elementos.filter((cita) =>
          cita.profesional_id === profesionalId && cita.estado !== 'CANCELLED' && cita.estado !== 'NO_SHOW',
        ));
        this.notas.set(fuentes.notas.filter((nota) => nota.vigente));
        this.odontograma.set(fuentes.odontograma?.vigente ? fuentes.odontograma : null);
        this.registrosPlaca.set(fuentes.registrosPlaca);
        this.cargandoFuentes.set(false);
      });
  }

  private alFallarFuente<T>(vacio: T): OperatorFunction<T, T> {
    return catchError((): Observable<T> => {
      this.errorFuentes.set('No se pudieron cargar algunas fuentes clínicas. Puede volver a intentarlo o guardar sin vincularlas.');
      return of(vacio);
    });
  }

  private limpiarFuentes(): void {
    this.citas.set([]);
    this.notas.set([]);
    this.odontograma.set(null);
    this.registrosPlaca.set([]);
    this.cargandoFuentes.set(false);
  }

  private limpiarVinculos(): void {
    this.citaId = '';
    this.notaId = '';
    this.odontogramaId = '';
    this.registroPlacaId = '';
    this.avisoFuentes.set('');
  }

  protected actualizarMotivo(evento: Event): void {
    const campo = evento.currentTarget;
    if (campo instanceof HTMLTextAreaElement) this.datos.motivo_consulta = campo.value;
  }

  protected etiqueta(codigo: string): string {
    return codigo.replaceAll('_', ' ').toLocaleLowerCase('es').replace(/(^|\s)\S/g, (letra) => letra.toLocaleUpperCase('es'));
  }

  protected presencia(valor: boolean | null): string {
    return valor === null ? 'Sin registro' : valor ? 'Sí' : 'No';
  }

  private mensajeError(fallo: unknown): string {
    return fallo instanceof FalloApi ? fallo.message : 'No se pudo completar la operación. Revise la conexión e intente otra vez.';
  }
}
