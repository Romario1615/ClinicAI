import { Component, OnInit, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { FalloApi } from '../../nucleo/servicios/api.service';
import { OperacionesService } from '../../nucleo/servicios/operaciones.service';
import { IconoComponent } from '../../compartido/icono.component';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';

type TipoPregunta = 'texto' | 'texto_largo' | 'booleano' | 'seleccion' | 'seleccion_multiple';
type Sensibilidad = 'N2' | 'N3';

interface PreguntaPlantilla {
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
  estado: 'BORRADOR' | 'PUBLICADA' | 'RETIRADA';
  nivel_sensibilidad: Sensibilidad;
  preguntas: PreguntaPlantilla[];
  creada_en: string;
  publicada_en: string | null;
}

interface PreguntaEditor extends PreguntaPlantilla {
  opcionesTexto: string;
}

@Component({
  selector: 'app-anamnesis-configuracion',
  standalone: true,
  imports: [FormsModule, IconoComponent, VentanaFlotanteComponent],
  template: `
    <section class="anamnesis-admin" aria-labelledby="titulo-anamnesis-admin">
      <header class="anamnesis-admin__cabecera">
        <div>
          <p class="ceja"><app-icono nombre="historia" [tamano]="16" /> HISTORIA CLÍNICA</p>
          <h2 id="titulo-anamnesis-admin">Plantillas de anamnesis</h2>
          <p>Diseña preguntas propias de la clínica, publica una versión y conserva las capturas anteriores.</p>
        </div>
        <button class="boton boton--principal" type="button" (click)="nuevoBorrador()" [disabled]="guardando()">
          <app-icono nombre="mas" [tamano]="16" /> Nueva plantilla
        </button>
      </header>

      <aside class="nota-alcance" role="note">
        <app-icono nombre="aviso" [tamano]="18" />
        <p>Estas son plantillas configurables de la clínica. No representan el Formulario MSP 033 oficial.</p>
      </aside>
      @if (aviso()) { <p class="mensaje mensaje--bien" role="status">{{ aviso() }}</p> }
      @if (error() && !editando()) { <p class="mensaje mensaje--error" role="alert">{{ error() }}</p> }

      <div class="anamnesis-admin__rejilla">
        <section class="tarjeta historial-plantillas" aria-label="Versiones de plantillas">
          <div class="seccion__titulo"><h3>Versiones guardadas</h3><button class="boton boton--pequeno" type="button" (click)="cargar()" [disabled]="cargando()">Actualizar</button></div>
          @if (cargando()) { <p role="status">Cargando plantillas…</p> }
          @else if (!plantillas().length) { <p class="vacio">Aún no hay plantillas. Crea una para empezar.</p> }
          @else {
            <ul class="lista-plantillas">
              @for (plantilla of plantillas(); track plantilla.id) {
                <li [class.lista-plantillas__activa]="plantillaActual()?.id === plantilla.id">
                  <div><strong>{{ plantilla.nombre }}</strong><span class="version">v{{ plantilla.version }}</span><small>{{ estado(plantilla.estado) }} · {{ plantilla.nivel_sensibilidad }}</small></div>
                  @if (plantilla.estado === 'BORRADOR') {
                    <button type="button" class="boton boton--pequeno" (click)="editar(plantilla)">Editar</button>
                  } @else if (plantilla.estado === 'PUBLICADA') {
                    <button type="button" class="boton boton--pequeno" (click)="nuevaVersion(plantilla)" [disabled]="guardando()">Nueva versión</button>
                  }
                </li>
              }
            </ul>
          }
        </section>

        <section class="tarjeta editor-plantilla" aria-label="Diseñador de preguntas">
          @if (!editando()) {
            <div class="editor-vacio"><span><app-icono nombre="documento-verificado" [tamano]="28" /></span><h3>Diseña una plantilla</h3><p>Agrega preguntas y publica la versión cuando esté lista para capturar respuestas.</p></div>
          } @else {
            <app-ventana-flotante ceja="Diseñador de anamnesis" [titulo]="idEditando() ? 'Editar preguntas' : 'Crear plantilla de anamnesis'" forma="centrada" [anchoMaximo]="900" [altoCompleto]="true" [cierraAlPulsarFuera]="false" (cerrar)="cancelarEdicion()">
            <form id="formulario-plantilla-anamnesis" (ngSubmit)="guardar()">
              <div class="seccion__titulo"><div><p class="ceja">{{ idEditando() ? 'VERSIÓN EN BORRADOR' : 'NUEVA PLANTILLA' }}</p><h3>{{ idEditando() ? 'Editar preguntas' : 'Datos de la plantilla' }}</h3></div></div>
              <div class="datos-plantilla">
              <label class="campo"><span class="campo__etiqueta">Nombre</span><input class="campo__control" name="nombre" [(ngModel)]="nombre" maxlength="100" minlength="3" required /></label>
              <label class="campo"><span class="campo__etiqueta">Sensibilidad de todas las respuestas</span>
                <select class="campo__control" name="sensibilidad" [(ngModel)]="sensibilidad">
                  <option value="N2">Clínica · N2</option><option value="N3">Clínica sensible · N3</option>
                </select>
                <small class="campo__ayuda">N3 solo se captura y consulta con el permiso historia_clinica.leer_sensible.</small>
              </label>
              </div>

              <div class="preguntas-cabecera"><h4>Preguntas <span>{{ preguntas.length }}/40</span></h4><button class="boton boton--pequeno" type="button" (click)="agregarPregunta()" [disabled]="preguntas.length >= 40">Agregar pregunta</button></div>
              <div class="preguntas-lista">
                @for (pregunta of preguntas; track $index; let indice = $index) {
                  <fieldset class="pregunta-editor">
                    <legend>Pregunta {{ indice + 1 }}</legend>
                    <div class="pregunta-editor__fila">
                      <label class="campo"><span class="campo__etiqueta">Identificador</span><input class="campo__control" [name]="'id-' + indice" [(ngModel)]="pregunta.id" pattern="[a-z][a-z0-9_-]{1,39}" maxlength="40" required placeholder="alergias_conocidas" /></label>
                      <button class="boton boton--pequeno" type="button" (click)="quitarPregunta(indice)" [disabled]="preguntas.length <= 1" [attr.aria-label]="'Quitar pregunta ' + (indice + 1)"><app-icono nombre="cerrar" [tamano]="16" /></button>
                    </div>
                    <label class="campo"><span class="campo__etiqueta">Texto visible</span><input class="campo__control" [name]="'etiqueta-' + indice" [(ngModel)]="pregunta.etiqueta" maxlength="160" required /></label>
                    <div class="pregunta-editor__fila">
                      <label class="campo"><span class="campo__etiqueta">Tipo de respuesta</span><select class="campo__control" [name]="'tipo-' + indice" [(ngModel)]="pregunta.tipo"><option value="texto">Texto corto</option><option value="texto_largo">Texto largo</option><option value="booleano">Sí / No</option><option value="seleccion">Una opción</option><option value="seleccion_multiple">Varias opciones</option></select></label>
                      <label class="requerida"><input type="checkbox" [name]="'obligatoria-' + indice" [(ngModel)]="pregunta.obligatoria" /> Obligatoria</label>
                    </div>
                    @if (pregunta.tipo === 'seleccion' || pregunta.tipo === 'seleccion_multiple') {
                      <label class="campo"><span class="campo__etiqueta">Opciones, una por línea</span><textarea class="campo__control" [name]="'opciones-' + indice" [(ngModel)]="pregunta.opcionesTexto" rows="3" required></textarea></label>
                    }
                    <label class="campo"><span class="campo__etiqueta">Ayuda opcional</span><input class="campo__control" [name]="'ayuda-' + indice" [(ngModel)]="pregunta.ayuda" maxlength="240" /></label>
                  </fieldset>
                }
              </div>
            </form>
            @if (error()) { <p class="mensaje mensaje--error" role="alert">{{ error() }}</p> }
            <div pie class="acciones acciones--final">
              <button class="boton" type="button" (click)="cancelarEdicion()" [disabled]="guardando()">Cancelar</button>
              @if (idEditando()) { <button class="boton" type="button" (click)="publicar()" [disabled]="guardando()">Publicar versión</button> }
              <button class="boton boton--principal" type="submit" form="formulario-plantilla-anamnesis" [disabled]="guardando() || !preguntas.length">{{ guardando() ? 'Guardando…' : 'Guardar borrador' }}</button>
            </div>
            </app-ventana-flotante>
          }
        </section>
      </div>
    </section>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    :host { display:block; }
    .anamnesis-admin { display:grid; gap:var(--espacio-4); }
    .anamnesis-admin__cabecera { display:flex; align-items:flex-start; justify-content:space-between; gap:var(--espacio-4); }
    .anamnesis-admin__cabecera h2 { margin:var(--espacio-1) 0 var(--espacio-2); }
    .anamnesis-admin__cabecera p:last-child { margin:0; color:var(--texto-suave); }
    .ceja { display:flex; align-items:center; gap:var(--espacio-2); margin:0; color:var(--acento); font-size:.74rem; font-weight:750; letter-spacing:.1em; }
    .nota-alcance { display:flex; align-items:flex-start; gap:var(--espacio-3); padding:var(--espacio-3) var(--espacio-4); border:1px solid var(--borde); border-left:4px solid var(--aviso); border-radius:var(--radio); background:var(--aviso-fondo); color:var(--aviso); }
    .nota-alcance p { margin:0; }
    .anamnesis-admin__rejilla { display:grid; grid-template-columns:minmax(280px,.78fr) minmax(0,1.5fr); gap:var(--espacio-4); align-items:start; }
    .tarjeta { min-width:0; }
    .seccion__titulo { display:flex; align-items:center; justify-content:space-between; gap:var(--espacio-3); margin-bottom:var(--espacio-3); }
    .seccion__titulo h3 { margin:0; }
    .lista-plantillas { display:grid; gap:var(--espacio-2); margin:0; padding:0; list-style:none; }
    .lista-plantillas li { display:flex; align-items:center; justify-content:space-between; gap:var(--espacio-2); padding:var(--espacio-3); border:1px solid var(--borde); border-radius:var(--radio); background:var(--superficie-elevada); }
    .lista-plantillas__activa { border-color:var(--acento) !important; box-shadow:inset 3px 0 var(--acento); }
    .lista-plantillas li > div { display:grid; gap:2px; min-width:0; }
    .lista-plantillas strong { overflow-wrap:anywhere; }
    .lista-plantillas small { color:var(--texto-suave); }
    .version { display:inline-flex; width:max-content; padding:1px 7px; border-radius:999px; background:var(--acento-suave); color:var(--acento-fuerte); font-size:.72rem; font-weight:700; }
    .vacio { color:var(--texto-suave); }
    .editor-plantilla { display:grid; min-height:260px; place-items:center; }
    .editor-vacio { display:grid; justify-items:center; gap:var(--espacio-2); max-width:480px; padding:var(--espacio-7) var(--espacio-4); text-align:center; color:var(--texto-suave); }
    .editor-vacio span { display:grid; width:58px; height:58px; place-items:center; border-radius:18px; background:var(--acento-suave); color:var(--acento); }
    .editor-vacio h3,.editor-vacio p { margin:0; }
    .datos-plantilla { display:grid; grid-template-columns:1fr 1fr; gap:var(--espacio-3); }
    .preguntas-cabecera { display:flex; align-items:center; justify-content:space-between; gap:var(--espacio-3); margin:var(--espacio-4) 0 var(--espacio-3); }
    .preguntas-cabecera h4 { margin:0; }
    .preguntas-cabecera h4 span { color:var(--texto-tenue); font-weight:500; }
    .preguntas-lista { display:grid; gap:var(--espacio-3); }
    .pregunta-editor { min-width:0; margin:0; padding:var(--espacio-3); border:1px solid var(--borde); border-radius:var(--radio); background:color-mix(in srgb,var(--superficie) 78%,transparent); }
    .pregunta-editor legend { padding:0 var(--espacio-2); color:var(--acento-fuerte); font-weight:700; }
    .pregunta-editor__fila { display:flex; align-items:end; gap:var(--espacio-3); }
    .pregunta-editor__fila .campo { flex:1 1 200px; min-width:0; }
    .requerida { display:flex; align-items:center; gap:var(--espacio-2); min-height:44px; padding-bottom:var(--espacio-4); white-space:nowrap; }
    @media(max-width:900px) { .anamnesis-admin__rejilla { grid-template-columns:1fr; } }
    @media(max-width:560px) { .anamnesis-admin__cabecera { flex-direction:column; } .pregunta-editor__fila { align-items:start; flex-wrap:wrap; } .datos-plantilla { grid-template-columns:1fr; } }
  `,
})
export class AnamnesisConfiguracionComponent implements OnInit {
  private readonly operaciones = inject(OperacionesService);
  protected readonly plantillas = signal<readonly PlantillaAnamnesis[]>([]);
  protected readonly plantillaActual = signal<PlantillaAnamnesis | null>(null);
  protected readonly cargando = signal(false);
  protected readonly guardando = signal(false);
  protected readonly error = signal('');
  protected readonly aviso = signal('');
  protected readonly idEditando = signal<string | null>(null);
  protected nombre = '';
  protected sensibilidad: Sensibilidad = 'N2';
  protected preguntas: PreguntaEditor[] = [];

  ngOnInit(): void { this.cargar(); }

  protected editando(): boolean { return this.idEditando() !== null || this.preguntas.length > 0; }

  protected cargar(): void {
    this.cargando.set(true);
    this.error.set('');
    this.operaciones.leer<PlantillaAnamnesis[]>('/historia/anamnesis/plantillas').subscribe({
      next: (plantillas) => { this.plantillas.set(plantillas); this.cargando.set(false); },
      error: (fallo: FalloApi) => { this.error.set(fallo.message); this.cargando.set(false); },
    });
  }

  protected nuevoBorrador(): void {
    this.idEditando.set(null);
    this.plantillaActual.set(null);
    this.nombre = '';
    this.sensibilidad = 'N2';
    this.preguntas = [this.preguntaVacia(1)];
    this.error.set('');
    this.aviso.set('');
  }

  protected editar(plantilla: PlantillaAnamnesis): void {
    this.idEditando.set(plantilla.id);
    this.plantillaActual.set(plantilla);
    this.nombre = plantilla.nombre;
    this.sensibilidad = plantilla.nivel_sensibilidad;
    this.preguntas = plantilla.preguntas.map((pregunta) => ({ ...pregunta, opcionesTexto: pregunta.opciones.join('\n') }));
    this.error.set('');
  }

  protected nuevaVersion(plantilla: PlantillaAnamnesis): void {
    this.guardando.set(true);
    this.error.set('');
    this.operaciones.analizar<PlantillaAnamnesis>(`/historia/anamnesis/plantillas/${plantilla.id}/nueva-version`).subscribe({
      next: (borrador) => {
        this.guardando.set(false);
        this.plantillaActual.set(borrador);
        this.idEditando.set(borrador.id);
        this.nombre = borrador.nombre;
        this.sensibilidad = borrador.nivel_sensibilidad;
        this.preguntas = borrador.preguntas.map((pregunta) => ({ ...pregunta, opcionesTexto: pregunta.opciones.join('\n') }));
        this.aviso.set(`Se creó la versión ${borrador.version} como borrador.`);
        this.cargar();
      },
      error: (fallo: FalloApi) => { this.error.set(fallo.message); this.guardando.set(false); },
    });
  }

  protected agregarPregunta(): void {
    if (this.preguntas.length < 40) this.preguntas = [...this.preguntas, this.preguntaVacia(this.preguntas.length + 1)];
  }

  protected quitarPregunta(indice: number): void {
    if (this.preguntas.length > 1) this.preguntas = this.preguntas.filter((_, i) => i !== indice);
  }

  protected cancelarEdicion(): void {
    this.idEditando.set(null);
    this.plantillaActual.set(null);
    this.preguntas = [];
    this.aviso.set('');
  }

  protected guardar(): void {
    this.error.set('');
    const payload = this.payload();
    if (!payload) return;
    const id = this.idEditando();
    this.guardando.set(true);
    const peticion = id
      ? this.operaciones.cambiar<PlantillaAnamnesis>(`/historia/anamnesis/plantillas/${id}`, payload)
      : this.operaciones.guardar<PlantillaAnamnesis>('/historia/anamnesis/plantillas', payload, crypto.randomUUID());
    peticion.subscribe({
      next: (plantilla) => {
        this.guardando.set(false);
        this.plantillaActual.set(plantilla);
        this.idEditando.set(plantilla.id);
        this.aviso.set(`Borrador v${plantilla.version} guardado. Puedes continuar editándolo o publicarlo.`);
        this.cargar();
      },
      error: (fallo: FalloApi) => { this.guardando.set(false); this.error.set(fallo.message); },
    });
  }

  protected publicar(): void {
    const id = this.idEditando();
    if (!id) return;
    this.guardando.set(true);
    this.error.set('');
    this.operaciones.analizar<PlantillaAnamnesis>(`/historia/anamnesis/plantillas/${id}/publicacion`).subscribe({
      next: (plantilla) => {
        this.guardando.set(false);
        this.plantillaActual.set(plantilla);
        this.idEditando.set(null);
        this.preguntas = [];
        this.aviso.set(`La versión ${plantilla.version} de «${plantilla.nombre}» está publicada para capturas nuevas.`);
        this.cargar();
      },
      error: (fallo: FalloApi) => { this.guardando.set(false); this.error.set(fallo.message); },
    });
  }

  protected estado(estado: PlantillaAnamnesis['estado']): string {
    return estado === 'PUBLICADA' ? 'Publicada' : estado === 'RETIRADA' ? 'Retirada' : 'Borrador';
  }

  private preguntaVacia(indice: number): PreguntaEditor {
    return { id: `pregunta_${indice}`, etiqueta: '', tipo: 'texto', obligatoria: false, ayuda: null, opciones: [], opcionesTexto: '' };
  }

  private payload(): { nombre: string; nivel_sensibilidad: Sensibilidad; preguntas: PreguntaPlantilla[] } | null {
    const preguntas: PreguntaPlantilla[] = this.preguntas.map((pregunta) => ({
      id: pregunta.id.trim(),
      etiqueta: pregunta.etiqueta.trim(),
      tipo: pregunta.tipo,
      obligatoria: pregunta.obligatoria,
      ayuda: pregunta.ayuda?.trim() || null,
      opciones: pregunta.tipo === 'seleccion' || pregunta.tipo === 'seleccion_multiple'
        ? pregunta.opcionesTexto.split('\n').map((opcion) => opcion.trim()).filter(Boolean)
        : [],
    }));
    if (!this.nombre.trim() || preguntas.some((pregunta) => !pregunta.id || !pregunta.etiqueta)) {
      this.error.set('Completa el nombre, el identificador y el texto de cada pregunta.');
      return null;
    }
    if (preguntas.some((pregunta) => ['seleccion', 'seleccion_multiple'].includes(pregunta.tipo) && !pregunta.opciones.length)) {
      this.error.set('Agrega al menos una opción a cada pregunta de selección.');
      return null;
    }
    if (new Set(preguntas.map((pregunta) => pregunta.id)).size !== preguntas.length) {
      this.error.set('Cada pregunta necesita un identificador distinto.');
      return null;
    }
    return { nombre: this.nombre.trim(), nivel_sensibilidad: this.sensibilidad, preguntas };
  }
}
