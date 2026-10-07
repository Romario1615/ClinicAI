import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { CONFIGURACION } from '../../nucleo/servicios/configuracion';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import type { PerfilProfesional } from '../../nucleo/modelos/dominio';

export interface DatosPerfilProfesional {
  especialidad_id: string;
  nombre: string;
  apellido: string;
  numero_registro_profesional: string | null;
  telefono_whatsapp: string | null;
  correo_calendario: string | null;
  estado_disponibilidad: Exclude<PerfilProfesional['estado_disponibilidad'], 'INACTIVO'>;
  acepta_pacientes_nuevos: boolean;
  minutos_preparacion_propio: number;
  activo: boolean;
  sede_ids: string[];
  sede_principal_id: string;
}

@Injectable({ providedIn: 'root' })
export class EquipoService {
  private readonly http = inject(HttpClient);
  private readonly configuracion = inject(CONFIGURACION);
  private readonly catalogo = inject(CatalogoService);
  private readonly base = `${this.configuracion.urlApi}/profesionales/gestion`;

  listar(): Observable<readonly PerfilProfesional[]> {
    return this.http.get<readonly PerfilProfesional[]>(this.base);
  }

  crear(datos: DatosPerfilProfesional): Observable<PerfilProfesional> {
    return this.http.post<PerfilProfesional>(this.base, datos);
  }

  actualizar(id: string, datos: DatosPerfilProfesional): Observable<PerfilProfesional> {
    return this.http.put<PerfilProfesional>(`${this.base}/${encodeURIComponent(id)}`, datos);
  }

  invalidarCatalogo(): void {
    this.catalogo.limpiar();
  }
}
