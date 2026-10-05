/**
 * Vocabulario del odontograma compartido por el lienzo y el historial de pieza.
 *
 * Refleja `backend/app/modulos/odontologia/vocabulario.py`: si se añade un
 * hallazgo allí, se añade aquí con su nombre y su color.
 */
import type {
  CaraOdontologica,
  Denticion,
  EstadoPiezaOdontograma,
  HallazgoCara,
  HallazgoPieza,
} from '../../nucleo/servicios/api.service';

export const CARAS: readonly { codigo: CaraOdontologica; nombre: string }[] = [
  { codigo: 'O', nombre: 'Oclusal o incisal' },
  { codigo: 'M', nombre: 'Mesial' },
  { codigo: 'D', nombre: 'Distal' },
  { codigo: 'V', nombre: 'Vestibular' },
  { codigo: 'L', nombre: 'Lingual o palatina' },
];

export const HALLAZGOS_PIEZA: readonly { codigo: HallazgoPieza; nombre: string }[] = [
  { codigo: 'AUSENTE', nombre: 'Ausente' },
  { codigo: 'A_EXTRAER', nombre: 'Pendiente de extracción' },
  { codigo: 'CORONA', nombre: 'Corona' },
  { codigo: 'ENDODONCIA', nombre: 'Endodoncia' },
  { codigo: 'IMPLANTE', nombre: 'Implante' },
  { codigo: 'PROTESIS_FIJA', nombre: 'Prótesis fija' },
  { codigo: 'RESTO_RADICULAR', nombre: 'Resto radicular' },
];

/** Color de cada hallazgo de cara: clase CSS `cara--<codigo>` en el lienzo. */
export const HALLAZGOS_CARA: readonly { codigo: HallazgoCara; nombre: string }[] = [
  { codigo: 'CARIES', nombre: 'Caries' },
  { codigo: 'OBTURACION_RESINA', nombre: 'Obturación de resina' },
  { codigo: 'OBTURACION_AMALGAMA', nombre: 'Obturación de amalgama' },
  { codigo: 'SELLANTE', nombre: 'Sellante' },
  { codigo: 'FRACTURA', nombre: 'Fractura' },
];

export const GRUPOS_FDI: Readonly<
  Record<Denticion, readonly { nombre: string; piezas: readonly number[] }[]>
> = {
  PERMANENTE: [
    { nombre: 'Superior derecho', piezas: [18, 17, 16, 15, 14, 13, 12, 11] },
    { nombre: 'Superior izquierdo', piezas: [21, 22, 23, 24, 25, 26, 27, 28] },
    { nombre: 'Inferior derecho', piezas: [48, 47, 46, 45, 44, 43, 42, 41] },
    { nombre: 'Inferior izquierdo', piezas: [31, 32, 33, 34, 35, 36, 37, 38] },
  ],
  TEMPORAL: [
    { nombre: 'Superior derecho', piezas: [55, 54, 53, 52, 51] },
    { nombre: 'Superior izquierdo', piezas: [61, 62, 63, 64, 65] },
    { nombre: 'Inferior derecho', piezas: [85, 84, 83, 82, 81] },
    { nombre: 'Inferior izquierdo', piezas: [71, 72, 73, 74, 75] },
  ],
  MIXTA: [
    { nombre: 'Superior derecho', piezas: [55, 54, 53, 52, 51, 18, 17, 16, 15, 14, 13, 12, 11] },
    { nombre: 'Superior izquierdo', piezas: [21, 22, 23, 24, 25, 26, 27, 28, 61, 62, 63, 64, 65] },
    { nombre: 'Inferior derecho', piezas: [85, 84, 83, 82, 81, 48, 47, 46, 45, 44, 43, 42, 41] },
    { nombre: 'Inferior izquierdo', piezas: [31, 32, 33, 34, 35, 36, 37, 38, 71, 72, 73, 74, 75] },
  ],
};

export const PIEZA_VACIA: EstadoPiezaOdontograma = { pieza: null, caras: {}, nota: null };

/** Posición de una región dentro del dibujo de la pieza, vista por el clínico. */
export type Region = 'arriba' | 'abajo' | 'izquierda' | 'derecha' | 'centro';

/**
 * Qué cara anatómica ocupa cada región del dibujo.
 *
 * El odontograma se mira de frente al paciente: su derecha queda a la
 * izquierda del clínico. Arriba del dibujo de una pieza superior está
 * vestibular y abajo palatina; en las inferiores es al revés. Mesial mira a
 * la línea media: a la derecha del dibujo en los cuadrantes 1, 4, 5 y 8, a la
 * izquierda en 2, 3, 6 y 7.
 */
export function caraEnRegion(pieza: number, region: Region): CaraOdontologica {
  const cuadrante = Math.floor(pieza / 10);
  const superior = [1, 2, 5, 6].includes(cuadrante);
  const mesialALaDerecha = [1, 4, 5, 8].includes(cuadrante);
  switch (region) {
    case 'centro':
      return 'O';
    case 'arriba':
      return superior ? 'V' : 'L';
    case 'abajo':
      return superior ? 'L' : 'V';
    case 'derecha':
      return mesialALaDerecha ? 'M' : 'D';
    case 'izquierda':
      return mesialALaDerecha ? 'D' : 'M';
  }
}

export function nombreHallazgoCara(codigo: string): string {
  return HALLAZGOS_CARA.find((opcion) => opcion.codigo === codigo)?.nombre ?? codigo;
}

export function nombreHallazgoPieza(codigo: string | null): string {
  return HALLAZGOS_PIEZA.find((opcion) => opcion.codigo === codigo)?.nombre ?? '';
}

/** Resumen legible del estado de una pieza: «Corona; O: Caries, M: Sellante». */
export function describirEstado(estado: EstadoPiezaOdontograma | undefined): string {
  if (!estado) return 'Sin hallazgos';
  const caras = Object.entries(estado.caras)
    .map(([cara, valor]) => `${cara}: ${nombreHallazgoCara(valor)}`)
    .join(', ');
  return [nombreHallazgoPieza(estado.pieza), caras].filter(Boolean).join('; ') || 'Sin hallazgos';
}

export function mismoEstado(
  a: EstadoPiezaOdontograma | undefined,
  b: EstadoPiezaOdontograma | undefined,
): boolean {
  const normal = (estado: EstadoPiezaOdontograma | undefined) => {
    const e = estado ?? PIEZA_VACIA;
    const caras = Object.keys(e.caras)
      .sort()
      .map((cara) => `${cara}=${e.caras[cara as CaraOdontologica]}`)
      .join(',');
    return `${e.pieza ?? ''}|${caras}|${e.nota ?? ''}`;
  };
  return normal(a) === normal(b);
}
