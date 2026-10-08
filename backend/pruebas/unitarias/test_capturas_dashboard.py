import uuid
from dataclasses import replace

import pytest

from app.nucleo.autorizacion import Ambito, NivelSensibilidad, Principal, TipoActor
from app.nucleo.huella_ambito import huella_ambito

pytestmark = pytest.mark.unitaria


def test_huella_cambia_con_permisos_nivel_y_dimensiones() -> None:
    p = Principal(
        actor_tipo=TipoActor.USUARIO,
        actor_id=uuid.uuid4(),
        clinica_id=uuid.uuid4(),
        permisos=frozenset({"dashboard.leer"}),
        ambito=Ambito(),
    )
    base = huella_ambito(p)
    assert len(base) == 64 and base == huella_ambito(p)
    assert base != huella_ambito(replace(p, permisos=p.permisos | {"pago.leer"}))
    assert base != huella_ambito(
        replace(p, ambito=replace(p.ambito, nivel_maximo=NivelSensibilidad.CLINICO))
    )
    assert base != huella_ambito(
        replace(p, ambito=replace(p.ambito, sedes=frozenset({uuid.uuid4()})))
    )
    assert base != huella_ambito(replace(p, profesional_id=uuid.uuid4()))
    assert base != huella_ambito(replace(p, role_ids=frozenset({uuid.uuid4()})))
