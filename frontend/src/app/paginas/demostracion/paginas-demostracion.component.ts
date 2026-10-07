/**
 * Pantallas del prototipo que todavía usan datos sintéticos.
 *
 * Están juntas a propósito. Son maquetas: existen para mostrar la forma que
 * tendrá cada sección y para que se pueda discutir la interfaz antes de
 * construir el backend correspondiente. Separarlas en carpetas por módulo
 * sugeriría una estructura que aún no existe, y cuando cada una se conecte de
 * verdad se moverá a su sitio con su servicio, sus estados y sus pruebas.
 *
 * **Todas llevan el aviso de demostración.** No es cortesía: una captura de
 * cualquiera de estas pantallas puede acabar en una reunión presentada como
 * datos de la clínica.
 *
 * Lo que sí es real aquí
 * ----------------------
 * Las **reglas** que las pantallas reflejan, aunque los datos no lo sean:
 *
 *  * Una receta sin confirmar por un profesional NO genera calendario de
 *    tomas, y la pantalla lo dice.
 *  * Un medicamento «cuando sea necesario» (PRN) NO tiene horarios fijos ni
 *    recordatorios. Convertirlo en pauta fija es un error de medicación.
 *  * Un documento archivado o vencido NO es recuperable por el agente.
 *
 * Esas reglas se mantienen cuando llegue el backend; los datos no.
 */
import { Component, computed, inject, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  AvisoDemostracionComponent,
  VacioComponent,
} from '../../compartido/estados.component';
import {
  ESPECIALIDADES,
  PACIENTES,
  PROFESIONALES,
  SEDES,
  SERVICIOS,
  nombreEspecialidad,
  nombrePaciente,
  nombreProfesional,
  nombreSede,
} from '../../datos-sinteticos/catalogo';
import {
  DOCUMENTOS,
  LISTA_ESPERA,
  NOTAS,
  RECETAS,
  TOMAS,
  type EstadoDocumento,
} from '../../datos-sinteticos/clinico';
import { SesionService } from '../../nucleo/servicios/sesion.service';

/**
 * Recorta un instante ISO a su parte de fecha.
 *
 * Se usa una funcion y no el pipe `slice` de `CommonModule`: importar el
 * modulo entero en cada componente por un recorte de texto es peso que se
 * descarga en la tableta de recepcion sin aportar nada.
 *
 * En las pantallas reales la fecha se formatea con la zona de la sede
 * (`nucleo/utilidades/fechas.ts`). Aqui no hace falta: son datos de
 * demostracion y no hay sede seleccionada.
 */
function soloFecha(instanteIso: string): string {
  return instanteIso.slice(0, 10);
}

// ===========================================================================
//  Panel
// ===========================================================================
@Component({
  selector: 'app-panel',
  standalone: true,
  imports: [AvisoDemostracionComponent],
  template: `
    <h1>Panel</h1>
    <app-aviso-demostracion
      detalle="Los indicadores todavía no se calculan sobre datos reales (Fase 8)."
    />

    <div class="rejilla">
      @for (indicador of indicadores(); track indicador.etiqueta) {
        <div class="tarjeta indicador">
          <p class="indicador__valor numerico">{{ indicador.valor }}</p>
          <p class="indicador__etiqueta">{{ indicador.etiqueta }}</p>
          <p class="indicador__nota">{{ indicador.nota }}</p>
        </div>
      }
    </div>

    <div class="tarjeta bienvenida">
      <h2>Sesión activa</h2>
      <p>
        {{ sesion.nombreCompleto() }} · {{ sesion.identidad()?.roles?.join(' · ') }}
      </p>
      <p class="bienvenida__permisos">
        {{ sesion.identidad()?.permisos?.length ?? 0 }} permisos efectivos, resueltos de la
        base de datos en cada petición. Revocar uno surte efecto de inmediato, sin esperar a
        que caduque su token.
      </p>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    .indicador__valor {
      font-size: 2rem;
      font-weight: 700;
      margin: 0;
      color: var(--acento);
    }
    .indicador__etiqueta {
      font-weight: 600;
      margin: 0 0 var(--espacio-1);
    }
    .indicador__nota {
      margin: 0;
      font-size: 0.85rem;
      color: var(--texto-tenue);
    }
    .bienvenida {
      margin-top: var(--espacio-5);
    }
    .bienvenida__permisos {
      color: var(--texto-suave);
      font-size: 0.9rem;
      margin: 0;
    }
  `,
})
export class PanelComponent {
  protected readonly sesion = inject(SesionService);

