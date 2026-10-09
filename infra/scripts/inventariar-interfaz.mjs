/** Inventario reproducible de formularios y botones declarados en Angular.
 * Complementa las pruebas de ejecución; un evento declarado no prueba su resultado.
 * Ejecutar: node infra/scripts/inventariar-interfaz.mjs > tmp/inventario-interfaz.json
 */
import { readFile, readdir } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const raiz = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const require = createRequire(join(raiz, 'frontend/package.json'));
const ts = require('typescript');
const { parseTemplate } = await import(pathToFileURL(require.resolve('@angular/compiler')).href);
const formularios = [], botones = [], errores = [];
const archivos = new Set();
async function recorrer(directorio) {
  for (const entrada of await readdir(directorio, { withFileTypes: true })) {
    const ruta = join(directorio, entrada.name);
    if (entrada.isDirectory()) await recorrer(ruta);
    else if (entrada.name.endsWith('.ts') && !entrada.name.endsWith('.spec.ts')) await analizar(ruta);
  }
}
function valorEstatico(nodo) {
  return ts.isStringLiteral(nodo) || ts.isNoSubstitutionTemplateLiteral(nodo) ? nodo.text : undefined;
}
async function analizar(ruta) {
  const texto = await readFile(ruta, 'utf8');
  const codigo = ts.createSourceFile(ruta, texto, ts.ScriptTarget.Latest, true);
  const plantillas = [];
  function visitar(nodo) {
    if (ts.isPropertyAssignment(nodo) && ts.isObjectLiteralExpression(nodo.parent) &&
        ts.isCallExpression(nodo.parent.parent) && nodo.parent.parent.expression.getText(codigo) === 'Component') {
      const nombre = nodo.name.getText(codigo), valor = valorEstatico(nodo.initializer);
      if (valor !== undefined && ['template', 'templateUrl'].includes(nombre)) {
        plantillas.push({ nombre, valor, linea: codigo.getLineAndCharacterOfPosition(nodo.initializer.getStart(codigo)).line + 1 });
      }
    }
    ts.forEachChild(nodo, visitar);
  }
  visitar(codigo);
  for (const plantilla of plantillas) {
    const fuente = plantilla.nombre === 'templateUrl' ? resolve(dirname(ruta), plantilla.valor) : ruta;
    const identificador = plantilla.nombre === 'templateUrl' ? fuente : `${fuente}:${plantilla.linea}`;
    if (archivos.has(identificador)) continue;
    archivos.add(identificador);
    const html = plantilla.nombre === 'templateUrl' ? await readFile(fuente, 'utf8') : plantilla.valor;
    const resultado = parseTemplate(html, fuente);
    for (const error of resultado.errors ?? []) errores.push({ archivo: relative(raiz, fuente), mensaje: error.msg });
    const vistos = new WeakSet();
    function visitarHtml(nodo, enFormulario = false) {
      if (!nodo || typeof nodo !== 'object' || vistos.has(nodo)) return;
      vistos.add(nodo);
      if (nodo.name === 'button' || nodo.name === 'form') {
        const atributos = Object.fromEntries((nodo.attributes ?? []).map(a => [a.name, a.value]));
        const entradas = (nodo.inputs ?? []).map(a => a.name);
        const eventos = (nodo.outputs ?? []).map(e => ({ evento: e.name, accion: e.handler?.source ?? '' }));
        const linea = (nodo.sourceSpan?.start.line ?? 0) + (plantilla.nombre === 'templateUrl' ? 1 : plantilla.linea);
        const registro = { archivo: relative(raiz, fuente).replaceAll('\\', '/'), linea, atributos, entradas, eventos };
        if (nodo.name === 'form') formularios.push(registro);
        else {
          const nativo = atributos.type === 'submit' || atributos.type === 'reset' ||
            (!('type' in atributos) && enFormulario) || 'popovertarget' in atributos;
          const navegacion = 'routerLink' in atributos || entradas.includes('routerLink');
          const declarado = eventos.some(e => ['click', 'pointerdown', 'mousedown', 'keydown'].includes(e.evento));
          botones.push({ ...registro, accion_declarada: nativo || navegacion || declarado });
        }
      }
      for (const clave of ['children', 'branches', 'groups', 'cases', 'empty', 'placeholder', 'loading', 'error']) {
        const valor = nodo[clave];
        const dentroDeForm = enFormulario || nodo.name === 'form';
        if (Array.isArray(valor)) for (const hijo of valor) visitarHtml(hijo, dentroDeForm);
        else visitarHtml(valor, dentroDeForm);
      }
    }
    for (const nodo of resultado.nodes) visitarHtml(nodo);
  }
}
await recorrer(join(raiz, 'frontend/src/app'));
const modulos = {};
for (const control of [...formularios, ...botones]) {
  const modulo = control.archivo.match(/paginas\/([^/]+)/)?.[1] ?? 'compartido/nucleo';
  modulos[modulo] ??= { formularios: 0, botones: 0 };
  modulos[modulo][formularios.includes(control) ? 'formularios' : 'botones']++;
}
process.stdout.write(JSON.stringify({
  plantillas: archivos.size, formularios: formularios.length, botones: botones.length,
  modulos, sin_accion_declarada: botones.filter(b => !b.accion_declarada), errores, detalle: { formularios, botones },
}, null, 2) + '\n');
if (errores.length || botones.some(b => !b.accion_declarada)) process.exitCode = 1;
