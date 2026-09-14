# Respaldo y restauración

> **Un respaldo sin restauración verificada no es un respaldo.** Es un archivo
> del que nadie sabe si sirve. Este documento describe un ciclo que **se ha
> ejecutado**, no uno que se ha diseñado.
>
> **Última verificación:** 2026‑09‑13, entorno local, PostgreSQL 16.15 con
> pgvector 0.8.6. 11 comprobaciones, 0 fallos.

---

## 1. Qué contiene un volcado de esta base

Historia clínica, recetas, datos de contacto de pacientes y la auditoría
completa. Un archivo de respaldo es **una copia íntegra de datos de salud sin
ninguno de los controles del sistema**: no tiene permisos, no tiene filtro de
ámbito, no registra quién lo abre.

De ahí las dos reglas que gobiernan todo lo demás:

1. **El volcado nunca toca el disco sin cifrar.** El cifrado va encadenado en
   la misma tubería que `pg_dump`, así que no existe ni siquiera un archivo
   temporal en claro.
2. **La clave no vive en el repositorio ni en el script.** Entra por
   `CLAVE_RESPALDO` desde el gestor de secretos del operador. Sin ella el
   script se niega a ejecutarse; producir un respaldo en claro «solo por esta
   vez» es justo como acaban existiendo.

---

## 2. Crear un respaldo

```powershell
# La clave viene del gestor de secretos. Nunca se escribe en un archivo.
$env:CLAVE_RESPALDO = <desde el gestor de secretos>

.\infra\scripts\respaldo.ps1 -Destino D:\respaldos-clinica
```

El script usa formato personalizado (`pg_dump -Fc`): comprime por su cuenta y
permite restaurar tablas sueltas, que es lo que hace falta cuando el incidente
afecta a una sola cosa y no a toda la base.

Cifrado: AES‑256‑CBC con `pbkdf2` y 600 000 iteraciones. Las iteraciones
encarecen un ataque por diccionario contra la clave; no son gratis en tiempo de
CPU y por eso se declaran aquí en lugar de esconderse.

El script **borra el archivo si sale por debajo de 1 KB**: un volcado truncado
que parece un respaldo es peor que no tenerlo, porque nadie lo mira hasta el
día que hace falta.

---

## 3. Verificar que se puede restaurar

Esto **no es opcional**, y es el único motivo por el que el criterio 14 de
[`production-readiness.md`](production-readiness.md) puede dejar de estar en
«no evaluado».

```bash
wsl -d clinica -- bash "/mnt/d/Sistema IA de Clinicas/infra/scripts/verificar-respaldo.sh"
```

El guion hace un ciclo completo contra una base desechable y la elimina al
terminar. **No toca la base de origen.**

### Qué comprueba, y por qué cada cosa

| # | Comprobación | Por qué importa |
|---|---|---|
| 1 | Recuento de origen | Punto de comparación |
| 2 | Volcado cifrado | El ciclo real, no una simulación |
| 3 | **Sin cabecera `PGDMP` en claro** | Si apareciera, el cifrado no se aplicó y el archivo es legible |
| 4 | **Una clave incorrecta no descifra** | Sin esta prueba, un cifrado roto pasaría inadvertido |
| 5 | Restauración en base limpia | `pg_restore` sobre una base nueva |
| 6 | **Los recuentos coinciden** | Pacientes, citas, notas y fragmentos, uno a uno |
| 7 | **`pgvector` sobrevive** | Sin la extensión, la búsqueda de conocimiento no arranca |
| 8 | **El índice HNSW se restaura** | Sin él la búsqueda funciona pero recorre la tabla entera: lenta, no rota, y por eso el fallo tardaría meses en notarse |
| 9 | Las restricciones críticas siguen | Nombradas una a una, no contadas |
| 10 | **Las 2 restricciones de exclusión siguen** | Son el anti doble‑reserva. Una restauración que las perdiera daría una base que acepta dos pacientes a la misma hora |
| 11 | Limpieza | La base de verificación se elimina |

### Resultado de la última ejecución

