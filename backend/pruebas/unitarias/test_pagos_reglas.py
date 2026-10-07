"""La máquina de estados y el esquema financiero permanecen acotados."""

from app.modulos.pagos.modelos import Pago
from app.modulos.pagos.servicios import TRANSICIONES


def test_transiciones_de_pago_coinciden_con_la_maquina_de_estados_completa() -> None:
    esperadas = {
        "PENDING": {"PROOF_RECEIVED", "CONFIRMED", "REJECTED"},
        "PROOF_RECEIVED": {"UNDER_REVIEW", "CONFIRMED", "REJECTED"},
        "UNDER_REVIEW": {"CONFIRMED", "REJECTED"},
        "REJECTED": {"PROOF_RECEIVED", "UNDER_REVIEW"},
        "CONFIRMED": {"REFUND_PENDING"},
        "REFUND_PENDING": set(),
    }
    assert {estado: set(transiciones) for estado, transiciones in TRANSICIONES.items()} == esperadas


def test_esquema_de_pago_no_persiste_credenciales_ni_datos_de_tarjeta() -> None:
    columnas = {columna.name.lower() for columna in Pago.__table__.columns}
    prohibidas = {
        "numero_tarjeta",
        "pan",
        "cvv",
        "cvc",
        "otp",
        "clave",
        "password",
        "token_financiero",
        "credencial_financiera",
    }
    assert columnas.isdisjoint(prohibidas)
