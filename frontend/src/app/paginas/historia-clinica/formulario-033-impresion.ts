import type { Formulario033Api } from '../../nucleo/servicios/api.service';

const escapar = (valor: unknown): string =>
  String(valor ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');

const dato = (valor: unknown): string => escapar(valor === null || valor === undefined || valor === '' ? 'Sin registro' : valor);

const siNo = (valor: boolean | null): string =>
  valor === null ? 'Sin registro' : valor ? 'Sí' : 'No';

const etiqueta = (valor: string): string =>
  escapar(valor.replaceAll('_', ' ').toLocaleLowerCase('es').replace(/(^|\s)\S/g, (letra) => letra.toLocaleUpperCase('es')));

function tabla(encabezados: readonly string[], filas: readonly (readonly string[])[]): string {
  const th = encabezados.map((celda) => `<th scope="col">${escapar(celda)}</th>`).join('');
  const body = filas.length
    ? filas.map((fila) => `<tr>${fila.map((celda) => `<td>${celda}</td>`).join('')}</tr>`).join('')
    : `<tr><td colspan="${encabezados.length}" class="vacio">Sin registros</td></tr>`;
  return `<table><thead><tr>${th}</tr></thead><tbody>${body}</tbody></table>`;
}

function bloque(titulo: string, contenido: string): string {
  return `<section class="bloque"><h2>${escapar(titulo)}</h2>${contenido}</section>`;
}

function datoDefinido(etiquetaDato: unknown, valor: unknown): string {
  return `<div class="dato"><strong>${escapar(etiquetaDato)}</strong><span>${dato(valor)}</span></div>`;
}

export function generarHtmlFormulario033(formulario: Formulario033Api): string {
  const contexto = formulario.contexto_identidad;
  const datos = formulario.datos;
  const paciente = `${contexto['nombres'] ?? 'Sin registro'} ${contexto['apellidos'] ?? 'Sin registro'}`;
  const identidad = [contexto['tipo_documento'], contexto['historia_clinica']]
    .filter((valor) => valor !== null && valor !== undefined && valor !== '')
    .map((valor) => String(valor))
    .join(' · ') || 'Sin registro';
  const persona = [contexto['edad'], contexto['unidad_edad']]
    .filter((valor) => valor !== null && valor !== undefined && valor !== '')
    .map((valor) => String(valor))
    .join(' ') || 'Sin registro';

  const antecedentes = [
    ...datos.antecedentes_personales.map((item) => [
      etiqueta(item.codigo), siNo(item.presente), dato(item.detalle),
    ]),
    ...datos.antecedentes_familiares.map((item) => [
      `Familiar · ${etiqueta(item.codigo)}`, siNo(item.presente), dato(item.detalle),
    ]),
  ].map((fila) => fila.map((celda) => celda));

  const vitales = datos.constantes_vitales;
  const signos = [
    ['Temperatura', vitales.temperatura_c === null ? null : `${vitales.temperatura_c} °C`],
    ['Pulso', vitales.pulso_minuto === null ? null : `${vitales.pulso_minuto} /min`],
    ['Frecuencia respiratoria', vitales.frecuencia_respiratoria_minuto === null ? null : `${vitales.frecuencia_respiratoria_minuto} /min`],
    ['Presión arterial', vitales.presion_sistolica_mmhg === null || vitales.presion_diastolica_mmhg === null
      ? null : `${vitales.presion_sistolica_mmhg}/${vitales.presion_diastolica_mmhg} mmHg`],
  ].map(([nombre, valor]) => [escapar(nombre), dato(valor)]);

  const hallazgos = datos.examen_estomatognatico.map((item) => [
    etiqueta(item.region), etiqueta(item.hallazgo), dato(item.detalle), dato(item.grado),
  ]);
  const higiene = datos.indicadores_salud_bucal;
  const sitios = higiene.sitios.map((item) => [
    dato(item.pieza), dato(item.placa), dato(item.calculo), siNo(item.gingivitis),
  ]);
  const cpo = Object.entries(datos.indices_cpo_ceo).map(([campo, valor]) => [etiqueta(campo), dato(valor)]);
  const examenes = datos.examenes_complementarios.map((item) => [
    etiqueta(item.tipo), dato(item.descripcion), dato(item.resultado),
  ]);
  const diagnosticos = datos.diagnosticos.map((item) => [
    etiqueta(item.tipo), dato(item.codigo_cie), dato(item.descripcion),
  ]);
  const sesiones = datos.sesiones_tratamiento.map((item) => [
    dato(item.numero), dato(item.fecha), dato(item.diagnostico_complicaciones),
    dato(item.procedimiento), dato(item.prescripciones), dato(item.proxima_cita), siNo(item.alta),
  ]);
  const fuentes = [
    ['Cita', formulario.cita_id],
    ['Nota clínica', formulario.nota_id],
    ['Odontograma', formulario.odontograma_id],
    ['Registro de placa', formulario.registro_placa_id],
  ].filter(([, id]) => Boolean(id));

  const cabecera = (lado: string): string => `
    <header class="cabecera">
      <div><span class="marca">ClinicAI</span><span class="submarca">Registro clínico odontológico</span></div>
      <div class="folio"><strong>MSP 033/2021</strong><span>Versión ${formulario.version} · ${lado}</span></div>
    </header>`;

  return `<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Formulario 033 · ${escapar(paciente)}</title>
<style>
@page{size:A4 portrait;margin:9mm}
*{box-sizing:border-box}body{margin:0;color:#182e32;font:9pt/1.35 Arial,Helvetica,sans-serif;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.barra{display:flex;justify-content:space-between;align-items:center;margin:0 auto 8mm;max-width:190mm;color:#51666a;font:10pt Arial,sans-serif}.barra button{border:0;border-radius:5px;padding:8px 14px;background:#0e6965;color:white;font-weight:700;cursor:pointer}
.pagina{position:relative;display:flex;flex-direction:column;max-width:190mm;min-height:276mm;margin:0 auto 12mm;padding:0 0 12mm;break-after:page;page-break-after:always}.pagina:last-of-type{break-after:auto;page-break-after:auto}
.cabecera{display:flex;justify-content:space-between;align-items:center;padding:0 0 3mm;border-bottom:2px solid #0e6965}.marca{display:block;color:#0b5b59;font-size:18pt;font-weight:800;letter-spacing:-.6pt}.submarca{color:#52696c;font-size:8pt}.folio{text-align:right}.folio strong,.folio span{display:block}.folio strong{font-size:12pt}.folio span{color:#52696c}
h1{margin:4mm 0 1mm;font-size:15pt}.intro{margin:0 0 3mm;color:#52696c}.bloque{margin:2.5mm 0 0;padding:2.2mm;border:1px solid #b9c9c8;border-radius:2mm;break-inside:avoid;page-break-inside:avoid}.bloque h2{margin:0 0 1.5mm;color:#0b5b59;font-size:9.2pt;letter-spacing:.1pt}.datos{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1.8mm}.dato{min-width:0;display:flex;flex-direction:column;gap:.5mm;padding:1.4mm;background:#f1f6f4;border-radius:1mm;overflow-wrap:anywhere}.dato strong{color:#52696c;font-size:7pt;text-transform:uppercase;letter-spacing:.2pt}.dato span{font-size:8.4pt;white-space:pre-wrap}.dos-columnas{display:grid;grid-template-columns:1fr 1fr;gap:2.5mm}.dos-columnas .bloque{margin-top:2.5mm}
table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:7.5pt}th,td{padding:1mm 1.3mm;border:1px solid #ccd7d6;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#edf4f2;color:#30484a;font-size:7pt}.vacio{text-align:center;color:#748487}.nota{margin:2mm 0 0;color:#52696c;font-size:7pt}.firma{display:grid;grid-template-columns:1fr 1fr;gap:12mm;margin:12mm 6mm 0}.linea-firma{padding-top:2mm;border-top:1px solid #45585b;text-align:center}.pie-pagina{display:flex;justify-content:space-between;gap:5mm;margin-top:auto;padding-top:2mm;border-top:1px solid #ccd7d6;color:#667679;font-size:6.5pt}.aviso{margin-top:2.5mm;padding:2mm;border-left:2px solid #c58b3b;background:#fcf6eb;color:#584b35;font-size:7pt}
@media print{.barra{display:none}.pagina{margin:0;min-height:276mm}.bloque{break-inside:avoid;page-break-inside:avoid}}
@media screen{body{padding:8mm;background:#e8efed}.pagina{padding:0 0 12mm;background:#fff;box-shadow:0 3mm 12mm #203e3b24}.barra{max-width:190mm}}
</style></head><body>
<nav class="barra" aria-label="Acciones de impresión"><span>Revisa la copia y selecciona impresión a doble cara si está disponible.</span><button id="imprimir" type="button">Imprimir o guardar en PDF</button></nav>
<main>
<article class="pagina">${cabecera('Anverso')}
  <h1>Registro asistencial odontológico</h1><p class="intro">Copia clínica del registro capturado en ClinicAI · generación ${dato(contexto['capturado_en'] ?? formulario.creado_en)}</p>
  ${bloque('Identificación y atención', `<div class="datos">${[
    ['Clínica', contexto['clinica']], ['Identificación fiscal', contexto['identificacion_fiscal_clinica']],
    ['Sede', contexto['sede']], ['Dirección', contexto['direccion_sede']],
    ['Paciente', paciente], ['Documento / historia clínica', identidad], ['Sexo registrado', contexto['sexo']],
    ['Edad al registrar', persona], ['Profesional', contexto['profesional']],
    ['Registro profesional', contexto['registro_profesional']], ['Fecha de captura', contexto['capturado_en'] ?? formulario.creado_en],
    ['Embarazo', siNo(datos.embarazada)],
  ].map(([nombre, valor]) => datoDefinido(nombre, valor)).join('')}</div>
  ${tabla(['Campo', 'Registro'], [['Motivo de consulta', dato(datos.motivo_consulta)], ['Enfermedad o problema actual', dato(datos.enfermedad_actual)]])}
  ${fuentes.length ? `<p class="nota"><strong>Fuentes vinculadas:</strong> ${fuentes.map(([tipo, id]) => `${escapar(tipo)} · ${escapar(id)}`).join(' &nbsp;|&nbsp; ')}</p>` : '<p class="nota"><strong>Fuentes vinculadas:</strong> Sin registro</p>'}</div>`)}
  <div class="dos-columnas">
    ${bloque('Antecedentes personales y familiares', tabla(['Antecedente', 'Presencia', 'Detalle'], antecedentes))}
    ${bloque('Constantes vitales', tabla(['Medición', 'Valor'], signos))}
  </div>
  ${bloque('Examen estomatognático', tabla(['Región', 'Hallazgo', 'Detalle', 'Grado'], hallazgos))}
  <footer class="pie-pagina"><span>Paciente: ${escapar(paciente)} · Documento: ${escapar(identidad)}</span><span>Formulario ${escapar(formulario.raiz_id)} · v${formulario.version}</span></footer>
</article>
<article class="pagina">${cabecera('Reverso')}
  <h1>Evaluación bucodental y tratamiento</h1><p class="intro">Registro ${escapar(formulario.raiz_id)} · versión ${formulario.version} · ${dato(contexto['capturado_en'] ?? formulario.creado_en)}</p>
  ${bloque('Salud bucal · índice simplificado', `<div class="datos">${[
    ['Enfermedad periodontal', etiqueta(higiene.enfermedad_periodontal ?? 'SIN_REGISTRO')],
    ['Oclusión', etiqueta(higiene.oclusion ?? 'SIN_REGISTRO')], ['Fluorosis', etiqueta(higiene.fluorosis ?? 'SIN_REGISTRO')],
  ].map(([nombre, valor]) => datoDefinido(nombre, valor)).join('')}</div>${tabla(['Pieza', 'Placa (0–3)', 'Cálculo (0–3)', 'Gingivitis'], sitios)}<p class="nota">Los valores sin evaluar se muestran como «Sin registro»; no se infieren resultados.</p></div>`)}
  ${bloque('Índices CPO–ceo', tabla(['Índice', 'Valor'], cpo))}
  ${bloque('Exámenes complementarios', tabla(['Tipo', 'Descripción', 'Resultado'], examenes))}
  ${bloque('Diagnósticos', tabla(['Clasificación', 'Código CIE', 'Descripción'], diagnosticos))}
  ${bloque('Sesiones de tratamiento', tabla(['N.º', 'Fecha', 'Diagnóstico / complicaciones', 'Procedimiento', 'Prescripciones', 'Próxima cita', 'Alta'], sesiones))}
  <div class="firma"><div class="linea-firma">${dato(contexto['profesional'])}<br>Profesional responsable · Reg. ${dato(contexto['registro_profesional'])}</div><div class="linea-firma">Firma manuscrita</div></div>
  <p class="aviso">Copia de impresión generada desde ClinicAI. La firma impresa no equivale a firma electrónica. Este diseño es una transcripción clínica y requiere cotejo institucional con el anexo oficial antes de presentarse como formulario oficial o documento de validez jurídica.</p>
  <footer class="pie-pagina"><span>Paciente: ${escapar(paciente)} · Documento: ${escapar(identidad)}</span><span>Formulario ${escapar(formulario.raiz_id)} · v${formulario.version}</span></footer>
</article>
</main></body></html>`;
}
