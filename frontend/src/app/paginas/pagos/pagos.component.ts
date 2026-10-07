/**
 * Pagos: registrar uno pendiente y revisar los que llegan.
 *
 * Cada pago se reconoce por paciente y fecha de la cita, no por su
 * identificador. Revisar abre una ventana flotante con el detalle y los
 * estados posibles; antes el formulario aparecía al final de la página, debajo
 * de la paginación, y parecía que el botón no hacía nada.
 *
 * Solo referencias administrativas: nunca tarjetas, claves ni códigos.
 */
import { Component, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';

import { SelectorPacienteComponent } from '../../compartido/selector-paciente.component';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
import { ApiService, FalloApi } from '../../nucleo/servicios/api.service';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { CargoPago, ComprobantePago, EventoHistorialPago, OperacionesService, Pago, Pagina } from '../../nucleo/servicios/operaciones.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import type { Cita, Paciente, Sede } from '../../nucleo/modelos/dominio';
import { ResumenModuloComponent } from '../../compartido/resumen-modulo.component';
import { IconoComponent } from '../../compartido/icono.component';

/** El listado trae además a quién y para cuándo. */
export interface PagoListado extends Pago {
  readonly paciente?: string | null;
  readonly cita_inicio?: string | null;
}

const ESTADOS: Record<string, string> = {
  PENDING: 'Pendiente',
  PROOF_RECEIVED: 'Comprobante recibido',
  UNDER_REVIEW: 'En revisión',
  CONFIRMED: 'Confirmado',
  REJECTED: 'Rechazado',
  REFUND_PENDING: 'Devolución pendiente',
};

const FILTROS: readonly { clave: string; texto: string }[] = [
  { clave: '', texto: 'Todos' },
  { clave: 'PENDING', texto: 'Pendientes' },
  { clave: 'PROOF_RECEIVED', texto: 'Con comprobante' },
  { clave: 'UNDER_REVIEW', texto: 'En revisión' },
  { clave: 'CONFIRMED', texto: 'Confirmados' },
  { clave: 'REJECTED', texto: 'Rechazados' },
];

const FILTROS_CARGOS = [
  { clave: false, texto: 'Todos los cargos' },
  { clave: true, texto: 'Vencidos' },
] as const;

function hoyEnGuayaquil(): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Guayaquil',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date());
}

function sumarDias(fecha: string, dias: number): string {
  const [anio, mes, dia] = fecha.split('-').map(Number);
  const resultado = new Date(Date.UTC(anio, mes - 1, dia + dias));
  return `${resultado.getUTCFullYear()}-${String(resultado.getUTCMonth() + 1).padStart(2, '0')}-${String(resultado.getUTCDate()).padStart(2, '0')}`;
}

