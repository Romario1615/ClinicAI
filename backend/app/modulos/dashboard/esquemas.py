from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, model_validator


class FiltroDashboard(BaseModel):
    desde: AwareDatetime
    hasta: AwareDatetime

    @model_validator(mode="after")
    def rango_valido(self) -> FiltroDashboard:
        if not timedelta(0) < self.hasta - self.desde <= timedelta(days=366):
            raise ValueError("Seleccione un periodo de hasta 366 dias con fin posterior al inicio.")
        return self


class ResumenDashboard(BaseModel):
    desde: datetime
    hasta: datetime
    citas: dict[str, int]
    total_citas: int
    pacientes: int
    pagos: dict[str, Decimal] | None
