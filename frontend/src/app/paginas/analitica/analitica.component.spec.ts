import { TestBed } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';
import { AnaliticaComponent } from './analitica.component';
import { GraficoKpiComponent } from './grafico-kpi.component';
import { grupoIndicador, rutaSerie, type AnaliticaDashboard, type KpiAnalitico } from './analitica.modelos';
import { BASE,PROVEEDORES_PRUEBA } from '../../nucleo/pruebas/sesion-sintetica';

const kpi:KpiAnalitico={clave:'citas',nombre:'Citas',unidad:'citas',definicion:'Turnos del ámbito',total:6,agregacion:'suma',historia:[{fecha:'2026-04-13',valor:2,muestras:2},{fecha:'2026-04-14',valor:null,muestras:0}],prediccion:[{fecha:'2026-04-15',valor:3,inferior:2,superior:4}],evidencia:{estado:'validado_localmente',motivo:'Evaluado con fechas posteriores',algoritmo:'Patrón semanal aprendido',observaciones:100,dias_historia:100,dias_seleccion:7,dias_evaluacion:7,mae:0,mae_base:1,mejora_porcentaje:100,entrenado_hasta:'2026-04-14',evaluacion_desde:'2026-04-08',evaluacion_hasta:'2026-04-14',banda:'Error empírico, sin probabilidad calibrada'}};
const datos:AnaliticaDashboard={generado_en:'2026-04-15T12:00:00Z',zona_horaria:'America/Guayaquil',desde:'2026-01-01',hasta:'2026-04-14',horizonte:14,kpis:[kpi],recomendaciones:[{titulo:'Revisar reservas',motivo:'Hay turnos pendientes',accion:'Contactar tras revisión',ruta:'/agenda',prioridad:'media',kpis:['citas'],requiere_revision:true}],limites:['Sin decisiones clínicas automáticas']};
describe('Rutas SVG de series',()=>{
  it('representa la misma escala, fechas y amplitud para histórico y pronóstico',()=>{
    TestBed.configureTestingModule({imports:[GraficoKpiComponent]});
    const f=TestBed.createComponent(GraficoKpiComponent);
    f.componentRef.setInput('kpi',{...kpi,historia:[{fecha:'2026-04-12',valor:0,muestras:1},{fecha:'2026-04-13',valor:5,muestras:5},{fecha:'2026-04-14',valor:10,muestras:10}],prediccion:[{fecha:'2026-04-15',valor:5,inferior:0,superior:10}]});
    f.componentRef.setInput('predictivo',true);f.detectChanges();
    // Unidades 0..10: eje Y 180..32; cuatro fechas equidistantes en X 32..568.
    const c=f.componentInstance as unknown as {historico():string;futuro():string;banda():string;primeraFecha():string;ultimaFecha():string};
    expect(c.historico()).toBe('M32.0,180.0 L210.7,106.0 L389.3,32.0');
    expect(c.futuro()).toBe('M389.3,32.0 L568.0,106.0');
    expect(c.banda()).toContain('568.0,32.0');expect(c.banda()).toContain('568.0,180.0');
    expect(c.primeraFecha()).toBe('2026-04-12');expect(c.ultimaFecha()).toBe('2026-04-15');
  });
  it('no une tramos desconocidos ni divide por cero',()=>{expect(rutaSerie([0,null,4],4)).toBe('M32.0,180.0  M568.0,32.0');expect(rutaSerie([1],0)).not.toContain('NaN');expect(rutaSerie([],1)).toBe('');});
  it('el gráfico alterna histórico, pronóstico y banda de error',()=>{
    TestBed.configureTestingModule({imports:[GraficoKpiComponent]});const f=TestBed.createComponent(GraficoKpiComponent);f.componentRef.setInput('kpi',kpi);f.detectChanges();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c=f.componentInstance as any;
    expect(c.futuro()).toBe('');expect(c.banda()).toBe('');f.componentRef.setInput('predictivo',true);f.detectChanges();expect(c.banda()).toContain(' Z');expect(c.ultimaFecha()).toBe('2026-04-15');expect(f.nativeElement.textContent).toContain('Pronóstico');
    f.componentRef.setInput('kpi',{...kpi,historia:[],prediccion:[]});f.detectChanges();expect(c.primeraFecha()).toBe('');expect(f.nativeElement.textContent).toContain('Sin observaciones');
  });
  it('diferencia una serie desconocida de una medición cero y dibuja puntos aislados',()=>{
    TestBed.configureTestingModule({imports:[GraficoKpiComponent]});
    const f=TestBed.createComponent(GraficoKpiComponent);
    f.componentRef.setInput('kpi',{...kpi,historia:[{fecha:'2026-04-14',valor:null,muestras:0}],prediccion:[]});f.detectChanges();
    expect(f.nativeElement.querySelector('svg')).toBeNull();expect(f.nativeElement.textContent).toContain('no se representan como cero');
    f.componentRef.setInput('kpi',{...kpi,historia:[{fecha:'2026-04-14',valor:0,muestras:1}],prediccion:[]});f.detectChanges();
    expect(f.nativeElement.querySelector('svg circle').getAttribute('cy')).toBe('180');
    expect(f.nativeElement.querySelector('svg path').getAttribute('d')).toBe('M32.0,180.0');
  });
  it('conserva los huecos al conectar pronóstico y permite ocultar el título repetido',()=>{
    TestBed.configureTestingModule({imports:[GraficoKpiComponent]});const f=TestBed.createComponent(GraficoKpiComponent);
    f.componentRef.setInput('kpi',kpi);f.componentRef.setInput('predictivo',true);f.componentRef.setInput('mostrarTitulo',false);f.detectChanges();
    expect(f.nativeElement.querySelector('figcaption')).toBeNull();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c=f.componentInstance as any;
    expect(c.futuro().trim().startsWith('M568.0')).toBe(true);
    expect(c.puntosVisibles()).toHaveLength(1);
    f.componentRef.setInput('kpi',{...kpi,historia:[]});f.detectChanges();
    expect(c.primeraFecha()).toBe('2026-04-15');expect(c.ultimoPronostico()).not.toBeNull();
    f.componentRef.setInput('kpi',{...kpi,historia:[{fecha:'2026-04-14',valor:2,muestras:2}]});f.detectChanges();
    expect(c.futuro()).toContain('L568.0');
  });
  it('agrupa series y capturas sin asumir permisos ni omitir indicadores nuevos',()=>{
    for(const clave of ['citas','estado.agenda.citas_hoy','estado.mis_citas.citas_hoy','estado.lista_espera.en_espera']) expect(grupoIndicador(clave).clave).toBe('agenda');
    for(const clave of ['cobros','gastos','ingreso_por_atencion','estado.pagos.pendientes']) expect(grupoIndicador(clave).clave).toBe('finanzas');
    for(const clave of ['registros_pacientes','pacientes_dia','estado.pacientes.total']) expect(grupoIndicador(clave).clave).toBe('pacientes');
    for(const clave of ['estado.clinico.recetas_por_confirmar','estado.adherencia.alertas_abiertas']) expect(grupoIndicador(clave).clave).toBe('seguimiento');
    expect(grupoIndicador('indicador_futuro').clave).toBe('operacion');
  });
});
describe('AnaliticaComponent',()=>{
  let http:HttpTestingController;
  function montar(){const f=TestBed.createComponent(AnaliticaComponent);f.detectChanges();http.expectOne(`${BASE}/catalogo/sedes`).flush([]);http.expectOne(r=>r.url===`${BASE}/dashboard/analitica`).flush(datos);f.detectChanges();return f;}
  beforeEach(()=>{TestBed.configureTestingModule({imports:[AnaliticaComponent],providers:PROVEEDORES_PRUEBA});http=TestBed.inject(HttpTestingController);});afterEach(()=>http.verify());
  it('usa una sección etiquetada dentro del main del armazón',()=>{
    const f=montar();const section=f.nativeElement.querySelector('section.analitica');
    expect(f.nativeElement.querySelector('main')).toBeNull();
    expect(section.getAttribute('aria-labelledby')).toBe('titulo-analitica');
    expect(section.querySelector('#titulo-analitica')?.tagName).toBe('H1');
  });
  it('describe valores, explica la evaluación y ofrece revisión humana',()=>{
    const f=montar();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c=f.componentInstance as any;
    expect(f.nativeElement.textContent).toContain('1 indicadores autorizados');c.tab.set('predictivo');f.detectChanges();
    f.nativeElement.querySelector('.analitica__ver-detalle').click();f.detectChanges();
    expect(f.nativeElement.querySelector('app-ventana-flotante').textContent).toContain('error absoluto medio');
    expect(f.nativeElement.querySelector('table').textContent).toContain('Sin evaluar');
    c.detalle.set(null);f.detectChanges();
    expect(c.estado('insuficiente')).toBe('Falta historial');expect(c.estado('experimental')).toBe('En evaluación');expect(c.estado('otra')).toBe('otra');
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
  it('busca sin distinguir tildes, combina el área y recupera todos los resultados',()=>{
    const f=montar();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c=f.componentInstance as any;
    c.datos.set({...datos,kpis:[kpi,{...kpi,clave:'cobros',nombre:'Cobros confirmados',unidad:'USD',definicion:'Importes recibidos'}]});
    c.busqueda.set(' AMBITO ');f.detectChanges();expect(c.indicadores()).toHaveLength(1);expect(c.indicadores()[0].clave).toBe('citas');
    c.busqueda.set('');c.grupo.set('finanzas');f.detectChanges();expect(c.indicadores()[0].clave).toBe('cobros');
    expect(c.grupos().map((g:{clave:string})=>g.clave)).toEqual(['agenda','finanzas']);
    c.busqueda.set('no existe');f.detectChanges();expect(f.nativeElement.textContent).toContain('Sin coincidencias');
    f.nativeElement.querySelector('.analitica__vacio button').click();f.detectChanges();expect(c.indicadores()).toHaveLength(2);
    expect(c.modelosEvaluados()).toBe(2);
  });
  it('restablece un área no autorizada tras actualizar y cierra detalles anteriores',()=>{
    const f=montar();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c=f.componentInstance as any;
    c.grupo.set('finanzas');c.detalle.set(kpi);c.mostrarLimites.set(true);c.cargar();f.detectChanges();
    expect(c.detalle()).toBeNull();expect(c.mostrarLimites()).toBe(false);
    expect(f.nativeElement.querySelector('form button').disabled).toBe(true);
    http.expectOne(r=>r.url===`${BASE}/dashboard/analitica`).flush(datos);f.detectChanges();
    expect(c.grupo()).toBe('todos');expect(c.indicadores()).toHaveLength(1);
  });
  it('abre límites en ventana flotante y presenta la hora de la clínica',()=>{
    const f=montar();
    f.nativeElement.querySelector('.analitica__alcance').click();f.detectChanges();
    expect(f.nativeElement.querySelector('app-ventana-flotante').textContent).toContain('Sin decisiones clínicas automáticas');
    const cerrar=[...f.nativeElement.querySelectorAll('app-ventana-flotante button')].find((b)=> (b as HTMLButtonElement).textContent?.includes('Volver al análisis')) as HTMLButtonElement;
    cerrar.click();f.detectChanges();expect(f.nativeElement.querySelector('app-ventana-flotante')).toBeNull();
    expect(f.nativeElement.querySelector('.analitica__actualizacion').textContent).toContain('7:00');
  });
  it('mantiene el resumen de filtros aplicado al editar la ventana sin consultar',()=>{
    const f=montar();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c=f.componentInstance as any;
    f.nativeElement.querySelector('.analitica__filtros-movil button').click();f.detectChanges();
    expect(f.nativeElement.querySelector('app-ventana-flotante')).not.toBeNull();
    c.dias=90;c.horizonte=7;f.detectChanges();
    expect(f.nativeElement.querySelector('.analitica__filtros-movil').textContent).toContain('180 días de historial · 14 días de previsión');
    c.cargar();http.expectOne(r=>r.url===`${BASE}/dashboard/analitica`).flush({...datos,horizonte:7});f.detectChanges();
    expect(c.mostrarFiltros()).toBe(false);
    expect(f.nativeElement.querySelector('.analitica__filtros-movil').textContent).toContain('90 días de historial · 7 días de previsión');
  });
  it('explica el error, reintenta desde la interfaz y contempla recomendaciones vacías',()=>{
    const f=montar();
    f.nativeElement.querySelector('form button').click();f.detectChanges();
    http.expectOne(r=>r.url===`${BASE}/dashboard/analitica`).flush({codigo:'F',mensaje:'Sin acceso'},{status:403,statusText:'Forbidden'});f.detectChanges();
    expect(f.nativeElement.querySelector('[role=alert]').textContent).toContain('Sin acceso');
    f.nativeElement.querySelector('[role=alert] button').click();f.detectChanges();
    http.expectOne(r=>r.url===`${BASE}/dashboard/analitica`).flush({...datos,recomendaciones:[]});f.detectChanges();
    (f.nativeElement.querySelectorAll('.analitica__tabs button')[2] as HTMLButtonElement).click();f.detectChanges();
    expect(f.nativeElement.textContent).toContain('Sin propuestas para revisar');
  });
});
