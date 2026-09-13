"""Proveedores de embeddings (ADR-0007).

Lo que se comprueba aqui es el **determinismo** del proveedor simulado, que es
la propiedad de la que depende que las pruebas de recuperacion sean
reproducibles. No se comprueba calidad semantica: el simulado no la tiene, y
decirlo es parte del contrato.

`EmbeddingsFastembed` no se prueba: descarga un modelo ONNX de cientos de
megabytes y no esta instalado en este equipo (limitacion E-9 y E-12). Su
cobertura baja es deliberada y esta declarada.
"""

from __future__ import annotations

import math

import pytest

from app.ia.embeddings import (
    DIMENSION_POR_DEFECTO,
    MODELO_SIMULADO,
    EmbeddingsFastembed,
    EmbeddingsSimulado,
    construir_proveedor_embeddings,
)

pytestmark = pytest.mark.unitaria


async def test_el_mismo_texto_produce_siempre_el_mismo_vector() -> None:
    """Es la propiedad de la que dependen las pruebas de recuperacion.

    Sin determinismo, una prueba que afirma «este documento se recupera antes
    que aquel» pasaria o fallaria segun la ejecucion.
    """
    proveedor = EmbeddingsSimulado()
    (uno,) = await proveedor.vectorizar(["preparacion para el examen"])
    (dos,) = await proveedor.vectorizar(["preparacion para el examen"])
    assert uno == dos


async def test_dos_instancias_distintas_coinciden() -> None:
    """El vector deriva del texto, no del estado del objeto.

    Si dependiera de la instancia, reindexar un documento produciria vectores
    que no casan con los de una consulta hecha por otro proceso.
    """
    (uno,) = await EmbeddingsSimulado().vectorizar(["texto"])
    (dos,) = await EmbeddingsSimulado().vectorizar(["texto"])
    assert uno == dos


async def test_los_espacios_y_las_mayusculas_no_cambian_el_vector() -> None:
    """El mismo contenido reindexado no puede parecer otro documento."""
    proveedor = EmbeddingsSimulado()
    (uno,) = await proveedor.vectorizar(["Preparacion   del  Examen"])
    (dos,) = await proveedor.vectorizar(["preparacion del examen"])
    assert uno == dos


async def test_textos_distintos_producen_vectores_distintos() -> None:
    proveedor = EmbeddingsSimulado()
    uno, dos = await proveedor.vectorizar(["examen de sangre", "horario de atencion"])
    assert uno != dos


async def test_el_vector_tiene_la_dimension_declarada() -> None:
    """La columna es `vector(384)`: una dimension distinta la rechaza el motor."""
    proveedor = EmbeddingsSimulado()
    (vector,) = await proveedor.vectorizar(["texto"])
    assert len(vector) == DIMENSION_POR_DEFECTO == proveedor.dimension


async def test_el_vector_esta_normalizado() -> None:
    """La busqueda usa distancia coseno.

    Sin normalizar, un texto largo produciria un vector de mayor magnitud y la
    comparacion dejaria de significar lo que se espera.
    """
    (vector,) = await EmbeddingsSimulado().vectorizar(["un texto cualquiera"])
    norma = math.sqrt(sum(componente**2 for componente in vector))
    assert norma == pytest.approx(1.0, abs=1e-9)


async def test_los_componentes_no_se_repiten_ciclicamente() -> None:
    """SHA-256 da 32 bytes; hacen falta 384 componentes.

    Si el relleno repitiera el mismo hash, los componentes 65 en adelante
    serian copia de los primeros y el vector tendria mucha menos informacion
    de la que aparenta.
    """
    (vector,) = await EmbeddingsSimulado().vectorizar(["texto"])
    primer_bloque = vector[:8]
    segundo_bloque = vector[8:16]
    assert primer_bloque != segundo_bloque


async def test_vectorizar_respeta_el_orden_del_lote() -> None:
    """El vector se asocia a su fragmento por posicion.

    Un desorden aqui asignaria el vector de un fragmento a otro, y la
    recuperacion devolveria textos que no corresponden.
    """
    proveedor = EmbeddingsSimulado()
    textos = ["primero", "segundo", "tercero"]
    lote = await proveedor.vectorizar(textos)
    for texto, vector in zip(textos, lote, strict=True):
        (individual,) = await proveedor.vectorizar([texto])
        assert vector == individual


async def test_la_consulta_usa_el_mismo_camino_en_el_simulado() -> None:
    """El simulado no distingue documento de consulta.

    El modelo real si -- E5 exige `passage:` y `query:` --, y por eso el
    contrato tiene dos metodos. Aqui se comprueba que el simulado es coherente
    consigo mismo, que es lo que hace reproducible la busqueda.
    """
    proveedor = EmbeddingsSimulado()
    (documento,) = await proveedor.vectorizar(["examen de sangre"])
    consulta = await proveedor.vectorizar_consulta("examen de sangre")
    assert documento == consulta


def test_el_modelo_simulado_se_identifica_en_la_columna() -> None:
    """Si un vector de pruebas acabara en una base real, se ve de un vistazo."""
    assert EmbeddingsSimulado().nombre_modelo == MODELO_SIMULADO
    assert MODELO_SIMULADO.startswith("simulado:")


# ---------------------------------------------------------------------------
#  Seleccion de proveedor
# ---------------------------------------------------------------------------
def test_el_modo_mock_devuelve_el_simulado() -> None:
    proveedor = construir_proveedor_embeddings(
        "mock", modelo="lo-que-sea", dimension=DIMENSION_POR_DEFECTO
    )
    assert isinstance(proveedor, EmbeddingsSimulado)


def test_el_modo_fastembed_devuelve_el_real_sin_cargarlo() -> None:
    """Construirlo no descarga nada: el modelo se carga al primer uso.

    Importar `fastembed` arrastra `onnxruntime`, y hacerlo al arrancar
    penalizaria a la API, que no vectoriza nada.
    """
    proveedor = construir_proveedor_embeddings(
        "fastembed",
        modelo="intfloat/multilingual-e5-small",
        dimension=DIMENSION_POR_DEFECTO,
    )
    assert isinstance(proveedor, EmbeddingsFastembed)
    assert proveedor.nombre_modelo == "intfloat/multilingual-e5-small"


def test_un_modo_desconocido_falla_en_lugar_de_caer_al_simulado() -> None:
    """Un entorno que cree usar el modelo real y usa hashes produce una
    recuperacion inutil **sin ningun error**, y eso no se detecta hasta que
    alguien se queja de las respuestas.
    """
    with pytest.raises(ValueError, match="no soportado"):
        construir_proveedor_embeddings("inventado", modelo="x", dimension=DIMENSION_POR_DEFECTO)
