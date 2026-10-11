/** Selector local de módulos; recibe exclusivamente enlaces ya autorizados. */
import { ChangeDetectionStrategy, Component, computed, input, output, signal } from '@angular/core';
import { IconoComponent, type NombreIcono } from './icono.component';
import { VentanaFlotanteComponent } from './ventana-flotante.component';

export interface GrupoSeccionesBuscables {
  readonly id: string;
  readonly etiqueta: string;
  readonly enlaces: readonly {
    readonly ruta: string;
    readonly etiqueta: string;
    readonly icono: NombreIcono;
    readonly demostracion: boolean;
  }[];
}

function normalizar(texto: string): string {
  return texto.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('es');
}

@Component({
  selector: 'app-buscador-secciones',
  standalone: true,
  imports: [IconoComponent, VentanaFlotanteComponent],
  templateUrl: './buscador-secciones.component.html',
  styleUrl: './buscador-secciones.component.scss',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class BuscadorSeccionesComponent {
  readonly grupos = input.required<readonly GrupoSeccionesBuscables[]>();
  readonly ocupada = input(false);
  readonly error = input<string | null>(null);
  readonly cerrar = output<void>();
  readonly elegir = output<{ evento: MouseEvent; ruta: string }>();
  protected readonly consulta = signal('');
  protected readonly resultados = computed(() => {
    const palabras = normalizar(this.consulta()).trim().split(/\s+/).filter(Boolean);
    return this.grupos().map((grupo) => ({
      ...grupo,
      enlaces: grupo.enlaces.filter((enlace) => {
        const texto = normalizar(`${grupo.etiqueta} ${enlace.etiqueta}`);
        return palabras.every((palabra) => texto.includes(palabra));
      }),
    })).filter((grupo) => grupo.enlaces.length > 0);
  });
  protected readonly cantidad = computed(() =>
    this.resultados().reduce((total, grupo) => total + grupo.enlaces.length, 0),
  );
}
