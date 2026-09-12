/**
 * Estado de la sesion.
 *
 * Donde viven los tokens, y por que
 * ---------------------------------
 * **En memoria. No en `localStorage` ni en `sessionStorage`** (ADR-0016).
 *
 * El coste es real y se acepta a conciencia: recargar la pestana cierra la
 * sesion. A cambio, un XSS no encuentra el token de refresco en ningun
 * almacen persistente. Con `localStorage` bastaria una linea de script
 * inyectado para llevarselo y mantener la sesion abierta indefinidamente
 * desde fuera.
 *
 * El token de acceso dura 15 minutos y se rota con el de refresco, que es de
 * un solo uso. Si aparecen dos copias del mismo refresco, el backend revoca
 * la familia completa de sesiones: el robo no se evita, se detecta y se
 * acota.
 *
 * Lo unico que se guarda entre recargas es el correo, para no obligar a
 * teclearlo cada vez. No es una credencial y no abre nada por si solo.
 */
import { Injectable, computed, signal } from '@angular/core';

import type { Identidad, ParTokens } from '../modelos/dominio';

const CLAVE_CORREO_RECORDADO = 'clinica.correo';

@Injectable({ providedIn: 'root' })
export class SesionService {
  /** Tokens vivos. `null` significa sesion cerrada. */
  private readonly _tokens = signal<ParTokens | null>(null);
  private readonly _identidad = signal<Identidad | null>(null);

  readonly identidad = this._identidad.asReadonly();

  readonly autenticado = computed(() => this._tokens() !== null);

  readonly tokenAcceso = computed(() => this._tokens()?.token_acceso ?? null);
  readonly tokenRefresco = computed(() => this._tokens()?.token_refresco ?? null);

  /**
   * Cierto cuando el rol exige segundo factor y la sesion no lo ha cumplido.
   *
   * El backend emite el token igualmente para que el cliente pueda pedir el
   * codigo, pero rechaza toda operacion. La interfaz tiene que reflejarlo o
   * el usuario veria una pantalla llena de acciones que fallan todas.
   */
  readonly segundoFactorPendiente = computed(() => {
    const identidad = this._identidad();
    if (identidad) {
      return identidad.requiere_segundo_factor && !identidad.segundo_factor_cumplido;
    }
    return this._tokens()?.requiere_segundo_factor ?? false;
  });

  readonly nombreCompleto = computed(() => {
    const identidad = this._identidad();
    return identidad ? `${identidad.nombre} ${identidad.apellido}`.trim() : '';
  });

  readonly correoRecordado = signal<string>(leerCorreoRecordado());

  establecerTokens(tokens: ParTokens): void {
    this._tokens.set(tokens);
  }

  establecerIdentidad(identidad: Identidad): void {
    this._identidad.set(identidad);
  }

  recordarCorreo(correo: string): void {
    const limpio = correo.trim().toLowerCase();
    this.correoRecordado.set(limpio);
    try {
      localStorage.setItem(CLAVE_CORREO_RECORDADO, limpio);
    } catch {
      // Modo privado, almacenamiento lleno o bloqueado por politica. No
      // recordar el correo es una molestia, no un fallo: se ignora.
    }
  }

  limpiar(): void {
    this._tokens.set(null);
    this._identidad.set(null);
  }

  /**
   * Comprueba un permiso.
   *
   * Repetido del backend a proposito, y **solo para decidir que mostrar**. El
   * backend revalida cada peticion y aplica ademas el filtro de ambito
   * (CLAUDE.md, regla 7).
   */
  tienePermiso(codigo: string): boolean {
    return this._identidad()?.permisos.includes(codigo) ?? false;
  }

  tieneAlgunPermiso(...codigos: readonly string[]): boolean {
    return codigos.some((codigo) => this.tienePermiso(codigo));
  }
}

function leerCorreoRecordado(): string {
  try {
    return localStorage.getItem(CLAVE_CORREO_RECORDADO) ?? '';
  } catch {
    return '';
  }
}
