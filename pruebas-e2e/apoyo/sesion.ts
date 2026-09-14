/**
 * Apoyo para los escenarios: acceso y datos de la clinica sintetica.
 *
 * Las credenciales son **sinteticas** y estan en las semillas del proyecto
 * (`backend/app/semillas/sinteticos.py`). No son un secreto: son cuentas de
 * desarrollo de una base local, y el propio codigo explica por que la
 * contrasena es fija. Nada de esto sirve fuera del entorno local.
 */
import type { Page } from '@playwright/test';

export const CONTRASENA = 'DesarrolloLocal2026';

/**
 * Cuentas sinteticas por rol.
 *
 * `administradora` y `auditor` **no** pueden iniciar sesion: su rol exige
 * segundo factor y estas cuentas no lo tienen configurado. Eso es el control
 * funcionando, y hay un escenario que lo comprueba.
 */
export const CUENTAS = {
  recepcion: 'rita.recepcion.11@example.invalid',
  asistente: 'alba.asistente.12@example.invalid',
  profesional: 'agustina.salgado.21@example.invalid',
  administradora: 'ana.administradora.10@example.invalid',
} as const;

export type Rol = keyof typeof CUENTAS;

/** Resuelve el identificador de la clinica sintetica desde la propia API. */
export async function obtenerClinicaId(page: Page): Promise<string> {
  const guardado = process.env.CLINICA_ID;
  if (guardado) {
    return guardado;
  }
  throw new Error(
    'Falta CLINICA_ID. Se obtiene con:\n' +
      "  docker exec clinica-pg psql -U clinica -d clinica -tAc \"select id from clinica where nombre like '%SINTETICO%' order by creado_en desc limit 1\"",
  );
}

/**
 * Inicia sesion por la interfaz, no por la API.
 *
 * Entrar por la API y sembrar el token seria mas rapido, y se saltaria
 * exactamente lo que estas pruebas existen para comprobar: que el formulario,
 * el interceptor y el guardia encajan.
 */
export async function acceder(page: Page, rol: Rol): Promise<void> {
  const clinicaId = await obtenerClinicaId(page);
  await page.goto('/acceso');
  await page.locator('input[name="clinica"]').fill(clinicaId);
  await page.locator('input[name="correo"]').fill(CUENTAS[rol]);
  await page.locator('input[name="contrasena"]').fill(CONTRASENA);
  await page.getByRole('button', { name: /entrar/i }).click();
  await page.waitForURL(/\/(panel|agenda)/, { timeout: 15_000 });
}

/** Navega a una seccion desde la barra de navegacion. */
export async function irA(page: Page, etiqueta: string | RegExp): Promise<void> {
  await page.getByRole('link', { name: etiqueta }).click();
}
