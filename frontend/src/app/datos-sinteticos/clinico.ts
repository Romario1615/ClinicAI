/**
 * Datos sinteticos de las pantallas clinicas del prototipo.
 *
 * Nada de aqui es informacion medica real ni describe a ninguna persona. Son
 * ejemplos de libro de texto con el unico fin de que la pantalla tenga la
 * forma que tendra en produccion.
 *
 * **Advertencia deliberada:** estas estructuras NO son el modelo definitivo
 * de la historia clinica ni de las recetas. El modelo real vive en el backend
 * (Fase 7) con versionado append-only, control de acceso por tipo de
 * informacion y generacion de tomas solo desde una receta confirmada por un
 * profesional. Lo que hay aqui es una maqueta.
 */
import { MARCA_SINTETICO } from './catalogo';

export type EstadoToma = 'PENDIENTE' | 'TOMADA' | 'OMITIDA';
export type EstadoDocumento = 'DRAFT' | 'PENDING_REVIEW' | 'APPROVED' | 'PUBLISHED' | 'ARCHIVED';

export interface NotaEvolucion {
  readonly id: string;
  readonly paciente_id: string;
  readonly profesional_id: string;
  readonly fecha: string;
  readonly version: number;
  readonly motivo_consulta: string;
  readonly evolucion: string;
  readonly motivo_modificacion: string | null;
}

export interface Receta {
  readonly id: string;
  readonly paciente_id: string;
  readonly profesional_id: string;
  readonly fecha: string;
  readonly confirmada: boolean;
  readonly medicamentos: readonly MedicamentoRecetado[];
}

export interface MedicamentoRecetado {
  readonly nombre: string;
  readonly dosis: string;
  readonly via: string;
  readonly frecuencia_horas: number | null;
  readonly dias: number;
  /**
   * «Cuando sea necesario».
   *
   * Un PRN **no** genera horarios fijos. Convertirlo en pauta fija es un
   * error de medicacion, no un detalle de interfaz, y por eso la maqueta ya
   * lo distingue: la pantalla no debe ofrecer recordatorios para estos.
   */
  readonly cuando_sea_necesario: boolean;
}

export interface Toma {
  readonly id: string;
  readonly receta_id: string;
  readonly medicamento: string;
  readonly programada_en: string;
  readonly estado: EstadoToma;
}

export interface EntradaListaEspera {
  readonly id: string;
  readonly paciente_id: string;
  readonly especialidad_id: string;
  readonly sede_id: string;
  readonly prioridad: 'NORMAL' | 'ALTA';
  readonly desde: string;
  readonly preferencia_horaria: string;
}

export interface DocumentoConocimiento {
  readonly id: string;
  readonly titulo: string;
  readonly categoria: string;
  readonly version: number;
  readonly estado: EstadoDocumento;
  readonly vigente_desde: string;
  readonly vigente_hasta: string | null;
  readonly resumen: string;
}

const HOY = new Date();

function dias(desplazamiento: number): string {
  const fecha = new Date(HOY);
  fecha.setDate(fecha.getDate() + desplazamiento);
  return fecha.toISOString();
}

export const NOTAS: readonly NotaEvolucion[] = [
  {
    id: 'nota-1',
    paciente_id: 'pac-1',
    profesional_id: 'prof-1',
    fecha: dias(-30),
    version: 2,
    motivo_consulta: `Control rutinario ${MARCA_SINTETICO}`,
    evolucion:
      'Ejemplo de nota de evolucion sin contenido clinico real. Signos vitales dentro de ' +
      'rango. Se indica control en un mes.',
    motivo_modificacion: 'Correccion de la fecha de control indicada',
  },
  {
    id: 'nota-2',
    paciente_id: 'pac-1',
    profesional_id: 'prof-1',
    fecha: dias(-90),
    version: 1,
    motivo_consulta: `Primera consulta ${MARCA_SINTETICO}`,
    evolucion: 'Ejemplo de nota inicial sin contenido clinico real.',
    motivo_modificacion: null,
  },
];

