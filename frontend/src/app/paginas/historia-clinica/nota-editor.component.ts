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
import { Component, OnInit, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService, FalloApi } from '../../nucleo/servicios/api.service';
import type { Nota, NotaNueva } from '../../nucleo/servicios/api.service';

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
  imports: [FormsModule],
  template: `
    <form class="tarjeta editor-nota" (ngSubmit)="guardar()">
      <h3>{{ base() ? 'Corregir nota (versión nueva)' : 'Nueva nota de evolución' }}</h3>
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
      <div class="acciones acciones--final">
        <button class="boton" type="button" (click)="cancelado.emit()">Cancelar</button>
        <button class="boton boton--principal" type="submit" [disabled]="guardando()">
          {{ guardando() ? 'Guardando…' : base() ? 'Guardar versión nueva' : 'Guardar nota' }}
        </button>
      </div>
    </form>
  `,
  styles: `
    .editor-nota { display: grid; gap: var(--espacio-2); margin-bottom: var(--espacio-4); }
    .editor-nota h3 { margin: 0 0 var(--espacio-2); }
    .editor-nota__fila { display: grid; grid-template-columns: minmax(160px, 220px) 1fr; gap: var(--espacio-3); }
    .editor-nota__signos { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: var(--espacio-3); margin: 0; padding: var(--espacio-3); border: 1px solid var(--borde); border-radius: var(--radio); }
    @media (max-width: 640px) { .editor-nota__fila { grid-template-columns: 1fr; } }
  `,
})
export class NotaEditorComponent implements OnInit {
  private readonly api = inject(ApiService);

  readonly pacienteId = input.required<string>();
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
  protected valores: Record<string, string> = { subjetivo: '', objetivo: '', analisis: '', plan: '' };
  protected vitales: Record<string, number | null> = {};
  protected motivo = '';
  protected readonly guardando = signal(false);
  protected readonly error = signal('');

  ngOnInit(): void {
    const nota = this.base();
    if (!nota) return;
    this.tipo = (nota.tipo as NotaNueva['tipo']) ?? 'EVOLUCION';
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
      tipo: this.tipo,
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
    peticion.subscribe({
      next: (nota) => {
        this.guardando.set(false);
        this.guardada.emit(nota);
      },
      error: (fallo: unknown) => {
        this.guardando.set(false);
        this.error.set(fallo instanceof FalloApi ? fallo.message : 'No se pudo guardar la nota.');
      },
    });
  }
}
