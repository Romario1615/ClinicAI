import { expect, type Page } from '@playwright/test';

/** Selecciona la cita en la vista de lista o en el calendario por horas. */
export async function seleccionarCitaEnAgenda(page: Page, nombre: string): Promise<void> {
  const fila = page.locator('.fila-dia').filter({ hasText: nombre }).first();
  const bloque = page.locator('app-calendario-agenda button.bloque').filter({ hasText: nombre }).first();
  const objetivo = (await fila.count()) > 0 ? fila : bloque;
  await expect(objetivo, `la agenda debe mostrar la cita de ${nombre}`).toBeVisible({ timeout: 6_000 });
  await objetivo.click();
}

/** Huecos en ambas presentaciones de la agenda. */
export function huecosVisiblesEnAgenda(page: Page) {
  return page.locator('.fila-dia--hueco, app-calendario-agenda button.bloque.estado--LIBRE');
}
