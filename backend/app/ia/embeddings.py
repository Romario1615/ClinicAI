"""Proveedores de embeddings (ADR-0007).

Por que hay un proveedor simulado, y por que es determinista
------------------------------------------------------------
El proveedor real (`fastembed`) descarga un modelo ONNX de varios cientos de
megabytes la primera vez que se usa. Eso en el arranque de la suite significa
una descarga en cada ejecutor de CI limpio, y en este equipo significa gastar
espacio en un disco que no lo tiene (ADR-0003).

Pero el motivo principal no es el peso: es que **la recuperacion debe ser
reproducible**. Una prueba que afirma «este documento se recupera antes que
aquel» solo vale si los vectores son los mismos en cada ejecucion. Un modelo
real los produce iguales, si -- pero cualquier cambio de version del modelo
movería los resultados, y la prueba fallaría por un motivo que no tiene que
ver con el codigo.

`EmbeddingsSimulado` deriva el vector del texto con SHA-256. Es determinista,
instantaneo y no descarga nada. **No mide parecido semantico**: dos textos que
significan lo mismo con palabras distintas quedan lejos. Lo que si conserva es
lo que las pruebas de seguridad necesitan comprobar -- que un fragmento no
autorizado **no aparece**, algo que no depende de la calidad del vector.

La calidad real de la recuperacion se mide aparte, con el modelo real, en el
arnes de evaluacion (RF-O08). Esa medicion no se sustituye por esto, y se
reportara medida, no supuesta (limitacion E-9).
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import math
import struct
from typing import Protocol, runtime_checkable

from app.nucleo.registro import obtener_logger

logger = obtener_logger(__name__)

# Dimension por defecto, la del modelo `intfloat/multilingual-e5-small`.
DIMENSION_POR_DEFECTO = 384
MODELO_FASTEMBED_POR_DEFECTO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Nombre con el que se guardan los vectores del proveedor simulado. Empieza
# por `simulado:` a proposito: si un vector de pruebas acabara en una base de
# datos real, la columna `modelo` lo delata de un vistazo.
MODELO_SIMULADO = "simulado:sha256"


@runtime_checkable
class ProveedorEmbeddings(Protocol):
    """Contrato de un proveedor de vectores."""

    nombre_modelo: str
    dimension: int

    async def vectorizar(self, textos: list[str]) -> list[list[float]]:
        """Devuelve un vector por texto, en el mismo orden.

        Trabaja por lotes y no de uno en uno porque todos los modelos reales
        son mucho mas eficientes asi, y porque la ingesta de un documento
        produce decenas de fragmentos a la vez.
        """
        ...

    async def vectorizar_consulta(self, texto: str) -> list[float]:
        """Vector de una consulta.

        Existe separado de `vectorizar` porque varios modelos -- el E5 entre
        ellos -- exigen prefijos distintos para documento y consulta
        (`passage:` y `query:`). Usar el mismo camino para ambos degrada la
        recuperacion de forma silenciosa: no falla, solo recupera peor.
        """
        ...


class EmbeddingsSimulado:
    """Vectores deterministas derivados del texto. No mide semantica.

    Se usa en las pruebas y en cualquier entorno sin el modelo descargado.
    """

    def __init__(self, dimension: int = DIMENSION_POR_DEFECTO) -> None:
        self.nombre_modelo = MODELO_SIMULADO
        self.dimension = dimension

    async def vectorizar(self, textos: list[str]) -> list[list[float]]:
        return [self._derivar(texto) for texto in textos]

    async def vectorizar_consulta(self, texto: str) -> list[float]:
        return self._derivar(texto)

    def _derivar(self, texto: str) -> list[float]:
        """Deriva un vector unitario del hash del texto.

        Se normaliza a longitud 1 porque la busqueda usa distancia coseno: sin
        normalizar, textos largos producirian vectores de mayor magnitud y la
        comparacion dejaria de significar lo que se espera.

        Se mezcla el indice del bloque en cada iteracion para que los 384
        componentes no se repitan ciclicamente a partir de los 32 bytes del
        primer hash.
        """
        # Se normaliza el texto para que dos fragmentos que solo difieren en
        # espacios o mayusculas produzcan el mismo vector. Sin esto, el mismo
        # contenido reindexado daria un vector distinto y pareceria otro
        # documento.
        semilla = " ".join(texto.lower().split()).encode("utf-8")

        bruto: list[float] = []
        bloque = 0
        while len(bruto) < self.dimension:
            resumen = hashlib.sha256(semilla + struct.pack(">I", bloque)).digest()
            # Cada 4 bytes producen un componente en [-1, 1).
            for desplazamiento in range(0, len(resumen), 4):
                if len(bruto) >= self.dimension:
                    break
                (entero,) = struct.unpack(">I", resumen[desplazamiento : desplazamiento + 4])
                bruto.append((entero / 2**31) - 1.0)
            bloque += 1

        norma = math.sqrt(sum(componente * componente for componente in bruto))
        if norma == 0.0:  # pragma: sin cobertura - imposible con SHA-256
            return [0.0] * self.dimension
        return [componente / norma for componente in bruto]


class EmbeddingsFastembed:
    """Proveedor local con `fastembed` (ONNX, sin clave y sin red en ejecucion).

    El modelo se descarga una vez a `ruta_cache` y despues funciona sin red.
    Por defecto `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensiones,
    multilingue): `intfloat/multilingual-e5-small`, el valor anterior, no
    existe en fastembed 0.7 y el modo real fallaba al primer uso.

    La calidad de recuperacion con un modelo pequeno es inferior a la de los
    comerciales grandes (limitacion E-9). Se medira y se publicara; no se
    supone.
    """

    def __init__(
        self,
        nombre_modelo: str = MODELO_FASTEMBED_POR_DEFECTO,
        dimension: int = DIMENSION_POR_DEFECTO,
        ruta_cache: str | None = None,
    ) -> None:
        self.nombre_modelo = nombre_modelo
        self.dimension = dimension
        self._ruta_cache = ruta_cache
        self._modelo: object | None = None
        # Los modelos E5 exigen `passage:`/`query:`; los demas, texto limpio.
        self._e5 = "e5" in nombre_modelo.lower()

    def _cargar(self) -> object:
        """Carga el modelo la primera vez que se usa.

        Perezoso a proposito: importar `fastembed` arrastra `onnxruntime`, y
        hacerlo al importar el modulo penalizaria el arranque de la API, que
        no vectoriza nada.
        """
        if self._modelo is None:
            # Por `importlib` y no `import`: con fastembed instalado, mypy lo
            # seguiria hasta los stubs de numpy, que exigen Python 3.12.
            fastembed = importlib.import_module("fastembed")
            self._modelo = fastembed.TextEmbedding(
                model_name=self.nombre_modelo, cache_dir=self._ruta_cache
            )
            logger.info("embeddings.modelo_cargado", modelo=self.nombre_modelo)
        return self._modelo

    def _embeber(self, textos: list[str]) -> list[list[float]]:
        vectores = [
            list(map(float, v))
            for v in self._cargar().embed(textos)  # type: ignore[attr-defined]
        ]
        # Una dimension distinta de la columna vectorial fallaria al guardar
        # con un error opaco; aqui se dice que esta mal configurado.
        if vectores and len(vectores[0]) != self.dimension:
            raise ValueError(
                f"El modelo {self.nombre_modelo} produce {len(vectores[0])} dimensiones y la "
                f"configuracion espera {self.dimension}. Ajuste DIMENSION_EMBEDDINGS o el modelo."
            )
        return vectores

    async def vectorizar(self, textos: list[str]) -> list[list[float]]:
        # El calculo es CPU pura: en un hilo, para no bloquear la API mientras
        # se ingiere un documento grande.
        preparados = [f"passage: {t}" for t in textos] if self._e5 else list(textos)
        return await asyncio.to_thread(self._embeber, preparados)

    async def vectorizar_consulta(self, texto: str) -> list[float]:
        preparado = f"query: {texto}" if self._e5 else texto
        return (await asyncio.to_thread(self._embeber, [preparado]))[0]


def construir_proveedor_embeddings(
    modo: str, *, modelo: str, dimension: int, ruta_cache: str | None = None
) -> ProveedorEmbeddings:
    """Proveedor segun la configuracion.

    Un modo desconocido falla en lugar de caer al simulado: un entorno que
    cree estar usando el modelo real y en realidad usa vectores de hash
    produce una recuperacion inutil **sin ningun error**, y eso no se detecta
    hasta que alguien se queja de las respuestas.
    """
    if modo == "mock":
        return EmbeddingsSimulado(dimension=dimension)
    if modo == "fastembed":
        return EmbeddingsFastembed(nombre_modelo=modelo, dimension=dimension, ruta_cache=ruta_cache)
    raise ValueError(
        f"Proveedor de embeddings no soportado: {modo!r}. Valores validos: 'fastembed', 'mock'."
    )


__all__ = [
    "DIMENSION_POR_DEFECTO",
    "MODELO_FASTEMBED_POR_DEFECTO",
    "MODELO_SIMULADO",
    "EmbeddingsFastembed",
    "EmbeddingsSimulado",
    "ProveedorEmbeddings",
    "construir_proveedor_embeddings",
]