  protected readonly indicadores = computed(() => [
    {
      etiqueta: 'Citas hoy',
      valor: 14,
      nota: 'Dato de demostración',
    },
    {
      etiqueta: 'En lista de espera',
      valor: LISTA_ESPERA.length,
      nota: 'Dato de demostración',
    },
    {
      etiqueta: 'Tomas pendientes',
      valor: TOMAS.filter((toma) => toma.estado === 'PENDIENTE').length,
      nota: 'Dato de demostración',
    },
    {
      etiqueta: 'Documentos publicados',
      valor: DOCUMENTOS.filter((documento) => documento.estado === 'PUBLISHED').length,
      nota: 'Dato de demostración',
    },
  ]);
}

// ===========================================================================
//  Pacientes (demostración)
// ===========================================================================
@Component({
  selector: 'app-pacientes-demo',
  standalone: true,
  imports: [FormsModule, AvisoDemostracionComponent, VacioComponent],
  template: `
    <h1>Pacientes</h1>
    <app-aviso-demostracion
      detalle="Listado de demostración. El buscador real contra el backend llega con la
               escritura de pacientes (Fase 2)."
    />

    <label class="campo">
      <span class="campo__etiqueta">Buscar por nombre o apellido</span>
      <input class="campo__control" name="busqueda" [(ngModel)]="termino" />
      <span class="campo__ayuda">
        En el sistema real hacen falta al menos tres caracteres: con menos, la búsqueda
        devolvería media clínica y dejaría de ser una búsqueda.
      </span>
    </label>

    @if (resultados().length === 0) {
      <div class="tarjeta">
        <app-vacio titulo="Sin coincidencias" detalle="Pruebe con otro término." />
      </div>
    } @else {
      <div class="tabla-envoltorio">
        <table class="tabla">
          <thead>
            <tr>
              <th scope="col">Paciente</th>
              <th scope="col">Documento</th>
              <th scope="col">Contacto</th>
              <th scope="col">Verificación</th>
            </tr>
          </thead>
          <tbody>
            @for (paciente of resultados(); track paciente.id) {
              <tr>
                <td>{{ paciente.apellido }}, {{ paciente.nombre }}</td>
                <td class="numerico">{{ paciente.numero_documento }}</td>
                <td>{{ paciente.telefono_whatsapp }}</td>
                <td>
                  <!-- El nivel de verificación no es decorativo: un teléfono
                       no verificado NO basta para dar información por
                       WhatsApp, y quien atiende tiene que verlo antes de
                       hablar. -->
                  <span class="verificacion">{{ paciente.nivel_verificacion }}</span>
                </td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    .verificacion {
      font-size: 0.8rem;
      font-weight: 650;
      padding: 2px var(--espacio-2);
      border-radius: 999px;
      border: 1px solid var(--aviso);
      background: var(--aviso-fondo);
      color: var(--aviso);
    }
  `,
})
export class PacientesDemoComponent {
  protected termino = '';

  protected resultados(): typeof PACIENTES {
    const busqueda = this.termino.trim().toLowerCase();
    if (!busqueda) {
      return PACIENTES;
    }
    return PACIENTES.filter((paciente) =>
      `${paciente.nombre} ${paciente.apellido}`.toLowerCase().includes(busqueda),
    );
  }
}