@Component({
  selector: 'app-pagos',
  standalone: true,
  imports: [FormsModule, SelectorPacienteComponent, ResumenModuloComponent, VentanaFlotanteComponent, IconoComponent],
  template: `
    <header class="modulo-cabecera"><div class="modulo-cabecera__texto"><p class="ceja">ADMINISTRACIÓN</p><h1><app-icono nombre="balance-clinico" [tamano]="28" /> Pagos</h1><p>Registro de efectivo y transferencias en USD. La confirmación la realiza el personal autorizado.</p></div><img class="modulo-cabecera__imagen" src="/images/pagos-administrativos.png" alt="" aria-hidden="true" loading="lazy" /></header>

    <app-resumen-modulo modulo="pagos" />
    <div class="cabecera-pagina">
      <h2>Pagos · {{ total() }}</h2>
      <div class="acciones-cabecera">
        @if (sesion.tienePermiso('pago.registrar')) {
          <button class="boton boton--principal" type="button" (click)="abrirRegistro()">Registrar un abono</button>
        }
        <button class="boton" type="button" (click)="cargar()" [disabled]="ocupado()">Actualizar</button>
      </div>
    </div>
    @if (puedeLeerPagos() && puedeExportar()) {
      <section class="tarjeta reporte-pagos" aria-labelledby="titulo-reporte-pagos">
        <div><p class="ceja">ANÁLISIS FINANCIERO</p><h2 id="titulo-reporte-pagos">Exportar movimientos</h2>
          <p>Resumen por día local, estado y método. No incluye nombres ni datos de pacientes.</p></div>
        <form class="reporte-pagos__formulario" (ngSubmit)="exportarReporte()">
          <label class="campo"><span class="campo__etiqueta">Desde</span><input class="campo__control" type="date" name="reporte-desde" [(ngModel)]="reporteDesde" required /></label>
          <label class="campo"><span class="campo__etiqueta">Hasta (exclusivo)</span><input class="campo__control" type="date" name="reporte-hasta" [(ngModel)]="reporteHasta" required /></label>
          @if (sedesReporte().length > 0) {
            <label class="campo"><span class="campo__etiqueta">Sede</span><select class="campo__control" name="reporte-sede" [(ngModel)]="reporteSedeId"><option value="">Todas mis sedes</option>@for (sede of sedesReporte(); track sede.id) { <option [value]="sede.id">{{ sede.nombre }}</option> }</select></label>
          }
          <button class="boton boton--principal" type="submit" [disabled]="exportandoReporte() || !reporteDesde || !reporteHasta || reporteHasta <= reporteDesde">
            {{ exportandoReporte() ? 'Preparando…' : 'Descargar CSV' }}
          </button>
        </form>
        @if (errorReporte()) { <p class="aviso-error" role="alert">{{ errorReporte() }}</p> }
        @if (avisoReporte()) { <p class="aviso-ok" role="status">{{ avisoReporte() }}</p> }
      </section>
    }
    @if (formularioAbonoAbierto() && sesion.tienePermiso('pago.registrar')) {
      <app-ventana-flotante ceja="Gestión financiera" titulo="Registrar un abono" forma="centrada" [anchoMaximo]="720" [cierraAlPulsarFuera]="false" (cerrar)="cerrarRegistro()">
        <app-selector-paciente (seleccion)="seleccionar($event)" />
        <form id="formulario-abono" class="formulario-abono" #formulario="ngForm" (ngSubmit)="registrar()">
          <div class="formulario-demo">
            <label>Cita<select name="cita" [(ngModel)]="citaId" (ngModelChange)="seleccionarCita($event)" required><option value="">Seleccione una cita</option>
              @for (c of citas(); track c.id) { <option [value]="c.id">{{ fecha(c.inicio) }} · {{ estadoCita(c.estado) }}</option> }
            </select></label>
            <label>Total pactado (USD)<input type="number" name="total-acordado" [(ngModel)]="totalAcordado" min="0.01" max="9999999999" step="0.01" [disabled]="$safeNavigationMigration(cargoSeleccionado()?.total_acordado) !== null && cargoSeleccionado() !== null" required /></label>
            <label>Importe (USD)<input type="number" name="importe" [(ngModel)]="importe" min="0.01" max="9999999999" step="0.01" required /></label>
            <label>Vencimiento (opcional)<input type="date" name="fecha-vencimiento" [(ngModel)]="fechaVencimiento" [disabled]="cargoSeleccionado() !== null && ($safeNavigationMigration(cargoSeleccionado()?.total_acordado) !== null || $safeNavigationMigration(cargoSeleccionado()?.fecha_vencimiento) !== null)" /><small>Se interpreta según la hora local de la sede.</small></label>
            <label>Método<select name="metodo" [(ngModel)]="metodo"><option value="EFECTIVO">Efectivo</option><option value="TRANSFERENCIA">Transferencia</option></select></label>
            <label>Referencia del comprobante (opcional)<input name="referencia" [(ngModel)]="referencia" maxlength="100" /></label>
          </div>
          @if (cargoSeleccionado(); as cargo) {
            <p class="ayuda-demo">{{ cargo.total_acordado === null ? 'Cargo histórico: indique el total acordado para conciliarlo.' : 'Abono para un cargo de ' + moneda(cargo.total_acordado) + '.' }} Disponible para nuevos abonos: {{ cargo.saldo_no_asignado === null ? 'total por conciliar' : moneda(cargo.saldo_no_asignado) }}.</p>
          }
          <p class="ayuda-demo">Registre solo la referencia administrativa. No introduzca tarjetas, claves ni códigos de seguridad.</p>
          @if (formulario.invalid) {
            <p class="ayuda-demo" role="status">Para registrar: elija al paciente y una cita, indique el total pactado y el importe del abono.</p>
          }
          @if (error()) { <p class="aviso-error" role="alert">{{ error() }}</p> }
        </form>
        <div pie class="acciones-demo">
          <button class="boton" type="button" (click)="cerrarRegistro()" [disabled]="ocupado()">Cancelar</button>
          @if (!cargoSeleccionado()) { <button class="boton" type="button" (click)="crearCargo()" [disabled]="!citaId || !totalAcordado || totalAcordado <= 0 || ocupado()">Crear solo el cargo</button> }
          <button class="boton boton--principal" type="submit" form="formulario-abono" [disabled]="formulario.invalid || ocupado()">Registrar abono pendiente</button>
        </div>
      </app-ventana-flotante>
    }
    @if (sesion.tienePermiso('pago.leer')) {
      <section class="tarjeta cargos" aria-labelledby="titulo-cargos">
        <div class="cabecera-pagina"><div><p class="ceja">TOTALES PACTADOS</p><h2 id="titulo-cargos">Cargos y saldos · {{ totalCargos() }}</h2></div><button class="boton" type="button" (click)="cargarCargos()" [disabled]="cargandoCargos()">Actualizar</button></div>
        <div class="filtros" role="group" aria-label="Filtrar cargos por vencimiento">
          @for (f of filtrosCargos; track f.clave) { <button type="button" class="filtro" [attr.aria-pressed]="soloVencidos() === f.clave" (click)="filtrarCargos(f.clave)">{{ f.texto }}</button> }
        </div>
        @if (errorCargos()) { <p class="aviso-error" role="alert">{{ errorCargos() }}</p> }
        @if (cargandoCargos()) { <p role="status">Cargando cargos…</p> }
        @if (!cargandoCargos() && cargos().length === 0) { <p>No hay cargos registrados. Al crear el primero, indique el total acordado con el paciente.</p> }
        @if (cargos().length > 0) {
          <div class="tabla-envoltorio tabla-cargos" tabindex="0" role="region" aria-label="Cargos y saldos; desplazamiento horizontal de columnas"><table class="tabla">
            <thead><tr><th>Paciente</th><th>Cita</th><th>Total</th><th>Confirmado</th><th>Por cobrar</th><th>Vencimiento</th><th>Disponible para abonos</th><th>Acción</th></tr></thead>
            <tbody>@for (cargo of cargos(); track cargo.id) {
              <tr><td>{{ cargo.paciente || 'Paciente' }}</td><td class="numerico">{{ cargo.cita_inicio ? fecha(cargo.cita_inicio) : '—' }}</td>
                <td class="numerico">{{ cargo.total_acordado === null ? 'Por conciliar' : moneda(cargo.total_acordado) }}</td>
                <td class="numerico">{{ moneda(cargo.total_confirmado) }}</td>
                <td class="numerico">{{ cargo.saldo_pendiente === null ? '—' : moneda(cargo.saldo_pendiente) }}</td>
                <td>{{ cargo.fecha_vencimiento || 'Sin fecha' }} @if (cargo.vencido) { <span class="estado estado--vencido">Vencido</span> }</td>
                <td class="numerico">{{ cargo.saldo_no_asignado === null ? '—' : moneda(cargo.saldo_no_asignado) }}</td>
                <td>@if (cargo.total_acordado === null && puedeValidar()) { <button class="boton boton--pequeno" type="button" (click)="abrirConciliacion(cargo)">Conciliar total</button> } @if (cargo.fecha_vencimiento === null && puedeValidar()) { <button class="boton boton--pequeno" type="button" (click)="abrirVencimiento(cargo)">Fijar vencimiento</button> }</td></tr>
            }</tbody>
          </table></div>
        }
        <div class="acciones-demo"><button class="boton" type="button" (click)="moverCargos(-1)" [disabled]="paginaCargos() === 0 || cargandoCargos()">Anterior</button><span>Página {{ paginaCargos() + 1 }}</span><button class="boton" type="button" (click)="moverCargos(1)" [disabled]="(paginaCargos() + 1) * 25 >= totalCargos() || cargandoCargos()">Siguiente</button></div>
      </section>
    }
    @if (error() && !revisando() && !formularioAbonoAbierto()) { <p class="aviso-error" role="alert">{{ error() }}</p> }
    @if (aviso()) { <p class="aviso-ok" role="status">{{ aviso() }}</p> }
    <div class="filtros" role="group" aria-label="Filtrar por estado">
      @for (f of filtros; track f.clave) {
        <button type="button" class="filtro" [attr.aria-pressed]="estadoFiltro() === f.clave" (click)="filtrar(f.clave)">{{ f.texto }}</button>
      }
    </div>

    @if (cargando()) { <p role="status">Cargando pagos…</p> }
    @if (!cargando() && pagos().length === 0) { <p class="tarjeta">No hay pagos con este filtro.</p> }
    @if (pagos().length > 0) {
      <div class="tabla-envoltorio tabla-pagos">
        <table class="tabla">
          <thead><tr><th>Paciente</th><th>Cita</th><th>Importe</th><th>Método</th><th>Estado</th><th>Referencia</th><th class="accion"><span class="solo-lectores">Acciones</span></th></tr></thead>
          <tbody>
            @for (p of pagos(); track p.id) {
              <tr>
                <td>{{ p.paciente || 'Paciente' }}</td>
                <td class="numerico">{{ p.cita_inicio ? fecha(p.cita_inicio) : '—' }}</td>
                <td class="numerico">{{ moneda(p.importe) }}</td>
                <td>{{ p.metodo === 'EFECTIVO' ? 'Efectivo' : 'Transferencia' }}</td>
                <td><span class="estado" [attr.data-estado]="p.estado">{{ estado(p.estado) }}</span></td>
                <td>{{ p.referencia || '—' }}</td>
                <td class="accion">
                  <button class="boton boton--pequeno" type="button" (click)="abrirCambio(p)">
                    {{ puedeRevisar(p) ? 'Revisar' : 'Historial' }}
                  </button>
                </td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    }
    <div class="acciones-demo"><button class="boton" (click)="mover(-1)" [disabled]="pagina() === 0 || cargando()">Anterior</button><span>Página {{ pagina() + 1 }}</span><button class="boton" (click)="mover(1)" [disabled]="(pagina() + 1) * 25 >= total() || cargando()">Siguiente</button></div>

    @if (revisando(); as pago) {
      <app-ventana-flotante [ceja]="puedeRevisar(pago) ? 'Revisar pago' : 'Historial de pago'" [titulo]="moneda(pago.importe) + ' · ' + (pago.paciente || 'Paciente')" forma="centrada"
        [anchoMaximo]="520" [cierraAlPulsarFuera]="false" (cerrar)="cerrarRevision()">
        <dl class="detalle">
          <div><dt>Cita</dt><dd>{{ pago.cita_inicio ? fecha(pago.cita_inicio) : '—' }}</dd></div>
          <div><dt>Método</dt><dd>{{ pago.metodo === 'EFECTIVO' ? 'Efectivo' : 'Transferencia' }}</dd></div>
          <div><dt>Estado actual</dt><dd>{{ estado(pago.estado) }}</dd></div>
          <div><dt>Referencia</dt><dd>{{ pago.referencia || '—' }}</dd></div>
          @if (pago.comentario) { <div><dt>Último comentario</dt><dd>{{ pago.comentario }}</dd></div> }
        </dl>
        <section class="historial" aria-label="Comprobantes adjuntos">
          <h3>Comprobantes</h3>
          @if (avisoComprobante()) { <p class="aviso-ok" role="status">{{ avisoComprobante() }}</p> }
          @if (comprobantesCargando()) { <p role="status">Cargando comprobantes…</p> }
          @if (!comprobantesCargando() && comprobantes().length === 0) { <p>No hay archivos adjuntos.</p> }
          @for (comprobante of comprobantes(); track comprobante.id) {
            <article class="comprobante">
              <div><span>{{ nombreTipo(comprobante.tipo_mime) }} · {{ bytes(comprobante.tamano_bytes) }}</span>
                <span [class.comprobante__aviso]="comprobante.antivirus === 'NO_DISPONIBLE'">
                  {{ comprobante.antivirus === 'LIMPIO' ? 'Analizado' : 'Antivirus no disponible al cargar' }}
                </span></div>
              <time>{{ fecha(comprobante.cargado_en) }}</time>
              <button class="boton boton--pequeno" type="button" (click)="descargar(comprobante)">Descargar</button>
            </article>
          }
          @if (errorComprobantes()) { <p class="campo__error" role="alert">{{ errorComprobantes() }}</p> }
          @if (sesion.tienePermiso('pago.registrar') && (pago.estado === 'PENDING' || pago.estado === 'REJECTED')) {
            <form class="adjuntar" (submit)="$event.preventDefault(); adjuntar(pago)">
              <label class="campo"><span class="campo__etiqueta">Agregar comprobante</span>
                <input type="file" accept="application/pdf,image/jpeg,image/png,image/webp" (change)="seleccionarArchivo($event)" />
              </label>
              <p class="ayuda-demo">PDF, JPEG, PNG o WebP. Máximo configurado por la clínica. En producción requiere análisis antivirus.</p>
              <button class="boton" type="submit" [disabled]="!archivoComprobante || ocupado()">Subir archivo</button>
            </form>
          }
        </section>
        <section class="historial" aria-label="Historial de cambios del pago">
          <h3>Historial de cambios</h3>
          @if (historialCargando()) { <p role="status">Cargando historial…</p> }
          @if (!historialCargando() && historial().length === 0) { <p>Aún no hay cambios registrados.</p> }
          @for (evento of historial(); track evento.id) {
            <article class="historial__evento">
              <div><strong>{{ evento.estado_anterior ? estado(evento.estado_anterior) + ' → ' : (evento.actor_id ? 'Pago registrado → ' : 'Estado conocido al iniciar el historial → ') }}{{ estado(evento.estado_nuevo) }}</strong>
                <time>{{ fecha(evento.ocurrido_en) }}</time></div>
              @if (evento.comentario) { <p>{{ evento.comentario }}</p> }
            </article>
          }
          @if (errorHistorial()) { <p class="campo__error" role="alert">{{ errorHistorial() }}</p> }
        </section>
        @if (puedeRevisar(pago)) {
        <form #revision="ngForm" (ngSubmit)="cambiar()">
          <label class="campo"><span class="campo__etiqueta">Nuevo estado</span>
            <select class="campo__control" name="estado" [(ngModel)]="nuevoEstado" required>
              @for (e of transiciones[pago.estado]; track e) { <option [value]="e">{{ estado(e) }}</option> }
            </select>
          </label>
          <label class="campo"><span class="campo__etiqueta">Comentario de revisión</span>
            <textarea class="campo__control" name="comentario" [(ngModel)]="comentario" required minlength="3" maxlength="500"
              placeholder="Ej.: transferencia verificada en el banco"></textarea>
          </label>
          @if (error()) { <p class="campo__error" role="alert">{{ error() }}</p> }
          <div class="pie">
            <button type="button" class="boton" (click)="cerrarRevision()">Cerrar</button>
            <button class="boton boton--principal" [disabled]="revision.invalid || ocupado()">Guardar revisión</button>
          </div>
        </form>
        }
      </app-ventana-flotante>
    }

    @if (cargoConciliando(); as cargo) {
      <app-ventana-flotante ceja="Revisión financiera" titulo="Conciliar total pactado" forma="centrada" [anchoMaximo]="480" [cierraAlPulsarFuera]="false" (cerrar)="cerrarConciliacion()">
        <p>Los registros migrados no tienen un total estimado. Confirme el importe acordado en la historia de la clínica.</p>
        <form (ngSubmit)="conciliarCargo()">
          <label class="campo"><span class="campo__etiqueta">Total pactado (USD)</span><input class="campo__control" type="number" name="total-conciliado" [(ngModel)]="totalConciliacion" min="0.01" max="9999999999" step="0.01" required /></label>
          @if (errorConciliacion()) { <p class="campo__error" role="alert">{{ errorConciliacion() }}</p> }
          <div class="pie"><button class="boton" type="button" (click)="cerrarConciliacion()">Cancelar</button><button class="boton boton--principal" [disabled]="!totalConciliacion || totalConciliacion <= 0 || ocupado()">Fijar total</button></div>
        </form>
      </app-ventana-flotante>
    }
    @if (cargoVencimiento(); as cargo) {
      <app-ventana-flotante ceja="Revisión financiera" titulo="Fijar fecha de vencimiento" forma="centrada" [anchoMaximo]="480" [cierraAlPulsarFuera]="false" (cerrar)="cerrarVencimiento()">
        <p>Esta fecha se guardará en la zona horaria local de la sede. Una vez fijada, no se puede cambiar.</p>
        <form (ngSubmit)="fijarVencimiento()">
          <label class="campo"><span class="campo__etiqueta">Fecha de vencimiento</span><input class="campo__control" type="date" name="fecha-vencimiento-cargo" [(ngModel)]="fechaVencimientoConciliacion" required /></label>
          @if (errorVencimiento()) { <p class="campo__error" role="alert">{{ errorVencimiento() }}</p> }
          <div class="pie"><button class="boton" type="button" (click)="cerrarVencimiento()">Cancelar</button><button class="boton boton--principal" [disabled]="!fechaVencimientoConciliacion || ocupado()">Guardar fecha</button></div>
        </form>
      </app-ventana-flotante>
    }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    .cargos { margin-bottom: var(--espacio-5); }
    .acciones-cabecera { display: flex; flex-wrap: wrap; gap: var(--espacio-2); }
    .formulario-abono { display: grid; gap: var(--espacio-3); }
    .formulario-abono .formulario-demo { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--espacio-3); }
    .formulario-abono .formulario-demo > label { display: grid; gap: 6px; min-width: 0; color: var(--texto); font-weight: 600; }
    .formulario-abono .formulario-demo input, .formulario-abono .formulario-demo select { width: 100%; min-height: 42px; padding: 8px 10px; border: 1px solid var(--borde); border-radius: var(--radio); background: var(--superficie); color: var(--texto); font: inherit; }
    .formulario-abono .formulario-demo small { color: var(--texto-suave); font-weight: 400; }
    .formulario-abono .acciones-demo { display: flex; justify-content: flex-end; flex-wrap: wrap; gap: var(--espacio-2); }
    .formulario-abono .ayuda-demo { margin: 0; }
    @media (max-width: 600px) { .formulario-abono .formulario-demo { grid-template-columns: 1fr; } .formulario-abono .acciones-demo > .boton { flex: 1 1 auto; } }
    .cargos .cabecera-pagina { margin-top: 0; }
    .reporte-pagos { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: end; gap: var(--espacio-4); margin-bottom: var(--espacio-5); }
    .reporte-pagos h2 { margin: 0; }
    .reporte-pagos p:not(.ceja) { margin: 5px 0 0; color: var(--texto-suave); }
    .reporte-pagos__formulario { display: flex; align-items: end; flex-wrap: wrap; gap: var(--espacio-2); }
    .reporte-pagos__formulario .campo { min-width: 150px; }
    @media (max-width: 760px) { .reporte-pagos { grid-template-columns: 1fr; } .reporte-pagos__formulario { align-items: stretch; } }
    .ceja { margin: 0 0 3px; color: var(--texto-suave); font-size: .72rem; font-weight: 750; letter-spacing: .1em; }
    .cargos .tabla { min-width: 1040px; }
    .filtros { display: flex; flex-wrap: wrap; gap: 6px; margin: var(--espacio-2) 0 var(--espacio-3); }
    .filtro { padding: 4px 12px; border: 1px solid var(--borde); border-radius: 999px; background: transparent;
      color: var(--texto); font: inherit; font-size: 0.9rem; cursor: pointer; }
    .filtro[aria-pressed='true'] { border-color: var(--acento); background: var(--acento-suave); color: var(--acento-fuerte); font-weight: 600; }
    .accion { text-align: right; white-space: nowrap; }
    .estado { padding: 2px 8px; border-radius: 999px; background: var(--superficie); font-size: 0.8rem; white-space: nowrap; }
    .estado[data-estado='CONFIRMED'] { background: var(--acento-suave); color: var(--acento-fuerte); }
    .estado[data-estado='PROOF_RECEIVED'], .estado[data-estado='UNDER_REVIEW'] { background: #fdf3dc; color: #7a5a10; }
    .estado[data-estado='REJECTED'] { background: #fde4e1; color: var(--peligro); }
    .estado--vencido { margin-left: 6px; background: #fde4e1; color: var(--peligro); }
    .aviso-ok { color: var(--acento-fuerte); }
    .detalle { display: grid; gap: var(--espacio-2); margin: 0 0 var(--espacio-3); }
    .detalle div { display: grid; grid-template-columns: 140px 1fr; gap: var(--espacio-2); }
    .detalle dt { color: var(--texto-suave); }
    .detalle dd { margin: 0; }
    .historial { margin: var(--espacio-3) 0; }
    .historial h3 { margin: 0 0 var(--espacio-2); font-size: 1rem; }
    .historial__evento { padding: var(--espacio-2) 0; border-top: 1px solid var(--borde); }
    .historial__evento div { display: flex; justify-content: space-between; gap: var(--espacio-2); }
    .historial__evento time { color: var(--texto-suave); font-size: 0.85rem; }
    .historial__evento p { margin: 4px 0 0; }
    .comprobante { display: grid; gap: 4px; padding: var(--espacio-2) 0; border-top: 1px solid var(--borde); }
    .comprobante > div { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; }
    .comprobante time { color: var(--texto-suave); font-size: 0.85rem; }
    .comprobante__aviso { color: #7a5a10; }
    .adjuntar { display: grid; gap: var(--espacio-2); padding-top: var(--espacio-2); }
    .pie { display: flex; justify-content: flex-end; gap: var(--espacio-2); margin-top: var(--espacio-3); }
  `,
})
export class PagosComponent {
  private readonly api = inject(OperacionesService);
  private readonly agenda = inject(ApiService);
  private readonly catalogo = inject(CatalogoService);
  protected readonly sesion = inject(SesionService);

