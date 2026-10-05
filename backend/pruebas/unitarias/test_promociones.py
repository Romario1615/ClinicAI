"""Piezas de la fase de promociones que no necesitan base de datos."""

from __future__ import annotations

import pytest

from app.ia.imagenes_generativas import GeneradorSandbox, validar_prompt
from app.mensajeria.adaptadores import (
    AdaptadorWhatsAppCloud,
    CredencialesWhatsApp,
    MensajeSaliente,
)
from app.mensajeria.plantillas import obtener
from app.modulos.conversaciones.intenciones import reconocer
from app.modulos.conversaciones.modelos import IntencionEntrante
from app.modulos.outbox.modelos import TipoMensajeOutbox
from app.nucleo.errores import DatosInvalidos

pytestmark = pytest.mark.unitaria


@pytest.mark.parametrize("frase", ["BAJA PROMOCIONES", "no quiero promociones", "Sin promociones."])
def test_baja_de_promociones_se_distingue_de_la_baja_total(frase: str) -> None:
    assert reconocer(frase) is IntencionEntrante.BAJA_PROMOCIONES
    assert reconocer("baja") is IntencionEntrante.BAJA


def test_plantilla_de_promocion_solo_admite_nombre_y_oferta() -> None:
    plantilla = obtener(TipoMensajeOutbox.PROMOCION)
    assert plantilla.variables_permitidas == frozenset({"nombre", "texto_promocion"})
    texto = plantilla.redactar(nombre="Persona", texto_promocion="Oferta de limpieza.")
    assert "BAJA PROMOCIONES" in texto
    with pytest.raises(ValueError):
        plantilla.redactar(nombre="Persona", texto_promocion="x", tratamiento="y")


def test_cuerpo_de_whatsapp_lleva_la_imagen_en_la_cabecera() -> None:
    adaptador = AdaptadorWhatsAppCloud(
        CredencialesWhatsApp(id_numero_telefono="000000", token_acceso="token-sintetico")
    )
    cuerpo = adaptador._construir_cuerpo(
        MensajeSaliente(
            destino="593999000101",
            nombre_plantilla="promocion_clinica",
            variables=("Persona", "Oferta"),
            texto="",
            imagen_cabecera="media-123",
        )
    )
    componentes = cuerpo["template"]["components"]  # type: ignore[index]
    assert componentes[0] == {
        "type": "header",
        "parameters": [{"type": "image", "image": {"id": "media-123"}}],
    }
    assert componentes[1]["type"] == "body"


def test_sin_imagen_no_hay_cabecera() -> None:
    adaptador = AdaptadorWhatsAppCloud(
        CredencialesWhatsApp(id_numero_telefono="000000", token_acceso="token-sintetico")
    )
    cuerpo = adaptador._construir_cuerpo(
        MensajeSaliente(destino="1", nombre_plantilla="p", variables=(), texto="")
    )
    assert [c["type"] for c in cuerpo["template"]["components"]] == ["body"]  # type: ignore[index]


@pytest.mark.parametrize("prompt", ["corto", "Llame al 099 123 4567 hoy", "x" * 700])
def test_prompt_invalido_se_rechaza(prompt: str) -> None:
    with pytest.raises(DatosInvalidos):
        validar_prompt(prompt)


@pytest.mark.asyncio
async def test_generador_sandbox_produce_un_png_valido() -> None:
    imagen = await GeneradorSandbox().generar("Sonrisa luminosa en tonos verdes")
    assert imagen.tipo_mime == "image/png"
    assert imagen.datos.startswith(b"\x89PNG\r\n\x1a\n")
    assert imagen.datos.endswith(b"IEND\xaeB`\x82")