// ===========================================================================
//  Lista de espera
// ===========================================================================
@Component({
  selector: 'app-lista-espera',
  standalone: true,
  imports: [AvisoDemostracionComponent, VacioComponent],
  template: `
    <h1>Lista de espera</h1>
    <app-aviso-demostracion
      detalle="La oferta automática de turnos liberados llega en la Fase 5."
    />

    <div class="tarjeta nota-diseno">
      <h2>Cómo funcionará</h2>
      <p>
        Cuando se libera un turno, el sistema ofrecerá ese hueco a
        <strong>una persona a la vez</strong>, con un plazo límite. No se envía a todos:
        varios pacientes aceptando el mismo turno producirían un ganador y varios avisos de
        «ya no está disponible», que erosiona la confianza en el aviso.
      </p>
      <p>
        Si dos aceptaciones llegan a la vez, un bloqueo consultivo de PostgreSQL sobre el
        turno decide: una gana y la otra recibe que el turno acaba de tomarse.
      </p>
    </div>

    @if (entradas.length === 0) {
      <app-vacio titulo="Nadie en lista de espera" />
    } @else {
      <div class="tabla-envoltorio">
        <table class="tabla">
          <thead>
            <tr>
              <th scope="col">Paciente</th>
              <th scope="col">Especialidad</th>
              <th scope="col">Sede</th>
              <th scope="col">Prioridad</th>
              <th scope="col">Preferencia</th>
            </tr>
          </thead>
          <tbody>
            @for (entrada of entradas; track entrada.id) {
              <tr>
                <td>{{ nombrePaciente(entrada.paciente_id) }}</td>
                <td>{{ nombreEspecialidad(entrada.especialidad_id) }}</td>
                <td>{{ nombreSede(entrada.sede_id) }}</td>
                <td>
                  <span class="prioridad" [class.prioridad--alta]="entrada.prioridad === 'ALTA'">
                    {{ entrada.prioridad }}
                  </span>
                </td>
                <td>{{ entrada.preferencia_horaria }}</td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    .nota-diseno {
      margin-bottom: var(--espacio-4);
      border-left: 4px solid var(--info);
    }
    .prioridad {
      font-size: 0.8rem;
      font-weight: 650;
      padding: 2px var(--espacio-2);
      border-radius: 999px;
      border: 1px solid var(--texto-suave);
      color: var(--texto-suave);
    }
    .prioridad--alta {
      border-color: var(--peligro);
      background: var(--peligro-fondo);
      color: var(--peligro);
    }
  `,
})
export class ListaEsperaComponent {
  protected readonly entradas = LISTA_ESPERA;
  protected readonly nombrePaciente = nombrePaciente;
  protected readonly nombreEspecialidad = nombreEspecialidad;
  protected readonly nombreSede = nombreSede;
}

// ===========================================================================
//  Historia clínica
// ===========================================================================
@Component({
  selector: 'app-historia-clinica',
  standalone: true,
  imports: [AvisoDemostracionComponent],
  template: `
    <h1>Historia clínica</h1>
    <app-aviso-demostracion
      detalle="Maqueta. La historia clínica real, con versionado append-only y control de
               acceso por tipo de información, llega en la Fase 7."
    />

    <div class="tarjeta nota-diseno">
      <h2>Reglas que la pantalla refleja</h2>
      <ul>
        <li>
          <strong>Las notas no se borran ni se sobrescriben.</strong> Cada modificación crea
          una versión nueva y conserva la anterior, con su autor, su fecha y el motivo del
          cambio.
        </li>
        <li>
          <strong>Recepción no ve esta sección.</strong> El permiso
          <code>historia_clinica.leer</code> no lo tiene, y el ámbito limita además a qué
          pacientes alcanza cada profesional.
        </li>
        <li>
          <strong>Cada lectura queda auditada.</strong> Ante «quién vio mi historia» tiene
          que haber respuesta.
        </li>
      </ul>
    </div>

    @for (nota of notas; track nota.id) {
      <article class="tarjeta nota">
        <header class="nota__cabecera">
          <h3>{{ nota.motivo_consulta }}</h3>
          <span class="nota__version">versión {{ nota.version }}</span>
        </header>
        <p class="nota__meta">
          {{ nombreProfesional(nota.profesional_id) }} ·
          {{ soloFecha(nota.fecha) }}
        </p>
        <p>{{ nota.evolucion }}</p>
        @if (nota.motivo_modificacion) {
          <p class="nota__modificacion">
            <strong>Motivo de la modificación:</strong> {{ nota.motivo_modificacion }}
          </p>
        }
      </article>
    }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    .nota-diseno {
      margin-bottom: var(--espacio-4);
      border-left: 4px solid var(--info);
    }
    .nota-diseno ul {
      margin: 0;
      padding-left: var(--espacio-5);
    }
    .nota-diseno li {
      margin-bottom: var(--espacio-2);
    }
    .nota {
      margin-bottom: var(--espacio-4);
    }
    .nota__cabecera {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: var(--espacio-3);
    }
    .nota__cabecera h3 {
      margin: 0;
    }
    .nota__version {
      font-size: 0.8rem;
      color: var(--texto-tenue);
      white-space: nowrap;
    }
    .nota__meta {
      color: var(--texto-suave);
      font-size: 0.9rem;
    }
    .nota__modificacion {
      margin: 0;
      padding: var(--espacio-2) var(--espacio-3);
      border-radius: var(--radio);
      background: var(--superficie-hundida);
      font-size: 0.9rem;
    }
    code {
      font-family: var(--fuente-mono);
    }
  `,
})
export class HistoriaClinicaComponent {
  protected readonly notas = NOTAS;
  protected readonly soloFecha = soloFecha;
  protected readonly nombreProfesional = nombreProfesional;
}

