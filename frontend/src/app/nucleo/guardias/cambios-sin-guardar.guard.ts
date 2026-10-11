import type { CanDeactivateFn } from '@angular/router';

/** Contrato mínimo para proteger los borradores al cambiar de sección. */
export interface ConfirmaSalidaConCambios {
  confirmarSalida(): boolean;
}

/** Deja la decisión en cada pantalla, junto a la definición de sus cambios. */
export const confirmarSalidaConCambios: CanDeactivateFn<ConfirmaSalidaConCambios> = (componente) =>
  componente.confirmarSalida();
