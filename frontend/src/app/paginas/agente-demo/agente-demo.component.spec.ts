import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';
import { AgenteDemoComponent } from './agente-demo.component';
import { BASE, PROVEEDORES_PRUEBA } from '../../nucleo/pruebas/sesion-sintetica';

describe('AgenteDemoComponent · preparación flotante',()=>{
  let f:ComponentFixture<AgenteDemoComponent>;let http:HttpTestingController;
  beforeEach(()=>{
    TestBed.configureTestingModule({imports:[AgenteDemoComponent],providers:PROVEEDORES_PRUEBA});
    http=TestBed.inject(HttpTestingController);f=TestBed.createComponent(AgenteDemoComponent);f.detectChanges();
    http.expectOne(`${BASE}/catalogo/sedes`).flush([{id:'s',nombre:'Sede sintética',zona_horaria:'America/Guayaquil'}]);
    http.expectOne(`${BASE}/catalogo/servicios`).flush([{id:'srv',nombre:'Consulta sintética',especialidad_id:'odo'}]);
    http.expectOne(`${BASE}/catalogo/profesionales?especialidad_id=odo&sede_id=s`).flush([{id:'prof',nombre:'Profesional',apellido:'Sintético'}]);f.detectChanges();
  });
  afterEach(()=>http.verify());
  function abrir(){f.componentInstance['preparando'].set(true);f.detectChanges();http.match(r=>r.url.includes('/pacientes')).forEach(r=>r.flush({elementos:[],total:0}));}
  it('abre los parámetros al elegir Preparar conversación',()=>{
    expect(f.nativeElement.querySelector('dialog')).toBeNull();
    const boton=[...f.nativeElement.querySelectorAll('button')].find((b:HTMLButtonElement)=>b.textContent?.trim()==='Preparar conversación');
    expect(boton).toBeDefined();boton.click();f.detectChanges();
    http.match(r=>r.url.includes('/pacientes')).forEach(r=>r.flush({elementos:[],total:0}));
    const enviar=f.nativeElement.querySelector('.ventana__pie button[type="submit"]') as HTMLButtonElement;
    expect(enviar.form?.id).toBe('formulario-conversacion-demo');
    expect(enviar.disabled).toBe(true);
  });
  it('cerrar el diálogo conserva los parámetros elegidos',()=>{
    abrir();f.componentInstance['fecha']='2026-10-09';
    const cerrar=f.nativeElement.querySelector('.ventana__cerrar') as HTMLButtonElement;
    cerrar.click();f.detectChanges();expect(f.nativeElement.querySelector('dialog')).toBeNull();
    expect(f.componentInstance['fecha']).toBe('2026-10-09');
  });
  it('una petición pendiente conserva el diálogo y un error se ve dentro',()=>{
    abrir();const c=f.componentInstance;c['paciente'].set({id:'p',nombre:'Paciente',apellido:'Sintético',tipo_documento:'PASAPORTE',numero_documento:'DOC-SINTETICO',telefono_whatsapp:null,correo:null,fecha_nacimiento:null,nivel_verificacion:'NO_VERIFICADO'});
    c['iniciar']();f.detectChanges();const solicitud=http.expectOne(`${BASE}/agente-demo/sesiones`);
    expect((f.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('.ventana__cerrar')?.disabled).toBe(true);
    solicitud.flush({codigo:'PRUEBA',mensaje:'Servicio temporalmente no disponible'},{status:503,statusText:'Unavailable'});f.detectChanges();
    expect(f.nativeElement.querySelector('dialog [role="alert"]').textContent).toContain('Servicio temporalmente no disponible');
  });
});
