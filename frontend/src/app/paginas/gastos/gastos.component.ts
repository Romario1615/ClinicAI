import { FotosRegistroComponent } from '../../compartido/fotos-registro.component';
/**
 * Gastos y caja.
 *
 * Dos preguntas en una pantalla: «¿en qué se fue el dinero?» (el libro de
 * gastos) y «¿cómo quedó la caja?» (pagos confirmados menos gastos del
 * periodo). El resultado es de caja y se dice así: no es un estado de
 * resultados ni sustituye a la contabilidad.
 *
 * Un gasto no se edita: se anula con motivo y se registra el correcto. La
 * pantalla lo refleja (no hay botón de editar) y el servidor lo impone.
 *
 * Gráficos en movimiento: las cifras del resultado cuentan hasta su valor y
 * las barras crecen al llegar (`data-crecer`), con la coreografía global.
 */
import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { DOCUMENT, NgTemplateOutlet } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { CapturaFotosComponent, type FotoSeleccionada } from '../../compartido/captura-fotos.component';
import { FotosRegistroService } from '../../nucleo/servicios/fotos-registro.service';

import { CargandoComponent, ErrorComponent, VacioComponent } from '../../compartido/estados.component';
import { IconoComponent } from '../../compartido/icono.component';
import { TarjetasIndicadoresComponent, type Indicador } from '../../compartido/tarjetas-indicadores.component';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
import type { Sede } from '../../nucleo/modelos/dominio';
import { FalloApi } from '../../nucleo/servicios/api.service';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { PERMISOS } from '../../nucleo/servicios/configuracion';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { hoyEnZona, sumarDias } from '../../nucleo/utilidades/fechas';
import {
  CATEGORIAS_GASTO,
  GastosService,
  type CategoriaGasto,
  type FlujoCaja,
  type Gasto,
  type MetodoGasto,
} from './gastos.service';

const POR_PAGINA = 25;
const ZONA_POR_DEFECTO = 'America/Guayaquil';
const FORMATO_DINERO = new Intl.NumberFormat('es-EC', { style: 'currency', currency: 'USD' });

const ETIQUETAS_CATEGORIA: Readonly<Record<string, string>> = Object.fromEntries(
  CATEGORIAS_GASTO.map((categoria) => [categoria.codigo, categoria.etiqueta]),
);
const ETIQUETAS_METODO: Readonly<Record<MetodoGasto, string>> = {
  EFECTIVO: 'Efectivo',
  TRANSFERENCIA: 'Transferencia',
  TARJETA: 'Tarjeta',
};

interface FormularioGasto {
  sede_id: string | null;
  fecha: string;
  categoria: CategoriaGasto;
  descripcion: string;
  proveedor: string;
  importe: number | null;
  metodo: MetodoGasto;
  referencia: string;
}

function aFallo(error: unknown, mensaje: string): FalloApi {
  return error instanceof FalloApi ? error : new FalloApi('ERROR_DESCONOCIDO', mensaje, 0);
}

