"""Normalizacion del numero de telefono para el proveedor.

Funcion pura, pero con una consecuencia concreta: la Cloud API rechaza los
numeros con formato, y ese rechazo llega como fallo de entrega sin explicacion
util. El panel guarda «+593 99 900 0333» porque es lo legible para una
persona; el proveedor quiere «593999000333».
"""

from __future__ import annotations

import pytest

from app.mensajeria.destinatarios import DestinatarioNoResoluble, normalizar_telefono

pytestmark = pytest.mark.unitaria


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("+593999000333", "593999000333"),
        ("+593 99 900 0333", "593999000333"),
        ("593-999-000-333", "593999000333"),
        ("(593) 999 000 333", "593999000333"),
        ("593999000333", "593999000333"),
    ],
)
def test_el_numero_se_deja_en_el_formato_del_proveedor(entrada: str, esperado: str) -> None:
    """La Cloud API exige solo digitos.

    Un numero con formato de panel se rechaza en el proveedor, y ese rechazo
    llega como fallo de entrega sin explicacion util.
    """
    assert normalizar_telefono(entrada) == esperado


def test_un_numero_sin_digitos_no_es_resoluble() -> None:
    with pytest.raises(DestinatarioNoResoluble, match="digitos"):
        normalizar_telefono("sin numero")
