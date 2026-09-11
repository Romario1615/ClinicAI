"""Anade a la migracion inicial lo que Alembic no sabe autogenerar.

Existe como herramienta, y no como edicion manual, porque al regenerar la
migracion las adiciones se pierden en silencio.  Volver a ejecutar este script
las restituye, y es idempotente.

Dos omisiones reales de `alembic revision --autogenerate`:

1. **Las extensiones no se crean.**  Solo existen por el script de
   inicializacion del contenedor, que es exclusivo del entorno local.  Una
   instancia gestionada de PostgreSQL no lo ejecuta y la migracion fallaria
   al llegar a la restriccion de exclusion, que necesita `btree_gist`.

2. **Los disparadores no se generan.**  Hacen falta para calcular `cita.fin`
   y para impedir modificaciones en las tablas de solo insercion.

Sobre las restricciones de exclusion
------------------------------------
Alembic SI las autogenera dentro de `op.create_table`, asi que no se crean
aqui: duplicarlas produce "relation already exists".  Lo que si se anade es
una **verificacion** al final de la migracion: si alguna vez dejaran de
generarse (ocurrio con una version anterior del modelo, cuando `rango` usaba
una expresion `Computed` compleja), la migracion falla de forma visible en
lugar de dejar el sistema sin proteccion anti doble reserva.

Uso:
    python -m herramientas.parchear_migracion_inicial
"""

from __future__ import annotations

import sys
from pathlib import Path

DIRECTORIO_VERSIONES = Path(__file__).resolve().parents[1] / "alembic" / "versions"
MARCA = "PARCHE_MIGRACION_INICIAL_APLICADO"

# El delimitador de PL/pgSQL se escribe con un marcador y se sustituye al
# final, para que no interfiera con el formateo de este archivo.
DELIMITADOR = "LANG_BLOCK"

DEFINICIONES_SQL = f'''
# ---------------------------------------------------------------------------
#  {MARCA}
#
#  Sentencias que Alembic no autogenera.  Anadidas por
#  `python -m herramientas.parchear_migracion_inicial`.
#  Si se regenera esta migracion, hay que volver a ejecutar esa herramienta.
# ---------------------------------------------------------------------------

SQL_CONFIGURACION_TEXTUAL = """
DO {DELIMITADOR}
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
{DELIMITADOR};
"""

# ---------------------------------------------------------------------------
#  Calculo de `cita.fin`
# ---------------------------------------------------------------------------
# No puede ser una columna generada: PostgreSQL exige que la expresion sea
# IMMUTABLE y `timestamptz + interval` es solo STABLE, porque la aritmetica de
# meses y dias depende de la zona horaria de la sesion.
#
# Con un disparador BEFORE el calculo sigue estando en el motor: un camino de
# codigo que olvidara el tiempo de preparacion no puede producir un rango
# incorrecto, porque el disparador lo sobrescribe.  Los disparadores BEFORE se
# ejecutan antes de comprobar NOT NULL, asi que la aplicacion puede insertar
# sin dar valor a `fin`.
SQL_FUNCION_CALCULAR_FIN = """
CREATE OR REPLACE FUNCTION cita_calcular_fin()
RETURNS trigger AS {DELIMITADOR}
BEGIN
    NEW.fin := NEW.inicio
        + make_interval(mins => NEW.duracion_minutos + NEW.minutos_preparacion);
    RETURN NEW;
END;
{DELIMITADOR} LANGUAGE plpgsql;
"""

SQL_TRIGGER_CALCULAR_FIN = """
CREATE TRIGGER cita_fin_calculado
  BEFORE INSERT OR UPDATE OF inicio, duracion_minutos, minutos_preparacion
  ON cita
  FOR EACH ROW EXECUTE FUNCTION cita_calcular_fin();
"""

# ---------------------------------------------------------------------------
#  Verificacion del anti doble reserva (ADR-0009)
# ---------------------------------------------------------------------------
# Las restricciones las crea `op.create_table`, no este parche.  Aqui solo se
# comprueba que EXISTAN de verdad en el esquema resultante.
#
# El motivo: son la unica garantia real contra la doble reserva, y una
# version anterior del modelo hizo que Alembic dejara de generarlas sin dar
# ningun aviso.  Una migracion que termina "bien" y deja el sistema sin esa
# proteccion es el peor resultado posible, porque el fallo aparece meses
# despues con dos pacientes citados a la misma hora.
SQL_VERIFICAR_EXCLUSIONES = """
DO LANG_BLOCK
DECLARE
    faltantes text;
BEGIN
    SELECT string_agg(esperada, ', ')
      INTO faltantes
      FROM (
        VALUES ('cita_sin_solape_profesional'), ('cita_sin_solape_consultorio')
      ) AS r(esperada)
     WHERE NOT EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conname = r.esperada
           AND contype = 'x'
     );

    IF faltantes IS NOT NULL THEN
        RAISE EXCEPTION
            'Faltan restricciones de exclusion: %. Son la unica garantia '
            'contra la doble reserva (ADR-0009). Revise que el modelo de '
            'Cita conserve sus ExcludeConstraint y regenere la migracion.',
            faltantes;
    END IF;
END
LANG_BLOCK;
"""

# ---------------------------------------------------------------------------
#  Tablas de solo insercion
# ---------------------------------------------------------------------------
# Se aplica con disparador y no solo revocando privilegios.  Revocar UPDATE y
# DELETE al rol de la aplicacion es la defensa correcta en produccion, pero
# exige un rol distinto del propietario del esquema, lo que depende del
# despliegue.  El disparador funciona en cualquier configuracion, incluida la
# local, donde la aplicacion suele conectarse como propietaria.
SQL_FUNCION_SOLO_INSERCION = """
CREATE OR REPLACE FUNCTION tabla_solo_insercion()
RETURNS trigger AS {DELIMITADOR}
BEGIN
    RAISE EXCEPTION
        'La tabla % es de solo insercion: % no esta permitido. Para corregir '
        'un registro erroneo, inserte una entrada nueva que lo aclare.',
        TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
{DELIMITADOR} LANGUAGE plpgsql;
"""

SQL_TRIGGER_AUDITORIA = """
CREATE TRIGGER auditoria_sin_modificacion
  BEFORE UPDATE OR DELETE ON auditoria
  FOR EACH ROW EXECUTE FUNCTION tabla_solo_insercion();
"""

SQL_TRIGGER_CITA_HISTORIAL = """
CREATE TRIGGER cita_historial_sin_modificacion
  BEFORE UPDATE OR DELETE ON cita_historial
  FOR EACH ROW EXECUTE FUNCTION tabla_solo_insercion();
"""

'''

