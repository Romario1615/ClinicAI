/**
 * Editor de notas de evolución (SOAP).
 *
 * Dos modos: nota nueva, o corrección de una existente. Corregir **no
 * reescribe**: el servidor crea una versión nueva y conserva la anterior, y
 * exige el motivo del cambio. El autor es siempre quien firma la sesión; no se
 * envía en la petición.
 *
 * Signos vitales opcionales, solo números. Nada de lo escrito aquí sale en
 * mensajes al paciente (regla 10).
 */
import { Component, OnInit, inject, input, output, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CapturaFotosComponent, type FotoSeleccionada } from '../../compartido/captura-fotos.component';
import { FotosRegistroService } from '../../nucleo/servicios/fotos-registro.service';

import { ApiService, FalloApi } from '../../nucleo/servicios/api.service';
import type { Nota, NotaNueva } from '../../nucleo/servicios/api.service';
import { PERMISOS } from '../../nucleo/servicios/configuracion';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';

const TIPOS = [
  { valor: 'EVOLUCION', texto: 'Evolución' },
  { valor: 'PROCEDIMIENTO', texto: 'Procedimiento' },
  { valor: 'INTERCONSULTA', texto: 'Interconsulta' },
  { valor: 'ENFERMERIA', texto: 'Enfermería' },
] as const;

const SIGNOS = [
  { clave: 'presion_sistolica', texto: 'PA sistólica (mmHg)' },
  { clave: 'presion_diastolica', texto: 'PA diastólica (mmHg)' },
  { clave: 'frecuencia_cardiaca', texto: 'FC (lpm)' },
  { clave: 'temperatura', texto: 'Temperatura (°C)' },
] as const;