@Component({
  selector: 'app-gastos',
  standalone: true,
  imports: [
    FormsModule, NgTemplateOutlet, CapturaFotosComponent, FotosRegistroComponent,
    IconoComponent,
    TarjetasIndicadoresComponent,
    VentanaFlotanteComponent,
    CargandoComponent,
    ErrorComponent,
    VacioComponent,
  ],
  host: { class: 'pantalla' },
  template: `
    <header class="modulo-cabecera pantalla__fijo">
      <div class="modulo-cabecera__texto">
        <p class="ceja"><app-icono nombre="gastos" [tamano]="16" /> FINANZAS</p>
        <h1>Gastos y caja</h1>
        <p>
          Cada salida de dinero de la clínica y el resultado de caja del periodo: pagos confirmados
          menos gastos vigentes. Un gasto no se edita; se anula con motivo y se registra el correcto.
        </p>
      </div>
      @if (puedeRegistrar()) {
        <button type="button" class="boton boton--principal" (click)="abrirAlta()">
          <app-icono nombre="mas" [tamano]="17" /> Registrar gasto
        </button>
      }
    </header>

    <form class="tarjeta gastos__filtros pantalla__fijo" (ngSubmit)="aplicar()" aria-label="Periodo y filtros">
      <label class="campo campo--linea">
        <span class="campo__etiqueta">Desde</span>
        <input class="campo__control" type="date" name="desde" required [max]="hasta" [(ngModel)]="desde" />
      </label>
      <label class="campo campo--linea">
        <span class="campo__etiqueta">Hasta (incluido)</span>
        <input class="campo__control" type="date" name="hasta" required [min]="desde" [max]="hoy()" [(ngModel)]="hasta" />
      </label>
      <label class="campo campo--linea">
        <span class="campo__etiqueta">Sede</span>
        <select class="campo__control" name="sede" [(ngModel)]="sedeFiltro">
          <option [ngValue]="null">Todas</option>
          @for (sede of sedes(); track sede.id) {
            <option [ngValue]="sede.id">{{ sede.nombre }}</option>
          }
        </select>
      </label>
      <label class="campo campo--linea">
        <span class="campo__etiqueta">Categoría</span>
        <select class="campo__control" name="categoria" [(ngModel)]="categoriaFiltro">
          <option [ngValue]="null">Todas</option>
          @for (categoria of categorias; track categoria.codigo) {
            <option [ngValue]="categoria.codigo">{{ categoria.etiqueta }}</option>
          }
        </select>
      </label>
      <label class="campo--en-linea gastos__anulados">
        <input type="checkbox" name="anulados" [(ngModel)]="incluirAnulados" />
        <span>Ver anulados</span>
      </label>
      <div class="acciones">
        <button type="submit" class="boton">Aplicar</button>
      </div>
    </form>

    @if (puedeVerFlujo() && !estrecho() && !cargandoFlujo() && !falloFlujo() && flujo()) {
      <app-tarjetas-indicadores class="pantalla__fijo" [indicadores]="indicadoresFlujo()" titulo="Resultado de caja del periodo" />
    }

    <!-- Movimientos del periodo: una sola definición, que se pinta en la
         columna (escritorio ancho y móvil) o en una ventana (escritorio
         estrecho, donde el libro necesita todo el ancho). -->
    <ng-template #movimientos>
      @if (cargandoFlujo()) {
        <app-cargando mensaje="Calculando el flujo de caja…" />
      } @else if (falloFlujo(); as fallo) {
        <app-error titulo="No se pudo calcular el flujo" [mensaje]="fallo.message" [codigo]="fallo.codigo" (reintentar)="cargarFlujo()" />
      } @else if (flujo(); as f) {
          <div class="rejilla gastos__graficos">
            <section class="tarjeta" aria-labelledby="titulo-categorias">
              <h3 id="titulo-categorias">Gastos por categoría</h3>
              @if (f.por_categoria.length === 0) {
                <p class="campo__ayuda">Sin gastos vigentes en el periodo.</p>
              } @else {
                <ul class="barras">
                  @for (categoria of f.por_categoria; track categoria.categoria) {
                    <li>
                      <span class="barras__etiqueta">{{ etiquetaCategoria(categoria.categoria) }}</span>
                      <span class="barras__pista" aria-hidden="true">
                        <span class="barras__valor barras__valor--gasto" data-crecer [style.width.%]="porcentajeCategoria(categoria.total)"></span>
                      </span>
                      <strong class="numerico">{{ dinero(categoria.total) }}</strong>
                    </li>
                  }
                </ul>
              }
            </section>
            <section class="tarjeta" aria-labelledby="titulo-dias">
              <h3 id="titulo-dias">Entradas y salidas por día</h3>
              @if (f.por_dia.length === 0) {
                <p class="campo__ayuda">Sin movimientos en el periodo.</p>
              } @else {
                <p class="gastos__leyenda">
                  <span class="gastos__muestra gastos__muestra--ingreso" aria-hidden="true"></span> Pagos confirmados
                  <span class="gastos__muestra gastos__muestra--gasto" aria-hidden="true"></span> Gastos
                </p>
                <ul class="dias">
                  @for (dia of f.por_dia; track dia.fecha) {
                    <li>
                      <span class="dias__fecha numerico">{{ fechaCorta(dia.fecha) }}</span>
                      <span class="dias__barras" aria-hidden="true">
                        <span class="barras__pista"><span class="barras__valor barras__valor--ingreso" data-crecer [style.width.%]="porcentajeDia(dia.ingresos)"></span></span>
                        <span class="barras__pista"><span class="barras__valor barras__valor--gasto" data-crecer [style.width.%]="porcentajeDia(dia.gastos)"></span></span>
                      </span>
                      <span class="dias__resultado numerico" [class.dias__resultado--negativo]="esNegativo(dia.resultado)">
                        <span class="solo-lectores">Ingresos {{ dinero(dia.ingresos) }}, gastos {{ dinero(dia.gastos) }}, resultado</span>
                        {{ dinero(dia.resultado) }}
                      </span>
                    </li>
                  }
                </ul>
              }
            </section>
          </div>
          <p class="campo__ayuda gastos__base">{{ f.base }}</p>
      }
    </ng-template>

    <div class="pantalla__columnas gastos__columnas" [class.gastos__columnas--sin-flujo]="!puedeVerFlujo() || estrecho()">
    @if (puedeVerFlujo() && !estrecho()) {
      <section class="tarjeta tarjeta--llena gastos__flujo" aria-labelledby="titulo-flujo">
        <h2 id="titulo-flujo">Movimientos del periodo</h2>
        <div class="desplazable gastos__flujo-cuerpo" tabindex="0" role="region" aria-labelledby="titulo-flujo">
          <ng-container [ngTemplateOutlet]="movimientos" />
        </div>
      </section>
    }

    <section class="tarjeta tarjeta--llena gastos__libro" aria-labelledby="titulo-libro">
      <div class="gastos__libro-cabecera">
        <h2 id="titulo-libro">Libro de gastos</h2>
        @if (pagina(); as p) {
          <p class="campo__ayuda">
            {{ p.total }} registro(s) · vigentes por {{ dinero(p.importe_total) }}
          </p>
        }
        @if (puedeVerFlujo() && estrecho()) {
          <button type="button" class="boton boton--pequeno" aria-haspopup="dialog" (click)="movimientosAbiertos.set(true)">
            <app-icono nombre="gastos" [tamano]="15" /> Movimientos del periodo
          </button>
        }
      </div>
      <!-- El aviso va en la tarjeta que cambia: no le quita alto a la lista. -->
      @if (aviso()) {
        <p class="exito gastos__aviso" role="status">{{ aviso() }}</p>
      }
      @if (cargandoLibro()) {
        <app-cargando mensaje="Cargando el libro…" />
      } @else if (falloLibro(); as fallo) {
        <app-error titulo="No se pudo cargar el libro de gastos" [mensaje]="fallo.message" [codigo]="fallo.codigo" (reintentar)="cargarLibro()" />
      } @else if (pagina()?.elementos?.length) {
        <div class="tabla-envoltorio desplazable" tabindex="0" role="region" aria-label="Gastos del periodo">
          <table class="tabla">
            <caption class="solo-lectores">Gastos del periodo</caption>
            <thead>
              <tr>
                <th scope="col">Fecha</th>
                <th scope="col">Gasto</th>
                <th scope="col" class="numerico">Importe</th>
                <th scope="col">Estado</th>
                <th scope="col"><span class="solo-lectores">Acciones</span></th>
              </tr>
            </thead>
            <tbody>
              @for (gasto of pagina()!.elementos; track gasto.id) {
                <tr [class.gastos__fila--anulada]="gasto.estado === 'ANULADO'">
                  <td class="numerico">{{ fechaCorta(gasto.fecha) }}</td>
                  <td>
                    {{ gasto.descripcion }}
                    <span class="gastos__detalle">{{ etiquetaCategoria(gasto.categoria) }} · {{ etiquetaMetodo(gasto.metodo) }}</span>
                    @if (gasto.proveedor || gasto.referencia) {
                      <span class="gastos__detalle">{{ gasto.proveedor }}{{ gasto.proveedor && gasto.referencia ? ' · ' : '' }}{{ gasto.referencia }}</span>
                    }
                    @if (gasto.motivo_anulacion) {
                      <span class="gastos__detalle">Anulado: {{ gasto.motivo_anulacion }}</span>
                    }
                  </td>
                  <td class="numerico">{{ dinero(gasto.importe) }}</td>
                  <td>
                    <span class="insignia" [class.insignia--peligro]="gasto.estado === 'ANULADO'">
                      {{ gasto.estado === 'ANULADO' ? 'Anulado' : 'Vigente' }}
                    </span>
                  </td>
                  <td class="acciones gastos__acciones">
                    <app-fotos-registro tipo="gasto" [registroId]="gasto.id" [puedeEditar]="puedeRegistrar() && gasto.estado === 'REGISTRADO'" />
                    @if (puedeRegistrar() && gasto.estado === 'REGISTRADO') {
                      <button type="button" class="boton boton--pequeno boton--peligro" (click)="abrirAnulacion(gasto)">
                        Anular
                      </button>
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
        <div class="acciones acciones--separadas gastos__paginas">
          <button type="button" class="boton boton--pequeno" [disabled]="desplazamiento() === 0" (click)="mover(-1)">Anterior</button>
          <span class="campo__ayuda">Página {{ paginaActual() }} de {{ totalPaginas() }}</span>
          <button type="button" class="boton boton--pequeno" [disabled]="paginaActual() >= totalPaginas()" (click)="mover(1)">Siguiente</button>
        </div>
      } @else {
        <app-vacio titulo="Sin gastos en este periodo" detalle="Cambie el periodo o los filtros, o registre el primer gasto." />
      }
    </section>
    </div>

    @if (movimientosAbiertos() && estrecho()) {
      <app-ventana-flotante ceja="Gastos" titulo="Movimientos del periodo" [anchoMaximo]="520" (cerrar)="movimientosAbiertos.set(false)">
        <div class="gastos__flujo-cuerpo">
          @if (!cargandoFlujo() && !falloFlujo() && flujo()) {
            <app-tarjetas-indicadores [indicadores]="indicadoresFlujo()" titulo="Resultado de caja del periodo" />
          }
          <ng-container [ngTemplateOutlet]="movimientos" />
        </div>
      </app-ventana-flotante>
    }

    @if (altaAbierta()) {
      <app-ventana-flotante ceja="Gastos" titulo="Registrar gasto" forma="centrada" [anchoMaximo]="560" [cierraAlPulsarFuera]="false" [ocupada]="guardando()" (cerrar)="altaAbierta.set(false)">
        <form id="formulario-gasto" #formAlta="ngForm" (ngSubmit)="registrar(formAlta.valid)" novalidate>
          <div class="formulario-demo">
            <label class="campo">
              <span class="campo__etiqueta">Fecha</span>
              <input class="campo__control" type="date" name="fecha" required [max]="hoy()" [(ngModel)]="formulario.fecha" />
            </label>
            <label class="campo">
              <span class="campo__etiqueta">Sede</span>
              <select class="campo__control" name="sede" [(ngModel)]="formulario.sede_id" [required]="!todasLasSedes()">
                @if (todasLasSedes()) {
                  <option [ngValue]="null">Toda la clínica</option>
                }
                @for (sede of sedes(); track sede.id) {
                  <option [ngValue]="sede.id">{{ sede.nombre }}</option>
                }
              </select>
            </label>
            <label class="campo">
              <span class="campo__etiqueta">Categoría</span>
              <select class="campo__control" name="categoria" required [(ngModel)]="formulario.categoria">
                @for (categoria of categorias; track categoria.codigo) {
                  <option [ngValue]="categoria.codigo">{{ categoria.etiqueta }}</option>
                }
              </select>
            </label>
            <label class="campo">
              <span class="campo__etiqueta">Importe (USD)</span>
              <input class="campo__control" type="number" name="importe" required min="0.01" step="0.01" inputmode="decimal" [(ngModel)]="formulario.importe" />
            </label>
          </div>
          <label class="campo">
            <span class="campo__etiqueta">Descripción</span>
            <input class="campo__control" name="descripcion" required minlength="3" maxlength="300" [(ngModel)]="formulario.descripcion" />
          </label>
          <div class="formulario-demo">
            <label class="campo">
              <span class="campo__etiqueta">Proveedor</span>
              <input class="campo__control" name="proveedor" maxlength="200" [(ngModel)]="formulario.proveedor" />
            </label>
            <label class="campo">
              <span class="campo__etiqueta">Método</span>
              <select class="campo__control" name="metodo" required [(ngModel)]="formulario.metodo">
                <option value="TRANSFERENCIA">Transferencia</option>
                <option value="EFECTIVO">Efectivo</option>
                <option value="TARJETA">Tarjeta</option>
              </select>
            </label>
            <label class="campo">
              <span class="campo__etiqueta">N.º de factura o referencia</span>
              <input class="campo__control" name="referencia" maxlength="100" [(ngModel)]="formulario.referencia" />
            </label>
          </div>
          <app-captura-fotos titulo="Fotos del comprobante o del gasto" [ocupada]="guardando()" (cambiadas)="fotos=$event" />
          @if (falloAlta(); as fallo) {
            <p class="aviso-error" role="alert">{{ fallo.message }}</p>
          }
        </form>
          <div pie class="acciones acciones--final">
            <button type="button" class="boton" (click)="altaAbierta.set(false)" [disabled]="guardando()">Cancelar</button>
            <button type="submit" form="formulario-gasto" class="boton boton--principal" [disabled]="guardando()">
              {{ guardando() ? 'Guardando…' : 'Registrar gasto' }}
            </button>
          </div>
      </app-ventana-flotante>
    }

    @if (anulando(); as gasto) {
      <app-ventana-flotante ceja="Gastos" titulo="Anular gasto" forma="centrada" [anchoMaximo]="480" [cierraAlPulsarFuera]="false" [ocupada]="guardando()" (cerrar)="anulando.set(null)">
        <form id="formulario-anular-gasto" (ngSubmit)="anular(gasto)" novalidate>
          <p>
            <strong>{{ gasto.descripcion }}</strong> · {{ dinero(gasto.importe) }} · {{ fechaCorta(gasto.fecha) }}
          </p>
          <p class="campo__ayuda">El gasto no se borra: queda anulado con su motivo y deja de sumar en la caja.</p>
          <label class="campo">
            <span class="campo__etiqueta">Motivo</span>
            <textarea class="campo__control" name="motivo" required minlength="5" maxlength="500" [(ngModel)]="motivo"></textarea>
          </label>
          @if (falloAnulacion(); as fallo) {
            <p class="aviso-error" role="alert">{{ fallo.message }}</p>
          }
        </form>
          <div pie class="acciones acciones--final">
            <button type="button" class="boton" (click)="anulando.set(null)" [disabled]="guardando()">Cancelar</button>
            <button type="submit" form="formulario-anular-gasto" class="boton boton--peligro" [disabled]="guardando() || motivo.trim().length < 5">Anular gasto</button>
          </div>
      </app-ventana-flotante>
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    .gastos__filtros {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-end;
      gap: var(--espacio-3);
      margin-bottom: var(--espacio-4);
    }
    .gastos__anulados {
      min-height: var(--toque-minimo);
    }
    .gastos__flujo h2,
    .gastos__libro-cabecera h2 {
      margin: 0;
      font-size: 1.05rem;
    }
    .gastos__flujo-cuerpo {
      display: grid;
      align-content: start;
      gap: var(--espacio-4);
    }
    .gastos__graficos {
      grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr));
    }
    .gastos__graficos h3 {
      font-size: 0.95rem;
    }
    .gastos__base {
      margin: 0;
    }
    .barras,
    .dias {
      display: grid;
      gap: var(--espacio-2);
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .barras li {
      display: grid;
      grid-template-columns: minmax(110px, auto) 1fr auto;
      align-items: center;
      gap: var(--espacio-3);
      font-size: 0.88rem;
    }
    .barras__pista {
      display: block;
      overflow: hidden;
      height: 10px;
      border-radius: 999px;
      background: rgb(16 42 46 / 7%);
    }
    .barras__valor {
      display: block;
      height: 100%;
      min-width: 3px;
      border-radius: inherit;
    }
    .barras__valor--ingreso {
      background: linear-gradient(90deg, #5fd1c4, var(--acento));
    }
    .barras__valor--gasto {
      background: linear-gradient(90deg, #f6c766, #c98a12);
    }
    .dias li {
      display: grid;
      grid-template-columns: 64px 1fr minmax(92px, auto);
      align-items: center;
      gap: var(--espacio-3);
      font-size: 0.85rem;
    }
    .dias__barras {
      display: grid;
      gap: 3px;
    }
    .dias__barras .barras__pista {
      height: 7px;
    }
    .dias__resultado {
      text-align: right;
      font-weight: 650;
      color: var(--exito);
    }
    .dias__resultado--negativo {
      color: var(--peligro);
    }
    .gastos__leyenda {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--espacio-2);
      margin-bottom: var(--espacio-3);
      color: var(--texto-suave);
      font-size: 0.82rem;
    }
    .gastos__muestra {
      display: inline-block;
      width: 18px;
      height: 8px;
      margin-left: var(--espacio-2);
      border-radius: 999px;
    }
    .gastos__muestra--ingreso {
      background: var(--acento);
    }
    .gastos__muestra--gasto {
      background: #c98a12;
    }
    .gastos__libro-cabecera {
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      justify-content: space-between;
      gap: var(--espacio-3);
      margin-bottom: var(--espacio-3);
    }
    .gastos__acciones {
      flex-wrap: nowrap;
      justify-content: flex-end;
    }
    .gastos__aviso {
      margin: 0;
    }
    .gastos__detalle {
      display: block;
      color: var(--texto-tenue);
      font-size: 0.82rem;
    }
    .gastos__fila--anulada td {
      color: var(--texto-tenue);
    }
    .gastos__fila--anulada td:nth-child(3) {
      text-decoration: line-through;
    }
    .gastos__paginas {
      margin-top: var(--espacio-3);
    }
    .insignia {
      display: inline-block;
      padding: 1px 10px;
      border: 1px solid var(--exito);
      border-radius: 999px;
      background: var(--exito-fondo);
      color: var(--exito);
      font-size: 0.78rem;
      font-weight: 650;
    }
    .insignia--peligro {
      border-color: var(--peligro);
      background: var(--peligro-fondo);
      color: var(--peligro);
    }
    /* Escritorio: cabecera y filtros fijos; el resultado de caja y el libro
       se reparten el alto y cada uno desplaza dentro de su tarjeta. */
    @media (min-width: 821px) and (min-height: 600px) {
      .gastos__filtros {
        margin-bottom: 0;
        padding-block: var(--espacio-3);
      }
      .gastos__columnas {
        --pantalla-columnas: minmax(0, 1fr) minmax(0, 2fr);
      }
      .gastos__columnas--sin-flujo {
        --pantalla-columnas: minmax(0, 1fr);
      }
      .gastos__flujo .gastos__graficos {
        grid-template-columns: minmax(0, 1fr);
      }
      .gastos__libro-cabecera {
        margin-bottom: 0;
      }
      .gastos__paginas {
        flex: none;
        margin-top: 0;
      }
    }
    /* Escritorio ancho: los filtros caben en una sola fila. */
    @media (min-width: 1280px) and (min-height: 600px) {
      .gastos__filtros {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 0.8fr)) repeat(2, minmax(0, 1fr)) auto auto;
      }
    }
    /* Escritorio bajo: la descripción de la cabecera cede su alto a la lista. */
    @media (min-width: 821px) and (min-height: 600px) and (max-height: 800px) {
      .modulo-cabecera__texto > p:not(.ceja) {
        display: none;
      }
    }
    /* Escritorio estrecho: la descripción es contexto y cede su alto. */
    @media (min-width: 821px) and (max-width: 1365px) and (min-height: 600px) {
      .modulo-cabecera__texto > p:not(.ceja) {
        display: none;
      }
    }
  `,
})
export class GastosComponent {
  protected readonly operacionFotos = inject(FotosRegistroService).operacion<Gasto>();
  protected fotos: readonly FotoSeleccionada[] = [];
  private readonly gastos = inject(GastosService);
  private readonly catalogo = inject(CatalogoService);
  private readonly sesion = inject(SesionService);

