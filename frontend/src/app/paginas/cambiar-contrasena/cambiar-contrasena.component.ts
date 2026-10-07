import { Component, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { FalloApi } from '../../nucleo/servicios/api.service';
import { OperacionesService } from '../../nucleo/servicios/operaciones.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';

@Component({
  selector: 'app-cambiar-contrasena',
  standalone: true,
  imports: [FormsModule],
  template: `
    <section class="tarjeta">
      <p class="sobretitulo">Seguridad de la cuenta</p>
      <h1>Elige una contraseña personal</h1>
      <p>Antes de entrar a la clínica, cambia la contraseña inicial que te compartió el administrador.</p>
      <form (ngSubmit)="guardar()">
        <label>Contraseña inicial<input name="actual" type="password" [(ngModel)]="actual" autocomplete="current-password" required /></label>
        <label>Nueva contraseña<input name="nueva" type="password" [(ngModel)]="nueva" autocomplete="new-password" minlength="12" maxlength="128" required /></label>
        <label>Repite la nueva contraseña<input name="confirmacion" type="password" [(ngModel)]="confirmacion" autocomplete="new-password" minlength="12" maxlength="128" required /></label>
        @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
        <button class="boton boton--principal" [disabled]="ocupado()">Actualizar contraseña</button>
      </form>
    </section>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    :host { min-height:70vh; display:grid; place-items:center; }
    .tarjeta { box-sizing:border-box; width:min(100% - 2rem, 480px); padding:2rem; border:1px solid #e4e7ec; border-radius:16px; background:white; }
    h1 { margin:.25rem 0 .75rem; } p { color:#667085; line-height:1.55; }
    .sobretitulo { color:#2c6e68; font-size:.8rem; font-weight:700; text-transform:uppercase; letter-spacing:.06em; }
    form,label { display:grid; gap:.75rem; } label { margin-top:1rem; color:#344054; font-size:.9rem; font-weight:600; }
    input { padding:.7rem .8rem; border:1px solid #d0d5dd; border-radius:8px; font:inherit; }
    .error { color:#b42318; } button { margin-top:1.25rem; }
  `,
})
export class CambiarContrasenaComponent {
  private readonly api = inject(OperacionesService);
  private readonly sesion = inject(SesionService);
  private readonly router = inject(Router);
  protected actual = '';
  protected nueva = '';
  protected confirmacion = '';
  protected readonly ocupado = signal(false);
  protected readonly error = signal('');

  protected guardar(): void {
    if (this.nueva !== this.confirmacion) { this.error.set('Las contraseñas nuevas no coinciden.'); return; }
    this.ocupado.set(true); this.error.set('');
    this.api.guardar<void>('/autenticacion/cambio-contrasena', {
      contrasena_actual: this.actual, contrasena_nueva: this.nueva,
    }, crypto.randomUUID()).subscribe({
      next: () => { this.sesion.limpiar(); void this.router.navigate(['/acceso']); },
      error: (fallo: FalloApi) => { this.error.set(fallo.message); this.ocupado.set(false); },
    });
  }
}