  protected readonly filtros = FILTROS;
  protected readonly filtrosCargos = FILTROS_CARGOS;
  protected readonly pagos = signal<PagoListado[]>([]);
  protected readonly total = signal(0);
  protected readonly pagina = signal(0);
  protected readonly cargos = signal<CargoPago[]>([]);
  protected readonly totalCargos = signal(0);
  protected readonly paginaCargos = signal(0);
  protected readonly soloVencidos = signal(false);
  protected readonly cargandoCargos = signal(false);
  protected readonly errorCargos = signal('');
  protected readonly cargoSeleccionado = signal<CargoPago | null>(null);
  protected readonly formularioAbonoAbierto = signal(false);
  protected readonly cargoConciliando = signal<CargoPago | null>(null);
  protected readonly cargoVencimiento = signal<CargoPago | null>(null);
  protected readonly errorConciliacion = signal('');
  protected readonly errorVencimiento = signal('');
  protected readonly estadoFiltro = signal('');
  protected readonly citas = signal<readonly Cita[]>([]);
  protected readonly cargando = signal(false);
  protected readonly ocupado = signal(false);
  protected readonly error = signal('');
  protected readonly aviso = signal('');
  protected readonly revisando = signal<PagoListado | null>(null);
  protected readonly historial = signal<readonly EventoHistorialPago[]>([]);
  protected readonly historialCargando = signal(false);
  protected readonly errorHistorial = signal('');
  protected readonly comprobantes = signal<readonly ComprobantePago[]>([]);
  protected readonly comprobantesCargando = signal(false);
  protected readonly errorComprobantes = signal('');
  protected readonly avisoComprobante = signal('');
  protected readonly puedeValidar = computed(() => this.sesion.tienePermiso('pago.validar'));
  protected readonly puedeRegistrarPago = computed(() => this.sesion.tienePermiso('pago.registrar'));
  protected readonly puedeLeerPagos = computed(() => this.sesion.tienePermiso('pago.leer'));
  protected readonly puedeExportar = computed(() => this.sesion.tienePermiso('reporte.exportar'));
  protected readonly exportandoReporte = signal(false);
  protected readonly errorReporte = signal('');
  protected readonly avisoReporte = signal('');
  protected readonly sedesReporte = signal<readonly Sede[]>([]);

