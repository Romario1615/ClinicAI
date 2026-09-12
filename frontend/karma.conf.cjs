// ---------------------------------------------------------------------------
//  Configuracion de Karma.
//
//  Existe explicitamente (y no se deja la implicita del CLI) por una razon:
//  el navegador. Ver ADR-0006.
//
//  En este equipo no hay Chrome instalado, pero si el Chromium que descargo
//  Playwright en D:\playwright-browsers. Descargar otro navegador solo para
//  las pruebas de componentes anadiria ~200 MB en un disco C: que ya esta al
//  limite (riesgo R-01), asi que se reutiliza el que ya esta.
//
//  `CHROME_BIN` se resuelve en este orden:
//    1. La variable de entorno, si el operador la define.
//    2. El Chromium de Playwright, buscando la version presente en lugar de
//       fijar un numero: la version cambia al actualizar Playwright, y una
//       ruta fija dejaria las pruebas rotas con un error de "navegador no
//       encontrado" que no dice nada del motivo real.
//    3. Nada: se deja que Karma falle con su propio mensaje.
// ---------------------------------------------------------------------------

const fs = require('node:fs');
const path = require('node:path');

const RAIZ_PLAYWRIGHT = process.env.PLAYWRIGHT_BROWSERS_PATH || 'D:\\playwright-browsers';

/** Busca el ejecutable de Chromium que Playwright haya descargado. */
function chromiumDePlaywright() {
  if (!fs.existsSync(RAIZ_PLAYWRIGHT)) {
    return null;
  }
  const candidatos = fs
    .readdirSync(RAIZ_PLAYWRIGHT)
    .filter((nombre) => nombre.startsWith('chromium-'))
    // Orden descendente: si hay varias versiones, se usa la mas reciente.
    .sort()
    .reverse()
    .flatMap((nombre) => [
      path.join(RAIZ_PLAYWRIGHT, nombre, 'chrome-win64', 'chrome.exe'),
      path.join(RAIZ_PLAYWRIGHT, nombre, 'chrome-linux', 'chrome'),
      path.join(RAIZ_PLAYWRIGHT, nombre, 'chrome-mac', 'Chromium.app', 'Contents', 'MacOS', 'Chromium'),
    ]);

  return candidatos.find((ruta) => fs.existsSync(ruta)) || null;
}

if (!process.env.CHROME_BIN) {
  const encontrado = chromiumDePlaywright();
  if (encontrado) {
    process.env.CHROME_BIN = encontrado;
  }
}

module.exports = function (config) {
  config.set({
    basePath: '',
    frameworks: ['jasmine', '@angular-devkit/build-angular'],
    plugins: [
      require('karma-jasmine'),
      require('karma-chrome-launcher'),
      require('karma-jasmine-html-reporter'),
      require('karma-coverage'),
      require('@angular-devkit/build-angular/plugins/karma'),
    ],
    client: {
      jasmine: {
        // Orden aleatorio a proposito. Una suite que solo pasa en un orden
        // concreto tiene dependencias ocultas entre pruebas, y eso se
        // descubre tarde y en la rama de otra persona.
        random: true,
      },
      clearContext: false,
    },
    jasmineHtmlReporter: { suppressAll: true },
    coverageReporter: {
      dir: path.join(__dirname, './cobertura'),
      subdir: '.',
      reporters: [{ type: 'html' }, { type: 'text-summary' }, { type: 'lcovonly' }],
      check: {
        // Umbral equivalente al del backend (RNF-06). El pipeline falla por
        // debajo.
        global: { statements: 80, branches: 70, functions: 80, lines: 80 },
      },
    },
    reporters: ['progress', 'kjhtml'],
    browsers: ['Chrome'],
    customLaunchers: {
      // Para CI y para cualquier ejecucion sin interfaz grafica.
      //
      // `--no-sandbox` es necesario dentro de contenedores, donde el sandbox
      // de Chromium no puede crear espacios de nombres de usuario. Es una
      // relajacion aceptable aqui y solo aqui: el navegador de CI carga
      // unicamente el codigo del propio repositorio, no contenido de
      // terceros.
      //
      // `--disable-dev-shm-usage` evita que Chromium se quede sin memoria
      // compartida: el /dev/shm por omision de Docker son 64 MB, y el
      // sintoma es una caida sin mensaje a mitad de la suite.
      ChromeHeadlessCI: {
        base: 'ChromeHeadless',
        flags: [
          '--no-sandbox',
          '--disable-gpu',
          '--disable-dev-shm-usage',
          '--headless=new',
        ],
      },
    },
    restartOnFileChange: true,
  });
};
