"""Capa de acceso a base de datos.

Reglas que se aplican aqui y no se negocian en los modulos:

* **Nunca SQL compuesto por concatenacion de cadenas.**  Todo pasa por
  SQLAlchemy con parametros enlazados, o por `text()` con parametros
  nombrados.  Es la defensa contra inyeccion SQL, y se verifica con una
  prueba que recorre el arbol de sintaxis buscando `text()` con f-strings.

* **La sesion se abre por peticion y se cierra siempre.**  Una sesion
  filtrada retiene una conexion del pool y acaba agotandolo bajo carga.

* **Una transaccion por operacion de negocio.**  El servicio decide el limite
  transaccional; el repositorio nunca hace `commit`.  Esto es lo que permite
  que el cambio de estado de una cita y su entrada en el outbox se confirmen
  juntos o no se confirmen (ADR-0008).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime, Uuid

# ---------------------------------------------------------------------------
#  Convencion de nombres de restricciones
# ---------------------------------------------------------------------------
# Sin esta convencion, Alembic genera nombres automaticos distintos en cada
# entorno y `downgrade` falla porque no encuentra la restriccion que quiere
# borrar.  Es la causa mas comun de migraciones irreversibles, y el requisito
# RNF-11 exige que sean reversibles.
CONVENCION_NOMBRES: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadatos = MetaData(naming_convention=CONVENCION_NOMBRES)


class Base(DeclarativeBase):
    """Base declarativa de todos los modelos."""

    metadata = metadatos

    type_annotation_map = {  # noqa: RUF012
        uuid.UUID: Uuid(as_uuid=True),
        datetime: DateTime(timezone=True),
    }


class MezclaIdentificador:
    """Clave primaria UUID generada por la base de datos.

    Se usa UUID y no un entero autoincremental porque los identificadores
    aparecen en URLs y en mensajes de WhatsApp: un secuencial permitiria
    enumerar pacientes probando numeros consecutivos.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


class MezclaAuditoria:
    """Columnas de trazabilidad presentes en toda tabla mutable.

    `creado_por` y `actualizado_por` no llevan clave externa a `usuario` a
    proposito: un actor puede ser el sistema o el agente de IA, que no son
    filas de `usuario`, y una clave externa obligaria a crear usuarios
    ficticios para representarlos.
    """

    creado_en: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )
    creado_por: Mapped[uuid.UUID | None] = mapped_column(default=None)
    actualizado_en: Mapped[datetime | None] = mapped_column(
        onupdate=func.now(),
        default=None,
    )
    actualizado_por: Mapped[uuid.UUID | None] = mapped_column(default=None)


class MezclaAnulacion:
    """Borrado logico.

    En este sistema no existe `DELETE` para entidades con valor historico: se
    anula con motivo.  Borrar una cita destruiria la trazabilidad de por que
    un paciente no fue atendido.
    """

    anulado_en: Mapped[datetime | None] = mapped_column(default=None)
    anulado_por: Mapped[uuid.UUID | None] = mapped_column(default=None)
    motivo_anulacion: Mapped[str | None] = mapped_column(default=None)

    @property
    def esta_anulado(self) -> bool:
        return self.anulado_en is not None