  protected reporteDesde = `${hoyEnGuayaquil().slice(0, 7)}-01`;
  protected reporteHasta = sumarDias(hoyEnGuayaquil(), 1);
  protected reporteSedeId = '';
  protected citaId = '';
  protected importe: number | null = null;
  protected totalAcordado: number | null = null;
  protected totalConciliacion: number | null = null;
  protected fechaVencimiento = '';
  protected fechaVencimientoConciliacion = '';
  protected metodo = 'EFECTIVO';
  protected referencia = '';
  protected nuevoEstado = '';
  protected comentario = '';
  protected archivoComprobante: File | null = null;
  private clave = crypto.randomUUID();
  private cuerpoAnterior = '';
  private consultaCargo = 0;
  protected readonly citaContexto = inject(ActivatedRoute, { optional: true })?.snapshot.queryParamMap.get('cita') ?? null;

  protected abrirRegistro(): void {
    if (!this.puedeRegistrarPago()) return;
    this.error.set('');
    this.aviso.set('');
    this.formularioAbonoAbierto.set(true);
    if (this.citaContexto) this.agenda.cita(this.citaContexto).subscribe({
      next: cita => { this.citas.set([cita]); this.citaId = cita.id; this.seleccionarCita(cita.id); },
      error: fallo => this.error.set(fallo.message),
    });
  }

