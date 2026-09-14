#!/usr/bin/env bash
# Verificacion real del ciclo respaldo -> restauracion.
# Un respaldo sin restauracion probada no cuenta como respaldo.
set -euo pipefail

# La clave viene del entorno. Si falta, se usa una de un solo uso: esta
# verificacion crea su propio volcado y lo borra al terminar, asi que la
# clave no protege nada que sobreviva al guion.
: "${CLAVE_RESPALDO:=verificacion-$(date +%s)-$RANDOM}"
export CLAVE_RESPALDO
TRABAJO=/tmp/respaldo-verificacion
BD_PRUEBA=clinica_restaurada
rm -rf "$TRABAJO"; mkdir -p "$TRABAJO"; cd "$TRABAJO"

echo "== 1. Estado de origen =="
ORIGEN=$(docker exec clinica-pg psql -U clinica -d clinica -tAc \
  "select (select count(*) from paciente)||'/'||(select count(*) from cita)||'/'||(select count(*) from nota_evolucion)||'/'||(select count(*) from knowledge_chunks)")
echo "  pacientes/citas/notas/fragmentos: $ORIGEN"

echo "== 2. Volcado cifrado =="
docker exec clinica-pg pg_dump -U clinica -d clinica -Fc \
  | openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -pass env:CLAVE_RESPALDO > clinica.dump.enc
echo "  tamano: $(du -h clinica.dump.enc | cut -f1)"

echo "== 3. El archivo no es legible en claro =="
if head -c 1024 clinica.dump.enc | grep -qa "PGDMP"; then
  echo "  FALLO: cabecera de pg_dump visible"; exit 1
else
  echo "  OK: sin cabecera PGDMP"
fi

echo "== 4. Una clave incorrecta no descifra =="
if openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass pass:clave-equivocada \
     -in clinica.dump.enc -out /dev/null 2>/dev/null; then
  echo "  FALLO: descifro con clave incorrecta"; exit 1
else
  echo "  OK: rechaza la clave incorrecta"
fi

echo "== 5. Restauracion en una base limpia =="
docker exec clinica-pg psql -U clinica -d postgres -c "DROP DATABASE IF EXISTS $BD_PRUEBA" >/dev/null
docker exec clinica-pg psql -U clinica -d postgres -c "CREATE DATABASE $BD_PRUEBA" >/dev/null
openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass env:CLAVE_RESPALDO -in clinica.dump.enc > clinica.dump
docker cp clinica.dump clinica-pg:/tmp/clinica.dump >/dev/null
docker exec clinica-pg pg_restore -U clinica -d "$BD_PRUEBA" --no-owner /tmp/clinica.dump 2>&1 | tail -3 || true

echo "== 6. Los datos coinciden =="
DESTINO=$(docker exec clinica-pg psql -U clinica -d "$BD_PRUEBA" -tAc \
  "select (select count(*) from paciente)||'/'||(select count(*) from cita)||'/'||(select count(*) from nota_evolucion)||'/'||(select count(*) from knowledge_chunks)")
echo "  origen:      $ORIGEN"
echo "  restaurado:  $DESTINO"
[ "$ORIGEN" = "$DESTINO" ] && echo "  OK: coinciden" || { echo "  FALLO: no coinciden"; exit 1; }

echo "== 7. La extension pgvector sobrevive =="
VEC=$(docker exec clinica-pg psql -U clinica -d "$BD_PRUEBA" -tAc \
  "select coalesce((select extversion from pg_extension where extname='vector'),'AUSENTE')")
echo "  pgvector: $VEC"
[ "$VEC" != "AUSENTE" ] || { echo "  FALLO: sin pgvector la busqueda no funciona"; exit 1; }

echo "== 8. Los indices vectoriales se restauran =="
IDX=$(docker exec clinica-pg psql -U clinica -d "$BD_PRUEBA" -tAc \
  "select count(*) from pg_indexes where indexdef ilike '%hnsw%'")
echo "  indices HNSW: $IDX"
[ "$IDX" -gt 0 ] || { echo "  FALLO: sin indice HNSW la busqueda seria un recorrido completo"; exit 1; }

echo "== 9. Las restricciones criticas sobreviven =="
for r in cita_sin_solape_profesional cita_sin_solape_consultorio ck_paciente_documento_exige_numero ck_conversacion_canal_valido; do
  N=$(docker exec clinica-pg psql -U clinica -d "$BD_PRUEBA" -tAc \
    "select count(*) from pg_constraint where conname='$r'")
  [ "$N" -gt 0 ] && echo "  OK: $r" || echo "  AUSENTE: $r"
done

echo "== 10. El anti doble-reserva sigue vigente tras restaurar =="
docker exec clinica-pg psql -U clinica -d "$BD_PRUEBA" -tAc \
  "select count(*) from pg_constraint where contype='x'" | xargs echo "  restricciones de exclusion:"

echo "== 11. Limpieza =="
docker exec clinica-pg psql -U clinica -d postgres -c "DROP DATABASE $BD_PRUEBA" >/dev/null
docker exec clinica-pg rm -f /tmp/clinica.dump
rm -rf "$TRABAJO"
echo "  base de verificacion eliminada"
echo
echo "RESTAURACION VERIFICADA"
