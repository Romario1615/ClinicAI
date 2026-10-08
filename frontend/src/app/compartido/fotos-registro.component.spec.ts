import { TestBed } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';
import { FotosRegistroComponent } from './fotos-registro.component';
import { BASE,PROVEEDORES_PRUEBA,archivo } from '../nucleo/pruebas/sesion-sintetica';

describe('FotosRegistroComponent',()=>{
  let http:HttpTestingController;
  function montar(editar=false){const f=TestBed.createComponent(FotosRegistroComponent);f.componentRef.setInput('tipo','gasto');f.componentRef.setInput('registroId','g');f.componentRef.setInput('puedeEditar',editar);f.detectChanges();return f;}
  beforeEach(()=>{TestBed.configureTestingModule({imports:[FotosRegistroComponent],providers:PROVEEDORES_PRUEBA});http=TestBed.inject(HttpTestingController);});afterEach(()=>http.verify());
  it('no descarga hasta abrir la ventana y libera imágenes al cerrar',()=>{
    const f=montar();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c=f.componentInstance as any;
    http.expectNone(`${BASE}/fotos-registro/gasto/g`);c.abierta.set(true);f.detectChanges();
    http.expectOne(`${BASE}/fotos-registro/gasto/g`).flush([{id:'a',descripcion:'Sintética'}]);
    http.expectOne(`${BASE}/fotos-registro/gasto/g/a/contenido`).flush(new Blob(['foto']));f.detectChanges();expect(c.urls().size).toBe(1);
    expect(f.nativeElement.textContent).toContain('Sintética');expect(f.nativeElement.querySelector('app-captura-fotos')).toBeNull();
    c.abierta.set(false);f.detectChanges();expect(c.urls().size).toBe(0);
  });
  it('permite adjuntar y retirar, informa errores',()=>{
    const f=montar(true);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c=f.componentInstance as any;
    c.abierta.set(true);f.detectChanges();http.expectOne(`${BASE}/fotos-registro/gasto/g`).flush([]);
    c.pendientes=[{id:'f',archivo:archivo('f.png','x','image/png'),url:'blob:x',descripcion:''}];c.guardar();http.expectOne(`${BASE}/fotos-registro/gasto/g`).flush({});http.expectOne(`${BASE}/fotos-registro/gasto/g`).flush([]);expect(c.ocupado()).toBe(false);
    c.retirando.set('f');c.motivo='Retirada sintética';c.retirar();http.expectOne(`${BASE}/fotos-registro/gasto/g/f/retirar`).flush(null);http.expectOne(`${BASE}/fotos-registro/gasto/g`).flush([]);expect(c.retirando()).toBeNull();
    c.retirar();c.retirando.set('f');c.retirar();http.expectOne(`${BASE}/fotos-registro/gasto/g/f/retirar`).flush({codigo:'F',mensaje:'Denegado'},{status:403,statusText:'Forbidden'});expect(c.error()).toBe('Denegado');
  });
  it('ignora respuestas de una ficha que ya cambió',()=>{
    const f=montar();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c=f.componentInstance as any;
    c.abierta.set(true);f.detectChanges();const vieja=http.expectOne(`${BASE}/fotos-registro/gasto/g`);
    f.componentRef.setInput('registroId','nuevo');f.detectChanges();http.expectOne(`${BASE}/fotos-registro/gasto/nuevo`).flush([]);vieja.flush([{id:'vieja'}]);expect(c.fotos()).toHaveLength(0);
  });
});
