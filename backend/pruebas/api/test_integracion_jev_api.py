"""JEV y el LLM de respuestas, configurados por clínica.

* JEV no se habilita sin clave; la clave se cifra y no vuelve a salir.
* El umbral de confianza tiene límites.
* Ollama solo en la red local; Anthropic solo si su integración tiene clave.
* «Probar conexión» usa un mensaje sintético y dice si JEV respondió.
* El agente usa la cuenta de JEV de la clínica, no la del entorno.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ia import proveedores_clinica
from app.ia.decisiones import ClasificadorJev, ClasificadorReglas, DecisionTipada, Intencion
from app.modulos.configuracion import rutas as rutas_configuracion
from app.modulos.organizacion.modelos import Clinica
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.configuracion import Configuracion
from app.nucleo.seguridad import CifradorDatos
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]

CLAVE = "jev-clave-sintetica-que-no-debe-filtrarse"


async def test_configurar_y_probar_jev(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    configuracion: Configuracion,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ruta = f"{api}/configuracion/integraciones"
    await conceder_permisos(sesion, usuario, clinica, "configuracion.escribir")
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    sin_clave = await cliente.put(
        f"{ruta}/typesafe", json={"habilitada": True, "ajustes": {}}, headers=cabeceras
    )
    assert sin_clave.status_code == 422
    umbral_malo = await cliente.put(
        f"{ruta}/typesafe",
        json={"habilitada": False, "ajustes": {"umbral_confianza": 0.2}},
        headers=cabeceras,
    )
    assert umbral_malo.status_code == 422
    sin_prueba = await cliente.post(f"{ruta}/typesafe/prueba", headers=cabeceras)
    assert sin_prueba.status_code == 422

    guardada = await cliente.put(
        f"{ruta}/typesafe",
        json={
            "habilitada": True,
            "ajustes": {"umbral_confianza": 0.7, "tiempo_limite": 2},
            "secretos": {"api_key": CLAVE},
        },
        headers=cabeceras,
    )
    assert guardada.status_code == 200, guardada.text
    assert CLAVE not in guardada.text
    assert guardada.json()["secretos"]["api_key"]["configurado"] is True

    async def responde(self: ClasificadorJev, texto: str) -> DecisionTipada:
        assert self._clave == CLAVE
        assert "proxima semana" in texto
        return DecisionTipada(Intencion.BUSCAR_HORARIOS, 0.93, 0.01, 0.0, "jev")

    monkeypatch.setattr(ClasificadorJev, "clasificar", responde)
    prueba = await cliente.post(f"{ruta}/typesafe/prueba", headers=cabeceras)
    assert prueba.status_code == 200, prueba.text
    assert prueba.json()["respondio"] is True
    assert prueba.json()["intencion"] == "buscar_horarios"

    async def falla(self: ClasificadorJev, texto: str) -> DecisionTipada:
        return await ClasificadorReglas().clasificar(texto)

    monkeypatch.setattr(ClasificadorJev, "clasificar", falla)
    fallida = await cliente.post(f"{ruta}/typesafe/prueba", headers=cabeceras)
    assert fallida.json()["respondio"] is False
    assert "reglas locales" in fallida.json()["mensaje"]

    # El agente usa la cuenta de la clínica y su umbral.
    decisiones = await proveedores_clinica.decisiones_de_clinica(
        sesion,
        CifradorDatos(configuracion.clave_cifrado_datos.get_secret_value()),
        configuracion,
        clinica.id,
        ClasificadorReglas(),
    )
    assert decisiones.origen == "jev"
    assert decisiones.umbral_intencion == 0.7
    assert isinstance(decisiones.clasificador, ClasificadorJev)
    assert rutas_configuracion.MENSAJE_PRUEBA


async def test_respuestas_ia_valida_ollama_local_y_anthropic_con_clave(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
) -> None:
    ruta = f"{api}/configuracion/integraciones/respuestas_ia"
    await conceder_permisos(sesion, usuario, clinica, "configuracion.escribir")
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    publica = await cliente.put(
        ruta,
        json={
            "habilitada": True,
            "ajustes": {
                "proveedor": "ollama",
                "ollama_url": "https://ollama.ejemplo.com",
                "ollama_modelo": "llama3",
            },
        },
        headers=cabeceras,
    )
    assert publica.status_code == 422
    local = await cliente.put(
        ruta,
        json={
            "habilitada": True,
            "ajustes": {
                "proveedor": "ollama",
                "ollama_url": "http://127.0.0.1:11434",
                "ollama_modelo": "llama3",
            },
        },
        headers=cabeceras,
    )
    assert local.status_code == 200, local.text
    anthropic_sin_clave = await cliente.put(
        ruta, json={"habilitada": True, "ajustes": {"proveedor": "anthropic"}}, headers=cabeceras
    )
    assert anthropic_sin_clave.status_code == 422
    desconocido = await cliente.put(
        ruta, json={"habilitada": True, "ajustes": {"proveedor": "otro"}}, headers=cabeceras
    )
    assert desconocido.status_code == 422