  protected readonly categorias = CATEGORIAS_GASTO;
  protected readonly zona = signal(ZONA_POR_DEFECTO);
  protected readonly hoy = computed(() => hoyEnZona(this.zona()));

  protected desde = '';
  protected hasta = '';
  protected sedeFiltro: string | null = null;
  protected categoriaFiltro: CategoriaGasto | null = null;
  protected incluirAnulados = false;

  protected readonly sedes = signal<readonly Sede[]>([]);
  protected readonly pagina = signal<{ elementos: readonly Gasto[]; total: number; importe_total: string } | null>(null);
  protected readonly flujo = signal<FlujoCaja | null>(null);
  protected readonly desplazamiento = signal(0);
  protected readonly cargandoLibro = signal(true);
  protected readonly cargandoFlujo = signal(false);
  protected readonly falloLibro = signal<FalloApi | null>(null);
  protected readonly falloFlujo = signal<FalloApi | null>(null);
  protected readonly aviso = signal('');

  /**
   * Escritorio estrecho: el libro ocupa todo el ancho y los movimientos se
   * abren en una ventana. Misma consulta que el CSS de la pantalla.
   */
  protected readonly estrecho = signal(false);
  protected readonly movimientosAbiertos = signal(false);
  protected readonly altaAbierta = signal(false);
  protected readonly anulando = signal<Gasto | null>(null);
  protected readonly guardando = signal(false);
  protected readonly falloAlta = signal<FalloApi | null>(null);
  protected readonly falloAnulacion = signal<FalloApi | null>(null);
  protected formulario: FormularioGasto = this.formularioVacio();
  protected motivo = '';
  private claveAlta = '';

