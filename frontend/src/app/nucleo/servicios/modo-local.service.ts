import { Injectable, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { Observable, catchError, map, of, shareReplay } from 'rxjs';

import { ApiService } from './api.service';

/** Publica si el backend habilitó las herramientas exclusivas del entorno local. */
@Injectable({ providedIn: 'root' })
export class ModoLocalService {
  private readonly api = inject(ApiService);

  private readonly accesos$ = this.api.accesosLocales().pipe(
    catchError(() => of({ habilitado: false, roles: [] })),
    shareReplay({ bufferSize: 1, refCount: false }),
  );

  readonly habilitado = toSignal(this.accesos$.pipe(map((respuesta) => respuesta.habilitado)), {
    initialValue: false,
  });

  accesosLocales(): Observable<{ habilitado: boolean; roles: readonly { codigo: string; nombre: string }[] }> {
    return this.accesos$;
  }

  /** Reutiliza la misma comprobación tanto en los enlaces como en las rutas. */
  comprobar(): Observable<boolean> {
    return this.accesos$.pipe(map((respuesta) => respuesta.habilitado));
  }
}
