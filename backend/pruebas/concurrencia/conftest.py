"""Fixtures de las pruebas de concurrencia.

Estas pruebas no pueden usar el aislamiento por transaccion del resto de la
suite.  El motivo es esencial: una transaccion no ve lo que hacen las otras
hasta que se confirman, asi que dos "peticiones" dentro de la misma
transaccion nunca competirian entre si y la prueba pasaria siempre sin
demostrar nada.

Aqui cada participante de la carrera abre su **propia conexion real** y
confirma de verdad.  A cambio hay que limpiar a mano lo que se cree, y por eso
todo lleva un sufijo unico y se borra al final.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.nucleo.configuracion import Configuracion

INSTANTE_REFERENCIA = datetime(2026, 4, 15, 14, 0, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class EscenarioAgenda:
    """Identificadores del escenario sintetico creado para una prueba."""

    clinica_id: uuid.UUID
    sede_id: uuid.UUID
    consultorio_id: uuid.UUID
    especialidad_id: uuid.UUID
    servicio_id: uuid.UUID
    profesional_id: uuid.UUID
    pacientes: tuple[uuid.UUID, ...]
    sufijo: str


@pytest.fixture(scope="session")
def configuracion_concurrencia() -> Configuracion:
    return Configuracion()


@pytest_asyncio.fixture
async def motor_concurrencia(
    configuracion_concurrencia: Configuracion,
) -> AsyncIterator[AsyncEngine]:
    """Motor con pool real, uno por prueba.

    A diferencia del motor de las pruebas de integracion, aqui SI hace falta
    un pool: las pruebas abren varias conexiones simultaneas y crear una
    conexion nueva por cada intento falsearia los tiempos de la carrera.

    El ambito es de FUNCION, no de sesion, aunque crear el pool en cada
    prueba cueste algo mas.  El motivo: pytest-asyncio abre un bucle de
    eventos nuevo por prueba, y un motor asincrono creado en el bucle de la
    primera prueba queda inservible en las siguientes.  El sintoma es un
    `RuntimeError: Event loop is closed` al cerrar las conexiones, que no
    tiene nada que ver con lo que la prueba estaba verificando.
    """
    motor = create_async_engine(
        configuracion_concurrencia.url_base_datos,
        pool_size=25,
        max_overflow=25,
        pool_pre_ping=True,
    )
    yield motor
    await motor.dispose()


@pytest_asyncio.fixture
async def fabrica_sesiones(
    motor_concurrencia: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Fabrica de sesiones independientes, cada una con su propia conexion."""
    return async_sessionmaker(bind=motor_concurrencia, expire_on_commit=False)


