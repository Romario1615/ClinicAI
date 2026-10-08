from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.dashboard.capturas import NOMBRES, CapturaIndicadores
from app.modulos.dashboard.indicadores import calcular
from app.nucleo.autorizacion import Principal
from app.nucleo.huella_ambito import huella_ambito


async def capturar_y_leer(
    sesion: AsyncSession, principal: Principal, ahora: datetime, zona: str, dias: int
) -> tuple[dict[str, float], list[CapturaIndicadores]]:
    if principal.actor_id is None or principal.clinica_id is None:
        return {}, []
    hoy = ahora.astimezone(ZoneInfo(zona)).date()
    desde = datetime.combine(hoy, time.min, ZoneInfo(zona))
    indicadores = await calcular(sesion, principal, desde, desde + timedelta(days=1))
    valores: dict[str, float] = {}
    for grupo, campos in indicadores.model_dump().items():
        if not isinstance(campos, dict):
            continue
        for campo, valor in campos.items():
            clave = f"{grupo}.{campo}"
            if clave in NOMBRES and isinstance(valor, (int, float, Decimal)):
                valores[clave] = float(valor)
    huella = huella_ambito(principal)
    stmt = insert(CapturaIndicadores).values(
        id=uuid.uuid4(),
        clinica_id=principal.clinica_id,
        actor_id=principal.actor_id,
        ambito_hash=huella,
        fecha=hoy,
        capturado_en=ahora,
        valores=valores,
    )
    await sesion.execute(
        stmt.on_conflict_do_update(
            constraint="uq_captura_indicadores_clinica_id",
            set_={"capturado_en": ahora, "valores": valores},
            where=CapturaIndicadores.capturado_en <= ahora,
        )
    )
    filas = list(
        (
            await sesion.scalars(
                select(CapturaIndicadores)
                .where(
                    CapturaIndicadores.clinica_id == principal.clinica_id,
                    CapturaIndicadores.actor_id == principal.actor_id,
                    CapturaIndicadores.ambito_hash == huella,
                    CapturaIndicadores.fecha >= hoy - timedelta(days=dias),
                    CapturaIndicadores.fecha < hoy,
                )
                .order_by(CapturaIndicadores.fecha)
            )
        ).all()
    )
    return valores, filas