  protected readonly puedeRegistrar = computed(() => this.sesion.tienePermiso(PERMISOS.gastoRegistrar));
  protected readonly puedeVerFlujo = computed(() => this.sesion.tienePermiso(PERMISOS.pagoLeer));
  protected readonly todasLasSedes = computed(() => this.sesion.identidad()?.ambito.todas_las_sedes ?? false);

  protected readonly paginaActual = computed(() => Math.floor(this.desplazamiento() / POR_PAGINA) + 1);
  protected readonly totalPaginas = computed(() => Math.max(1, Math.ceil((this.pagina()?.total ?? 0) / POR_PAGINA)));

  protected readonly indicadoresFlujo = computed<readonly Indicador[]>(() => {
    const f = this.flujo();
    if (!f) {
      return [];
    }
    const negativo = this.esNegativo(f.resultado);
    return [
      { etiqueta: 'Pagos confirmados', valor: this.dinero(f.ingresos), detalle: 'Entradas de caja', tono: 'bien' },
      { etiqueta: 'Gastos vigentes', valor: this.dinero(f.gastos), detalle: 'Salidas de caja' },
      {
        etiqueta: 'Resultado de caja',
        valor: this.dinero(f.resultado),
        detalle: negativo ? 'Salió más de lo que entró' : 'Entradas menos salidas',
        tono: negativo ? 'alerta' : 'bien',
      },
      {
        etiqueta: 'Margen de caja',
        valor: f.margen_porcentaje === null ? '—' : `${f.margen_porcentaje.replace('.', ',')} %`,
        detalle: f.margen_porcentaje === null ? 'Sin ingresos en el periodo' : 'Resultado sobre ingresos',
      },
    ];
  });

