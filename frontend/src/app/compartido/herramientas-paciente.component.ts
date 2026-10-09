import { Component, computed, inject, input, output, signal } from '@angular/core';
import { Router } from '@angular/router';
import { EspecialidadHistoriaService, type ModuloHistoria } from '../nucleo/servicios/especialidad-historia.service';
import { SesionService } from '../nucleo/servicios/sesion.service';
import { OperacionesService } from '../nucleo/servicios/operaciones.service';
import { VentanaFlotanteComponent } from './ventana-flotante.component';

export type HerramientaHistoria = 'evolucion' | 'recetas' | 'indicaciones' | 'documentos' | 'faciograma' | 'odontograma' | 'formulario033' | 'periodoncia' | 'imagenes' | 'planes';
interface Herramienta { clave: HerramientaHistoria; nombre: string; detalle: string; lectura: string; escritura: string; modulo?: ModuloHistoria }
interface OpcionHerramienta extends Herramienta { disponible: boolean; especialidadId?: string; especialidadNombre?: string | null; editable: boolean }
const HERRAMIENTAS: readonly Herramienta[] = [
  { clave: 'evolucion', nombre: 'Evolución y antecedentes', detalle: 'Alergias, anamnesis, notas y versiones de la historia.', lectura: 'historia_clinica.leer', escritura: 'historia_clinica.escribir' },
  { clave: 'recetas', nombre: 'Recetas', detalle: 'Prescripciones y seguimiento de sus versiones.', lectura: 'receta.leer', escritura: 'receta.crear' },
  { clave: 'indicaciones', nombre: 'Indicaciones', detalle: 'Orientaciones registradas y entrega al paciente.', lectura: 'historia_clinica.leer', escritura: 'historia_clinica.escribir' },
  { clave: 'documentos', nombre: 'Documentos y PDF', detalle: 'Presupuestos, cotizaciones y documentos de recetas.', lectura: 'historia_clinica.leer', escritura: 'historia_clinica.escribir' },
  { clave: 'odontograma', nombre: 'Odontograma', detalle: 'Piezas, superficies e historial dental.', lectura: 'odontograma.leer', escritura: 'odontograma.escribir', modulo: 'odontograma' },
  { clave: 'periodoncia', nombre: 'Periodontograma e índice de placa', detalle: '32 piezas, seis sitios, controles y evolución periodontal.', lectura: 'odontograma.leer', escritura: 'odontograma.escribir', modulo: 'periodoncia' },
  { clave: 'formulario033', nombre: 'Formulario 033', detalle: 'Historia odontológica MSP. Requiere acceso clínico sensible.', lectura: 'historia_clinica.leer_sensible', escritura: 'historia_clinica.escribir', modulo: 'odontograma' },
  { clave: 'planes', nombre: 'Planes de tratamiento', detalle: 'Fases, procedimientos, presupuesto y seguimiento.', lectura: 'plan_tratamiento.leer', escritura: 'plan_tratamiento.escribir', modulo: 'planes' },
  { clave: 'faciograma', nombre: 'Faciograma', detalle: 'Mapa facial, puntos, observaciones y seguimiento estético.', lectura: 'historia_clinica.leer', escritura: 'historia_clinica.escribir', modulo: 'faciograma' },
  { clave: 'imagenes', nombre: 'Fotos y radiografías', detalle: 'Archivo de imágenes clínicas y evolución visual.', lectura: 'imagen_clinica.leer', escritura: 'imagen_clinica.cargar', modulo: 'imagenes' },
];

