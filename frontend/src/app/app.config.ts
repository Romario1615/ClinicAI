/**
 * Configuracion de arranque.
 *
 * `provideHttpClient(withInterceptors(...))` y no el modulo clasico: es el
 * estilo de Angular sin NgModules y permite que el interceptor de token se
 * declare como funcion, con `inject()` dentro.
 */
import {
  type ApplicationConfig,
  isDevMode,
  provideZoneChangeDetection,
} from '@angular/core';
import { provideHttpClient, withInterceptors, withXhr } from '@angular/common/http';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { provideServiceWorker } from '@angular/service-worker';

import { routes } from './app.routes';
import { tokenInterceptor } from './nucleo/interceptores/token.interceptor';
import { CONFIGURACION, CONFIGURACION_POR_DEFECTO } from './nucleo/servicios/configuracion';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes, withComponentInputBinding()),
    provideHttpClient(withXhr(), withInterceptors([tokenInterceptor])),
    { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
    provideServiceWorker('ngsw-worker.js', {
      enabled: !isDevMode(),
      // Se registra cuando la aplicacion esta estable, no de inmediato: en
      // una tableta lenta, competir con la carga inicial retrasa la primera
      // pantalla util.
      registrationStrategy: 'registerWhenStable:30000',
    }),
  ],
};
