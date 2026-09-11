# ADR‑0003 — Cachés y artefactos de construcción fuera del disco C:

* **Estado:** aceptada
* **Fecha:** 2026‑09‑11

## Contexto

El disco C: del equipo de desarrollo tiene **764 MB libres**. Es un estado crítico: por
debajo de ~1 GB Windows puede fallar al paginar, actualizar o crear archivos temporales.
Las herramientas de la pila, por defecto, escriben en C:

| Herramienta | Ubicación por defecto | Tamaño típico |
|---|---|---|
| caché de pip | `%LOCALAPPDATA%\pip\cache` | 0.5–2 GB |
| caché de uv | `%LOCALAPPDATA%\uv\cache` | 0.5–2 GB |
| navegadores de Playwright | `%LOCALAPPDATA%\ms-playwright` | 0.5–1.5 GB |
| modelos ONNX de fastembed | caché del usuario en C: | 0.1–0.5 GB |
| entorno virtual y `node_modules` | según el proyecto | 1–3 GB |

El caché de npm ya estaba redirigido a `D:\npm-cache` y los navegadores de Playwright ya
estaban descargados en `D:\playwright-browsers`.

## Decisión

Todo artefacto generado se ubica en D:. Se fija por variables de entorno del proyecto,
documentadas en `docs/deployment.md` y aplicadas por `infra/scripts/entorno-dev.ps1`:

```
PIP_CACHE_DIR=D:\cache\pip
UV_CACHE_DIR=D:\cache\uv
PLAYWRIGHT_BROWSERS_PATH=D:\playwright-browsers
RUTA_CACHE_EMBEDDINGS=D:\cache\fastembed
```

El entorno virtual vive en `backend/.venv` y `node_modules` en `frontend/node_modules`,
ambos ya en D: por estar dentro del repositorio.

## Consecuencias

* Se reutiliza el Chromium de Playwright ya descargado: no hay descarga nueva.
* Cualquier herramienta futura que exija espacio en C: se reporta al usuario en lugar de
  instalarse silenciosamente.
* Riesgo residual: el propio Windows y los perfiles de usuario siguen en C: con muy poco
  margen. Está registrado como riesgo **R‑01** en
  [`../threat-model.md`](../threat-model.md); su resolución (liberar espacio) queda del
  lado del usuario.
