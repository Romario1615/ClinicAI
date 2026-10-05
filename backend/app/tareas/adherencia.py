"""Evaluacion periodica de omisiones de tomas.

El trabajo aplica el umbral operativo existente; no interpreta la pauta ni
decide cambios clinicos. Cada alerta se escribe en la misma transaccion que
su rastro de auditoria, y el indice parcial evita duplicados abiertos.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.modulos.auditoria.repositorio import RepositorioAuditoria
from app.modulos.historia.repositorio import RepositorioHistoria
from app.modulos.historia.servicios import ServicioHistoria
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import principal_sistema
from app.nucleo.bd import GestorBaseDatos
from app.nucleo.errores import RecetaNoConfirmada, RecursoNoEncontrado
from app.nucleo.registro import obtener_logger
from app.nucleo.reloj import Reloj

_logger = obtener_logger(__name__)
TAMANO_LOTE = 200


async def evaluar_alertas_adherencia(
    ctx: dict[Any, Any], *_argumentos: Any, **_opciones: Any
) -> int:
    """Crea alertas abiertas cuando se alcanza el umbral de siete dias."""
    gestor: GestorBaseDatos = ctx["gestor_bd"]
    reloj: Reloj = ctx["reloj"]
    ahora = reloj.ahora()
    total = 0

    async for sesion in gestor.sesion():
        repo = RepositorioHistoria(sesion)
        auditor = RepositorioAuditoria(sesion)
        servicio = ServicioHistoria(sesion, repo, reloj)

        # Las alertas creadas dejan de ser candidatas por el indice parcial;
        # se repite para recorrer mas de un lote sin omitir clinicas grandes.
        for _ in range(50):
            candidatos = await repo.recetas_candidatas_adherencia(
                desde=ahora - timedelta(days=7),
                hasta=ahora,
                limite=TAMANO_LOTE,
            )
            if not candidatos:
                break
            creadas = 0
            for receta_id, clinica_id in candidatos:
                principal = principal_sistema(clinica_id)
                try:
                    alerta = await servicio.evaluar_adherencia(
                        receta_id, principal=principal, dias=7
                    )
                except (RecetaNoConfirmada, RecursoNoEncontrado):
                    # Una receta concurrentemente suspendida deja de estar
                    # evaluable; el resto del lote sigue procesandose.
                    _logger.info("adherencia.receta.no_evaluada", receta_id=str(receta_id))
                    continue
                if alerta is None:
                    continue
                await auditor.registrar(
                    [
                        construir_entrada(
                            accion=AccionAuditada.ALERTA_ADHERENCIA_CREADA,
                            principal=principal,
                            ahora=ahora,
                            entidad_tipo="alerta_adherencia",
                            entidad_id=alerta.id,
                            paciente_id=alerta.paciente_id,
                        )
                    ]
                )
                creadas += 1
            total += creadas
            await sesion.commit()
            if creadas == 0:
                break

    if total:
        _logger.info("adherencia.alertas_creadas", cantidad=total)
    return total


__all__ = ["evaluar_alertas_adherencia"]
