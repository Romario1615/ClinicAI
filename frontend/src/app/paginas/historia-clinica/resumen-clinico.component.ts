/**
 * «Antes de entrar»: lo que el profesional tiene que saber del paciente.
 *
 * Alergias primero y en rojo si son graves; después la medicación confirmada
 * con cómo la está tomando, las últimas notas y los planes en curso. Todo es
 * dato de la historia, sin interpretación.
 *
 * «Redactar con IA local» convierte ese resumen en un párrafo con un modelo
 * que corre en el servidor de la clínica. No se guarda y lleva su aviso: es
 * una ayuda de lectura, no una conclusión clínica.
 */
import { Component, effect, inject, input, output, signal, untracked, ChangeDetectionStrategy } from '@angular/core';
import { DatePipe, LowerCasePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { OperacionesService } from '../../nucleo/servicios/operaciones.service';
import { FalloApi } from '../../nucleo/servicios/api.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
import { AnamnesisCapturaComponent } from './anamnesis-captura.component';

export interface AlergiaResumen {
  readonly id: string;
  readonly sustancia: string;
  readonly reaccion: string | null;
  readonly severidad: string;
}

export interface ResumenClinico {
  readonly edad: number | null;
  readonly sexo: string | null;
  readonly alergias: readonly AlergiaResumen[];
  readonly antecedentes: readonly { categoria: string; descripcion: string; nivel_sensibilidad: string }[];
  readonly medicacion_activa: readonly {
    nombre: string;
    concentracion: string | null;
    dosis: string;
    via: string;
    cuando_sea_necesario: boolean;
    frecuencia_horas: number | null;
    duracion_dias: number | null;
    instrucciones: string | null;
    desde: string | null;
  }[];
  readonly adherencia: { dias: number; tomadas: number; omitidas: number; sin_registrar: number };
  readonly ultimas_notas: readonly {
    fecha: string;
    tipo: string;
    nivel_sensibilidad: 'N2' | 'N3';
    motivo_consulta: string | null;
    analisis: string | null;
    plan: string | null;
  }[];
  readonly planes: readonly { titulo: string; estado: string; procedimientos_pendientes: number; nivel_sensibilidad: 'N2' | 'N3' }[];
  readonly ultima_atencion: string | null;
  readonly proxima_cita: string | null;
  readonly redaccion_disponible: boolean;
}

@Component({
  selector: 'app-resumen-clinico',
  standalone: true,
  imports: [DatePipe, LowerCasePipe, FormsModule, VentanaFlotanteComponent, AnamnesisCapturaComponent],
  template: `
    <section class="resumen" aria-labelledby="titulo-resumen">
      <header class="resumen__cabecera">
        <div>
          <p class="ceja">ANTES DE ENTRAR</p>
          <h3 id="titulo-resumen">Resumen para la consulta</h3>
        </div>
        <div class="resumen__acciones">
          <!-- La anamnesis es un bloque largo (plantillas y capturas): se abre
               en una ventana y solo entonces se consulta. -->
          @if (puedeAccederAnamnesis()) {
            <button type="button" class="boton boton--pequeno" aria-haspopup="dialog" (click)="abrirAnamnesis()">
              Anamnesis
            </button>
          }
          @if (datos()?.redaccion_disponible) {
            <button type="button" class="boton boton--pequeno" [disabled]="redactando()" (click)="redactar()">
              {{ redactando() ? 'Redactando…' : 'Redactar con IA local' }}
            </button>
          }
        </div>
      </header>

      @if (cargando()) {
        <p class="resumen__nada" role="status">Cargando el resumen…</p>
      } @else if (error()) {
        <p class="resumen__aviso" role="alert">{{ error() }}</p>
      } @else if (datos()) {
        @let d = datos()!;
        <!-- En la historia la columna desplaza dentro de su marco; en la ficha
             del paciente fluye con el resto. -->
        <div class="resumen__cuerpo desplazable" tabindex="0" role="region" aria-label="Contenido del resumen para la consulta">
          @if (redaccion(); as r) {
            <div class="redaccion" role="note">
              <p class="redaccion__texto">{{ r.texto }}</p>
              <p class="redaccion__aviso">{{ r.aviso }} Modelo: {{ r.modelo }}.</p>
            </div>
          }
          @if (errorRedaccion()) { <p class="resumen__aviso" role="alert">{{ errorRedaccion() }}</p> }
          @if (errorAnamnesis() && !formularioAlergia() && !formularioAntecedente() && !alergiaDesactivando()) { <p class="resumen__aviso" role="alert">{{ errorAnamnesis() }}</p> }
          @if (avisoAnamnesis()) { <p class="resumen__aviso" role="status">{{ avisoAnamnesis() }}</p> }

          <div class="rejilla">
            <div class="bloque" [class.bloque--alerta]="hayAlergiaGrave()">
              <div class="bloque__cabecera"><h4>Alergias</h4>
                @if (puedeEditarAnamnesis()) { <button type="button" class="boton boton--pequeno" (click)="abrirFormularioAlergia()">Añadir alergia</button> }
              </div>
              @for (a of d.alergias; track a.id) {
                <div class="registro-clinico"><p><strong>{{ a.sustancia }}</strong> · {{ severidad(a.severidad) }}@if (a.reaccion) { · {{ a.reaccion }} }</p>
                  @if (puedeEditarAnamnesis() && alergiaDesactivando() !== a.id) { <button class="boton boton--texto" type="button" (click)="abrirDesactivacion(a.id)">Desactivar</button> }
                  @if (alergiaDesactivando() === a.id) {
                    <app-ventana-flotante ceja="Seguridad clínica" [titulo]="'Desactivar alergia: ' + a.sustancia" forma="centrada" [anchoMaximo]="520" [cierraAlPulsarFuera]="false" (cerrar)="cerrarDesactivacion()">
                      <p>El registro y el motivo se conservarán en el historial clínico.</p>
                      <form id="form-desactivar-alergia" (ngSubmit)="desactivarAlergia(a.id)">
                        <label class="campo"><span class="campo__etiqueta">Motivo para desactivar</span><input class="campo__control" name="motivo-desactivacion" [(ngModel)]="motivoDesactivacion" minlength="5" maxlength="500" required /></label>
                      </form>
                      @if (errorAnamnesis()) { <p class="resumen__aviso" role="alert">{{ errorAnamnesis() }}</p> }
                      <div pie class="acciones-anamnesis">
                        <button class="boton boton--pequeno" type="button" (click)="cerrarDesactivacion()" [disabled]="guardandoAnamnesis()">Cancelar</button>
                        <button class="boton boton--principal boton--pequeno" type="submit" form="form-desactivar-alergia" [disabled]="guardandoAnamnesis() || motivoDesactivacion.trim().length < 5">{{ guardandoAnamnesis() ? 'Guardando…' : 'Confirmar desactivación' }}</button>
                      </div>
                    </app-ventana-flotante>
                  }
                </div>
              } @empty { <p class="resumen__nada">Sin alergias registradas.</p> }
              @if (formularioAlergia()) {
                <app-ventana-flotante ceja="Historia clínica" titulo="Registrar alergia" forma="centrada" [anchoMaximo]="560" [cierraAlPulsarFuera]="false" (cerrar)="cerrarFormularioAlergia()">
                  <p>Registra la sustancia y la reacción observada. La severidad describe el registro y no la interpreta el sistema.</p>
                  <form id="form-nueva-alergia" class="formulario-anamnesis" (ngSubmit)="registrarAlergia()">
                    <label class="campo"><span class="campo__etiqueta">Sustancia</span><input class="campo__control" name="sustancia" [(ngModel)]="nuevaSustancia" minlength="2" maxlength="200" required /></label>
                    <label class="campo"><span class="campo__etiqueta">Reacción observada</span><input class="campo__control" name="reaccion" [(ngModel)]="nuevaReaccion" maxlength="200" /></label>
                    <label class="campo"><span class="campo__etiqueta">Severidad registrada</span><select class="campo__control" name="severidad" [(ngModel)]="nuevaSeveridad"><option value="LEVE">Leve</option><option value="MODERADA">Moderada</option><option value="GRAVE">Grave</option><option value="ANAFILAXIA">Anafilaxia</option></select></label>
                  </form>
                  @if (errorAnamnesis()) { <p class="resumen__aviso" role="alert">{{ errorAnamnesis() }}</p> }
                  <div pie class="acciones-anamnesis">
                    <button class="boton boton--pequeno" type="button" (click)="cerrarFormularioAlergia()" [disabled]="guardandoAnamnesis()">Cancelar</button>
                    <button class="boton boton--principal boton--pequeno" type="submit" form="form-nueva-alergia" [disabled]="guardandoAnamnesis() || nuevaSustancia.trim().length < 2">{{ guardandoAnamnesis() ? 'Guardando…' : 'Guardar alergia registrada' }}</button>
                  </div>
                </app-ventana-flotante>
              }
            </div>

            <div class="bloque">
              <div class="bloque__cabecera"><h4>Antecedentes</h4>
                @if (puedeEditarAnamnesis()) { <button type="button" class="boton boton--pequeno" (click)="abrirFormularioAntecedente()">Añadir antecedente</button> }
              </div>
              @for (a of d.antecedentes; track a.descripcion) { <p><span class="tenue">{{ categoriaAntecedente(a.categoria) }}:</span> {{ a.descripcion }} @if (a.nivel_sensibilidad === 'N3') { <span class="insignia-sensible">Acceso sensible · N3</span> }</p> }
              @empty { <p class="resumen__nada">Sin antecedentes registrados.</p> }
              @if (formularioAntecedente()) {
                <app-ventana-flotante ceja="Historia clínica" titulo="Registrar antecedente" forma="centrada" [anchoMaximo]="620" [cierraAlPulsarFuera]="false" (cerrar)="cerrarFormularioAntecedente()">
                  <p>Selecciona la categoría y el nivel de sensibilidad que corresponde al registro.</p>
                  <form id="form-nuevo-antecedente" class="formulario-anamnesis" (ngSubmit)="registrarAntecedente()">
                    <label class="campo"><span class="campo__etiqueta">Categoría</span><select class="campo__control" name="categoria" [(ngModel)]="nuevaCategoria"><option value="PERSONAL">Personal</option><option value="FAMILIAR">Familiar</option><option value="QUIRURGICO">Quirúrgico</option><option value="FARMACOLOGICO">Farmacológico</option><option value="HABITOS">Hábitos</option><option value="OTRO">Otro</option></select></label>
                    <label class="campo"><span class="campo__etiqueta">Descripción</span><textarea class="campo__control" name="descripcion-antecedente" [(ngModel)]="nuevaDescripcion" minlength="3" maxlength="4000" required></textarea></label>
                    <label class="campo"><span class="campo__etiqueta">Sensibilidad</span><select class="campo__control" name="sensibilidad-antecedente" [(ngModel)]="nuevoNivelSensibilidad"><option value="N2">Clínica · N2</option>@if (puedeLeerSensible()) { <option value="N3">Clínica sensible · N3</option> }</select><span class="campo__ayuda">Los antecedentes N3 solo aparecen con permiso sensible y generan auditoría reforzada.</span></label>
                  </form>
                  @if (errorAnamnesis()) { <p class="resumen__aviso" role="alert">{{ errorAnamnesis() }}</p> }
                  <div pie class="acciones-anamnesis">
                    <button class="boton boton--pequeno" type="button" (click)="cerrarFormularioAntecedente()" [disabled]="guardandoAnamnesis()">Cancelar</button>
                    <button class="boton boton--principal boton--pequeno" type="submit" form="form-nuevo-antecedente" [disabled]="guardandoAnamnesis() || nuevaDescripcion.trim().length < 3">{{ guardandoAnamnesis() ? 'Guardando…' : 'Guardar antecedente' }}</button>
                  </div>
                </app-ventana-flotante>
              }
            </div>

            <div class="bloque">
              <h4>Medicación activa</h4>
              @for (m of d.medicacion_activa; track $index) {
                <p>
                  <strong>{{ m.nombre }}@if (m.concentracion) { {{ m.concentracion }} }</strong> · {{ m.dosis }} · {{ m.via | lowercase }}
                  · {{ m.cuando_sea_necesario ? 'cuando sea necesario' : m.frecuencia_horas ? 'cada ' + m.frecuencia_horas + ' h' : 'pauta sin frecuencia' }}
                  @if (m.duracion_dias) { · {{ m.duracion_dias }} días }
                </p>
              } @empty { <p class="resumen__nada">Sin medicación confirmada.</p> }
              <p class="adherencia">
                Últimos {{ d.adherencia.dias }} días:
                <strong class="numerico">{{ d.adherencia.tomadas }}</strong> tomadas ·
                <strong class="numerico" [class.alerta]="d.adherencia.omitidas > 0">{{ d.adherencia.omitidas }}</strong> omitidas ·
                <strong class="numerico">{{ d.adherencia.sin_registrar }}</strong> sin registrar
              </p>
            </div>

            <div class="bloque">
              <h4>Evolución reciente</h4>
              @for (n of d.ultimas_notas; track $index) {
                <p>
                  <span class="numerico">{{ n.fecha | date: 'dd/MM/yy' }}</span> ·
                  <strong>{{ n.motivo_consulta || 'Sin motivo registrado' }}</strong>
                  @if (n.plan) { <br /><span class="tenue">Plan: {{ n.plan }}</span> }
                </p>
              } @empty { <p class="resumen__nada">Sin notas.</p> }
            </div>

            <div class="bloque">
              <h4>Tratamiento y citas</h4>
              @for (p of d.planes; track p.titulo) {
                <p><strong>{{ p.titulo }}</strong> · {{ estadoPlan(p.estado) }} · {{ p.procedimientos_pendientes }} procedimiento(s) pendiente(s) @if (p.nivel_sensibilidad === 'N3') { <span class="insignia-sensible">Acceso sensible · N3</span> }</p>
              } @empty { <p class="resumen__nada">Sin planes en curso.</p> }
              <p class="tenue">
                Última atención: {{ d.ultima_atencion ? (d.ultima_atencion | date: 'dd/MM/yy') : 'sin registro' }} ·
                Próxima cita: {{ d.proxima_cita ? (d.proxima_cita | date: 'dd/MM/yy HH:mm') : 'sin agendar' }}
              </p>
            </div>
          </div>
        </div>
      }
    </section>
    @if (anamnesisAbierta()) {
      <app-ventana-flotante
        ceja="Registro asistencial"
        titulo="Anamnesis del paciente"
        [anchoMaximo]="760"
        [altoCompleto]="true"
        (cerrar)="cerrarAnamnesis()"
      >
        <app-anamnesis-captura [pacienteId]="pacienteId()" />
      </app-ventana-flotante>
    }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    :host { display: block; min-width: 0; }
    /* El anfitrión puede ocultarse con [hidden] (pestaña inactiva): sin esta
       regla el display del modo «llena» lo volvería a mostrar. */
    :host([hidden]) { display: none !important; }
    .resumen { display: grid; gap: var(--espacio-3); padding: var(--espacio-4); border: 1px solid var(--borde); border-radius: var(--radio); background: var(--superficie-elevada); }
    .resumen__cabecera { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: var(--espacio-2) var(--espacio-3); }
    .resumen__acciones { display: flex; flex-wrap: wrap; gap: var(--espacio-2); }
    .resumen__cuerpo { display: grid; align-content: start; gap: var(--espacio-3); min-width: 0; }
    .resumen__cuerpo:focus-visible { outline: 3px solid var(--acento); outline-offset: 2px; }
    .resumen__cabecera h3 { margin: 0; font-size: 1.05rem; }
    .ceja { margin: 0; color: var(--acento); font-size: 0.7rem; font-weight: 700; letter-spacing: 0.1em; }
    .resumen__nada { margin: 0; color: var(--texto-tenue); font-size: 0.88rem; }
    .resumen__aviso { margin: 0; color: var(--aviso); font-size: 0.88rem; }
    .rejilla { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: var(--espacio-3); }
    .bloque { padding: var(--espacio-3); border-radius: var(--radio); background: var(--superficie); border: 1px solid var(--superficie-hundida); }
    .bloque h4 { margin: 0 0 var(--espacio-2); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--texto-suave); }
    .bloque__cabecera { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--espacio-2); margin-bottom: var(--espacio-2); }
    .bloque__cabecera h4 { margin: 0; }
    .registro-clinico { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; }
    .registro-clinico p { flex: 1 1 200px; }
    .boton--texto { padding: 0; border: 0; background: transparent; color: var(--texto-suave); font: inherit; font-size: .78rem; text-decoration: underline; cursor: pointer; }
    .formulario-anamnesis { display: grid; gap: var(--espacio-2); margin-top: var(--espacio-3); padding-top: var(--espacio-3); border-top: 1px solid var(--borde); }
    .acciones-anamnesis { display: flex; justify-content: flex-end; gap: var(--espacio-2); }
    .bloque h4.sub { margin-top: var(--espacio-3); }
    .bloque p { margin: 0 0 var(--espacio-1); font-size: 0.88rem; }
    .bloque--alerta { border-color: color-mix(in srgb, var(--peligro) 45%, transparent); background: var(--peligro-fondo); }
    .bloque--alerta h4 { color: var(--peligro); }
    .adherencia { margin-top: var(--espacio-2) !important; color: var(--texto-suave); }
    .alerta { color: var(--aviso); }
    .tenue { color: var(--texto-suave); }
    .insignia-sensible { display:inline-flex; margin-left:var(--espacio-1); padding:1px 7px; border:1px solid color-mix(in srgb,var(--aviso) 40%,transparent); border-radius:999px; background:var(--aviso-fondo); color:var(--aviso); font-size:.72rem; font-weight:700; }
    .redaccion { padding: var(--espacio-3); border-radius: var(--radio); background: var(--acento-suave); }
    .redaccion__texto { margin: 0 0 var(--espacio-2); white-space: pre-line; }
    .redaccion__aviso { margin: 0; font-size: 0.78rem; color: var(--texto-suave); }

    /* Modo «llena» (columna de la historia en escritorio): la cabecera queda
       fija y los bloques desplazan dentro de su marco. */
    @media (min-width: 821px) and (min-height: 600px) {
      :host(.llena) { display: flex; flex-direction: column; min-height: 0; }
      :host(.llena) .resumen { display: flex; flex: 1 1 0; flex-direction: column; min-height: 0; padding: var(--espacio-3) var(--espacio-4); }
      :host(.llena) .resumen__cuerpo { padding-right: 2px; }
    }
  `,
})
export class ResumenClinicoComponent {
  private readonly api = inject(OperacionesService);
  private readonly sesion = inject(SesionService);
  readonly pacienteId = input.required<string>();
  /**
   * Alergias de cada carga del resumen. La historia las repite en la cabecera
   * del paciente para que sigan a la vista en todas las pestañas.
   */
  readonly alergiasCargadas = output<readonly AlergiaResumen[]>();

  protected readonly datos = signal<ResumenClinico | null>(null);
  protected readonly cargando = signal(true);
  protected readonly error = signal('');
  protected readonly redactando = signal(false);
  protected readonly errorRedaccion = signal('');
  protected readonly redaccion = signal<{ texto: string; modelo: string; aviso: string } | null>(null);
  protected readonly formularioAlergia = signal(false);
  protected readonly formularioAntecedente = signal(false);
  protected readonly anamnesisAbierta = signal(false);
  protected readonly alergiaDesactivando = signal<string | null>(null);
  protected readonly guardandoAnamnesis = signal(false);
  protected readonly avisoAnamnesis = signal('');
  protected readonly errorAnamnesis = signal('');
  protected nuevaSustancia = '';
  protected nuevaReaccion = '';
  protected nuevaSeveridad = 'MODERADA';
  protected nuevaCategoria = 'PERSONAL';
  protected nuevaDescripcion = '';
  protected nuevoNivelSensibilidad = 'N2';
  protected motivoDesactivacion = '';
  private pacienteActualId: string | null = null;

  protected puedeEditarAnamnesis(): boolean {
    return this.sesion.tienePermiso('historia_clinica.escribir') &&
      !!this.sesion.identidad()?.profesional_id;
  }

  protected puedeAccederAnamnesis(): boolean {
    return this.sesion.tienePermiso('historia_clinica.leer') || this.puedeEditarAnamnesis();
  }

  protected abrirAnamnesis(): void {
    this.anamnesisAbierta.set(true);
  }

  protected cerrarAnamnesis(): void {
    this.anamnesisAbierta.set(false);
  }

  protected abrirFormularioAlergia(): void {
    if (!this.puedeEditarAnamnesis() || this.guardandoAnamnesis()) return;
    this.formularioAntecedente.set(false);
    this.alergiaDesactivando.set(null);
    this.nuevaSustancia = '';
    this.nuevaReaccion = '';
    this.nuevaSeveridad = 'MODERADA';
    this.errorAnamnesis.set('');
    this.formularioAlergia.set(true);
  }

  protected cerrarFormularioAlergia(): void {
    if (this.guardandoAnamnesis()) return;
    this.formularioAlergia.set(false);
    this.nuevaSustancia = '';
    this.nuevaReaccion = '';
    this.nuevaSeveridad = 'MODERADA';
    this.errorAnamnesis.set('');
  }

  protected abrirFormularioAntecedente(): void {
    if (!this.puedeEditarAnamnesis() || this.guardandoAnamnesis()) return;
    this.formularioAlergia.set(false);
    this.alergiaDesactivando.set(null);
    this.nuevaCategoria = 'PERSONAL';
    this.nuevaDescripcion = '';
    this.nuevoNivelSensibilidad = 'N2';
    this.errorAnamnesis.set('');
    this.formularioAntecedente.set(true);
  }

  protected cerrarFormularioAntecedente(): void {
    if (this.guardandoAnamnesis()) return;
    this.formularioAntecedente.set(false);
    this.nuevaCategoria = 'PERSONAL';
    this.nuevaDescripcion = '';
    this.nuevoNivelSensibilidad = 'N2';
    this.errorAnamnesis.set('');
  }

  protected puedeLeerSensible(): boolean {
    return this.sesion.tienePermiso('historia_clinica.leer_sensible');
  }

  constructor() {
    effect(() => {
      const id = this.pacienteId();
      untracked(() => {
        if (this.pacienteActualId !== null && this.pacienteActualId !== id) this.limpiarFormularioClinico();
        this.pacienteActualId = id;
        this.cargar(id);
      });
    });
  }

  private limpiarFormularioClinico(): void {
    this.formularioAlergia.set(false);
    this.formularioAntecedente.set(false);
    this.anamnesisAbierta.set(false);
    this.alergiaDesactivando.set(null);
    this.guardandoAnamnesis.set(false);
    this.nuevaSustancia = '';
    this.nuevaReaccion = '';
    this.nuevaSeveridad = 'MODERADA';
    this.nuevaCategoria = 'PERSONAL';
    this.nuevaDescripcion = '';
    this.nuevoNivelSensibilidad = 'N2';
    this.motivoDesactivacion = '';
    this.errorAnamnesis.set('');
    this.avisoAnamnesis.set('');
    this.errorRedaccion.set('');
    this.redaccion.set(null);
  }

  private cargar(id: string): void {
    this.cargando.set(true);
    this.error.set('');
    this.redaccion.set(null);
    this.api.leer<ResumenClinico>(`/historia/pacientes/${id}/resumen-clinico`).subscribe({
      next: (datos) => {
        if (id !== this.pacienteId()) return;
        this.datos.set(datos);
        this.cargando.set(false);
        this.alergiasCargadas.emit(datos.alergias);
      },
      error: (fallo: FalloApi) => {
        if (id !== this.pacienteId()) return;
        this.cargando.set(false);
        this.error.set(fallo.estado === 404 ? 'La información clínica solicitada no está disponible con este acceso.' : fallo.message);
      },
    });
  }

  protected redactar(): void {
    this.redactando.set(true);
    this.errorRedaccion.set('');
    this.api
      .guardar<{ texto: string; modelo: string; aviso: string }>(
        `/historia/pacientes/${this.pacienteId()}/resumen-clinico/redaccion`,
        {},
        crypto.randomUUID(),
      )
      .subscribe({
        next: (redaccion) => {
          this.redactando.set(false);
          this.redaccion.set(redaccion);
        },
        error: (fallo: FalloApi) => {
          this.redactando.set(false);
          this.errorRedaccion.set(fallo.message);
        },
      });
  }

  protected registrarAlergia(): void {
    this.enviarAnamnesis('alergias', {
      sustancia: this.nuevaSustancia.trim(),
      tipo_reaccion: this.nuevaReaccion.trim() || null,
      severidad: this.nuevaSeveridad,
    }, 'Alergia registrada.');
  }

  protected registrarAntecedente(): void {
    this.enviarAnamnesis('antecedentes', {
      categoria: this.nuevaCategoria,
      descripcion: this.nuevaDescripcion.trim(),
      nivel_sensibilidad: this.nuevoNivelSensibilidad,
    }, 'Antecedente registrado.');
  }

  protected abrirDesactivacion(id: string): void {
    if (!this.puedeEditarAnamnesis() || this.guardandoAnamnesis()) return;
    this.formularioAlergia.set(false);
    this.formularioAntecedente.set(false);
    this.alergiaDesactivando.set(id);
    this.motivoDesactivacion = '';
    this.errorAnamnesis.set('');
  }

  protected cerrarDesactivacion(): void {
    if (this.guardandoAnamnesis()) return;
    this.alergiaDesactivando.set(null);
    this.motivoDesactivacion = '';
    this.errorAnamnesis.set('');
  }

  protected desactivarAlergia(id: string): void {
    if (this.motivoDesactivacion.trim().length < 5) return;
    const pacienteId = this.pacienteId();
    this.guardandoAnamnesis.set(true);
    this.errorAnamnesis.set('');
    this.api.guardar(
      `/historia/pacientes/${pacienteId}/anamnesis/alergias/${id}/desactivacion`,
      { motivo: this.motivoDesactivacion.trim() },
      crypto.randomUUID(),
    ).subscribe({
      next: () => {
        if (pacienteId !== this.pacienteId()) return;
        this.alergiaDesactivando.set(null);
        this.guardandoAnamnesis.set(false);
        this.avisoAnamnesis.set('Alergia desactivada; su registro y motivo se conservaron.');
        this.cargar(pacienteId);
      },
      error: (fallo: FalloApi) => {
        if (pacienteId !== this.pacienteId()) return;
        this.guardandoAnamnesis.set(false);
        this.errorAnamnesis.set(fallo.message);
      },
    });
  }

  protected categoriaAntecedente(categoria: string): string {
    return ({ PERSONAL: 'Personal', FAMILIAR: 'Familiar', QUIRURGICO: 'Quirúrgico', FARMACOLOGICO: 'Farmacológico', HABITOS: 'Hábitos', OTRO: 'Otro' } as Record<string, string>)[categoria] ?? categoria;
  }

  private enviarAnamnesis(
    tipo: 'alergias' | 'antecedentes', datos: unknown, mensaje: string,
  ): void {
    const pacienteId = this.pacienteId();
    this.guardandoAnamnesis.set(true);
    this.errorAnamnesis.set('');
    this.avisoAnamnesis.set('');
    this.api.guardar(
      `/historia/pacientes/${pacienteId}/anamnesis/${tipo}`,
      datos,
      crypto.randomUUID(),
    ).subscribe({
      next: () => {
        if (pacienteId !== this.pacienteId()) return;
        this.guardandoAnamnesis.set(false);
        this.formularioAlergia.set(false);
        this.formularioAntecedente.set(false);
        this.nuevaSustancia = '';
        this.nuevaReaccion = '';
        this.nuevaDescripcion = '';
        this.avisoAnamnesis.set(mensaje);
        this.cargar(pacienteId);
      },
      error: (fallo: FalloApi) => {
        if (pacienteId !== this.pacienteId()) return;
        this.guardandoAnamnesis.set(false);
        this.errorAnamnesis.set(fallo.message);
      },
    });
  }

  protected hayAlergiaGrave(): boolean {
    return (this.datos()?.alergias ?? []).some((a) => a.severidad === 'GRAVE' || a.severidad === 'ANAFILAXIA');
  }

  protected severidad(valor: string): string {
    return ({ LEVE: 'leve', MODERADA: 'moderada', GRAVE: 'grave', ANAFILAXIA: 'anafilaxia' } as Record<string, string>)[valor] ?? valor.toLowerCase();
  }

  protected estadoPlan(valor: string): string {
    return ({ BORRADOR: 'borrador', PROPUESTO: 'propuesto', ACEPTADO: 'en curso' } as Record<string, string>)[valor] ?? valor.toLowerCase();
  }
}
