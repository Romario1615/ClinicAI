/**
 * Ficha del paciente, como panel lateral sobre la pantalla actual.
 *
 * Por qué un panel y no una pantalla
 * ----------------------------------
 * Antes, saber quién es el paciente de las 10:30 exigía salir de la agenda,
 * buscarlo en la pantalla de pacientes y volver. Con un paciente delante y el
 * teléfono sonando, eso significa que no se consulta: se atiende a ciegas.
 *
 * El panel se abre encima, no navega, y al cerrarlo la agenda sigue donde
 * estaba —mismo día, misma selección—.
 *
 * Lo que muestra y lo que no
 * --------------------------
 * Muestra lo **administrativo**: identidad, nivel de verificación, próxima
 * cita, historial de citas y contacto. No muestra historia clínica, ni
 * diagnósticos, ni medicación, y lo **dice en la propia pantalla** en lugar de
 * dejar que parezca que esos datos no existen. Un hueco sin explicación se
 * interpreta como un error del sistema; un límite declarado se entiende.
 *
 * Sobre el número de documento
 * ----------------------------
 * Se muestra completo. La minimización de ADR‑0020 se aplica al menú que el
 * agente ofrece por WhatsApp a quien tenga el teléfono en la mano, no aquí:
 * este panel lo abre personal con permiso de ficha, y comprobar el documento
 * en el mostrador es precisamente cómo se verifica una identidad.
 */
import { Component, computed, inject, input, type OnInit, output, signal } from '@angular/core';

import { ApiService, FalloApi, type PacienteDetalle } from '../nucleo/servicios/api.service';
import { InsigniaEstadoComponent } from './insignia-estado.component';
import type { Cita } from '../nucleo/modelos/dominio';
import { formatearFecha, formatearFechaHora } from '../nucleo/utilidades/fechas';

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

type Pestana = 'resumen' | 'citas' | 'contacto';

@Component({
  selector: 'app-ficha-paciente',
  standalone: true,
  imports: [InsigniaEstadoComponent],
  template: `
    <aside class="ficha" role="complementary" [attr.aria-label]="'Ficha de ' + nombre()">
      <header class="ficha__cabecera">
        <div class="ficha__identidad">
          <span class="ficha__inicial" aria-hidden="true">{{ iniciales() }}</span>
          <div class="ficha__nombre">
            <h2>{{ nombre() }}</h2>
            @if (paciente(); as p) {
              <p class="numerico">
                {{ p.tipo_documento }} {{ p.numero_documento }}
                @if (edad()) {
                  <span> · {{ edad() }}</span>
                }
              </p>
            }
          </div>
          <button
            type="button"
            class="boton boton--plano ficha__cerrar"
            (click)="cerrar.emit()"
            aria-label="Cerrar la ficha del paciente"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        @if (verificacion(); as v) {
          <p class="ficha__verificacion" [class.ficha__verificacion--alerta]="v.alerta">
            <strong>{{ v.etiqueta }}.</strong> {{ v.consecuencia }}
          </p>
        }
      </header>

      @if (cargando()) {
        <p class="ficha__aviso" role="status">Cargando la ficha…</p>
      } @else if (error()) {
        <p class="ficha__error" role="alert">{{ error()!.message }}</p>
      } @else {
        <div class="ficha__pestanas" role="tablist">
          @for (tab of pestanas; track tab.clave) {
            <button
              type="button"
              role="tab"
              class="ficha__pestana"
              [class.ficha__pestana--activa]="pestana() === tab.clave"
              [attr.aria-selected]="pestana() === tab.clave"
              (click)="pestana.set(tab.clave)"
            >
              {{ tab.etiqueta }}
              @if (tab.clave === 'citas' && citas().length > 0) {
                <span class="ficha__cuenta numerico">{{ citas().length }}</span>
              }
            </button>
          }
        </div>

        <div class="ficha__cuerpo">
          @switch (pestana()) {
            @case ('resumen') {
              <section>
                <h3>Próxima cita</h3>
                @if (proxima(); as cita) {
                  <div class="tarjeta ficha__proxima">
                    <p class="ficha__hora numerico">
                      {{ fechaHora(cita.inicio) }}
                      <app-insignia-estado [estado]="cita.estado" />
                    </p>
                    @if (cita.estado === 'HELD' && cita.expira_en) {
                      <p class="ficha__caduca">
                        Turno apartado sin confirmar: caduca el {{ fechaHora(cita.expira_en) }}.
                      </p>
                    }
                  </div>
                } @else {
                  <p class="ficha__nada">Sin citas futuras.</p>
                }
              </section>

              <section>
                <h3>Cómo tratarle</h3>
                <ul class="ficha__banderas">
                  @for (bandera of banderas(); track bandera.titulo) {
                    <li>
                      <strong>{{ bandera.titulo }}</strong>
                      <span>{{ bandera.detalle }}</span>
                    </li>
                  }
                  @if (banderas().length === 0) {
                    <li><span>Nada que destacar en el historial administrativo.</span></li>
                  }
                </ul>
              </section>

              <!-- El límite de ámbito, dicho aquí y no solo en la documentación.
                   Un hueco sin explicar se lee como un fallo del sistema. -->
              <section class="ficha__limite">
                <h3>Sin información clínica</h3>
                <p>
                  Esta ficha muestra lo administrativo. El historial, los diagnósticos y la
                  medicación no están aquí porque su rol no los alcanza, no porque falten.
                </p>
                <p class="campo__ayuda">
                  Cada lectura de datos clínicos queda registrada con nombre y hora.
                </p>
              </section>
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
                        <span class="numerico">{{ fecha(cita.inicio) }}</span>
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
            }
          }
        </div>
      }
    </aside>
  `,
  styles: `
    .ficha {
      display: flex;
      flex-direction: column;
      height: 100%;
      min-height: 0;
      border: 1px solid var(--borde);
      border-radius: var(--radio);
      background: var(--superficie-elevada);
      box-shadow: var(--sombra-2);
      overflow: hidden;
    }

    .ficha__cabecera {
      padding: var(--espacio-4);
      border-bottom: 1px solid var(--borde);
    }

    .ficha__identidad {
      display: flex;
      align-items: flex-start;
      gap: var(--espacio-3);
    }

    .ficha__inicial {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 44px;
      height: 44px;
      flex: 0 0 44px;
      border-radius: 999px;
      background: var(--acento-suave);
      color: var(--acento-fuerte);
      font-weight: 700;
    }

    .ficha__nombre {
      flex: 1 1 auto;
      min-width: 0;
    }

    .ficha__nombre h2 {
      margin: 0;
      font-size: 1.25rem;
    }

    .ficha__nombre p {
      margin: 2px 0 0;
      color: var(--texto-suave);
      font-size: 0.88rem;
    }

    .ficha__cerrar {
      min-width: 36px;
      min-height: 36px;
      padding: 0;
    }

    .ficha__verificacion {
      margin: var(--espacio-3) 0 0;
      padding: var(--espacio-2) var(--espacio-3);
      border: 1px solid var(--borde);
      border-left-width: 4px;
      border-radius: var(--radio);
      background: var(--superficie-hundida);
      font-size: 0.88rem;
    }

    .ficha__verificacion--alerta {
      border-color: var(--aviso);
      background: var(--aviso-fondo);
      color: var(--aviso);
    }

    .ficha__pestanas {
      display: flex;
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
      padding: var(--espacio-4);
      display: flex;
      flex-direction: column;
      gap: var(--espacio-5);
    }

    .ficha__cuerpo h3 {
      margin: 0 0 var(--espacio-2);
      font-size: 0.85rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--texto-suave);
    }

    .ficha__proxima {
      padding: var(--espacio-3);
    }

    .ficha__hora {
      display: flex;
      align-items: center;
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
      padding-bottom: var(--espacio-2);
      border-bottom: 1px solid var(--superficie-hundida);
      font-size: 0.9rem;
    }

    .ficha__banderas span {
      color: var(--texto-suave);
      font-size: 0.86rem;
    }

    .ficha__citas {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
    }

    .ficha__citas li {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--espacio-3);
      padding: var(--espacio-2) 0;
      border-bottom: 1px solid var(--superficie-hundida);
      font-size: 0.9rem;
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
      flex: 0 0 120px;
      color: var(--texto-tenue);
      font-size: 0.88rem;
    }

    .ficha__datos dd {
      margin: 0;
      flex: 1 1 auto;
      font-size: 0.92rem;
    }

    .ficha__limite {
      padding: var(--espacio-3);
      border: 1px dashed var(--borde-fuerte);
      border-radius: var(--radio);
      background: var(--superficie);
    }

    .ficha__limite p {
      margin: 0;
      color: var(--texto-suave);
      font-size: 0.88rem;
    }

    .ficha__limite .campo__ayuda {
      margin-top: var(--espacio-2);
    }
  `,
})
export class FichaPacienteComponent implements OnInit {
  private readonly api = inject(ApiService);

