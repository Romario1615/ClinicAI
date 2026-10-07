"""Genera los vectores de conocimiento que faltan para el modelo configurado.

Cuándo hace falta
-----------------
Al cambiar `PROVEEDOR_EMBEDDINGS` o `MODELO_EMBEDDINGS` (por ejemplo, de
`mock` al modelo real), los documentos ya cargados no tienen vector del modelo
nuevo y la mitad semántica de la búsqueda no los encuentra. El texto no se
toca: solo se añaden vectores. Se puede repetir sin efectos: lo ya indexado
con el modelo actual no se vuelve a calcular.

Uso:
    uv run python -m herramientas.reindexar_conocimiento

Códigos de salida:
    0  terminado (también si no había nada pendiente)
    2  configuración inválida o proveedor simulado
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Permite ejecutarlo como script sin instalar el paquete.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ia.embeddings import construir_proveedor_embeddings
from app.modulos.conocimiento.servicios import ServicioConocimiento
from app.nucleo.bd import GestorBaseDatos
from app.nucleo.configuracion import Configuracion
from app.nucleo.reloj import RelojSistema


async def _reindexar(configuracion: Configuracion) -> int:
    embeddings = construir_proveedor_embeddings(
        configuracion.proveedor_embeddings,
        modelo=configuracion.modelo_embeddings,
        dimension=configuracion.dimension_embeddings,
        ruta_cache=str(configuracion.ruta_cache_embeddings),
    )
    gestor = GestorBaseDatos(configuracion.url_base_datos, eco=False)
    try:
        async for sesion in gestor.sesion():
            servicio = ServicioConocimiento(sesion, RelojSistema(), embeddings)
            creados = await servicio.reindexar_embeddings()
            await sesion.commit()
            return creados
        return 0
    finally:
        await gestor.cerrar()


def main() -> int:
    configuracion = Configuracion()
    if configuracion.proveedor_embeddings == "mock":
        print(
            "PROVEEDOR_EMBEDDINGS=mock: los vectores simulados no sirven para buscar. Nada que hacer."
        )
        return 2
    creados = asyncio.run(_reindexar(configuracion))
    print(f"Vectores creados con {configuracion.modelo_embeddings}: {creados}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