# ---------------------------------------------------------------------------
#  Motor y sesiones
# ---------------------------------------------------------------------------
class GestorBaseDatos:
    """Ciclo de vida del motor y de las sesiones.

    Se encapsula en una clase en lugar de usar variables de modulo para que
    las pruebas puedan crear instancias independientes contra la base de
    pruebas sin tocar estado global.
    """

    def __init__(
        self,
        url: str,
        *,
        tamano_pool: int = 10,
        desborde_maximo: int = 20,
        eco: bool = False,
        usar_pool: bool = True,
    ) -> None:
        argumentos: dict[str, Any] = {
            "echo": eco,
            # Comprueba la conexion antes de usarla.  Sin esto, una conexion
            # que el servidor cerro por tiempo de inactividad produce un error
            # en la primera consulta tras un periodo de calma.
            "pool_pre_ping": True,
            "connect_args": {
                # Tiempo limite de conexion explicito.
                #
                # Sin el, un host inalcanzable no produce un error: el intento
                # se queda colgado de forma indefinida y el proceso parece
                # arrancar sin terminar nunca.  Es exactamente lo que ocurria
                # al resolver "localhost" a ::1 en Windows.  Un fallo visible
                # en 10 segundos es mucho mejor que un bloqueo silencioso.
                "timeout": 10,
                # Desactiva la cache de sentencias preparadas de asyncpg.
                # Es necesario si alguna vez se pone un pooler en modo
                # transaccion delante; con ella, las sentencias preparadas se
                # invalidan y aparecen errores intermitentes.
                "statement_cache_size": 0,
                "server_settings": {
                    # Toda sesion trabaja en UTC (ADR-0010).  No se confia en
                    # la zona horaria del servidor ni del contenedor.
                    "timezone": "UTC",
                    "application_name": "clinica-backend",
                },
            },
        }

        if usar_pool:
            argumentos["pool_size"] = tamano_pool
            argumentos["max_overflow"] = desborde_maximo
            argumentos["pool_recycle"] = 1800
        else:
            # Las pruebas usan NullPool: cada prueba abre y cierra su
            # conexion, de modo que una prueba no hereda estado de otra.
            argumentos["poolclass"] = NullPool

        self._motor: AsyncEngine = create_async_engine(url, **argumentos)
        self._fabrica: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self._motor,
            expire_on_commit=False,
            autoflush=False,
        )

    @property
    def motor(self) -> AsyncEngine:
        return self._motor

    async def sesion(self) -> AsyncIterator[AsyncSession]:
        """Sesion por peticion, cerrada siempre.

        No hace `commit` automatico: el limite transaccional lo decide el
        servicio.  Si la peticion termina con una transaccion abierta, se
        deshace, que es el comportamiento seguro ante un error no controlado.
        """
        sesion = self._fabrica()
        try:
            yield sesion
        except Exception:
            await sesion.rollback()
            raise
        finally:
            await sesion.close()

    async def comprobar_salud(self) -> bool:
        """Comprobacion de salud real.

        No se limita a abrir una conexion: verifica que las extensiones
        criticas existan.  Un PostgreSQL sano sin `vector` o sin `btree_gist`
        no puede indexar conocimiento ni impedir la doble reserva, asi que no
        esta sano para este sistema.
        """
        async with self._motor.connect() as conexion:
            resultado = await conexion.execute(
                text(
                    "SELECT extname FROM pg_extension "
                    "WHERE extname IN ('vector', 'btree_gist', 'pg_trgm', 'pgcrypto')"
                )
            )
            presentes = {fila[0] for fila in resultado}
        return presentes >= {"vector", "btree_gist", "pg_trgm", "pgcrypto"}

    async def extensiones_faltantes(self) -> set[str]:
        requeridas = {"vector", "btree_gist", "pg_trgm", "pgcrypto", "unaccent"}
        async with self._motor.connect() as conexion:
            resultado = await conexion.execute(text("SELECT extname FROM pg_extension"))
            presentes = {fila[0] for fila in resultado}
        return requeridas - presentes

    async def cerrar(self) -> None:
        await self._motor.dispose()


# ---------------------------------------------------------------------------
#  Bloqueos consultivos
# ---------------------------------------------------------------------------
async def tomar_bloqueo_consultivo(sesion: AsyncSession, *, espacio: int, clave: str) -> None:
    """Toma un bloqueo consultivo de PostgreSQL para la transaccion actual.

    Se usa donde el conflicto es sobre algo que todavia no es una fila y por
    tanto no hay restriccion que lo proteja: sobre todo la aceptacion de una
    oferta de lista de espera, donde dos pacientes pueden responder en el
    mismo instante.

    `pg_advisory_xact_lock` se libera solo al terminar la transaccion, con
    commit o con rollback.  Eso descarta la clase de fallo mas peligrosa de
    los bloqueos: quedarse tomado para siempre porque el proceso murio antes
    de liberarlo.

    La clave de texto se reduce a un entero de 64 bits con `hashtext`.  Una
    colision solo produciria una serializacion innecesaria entre dos turnos
    distintos, no un error de correccion.
    """
    await sesion.execute(
        text("SELECT pg_advisory_xact_lock(:espacio, hashtext(:clave))"),
        {"espacio": espacio, "clave": clave},
    )


# Espacios de nombres de bloqueo.  Separarlos evita que dos usos distintos
# colisionen entre si.
ESPACIO_BLOQUEO_TURNO = 1
ESPACIO_BLOQUEO_OFERTA = 2
ESPACIO_BLOQUEO_OUTBOX = 3
ESPACIO_BLOQUEO_INGESTA = 4
