export type SitioPerio = 'VM' | 'VC' | 'VD' | 'LM' | 'LC' | 'LD';
export interface MedicionPerio { profundidad: number | null; margen: number | null; sangrado: boolean | null; placa: boolean | null; supuracion: boolean | null }
export interface PiezaPerio { ausente: boolean; implante: boolean; movilidad: number | null; furcacion: number | null; sitios: Partial<Record<SitioPerio, MedicionPerio>>; nota: string | null }
export interface ResumenPerio { sitios_posibles: number; sitios_sondados: number; profundidad_media: number | null; insercion_media: number | null; sitios_insercion: number; sangrado_positivos: number; sangrado_evaluados: number; sangrado_porcentaje: number | null; placa_positivos: number; placa_evaluados: number; placa_porcentaje: number | null; sitios_4_5: number; sitios_6_mas: number }
export interface Periodontograma { id: string; raiz_id: string; version: number; paciente_id: string; profesional_id: string; especialidad_id: string; sede_id: string | null; cita_id: string | null; fecha_examen: string; piezas: Record<string, PiezaPerio>; observaciones: string | null; motivo: string; nivel_sensibilidad: 'N2' | 'N3'; anulado: boolean; vigente: boolean; puede_editar: boolean; creado_en: string; resumen: ResumenPerio }
export const SITIOS_PERIO: readonly { id: SitioPerio; nombre: string }[] = [
  {id:'VM', nombre:'Vestibular mesial'}, {id:'VC', nombre:'Vestibular central'}, {id:'VD', nombre:'Vestibular distal'},
  {id:'LM', nombre:'Palatino/lingual mesial'}, {id:'LC', nombre:'Palatino/lingual central'}, {id:'LD', nombre:'Palatino/lingual distal'},
];
export function piezaVacia(): PiezaPerio { return {ausente:false, implante:false, movilidad:null, furcacion:null, sitios:{}, nota:null}; }
export function sitioVacio(): MedicionPerio { return {profundidad:null, margen:null, sangrado:null, placa:null, supuracion:null}; }
export function compararPeriodontogramas(a: Periodontograma, b: Periodontograma): { sitios: number; diferencia: number | null } {
  const diferencias: number[] = [];
  for (const [codigo, pieza] of Object.entries(a.piezas)) {
    const anterior = b.piezas[codigo];
    if (pieza.ausente || !anterior || anterior.ausente || pieza.implante !== anterior.implante) continue;
    for (const {id} of SITIOS_PERIO) {
      const actual = pieza.sitios[id]?.profundidad;
      const previo = anterior.sitios[id]?.profundidad;
      if (actual != null && previo != null) diferencias.push(actual - previo);
    }
  }
  return {sitios:diferencias.length, diferencia:diferencias.length ? diferencias.reduce((a,b)=>a+b,0)/diferencias.length : null};
}
