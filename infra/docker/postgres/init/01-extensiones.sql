-- ---------------------------------------------------------------------------
--  Extensiones requeridas por la plataforma.
--  Se ejecuta una sola vez, al inicializar el volumen de datos.
--
--  Si este script falla, el contenedor no queda saludable: es deliberado.
--  Arrancar sin `vector` o sin `btree_gist` daría un sistema que parece
--  funcionar pero no puede indexar conocimiento ni impedir la doble reserva.
-- ---------------------------------------------------------------------------

-- gen_random_uuid() para las claves primarias
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Necesaria para la restriccion de exclusion que impide el solapamiento de
-- citas: permite combinar igualdad (profesional_id) con solapamiento de
-- rangos (&&) en un mismo indice GiST.  Ver ADR-0009.
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Busqueda por similitud de texto: tolera errores de escritura en los
-- nombres de servicios, examenes y medicamentos.  Ver ADR-0013.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Busqueda textual insensible a tildes: "protocolo de preparacion" debe
-- encontrar "protocolo de preparación".
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Embeddings de la base de conocimiento.
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
--  Configuracion de busqueda textual en espanol sin tildes.
--  Se define aqui, en la inicializacion, para que este disponible a las
--  columnas generadas `tsvector` de knowledge_chunks, que no pueden depender
--  de una configuracion creada mas tarde por una migracion.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_ts_config WHERE cfgname = 'espanol_sin_tildes'
    ) THEN
        CREATE TEXT SEARCH CONFIGURATION espanol_sin_tildes ( COPY = spanish );
        ALTER TEXT SEARCH CONFIGURATION espanol_sin_tildes
            ALTER MAPPING FOR hword, hword_part, word
            WITH unaccent, spanish_stem;
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
--  Verificacion: si falta alguna extension, se aborta con error visible.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    faltantes text;
BEGIN
    SELECT string_agg(requerida, ', ')
      INTO faltantes
      FROM (
        VALUES ('pgcrypto'), ('btree_gist'), ('pg_trgm'), ('unaccent'), ('vector')
      ) AS r(requerida)
     WHERE NOT EXISTS (
        SELECT 1 FROM pg_extension WHERE extname = r.requerida
     );

    IF faltantes IS NOT NULL THEN
        RAISE EXCEPTION 'Extensiones no disponibles: %', faltantes;
    END IF;

    RAISE NOTICE 'Extensiones verificadas correctamente.';
END
$$;
