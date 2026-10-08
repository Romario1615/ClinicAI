import { TestBed } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';
import { AnaliticaComponent } from './analitica.component';
import { GraficoKpiComponent } from './grafico-kpi.component';
import { rutaSerie, type AnaliticaDashboard, type KpiAnalitico } from './analitica.modelos';
import { BASE,PROVEEDORES_PRUEBA } from '../../nucleo/pruebas/sesion-sintetica';

const kpi:KpiAnalitico={clave:'citas',nombre:'Citas',unidad:'citas',definicion:'Turnos del ámbito',total:6,agregacion:'suma',historia:[{fecha:'2026-04-13',valor:2,muestras:2},{fecha:'2026-04-14',valor:null,muestras:0}],prediccion:[{fecha:'2026-04-15',valor:3,inferior:2,superior:4}],evidencia:{estado:'validado_localmente',motivo:'Evaluado con fechas posteriores',algoritmo:'Patrón semanal aprendido',observaciones:100,dias_historia:100,dias_seleccion:7,dias_evaluacion:7,mae:0,mae_base:1,mejora_porcentaje:100,entrenado_hasta:'2026-04-14',evaluacion_desde:'2026-04-08',evaluacion_hasta:'2026-04-14',banda:'Error empírico, sin probabilidad calibrada'}};
const datos:AnaliticaDashboard={generado_en:'2026-04-15T12:00:00Z',zona_horaria:'America/Guayaquil',desde:'2026-01-01',hasta:'2026-04-14',horizonte:14,kpis:[kpi],recomendaciones:[{titulo:'Revisar reservas',motivo:'Hay turnos pendientes',accion:'Contactar tras revisión',ruta:'/agenda',prioridad:'media',kpis:['citas'],requiere_revision:true}],limites:['Sin decisiones clínicas automáticas']};
describe('Rutas SVG de series',()=>{
  it('no une tramos desconocidos ni divide por cero',()=>{expect(rutaSerie([0,null,4],4)).toBe('M32.0,180.0  M568.0,32.0');expect(rutaSerie([1],0)).not.toContain('NaN');expect(rutaSerie([],1)).toBe('');});
  it('el gráfico alterna histórico, pronóstico y banda de error',()=>{
    TestBed.configureTestingModule({imports:[GraficoKpiComponent]});const f=TestBed.createComponent(GraficoKpiComponent);f.componentRef.setInput('kpi',kpi);f.detectChanges();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c=f.componentInstance as any;
    expect(c.futuro()).toBe('');expect(c.banda()).toBe('');f.componentRef.setInput('predictivo',true);f.detectChanges();expect(c.banda()).toContain(' Z');expect(c.ultimaFecha()).toBe('2026-04-15');expect(f.nativeElement.textContent).toContain('Pronóstico');
    f.componentRef.setInput('kpi',{...kpi,historia:[],prediccion:[]});f.detectChanges();expect(c.primeraFecha()).toBe('');expect(f.nativeElement.textContent).toContain('Sin observaciones');
  });
});
describe('AnaliticaComponent',()=>{
  let http:HttpTestingController;
  function montar(){const f=TestBed.createComponent(AnaliticaComponent);f.detectChanges();http.expectOne(`${BASE}/catalogo/sedes`).flush([]);http.expectOne(r=>r.url===`${BASE}/dashboard/analitica`).flush(datos);f.detectChanges();return f;}
  beforeEach(()=>{TestBed.configureTestingModule({imports:[AnaliticaComponent],providers:PROVEEDORES_PRUEBA});http=TestBed.inject(HttpTestingController);});afterEach(()=>http.verify());
  it('describe valores, explica la evaluación y ofrece revisión humana',()=>{
    const f=montar();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c=f.componentInstance as any;
    expect(f.nativeElement.textContent).toContain('1 indicadores autorizados');c.tab.set('predictivo');f.detectChanges();expect(f.nativeElement.textContent).toContain('error absoluto medio');expect(c.estado('insuficiente')).toBe('Falta historial');expect(c.estado('experimental')).toBe('En evaluación');expect(c.estado('otra')).toBe('otra');
    c.tab.set('prescriptivo');f.detectChanges();expect(f.nativeElement.textContent).toContain('Revisar reservas');expect(f.nativeElement.textContent).toContain('REVISIÓN HUMANA');
  });
  it('aplica sede y horizonte; al fallar elimina cifras anteriores',()=>{
    const f=montar();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c=f.componentInstance as any;
    c.sede='s';c.dias=90;c.horizonte=7;c.cargar();const r=http.expectOne(r=>r.url===`${BASE}/dashboard/analitica`);expect(r.request.params.get('sede_id')).toBe('s');expect(r.request.params.get('horizonte')).toBe('7');r.flush({codigo:'F',mensaje:'Sin acceso'},{status:403,statusText:'Forbidden'});expect(c.datos()).toBeNull();expect(c.error()).toBe('Sin acceso');
  });
  it('ignora respuestas anteriores y explica el ámbito vacío',()=>{
    const f=montar();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c=f.componentInstance as any;
    c.cargar();const antigua=http.expectOne(r=>r.url===`${BASE}/dashboard/analitica`);c.cargar();http.expectOne(r=>r.url===`${BASE}/dashboard/analitica`).flush({...datos,kpis:[]});antigua.flush(datos);f.detectChanges();expect(c.datos().kpis).toHaveLength(0);expect(f.nativeElement.textContent).toContain('No hay indicadores');
  });
});