BLOQUE_EXTENSIONES = """def upgrade() -> None:
    # =======================================================================
    #  Extensiones
    # =======================================================================
    #  Se crean AQUI, no solo en el script de inicializacion del contenedor.
    #  Ese script es exclusivo del entorno local: una instancia gestionada de
    #  PostgreSQL nunca lo ejecuta.  Sin `btree_gist` la restriccion de
    #  exclusion no se puede crear y la migracion fallaria a mitad.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(SQL_CONFIGURACION_TEXTUAL)

"""

BLOQUE_FINAL = """    # =======================================================================
    #  Calculo de cita.fin  (ver la nota junto a SQL_FUNCION_CALCULAR_FIN)
    # =======================================================================
    op.execute(SQL_FUNCION_CALCULAR_FIN)
    op.execute(SQL_TRIGGER_CALCULAR_FIN)

    # Rellena `fin` en las filas que ya existieran.  En la migracion inicial
    # la tabla esta vacia, pero deja la sentencia por si se reordena.
    op.execute(
        "UPDATE cita SET fin = inicio "
        "+ make_interval(mins => duracion_minutos + minutos_preparacion) "
        "WHERE fin IS NULL"
    )

    # =======================================================================
    #  Verificacion del anti doble reserva (ADR-0009)
    # =======================================================================
    #  Las crea `op.create_table`; aqui se comprueba que existan.  Si no
    #  estan, la migracion falla en lugar de dejar el sistema sin proteccion.
    op.execute(SQL_VERIFICAR_EXCLUSIONES)

    # =======================================================================
    #  Tablas de solo insercion
    # =======================================================================
    op.execute(SQL_FUNCION_SOLO_INSERCION)
    op.execute(SQL_TRIGGER_AUDITORIA)
    op.execute(SQL_TRIGGER_CITA_HISTORIAL)

    # ### end Alembic commands ###
"""

BLOQUE_DOWNGRADE = """def downgrade() -> None:
    # Se deshace primero lo anadido a mano, en orden inverso.
    op.execute(
        "DROP TRIGGER IF EXISTS cita_historial_sin_modificacion ON cita_historial"
    )
    op.execute("DROP TRIGGER IF EXISTS auditoria_sin_modificacion ON auditoria")
    op.execute("DROP FUNCTION IF EXISTS tabla_solo_insercion()")
    # Las restricciones de exclusion no se sueltan aqui: las elimina el
    # `op.drop_table("cita")` que genera Alembic mas abajo.
    op.execute("DROP TRIGGER IF EXISTS cita_fin_calculado ON cita")
    op.execute("DROP FUNCTION IF EXISTS cita_calcular_fin()")

    # Las extensiones NO se eliminan a proposito: otras bases de datos del
    # mismo servidor podrian estar usandolas, y `DROP EXTENSION ... CASCADE`
    # borraria sus indices y columnas.  Dejarlas instaladas no tiene coste.

"""


def localizar_migracion_inicial() -> Path:
    """Devuelve la migracion cuyo `down_revision` es None."""
    candidatas = [
        ruta
        for ruta in DIRECTORIO_VERSIONES.glob("*.py")
        if "down_revision: str | None = None" in ruta.read_text(encoding="utf-8")
    ]
    if len(candidatas) != 1:
        raise SystemExit(
            f"Se esperaba exactamente una migracion inicial, hay {len(candidatas)}: "
            f"{[c.name for c in candidatas]}"
        )
    return candidatas[0]


def main() -> int:
    ruta = localizar_migracion_inicial()
    texto = ruta.read_text(encoding="utf-8")

    if MARCA in texto:
        print(f"{ruta.name}: ya parcheada; no se toca.")
        return 0

    marcador_upgrade = "def upgrade() -> None:\n"
    if texto.count(marcador_upgrade) != 1:
        raise SystemExit("No se encontro un unico `def upgrade`")

    # 1. Constantes SQL antes de `def upgrade`
    texto = texto.replace(marcador_upgrade, DEFINICIONES_SQL + marcador_upgrade, 1)
    # 2. Extensiones al inicio de upgrade
    texto = texto.replace(marcador_upgrade, BLOQUE_EXTENSIONES, 1)
    # 3. Disparadores y exclusiones al final de upgrade
    cierre = "    # ### end Alembic commands ###\n"
    indice = texto.index(cierre)
    texto = texto[:indice] + BLOQUE_FINAL + texto[indice + len(cierre) :]
    # 4. Reverso en downgrade
    texto = texto.replace("def downgrade() -> None:\n", BLOQUE_DOWNGRADE, 1)
    # 5. Delimitador real de PL/pgSQL
    texto = texto.replace(DELIMITADOR, "$" + "$")

    ruta.write_text(texto, encoding="utf-8")
    print(f"{ruta.name}: parcheada ({len(texto.splitlines())} lineas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
