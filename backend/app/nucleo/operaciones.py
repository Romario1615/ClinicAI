"""Idempotencia transaccional para escrituras del panel.

El bloqueo se mantiene hasta el commit de negocio. Las claves quedan ligadas
al actor y a la clinica; una repeticion no comparte resultados entre usuarios.
"""

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import ClaveIdempotencia
from app.nucleo.autorizacion import Principal
from app.nucleo.bd import tomar_bloqueo_consultivo
from app.nucleo.errores import ClaveIdempotenciaConflictiva, DatosInvalidos
from app.nucleo.idempotencia import (
    calcular_clave_deduplicacion,
    calcular_hash_peticion,
    validar_clave_cliente,
)
from app.nucleo.reloj import Reloj


async def iniciar_operacion(
    sesion: AsyncSession,
    principal: Principal,
    reloj: Reloj,
    alcance: str,
    clave: str,
    cuerpo: Any,
) -> ClaveIdempotencia:
    try:
        limpia = validar_clave_cliente(clave)
    except ValueError as exc:
        raise DatosInvalidos(str(exc)) from exc
    identificador = calcular_clave_deduplicacion(
        str(principal.clinica_id), str(principal.actor_id), alcance, limpia
    )
    await tomar_bloqueo_consultivo(sesion, espacio=7310, clave=identificador)
    registro = (
        await sesion.execute(
            select(ClaveIdempotencia).where(
                ClaveIdempotencia.alcance == alcance,
                ClaveIdempotencia.clave == identificador,
            )
        )
    ).scalar_one_or_none()
    huella = calcular_hash_peticion(cuerpo)
    if registro is not None:
        if registro.hash_peticion != huella:
            raise ClaveIdempotenciaConflictiva("La clave ya se uso con otros datos.")
        return registro
    registro = ClaveIdempotencia(
        clave=identificador,
        alcance=alcance,
        clinica_id=principal.clinica_id,
        hash_peticion=huella,
        expira_en=reloj.ahora() + timedelta(days=1),
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


def completar_operacion(
    registro: ClaveIdempotencia, respuesta: dict[str, object], reloj: Reloj
) -> None:
    registro.respuesta = respuesta
    registro.estado = "COMPLETADA"
    registro.completado_en = reloj.ahora()
    registro.codigo_http = 200
