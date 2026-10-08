import { Component, computed, effect, inject, input, signal } from '@angular/core';
import { DatePipe, DecimalPipe, NgTemplateOutlet } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { DestroyRef } from '@angular/core';
import { catchError } from 'rxjs';
import { CONFIGURACION, PERMISOS } from '../../nucleo/servicios/configuracion';
import { traducirFallo } from '../../nucleo/servicios/api.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
import { IndicePlacaComponent } from './indice-placa.component';
import { CapturaFotosComponent, type FotoSeleccionada } from '../../compartido/captura-fotos.component';
import { FotosRegistroComponent } from '../../compartido/fotos-registro.component';
import { FotosRegistroService } from '../../nucleo/servicios/fotos-registro.service';
import { SITIOS_PERIO, compararPeriodontogramas, piezaVacia, sitioVacio, type Periodontograma, type PiezaPerio, type SitioPerio } from './periodontograma.modelos';

@Component({selector:'app-periodontograma', standalone:true, imports:[FormsModule, DatePipe, DecimalPipe, NgTemplateOutlet, VentanaFlotanteComponent, IndicePlacaComponent, CapturaFotosComponent, FotosRegistroComponent],
  templateUrl:'./periodontograma.component.html', styleUrl:'./periodontograma.component.scss'})
export class PeriodontogramaComponent {
  private readonly http = inject(HttpClient);
  private readonly config = inject(CONFIGURACION);
  private readonly sesion = inject(SesionService);
  private readonly destruir = inject(DestroyRef);
  private readonly catalogo = inject(CatalogoService);
  protected readonly sedes = signal<readonly {id:string; nombre:string}[]>([]);
  protected readonly corrigiendo = signal(false);
  protected sede = '';
  protected readonly operacionFotos = inject(FotosRegistroService).operacion<Periodontograma>();
  protected fotos: readonly FotoSeleccionada[]=[];
  protected readonly puedeLeerFotos = computed(()=>this.sesion.tienePermiso(PERMISOS.imagenClinicaLeer));
  readonly pacienteId = input.required<string>();
  readonly citaId = input<string | null>(null);
  protected readonly registros = signal<readonly Periodontograma[]>([]);
  protected readonly elegido = signal<string | null>(null);
  protected readonly previo = signal<string | null>(null);
  protected readonly actual = computed(() => this.registros().find(r=>r.id===this.elegido()) ?? this.registros()[0] ?? null);
  protected readonly comparacion = computed(() => {
    const a=this.actual(), b=this.registros().find(r=>r.id===this.previo());
    return a && b ? compararPeriodontogramas(a,b) : null;
  });
  protected readonly puedeEscribir = computed(()=>this.sesion.tienePermiso(PERMISOS.odontogramaEscribir));
  protected readonly error = signal('');
  protected readonly ocupado = signal(false);
  protected readonly editor = signal(false);
  protected readonly piezaElegida = signal<number | null>(null);
  protected readonly vista = signal<'V'|'L'>('V');
  protected readonly placa = signal(false);
  protected readonly sitios = SITIOS_PERIO;
  protected readonly arcadas = [
    {nombre:'Superior', piezas:[18,17,16,15,14,13,12,11,21,22,23,24,25,26,27,28]},
    {nombre:'Inferior', piezas:[48,47,46,45,44,43,42,41,31,32,33,34,35,36,37,38]},
  ];
  protected borrador: Record<string,PiezaPerio> = {};
  protected pieza: PiezaPerio = piezaVacia();
  protected fecha = '';
  protected motivo = '';
  protected observaciones = '';
  protected nivel: 'N2'|'N3' = 'N2';
  private base: Periodontograma | null = null;
  private clave = crypto.randomUUID();
  private secuencia = 0;

