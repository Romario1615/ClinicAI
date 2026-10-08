import { TestBed } from '@angular/core/testing';
import { CapturaFotosComponent, validarFoto, MAX_FOTO_BYTES } from './captura-fotos.component';
import { archivo } from '../nucleo/pruebas/sesion-sintetica';

describe('CapturaFotosComponent',()=>{
  function montar(perfil=false){const f=TestBed.createComponent(CapturaFotosComponent);f.componentRef.setInput('perfil',perfil);f.detectChanges();return f;}
  function evento(files:File[]){const target=document.createElement('input');Object.defineProperty(target,'files',{value:files});return {target} as unknown as Event;}
  it.each(['image/png','image/jpeg','image/webp'])('acepta %s con contenido',tipo=>expect(validarFoto(archivo('imagen','sintético',tipo))).toBe(''));
  it('rechaza tipos, vacíos y tamaño excesivo',()=>{
    expect(validarFoto(archivo('x','x','text/plain'))).toContain('JPEG');
    expect(validarFoto(archivo('x','','image/png'))).toContain('contenido');
    expect(validarFoto(archivo('x',new Uint8Array(MAX_FOTO_BYTES+1),'image/png'))).toContain('10 MB');
  });
  it('selecciona, describe, retira y libera las vistas previas',()=>{
    const f=montar();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c=f.componentInstance as any;
    const emit=vi.spyOn(c.cambiadas,'emit'), revoke=vi.spyOn(URL,'revokeObjectURL');
    c.seleccionar(evento([archivo('a','x','image/png'),archivo('b','y','image/jpeg')]));
    expect(c.fotos()).toHaveLength(2);expect(emit).toHaveBeenCalled();
    c.describir(c.fotos()[0].id,'Comprobante sintético');expect(c.fotos()[0].descripcion).toBe('Comprobante sintético');
    c.quitar(c.fotos()[0].id);expect(c.fotos()).toHaveLength(1);expect(revoke).toHaveBeenCalled();
    c.quitar('inexistente');f.destroy();expect(revoke).toHaveBeenCalledTimes(2);
  });
  it('perfil sustituye la foto anterior y usa cámara frontal',()=>{
    const f=montar(true);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c=f.componentInstance as any;
    c.seleccionar(evento([archivo('a','x','image/png')]));c.seleccionar(evento([archivo('b','y','image/png')]));
    expect(c.fotos()).toHaveLength(1);expect(c.fotos()[0].archivo.name).toBe('b');
    expect(f.nativeElement.querySelector('input[capture=user]')).not.toBeNull();c.limpiar();expect(c.fotos()).toHaveLength(0);
  });
  it('una selección inválida no agrega fotos y limita a veinte',()=>{
    const f=montar();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c=f.componentInstance as any;
    c.seleccionar(evento([]));c.seleccionar(evento([archivo('x','x','text/plain')]));expect(c.fotos()).toHaveLength(0);
    c.seleccionar(evento(Array.from({length:21},()=>archivo('x','x','image/png'))));expect(c.error()).toContain('veinte');
    expect(f.nativeElement.querySelector('input[capture=environment]')).not.toBeNull();
  });
});
