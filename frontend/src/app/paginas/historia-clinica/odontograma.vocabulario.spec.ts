/**
 * Orientación del dibujo: vestibular arriba en la arcada superior y abajo en
 * la inferior; mesial siempre hacia la línea media.
 */
import {
  caraEnRegion,
  describirEstado,
  mismoEstado,
  nombreHallazgoPieza,
} from './odontograma.vocabulario';

describe('vocabulario del odontograma', () => {
  it('ubica cada cara según el cuadrante', () => {
    expect(caraEnRegion(16, 'arriba')).toBe('V');
    expect(caraEnRegion(16, 'abajo')).toBe('L');
    expect(caraEnRegion(16, 'derecha')).toBe('M');
    expect(caraEnRegion(16, 'izquierda')).toBe('D');
    expect(caraEnRegion(26, 'izquierda')).toBe('M');
    expect(caraEnRegion(26, 'derecha')).toBe('D');
    expect(caraEnRegion(36, 'arriba')).toBe('L');
    expect(caraEnRegion(36, 'abajo')).toBe('V');
    expect(caraEnRegion(36, 'izquierda')).toBe('M');
    expect(caraEnRegion(46, 'derecha')).toBe('M');
    expect(caraEnRegion(55, 'centro')).toBe('O');
    expect(caraEnRegion(75, 'izquierda')).toBe('M');
  });

  it('describe y compara estados', () => {
    expect(describirEstado(undefined)).toBe('Sin hallazgos');
    expect(describirEstado({ pieza: 'CORONA', caras: { O: 'CARIES' }, nota: null })).toBe(
      'Corona; O: Caries',
    );
    expect(nombreHallazgoPieza(null)).toBe('');
    expect(mismoEstado(undefined, { pieza: null, caras: {}, nota: null })).toBeTrue();
    expect(
      mismoEstado(
        { pieza: null, caras: { O: 'CARIES', M: 'SELLANTE' }, nota: null },
        { pieza: null, caras: { M: 'SELLANTE', O: 'CARIES' }, nota: null },
      ),
    ).toBeTrue();
    expect(mismoEstado(undefined, { pieza: null, caras: {}, nota: 'x' })).toBeFalse();
  });
});
