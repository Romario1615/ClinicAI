"""Fixtures de las pruebas de integracion.

Usan PostgreSQL y Redis **reales** en contenedores, no dobles de prueba.  El
motivo es concreto: lo que se verifica aqui son garantias del motor de base de
datos -- restricciones de exclusion, disparadores, indices unicos parciales,
aislamiento transaccional -- y un doble de prueba no las tiene.  Una suite que
sustituye PostgreSQL por SQLite prueba el codigo, no el sistema.

Aislamiento entre pruebas
-------------------------
Cada prueba corre dentro de una transaccion que se deshace al terminar.  Es
mas rapido que recrear el esquema y garantiza que el orden de ejecucion no
afecte al resultado.

La excepcion son las pruebas de concurrencia: necesitan varias conexiones
reales que se vean entre si, asi que usan sus propias sesiones y limpian
explicitamente.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.modelos import (
    Clinica,
    Consultorio,
    Especialidad,
    Paciente,
    Profesional,
    Sede,
    Servicio,
    Usuario,
)
from app.nucleo.configuracion import Configuracion
from app.nucleo.seguridad import hashear_contrasena

# Instante de referencia: miercoles laborable a media manana en Guayaquil.
INSTANTE_REFERENCIA = datetime(2026, 4, 15, 14, 0, 0, tzinfo=UTC)


def _configuracion_pruebas() -> Configuracion:
    """Configuracion apuntando a la base de datos de desarrollo local.

    Se usa la base de desarrollo y no la de pruebas del compose porque cada
    prueba se aisla con una transaccion que se deshace; no queda rastro.
    Para la suite completa en CI se levanta `docker-compose.test.yml`, que
    expone el puerto 5433, y se pasa por entorno.
    """
    return Configuracion()


@pytest.fixture(scope="session")
def configuracion() -> Configuracion:
    return _configuracion_pruebas()


@pytest.fixture(scope="session")
def url_bd(configuracion: Configuracion) -> str:
    return configuracion.url_base_datos


@pytest_asyncio.fixture(scope="session")
async def motor(url_bd: str) -> AsyncIterator[sa.ext.asyncio.AsyncEngine]:
    """Motor de sesion.

    Se comprueba al arrancar que el esquema este migrado.  Sin esta
    comprobacion, una suite sin migrar falla con errores de "tabla no existe"
    repartidos por todas las pruebas, que es mucho mas dificil de diagnosticar
    que un unico mensaje claro.
    """
    creado = create_async_engine(url_bd, poolclass=sa.pool.NullPool)

    async with creado.connect() as conexion:
        faltan = await conexion.run_sync(
            lambda sync_conn: [
                tabla
                for tabla in ("clinica", "cita", "paciente", "auditoria")
                if not sa.inspect(sync_conn).has_table(tabla)
            ]
        )
    if faltan:
        await creado.dispose()
        pytest.fail(
            f"El esquema no esta migrado; faltan tablas: {faltan}.\n"
            "Ejecute:  uv run alembic upgrade head",
            pytrace=False,
        )

    yield creado
    await creado.dispose()


@pytest_asyncio.fixture
async def sesion(
    motor: sa.ext.asyncio.AsyncEngine,
) -> AsyncIterator[AsyncSession]:
    """Sesion aislada: todo lo que haga la prueba se deshace al terminar.

    Se abre una transaccion externa sobre la conexion y la sesion se une a
    ella.  Aunque el codigo bajo prueba haga `commit`, ese commit solo
    confirma la transaccion interna; al deshacer la externa no queda nada.
    """
    async with motor.connect() as conexion:
        transaccion = await conexion.begin()
        fabrica = async_sessionmaker(
            bind=conexion, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        sesion_prueba = fabrica()
        try:
            yield sesion_prueba
        finally:
            await sesion_prueba.close()
            await transaccion.rollback()


# ---------------------------------------------------------------------------
#  Datos sinteticos minimos
# ---------------------------------------------------------------------------
# Nombres claramente ficticios.  NUNCA datos reales de pacientes (regla 6 de
# CLAUDE.md); el sufijo "de Prueba" lo hace evidente en cualquier volcado.
@pytest.fixture
def sufijo() -> str:
    """Sufijo unico para evitar colisiones de restricciones unicas."""
    return uuid.uuid4().hex[:8]


@pytest_asyncio.fixture
async def clinica(sesion: AsyncSession, sufijo: str) -> Clinica:
    registro = Clinica(
        nombre=f"Clinica de Prueba {sufijo}",
        identificacion_fiscal=f"PRUEBA-{sufijo}",
        zona_horaria="America/Guayaquil",
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


@pytest_asyncio.fixture
async def sede(sesion: AsyncSession, clinica: Clinica, sufijo: str) -> Sede:
    registro = Sede(
        clinica_id=clinica.id,
        nombre=f"Sede de Prueba {sufijo}",
        direccion="Calle Ficticia 123",
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


@pytest_asyncio.fixture
async def consultorio(sesion: AsyncSession, sede: Sede, sufijo: str) -> Consultorio:
    registro = Consultorio(sede_id=sede.id, nombre=f"Consultorio {sufijo}")
    sesion.add(registro)
    await sesion.flush()
    return registro


@pytest_asyncio.fixture
async def especialidad(sesion: AsyncSession, clinica: Clinica, sufijo: str) -> Especialidad:
    registro = Especialidad(clinica_id=clinica.id, nombre=f"Especialidad de Prueba {sufijo}")
    sesion.add(registro)
    await sesion.flush()
    return registro


@pytest_asyncio.fixture
async def servicio(
    sesion: AsyncSession, clinica: Clinica, especialidad: Especialidad, sufijo: str
) -> Servicio:
    registro = Servicio(
        clinica_id=clinica.id,
        especialidad_id=especialidad.id,
        nombre=f"Servicio de Prueba {sufijo}",
        duracion_minutos=30,
        minutos_preparacion=10,
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


@pytest_asyncio.fixture
async def usuario(sesion: AsyncSession, clinica: Clinica, sufijo: str) -> Usuario:
    registro = Usuario(
        clinica_id=clinica.id,
        correo=f"prueba-{sufijo}@example.invalid",
        hash_contrasena=hashear_contrasena("ContrasenaDePrueba123"),
        nombre="Usuario",
        apellido="De Prueba",
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


@pytest_asyncio.fixture
async def profesional(
    sesion: AsyncSession,
    clinica: Clinica,
    especialidad: Especialidad,
    usuario: Usuario,
    sufijo: str,
) -> Profesional:
    registro = Profesional(
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        especialidad_id=especialidad.id,
        nombre="Profesional",
        apellido="De Prueba",
        numero_registro_profesional=f"REG-{sufijo}",
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


@pytest_asyncio.fixture
async def paciente(sesion: AsyncSession, clinica: Clinica, sufijo: str) -> Paciente:
    registro = Paciente(
        clinica_id=clinica.id,
        tipo_documento="CEDULA",
        # Documento sintetico: no corresponde a ninguna cedula real.
        numero_documento=f"9{sufijo[:9]}",
        nombre="Paciente",
        apellido="De Prueba",
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


@pytest_asyncio.fixture
async def segundo_paciente(sesion: AsyncSession, clinica: Clinica, sufijo: str) -> Paciente:
    registro = Paciente(
        clinica_id=clinica.id,
        tipo_documento="CEDULA",
        numero_documento=f"8{sufijo[:9]}",
        nombre="Segundo Paciente",
        apellido="De Prueba",
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


@pytest.fixture
def instante() -> datetime:
    """Instante de referencia de las pruebas."""
    return INSTANTE_REFERENCIA


@pytest.fixture
def manana(instante: datetime) -> datetime:
    """Mismo momento del dia siguiente; evita colisiones con datos previos."""
    return instante + timedelta(days=1)


@pytest.fixture(autouse=True)
def _sin_aislamiento_de_entorno() -> Iterator[None]:
    """Anula el aislamiento de entorno de las pruebas unitarias.

    El `conftest.py` raiz borra las variables POSTGRES_* para que las pruebas
    unitarias de configuracion no dependan del .env del desarrollador.  Las de
    integracion necesitan justo lo contrario: la configuracion real, para
    saber a que base conectarse.
    """
    yield