  protected cerrarRegistro(): void {
    if (this.ocupado()) return;
    this.formularioAbonoAbierto.set(false);
    this.consultaCargo += 1;
    this.citas.set([]);
    this.citaId = '';
    this.importe = null;
    this.totalAcordado = null;
    this.fechaVencimiento = '';
    this.metodo = 'EFECTIVO';
    this.referencia = '';
    this.cargoSeleccionado.set(null);
    this.error.set('');
  }

  protected readonly transiciones: Record<string, string[]> = {
    PENDING: ['PROOF_RECEIVED', 'CONFIRMED', 'REJECTED'],
    PROOF_RECEIVED: ['UNDER_REVIEW', 'CONFIRMED', 'REJECTED'],
    UNDER_REVIEW: ['CONFIRMED', 'REJECTED'],
    REJECTED: ['PROOF_RECEIVED', 'UNDER_REVIEW'],
    CONFIRMED: ['REFUND_PENDING'],
    REFUND_PENDING: [],
  };

  constructor() {
    this.cargar();
    if (this.puedeLeerPagos() && this.puedeExportar()) {
      this.catalogo.sedes().subscribe({ next: (sedes) => this.sedesReporte.set(sedes) });
    }
  }

  protected cargar(): void {
    this.cargarCargos();
    this.cargando.set(true);
    this.error.set('');
    const parametros: Record<string, string | number> = { limite: 25, desplazamiento: this.pagina() * 25 };
    if (this.citaContexto) parametros['cita_id'] = this.citaContexto;
    if (this.estadoFiltro()) parametros['estado'] = this.estadoFiltro();
    this.api.leer<Pagina<PagoListado>>('/pagos/', parametros).subscribe({
      next: (p) => {
        this.pagos.set(p.elementos);
        this.total.set(p.total);
        this.cargando.set(false);
      },
      error: (e: FalloApi) => {
        this.error.set(e.message);
        this.cargando.set(false);
      },
    });
  }

