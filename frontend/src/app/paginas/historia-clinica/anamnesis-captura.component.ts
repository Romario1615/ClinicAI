import { Component, effect, inject, input, signal, untracked, ChangeDetectionStrategy } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { IconoComponent } from '../../compartido/icono.component';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
import { FalloApi } from '../../nucleo/servicios/api.service';
import { OperacionesService } from '../../nucleo/servicios/operaciones.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';

type TipoPregunta = 'texto' | 'texto_largo' | 'booleano' | 'seleccion' | 'seleccion_multiple';

interface PreguntaAnamnesis {
  id: string;
  etiqueta: string;
  tipo: TipoPregunta;
  obligatoria: boolean;
  ayuda: string | null;
  opciones: string[];
}

interface PlantillaAnamnesis {
  id: string;
  nombre: string;
  version: number;
  nivel_sensibilidad: 'N2' | 'N3';
  preguntas: PreguntaAnamnesis[];
}

interface RespuestaAnamnesis {
  id: string;
  plantilla_id: string;
  plantilla: string;
  version_plantilla: number;
  nivel_sensibilidad: 'N2' | 'N3';
  preguntas: PreguntaAnamnesis[];
  respuestas: Record<string, unknown>;
  registrada_en: string;
}

@Component({
  selector: 'app-anamnesis-captura',
  standalone: true,
  imports: [DatePipe, FormsModule, IconoComponent, VentanaFlotanteComponent],
  template: `
    <section class="captura" aria-labelledby="titulo-captura-anamnesis">
      <header class="captura__cabecera">
        <div><p class="ceja"><app-icono nombre="historia" [tamano]="15" /> REGISTRO ASISTENCIAL</p><h3 id="titulo-captura-anamnesis">Anamnesis de la clínica</h3><p>Las respuestas se guardan con la versión de preguntas utilizada.</p></div>
        <button type="button" class="boton boton--pequeno" (click)="cargar()" [disabled]="cargando()">Actualizar</button>
      </header>
      @if (error()) { <p class="captura__error" role="alert">{{ error() }}</p> }
      @if (aviso()) { <p class="captura__aviso" role="status">{{ aviso() }}</p> }
      @if (cargando()) { <p class="captura__estado" role="status">Cargando formularios y capturas…</p> }
      @else {
        @if (plantillas().length && puedeEscribir()) {
          <div class="iniciar-captura">
            <p>Registra las respuestas con la plantilla clínica publicada.</p>
            <button type="button" class="boton boton--principal" (click)="abrirEditor()" aria-haspopup="dialog">
              Registrar anamnesis
            </button>
          </div>
        }
        @if (editorAbierto()) {
          <app-ventana-flotante
            ceja="Registro asistencial"
            titulo="Registrar anamnesis"
            forma="centrada"
            [anchoMaximo]="900"
            [altoCompleto]="true"
            [cierraAlPulsarFuera]="false"
            (cerrar)="cerrarEditor()"
          >
          <form id="formulario-captura-anamnesis" class="formulario" (ngSubmit)="guardar()">
            <div class="formulario__encabezado">
              <label class="campo"><span class="campo__etiqueta">Formulario activo</span>
                <select class="campo__control" name="plantilla" [ngModel]="plantillaSeleccionada()" (ngModelChange)="seleccionar($event)">
                  @for (plantilla of plantillas(); track plantilla.id) { <option [ngValue]="plantilla.id">{{ plantilla.nombre }} · v{{ plantilla.version }}</option> }
                </select>
              </label>
              @if (plantillaActual(); as plantilla) { <span class="sensibilidad" [class.sensibilidad--n3]="plantilla.nivel_sensibilidad === 'N3'">{{ plantilla.nivel_sensibilidad }} · {{ plantilla.nivel_sensibilidad === 'N3' ? 'sensible' : 'clínico' }}</span> }
            </div>
            @if (plantillaActual(); as plantilla) {
              <div class="preguntas">
                @for (pregunta of plantilla.preguntas; track pregunta.id) {
                  <div class="pregunta">
                    @if (pregunta.tipo === 'texto') {
                      <label class="campo"><span class="campo__etiqueta">{{ pregunta.etiqueta }}@if (pregunta.obligatoria) { <span class="obligatorio">*</span> }</span><input class="campo__control" [name]="pregunta.id" type="text" [required]="pregunta.obligatoria" maxlength="500" [(ngModel)]="valores[pregunta.id]" [attr.aria-describedby]="pregunta.ayuda ? 'ayuda-' + pregunta.id : null" /></label>
                    } @else if (pregunta.tipo === 'texto_largo') {
                      <label class="campo"><span class="campo__etiqueta">{{ pregunta.etiqueta }}@if (pregunta.obligatoria) { <span class="obligatorio">*</span> }</span><textarea class="campo__control" [name]="pregunta.id" [required]="pregunta.obligatoria" maxlength="4000" rows="3" [(ngModel)]="valores[pregunta.id]" [attr.aria-describedby]="pregunta.ayuda ? 'ayuda-' + pregunta.id : null"></textarea></label>
                    } @else if (pregunta.tipo === 'booleano') {
                      <fieldset class="opciones"><legend>{{ pregunta.etiqueta }}@if (pregunta.obligatoria) { <span class="obligatorio">*</span> }</legend><label><input type="radio" [name]="pregunta.id" [checked]="valores[pregunta.id] === true" [required]="pregunta.obligatoria" (change)="establecerBooleano(pregunta.id, true)" /> Sí</label><label><input type="radio" [name]="pregunta.id" [checked]="valores[pregunta.id] === false" (change)="establecerBooleano(pregunta.id, false)" /> No</label></fieldset>
                    } @else if (pregunta.tipo === 'seleccion') {
                      <label class="campo"><span class="campo__etiqueta">{{ pregunta.etiqueta }}@if (pregunta.obligatoria) { <span class="obligatorio">*</span> }</span><select class="campo__control" [name]="pregunta.id" [required]="pregunta.obligatoria" [(ngModel)]="valores[pregunta.id]"><option [ngValue]="undefined">Seleccione…</option>@for (opcion of pregunta.opciones; track opcion) { <option [value]="opcion">{{ opcion }}</option> }</select></label>
                    } @else {
                      <fieldset class="opciones"><legend>{{ pregunta.etiqueta }}@if (pregunta.obligatoria) { <span class="obligatorio">*</span> }</legend>@for (opcion of pregunta.opciones; track opcion) { <label><input type="checkbox" [checked]="opcionElegida(pregunta.id, opcion)" (change)="alternarOpcion(pregunta.id, opcion, $any($event.target).checked)" /> {{ opcion }}</label> }</fieldset>
                    }
                    @if (pregunta.ayuda) { <small class="ayuda" [id]="'ayuda-' + pregunta.id">{{ pregunta.ayuda }}</small> }
                  </div>
                }
              </div>
            }
          </form>
          <div pie>
            <button class="boton" type="button" (click)="cerrarEditor()" [disabled]="guardando()">Cancelar</button>
            <button class="boton boton--principal" type="submit" form="formulario-captura-anamnesis" [disabled]="guardando() || !plantillaActual()">
              {{ guardando() ? 'Guardando…' : 'Guardar respuestas' }}
            </button>
          </div>
          </app-ventana-flotante>
        }
        @if (!plantillas().length) {
          <p class="captura__estado">No hay una plantilla publicada disponible para esta clínica.</p>
        }

        <section class="historial" aria-labelledby="titulo-historial-anamnesis">
          <div class="historial__cabecera"><h4 id="titulo-historial-anamnesis">Capturas anteriores</h4><span>{{ respuestas().length }}</span></div>
          @if (!respuestas().length) { <p class="captura__estado">Todavía no hay capturas de plantillas.</p> }
          @for (respuesta of respuestas(); track respuesta.id) {
            <article class="captura-anterior">
              <header><div><strong>{{ respuesta.plantilla }} · v{{ respuesta.version_plantilla }}</strong><span>{{ respuesta.registrada_en | date:'dd/MM/yyyy HH:mm' }}</span></div><span class="sensibilidad" [class.sensibilidad--n3]="respuesta.nivel_sensibilidad === 'N3'">{{ respuesta.nivel_sensibilidad }}</span></header>
              <dl>@for (pregunta of respuesta.preguntas; track pregunta.id) { <div><dt>{{ pregunta.etiqueta }}</dt><dd>{{ valorLegible(respuesta.respuestas[pregunta.id]) }}</dd></div> }</dl>
            </article>
          }
        </section>
      }
    </section>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    :host { display:block; }
    .captura { display:grid; gap:var(--espacio-3); padding:var(--espacio-4); border:1px solid var(--borde); border-radius:var(--radio); background:var(--superficie-elevada); }
    .captura__cabecera,.historial__cabecera { display:flex; align-items:flex-start; justify-content:space-between; gap:var(--espacio-3); }
    .captura__cabecera h3 { margin:2px 0 3px; font-size:1.04rem; }
    .captura__cabecera p:last-child { margin:0; color:var(--texto-suave); font-size:.88rem; }
    .ceja { display:flex; align-items:center; gap:var(--espacio-1); margin:0; color:var(--acento); font-size:.7rem; font-weight:750; letter-spacing:.1em; }
    .captura__error,.captura__aviso,.captura__estado { margin:0; padding:var(--espacio-3); border-radius:var(--radio-pequeno); }
    .captura__error { color:var(--peligro); background:var(--peligro-fondo); }
    .captura__aviso { color:var(--exito); background:var(--exito-fondo); }
    .captura__estado { color:var(--texto-suave); background:var(--superficie); }
    .iniciar-captura { display:flex; align-items:center; justify-content:space-between; gap:var(--espacio-3); padding:var(--espacio-3); border:1px solid var(--cristal-borde); border-radius:var(--radio); background:var(--cristal-superficie); box-shadow:inset 0 1px rgb(255 255 255 / 85%); }
    .iniciar-captura p { margin:0; color:var(--texto-suave); font-size:.9rem; }
    .formulario { display:grid; gap:var(--espacio-3); }
    .formulario__encabezado { display:flex; align-items:end; gap:var(--espacio-3); }
    .formulario__encabezado .campo { flex:1; margin:0; }
    .sensibilidad { display:inline-flex; align-items:center; width:max-content; padding:3px 9px; border:1px solid var(--borde); border-radius:999px; color:var(--texto-suave); font-size:.72rem; font-weight:700; }
    .sensibilidad--n3 { border-color:var(--aviso); background:var(--aviso-fondo); color:var(--aviso); }
    .preguntas { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr)); gap:var(--espacio-3); }
    .pregunta { min-width:0; padding:var(--espacio-3); border:1px solid var(--borde); border-radius:var(--radio-pequeno); background:var(--superficie-elevada); }
    .pregunta .campo { margin:0; }
    .obligatorio { color:var(--peligro); }
    .ayuda { display:block; margin-top:var(--espacio-1); color:var(--texto-tenue); }
    .opciones { display:flex; flex-wrap:wrap; gap:var(--espacio-2) var(--espacio-4); min-width:0; margin:0; padding:0; border:0; }
    .opciones legend { width:100%; margin-bottom:var(--espacio-2); font-size:.9rem; font-weight:650; color:var(--texto-suave); }
    .opciones label { display:flex; align-items:center; gap:var(--espacio-1); min-height:32px; }
    .historial { display:grid; gap:var(--espacio-3); }
    .historial__cabecera { align-items:center; padding-bottom:var(--espacio-2); border-bottom:1px solid var(--borde); }
    .historial__cabecera h4 { margin:0; font-size:.88rem; }
    .historial__cabecera > span { color:var(--texto-tenue); font-variant-numeric:tabular-nums; }
    .captura-anterior { display:grid; gap:var(--espacio-3); padding:var(--espacio-3); border:1px solid var(--borde); border-radius:var(--radio-pequeno); }
    .captura-anterior header { display:flex; justify-content:space-between; gap:var(--espacio-3); }
    .captura-anterior header div { display:grid; gap:2px; }
    .captura-anterior header div span { color:var(--texto-tenue); font-size:.8rem; }
    .captura-anterior dl { display:grid; gap:var(--espacio-2); margin:0; }
    .captura-anterior dl div { display:grid; grid-template-columns:minmax(130px,.7fr) minmax(0,1.3fr); gap:var(--espacio-3); }
    .captura-anterior dt { color:var(--texto-suave); font-size:.86rem; font-weight:650; }
    .captura-anterior dd { margin:0; overflow-wrap:anywhere; font-size:.9rem; }
    @media(max-width:560px) { .iniciar-captura { align-items:stretch; flex-direction:column; } .formulario__encabezado { align-items:stretch; flex-direction:column; } .captura-anterior dl div { grid-template-columns:1fr; gap:2px; } }
  `,
})
export class AnamnesisCapturaComponent {
  private readonly operaciones = inject(OperacionesService);
  private readonly sesion = inject(SesionService);
  readonly pacienteId = input.required<string>();
  protected readonly plantillas = signal<readonly PlantillaAnamnesis[]>([]);
  protected readonly respuestas = signal<readonly RespuestaAnamnesis[]>([]);
  protected readonly plantillaSeleccionada = signal('');
  protected readonly cargando = signal(true);
  protected readonly guardando = signal(false);
  protected readonly error = signal('');
  protected readonly aviso = signal('');
  protected readonly editorAbierto = signal(false);
  protected valores: Record<string, unknown> = {};

