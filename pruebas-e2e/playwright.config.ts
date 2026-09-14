/**
 * Configuracion de las pruebas de extremo a extremo.
 *
 * Que se prueba aqui y que no
 * ---------------------------
 * Aqui se prueba el **recorrido completo**: navegador real, frontend real,
 * API real y PostgreSQL real. No hay dobles de ningun tipo.
 *
 * Lo que NO se prueba aqui son las reglas de dominio. Esas ya tienen 1267
 * pruebas del backend que las cubren mucho mejor y mucho mas rapido. Repetirlas
 * a traves del navegador daria una suite lenta y fragil que tarda diez veces
 * mas en decir lo mismo.
 *
 * Lo que solo se puede comprobar aqui es que **las piezas encajan**: que la
 * sesion se propaga, que el guardia de navegacion coincide con el permiso que
 * el backend exige, que un 403 del servidor se convierte en algo legible, y que
 * lo que se ve en pantalla es lo que la API devolvio.
 *
 * Requisitos
 * ----------
 * La infraestructura, la API y el frontend tienen que estar arriba. No se
 * arrancan desde aqui a proposito: `webServer` de Playwright los mataria al
 * terminar, y en este proyecto el servidor de desarrollo es algo que la persona
 * deja corriendo mientras trabaja.
 */
import { defineConfig, devices } from '@playwright/test';

const BASE = process.env.URL_BASE ?? 'http://localhost:4200';

export default defineConfig({
  testDir: './escenarios',
  /**
   * Sin paralelismo entre archivos.
   *
   * Los escenarios comparten la misma base de datos de desarrollo y varios
   * escriben en ella. En paralelo, uno que crea una cita y otro que consulta la
   * agenda del mismo profesional se estorban, y el fallo aparece de forma
   * intermitente, que es la peor clase de fallo.
   */
  fullyParallel: false,
  workers: 1,
  /**
   * Ningun reintento, tampoco en CI.
   *
   * Un reintento convierte una prueba intermitente en una prueba que «pasa a
   * veces» y deja de avisar. Si un escenario falla de forma esporadica, el
   * problema es el escenario o el sistema, y hay que mirarlo.
   */
  retries: 0,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['html', { outputFolder: 'informe', open: 'never' }]],
  use: {
    baseURL: BASE,
    locale: 'es-EC',
    timezoneId: 'America/Guayaquil',
    /** Traza solo del fallo: guardar todas llena el disco sin aportar nada. */
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