@pytest_asyncio.fixture
async def escenario(
    motor_concurrencia: AsyncEngine,
) -> AsyncIterator[EscenarioAgenda]:
    """Crea un escenario sintetico completo y lo borra al terminar.

    Se confirma de verdad (no hay transaccion envolvente) para que las
    conexiones concurrentes puedan verlo.  La limpieza va en `finally` y
    borra en orden inverso a las dependencias.

    Todos los nombres llevan "de Prueba" y un sufijo aleatorio: son datos
    sinteticos y deben ser reconocibles como tales en cualquier volcado
    (regla 6 de CLAUDE.md).
    """
    sufijo = uuid.uuid4().hex[:8]
    fabrica = async_sessionmaker(bind=motor_concurrencia, expire_on_commit=False)

    async with fabrica() as sesion:
        clinica_id = (
            await sesion.execute(
                sa.text(
                    "INSERT INTO clinica (nombre, identificacion_fiscal, zona_horaria, "
                    "idioma, moneda, activa) "
                    "VALUES (:nombre, :fiscal, 'America/Guayaquil', 'es', 'USD', true) "
                    "RETURNING id"
                ),
                {
                    "nombre": f"Clinica Concurrencia {sufijo}",
                    "fiscal": f"CONC-{sufijo}",
                },
            )
        ).scalar_one()

        sede_id = (
            await sesion.execute(
                sa.text(
                    "INSERT INTO sede (clinica_id, nombre, minutos_antelacion_minima, activa) "
                    "VALUES (:clinica, :nombre, 60, true) RETURNING id"
                ),
                {"clinica": clinica_id, "nombre": f"Sede Concurrencia {sufijo}"},
            )
        ).scalar_one()

        consultorio_id = (
            await sesion.execute(
                sa.text(
                    "INSERT INTO consultorio (sede_id, nombre, tipo, capacidad, activo) "
                    "VALUES (:sede, :nombre, 'CONSULTA', 1, true) RETURNING id"
                ),
                {"sede": sede_id, "nombre": f"Consultorio {sufijo}"},
            )
        ).scalar_one()

        especialidad_id = (
            await sesion.execute(
                sa.text(
                    "INSERT INTO especialidad (clinica_id, nombre, activa) "
                    "VALUES (:clinica, :nombre, true) RETURNING id"
                ),
                {"clinica": clinica_id, "nombre": f"Especialidad {sufijo}"},
            )
        ).scalar_one()

        servicio_id = (
            await sesion.execute(
                sa.text(
                    "INSERT INTO servicio (clinica_id, especialidad_id, nombre, "
                    "duracion_minutos, minutos_preparacion, moneda, "
                    "requiere_pago_previo, activo) "
                    "VALUES (:clinica, :esp, :nombre, 30, 0, 'USD', false, true) "
                    "RETURNING id"
                ),
                {
                    "clinica": clinica_id,
                    "esp": especialidad_id,
                    "nombre": f"Servicio {sufijo}",
                },
            )
        ).scalar_one()

        profesional_id = (
            await sesion.execute(
                sa.text(
                    "INSERT INTO profesional (clinica_id, especialidad_id, nombre, "
                    "apellido, numero_registro_profesional, estado_disponibilidad, "
                    "acepta_pacientes_nuevos, minutos_preparacion_propio, activo) "
                    "VALUES (:clinica, :esp, 'Profesional', 'De Prueba', :registro, "
                    "'DISPONIBLE', true, 0, true) RETURNING id"
                ),
                {
                    "clinica": clinica_id,
                    "esp": especialidad_id,
                    "registro": f"CONC-{sufijo}",
                },
            )
        ).scalar_one()

        # Varios pacientes: uno por participante de la carrera.
        pacientes: list[uuid.UUID] = []
        for indice in range(50):
            paciente_id = (
                await sesion.execute(
                    sa.text(
                        "INSERT INTO paciente (clinica_id, tipo_documento, "
                        "numero_documento, nombre, apellido, nivel_verificacion, activo) "
                        "VALUES (:clinica, 'CEDULA', :documento, :nombre, "
                        "'De Prueba', 'NO_VERIFICADO', true) RETURNING id"
                    ),
                    {
                        "clinica": clinica_id,
                        # Documento sintetico: no corresponde a ninguna cedula real.
                        "documento": f"9{sufijo}{indice:02d}",
                        "nombre": f"Paciente {indice}",
                    },
                )
            ).scalar_one()
            pacientes.append(paciente_id)

        await sesion.commit()

    datos = EscenarioAgenda(
        clinica_id=clinica_id,
        sede_id=sede_id,
        consultorio_id=consultorio_id,
        especialidad_id=especialidad_id,
        servicio_id=servicio_id,
        profesional_id=profesional_id,
        pacientes=tuple(pacientes),
        sufijo=sufijo,
    )

    try:
        yield datos
    finally:
        # Limpieza en orden inverso a las dependencias.  `cita_historial` y
        # `auditoria` no se borran: son de solo insercion y el disparador lo
        # impide, que es justo lo que se quiere.
        async with fabrica() as sesion:
            await sesion.execute(
                sa.text("DELETE FROM cita WHERE clinica_id = :clinica"),
                {"clinica": clinica_id},
            )
            await sesion.execute(
                sa.text("DELETE FROM paciente WHERE clinica_id = :clinica"),
                {"clinica": clinica_id},
            )
            await sesion.execute(
                sa.text("DELETE FROM profesional WHERE clinica_id = :clinica"),
                {"clinica": clinica_id},
            )
            await sesion.execute(
                sa.text("DELETE FROM servicio WHERE clinica_id = :clinica"),
                {"clinica": clinica_id},
            )
            await sesion.execute(
                sa.text("DELETE FROM consultorio WHERE sede_id = :sede"),
                {"sede": sede_id},
            )
            await sesion.execute(
                sa.text("DELETE FROM especialidad WHERE clinica_id = :clinica"),
                {"clinica": clinica_id},
            )
            await sesion.execute(
                sa.text("DELETE FROM sede WHERE clinica_id = :clinica"),
                {"clinica": clinica_id},
            )
            await sesion.execute(
                sa.text("DELETE FROM clinica WHERE id = :clinica"),
                {"clinica": clinica_id},
            )
            await sesion.commit()


@pytest.fixture
def turno_disputado() -> datetime:
    """El instante por el que compiten los participantes."""
    return INSTANTE_REFERENCIA
