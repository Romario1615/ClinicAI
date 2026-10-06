import { FalloApi } from '../servicios/api.service';
import {
  MENSAJE_SIN_ACCESO_CLINICO,
  esSinAccesoClinico,
  falloClinicoLegible,
  mensajeFalloClinico,
} from './acceso-clinico';

describe('acceso clínico', () => {
  const noEncontrado = new FalloApi('RECURSO_NO_ENCONTRADO', 'El paciente solicitado no existe.', 404, undefined, 'c-1');
  const conflicto = new FalloApi('CONFLICTO', 'Otro motivo', 409);

  it('un 404 dentro de la ficha se lee como falta de acceso, no como paciente inexistente', () => {
    expect(esSinAccesoClinico(noEncontrado)).toBeTrue();
    expect(mensajeFalloClinico(noEncontrado, 'x')).toBe(MENSAJE_SIN_ACCESO_CLINICO);
    const legible = falloClinicoLegible(noEncontrado);
    expect(legible.message).toBe(MENSAJE_SIN_ACCESO_CLINICO);
    expect(legible.correlacionId).toBe('c-1');
  });

  it('otros fallos conservan su mensaje', () => {
    expect(mensajeFalloClinico(conflicto, 'x')).toBe('Otro motivo');
    expect(mensajeFalloClinico(new Error('red'), 'alternativo')).toBe('alternativo');
    expect(falloClinicoLegible(conflicto)).toBe(conflicto);
  });
});