  protected exportarReporte(): void {
    if (!this.reporteDesde || !this.reporteHasta || this.reporteHasta <= this.reporteDesde) {
      this.errorReporte.set('Elija un rango válido; la fecha final no está incluida.');
      return;
    }
    this.exportandoReporte.set(true);
    this.errorReporte.set('');
    this.avisoReporte.set('');
    this.api
      .descargarReportePagos(this.reporteDesde, this.reporteHasta, this.reporteSedeId || undefined)
      .subscribe({
      next: (archivo) => {
        const url = URL.createObjectURL(archivo);
        const enlace = document.createElement('a');
        enlace.href = url;
        enlace.download = `resumen-pagos-${this.reporteDesde}-${this.reporteHasta}.csv`;
        enlace.click();
        URL.revokeObjectURL(url);
        this.exportandoReporte.set(false);
        this.avisoReporte.set('El resumen financiero se descargó.');
      },
      error: (fallo: FalloApi) => {
        this.errorReporte.set(fallo.message);
        this.exportandoReporte.set(false);
      },
      });
  }

  protected cargarCargos(): void {
    if (!this.sesion.tienePermiso('pago.leer')) return;
    this.cargandoCargos.set(true);
    this.errorCargos.set('');
    this.api.leer<Pagina<CargoPago>>('/pagos/cargos/', {
      limite: 25,
      desplazamiento: this.paginaCargos() * 25,
      vencidos: this.soloVencidos(),
      ...(this.citaContexto ? { cita_id: this.citaContexto } : {}),
    }).subscribe({
      next: (pagina) => {
        this.cargos.set(pagina.elementos);
        this.totalCargos.set(pagina.total);
        this.cargandoCargos.set(false);
      },
      error: (fallo: FalloApi) => {
        this.errorCargos.set(fallo.message);
        this.cargandoCargos.set(false);
      },
    });
  }

  protected moverCargos(direccion: number): void {
    this.paginaCargos.update((pagina) => pagina + direccion);
    this.cargarCargos();
  }

  protected filtrarCargos(vencidos: boolean): void {
    this.soloVencidos.set(vencidos);
    this.paginaCargos.set(0);
    this.cargarCargos();
  }

