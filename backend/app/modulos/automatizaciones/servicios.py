"""Estado de las automatizaciones por clínica.

Se guarda en `configuracion_clinica` bajo la clave ``automatizaciones``, con
el mismo versionado que el resto de la configuración: cambiar un flujo crea
una versión nueva y conserva la anterior, porque ante una reclamación
(«¿por qué no me llegó el recordatorio?») hay que poder decir qué estaba
encendido ese día.

Un flujo sin registro está **encendido**. Apagar es la decisión explícita.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.automatizaciones.catalogo import FLUJO_POR_TIPO, FLUJOS, POR_CODIGO, Flujo
from app.modulos.organizacion.modelos import ConfiguracionClinica
from app.modulos.outbox.modelos import OutboxMensaje, TipoMensajeOutbox
from app.nucleo.auditoria import AccionAuditada, EntradaAuditoria, construir_entrada
from app.nucleo.autorizacion import Principal
from app.nucleo.errores import DatosInvalidos, RecursoNoEncontrado, ReglaNegocioViolada
from app.nucleo.reloj import Reloj

CLAVE = "automatizaciones"


async def _vigente(sesion: AsyncSession, clinica_id: uuid.UUID) -> ConfiguracionClinica | None:
    return (
        await sesion.execute(
            select(ConfiguracionClinica).where(
                ConfiguracionClinica.clinica_id == clinica_id,
                ConfiguracionClinica.clave == CLAVE,
                ConfiguracionClinica.vigente.is_(True),
            )
        )
    ).scalar_one_or_none()


async def estados(sesion: AsyncSession, clinica_id: uuid.UUID) -> dict[str, bool]:
    """Encendido o apagado de cada flujo de la clínica."""
    fila = await _vigente(sesion, clinica_id)
    guardado = dict(fila.valor) if fila else {}
    return {
        flujo.codigo: True if flujo.obligatorio else bool(guardado.get(flujo.codigo, True))
        for flujo in FLUJOS
    }


async def tipo_permitido(
    sesion: AsyncSession, clinica_id: uuid.UUID | None, tipo: TipoMensajeOutbox
) -> bool:
    """¿Puede encolarse este tipo de mensaje en esta clínica?

    Los mensajes sin flujo (verificación de correo, calendario) y los de
    flujos obligatorios siempre pueden.
    """
    flujo = FLUJO_POR_TIPO.get(tipo)
    if flujo is None or flujo.obligatorio or clinica_id is None:
        return True
    return (await estados(sesion, clinica_id)).get(flujo.codigo, True)


async def ejecuciones_30_dias(sesion: AsyncSession, clinica_id: uuid.UUID) -> dict[str, int]:
    """Mensajes encolados por cada flujo en el periodo, para ver que funciona."""
    filas = await sesion.execute(
        select(OutboxMensaje.tipo, func.count())
        .where(
            OutboxMensaje.clinica_id == clinica_id,
            OutboxMensaje.creado_en >= func.now() - timedelta(days=30),
        )
        .group_by(OutboxMensaje.tipo)
    )
    por_tipo = {str(tipo): int(cantidad) for tipo, cantidad in filas}
    return {
        flujo.codigo: sum(por_tipo.get(tipo.value, 0) for tipo in flujo.tipos) for flujo in FLUJOS
    }


async def cambiar(
    sesion: AsyncSession,
    principal: Principal,
    reloj: Reloj,
    codigo: str,
    activo: bool,
    motivo: str,
) -> tuple[Flujo, EntradaAuditoria]:
    flujo = POR_CODIGO.get(codigo)
    if flujo is None:
        raise RecursoNoEncontrado("La automatización indicada no existe.")
    if flujo.obligatorio and not activo:
        raise ReglaNegocioViolada(
            "Esta automatización es obligatoria y no se puede apagar.",
            detalles={"automatizacion": codigo},
        )
    if principal.clinica_id is None:
        raise DatosInvalidos("La sesión no pertenece a una clínica.")
    actual = await _vigente(sesion, principal.clinica_id)
    valor = dict(actual.valor) if actual else {}
    valor[codigo] = activo
    version = 1
    if actual is not None:
        version = actual.version + 1
        await sesion.execute(
            update(ConfiguracionClinica)
            .where(ConfiguracionClinica.id == actual.id)
            .values(vigente=False)
        )
        await sesion.flush()
    sesion.add(
        ConfiguracionClinica(
            clinica_id=principal.clinica_id,
            clave=CLAVE,
            valor=valor,
            version=version,
            vigente=True,
            creado_por=principal.actor_id,
        )
    )
    await sesion.flush()
    entrada = construir_entrada(
        accion=AccionAuditada.AUTOMATIZACION_CAMBIADA,
        principal=principal,
        ahora=reloj.ahora(),
        entidad_tipo="automatizacion",
        entidad_id=None,
        motivo=motivo,
        automatizacion=codigo,
        activo=activo,
    )
    return flujo, entrada


__all__ = ["CLAVE", "cambiar", "ejecuciones_30_dias", "estados", "tipo_permitido"]
