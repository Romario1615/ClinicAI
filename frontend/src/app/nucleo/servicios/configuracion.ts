/**
 * Configuracion del cliente.
 *
 * Nada de esto es secreto. Todo lo que llega al navegador es publico por
 * definicion: un `environment.ts` con una clave dentro es una clave
 * publicada, aunque el archivo no se suba al repositorio. Aqui solo hay la
 * direccion de la API y el modo de datos.
 *
 * Modo de datos
 * -------------
 * `origen` decide de donde salen los datos de cada pantalla:
 *
 *  * `api`       -- todo del backend. Es el modo de operacion.
 *  * `hibrido`   -- autenticacion y agenda del backend real; el resto, datos
 *                   sinteticos. Es el modo del prototipo, porque esas dos
 *                   partes ya existen y las demas no.
 *  * `sintetico` -- todo sintetico, sin backend. Sirve para revisar la
 *                   interfaz sin levantar PostgreSQL.
 *
 * Que exista `hibrido` es deliberado y no es deuda: construir dobles para la
 * autenticacion, que ya funciona y esta probada, seria trabajo que hay que
 * borrar despues. Lo que si es obligatorio es que la interfaz **diga** cuando
 * un dato es de demostracion; de eso se encarga `AvisoDemostracion`.
 */
import { InjectionToken } from '@angular/core';

export type OrigenDatos = 'api' | 'hibrido' | 'sintetico';

export interface ConfiguracionCliente {
  /** Base de la API, sin barra final. */
  readonly urlApi: string;
  readonly origenDatos: OrigenDatos;
  /**
   * Identificador de la clinica para el formulario de acceso.
   *
   * El backend exige `clinica_id` al iniciar sesion porque el correo es unico
   * por clinica, no globalmente. En una instalacion real lo fija el
   * despliegue (un dominio por clinica); aqui queda configurable y, si esta
   * vacio, el formulario lo pide.
   */
  readonly clinicaPorDefecto: string;
  /** Zona horaria de presentacion mientras no haya sede seleccionada. */
  readonly zonaHorariaPorDefecto: string;
}

export const CONFIGURACION = new InjectionToken<ConfiguracionCliente>('ConfiguracionCliente');

export const CONFIGURACION_POR_DEFECTO: ConfiguracionCliente = {
  urlApi: 'http://127.0.0.1:8000/api/v1',
  origenDatos: 'hibrido',
  clinicaPorDefecto: '',
  zonaHorariaPorDefecto: 'America/Guayaquil',
};

/**
 * Permisos que la interfaz consulta para decidir que ofrecer.
 *
 * **No son un control de seguridad.** El backend revalida cada peticion y
 * aplica ademas el filtro de ambito; esconder un boton solo evita que alguien
 * pulse algo que va a recibir un 403. Un guard de frontend nunca protege
 * datos (CLAUDE.md, regla 7).
 */
export const PERMISOS = {
  agendaLeer: 'agenda.leer',
  citaCrear: 'cita.crear',
  citaCancelar: 'cita.cancelar',
  citaReprogramar: 'cita.reprogramar',
  citaCompletar: 'cita.completar',
  citaInasistencia: 'cita.marcar_inasistencia',
  pacienteLeer: 'paciente.leer_administrativo',
  pacienteCrear: 'paciente.crear',
  historiaLeer: 'historia_clinica.leer',
  historiaEscribir: 'historia_clinica.escribir',
  recetaCrear: 'receta.crear',
  // Un asistente tiene `receta.leer` y `adherencia.leer` sin tener
  // `historia_clinica.leer`: puede seguir la medicacion y no leer las notas.
  recetaLeer: 'receta.leer',
  adherenciaLeer: 'adherencia.leer',
  listaEsperaGestionar: 'lista_espera.gestionar',
  conocimientoLeer: 'conocimiento.leer',
  metricasLeer: 'metricas.leer',
} as const;
