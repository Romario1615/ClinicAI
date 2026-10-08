import { Component, EventEmitter, Input, OnChanges, Output, ViewChild, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule, NgForm } from '@angular/forms';

import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
import type { Paciente } from '../../nucleo/modelos/dominio';
import { FalloApi } from '../../nucleo/servicios/api.service';
import { OperacionesService } from '../../nucleo/servicios/operaciones.service';
import { CapturaFotosComponent, type FotoSeleccionada } from '../../compartido/captura-fotos.component';
import { FotosRegistroService } from '../../nucleo/servicios/fotos-registro.service';

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
  imports: [FormsModule, VentanaFlotanteComponent, CapturaFotosComponent],
  template: `
    <app-ventana-flotante
      ceja="Paciente"
      [titulo]="paciente ? 'Editar paciente' : 'Registrar paciente'"
      forma="centrada"
      [anchoMaximo]="640"
      [cierraAlPulsarFuera]="false"
      (cerrar)="cerrar.emit()"
    >
      <form #formulario="ngForm" (ngSubmit)="guardar()" novalidate>
        <p class="campo__ayuda formulario__leyenda">Los campos con <span class="obligatorio">*</span> son obligatorios.</p>
        <div class="rejilla-campos">
          <label class="campo">
            <span class="campo__etiqueta">Nombres</span>
            <input class="campo__control" name="nombre" [(ngModel)]="nombre" required maxlength="100" #campoNombre="ngModel" autocomplete="off" />
            @if (campoNombre.invalid && (campoNombre.touched || intentado())) {
              <span class="campo__error">Escriba los nombres del paciente.</span>
            }
          </label>
          <label class="campo">
            <span class="campo__etiqueta">Apellidos</span>
            <input class="campo__control" name="apellido" [(ngModel)]="apellido" required maxlength="100" #campoApellido="ngModel" autocomplete="off" />
            @if (campoApellido.invalid && (campoApellido.touched || intentado())) {
              <span class="campo__error">Escriba los apellidos del paciente.</span>
            }
          </label>
          <label class="campo">
            <span class="campo__etiqueta">Tipo de documento</span>
            <select class="campo__control" name="tipo" [(ngModel)]="tipo" required>
              <option value="CEDULA">Cédula</option>
              <option value="PASAPORTE">Pasaporte</option>
              <option value="RUC">RUC</option>
              <option value="SIN_DOCUMENTO">Sin documento</option>
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
                #campoNumero="ngModel"
                autocomplete="off"
              />
              @if (campoNumero.invalid && (campoNumero.touched || intentado())) {
                <span class="campo__error">Indique el número (mínimo 3 caracteres).</span>
              }
            </label>
          }
          <label class="campo">
            <span class="campo__etiqueta">Fecha de nacimiento</span>
            <input class="campo__control" type="date" name="nacimiento" [(ngModel)]="nacimiento" [max]="hoy" />
            @if (nacimiento && nacimiento > hoy) {
              <span class="campo__error">La fecha de nacimiento no puede estar en el futuro.</span>
            }
          </label>
          <label class="campo">
            <span class="campo__etiqueta">Sexo</span>
            <select class="campo__control" name="sexo" [(ngModel)]="sexo">
              <option value="">Sin registrar</option>
              <option value="F">Femenino</option>
              <option value="M">Masculino</option>
              <option value="OTRO">Otro</option>
            </select>
          </label>
          <label class="campo">
            <span class="campo__etiqueta">WhatsApp</span>
            <input
              class="campo__control"
              type="tel"
              name="telefono"
              [(ngModel)]="telefono"
              maxlength="32"
              pattern="^\\+?[0-9 ()-]{7,32}$"
              placeholder="+593 99 999 9999"
              #campoTelefono="ngModel"
            />
            @if (campoTelefono.invalid && (campoTelefono.touched || intentado())) {
              <span class="campo__error">Use solo números, con el código de país (ej. +593…).</span>
            } @else {
              <span class="campo__ayuda">Sin teléfono no recibe recordatorios ni ofertas.</span>
            }
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
              #campoCorreo="ngModel"
            />
            @if (campoCorreo.invalid && (campoCorreo.touched || intentado())) {
              <span class="campo__error">Revise el correo: debe tener la forma nombre&#64;dominio.com.</span>
            }
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
            [disabled]="ocupado()"
            (click)="intentado.set(true)"
          >
            {{ ocupado() ? 'Guardando…' : 'Guardar paciente' }}
          </button>
        </div>
        <app-captura-fotos titulo="Foto de perfil" [perfil]="true" [ocupada]="ocupado()" (cambiadas)="fotos=$event" />
      </form>
    </app-ventana-flotante>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
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
  protected readonly operacionFotos = inject(FotosRegistroService).operacion<Paciente>();
  protected fotos: readonly FotoSeleccionada[] = [];
  @Input() paciente: (Paciente & { direccion?: string | null }) | null = null;
  @Output() readonly guardado = new EventEmitter<Paciente>();
  @Output() readonly cerrar = new EventEmitter<void>();
  protected nombre = ''; protected apellido = ''; protected tipo = 'CEDULA'; protected numero = '';
  protected nacimiento = ''; protected telefono = ''; protected correo = ''; protected direccion = '';
  protected readonly ocupado = signal(false); protected readonly error = signal('');
  /** Tras el primer intento de guardar, todos los errores se muestran aunque el campo no se haya tocado. */
  protected readonly intentado = signal(false);
  protected sexo = '';
  protected readonly hoy = new Date().toISOString().slice(0, 10);
  @ViewChild('formulario') private formulario?: NgForm;
  private clave = crypto.randomUUID(); private ultimoCuerpo = '';
  ngOnChanges(): void {
    this.operacionFotos.reiniciar(); this.fotos=[];
    const p = this.paciente;
    this.nombre = p?.nombre ?? ''; this.apellido = p?.apellido ?? ''; this.tipo = p?.tipo_documento ?? 'CEDULA';
    this.numero = p?.numero_documento ?? ''; this.nacimiento = p?.fecha_nacimiento ?? '';
    this.telefono = p?.telefono_whatsapp ?? ''; this.correo = p?.correo ?? ''; this.direccion = p?.direccion ?? '';
    this.sexo = (p as { sexo?: string | null } | null)?.sexo ?? '';
    this.clave = crypto.randomUUID(); this.ultimoCuerpo = ''; this.error.set(''); this.intentado.set(false);
  }
  protected guardar(): void {
    this.intentado.set(true);
    if (this.ocupado()) return;
    if (this.formulario?.invalid || (this.nacimiento && this.nacimiento > this.hoy)) {
      this.error.set('Revise los campos marcados antes de guardar.');
      return;
    }
    const datos = { nombre: this.nombre.trim(), apellido: this.apellido.trim(), tipo_documento: this.tipo,
      numero_documento: this.tipo === 'SIN_DOCUMENTO' ? null : this.numero.trim(), fecha_nacimiento: this.nacimiento || null,
      sexo: this.sexo || null,
      telefono_whatsapp: this.telefono.trim() || null, correo: this.correo.trim() || null, direccion: this.direccion.trim() || null };
    const cuerpo = JSON.stringify(datos);
    if (this.ultimoCuerpo && cuerpo !== this.ultimoCuerpo) this.clave = crypto.randomUUID();
    this.ultimoCuerpo = cuerpo; this.ocupado.set(true); this.error.set('');
    this.operacionFotos.guardar('perfil_paciente', this.api.guardar<Paciente>(this.paciente ? `/pacientes/${this.paciente.id}` : '/pacientes/', datos, this.clave, !!this.paciente), this.fotos).subscribe({
      next: p => { this.ocupado.set(false); this.guardado.emit(p); },
      error: (e: FalloApi) => { this.error.set(e.message); this.ocupado.set(false); },
    });
  }
}
