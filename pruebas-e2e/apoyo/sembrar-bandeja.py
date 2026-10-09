"""Dos hilos sintéticos para comprobar la bandeja, exclusivamente en una BD de QA."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import uuid
from datetime import timedelta
from urllib.parse import urlparse

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

PUERTO_QA = 8020


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bd", required=True)
    parser.add_argument("--api", default="http://127.0.0.1:8020/api/v1")
    argumentos = parser.parse_args()
    if not re.fullmatch(r"clinicai_qa_modulos_e2e_[a-f0-9]{8}", argumentos.bd):
        parser.error("Use la base sintética exclusiva de la revisión de módulos.")
    url = urlparse(argumentos.api)
    if url.hostname not in {"127.0.0.1", "localhost"} or url.port != PUERTO_QA:
        parser.error("La API de pruebas debe estar en el puerto local 8020.")
    os.environ.update(
        POSTGRES_BD=argumentos.bd,
        BD_URL="",
        ENTORNO="local",
        PROVEEDOR_LLM="mock",
        PROVEEDOR_EMBEDDINGS="mock",
        MODO_WHATSAPP="sandbox",
        MODO_CALENDARIO="sandbox",
    )
    # Los modelos se registran al importar la aplicación, después de fijar la BD.
    from app.main import crear_aplicacion  # noqa: PLC0415
    from app.modulos.conversaciones.modelos import Conversacion, MensajeEntrante  # noqa: PLC0415
    from app.nucleo.configuracion import Configuracion  # noqa: PLC0415
    from app.nucleo.reloj import RelojSistema  # noqa: PLC0415

    crear_aplicacion()
    async with httpx.AsyncClient(base_url=argumentos.api, timeout=30) as cliente:
        acceso = await cliente.post(
            "/autenticacion/sesion-local", json={"codigo_rol": "administrador_clinica"}
        )
        acceso.raise_for_status()
        headers = {"Authorization": f"Bearer {acceso.json()['token_acceso']}"}
        clinica = await cliente.get("/catalogo/clinica", headers=headers)
        pacientes = await cliente.get("/pacientes/", params={"limite": 1}, headers=headers)
        clinica.raise_for_status()
        pacientes.raise_for_status()
        clinica_id = uuid.UUID(clinica.json()["id"])
        paciente_id = uuid.UUID(pacientes.json()["elementos"][0]["id"])
    motor = create_async_engine(Configuracion().url_base_datos)
    ahora = RelojSistema().ahora()
    datos = {}
    try:
        async with async_sessionmaker(motor)() as sesion:
            for nombre, horas in [("vigente", 20), ("vencida", -1)]:
                telefono = f"5939{uuid.uuid4().int % 10**8:08d}"
                hilo = Conversacion(
                    clinica_id=clinica_id,
                    paciente_id=paciente_id,
                    telefono=telefono,
                    canal="WHATSAPP",
                    estado="EN_HANDOFF",
                    motivo_handoff="Consulta administrativa sintética de QA",
                    ultima_actividad_en=ahora,
                    ventana_expira_en=ahora + timedelta(hours=horas),
                )
                sesion.add(hilo)
                await sesion.flush()
                sesion.add(
                    MensajeEntrante(
                        conversacion_id=hilo.id,
                        external_id=f"qa-modulos-{uuid.uuid4()}",
                        telefono_origen=telefono,
                        tipo="text",
                        texto="Quisiera consultar el horario de la clínica sintética.",
                        intencion="AYUDA",
                        recibido_en=ahora if horas > 0 else ahora - timedelta(hours=25),
                    )
                )
                datos[nombre] = {"id": str(hilo.id), "telefono": telefono}
            await sesion.commit()
    finally:
        await motor.dispose()
    sys.stdout.write(json.dumps(datos) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
