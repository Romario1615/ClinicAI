/**
 * Panel: el tablero muestra solo los grupos que el rol alcanza, en el orden
 * en que se atienden (mi día, la clínica hoy, lo pendiente, la gestión).
 */
import { TestBed } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';
import { of } from 'rxjs';

import { PanelComponent } from './panel.component';
import { IndicadoresService, type Indicadores } from '../../nucleo/servicios/indicadores.service';
import { PROVEEDORES_PRUEBA, iniciarSesionCon } from '../../nucleo/pruebas/sesion-sintetica';

function indicadores(extra: Partial<Indicadores>): Indicadores {
  return {
    agenda: null, mis_citas: null, pacientes: null, lista_espera: null, pagos: null, clinico: null,
    adherencia: null, mensajes: null, conocimiento: null, promociones: null, usuarios: null,
    ...extra,
  };
}

describe('PanelComponent · tablero por rol', () => {
  function montar(datos: Indicadores, permisos: readonly string[]) {
    TestBed.configureTestingModule({
      imports: [PanelComponent],
      providers: [
        ...PROVEEDORES_PRUEBA,
        { provide: IndicadoresService, useValue: { obtener: () => of(datos), refrescar: () => undefined } },
      ],
    });
    iniciarSesionCon(permisos);
    const fixture = TestBed.createComponent(PanelComponent);
    fixture.detectChanges();
    // El resto del panel (carga de hoy, cifras) no es objeto de esta prueba.
    const http = TestBed.inject(HttpTestingController);
    for (const peticion of http.match(() => true)) {
      if (!peticion.cancelled) {
        peticion.flush(peticion.request.url.endsWith('/profesionales') ? [] : { elementos: [], total: 0, limite: 200, desplazamiento: 0 });
      }
    }
    fixture.detectChanges();
    return fixture;
  }

  it('el profesional ve su día y lo pendiente; no ve gestión', () => {
    const fixture = montar(
      indicadores({
        mis_citas: { citas_hoy: 3, pendientes_hoy: 1, proxima_inicio: null },
        agenda: { citas_hoy: 9, por_confirmar_hoy: 2, en_sala: 0, en_atencion: 1, atendidas_hoy: 4, inasistencias_hoy: 0, citas_proximos_7_dias: 30 },
        clinico: { recetas_por_confirmar: 1, planes_propuestos: 0, planes_en_curso: 2 },
      }),
      ['agenda.leer'],
    );
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const grupos = (fixture.componentInstance as any).tablero().map((g: { titulo: string }) => g.titulo);
    expect(grupos).toEqual(['Mi día', 'La clínica hoy', 'Pendiente de atender']);
    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Mis citas de hoy');
    expect(texto).toContain('Recetas por confirmar');
  });

  it('administración ve la gestión de la clínica', () => {
    const fixture = montar(
      indicadores({
        usuarios: { activos: 10, inactivos: 0, roles: 5 },
        pagos: { pendientes: 0, por_validar: 1, confirmado_30_dias: '100' },
      }),
      ['usuario.leer'],
    );
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const grupos = (fixture.componentInstance as any).tablero().map((g: { titulo: string }) => g.titulo);
    expect(grupos).toEqual(['Pendiente de atender', 'Gestión de la clínica']);
  });
});
