import { TipoDocumentoPipe } from './tipo-documento.pipe';

describe('TipoDocumentoPipe', () => {
  it('traduce los tipos conocidos y deja pasar los demás', () => {
    const pipe = new TipoDocumentoPipe();
    expect(pipe.transform('CEDULA')).toBe('Cédula');
    expect(pipe.transform('SIN_DOCUMENTO')).toBe('Sin documento');
    expect(pipe.transform('OTRO')).toBe('OTRO');
    expect(pipe.transform(null)).toBe('');
  });
});
