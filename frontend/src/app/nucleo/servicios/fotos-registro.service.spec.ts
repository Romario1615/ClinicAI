import { TestBed } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';
import { defer, of } from 'rxjs';
import { FotosRegistroService } from './fotos-registro.service';
import { BASE,PROVEEDORES_PRUEBA,archivo } from '../pruebas/sesion-sintetica';
import { type FotoSeleccionada } from '../../compartido/captura-fotos.component';

describe('FotosRegistroService',()=>{
  let api:FotosRegistroService,http:HttpTestingController;
  const foto:FotoSeleccionada={id:'foto-1',archivo:archivo('imagen.png','sintético','image/png'),url:'blob:sintetico',descripcion:'Comprobante'};
  beforeEach(()=>{TestBed.configureTestingModule({providers:PROVEEDORES_PRUEBA});api=TestBed.inject(FotosRegistroService);http=TestBed.inject(HttpTestingController);});
  afterEach(()=>http.verify());
  it('lista y descarga por el API privado y retira con motivo',()=>{
    api.listar('gasto','g-1').subscribe();http.expectOne(`${BASE}/fotos-registro/gasto/g-1`).flush([]);
    api.contenido('gasto','g-1','f-1').subscribe();const r=http.expectOne(`${BASE}/fotos-registro/gasto/g-1/f-1/contenido`);expect(r.request.responseType).toBe('blob');r.flush(new Blob(['sintético']));
    api.retirar('gasto','g-1','f-1','Retirada sintética').subscribe();const retiro=http.expectOne(`${BASE}/fotos-registro/gasto/g-1/f-1/retirar`);expect(retiro.request.body.motivo).toBe('Retirada sintética');retiro.flush(null);
  });
  it.each([['gasto','POST','/fotos-registro/gasto/g-1'],['perfil_paciente','POST','/pacientes/g-1/foto-perfil'],['perfil_usuario','PUT','/usuarios/g-1/foto']])('sube %s conservando su endpoint', (tipo,metodo,ruta)=>{
    api.subir(tipo,'g-1',foto).subscribe();const r=http.expectOne(`${BASE}${ruta}`);expect(r.request.method).toBe(metodo);expect(r.request.body.get('clave_idempotencia')).toBe('foto-1');expect(r.request.body.get('descripcion')).toBe('Comprobante');r.flush({});
  });
  it('sin fotografías no hace llamadas adicionales',()=>{let resultado;api.finalizar('gasto',{id:'g'},[]).subscribe(r=>resultado=r);expect(resultado).toEqual({registro:{id:'g'},fallo:'',pendientes:[]});});
  it('un fallo de foto permite reintentar sin crear dos registros',()=>{
    let altas=0;const crear=defer(()=>{altas++;return of({id:'g-1'});}), op=api.operacion<{id:string}>();let mensaje='';
    op.guardar('gasto',crear,[foto]).subscribe({error:e=>mensaje=e.message});
    http.expectOne(`${BASE}/fotos-registro/gasto/g-1`).flush({codigo:'ALMACEN',mensaje:'Almacén sin conexión'},{status:503,statusText:'Unavailable'});
    expect(mensaje).toContain('registro ya se guardó');expect(op.guardado).toBe(true);
    op.guardar('gasto',crear,[foto]).subscribe();http.expectOne(`${BASE}/fotos-registro/gasto/g-1`).flush({});expect(altas).toBe(1);
    op.reiniciar();expect(op.guardado).toBe(false);op.guardar('gasto',crear,[]).subscribe();expect(altas).toBe(2);
  });
  it('devuelve solo fotos pendientes y conserva la primera causa',()=>{
    let fallo='',pendientes=0;
    api.finalizar('gasto',{id:'g'},[foto,{...foto,id:'foto-2',descripcion:''}]).subscribe(r=>{fallo=r.fallo;pendientes=r.pendientes.length;});
    http.expectOne(`${BASE}/fotos-registro/gasto/g`).flush({});const r=http.expectOne(`${BASE}/fotos-registro/gasto/g`);expect(r.request.body.has('descripcion')).toBe(false);r.flush({codigo:'F',mensaje:'No permitido'},{status:403,statusText:'Forbidden'});
    expect(fallo).toBe('No permitido');expect(pendientes).toBe(1);
  });
});
