/** Accesos por rol para los usuarios sintéticos del entorno local. */
import type { Page } from '@playwright/test';

export const CODIGOS_ROL = {
  recepcion: 'recepcion',
  asistente: 'asistente',
  profesional: 'profesional',
  administradora: 'administrador_clinica',
  auditor: 'auditor',
  superadministrador: 'superadministrador',
} as const;

export type Rol = keyof typeof CODIGOS_ROL;

const ETIQUETAS_ROL: Record<Rol, RegExp> = {
  recepcion: /recepción/i,
  asistente: /asistencia clínica/i,
  profesional: /profesional de salud/i,
  administradora: /administración de clínica/i,
  auditor: /auditoría/i,
  superadministrador: /superadministrador/i,
};

/** Inicia sesión seleccionando el rol desde la interfaz local. */
export async function acceder(page: Page, rol: Rol): Promise<void> {
  await page.goto('/acceso');
  const boton = page.getByRole('button', { name: ETIQUETAS_ROL[rol] });
  await boton.waitFor({ state: 'visible', timeout: 15_000 });
  await boton.click();
  await page.waitForURL(/\/(panel|agenda)/, { timeout: 15_000 });
}

/** Navega a una sección desde la barra de navegación. */
export async function irA(page: Page, etiqueta: string | RegExp): Promise<void> {
  await page.getByRole('navigation', { name: 'Secciones' }).getByRole('link', { name: etiqueta }).click();
}
