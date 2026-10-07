/**
 * Tarjetas por módulo: un bloque `null` no produce tarjetas, un pendiente
 * mayor que cero se marca como alerta y cero como «bien».
 */
import { indicadoresDe, type ModuloIndicadores } from './indicadores';
import type { Indicadores } from '../servicios/indicadores.service';

const COMPLETOS: Indicadores = {
    agenda: { citas_hoy: 5, por_confirmar_hoy: 2, en_sala: 1, en_atencion: 1, atendidas_hoy: 3, inasistencias_hoy: 1, citas_proximos_7_dias: 20 },
    mis_citas: { citas_hoy: 2, pendientes_hoy: 0, proxima_inicio: '2026-10-06T13:00:00Z' },
    pacientes: { total: 90, nuevos_30_dias: 4, sin_verificar: 0, sin_whatsapp: 3 },
    lista_espera: { en_espera: 6, con_oferta: 1 },
    pagos: { pendientes: 0, por_validar: 2, confirmado_30_dias: '1250.5' },
    clinico: { recetas_por_confirmar: 1, planes_propuestos: 2, planes_en_curso: 3 },
    adherencia: { alertas_abiertas: 0 },
    mensajes: { derivadas_a_persona: 4, abiertas: 1 },
    conocimiento: { borradores: 1, en_revision: 0, vigentes: 6 },
    promociones: { borradores: 1, aprobadas_sin_enviar: 1, enviadas_30_dias: 2 },
    usuarios: { activos: 12, inactivos: 1, roles: 5 },
};

const VACIOS: Indicadores = {
    agenda: null, mis_citas: null, pacientes: null, lista_espera: null, pagos: null, clinico: null,
    adherencia: null, mensajes: null, conocimiento: null, promociones: null, usuarios: null,
};

const MODULOS: ModuloIndicadores[] = [
    'mi_dia', 'agenda', 'pacientes', 'lista_espera', 'pagos', 'clinico', 'mensajes', 'conocimiento', 'promociones', 'usuarios',
];

describe('indicadoresDe', () => {
    it('cada módulo con datos produce tarjetas con enlace', () => {
        for (const modulo of MODULOS) {
            const tarjetas = indicadoresDe(COMPLETOS, modulo);
            expect(tarjetas.length, modulo).toBeGreaterThan(0);
            expect(tarjetas.every((t) => !!t.enlace), modulo).toBe(true);
        }
    });

    it('sin datos o sin bloque no produce tarjetas', () => {
        expect(indicadoresDe(null, 'agenda')).toEqual([]);
        for (const modulo of MODULOS) {
            expect(indicadoresDe(VACIOS, modulo), modulo).toEqual([]);
        }
    });

    it('marca alertas y formatea importes y horas', () => {
        const agenda = indicadoresDe(COMPLETOS, 'agenda');
        expect(agenda.find((t) => t.etiqueta === 'Por confirmar')?.tono).toBe('alerta');
        const pacientes = indicadoresDe(COMPLETOS, 'pacientes');
        expect(pacientes.find((t) => t.etiqueta === 'Sin verificar')?.tono).toBe('bien');
        const pagos = indicadoresDe(COMPLETOS, 'pagos');
        expect(String(pagos.find((t) => t.etiqueta.startsWith('Confirmado'))?.valor)).toContain('1');
        expect(indicadoresDe({ ...COMPLETOS, pagos: { ...COMPLETOS.pagos!, confirmado_30_dias: 'x' } }, 'pagos')[2].valor).toBe('x');
        expect(indicadoresDe(COMPLETOS, 'mi_dia')[2].valor).not.toBe('—');
        expect(indicadoresDe({ ...COMPLETOS, mis_citas: { citas_hoy: 0, pendientes_hoy: 0, proxima_inicio: null } }, 'mi_dia')[2].valor).toBe('—');
        // Clínico incluye la adherencia aunque no haya bloque clínico propio.
        expect(indicadoresDe({ ...COMPLETOS, clinico: null }, 'clinico').length).toBe(1);
    });
});
