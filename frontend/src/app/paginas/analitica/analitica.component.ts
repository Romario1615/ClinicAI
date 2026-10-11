import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient, HttpParams } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { catchError } from 'rxjs';
import { CONFIGURACION } from '../../nucleo/servicios/configuracion';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { traducirFallo } from '../../nucleo/servicios/api.service';
import { IconoComponent, type NombreIcono } from '../../compartido/icono.component';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
import { type AnaliticaDashboard, type KpiAnalitico, grupoIndicador, GRUPOS_INDICADORES } from './analitica.modelos';
import { GraficoKpiComponent } from './grafico-kpi.component';

type TipoAnalisis = 'descriptivo' | 'predictivo' | 'prescriptivo';

@Component({
  selector: 'app-analitica',
  host: { class: 'pantalla' },
  standalone: true,
  imports: [FormsModule, RouterLink, DatePipe, DecimalPipe, GraficoKpiComponent,
    IconoComponent, VentanaFlotanteComponent],
  templateUrl: './analitica.component.html',
  styleUrl: './analitica.component.scss',
})
export class AnaliticaComponent {
  private readonly http = inject(HttpClient);
  private readonly config = inject(CONFIGURACION);
  private readonly catalogo = inject(CatalogoService);
  private readonly destruir = inject(DestroyRef);
  protected readonly datos = signal<AnaliticaDashboard | null>(null);
  protected readonly error = signal('');
  protected readonly ocupado = signal(false);
  protected readonly tab = signal<TipoAnalisis>('descriptivo');
  protected readonly sedes = signal<readonly { id: string; nombre: string }[]>([]);
  protected readonly busqueda = signal('');
  protected readonly grupo = signal('todos');
  protected readonly detalle = signal<KpiAnalitico | null>(null);
  protected readonly mostrarLimites = signal(false);
  protected readonly mostrarFiltros = signal(false);
  protected readonly filtrosAplicados = signal<{ dias: number; horizonte: number } | null>(null);
  protected readonly grupoIndicador = grupoIndicador;
  protected readonly grupos = computed(() => GRUPOS_INDICADORES.filter(g =>
    this.datos()?.kpis.some(k => grupoIndicador(k.clave).clave === g.clave)));
  protected readonly indicadores = computed(() => {
    const texto = this.normalizar(this.busqueda());
    return (this.datos()?.kpis ?? []).filter(k =>
      (this.grupo() === 'todos' || grupoIndicador(k.clave).clave === this.grupo()) &&
      this.normalizar(`${k.nombre} ${k.definicion} ${k.unidad}`).includes(texto));
  });
  protected readonly modelosEvaluados = computed(() =>
    this.datos()?.kpis.filter(k => k.evidencia.estado === 'validado_localmente').length ?? 0);
  protected readonly vistas: readonly {
    clave: TipoAnalisis; nombre: string; ayuda: string; icono: NombreIcono;
  }[] = [
    { clave: 'descriptivo', nombre: 'Descriptivo', ayuda: 'qué pasó', icono: 'metricas' },
    { clave: 'predictivo', nombre: 'Predictivo', ayuda: 'qué puede pasar', icono: 'analisis-ia' },
    { clave: 'prescriptivo', nombre: 'Prescriptivo', ayuda: 'qué revisar', icono: 'revision-operativa' },
  ];
  protected dias = 180;
  protected horizonte = 14;
  protected sede = '';
  private secuencia = 0;

  constructor() {
    this.catalogo.sedes().pipe(catchError(traducirFallo), takeUntilDestroyed(this.destruir))
      .subscribe({ next: s => this.sedes.set(s), error: () => this.sedes.set([]) });
    this.cargar();
  }

  protected cargar(): void {
    const n = ++this.secuencia;
    const filtros = { dias: this.dias, horizonte: this.horizonte };
    this.ocupado.set(true);
    this.error.set('');
    this.detalle.set(null);
    this.mostrarLimites.set(false);
    this.mostrarFiltros.set(false);
    let params = new HttpParams().set('dias', this.dias).set('horizonte', this.horizonte);
    if (this.sede) params = params.set('sede_id', this.sede);
    this.http.get<AnaliticaDashboard>(`${this.config.urlApi}/dashboard/analitica`, { params })
      .pipe(catchError(traducirFallo), takeUntilDestroyed(this.destruir)).subscribe({
        next: d => {
          if (n !== this.secuencia) return;
          this.datos.set(d);
          this.filtrosAplicados.set(filtros);
          if (this.grupo() !== 'todos' && !this.grupos().some(g => g.clave === this.grupo())) {
            this.grupo.set('todos');
          }
          this.ocupado.set(false);
        },
        error: e => {
          if (n !== this.secuencia) return;
          this.error.set(e.message);
          this.ocupado.set(false);
          this.datos.set(null);
        },
      });
  }

  protected limpiarFiltros(): void {
    this.busqueda.set('');
    this.grupo.set('todos');
  }

  protected estado(valor: string): string {
    return ({ insuficiente: 'Falta historial', experimental: 'En evaluación',
      validado_localmente: 'Evaluado con datos locales' } as Record<string, string>)[valor] ?? valor;
  }

  protected generado(fecha: string): string {
    return new Intl.DateTimeFormat('es-EC', {
      dateStyle: 'short', timeStyle: 'short', timeZone: this.datos()?.zona_horaria ?? 'UTC',
    }).format(new Date(fecha));
  }

  private normalizar(texto: string): string {
    return texto.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('es').trim();
  }
}
