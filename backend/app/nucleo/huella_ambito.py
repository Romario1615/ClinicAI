"""Huella de permisos, sensibilidad y dimensiones autorizadas."""

import hashlib
import json
from typing import Any

from app.nucleo.autorizacion import Principal


def huella_ambito(principal: Principal) -> str:
    ambito = principal.ambito
    datos: dict[str, Any] = {
        "permisos": sorted(principal.permisos),
        "roles": sorted(str(r) for r in principal.role_ids),
        "profesional": str(principal.profesional_id),
        "nivel_maximo": ambito.nivel_maximo.value,
        "version": 1,
    }
    for dimension, comodin in (
        ("sedes", "todas_las_sedes"),
        ("especialidades", "todas_las_especialidades"),
        ("profesionales", "todos_los_profesionales"),
        ("pacientes", "todos_los_pacientes"),
    ):
        datos[dimension] = sorted(str(v) for v in getattr(ambito, dimension))
        datos[comodin] = getattr(ambito, comodin)
    return hashlib.sha256(json.dumps(datos, sort_keys=True).encode()).hexdigest()
