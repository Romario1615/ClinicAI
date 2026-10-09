export interface PuntoAnalitico {fecha:string; valor:number|null; muestras:number}
export interface PrediccionKpi {fecha:string; valor:number; inferior:number; superior:number}
export interface KpiAnalitico {clave:string; nombre:string; unidad:string; definicion:string; total:number|null; agregacion:string; historia:readonly PuntoAnalitico[]; prediccion:readonly PrediccionKpi[]; evidencia:{estado:string; motivo:string; algoritmo:string|null; observaciones:number; dias_historia:number; dias_seleccion:number; dias_evaluacion:number; mae:number|null; mae_base:number|null; mejora_porcentaje:number|null; entrenado_hasta:string|null; evaluacion_desde:string|null; evaluacion_hasta:string|null; banda:string}}
export interface AnaliticaDashboard {generado_en:string; zona_horaria:string; desde:string; hasta:string; horizonte:number; kpis:readonly KpiAnalitico[]; recomendaciones:readonly {titulo:string; motivo:string; accion:string; ruta:string; prioridad:string; kpis:readonly string[]; requiere_revision:boolean}[]; limites:readonly string[]}
/** Agrupa solo los indicadores ya autorizados por la API; no añade cifras. */
export const GRUPOS_INDICADORES = [
  { clave: 'agenda', nombre: 'Agenda y atención', icono: 'agenda' },
  { clave: 'pacientes', nombre: 'Pacientes', icono: 'pacientes' },
  { clave: 'finanzas', nombre: 'Finanzas', icono: 'balance-clinico' },
  { clave: 'seguimiento', nombre: 'Seguimiento', icono: 'pulso' },
  { clave: 'operacion', nombre: 'Operación', icono: 'red-clinica' },
] as const;

export function grupoIndicador(clave: string): typeof GRUPOS_INDICADORES[number] {
  const original = clave.replace(/^estado\./, '');
  if (['cobros', 'gastos', 'ingreso_por_atencion'].includes(original) || original.startsWith('pagos.')) return GRUPOS_INDICADORES[2];
  if (['registros_pacientes', 'pacientes_dia'].includes(original) || original.startsWith('pacientes.')) return GRUPOS_INDICADORES[1];
  if (/^(clinico|adherencia)\./.test(original)) return GRUPOS_INDICADORES[3];
  if (/^(agenda|mis_citas|lista_espera)\./.test(original) || [
    'citas', 'atenciones', 'inasistencias', 'cancelaciones', 'pendientes',
    'minutos_atendidos', 'espera', 'tasa_asistencia', 'tasa_inasistencia', 'tasa_cancelacion',
  ].includes(original)) return GRUPOS_INDICADORES[0];
  return GRUPOS_INDICADORES[4];
}

export function rutaSerie(valores: readonly (number|null)[], maximo:number, desplazamiento=0, total=valores.length): string {
  let abierto=false;
  return valores.map((v,i)=>{if(v===null){abierto=false;return '';}const x=32+(i+desplazamiento)*536/Math.max(total-1,1);const y=180-v/Math.max(maximo,1)*148;const parte=`${abierto?'L':'M'}${x.toFixed(1)},${y.toFixed(1)}`;abierto=true;return parte;}).join(' ');
}