// ===========================================================================
//  Medicamentos
// ===========================================================================
@Component({
  selector: 'app-medicamentos',
  standalone: true,
  imports: [AvisoDemostracionComponent],
  template: `
    <h1>Medicamentos y adherencia</h1>
    <app-aviso-demostracion
      detalle="Maqueta. Ningún medicamento de esta pantalla está indicado a nadie (Fase 7)."
    />

    @for (receta of recetas; track receta.id) {
      <article class="tarjeta receta">
        <header class="receta__cabecera">
          <h2>Receta del {{ soloFecha(receta.fecha) }}</h2>
          @if (receta.confirmada) {
            <span class="marca marca--exito">Confirmada</span>
          } @else {
            <!-- La distinción no es cosmética: una receta sin confirmar por
                 el profesional NO genera calendario de tomas. Mostrarlas
                 iguales llevaría a creer que los recordatorios están
                 activos. -->
            <span class="marca marca--aviso">Sin confirmar</span>
          }
        </header>

        @if (!receta.confirmada) {
          <p class="receta__advertencia">
            Una receta sin confirmar por el profesional <strong>no genera</strong> calendario
            de tomas ni recordatorios.
          </p>
        }

        <ul class="medicamentos">
          @for (medicamento of receta.medicamentos; track medicamento.nombre) {
            <li class="medicamento">
              <p class="medicamento__nombre">{{ medicamento.nombre }}</p>
              <p class="medicamento__pauta">
                {{ medicamento.dosis }} · {{ medicamento.via }} ·
                @if (medicamento.cuando_sea_necesario) {
                  <strong>cuando sea necesario</strong>
                } @else {
                  cada {{ medicamento.frecuencia_horas }} h durante {{ medicamento.dias }} días
                }
              </p>
              @if (medicamento.cuando_sea_necesario) {
                <!-- Regla de seguridad clínica, no de interfaz: convertir un
                     PRN en pauta fija es un error de medicación. -->
                <p class="medicamento__prn">
                  Sin horarios fijos ni recordatorios automáticos: convertir un «cuando sea
                  necesario» en pauta fija sería un error de medicación.
                </p>
              }
            </li>
          }
        </ul>
      </article>
    }

    <h2>Registro de tomas</h2>
    <div class="tabla-envoltorio">
      <table class="tabla">
        <thead>
          <tr>
            <th scope="col">Medicamento</th>
            <th scope="col">Programada</th>
            <th scope="col">Estado</th>
          </tr>
        </thead>
        <tbody>
          @for (toma of tomas; track toma.id) {
            <tr>
              <td>{{ toma.medicamento }}</td>
              <td class="numerico">{{ soloFecha(toma.programada_en) }}</td>
              <td>
                <span class="marca" [class]="'marca--' + claseEstado(toma.estado)">
                  {{ toma.estado }}
                </span>
              </td>
            </tr>
          }
        </tbody>
      </table>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    .receta {
      margin-bottom: var(--espacio-4);
    }
    .receta__cabecera {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--espacio-3);
      margin-bottom: var(--espacio-3);
    }
    .receta__cabecera h2 {
      margin: 0;
    }
    .receta__advertencia {
      padding: var(--espacio-2) var(--espacio-3);
      border-radius: var(--radio);
      background: var(--aviso-fondo);
      color: var(--aviso);
    }
    .medicamentos {
      list-style: none;
      margin: 0;
      padding: 0;
    }
    .medicamento {
      padding: var(--espacio-3) 0;
      border-top: 1px solid var(--borde);
    }
    .medicamento__nombre {
      font-weight: 650;
      margin: 0;
    }
    .medicamento__pauta {
      margin: 0;
      color: var(--texto-suave);
    }
    .medicamento__prn {
      margin: var(--espacio-2) 0 0;
      font-size: 0.88rem;
      color: var(--aviso);
    }
    .marca {
      font-size: 0.8rem;
      font-weight: 650;
      padding: 2px var(--espacio-2);
      border-radius: 999px;
      border: 1px solid currentcolor;
      white-space: nowrap;
    }
    .marca--exito {
      color: var(--exito);
      background: var(--exito-fondo);
    }
    .marca--aviso {
      color: var(--aviso);
      background: var(--aviso-fondo);
    }
    .marca--peligro {
      color: var(--peligro);
      background: var(--peligro-fondo);
    }
    .marca--neutra {
      color: var(--texto-suave);
      background: var(--superficie-hundida);
    }
  `,
})
export class MedicamentosComponent {
  protected readonly recetas = RECETAS;
  protected readonly soloFecha = soloFecha;
  protected readonly tomas = TOMAS;

