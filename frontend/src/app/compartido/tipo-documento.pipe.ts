import { Pipe, type PipeTransform } from '@angular/core';

const NOMBRES: Record<string, string> = {
  CEDULA: 'Cédula',
  PASAPORTE: 'Pasaporte',
  RUC: 'RUC',
  SIN_DOCUMENTO: 'Sin documento',
};

/** Tipo de documento en palabras («CEDULA» → «Cédula»). El código sigue en el API. */
@Pipe({ name: 'tipoDocumento', standalone: true })
export class TipoDocumentoPipe implements PipeTransform {
  transform(tipo: string | null | undefined): string {
    return tipo ? (NOMBRES[tipo] ?? tipo) : '';
  }
}
