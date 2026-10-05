/**
 * Prescripción: crear una receta en borrador y confirmarla.
 *
 * Lo escribe y lo confirma un profesional; la IA no participa (regla 5).
 * Solo la confirmación genera el calendario de tomas. Un medicamento «cuando
 * sea necesario» no lleva frecuencia: no se convierte en horario fijo.
 *
 * Firma: por defecto, quien firma la sesión. Si el profesional tiene una
 * delegación vigente registrada por administración, puede firmar por su
 * adjunto; el servidor vuelve a comprobarla y la auditoría lo marca.
 */
import { Component, computed, effect, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService, FalloApi } from '../../nucleo/servicios/api.service';
import type {
  DelegacionFirma,
  MedicamentoNuevo,
  Receta,
} from '../../nucleo/servicios/api.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';

const VIAS = [
  'ORAL',
  'TOPICA',
  'INHALATORIA',
  'INTRAMUSCULAR',
  'INTRAVENOSA',
  'SUBCUTANEA',
  'OFTALMICA',
  'OTICA',
  'RECTAL',
  'OTRA',
] as const;

function lineaVacia(): MedicamentoNuevo {
  return {
    nombre: '',
    dosis: '',
    via: 'ORAL',
    concentracion: null,
    cuando_sea_necesario: false,
    frecuencia_horas: 8,
    duracion_dias: null,
    instrucciones: null,
  };
}

@Component({
  selector: 'app-receta-editor',
  standalone: true,
  imports: [FormsModule],
  template: `
    <form class="tarjeta editor-receta" (ngSubmit)="crear()">
      <h3>Nueva receta (borrador)</h3>
      <p class="campo__ayuda">
        El borrador no genera recordatorios. Al confirmarlo se crea el calendario de tomas.
      </p>
      @for (linea of lineas(); track $index; let i = $index) {
        <fieldset class="linea">
          <legend class="campo__etiqueta">Medicamento {{ i + 1 }}</legend>
          <div class="linea__rejilla">
            <label class="campo"><span class="campo__etiqueta">Nombre</span>
              <input class="campo__control" [name]="'nombre' + i" [(ngModel)]="linea.nombre" maxlength="200" />
            </label>
            <label class="campo"><span class="campo__etiqueta">Concentración</span>
              <input class="campo__control" [name]="'conc' + i" [(ngModel)]="linea.concentracion" maxlength="64" />
            </label>
            <label class="campo"><span class="campo__etiqueta">Dosis</span>
              <input class="campo__control" [name]="'dosis' + i" [(ngModel)]="linea.dosis" maxlength="120" />
            </label>
            <label class="campo"><span class="campo__etiqueta">Vía</span>
              <select class="campo__control" [name]="'via' + i" [(ngModel)]="linea.via">
                @for (via of vias; track via) { <option [value]="via">{{ via.toLowerCase() }}</option> }
              </select>
            </label>
            <label class="campo"><span class="campo__etiqueta">Cada (horas)</span>
              <input class="campo__control numerico" type="number" min="1" max="168" [name]="'frec' + i" [(ngModel)]="linea.frecuencia_horas" [disabled]="linea.cuando_sea_necesario" />
            </label>
            <label class="campo"><span class="campo__etiqueta">Durante (días)</span>
              <input class="campo__control numerico" type="number" min="1" max="365" [name]="'dur' + i" [(ngModel)]="linea.duracion_dias" />
            </label>
          </div>
          <label class="campo--en-linea">
            <input type="checkbox" [name]="'prn' + i" [(ngModel)]="linea.cuando_sea_necesario" (ngModelChange)="alternarPrn(linea, $event)" />
            Solo cuando sea necesario (sin horario fijo)
          </label>
          <label class="campo"><span class="campo__etiqueta">Instrucciones</span>
            <input class="campo__control" [name]="'instr' + i" [(ngModel)]="linea.instrucciones" maxlength="1000" />
          </label>
          @if (lineas().length > 1) {
            <button type="button" class="boton boton--plano boton--pequeno" (click)="quitar(i)">Quitar medicamento</button>
          }
        </fieldset>
      }
      <button type="button" class="boton boton--pequeno" (click)="agregar()">Añadir medicamento</button>

      <label class="campo"><span class="campo__etiqueta">Indicaciones generales</span>
        <textarea class="campo__control" name="indicaciones" rows="2" maxlength="2000" [(ngModel)]="indicaciones"></textarea>
      </label>
      <label class="campo"><span class="campo__etiqueta">Firma</span>
        <select class="campo__control" name="firmante" [(ngModel)]="firmante">
          @for (opcion of firmantes(); track opcion.id) {
            <option [value]="opcion.id">{{ opcion.texto }}</option>
          }
        </select>
        @if (firmantes().length > 1) {
          <span class="campo__ayuda">Firmar por otro profesional requiere una delegación vigente; queda auditado.</span>
        }
      </label>
      @if (error()) { <p class="aviso-error" role="alert">{{ error() }}</p> }
      <div class="acciones acciones--final">
        <button class="boton" type="button" (click)="cancelado.emit()">Cancelar</button>
        <button class="boton boton--principal" type="submit" [disabled]="guardando()">
          {{ guardando() ? 'Guardando…' : 'Guardar borrador' }}
        </button>
      </div>
    </form>
  `,
  styles: `
    .editor-receta { display: grid; gap: var(--espacio-3); margin-bottom: var(--espacio-4); }
    .editor-receta h3 { margin: 0; }
    .linea { display: grid; gap: var(--espacio-2); margin: 0; padding: var(--espacio-3); border: 1px solid var(--borde); border-radius: var(--radio); }
    .linea__rejilla { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: var(--espacio-3); }
    .linea .boton, .editor-receta > .boton { justify-self: start; }
  `,
})
export class RecetaEditorComponent {
  private readonly api = inject(ApiService);
  private readonly sesion = inject(SesionService);