  private readonly maximoCategoria = computed(() =>
    Math.max(1, ...(this.flujo()?.por_categoria ?? []).map((c) => Number(c.total))),
  );
  private readonly maximoDia = computed(() =>
    Math.max(1, ...(this.flujo()?.por_dia ?? []).flatMap((d) => [Number(d.ingresos), Number(d.gastos)])),
  );

  constructor() {
    const vista = inject(DOCUMENT).defaultView;
    if (typeof vista?.matchMedia === 'function') {
      const consulta = vista.matchMedia('(min-width: 821px) and (max-width: 1365px) and (min-height: 600px)');
      this.estrecho.set(consulta.matches);
      const alCambiar = (evento: MediaQueryListEvent) => this.estrecho.set(evento.matches);
      consulta.addEventListener('change', alCambiar);
      inject(DestroyRef).onDestroy(() => consulta.removeEventListener('change', alCambiar));
    }
    this.fijarPeriodoPorDefecto();
    this.catalogo.sedes().subscribe({ next: (sedes) => this.sedes.set(sedes), error: () => this.sedes.set([]) });
    this.catalogo.clinica().subscribe({
      next: (clinica) => {
        if (clinica.zona_horaria && clinica.zona_horaria !== this.zona()) {
          this.zona.set(clinica.zona_horaria);
          this.fijarPeriodoPorDefecto();
        }
        this.aplicar();
      },
      error: () => this.aplicar(),
    });
  }

