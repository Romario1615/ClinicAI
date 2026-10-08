/**
 * Ficha del paciente: todo lo que el rol puede ver, en una sola ventana.
 *
 * Por qué una ventana y no una pantalla
 * -------------------------------------
 * Antes, saber quién es el paciente de las 10:30 exigía salir de la agenda,
 * buscarlo en la pantalla de pacientes y volver. Con un paciente delante y el
 * teléfono sonando, eso significa que no se consulta: se atiende a ciegas.
 * La ficha se abre encima, no navega, y al cerrarla la pantalla de detrás
 * sigue donde estaba.
 *
 * Qué muestra
 * -----------
 * A la izquierda, siempre: foto (con «Subir foto» / «Tomar foto» si el rol
 * puede editar la ficha), documento, edad, nivel de verificación y contacto
 * rápido. A la derecha, pestañas: resumen, citas y contacto para todos; y las
 * clínicas —historia y recetas, odontograma, plan de tratamiento e imágenes—
 * **solo** si el rol tiene el permiso que el backend exige para cada una. El
 * backend vuelve a comprobarlo todo: ocultar una pestaña aquí es comodidad,
 * no seguridad.
 *
 * Si el rol no alcanza nada clínico, la ficha lo **dice** en lugar de dejar
 * que parezca que esos datos no existen.
 *
 * Lo clínico se pide al abrir su pestaña, no al abrir la ficha: cada lectura
 * queda auditada y no debe registrarse una consulta que nadie hizo.
 *
 * Sobre el número de documento
 * ----------------------------
 * Se muestra completo. La minimización de ADR‑0020 se aplica al menú que el
 * agente ofrece por WhatsApp a quien tenga el teléfono en la mano, no aquí:
 * esta ficha la abre personal con permiso, y comprobar el documento en el
 * mostrador es precisamente cómo se verifica una identidad.
 */
import { Component, computed, inject, input, type OnInit, output, signal, viewChild, ElementRef, ChangeDetectionStrategy } from '@angular/core';
import { Router } from '@angular/router';

import {
  ApiService,
  FalloApi,
  type Nota,
  type PacienteDetalle,
  type Receta,
} from '../nucleo/servicios/api.service';
import { PERMISOS } from '../nucleo/servicios/configuracion';
import { SesionService } from '../nucleo/servicios/sesion.service';
import {
  EspecialidadHistoriaService,
  type ModuloHistoria,
} from '../nucleo/servicios/especialidad-historia.service';
import { SelectorEspecialidadComponent } from './selector-especialidad.component';
import { RecorridoPacienteComponent } from './recorrido-paciente.component';
import { OdontogramaComponent } from '../paginas/historia-clinica/odontograma.component';
import { PlanesTratamientoComponent } from '../paginas/historia-clinica/planes-tratamiento.component';
import { ResumenClinicoComponent } from '../paginas/historia-clinica/resumen-clinico.component';
import { ConsentimientosPacienteComponent } from './consentimientos-paciente.component';
import { FotoPerfilComponent } from './foto-perfil.component';
import { GaleriaImagenesComponent } from './galeria-imagenes.component';
import { InsigniaEstadoComponent } from './insignia-estado.component';
import type { Cita } from '../nucleo/modelos/dominio';
import { formatearFecha, formatearFechaHora } from '../nucleo/utilidades/fechas';
import { IconoComponent } from './icono.component';
import { TipoDocumentoPipe } from './tipo-documento.pipe';
import { MENSAJE_SIN_ACCESO_CLINICO, mensajeFalloClinico } from '../nucleo/utilidades/acceso-clinico';
import { OperacionesService } from '../nucleo/servicios/operaciones.service';
import { AtencionPacienteComponent } from './atencion-paciente.component';
import { EditorPacienteComponent } from '../paginas/pacientes/editor-paciente.component';
import { PeriodontogramaComponent } from '../paginas/historia-clinica/periodontograma.component';
import { VentanaFlotanteComponent } from './ventana-flotante.component';
import { AgentePacienteComponent } from './agente-paciente.component';

/** Traducción del nivel de verificación, con lo que implica para quien atiende. */
const VERIFICACION: Record<string, { etiqueta: string; consecuencia: string; alerta: boolean }> = {
  NO_VERIFICADO: {
    etiqueta: 'Sin verificar',
    consecuencia:
      'No dé información ni ejecute cambios por teléfono sin comprobar identidad en el mostrador.',
    alerta: true,
  },
  TELEFONO: {
    etiqueta: 'Teléfono verificado',
    consecuencia:
      'Basta para confirmar una cita. No basta para cancelar ni reprogramar sin comprobar identidad.',
    alerta: true,
  },
  DOCUMENTO: {
    etiqueta: 'Documento verificado',
    consecuencia: 'Identidad comprobada contra documento.',
    alerta: false,
  },
  PRESENCIAL: {
    etiqueta: 'Verificado en persona',
    consecuencia: 'Identidad comprobada en el mostrador.',
    alerta: false,
  },
};

type Pestana =
  | 'resumen'
  | 'citas'
  | 'contacto'
  | 'recorrido'
  | 'historia'
  | 'odontograma'
  | 'periodoncia'
  | 'planes'
  | 'imagenes'
  | 'atencion'
  | 'faciograma'
  | 'documentos';

/** Estados de receta en palabras de quien atiende. */
const ESTADO_RECETA: Record<string, string> = {
  BORRADOR: 'Borrador',
  PENDIENTE_CONFIRMACION: 'Por confirmar',
  CONFIRMADA: 'Confirmada',
  SUSPENDIDA: 'Suspendida',
};

