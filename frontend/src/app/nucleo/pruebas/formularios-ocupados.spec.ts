import { type Type, type WritableSignal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';
import { PROVEEDORES_PRUEBA } from './sesion-sintetica';
import { EquipoComponent } from '../../paginas/equipo/equipo.component';
import { GastosComponent } from '../../paginas/gastos/gastos.component';
import { AgendaConfiguracionComponent } from '../../paginas/configuracion/agenda-configuracion.component';
import { AgendaProfesionalesComponent } from '../../paginas/configuracion/agenda-profesionales.component';
import { AnamnesisConfiguracionComponent } from '../../paginas/configuracion/anamnesis-configuracion.component';
import { ConfiguracionComponent } from '../../paginas/configuracion/configuracion.component';
import { ModulosEspecialidadComponent } from '../../paginas/catalogo/modulos-especialidad.component';
import { IntegracionesIaComponent } from '../../paginas/configuracion/integraciones-ia.component';

interface Caso { nombre: string; componente: Type<unknown>; estado: string; metodo: string; argumentos?: unknown[] }
const CASOS: Caso[] = [
  { nombre: 'perfil profesional', componente: EquipoComponent, estado: 'guardando', metodo: 'guardar' },
  { nombre: 'horario de sede', componente: AgendaConfiguracionComponent, estado: 'guardando', metodo: 'guardarHorario' },
  { nombre: 'feriado', componente: AgendaConfiguracionComponent, estado: 'guardando', metodo: 'guardarFeriado' },
  { nombre: 'franja profesional', componente: AgendaProfesionalesComponent, estado: 'guardando', metodo: 'guardar' },
  { nombre: 'plantilla de anamnesis', componente: AnamnesisConfiguracionComponent, estado: 'guardando', metodo: 'guardar' },
  { nombre: 'publicar anamnesis', componente: AnamnesisConfiguracionComponent, estado: 'guardando', metodo: 'publicar' },
  { nombre: 'información clínica', componente: ConfiguracionComponent, estado: 'guardandoClinica', metodo: 'guardarClinica' },
  { nombre: 'integración SMTP', componente: ConfiguracionComponent, estado: 'guardando', metodo: 'guardar', argumentos: ['smtp'] },
  { nombre: 'activar agente WhatsApp', componente: ConfiguracionComponent, estado: 'guardandoAgenteWhatsApp', metodo: 'cambiarAgenteWhatsApp', argumentos: [true] },
  { nombre: 'configuración JEV', componente: IntegracionesIaComponent, estado: 'ocupado', metodo: 'guardarJev' },
  { nombre: 'modelo de respuestas', componente: IntegracionesIaComponent, estado: 'ocupado', metodo: 'guardarRespuestas' },
  { nombre: 'módulos de especialidad', componente: ModulosEspecialidadComponent, estado: 'guardando', metodo: 'guardar', argumentos: [{ id: 'area-sintetica' }] },
  { nombre: 'alta de gasto', componente: GastosComponent, estado: 'guardando', metodo: 'registrar', argumentos: [true] },
  { nombre: 'anular gasto', componente: GastosComponent, estado: 'guardando', metodo: 'anular', argumentos: [{ id: 'gasto-sintetico' }] },
];

describe('Formularios con petición pendiente', () => {
  it.each(CASOS)('$nombre no envía ni desbloquea otra petición durante el guardado', caso => {
    TestBed.configureTestingModule({ imports: [caso.componente], providers: PROVEEDORES_PRUEBA });
    const fixture = TestBed.createComponent(caso.componente);
    const http = TestBed.inject(HttpTestingController);
    // Solo se admiten las lecturas iniciales del constructor. No hace falta
    // renderizar hijos para probar el bloqueo del método de envío.
    const iniciales = http.match(() => true);
    expect(iniciales.every(p => p.request.method === 'GET')).toBe(true);
    const c = fixture.componentInstance as Record<string, unknown>;
    const estado = c[caso.estado] as WritableSignal<boolean>;
    estado.set(true);
    (c[caso.metodo] as (...args: unknown[]) => void).apply(c, caso.argumentos ?? []);
    http.expectNone(() => true);
    expect(estado()).toBe(true);
    http.verify();
  });
});
