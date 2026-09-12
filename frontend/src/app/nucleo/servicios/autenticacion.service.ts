/**
 * Inicio de sesion, cierre y rotacion del token.
 *
 * La rotacion es el punto delicado
 * --------------------------------
 * Cuando el token de acceso caduca, varias peticiones en vuelo reciben 401 a
 * la vez. Si cada una pidiera su propia rotacion, el backend veria **el mismo
 * refresco presentado varias veces** y lo interpretaria -- con razon -- como
 * un token robado: revocaria la familia completa de sesiones y echaria al
 * usuario.
 *
 * Por eso la rotacion se comparte: la primera peticion que la necesita inicia
 * el intercambio, y las demas esperan ese mismo resultado. `shareReplay` es
 * lo que lo consigue.
 */
import { Injectable, inject } from '@angular/core';
import { Observable, of, shareReplay, switchMap, tap, throwError } from 'rxjs';
import { catchError, map } from 'rxjs/operators';

import { ApiService, FalloApi } from './api.service';
import { SesionService } from './sesion.service';
import type { Identidad, ParTokens } from '../modelos/dominio';

export interface CredencialesAcceso {
  readonly correo: string;
  readonly contrasena: string;
  readonly clinicaId: string;
  readonly codigo2fa?: string | null;
  readonly recordarCorreo?: boolean;
}

@Injectable({ providedIn: 'root' })
export class AutenticacionService {
  private readonly api = inject(ApiService);
  private readonly sesion = inject(SesionService);

  /** Rotacion en curso, compartida entre todas las peticiones que la esperan. */
  private rotacionEnCurso: Observable<ParTokens> | null = null;

  iniciarSesion(credenciales: CredencialesAcceso): Observable<Identidad> {
    return this.api
      .iniciarSesion({
        correo: credenciales.correo.trim(),
        contrasena: credenciales.contrasena,
        clinica_id: credenciales.clinicaId.trim(),
        codigo_2fa: credenciales.codigo2fa?.trim() || null,
      })
      .pipe(
        tap((tokens) => {
          this.sesion.establecerTokens(tokens);
          if (credenciales.recordarCorreo) {
            this.sesion.recordarCorreo(credenciales.correo);
          }
        }),
        switchMap(() => this.cargarIdentidad()),
      );
  }

  cargarIdentidad(): Observable<Identidad> {
    return this.api.identidad().pipe(tap((identidad) => this.sesion.establecerIdentidad(identidad)));
  }

  /**
   * Cierra la sesion.
   *
   * Limpia el estado local **siempre**, incluso si la llamada al backend
   * falla. Dejar al usuario dentro porque no se pudo avisar al servidor seria
   * lo contrario de lo que pidio; y el refresco, sin rotar, caduca solo.
   */
  cerrarSesion(todosLosDispositivos = false): Observable<void> {
    const refresco = this.sesion.tokenRefresco();
    this.rotacionEnCurso = null;

    if (!refresco) {
      this.sesion.limpiar();
      return of(void 0);
    }

    return this.api.cerrarSesion(refresco, todosLosDispositivos).pipe(
      catchError(() => of(void 0)),
      tap(() => this.sesion.limpiar()),
      map(() => void 0),
    );
  }

  /**
   * Rota el token, compartiendo una unica rotacion entre los que la esperan.
   *
   * Ver la nota del encabezado: sin compartirla, varias peticiones caducadas
   * a la vez presentarian el mismo refresco y el backend revocaria la sesion
   * por sospecha de robo -- correctamente, porque desde fuera es
   * indistinguible.
   */
  rotarToken(): Observable<ParTokens> {
    if (this.rotacionEnCurso) {
      return this.rotacionEnCurso;
    }

    const refresco = this.sesion.tokenRefresco();
    if (!refresco) {
      return throwError(
        () => new FalloApi('NO_AUTENTICADO', 'La sesion expiro. Vuelva a iniciar sesion.', 401),
      );
    }

    this.rotacionEnCurso = this.api.refrescar(refresco).pipe(
      tap((tokens) => {
        this.sesion.establecerTokens(tokens);
        this.rotacionEnCurso = null;
      }),
      catchError((error: unknown) => {
        // La rotacion fallo: el refresco estaba usado, revocado o caducado.
        // La sesion no se puede recuperar, asi que se limpia y se obliga a
        // iniciar sesion otra vez.
        this.rotacionEnCurso = null;
        this.sesion.limpiar();
        return throwError(() => error);
      }),
      // `shareReplay` con `refCount: false` para que el resultado siga
      // disponible a quien se suscriba despues de que la rotacion termine,
      // dentro de la misma rafaga de 401.
      shareReplay({ bufferSize: 1, refCount: false }),
    );

    return this.rotacionEnCurso;
  }
}
