# Pruebas de carga

## Qué se mide aquí, y qué no

La reserva es el único camino del sistema donde **la corrección depende de una
garantía del motor bajo concurrencia**: la restricción de exclusión que impide
dos citas solapadas. Todo lo demás puede ir lento; esto no puede ir **mal**.

Por eso el umbral que manda no es la latencia:

```
reservas_duplicadas = 0
```

Si ese contador sube, la prueba falla aunque la latencia sea excelente. Y la
comprobación no es contar los 409 —eso diría que el sistema rechazó cosas, no
que no aceptó dos—: al terminar se releen las citas activas del profesional y se
busca cualquier hora con más de una.

### Lo que estos números NO significan

Corren contra un portátil con PostgreSQL en WSL2, 200 pacientes sintéticos y
una base de 384 KB. Sirven para **comparar entre ejecuciones** —detectar que un
cambio empeoró algo— **no para prometerle capacidad a una clínica**.

Dimensionar de verdad exige volumen representativo, el hardware de destino y un
perfil de uso medido, no inventado.

## Cómo se ejecuta

```bash
# 1. La API accesible desde WSL y con límites de corrida
cd backend
LIMITE_LOGIN_POR_MINUTO=500 LIMITE_PETICIONES_POR_MINUTO=20000 \
  uv run uvicorn app.main:crear_aplicacion --factory --host 0.0.0.0

# 2. Desde WSL, con la IP del anfitrión (NO 127.0.0.1: ese es el loopback de WSL)
wsl -d clinica -- bash -lc "ip route show default | cut -d' ' -f3"

k6 run -e URL_API=http://<ip-del-anfitrion>:8000/api/v1 \
       -e CLINICA_ID=<uuid> reservas.js
```

Los dos ajustes de entorno —el límite de tasa y el `--host 0.0.0.0`— son de la
corrida, **no** del despliegue. Exponer la API en todas las interfaces de un
equipo de desarrollo la deja accesible en la red local; conviene devolverla a
`127.0.0.1` al terminar.

## Última ejecución

**2026‑09‑14**, portátil de desarrollo, 18 usuarios virtuales máximo.

| Métrica | Resultado |
|---|---|
| **Reservas duplicadas** | **0** |
| Colisiones resueltas con 409 | 37 |
| Peticiones totales | 2 314 |
| Errores inesperados | **0** de 429 comprobaciones |
| Latencia de disponibilidad | p95 **88 ms** · mediana 68 ms |
| Latencia de reserva | p95 **161 ms** · mediana 128 ms |
| Umbrales | todos superados |

Las 37 colisiones son el dato interesante: ocho usuarios virtuales peleando por
el mismo turno durante 30 segundos produjeron 37 rechazos correctos y **ninguna
cita duplicada**.

## Por qué hay un umbral de tráfico mínimo

```js
http_reqs: ['count > 100'],
```

La primera corrida de esta prueba **falló al conectar** y k6 informó
`reservas_duplicadas: 0` en verde. Un informe que dice «cero duplicados» cuando
no se intentó ni una reserva es peor que un fallo: se archiva como evidencia de
algo que nunca se comprobó.

## Lo que falta

| Pendiente | Por qué importa |
|---|---|
| **Volumen representativo** | Una base con años de historia se comporta de otra manera; los índices que sobran hoy hacen falta entonces |
| **Carga sostenida** (horas, no minutos) | Las fugas de memoria y el agotamiento del pool no aparecen en 90 segundos |
| **El worker bajo carga** | El outbox procesando mientras la API atiende no se ha medido |
| **Búsqueda RAG bajo carga** | La búsqueda vectorial es lo más caro del sistema y aquí no se toca |
| **Perfil de uso real** | La mezcla de operaciones está inventada: nadie ha medido qué hace de verdad una recepción |

## Volumen: consultas con 40 000 pacientes y 200 000 citas

`reservas.js` mide concurrencia sobre una base pequeña. Para ver qué consultas
dejan de escalar hace falta volumen: [`volumen.sql`](volumen.sql) lo genera en
SQL sobre una base aparte (`clinica_carga`). El modo de uso está en su
cabecera.

Cómo se midió (2026‑10‑08): una API contra `clinica_carga`, el escenario E2E 15
recorriendo todas las secciones del menú y `log_min_duration_statement = 20`
**solo en esa base** (`ALTER DATABASE clinica_carga SET …`, sin reiniciar
PostgreSQL). Después, `EXPLAIN ANALYZE` de cada consulta registrada.

| Consulta | Antes | Después | Cambio |
|---|---|---|---|
| Sala de espera: llegadas del día, espera media | seq scan, ~30 ms | 0,04–0,1 ms | índice parcial `ix_cita_llegada` |
| Cancelaciones del día | seq scan | 0,09 ms | índice parcial `ix_cita_cancelada` |
| Ocupación del periodo (`inicio < hasta AND fin > desde`) | seq scan, ~30 ms | 0,17 ms | índice `ix_cita_clinica_fin` |
| Pacientes nuevos y recurrentes | agregaba toda la historia, ~100–340 ms | sale del registro de ≥ 20 ms | `EXISTS` por paciente del periodo |
| Búsqueda de pacientes por nombre | seq scan, 119 ms | 0,9 ms | trigram `ix_paciente_nombre_completo_trgm` |
| Altas por periodo (cohortes) | seq scan | índice | `ix_paciente_creado` |

De punta a punta (API sobre la base de volumen): el panel pasó de una media de
814 ms (máximo 1,9 s) a 568 ms (máximo 1,1 s) antes de los dos últimos
índices; la búsqueda de pacientes, de unos 300 ms a 80–140 ms. Lo que queda
por petición (~70 ms) es sobre todo autenticación: unas seis consultas
pequeñas para construir el principal, que no se cachean a propósito porque una
revocación debe surtir efecto en la siguiente petición.

Mismas advertencias que arriba: portátil y WSL2, sin el hardware de destino.
Sirve para detectar consultas que no escalan, no para prometer capacidad.
