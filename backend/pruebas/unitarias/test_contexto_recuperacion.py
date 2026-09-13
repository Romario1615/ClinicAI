"""Traduccion del principal al contexto de autorizacion del RAG.

No toca la base de datos: solo traduce un `Principal` en las condiciones con
las que se buscara. Es poco codigo y decide quien ve que, asi que conviene
tenerlo cubierto aparte de las pruebas de consulta.

Vive en las unitarias porque los modulos de integracion llevan
`pytest.mark.asyncio` a nivel de modulo, que no admite pruebas sincronas.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.ia.recuperador import MENSAJE_SIN_FUENTE, contexto_desde_principal
from app.nucleo.autorizacion import Ambito, NivelSensibilidad, Principal, TipoActor

pytestmark = [pytest.mark.unitaria, pytest.mark.seguridad]

AHORA = datetime(2026, 4, 15, 14, 0, tzinfo=UTC)


def _principal(
    *,
    clinica_id: uuid.UUID | None,
    ambito: Ambito,
) -> Principal:
    return Principal(
        actor_tipo=TipoActor.USUARIO,
        actor_id=uuid.uuid4(),
        clinica_id=clinica_id,
        permisos=frozenset(),
        ambito=ambito,
    )


def test_el_mensaje_sin_fuente_ofrece_derivar() -> None:
    """No basta con decir «no se»: hay que ofrecer una salida.

    Un paciente que recibe «no tengo informacion» y nada mas se queda sin
    respuesta y sin saber a quien preguntar.
    """
    assert "derivar" in MENSAJE_SIN_FUENTE.lower()


def test_el_contexto_hereda_el_ambito_del_principal() -> None:
    clinica_id = uuid.uuid4()
    sede_id = uuid.uuid4()
    principal = _principal(
        clinica_id=clinica_id,
        ambito=Ambito(
            clinica_id=clinica_id,
            sedes=frozenset({sede_id}),
            todas_las_especialidades=True,
            nivel_maximo=NivelSensibilidad.CLINICO,
        ),
    )
    contexto = contexto_desde_principal(principal, ahora=AHORA)
    assert contexto.sedes == frozenset({sede_id})
    # `todas_las_especialidades` se traduce a `None`, que significa «sin
    # restriccion» -- distinto del conjunto vacio, que significa «ninguna».
    assert contexto.especialidades is None
    assert contexto.nivel_maximo is NivelSensibilidad.CLINICO


def test_el_nivel_se_puede_acotar_pero_no_ampliar() -> None:
    """El parametro sirve para buscar con MENOS privilegio, nunca con mas.

    Es lo que permite que el agente responda por WhatsApp -- donde la
    identidad no esta verificada -- con menos alcance que la persona que
    pregunta.
    """
    clinica_id = uuid.uuid4()
    principal = _principal(
        clinica_id=clinica_id,
        ambito=Ambito(
            clinica_id=clinica_id,
            todas_las_sedes=True,
            todas_las_especialidades=True,
            nivel_maximo=NivelSensibilidad.ADMINISTRATIVO,
        ),
    )

    acotado = contexto_desde_principal(
        principal, ahora=AHORA, nivel_maximo=NivelSensibilidad.PUBLICO
    )
    assert acotado.nivel_maximo is NivelSensibilidad.PUBLICO

    intento_ampliar = contexto_desde_principal(
        principal, ahora=AHORA, nivel_maximo=NivelSensibilidad.CLINICO_SENSIBLE
    )
    assert intento_ampliar.nivel_maximo is NivelSensibilidad.ADMINISTRATIVO


def test_un_principal_sin_clinica_no_puede_buscar() -> None:
    """Sin clinica no hay aislamiento posible: se rechaza en lugar de buscar."""
    principal = _principal(clinica_id=None, ambito=Ambito())
    with pytest.raises(ValueError, match="sin clinica"):
        contexto_desde_principal(principal, ahora=AHORA)
