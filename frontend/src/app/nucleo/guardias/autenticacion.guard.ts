/**
 * Guardias de ruta.
 *
 * **No son controles de seguridad.** Ordenan la navegacion: evitan que
 * alguien llegue a una pantalla que va a estar vacia o que va a devolver 403
 * en cada llamada. El control real esta en el backend, que revalida el
 * permiso y aplica el filtro de ambito en cada peticion (CLAUDE.md, regla 7).
 *
 * Dicho de otro modo: quitar estos guardias no expondria ningun dato, solo
 * daria una experiencia peor.
 */
import { inject } from '@angular/core';
import { Router, type CanActivateFn } from '@angular/router';

import { SesionService } from '../servicios/sesion.service';

/** Exige sesion abierta. */
export const guardiaAutenticacion: CanActivateFn = (_ruta, estado) => {
  const sesion = inject(SesionService);
  const router = inject(Router);

  if (sesion.autenticado()) {
    return true;
  }

  // Se conserva el destino para volver alli despues de entrar. Sin esto, un
  // enlace compartido a una cita concreta lleva al panel y hay que buscarla
  // otra vez a mano.
  return router.createUrlTree(['/acceso'], {
    queryParams: { destino: estado.url },
  });
};

/** Impide volver al formulario de acceso con la sesion ya abierta. */
export const guardiaInvitado: CanActivateFn = () => {
  const sesion = inject(SesionService);
  const router = inject(Router);
  return sesion.autenticado() ? router.createUrlTree(['/panel']) : true;
};

/**
 * Exige alguno de los permisos indicados.
 *
 * Basta con uno: es el caso de una pantalla a la que llegan roles distintos
 * por caminos distintos.
 */
export function guardiaPermiso(...codigos: readonly string[]): CanActivateFn {
  if (codigos.length === 0) {
    throw new Error('guardiaPermiso necesita al menos un codigo de permiso.');
  }

  return () => {
    const sesion = inject(SesionService);
    const router = inject(Router);

    if (!sesion.autenticado()) {
      return router.createUrlTree(['/acceso']);
    }
    if (sesion.tieneAlgunPermiso(...codigos)) {
      return true;
    }
    return router.createUrlTree(['/sin-permiso']);
  };
}

/**
 * Bloquea la navegacion mientras el segundo factor este pendiente.
 *
 * El backend emite el token para que el cliente pueda pedir el codigo, pero
 * rechaza toda operacion. Sin este guardia, el usuario veria el panel
 * completo con todas las acciones fallando, que es peor que una pantalla que
 * explica lo que falta.
 */
export const guardiaSegundoFactor: CanActivateFn = () => {
  const sesion = inject(SesionService);
  const router = inject(Router);
  return sesion.segundoFactorPendiente() ? router.createUrlTree(['/acceso']) : true;
};
