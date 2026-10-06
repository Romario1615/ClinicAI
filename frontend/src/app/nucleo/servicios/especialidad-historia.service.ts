/**
 * Especialidad desde la que se revisa una historia clínica.
 *
 * El backend dice desde cuáles puede revisar quien tiene la sesión y qué
 * módulos usa cada una (odontograma, periodoncia, planes, imágenes). Aquí se
 * guarda la elegida para que la historia y la ficha muestren lo mismo.
 *
 * Ocultar un módulo en la interfaz es comodidad, no control: el backend filtra
 * las notas por especialidad y niega los módulos que no correspondan.
 */
import { Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';

import { CONFIGURACION } from './configuracion';
import { SesionService } from './sesion.service';

export type ModuloHistoria = 'odontograma' | 'periodoncia' | 'planes' | 'imagenes';

export interface EspecialidadHistoria {
  readonly id: string;
  readonly nombre: string;
  readonly modulos: readonly ModuloHistoria[];
  readonly propia: boolean;
}

const CLAVE_GUARDADA = 'historia.especialidad';

@Injectable({ providedIn: 'root' })
export class EspecialidadHistoriaService {
  private readonly http = inject(HttpClient);
  private readonly configuracion = inject(CONFIGURACION);
  private readonly sesion = inject(SesionService);

  readonly disponibles = signal<readonly EspecialidadHistoria[]>([]);
  readonly cargada = signal(false);
  private readonly elegidaId = signal<string | null>(null);
  private usuarioCargado: string | null = null;

  /** La elegida o, si no hay, la propia (el backend la pone primero). */
  readonly elegida = computed(() => {
    const lista = this.disponibles();
    return lista.find((e) => e.id === this.elegidaId()) ?? lista[0] ?? null;
  });

  tieneModulo(modulo: ModuloHistoria): boolean {
    return this.elegida()?.modulos.includes(modulo) ?? false;
  }

  /** Carga una vez por sesión; si cambia la persona, vuelve a cargar. */
  cargar(): void {
    const usuario = this.sesion.identidad()?.usuario_id ?? null;
    if (this.usuarioCargado === usuario && this.cargada()) return;
    this.usuarioCargado = usuario;
    this.cargada.set(false);
    this.http
      .get<readonly EspecialidadHistoria[]>(`${this.configuracion.urlApi}/historia/especialidades`)
      .subscribe({
        next: (lista) => {
          this.disponibles.set(lista);
          const guardada = leerGuardada();
          this.elegidaId.set(lista.some((e) => e.id === guardada) ? guardada : null);
          this.cargada.set(true);
        },
        // Sin permisos clínicos no hay especialidad desde la que revisar.
        error: () => {
          this.disponibles.set([]);
          this.cargada.set(true);
        },
      });
  }

  elegir(id: string): void {
    this.elegidaId.set(id);
    try {
      sessionStorage.setItem(CLAVE_GUARDADA, id);
    } catch {
      // Sin almacenamiento se recuerda solo mientras la página siga abierta.
    }
  }
}

function leerGuardada(): string | null {
  try {
    return sessionStorage.getItem(CLAVE_GUARDADA);
  } catch {
    return null;
  }
}