  protected filtrar(estado: string): void {
    this.estadoFiltro.set(estado);
    this.pagina.set(0);
    this.cargar();
  }

  protected mover(n: number): void {
    this.pagina.update((p) => p + n);
    this.cargar();
  }

  protected seleccionar(p: Paciente | null): void {
    this.consultaCargo += 1;
    this.citaId = '';
    this.citas.set([]);
    this.totalAcordado = null;
    this.fechaVencimiento = '';
    this.cargoSeleccionado.set(null);
    this.error.set('');
    if (!p) return;
    const consulta = this.consultaCargo;
    this.agenda.citas({ paciente_id: p.id, limite: 200 }).subscribe({
      next: (r) => { if (consulta === this.consultaCargo) this.citas.set(r.elementos); },
      error: (e: FalloApi) => { if (consulta === this.consultaCargo) this.error.set(e.message); },
    });
  }

  protected seleccionarCita(citaId: string): void {
    const consulta = ++this.consultaCargo;
    this.cargoSeleccionado.set(null);
    this.totalAcordado = null;
    if (!citaId || !this.sesion.tienePermiso('pago.leer')) return;
    this.api.leer<Pagina<CargoPago>>('/pagos/cargos/', { cita_id: citaId, limite: 1 }).subscribe({
      next: (resultado) => {
        if (consulta !== this.consultaCargo || this.citaId !== citaId) return;
        const cargo = resultado.elementos[0] ?? null;
        this.cargoSeleccionado.set(cargo);
        this.fechaVencimiento = cargo?.fecha_vencimiento ?? '';
        if (cargo && cargo.total_acordado !== null) {
          this.totalAcordado = Number(cargo.total_acordado);
        }
      },
      error: (fallo: FalloApi) => { if (consulta === this.consultaCargo) this.error.set(fallo.message); },
    });
  }

  protected registrar(): void {
    if (!this.citaId || !this.importe || this.importe <= 0 || !this.totalAcordado || this.totalAcordado <= 0) {
      this.error.set('Indique la cita, el total acordado y el importe del abono.');
      return;
    }
    this.enviar('/pagos/', {
      cita_id: this.citaId,
      importe: this.importe,
      total_acordado: this.totalAcordado,
      fecha_vencimiento: this.fechaVencimiento || null,
      metodo: this.metodo,
      referencia: this.referencia.trim() || null,
    }, 'Abono registrado como pendiente de confirmación.', () => this.cerrarRegistro());
  }

  protected crearCargo(): void {
    if (!this.citaId || !this.totalAcordado || this.totalAcordado <= 0 || this.cargoSeleccionado()) {
      this.error.set('Seleccione una cita nueva e indique su total pactado.');
      return;
    }
    this.enviar<CargoPago>('/pagos/cargos/', {
      cita_id: this.citaId,
      total_acordado: this.totalAcordado,
      fecha_vencimiento: this.fechaVencimiento || null,
    }, 'Cargo registrado sin abono inicial.', () => this.cerrarRegistro());
  }

  protected abrirConciliacion(cargo: CargoPago): void {
    this.cargoConciliando.set(cargo);
    this.totalConciliacion = null;
    this.fechaVencimientoConciliacion = cargo.fecha_vencimiento ?? '';
    this.errorConciliacion.set('');
  }

  protected cerrarConciliacion(): void {
    this.cargoConciliando.set(null);
    this.totalConciliacion = null;
    this.errorConciliacion.set('');
  }

  protected conciliarCargo(): void {
    const cargo = this.cargoConciliando();
    const total = this.totalConciliacion;
    if (!cargo || !total || total <= 0 || this.ocupado()) return;
    this.ocupado.set(true);
    this.errorConciliacion.set('');
    this.api.cambiar<CargoPago>(`/pagos/cargos/${cargo.id}/total`, {
      total_acordado: total,
      fecha_vencimiento: this.fechaVencimientoConciliacion || null,
    }).subscribe({
      next: () => {
        this.ocupado.set(false);
        this.cerrarConciliacion();
        this.aviso.set('Total pactado conciliado y fijado en el historial.');
        this.cargarCargos();
        this.seleccionarCita(cargo.cita_id);
      },
      error: (fallo: FalloApi) => {
        this.errorConciliacion.set(fallo.message);
        this.ocupado.set(false);
      },
    });
  }

  protected cerrarVencimiento(): void {
    this.cargoVencimiento.set(null);
    this.fechaVencimientoConciliacion = '';
    this.errorVencimiento.set('');
  }

  protected abrirVencimiento(cargo: CargoPago): void {
    this.cargoVencimiento.set(cargo);
    this.fechaVencimientoConciliacion = '';
    this.errorVencimiento.set('');
  }

  protected fijarVencimiento(): void {
    const cargo = this.cargoVencimiento();
    if (!cargo || !this.fechaVencimientoConciliacion || this.ocupado()) return;
    this.ocupado.set(true);
    this.errorVencimiento.set('');
    this.api.cambiar<CargoPago>(`/pagos/cargos/${cargo.id}/vencimiento`, {
      fecha_vencimiento: this.fechaVencimientoConciliacion,
    }).subscribe({
      next: () => {
        this.ocupado.set(false);
        this.cerrarVencimiento();
        this.aviso.set('Fecha de vencimiento fijada y auditada.');
        this.cargarCargos();
        this.seleccionarCita(cargo.cita_id);
      },
      error: (fallo: FalloApi) => {
        this.errorVencimiento.set(fallo.message);
        this.ocupado.set(false);
      },
    });
  }

  protected puedeRevisar(p: PagoListado): boolean {
    return this.puedeValidar() && (this.transiciones[p.estado]?.length ?? 0) > 0;
  }

