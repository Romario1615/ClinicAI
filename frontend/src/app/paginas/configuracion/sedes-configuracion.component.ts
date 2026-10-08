import { Component, OnInit, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CapturaFotosComponent, type FotoSeleccionada } from '../../compartido/captura-fotos.component';
import { FotosRegistroComponent } from '../../compartido/fotos-registro.component';
import { FotosRegistroService } from '../../nucleo/servicios/fotos-registro.service';

import { IconoComponent } from '../../compartido/icono.component';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
import { FalloApi } from '../../nucleo/servicios/api.service';
import { CatalogoService, type DatosSede, type SedeGestion } from '../../nucleo/servicios/catalogo.service';

@Component({
  selector: 'app-sedes-configuracion',
  standalone: true,
  imports: [FotosRegistroComponent,FormsModule, IconoComponent, VentanaFlotanteComponent, CapturaFotosComponent],
  template: `
    <section class="sedes-cabecera" aria-labelledby="sedes-titulo">
      <div>
        <p class="ceja"><app-icono nombre="sedes" [tamano]="16" /> OPERACIÓN DE LA CLÍNICA</p>
        <h2 id="sedes-titulo">Sedes y datos de reserva</h2>
        <p>Actualiza la información de las sedes habilitadas dentro de tu ámbito.</p>
      </div>
      <img src="/images/sedes-red-clinicas.jpg" alt="" aria-hidden="true" fetchpriority="low" />
    </section>

    @if (aviso()) { <p class="mensaje mensaje--bien" role="status">{{ aviso() }}</p> }
    @if (error() && !formulario()) { <p class="mensaje mensaje--error" role="alert">{{ error() }}</p> }
    @if (cargando()) { <p class="tarjeta" role="status">Cargando sedes…</p> }

    @if (!cargando() && !error() && sedes().length === 0) {
      <section class="tarjeta sedes-vacias">
        <app-icono nombre="sala-clinica" [tamano]="28" />
        <h3>No hay sedes disponibles en tu ámbito</h3>
        <p>Solicita al administrador de la clínica acceso a una sede activa.</p>
      </section>
    }

    <div class="sedes-lista">
      @for (sede of sedes(); track sede.id) {
        <article class="tarjeta sede">
          <header class="sede__cabecera">
            <span class="sede__icono"><app-icono nombre="sala-clinica" [tamano]="21" /></span>
            <div class="sede__titulo"><h3>{{ sede.nombre }}</h3><app-fotos-registro tipo="sede" [registroId]="sede.id" [puedeEditar]="true" /><p>{{ sede.zona_horaria }}</p></div>
            @if (editando() !== sede.id) {
              <button class="boton" type="button" (click)="editar(sede)">Editar sede</button>
            }
          </header>

          <dl class="sede__datos">
            <div><dt>Dirección</dt><dd>{{ sede.direccion || 'Sin dirección registrada' }}</dd></div>
            <div><dt>Teléfono</dt><dd>{{ sede.telefono || 'Sin teléfono registrado' }}</dd></div>
            <div><dt>Antelación mínima</dt><dd>{{ sede.minutos_antelacion_minima }} minutos</dd></div>
          </dl>
        </article>
      }
    </div>

    @if (formulario(); as datos) {
      <app-ventana-flotante
        ceja="Operación de la clínica"
        [titulo]="'Editar sede · ' + (sedeEditada()?.nombre ?? '')"
        forma="centrada"
        [anchoMaximo]="640"
        [cierraAlPulsarFuera]="false"
        (cerrar)="cancelar()"
      >
        @if (error()) { <p class="mensaje mensaje--error" role="alert">{{ error() }}</p> }
        <form id="formulario-sede" class="sede__formulario" (ngSubmit)="guardar()">
          <label class="campo"><span class="campo__etiqueta">Nombre de la sede</span>
            <input class="campo__control" name="nombre-sede" [(ngModel)]="datos.nombre" maxlength="200" autocomplete="organization" required />
          </label>
          <label class="campo"><span class="campo__etiqueta">Dirección</span>
            <input class="campo__control" name="direccion-sede" [(ngModel)]="datos.direccion" maxlength="500" autocomplete="street-address" />
          </label>
          <label class="campo"><span class="campo__etiqueta">Teléfono</span>
            <input class="campo__control" name="telefono-sede" [(ngModel)]="datos.telefono" type="tel" maxlength="32" autocomplete="tel" />
          </label>
          <label class="campo"><span class="campo__etiqueta">Zona horaria IANA</span>
            <input class="campo__control" name="zona-sede" [(ngModel)]="datos.zona_horaria" placeholder="America/Guayaquil" maxlength="64" required aria-describedby="ayuda-zona-sede" />
            <small id="ayuda-zona-sede" class="campo__ayuda">Se usa para mostrar horarios y calcular reservas.</small>
          </label>
          <label class="campo campo--completo"><span class="campo__etiqueta">Antelación mínima para reservar (minutos)</span>
            <input class="campo__control" name="antelacion-sede" [(ngModel)]="datos.minutos_antelacion_minima" type="number" min="0" max="10080" step="1" required />
          </label>
          <app-captura-fotos titulo="Imágenes de la sede" [ocupada]="guardando()" (cambiadas)="fotos=$event" />
        </form>
        <div pie class="sede__acciones">
          <button class="boton" type="button" (click)="cancelar()" [disabled]="guardando()">Cancelar</button>
          <button class="boton boton--principal" type="submit" form="formulario-sede" [disabled]="guardando()">
            {{ guardando() ? 'Guardando…' : 'Guardar cambios' }}
          </button>
        </div>
      </app-ventana-flotante>
    }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    .sedes-cabecera { position:relative; display:flex; align-items:center; min-height:clamp(160px,18vw,210px); overflow:hidden; padding:var(--espacio-5); margin-bottom:var(--espacio-4); border:1px solid var(--borde); border-radius:var(--radio); background:linear-gradient(105deg,#f8fcfb 0%,#edf7f5 64%,#e3f1ef 100%); isolation:isolate; }
    .sedes-cabecera::after { content:""; position:absolute; z-index:-1; inset:-50%; pointer-events:none; background:radial-gradient(ellipse at 82% 50%,rgb(95 209 196 / 18%),transparent 35%); animation:sedes-halo 21s ease-in-out infinite alternate; }
    .sedes-cabecera > div { position:relative; z-index:1; max-width:560px; }
    .sedes-cabecera .ceja { display:flex; align-items:center; gap:var(--espacio-2); margin:0 0 var(--espacio-2); }
    .sedes-cabecera h2 { margin:0; font-size:clamp(1.2rem,2vw,1.6rem); }
    .sedes-cabecera p:last-child { margin:var(--espacio-2) 0 0; color:var(--texto-suave); }
    .sedes-cabecera img { position:absolute; z-index:0; inset:0 0 0 auto; width:min(62%,760px); height:100%; object-fit:cover; object-position:center 54%; mask-image:linear-gradient(90deg,transparent 0%,#000 32%); transform-origin:75% center; animation:sedes-ilustracion 25s ease-in-out infinite alternate; }
    @keyframes sedes-ilustracion { from { transform:translate3d(0,2px,0) scale(1); } to { transform:translate3d(0,-3px,0) scale(1.018); } }
    @keyframes sedes-halo { from { transform:translate3d(-1%,1%,0) scale(.98); opacity:.55; } to { transform:translate3d(2%,-1%,0) scale(1.04); opacity:1; } }
    .sedes-lista { display:grid; gap:var(--espacio-3); }
    .sede { min-width:0; padding:var(--espacio-4) var(--espacio-5); }
    .sede__cabecera { display:flex; align-items:center; gap:var(--espacio-3); }
    .sede__icono { display:grid; flex:0 0 44px; width:44px; height:44px; place-items:center; border-radius:12px; color:var(--acento-fuerte); background:var(--acento-suave); }
    .sede__titulo { flex:1; min-width:0; }
    .sede__titulo h3 { margin:0; }
    .sede__titulo p { margin:2px 0 0; color:var(--texto-tenue); font-size:.85rem; }
    .sede__datos { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:var(--espacio-4); margin:var(--espacio-4) 0 0 56px; }
    .sede__datos dt { color:var(--texto-tenue); font-size:.78rem; }
    .sede__datos dd { margin:2px 0 0; font-weight:600; overflow-wrap:anywhere; }
    .sede__formulario { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:var(--espacio-3) var(--espacio-4); }
    .sede__formulario .campo { margin:0; }
    .sede__acciones { justify-content:flex-end; flex-wrap:wrap; }
    .sedes-vacias { display:grid; justify-items:center; gap:var(--espacio-2); padding:var(--espacio-6); color:var(--texto-suave); text-align:center; }
    .sedes-vacias h3,.sedes-vacias p { margin:0; }
    .sedes-vacias app-icono { color:var(--acento); }
    .mensaje { padding:var(--espacio-3) var(--espacio-4); border-radius:var(--radio); }
    .mensaje--bien { color:var(--exito); background:var(--exito-fondo); }
    .mensaje--error { color:var(--peligro); background:var(--peligro-fondo); }
    @media (max-width:680px) { .sede__datos { grid-template-columns:1fr; margin-left:0; } .sede__formulario { grid-template-columns:1fr; } .sede__formulario .campo--completo { grid-column:auto; } .sedes-cabecera { min-height:190px; align-items:flex-start; } .sedes-cabecera img { width:78%; opacity:.56; mask-image:linear-gradient(90deg,transparent 0%,#000 40%); } .sede { padding:var(--espacio-4); } }
    @media (prefers-reduced-motion: reduce) { .sedes-cabecera::after, .sedes-cabecera img { animation:none; } }
  `,
})
export class SedesConfiguracionComponent implements OnInit {
  protected readonly operacionFotos=inject(FotosRegistroService).operacion<SedeGestion>();
  protected fotos:readonly FotoSeleccionada[]=[];
  private readonly catalogo = inject(CatalogoService);
  protected readonly sedes = signal<readonly SedeGestion[]>([]);
  protected readonly cargando = signal(false);
  protected readonly guardando = signal(false);
  protected readonly editando = signal<string | null>(null);
  protected readonly formulario = signal<DatosSede | null>(null);
  protected readonly error = signal('');
  protected readonly aviso = signal('');

