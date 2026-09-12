/**
 * Adjunta el token de acceso y rota cuando caduca.
 *
 * Lo que este interceptor NO hace, a proposito
 * --------------------------------------------
 * **No reintenta la rotacion.** Si el intercambio del refresco falla, la
 * sesion se cierra. Reintentar presentaria el mismo refresco por segunda vez,
 * y para el backend eso es la firma de un token robado: revocaria la familia
 * completa de sesiones. El reintento haria realidad el problema que intenta
 * evitar.
 *
 * **No toca las rutas de autenticacion.** Iniciar sesion, rotar y cerrar
 * sesion se autorizan por su propio cuerpo, no por la cabecera. Sin esta
 * exclusion, un 401 de credenciales incorrectas dispararia una rotacion, que
 * fallaria, y el usuario veria "la sesion expiro" en lugar de "contrasena
 * incorrecta".
 */
import { HttpErrorResponse, type HttpInterceptorFn, type HttpRequest } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, switchMap, throwError } from 'rxjs';

import { AutenticacionService } from '../servicios/autenticacion.service';
import { SesionService } from '../servicios/sesion.service';

/** Rutas que se autorizan por su cuerpo y no por la cabecera. */
const RUTAS_SIN_TOKEN = ['/autenticacion/sesion', '/autenticacion/refresco', '/autenticacion/cierre'];

export const tokenInterceptor: HttpInterceptorFn = (peticion, siguiente) => {
  const sesion = inject(SesionService);
  const autenticacion = inject(AutenticacionService);

  if (RUTAS_SIN_TOKEN.some((ruta) => peticion.url.includes(ruta))) {
    return siguiente(peticion);
  }

  const token = sesion.tokenAcceso();
  const conToken = token ? conAutorizacion(peticion, token) : peticion;

  return siguiente(conToken).pipe(
    catchError((error: unknown) => {
      const esCaducado =
        error instanceof HttpErrorResponse && error.status === 401 && token !== null;

      if (!esCaducado) {
        return throwError(() => error);
      }

      return autenticacion.rotarToken().pipe(
        switchMap((tokens) => siguiente(conAutorizacion(peticion, tokens.token_acceso))),
      );
    }),
  );
};

function conAutorizacion<T>(peticion: HttpRequest<T>, token: string): HttpRequest<T> {
  return peticion.clone({ setHeaders: { Authorization: `Bearer ${token}` } });
}
