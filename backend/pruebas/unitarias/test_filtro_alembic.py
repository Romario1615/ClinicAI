"""Autogenerate conserva el respaldo reversible y detecta tablas ajenas."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unitaria


@pytest.mark.parametrize(
    ("nombre", "tipo", "esperado"),
    [
        ("respaldo_consulta_roles_20261009", "table", False),
        ("alembic_version", "table", False),
        ("pg_interna", "table", False),
        ("paciente", "table", True),
        ("respaldo_desconocido", "table", True),
        ("respaldo_consulta_roles_20261009", "column", True),
        (None, "table", True),
    ],
)
def test_filtro_autogenerate(nombre: str | None, tipo: str, esperado: bool) -> None:
    # Extraer la funcion evita ejecutar env.py, que requiere contexto Alembic
    # y abre una conexion. Se prueba la misma funcion usada por check/revision.
    archivo = Path(__file__).resolve().parents[2] / "alembic" / "env.py"
    arbol = ast.parse(archivo.read_text(encoding="utf-8"))
    funcion = next(
        nodo
        for nodo in arbol.body
        if isinstance(nodo, ast.FunctionDef) and nodo.name == "_incluir_objeto"
    )
    modulo = ast.Module(body=[funcion], type_ignores=[])
    espacio: dict = {}
    exec(compile(modulo, str(archivo), "exec"), espacio)
    assert espacio["_incluir_objeto"](object(), nombre, tipo, True, None) is esperado