  constructor() { effect(()=> { const id=this.pacienteId(); this.cargar(id); }); }
  private ruta(id=this.pacienteId()): string { return `${this.config.urlApi}/odontologia/pacientes/${id}/periodontogramas`; }
  protected cargar(id=this.pacienteId()): void {
    const numero=++this.secuencia; this.error.set('');
    this.http.get<readonly Periodontograma[]>(this.ruta(id)).pipe(catchError(traducirFallo), takeUntilDestroyed(this.destruir)).subscribe({
      next: r=>{if(numero===this.secuencia) this.registros.set(r);},
      error: e=>{if(numero===this.secuencia) this.error.set(e.message);},
    });
  }
  protected nuevo(corregir=false): void {
    this.operacionFotos.reiniciar(); this.fotos=[];
    this.base=corregir ? this.actual() : null;
    this.corrigiendo.set(!!this.base);
    this.sede=this.base?.sede_id ?? '';
    this.catalogo.sedes().pipe(takeUntilDestroyed(this.destruir)).subscribe({next:s=>this.sedes.set(s),error:()=>this.sedes.set([])});
    this.borrador=this.base ? structuredClone(this.base.piezas) : {};
    this.fecha=this.base?.fecha_examen ?? new Date().toLocaleDateString('sv-SE');
    this.motivo=''; this.observaciones=this.base?.observaciones ?? ''; this.nivel=this.base?.nivel_sensibilidad ?? 'N2';
    this.clave=crypto.randomUUID(); this.error.set(''); this.editor.set(true); this.piezaElegida.set(null);
  }
  protected abrirPieza(codigo:number): void {
    if(this.operacionFotos.guardado || this.ocupado()) return;
    this.piezaElegida.set(codigo); this.pieza=structuredClone(this.borrador[codigo] ?? piezaVacia());
    for(const {id} of this.sitios) this.pieza.sitios[id] ??= sitioVacio();
  }
  protected confirmarPieza(): void {
    const codigo=this.piezaElegida(); if(codigo===null) return;
    const p=structuredClone(this.pieza);
    if(p.ausente) {p.sitios={}; p.implante=false; p.movilidad=null; p.furcacion=null;}
    if(p.implante) {p.movilidad=null; p.furcacion=null;}
    this.borrador={...this.borrador, [codigo]:p}; this.piezaElegida.set(null);
  }
  protected valor(codigo:number, sitio:SitioPerio): number | null { return (this.editor() ? this.borrador : this.actual()?.piezas)?.[codigo]?.sitios[sitio]?.profundidad ?? null; }
  protected sitiosVista(): readonly SitioPerio[] { return this.vista()==='V' ? ['VM','VC','VD'] : ['LM','LC','LD']; }
  protected ausente(codigo:number): boolean { return (this.editor() ? this.borrador : this.actual()?.piezas)?.[codigo]?.ausente ?? false; }
  protected altura(codigo:number, sitio:SitioPerio): number { return Math.max(2,(this.valor(codigo,sitio) ?? 0)*6); }
  protected guardar(anular=false): void {
    if(this.ocupado() || this.motivo.trim().length<8 || !this.fecha) return;
    this.ocupado.set(true); this.error.set('');
    const cuerpo={clave_idempotencia:this.clave, version_anterior_id:this.base?.id ?? null,
      fecha_examen:this.fecha, cita_id:this.base ? this.base.cita_id : this.citaId(), sede_id:this.base ? this.base.sede_id : this.sede || null,
      piezas:this.borrador, observaciones:this.observaciones.trim() || null, motivo:this.motivo.trim(), nivel_sensibilidad:this.nivel, anulado:anular};
    this.operacionFotos.guardar('periodontograma',this.http.post<Periodontograma>(this.ruta(),cuerpo).pipe(catchError(traducirFallo)), anular ? [] : this.fotos).pipe(takeUntilDestroyed(this.destruir)).subscribe({
      next: r=>{this.ocupado.set(false); this.editor.set(false); this.elegido.set(r.id); this.cargar();},
      error: e=>{this.error.set(e.message); this.ocupado.set(false);},
    });
  }
  protected descargar(): void {
    const r=this.actual(); if(!r || this.ocupado()) return;
    this.ocupado.set(true);
    this.http.get(`${this.ruta()}/${r.id}/pdf`,{responseType:'blob'}).pipe(catchError(traducirFallo), takeUntilDestroyed(this.destruir)).subscribe({
      next: b=>{const url=URL.createObjectURL(b); const a=document.createElement('a'); a.href=url; a.download='periodontograma.pdf'; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000); this.ocupado.set(false);},
      error:e=>{this.error.set(e.message); this.ocupado.set(false);},
    });
  }
}