  constructor() {
    effect(() => {
      const paciente = this.pacienteId();
      untracked(() => this.cargar(paciente));
    });
  }

  protected puedeEscribir(): boolean {
    return this.sesion.tienePermiso('historia_clinica.escribir') && !!this.sesion.identidad()?.profesional_id;
  }

  protected plantillaActual(): PlantillaAnamnesis | null {
    return this.plantillas().find((plantilla) => plantilla.id === this.plantillaSeleccionada()) ?? null;
  }

  protected abrirEditor(): void {
    this.valores = {};
    this.error.set('');
    this.editorAbierto.set(true);
  }

  protected cerrarEditor(): void {
    if (this.guardando()) return;
    this.editorAbierto.set(false);
    this.valores = {};
    this.error.set('');
  }

  protected seleccionar(id: string): void {
    this.plantillaSeleccionada.set(id);
    this.valores = {};
  }

  protected opcionElegida(preguntaId: string, opcion: string): boolean {
    const valor = this.valores[preguntaId];
    return Array.isArray(valor) && valor.includes(opcion);
  }

  protected alternarOpcion(preguntaId: string, opcion: string, marcada: boolean): void {
    const actual = Array.isArray(this.valores[preguntaId]) ? this.valores[preguntaId] as string[] : [];
    this.valores = { ...this.valores, [preguntaId]: marcada ? [...actual, opcion] : actual.filter((item) => item !== opcion) };
  }