export const RECETAS: readonly Receta[] = [
  {
    id: 'receta-1',
    paciente_id: 'pac-1',
    profesional_id: 'prof-1',
    fecha: dias(-30),
    confirmada: true,
    medicamentos: [
      {
        nombre: 'Medicamento de ejemplo A',
        dosis: '1 comprimido',
        via: 'Oral',
        frecuencia_horas: 12,
        dias: 7,
        cuando_sea_necesario: false,
      },
      {
        nombre: 'Medicamento de ejemplo B',
        dosis: '1 comprimido',
        via: 'Oral',
        frecuencia_horas: null,
        dias: 7,
        // PRN: la pantalla no ofrece recordatorios para este.
        cuando_sea_necesario: true,
      },
    ],
  },
  {
    id: 'receta-2',
    paciente_id: 'pac-2',
    profesional_id: 'prof-1',
    fecha: dias(-2),
    // Sin confirmar: no genera calendario de tomas. La pantalla tiene que
    // dejarlo claro, porque es la diferencia entre un borrador y una
    // indicacion.
    confirmada: false,
    medicamentos: [
      {
        nombre: 'Medicamento de ejemplo C',
        dosis: '5 ml',
        via: 'Oral',
        frecuencia_horas: 8,
        dias: 5,
        cuando_sea_necesario: false,
      },
    ],
  },
];

export const TOMAS: readonly Toma[] = [
  {
    id: 'toma-1',
    receta_id: 'receta-1',
    medicamento: 'Medicamento de ejemplo A',
    programada_en: dias(-1),
    estado: 'TOMADA',
  },
  {
    id: 'toma-2',
    receta_id: 'receta-1',
    medicamento: 'Medicamento de ejemplo A',
    programada_en: dias(-1),
    estado: 'OMITIDA',
  },
  {
    id: 'toma-3',
    receta_id: 'receta-1',
    medicamento: 'Medicamento de ejemplo A',
    programada_en: dias(0),
    estado: 'PENDIENTE',
  },
  {
    id: 'toma-4',
    receta_id: 'receta-1',
    medicamento: 'Medicamento de ejemplo A',
    programada_en: dias(1),
    estado: 'PENDIENTE',
  },
];

export const LISTA_ESPERA: readonly EntradaListaEspera[] = [
  {
    id: 'espera-1',
    paciente_id: 'pac-3',
    especialidad_id: 'esp-medicina-general',
    sede_id: 'sede-centro',
    prioridad: 'ALTA',
    desde: dias(-5),
    preferencia_horaria: 'Mananas',
  },
  {
    id: 'espera-2',
    paciente_id: 'pac-4',
    especialidad_id: 'esp-fisioterapia',
    sede_id: 'sede-centro',
    prioridad: 'NORMAL',
    desde: dias(-3),
    preferencia_horaria: 'Tardes',
  },
  {
    id: 'espera-3',
    paciente_id: 'pac-5',
    especialidad_id: 'esp-nutricion',
    sede_id: 'sede-norte',
    prioridad: 'NORMAL',
    desde: dias(-1),
    preferencia_horaria: 'Cualquiera',
  },
];

export const DOCUMENTOS: readonly DocumentoConocimiento[] = [
  {
    id: 'doc-1',
    titulo: 'Preparacion para analisis de sangre',
    categoria: 'Preparacion de examenes',
    version: 3,
    estado: 'PUBLISHED',
    vigente_desde: dias(-200),
    vigente_hasta: null,
    resumen: 'Documento de ejemplo. Indicaciones generales de ayuno y horario.',
  },
  {
    id: 'doc-2',
    titulo: 'Politica de cancelacion de citas',
    categoria: 'Politicas de la clinica',
    version: 2,
    estado: 'APPROVED',
    vigente_desde: dias(-60),
    vigente_hasta: dias(300),
    resumen: 'Documento de ejemplo. Plazos y condiciones de cancelacion.',
  },
  {
    id: 'doc-3',
    titulo: 'Horarios de atencion por sede',
    categoria: 'Informacion general',
    version: 5,
    estado: 'PUBLISHED',
    vigente_desde: dias(-20),
    vigente_hasta: null,
    resumen: 'Documento de ejemplo. Horarios por sede y especialidad.',
  },
  {
    id: 'doc-4',
    titulo: 'Protocolo interno retirado',
    categoria: 'Politicas de la clinica',
    version: 1,
    estado: 'ARCHIVED',
    vigente_desde: dias(-500),
    vigente_hasta: dias(-120),
    resumen:
      'Documento de ejemplo ARCHIVADO. Un documento archivado o vencido nunca se recupera ' +
      'en una consulta del agente (ADR-0013).',
  },
];