const DETALLE_CLINICO: Partial<Record<Pestana, string>> = {
  historia: 'Notas de evolución y recetas',
  odontograma: 'Estado por pieza e historial de cada diente',
  periodoncia: 'Periodontograma de seis sitios e índice de placa dental',
  faciograma: 'Mapa del rostro, zonas y seguimiento estético',
  documentos: 'Presupuestos, cotizaciones, recetas y PDF',
  planes: 'Fases, procedimientos y fotos del tratamiento',
  imagenes: 'Radiografías y fotos clínicas',
};

@Component({
  selector: 'app-ficha-paciente',
  standalone: true,
  imports: [
    AgentePacienteComponent,
    PeriodontogramaComponent,
    VentanaFlotanteComponent,
    AtencionPacienteComponent,
    EditorPacienteComponent,
    InsigniaEstadoComponent,
    IconoComponent,
    GaleriaImagenesComponent,
    FotoPerfilComponent,
    ConsentimientosPacienteComponent,
    OdontogramaComponent,
    PlanesTratamientoComponent,
    TipoDocumentoPipe,
    ResumenClinicoComponent,
    SelectorEspecialidadComponent,
    RecorridoPacienteComponent,
  ],
  template: `
    <div class="ficha" [class.ficha--embebida]="sinCabecera()" [class.ficha--con-agente]="agenteAbierto()" [attr.aria-label]="'Ficha de ' + nombre()">
      <!-- ============ Identidad: foto, documento y lo urgente ============ -->
      <aside class="ficha__lado">
        <div class="ficha__foto">
          <app-foto-perfil
            [pacienteId]="pacienteId()"
            [nombre]="nombre()"
            [iniciales]="iniciales()"
            [tamano]="112"
            [puedeEditar]="puedeEditarFoto()"
            [conBotones]="true"
          />
        </div>
        @if (!sinCabecera()) {
          <h2 class="ficha__nombre">{{ nombre() }}</h2>
        }
        @if (paciente(); as p) {
          <p class="ficha__documento numerico">
            {{ p.tipo_documento | tipoDocumento }} {{ p.numero_documento }}
            @if (edad()) {
              <span> · {{ edad() }}</span>
            }
          </p>
        }
        @if (verificacion(); as v) {
          <p class="ficha__verificacion" [class.ficha__verificacion--alerta]="v.alerta">
            <strong>{{ v.etiqueta }}.</strong> {{ v.consecuencia }}
          </p>
        }
        @if (paciente(); as p) {
          <dl class="ficha__rapido">
            <div>
              <dt>WhatsApp</dt>
              <dd class="numerico">{{ p.telefono_whatsapp ?? 'sin registrar' }}</dd>
            </div>
            <div>
              <dt>Correo</dt>
              <dd>{{ p.correo ?? 'sin registrar' }}</dd>
            </div>
            <div>
              <dt>Próxima cita</dt>
              <dd>
                @if (proxima(); as cita) {
                  <span class="numerico">{{ fechaHora(cita.inicio) }}</span>
                } @else {
                  sin citas futuras
                }
              </dd>
            </div>
          </dl>
          @if (puedeEditarFoto()) { <button class="boton boton--pequeno" type="button" (click)="editandoDatos.set(true)">Editar datos del paciente</button> }
        }
        @if (!sinCabecera()) {
          <button
            type="button"
            class="boton boton--plano ficha__cerrar"
            (click)="cerrar.emit()"
            aria-label="Cerrar la ficha del paciente"
          >
            <app-icono nombre="cerrar" [tamano]="18" />
          </button>
        }
      </aside>

      <!-- ===================== Contenido por pestañas ===================== -->
      <section class="ficha__principal">
        @if (paciente() && puedeUsarAgente()) {
          <div class="ficha__agente-acceso"><span>Apoyo para {{ nombre() }}</span><button #botonAgente class="boton boton--principal" type="button" [attr.aria-expanded]="agenteAbierto()" (click)="agenteAbierto.set(!agenteAbierto())">{{ agenteAbierto() ? 'Ocultar agente' : 'Agente del paciente' }}</button></div>
        }
        @if (cargando()) {
          <p class="ficha__aviso" role="status">Cargando la ficha…</p>
        } @else if (error()) {
          <p class="ficha__error" role="alert">{{ error()!.message }}</p>
        } @else {
          <app-selector-especialidad class="ficha__especialidad" (cambio)="cambiarEspecialidad()" />
          @if (accesosClinicos().length && !sinAccesoClinico()) {
            <div class="ficha__registrar"><span>{{ especialidades.elegida()?.nombre }}</span><button class="boton boton--principal" type="button" (click)="selectorRegistro.set(true)">Elegir qué registrar</button></div>
          }
          <div class="ficha__pestanas" role="tablist" aria-label="Secciones de la ficha">
            @for (tab of pestanas(); track tab.clave) {
              <button
                type="button"
                role="tab"
                class="ficha__pestana"
                [class.ficha__pestana--activa]="pestana() === tab.clave"
                [attr.aria-selected]="pestana() === tab.clave"
                (click)="elegir(tab.clave)"
              >
                {{ tab.etiqueta }}
                @if (tab.clave === 'citas' && citas().length > 0) {
                  <span class="ficha__cuenta numerico">{{ citas().length }}</span>
                }
              </button>
            }
          </div>

          <div class="ficha__cuerpo" role="tabpanel">
            @switch (pestana()) {
              @case ('atencion') { <app-atencion-paciente [pacienteId]="pacienteId()" [citaInicial]="citaParaAtencion()" (cambioCita)="citaElegidaId.set($event?.id ?? null)" /> }
              @case ('faciograma') { <app-atencion-paciente [pacienteId]="pacienteId()" [citaInicial]="citaParaAtencion()" moduloInicial="faciograma" (cambioCita)="citaElegidaId.set($event?.id ?? null)" /> }
              @case ('documentos') { <app-atencion-paciente [pacienteId]="pacienteId()" [citaInicial]="citaParaAtencion()" moduloInicial="documentos" (cambioCita)="citaElegidaId.set($event?.id ?? null)" /> }
              @case ('periodoncia') { <app-periodontograma [pacienteId]="pacienteId()" [citaId]="citaParaAtencion()" /> }
              @case ('resumen') {
                <div class="ficha__rejilla">
                  <section class="ficha__bloque">
                    <h3>Próxima cita</h3>
                    @if (proxima(); as cita) {
                      <p class="ficha__hora numerico">
                        {{ fechaHora(cita.inicio) }}
                        <app-insignia-estado [estado]="cita.estado" />
                      </p>
                      @if (cita.estado === 'HELD' && cita.expira_en) {
                        <p class="ficha__caduca">
                          Turno apartado sin confirmar: caduca el {{ fechaHora(cita.expira_en) }}.
                        </p>
                      }
                    } @else {
                      <p class="ficha__nada">Sin citas futuras.</p>
                    }
                  </section>

                  <section class="ficha__bloque">
                    <h3>Cómo tratarle</h3>
                    <ul class="ficha__banderas">
                      @for (bandera of banderas(); track bandera.titulo) {
                        <li>
                          <strong>{{ bandera.titulo }}</strong>
                          <span>{{ bandera.detalle }}</span>
                        </li>
                      } @empty {
                        <li><span>Nada que destacar en el historial administrativo.</span></li>
                      }
                    </ul>
                  </section>

                  <section class="ficha__bloque">
                    <h3>Datos personales</h3>
                    <dl class="ficha__datos">
                      @for (dato of contacto(); track dato.campo) {
                        <div>
                          <dt>{{ dato.campo }}</dt>
                          <dd>{{ dato.valor }}</dd>
                        </div>
                      }
                    </dl>
                  </section>

                  @if (accesosClinicos().length) {
                    <section class="ficha__bloque">
                      <h3>Herramientas de su especialidad</h3>
                      <div class="ficha__atajos">
                        @for (atajo of accesosClinicos(); track atajo.clave) {
                          <button type="button" class="ficha__atajo" (click)="elegir(atajo.clave)">
                            <strong>{{ atajo.etiqueta }}</strong>
                            <span>{{ atajo.detalle }}</span>
                          </button>
                        }
                      </div>
                      <p class="campo__ayuda">
                        Cada lectura de datos clínicos queda registrada con nombre y hora.
                      </p>
                    </section>
                  } @else {
                    <!-- El límite de ámbito, dicho aquí: un hueco sin explicar se lee como un fallo. -->
                    <section class="ficha__bloque ficha__limite">
                      <h3>Sin información clínica</h3>
                      <p>
                        Esta ficha muestra lo administrativo. El historial, los diagnósticos y la
                        medicación no están aquí porque su rol no los alcanza, no porque falten.
                      </p>
                    </section>
                  }
                </div>
              }

              @case ('citas') {
                <section>
                  <h3>Historial de citas</h3>
                  @if (citas().length === 0) {
                    <p class="ficha__nada">Sin citas registradas.</p>
                  } @else {
                    <ul class="ficha__citas">
                      @for (cita of citas(); track cita.id) {
                        <li>
                          <span class="numerico">{{ fechaHora(cita.inicio) }}</span>
                          <app-insignia-estado [estado]="cita.estado" />
                        </li>
                      }
                    </ul>
                    @if (inasistencias() > 0) {
                      <p class="ficha__ojo">
                        <strong>{{ inasistencias() }} inasistencia(s) registradas.</strong>
                        Conviene confirmar por llamada en lugar de solo enviar el recordatorio.
                      </p>
                    }
                  }
                </section>
              }

              @case ('contacto') {
                <section>
                  <h3>Contacto</h3>
                  <dl class="ficha__datos">
                    @for (dato of contacto(); track dato.campo) {
                      <div>
                        <dt>{{ dato.campo }}</dt>
                        <dd class="numerico">{{ dato.valor }}</dd>
                      </div>
                    }
                  </dl>
                  <p class="campo__ayuda">
                    Ningún recordatorio automático incluye diagnóstico, medicamento ni motivo de
                    consulta.
                  </p>
                </section>
                <app-consentimientos-paciente [pacienteId]="pacienteId()" />
              }

              @case ('historia') {
                <section>
                  <div class="ficha__titulo-accion">
                    <h3>Historia clínica</h3>
                    <button type="button" class="boton boton--pequeno" (click)="abrirHistoria()">
                      Abrir historia completa
                    </button>
                  </div>
                  @if (puedeLeerHistoria() && !consultandoAcceso() && !sinAccesoClinico()) {
                    <app-resumen-clinico [pacienteId]="pacienteId()" />
                  }
                  @if (cargandoClinico()) {
                    <p class="ficha__nada" role="status">Cargando…</p>
                  } @else {
                    @if (avisoClinico()) {
                      <p class="ficha__ojo" role="status">{{ avisoClinico() }}</p>
                    }
                    @if (puedeLeerHistoria() && !avisoClinico()) {
                      <h4 class="ficha__subtitulo">Últimas notas de evolución</h4>
                      <ul class="ficha__notas">
                        @for (nota of notas(); track nota.id) {
                          <li>
                            <span class="numerico">{{ fecha(nota.creado_en) }}</span>
                            <strong>{{ nota.tipo }}</strong>
                            <span>{{ nota.motivo_consulta || 'Sin motivo de consulta registrado' }}</span>
                          </li>
                        } @empty {
                          <li class="ficha__nada">Sin notas registradas.</li>
                        }
                      </ul>
                    }
                    @if (puedeLeerRecetas() && !recetasNoDisponibles()) {
                      <h4 class="ficha__subtitulo">Recetas</h4>
                      <ul class="ficha__notas">
                        @for (receta of recetas(); track receta.id) {
                          <li>
                            <span class="numerico">{{ fecha(receta.creado_en) }}</span>
                            <strong>{{ estadoReceta(receta.estado) }}</strong>
                            <span>{{ medicamentos(receta) }}</span>
                          </li>
                        } @empty {
                          <li class="ficha__nada">Sin recetas registradas.</li>
                        }
                      </ul>
                    }
                  }
                </section>
              }

              @case ('odontograma') {
                <app-odontograma [pacienteId]="pacienteId()" />
              }

              @case ('planes') {
                <app-planes-tratamiento
                  [pacienteId]="pacienteId()"
                  [nombrePaciente]="nombre()"
                  [puedeEditar]="puedeEditarPlanes()"
                />
              }

              @case ('imagenes') {
                <app-galeria-imagenes [pacienteId]="pacienteId()" />
              }
              @case ('recorrido') {
                <app-recorrido-paciente [pacienteId]="pacienteId()" [zona]="zona()" />
              }
            }
          </div>
        }
      </section>
      @if (agenteAbierto()) {
        <aside class="ficha__agente"><app-agente-paciente [pacienteId]="pacienteId()" [nombre]="nombre()" [citaId]="citaParaAtencion()" [zona]="zona()" (cerrar)="cerrarAgente()" (actualizado)="actualizarCitasAgente()" /></aside>
      }
    </div>
    @if (editandoDatos() && paciente(); as p) {
      <app-editor-paciente [paciente]="p" (cerrar)="editandoDatos.set(false)" (guardado)="editandoDatos.set(false); recargarDatos()" />
    }
    @if (selectorRegistro()) {
      <app-ventana-flotante ceja="Ficha del paciente" titulo="¿Qué desea registrar?" forma="centrada" [anchoMaximo]="680" (cerrar)="selectorRegistro.set(false)">
        <p>{{ especialidades.elegida()?.nombre }} · {{ nombre() }}</p>
        <div class="ficha__atajos">@for (atajo of accesosClinicos(); track atajo.clave) {
          <button class="ficha__atajo" type="button" (click)="selectorRegistro.set(false); elegir(atajo.clave)"><strong>{{ atajo.etiqueta }}</strong><span>{{ atajo.detalle }}</span></button>
        }</div>
      </app-ventana-flotante>
    }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    .ficha__agente-acceso { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; padding:12px 20px; border-bottom:1px solid var(--borde); }
    .ficha.ficha--con-agente { grid-template-columns:220px minmax(0,1fr) minmax(310px,36%); }
    .ficha__agente { min-height:0; min-width:0; overflow-y:auto; border-left:1px solid var(--borde); }
    @media (max-width:1100px) {
      .ficha.ficha--con-agente { grid-template-columns:minmax(0,1fr) minmax(300px,42%); }
      .ficha--con-agente .ficha__lado { display:none; }
    }
    @media (max-width:700px) {
      .ficha.ficha--con-agente { grid-template-columns:minmax(0,1fr); height:auto; overflow:visible; }
      .ficha__agente { min-height:580px; border-left:0; border-top:1px solid var(--borde); }
    }
    .ficha__registrar { display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 20px;flex-wrap:wrap; }
    .ficha {
      position: relative;
      display: grid;
      grid-template-columns: 272px minmax(0, 1fr);
      height: 100%;
      min-height: 0;
      border: 1px solid var(--borde);
      border-radius: var(--radio);
      background: var(--superficie-elevada);
      box-shadow: var(--sombra-2);
      overflow: hidden;
    }

    /* Dentro de una ventana flotante no lleva marco propio: seria un borde
       dentro de otro borde a dos pixeles de distancia. */
    .ficha--embebida {
      border: 0;
      border-radius: 0;
      box-shadow: none;
      margin: calc(var(--espacio-4) * -1);
      height: calc(100% + var(--espacio-4) * 2);
    }

    .ficha__lado {
      display: flex;
      flex-direction: column;
      gap: var(--espacio-3);
      padding: var(--espacio-5) var(--espacio-4);
      border-right: 1px solid var(--borde);
      background: var(--superficie);
      overflow-y: auto;
    }

    .ficha__foto {
      display: flex;
      justify-content: center;
    }

    .ficha__nombre {
      margin: 0;
      font-size: 1.2rem;
      text-align: center;
    }

    .ficha__documento {
      margin: 0;
      text-align: center;
      color: var(--texto-suave);
      font-size: 0.9rem;
    }

    .ficha__verificacion {
      margin: 0;
      padding: var(--espacio-2) var(--espacio-3);
      border: 1px solid var(--borde);
      border-radius: var(--radio);
      background: var(--superficie-hundida);
      font-size: 0.84rem;
    }

    .ficha__verificacion--alerta {
      border-color: color-mix(in srgb, var(--aviso) 40%, transparent);
      background: var(--aviso-fondo);
      color: var(--aviso);
    }

    .ficha__rapido {
      margin: 0;
      display: grid;
      gap: var(--espacio-2);
    }

    .ficha__rapido div {
      display: grid;
      gap: 2px;
    }

    .ficha__rapido dt {
      color: var(--texto-tenue);
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    .ficha__rapido dd {
      margin: 0;
      font-size: 0.9rem;
      overflow-wrap: anywhere;
    }

    .ficha__cerrar {
      position: absolute;
      top: var(--espacio-2);
      right: var(--espacio-2);
      min-width: 36px;
      min-height: 36px;
      padding: 0;
    }

    .ficha__principal {
      display: flex;
      flex-direction: column;
      min-width: 0;
      min-height: 0;
    }

    .ficha__especialidad { display: block; margin-bottom: var(--espacio-3); }
    .ficha__pestanas {
      display: flex;
      flex-wrap: wrap;
      gap: 2px;
      padding: 0 var(--espacio-3);
      border-bottom: 1px solid var(--borde);
    }

    .ficha__pestana {
      min-height: var(--toque-minimo);
      padding: 0 var(--espacio-3);
      border: 0;
      background: transparent;
      color: var(--texto-suave);
      font-weight: 600;
      cursor: pointer;
    }

    .ficha__pestana:hover {
      color: var(--texto);
    }

    .ficha__pestana:focus-visible {
      outline: 3px solid var(--acento);
      outline-offset: -3px;
    }

    .ficha__pestana--activa {
      color: var(--acento-fuerte);
      box-shadow: inset 0 -3px 0 var(--acento);
    }

    .ficha__cuenta {
      margin-left: var(--espacio-1);
      padding: 0 6px;
      border-radius: 999px;
      background: var(--superficie-hundida);
      color: var(--texto-suave);
      font-size: 0.75rem;
      font-weight: 700;
    }

    .ficha__cuerpo {
      flex: 1 1 auto;
      min-height: 0;
      overflow-y: auto;
      padding: var(--espacio-4) var(--espacio-5);
      display: flex;
      flex-direction: column;
      gap: var(--espacio-4);
    }

    .ficha__cuerpo h3 {
      margin: 0 0 var(--espacio-2);
      font-size: 0.8rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--texto-suave);
    }

    .ficha__subtitulo {
      margin: var(--espacio-3) 0 var(--espacio-1);
      font-size: 0.9rem;
    }

    .ficha__rejilla {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: var(--espacio-3);
    }

    .ficha__bloque {
      padding: var(--espacio-3) var(--espacio-4);
      border: 1px solid var(--borde);
      border-radius: var(--radio);
      background: var(--superficie);
    }

    .ficha__hora {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: var(--espacio-2);
      margin: 0;
      font-size: 1.05rem;
      font-weight: 650;
    }

    .ficha__caduca {
      margin: var(--espacio-2) 0 0;
      color: var(--aviso);
      font-size: 0.88rem;
      font-weight: 600;
    }

    .ficha__nada,
    .ficha__aviso {
      margin: 0;
      color: var(--texto-tenue);
    }

    .ficha__aviso,
    .ficha__error {
      padding: var(--espacio-4);
    }

    .ficha__error {
      margin: 0;
      color: var(--peligro);
    }

    .ficha__banderas {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: var(--espacio-2);
    }

    .ficha__banderas li {
      display: flex;
      flex-direction: column;
      font-size: 0.9rem;
    }

    .ficha__banderas span {
      color: var(--texto-suave);
      font-size: 0.86rem;
    }

    .ficha__citas,
    .ficha__notas {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
    }

    .ficha__citas li,
    .ficha__notas li {
      display: flex;
      align-items: center;
      gap: var(--espacio-3);
      padding: var(--espacio-2) 0;
      border-bottom: 1px solid var(--superficie-hundida);
      font-size: 0.9rem;
    }

    .ficha__citas li {
      justify-content: space-between;
    }

    .ficha__notas li span:last-child {
      min-width: 0;
      color: var(--texto-suave);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .ficha__ojo {
      margin: var(--espacio-3) 0 0;
      color: var(--aviso);
      font-size: 0.88rem;
    }

    .ficha__datos {
      margin: 0;
      display: flex;
      flex-direction: column;
      gap: var(--espacio-2);
    }

    .ficha__datos div {
      display: flex;
      gap: var(--espacio-3);
      padding-bottom: var(--espacio-2);
      border-bottom: 1px solid var(--superficie-hundida);
    }

    .ficha__datos dt {
      flex: 0 1 110px;
      max-width: 40%;
      color: var(--texto-tenue);
      font-size: 0.86rem;
    }

    .ficha__datos dd {
      margin: 0;
      flex: 1 1 auto;
      min-width: 0;
      overflow-wrap: anywhere;
      font-size: 0.9rem;
    }

    .ficha__atajos {
      display: grid;
      gap: var(--espacio-2);
    }

    .ficha__atajo {
      display: grid;
      gap: 2px;
      padding: var(--espacio-2) var(--espacio-3);
      border: 1px solid var(--borde);
      border-radius: var(--radio);
      background: var(--superficie-elevada);
      color: var(--texto);
      text-align: left;
      cursor: pointer;
    }

    .ficha__atajo:hover {
      border-color: var(--acento);
    }

    .ficha__atajo:focus-visible {
      outline: 3px solid var(--acento);
      outline-offset: 2px;
    }

    .ficha__atajo span {
      color: var(--texto-suave);
      font-size: 0.82rem;
    }

    .ficha__titulo-accion {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: var(--espacio-3);
    }

    .ficha__titulo-accion h3 {
      margin: 0;
    }

    .ficha__limite {
      border-style: dashed;
    }

    .ficha__limite p {
      margin: 0;
      color: var(--texto-suave);
      font-size: 0.88rem;
    }

    @media (max-width: 860px) {
      .ficha {
        grid-template-columns: 1fr;
        overflow-y: auto;
      }

      .ficha__lado {
        border-right: 0;
        border-bottom: 1px solid var(--borde);
        overflow: visible;
      }

      .ficha__cuerpo {
        overflow: visible;
        padding: var(--espacio-4);
      }

      .ficha__pestanas {
        flex-wrap: nowrap;
        overflow-x: auto;
        flex-shrink: 0;
        scrollbar-width: thin;
      }

      .ficha__pestana {
        flex-shrink: 0;
        white-space: nowrap;
      }

      .ficha__rejilla {
        grid-template-columns: 1fr;
      }
    }
  `,
})
export class FichaPacienteComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly sesion = inject(SesionService);
  protected readonly especialidades = inject(EspecialidadHistoriaService);
  private readonly router = inject(Router);
  private readonly operaciones = inject(OperacionesService);

  readonly pacienteId = input.required<string>();
  readonly citaInicial = input<string | null>(null);
  protected readonly citaElegidaId = signal<string | null | undefined>(undefined);
  protected readonly citaParaAtencion = computed(() => this.citaElegidaId() === undefined ? this.citaInicial() : this.citaElegidaId() ?? null);
  protected readonly editandoDatos = signal(false);
  protected readonly agenteAbierto = signal(false);
  private readonly botonAgente = viewChild<ElementRef<HTMLButtonElement>>('botonAgente');
  protected cerrarAgente(): void {
    this.agenteAbierto.set(false);
    this.botonAgente()?.nativeElement.focus();
  }
  protected readonly puedeUsarAgente = computed(() => this.sesion.tienePermiso('paciente.leer_administrativo'));
  /**
   * Cierto cuando va dentro de una ventana flotante, que ya pone su título
   * (el nombre) y su botón de cerrar.
   */
  readonly sinCabecera = input(false);
  /** Zona de presentación de la sede, nunca la del equipo. */
  readonly zona = input('America/Guayaquil');
  readonly cerrar = output<void>();

  protected readonly puedeLeerHistoria = computed(() =>
    this.sesion.tienePermiso(PERMISOS.historiaLeer),
  );
  protected readonly puedeLeerRecetas = computed(() =>
    this.sesion.tienePermiso(PERMISOS.recetaLeer),
  );
  protected readonly puedeEditarPlanes = computed(() =>
    this.sesion.tienePermiso(PERMISOS.planTratamientoEscribir),
  );

  /** Cada pestaña clínica aparece solo si el rol tiene el permiso que el backend exige. */
  protected readonly pestanas = computed(() => {
    const lista: { clave: Pestana; etiqueta: string }[] = [
      { clave: 'resumen', etiqueta: 'Resumen' },
      { clave: 'citas', etiqueta: 'Citas' },
      { clave: 'contacto', etiqueta: 'Contacto y consentimientos' },
    ];
    // Por dónde pasó en la clínica: dato administrativo, lo ve quien ve la agenda.
    if (this.sesion.tieneAlgunPermiso('agenda.leer', 'historia_clinica.leer', 'receta.leer')) lista.push({ clave: 'atencion', etiqueta: 'Atención y documentos' });
    if (this.sesion.tienePermiso('agenda.leer')) {
      lista.push({ clave: 'recorrido', etiqueta: 'Recorrido' });
    }
    if (this.puedeLeerHistoria() || this.puedeLeerRecetas()) {
      lista.push({ clave: 'historia', etiqueta: 'Historia y recetas' });
    }
    // Además del permiso, el módulo debe estar activo en la especialidad elegida.
    const modulo = (m: ModuloHistoria) => this.especialidades.tieneModulo(m);
    // Sin acceso clínico no se ofrecen: solo darían «no disponible».
    const clinico = !this.sinAccesoClinico();
    if (clinico && this.sesion.tienePermiso(PERMISOS.odontogramaLeer) && modulo('odontograma')) {
      lista.push({ clave: 'odontograma', etiqueta: 'Odontograma' });
    }
    if (clinico && this.sesion.tienePermiso(PERMISOS.odontogramaLeer) && modulo('periodoncia')) {
      lista.push({ clave: 'periodoncia', etiqueta: 'Periodoncia' });
    }
    if (clinico && this.puedeLeerHistoria()) {
      if (modulo('faciograma')) lista.push({ clave: 'faciograma', etiqueta: 'Faciograma' });
      lista.push({ clave: 'documentos', etiqueta: 'Documentos y PDF' });
    }
    if (clinico && this.sesion.tienePermiso(PERMISOS.planTratamientoLeer) && modulo('planes')) {
      lista.push({ clave: 'planes', etiqueta: 'Plan de tratamiento' });
    }
    if (clinico && this.sesion.tienePermiso(PERMISOS.imagenClinicaLeer) && modulo('imagenes')) {
      lista.push({ clave: 'imagenes', etiqueta: 'Imágenes' });
    }
    return lista;
  });

  /** Atajos del resumen a las secciones clínicas que el rol puede abrir. */
  protected readonly accesosClinicos = computed(() =>
    this.pestanas()
      .filter((tab) => DETALLE_CLINICO[tab.clave])
      .map((tab) => ({ ...tab, detalle: DETALLE_CLINICO[tab.clave] ?? '' })),
  );

  protected readonly pestana = signal<Pestana>('resumen');
  protected readonly selectorRegistro = signal(false);
  protected readonly paciente = signal<PacienteDetalle | null>(null);
  protected readonly citas = signal<readonly Cita[]>([]);
  protected readonly cargando = signal(true);
  protected readonly error = signal<FalloApi | null>(null);
  protected readonly notas = signal<readonly Nota[]>([]);
  protected readonly recetas = signal<readonly Receta[]>([]);
  protected readonly cargandoClinico = signal(false);
  /**
   * Si quien mira puede pedir los datos clínicos de este paciente. `null`:
   * aún no se sabe o no aplica. Con `false` no se piden (el backend daría 404:
   * falta relación asistencial) y se explica en su lugar.
   */
  protected readonly accesoClinico = signal<boolean | null>(null);
  protected readonly sinAccesoClinico = computed(() => this.accesoClinico() === false);
  protected readonly consultandoAcceso = signal(false);
  /** Las recetas no se pudieron cargar: no se dice «sin recetas». */
  protected readonly recetasNoDisponibles = signal(false);
  protected readonly avisoClinico = signal('');
  private clinicoCargado = false;

  protected readonly nombre = computed(() => {
    const p = this.paciente();
    return p ? `${p.nombre} ${p.apellido}` : 'Paciente';
  });

  /** Cambiar la foto es editar la ficha: mismo permiso que el backend exige. */
  protected readonly puedeEditarFoto = computed(() =>
    this.sesion.tienePermiso(PERMISOS.pacienteEditar),
  );

  protected readonly iniciales = computed(() => {
    const p = this.paciente();
    if (!p) {
      return '··';
    }
    return `${p.nombre.charAt(0)}${p.apellido.charAt(0)}`.toUpperCase();
  });

  protected readonly verificacion = computed(() => {
    const p = this.paciente();
    if (!p) {
      return null;
    }
    return (
      VERIFICACION[p.nivel_verificacion] ?? {
        etiqueta: p.nivel_verificacion,
        consecuencia: 'Nivel de verificación desconocido: compruebe identidad en el mostrador.',
        alerta: true,
      }
    );
  });

  protected readonly edad = computed(() => {
    const nacimiento = this.paciente()?.fecha_nacimiento;
    if (!nacimiento) {
      return '';
    }
    const anos = Math.floor((Date.now() - Date.parse(nacimiento)) / 31_557_600_000);
    return anos >= 0 && anos < 130 ? `${anos} años` : '';
  });

  /** La primera cita futura que todavía cuenta. */
  protected readonly proxima = computed(() => {
    const ahora = Date.now();
    return (
      this.citas()
        .filter(
          (cita) =>
            Date.parse(cita.inicio) >= ahora &&
            (cita.estado === 'PENDING' ||
              cita.estado === 'HELD' ||
              cita.estado === 'CONFIRMED' ||
              cita.estado === 'RESCHEDULED'),
        )
        .sort((a, b) => Date.parse(a.inicio) - Date.parse(b.inicio))[0] ?? null
    );
  });

  protected readonly inasistencias = computed(
    () => this.citas().filter((cita) => cita.estado === 'NO_SHOW').length,
  );

  /**
   * Lo que quien atiende necesita saber antes de hablar.
   *
   * Solo se dice lo que se deduce de datos reales: nada inventado y nada
   * clínico.
   */
  protected readonly banderas = computed(() => {
    const avisos: { titulo: string; detalle: string }[] = [];
    const p = this.paciente();

    if (this.inasistencias() >= 2) {
      avisos.push({
        titulo: `${this.inasistencias()} inasistencias registradas`,
        detalle: 'Confirmar por llamada da mejor resultado que el recordatorio automático.',
      });
    }
    if (p && !p.telefono_whatsapp) {
      avisos.push({
        titulo: 'Sin teléfono de WhatsApp',
        detalle: 'No recibe recordatorios ni ofertas de lista de espera: hay que llamar.',
      });
    }
    const proxima = this.proxima();
    if (proxima && proxima.estado === 'HELD') {
      avisos.push({
        titulo: 'Tiene un turno apartado sin confirmar',
        detalle: 'Si caduca, el hueco vuelve a la agenda y se queda sin cita.',
      });
    }
    if (p && !p.activo) {
      avisos.push({
        titulo: 'Ficha inactiva',
        detalle: 'No debería agendarse sin revisar antes con administración.',
      });
    }
    return avisos;
  });

  protected readonly contacto = computed(() => {
    const p = this.paciente();
    if (!p) {
      return [];
    }
    return [
      { campo: 'WhatsApp', valor: p.telefono_whatsapp ?? 'sin registrar' },
      { campo: 'Correo', valor: p.correo ?? 'sin registrar' },
      { campo: 'Sexo', valor: p.sexo ?? 'sin registrar' },
      {
        campo: 'Nacimiento',
        valor: p.fecha_nacimiento ? this.fecha(p.fecha_nacimiento) : 'sin registrar',
      },
      { campo: 'Dirección', valor: p.direccion ?? 'sin registrar' },
      { campo: 'Ficha', valor: p.activo ? 'activa' : 'inactiva' },
    ];
  });

  /**
   * La carga va en `ngOnInit` y no en el constructor: una entrada obligatoria
   * no existe todavía cuando corre el constructor (NG0950). La ficha se
   * destruye y se vuelve a crear al cambiar de paciente.
   */
  ngOnInit(): void {
    if (this.citaInicial()) this.pestana.set('atencion');
    this.especialidades.cargar();
    this.cargar();
    this.consultarAccesoClinico();
  }

  /** Pregunta una vez si se pueden pedir los datos clínicos (200 sí/no, nunca 404 en cadena). */
  private consultarAccesoClinico(): void {
    const clinicos = ['historia_clinica.leer', 'odontograma.leer', 'plan_tratamiento.leer', 'imagen_clinica.leer'];
    if (!this.sesion.tieneAlgunPermiso(...clinicos)) return;
    this.consultandoAcceso.set(true);
    this.operaciones
      .leer<{ acceso_clinico: boolean }>(`/pacientes/${this.pacienteId()}/acceso-clinico`)
      .subscribe({
        next: (r) => this.accesoClinico.set(r.acceso_clinico),
        // Si no se puede saber, se intenta como antes y cada pestaña explica su fallo.
        error: () => this.accesoClinico.set(null),
        complete: () => this.trasConsultarAcceso(),
      });
  }

  private trasConsultarAcceso(): void {
    this.consultandoAcceso.set(false);
    if (this.pestana() === 'historia' && !this.clinicoCargado) this.cargarClinico();
  }

  /** Otra especialidad: las notas se vuelven a pedir y las pestañas cambian. */
  protected cambiarEspecialidad(): void {
    if (!this.pestanas().some((tab) => tab.clave === this.pestana())) {
      this.pestana.set('resumen');
    }
    if (this.clinicoCargado) this.cargarClinico();
  }

  protected recargarDatos(): void { this.cargar(); }
  protected actualizarCitasAgente(): void {
    this.api.citas({ paciente_id: this.pacienteId(), limite: 50 }).subscribe({
      next: (pagina) => this.citas.set([...pagina.elementos].sort((a,b) => Date.parse(b.inicio)-Date.parse(a.inicio))),
      error: () => this.avisoClinico.set('La acción fue procesada. Actualice la ficha para consultar el estado de la agenda.'),
    });
  }
  private cargar(): void {
    const id = this.pacienteId();
    this.cargando.set(true);
    this.error.set(null);

    this.api.paciente(id).subscribe({
      next: (detalle) => {
        this.paciente.set(detalle);
        this.api.citas({ paciente_id: id, limite: 50 }).subscribe({
          next: (pagina) => {
            this.citas.set(
              [...pagina.elementos].sort((a, b) => Date.parse(b.inicio) - Date.parse(a.inicio)),
            );
            this.cargando.set(false);
          },
          error: () => {
            // La identidad ya está cargada: sin el historial la ficha sigue
            // sirviendo, así que no se convierte en pantalla de error.
            this.cargando.set(false);
          },
        });
      },
      error: (fallo: unknown) => {
        this.cargando.set(false);
        this.error.set(
          fallo instanceof FalloApi
            ? fallo
            : new FalloApi('ERROR_DESCONOCIDO', 'No se pudo cargar la ficha.', 0),
        );
      },
    });
  }

  protected elegir(clave: Pestana): void {
    this.pestana.set(clave);
    // Si aún se está consultando el acceso, se carga al terminar la consulta.
    if (clave === 'historia' && !this.clinicoCargado && !this.consultandoAcceso()) {
      this.cargarClinico();
    }
  }

  /** Notas y recetas, cada una solo si el rol puede leerlas. */
  private cargarClinico(): void {
    this.clinicoCargado = true;
    this.cargandoClinico.set(true);
    this.avisoClinico.set('');
    this.recetasNoDisponibles.set(false);
    const id = this.pacienteId();
    // Sin acceso clínico, las notas no se piden; las recetas son compartidas.
    const pedirNotas = this.puedeLeerHistoria() && !this.sinAccesoClinico();
    if (this.puedeLeerHistoria() && !pedirNotas) this.avisoClinico.set(MENSAJE_SIN_ACCESO_CLINICO);
    let pendientes = (pedirNotas ? 1 : 0) + (this.puedeLeerRecetas() ? 1 : 0);
    if (pendientes === 0) this.cargandoClinico.set(false);
    const terminar = () => {
      pendientes -= 1;
      if (pendientes <= 0) {
        this.cargandoClinico.set(false);
      }
    };
    const denegado = (fallo: unknown) => {
      this.avisoClinico.set(
        fallo instanceof FalloApi && fallo.codigo === 'RELACION_ASISTENCIAL_REQUERIDA'
          ? 'No tiene relación asistencial con este paciente: la historia solo la ve quien le atiende.'
          : mensajeFalloClinico(fallo, 'No se pudo cargar la historia.'),
      );
      terminar();
    };
    if (pedirNotas) {
      this.api.notas(id, false, this.especialidades.elegida()?.id ?? null).subscribe({
        next: (notas) => {
          this.notas.set(
            [...notas].sort((a, b) => Date.parse(b.creado_en) - Date.parse(a.creado_en)).slice(0, 8),
          );
          terminar();
        },
        error: denegado,
      });
    }
    if (this.puedeLeerRecetas()) {
      this.api.recetas(id).subscribe({
        next: (recetas) => {
          this.recetas.set(recetas);
          terminar();
        },
        error: (fallo: unknown) => {
          this.recetasNoDisponibles.set(true);
          denegado(fallo);
        },
      });
    }
  }

  protected abrirHistoria(): void {
    void this.router.navigate(['/historia-clinica'], {
      queryParams: { paciente: this.pacienteId() },
    });
    this.cerrar.emit();
  }

  protected estadoReceta(estado: string): string {
    return ESTADO_RECETA[estado] ?? estado;
  }

  protected medicamentos(receta: Receta): string {
    return (
      receta.medicamentos.map((m) => `${m.nombre} ${m.dosis}`).join(' · ') || 'Sin medicamentos'
    );
  }

  protected fecha(instante: string): string {
    return formatearFecha(instante, this.zona());
  }

  protected fechaHora(instante: string): string {
    return formatearFechaHora(instante, this.zona());
  }
}
