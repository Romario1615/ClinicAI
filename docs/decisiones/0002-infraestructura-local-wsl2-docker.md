# ADR‑0002 — WSL2 con Docker Engine como infraestructura local

* **Estado:** aceptada
* **Fecha:** 2026‑09‑11

## Contexto

El sistema necesita PostgreSQL 16 con `pgvector`, `btree_gist` y `pg_trgm`, más Redis, y
las pruebas de integración deben ejecutarse contra servicios reales en contenedores. La
inspección del equipo de desarrollo arrojó:

* Docker **no instalado** (ni Docker Desktop ni engine).
* Disco **C: con 764 MB libres**. Docker Desktop requiere del orden de 4 GB en C: y no
  permite mover su instalación de programa a otro volumen.
* **Sin compilador MSVC** (solo el shell del instalador de Visual Studio), por lo que
  `pgvector` no puede compilarse de forma nativa para un PostgreSQL de Windows; instalar
  las herramientas de compilación supondría otros ~2‑3 GB en C:.
* WSL2 habilitado y establecido como versión por defecto, pero **sin distribución
  instalada**.
* Disco **D: con 40.1 GB libres**.
* El único PostgreSQL presente es el embebido de Odoo 16 (servicio detenido, en C:, sin
  `pgvector`).

## Opciones consideradas

| Opción | Resultado |
|---|---|
| Docker Desktop | Descartada: imposible por espacio en C: |
| PostgreSQL nativo de Windows + pgvector compilado | Descartada: sin MSVC y sin espacio para instalarlo |
| Reutilizar el PostgreSQL de Odoo | Descartada: sin `pgvector`, en C:, y reutilizarlo pondría en riesgo una instalación ajena al proyecto |
| **WSL2 con Ubuntu importado a D: y Docker Engine dentro** | **Elegida** |
| Diferir la infraestructura y usar dobles de prueba | Descartada: incumpliría las pruebas de integración, concurrencia y RAG exigidas |

## Decisión

Se importa una distribución Ubuntu a `D:\wsl\ubuntu` mediante `wsl --import` (evitando
la instalación por defecto, que ubica el disco virtual en C:) y dentro se instala Docker
Engine con el plugin Compose. Los ficheros `docker-compose` del repositorio se ejecutan
ahí, con la imagen `pgvector/pgvector:pg16` y `redis:7-alpine`.

## Consecuencias

**A favor**

* Paridad real entre el desarrollo local y el pipeline de CI: los mismos ficheros
  compose y la misma imagen de PostgreSQL con `pgvector`.
* Consumo de disco en D:, que tiene espacio.
* No se toca el PostgreSQL de Odoo ni MSSQLSERVER.

**En contra y mitigaciones**

* Configuración inicial más larga que Docker Desktop; se automatiza en
  `infra/wsl/aprovisionar.ps1`.
* El rendimiento de entrada/salida cae si los datos viven en el sistema de archivos de
  Windows montado (`/mnt/d`). Mitigación: los volúmenes de PostgreSQL se declaran como
  volúmenes de Docker dentro del sistema de archivos ext4 de la distribución, no como
  montajes de `/mnt/d`.
* Algún paso del aprovisionamiento puede pedir elevación de permisos; se avisa al usuario
  antes de ejecutarlo.
* La memoria es limitada (13.9 GB totales, ~2.8 GB libres con MSSQLSERVER activo). Se
  acota el consumo de WSL mediante `.wslconfig` y se declaran límites en compose.
