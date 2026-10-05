/**
 * Matriz de accesos: qué puede hacer cada rol, módulo por módulo.
 *
 * Los permisos son códigos técnicos (`cita.reprogramar`, `odontograma.leer`).
 * Para decidir qué rol dar a una persona hace falta verlo en el idioma de la
 * clínica: «Recepción consulta la agenda y gestiona citas, no ve historia
 * clínica». Esta tabla lo resume a partir de los permisos reales de cada rol
 * (los mismos que aplica el backend), sin interpretación propia.
 *
 * Es solo lectura. Cambiar lo que puede hacer un rol se hace creando un rol de
 * la clínica con sus permisos; los roles del sistema no se modifican.
 */
import { Component, computed, input } from '@angular/core';

interface RolConPermisos {
  readonly id: string;
  readonly nombre: string;
  readonly permisos: readonly string[];
}

type Nivel = 'gestiona' | 'consulta' | 'metadatos' | 'ninguno';

const MODULOS: readonly { nombre: string; prefijos: readonly string[] }[] = [
  { nombre: 'Agenda y citas', prefijos: ['agenda', 'cita', 'bloqueo'] },
  { nombre: 'Pacientes y consentimientos', prefijos: ['paciente', 'consentimiento'] },
  { nombre: 'Lista de espera', prefijos: ['lista_espera'] },
  { nombre: 'Historia clínica', prefijos: ['historia_clinica', 'diagnostico', 'acceso_emergencia'] },
  { nombre: 'Recetas', prefijos: ['receta'] },
  { nombre: 'Seguimiento de adherencia', prefijos: ['adherencia', 'alerta_adherencia'] },
  { nombre: 'Imágenes clínicas', prefijos: ['imagen_clinica'] },
  { nombre: 'Odontograma', prefijos: ['odontograma'] },
  { nombre: 'Plan de tratamiento', prefijos: ['plan_tratamiento'] },
  { nombre: 'Mensajes de WhatsApp', prefijos: ['conversacion'] },
  { nombre: 'Base de conocimiento', prefijos: ['conocimiento'] },
  { nombre: 'Promociones', prefijos: ['promocion'] },
  { nombre: 'Pagos', prefijos: ['pago'] },
  { nombre: 'Profesionales y firmas', prefijos: ['profesional'] },
  { nombre: 'Usuarios y roles', prefijos: ['usuario', 'rol'] },
  {
    nombre: 'Clínica, sedes y catálogo',
    prefijos: ['clinica', 'sede', 'especialidad', 'servicio', 'configuracion'],
  },
  {
    nombre: 'Panel, reportes y auditoría',
    prefijos: ['dashboard', 'prediccion', 'reporte', 'auditoria', 'exportacion'],
  },
];

/** Acciones que solo leen: con ellas el rol consulta, no gestiona. */
const ACCIONES_DE_LECTURA = new Set([
  'leer',
  'leer_administrativo',
  'leer_metadatos',
  'leer_sensible',
  'consultar',
]);

const TEXTO_NIVEL: Record<Nivel, string> = {
  gestiona: 'Gestiona',
  consulta: 'Consulta',
  metadatos: 'Solo registros',
  ninguno: 'Sin acceso',
};

@Component({
  selector: 'app-matriz-accesos',
  standalone: true,
  template: `
    <section class="matriz" aria-labelledby="titulo-matriz">
      <h2 id="titulo-matriz">Qué puede hacer cada rol</h2>
      <p class="matriz__ayuda">
        Resumen de los permisos reales de cada rol. <strong>Gestiona</strong>: puede crear o
        modificar. <strong>Consulta</strong>: solo ver. <strong>Solo registros</strong>: sabe qué
        registros existen y quién los consultó, sin ver su contenido. Pase el cursor sobre una celda para ver los
        permisos exactos.
      </p>
      <div class="matriz__tabla">
        <table>
          <thead>
            <tr>
              <th scope="col">Módulo</th>
              @for (rol of roles(); track rol.id) {
                <th scope="col">{{ rol.nombre }}</th>
              }
            </tr>
          </thead>
          <tbody>
            @for (fila of filas(); track fila.modulo) {
              <tr>
                <th scope="row">{{ fila.modulo }}</th>
                @for (celda of fila.celdas; track celda.rol) {
                  <td>
                    <span
                      [class]="'nivel nivel--' + celda.nivel"
                      [attr.title]="celda.permisos.length ? celda.permisos.join(', ') : 'Sin permisos en este módulo'"
                    >{{ texto(celda.nivel) }}</span>
                  </td>
                }
              </tr>
            }
          </tbody>
        </table>
      </div>
    </section>
  `,
  styles: `
    .matriz { padding: 1.25rem; border: 1px solid var(--borde); border-radius: 14px; background: var(--superficie); }
    h2 { margin: 0.1rem 0 0.4rem; font-size: 1.15rem; }
    .matriz__ayuda { margin: 0 0 1rem; color: var(--texto-suave); font-size: 0.9rem; }
    .matriz__tabla { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    th, td { padding: 0.5rem 0.6rem; border-bottom: 1px solid var(--superficie-hundida); text-align: center; white-space: nowrap; }
    thead th { position: sticky; top: 0; background: var(--superficie); color: var(--texto-suave); font-size: 0.78rem; font-weight: 700; }
    tbody th { text-align: left; font-weight: 600; }
    .nivel { display: inline-block; min-width: 5.5rem; padding: 0.15rem 0.5rem; border-radius: 999px; font-size: 0.75rem; font-weight: 700; cursor: help; }
    .nivel--gestiona { background: color-mix(in srgb, var(--exito) 16%, transparent); color: var(--exito); }
    .nivel--consulta { background: color-mix(in srgb, var(--acento) 14%, transparent); color: var(--acento-fuerte); }
    .nivel--metadatos { background: var(--superficie-hundida); color: var(--texto-suave); }
    .nivel--ninguno { color: var(--texto-tenue); font-weight: 500; }
  `,
})
export class MatrizAccesosComponent {
  readonly roles = input<readonly RolConPermisos[]>([]);

  protected readonly filas = computed(() =>
    MODULOS.map((modulo) => ({
      modulo: modulo.nombre,
      celdas: this.roles().map((rol) => {
        const permisos = rol.permisos.filter((codigo) =>
          modulo.prefijos.includes(codigo.split('.')[0]),
        );
        const gestiona = permisos.some(
          (codigo) => !ACCIONES_DE_LECTURA.has(codigo.split('.').slice(1).join('.')),
        );
        // Ver que un registro existe y quién lo consultó no es ver su contenido.
        const soloMetadatos =
          permisos.length > 0 && permisos.every((codigo) => codigo.endsWith('.leer_metadatos'));
        const nivel: Nivel =
          permisos.length === 0
            ? 'ninguno'
            : soloMetadatos
              ? 'metadatos'
              : gestiona
                ? 'gestiona'
                : 'consulta';
        return { rol: rol.id, nivel, permisos };
      }),
    })),
  );

  protected texto(nivel: Nivel): string {
    return TEXTO_NIVEL[nivel];
  }
}