  protected establecerBooleano(preguntaId: string, valor: boolean): void {
    this.valores = { ...this.valores, [preguntaId]: valor };
  }

  protected valorLegible(valor: unknown): string {
    if (typeof valor === 'boolean') return valor ? 'Sí' : 'No';
    if (Array.isArray(valor)) return valor.join(', ');
    return typeof valor === 'string' && valor.trim() ? valor : 'Sin respuesta';
  }

  protected guardar(): void {
    const plantilla = this.plantillaActual();
    if (!plantilla || !this.puedeEscribir()) return;
    this.guardando.set(true);
    this.error.set('');
    this.aviso.set('');
    this.operaciones.guardar<RespuestaAnamnesis>(
      `/historia/pacientes/${this.pacienteId()}/anamnesis/respuestas`,
      { plantilla_id: plantilla.id, respuestas: this.valores },
      crypto.randomUUID(),
    ).subscribe({
      next: (respuesta) => {
        this.respuestas.update((actuales) => [respuesta, ...actuales]);
        this.valores = {};
        this.aviso.set(`Respuestas de «${respuesta.plantilla}» guardadas en la historia clínica.`);
        this.guardando.set(false);
        this.editorAbierto.set(false);
      },
      error: (fallo: FalloApi) => { this.error.set(fallo.message); this.guardando.set(false); },
    });
  }

  protected cargar(pacienteId = this.pacienteId()): void {
    this.cargando.set(true);
    this.error.set('');
    this.operaciones.leer<PlantillaAnamnesis[]>(`/historia/pacientes/${pacienteId}/anamnesis/plantillas-activas`).subscribe({
      next: (plantillas) => {
        this.plantillas.set(plantillas);
        if (!plantillas.some((plantilla) => plantilla.id === this.plantillaSeleccionada())) {
          this.plantillaSeleccionada.set(plantillas[0]?.id ?? '');
          this.valores = {};
        }
        this.cargarRespuestas(pacienteId);
      },
      error: (fallo: FalloApi) => { this.error.set(fallo.message); this.cargando.set(false); },
    });
  }

  private cargarRespuestas(pacienteId: string): void {
    this.operaciones.leer<RespuestaAnamnesis[]>(`/historia/pacientes/${pacienteId}/anamnesis/respuestas`).subscribe({
      next: (respuestas) => { this.respuestas.set(respuestas); this.cargando.set(false); },
      error: (fallo: FalloApi) => { this.error.set(fallo.message); this.cargando.set(false); },
    });
  }
}