```
origen:      200 pacientes / 644 citas / 16 notas / 18 fragmentos
restaurado:  200 pacientes / 644 citas / 16 notas / 18 fragmentos
OK: coinciden

OK: sin cabecera PGDMP
OK: rechaza la clave incorrecta
pgvector: 0.8.6
indices HNSW: 1
OK: cita_sin_solape_profesional
OK: cita_sin_solape_consultorio
OK: ck_paciente_documento_exige_numero
OK: ck_conversacion_canal_valido
restricciones de exclusion: 2

RESTAURACION VERIFICADA
```

---

## 4. Restaurar de verdad, tras un incidente

```bash
# 1. Detener la aplicación. Restaurar con escrituras en curso mezcla estados.
#    La base queda con filas de antes y de después del volcado.

# 2. Descifrar
openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 \
  -pass env:CLAVE_RESPALDO -in clinica-AAAAMMDD-HHMMSS.dump.enc -out clinica.dump

# 3. Restaurar sobre una base NUEVA, nunca sobre la dañada
docker exec clinica-pg psql -U clinica -d postgres -c "CREATE DATABASE clinica_recuperada"
docker cp clinica.dump clinica-pg:/tmp/clinica.dump
docker exec clinica-pg pg_restore -U clinica -d clinica_recuperada --no-owner /tmp/clinica.dump

# 4. Comprobar ANTES de apuntar la aplicación
docker exec clinica-pg psql -U clinica -d clinica_recuperada -c \
  "select count(*) from paciente; select count(*) from pg_constraint where contype='x'"

# 5. Solo entonces, apuntar la aplicación a la base recuperada

# 6. Borrar el .dump descifrado
shred -u clinica.dump 2>/dev/null || rm -f clinica.dump
```

**Nunca se restaura sobre la base dañada.** Si la restauración falla a medias
se pierden las dos: la dañada, que quizá era recuperable, y la copia. Restaurar
en una base nueva deja la original intacta mientras se comprueba.

**El `.dump` descifrado se borra.** Es el mismo contenido que el cifrado, sin
la protección. Olvidarlo en `/tmp` anula todo lo anterior.

---

## 5. Lo que este procedimiento **no** cubre

Se declara porque asumirlo cubierto es peor que saberlo pendiente.

| Pendiente | Consecuencia |
|---|---|
| **No hay programación automática.** El respaldo se lanza a mano | Un respaldo que depende de que alguien se acuerde no existe los fines de semana |
| **No hay retención ni rotación.** Los archivos se acumulan | Disco lleno, y copias antiguas sin vigilancia acumulando datos de salud |
| **No se ha probado con volumen real.** 384 KB sobre datos sintéticos | Una base con años de historia tarda otro orden de magnitud, y el tiempo de restauración *es* el tiempo de caída |
| **No hay copia fuera del equipo.** El archivo vive en el mismo disco | Un fallo del disco se lleva la base y su respaldo |
| **No hay recuperación a un punto en el tiempo** (PITR/WAL) | Se pierde todo lo ocurrido entre el último volcado y el incidente |
| **No se ha medido RTO ni RPO** | «Cuánto tardamos» y «cuánto perdemos» son preguntas que la clínica hará y que hoy no tienen respuesta medida |
| **La custodia de la clave no está definida** | Un respaldo cuya clave se pierde es un archivo inútil. Quién la guarda, dónde y cómo se rota es una decisión de la clínica |

---

## 6. Antes de usar esto con pacientes reales

1. Programar el respaldo (tarea programada o `cron` en el anfitrión).
2. Definir retención, rotación y copia fuera del equipo.
3. Definir la custodia y rotación de `CLAVE_RESPALDO`.
4. Medir RTO y RPO sobre un volumen representativo.
5. **Ejecutar `verificar-respaldo.sh` periódicamente, no una sola vez.** Un
   respaldo verificado en septiembre no dice nada de uno hecho en diciembre
   tras tres migraciones de esquema.
6. Decidir si hace falta PITR. Para una clínica, perder un día de citas y notas
   es una decisión que la clínica tiene que tomar con conocimiento, no una que
   se hereda del valor por defecto.

Ver también [`deployment.md`](deployment.md) y
[`incident-response.md`](incident-response.md).
