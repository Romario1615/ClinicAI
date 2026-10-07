/**
 * Promociones por WhatsApp.
 *
 * Lo que esta pantalla tiene que dejar claro
 * ------------------------------------------
 * **La IA propone; una persona aprueba.** La imagen generada aparece como
 * propuesta, se puede regenerar o sustituir por una subida a mano, y nada sale
 * a ningún paciente hasta que alguien con permiso de aprobación lo decide.
 *
 * **Solo llega a quien aceptó publicidad.** La audiencia se muestra como un
 * número de pacientes con consentimiento de promociones vigente. No se listan
 * pacientes: esta pantalla es de marketing, no de fichas.
 *
 * **Sin datos clínicos.** El segmento solo filtra por sede y por la antigüedad
 * de la última visita. No hay filtro por tratamiento ni por diagnóstico.
 */
import { Component, DestroyRef, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { IconoComponent } from '../../compartido/icono.component';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
import { ApiService, FalloApi } from '../../nucleo/servicios/api.service';
import type { Campana, EstadoCampana } from '../../nucleo/servicios/api.service';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { PERMISOS } from '../../nucleo/servicios/configuracion';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import type { Sede } from '../../nucleo/modelos/dominio';

const ESTADOS: Record<EstadoCampana, { texto: string; tono: string }> = {
  BORRADOR: { texto: 'Borrador', tono: 'neutro' },
  APROBADA: { texto: 'Aprobada', tono: 'info' },
  ENVIADA: { texto: 'Enviada', tono: 'exito' },
  CANCELADA: { texto: 'Cancelada', tono: 'neutro' },
};

type Audiencia = 'todos' | 'reactivar' | 'recientes';

import { ResumenModuloComponent } from '../../compartido/resumen-modulo.component';
@Component({
  selector: 'app-promociones',
  standalone: true,
  imports: [ResumenModuloComponent, DatePipe, FormsModule, IconoComponent, VentanaFlotanteComponent],
  templateUrl: './promociones.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './promociones.component.scss',
})
export class PromocionesComponent {
  private readonly api = inject(ApiService);
  private readonly catalogo = inject(CatalogoService);
  private readonly sesion = inject(SesionService);

  protected readonly campanas = signal<readonly Campana[]>([]);
  protected readonly sedes = signal<readonly Sede[]>([]);
  protected readonly seleccionada = signal<Campana | null>(null);
  protected readonly imagenUrl = signal<string | null>(null);
  protected readonly audiencia = signal<number | null>(null);
  protected readonly cargando = signal(true);
  protected readonly trabajando = signal(false);
  protected readonly generando = signal(false);
  protected readonly error = signal('');
  protected readonly exito = signal('');
  protected readonly creando = signal(false);

  protected readonly puedeAprobar = computed(() =>
    this.sesion.tienePermiso(PERMISOS.promocionAprobar),
  );

  // --- Formulario de campaña nueva ---
  protected nombre = '';
  protected texto = '';
  protected plantillaMeta = 'promocion_clinica';
  protected sedeId = '';
  protected tipoAudiencia: Audiencia = 'todos';
  protected dias = 180;

  // --- Acciones sobre la seleccionada ---
  protected descripcionImagen = '';
  protected programadaPara = '';
  protected motivoCancelacion = '';
  protected readonly pidiendoCancelacion = signal(false);

  protected readonly estados = ESTADOS;

  constructor() {
    this.cargar();
    this.catalogo.sedes().subscribe({ next: (sedes) => this.sedes.set(sedes), error: () => undefined });
    inject(DestroyRef).onDestroy(() => this.liberarImagen());
  }

  protected cargar(): void {
    this.cargando.set(true);
    this.api.campanas().subscribe({
      next: (lista) => {
        this.campanas.set(lista);
        this.cargando.set(false);
        const actual = this.seleccionada();
        if (actual) {
          const fresca = lista.find((c) => c.id === actual.id);
          if (fresca) this.seleccionada.set(fresca);
        }
      },
      error: (fallo: unknown) => {
        this.error.set(this.mensaje(fallo));
        this.cargando.set(false);
      },
    });
  }

  // ======================================================================
  //  Crear
  // ======================================================================
  protected abrirCreacion(): void {
    this.nombre = '';
    this.texto = '';
    this.plantillaMeta = 'promocion_clinica';
    this.sedeId = '';
    this.tipoAudiencia = 'todos';
    this.dias = 180;
    this.error.set('');
    this.creando.set(true);
  }

  protected cerrarCreacion(): void {
    if (!this.trabajando()) this.creando.set(false);
  }

  protected crear(): void {
    if (this.trabajando()) return;
    const segmento = {
      sede_id: this.sedeId || null,
      sin_visita_hace_dias: this.tipoAudiencia === 'reactivar' ? this.dias : null,
      visita_en_ultimos_dias: this.tipoAudiencia === 'recientes' ? this.dias : null,
    };
    this.trabajando.set(true);
    this.error.set('');
    this.api
      .crearCampana({
        nombre: this.nombre.trim(),
        texto: this.texto.trim(),
        plantilla_meta: this.plantillaMeta.trim() || 'promocion_clinica',
        segmento,
      })
      .subscribe({
        next: (campana) => {
          this.trabajando.set(false);
          this.creando.set(false);
          this.nombre = '';
          this.texto = '';
          this.campanas.update((lista) => [campana, ...lista]);
          this.seleccionar(campana);
          this.exito.set('Borrador creado. Agregue la imagen: súbala o pídala a la IA.');
        },
        error: (fallo: unknown) => {
          this.trabajando.set(false);
          this.error.set(this.mensaje(fallo));
        },
      });
  }

  // ======================================================================
  //  Seleccion
  // ======================================================================
  protected seleccionar(campana: Campana): void {
    this.seleccionada.set(campana);
    this.descripcionImagen = campana.imagen_prompt ?? '';
    this.pidiendoCancelacion.set(false);
    this.audiencia.set(null);
    this.cargarImagen(campana);
    this.api.audienciaCampana(campana.id).subscribe({
      next: (respuesta) => this.audiencia.set(respuesta.con_consentimiento),
      error: () => this.audiencia.set(null),
    });
  }

  private cargarImagen(campana: Campana): void {
    this.liberarImagen();
    if (!campana.tiene_imagen) return;
    this.api.imagenCampana(campana.id).subscribe({
      next: (blob) => this.imagenUrl.set(URL.createObjectURL(blob)),
      error: () => undefined,
    });
  }

  private liberarImagen(): void {
    const actual = this.imagenUrl();
    if (actual) URL.revokeObjectURL(actual);
    this.imagenUrl.set(null);
  }

  // ======================================================================
  //  Imagen
  // ======================================================================
  protected generar(): void {
    const campana = this.seleccionada();
    if (!campana || this.generando()) return;
    this.generando.set(true);
    this.error.set('');
    this.api.generarImagenCampana(campana.id, this.descripcionImagen.trim()).subscribe({
      next: (actualizada) => {
        this.generando.set(false);
        this.actualizar(actualizada);
        this.exito.set('Imagen propuesta por la IA. Revísela antes de aprobar la campaña.');
      },
      error: (fallo: unknown) => {
        this.generando.set(false);
        this.error.set(this.mensaje(fallo));
      },
    });
  }

  protected subir(evento: Event): void {
    const campana = this.seleccionada();
    const campo = evento.target as HTMLInputElement;
    const archivo = campo.files?.[0];
    campo.value = '';
    if (!campana || !archivo) return;
    this.trabajando.set(true);
    this.api.subirImagenCampana(campana.id, archivo).subscribe({
      next: (actualizada) => {
        this.trabajando.set(false);
        this.actualizar(actualizada);
        this.exito.set('Imagen cargada.');
      },
      error: (fallo: unknown) => {
        this.trabajando.set(false);
        this.error.set(this.mensaje(fallo));
      },
    });
  }

  // ======================================================================
  //  Aprobar, enviar, cancelar
  // ======================================================================
  protected aprobar(): void {
    const campana = this.seleccionada();
    if (!campana) return;
    this.ejecutar(this.api.aprobarCampana(campana.id), 'Campaña aprobada. Ya se puede enviar.');
  }

  protected enviar(): void {
    const campana = this.seleccionada();
    if (!campana) return;
    const programada = this.programadaPara ? new Date(this.programadaPara).toISOString() : null;
    this.ejecutar(this.api.enviarCampana(campana.id, programada), (actualizada) =>
      `${actualizada.encolados} mensaje(s) en cola de envío` +
      (actualizada.omitidos ? `; ${actualizada.omitidos} omitido(s) por consentimiento.` : '.'),
    );
  }

  protected cancelar(): void {
    const campana = this.seleccionada();
    const motivo = this.motivoCancelacion.trim();
    if (!campana) return;
    if (motivo.length < 5) {
      this.error.set('Indique el motivo de la cancelación.');
      return;
    }
    this.ejecutar(this.api.cancelarCampana(campana.id, motivo), 'Campaña cancelada.');
  }

  private ejecutar(
    peticion: ReturnType<ApiService['aprobarCampana']>,
    exito: string | ((campana: Campana) => string),
  ): void {
    if (this.trabajando()) return;
    this.trabajando.set(true);
    this.error.set('');
    peticion.subscribe({
      next: (actualizada) => {
        this.trabajando.set(false);
        this.pidiendoCancelacion.set(false);
        this.actualizar(actualizada);
        this.exito.set(typeof exito === 'string' ? exito : exito(actualizada));
      },
      error: (fallo: unknown) => {
        this.trabajando.set(false);
        this.error.set(this.mensaje(fallo));
      },
    });
  }

  private actualizar(campana: Campana): void {
    this.campanas.update((lista) => lista.map((c) => (c.id === campana.id ? campana : c)));
    const imagenCambio =
      campana.tiene_imagen !== this.seleccionada()?.tiene_imagen ||
      campana.imagen_prompt !== this.seleccionada()?.imagen_prompt ||
      campana.imagen_origen !== this.seleccionada()?.imagen_origen;
    this.seleccionada.set(campana);
    if (imagenCambio || !this.imagenUrl()) this.cargarImagen(campana);
  }

  // ======================================================================
  //  Presentacion
  // ======================================================================
  protected describirSegmento(campana: Campana): string {
    const partes: string[] = [];
    const sede = this.sedes().find((s) => s.id === campana.segmento.sede_id);
    partes.push(sede ? `Sede ${sede.nombre}` : 'Todas las sedes');
    if (campana.segmento.sin_visita_hace_dias) {
      partes.push(`sin visita hace ${campana.segmento.sin_visita_hace_dias} días o más`);
    }
    if (campana.segmento.visita_en_ultimos_dias) {
      partes.push(`visitaron en los últimos ${campana.segmento.visita_en_ultimos_dias} días`);
    }
    return partes.join(' · ');
  }

  private mensaje(fallo: unknown): string {
    return fallo instanceof FalloApi ? fallo.message : 'No se pudo completar la operación.';
  }
}
