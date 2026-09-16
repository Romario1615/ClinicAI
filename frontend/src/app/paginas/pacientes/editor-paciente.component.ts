import { Component, EventEmitter, Input, OnChanges, Output, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
import type { Paciente } from '../../nucleo/modelos/dominio';
import { FalloApi } from '../../nucleo/servicios/api.service';
import { OperacionesService } from '../../nucleo/servicios/operaciones.service';

/**
 * Alta y edicion de un paciente, en una ventana flotante.
 *
 * Por que flotante y no en la pagina
 * ----------------------------------
 * El formulario se pintaba encima del listado y lo empujaba hacia abajo: al
 * abrirlo, la fila que se iba a editar dejaba de estar donde estaba, y al
 * guardar habia que volver a buscarla. Ahora el listado no se mueve.
 *
 * No se cierra al pulsar fuera: son diez campos, y perderlos por un clic
 * despistado se paga en una recepcion con prisa.
 */
@Component({
  selector: 'app-editor-paciente',
  standalone: true,
  imports: [FormsModule, VentanaFlotanteComponent],
  template: `
    <app-ventana-flotante
      ceja="Paciente"
      [titulo]="paciente ? 'Editar paciente' : 'Registrar paciente'"
      forma="centrada"
      [anchoMaximo]="640"
      [cierraAlPulsarFuera]="false"
      (cerrar)="cerrar.emit()"
    >
      <form #formulario="ngForm" (ngSubmit)="guardar()">
        <div class="rejilla-campos">
          <label class="campo">
            <span class="campo__etiqueta">Nombres</span>
            <input class="campo__control" name="nombre" [(ngModel)]="nombre" required maxlength="100" />
          </label>
          <label class="campo">
            <span class="campo__etiqueta">Apellidos</span>
            <input class="campo__control" name="apellido" [(ngModel)]="apellido" required maxlength="100" />
          </label>
          <label class="campo">
            <span class="campo__etiqueta">Tipo de documento</span>
            <select class="campo__control" name="tipo" [(ngModel)]="tipo">
              <option>CEDULA</option>
              <option>PASAPORTE</option>
              <option>RUC</option>
              <option>SIN_DOCUMENTO</option>
            </select>
          </label>
          @if (tipo !== 'SIN_DOCUMENTO') {
            <label class="campo">
              <span class="campo__etiqueta">Número de documento</span>
              <input
                class="campo__control"
                name="numero"
                [(ngModel)]="numero"
                required
                minlength="3"
                maxlength="32"
              />
            </label>
          }
          <label class="campo">
            <span class="campo__etiqueta">Fecha de nacimiento</span>
            <input class="campo__control" type="date" name="nacimiento" [(ngModel)]="nacimiento" />
          </label>
          <label class="campo">
            <span class="campo__etiqueta">WhatsApp</span>
            <input
              class="campo__control"
              type="tel"
              name="telefono"
              [(ngModel)]="telefono"
              maxlength="32"
              placeholder="Código de país y número"
            />
            <span class="campo__ayuda">Sin teléfono no recibe recordatorios ni ofertas.</span>
          </label>
          <label class="campo">
            <span class="campo__etiqueta">Correo</span>
            <input
              class="campo__control"
              type="email"
              name="correo"
              [(ngModel)]="correo"
              email
              maxlength="200"
            />
          </label>
          <label class="campo">
            <span class="campo__etiqueta">Dirección</span>
            <input class="campo__control" name="direccion" [(ngModel)]="direccion" maxlength="500" />
          </label>
        </div>

        @if (error()) {
          <p class="aviso-error" role="alert">{{ error() }}</p>
        }

        <div class="acciones acciones--final">
          <button type="button" class="boton" (click)="cerrar.emit()" [disabled]="ocupado()">
            Cancelar
          </button>
          <button
            type="submit"
            class="boton boton--principal"
            [disabled]="formulario.invalid || ocupado()"
          >
            {{ ocupado() ? 'Guardando…' : 'Guardar paciente' }}
          </button>
        </div>
      </form>
    </app-ventana-flotante>
  `,
  styles: `
    .rejilla-campos {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: var(--espacio-4);
    }

    .rejilla-campos .campo {
      margin-bottom: 0;
    }

    .acciones {
      margin-top: var(--espacio-5);
      padding-top: var(--espacio-4);
      border-top: 1px solid var(--borde);
    }
  `,
})
export class EditorPacienteComponent implements OnChanges {
  private readonly api = inject(OperacionesService);
  @Input() paciente: (Paciente & { direccion?: string | null }) | null = null;
  @Output() readonly guardado = new EventEmitter<Paciente>();
  @Output() readonly cerrar = new EventEmitter<void>();
  protected nombre = ''; protected apellido = ''; protected tipo = 'CEDULA'; protected numero = '';
  protected nacimiento = ''; protected telefono = ''; protected correo = ''; protected direccion = '';
  protected readonly ocupado = signal(false); protected readonly error = signal('');
  private clave = crypto.randomUUID(); private ultimoCuerpo = '';
  ngOnChanges(): void {
    const p = this.paciente;
    this.nombre = p?.nombre ?? ''; this.apellido = p?.apellido ?? ''; this.tipo = p?.tipo_documento ?? 'CEDULA';
    this.numero = p?.numero_documento ?? ''; this.nacimiento = p?.fecha_nacimiento ?? '';
    this.telefono = p?.telefono_whatsapp ?? ''; this.correo = p?.correo ?? ''; this.direccion = p?.direccion ?? '';
    this.clave = crypto.randomUUID(); this.ultimoCuerpo = ''; this.error.set('');
  }
  protected guardar(): void {
    if (this.ocupado()) return;
    const datos = { nombre: this.nombre.trim(), apellido: this.apellido.trim(), tipo_documento: this.tipo,
      numero_documento: this.tipo === 'SIN_DOCUMENTO' ? null : this.numero.trim(), fecha_nacimiento: this.nacimiento || null,
      telefono_whatsapp: this.telefono.trim() || null, correo: this.correo.trim() || null, direccion: this.direccion.trim() || null };
    const cuerpo = JSON.stringify(datos);
    if (this.ultimoCuerpo && cuerpo !== this.ultimoCuerpo) this.clave = crypto.randomUUID();
    this.ultimoCuerpo = cuerpo; this.ocupado.set(true); this.error.set('');
    this.api.guardar<Paciente>(this.paciente ? `/pacientes/${this.paciente.id}` : '/pacientes/', datos, this.clave, !!this.paciente).subscribe({
      next: p => { this.ocupado.set(false); this.guardado.emit(p); },
      error: (e: FalloApi) => { this.error.set(e.message); this.ocupado.set(false); },
    });
  }
}