@Component({
  selector: 'app-herramientas-paciente', standalone: true, imports: [VentanaFlotanteComponent],
  template: `
    <div class="barra">
      <div><strong>Herramientas del paciente</strong><span>{{ especialidades.elegida()?.nombre || 'Historia clínica' }} · {{ especialidades.puedeRegistrar() ? 'Registro según especialidad' : 'Solo consulta' }}</span></div>
      <button class="boton boton--principal boton--pequeno" type="button" (click)="abierta.set(true)">Elegir qué registrar</button>
    </div>
    @if (abierta()) {
      <app-ventana-flotante titulo="Herramientas del paciente" ceja="Consulta y atención" forma="centrada" [anchoMaximo]="860" [ocupada]="iniciando()" (cerrar)="!iniciando() && abierta.set(false)">
        <p class="campo__ayuda">Disponibles desde la creación del paciente. Cada sección conserva sus registros y comienza vacía hasta la primera atención. El registro depende de su rol y especialidad.</p>
        @if (puedeIniciar()) { <p class="campo__ayuda">Para empezar una primera atención sin cita, pulse Comenzar atención. Quedará registrado como profesional responsable.</p> }
        @if (error()) { <p class="aviso-error" role="alert">{{ error() }}</p> }
        <div class="herramientas">
          @for (opcion of opciones(); track opcion.clave) {
            <button class="herramienta" type="button" [disabled]="!opcion.disponible || iniciando()" (click)="abrir(opcion)">
              <strong>{{ opcion.nombre }}</strong><span>{{ opcion.detalle }}</span>
              <small>{{ opcion.disponible ? (opcion.editable ? 'Consultar y registrar' : 'Solo consulta') : 'Requiere acceso sensible' }}@if(opcion.especialidadNombre){ · {{ opcion.especialidadNombre }} }</small>
            </button>
          }
        </div>
        <div pie class="acciones">
          @if(puedeIniciar()){<button class="boton boton--principal" type="button" [disabled]="iniciando()" (click)="iniciarAtencion()">{{ iniciando() ? 'Iniciando…' : 'Comenzar atención sin cita' }}</button>}
          @if(sesion.tienePermiso('agenda.leer')){<button class="boton" type="button" [disabled]="iniciando()" (click)="ir('/agenda')">Gestionar citas</button>}
          @if(sesion.tienePermiso('pago.leer')){<button class="boton" type="button" [disabled]="iniciando()" (click)="ir('/pagos')">Pagos del paciente</button>}
          <button class="boton" type="button" [disabled]="iniciando()" (click)="!iniciando() && abierta.set(false)">Cerrar</button>
        </div>
      </app-ventana-flotante>
    }
  `,
  styles: `:host{display:block;min-width:0}.barra{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:12px 16px;background:var(--acento-suave);border:1px solid var(--borde);border-radius:var(--radio)}.barra>div{display:grid;gap:4px;min-width:0}.barra strong{font-size:.85rem}.barra span{font-size:.75rem;color:var(--texto-suave);overflow-wrap:anywhere}.herramientas{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.herramienta{display:flex;flex-direction:column;gap:8px;min-width:0;text-align:left;padding:16px;border:1px solid var(--borde);border-radius:var(--radio);background:var(--superficie-elevada);color:var(--texto);font:inherit;cursor:pointer}.herramienta:hover:not(:disabled){border-color:var(--acento);background:var(--acento-suave)}.herramienta:focus-visible{outline:3px solid var(--acento);outline-offset:3px}.herramienta span{font-size:.8rem;color:var(--texto-suave);overflow-wrap:anywhere}.herramienta small{font-weight:650;color:var(--acento)}.herramienta:disabled{cursor:default;opacity:.8}.acciones{display:flex;gap:8px;flex-wrap:wrap}@media(max-width:560px){.herramientas{grid-template-columns:1fr}.barra{padding:10px}.barra .boton{width:100%}}`,
})
export class HerramientasPacienteComponent {
  protected readonly sesion = inject(SesionService);
  protected readonly especialidades = inject(EspecialidadHistoriaService);
  private readonly router = inject(Router);
  private readonly api = inject(OperacionesService);
  readonly pacienteId = input.required<string>();
  readonly citaId = input<string | null>(null);
  readonly elegida = output<HerramientaHistoria>();
  protected readonly abierta = signal(false);
  protected readonly iniciando = signal(false);
  protected readonly error = signal('');
  protected readonly puedeIniciar = computed(() => !this.citaId() && this.especialidades.puedeRegistrar() && this.sesion.tienePermiso('historia_clinica.escribir'));
  private claveInicio = crypto.randomUUID();
  protected readonly opciones = computed<OpcionHerramienta[]>(() => HERRAMIENTAS.flatMap(herramienta => {
    const seleccionada = this.especialidades.elegida();
    const especialidad = !herramienta.modulo ? seleccionada :
      (seleccionada?.modulos.includes(herramienta.modulo) ? seleccionada : this.especialidades.disponibles().find(e => e.modulos.includes(herramienta.modulo!)));
    if (herramienta.modulo && !especialidad) return [];
    const disponible = this.sesion.tienePermiso(herramienta.lectura);
    if (!disponible && herramienta.clave !== 'formulario033') return [];
    return [{ ...herramienta, disponible, especialidadId: especialidad?.id, especialidadNombre: herramienta.modulo ? especialidad?.nombre : null,
      editable: disponible && especialidad?.propia === true && !!this.sesion.identidad()?.profesional_id && this.sesion.tienePermiso(herramienta.escritura) }];
  }));
  protected abrir(opcion: OpcionHerramienta): void {
    if (!opcion.disponible || this.iniciando()) return;
    if (opcion.especialidadId) this.especialidades.elegir(opcion.especialidadId);
    this.abierta.set(false);
    this.elegida.emit(opcion.clave);
  }
  protected ir(ruta: string): void { if (this.iniciando()) return; this.abierta.set(false); void this.router.navigate([ruta], { queryParams: { paciente: this.pacienteId(), cita: this.citaId() } }); }
  protected iniciarAtencion(): void {
    if (!this.puedeIniciar() || this.iniciando()) return;
    this.iniciando.set(true); this.error.set('');
    this.api.guardar(`/pacientes/${this.pacienteId()}/atencion-profesional`, { motivo: 'Atención presencial sin cita iniciada por el profesional.' }, this.claveInicio).subscribe({
      next: () => { this.iniciando.set(false); this.claveInicio = crypto.randomUUID(); this.abierta.set(false); this.elegida.emit('evolucion'); },
      error: error => { this.iniciando.set(false); this.error.set(error.message); },
    });
  }
}
