import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { CONFIGURACION } from '../../nucleo/servicios/configuracion';
import { catchError } from 'rxjs';
import { traducirFallo } from '../../nucleo/servicios/api.service';

export interface ConexionCalendario {
  id: string;
  calendar_id: string;
  estado_sincronizacion: 'CONECTADO' | 'TOKEN_VENCIDO' | 'DESCONECTADO' | 'ERROR';
  ultima_sincronizacion_en: string | null;
  expira_en: string | null;
  ultimo_error: string | null;
}
export interface ResumenCalendario {
  creados: number; actualizados: number; eliminados: number; recreados: number;
  conflictos: number; reintentables: number; errores: number;
  sin_conexion: number; token_vencido: number;
}

@Injectable({ providedIn: 'root' })
export class CalendarioProfesionalService {
  private readonly http = inject(HttpClient);
  private readonly base = `${inject(CONFIGURACION).urlApi}/calendario`;
  listar() { return this.http.get<{ elementos: readonly ConexionCalendario[] }>(`${this.base}/conexiones`).pipe(catchError(traducirFallo)); }
  conectar(calendarId: string) {
    return this.http.post<{ url_autorizacion: string }>(`${this.base}/oauth/inicio`, { calendar_id: calendarId }).pipe(catchError(traducirFallo));
  }
  sincronizar(id: string) {
    return this.http.post<ResumenCalendario>(`${this.base}/conexiones/${encodeURIComponent(id)}/sincronizacion`, {}).pipe(catchError(traducirFallo));
  }
  desconectar(id: string, motivo: string) {
    return this.http.post<ConexionCalendario>(`${this.base}/conexiones/${encodeURIComponent(id)}/desconexion`, { motivo }).pipe(catchError(traducirFallo));
  }
  validarUrlGoogle(url: string): string {
    const destino = new URL(url);
    if (destino.protocol !== 'https:' || destino.hostname !== 'accounts.google.com'
      || destino.username || destino.password || destino.port
      || destino.pathname !== '/o/oauth2/v2/auth') {
      throw new Error('La dirección de autorización de Google no es válida.');
    }
    return destino.href;
  }
}
