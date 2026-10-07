/**
 * Módulos de historia clínica de cada especialidad.
 *
 * Decide qué se activa al revisar una historia desde cada especialidad: el
 * odontólogo trabaja con odontograma, periodoncia y planes; dermatología no.
 * Cambiarlo pide motivo y queda versionado y auditado en el servidor, que es
 * quien de verdad niega los módulos no activos.
 */
import { Component, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';

import { CONFIGURACION } from '../../nucleo/servicios/configuracion';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';

export interface ModuloCatalogo {
  readonly codigo: string;
  readonly nombre: string;
  readonly descripcion: string;
}

export interface ModulosDeEspecialidad {
  readonly id: string;
  readonly nombre: string;
  readonly activa: boolean;
  readonly modulos: readonly string[];
}

interface Configuracion {
  readonly catalogo: readonly ModuloCatalogo[];
  readonly especialidades: readonly ModulosDeEspecialidad[];
}

@Component({
  selector: 'app-modulos-especialidad',
  standalone: true,
  imports: [FormsModule, VentanaFlotanteComponent],
  template: `
    <section class="gestion catalogo-admin" aria-labelledby="titulo-modulos-historia">
      <div class="seccion-cabecera">
        <div>
          <p class="ceja">HISTORIA CLÍNICA</p>
          <h2 id="titulo-modulos-historia">Módulos por especialidad</h2>
          <p>
            Qué se activa al revisar una historia desde cada especialidad. Las notas de evolución, las
            recetas y las indicaciones están siempre; alergias y medicamentos se comparten entre todas.
          </p>
        </div>
      </div>
      @if (error()) { <p class="aviso aviso--error" role="alert">{{ error() }}</p> }
      @if (aviso()) { <p class="aviso" role="status">{{ aviso() }}</p> }
      @if (catalogo().length > 0) {
        <div class="tabla-envoltorio">
          <table class="tabla">
            <thead>
              <tr>
                <th>Especialidad</th>
                @for (modulo of catalogo(); track modulo.codigo) { <th class="centrado">{{ modulo.nombre }}</th> }
                <th class="accion"><span class="solo-lectores">Acciones</span></th>
              </tr>
            </thead>
            <tbody>
              @for (esp of especialidades(); track esp.id) {
                <tr>
                  <td>
                    {{ esp.nombre }}
                    @if (!esp.activa) { <small class="inactiva">Inactiva</small> }
                  </td>
                  @for (modulo of catalogo(); track modulo.codigo) {
                    <td class="centrado">
                      @if (esp.modulos.includes(modulo.codigo)) {
                        <span class="marca marca--si" [attr.aria-label]="modulo.nombre + ': activo'">Sí</span>
                      } @else {
                        <span class="marca" [attr.aria-label]="modulo.nombre + ': no activo'">—</span>
                      }
                    </td>
                  }
                  <td class="accion">
                    <button class="boton boton--pequeno" type="button" (click)="abrir(esp)">Cambiar</button>
                  </td>
                </tr>
              } @empty {
                <tr><td [attr.colspan]="catalogo().length + 2">Aún no hay especialidades registradas.</td></tr>
              }
            </tbody>
          </table>
        </div>
      }
    </section>

    @if (editando(); as esp) {
      <app-ventana-flotante
        ceja="Módulos de historia"
        [titulo]="esp.nombre"
        forma="centrada"
        [anchoMaximo]="520"
        (cerrar)="editando.set(null)"
      >
        <form class="formulario" (ngSubmit)="guardar(esp)">
          <fieldset class="modulos">
            <legend>Se activan al revisar desde {{ esp.nombre }}</legend>
            @for (modulo of catalogo(); track modulo.codigo) {
              <label class="modulo">
                <input
                  type="checkbox"
                  [name]="'modulo-' + modulo.codigo"
                  [checked]="elegidos().has(modulo.codigo)"
                  (change)="alternar(modulo.codigo)"
                />
                <span><strong>{{ modulo.nombre }}</strong><small>{{ modulo.descripcion }}</small></span>
              </label>
            }
          </fieldset>
          <label class="campo">
            <span class="campo__etiqueta">Motivo del cambio</span>
            <input
              class="campo__control"
              name="motivo"
              [(ngModel)]="motivo"
              minlength="5"
              maxlength="300"
              required
              placeholder="Ej.: la especialidad empieza a usar fotos clínicas"
            />
          </label>
          @if (errorCambio()) { <p class="campo__error" role="alert">{{ errorCambio() }}</p> }
          <div class="pie">
            <button class="boton" type="button" (click)="editando.set(null)">Cancelar</button>
            <button class="boton boton--principal" type="submit" [disabled]="guardando()">
              {{ guardando() ? 'Guardando…' : 'Guardar módulos' }}
            </button>
          </div>
        </form>
      </app-ventana-flotante>
    }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    .centrado { text-align: center; }
    .accion { text-align: right; white-space: nowrap; }
    .marca { color: var(--texto-suave); }
    .marca--si { display: inline-block; padding: 1px 10px; border-radius: 999px; background: var(--acento-suave);
      color: var(--acento-fuerte); font-size: 0.8rem; font-weight: 600; }
    .inactiva { display: block; color: var(--texto-suave); }
    .aviso { margin: 0 0 var(--espacio-3); color: var(--texto-suave); }
    .aviso--error { color: var(--peligro); }
    .modulos { display: grid; gap: var(--espacio-2); margin: 0 0 var(--espacio-3); padding: 0; border: 0; }
    .modulos legend { margin-bottom: var(--espacio-2); color: var(--texto-suave); font-size: 0.9rem; }
    .modulo { display: flex; align-items: flex-start; gap: var(--espacio-2); padding: var(--espacio-2);
      border: 1px solid var(--borde); border-radius: var(--radio); cursor: pointer; }
    .modulo input { margin-top: 3px; }
    .modulo span { display: grid; gap: 2px; }
    .modulo small { color: var(--texto-suave); }
    .pie { display: flex; justify-content: flex-end; gap: var(--espacio-2); margin-top: var(--espacio-3); }
  `,
})
export class ModulosEspecialidadComponent {
  private readonly http = inject(HttpClient);
  private readonly configuracion = inject(CONFIGURACION);

  protected readonly catalogo = signal<readonly ModuloCatalogo[]>([]);
  protected readonly especialidades = signal<readonly ModulosDeEspecialidad[]>([]);
  protected readonly error = signal('');
  protected readonly aviso = signal('');

  protected readonly editando = signal<ModulosDeEspecialidad | null>(null);
  protected readonly elegidos = signal<ReadonlySet<string>>(new Set());
  protected readonly guardando = signal(false);
  protected readonly errorCambio = signal('');
  protected motivo = '';

  private get ruta(): string {
    return `${this.configuracion.urlApi}/catalogo/especialidades`;
  }

  constructor() {
    this.http.get<Configuracion>(`${this.ruta}/modulos-historia`).subscribe({
      next: (datos) => {
        this.catalogo.set(datos.catalogo);
        this.especialidades.set(datos.especialidades);
      },
      error: (fallo: HttpErrorResponse) => this.error.set(mensaje(fallo, 'No se pudieron cargar los módulos.')),
    });
  }

  protected abrir(esp: ModulosDeEspecialidad): void {
    this.elegidos.set(new Set(esp.modulos));
    this.motivo = '';
    this.errorCambio.set('');
    this.aviso.set('');
    this.editando.set(esp);
  }

  protected alternar(codigo: string): void {
    this.elegidos.update((actual) => {
      const nuevo = new Set(actual);
      if (nuevo.has(codigo)) nuevo.delete(codigo);
      else nuevo.add(codigo);
      return nuevo;
    });
  }

  protected guardar(esp: ModulosDeEspecialidad): void {
    const motivo = this.motivo.trim();
    if (motivo.length < 5) {
      this.errorCambio.set('Indique un motivo de al menos 5 caracteres.');
      return;
    }
    this.guardando.set(true);
    this.errorCambio.set('');
    const modulos = this.catalogo()
      .map((m) => m.codigo)
      .filter((codigo) => this.elegidos().has(codigo));
    this.http
      .put<ModulosDeEspecialidad>(`${this.ruta}/${esp.id}/modulos-historia`, { modulos, motivo })
      .subscribe({
        next: (actualizada) => {
          this.guardando.set(false);
          this.especialidades.update((lista) => lista.map((e) => (e.id === actualizada.id ? actualizada : e)));
          this.editando.set(null);
          this.aviso.set(`Módulos de ${actualizada.nombre} actualizados.`);
        },
        error: (fallo: HttpErrorResponse) => {
          this.guardando.set(false);
          this.errorCambio.set(mensaje(fallo, 'No se pudieron guardar los módulos.'));
        },
      });
  }
}

function mensaje(fallo: HttpErrorResponse, porDefecto: string): string {
  return (fallo.error as { mensaje?: string } | null)?.mensaje ?? porDefecto;
}
