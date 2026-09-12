/**
 * Pantalla de acceso.
 *
 * Cuatro decisiones que no son estéticas
 * --------------------------------------
 * **El mensaje de error no distingue la causa.** Correo inexistente,
 * contraseña incorrecta y cuenta desactivada devuelven lo mismo desde el
 * backend, y aquí se muestra tal cual. Refinarlo («ese correo no existe»)
 * permitiría enumerar al personal de la clínica probando direcciones.
 *
 * **La cuenta bloqueada sí se distingue.** Comparte el 401 con el resto, pero
 * su `codigo` es `CUENTA_BLOQUEADA` y el mensaje indica cuántos minutos
 * faltan. Es el único caso donde informar gana: una recepcionista bloqueada a
 * las 08:00 necesita saber que tiene que esperar, no seguir probando
 * contraseñas que agravan el bloqueo.
 *
 * **El campo del segundo factor aparece solo cuando el backend lo pide.**
 * Mostrarlo siempre haría que quien no tiene 2FA configurado creyera que le
 * falta algo.
 *
 * **La contraseña no se guarda en ningún sitio, ni siquiera en el estado del
 * formulario más allá del envío.** El correo sí se recuerda, porque no es una
 * credencial y teclearlo cada mañana es fricción sin beneficio.
 */
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';

import { FalloApi } from '../../nucleo/servicios/api.service';
import { AutenticacionService } from '../../nucleo/servicios/autenticacion.service';
import { CONFIGURACION } from '../../nucleo/servicios/configuracion';
import { SesionService } from '../../nucleo/servicios/sesion.service';

@Component({
  selector: 'app-acceso',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './acceso.component.html',
  styleUrl: './acceso.component.scss',
})
export class AccesoComponent {
  private readonly autenticacion = inject(AutenticacionService);
  private readonly router = inject(Router);
  private readonly ruta = inject(ActivatedRoute);
  private readonly configuracion = inject(CONFIGURACION);
  protected readonly sesion = inject(SesionService);

  protected correo = this.sesion.correoRecordado();
  protected contrasena = '';
  protected codigo2fa = '';
  protected clinicaId = this.configuracion.clinicaPorDefecto;
  protected recordar = this.sesion.correoRecordado() !== '';

  protected readonly enviando = signal(false);
  protected readonly error = signal<FalloApi | null>(null);

  /**
   * Cierto cuando hay que pedir el código del segundo factor.
   *
   * El backend lo indica de dos formas distintas: con
   * `SEGUNDO_FACTOR_REQUERIDO` cuando falta el código, y con
   * `SEGUNDO_FACTOR_INVALIDO` cuando el enviado no vale. En ambos casos el
   * campo debe seguir visible.
   */
  protected readonly pideSegundoFactor = computed(() => {
    const codigo = this.error()?.codigo;
    return codigo === 'SEGUNDO_FACTOR_REQUERIDO' || codigo === 'SEGUNDO_FACTOR_INVALIDO';
  });

  /** El identificador de clínica solo se pide si el despliegue no lo fija. */
  protected readonly pideClinica = this.configuracion.clinicaPorDefecto === '';

  protected readonly mensajeError = computed(() => this.error()?.message ?? '');

  /**
   * Cierto si el fallo es del sistema y no de las credenciales.
   *
   * Cambia el tono del mensaje: «revise sus datos» no sirve de nada cuando el
   * problema es que el servidor no responde.
   */
  protected readonly esFalloDelSistema = computed(() => {
    const estado = this.error()?.estado ?? 0;
    return estado === 0 || estado >= 500;
  });

  protected entrar(): void {
    if (this.enviando()) {
      return;
    }
    this.error.set(null);
    this.enviando.set(true);

    this.autenticacion
      .iniciarSesion({
        correo: this.correo,
        contrasena: this.contrasena,
        clinicaId: this.clinicaId,
        codigo2fa: this.codigo2fa || null,
        recordarCorreo: this.recordar,
      })
      .subscribe({
        next: () => {
          this.enviando.set(false);
          // La contraseña se borra del estado en cuanto deja de hacer falta.
          this.contrasena = '';
          this.codigo2fa = '';
          const destino = this.ruta.snapshot.queryParamMap.get('destino') ?? '/panel';
          void this.router.navigateByUrl(destino);
        },
        error: (fallo: unknown) => {
          this.enviando.set(false);
          this.contrasena = '';
          this.error.set(
            fallo instanceof FalloApi
              ? fallo
              : new FalloApi('ERROR_DESCONOCIDO', 'Ocurrió un error inesperado.', 0),
          );
        },
      });
  }
}