  protected aplicar(): void {
    this.desplazamiento.set(0);
    this.cargarLibro();
    this.cargarFlujo();
  }

  cargarLibro(): void {
    this.cargandoLibro.set(true);
    this.falloLibro.set(null);
    this.gastos
      .listar({
        ...this.periodo(),
        sede_id: this.sedeFiltro,
        categoria: this.categoriaFiltro,
        incluir_anulados: this.incluirAnulados,
        limite: POR_PAGINA,
        desplazamiento: this.desplazamiento(),
      })
      .subscribe({
        next: (pagina) => {
          this.pagina.set(pagina);
          this.cargandoLibro.set(false);
        },
        error: (error: unknown) => {
          this.falloLibro.set(aFallo(error, 'No se pudo cargar el libro de gastos.'));
          this.cargandoLibro.set(false);
        },
      });
  }

  cargarFlujo(): void {
    if (!this.puedeVerFlujo()) {
      return;
    }
    this.cargandoFlujo.set(true);
    this.falloFlujo.set(null);
    this.gastos.flujo({ ...this.periodo(), sede_id: this.sedeFiltro }).subscribe({
      next: (flujo) => {
        this.flujo.set(flujo);
        this.cargandoFlujo.set(false);
      },
      error: (error: unknown) => {
        this.falloFlujo.set(aFallo(error, 'No se pudo calcular el flujo de caja.'));
        this.cargandoFlujo.set(false);
      },
    });
  }

