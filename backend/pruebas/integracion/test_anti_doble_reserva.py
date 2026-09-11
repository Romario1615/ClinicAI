"""Verifica la garantia central del sistema: no hay doble reserva.

Estas pruebas no comprueban el codigo de la aplicacion, comprueban el
**esquema**.  La pregunta que responden es: si el codigo tuviera un error,
¿la base de datos seguiria rechazando dos pacientes a la misma hora con el
mismo medico?

Por eso insertan directamente con SQLAlchemy, sin pasar por la capa de
servicios.  Si la proteccion dependiera de la logica de negocio, estas
pruebas pasarian y el sistema seguiria siendo vulnerable a cualquier camino
que la omitiera: una carga de datos, un script de correccion, una futura
funcion de importacion.

Ver ADR-0009.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modelos import (
    Cita,
    Consultorio,
    EstadoCita,
    Paciente,
    Profesional,
    Sede,
    Servicio,
)
from app.modulos.agenda.modelos import _ESTADOS_QUE_OCUPAN

pytestmark = [pytest.mark.integracion, pytest.mark.asyncio]


async def _crear_cita(
    sesion: AsyncSession,
    *,
    clinica_id: uuid.UUID,
    sede: Sede,
    paciente: Paciente,
    profesional: Profesional,
    servicio: Servicio,
    inicio: datetime,
    estado: EstadoCita = EstadoCita.CONFIRMED,
    consultorio: Consultorio | None = None,
    duracion_minutos: int = 30,
    minutos_preparacion: int = 0,
) -> Cita:
    """Inserta una cita directamente, sin pasar por la capa de servicios."""
    cita = Cita(
        clinica_id=clinica_id,
        sede_id=sede.id,
        consultorio_id=consultorio.id if consultorio else None,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        servicio_id=servicio.id,
        inicio=inicio,
        duracion_minutos=duracion_minutos,
        minutos_preparacion=minutos_preparacion,
        estado=estado.value,
        motivo_cancelacion=("Motivo de prueba" if estado is EstadoCita.CANCELLED else None),
        expira_en=(inicio + timedelta(minutes=10) if estado is EstadoCita.HELD else None),
    )
    sesion.add(cita)
    await sesion.flush()
    return cita


class TestDisparadorDeFin:
    """El motor calcula `fin` y `rango`; la aplicacion no puede equivocarse."""

    async def test_fin_se_calcula_con_duracion_y_preparacion(
        self, sesion, clinica, sede, paciente, profesional, servicio, manana
    ) -> None:
        cita = await _crear_cita(
            sesion,
            clinica_id=clinica.id,
            sede=sede,
            paciente=paciente,
            profesional=profesional,
            servicio=servicio,
            inicio=manana,
            duracion_minutos=30,
            minutos_preparacion=10,
        )
        await sesion.refresh(cita)
        # 30 de consulta + 10 de preparacion = 40 minutos ocupados.
        assert cita.fin == manana + timedelta(minutes=40)

    async def test_el_rango_deriva_de_inicio_y_fin(
        self, sesion, clinica, sede, paciente, profesional, servicio, manana
    ) -> None:
        cita = await _crear_cita(
            sesion,
            clinica_id=clinica.id,
            sede=sede,
            paciente=paciente,
            profesional=profesional,
            servicio=servicio,
            inicio=manana,
            duracion_minutos=45,
            minutos_preparacion=15,
        )
        resultado = await sesion.execute(
            sa.text("SELECT lower(rango), upper(rango), upper_inc(rango) FROM cita WHERE id = :id"),
            {"id": cita.id},
        )
        inferior, superior, incluye_superior = resultado.one()
        assert inferior == manana
        assert superior == manana + timedelta(minutes=60)
        # El rango es semiabierto '[)': dos citas consecutivas no se solapan.
        # Con '[]' una cita que termina a las 10:00 y otra que empieza a las
        # 10:00 colisionarian y la agenda perderia un turno por hueco.
        assert incluye_superior is False

    async def test_la_aplicacion_no_puede_falsear_el_fin(
        self, sesion, clinica, sede, paciente, profesional, servicio, manana
    ) -> None:
        """Un `fin` incorrecto enviado por la aplicacion se sobrescribe.

        Es lo que hace que la proteccion no dependa del codigo: aunque un
        camino olvidara el buffer de preparacion, el disparador recalcula.
        """
        cita = Cita(
            clinica_id=clinica.id,
            sede_id=sede.id,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            servicio_id=servicio.id,
            inicio=manana,
            duracion_minutos=30,
            minutos_preparacion=10,
            # Valor deliberadamente incorrecto: solo 5 minutos.
            fin=manana + timedelta(minutes=5),
            estado=EstadoCita.CONFIRMED.value,
        )
        sesion.add(cita)
        await sesion.flush()
        await sesion.refresh(cita)
        assert cita.fin == manana + timedelta(minutes=40), (
            "El disparador debe recalcular `fin` e ignorar el valor recibido."
        )

    async def test_el_fin_se_recalcula_al_cambiar_la_duracion(
        self, sesion, clinica, sede, paciente, profesional, servicio, manana
    ) -> None:
        cita = await _crear_cita(
            sesion,
            clinica_id=clinica.id,
            sede=sede,
            paciente=paciente,
            profesional=profesional,
            servicio=servicio,
            inicio=manana,
            duracion_minutos=30,
        )
        cita.duracion_minutos = 60
        await sesion.flush()
        await sesion.refresh(cita)
        assert cita.fin == manana + timedelta(minutes=60)


class TestSolapamientoPorProfesional:
    """Un profesional no puede tener dos citas activas solapadas."""

    async def test_solapamiento_exacto_se_rechaza(
        self,
        sesion,
        clinica,
        sede,
        paciente,
        segundo_paciente,
        profesional,
        servicio,
        manana,
    ) -> None:
        await _crear_cita(
            sesion,
            clinica_id=clinica.id,
            sede=sede,
            paciente=paciente,
            profesional=profesional,
            servicio=servicio,
            inicio=manana,
        )
        with pytest.raises(IntegrityError) as excinfo:
            await _crear_cita(
                sesion,
                clinica_id=clinica.id,
                sede=sede,
                paciente=segundo_paciente,
                profesional=profesional,
                servicio=servicio,
                inicio=manana,
            )
        assert "cita_sin_solape_profesional" in str(excinfo.value)

    @pytest.mark.parametrize(
        ("desplazamiento_minutos", "descripcion"),
        [
            (10, "la segunda empieza dentro de la primera"),
            (-10, "la primera empieza dentro de la segunda"),
            (29, "se solapan por un minuto"),
            (-29, "se solapan por un minuto, al reves"),
        ],
    )
    async def test_solapamientos_parciales_se_rechazan(
        self,
        sesion,
        clinica,
        sede,
        paciente,
        segundo_paciente,
        profesional,
        servicio,
        manana,
        desplazamiento_minutos: int,
        descripcion: str,
    ) -> None:
        await _crear_cita(
            sesion,
            clinica_id=clinica.id,
            sede=sede,
            paciente=paciente,
            profesional=profesional,
            servicio=servicio,
            inicio=manana,
            duracion_minutos=30,
        )
        with pytest.raises(IntegrityError, match="cita_sin_solape_profesional"):
            await _crear_cita(
                sesion,
                clinica_id=clinica.id,
                sede=sede,
                paciente=segundo_paciente,
                profesional=profesional,
                servicio=servicio,
                inicio=manana + timedelta(minutes=desplazamiento_minutos),
                duracion_minutos=30,
            )

    async def test_citas_consecutivas_se_aceptan(
        self,
        sesion,
        clinica,
        sede,
        paciente,
        segundo_paciente,
        profesional,
        servicio,
        manana,
    ) -> None:
        """Una cita que empieza cuando acaba la anterior NO se solapa.

        Es la consecuencia del rango semiabierto.  Si se rechazara, la agenda
        perderia un turno entre cada par de citas.
        """
        await _crear_cita(
            sesion,
            clinica_id=clinica.id,
            sede=sede,
            paciente=paciente,
            profesional=profesional,
            servicio=servicio,
            inicio=manana,
            duracion_minutos=30,
            minutos_preparacion=0,
        )
        # Debe poder insertarse sin error.
        await _crear_cita(
            sesion,
            clinica_id=clinica.id,
            sede=sede,
            paciente=segundo_paciente,
            profesional=profesional,
            servicio=servicio,
            inicio=manana + timedelta(minutes=30),
            duracion_minutos=30,
        )

    async def test_el_buffer_de_preparacion_bloquea_el_turno_siguiente(
        self,
        sesion,
        clinica,
        sede,
        paciente,
        segundo_paciente,
        profesional,
        servicio,
        manana,
    ) -> None:
        """El tiempo de preparacion tambien esta protegido por el motor.

        Si el buffer viviera solo en el codigo, un camino que lo olvidara
        produciria citas pegadas sin margen para limpiar la sala.
        """
        await _crear_cita(
            sesion,
            clinica_id=clinica.id,
            sede=sede,
            paciente=paciente,
            profesional=profesional,
            servicio=servicio,
            inicio=manana,
            duracion_minutos=30,
            minutos_preparacion=15,
        )
        # A los 30 minutos la consulta acabo, pero el buffer llega hasta los 45.
        with pytest.raises(IntegrityError, match="cita_sin_solape_profesional"):
            await _crear_cita(
                sesion,
                clinica_id=clinica.id,
                sede=sede,
                paciente=segundo_paciente,
                profesional=profesional,
                servicio=servicio,
                inicio=manana + timedelta(minutes=30),
                duracion_minutos=30,
            )

    async def test_profesionales_distintos_a_la_misma_hora_se_aceptan(
        self,
        sesion,
        clinica,
        sede,
        especialidad,
        paciente,
        segundo_paciente,
        profesional,
        servicio,
        manana,
        sufijo,
    ) -> None:
        otro = Profesional(
            clinica_id=clinica.id,
            especialidad_id=especialidad.id,
            nombre="Otro Profesional",
            apellido="De Prueba",
            numero_registro_profesional=f"REG2-{sufijo}",
        )
        sesion.add(otro)
        await sesion.flush()

        await _crear_cita(
            sesion,
            clinica_id=clinica.id,
            sede=sede,
            paciente=paciente,
            profesional=profesional,
            servicio=servicio,
            inicio=manana,
        )
        await _crear_cita(
            sesion,
            clinica_id=clinica.id,
            sede=sede,
            paciente=segundo_paciente,
            profesional=otro,
            servicio=servicio,
            inicio=manana,
        )


class TestEstadosQueNoOcupanTurno:
    """El historico se conserva sin bloquear el horario."""

    @pytest.mark.parametrize(
        "estado", [EstadoCita.CANCELLED, EstadoCita.COMPLETED, EstadoCita.NO_SHOW]
    )
    async def test_un_estado_terminal_libera_el_turno(
        self,
        sesion,
        clinica,
        sede,
        paciente,
        segundo_paciente,
        profesional,
        servicio,
        manana,
        estado: EstadoCita,
    ) -> None:
        """Una cita cancelada no impide reasignar su turno.

        Es lo que hace posible la lista de espera: el turno queda libre pero
        la fila permanece, con su motivo, para poder explicar despues por que
        el paciente no fue atendido.
        """
        await _crear_cita(
            sesion,
            clinica_id=clinica.id,
            sede=sede,
            paciente=paciente,
            profesional=profesional,
            servicio=servicio,
            inicio=manana,
            estado=estado,
        )
        # El mismo turno debe poder asignarse a otra persona.
        await _crear_cita(
            sesion,
            clinica_id=clinica.id,
            sede=sede,
            paciente=segundo_paciente,
            profesional=profesional,
            servicio=servicio,
            inicio=manana,
            estado=EstadoCita.CONFIRMED,
        )

    @pytest.mark.parametrize(
        "estado", [EstadoCita.HELD, EstadoCita.CONFIRMED, EstadoCita.RESCHEDULED]
    )
    async def test_un_estado_activo_bloquea_el_turno(
        self,
        sesion,
        clinica,
        sede,
        paciente,
        segundo_paciente,
        profesional,
        servicio,
        manana,
        estado: EstadoCita,
    ) -> None:
        """Un bloqueo temporal cuenta igual que una cita confirmada.

        Si HELD no bloqueara, dos pacientes podrian avanzar en paralelo hasta
        el paso de confirmacion y uno de los dos se llevaria un rechazo tras
        haber creido reservar.
        """
        await _crear_cita(
            sesion,
            clinica_id=clinica.id,
            sede=sede,
            paciente=paciente,
            profesional=profesional,
            servicio=servicio,
            inicio=manana,
            estado=estado,
        )
        with pytest.raises(IntegrityError, match="cita_sin_solape_profesional"):
            await _crear_cita(
                sesion,
                clinica_id=clinica.id,
                sede=sede,
                paciente=segundo_paciente,
                profesional=profesional,
                servicio=servicio,
                inicio=manana,
                estado=EstadoCita.CONFIRMED,
            )

    async def test_los_estados_del_codigo_y_del_esquema_coinciden(self, sesion) -> None:
        """El conjunto de estados que ocupan turno debe ser el mismo en ambos.

        Si el codigo y la clausula WHERE de la restriccion divergieran, la
        aplicacion creeria que un estado bloquea el turno cuando la base de
        datos ya lo ha liberado, o al contrario.  Esta prueba lee la
        definicion real de la restriccion.
        """
        resultado = await sesion.execute(
            sa.text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'cita_sin_solape_profesional'"
            )
        )
        definicion = resultado.scalar_one()
        for estado in _ESTADOS_QUE_OCUPAN:
            assert f"'{estado.value}'" in definicion, (
                f"El estado {estado.value} ocupa turno segun el codigo, pero no "
                f"aparece en la restriccion: {definicion}"
            )


class TestSolapamientoPorConsultorio:
    """Dos profesionales no pueden ocupar la misma sala a la vez."""

    async def test_mismo_consultorio_se_rechaza(
        self,
        sesion,
        clinica,
        sede,
        consultorio,
        especialidad,
        paciente,
        segundo_paciente,
        profesional,
        servicio,
        manana,
        sufijo,
    ) -> None:
        otro = Profesional(
            clinica_id=clinica.id,
            especialidad_id=especialidad.id,
            nombre="Otro Profesional",
            apellido="De Prueba",
            numero_registro_profesional=f"REG3-{sufijo}",
        )
        sesion.add(otro)
        await sesion.flush()

        await _crear_cita(
            sesion,
            clinica_id=clinica.id,
            sede=sede,
            consultorio=consultorio,
            paciente=paciente,
            profesional=profesional,
            servicio=servicio,
            inicio=manana,
        )
        with pytest.raises(IntegrityError, match="cita_sin_solape_consultorio"):
            await _crear_cita(
                sesion,
                clinica_id=clinica.id,
                sede=sede,
                consultorio=consultorio,
                paciente=segundo_paciente,
                profesional=otro,
                servicio=servicio,
                inicio=manana,
            )

    async def test_sin_consultorio_no_hay_conflicto_de_sala(
        self,
        sesion,
        clinica,
        sede,
        especialidad,
        paciente,
        segundo_paciente,
        profesional,
        servicio,
        manana,
        sufijo,
    ) -> None:
        """Las citas sin consultorio asignado no colisionan entre si.

        La clausula `consultorio_id IS NOT NULL` de la restriccion existe por
        esto: sin ella, todas las citas sin sala asignada colisionarian y la
        agenda quedaria limitada a una cita simultanea en toda la clinica.
        """
        otro = Profesional(
            clinica_id=clinica.id,
            especialidad_id=especialidad.id,
            nombre="Otro Profesional",
            apellido="De Prueba",
            numero_registro_profesional=f"REG4-{sufijo}",
        )
        sesion.add(otro)
        await sesion.flush()

        await _crear_cita(
            sesion,
            clinica_id=clinica.id,
            sede=sede,
            paciente=paciente,
            profesional=profesional,
            servicio=servicio,
            inicio=manana,
        )
        await _crear_cita(
            sesion,
            clinica_id=clinica.id,
            sede=sede,
            paciente=segundo_paciente,
            profesional=otro,
            servicio=servicio,
            inicio=manana,
        )


class TestRestriccionesDeCoherencia:
    async def test_held_exige_fecha_de_expiracion(
        self, sesion, clinica, sede, paciente, profesional, servicio, manana
    ) -> None:
        """Un bloqueo sin caducidad retendria el turno para siempre."""
        cita = Cita(
            clinica_id=clinica.id,
            sede_id=sede.id,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            servicio_id=servicio.id,
            inicio=manana,
            duracion_minutos=30,
            estado=EstadoCita.HELD.value,
            expira_en=None,
        )
        sesion.add(cita)
        with pytest.raises(IntegrityError, match="held_exige_expiracion"):
            await sesion.flush()

    async def test_cancelacion_exige_motivo(
        self, sesion, clinica, sede, paciente, profesional, servicio, manana
    ) -> None:
        """Sin motivo no se puede explicar despues por que no fue atendido."""
        cita = Cita(
            clinica_id=clinica.id,
            sede_id=sede.id,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            servicio_id=servicio.id,
            inicio=manana,
            duracion_minutos=30,
            estado=EstadoCita.CANCELLED.value,
            motivo_cancelacion=None,
        )
        sesion.add(cita)
        with pytest.raises(IntegrityError, match="cancelacion_exige_motivo"):
            await sesion.flush()

    async def test_duracion_debe_ser_positiva(
        self, sesion, clinica, sede, paciente, profesional, servicio, manana
    ) -> None:
        cita = Cita(
            clinica_id=clinica.id,
            sede_id=sede.id,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            servicio_id=servicio.id,
            inicio=manana,
            duracion_minutos=0,
            estado=EstadoCita.CONFIRMED.value,
        )
        sesion.add(cita)
        with pytest.raises(IntegrityError, match="duracion_positiva"):
            await sesion.flush()

    async def test_la_clave_de_idempotencia_es_unica_por_clinica(
        self,
        sesion,
        clinica,
        sede,
        paciente,
        segundo_paciente,
        profesional,
        servicio,
        manana,
    ) -> None:
        """La misma clave no puede crear dos citas.

        Es lo que impide que un doble clic o un reintento de webhook
        produzcan dos citas.
        """
        clave = f"idem-{uuid.uuid4().hex[:12]}"
        cita = await _crear_cita(
            sesion,
            clinica_id=clinica.id,
            sede=sede,
            paciente=paciente,
            profesional=profesional,
            servicio=servicio,
            inicio=manana,
        )
        cita.clave_idempotencia = clave
        await sesion.flush()

        otra = Cita(
            clinica_id=clinica.id,
            sede_id=sede.id,
            paciente_id=segundo_paciente.id,
            profesional_id=profesional.id,
            servicio_id=servicio.id,
            # Horario distinto para que no choque con la exclusion y se vea
            # que el rechazo viene de la clave de idempotencia.
            inicio=manana + timedelta(hours=3),
            duracion_minutos=30,
            estado=EstadoCita.CONFIRMED.value,
            clave_idempotencia=clave,
        )
        sesion.add(otra)
        with pytest.raises(IntegrityError, match="ix_cita_idempotencia"):
            await sesion.flush()


class TestTablasDeSoloInsercion:
    """La auditoria y el historial de citas no se pueden alterar."""

    async def test_la_auditoria_no_admite_modificacion(self, sesion) -> None:
        resultado = await sesion.execute(
            sa.text(
                "INSERT INTO auditoria (accion, actor_tipo, resultado, origen) "
                "VALUES ('login.exitoso', 'USUARIO', 'EXITO', 'API') RETURNING id"
            )
        )
        identificador = resultado.scalar_one()

        with pytest.raises(Exception, match="solo insercion"):
            await sesion.execute(
                sa.text("UPDATE auditoria SET resultado = 'DENEGADO' WHERE id = :id"),
                {"id": identificador},
            )

    async def test_la_auditoria_no_admite_borrado(self, sesion) -> None:
        resultado = await sesion.execute(
            sa.text(
                "INSERT INTO auditoria (accion, actor_tipo, resultado, origen) "
                "VALUES ('login.fallido', 'USUARIO', 'DENEGADO', 'API') RETURNING id"
            )
        )
        identificador = resultado.scalar_one()

        with pytest.raises(Exception, match="solo insercion"):
            await sesion.execute(
                sa.text("DELETE FROM auditoria WHERE id = :id"), {"id": identificador}
            )
