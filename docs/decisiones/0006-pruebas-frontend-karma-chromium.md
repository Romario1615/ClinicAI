# ADR‑0006 — Pruebas de componentes con Karma y el Chromium de Playwright

* **Estado:** aceptada
* **Fecha:** 2026‑09‑11

## Contexto

Angular 19 trae Karma con Jasmine como ejecutor de pruebas por defecto; el soporte de
Vitest en el constructor de Angular llegó después y en la 19 no es una opción estable.
Karma necesita un navegador real y, por defecto, busca Chrome instalado. El equipo tiene
**Chromium 1228 de Playwright ya descargado** en `D:\playwright-browsers`, y el disco C:
no admite instalar otro navegador (ADR‑0003).

## Decisión

Se mantiene Karma + Jasmine y se apunta el ejecutor al Chromium de Playwright fijando
`CHROME_BIN` a su ruta. Se define un lanzador personalizado `ChromeHeadlessCI` con
`--no-sandbox` y `--disable-gpu` para el pipeline. La ruta se resuelve de forma dinámica
en `karma.conf.js` a partir de `PLAYWRIGHT_BROWSERS_PATH`, no se escribe fija.

## Consecuencias

* Cero descargas de navegador y un único navegador compartido entre las pruebas de
  componentes y las pruebas de extremo a extremo.
* Si el número de compilación de Chromium cambia al actualizar Playwright, la resolución
  dinámica lo absorbe; si no encuentra ningún binario, el `karma.conf.js` falla con un
  mensaje explícito en lugar de un error opaco de Karma.
* Se renuncia a la velocidad de Vitest. Queda como tarea de mantenimiento al actualizar
  Angular, registrada en [`../backlog.md`](../backlog.md).