  ngOnInit(): void {
    this.cargar();
  }

  protected cargar(): void {
    this.cargando.set(true);
    this.error.set('');
    this.catalogo.sedesGestion().subscribe({
      next: (sedes) => {
        this.sedes.set(sedes);
        this.cargando.set(false);
      },
      error: (fallo: unknown) => {
        this.error.set(fallo instanceof FalloApi ? fallo.message : 'No se pudieron cargar las sedes.');
        this.cargando.set(false);
      },
    });
  }

  protected editar(sede: SedeGestion): void {
    this.operacionFotos.reiniciar(); this.fotos=[];
    this.editando.set(sede.id);
    this.formulario.set({
      nombre: sede.nombre,
      direccion: sede.direccion,
      telefono: sede.telefono,
      zona_horaria: sede.zona_horaria,
      minutos_antelacion_minima: sede.minutos_antelacion_minima,
    });
    this.error.set('');
    this.aviso.set('');
  }

  protected cancelar(): void {
    if (this.guardando()) return;
    this.editando.set(null);
    this.formulario.set(null);
    this.error.set('');
  }

  protected sedeEditada(): SedeGestion | null {
    const id = this.editando();
    return id ? this.sedes().find((sede) => sede.id === id) ?? null : null;
  }

  protected guardar(): void {
    const id = this.editando();
    const datos = this.formulario();
    if (!id || !datos || this.guardando()) return;

    this.guardando.set(true);
    this.error.set('');
    this.aviso.set('');
    this.operacionFotos.guardar('sede',this.catalogo.actualizarSede(id, datos),this.fotos).subscribe({
      next: (actualizada) => {
        this.sedes.update((actuales) => actuales.map((sede) => sede.id === id ? actualizada : sede));
        this.editando.set(null);
        this.formulario.set(null);
        this.guardando.set(false);
        this.aviso.set('La información de la sede se actualizó.');
      },
      error: (fallo: unknown) => {
        this.error.set(fallo instanceof FalloApi ? fallo.message : 'No se pudo guardar la sede.');
        this.guardando.set(false);
      },
    });
  }
}
