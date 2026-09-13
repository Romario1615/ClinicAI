"""La frontera del agente, verificada sobre el arbol sintactico.

Estas pruebas no ejercitan comportamiento: comprueban propiedades del codigo.
Existen porque las dos reglas que protegen al paciente aqui -- la IA no
escribe en la base y la IA no decide nada clinico -- se pueden romper con un
`import` bienintencionado, y una prueba de comportamiento no lo detectaria:
seguiria pasando mientras la via nueva funcione.

Lo que se verifica:

* Ninguna herramienta construye SQL ni toca la sesion directamente.
* El catalogo es exactamente el de la especificacion, ni una mas.
* Ningun esquema de argumentos deja que el modelo elija identidad ni ambito.
* Ninguna herramienta escribe en tablas clinicas.

Si una de estas falla, la respuesta correcta casi nunca es ajustar la prueba.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from app.ia.herramientas.registro import HERRAMIENTAS, NOMBRES_ESPERADOS

pytestmark = pytest.mark.unitaria

RAIZ = pathlib.Path(__file__).resolve().parents[2] / "app"
HERRAMIENTAS_DIR = RAIZ / "ia" / "herramientas"

# Nombres que, invocados dentro de las herramientas, significan que alguien
# esta construyendo una consulta en lugar de llamar a la capa de servicios.
CONSTRUCTORES_SQL: frozenset[str] = frozenset(
    {"select", "insert", "update", "delete", "text", "exists", "union", "join"}
)

# Metodos de sesion que escriben o ejecutan. `flush` y `refresh` tambien: si
# una herramienta necesita vaciar la sesion, es que esta manipulando objetos
# del modelo, y eso es trabajo del servicio.
METODOS_DE_SESION: frozenset[str] = frozenset(
    {"execute", "add", "add_all", "delete", "merge", "flush", "commit", "scalar", "scalars"}
)

# `repositorio.py` se permite en las de lectura: un repositorio aplica el
# filtro de ambito, que es justo lo que se quiere. Lo que no se permite es
# saltarselo y hablar con la sesion.
MODULOS = sorted(p for p in HERRAMIENTAS_DIR.rglob("*.py") if "__pycache__" not in p.parts)


def _arbol(archivo: pathlib.Path) -> ast.Module:
    return ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))


def _nombre_llamada(nodo: ast.Call) -> str:
    if isinstance(nodo.func, ast.Name):
        return nodo.func.id
    if isinstance(nodo.func, ast.Attribute):
        return nodo.func.attr
    return ""


@pytest.mark.parametrize("archivo", MODULOS, ids=lambda p: p.name)
def test_ninguna_herramienta_construye_sql(archivo: pathlib.Path) -> None:
    """Regla 4: el agente no escribe en la base, invoca servicios.

    Construir un `select` aqui seria una segunda via de acceso, y esa via no
    pasa por el filtro de ambito del repositorio. El resultado practico de una
    fuga asi es que el agente de una clinica lea la agenda de otra.
    """
    hallazgos = [
        _nombre_llamada(nodo)
        for nodo in ast.walk(_arbol(archivo))
        if isinstance(nodo, ast.Call) and _nombre_llamada(nodo) in CONSTRUCTORES_SQL
    ]
    assert not hallazgos, (
        f"{archivo.name} construye SQL: {sorted(set(hallazgos))}. "
        "Las herramientas llaman a la capa de servicios; el SQL vive en el repositorio."
    )


@pytest.mark.parametrize("archivo", MODULOS, ids=lambda p: p.name)
def test_ninguna_herramienta_usa_la_sesion_directamente(archivo: pathlib.Path) -> None:
    """Pasar la sesion a un servicio esta bien; escribir con ella, no.

    La diferencia importa: el servicio audita, aplica reglas de negocio y
    conoce el limite transaccional. Una herramienta que hace `sesion.add` se
    salta las tres cosas.
    """
    infractores: list[str] = []
    for nodo in ast.walk(_arbol(archivo)):
        if not isinstance(nodo, ast.Call) or not isinstance(nodo.func, ast.Attribute):
            continue
        if nodo.func.attr not in METODOS_DE_SESION:
            continue
        objeto = nodo.func.value
        nombre_objeto = (
            objeto.attr
            if isinstance(objeto, ast.Attribute)
            else objeto.id
            if isinstance(objeto, ast.Name)
            else ""
        )
        if "sesion" in nombre_objeto.lower():
            infractores.append(f"{nombre_objeto}.{nodo.func.attr}")

    assert not infractores, (
        f"{archivo.name} opera sobre la sesion: {sorted(set(infractores))}. "
        "La escritura pasa por la capa de servicios (CLAUDE.md, regla 4)."
    )


def test_el_catalogo_es_exactamente_el_de_la_especificacion() -> None:
    """Ni una herramienta de mas.

    Cada herramienta nueva es superficie que el agente puede invocar. Que
    anadir una obligue a tocar esta prueba es el punto: convierte la adicion
    en una decision explicita.
    """
    assert set(HERRAMIENTAS) == NOMBRES_ESPERADOS


def test_no_existe_ninguna_herramienta_que_toque_contenido_clinico() -> None:
    """Regla 5: la garantia real es que no hay por donde.

    No se comprueba con una lista negra de comportamientos, sino con la
    ausencia de la capacidad. Una herramienta llamada `create_prescription`
    no esta prohibida: no existe.
    """
    prohibidas = {
        "create_prescription",
        "update_prescription",
        "change_dose",
        "suspend_medication",
        "write_clinical_note",
        "record_diagnosis",
        "interpret_symptoms",
    }
    assert not (set(HERRAMIENTAS) & prohibidas)


@pytest.mark.parametrize("nombre", sorted(NOMBRES_ESPERADOS))
def test_ningun_esquema_deja_que_el_modelo_elija_identidad(nombre: str) -> None:
    """El «quien» no sale nunca de los argumentos.

    Si un esquema admitiera `clinica_id`, una inyeccion de prompt en un
    documento indexado bastaria para que el agente operase sobre otra clinica.
    El principal viaja en el contexto, fuera del alcance del modelo (ADR-0014).
    """
    esquema = HERRAMIENTAS[nombre].argumentos.model_json_schema()
    prohibidos = {
        "clinica_id",
        "actor_id",
        "actor_tipo",
        "permisos",
        "permiso",
        "ambito",
        "principal",
        "rol",
        "roles",
        "nivel_verificacion",
    }
    encontrados = set(esquema.get("properties", {})) & prohibidos
    assert not encontrados, (
        f"{nombre} admite campos de identidad: {sorted(encontrados)}. "
        "El principal se resuelve del token o del canal verificado, no del modelo."
    )


@pytest.mark.parametrize("nombre", sorted(NOMBRES_ESPERADOS))
def test_toda_herramienta_declara_su_permiso_o_justifica_no_tenerlo(nombre: str) -> None:
    """Un permiso a `None` solo se admite en la derivacion.

    Derivar a una persona no accede a ningun dato, y exigirle permiso
    significaria que un principal mal configurado se quedaria sin la unica
    salida segura del sistema. Cualquier otra herramienta sin permiso es un
    olvido.
    """
    herramienta = HERRAMIENTAS[nombre]
    if herramienta.permiso is None:
        assert nombre == "handoff_to_human"
    else:
        assert "." in herramienta.permiso


@pytest.mark.parametrize("nombre", sorted(NOMBRES_ESPERADOS))
def test_toda_herramienta_tiene_descripcion_util(nombre: str) -> None:
    """La descripcion es prompt: es lo que el modelo lee para decidir.

    Una descripcion vaga produce invocaciones equivocadas, y en este dominio
    una invocacion equivocada cancela la cita de alguien.
    """
    descripcion = HERRAMIENTAS[nombre].descripcion
    assert len(descripcion) >= 40, f"{nombre} tiene una descripcion demasiado escueta."
