import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { CalendarioProfesionalService, type ConexionCalendario } from './calendario-profesional.service';

@Component({
  selector: 'app-calendario-profesional',
  imports: [FormsModule, DatePipe, VentanaFlotanteComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (permitido()) {
      <button type="button" class="boton boton--pequeno" (click)="abrir()">Mi Google Calendar</button>
    }
    @if (abierta()) {
      <app-ventana-flotante titulo="Mi Google Calendar" ceja="AGENDA PERSONAL" [ocupada]="ocupada()" (cerrar)="cerrar()">
        <p>Refleja tus horarios de atención. Los eventos no incluyen nombres de pacientes ni información clínica.</p>
        @if (error()) { <p class="calendario-error" role="alert">{{ error() }}</p> }
        @if (mensaje()) { <p role="status">{{ mensaje() }}</p> }
        @if (cargando()) { <p role="status">Consultando tus calendarios…</p> }
        @if (confirmando(); as conexion) {
          <form #desconexion="ngForm" (ngSubmit)="desconectar()">
            <h3>Desconectar {{ conexion.calendar_id }}</h3>
            <p>Se detiene la sincronización y se retiran las credenciales guardadas. Los eventos que ya están en Google se conservan.</p>
            <label class="campo"><span class="campo__etiqueta">Motivo</span><textarea class="campo__control" name="motivo" [(ngModel)]="motivo" required minlength="5" maxlength="255" [disabled]="ocupada()"></textarea></label>
            <div class="acciones"><button class="boton" type="button" [disabled]="ocupada()" (click)="confirmando.set(null)">Cancelar</button>
              <button class="boton boton--peligro" type="submit" [disabled]="ocupada() || desconexion.invalid || motivo.trim().length < 5">Desconectar calendario</button></div>
          </form>
        } @else {
          <div class="calendarios">
            @for (conexion of conexiones(); track conexion.id) {
              <article class="tarjeta calendario">
                <h3>{{ conexion.calendar_id }}</h3><p>{{ estado(conexion.estado_sincronizacion) }}</p>
                @if (conexion.ultima_sincronizacion_en) { <small>Última sincronización: {{ conexion.ultima_sincronizacion_en | date:'dd/MM/yyyy HH:mm':'UTC' }} UTC</small> }
                @if (conexion.ultimo_error) { <p role="status">{{ conexion.ultimo_error }}</p> }
                @if (conexion.estado_sincronizacion !== 'DESCONECTADO') {
                  <div class="acciones">
                    <button type="button" class="boton" [disabled]="ocupada() || cargando()" (click)="sincronizar(conexion)">Sincronizar ahora</button>
                    <button type="button" class="boton boton--plano" [disabled]="ocupada() || cargando()" (click)="prepararDesconexion(conexion)">Desconectar</button>
                  </div>
                }
              </article>
            } @empty { @if (!cargando()) { <p>No tienes calendarios conectados.</p> } }
          </div>
          <form #conexion="ngForm" (ngSubmit)="conectar()">
            <h3>Conectar o volver a autorizar</h3>
            <label class="campo"><span class="campo__etiqueta">Calendario de Google</span><input class="campo__control" name="calendario" [(ngModel)]="calendarId" (ngModelChange)="urlAutorizacion.set('')" required maxlength="255" [disabled]="ocupada()" /></label>
            <p class="ayuda">Usa «primary» para tu calendario principal. El administrador configura las credenciales de la clínica en Integraciones.</p>
            <button type="submit" class="boton boton--principal" [disabled]="ocupada() || conexion.invalid || !calendarId.trim()">Autorizar en Google</button>
            @if (urlAutorizacion()) {
              <a class="boton boton--principal" [href]="urlAutorizacion()" target="_blank" rel="noopener noreferrer">Continuar en Google <span class="solo-lectores">(abre otra pestaña)</span></a>
              <p role="status">Completa la autorización en la otra pestaña y vuelve aquí para actualizar el estado.</p>
            }
          </form>
        }
        <div pie class="acciones"><button type="button" class="boton" [disabled]="ocupada() || cargando()" (click)="cargar()">Actualizar estado</button>
          <button type="button" class="boton" [disabled]="ocupada()" (click)="cerrar()">Cerrar</button></div>
      </app-ventana-flotante>
    }
  `,
  styles: [`:host{display:contents}.calendarios{display:grid;gap:1rem;margin-block:1rem}.calendario{padding:1rem;overflow-wrap:anywhere}.acciones{display:flex;flex-wrap:wrap;gap:.65rem;margin-top:.8rem}form{display:grid;gap:.7rem}.campo{display:grid;gap:.4rem}.calendario-error{padding:.8rem;border-left:3px solid var(--peligro,#b42318);background:var(--superficie);border-radius:.5rem}textarea{min-height:5rem}`],
})
export class CalendarioProfesionalComponent {
  private readonly servicio = inject(CalendarioProfesionalService);
  private readonly sesion = inject(SesionService);
  private readonly destroyRef = inject(DestroyRef);
  readonly permitido = computed(() => this.sesion.tienePermiso('profesional.conectar_calendario') && !!this.sesion.identidad()?.profesional_id);
  readonly abierta = signal(false);
  readonly ocupada = signal(false);
  readonly cargando = signal(false);
  readonly error = signal('');
  readonly mensaje = signal('');
  readonly conexiones = signal<readonly ConexionCalendario[]>([]);
  readonly confirmando = signal<ConexionCalendario | null>(null);
  readonly urlAutorizacion = signal('');
  calendarId = 'primary';
  motivo = '';
  private carga = 0;
  abrir(): void { if (!this.permitido()) return; this.abierta.set(true); this.cargar(); }
  cerrar(): void { if (this.ocupada()) return; this.carga++; this.abierta.set(false); this.confirmando.set(null); this.error.set(''); this.mensaje.set(''); this.urlAutorizacion.set(''); }
  cargar(): void {
    if (!this.permitido() || this.ocupada()) return;
    const carga = ++this.carga;
    this.cargando.set(true); this.error.set('');
    this.servicio.listar().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: pagina => { if (carga !== this.carga) return; this.conexiones.set(pagina.elementos); this.cargando.set(false); },
      error: fallo => { if (carga !== this.carga) return; this.fallar(fallo); this.cargando.set(false); },
    });
  }
  conectar(): void {
    if (!this.permitido() || this.ocupada() || !this.calendarId.trim() || this.calendarId.trim().length > 255) return;
    this.ocupada.set(true); this.error.set(''); this.urlAutorizacion.set('');
    this.servicio.conectar(this.calendarId.trim()).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: respuesta => { try { this.urlAutorizacion.set(this.servicio.validarUrlGoogle(respuesta.url_autorizacion)); } catch (fallo) { this.fallar(fallo); } finally { this.ocupada.set(false); } },
      error: fallo => this.fallar(fallo),
    });
  }
  sincronizar(conexion: ConexionCalendario): void {
    if (!this.permitido() || this.ocupada() || this.cargando()) return;
    this.ocupada.set(true); this.error.set(''); this.mensaje.set('');
    this.servicio.sincronizar(conexion.id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: resumen => {
        this.ocupada.set(false);
        this.mensaje.set(`Creados: ${resumen.creados}. Actualizados: ${resumen.actualizados}. Retirados: ${resumen.eliminados}. Recreados: ${resumen.recreados}. Conflictos: ${resumen.conflictos}. Pendientes de reintento: ${resumen.reintentables}. Errores: ${resumen.errores}. Sin conexión disponible: ${resumen.sin_conexion}. Autorizaciones vencidas: ${resumen.token_vencido}.`);
        this.cargar();
      }, error: fallo => this.fallar(fallo),
    });
  }
  prepararDesconexion(conexion: ConexionCalendario): void { if (this.ocupada()) return; this.motivo = ''; this.confirmando.set(conexion); }
  desconectar(): void {
    const conexion = this.confirmando();
    if (!this.permitido() || this.ocupada() || !conexion || this.motivo.trim().length < 5 || this.motivo.trim().length > 255) return;
    this.ocupada.set(true); this.error.set('');
    this.servicio.desconectar(conexion.id, this.motivo.trim()).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => { this.ocupada.set(false); this.confirmando.set(null); this.mensaje.set('Calendario desconectado.'); this.cargar(); },
      error: fallo => this.fallar(fallo),
    });
  }
  estado(valor: ConexionCalendario['estado_sincronizacion']): string {
    return ({ CONECTADO: 'Conectado', TOKEN_VENCIDO: 'Necesita una nueva autorización', DESCONECTADO: 'Desconectado', ERROR: 'Revisar configuración o sincronización' })[valor];
  }
  private fallar(fallo: unknown): void { this.ocupada.set(false); this.error.set(fallo instanceof Error ? fallo.message : 'No se pudo completar la operación.'); }
}
