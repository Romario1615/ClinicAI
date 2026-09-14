import { Component, EventEmitter, Input, OnChanges, Output, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import type { Paciente } from '../../nucleo/modelos/dominio';
import { FalloApi } from '../../nucleo/servicios/api.service';
import { OperacionesService } from '../../nucleo/servicios/operaciones.service';

@Component({
  selector: 'app-editor-paciente', standalone: true, imports: [FormsModule],
  template: `
    <section class="tarjeta editor-demo"><h2>{{ paciente ? 'Editar paciente' : 'Registrar paciente' }}</h2>
      <form #formulario="ngForm" (ngSubmit)="guardar()">
        <div class="formulario-demo">
          <label>Nombres<input name="nombre" [(ngModel)]="nombre" required maxlength="100" /></label>
          <label>Apellidos<input name="apellido" [(ngModel)]="apellido" required maxlength="100" /></label>
          <label>Tipo de documento<select name="tipo" [(ngModel)]="tipo"><option>CEDULA</option><option>PASAPORTE</option><option>RUC</option><option>SIN_DOCUMENTO</option></select></label>
          @if (tipo !== 'SIN_DOCUMENTO') { <label>Número de documento<input name="numero" [(ngModel)]="numero" required minlength="3" maxlength="32" /></label> }
          <label>Fecha de nacimiento<input type="date" name="nacimiento" [(ngModel)]="nacimiento" /></label>
          <label>WhatsApp<input type="tel" name="telefono" [(ngModel)]="telefono" maxlength="32" placeholder="Código de país y número" /></label>
          <label>Correo<input type="email" name="correo" [(ngModel)]="correo" email maxlength="200" /></label>
          <label>Dirección<input name="direccion" [(ngModel)]="direccion" maxlength="500" /></label>
        </div>
        @if (error()) { <p class="aviso-error" role="alert">{{ error() }}</p> }
        <div class="acciones-demo"><button class="boton boton--principal" [disabled]="formulario.invalid || ocupado()">{{ ocupado() ? 'Guardando…' : 'Guardar paciente' }}</button>
          <button type="button" class="boton" (click)="cerrar.emit()" [disabled]="ocupado()">Cerrar formulario</button></div>
      </form>
    </section>
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
