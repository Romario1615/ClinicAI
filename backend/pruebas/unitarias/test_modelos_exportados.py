"""Verifica que `app/modelos.py` exporte todos los modelos.

Por que existe esta prueba
--------------------------
Un modelo ausente de `app/modelos.py` no llega al metadata de SQLAlchemy, y
entonces `alembic revision --autogenerate` ve su tabla en la base de datos, no
la ve en el metadata, y **genera una migracion que la borra**.  Es la forma
mas rapida de perder datos con Alembic.

El fallo es sigiloso por partida doble: una clase importada pero ausente de
`__all__` la elimina `ruff --fix` por considerarla sin usar.  Ya ocurrio con
`Sede` durante el desarrollo: la importacion desaparecio en una pasada de
formateo y la suite de integracion se rompio con un `ImportError`.  Si en
lugar de romperse hubiera pasado inadvertida, la siguiente migracion habria
llevado un `op.drop_table("sede")`.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

import pytest

from app import modelos
from app.nucleo.bd import Base

pytestmark = pytest.mark.unitaria

RAIZ_APP = Path(modelos.__file__).resolve().parent
DIRECTORIO_MODULOS = RAIZ_APP / "modulos"


def _clases_de_modelo_en_disco() -> dict[str, str]:
    """Devuelve {nombre de clase: modulo} recorriendo `app/modulos/*/modelos.py`.

    Se lee el arbol de sintaxis en lugar de importar cada modulo para que la
    prueba detecte tambien un modulo que no se importa en ninguna parte, que
    es justo el caso peligroso.
    """
    encontradas: dict[str, str] = {}
    for ruta in sorted(DIRECTORIO_MODULOS.glob("*/modelos.py")):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        modulo = f"app.modulos.{ruta.parent.name}.modelos"
        for nodo in arbol.body:
            if not isinstance(nodo, ast.ClassDef):
                continue
            nombres_base = {
                base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
                for base in nodo.bases
            }
            # Modelos de tabla y enumeraciones de dominio.
            if nombres_base & {"Base", "StrEnum"}:
                encontradas[nodo.name] = modulo
    return encontradas


def test_todos_los_modelos_estan_exportados() -> None:
    """Cada clase de `app/modulos/*/modelos.py` debe estar en `app.modelos`."""
    en_disco = _clases_de_modelo_en_disco()
    exportadas = set(modelos.__all__)

    faltantes = {nombre: modulo for nombre, modulo in en_disco.items() if nombre not in exportadas}
    assert not faltantes, (
        "Estas clases no estan exportadas en app/modelos.py:\n"
        + "\n".join(f"  - {n}  (de {m})" for n, m in sorted(faltantes.items()))
        + "\n\nUna tabla ausente del metadata hace que `alembic autogenerate` "
        "genere una migracion que la BORRA."
    )


def test_todo_lo_declarado_en_all_existe() -> None:
    """`__all__` no debe referenciar nombres inexistentes."""
    inexistentes = [nombre for nombre in modelos.__all__ if not hasattr(modelos, nombre)]
    assert not inexistentes, f"`__all__` declara nombres que no existen: {inexistentes}"


def test_all_esta_ordenado_y_sin_duplicados() -> None:
    """Facilita las revisiones: un `__all__` desordenado produce diffs ruidosos."""
    assert modelos.__all__ == sorted(modelos.__all__), "`__all__` debe estar ordenado."
    assert len(modelos.__all__) == len(set(modelos.__all__))


def test_todas_las_tablas_del_metadata_tienen_modelo() -> None:
    """El metadata y las clases exportadas deben corresponderse.

    Detecta el caso inverso: una tabla que sigue en el metadata porque otro
    modulo la importa, pero cuya clase ya no se exporta aqui.
    """
    clases_exportadas = {
        nombre
        for nombre in modelos.__all__
        if inspect.isclass(getattr(modelos, nombre))
        and issubclass(getattr(modelos, nombre), Base)
        and getattr(modelos, nombre) is not Base
    }
    tablas_de_clases = {getattr(modelos, nombre).__tablename__ for nombre in clases_exportadas}
    tablas_del_metadata = set(Base.metadata.tables)

    sin_clase_exportada = tablas_del_metadata - tablas_de_clases
    assert not sin_clase_exportada, (
        f"Tablas en el metadata sin clase exportada en app/modelos.py: "
        f"{sorted(sin_clase_exportada)}"
    )


def test_los_modulos_de_modelos_se_importan_sin_error() -> None:
    """Cada modulo de modelos debe poder importarse por si solo."""
    for ruta in sorted(DIRECTORIO_MODULOS.glob("*/modelos.py")):
        nombre = f"app.modulos.{ruta.parent.name}.modelos"
        importlib.import_module(nombre)
