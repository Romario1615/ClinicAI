/**
 * Qué tarjetas muestra cada módulo a partir de los indicadores del backend.
 *
 * Una sola fuente para el panel y para la cabecera de cada módulo: así el
 * número de «citas por confirmar» es el mismo en los dos sitios y se llama
 * igual. Un bloque `null` (el rol no alcanza ese módulo) no produce tarjetas.
 */
import type { Indicador } from '../../compartido/tarjetas-indicadores.component';
import type { Indicadores } from '../servicios/indicadores.service';

export type ModuloIndicadores =
  | 'mi_dia'
  | 'agenda'
  | 'pacientes'
  | 'lista_espera'
  | 'pagos'
  | 'clinico'
  | 'mensajes'
  | 'conocimiento'
  | 'promociones'
  | 'usuarios';

const alerta = (n: number): Indicador['tono'] => (n > 0 ? 'alerta' : 'bien');

function dinero(valor: string): string {
  const n = Number(valor);
  return Number.isFinite(n) ? `$${n.toLocaleString('es', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : valor;
}

function hora(iso: string | null): string {
  if (!iso) return '—';
  return new Intl.DateTimeFormat('es', { weekday: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(iso));
}

export function indicadoresDe(datos: Indicadores | null, modulo: ModuloIndicadores): Indicador[] {
  if (!datos) return [];
  switch (modulo) {
    case 'mi_dia': {
      const m = datos.mis_citas;
      if (!m) return [];
      return [
        { etiqueta: 'Mis citas de hoy', valor: m.citas_hoy, enlace: '/agenda' },
        { etiqueta: 'Por atender hoy', valor: m.pendientes_hoy, tono: m.pendientes_hoy ? 'normal' : 'bien', enlace: '/agenda' },
        { etiqueta: 'Mi próxima cita', valor: hora(m.proxima_inicio), enlace: '/agenda' },
      ];
    }
    case 'agenda': {
      const a = datos.agenda;
      if (!a) return [];
      return [
        { etiqueta: 'Citas hoy', valor: a.citas_hoy, enlace: '/agenda' },
        { etiqueta: 'Por confirmar', valor: a.por_confirmar_hoy, tono: alerta(a.por_confirmar_hoy), detalle: 'Pendientes o apartadas', enlace: '/agenda' },
        { etiqueta: 'En sala de espera', valor: a.en_sala, enlace: '/agenda' },
        { etiqueta: 'En atención', valor: a.en_atencion, enlace: '/agenda' },
        { etiqueta: 'Atendidas hoy', valor: a.atendidas_hoy, tono: 'bien', enlace: '/agenda' },
        { etiqueta: 'No asistieron', valor: a.inasistencias_hoy, tono: a.inasistencias_hoy ? 'alerta' : 'normal', enlace: '/agenda' },
        { etiqueta: 'Próximos 7 días', valor: a.citas_proximos_7_dias, detalle: 'Citas agendadas', enlace: '/agenda' },
      ];
    }
    case 'pacientes': {
      const p = datos.pacientes;
      if (!p) return [];
      return [
        { etiqueta: 'Pacientes activos', valor: p.total, enlace: '/pacientes' },
        { etiqueta: 'Nuevos (30 días)', valor: p.nuevos_30_dias, enlace: '/pacientes' },
        { etiqueta: 'Sin verificar', valor: p.sin_verificar, tono: alerta(p.sin_verificar), detalle: 'Comprobar identidad en mostrador', enlace: '/pacientes' },
        { etiqueta: 'Sin WhatsApp', valor: p.sin_whatsapp, tono: alerta(p.sin_whatsapp), detalle: 'No reciben recordatorios', enlace: '/pacientes' },
      ];
    }
    case 'lista_espera': {
      const l = datos.lista_espera;
      if (!l) return [];
      return [
        { etiqueta: 'En espera', valor: l.en_espera, enlace: '/lista-espera' },
        { etiqueta: 'Con oferta en curso', valor: l.con_oferta, tono: alerta(l.con_oferta), detalle: 'Esperan respuesta', enlace: '/lista-espera' },
      ];
    }
    case 'pagos': {
      const p = datos.pagos;
      if (!p) return [];
      return [
        { etiqueta: 'Pagos pendientes', valor: p.pendientes, tono: alerta(p.pendientes), enlace: '/pagos' },
        { etiqueta: 'Por validar', valor: p.por_validar, tono: alerta(p.por_validar), detalle: 'Comprobante recibido', enlace: '/pagos' },
        { etiqueta: 'Confirmado (30 días)', valor: dinero(p.confirmado_30_dias), tono: 'bien', enlace: '/pagos' },
      ];
    }
    case 'clinico': {
      const c = datos.clinico;
      const lista: Indicador[] = [];
      if (c) {
        lista.push(
          { etiqueta: 'Recetas por confirmar', valor: c.recetas_por_confirmar, tono: alerta(c.recetas_por_confirmar), detalle: 'Borradores con su firma', enlace: '/historia-clinica' },
          { etiqueta: 'Planes propuestos', valor: c.planes_propuestos, detalle: 'Esperan aceptación del paciente', enlace: '/historia-clinica' },
          { etiqueta: 'Planes en curso', valor: c.planes_en_curso, enlace: '/historia-clinica' },
        );
      }
      if (datos.adherencia) {
        lista.push({ etiqueta: 'Alertas de adherencia', valor: datos.adherencia.alertas_abiertas, tono: alerta(datos.adherencia.alertas_abiertas), detalle: 'Sin atender', enlace: '/medicamentos' });
      }
      return lista;
    }
    case 'mensajes': {
      const m = datos.mensajes;
      if (!m) return [];
      return [
        { etiqueta: 'Esperan a una persona', valor: m.derivadas_a_persona, tono: alerta(m.derivadas_a_persona), detalle: 'Derivadas por el asistente', enlace: '/conversaciones' },
        { etiqueta: 'Conversaciones abiertas', valor: m.abiertas, enlace: '/conversaciones' },
      ];
    }
    case 'conocimiento': {
      const k = datos.conocimiento;
      if (!k) return [];
      return [
        { etiqueta: 'Documentos vigentes', valor: k.vigentes, tono: 'bien', detalle: 'Responden consultas', enlace: '/conocimiento' },
        { etiqueta: 'En revisión', valor: k.en_revision, tono: alerta(k.en_revision), detalle: 'Esperan aprobación', enlace: '/conocimiento' },
        { etiqueta: 'Borradores', valor: k.borradores, enlace: '/conocimiento' },
      ];
    }
    case 'promociones': {
      const p = datos.promociones;
      if (!p) return [];
      return [
        { etiqueta: 'Campañas en borrador', valor: p.borradores, enlace: '/promociones' },
        { etiqueta: 'Aprobadas sin enviar', valor: p.aprobadas_sin_enviar, tono: alerta(p.aprobadas_sin_enviar), enlace: '/promociones' },
        { etiqueta: 'Enviadas (30 días)', valor: p.enviadas_30_dias, enlace: '/promociones' },
      ];
    }
    case 'usuarios': {
      const u = datos.usuarios;
      if (!u) return [];
      return [
        { etiqueta: 'Cuentas activas', valor: u.activos, tono: 'bien', enlace: '/usuarios' },
        { etiqueta: 'Sin acceso', valor: u.inactivos, detalle: 'Cuentas desactivadas', enlace: '/usuarios' },
        { etiqueta: 'Roles disponibles', valor: u.roles, enlace: '/usuarios' },
      ];
    }
  }
}