  protected mover(paso: number): void {
    this.desplazamiento.update((actual) => Math.max(0, actual + paso * POR_PAGINA));
    this.cargarLibro();
  }

  protected abrirAlta(): void {
    this.operacionFotos.reiniciar(); this.fotos=[];
    this.formulario = this.formularioVacio();
    this.falloAlta.set(null);
    // Una clave por formulario abierto: el doble clic y el reintento tras un
    // corte de red no duplican el gasto.
    this.claveAlta = `gasto-${crypto.randomUUID()}`;
    this.altaAbierta.set(true);
  }

  protected registrar(valido: boolean | null): void {
    const importe = Number(this.formulario.importe);
    if (!valido || !Number.isFinite(importe) || importe <= 0) {
      this.falloAlta.set(new FalloApi('DATOS_INVALIDOS', 'Revise los campos obligatorios y el importe.', 422));
      return;
    }
    this.guardando.set(true);
    this.falloAlta.set(null);
    this.operacionFotos.guardar('gasto',this.gastos
      .registrar(
        {
          sede_id: this.formulario.sede_id,
          fecha: this.formulario.fecha,
          categoria: this.formulario.categoria,
          descripcion: this.formulario.descripcion.trim(),
          proveedor: this.formulario.proveedor.trim() || null,
          importe: importe.toFixed(2),
          metodo: this.formulario.metodo,
          referencia: this.formulario.referencia.trim() || null,
        },
        this.claveAlta,
      ),this.fotos)
      .subscribe({
        next: (gasto) => {
          this.guardando.set(false);
          this.altaAbierta.set(false);
          this.aviso.set(`Gasto registrado: ${gasto.descripcion} por ${this.dinero(gasto.importe)}.`);
          this.aplicar();
        },
        error: (error: unknown) => {
          this.guardando.set(false);
          this.falloAlta.set(aFallo(error, 'No se pudo registrar el gasto.'));
        },
      });
  }

