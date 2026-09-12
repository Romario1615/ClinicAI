"""Verificacion de la firma del webhook.

El webhook es el unico endpoint publico sin autenticacion del sistema.  Lo
unico que distingue un mensaje real de uno fabricado es esta firma, y sin ella
un tercero podria inyectar cancelaciones de citas de pacientes que nunca las
pidieron.
"""

from __future__ import annotations

import hashlib
import hmac

import pytest

from app.mensajeria.firma import calcular_firma, verificar_firma, verificar_reto
from app.nucleo.errores import FirmaInvalida

pytestmark = pytest.mark.unitaria

# Secreto sintetico, solo para estas pruebas. No es ni se parece a una
# credencial real (CLAUDE.md, regla 2).
SECRETO = "secreto-sintetico-de-prueba"
CUERPO = b'{"object":"whatsapp_business_account","entry":[]}'


def test_una_firma_valida_se_acepta() -> None:
    verificar_firma(CUERPO, calcular_firma(CUERPO, SECRETO), SECRETO)


def test_una_firma_invalida_se_rechaza() -> None:
    ajena = calcular_firma(CUERPO, "otro-secreto")
    with pytest.raises(FirmaInvalida, match="no coincide"):
        verificar_firma(CUERPO, ajena, SECRETO)


def test_un_cuerpo_alterado_invalida_la_firma() -> None:
    """Es el ataque que la firma existe para detener.

    Un tercero que reenvia un cuerpo capturado y le cambia el numero de
    telefono para hacerse pasar por otro paciente.
    """
    firma = calcular_firma(CUERPO, SECRETO)
    alterado = CUERPO.replace(b"[]", b'[{"id":"falso"}]')
    with pytest.raises(FirmaInvalida):
        verificar_firma(alterado, firma, SECRETO)


def test_el_cuerpo_reserializado_no_valida() -> None:
    """La firma se calcula sobre los bytes crudos, no sobre el JSON parseado.

    Este es el error de implementacion mas habitual en un webhook firmado:
    parsear el cuerpo y volver a serializarlo cambia espacios, orden de claves
    y escapes, y el HMAC deja de coincidir.  La prueba fija la expectativa
    para que nadie «simplifique» la ruta pasando el cuerpo ya parseado.
    """
    firma = calcular_firma(CUERPO, SECRETO)
    reserializado = b'{"object": "whatsapp_business_account", "entry": []}'
    with pytest.raises(FirmaInvalida):
        verificar_firma(reserializado, firma, SECRETO)


def test_sin_cabecera_se_rechaza() -> None:
    with pytest.raises(FirmaInvalida, match="cabecera"):
        verificar_firma(CUERPO, None, SECRETO)


def test_cabecera_sin_el_prefijo_se_rechaza() -> None:
    """Meta envia `sha256=<hex>`. Un hex desnudo no es la cabecera esperada."""
    solo_hex = hmac.new(SECRETO.encode(), CUERPO, hashlib.sha256).hexdigest()
    with pytest.raises(FirmaInvalida, match="formato"):
        verificar_firma(CUERPO, solo_hex, SECRETO)


def test_sin_secreto_configurado_se_rechaza() -> None:
    """Un endpoint que acepta cualquier cuerpo porque nadie configuro el
    secreto es peor que uno que no responde: parece que funciona.
    """
    with pytest.raises(FirmaInvalida, match="secreto"):
        verificar_firma(CUERPO, calcular_firma(CUERPO, SECRETO), "")


def test_cuerpo_vacio_con_firma_valida_se_acepta() -> None:
    """Un cuerpo vacio firmado es valido; lo que importa es la firma."""
    verificar_firma(b"", calcular_firma(b"", SECRETO), SECRETO)


# ---------------------------------------------------------------------------
#  Reto de verificacion inicial
# ---------------------------------------------------------------------------
def test_el_reto_valido_devuelve_el_desafio() -> None:
    assert (
        verificar_reto(
            modo="subscribe",
            token="token-sintetico",
            reto="1158201444",
            token_esperado="token-sintetico",
        )
        == "1158201444"
    )


def test_el_reto_con_token_incorrecto_se_rechaza() -> None:
    with pytest.raises(FirmaInvalida, match="token de verificacion"):
        verificar_reto(
            modo="subscribe", token="equivocado", reto="123", token_esperado="token-sintetico"
        )


def test_el_reto_con_modo_desconocido_se_rechaza() -> None:
    with pytest.raises(FirmaInvalida, match="Modo"):
        verificar_reto(
            modo="unsubscribe",
            token="token-sintetico",
            reto="123",
            token_esperado="token-sintetico",
        )


def test_el_reto_sin_desafio_se_rechaza() -> None:
    with pytest.raises(FirmaInvalida, match="reto"):
        verificar_reto(
            modo="subscribe", token="token-sintetico", reto=None, token_esperado="token-sintetico"
        )


def test_el_reto_sin_token_configurado_se_rechaza() -> None:
    with pytest.raises(FirmaInvalida, match="token de verificacion configurado"):
        verificar_reto(modo="subscribe", token="lo-que-sea", reto="123", token_esperado="")