@Component({
  selector: 'app-nota-editor',
  standalone: true,
  imports: [FormsModule, VentanaFlotanteComponent, CapturaFotosComponent],
  template: `
    @if (abierta()) {
      <!-- La ventana protege lo escrito: mientras se guarda no se cierra, y
           con cambios pide confirmación antes de descartarlos (Escape, la X o
           Cancelar pasan por el mismo sitio). -->
      <app-ventana-flotante
        #v
        ceja="Historia clínica"
        [titulo]="base() ? 'Corregir nota · versión nueva' : 'Nueva nota de evolución'"
        forma="centrada"
        [anchoMaximo]="960"
        [altoCompleto]="true"
        [cierraAlPulsarFuera]="false"
        [ocupada]="guardando()"
        [cambiosSinGuardar]="hayCambios()"
        (cerrar)="cerrar()"
      >
    <form id="form-nota" class="editor-nota" (ngSubmit)="guardar()">
      <div class="editor-nota__fila">
        <label class="campo">
          <span class="campo__etiqueta">Tipo</span>
          <select class="campo__control" name="tipo" [(ngModel)]="tipo">
            @for (opcion of tipos; track opcion.valor) {
              <option [value]="opcion.valor">{{ opcion.texto }}</option>
            }
          </select>
        </label>
        <label class="campo editor-nota__ancho">
          <span class="campo__etiqueta">Motivo de consulta</span>
          <input class="campo__control" name="motivoConsulta" maxlength="500" [(ngModel)]="motivoConsulta" />
        </label>
      </div>
      <label class="campo">
        <span class="campo__etiqueta">Sensibilidad de la nota</span>
        <select class="campo__control" name="nivelSensibilidad" [(ngModel)]="nivelSensibilidad">
          <option value="N2">Clínica · N2</option>
          @if (puedeLeerSensible()) { <option value="N3">Clínica sensible · N3</option> }
        </select>
        <span class="campo__ayuda">Las notas N3 solo son visibles con permiso clínico sensible. Una corrección nunca reduce la sensibilidad de la versión anterior.</span>
      </label>
      @for (campo of soap; track campo.clave) {
        <label class="campo">
          <span class="campo__etiqueta">{{ campo.texto }}</span>
          <textarea class="campo__control" rows="3" [name]="campo.clave" [(ngModel)]="valores[campo.clave]"></textarea>
        </label>
      }
      <fieldset class="editor-nota__signos">
        <legend class="campo__etiqueta">Signos vitales (opcional)</legend>
        @for (signo of signos; track signo.clave) {
          <label class="campo">
            <span class="campo__etiqueta">{{ signo.texto }}</span>
            <input class="campo__control numerico" type="number" step="0.1" [name]="signo.clave" [(ngModel)]="vitales[signo.clave]" />
          </label>
        }
      </fieldset>
      @if (base()) {
        <label class="campo">
          <span class="campo__etiqueta">Motivo de la corrección</span>
          <input class="campo__control" name="motivo" maxlength="500" [(ngModel)]="motivo" />
          <span class="campo__ayuda">La versión anterior se conserva y sigue consultable.</span>
        </label>
      }
      @if (error()) {
        <p class="aviso-error" role="alert">{{ error() }}</p>
      }
      @if (puedeFotos()) { <app-captura-fotos titulo="Fotografías del registro" [ocupada]="guardando()" (cambiadas)="fotos=$event" /> }
    </form>
        <div class="acciones acciones--final" pie>
          <button class="boton" type="button" [disabled]="guardando()" (click)="v.solicitarCierre()">Cancelar</button>
          <button class="boton boton--principal" type="submit" form="form-nota" [disabled]="guardando()">
            {{ guardando() ? 'Guardando…' : base() ? 'Guardar versión nueva' : 'Guardar nota' }}
          </button>
        </div>
      </app-ventana-flotante>
    }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    .editor-nota { display: grid; gap: var(--espacio-3); }
    .editor-nota__fila { display: grid; grid-template-columns: minmax(160px, 220px) 1fr; gap: var(--espacio-3); }
    .editor-nota__signos { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: var(--espacio-3); margin: 0; padding: var(--espacio-3); border: 1px solid var(--borde); border-radius: var(--radio); }
    @media (max-width: 640px) { .editor-nota__fila { grid-template-columns: 1fr; } }
  `,
})
export class NotaEditorComponent implements OnInit {
  private readonly api = inject(ApiService);
  protected readonly operacionFotos = inject(FotosRegistroService).operacion<Nota>();
  protected fotos: readonly FotoSeleccionada[] = [];
  protected puedeFotos(): boolean { return this.sesion.tienePermiso(PERMISOS.imagenClinicaCargar); }
  private readonly sesion = inject(SesionService);

  readonly pacienteId = input.required<string>();
  readonly citaId = input<string | null>(null);
  /** Nota a corregir. Sin ella, el editor crea una nota nueva. */
  readonly base = input<Nota | null>(null);
  readonly guardada = output<Nota>();
  readonly cancelado = output<void>();

  protected readonly tipos = TIPOS;
  protected readonly signos = SIGNOS;
  protected readonly soap = [
    { clave: 'subjetivo', texto: 'Subjetivo (lo que refiere el paciente)' },
    { clave: 'objetivo', texto: 'Objetivo (exploración)' },
    { clave: 'analisis', texto: 'Análisis' },
    { clave: 'plan', texto: 'Plan' },
  ] as const;

  protected tipo: NotaNueva['tipo'] = 'EVOLUCION';
  protected motivoConsulta = '';
  protected nivelSensibilidad: NotaNueva['nivel_sensibilidad'] = 'N2';
  protected valores: Record<string, string> = { subjetivo: '', objetivo: '', analisis: '', plan: '' };
  protected vitales: Record<string, number | null> = {};
  protected motivo = '';
  protected readonly abierta = signal(true);
  protected readonly guardando = signal(false);
  protected readonly error = signal('');
  /** Lo que había al abrir: con eso se sabe si cerrar perdería algo. */
  private huellaInicial = '';

  ngOnInit(): void {
    this.cargarBase();
    this.huellaInicial = this.huella();
  }