  protected abrirAnulacion(gasto: Gasto): void {
    this.motivo = '';
    this.falloAnulacion.set(null);
    this.anulando.set(gasto);
  }

  protected anular(gasto: Gasto): void {
    if (this.motivo.trim().length < 5) {
      return;
    }
    this.guardando.set(true);
    this.gastos.anular(gasto.id, this.motivo.trim()).subscribe({
      next: () => {
        this.guardando.set(false);
        this.anulando.set(null);
        this.aviso.set(`Gasto anulado: ${gasto.descripcion}.`);
        this.aplicar();
      },
      error: (error: unknown) => {
        this.guardando.set(false);
        this.falloAnulacion.set(aFallo(error, 'No se pudo anular el gasto.'));
      },
    });
  }

  protected dinero(valor: string | number): string {
    return FORMATO_DINERO.format(Number(valor));
  }

  protected esNegativo(valor: string): boolean {
    return Number(valor) < 0;
  }

  protected fechaCorta(fecha: string): string {
    const [ano, mes, dia] = fecha.split('-');
    return `${dia}/${mes}/${ano.slice(2)}`;
  }

  protected etiquetaCategoria(codigo: string): string {
    return ETIQUETAS_CATEGORIA[codigo] ?? codigo;
  }

  protected etiquetaMetodo(metodo: MetodoGasto): string {
    return ETIQUETAS_METODO[metodo] ?? metodo;
  }

  protected porcentajeCategoria(total: string): number {
    return (Number(total) / this.maximoCategoria()) * 100;
  }

  protected porcentajeDia(valor: string): number {
    return (Number(valor) / this.maximoDia()) * 100;
  }

  /** Periodo para la API: `hasta` exclusivo, un día después del elegido. */
  private periodo(): { desde: string; hasta: string } {
    return { desde: this.desde, hasta: sumarDias(this.hasta, 1) };
  }

  private fijarPeriodoPorDefecto(): void {
    const hoy = this.hoy();
    this.hasta = hoy;
    this.desde = `${hoy.slice(0, 8)}01`;
  }

  private formularioVacio(): FormularioGasto {
    const ambito = this.sesion.identidad()?.ambito;
    const sede = ambito?.todas_las_sedes ? null : (ambito?.sedes[0] ?? null);
    return {
      sede_id: sede,
      fecha: this.hoy(),
      categoria: 'INSUMOS',
      descripcion: '',
      proveedor: '',
      importe: null,
      metodo: 'TRANSFERENCIA',
      referencia: '',
    };
  }
}
