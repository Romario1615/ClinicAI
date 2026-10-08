import { TestBed } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';
import { PeriodontogramaComponent } from './periodontograma.component';
import { compararPeriodontogramas, piezaVacia, sitioVacio, type Periodontograma } from './periodontograma.modelos';
import { BASE,PROVEEDORES_PRUEBA,iniciarSesionCon } from '../../nucleo/pruebas/sesion-sintetica';

export function examen():Periodontograma {
  return {id:'e-1',raiz_id:'e-1',version:1,paciente_id:'p',profesional_id:'prof',especialidad_id:'odo',sede_id:'s',cita_id:null,fecha_examen:'2026-04-15',piezas:{'16':{...piezaVacia(),sitios:{VM:{...sitioVacio(),profundidad:4,margen:2,sangrado:true}}}},observaciones:'Sintética',motivo:'Control sintético',nivel_sensibilidad:'N2',anulado:false,vigente:true,puede_editar:true,creado_en:'2026-04-15T12:00:00Z',resumen:{sitios_posibles:192,sitios_sondados:1,profundidad_media:4,insercion_media:6,sangrado_positivos:1,sangrado_evaluados:1,sangrado_porcentaje:100,placa_positivos:0,placa_evaluados:0,placa_porcentaje:null,sitios_insercion:1,sitios_4_5:1,sitios_6_mas:0}};
}
describe('Mediciones periodontales',()=>{
  it('una pieza vacía conserva desconocidos, compara solo sitios comunes',()=>{
    expect(sitioVacio().profundidad).toBeNull();const a=examen(),b=examen();b.piezas['16'].sitios.VM!.profundidad=2;
    expect(compararPeriodontogramas(a,b)).toEqual({sitios:1,diferencia:2});
    b.piezas['16'].ausente=true;expect(compararPeriodontogramas(a,b).sitios).toBe(0);
    b.piezas['16'].ausente=false;b.piezas['16'].implante=true;expect(compararPeriodontogramas(a,b).diferencia).toBeNull();
  });
});
describe('PeriodontogramaComponent',()=>{
  let http:HttpTestingController;
  const ruta=`${BASE}/odontologia/pacientes/p/periodontogramas`;
  function montar(registros:Periodontograma[]=[],escribir=true){iniciarSesionCon(escribir?['odontograma.leer','odontograma.escribir']:['odontograma.leer']);const f=TestBed.createComponent(PeriodontogramaComponent);f.componentRef.setInput('pacienteId','p');f.detectChanges();http.expectOne(ruta).flush(registros);f.detectChanges();return f;}
  beforeEach(()=>{TestBed.configureTestingModule({imports:[PeriodontogramaComponent],providers:PROVEEDORES_PRUEBA});http=TestBed.inject(HttpTestingController);});afterEach(()=>http.verify());
  it('deja Guardar examen fijo y el editor de los seis sitios dentro del cuerpo',()=>{
    const f=montar();f.componentInstance['nuevo']();http.expectOne(`${BASE}/catalogo/sedes`).flush([]);f.detectChanges();
    const raiz=f.nativeElement as HTMLElement;
    const boton=raiz.querySelector<HTMLButtonElement>('.ventana__pie button[type="submit"]');
    expect(boton?.form?.id).toBe('formulario-periodontograma');
    f.componentInstance['abrirPieza'](16);f.detectChanges();
    expect(raiz.querySelectorAll('.ventana__cuerpo .perio__sitio')).toHaveLength(6);
    expect(boton?.disabled).toBe(true);
  });
  it('abre seis sitios por pieza y guarda una observación con su sede',()=>{
    const f=montar();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c=f.componentInstance as any;
    c.nuevo();http.expectOne(`${BASE}/catalogo/sedes`).flush([{id:'s',nombre:'Sede sintética'}]);c.sede='s';c.abrirPieza(16);expect(Object.keys(c.pieza.sitios)).toHaveLength(6);
    c.pieza.sitios.VM.profundidad=4;c.pieza.sitios.VM.margen=2;c.confirmarPieza();expect(c.valor(16,'VM')).toBe(4);expect(c.altura(16,'VM')).toBe(24);
    c.motivo='Control sintético';c.guardar();const r=http.expectOne({method:'POST',url:ruta});expect(r.request.body.sede_id).toBe('s');expect(r.request.body.version_anterior_id).toBeNull();r.flush(examen());http.expectOne(ruta).flush([examen()]);expect(c.editor()).toBe(false);
  });
  it('pieza ausente e implante limpian mediciones incompatibles',()=>{
    const f=montar();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c=f.componentInstance as any;
    c.nuevo();http.expectOne(`${BASE}/catalogo/sedes`).flush([]);c.abrirPieza(16);c.pieza.ausente=true;c.pieza.movilidad=2;c.confirmarPieza();expect(c.ausente(16)).toBe(true);expect(c.borrador['16'].sitios).toEqual({});
    c.abrirPieza(15);c.pieza.implante=true;c.pieza.furcacion=2;c.confirmarPieza();expect(c.borrador['15'].furcacion).toBeNull();c.confirmarPieza();
  });
  it('corrige conservando la cita, anula con motivo y muestra el rechazo',()=>{
    const f=montar([examen()]);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c=f.componentInstance as any;
    c.nuevo(true);http.expectOne(`${BASE}/catalogo/sedes`).flush([]);expect(c.corrigiendo()).toBe(true);c.motivo='Anulación sintética';c.guardar(true);const r=http.expectOne({method:'POST',url:ruta});expect(r.request.body.version_anterior_id).toBe('e-1');expect(r.request.body.anulado).toBe(true);r.flush({codigo:'CAMBIO',mensaje:'Recargue la última versión'},{status:409,statusText:'Conflict'});expect(c.error()).toContain('última versión');expect(c.ocupado()).toBe(false);
  });
  it('solo lectura conserva las mediciones y no ofrece un nuevo examen',()=>{
    const r=examen();r.puede_editar=false;const f=montar([r],false);expect(f.nativeElement.textContent).not.toContain('Nuevo examen');expect(f.nativeElement.textContent).toContain('4.0 mm');
  });
  it('descarga PDF y presenta errores sin bloquear el editor',()=>{
    const f=montar([examen()]);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c=f.componentInstance as any;
    c.descargar();http.expectOne(`${ruta}/e-1/pdf`).flush(new Blob(['%PDF-sintético']));expect(c.ocupado()).toBe(false);
    c.descargar();http.expectOne(`${ruta}/e-1/pdf`).flush(new Blob([]),{status:503,statusText:'Unavailable'});expect(c.ocupado()).toBe(false);expect(c.error()).toBeTruthy();
  });
});
