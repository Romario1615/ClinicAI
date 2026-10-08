/**
 * Panel: el arranque del turno.
 *
 * Qué estaba mal
 * --------------
 * La versión anterior abría con cuatro cifras —«citas del periodo: 128»— y una
 * barra por estado. Todo cierto y nada accionable: a las ocho de la mañana, con
 * la sala llenándose, nadie necesita un recuento del mes. Necesita saber **qué
 * se rompe hoy si nadie lo toca**.
 *
 * El orden de la pantalla es el orden de utilidad:
 *
 * 1. **La cola de trabajo.** Lo que tiene plazo: un turno bloqueado que
 *    caduca, una oferta de lista de espera que nadie comunicó, citas sin
 *    confirmar. Es el mismo componente que ocupa el panel derecho de la
 *    agenda, a propósito: la misma pregunta debe dar la misma respuesta en las
 *    dos pantallas.
 * 2. **La carga de hoy por profesional.** Minutos de consulta comprometidos,
 *    no número de citas: una primera consulta y un control no cargan igual.
 * 3. **Las cifras del periodo**, al final, como contexto. La inasistencia va
 *    con su variación respecto al periodo anterior, porque un 8 % no dice nada
 *    sin saber si sube o baja.
 *
 * La ocupación usa los horarios reales de agenda y resta pausas, feriados y
 * bloqueos. Solo se calcula con todos los estados y con el ámbito completo de
 * pacientes para que el numerador y el denominador sean comparables.
 */
