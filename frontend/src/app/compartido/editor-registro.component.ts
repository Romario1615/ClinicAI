import { ChangeDetectionStrategy, Component, inject, input, OnInit, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { OperacionesService } from '../nucleo/servicios/operaciones.service';
import { VentanaFlotanteComponent } from './ventana-flotante.component';

@Component({
  selector: 'app-editor-registro', standalone: true, imports: [FormsModule, VentanaFlotanteComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <app-ventana-flotante [titulo]="titulo()" ceja="Gestión de registros" forma="centrada" [anchoMaximo]="660" [cierraAlPulsarFuera]="false" [ocupada]="ocupado()" (cerrar)="cancelar()">
      @if (error()) { <p role="alert">{{ error() }}</p> }
      @if (cargando()) { <p role="status">Cargando datos…</p> }
      <form id="editar-registro" #formulario="ngForm" (ngSubmit)="guardar()">
        @if (estado() !== null) {
          <p>{{ estado() ? 'Se restaurará el acceso al registro.' : 'Se desactivará el acceso y se conservará el historial.' }}</p>
          <label class="campo">Motivo<textarea class="campo__control" name="motivo" [(ngModel)]="motivo" required minlength="5" maxlength="500"></textarea></label>
        } @else {
          @for (campo of campos(); track campo.clave) {
            <label class="campo">{{ campo.etiqueta }}<input class="campo__control" [disabled]="cargando() || ocupado()" [type]="campo.clave === 'correo' ? 'email' : 'text'" [name]="campo.clave" [attr.name]="campo.clave" [(ngModel)]="datos[campo.clave]" [required]="campo.obligatorio" [maxlength]="campo.maximo" /></label>
          }
        }
      </form>
      <div pie class="acciones"><button class="boton" type="button" (click)="cancelar()" [disabled]="ocupado()">Cancelar</button><button class="boton boton--principal" type="submit" form="editar-registro" [disabled]="ocupado() || cargando() || formulario.invalid">{{ ocupado() ? 'Guardando…' : 'Guardar cambios' }}</button></div>
    </app-ventana-flotante>
  `,
  styles: `.acciones{display:flex;gap:12px;justify-content:flex-end;flex-wrap:wrap} .campo{margin-bottom:14px}`,
})
export class EditorRegistroComponent implements OnInit {
  private readonly api = inject(OperacionesService);
  readonly tipo = input.required<'clinica' | 'usuario'>();
  readonly ruta = input.required<string>();
  readonly titulo = input('Editar datos');
  readonly inicial = input<{ nombre: string; apellido?: string; correo?: string | null }>({ nombre: '' });
  readonly estado = input<boolean | null>(null);
  readonly guardado = output<void>();
  readonly cerrar = output<void>();
  protected readonly error = signal('');
  protected readonly ocupado = signal(false);
  protected readonly cargando = signal(false);
  protected motivo = '';
  protected datos: Record<string, string | null> = {};
  protected campos(): { clave: string; etiqueta: string; obligatorio: boolean; maximo: number }[] {
    const campos = [{ clave: 'nombre', etiqueta: 'Nombre', obligatorio: true, maximo: this.tipo() === 'usuario' ? 100 : 200 }, { clave: 'correo', etiqueta: 'Correo', obligatorio: this.tipo() === 'usuario', maximo: 200 }];
    return this.tipo() === 'usuario' ? [...campos, { clave: 'apellido', etiqueta: 'Apellido', obligatorio: true, maximo: 100 }] : [...campos,
      { clave: 'identificacion_fiscal', etiqueta: 'Identificación fiscal', obligatorio: false, maximo: 50 },
      { clave: 'telefono', etiqueta: 'Teléfono', obligatorio: false, maximo: 32 },
      { clave: 'zona_horaria', etiqueta: 'Zona horaria IANA', obligatorio: true, maximo: 64 },
      { clave: 'moneda', etiqueta: 'Moneda (USD, EUR…)', obligatorio: true, maximo: 3 },
      { clave: 'idioma', etiqueta: 'Idioma', obligatorio: true, maximo: 8 }];
  }
  ngOnInit(): void {
    this.datos = { nombre: this.inicial().nombre, apellido: this.inicial().apellido ?? '', correo: this.inicial().correo ?? '' };
    if (this.tipo() === 'clinica' && this.estado() === null) {
      this.cargando.set(true);
      this.api.leer<Record<string, string | null>>(this.ruta() + '/datos').subscribe({
        next: datos => { this.datos = datos; this.cargando.set(false); },
        error: error => { this.error.set(error.message); this.cargando.set(false); },
      });
    }
  }
  protected cancelar(): void { if (!this.ocupado()) this.cerrar.emit(); }
  protected guardar(): void {
    if (this.ocupado() || this.cargando()) return;
    const datos = this.estado() !== null ? { activo: this.estado(), motivo: this.motivo } : Object.fromEntries(this.campos().map(c => [c.clave, this.datos[c.clave] || null]));
    this.ocupado.set(true); this.error.set('');
    this.api.guardar(this.ruta() + (this.estado() === null ? '/datos' : '/estado'), datos, crypto.randomUUID(), true).subscribe({
      next: () => { this.ocupado.set(false); this.guardado.emit(); },
      error: error => { this.ocupado.set(false); this.error.set(error.message); },
    });
  }
}
