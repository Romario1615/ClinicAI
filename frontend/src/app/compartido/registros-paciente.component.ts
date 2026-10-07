import { ChangeDetectionStrategy, Component, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService, Receta } from '../nucleo/servicios/api.service';
import { CatalogoService } from '../nucleo/servicios/catalogo.service';
import { EspecialidadHistoriaService } from '../nucleo/servicios/especialidad-historia.service';
import { SesionService } from '../nucleo/servicios/sesion.service';
import { guardarPdf, PartidaDocumento, PuntoFacial, RegistroPaciente, RegistrosPacienteService, ZonaFacial } from '../nucleo/servicios/registros-paciente.service';
import { Sede } from '../nucleo/modelos/dominio';
import { MapaFacialComponent } from './mapa-facial.component';
import { VentanaFlotanteComponent } from './ventana-flotante.component';

@Component({
  selector: 'app-registros-paciente', standalone: true,
  imports: [FormsModule, DatePipe, DecimalPipe, MapaFacialComponent, VentanaFlotanteComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './registros-paciente.component.html', styleUrl: './registros-paciente.component.scss',
})
export class RegistrosPacienteComponent {
  private readonly api = inject(RegistrosPacienteService);
  private readonly pacientes = inject(ApiService);
  private readonly catalogo = inject(CatalogoService);
  protected readonly especialidades = inject(EspecialidadHistoriaService);
  protected readonly sesion = inject(SesionService);
  readonly pacienteId = input.required<string>();
  readonly citaId = input<string | null>(null);
  readonly facial = input(false);
  readonly sedeId = input<string | null>(null);
  protected readonly registros = signal<RegistroPaciente[]>([]);
  protected readonly puntos = signal<PuntoFacial[]>([]);
  protected readonly sedes = signal<readonly Sede[]>([]);
  protected readonly recetas = signal<readonly Receta[]>([]);
  protected readonly cargando = signal(false);
  protected readonly ocupado = signal(false);
  protected readonly error = signal('');
  protected readonly aviso = signal('');
  protected readonly historico = signal(false);
  protected readonly editor = signal(false);
  protected readonly esEdicion = signal(false);
  protected readonly hayMas = signal(false);
  protected readonly seleccionado = signal<RegistroPaciente | null>(null);
  protected readonly anularRegistro = signal<RegistroPaciente | null>(null);
  protected readonly enviarRegistro = signal<RegistroPaciente | null>(null);
  protected readonly detalleZona = signal<string | null>(null);
  protected readonly listado = computed(() => this.registros().filter(r => (r.tipo === 'FACIOGRAMA') === this.facial()));
  protected readonly puedeEscribir = computed(() => this.sesion.tienePermiso('historia_clinica.escribir') && !!this.sesion.identidad()?.profesional_id);
  protected titulo = '';
  protected tipo: RegistroPaciente['tipo'] = 'PRESUPUESTO';
  protected motivo = '';
  protected observaciones = '';
  protected moneda = 'USD';
  protected validoHasta = '';
  protected recetaId = '';
  protected sedeElegida = '';
  protected sensible = false;
  protected partidas: PartidaDocumento[] = [];
  protected zonas: ZonaFacial[] = [];
  protected zonaElegida = '';
  protected zonaEstado: ZonaFacial['estado'] = 'OBSERVACION';
  protected zonaObservacion = '';
  protected zonaProcedimiento = '';
  protected confirmoDestinatario = false;
  private claveGuardado = crypto.randomUUID();
  private claveEnvio = crypto.randomUUID();
  private versionEditando: RegistroPaciente | null = null;
  private turnoCarga = 0;

  constructor() {
    effect(() => {
      const especialidad = this.especialidades.elegida()?.id;
      const paciente = this.pacienteId();
      this.facial();
      if (especialidad && paciente) untracked(() => this.cargar());
    });
    this.catalogo.sedes().subscribe({ next: sedes => this.sedes.set(sedes), error: () => this.error.set('No se pudieron cargar las sedes.') });
  }
  protected cargar(ampliar = false): void {
    const especialidad = this.especialidades.elegida()?.id;
    if (!especialidad) return;
    const turno = ++this.turnoCarga;
    this.cargando.set(true); this.error.set('');
    if (!ampliar) { this.seleccionado.set(null); this.registros.set([]); }
    this.api.listar(this.pacienteId(), especialidad, this.historico(), this.facial(), ampliar ? this.registros().length : 0).subscribe({
      next: registros => { if (turno !== this.turnoCarga) return; this.hayMas.set(registros.length === 50); this.registros.update(anteriores => ampliar ? [...anteriores, ...registros] : registros); if (!ampliar) this.seleccionado.set(this.listado().find(r => r.vigente && !r.anulado) ?? this.listado()[0] ?? null); this.cargando.set(false); },
      error: error => { if (turno === this.turnoCarga) { this.error.set(error.message); this.cargando.set(false); } },
    });
    if (this.facial()) this.api.zonas().subscribe({ next: puntos => this.puntos.set(puntos), error: error => this.error.set(error.message) });
  }
  protected editar(registro: RegistroPaciente | null = null): void {
    this.error.set(''); this.aviso.set(''); this.versionEditando = registro; this.esEdicion.set(!!registro); this.claveGuardado = crypto.randomUUID();
    this.tipo = registro?.tipo ?? (this.facial() ? 'FACIOGRAMA' : 'PRESUPUESTO');
    this.titulo = registro?.titulo ?? (this.facial() ? 'Evaluación y seguimiento facial' : 'Presupuesto de atención');
    this.zonas = structuredClone(registro?.contenido.zonas ?? []);
    this.partidas = structuredClone(registro?.contenido.partidas ?? [{ descripcion: '', cantidad: 1, precio_unitario: 0 }]);
    this.observaciones = registro?.contenido.observaciones ?? ''; this.moneda = registro?.contenido.moneda ?? 'USD';
    this.validoHasta = registro?.contenido.valido_hasta ?? ''; this.motivo = registro ? '' : 'Registro inicial';
    this.recetaId = ''; this.sedeElegida = registro?.sede_id ?? this.sedeId() ?? ''; this.sensible = registro?.nivel_sensibilidad === 'N3';
    this.zonaElegida = ''; this.zonaObservacion = ''; this.zonaProcedimiento = ''; this.editor.set(true);
    if (!this.facial() && this.sesion.tienePermiso('receta.leer')) this.pacientes.recetas(this.pacienteId()).subscribe({ next: recetas => this.recetas.set(recetas.filter(r => r.estado === 'CONFIRMADA')), error: error => this.error.set(error.message) });
  }
  protected propia(registro: RegistroPaciente): boolean { return registro.profesional_id === this.sesion.identidad()?.profesional_id; }
  protected elegirZona(codigo: string): void {
    this.zonaElegida = codigo;
    const zona = this.zonas.find(z => z.zona === codigo);
    this.zonaEstado = zona?.estado ?? 'OBSERVACION'; this.zonaObservacion = zona?.observacion ?? ''; this.zonaProcedimiento = zona?.procedimiento ?? '';
  }
  protected registrarZona(): void {
    if (!this.zonaElegida || !this.zonaObservacion.trim()) return;
    this.zonas = [...this.zonas.filter(z => z.zona !== this.zonaElegida), { zona: this.zonaElegida, estado: this.zonaEstado, observacion: this.zonaObservacion.trim(), procedimiento: this.zonaProcedimiento.trim() || null }];
    this.zonaElegida = '';
  }
  protected quitarZona(codigo: string): void { this.zonas = this.zonas.filter(z => z.zona !== codigo); if (this.zonaElegida === codigo) this.zonaElegida = ''; }
  protected nombreZona(codigo: string): string { return this.puntos().find(p => p.codigo === codigo)?.nombre ?? codigo; }
  protected agregarPartida(): void { this.partidas = [...this.partidas, { descripcion: '', cantidad: 1, precio_unitario: 0 }]; }
  protected quitarPartida(indice: number): void { this.partidas = this.partidas.filter((_, i) => i !== indice); }
  protected total(partidas = this.partidas): number {
    // Cantidad y precio tienen dos decimales: calcular con enteros evita
    // diferencias de redondeo respecto al Decimal del PDF del servidor.
    return partidas.reduce((total, p) => total + Math.floor((Math.round(Number(p.cantidad) * 100) * Math.round(Number(p.precio_unitario) * 100) + 50) / 100), 0) / 100;
  }
  protected guardar(): void {
    const especialidad = this.especialidades.elegida()?.id;
    if (!especialidad || this.ocupado()) return;
    if (this.zonaElegida && this.zonaObservacion.trim()) this.registrarZona();
    const registro = this.versionEditando;
    this.ocupado.set(true); this.error.set('');
    this.api.guardar(this.pacienteId(), {
      clave_idempotencia: this.claveGuardado, tipo: this.tipo, titulo: this.titulo,
      especialidad_id: especialidad, sede_id: this.sedeElegida || null, cita_id: registro ? registro.cita_id : this.citaId(),
      raiz_id: registro?.raiz_id ?? null, version_base: registro?.version ?? 0, motivo: this.motivo,
      nivel_sensibilidad: this.sensible ? 'N3' : 'N2', zonas: this.facial() ? this.zonas : [],
      partidas: this.facial() || this.tipo === 'RECETA' ? [] : this.partidas,
      receta_id: this.tipo === 'RECETA' ? this.recetaId || null : null,
      moneda: this.moneda, valido_hasta: this.validoHasta || null, observaciones: this.observaciones,
    }).subscribe({ next: () => { this.ocupado.set(false); this.editor.set(false); this.aviso.set('Versión guardada en la historia del paciente.'); this.cargar(); }, error: error => { this.ocupado.set(false); this.error.set(error.message); } });
  }
  protected descargar(registro: RegistroPaciente): void {
    this.error.set(''); this.ocupado.set(true);
    this.api.pdf(this.pacienteId(), registro.id).subscribe({ next: pdf => { guardarPdf(pdf, `ClinicAI-${registro.tipo.toLowerCase()}-v${registro.version}.pdf`); this.ocupado.set(false); }, error: error => { this.error.set(error.message); this.ocupado.set(false); } });
  }
  protected pedirAnulacion(registro: RegistroPaciente): void { this.motivo = ''; this.error.set(''); this.anularRegistro.set(registro); }
  protected anular(): void {
    const registro = this.anularRegistro(); if (!registro || this.ocupado()) return;
    this.ocupado.set(true);
    this.api.anular(this.pacienteId(), registro.id, this.motivo).subscribe({ next: () => { this.ocupado.set(false); this.anularRegistro.set(null); this.aviso.set('Registro anulado; el historial permanece disponible.'); this.cargar(); }, error: error => { this.ocupado.set(false); this.error.set(error.message); } });
  }
  protected pedirEnvio(registro: RegistroPaciente): void { this.error.set(''); this.confirmoDestinatario = false; this.claveEnvio = crypto.randomUUID(); this.enviarRegistro.set(registro); }
  protected enviar(): void {
    const registro = this.enviarRegistro(); if (!registro || !this.confirmoDestinatario || this.ocupado()) return;
    this.ocupado.set(true);
    this.api.compartir(this.pacienteId(), registro.id, this.claveEnvio).subscribe({
      next: entrega => { this.ocupado.set(false); this.enviarRegistro.set(null); this.aviso.set(entrega.modo === 'sandbox' ? 'Solicitud registrada en WhatsApp sandbox. El proveedor real aún no está configurado.' : `Envío registrado: ${entrega.estado}. Consulte su entrega en Mensajes.`); },
      error: error => { this.ocupado.set(false); this.error.set(error.message); },
    });
  }
  protected cerrarEditor(): void { if (!this.ocupado()) this.editor.set(false); }
}
