"""Reanuda trabajos de ingesta de conocimiento que quedaron pendientes.

La API confirma la fuente y el trabajo antes de calcular embeddings. Si el
proceso web se interrumpe, este barrido retoma el trabajo desde la fuente
temporal. Cada candidato se bloquea con ``SKIP LOCKED`` y cada documento se
confirma por separado, para repartir la cola entre workers sin mantener una
transaccion grande abierta.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.ia.embeddings import ProveedorEmbeddings
from app.modulos.conocimiento.modelos import (
    EstadoIngesta,
    KnowledgeDocument,
    KnowledgeIngestionJob,
    KnowledgeVersion,
)
from app.modulos.conocimiento.servicios import ServicioConocimiento
from app.nucleo.autorizacion import principal_sistema
from app.nucleo.bd import GestorBaseDatos
from app.nucleo.errores import IngestaNoDisponible
from app.nucleo.registro import obtener_logger
from app.nucleo.reloj import Reloj

_logger = obtener_logger(__name__)
TAMANO_LOTE = 10


async def procesar_ingestas_conocimiento(
    ctx: dict[Any, Any], *_argumentos: Any, **_opciones: Any
) -> int:
    """Procesa hasta diez ingestas pendientes y devuelve las completadas."""
    gestor: GestorBaseDatos = ctx["gestor_bd"]
    reloj: Reloj = ctx["reloj"]
    embeddings: ProveedorEmbeddings = ctx["embeddings"]
    completadas = 0
    procesadas = 0

    async for sesion in gestor.sesion():
        while procesadas < TAMANO_LOTE:
            candidato = (
                await sesion.execute(
                    select(
                        KnowledgeIngestionJob.document_id,
                        KnowledgeIngestionJob.version,
                        KnowledgeDocument.clinic_id,
                    )
                    .join(
                        KnowledgeDocument,
                        KnowledgeDocument.id == KnowledgeIngestionJob.document_id,
                    )
                    .join(
                        KnowledgeVersion,
                        (KnowledgeVersion.document_id == KnowledgeIngestionJob.document_id)
                        & (KnowledgeVersion.version == KnowledgeIngestionJob.version),
                    )
                    .where(
                        KnowledgeIngestionJob.estado == EstadoIngesta.PENDIENTE.value,
                        KnowledgeVersion.contenido_texto.is_not(None),
                        KnowledgeDocument.status != "ARCHIVED",
                    )
                    .order_by(KnowledgeIngestionJob.creado_en, KnowledgeIngestionJob.document_id)
                    .limit(1)
                    .with_for_update(of=KnowledgeIngestionJob, skip_locked=True)
                )
            ).one_or_none()
            if candidato is None:
                break
            document_id, version, clinic_id = candidato
            procesadas += 1
            servicio = ServicioConocimiento(sesion, reloj, embeddings)
            try:
                await servicio.procesar_ingesta(
                    principal=principal_sistema(clinic_id),
                    document_id=document_id,
                    version=version,
                )
                await sesion.commit()
                completadas += 1
            except IngestaNoDisponible:
                # El servicio guarda el estado FALLIDA y el error sanitizado.
                # No insistir en el mismo documento en cada barrido; el
                # usuario puede reintentar después de corregir el proveedor.
                _logger.warning(
                    "conocimiento.worker_ingesta_reintentable",
                    document_id=str(document_id),
                    version=version,
                )
            except Exception:
                # Un error de base de datos o de programación no se oculta:
                # el cron fallará y el pendiente quedará para el barrido
                # siguiente después de que se corrija la causa.
                await sesion.rollback()
                raise

    if completadas:
        _logger.info(
            "conocimiento.worker_ingestas_completadas",
            cantidad=completadas,
            lote=TAMANO_LOTE,
        )
        if completadas == TAMANO_LOTE:
            _logger.warning(
                "conocimiento.worker_lote_lleno",
                cantidad=completadas,
                nota="Puede haber mas trabajos pendientes para la siguiente ejecucion.",
            )
    return completadas


__all__ = ["TAMANO_LOTE", "procesar_ingestas_conocimiento"]