  readonly pacienteId = input.required<string>();
  /** Zona de presentación de la sede, nunca la del equipo. */
  readonly zona = input('America/Guayaquil');
  readonly cerrar = output<void>();

  protected readonly pestanas: readonly { clave: Pestana; etiqueta: string }[] = [
    { clave: 'resumen', etiqueta: 'Resumen' },
    { clave: 'citas', etiqueta: 'Citas' },
    { clave: 'contacto', etiqueta: 'Contacto' },
  ];

  protected readonly pestana = signal<Pestana>('resumen');
  protected readonly paciente = signal<PacienteDetalle | null>(null);
  protected readonly citas = signal<readonly Cita[]>([]);
  protected readonly cargando = signal(true);
  protected readonly error = signal<FalloApi | null>(null);

  protected readonly nombre = computed(() => {
    const p = this.paciente();
    return p ? `${p.nombre} ${p.apellido}` : 'Paciente';
  });

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
      {
        campo: 'Nacimiento',
        valor: p.fecha_nacimiento ? this.fecha(p.fecha_nacimiento) : 'sin registrar',
      },
      { campo: 'Dirección', valor: p.direccion ?? 'sin registrar' },
      { campo: 'Ficha', valor: p.activo ? 'activa' : 'inactiva' },
    ];
  });

  /**
   * La carga va en `ngOnInit` y no en el constructor.
   *
   * No es una preferencia de estilo: una entrada obligatoria **no existe
   * todavía** cuando corre el constructor, así que leerla ahí lanza NG0950 y
   * el panel no llega a pintarse. Este panel se destruye y se vuelve a crear
   * al cambiar de paciente, así que una carga única aquí es correcta.
   */
  ngOnInit(): void {
    this.cargar();
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

  protected fecha(instante: string): string {
    return formatearFecha(instante, this.zona());
  }

  protected fechaHora(instante: string): string {
    return formatearFechaHora(instante, this.zona());
  }
}