  protected claseEstado(estado: string): string {
    if (estado === 'TOMADA') {
      return 'exito';
    }
    if (estado === 'OMITIDA') {
      return 'peligro';
    }
    return 'neutra';
  }
}

// ===========================================================================
//  Conocimiento
// ===========================================================================
@Component({
  selector: 'app-conocimiento',
  standalone: true,
  imports: [AvisoDemostracionComponent],
  template: `
    <h1>Base de conocimiento</h1>
    <app-aviso-demostracion
      detalle="Maqueta. La ingesta, el versionado y la búsqueda con RAG llegan en la Fase 6."
    />

    <div class="tarjeta nota-diseno">
      <h2>Qué puede recuperar el agente</h2>
      <p>
        Solo documentos en estado <strong>APPROVED</strong> o <strong>PUBLISHED</strong> y
        <strong>vigentes</strong>. El filtro va en el <code>WHERE</code> de la consulta SQL,
        nunca como descarte posterior en código: un post-filtro deja de aplicarse en cuanto
        alguien añade una rama y lo olvida.
      </p>
      <p>
        El texto de un documento es <strong>dato citado, nunca instrucción</strong>. Un PDF
        que diga «ignora las reglas anteriores» no cambia el comportamiento del agente,
        porque su contenido no llega al modelo como orden (ADR-0014).
      </p>
    </div>

    <div class="tabla-envoltorio">
      <table class="tabla">
        <thead>
          <tr>
            <th scope="col">Documento</th>
            <th scope="col">Categoría</th>
            <th scope="col">Versión</th>
            <th scope="col">Estado</th>
            <th scope="col">¿Recuperable?</th>
          </tr>
        </thead>
        <tbody>
          @for (documento of documentos; track documento.id) {
            <tr>
              <td>
                {{ documento.titulo }}
                <span class="resumen">{{ documento.resumen }}</span>
              </td>
              <td>{{ documento.categoria }}</td>
              <td class="numerico">{{ documento.version }}</td>
              <td>{{ documento.estado }}</td>
              <td>
                @if (esRecuperable(documento.estado)) {
                  <span class="marca marca--exito">Sí</span>
                } @else {
                  <span class="marca marca--peligro">No</span>
                }
              </td>
            </tr>
          }
        </tbody>
      </table>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    .nota-diseno {
      margin-bottom: var(--espacio-4);
      border-left: 4px solid var(--info);
    }
    .resumen {
      display: block;
      font-size: 0.85rem;
      color: var(--texto-tenue);
      max-width: 52ch;
    }
    .marca {
      font-size: 0.8rem;
      font-weight: 650;
      padding: 2px var(--espacio-2);
      border-radius: 999px;
      border: 1px solid currentcolor;
    }
    .marca--exito {
      color: var(--exito);
      background: var(--exito-fondo);
    }
    .marca--peligro {
      color: var(--peligro);
      background: var(--peligro-fondo);
    }
    code {
      font-family: var(--fuente-mono);
    }
  `,
})
export class ConocimientoComponent {
  protected readonly documentos = DOCUMENTOS;

