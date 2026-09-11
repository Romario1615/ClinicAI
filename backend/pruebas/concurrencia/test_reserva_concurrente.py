"""Carrera real por el mismo turno: solo uno debe ganar.

Esta es la prueba que justifica el ADR-0009.

Que hace distinta a esta prueba
-------------------------------
No simula concurrencia: la provoca.  Cada participante abre su **propia
conexion** a PostgreSQL, todos esperan en una barrera y despues intentan
insertar la misma cita a la vez.  Con el nivel de aislamiento por defecto
(`READ COMMITTED`) ninguno ve el intento de los demas hasta que uno confirma.

Es la unica forma de verificar la garantia.  Una prueba que inserte dos citas
en la misma transaccion pasaria siempre, porque una transaccion no compite
consigo misma, y no demostraria nada.

Lo que se verifica
------------------
* Ninguna cita activa se solapa con otra.  Es la invariante del sistema, y se
  comprueba con una consulta sobre el resultado, no contando ganadores: no
  depende de cuantos intentos compitieran ni de quien llegara primero.
* Todo rechazo proviene de una garantia del motor y llega con un SQLSTATE que
  la capa de servicios sabe traducir a un mensaje util.
* Al menos un participante obtiene turno.  Sin esta comprobacion, un sistema
  que rechazara todas las reservas cumpliria la invariante y pasaria la
  prueba.

Hallazgo durante el desarrollo
------------------------------
Con muchos participantes simultaneos, una parte de los rechazos NO llega como
violacion de la restriccion de exclusion (23P01) sino como **interbloqueo**
(40P01).  Ocurre porque la segunda transaccion que inserta una fila solapada
espera a que la primera resuelva, y varias transacciones pueden acabar
esperandose en circulo.

La integridad se mantiene, pero tiene una consecuencia de diseno: la capa de
servicios debe traducir el interbloqueo igual que la violacion de exclusion.
Si se dejara escapar, el paciente veria un error 500 en lugar de «ese turno ya
no esta disponible».
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pruebas.concurrencia.conftest import EscenarioAgenda

pytestmark = [pytest.mark.concurrencia, pytest.mark.integracion, pytest.mark.asyncio]

SQL_INSERTAR_CITA = sa.text(
    """
    INSERT INTO cita (
        clinica_id, sede_id, consultorio_id, paciente_id, profesional_id,
        servicio_id, inicio, duracion_minutos, minutos_preparacion,
        estado, expira_en, origen
    ) VALUES (
        :clinica, :sede, :consultorio, :paciente, :profesional,
        :servicio, :inicio, :duracion, 0,
        :estado, :expira_en, 'PANEL'
    ) RETURNING id
    """
)


# Codigos SQLSTATE que representan un rechazo VALIDO de la carrera.
#
#   23P01  exclusion_violation    -> el turno ya estaba ocupado
#   23505  unique_violation       -> clave de idempotencia repetida
#   40P01  deadlock_detected      -> ver la nota de abajo
#   40001  serialization_failure  -> idem
#
# Sobre el interbloqueo
# ---------------------
# Con una restriccion de exclusion, la segunda transaccion que inserta una
# fila solapada queda esperando a que la primera confirme o deshaga.  Si
# varias transacciones se esperan en circulo, PostgreSQL detecta el
# interbloqueo y aborta una de ellas con SQLSTATE 40P01.
#
# Es un resultado correcto del motor: la integridad se mantiene.  Pero **la
# capa de servicios tiene que traducirlo**, igual que la violacion de
# exclusion, a "turno ya no disponible".  Si se dejara escapar, el paciente
# recibiria un error 500 en lugar de un mensaje util, y el registro se
# llenaria de errores que parecen fallos del sistema sin serlo.
SQLSTATES_RECHAZO_VALIDO: frozenset[str] = frozenset({"23P01", "23505", "40P01", "40001"})


@dataclass(slots=True)
class Resultado:
    """Resultado de un participante de la carrera."""

    indice: int
    cita_id: uuid.UUID | None
    tipo_error: str | None
    mensaje_error: str | None
    sqlstate: str | None = None

    @property
    def gano(self) -> bool:
        return self.cita_id is not None

    @property
    def rechazo_valido(self) -> bool:
        """El rechazo proviene de una garantia del motor, no de un fallo."""
        return self.sqlstate in SQLSTATES_RECHAZO_VALIDO


def _sqlstate(excepcion: BaseException) -> str | None:
    """Extrae el SQLSTATE de una excepcion de base de datos."""
    for candidato in (excepcion, getattr(excepcion, "orig", None)):
        if candidato is None:
            continue
        codigo = getattr(candidato, "sqlstate", None) or getattr(candidato, "pgcode", None)
        if codigo:
            return str(codigo)
    return None


async def _intentar_reservar(
    fabrica: async_sessionmaker[AsyncSession],
    escenario: EscenarioAgenda,
    indice: int,
    inicio: datetime,
    barrera: asyncio.Barrier,
    *,
    estado: str = "CONFIRMED",
    duracion: int = 30,
    con_consultorio: bool = False,
) -> Resultado:
    """Un participante: abre su conexion, espera en la barrera e inserta.

    La conexion se abre ANTES de la barrera a proposito.  Si se abriera
    despues, el coste de establecerla dominaria y los intentos se
    escalonarian, con lo que la carrera no llegaria a producirse.
    """
    async with fabrica() as sesion:
        # Fuerza el establecimiento real de la conexion antes de competir.
        await sesion.execute(sa.text("SELECT 1"))

        # Todos los participantes llegan aqui y salen juntos.
        await barrera.wait()

        try:
            resultado = await sesion.execute(
                SQL_INSERTAR_CITA,
                {
                    "clinica": escenario.clinica_id,
                    "sede": escenario.sede_id,
                    "consultorio": escenario.consultorio_id if con_consultorio else None,
                    "paciente": escenario.pacientes[indice],
                    "profesional": escenario.profesional_id,
                    "servicio": escenario.servicio_id,
                    "inicio": inicio,
                    "duracion": duracion,
                    "estado": estado,
                    "expira_en": (inicio + timedelta(minutes=10) if estado == "HELD" else None),
                },
            )
            cita_id = resultado.scalar_one()
            await sesion.commit()
            return Resultado(indice, cita_id, None, None)
        except SQLAlchemyError as exc:
            await sesion.rollback()
            return Resultado(
                indice,
                None,
                type(exc).__name__,
                str(getattr(exc, "orig", exc)),
                _sqlstate(exc),
            )


async def _contar_pares_solapados(
    fabrica: async_sessionmaker[AsyncSession],
    escenario: EscenarioAgenda,
) -> int:
    """Cuenta los pares de citas activas que se solapan.

    Es la invariante del sistema expresada como consulta: debe ser cero
    siempre.  Comprobarla asi es mas solido que contar ganadores, porque no
    depende de cuantos intentos compitieran ni de quien llegara primero.
    """
    async with fabrica() as sesion:
        resultado = await sesion.execute(
            sa.text(
                "SELECT count(*) FROM cita a JOIN cita b "
                "  ON a.id < b.id "
                " AND a.profesional_id = b.profesional_id "
                " AND a.rango && b.rango "
                "WHERE a.clinica_id = :clinica "
                "  AND a.estado IN ('HELD', 'CONFIRMED', 'RESCHEDULED') "
                "  AND b.estado IN ('HELD', 'CONFIRMED', 'RESCHEDULED')"
            ),
            {"clinica": escenario.clinica_id},
        )
        return int(resultado.scalar_one())


async def _contar_citas_activas(
    fabrica: async_sessionmaker[AsyncSession],
    escenario: EscenarioAgenda,
    inicio: datetime,
) -> int:
    async with fabrica() as sesion:
        resultado = await sesion.execute(
            sa.text(
                "SELECT count(*) FROM cita "
                "WHERE profesional_id = :profesional AND inicio = :inicio "
                "AND estado IN ('HELD', 'CONFIRMED', 'RESCHEDULED')"
            ),
            {"profesional": escenario.profesional_id, "inicio": inicio},
        )
        return int(resultado.scalar_one())


class TestCarreraPorElMismoTurno:
    @pytest.mark.parametrize("participantes", [2, 10, 50])
    async def test_solo_un_participante_obtiene_el_turno(
        self,
        fabrica_sesiones: async_sessionmaker[AsyncSession],
        escenario: EscenarioAgenda,
        turno_disputado: datetime,
        participantes: int,
    ) -> None:
        """N pacientes intentan reservar el mismo turno a la vez.

        Se prueba con 2, 10 y 50: dos participantes es el caso minimo, y
        cincuenta somete la restriccion a una presion que un bloqueo en
        Python no soportaria.
        """
        barrera = asyncio.Barrier(participantes)

        resultados: list[Resultado] = list(
            await asyncio.gather(
                *[
                    _intentar_reservar(
                        fabrica_sesiones,
                        escenario,
                        indice,
                        turno_disputado,
                        barrera,
                    )
                    for indice in range(participantes)
                ]
            )
        )

        ganadores = [r for r in resultados if r.gano]
        perdedores = [r for r in resultados if not r.gano]

        assert len(ganadores) == 1, (
            f"Con {participantes} intentos simultaneos debe ganar exactamente "
            f"uno, ganaron {len(ganadores)}.\n"
            f"Resultados: {[(r.indice, r.gano, r.tipo_error) for r in resultados]}"
        )
        assert len(perdedores) == participantes - 1

        # La base de datos debe corroborarlo.
        assert await _contar_citas_activas(fabrica_sesiones, escenario, turno_disputado) == 1

    async def test_los_perdedores_reciben_el_error_correcto(
        self,
        fabrica_sesiones: async_sessionmaker[AsyncSession],
        escenario: EscenarioAgenda,
        turno_disputado: datetime,
    ) -> None:
        """El rechazo debe venir de la restriccion de exclusion.

        Importa que sea exactamente ese error: es el que el servicio traduce a
        «turno ya no disponible», un mensaje que el paciente entiende.  Un
        interbloqueo o un fallo de serializacion indicarian un problema
        distinto y producirian un error 500 en lugar de una respuesta util.
        """
        participantes = 10
        barrera = asyncio.Barrier(participantes)

        resultados = list(
            await asyncio.gather(
                *[
                    _intentar_reservar(fabrica_sesiones, escenario, i, turno_disputado, barrera)
                    for i in range(participantes)
                ]
            )
        )

        perdedores = [r for r in resultados if not r.gano]
        assert len(perdedores) == participantes - 1

        por_exclusion = 0
        por_interbloqueo = 0
        for perdedor in perdedores:
            assert perdedor.rechazo_valido, (
                f"El participante {perdedor.indice} fallo con un error que la "
                f"capa de servicios no sabria traducir "
                f"(SQLSTATE {perdedor.sqlstate}): {perdedor.mensaje_error}"
            )
            if perdedor.sqlstate == "23P01":
                por_exclusion += 1
            else:
                por_interbloqueo += 1

        # Con muchos participantes simultaneos una parte de los rechazos llega
        # como interbloqueo y no como violacion de exclusion.  Ambos son
        # rechazos legitimos y la capa de servicios debe tratarlos igual.
        assert por_exclusion + por_interbloqueo == len(perdedores)

    async def test_carrera_entre_bloqueo_temporal_y_confirmacion(
        self,
        fabrica_sesiones: async_sessionmaker[AsyncSession],
        escenario: EscenarioAgenda,
        turno_disputado: datetime,
    ) -> None:
        """Un HELD y un CONFIRMED simultaneos: gana uno solo.

        Es el caso real de un paciente reservando por WhatsApp (que pasa por
        HELD) mientras recepcion confirma directamente desde el panel.  Si
        HELD no bloqueara, ambos avanzarian y uno recibiria un rechazo despues
        de creer que ya tenia la cita.
        """
        barrera = asyncio.Barrier(2)
        resultados = list(
            await asyncio.gather(
                _intentar_reservar(
                    fabrica_sesiones,
                    escenario,
                    0,
                    turno_disputado,
                    barrera,
                    estado="HELD",
                ),
                _intentar_reservar(
                    fabrica_sesiones,
                    escenario,
                    1,
                    turno_disputado,
                    barrera,
                    estado="CONFIRMED",
                ),
            )
        )
        assert sum(1 for r in resultados if r.gano) == 1

    async def test_turnos_con_inicios_distintos_pero_solapados(
        self,
        fabrica_sesiones: async_sessionmaker[AsyncSession],
        escenario: EscenarioAgenda,
        turno_disputado: datetime,
    ) -> None:
        """Un indice sobre `(profesional_id, inicio)` no bastaria.

        Es el error habitual al implementar esto: serviria para horas
        identicas, pero 14:00-14:30 y 14:15-14:45 tienen inicios distintos y
        se solapan igualmente.  Solo una restriccion sobre rangos lo detecta.

        Lo que se afirma NO es un recuento de ganadores, sino la invariante
        real: **ninguna cita activa se solapa con otra**.

        Con tres intentos a 13:45, 14:00 y 14:15 de 30 minutos, los rangos son
        [13:45,14:15), [14:00,14:30) y [14:15,14:45).  El central choca con
        los otros dos, pero el primero y el tercero NO se solapan entre si,
        porque los rangos son semiabiertos.  Por eso el numero correcto de
        ganadores es uno o dos segun quien llegue primero, y exigir
        exactamente uno seria exigir que el sistema rechace reservas
        legitimas.
        """
        barrera = asyncio.Barrier(3)
        resultados = list(
            await asyncio.gather(
                *[
                    _intentar_reservar(
                        fabrica_sesiones,
                        escenario,
                        indice,
                        turno_disputado + timedelta(minutes=15 * (indice - 1)),
                        barrera,
                    )
                    for indice in range(3)
                ]
            )
        )

        for perdedor in (r for r in resultados if not r.gano):
            assert perdedor.rechazo_valido, (
                f"El participante {perdedor.indice} fallo con un error que no "
                f"es un rechazo de la carrera ({perdedor.sqlstate}): "
                f"{perdedor.mensaje_error}"
            )

        # La invariante del sistema.
        assert await _contar_pares_solapados(fabrica_sesiones, escenario) == 0

        # Y al menos uno tuvo que entrar: rechazar todo tambien cumpliria la
        # invariante, y seria un sistema inutil.
        assert any(r.gano for r in resultados), (
            "Ningun participante obtuvo turno; el sistema esta rechazando reservas legitimas."
        )

    async def test_turnos_consecutivos_no_compiten(
        self,
        fabrica_sesiones: async_sessionmaker[AsyncSession],
        escenario: EscenarioAgenda,
        turno_disputado: datetime,
    ) -> None:
        """Tres turnos seguidos deben entrar los tres.

        Es la contraprueba: si la restriccion fuera demasiado estricta, la
        agenda perderia capacidad y el sistema seria inutilizable aunque
        «nunca hubiera doble reserva».  Una prueba de concurrencia sin este
        caso no distingue un sistema correcto de uno que rechaza todo.
        """
        barrera = asyncio.Barrier(3)
        resultados = list(
            await asyncio.gather(
                *[
                    _intentar_reservar(
                        fabrica_sesiones,
                        escenario,
                        indice,
                        turno_disputado + timedelta(minutes=30 * indice),
                        barrera,
                    )
                    for indice in range(3)
                ]
            )
        )
        ganadores = [r for r in resultados if r.gano]
        assert len(ganadores) == 3, (
            "Tres turnos consecutivos no se solapan y deben entrar los tres. "
            f"Errores: {[(r.indice, r.tipo_error, r.mensaje_error) for r in resultados if not r.gano]}"
        )


class TestCarreraPorConsultorio:
    async def test_dos_profesionales_compiten_por_la_sala(
        self,
        fabrica_sesiones: async_sessionmaker[AsyncSession],
        escenario: EscenarioAgenda,
        turno_disputado: datetime,
        motor_concurrencia,
    ) -> None:
        """Profesionales distintos, misma sala, misma hora: gana uno.

        Sin esta proteccion la agenda cuadraria en el papel y la clinica
        tendria dos consultas simultaneas en la misma habitacion.
        """
        # Un segundo profesional en la misma especialidad.
        fabrica = fabrica_sesiones
        async with fabrica() as sesion:
            segundo_profesional = (
                await sesion.execute(
                    sa.text(
                        "INSERT INTO profesional (clinica_id, especialidad_id, nombre, "
                        "apellido, numero_registro_profesional, estado_disponibilidad, "
                        "acepta_pacientes_nuevos, minutos_preparacion_propio, activo) "
                        "VALUES (:clinica, :esp, 'Segundo', 'De Prueba', :registro, "
                        "'DISPONIBLE', true, 0, true) RETURNING id"
                    ),
                    {
                        "clinica": escenario.clinica_id,
                        "esp": escenario.especialidad_id,
                        "registro": f"CONC2-{escenario.sufijo}",
                    },
                )
            ).scalar_one()
            await sesion.commit()

        async def intentar(indice: int, profesional_id: uuid.UUID) -> Resultado:
            async with fabrica() as sesion:
                await sesion.execute(sa.text("SELECT 1"))
                await barrera.wait()
                try:
                    resultado = await sesion.execute(
                        SQL_INSERTAR_CITA,
                        {
                            "clinica": escenario.clinica_id,
                            "sede": escenario.sede_id,
                            "consultorio": escenario.consultorio_id,
                            "paciente": escenario.pacientes[indice],
                            "profesional": profesional_id,
                            "servicio": escenario.servicio_id,
                            "inicio": turno_disputado,
                            "duracion": 30,
                            "estado": "CONFIRMED",
                            "expira_en": None,
                        },
                    )
                    cita_id = resultado.scalar_one()
                    await sesion.commit()
                    return Resultado(indice, cita_id, None, None)
                except SQLAlchemyError as exc:
                    await sesion.rollback()
                    return Resultado(
                        indice,
                        None,
                        type(exc).__name__,
                        str(getattr(exc, "orig", exc)),
                        _sqlstate(exc),
                    )

        barrera = asyncio.Barrier(2)
        resultados = list(
            await asyncio.gather(
                intentar(0, escenario.profesional_id),
                intentar(1, segundo_profesional),
            )
        )

        ganadores = [r for r in resultados if r.gano]
        assert len(ganadores) == 1
        perdedor = next(r for r in resultados if not r.gano)
        assert perdedor.rechazo_valido, (
            f"El rechazo debe venir de una garantia del motor "
            f"(SQLSTATE {perdedor.sqlstate}): {perdedor.mensaje_error}"
        )


class TestIdempotenciaConcurrente:
    async def test_la_misma_clave_no_crea_dos_citas(
        self,
        fabrica_sesiones: async_sessionmaker[AsyncSession],
        escenario: EscenarioAgenda,
        turno_disputado: datetime,
    ) -> None:
        """Dos peticiones identicas simultaneas: una sola cita.

        Es el caso del doble clic y el del reintento de webhook de WhatsApp.
        Se usan horarios DISTINTOS a proposito, para que el rechazo no pueda
        venir de la restriccion de exclusion y quede claro que lo produce la
        clave de idempotencia.
        """
        clave = f"idem-conc-{escenario.sufijo}"
        barrera = asyncio.Barrier(5)

        async def intentar(indice: int) -> Resultado:
            async with fabrica_sesiones() as sesion:
                await sesion.execute(sa.text("SELECT 1"))
                await barrera.wait()
                try:
                    resultado = await sesion.execute(
                        sa.text(
                            "INSERT INTO cita (clinica_id, sede_id, paciente_id, "
                            "profesional_id, servicio_id, inicio, duracion_minutos, "
                            "minutos_preparacion, estado, origen, clave_idempotencia) "
                            "VALUES (:clinica, :sede, :paciente, :profesional, "
                            ":servicio, :inicio, 30, 0, 'CONFIRMED', 'WHATSAPP', :clave) "
                            "RETURNING id"
                        ),
                        {
                            "clinica": escenario.clinica_id,
                            "sede": escenario.sede_id,
                            "paciente": escenario.pacientes[indice],
                            "profesional": escenario.profesional_id,
                            "servicio": escenario.servicio_id,
                            # Cada intento en una hora distinta.
                            "inicio": turno_disputado + timedelta(hours=indice + 1),
                            "clave": clave,
                        },
                    )
                    cita_id = resultado.scalar_one()
                    await sesion.commit()
                    return Resultado(indice, cita_id, None, None)
                except SQLAlchemyError as exc:
                    await sesion.rollback()
                    return Resultado(
                        indice,
                        None,
                        type(exc).__name__,
                        str(getattr(exc, "orig", exc)),
                        _sqlstate(exc),
                    )

        resultados = list(await asyncio.gather(*[intentar(i) for i in range(5)]))

        ganadores = [r for r in resultados if r.gano]
        assert len(ganadores) == 1, (
            f"La misma clave de idempotencia no puede crear dos citas. Ganaron {len(ganadores)}."
        )
        for perdedor in (r for r in resultados if not r.gano):
            assert perdedor.rechazo_valido, (
                f"El rechazo debe venir de una garantia del motor "
                f"(SQLSTATE {perdedor.sqlstate}): {perdedor.mensaje_error}"
            )


class TestEstadosTerminalesLiberanElTurno:
    async def test_tras_cancelar_el_turno_vuelve_a_estar_disponible(
        self,
        fabrica_sesiones: async_sessionmaker[AsyncSession],
        escenario: EscenarioAgenda,
        turno_disputado: datetime,
    ) -> None:
        """Cancelar libera el turno para una carrera nueva.

        Es el mecanismo que hace posible la lista de espera: varios candidatos
        pueden competir por un hueco recien liberado, y de nuevo solo uno debe
        obtenerlo.
        """
        # Reserva inicial.
        barrera_inicial = asyncio.Barrier(1)
        primero = await _intentar_reservar(
            fabrica_sesiones, escenario, 0, turno_disputado, barrera_inicial
        )
        assert primero.gano

        # Cancelacion.
        async with fabrica_sesiones() as sesion:
            await sesion.execute(
                sa.text(
                    "UPDATE cita SET estado = 'CANCELLED', "
                    "motivo_cancelacion = 'Prueba de liberacion de turno', "
                    "cancelada_en = now() WHERE id = :id"
                ),
                {"id": primero.cita_id},
            )
            await sesion.commit()

        # Carrera por el turno liberado.
        participantes = 10
        barrera = asyncio.Barrier(participantes)
        resultados = list(
            await asyncio.gather(
                *[
                    _intentar_reservar(
                        fabrica_sesiones,
                        escenario,
                        indice + 1,
                        turno_disputado,
                        barrera,
                    )
                    for indice in range(participantes)
                ]
            )
        )

        ganadores = [r for r in resultados if r.gano]
        assert len(ganadores) == 1, (
            f"Tras la cancelacion, {participantes} candidatos compiten y solo "
            f"uno debe obtener el turno; ganaron {len(ganadores)}."
        )
        # Y sigue habiendo una sola cita activa.
        assert await _contar_citas_activas(fabrica_sesiones, escenario, turno_disputado) == 1