import { Component, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { PerfilPacientesComponent } from './perfil-pacientes.component';

import { ColaTrabajoComponent } from '../../compartido/cola-trabajo.component';
import { IconoComponent, type NombreIcono } from '../../compartido/icono.component';
import { FondoIAComponent } from '../../compartido/fondo-ia.component';
import { PestanasComponent, type OpcionPestana } from '../../compartido/pestanas.component';
import { TarjetasIndicadoresComponent } from '../../compartido/tarjetas-indicadores.component';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
import { IndicadoresService, type Indicadores } from '../../nucleo/servicios/indicadores.service';
import { indicadoresDe } from '../../nucleo/utilidades/indicadores';
import { FalloApi } from '../../nucleo/servicios/api.service';
import { ApiService } from '../../nucleo/servicios/api.service';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { PERMISOS } from '../../nucleo/servicios/configuracion';
import {
  OperacionesService,
  type EntradaEspera,
  type Pagina,
  type ResumenPanel,
} from '../../nucleo/servicios/operaciones.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import type { Cita, Especialidad, Profesional, Sede, Servicio } from '../../nucleo/modelos/dominio';
import { derivarPendientes, type TareaPendiente } from '../../nucleo/utilidades/pendientes';
import { cargaPorProfesional, duracionLegible } from '../../nucleo/utilidades/secuencia-dia';
import { hoyEnZona, rangoDelDia, sumarDias } from '../../nucleo/utilidades/fechas';

/** Estados en el orden en que interesan, con su tono semántico. */
const ESTADOS: readonly { codigo: string; etiqueta: string; clase: string }[] = [
  { codigo: 'CONFIRMED', etiqueta: 'Confirmadas', clase: 'exito' },
  { codigo: 'RESCHEDULED', etiqueta: 'Reprogramadas', clase: 'info' },
  { codigo: 'COMPLETED', etiqueta: 'Atendidas', clase: 'neutra' },
  { codigo: 'PENDING', etiqueta: 'Pendientes', clase: 'neutra' },
  { codigo: 'HELD', etiqueta: 'Bloqueadas', clase: 'aviso' },
  { codigo: 'CANCELLED', etiqueta: 'Canceladas', clase: 'peligro' },
  { codigo: 'NO_SHOW', etiqueta: 'No asistió', clase: 'peligro' },
];

const DIAS_POR_PERIODO: Record<string, number> = { hoy: 1, '7': 7, '30': 30 };

@Component({
  selector: 'app-panel',
  standalone: true,
  imports: [
    FormsModule,
    RouterLink,
    ColaTrabajoComponent,
    IconoComponent,
    FondoIAComponent,
    TarjetasIndicadoresComponent,
    VentanaFlotanteComponent,
    PerfilPacientesComponent,
    PestanasComponent,
  ],
  host: { class: 'pantalla' },
  template: `
    <div class="cabecera-pagina panel__portada pantalla__fijo">
      <app-fondo-ia [oscuro]="true" />
      <div>
        <p class="ceja panel__ceja"><app-icono nombre="agente" [tamano]="16" /> CLINICAI · GESTIÓN CON IA</p>
        <h1>Panel de seguimiento</h1>
        <p class="panel__contexto">{{ hoyLegible() }} · horario de {{ zona() }}</p>
      </div>
      <a class="boton boton--principal" routerLink="/agenda"><app-icono nombre="calendario-check" [tamano]="18" /> Abrir agenda</a>
    </div>

    @if (error()) {
      <p class="aviso-error pantalla__fijo" role="alert">{{ error() }}</p>
    }

    @if (!vistas().length) {
      <div class="tarjeta pantalla__fijo">
        <h2>Su espacio de trabajo</h2>
        <p>Use el menú para acceder a las gestiones habilitadas para su rol.</p>
      </div>
    }

    <!-- Una vista a la vez: el panel apilado medía casi 4000 px de alto. Las
         vistas inactivas se ocultan, no se desmontan, para no repetir
         peticiones al volver a ellas. En escritorio cada vista llena el alto y
         solo desplaza dentro de sus tarjetas. -->
    @if (vistas().length > 1) {
      <app-pestanas
        class="pantalla__fijo"
        grupo="panel"
        etiqueta="Vistas del panel"
        [opciones]="vistas()"
        [activa]="vistaActiva()"
        (activaChange)="vista.set($event)"
      />
    }

    <div class="pantalla__resto">
      <!-- ============ 0. Tablero de su rol ============
           Cada grupo aparece solo si el rol alcanza ese módulo: el backend no
           envía el bloque y aquí no se pinta. Cada tarjeta lleva a donde se
           resuelve lo que cuenta. -->
      @if (tablero().length) {
        <section
          role="tabpanel"
          class="panel__vista desplazable"
          id="panel-panel-resumen"
          aria-labelledby="panel-pestana-resumen"
          [hidden]="vistaActiva() !== 'resumen'"
        >
          @for (grupo of tablero(); track grupo.titulo) {
            <section class="bloque">
              <div class="bloque__cabecera">
                <h2>{{ grupo.titulo }}</h2>
                <span class="bloque__linea" aria-hidden="true"></span>
              </div>
              <app-tarjetas-indicadores [indicadores]="grupo.tarjetas" [titulo]="grupo.titulo" />
            </section>
          }
        </section>
      }

      <!-- ============ 1. Lo que tiene plazo y 2. la carga de hoy ============ -->
      @if (sesion.tienePermiso(PERMISOS.agendaLeer)) {
        <section
          role="tabpanel"
          class="panel__vista pantalla__columnas panel__hoy"
          id="panel-panel-hoy"
          aria-labelledby="panel-pestana-hoy"
          [hidden]="vistaActiva() !== 'hoy'"
        >
          <section class="bloque">
            <div class="bloque__cabecera">
              <h2>Lo primero</h2>
              <span class="bloque__linea" aria-hidden="true"></span>
              <span class="bloque__cuenta numerico">
                {{ pendientes().length }} tarea(s) con plazo
              </span>
            </div>
            <div class="desplazable" tabindex="0" role="region" aria-label="Tareas con plazo">
              @if (cargandoHoy()) {
                <p role="status">Consultando el día…</p>
              } @else {
                <app-cola-trabajo
                  [tareas]="pendientes()"
                  [rejilla]="true"
                  (actuar)="irALaAgenda()"
                  (localizar)="irALaAgenda()"
                />
              }
            </div>
          </section>

          <section class="bloque">
            <div class="bloque__cabecera">
              <h2>Carga de hoy</h2>
              <span class="bloque__linea" aria-hidden="true"></span>
            </div>
            <div class="tarjeta tarjeta--llena">
              <p class="campo__ayuda carga__nota">
                Minutos de consulta comprometidos por profesional durante la jornada.
              </p>
              <div class="desplazable" tabindex="0" role="region" aria-label="Carga por profesional">
                @if (carga().length === 0) {
                  <p class="carga__vacio">Sin citas hoy en su ámbito.</p>
                } @else {
                  <ul class="carga">
                    @for (fila of carga(); track fila.id) {
                      <li class="carga__fila">
                        <span class="carga__nombre">{{ fila.nombre }}</span>
                        <span class="carga__pista" [attr.title]="fila.nombre + ': ' + fila.legible">
                          <span class="carga__barra" [style.width.%]="fila.porcentaje"></span>
                        </span>
                        <span class="carga__valor numerico">{{ fila.legible }}</span>
                      </li>
                    }
                  </ul>
                }
              </div>
            </div>
          </section>
        </section>
      }

      <!-- ============ 3. Las cifras, como contexto ============
           Tres vistas (cifras, distribución y pacientes) comparten el periodo
           y los filtros: los mandos se quedan arriba y no se repiten. -->
      @if (sesion.tienePermiso(PERMISOS.metricasLeer)) {
        <section
          role="tabpanel"
          class="panel__vista panel__cifras"
          [id]="'panel-panel-' + vistaCifras()"
          [attr.aria-labelledby]="'panel-pestana-' + vistaCifras()"
          [hidden]="!esVistaDeCifras()"
        >
          <div class="cifras__mandos">
            <div class="periodos" role="group" aria-label="Periodo">
              @for (opcion of opciones; track opcion.clave) {
                <button
                  type="button"
                  class="periodos__boton"
                  [class.periodos__boton--activo]="periodo() === opcion.clave"
                  [attr.aria-pressed]="periodo() === opcion.clave"
                  (click)="cambiarPeriodo(opcion.clave)"
                >
                  {{ opcion.etiqueta }}
                </button>
              }
            </div>
            <div class="filtros-dashboard__barra">
              <p class="filtros-dashboard__estado" aria-live="polite">
                @if (cantidadFiltrosActivos() > 0) {
                  {{ cantidadFiltrosActivos() }} filtro(s) activo(s) en este resumen
                } @else {
                  Métricas de toda la clínica · hoy
                }
              </p>
              <button
                class="boton boton--secundario filtros-dashboard__abrir"
                type="button"
                (click)="abrirFiltros()"
                aria-haspopup="dialog"
              >
                <app-icono nombre="configuracion" [tamano]="17" /> Ajustar filtros
                @if (cantidadFiltrosActivos() > 0) {
                  <span class="filtros-dashboard__contador">{{ cantidadFiltrosActivos() }}</span>
                }
              </button>
            </div>
            @if (errorFechas()) { <p class="aviso-error" role="alert">{{ errorFechas() }}</p> }
          </div>

          @if (cargandoResumen()) {
            <p role="status">Consultando actividad…</p>
          } @else if (resumen()) {
            @let r = resumen()!;
            <div class="rejilla cifras__rejilla" [hidden]="vistaActiva() !== 'cifras'">
              @if (r.ocupacion_agenda; as ocupacion) {
              <article class="tarjeta tarjeta-vidrio">
                <div class="ocupacion-agenda__cabecera">
                  <span class="ocupacion-agenda__icono" aria-hidden="true"><app-icono nombre="metricas" [tamano]="19" /></span>
                  <div>
                    <p class="cifra__titulo">Ocupación de agenda</p>
                    <p class="campo__ayuda">Reservas activas sobre minutos disponibles</p>
                  </div>
                </div>
                @if (ocupacion.porcentaje === null) {
                  <strong class="ocupacion-agenda__valor">—</strong>
                } @else {
                  <strong class="ocupacion-agenda__valor numerico">{{ ocupacion.porcentaje }}<span>%</span></strong>
                  <progress
                    class="ocupacion-agenda__barra"
                    max="100"
                    [value]="ocupacion.porcentaje"
                    [attr.aria-label]="'Ocupación de agenda: ' + ocupacion.porcentaje + ' por ciento'"
                  ></progress>
                }
                @if (ocupacion.minutos_disponibles !== null && ocupacion.minutos_ocupados !== null) {
                  <p class="ocupacion-agenda__tiempos numerico">
                    {{ formatearDuracion(ocupacion.minutos_ocupados) }} reservados
                    <span aria-hidden="true">·</span>
                    {{ formatearDuracion(ocupacion.minutos_disponibles) }} disponibles
                  </p>
                }
                <p class="campo__ayuda ocupacion-agenda__detalle">{{ ocupacion.detalle }}</p>
              </article>
              }

              <article class="tarjeta inasistencia">
                <p class="inasistencia__titulo">Inasistencia</p>
                <p class="inasistencia__valor">
                  <strong class="numerico">{{ inasistencia().valor }}</strong>
                  @if (inasistencia().delta !== null) {
                    <span
                      class="insignia"
                      [class.insignia--peligro]="inasistencia().sube"
                      [class.insignia--exito]="!inasistencia().sube"
                    >
                      {{ inasistencia().sube ? '▲' : '▼' }} {{ inasistencia().delta }} pt
                    </span>
                  }
                </p>
                <p class="inasistencia__lectura">{{ inasistencia().lectura }}</p>
              </article>

              <article class="tarjeta">
                <p class="cifra__titulo">Citas del periodo</p>
                <strong class="cifra numerico">{{ r.total_citas }}</strong>
                <p class="campo__ayuda">{{ r.pacientes }} paciente(s) distintos</p>
              </article>

              <article class="tarjeta">
                <p class="cifra__titulo">Pacientes atendidos</p>
                @if (r.pacientes_nuevos === null || r.pacientes_recurrentes === null) {
                  <p class="campo__ayuda">El filtro por estado impide comparar primeras atenciones completadas.</p>
                } @else {
                  <dl class="pacientes-tipo">
                    <div><dt>Nuevos</dt><dd class="numerico">{{ r.pacientes_nuevos }}</dd></div>
                    <div><dt>Recurrentes</dt><dd class="numerico">{{ r.pacientes_recurrentes }}</dd></div>
                  </dl>
                  <p class="campo__ayuda">Clasificados por su primera atención completada dentro del filtro.</p>
                }
              </article>

              <article class="tarjeta tarjeta-vidrio retorno-30d" aria-labelledby="retorno-30d-titulo">
                <h3 id="retorno-30d-titulo" class="cifra__titulo">Retorno a 30 días</h3>
                @if (estadoCita()) {
                  <p class="campo__ayuda">Elige “Todos los estados” para calcular cohortes de atenciones completadas.</p>
                } @else if (r.retorno_30_dias; as retorno) {
                  <strong class="cifra numerico">{{ retorno.porcentaje }}%</strong>
                  <progress
                    class="ocupacion-agenda__barra"
                    [value]="retorno.porcentaje"
                    max="100"
                    [attr.aria-label]="'Retorno a 30 días: ' + retorno.porcentaje + ' por ciento'"
                  ></progress>
                  <p class="campo__ayuda numerico">
                    {{ retorno.pacientes_que_regresaron }} de {{ retorno.pacientes_seguimiento_completo }} pacientes regresaron.
                  </p>
                  <p class="campo__ayuda">
                    Otra atención completada dentro de las 720 horas posteriores a la primera del periodo; solo cohortes con seguimiento completo.
                  </p>
                } @else {
                  <p class="campo__ayuda">Sin una cohorte con seguimiento completo o el resultado está protegido para grupos pequeños.</p>
                }
              </article>

              <article class="tarjeta altas-pacientes" aria-labelledby="altas-pacientes-titulo">
                <h3 id="altas-pacientes-titulo" class="cifra__titulo">Altas de pacientes</h3>
                @if (r.pacientes_registrados === null || r.pacientes_registrados === undefined || r.pacientes_registrados_sin_cita === null || r.pacientes_registrados_sin_cita === undefined) {
                  <p class="campo__ayuda">Elige “Todos los estados” para consultar las altas y su registro de citas.</p>
                } @else {
                  <dl class="pacientes-tipo">
                    <div><dt>Registrados</dt><dd class="numerico">{{ r.pacientes_registrados }}</dd></div>
                    <div><dt>Sin cita en los filtros</dt><dd class="numerico">{{ r.pacientes_registrados_sin_cita }}</dd></div>
                  </dl>
                  <p class="campo__ayuda">Alta administrativa dentro del periodo. “Sin cita” significa que no hay un registro de cita dentro de las fechas y filtros actuales.</p>
                }
              </article>

              <article class="tarjeta">
                <p class="cifra__titulo">Sala de espera</p>
                <strong class="cifra numerico">{{ r.espera.personas_en_espera }}</strong>
                <p class="campo__ayuda">paciente(s) esperando en el periodo</p>
                <p class="campo__ayuda">
                  Espera media hasta iniciar:
                  @if (r.espera.promedio_minutos === null) {
                    sin atenciones iniciadas
                  } @else {
                    {{ r.espera.promedio_minutos }} min
                  }
                </p>
                @if (r.espera.espera_mayor_15_minutos > 0) {
                  <p class="carga__demora" role="status">
                    {{ r.espera.espera_mayor_15_minutos }} supera 15 minutos
                  </p>
                }
              </article>

              <article class="tarjeta">
                <p class="cifra__titulo">Recuperación de turnos</p>
                @if (r.recuperacion_turnos.turnos_liberados === null) {
                  <p class="campo__ayuda">Elige “Todos los estados” para consultar cancelaciones y recuperaciones.</p>
                } @else {
                  <dl class="pacientes-tipo">
                    <div><dt>Liberados</dt><dd class="numerico">{{ r.recuperacion_turnos.turnos_liberados }}</dd></div>
                    <div><dt>Recuperados</dt><dd class="numerico">{{ r.recuperacion_turnos.turnos_recuperados }}</dd></div>
                  </dl>
                  <p class="campo__ayuda">
                    Los liberados usan la fecha de cancelación; los recuperados, la fecha de aceptación.
                    @if (r.recuperacion_turnos.promedio_minutos_para_recuperar === null) {
                      Sin ofertas aceptadas en el periodo.
                    } @else {
                      Media hasta aceptar una oferta: {{ r.recuperacion_turnos.promedio_minutos_para_recuperar }} min.
                    }
                  </p>
                }
              </article>

              @if (r.adherencia; as a) {
                <article class="tarjeta">
                  <p class="cifra__titulo">Registro de medicación</p>
                  <strong class="cifra numerico">
                    @if (a.porcentaje_registro_positivo === null) {
                      —
                    } @else {
                      {{ a.porcentaje_registro_positivo }}%
                    }
                  </strong>
                  <dl class="pacientes-tipo">
                    <div><dt>Tomas registradas</dt><dd class="numerico">{{ a.tomas_confirmadas }}</dd></div>
                    <div><dt>Omitidas</dt><dd class="numerico">{{ a.tomas_omitidas }}</dd></div>
                  </dl>
                  <p class="campo__ayuda">
                    @if (a.porcentaje_registro_positivo === null) {
                      Sin tomas confirmadas u omitidas en este periodo.
                    } @else {
                      Porcentaje de tomas registradas como realizadas entre las registradas.
                    }
                    {{ a.seguimientos_pendientes }}
                    {{ a.seguimientos_pendientes === 1 ? 'seguimiento pendiente actualmente' : 'seguimientos pendientes actualmente' }}.
                  </p>
                  <p class="campo__ayuda">Dato administrativo del registro, no evalúa el resultado del tratamiento.</p>
                  @if (sedeId() || servicioId()) {
                    <p class="campo__ayuda">Con filtro de sede o servicio se consideran recetas vinculadas a una cita de ese contexto.</p>
                  }
                </article>
              }

              @if (r.pagos; as pagos) {
                <article class="tarjeta">
                  <p class="cifra__titulo">Pagos de esas citas</p>
                  <ul class="pagos">
                    @for (par of pagosLegibles(pagos); track par.estado) {
                      <li>
                        <span>{{ par.estado }}</span>
                        <span class="numerico">{{ par.importe }}</span>
                      </li>
                    } @empty {
                      <li class="pagos__vacio">Sin pagos registrados para esas citas.</li>
                    }
                  </ul>
                </article>
              }
            </div>

            <div class="panel__graficos" role="group" aria-label="Distribución de citas en el periodo" [hidden]="vistaActiva() !== 'distribucion'">
              <div class="tarjeta tarjeta--llena estados panel__grafico">
                <p class="cifra__titulo">Reparto por estado</p>
                @for (estado of estadosConDatos(); track estado.codigo) {
                  <div class="estados__fila">
                    <span class="insignia" [class]="'insignia--' + estado.clase">
                      {{ estado.etiqueta }}
                    </span>
                    <span class="estados__pista" aria-hidden="true">
                      <span
                        class="estados__barra"
                        [class]="'estados__barra--' + estado.clase"
                        [style.width.%]="estado.porcentaje"
                      ></span>
                    </span>
                    <span class="numerico estados__valor">{{ estado.cantidad }}</span>
                  </div>
                }
              </div>
              <section class="tarjeta tarjeta--llena tendencia panel__grafico" aria-labelledby="tendencia-diaria">
                <h3 id="tendencia-diaria">Citas por día</h3>
                @if (r.tendencia_diaria.length === 0) {
                  <p class="campo__ayuda">Sin citas en este periodo.</p>
                } @else {
                  <ul class="tendencia__lista desplazable">
                    @for (item of r.tendencia_diaria; track item.fecha) {
                      <li>
                        <span>{{ etiquetaFecha(item.fecha) }}</span>
                        <span class="tendencia__pista" aria-hidden="true"><span [style.width.%]="(item.total / maximoTendencia(r.tendencia_diaria)) * 100"></span></span>
                        <strong class="numerico">{{ item.total }}</strong>
                      </li>
                    }
                  </ul>
                }
              </section>
              <section class="tarjeta tarjeta--llena tendencia panel__grafico" aria-labelledby="tendencia-semanal">
                <h3 id="tendencia-semanal">Citas por día de la semana</h3>
                @if (r.por_dia_semana.length === 0) {
                  <p class="campo__ayuda">Sin citas en este periodo.</p>
                } @else {
                  <ul class="tendencia__lista desplazable">
                    @for (item of r.por_dia_semana; track item.dia) {
                      <li>
                        <span>{{ etiquetaDia(item.dia) }}</span>
                        <span class="tendencia__pista" aria-hidden="true"><span [style.width.%]="(item.total / maximoTendencia(r.por_dia_semana)) * 100"></span></span>
                        <strong class="numerico">{{ item.total }}</strong>
                      </li>
                    }
                  </ul>
                }
              </section>
              <section class="tarjeta tarjeta--llena tendencia panel__grafico" aria-labelledby="tendencia-horaria">
                <h3 id="tendencia-horaria">Citas por hora local</h3>
                @if (r.por_hora.length === 0) {
                  <p class="campo__ayuda">Sin citas en este periodo.</p>
                } @else {
                  <ul class="tendencia__lista desplazable">
                    @for (item of r.por_hora; track item.hora) {
                      <li>
                        <span>{{ etiquetaHora(item.hora) }}</span>
                        <span class="tendencia__pista" aria-hidden="true"><span [style.width.%]="(item.total / maximoTendencia(r.por_hora)) * 100"></span></span>
                        <strong class="numerico">{{ item.total }}</strong>
                      </li>
                    }
                  </ul>
                }
              </section>
            </div>

            <div class="pantalla__columnas panel__pacientes" [hidden]="vistaActiva() !== 'pacientes'">
              <div class="desplazable panel__perfil" tabindex="0" role="region" aria-label="Perfil de pacientes">
                <app-perfil-pacientes [demografia]="r.demografia" />
              </div>
              <section class="tarjeta tarjeta--llena cohortes-registro" aria-labelledby="cohortes-registro-titulo">
                <h3 id="cohortes-registro-titulo">Cohortes de registro</h3>
                <p class="campo__ayuda">Altas agrupadas por mes · citas registradas dentro del periodo y los filtros actuales.</p>
                @if (r.cohortes_registro === null || r.cohortes_registro === undefined) {
                  <p class="campo__ayuda">El desglose se oculta al filtrar por estado porque una cita en otro estado no debe contarse como ausencia.</p>
                } @else if (r.cohortes_registro.length === 0) {
                  <p class="campo__ayuda">No hay altas de pacientes en este periodo.</p>
                } @else {
                  <div class="cohortes-registro__desplazamiento desplazable" role="region" aria-label="Tabla de altas mensuales" tabindex="0">
                    <table class="cohortes-registro__tabla">
                      <caption>Pacientes según su mes de registro</caption>
                      <thead>
                        <tr><th scope="col">Mes</th><th scope="col">Registrados</th><th scope="col">Con cita</th><th scope="col">Sin cita</th></tr>
                      </thead>
                      <tbody>
                        @for (cohorte of r.cohortes_registro; track cohorte.mes) {
                          <tr>
                            <th scope="row"><time [attr.datetime]="cohorte.mes">{{ etiquetaMesCohorte(cohorte.mes) }}</time></th>
                            <td class="numerico">{{ cohorte.registrados }}</td>
                            <td class="numerico">{{ cohorte.con_cita_en_filtros }}</td>
                            <td class="numerico">{{ cohorte.sin_cita_en_filtros }}</td>
                          </tr>
                        }
                      </tbody>
                    </table>
                  </div>
                }
              </section>
            </div>
          }
        </section>

        <section
          role="tabpanel"
          class="panel__vista bloque seguimiento"
          id="panel-panel-seguimiento"
          aria-labelledby="panel-pestana-seguimiento"
          [hidden]="vistaActiva() !== 'seguimiento'"
        >
          <div class="bloque__cabecera">
            <h2 id="seguimiento-inteligente"><app-icono nombre="actividad-inteligente" [tamano]="18" /> Seguimiento inteligente</h2>
            <span class="bloque__linea" aria-hidden="true"></span>
            <span class="seguimiento__metodo">Señales basadas en actividad real</span>
            <button class="boton boton--pequeno" type="button" (click)="generarResumenLocal()" [disabled]="analizandoLocal()">
              {{ analizandoLocal() ? 'Preparando…' : 'Resumen operativo' }}
            </button>
            @if (sesion.tienePermiso(PERMISOS.configuracionEscribir)) {
              <button class="boton boton--pequeno" type="button" (click)="generarAnalisisIA()" [disabled]="analizandoIA()">
                {{ analizandoIA() ? 'Analizando…' : 'Analizar con IA' }}
              </button>
            }
          </div>
          <div class="desplazable seguimiento__cuerpo" tabindex="0" role="region" aria-labelledby="seguimiento-inteligente">
            @if (errorIA()) { <p class="aviso-error" role="alert">{{ errorIA() }}</p> }
            @if (!resumenLocal().length && !analisisIA()) {
              <div class="seguimiento__vacio">
                <img
                  src="/images/seguimiento-inteligente-clinica.svg"
                  alt=""
                  aria-hidden="true"
                  width="192"
                  height="144"
                  loading="lazy"
                />
                <div>
                  <p class="ceja"><app-icono nombre="revision-operativa" [tamano]="15" /> LECTURA DEL PERIODO</p>
                  <h3>El pulso operativo de la clínica, en contexto</h3>
                  <p>Prepara un resumen con actividad real o solicita un análisis con IA para este periodo.</p>
                </div>
              </div>
            }
            @if (resumenLocal().length) {
              <article class="tarjeta analisis-ia" aria-live="polite">
                <p class="ceja"><app-icono nombre="revision-operativa" [tamano]="15" /> RESUMEN OPERATIVO LOCAL · {{ etiquetaPeriodo() }}</p>
                <ul>@for (hallazgo of resumenLocal(); track hallazgo) { <li>{{ hallazgo }}</li> }</ul>
              </article>
            }
            @if (analisisIA()) { <article class="tarjeta analisis-ia"><p class="ceja"><app-icono nombre="analisis-ia" [tamano]="15" /> ANÁLISIS GENERATIVO · {{ etiquetaPeriodo() }}</p><p>{{ analisisIA() }}</p></article> }
            <div class="seguimiento__rejilla">
              @for (senal of senalesSeguimiento(); track senal.titulo) {
                <article class="tarjeta seguimiento__senal" [class.seguimiento__senal--alerta]="senal.alerta">
                  <span class="seguimiento__pictograma" aria-hidden="true"><app-icono [nombre]="senal.icono" [tamano]="18" /></span>
                  <div><h3>{{ senal.titulo }}</h3><p>{{ senal.detalle }}</p></div>
                </article>
              }
            </div>
            <p class="seguimiento__nota">Estas señales usan reglas transparentes sobre agenda y cobros; no generan diagnósticos ni predicciones clínicas.</p>
          </div>
        </section>
      }
    </div>

    @if (filtrosAbiertos()) {
      <app-ventana-flotante
        titulo="Filtros del dashboard"
        ceja="Métricas operativas"
        forma="centrada"
        [anchoMaximo]="760"
        [cierraAlPulsarFuera]="false"
        (cerrar)="cerrarFiltros()"
      >
        <p class="campo__ayuda filtros-dashboard__ayuda">
          Los cambios se aplican al seleccionar cada opción. Las fechas usan la zona horaria de la sede elegida.
        </p>
        <div class="filtros-dashboard" aria-label="Filtros de métricas">
          <label class="campo campo--linea"><span class="campo__etiqueta">Desde</span>
            <input class="campo__control" type="date" name="dashboard-desde" [ngModel]="fechaDesde()" (ngModelChange)="cambiarFechaDesde($event)" />
          </label>
          <label class="campo campo--linea"><span class="campo__etiqueta">Hasta</span>
            <input class="campo__control" type="date" name="dashboard-hasta" [ngModel]="fechaHasta()" (ngModelChange)="cambiarFechaHasta($event)" />
          </label>
          <label class="campo campo--linea"><span class="campo__etiqueta">Sede</span>
            <select class="campo__control" name="dashboard-sede" [ngModel]="sedeId()" (ngModelChange)="cambiarSede($event)">
              <option value="">Todas las sedes</option>
              @for (sede of sedes(); track sede.id) { <option [value]="sede.id">{{ sede.nombre }}</option> }
            </select>
          </label>
          <label class="campo campo--linea"><span class="campo__etiqueta">Especialidad</span>
            <select class="campo__control" name="dashboard-especialidad" [ngModel]="especialidadId()" (ngModelChange)="cambiarEspecialidad($event)">
              <option value="">Todas las especialidades</option>
              @for (especialidad of especialidades(); track especialidad.id) { <option [value]="especialidad.id">{{ especialidad.nombre }}</option> }
            </select>
          </label>
          <label class="campo campo--linea"><span class="campo__etiqueta">Profesional</span>
            <select class="campo__control" name="dashboard-profesional" [ngModel]="profesionalId()" (ngModelChange)="profesionalId.set($event); aplicarFiltros()">
              <option value="">Todos los profesionales</option>
              @for (profesional of profesionales(); track profesional.id) { <option [value]="profesional.id">{{ profesional.nombre }} {{ profesional.apellido }}</option> }
            </select>
          </label>
          <label class="campo campo--linea"><span class="campo__etiqueta">Servicio</span>
            <select class="campo__control" name="dashboard-servicio" [ngModel]="servicioId()" (ngModelChange)="servicioId.set($event); aplicarFiltros()">
              <option value="">Todos los servicios</option>
              @for (servicio of servicios(); track servicio.id) { <option [value]="servicio.id">{{ servicio.nombre }}</option> }
            </select>
          </label>
          <label class="campo campo--linea"><span class="campo__etiqueta">Estado de cita</span>
            <select class="campo__control" name="dashboard-estado" [ngModel]="estadoCita()" (ngModelChange)="estadoCita.set($event); aplicarFiltros()">
              <option value="">Todos los estados</option>
              @for (estado of estados; track estado.codigo) { <option [value]="estado.codigo">{{ estado.etiqueta }}</option> }
            </select>
          </label>
        </div>
        @if (errorFechas()) { <p class="aviso-error" role="alert">{{ errorFechas() }}</p> }
        <div pie>
          <button class="boton" type="button" (click)="limpiarFiltros()" [disabled]="!hayFiltros()">Restablecer</button>
          <button class="boton boton--principal" type="button" (click)="cerrarFiltros()">Listo</button>
        </div>
      </app-ventana-flotante>
    }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    .cabecera-pagina {
      position: relative;
      min-height: 138px;
      padding: var(--espacio-5) var(--espacio-6);
      overflow: hidden;
      border: 1px solid var(--borde);
      border-radius: var(--radio);
      background-image:
        radial-gradient(ellipse at 85% 20%, rgb(99 128 223 / 35%), transparent 52%),
        linear-gradient(115deg, #132445, #172a52 65%, #253e73);
      background-position: center, 50% 52%;
      background-size: cover;
      isolation: isolate;
      color: #fff;
    }

    .cabecera-pagina::after {
      content: '';
      position: absolute;
      z-index: 0;
      inset: -55% 12% -55% 42%;
      pointer-events: none;
      background: radial-gradient(ellipse, rgb(129 166 255 / 20%), transparent 66%);
      opacity: .8;
      animation: panel-resplandor 14s ease-in-out infinite alternate;
    }

    .cabecera-pagina::before {
      content: '';
      position: absolute;
      z-index: 0;
      inset: 0;
      pointer-events: none;
      background: linear-gradient(112deg, transparent 36%, rgb(182 255 246 / 9%) 52%, transparent 68%);
      background-size: 220% 100%;
      animation: panel-brillo 18s ease-in-out infinite;
    }

    @keyframes panel-fondo-desplazamiento {
      from { background-position: center, 48% 52%; }
      to { background-position: center, 54% 52%; }
    }

    @keyframes panel-resplandor {
      from { transform: translate3d(-2%, 0, 0) scale(.96); opacity: .55; }
      to { transform: translate3d(2%, 1%, 0) scale(1.04); opacity: .9; }
    }

    @keyframes panel-brillo {
      0%, 18% { background-position: 100% 0; }
      72%, 100% { background-position: 0 0; }
    }

    .cabecera-pagina > div,
    .cabecera-pagina > a {
      position: relative;
      z-index: 1;
    }

    .cabecera-pagina h1 { color: #fff; }
    .cabecera-pagina .boton--principal { background:#e9efff; color:#243f8e; border-color:#f5f8ff; box-shadow:0 4px 20px rgb(0 0 0 / 12%); }
    .cabecera-pagina .boton--principal:hover { background:#fff; }

    @media (max-width: 600px) {
      .cabecera-pagina {
        min-height: 132px;
        padding: var(--espacio-4);
        background-position: center, 68% center;
      }
    }

    @media (prefers-reduced-motion: reduce) {
      .cabecera-pagina,
      .cabecera-pagina::after,
      .cabecera-pagina::before,
      .panel__ceja app-icono { animation: none; }
    }

    .panel__contexto {
      margin: 2px 0 0;
      color: #d1def5;
      font-size: 0.9rem;
    }

    .panel__ceja { display: flex; align-items: center; gap: var(--espacio-2); color: #aad8ff; }
    .panel__ceja app-icono { animation: panel-latido 5s ease-in-out infinite; }
    @keyframes panel-latido {
      0%, 100% { transform: scale(1); filter: drop-shadow(0 0 0 rgb(170 244 233 / 0%)); }
      50% { transform: scale(1.08); filter: drop-shadow(0 0 7px rgb(170 244 233 / 60%)); }
    }

    .bloque {
      margin-top: var(--espacio-5);
    }

    .seguimiento__metodo { color:var(--texto-tenue); font-size:.78rem; }
    .seguimiento__vacio {
      display:grid;
      grid-template-columns:minmax(120px, 190px) minmax(0, 1fr);
      align-items:center;
      gap:var(--espacio-4);
      margin:0 0 var(--espacio-3);
      padding:var(--espacio-3) var(--espacio-4);
      overflow:hidden;
      border:1px solid var(--borde);
      border-radius:var(--radio);
      background:
        radial-gradient(ellipse at 82% 24%, rgb(95 209 196 / 13%), transparent 42%),
        linear-gradient(115deg, rgb(238 248 245 / 86%), rgb(255 255 255 / 96%) 66%);
      background-size:190% 190%, 100% 100%;
      animation:seguimiento-fondo 26s ease-in-out infinite alternate;
    }
    .seguimiento__vacio img {
      display:block;
      width:100%;
      max-height:138px;
      object-fit:contain;
      animation:seguimiento-flotar 8s ease-in-out infinite;
    }
    .seguimiento__vacio .ceja { display:flex; align-items:center; gap:var(--espacio-1); color:var(--acento-fuerte); }
    .seguimiento__vacio h3 { margin:0; font-size:1.04rem; }
    .seguimiento__vacio p:last-child { max-width:62ch; margin:var(--espacio-1) 0 0; color:var(--texto-suave); }
    @keyframes seguimiento-flotar { 0%,100% { transform:translateY(0); } 50% { transform:translateY(-4px); } }
    @keyframes seguimiento-fondo { from { background-position:15% 0%, center; } to { background-position:85% 100%, center; } }
    .tendencias { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr)); gap:var(--espacio-3); margin-top:var(--espacio-3); }
    .tendencia h3 { margin:0 0 var(--espacio-3); font-size:.9rem; }
    .tendencia .campo__ayuda { margin:0; }
    .tendencia__lista { display:grid; gap:var(--espacio-2); list-style:none; margin:0; padding:0; }
    .tendencia__lista li { display:grid; grid-template-columns:minmax(62px,auto) minmax(48px,1fr) 2ch; align-items:center; gap:var(--espacio-2); font-size:.82rem; }
    .tendencia__pista { overflow:hidden; height:8px; border-radius:999px; background:var(--superficie-hundida); }
    .tendencia__pista span { display:block; height:100%; min-width:3px; border-radius:inherit; background:var(--acento); }
    .tendencia__lista strong { text-align:right; }
    .seguimiento .bloque__cabecera h2 app-icono { color:var(--acento); animation:pulso-red-ia 4s ease-in-out infinite; }
    @keyframes pulso-red-ia { 0%,100% { filter:drop-shadow(0 0 0 rgb(34 116 112 / 0%)); } 50% { filter:drop-shadow(0 0 5px rgb(34 116 112 / 35%)); } }
    .seguimiento__rejilla { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:var(--espacio-3); }
    .seguimiento__senal { display:flex; align-items:flex-start; gap:var(--espacio-3); padding:var(--espacio-4); }
    .seguimiento__senal h3 { margin:0; font-size:.98rem; }
    .seguimiento__senal p { margin:var(--espacio-1) 0 0; color:var(--texto-suave); font-size:.9rem; }
    .seguimiento__pictograma { display:grid; flex:0 0 34px; width:34px; height:34px; place-items:center; border-radius:11px; color:var(--acento-fuerte); background:var(--acento-suave); }
    .seguimiento__senal--alerta .seguimiento__pictograma { color:var(--aviso); background:var(--aviso-fondo); }
    .seguimiento__nota { margin:var(--espacio-2) 0 0; color:var(--texto-tenue); font-size:.8rem; }
    .analisis-ia { margin:0 0 var(--espacio-3); padding:var(--espacio-4); border-color:var(--acento); white-space:pre-line; }
    .analisis-ia p:last-child, .analisis-ia ul:last-child { margin-bottom:0; }
    @media (max-width:700px) { .seguimiento__rejilla { grid-template-columns:1fr; } }
    @media (max-width:540px) { .seguimiento__vacio { grid-template-columns:100px minmax(0,1fr); gap:var(--espacio-2); padding:var(--espacio-2); } .seguimiento__vacio h3 { font-size:.94rem; } .seguimiento__vacio p:last-child { font-size:.84rem; } }
    @media (max-width:600px) {
      .seguimiento .bloque__cabecera { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:var(--espacio-2); }
      .seguimiento .bloque__cabecera h2, .seguimiento__metodo { grid-column:1/-1; }
      .seguimiento .bloque__linea { display:none; }
      .seguimiento .bloque__cabecera .boton { width:100%; min-width:0; min-height:var(--toque-minimo); padding-inline:var(--espacio-2); white-space:normal; text-align:center; }
    }
    @media (prefers-reduced-motion: reduce) { .seguimiento__vacio, .seguimiento__vacio img, .seguimiento .bloque__cabecera h2 app-icono { animation:none; } }

    .bloque__cabecera {
      display: flex;
      align-items: center;
      gap: var(--espacio-3);
      margin-bottom: var(--espacio-3);

      h2 {
        display: flex;
        align-items: center;
        gap: var(--espacio-2);
        margin: 0;
        font-size: 0.85rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: var(--texto-suave);
      }
    }

    .bloque__linea {
      flex: 1 1 auto;
      height: 1px;
      background: var(--borde);
    }

    .bloque__cuenta {
      color: var(--texto-tenue);
      font-size: 0.85rem;
    }

    /* --- Selector de periodo --- */
    .periodos {
      display: flex;
      gap: var(--espacio-1);
      padding: 3px;
      border: 1px solid var(--borde);
      border-radius: var(--radio);
      background: var(--superficie-elevada);
    }

    .periodos__boton {
      white-space: nowrap;
      min-height: 34px;
      padding: 0 var(--espacio-3);
      border: 0;
      border-radius: var(--radio-pequeno);
      background: transparent;
      color: var(--texto-suave);
      font-weight: 600;
      font-size: 0.9rem;
      cursor: pointer;
    }

    .periodos__boton--activo {
      background: var(--acento);
      color: var(--acento-texto);
    }

    .filtros-dashboard {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(min(100%, 190px), 1fr));
      align-items: end;
      gap: var(--espacio-3);
      padding: var(--espacio-4);
      border: 1px solid var(--borde);
      border-radius: var(--radio);
      background: rgb(255 255 255 / 58%);
      -webkit-backdrop-filter: blur(14px);
      backdrop-filter: blur(14px);
    }

    .filtros-dashboard .campo { min-width: 0; margin: 0; }
    .filtros-dashboard .campo__control { min-height: 42px; }
    .filtros-dashboard__barra {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--espacio-3);
      min-height: 48px;
      padding: var(--espacio-2) var(--espacio-3);
      margin-bottom: var(--espacio-4);
      border: 1px solid rgb(255 255 255 / 72%);
      border-radius: var(--radio);
      background: linear-gradient(110deg, rgb(255 255 255 / 78%), rgb(238 248 247 / 68%));
      box-shadow: 0 8px 24px rgb(26 53 61 / 6%), inset 0 1px rgb(255 255 255 / 88%);
      -webkit-backdrop-filter: blur(18px) saturate(135%);
      backdrop-filter: blur(18px) saturate(135%);
    }
    .filtros-dashboard__estado { margin: 0; color: var(--texto-suave); font-size: .88rem; }
    .filtros-dashboard__abrir { min-height: 40px; flex: 0 0 auto; }
    .filtros-dashboard__contador {
      display: inline-grid;
      min-width: 22px;
      min-height: 22px;
      padding: 0 6px;
      place-items: center;
      border-radius: 999px;
      background: var(--acento);
      color: var(--acento-texto);
      font-size: .75rem;
      font-weight: 750;
      line-height: 1;
    }
    .filtros-dashboard__ayuda { margin: 0 0 var(--espacio-3); }

    @media (max-width: 520px) {
      .filtros-dashboard__barra { align-items: flex-start; flex-direction: column; }
      .filtros-dashboard__abrir { width: 100%; justify-content: center; }
      .filtros-dashboard { grid-template-columns: minmax(0, 1fr); }
    }

    .pacientes-tipo { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--espacio-3); margin: 0; }
    .pacientes-tipo div { display: grid; gap: var(--espacio-1); }
    .pacientes-tipo dt { color: var(--texto-suave); font-size: .85rem; }
    .pacientes-tipo dd { margin: 0; font-size: 1.6rem; font-weight: 750; }
    .cohortes-registro { margin-top: var(--espacio-3); min-width: 0; }
    .cohortes-registro__desplazamiento { max-height: 300px; overflow: auto; }
    .cohortes-registro__tabla { width: 100%; border-collapse: collapse; }
    .cohortes-registro__tabla caption { color: var(--texto-suave); text-align: left; }
    .cohortes-registro__tabla th, .cohortes-registro__tabla td { padding: var(--espacio-2); border-top: 1px solid var(--borde); }
    .cohortes-registro__tabla thead th { position: sticky; top: 0; background: var(--superficie); text-align: right; }
    .cohortes-registro__tabla th:first-child { text-align: left; }
    .cohortes-registro__tabla tbody td { text-align: right; font-variant-numeric: tabular-nums; }

    /* --- Carga por profesional --- */
    .carga {
      list-style: none;
      margin: var(--espacio-3) 0 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: var(--espacio-2);
    }

    .carga__fila {
      display: grid;
      grid-template-columns: minmax(120px, 200px) minmax(0, 1fr) 76px;
      gap: var(--espacio-3);
      align-items: center;
    }

    .carga__nombre {
      font-size: 0.92rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .carga__pista {
      height: 10px;
      border-radius: 0 999px 999px 0;
      background: var(--superficie-hundida);
      overflow: hidden;
    }

    /* Un solo tono: esto mide magnitud, no identidad. Categorías distintas
       pedirían colores distintos; aquí todas las filas son lo mismo. */
    .carga__barra {
      display: block;
      height: 10px;
      border-radius: 0 4px 4px 0;
      background: var(--acento);
    }

    /* En pantallas estrechas el nombre va arriba y la barra ocupa todo el ancho:
       con tres columnas la barra se quedaba en un punto. */
    @media (max-width: 600px) {
      .carga__fila {
        grid-template-columns: minmax(0, 1fr) auto;
        row-gap: 4px;
      }

      .carga__pista {
        grid-column: 1 / -1;
        grid-row: 2;
      }
    }

    .pagos__vacio {
      color: var(--texto-tenue);
      font-size: 0.88rem;
    }

    .carga__valor {
      text-align: right;
      font-weight: 600;
      font-size: 0.9rem;
    }

    .carga__nota,
    .carga__vacio {
      margin: 0;
    }

    .carga__demora {
      margin: var(--espacio-2) 0 0;
      color: var(--aviso);
      font-weight: 650;
    }

    .tarjeta-vidrio {
      position: relative;
      overflow: hidden;
      border: 1px solid rgb(255 255 255 / 76%);
      background:
        radial-gradient(ellipse at 92% 6%, rgb(104 214 203 / 22%), transparent 48%),
        linear-gradient(145deg, rgb(255 255 255 / 84%), rgb(232 247 244 / 72%));
      box-shadow: 0 12px 32px rgb(20 61 66 / 9%), inset 0 1px rgb(255 255 255 / 94%);
      -webkit-backdrop-filter: blur(22px) saturate(145%);
      backdrop-filter: blur(22px) saturate(145%);
    }
    .ocupacion-agenda__cabecera { display:flex; align-items:center; gap:var(--espacio-2); }
    .ocupacion-agenda__cabecera .cifra__titulo { margin-bottom:2px; }
    .ocupacion-agenda__cabecera .campo__ayuda { margin:0; }
    .ocupacion-agenda__icono { display:grid; flex:0 0 38px; width:38px; height:38px; place-items:center; border:1px solid rgb(255 255 255 / 82%); border-radius:13px; color:var(--acento-fuerte); background:rgb(255 255 255 / 62%); box-shadow:inset 0 1px rgb(255 255 255 / 90%); }
    .ocupacion-agenda__valor { display:block; margin:var(--espacio-3) 0 var(--espacio-2); color:var(--texto); font-size:2.65rem; font-weight:760; letter-spacing:-.055em; line-height:1; }
    .ocupacion-agenda__valor span { margin-left:2px; color:var(--acento-fuerte); font-size:1.35rem; }
    .ocupacion-agenda__barra { display:block; width:100%; height:9px; overflow:hidden; appearance:none; border:0; border-radius:99px; background:rgb(32 79 82 / 10%); }
    .ocupacion-agenda__barra::-webkit-progress-bar { border-radius:99px; background:rgb(32 79 82 / 10%); }
    .ocupacion-agenda__barra::-webkit-progress-value { border-radius:99px; background:linear-gradient(90deg,#52bcae,#247c79); transition:width .5s ease; }
    .ocupacion-agenda__barra::-moz-progress-bar { border-radius:99px; background:linear-gradient(90deg,#52bcae,#247c79); }
    .ocupacion-agenda__tiempos { margin:var(--espacio-2) 0 0; font-size:.83rem; font-weight:650; }
    .ocupacion-agenda__tiempos span { margin:0 4px; color:var(--texto-tenue); }
    .ocupacion-agenda__detalle { margin:var(--espacio-2) 0 0; }

    /* --- Cifras --- */
    .cifra {
      display: block;
      font-size: 2.1rem;
      font-weight: 650;
      letter-spacing: -0.02em;
      line-height: 1.1;
    }

    .cifra__titulo,
    .inasistencia__titulo {
      margin: 0 0 var(--espacio-1);
      font-size: 0.85rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--texto-suave);
    }

    .inasistencia__valor {
      display: flex;
      align-items: center;
      gap: var(--espacio-3);
      margin: 0;

      strong {
        font-size: 2.1rem;
        font-weight: 650;
        letter-spacing: -0.02em;
      }
    }

    .inasistencia__lectura {
      margin: var(--espacio-2) 0 0;
      color: var(--texto-suave);
      font-size: 0.88rem;
    }

    .insignia {
      display: inline-block;
      padding: 2px var(--espacio-2);
      border-radius: 999px;
      border: 1px solid currentcolor;
      font-size: 0.8rem;
      font-weight: 650;
      white-space: nowrap;
    }

    .insignia--exito {
      color: var(--exito);
      background: var(--exito-fondo);
    }
    .insignia--aviso {
      color: var(--aviso);
      background: var(--aviso-fondo);
    }
    .insignia--peligro {
      color: var(--peligro);
      background: var(--peligro-fondo);
    }
    .insignia--info {
      color: var(--info);
      background: var(--info-fondo);
    }
    .insignia--neutra {
      color: var(--texto-suave);
      background: var(--superficie-hundida);
    }

    .pagos {
      list-style: none;
      margin: 0;
      padding: 0;

      li {
        display: flex;
        justify-content: space-between;
        gap: var(--espacio-3);
        padding: var(--espacio-1) 0;
        border-bottom: 1px solid var(--superficie-hundida);
        font-size: 0.92rem;
      }
    }

    /* --- Reparto por estado --- */
    .estados {
      margin-top: var(--espacio-4);
    }

    .estados__fila {
      display: grid;
      grid-template-columns: 140px minmax(0, 1fr) 48px;
      gap: var(--espacio-3);
      align-items: center;
      padding: var(--espacio-1) 0;
    }

    .estados__pista {
      height: 8px;
      border-radius: 0 999px 999px 0;
      background: var(--superficie-hundida);
      overflow: hidden;
    }

    .estados__barra {
      display: block;
      height: 8px;
      border-radius: 0 4px 4px 0;
      background: var(--texto-tenue);
    }

    .estados__barra--exito {
      background: var(--exito);
    }
    .estados__barra--aviso {
      background: var(--aviso);
    }
    .estados__barra--peligro {
      background: var(--peligro);
    }
    .estados__barra--info {
      background: var(--info);
    }

    .estados__valor {
      text-align: right;
      font-weight: 600;
      font-size: 0.9rem;
    }

    /* --- Vistas en pestañas ---
       Las clases de reparto fijan display; sin !important el atributo hidden
       perdería contra ellas y se verían dos vistas a la vez. */
    .panel__vista[hidden],
    .panel__vista [hidden] { display: none !important; }

    .panel__vista > .bloque,
    .panel__vista.bloque,
    .panel__vista .estados { margin-top: 0; }

    .panel__vista > .bloque + .bloque { margin-top: var(--espacio-4); }

    .cifras__mandos {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--espacio-3);
      margin-bottom: var(--espacio-3);
    }

    .cifras__mandos .filtros-dashboard__barra {
      flex: 1 1 320px;
      min-height: 44px;
      margin-bottom: 0;
      padding-block: var(--espacio-1);
    }

    /* Tarjetas de cifras más densas: caben dos filas en 768 px de alto. */
    .cifras__rejilla {
      gap: var(--espacio-3);
      grid-template-columns: repeat(auto-fill, minmax(min(100%, 180px), 1fr));
    }

    .cifras__rejilla > .tarjeta { padding: var(--espacio-3); }
    .cifras__rejilla .cifra__titulo,
    .cifras__rejilla .inasistencia__titulo { font-size: .76rem; }
    .cifras__rejilla .cifra,
    .cifras__rejilla .inasistencia__valor strong { font-size: 1.6rem; }
    .cifras__rejilla .pacientes-tipo { gap: var(--espacio-2); }
    .cifras__rejilla .pacientes-tipo dt { font-size: .78rem; }
    .cifras__rejilla .pacientes-tipo dd { font-size: 1.3rem; }
    .cifras__rejilla .ocupacion-agenda__icono { display: none; }
    .cifras__rejilla .ocupacion-agenda__valor { margin: var(--espacio-2) 0; font-size: 2rem; }
    .cifras__rejilla .campo__ayuda,
    .cifras__rejilla .inasistencia__lectura,
    .cifras__rejilla .ocupacion-agenda__tiempos { font-size: .78rem; line-height: 1.35; }
    .cifras__rejilla .campo__ayuda { margin-block: var(--espacio-1) 0; }

    .panel__graficos {
      display: grid;
      gap: var(--espacio-3);
      grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr));
    }

    /* Una barra que no cabe se recorta dentro de su pista: nunca pisa la
       etiqueta ni la cifra de al lado. */
    .panel__grafico { min-width: 0; }
    .estados__fila { grid-template-columns: auto minmax(32px, 1fr) 4ch; }
    .tendencia__lista li { grid-template-columns: minmax(0, 72px) minmax(40px, 1fr) 4ch; }
    .tendencia__lista li > span:first-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

    .panel__hoy { --pantalla-columnas: minmax(0, 1.25fr) minmax(0, 1fr); }
    .panel__pacientes { --pantalla-columnas: minmax(0, 1.5fr) minmax(0, 1fr); }

    @media (min-width: 821px) and (min-height: 600px) {
      .cabecera-pagina {
        min-height: 0;
        padding: var(--espacio-2) var(--espacio-5);
      }

      .cabecera-pagina .ceja { margin-bottom: 2px; font-size: .72rem; }
      .panel__contexto { margin: 0; font-size: .8rem; }

      .panel__vista:not(.pantalla__columnas) {
        display: flex;
        flex: 1 1 0;
        flex-direction: column;
        min-height: 0;
      }

      .panel__vista.desplazable { display: block; }

      .panel__hoy > .bloque > .desplazable,
      .panel__hoy .tarjeta--llena > .desplazable { flex: 1 1 0; }

      /* El alto sobrante se reparte entre las filas de tarjetas; si no
         alcanza, la rejilla desplaza y cada tarjeta conserva un alto legible. */
      .cifras__rejilla,
      .panel__graficos {
        flex: 1 1 0;
        min-height: 0;
        overflow: auto;
        overscroll-behavior: contain;
        scrollbar-width: thin;
        align-content: stretch;
      }

      .cifras__rejilla { grid-auto-rows: minmax(150px, 1fr); }
      .panel__graficos { grid-auto-rows: minmax(220px, 1fr); }

      .cifras__rejilla > .tarjeta,
      .panel__grafico {
        min-height: 0;
        overflow: auto;
        scrollbar-width: thin;
      }

      /* Con menos de cinco columnas no caben dos filas: la tarjeta muestra
         todo lo suyo y solo desplaza la rejilla, nunca las dos cosas. */
      @media (max-width: 1180px) {
        .cifras__rejilla { grid-auto-rows: minmax(min-content, 1fr); }
        .cifras__rejilla > .tarjeta { overflow: visible; }
      }

      .tendencia__lista { align-content: start; }

      .panel__pacientes { flex: 1 1 0; }
      .cohortes-registro { margin-top: 0; }
      .cohortes-registro__desplazamiento { max-height: none; }

      .seguimiento > .bloque__cabecera { flex: none; }
      .seguimiento__vacio img { max-height: 110px; }
    }
  `,
})
export class PanelComponent {
  private readonly operaciones = inject(OperacionesService);
  private readonly api = inject(ApiService);
  private readonly catalogo = inject(CatalogoService);
  protected readonly sesion = inject(SesionService);
  protected readonly PERMISOS = PERMISOS;

  protected readonly opciones = [
    { clave: 'hoy', etiqueta: 'Hoy' },
    { clave: '7', etiqueta: '7 días' },
    { clave: '30', etiqueta: '30 días' },
  ] as const;
  protected readonly estados = ESTADOS;

  protected readonly periodo = signal<string>('hoy');
  protected readonly sedeId = signal('');
  protected readonly sedes = signal<readonly Sede[]>([]);
  private readonly zonaClinica = signal('America/Guayaquil');
  protected readonly zona = computed(() =>
    this.sedes().find((sede) => sede.id === this.sedeId())?.zona_horaria ?? this.zonaClinica(),
  );
  protected readonly fechaDesde = signal(hoyEnZona('America/Guayaquil'));
  protected readonly fechaHasta = signal(hoyEnZona('America/Guayaquil'));
  protected readonly especialidadId = signal('');
  protected readonly profesionalId = signal('');
  protected readonly servicioId = signal('');
  protected readonly estadoCita = signal('');

  protected readonly resumen = signal<ResumenPanel | null>(null);
  /** El mismo resumen del periodo anterior, solo para la variación. */
  protected readonly anterior = signal<ResumenPanel | null>(null);
  protected readonly citasHoy = signal<readonly Cita[]>([]);
  protected readonly ofertasSinAvisar = signal<readonly EntradaEspera[]>([]);
  protected readonly especialidades = signal<readonly Especialidad[]>([]);
  protected readonly servicios = signal<readonly Servicio[]>([]);
  protected readonly profesionales = signal<readonly Profesional[]>([]);
  protected readonly filtrosAbiertos = signal(false);
  protected readonly cantidadFiltrosActivos = computed(() => [
    this.periodo() !== 'hoy',
    Boolean(this.sedeId()),
    Boolean(this.especialidadId()),
    Boolean(this.profesionalId()),
    Boolean(this.servicioId()),
    Boolean(this.estadoCita()),
  ].filter(Boolean).length);
  protected readonly hayFiltros = computed(() => this.cantidadFiltrosActivos() > 0);
  protected readonly errorFechas = computed(() => {
    const inicio = this.fechaDesde();
    const fin = this.fechaHasta();
    const esFecha = (valor: string) => {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(valor)) return false;
      const instante = Date.parse(`${valor}T00:00:00Z`);
      return Number.isFinite(instante) && new Date(instante).toISOString().slice(0, 10) === valor;
    };
    if (!esFecha(inicio) || !esFecha(fin)) return 'Indica una fecha de inicio y una fecha de fin válidas.';
    if (inicio > fin) return 'La fecha de inicio debe ser anterior o igual a la fecha de fin.';
    const desde = Date.parse(rangoDelDia(inicio, this.zona()).desde);
    const hasta = Date.parse(rangoDelDia(fin, this.zona()).hasta);
    if (hasta - desde > 366 * 24 * 60 * 60 * 1000) return 'El periodo no puede superar 366 días.';
    return '';
  });

  protected readonly cargandoResumen = signal(false);
  protected readonly cargandoHoy = signal(false);
  protected readonly error = signal('');
  protected readonly analisisIA = signal('');
  protected readonly resumenLocal = signal<readonly string[]>([]);
  protected readonly errorIA = signal('');
  protected readonly analizandoIA = signal(false);
  protected readonly analizandoLocal = signal(false);

  protected readonly hoyLegible = computed(() =>
    new Intl.DateTimeFormat('es-EC', {
      timeZone: this.zona(),
      weekday: 'long',
      day: 'numeric',
      month: 'long',
    }).format(new Date()),
  );

  protected readonly pendientes = computed<readonly TareaPendiente[]>(() =>
    derivarPendientes({
      citas: this.citasHoy(),
      ofertasSinAvisar: this.ofertasSinAvisar(),
      ahora: new Date(),
      nombrePaciente: (id) => `Paciente ${id.slice(0, 8)}`,
    }),
  );

  /** Carga de hoy, de más ocupado a menos. */
  protected readonly carga = computed(() => {
    const minutos = cargaPorProfesional(this.citasHoy());
    const mayor = Math.max(1, ...minutos.values());
    return [...minutos.entries()]
      .map(([id, valor]) => ({
        id,
        nombre: this.nombreProfesional(id),
        minutos: valor,
        legible: duracionLegible(valor),
        porcentaje: Math.round((valor / mayor) * 100),
      }))
      .sort((a, b) => b.minutos - a.minutos);
  });

  /**
   * Inasistencia del periodo, con su variación en puntos.
   *
   * Un 8 % no dice nada sin saber si sube o baja; la variación exige el
   * periodo anterior, así que se piden los dos.
   */
  protected readonly inasistencia = computed(() => {
    const actual = this.resumen();
    if (this.estadoCita()) {
      return { valor: '—', delta: null as string | null, sube: false, lectura: 'La tasa no se calcula mientras se filtra por un único estado.' };
    }

    if (!actual || actual.total_citas === 0) {
      return { valor: '—', delta: null as string | null, sube: false, lectura: 'Sin citas en el periodo.' };
    }
    const tasa = ((actual.citas['NO_SHOW'] ?? 0) / actual.total_citas) * 100;
    const previo = this.anterior();
    if (!previo || previo.total_citas === 0) {
      return {
        valor: `${tasa.toFixed(1)} %`,
        delta: null,
        sube: false,
        lectura: 'Sin datos del periodo anterior para comparar.',
      };
    }
    const tasaPrevia = ((previo.citas['NO_SHOW'] ?? 0) / previo.total_citas) * 100;
    const diferencia = tasa - tasaPrevia;
    const sube = diferencia > 0;
    return {
      valor: `${tasa.toFixed(1)} %`,
      delta: Math.abs(diferencia).toFixed(1),
      sube,
      lectura: sube
        ? 'Sube respecto al periodo anterior. Las citas sin confirmar son el primer sitio donde mirar.'
        : 'Baja respecto al periodo anterior.',
    };
  });

  protected maximoTendencia(items: readonly { total: number }[]): number {
    return Math.max(1, ...items.map((item) => item.total));
  }

  protected formatearDuracion(minutos: number): string {
    return duracionLegible(minutos);
  }

  protected etiquetaDia(dia: number): string {
    return ['', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'][dia] ?? '—';
  }

  /** La API devuelve una fecha de calendario local, no un instante UTC. */
  protected etiquetaFecha(fecha: string): string {
    const mediodiaUtc = new Date(`${fecha}T12:00:00Z`);
    if (Number.isNaN(mediodiaUtc.getTime())) {
      return fecha;
    }
    return new Intl.DateTimeFormat('es-EC', {
      weekday: 'short',
      day: 'numeric',
      timeZone: 'UTC',
    }).format(mediodiaUtc);
  }

  protected etiquetaMesCohorte(mes: string): string {
    const inicioUtc = new Date(`${mes}T12:00:00Z`);
    if (Number.isNaN(inicioUtc.getTime())) {
      return mes;
    }
    return new Intl.DateTimeFormat('es-EC', {
      month: 'long',
      year: 'numeric',
      timeZone: 'UTC',
    }).format(inicioUtc);
  }

  protected etiquetaHora(hora: number): string {
    return `${String(hora).padStart(2, '0')}:00`;
  }

  /** Estados con al menos una cita, escalados contra el mayor. */
  protected readonly estadosConDatos = computed(() => {
    const datos = this.resumen();
    if (!datos) {
      return [];
    }
    const presentes = ESTADOS.map((estado) => ({
      ...estado,
      cantidad: datos.citas[estado.codigo] ?? 0,
    })).filter((estado) => estado.cantidad > 0);
    const mayor = Math.max(1, ...presentes.map((estado) => estado.cantidad));
    return presentes.map((estado) => ({
      ...estado,
      porcentaje: Math.round((estado.cantidad / mayor) * 100),
    }));
  });

  protected readonly senalesSeguimiento = computed(() => {
    const resumen = this.resumen();
    const abiertas = this.pendientes().length;
    const inasistencia = resumen?.total_citas && !this.estadoCita()
      ? ((resumen.citas['NO_SHOW'] ?? 0) / resumen.total_citas) * 100
      : null;
    const senales: { titulo: string; detalle: string; alerta: boolean; icono: NombreIcono }[] = [];
    senales.push(abiertas > 0
      ? { titulo: `${abiertas} tarea(s) requieren seguimiento`, detalle: 'Hay citas por confirmar, turnos que vencen u ofertas de espera sin comunicar en la jornada.', alerta: true, icono: 'agenda' }
      : { titulo: 'La cola de hoy está al día', detalle: 'No hay tareas operativas urgentes en la agenda consultada.', alerta: false, icono: 'calendario-check' });
    if (inasistencia !== null) {
      senales.push(inasistencia >= 10
        ? { titulo: 'Inasistencia sobre 10 %', detalle: `La tasa del periodo es ${inasistencia.toFixed(1)} %. Revise confirmaciones y los periodos comparables.`, alerta: true, icono: 'pulso' }
        : { titulo: 'Inasistencia bajo control', detalle: `La tasa del periodo es ${inasistencia.toFixed(1)} % sobre ${resumen!.total_citas} citas.`, alerta: false, icono: 'pulso' });
    } else if (!this.estadoCita()) {
      senales.push({ titulo: 'Aún no hay base para comparar', detalle: 'El periodo no contiene citas para calcular indicadores de asistencia.', alerta: false, icono: 'metricas' });
    }
    const esperando = resumen?.espera;
    if (esperando && esperando.personas_en_espera > 0) {
      senales.push({
        titulo: `${esperando.personas_en_espera} paciente(s) en sala de espera`,
        detalle: esperando.espera_mayor_15_minutos > 0
          ? `${esperando.espera_mayor_15_minutos} superan 15 minutos; revise la atención pendiente.`
          : 'La espera registrada todavía no supera 15 minutos.',
        alerta: esperando.espera_mayor_15_minutos > 0,
        icono: 'sala-clinica',
      });
    }
    const pendientesPago = Object.entries(resumen?.pagos ?? {}).find(([estado]) => ['PENDING', 'UNDER_REVIEW', 'PROOF_RECEIVED'].includes(estado));
    if (pendientesPago) {
      senales.push({ titulo: 'Cobros en seguimiento', detalle: `El estado ${pendientesPago[0]} suma ${pendientesPago[1]}.`, alerta: true, icono: 'pagos' });
    }
    return senales;
  });

  private readonly indicadoresServicio = inject(IndicadoresService);
  private readonly indicadores = signal<Indicadores | null>(null);

  /** Grupos del tablero en el orden en que se atienden: lo mío, la clínica hoy, lo pendiente y la gestión. */
  protected readonly tablero = computed(() => {
    const datos = this.indicadores();
    const grupos = [
      { titulo: 'Mi día', tarjetas: indicadoresDe(datos, 'mi_dia') },
      { titulo: 'La clínica hoy', tarjetas: indicadoresDe(datos, 'agenda') },
      {
        titulo: 'Pendiente de atender',
        tarjetas: [
          ...indicadoresDe(datos, 'clinico'),
          ...indicadoresDe(datos, 'mensajes'),
          ...indicadoresDe(datos, 'lista_espera'),
          ...indicadoresDe(datos, 'pagos'),
        ],
      },
      {
        titulo: 'Gestión de la clínica',
        tarjetas: [
          ...indicadoresDe(datos, 'pacientes'),
          ...indicadoresDe(datos, 'conocimiento'),
          ...indicadoresDe(datos, 'promociones'),
          ...indicadoresDe(datos, 'usuarios'),
        ],
      },
    ];
    return grupos.filter((grupo) => grupo.tarjetas.length > 0);
  });

  /**
   * Vistas del panel, solo las que el rol alcanza. El tablero sale si el
   * backend envió algún grupo; lo demás depende de los permisos de agenda y
   * de métricas, igual que antes de repartirlo en pestañas.
   */
  protected readonly vistas = computed<readonly OpcionPestana[]>(() => {
    const lista: OpcionPestana[] = [];
    if (this.tablero().length) lista.push({ clave: 'resumen', etiqueta: 'Resumen', icono: 'metricas' });
    if (this.sesion.tienePermiso(PERMISOS.agendaLeer)) {
      lista.push({ clave: 'hoy', etiqueta: 'Hoy', icono: 'calendario-check', cuenta: this.pendientes().length });
    }
    if (this.sesion.tienePermiso(PERMISOS.metricasLeer)) {
      lista.push(
        { clave: 'cifras', etiqueta: 'Cifras del periodo' },
        { clave: 'distribucion', etiqueta: 'Distribución' },
        { clave: 'pacientes', etiqueta: 'Pacientes' },
        { clave: 'seguimiento', etiqueta: 'Seguimiento', icono: 'actividad-inteligente' },
      );
    }
    return lista;
  });

  /** La vista elegida; vacía hasta que se elige una pestaña. */
  protected readonly vista = signal('');

  /** La vista que se muestra: la elegida si el rol la alcanza, o la primera. */
  protected readonly vistaActiva = computed(() => {
    const claves = this.vistas().map((opcion) => opcion.clave);
    return claves.includes(this.vista()) ? this.vista() : (claves[0] ?? '');
  });

  protected readonly esVistaDeCifras = computed(() =>
    ['cifras', 'distribucion', 'pacientes'].includes(this.vistaActiva()),
  );

  /** La vista de cifras que nombra el panel compartido, aunque esté oculto. */
  protected readonly vistaCifras = computed(() => (this.esVistaDeCifras() ? this.vistaActiva() : 'cifras'));

  constructor() {
    this.indicadoresServicio.refrescar();
    this.indicadoresServicio.obtener().subscribe({
      next: (datos) => this.indicadores.set(datos),
      error: () => this.indicadores.set(null),
    });
    this.catalogo.clinica().subscribe({
      next: (clinica) => {
        const anterior = this.zona();
        this.zonaClinica.set(clinica.zona_horaria);
        if (anterior !== this.zona() && this.periodo() !== 'personalizado') this.cambiarPeriodo(this.periodo());
      },
      error: () => undefined,
    });
    this.catalogo.sedes().subscribe({ next: (lista) => this.sedes.set(lista), error: () => this.sedes.set([]) });
    this.catalogo.especialidades().subscribe({ next: (lista) => this.especialidades.set(lista), error: () => this.especialidades.set([]) });
    this.cargarServicios();
    this.cargarProfesionales();
    this.cargar();
  }

  protected abrirFiltros(): void {
    this.filtrosAbiertos.set(true);
  }

  protected cerrarFiltros(): void {
    this.filtrosAbiertos.set(false);
  }

  protected cambiarPeriodo(clave: string): void {
    this.periodo.set(clave);
    const fin = hoyEnZona(this.zona());
    const dias = DIAS_POR_PERIODO[clave] ?? 1;
    this.fechaHasta.set(fin);
    this.fechaDesde.set(sumarDias(fin, -(dias - 1)));
    this.analisisIA.set('');
    this.resumenLocal.set([]);
    this.cargarResumen();
  }

  protected cambiarSede(id: string): void {
    this.sedeId.set(id);
    this.profesionalId.set('');
    if (this.periodo() !== 'personalizado') {
      const fin = hoyEnZona(this.zona());
      const dias = DIAS_POR_PERIODO[this.periodo()] ?? 1;
      this.fechaHasta.set(fin);
      this.fechaDesde.set(sumarDias(fin, -(dias - 1)));
    }
    this.cargarProfesionales();
    this.aplicarFiltros();
  }

  protected cambiarEspecialidad(id: string): void {
    this.especialidadId.set(id);
    this.servicioId.set('');
    this.profesionalId.set('');
    this.cargarServicios();
    this.cargarProfesionales();
    this.aplicarFiltros();
  }

  protected limpiarFiltros(): void {
    this.periodo.set('hoy');
    this.sedeId.set('');
    const hoy = hoyEnZona(this.zona());
    this.fechaDesde.set(hoy);
    this.fechaHasta.set(hoy);
    this.especialidadId.set('');
    this.profesionalId.set('');
    this.servicioId.set('');
    this.estadoCita.set('');
    this.cargarServicios();
    this.cargarProfesionales();
    this.aplicarFiltros();
    this.cerrarFiltros();
  }

  protected aplicarFiltros(): void {
    this.analisisIA.set('');
    this.resumenLocal.set([]);
    if (this.errorFechas()) {
      this.resumen.set(null);
      this.anterior.set(null);
      this.cargandoResumen.set(false);
      return;
    }
    this.cargarResumen();
  }

  protected cambiarFechaDesde(fecha: string): void {
    this.fechaDesde.set(fecha);
    this.periodo.set('personalizado');
    this.aplicarFiltros();
  }

  protected cambiarFechaHasta(fecha: string): void {
    this.fechaHasta.set(fecha);
    this.periodo.set('personalizado');
    this.aplicarFiltros();
  }

  protected etiquetaPeriodo(): string {
    if (this.periodo() === 'hoy') return 'HOY';
    if (this.periodo() !== 'personalizado') return `${this.periodo()} DÍAS`;
    const formato = (fecha: string) => {
      const instante = Date.parse(`${fecha}T12:00:00Z`);
      if (!Number.isFinite(instante) || new Date(instante).toISOString().slice(0, 10) !== fecha) return '—';
      return new Intl.DateTimeFormat('es-EC', {
        timeZone: 'UTC', day: '2-digit', month: 'short', year: 'numeric',
      }).format(new Date(instante));
    };
    return `${formato(this.fechaDesde())} – ${formato(this.fechaHasta())}`;
  }

  private cargarServicios(): void {
    this.catalogo.servicios(this.especialidadId() || undefined).subscribe({
      next: (lista) => this.servicios.set(lista),
      error: () => this.servicios.set([]),
    });
  }

  private cargarProfesionales(): void {
    this.catalogo.profesionales({
      especialidadId: this.especialidadId() || undefined,
      sedeId: this.sedeId() || undefined,
    }).subscribe({
      next: (lista) => this.profesionales.set(lista),
      error: () => this.profesionales.set([]),
    });
  }

  private parametrosFiltros(): Record<string, string> {
    const parametros: Record<string, string> = {};
    if (this.sedeId()) parametros['sede_id'] = this.sedeId();
    if (this.especialidadId()) parametros['especialidad_id'] = this.especialidadId();
    if (this.profesionalId()) parametros['profesional_id'] = this.profesionalId();
    if (this.servicioId()) parametros['servicio_id'] = this.servicioId();
    if (this.estadoCita()) parametros['estado'] = this.estadoCita();
    return parametros;
  }

  protected generarResumenLocal(): void {
    const parametros = this.rangoAnalisis();
    this.analizandoLocal.set(true);
    this.errorIA.set('');
    this.resumenLocal.set([]);
    this.operaciones.analizar<{ hallazgos: string[] }>('/dashboard/analisis-local', parametros).subscribe({
      next: (resultado) => { this.resumenLocal.set(resultado.hallazgos); this.analizandoLocal.set(false); },
      error: (fallo: unknown) => {
        this.errorIA.set(fallo instanceof FalloApi ? fallo.message : 'No se pudo preparar el resumen operativo.');
        this.analizandoLocal.set(false);
      },
    });
  }

  protected generarAnalisisIA(): void {
    const parametros = this.rangoAnalisis();
    this.analizandoIA.set(true);
    this.errorIA.set('');
    this.analisisIA.set('');
    this.operaciones.analizar<{ analisis: string }>('/dashboard/analisis-ia', parametros).subscribe({
      next: (resultado) => { this.analisisIA.set(resultado.analisis); this.analizandoIA.set(false); },
      error: (fallo: unknown) => { this.errorIA.set(fallo instanceof FalloApi ? fallo.message : 'No se pudo generar el análisis.'); this.analizandoIA.set(false); },
    });
  }

  private rangoAnalisis(): Record<string, string> {
    return {
      desde: rangoDelDia(this.fechaDesde(), this.zona()).desde,
      hasta: rangoDelDia(this.fechaHasta(), this.zona()).hasta,
      ...this.parametrosFiltros(),
    };
  }

  protected irALaAgenda(): void {
    // Las acciones sobre una cita viven en la agenda, que es donde se ve el
    // contexto del día. Este panel señala; no ejecuta.
    window.location.href = '/agenda';
  }

  private cargar(): void {
    this.cargarResumen();
    this.cargarHoy();
  }

  private cargarResumen(): void {
    if (!this.sesion.tienePermiso(PERMISOS.metricasLeer)) {
      return;
    }
    this.cargandoResumen.set(true);
    this.error.set('');

    const inicio = this.fechaDesde();
    const fin = this.fechaHasta();
    const dias = Math.round((Date.parse(`${fin}T00:00:00Z`) - Date.parse(`${inicio}T00:00:00Z`)) / (24 * 60 * 60 * 1000)) + 1;
    const previoFin = sumarDias(inicio, -1);
    const previoInicio = sumarDias(previoFin, -(dias - 1));

    const actual = rangoDelDia(inicio, this.zona());
    const finActual = rangoDelDia(fin, this.zona());
    const previo = rangoDelDia(previoInicio, this.zona());
    const finPrevio = rangoDelDia(previoFin, this.zona());

    this.operaciones
      .leer<ResumenPanel>('/dashboard/', {
        desde: actual.desde,
        hasta: finActual.hasta,
        ...this.parametrosFiltros(),
      })
      .subscribe({
        next: (datos) => {
          this.resumen.set(datos);
          this.cargandoResumen.set(false);
        },
        error: (fallo: FalloApi) => {
          this.error.set(fallo.message);
          this.resumen.set(null);
          this.anterior.set(null);
          this.cargandoResumen.set(false);
        },
      });

    this.operaciones
      .leer<ResumenPanel>('/dashboard/', {
        desde: previo.desde,
        hasta: finPrevio.hasta,
        ...this.parametrosFiltros(),
      })
      .subscribe({
        // Sin el periodo anterior la pantalla sigue sirviendo: se muestra la
        // tasa sin variación en lugar de un error.
        next: (datos) => this.anterior.set(datos),
        error: () => this.anterior.set(null),
      });
  }

  private cargarHoy(): void {
    if (!this.sesion.tienePermiso(PERMISOS.agendaLeer)) {
      return;
    }
    this.cargandoHoy.set(true);
    const { desde, hasta } = rangoDelDia(hoyEnZona(this.zona()), this.zona());

    this.api.citas({ desde, hasta, limite: 200 }).subscribe({
      next: (pagina) => {
        this.citasHoy.set(pagina.elementos);
        this.cargandoHoy.set(false);
      },
      error: () => this.cargandoHoy.set(false),
    });

    if (this.sesion.tienePermiso(PERMISOS.listaEsperaGestionar)) {
      this.operaciones
        .leer<Pagina<EntradaEspera>>('/lista-espera/', { limite: 25, solo_sin_avisar: true })
        .subscribe({
          next: (pagina) => this.ofertasSinAvisar.set(pagina.elementos),
          error: () => this.ofertasSinAvisar.set([]),
        });
    }
  }

  protected nombreProfesional(id: string): string {
    const profesional = this.profesionales().find((p) => p.id === id);
    return profesional ? `${profesional.nombre} ${profesional.apellido}` : `Profesional ${id.slice(0, 8)}`;
  }

  protected pagosLegibles(pagos: Record<string, string>): { estado: string; importe: string }[] {
    const nombres: Record<string, string> = {
      PENDING: 'Pendiente',
      PROOF_RECEIVED: 'Comprobante recibido',
      UNDER_REVIEW: 'En revisión',
      CONFIRMED: 'Confirmado',
      REJECTED: 'Rechazado',
      REFUND_PENDING: 'Devolución pendiente',
    };
    return Object.entries(pagos).map(([estado, importe]) => ({
      estado: nombres[estado] ?? estado,
      importe: Number.isFinite(Number(importe)) ? `$${Number(importe).toFixed(2)}` : importe,
    }));
  }
}
