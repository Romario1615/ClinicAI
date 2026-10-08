export interface PuntoAnalitico {fecha:string; valor:number|null; muestras:number}
export interface PrediccionKpi {fecha:string; valor:number; inferior:number; superior:number}
export interface KpiAnalitico {clave:string; nombre:string; unidad:string; definicion:string; total:number|null; agregacion:string; historia:readonly PuntoAnalitico[]; prediccion:readonly PrediccionKpi[]; evidencia:{estado:string; motivo:string; algoritmo:string|null; observaciones:number; dias_historia:number; dias_seleccion:number; dias_evaluacion:number; mae:number|null; mae_base:number|null; mejora_porcentaje:number|null; entrenado_hasta:string|null; evaluacion_desde:string|null; evaluacion_hasta:string|null; banda:string}}
export interface AnaliticaDashboard {generado_en:string; zona_horaria:string; desde:string; hasta:string; horizonte:number; kpis:readonly KpiAnalitico[]; recomendaciones:readonly {titulo:string; motivo:string; accion:string; ruta:string; prioridad:string; kpis:readonly string[]; requiere_revision:boolean}[]; limites:readonly string[]}
export function rutaSerie(valores: readonly (number|null)[], maximo:number, desplazamiento=0, total=valores.length): string {
  let abierto=false;
  return valores.map((v,i)=>{if(v===null){abierto=false;return '';}const x=32+(i+desplazamiento)*536/Math.max(total-1,1);const y=180-v/Math.max(maximo,1)*148;const parte=`${abierto?'L':'M'}${x.toFixed(1)},${y.toFixed(1)}`;abierto=true;return parte;}).join(' ');
}
