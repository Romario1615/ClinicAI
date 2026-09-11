# ADR‑0004 — `uv` con archivo de bloqueo para las dependencias de Python

* **Estado:** aceptada
* **Fecha:** 2026‑09‑11

## Contexto

El pipeline exige una «instalación reproducible». El entorno tiene Python 3.11.9 y pip
24.0, pero **no** tiene Poetry ni uv. Una instalación con `pip install -r
requirements.txt` sin fijar el árbol completo de dependencias transitivas no es
reproducible: dos ejecuciones en fechas distintas pueden resolver versiones diferentes,
lo que en un sistema que maneja datos clínicos convierte cualquier auditoría de
dependencias en una foto caducada.

## Opciones consideradas

* **pip + requirements.txt a mano**: no reproducible; descartada.
* **pip-tools** (`pip-compile`): reproducible y solo necesita pip, pero lento y sin
  gestión del entorno virtual.
* **Poetry**: maduro, pero pesado y con historial de fricción en resolución.
* **uv**: instalable con `pip install uv` sin permisos de administrador, resuelve órdenes
  de magnitud más rápido, genera `uv.lock` con hashes de todo el árbol y gestiona el
  entorno virtual.

## Decisión

Se usa `uv` con `pyproject.toml` y `uv.lock` versionado. La instalación, tanto local como
en CI, se hace con `uv sync --frozen`, que falla si el archivo de bloqueo no corresponde
al `pyproject.toml`. El caché de uv se dirige a D: (ADR‑0003).

## Consecuencias

* `uv.lock` se versiona y es obligatorio actualizarlo en el mismo commit que cambie una
  dependencia; el CI lo verifica con `--frozen`.
* Los hashes del archivo de bloqueo permiten que `pip-audit` y el escaneo de
  dependencias analicen exactamente lo que se instalará.
* Dependencia añadida de una herramienta relativamente joven. Mitigación: `uv` respeta
  `pyproject.toml` estándar (PEP 621), así que migrar a pip‑tools o Poetry sería
  mecánico si hiciera falta.
