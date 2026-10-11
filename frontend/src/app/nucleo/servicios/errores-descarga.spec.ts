import { HttpErrorResponse } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { FalloApi, traducirFallo } from './api.service';

describe('Errores de descargas PDF', () => {
  async function fallo(blob: Blob, estado = 400): Promise<FalloApi> {
    try {
      await firstValueFrom(traducirFallo(new HttpErrorResponse({ error: blob, status: estado })));
      throw new Error('La descarga debía fallar');
    } catch (error) {
      expect(error instanceof FalloApi).toBe(true);
      return error as FalloApi;
    }
  }

  it('muestra la explicación de un PDF no exportable sin perder estado ni correlación', async () => {
    const error = await fallo(new Blob([JSON.stringify({ codigo: 'DATOS_INVALIDOS', mensaje: 'Revise los caracteres del documento.', correlacion_id: 'qa-sintetica' })], { type: 'application/json' }));
    expect(error.message).toBe('Revise los caracteres del documento.');
    expect(error.codigo).toBe('DATOS_INVALIDOS');
    expect(error.estado).toBe(400);
    expect(error.correlacionId).toBe('qa-sintetica');
  });

  for (const cuerpo of ['%PDF-sintetico', '<html>Error sintético</html>', 'null', '[1,2]', '"mensaje"']) {
    it(`usa el error genérico cuando el cuerpo no es un objeto JSON: ${cuerpo}`, async () => {
      const error = await fallo(new Blob([cuerpo]), 500);
      expect(error.codigo).toBe('ERROR_DESCONOCIDO');
      expect(error.estado).toBe(500);
    });
  }

  it('no lee un archivo grande recibido como error', async () => {
    const blob = new Blob(['X'.repeat(65537)]);
    const lectura = vi.spyOn(blob, 'text');
    expect((await fallo(blob)).codigo).toBe('ERROR_DESCONOCIDO');
    expect(lectura).not.toHaveBeenCalled();
  });

  it('conserva el error HTTP si falla la lectura del archivo', async () => {
    const blob = new Blob(['sintético']);
    vi.spyOn(blob, 'text').mockRejectedValue(new Error('Lectura sintética fallida'));
    expect((await fallo(blob, 403)).estado).toBe(403);
  });

  it('resuelve un error sin cuerpo inmediatamente y sin leer el Blob', () => {
    const blob = new Blob([]);
    const lectura = vi.spyOn(blob, 'text');
    let error: FalloApi | undefined;
    traducirFallo(new HttpErrorResponse({ error: blob, status: 500 })).subscribe({ error: recibido => { error = recibido; } });
    expect(error?.estado).toBe(500);
    expect(lectura).not.toHaveBeenCalled();
  });
});