  /** Hay algo escrito (o cambiado) que cerrar perdería. */
  protected hayCambios(): boolean {
    return this.fotos.length > 0 || this.huella() !== this.huellaInicial;
  }

  /**
   * El contenido del formulario en una cadena comparable. Los espacios en los
   * extremos y los signos vacíos no cuentan como cambio.
   */
  private huella(): string {
    const vitales = Object.entries(this.vitales)
      .filter((par): par is [string, number] => typeof par[1] === 'number' && Number.isFinite(par[1]))
      .sort(([a], [b]) => a.localeCompare(b));
    return JSON.stringify({
      tipo: this.tipo,
      motivoConsulta: this.motivoConsulta.trim(),
      nivelSensibilidad: this.nivelSensibilidad,
      valores: Object.fromEntries(Object.entries(this.valores).map(([clave, valor]) => [clave, (valor ?? '').trim()])),
      vitales,
      motivo: this.motivo.trim(),
    });
  }

  private cargarBase(): void {
    const nota = this.base();
    if (!nota) return;
    this.tipo = (nota.tipo as NotaNueva['tipo']) ?? 'EVOLUCION';
    this.nivelSensibilidad = nota.nivel_sensibilidad;
    this.motivoConsulta = nota.motivo_consulta ?? '';
    this.valores = {
      subjetivo: nota.subjetivo ?? '',
      objetivo: nota.objetivo ?? '',
      analisis: nota.analisis ?? '',
      plan: nota.plan ?? '',
    };
    for (const [clave, valor] of Object.entries(nota.signos_vitales ?? {})) {
      if (typeof valor === 'number') this.vitales[clave] = valor;
    }
  }

  protected guardar(): void {
    if (this.guardando()) return;
    const texto = (valor: string) => valor.trim() || null;
    const vitales = Object.fromEntries(
      Object.entries(this.vitales).filter(
        (par): par is [string, number] => typeof par[1] === 'number' && Number.isFinite(par[1]),
      ),
    );
    const datos: NotaNueva = {
      paciente_id: this.pacienteId(),
      ...(this.citaId() ? { cita_id: this.citaId() } : {}),
      tipo: this.tipo,
      nivel_sensibilidad: this.nivelSensibilidad,
      motivo_consulta: texto(this.motivoConsulta),
      subjetivo: texto(this.valores['subjetivo']),
      objetivo: texto(this.valores['objetivo']),
      analisis: texto(this.valores['analisis']),
      plan: texto(this.valores['plan']),
      signos_vitales: Object.keys(vitales).length ? vitales : null,
    };
    if (!datos.subjetivo && !datos.objetivo && !datos.analisis && !datos.plan) {
      this.error.set('Escriba al menos una sección de la nota.');
      return;
    }
    const base = this.base();
    if (base && this.motivo.trim().length < 5) {
      this.error.set('Indique el motivo de la corrección (mínimo 5 caracteres).');
      return;
    }
    this.guardando.set(true);
    this.error.set('');
    const peticion = base
      ? this.api.corregirNota(base.raiz_id, { ...datos, motivo: this.motivo.trim() })
      : this.api.crearNota(datos);
    this.operacionFotos.guardar('nota', peticion, this.fotos).subscribe({
      next: (nota) => {
        this.guardando.set(false);
        this.abierta.set(false);
        this.guardada.emit(nota);
      },
      error: (fallo: unknown) => {
        this.guardando.set(false);
        this.error.set(fallo instanceof FalloApi ? fallo.message : 'No se pudo guardar la nota.');
      },
    });
  }

  /**
   * Cierre ya confirmado: la ventana solo lo pide tras «Descartar cambios»
   * cuando hay algo escrito, y nunca a mitad de guardado.
   */
  protected cerrar(): void {
    if (this.guardando()) return;
    this.abierta.set(false);
    this.cancelado.emit();
  }

  protected puedeLeerSensible(): boolean {
    return this.sesion.tienePermiso(PERMISOS.historiaLeerSensible);
  }
}
