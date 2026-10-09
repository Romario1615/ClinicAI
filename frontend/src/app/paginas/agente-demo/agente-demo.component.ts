import { Component, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { forkJoin } from 'rxjs';

import { SelectorPacienteComponent } from '../../compartido/selector-paciente.component';
import { InsigniaEstadoComponent } from '../../compartido/insignia-estado.component';
import { CargandoComponent } from '../../compartido/estados.component';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
import { ChatConversacionalComponent } from '../../compartido/chat-conversacional.component';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { OperacionesService } from '../../nucleo/servicios/operaciones.service';
import { FalloApi } from '../../nucleo/servicios/api.service';
import { hoyEnZona, rangoDelDia, sumarDias } from '../../nucleo/utilidades/fechas';
import type { EstadoCita, Paciente, Profesional, Sede, Servicio } from '../../nucleo/modelos/dominio';

interface RespuestaDemo {
  sesion_id: string; modo: string; mensaje: string; requiere_humano: boolean;
  herramientas: string[];
  datos: {
    turnos?: { inicio: string; fin: string }[];
    citas?: { cita_id: string; inicio: string; estado: EstadoCita }[];
    cita_id?: string; inicio?: string; expira_en?: string; zona_horaria?: string;
  };
}
interface Mensaje { autor: 'Usted' | 'Asistente'; texto: string; respuesta?: RespuestaDemo }

@Component({
  selector: 'app-agente-demo', standalone: true,
  imports: [FormsModule, SelectorPacienteComponent, InsigniaEstadoComponent, CargandoComponent, VentanaFlotanteComponent, ChatConversacionalComponent],
  host: { class: 'pantalla' },
  templateUrl: './agente-demo.component.html', changeDetection: ChangeDetectionStrategy.Eager,
 styleUrl: './agente-demo.component.scss',
})
export class AgenteDemoComponent {
  private readonly catalogo = inject(CatalogoService);
  private readonly api = inject(OperacionesService);
  protected readonly sedes = signal<readonly Sede[]>([]);
  protected readonly servicios = signal<readonly Servicio[]>([]);
  protected readonly profesionales = signal<readonly Profesional[]>([]);
  protected readonly paciente = signal<Paciente | null>(null);
  protected readonly sedeId = signal('');
  protected readonly servicioId = signal('');
  protected profesionalId = '';
  protected fecha = '';
  protected modo: 'simulado' | 'configurado' = 'simulado';
  protected texto = '';
  protected readonly cargando = signal(true);
  protected readonly cargandoProfesionales = signal(false);
  protected readonly ocupado = signal(false);
  protected readonly error = signal('');
  protected readonly sesionId = signal('');
  protected readonly preparando = signal(false);
  protected readonly mensajes = signal<Mensaje[]>([]);
  protected readonly requiereHumano = signal(false);
  protected readonly respuestaActual = signal<RespuestaDemo | null>(null);
  protected readonly pendiente = signal<{ texto: string; clave: string } | null>(null);
  protected readonly zona = computed(() => this.sedes().find(s => s.id === this.sedeId())?.zona_horaria ?? 'America/Guayaquil');
  protected readonly turnos = computed(() => this.respuestaActual()?.datos.turnos?.slice(0, 5) ?? []);
  protected readonly sugerencias = computed(() => [
    'Buscar horarios', ...(this.puedeConfirmar() ? ['Confirmar cita'] : []), 'Mis citas', 'Mis pagos', 'Hablar con una persona',
  ]);
  protected readonly puedeConfirmar = computed(() => !!this.respuestaActual()?.datos.expira_en);
  private apertura = { cuerpo: '', clave: '' };
  private consultaProfesionales = 0;

  constructor() { this.cargar(); }

  protected cargar(): void {
    this.cargando.set(true); this.error.set('');
    forkJoin({ sedes: this.catalogo.sedes(), servicios: this.catalogo.servicios() }).subscribe({
      next: datos => {
        this.sedes.set(datos.sedes); this.servicios.set(datos.servicios);
        this.sedeId.set(datos.sedes[0]?.id ?? ''); this.servicioId.set(datos.servicios[0]?.id ?? '');
        this.fecha = sumarDias(hoyEnZona(this.zona()), 1);
        this.cargando.set(false); this.cambiarSeleccion();
      },
      error: (e: unknown) => { this.error.set(this.mensajeError(e)); this.cargando.set(false); },
    });
  }

  protected cambiarSeleccion(): void {
    const consulta = ++this.consultaProfesionales;
    this.profesionalId = ''; this.profesionales.set([]);
    const especialidadId = this.servicios().find(s => s.id === this.servicioId())?.especialidad_id;
    if (!this.sedeId() || !especialidadId) return;
    this.cargandoProfesionales.set(true);
    this.catalogo.profesionales({ sedeId: this.sedeId(), especialidadId }).subscribe({
      next: lista => {
        if (consulta !== this.consultaProfesionales) return;
        this.profesionales.set(lista); this.profesionalId = lista[0]?.id ?? '';
        this.cargandoProfesionales.set(false);
      },
      error: (e: unknown) => {
        if (consulta !== this.consultaProfesionales) return;
        this.cargandoProfesionales.set(false); this.error.set(this.mensajeError(e));
      },
    });
  }

  protected iniciar(): void {
    if (!this.paciente() || !this.fecha || !this.profesionalId || this.ocupado()) return;
    const rango = rangoDelDia(this.fecha, this.zona());
    const datos = { modo: this.modo, paciente_id: this.paciente()!.id, sede_id: this.sedeId(), servicio_id: this.servicioId(),
      profesional_id: this.profesionalId, desde: rango.desde,
      hasta: rangoDelDia(sumarDias(this.fecha, 6), this.zona()).hasta };
    const cuerpo = JSON.stringify(datos);
    if (this.apertura.cuerpo !== cuerpo) this.apertura = { cuerpo, clave: crypto.randomUUID() };
    this.ocupado.set(true); this.error.set('');
    this.api.guardar<RespuestaDemo>('/agente-demo/sesiones', datos, this.apertura.clave).subscribe({
      next: respuesta => {
        this.sesionId.set(respuesta.sesion_id); this.preparando.set(false); this.recibir(respuesta); this.ocupado.set(false);
      },
      error: (e: unknown) => { this.error.set(this.mensajeError(e)); this.ocupado.set(false); },
    });
  }

  protected enviar(texto = this.texto): void {
    texto = texto.trim();
    if (!this.sesionId() || !texto || texto.length > 1000 || this.ocupado() || this.requiereHumano()) return;
    let peticion = this.pendiente();
    if (!peticion) {
      peticion = { texto, clave: crypto.randomUUID() }; this.pendiente.set(peticion);
      this.mensajes.update(lista => [...lista, { autor: 'Usted', texto }]);
    }
    this.ocupado.set(true); this.error.set('');
    this.api.guardar<RespuestaDemo>(`/agente-demo/sesiones/${this.sesionId()}/mensajes`,
      { texto: peticion.texto }, peticion.clave).subscribe({
      next: respuesta => {
        this.recibir(respuesta); this.texto = ''; this.pendiente.set(null); this.ocupado.set(false);
      },
      error: (e: unknown) => { this.error.set(this.mensajeError(e)); this.ocupado.set(false); },
    });
  }

  protected elegir(indice: number): void { this.enviar(String(indice + 1)); }

  protected nueva(): void {
    if (this.ocupado()) return;
    this.sesionId.set(''); this.mensajes.set([]); this.respuestaActual.set(null);
    this.requiereHumano.set(false); this.pendiente.set(null); this.error.set(''); this.texto = '';
    this.apertura = { cuerpo: '', clave: '' };
  }

  protected fechaHora(instante: string): string {
    return new Intl.DateTimeFormat('es-EC', { timeZone: this.zona(), dateStyle: 'medium', timeStyle: 'short' }).format(new Date(instante));
  }

  private recibir(respuesta: RespuestaDemo): void {
    this.respuestaActual.set(respuesta); this.requiereHumano.set(respuesta.requiere_humano);
    this.mensajes.update(lista => [...lista, { autor: 'Asistente', texto: respuesta.mensaje, respuesta }]);
  }

  private mensajeError(e: unknown): string {
    return e instanceof FalloApi ? e.message : 'No se pudieron cargar los datos. Inténtelo de nuevo.';
  }
}
