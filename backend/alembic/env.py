"""Entorno de Alembic.

Dos decisiones que evitan problemas conocidos:

1. **La URL viene de la configuracion de la aplicacion, no de alembic.ini.**
   Tener la cadena de conexion en un archivo versionado invita a que alguien
   escriba ahi una contrasena real.  `alembic.ini` no contiene ninguna URL.

2. **`compare_type` y `compare_server_default` activados.**  Sin ellos,
   Alembic no detecta un cambio de tipo ni de valor por defecto, y la
   migracion generada parece correcta mientras el esquema real se desvia del
   modelo.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Importar `app.modelos` puebla el metadata con TODAS las tablas.  Si faltara
# un modulo, autogenerate generaria una migracion que borra su tabla.
from app.modelos import Base
from app.nucleo.configuracion import Configuracion

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# La configuracion se lee del entorno, igual que la aplicacion.
_configuracion = Configuracion()  # type: ignore[call-arg]


def _url_base_datos() -> str:
    """URL sincrona: Alembic no usa el driver asincrono."""
    # Permite sobrescribirla al ejecutar contra la base de pruebas:
    #   alembic -x url=postgresql+psycopg://... upgrade head
    argumentos = context.get_x_argument(as_dictionary=True)
    if "url" in argumentos:
        return str(argumentos["url"])
    return _configuracion.url_base_datos_sincrona


def _incluir_objeto(
    objeto: object, nombre: str | None, tipo: str, reflejado: bool, comparar_con: object
) -> bool:
    """Filtra objetos que Alembic no debe gestionar.

    Las tablas internas de la extension `vector` y las de Alembic no forman
    parte del modelo y no deben aparecer en las migraciones.
    """
    del objeto, reflejado, comparar_con
    if tipo == "table" and nombre is not None:
        return not nombre.startswith(("pg_", "sql_", "alembic_"))
    return True


def ejecutar_migraciones_offline() -> None:
    """Genera el SQL sin conectarse.

    Util para revisar que hara una migracion en produccion antes de
    aplicarla, y para entregar el SQL a un administrador de base de datos.
    """
    context.configure(
        url=_url_base_datos(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=_incluir_objeto,
    )
    with context.begin_transaction():
        context.run_migrations()


def ejecutar_migraciones_online() -> None:
    """Aplica las migraciones contra la base de datos."""
    seccion = config.get_section(config.config_ini_section, {})
    seccion["sqlalchemy.url"] = _url_base_datos()

    motor = engine_from_config(
        seccion,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        # Tiempo limite explicito: sin el, un host inalcanzable deja a
        # `alembic upgrade` colgado en silencio, sin mensaje y sin salida,
        # que es la peor forma posible de fallar durante un despliegue.
        connect_args={"connect_timeout": 10},
    )

    with motor.connect() as conexion:
        context.configure(
            connection=conexion,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_object=_incluir_objeto,
            # Envuelve cada migracion en una transaccion: si falla a medias,
            # no deja el esquema en un estado intermedio.  PostgreSQL admite
            # DDL transaccional, asi que esto funciona de verdad.
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    ejecutar_migraciones_offline()
else:
    ejecutar_migraciones_online()
