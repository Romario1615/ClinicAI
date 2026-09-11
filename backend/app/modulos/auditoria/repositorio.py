"""Persistencia de la auditoria.

Los servicios **devuelven** entradas de auditoria en lugar de escribirlas
(ver `ResultadoOperacion` en la agenda y `ResultadoAutenticacion` en usuarios).
Este repositorio es quien las escribe, y lo hace dentro de la misma
transaccion que el cambio que describen.

El motivo de separarlo asi: si la auditoria se escribiera en su propia
transaccion, una caida entre ambas dejaria una de las dos cosas.  Con un
cambio confirmado y sin registro, la auditoria miente por omision; con un
registro de algo que no ocurrio, miente al reves.  Confirmar las dos juntas
es la unica variante en la que no miente.

La tabla es de solo insercion, garantizado por un disparador
(`auditoria_sin_modificacion`), no por una convencion de este modulo.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.modelos import Auditoria
from app.nucleo.auditoria import EntradaAuditoria
from app.nucleo.registro import obtener_logger

_logger = obtener_logger(__name__)


class RepositorioAuditoria:
    """Escribe entradas de auditoria. No lee: la consulta la hace el auditor."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def registrar(self, entradas: Sequence[EntradaAuditoria]) -> int:
        """Persiste las entradas y devuelve cuantas se escribieron.

        No hace `commit`: el limite transaccional lo decide quien orquesta la
        operacion.  Ver la nota del encabezado sobre por que importa.
        """
        if not entradas:
            return 0

        for entrada in entradas:
            self._sesion.add(
                Auditoria(
                    accion=entrada.accion.value,
                    actor_tipo=entrada.actor_tipo.value,
                    actor_id=entrada.actor_id,
                    resultado=entrada.resultado.value,
                    entidad_tipo=entrada.entidad_tipo,
                    entidad_id=entrada.entidad_id,
                    clinica_id=entrada.clinica_id,
                    sede_id=entrada.sede_id,
                    paciente_id=entrada.paciente_id,
                    nivel_sensibilidad=(
                        entrada.nivel_sensibilidad.value
                        if entrada.nivel_sensibilidad is not None
                        else None
                    ),
                    ip=entrada.ip,
                    origen=entrada.origen,
                    correlacion_id=entrada.correlacion_id,
                    motivo=entrada.motivo,
                    metadatos=entrada.metadatos or None,
                    ocurrido_en=entrada.ocurrido_en,
                )
            )

            # Las acciones marcadas para alerta salen ademas por el registro,
            # que es lo que un sistema de monitorizacion vigila.  Una fila en
            # una tabla no despierta a nadie; una linea de log con nivel de
            # advertencia si.
            if entrada.requiere_alerta:
                _logger.warning(
                    "auditoria.alerta",
                    accion=entrada.accion.value,
                    resultado=entrada.resultado.value,
                    actor_id=str(entrada.actor_id) if entrada.actor_id else None,
                    entidad_tipo=entrada.entidad_tipo,
                    correlacion_id=entrada.correlacion_id,
                    motivo=entrada.motivo,
                )

        await self._sesion.flush()
        return len(entradas)


__all__ = ["RepositorioAuditoria"]
