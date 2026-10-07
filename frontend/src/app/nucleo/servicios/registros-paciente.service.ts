import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { catchError } from 'rxjs';
import { CONFIGURACION } from './configuracion';
import { traducirFallo } from './api.service';

export interface ZonaFacial { zona: string; estado: 'OBSERVACION' | 'PLANIFICADO' | 'REALIZADO'; observacion: string; procedimiento: string | null }
export interface PuntoFacial { codigo: string; nombre: string; x: number; y: number }
export interface PartidaDocumento { descripcion: string; cantidad: number | string; precio_unitario: number | string }
export interface ContenidoRegistro {
  zonas: ZonaFacial[]; partidas: PartidaDocumento[]; observaciones: string; moneda: string;
  valido_hasta: string | null; paciente: string; clinica: string; profesional: string; sede: string | null;
  receta_id?: string; medicamentos?: { nombre: string; dosis: string; via: string; cuando_sea_necesario: boolean; frecuencia_horas: number | null }[];
}
export interface RegistroPaciente {
  id: string; raiz_id: string; version: number; titulo: string; tipo: 'FACIOGRAMA' | 'PRESUPUESTO' | 'COTIZACION' | 'RECETA';
  vigente: boolean; anulado: boolean; motivo: string; creado_en: string; profesional_id: string;
  especialidad_id: string; cita_id: string | null; sede_id: string | null; nivel_sensibilidad: 'N2' | 'N3'; contenido: ContenidoRegistro;
}
export interface EntregaDocumento { id: string; enlace: string; expira_en: string; estado: string; modo: string }
@Injectable({ providedIn: 'root' })
export class RegistrosPacienteService {
  private readonly http = inject(HttpClient);
  private readonly config = inject(CONFIGURACION);
  private ruta(paciente: string, sufijo = ''): string { return `${this.config.urlApi}/historia/pacientes/${paciente}/registros${sufijo}`; }
  listar(paciente: string, especialidad: string, historico: boolean, facial = false, desplazamiento = 0) { return this.http.get<RegistroPaciente[]>(this.ruta(paciente), { params: { especialidad_id: especialidad, historico, grupo: facial ? 'facial' : 'documentos', limite: 50, desplazamiento } }).pipe(catchError(traducirFallo)); }
  zonas() { return this.http.get<PuntoFacial[]>(`${this.config.urlApi}/historia/faciograma/zonas`).pipe(catchError(traducirFallo)); }
  desdePlan(plan: string, clave: string, sede: string | null = null, cita: string | null = null) { return this.http.post<RegistroPaciente>(`${this.config.urlApi}/historia/planes/${plan}/presupuesto-documento`, { clave_idempotencia: clave, sede_id: sede, cita_id: cita }).pipe(catchError(traducirFallo)); }
  guardar(paciente: string, datos: unknown) { return this.http.post<RegistroPaciente>(this.ruta(paciente), datos).pipe(catchError(traducirFallo)); }
  anular(paciente: string, registro: string, motivo: string) { return this.http.post<RegistroPaciente>(this.ruta(paciente, `/${registro}/anulacion`), { motivo }).pipe(catchError(traducirFallo)); }
  pdf(paciente: string, registro: string) { return this.http.get(this.ruta(paciente, `/${registro}/pdf`), { responseType: 'blob' }).pipe(catchError(traducirFallo)); }
  compartir(paciente: string, registro: string, clave: string) { return this.http.post<EntregaDocumento>(this.ruta(paciente, `/${registro}/whatsapp`), { clave_idempotencia: clave, identidad_destinatario_confirmada: true, dias_validez: 7 }).pipe(catchError(traducirFallo)); }
}

export function guardarPdf(blob: Blob, nombre: string): void {
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement('a'); enlace.href = url; enlace.download = nombre;
  enlace.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
