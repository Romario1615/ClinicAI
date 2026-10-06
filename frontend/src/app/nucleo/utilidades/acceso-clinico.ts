/**
 * Cómo se lee un 404 en los datos clínicos de un paciente que ya se ve.
 *
 * El backend responde 404 indistinguible cuando el paciente no existe, está
 * fuera de ámbito o falta relación asistencial (docs/security.md): así nadie
 * puede tantear identificadores. Pero dentro de la ficha el paciente ya está a
 * la vista, y «El paciente solicitado no existe» es falso y confunde. Aquí se
 * traduce a lo que significa en ese contexto, sin revelar nada nuevo.
 */
import { FalloApi } from '../servicios/api.service';

export const MENSAJE_SIN_ACCESO_CLINICO =
  'Sin acceso clínico a este paciente con su sesión: la historia solo la ve quien le atiende ' +
  '(relación asistencial vigente) o mediante un acceso de emergencia justificado.';

/** Cierto si el fallo es el 404 con el que el backend oculta el dato clínico. */
export function esSinAccesoClinico(fallo: unknown): boolean {
  return fallo instanceof FalloApi && fallo.estado === 404;
}

/** Mensaje para mostrar: el de acceso si es ese 404; si no, el del fallo o el alternativo. */
export function mensajeFalloClinico(fallo: unknown, alternativo: string): string {
  if (esSinAccesoClinico(fallo)) return MENSAJE_SIN_ACCESO_CLINICO;
  return fallo instanceof FalloApi ? fallo.message : alternativo;
}

/** El mismo fallo con el mensaje de acceso, para pantallas que guardan el `FalloApi`. */
export function falloClinicoLegible(fallo: FalloApi): FalloApi {
  return esSinAccesoClinico(fallo)
    ? new FalloApi(fallo.codigo, MENSAJE_SIN_ACCESO_CLINICO, fallo.estado, fallo.detalles, fallo.correlacionId)
    : fallo;
}