  protected abrirCambio(p: PagoListado): void {
    this.error.set('');
    this.aviso.set('');
    this.revisando.set(p);
    this.nuevoEstado = this.transiciones[p.estado]?.[0] ?? '';
    this.comentario = '';
    this.clave = crypto.randomUUID();
    this.cuerpoAnterior = '';
    this.historial.set([]);
    this.errorHistorial.set('');
    this.comprobantes.set([]);
    this.errorComprobantes.set('');
    this.avisoComprobante.set('');
    this.archivoComprobante = null;
    if (this.sesion.tienePermiso('pago.leer')) {
      this.historialCargando.set(true);
      this.api.leer<{ elementos: EventoHistorialPago[] }>(`/pagos/${p.id}/historial`).subscribe({
        next: (resultado) => {
          this.historial.set(resultado.elementos);
          this.historialCargando.set(false);
        },
        error: (fallo: FalloApi) => {
          this.errorHistorial.set(fallo.message);
          this.historialCargando.set(false);
        },
      });
      this.comprobantesCargando.set(true);
      this.api.leer<{ elementos: ComprobantePago[] }>(`/pagos/${p.id}/comprobantes`).subscribe({
        next: (resultado) => {
          this.comprobantes.set(resultado.elementos);
          this.comprobantesCargando.set(false);
        },
        error: (fallo: FalloApi) => {
          this.errorComprobantes.set(fallo.message);
          this.comprobantesCargando.set(false);
        },
      });
    }
  }

  protected cerrarRevision(): void {
    this.revisando.set(null);
    this.error.set('');
    this.historial.set([]);
    this.historialCargando.set(false);
    this.comprobantes.set([]);
    this.archivoComprobante = null;
    this.avisoComprobante.set('');
  }

  protected seleccionarArchivo(evento: Event): void {
    const entrada = evento.target as HTMLInputElement;
    this.archivoComprobante = entrada.files?.[0] ?? null;
  }

  protected adjuntar(pago: PagoListado): void {
    const archivo = this.archivoComprobante;
    if (!archivo || this.ocupado()) return;
    this.ocupado.set(true);
    this.error.set('');
    this.api.subirComprobante(pago.id, archivo).subscribe({
      next: (comprobante) => {
        this.comprobantes.update((elementos) => [...elementos, comprobante]);
        this.archivoComprobante = null;
        this.ocupado.set(false);
        this.cargar();
        this.abrirCambio({ ...pago, estado: 'PROOF_RECEIVED' });
        this.avisoComprobante.set('Comprobante cargado. El pago quedó marcado para revisión.');
        this.aviso.set('Comprobante cargado. El pago quedó marcado para revisión.');
      },
      error: (fallo: FalloApi) => {
        this.error.set(fallo.message);
        this.ocupado.set(false);
      },
    });
  }

  protected descargar(comprobante: ComprobantePago): void {
    this.api.descargarComprobante(comprobante.id).subscribe({
      next: (archivo) => {
        const url = URL.createObjectURL(archivo);
        const enlace = document.createElement('a');
        enlace.href = url;
        enlace.download = `comprobante-${comprobante.id}.${this.extension(comprobante.tipo_mime)}`;
        enlace.click();
        URL.revokeObjectURL(url);
      },
      error: (fallo: FalloApi) => this.errorComprobantes.set(fallo.message),
    });
  }

  protected nombreTipo(tipo: ComprobantePago['tipo_mime']): string {
    return tipo === 'application/pdf' ? 'PDF' : tipo.split('/')[1].toUpperCase();
  }

  protected bytes(tamano: number): string {
    return `${(tamano / 1024).toFixed(1)} KB`;
  }

  private extension(tipo: ComprobantePago['tipo_mime']): string {
    return { 'application/pdf': 'pdf', 'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp' }[tipo];
  }

  protected cambiar(): void {
    const p = this.revisando();
    if (p) {
      this.enviar(`/pagos/${p.id}/estado`, { estado: this.nuevoEstado, comentario: this.comentario },
        `Pago marcado como «${this.estado(this.nuevoEstado).toLowerCase()}».`);
    }
  }

  private enviar<T = Pago>(ruta: string, datos: unknown, exito: string, alCompletar?: () => void): void {
    if (this.ocupado()) return;
    const cuerpo = JSON.stringify({ ruta, datos });
    if (this.cuerpoAnterior && cuerpo !== this.cuerpoAnterior) this.clave = crypto.randomUUID();
    this.cuerpoAnterior = cuerpo;
    this.ocupado.set(true);
    this.error.set('');
    this.aviso.set('');
    this.api.guardar<T>(ruta, datos, this.clave).subscribe({
      next: () => {
        this.ocupado.set(false);
        this.revisando.set(null);
        this.aviso.set(exito);
        this.clave = crypto.randomUUID();
        this.cuerpoAnterior = '';
        alCompletar?.();
        this.cargar();
      },
      error: (e: FalloApi) => {
        this.error.set(e.message);
        this.ocupado.set(false);
      },
    });
  }

  protected estadoCita(estado: string): string {
    const nombres: Record<string, string> = {
      PENDING: 'Pendiente', HELD: 'Apartada', CONFIRMED: 'Confirmada', RESCHEDULED: 'Reprogramada',
      COMPLETED: 'Atendida', NO_SHOW: 'No asistió', CANCELLED: 'Cancelada',
    };
    return nombres[estado] ?? estado;
  }

  protected fecha(s: string): string {
    return new Date(s).toLocaleString('es-EC', { timeZone: 'America/Guayaquil', dateStyle: 'short', timeStyle: 'short' });
  }

  protected moneda(s: string): string {
    return new Intl.NumberFormat('es-EC', { style: 'currency', currency: 'USD' }).format(Number(s));
  }

  protected estado(s: string): string {
    return ESTADOS[s] || s;
  }
}