  /** Solo aprobados o publicados son recuperables (ADR-0013). */
  protected esRecuperable(estado: EstadoDocumento): boolean {
    return estado === 'APPROVED' || estado === 'PUBLISHED';
  }
}

// ===========================================================================
//  Catálogo
// ===========================================================================
@Component({
  selector: 'app-catalogo-demo',
  standalone: true,
  imports: [AvisoDemostracionComponent],
  template: `
    <h1>Catálogo</h1>
    <app-aviso-demostracion
      detalle="Vista de demostración. La agenda sí lee el catálogo real del backend; esta
               pantalla muestra el ejemplo con el que se diseñó."
    />

    <h2>Sedes</h2>
    <div class="rejilla">
      @for (sede of sedes; track sede.id) {
        <div class="tarjeta">
          <h3>{{ sede.nombre }}</h3>
          <p>{{ sede.direccion }}</p>
          <p class="tenue">{{ sede.zona_horaria }}</p>
        </div>
      }
    </div>

    <h2>Servicios</h2>
    <div class="tabla-envoltorio">
      <table class="tabla">
        <thead>
          <tr>
            <th scope="col">Servicio</th>
            <th scope="col">Especialidad</th>
            <th scope="col">Duración</th>
            <th scope="col">Preparación</th>
          </tr>
        </thead>
        <tbody>
          @for (servicio of servicios; track servicio.id) {
            <tr>
              <td>{{ servicio.nombre }}</td>
              <td>{{ nombreEspecialidad(servicio.especialidad_id) }}</td>
              <td class="numerico">{{ servicio.duracion_minutos }} min</td>
              <td class="numerico">{{ servicio.minutos_preparacion }} min</td>
            </tr>
          }
        </tbody>
      </table>
    </div>
    <p class="tenue nota-granularidad">
      Las duraciones y preparaciones son múltiplos de 15 a propósito: encajan con la
      granularidad de las franjas del motor de disponibilidad. Con otros valores se pierde
      capacidad por redondeo.
    </p>

    <h2>Profesionales</h2>
    <div class="rejilla">
      @for (profesional of profesionales; track profesional.id) {
        <div class="tarjeta">
          <h3>{{ profesional.nombre }} {{ profesional.apellido }}</h3>
          <p>{{ nombreEspecialidad(profesional.especialidad_id) }}</p>
          <p class="tenue numerico">{{ profesional.numero_registro_profesional }}</p>
        </div>
      }
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    h2 {
      margin-top: var(--espacio-6);
    }
    .tenue {
      color: var(--texto-tenue);
      font-size: 0.88rem;
    }
    .nota-granularidad {
      max-width: 70ch;
      margin-top: var(--espacio-3);
    }
  `,
})
export class CatalogoDemoComponent {
  protected readonly sedes = SEDES;
  protected readonly servicios = SERVICIOS;
  protected readonly profesionales = PROFESIONALES;
  protected readonly especialidades = ESPECIALIDADES;
  protected readonly nombreEspecialidad = nombreEspecialidad;
}

// ===========================================================================
//  Sin permiso
// ===========================================================================
@Component({
  selector: 'app-sin-permiso',
  standalone: true,
  template: `
    <div class="tarjeta sin-permiso">
      <h1>No tiene acceso a esta sección</h1>
      <p>
        Su rol no incluye los permisos que esta sección requiere. No es un error: el sistema
        concede el mínimo necesario para trabajar, y el acceso a datos clínicos está
        separado del acceso administrativo a propósito.
      </p>
      <p class="sin-permiso__nota">
        Si necesita entrar, pídalo al administrador de la clínica. El cambio surte efecto en
        su siguiente petición, sin tener que volver a iniciar sesión.
      </p>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    .sin-permiso {
      max-width: 60ch;
    }
    .sin-permiso__nota {
      color: var(--texto-suave);
      font-size: 0.92rem;
      margin: 0;
    }
  `,
})
export class SinPermisoComponent {}