  readonly pacienteId = input.required<string>();
  readonly guardada = output<Receta>();
  readonly cancelado = output<void>();

  protected readonly vias = VIAS;
  protected readonly lineas = signal<MedicamentoNuevo[]>([lineaVacia()]);
  protected readonly delegaciones = signal<readonly DelegacionFirma[]>([]);
  protected readonly guardando = signal(false);
  protected readonly error = signal('');
  protected indicaciones = '';
  protected firmante = '';

  protected readonly propio = computed(() => this.sesion.identidad()?.profesional_id ?? null);
  protected readonly firmantes = computed(() => {
    const propio = this.propio();
    const lista = propio ? [{ id: propio, texto: 'Firmo yo' }] : [];
    for (const delegacion of this.delegaciones()) {
      if (delegacion.vigente && delegacion.delegado_id === propio) {
        lista.push({ id: delegacion.delegante_id, texto: `Por delegación (${delegacion.motivo})` });
      }
    }
    return lista;
  });

  constructor() {
    effect(() => {
      this.firmante = this.propio() ?? '';
    });
    this.api.delegacionesMias().subscribe({
      next: (lista) => this.delegaciones.set(lista),
      error: () => this.delegaciones.set([]),
    });
  }

  protected agregar(): void {
    this.lineas.update((lista) => [...lista, lineaVacia()]);
  }

  protected quitar(indice: number): void {
    this.lineas.update((lista) => lista.filter((_, i) => i !== indice));
  }

  protected alternarPrn(linea: MedicamentoNuevo, prn: boolean): void {
    // Un PRN no tiene frecuencia: se borra en lugar de dejarla oculta.
    linea.frecuencia_horas = prn ? null : (linea.frecuencia_horas ?? 8);
  }

  protected crear(): void {
    if (this.guardando()) return;
    const medicamentos = this.lineas().map((linea) => ({
      ...linea,
      nombre: linea.nombre.trim(),
      dosis: linea.dosis.trim(),
      concentracion: linea.concentracion?.trim() || null,
      instrucciones: linea.instrucciones?.trim() || null,
    }));
    if (medicamentos.some((m) => m.nombre.length < 2 || !m.dosis)) {
      this.error.set('Cada medicamento necesita nombre y dosis.');
      return;
    }
    if (medicamentos.some((m) => !m.cuando_sea_necesario && !m.frecuencia_horas)) {
      this.error.set('Una pauta fija necesita la frecuencia en horas, o márquela como «cuando sea necesario».');
      return;
    }
    if (!this.firmante) {
      this.error.set('Su cuenta no está vinculada a un profesional: no puede firmar recetas.');
      return;
    }
    this.guardando.set(true);
    this.error.set('');
    this.api
      .crearReceta({
        paciente_id: this.pacienteId(),
        profesional_id: this.firmante,
        indicaciones_generales: this.indicaciones.trim() || null,
        medicamentos,
      })
      .subscribe({
        next: (receta) => {
          this.guardando.set(false);
          this.guardada.emit(receta);
        },
        error: (fallo: unknown) => {
          this.guardando.set(false);
          this.error.set(fallo instanceof FalloApi ? fallo.message : 'No se pudo guardar la receta.');
        },
      });
  }
}
