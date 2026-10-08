-- Volumen sintético para medir consultas (pacientes y citas).
--
-- Se ejecuta sobre una base APARTE, nunca sobre la de desarrollo:
--   CREATE DATABASE clinica_carga;
--   POSTGRES_BD=clinica_carga uv run alembic upgrade head
--   POSTGRES_BD=clinica_carga uv run python -m app.semillas.cargar --embeddings mock
--   psql -d clinica_carga -v ON_ERROR_STOP=1 -f pruebas-carga/volumen.sql
--
-- Añade 40 000 pacientes [SINTETICO] y 25 000 citas pasadas por profesional
-- de la primera clínica (200 000 con las 8 de la semilla), en franjas de
-- 30 min sin solape. Solo datos sintéticos: documentos con prefijo CARGA.
-- La semilla en Python no sirve para este volumen: inserta fila a fila en una
-- transacción y con 2 000 pacientes y 20 000 citas no terminó en 40 minutos.
\timing on
begin;
insert into paciente (clinica_id, tipo_documento, numero_documento, nombre, apellido, nivel_verificacion, activo, fecha_nacimiento)
select c.id, 'CEDULA', 'CARGA' || lpad(g::text, 7, '0'), 'Paciente' || g || ' [SINTETICO]', 'Carga' || (g % 997), 'NO_VERIFICADO', true,
       date '1950-01-01' + (g * 37 % 25000)
from generate_series(1, 40000) g, (select id from clinica order by creado_en limit 1) c;

create temp table prof as
select p.id, p.clinica_id, row_number() over (order by p.id) - 1 as n,
  (select ps.sede_id from profesional_sede ps where ps.profesional_id = p.id limit 1) as sede_id,
  coalesce((select s.servicio_id from profesional_servicio s where s.profesional_id = p.id limit 1),
           (select id from servicio where clinica_id = p.clinica_id limit 1)) as servicio_id
from profesional p where p.clinica_id = (select id from clinica order by creado_en limit 1);
select count(*), count(sede_id), count(servicio_id) from prof;

create temp table pacs as select id, row_number() over (order by id) - 1 as n from paciente where numero_documento like 'CARGA%';

-- 25 000 citas por profesional: 16 franjas de 30 min por dia laborable, desde hace ~4 anos
insert into cita (clinica_id, sede_id, paciente_id, profesional_id, servicio_id, inicio, duracion_minutos, minutos_preparacion, fin, estado, origen, motivo_cancelacion)
select pr.clinica_id, pr.sede_id, pa.id, pr.id, pr.servicio_id, t.inicio, 30, 0, t.inicio + interval '30 min',

       case when t.inicio > now() then 'CONFIRMED' when k % 11 = 0 then 'CANCELLED' when k % 17 = 0 then 'NO_SHOW' else 'COMPLETED' end,
       case when k % 3 = 0 then 'WHATSAPP' else 'PANEL' end,
       case when t.inicio <= now() and k % 11 = 0 then 'Cancelación sintética de carga' end
from prof pr
cross join generate_series(0, 24999) k
cross join lateral (select (date_trunc('day', now()) - interval '1570 days' + ((k / 16) * interval '1 day') + interval '13 hours' + ((k % 16) * interval '30 min')) as inicio) t
join pacs pa on pa.n = (k * 8 + pr.n) % 40000;
commit;
analyze paciente; analyze cita;
select (select count(*) from paciente) pacientes, (select count(*) from cita) citas;
