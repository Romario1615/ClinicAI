"""Prueba de arquitectura: una sola puerta a `knowledge_chunks`.

ADR-0013 afirma que **no existe ninguna otra via de consulta a
`knowledge_chunks` desde la capa de IA**. Esa afirmacion es la que sostiene la
seguridad del RAG: si alguien anade una consulta nueva en otro modulo y se
olvida de una condicion del filtro, es una fuga entre sedes, entre
especialidades o de documentos sin aprobar.

Una afirmacion asi no se puede sostener leyendo el codigo cada vez. Esta
prueba recorre el **arbol de sintaxis** de todo `app/` y comprueba que el
modelo solo se referencia desde los modulos autorizados.

Por que AST y no una busqueda de texto
--------------------------------------
`grep KnowledgeChunk` daria falsos positivos con los comentarios y los
docstrings -- que mencionan la tabla a menudo, precisamente porque esta
documentada -- y falsos negativos con un `from ... import (\\n  KnowledgeChunk`
partido en varias lineas. El AST ve lo que el interprete ve.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = [pytest.mark.unitaria, pytest.mark.seguridad]

RAIZ = pathlib.Path(__file__).resolve().parents[2] / "app"

# Nombres cuyo uso implica acceso directo a los fragmentos de conocimiento.
MODELOS_RESTRINGIDOS = frozenset({"KnowledgeChunk", "KnowledgeEmbedding"})

# Modulos que SI pueden usarlos, con el motivo.
#
# La lista es corta a proposito: cada entrada nueva es una via mas por la que
# puede escaparse un filtro, y anadirla deberia costar una conversacion.
AUTORIZADOS: dict[str, str] = {
    "app/modulos/conocimiento/modelos.py": "Los define.",
    "app/modulos/conocimiento/repositorio.py": (
        "Es la unica puerta de consulta, y aplica el filtro completo."
    ),
    "app/modulos/conocimiento/servicios.py": (
        "Los escribe durante la ingesta y propaga el estado del documento."
    ),
    "app/modelos.py": "Punto unico de importacion que necesita Alembic.",
}


def _modulos_python() -> list[pathlib.Path]:
    return sorted(p for p in RAIZ.rglob("*.py") if "__pycache__" not in p.parts)


def _ruta_relativa(archivo: pathlib.Path) -> str:
    return archivo.relative_to(RAIZ.parent).as_posix()


def _usa_modelos_restringidos(arbol: ast.AST) -> set[str]:
    """Nombres restringidos que el modulo importa o referencia.

    Se miran los `import` y tambien los `Name`/`Attribute`: un modulo podria
    acceder al modelo a traves de `app.modelos.KnowledgeChunk` sin importarlo
    directamente.
    """
    usados: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom):
            usados.update(alias.name for alias in nodo.names if alias.name in MODELOS_RESTRINGIDOS)
        elif isinstance(nodo, ast.Name) and nodo.id in MODELOS_RESTRINGIDOS:
            usados.add(nodo.id)
        elif isinstance(nodo, ast.Attribute) and nodo.attr in MODELOS_RESTRINGIDOS:
            usados.add(nodo.attr)
    return usados


def test_solo_los_modulos_autorizados_tocan_los_fragmentos() -> None:
    """Ningun modulo fuera de la lista referencia `KnowledgeChunk`.

    Si esta prueba falla, la pregunta no es «como la hago pasar»: es si la
    consulta nueva aplica **todas** las condiciones de `_condiciones`. Si las
    aplica, lo correcto casi siempre sigue siendo llamar al repositorio.
    """
    infractores: dict[str, set[str]] = {}

    for archivo in _modulos_python():
        relativa = _ruta_relativa(archivo)
        if relativa in AUTORIZADOS:
            continue
        arbol = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))
        usados = _usa_modelos_restringidos(arbol)
        if usados:
            infractores[relativa] = usados

    assert not infractores, (
        "Estos modulos acceden a los fragmentos de conocimiento sin pasar por "
        f"`RepositorioConocimiento`: { {k: sorted(v) for k, v in infractores.items()} }.\n"
        "Toda consulta debe ir por `buscar_conocimiento_autorizado`, que aplica el "
        "filtro de autorizacion completo (ADR-0013)."
    )


def test_la_lista_de_autorizados_no_tiene_entradas_muertas() -> None:
    """Cada excepcion debe corresponder a un archivo que existe.

    Una entrada que sobrevive al archivo que la justificaba deja un permiso
    abierto para el proximo modulo que se cree con ese nombre.
    """
    faltantes = [ruta for ruta in AUTORIZADOS if not (RAIZ.parent / ruta).exists()]
    assert not faltantes, f"Entradas de AUTORIZADOS sin archivo: {faltantes}"


def test_cada_autorizado_declara_su_motivo() -> None:
    """La lista no admite una entrada sin explicacion.

    Un permiso sin motivo escrito no se puede revisar despues: nadie sabe si
    sigue haciendo falta.
    """
    sin_motivo = [ruta for ruta, motivo in AUTORIZADOS.items() if not motivo.strip()]
    assert not sin_motivo


def test_el_repositorio_exige_contexto_de_autorizacion() -> None:
    """`buscar_conocimiento_autorizado` no admite buscar sin contexto.

    Si `contexto` tuviera un valor por defecto, bastaria olvidarlo en una
    llamada para buscar sin filtros. Se comprueba sobre la firma real.
    """
    import inspect  # noqa: PLC0415

    from app.modulos.conocimiento.repositorio import RepositorioConocimiento  # noqa: PLC0415

    firma = inspect.signature(RepositorioConocimiento.buscar_conocimiento_autorizado)
    contexto = firma.parameters["contexto"]
    assert contexto.default is inspect.Parameter.empty, (
        "`contexto` tiene valor por defecto. Un contexto opcional permite buscar "
        "sin filtros olvidandolo en una llamada."
    )
    assert contexto.kind is inspect.Parameter.KEYWORD_ONLY, (
        "`contexto` debe ser solo por palabra clave, para que no se pase por "
        "posicion y acabe en el parametro equivocado."
    )


def test_el_contexto_de_autorizacion_no_tiene_valores_por_defecto() -> None:
    """Ningun campo del contexto es opcional.

    Un contexto con defaults permisivos seria la forma mas facil de introducir
    una fuga: bastaria olvidar un campo al construirlo.
    """
    import dataclasses  # noqa: PLC0415

    from app.modulos.conocimiento.repositorio import ContextoAutorizacion  # noqa: PLC0415

    con_defecto = [
        campo.name
        for campo in dataclasses.fields(ContextoAutorizacion)
        if campo.default is not dataclasses.MISSING
        or campo.default_factory is not dataclasses.MISSING
    ]
    assert not con_defecto, f"Campos con valor por defecto en el contexto: {con_defecto}"
