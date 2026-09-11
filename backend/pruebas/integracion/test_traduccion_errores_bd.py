"""Verifica que los errores del motor se traduzcan a mensajes utiles.

Estas pruebas provocan violaciones **reales** en PostgreSQL y comprueban la
traduccion.  Construir excepciones falsas no serviria: el punto de la prueba
es que el nombre de la restriccion y el SQLSTATE que el driver expone de
verdad sean los que el traductor sabe reconocer.

Es el complemento necesario de la restriccion de exclusion: sin traduccion, la
garantia funciona pero el paciente recibe un error 500 en lugar de «ese turno
ya no esta disponible».

La clasificacion pura (que codigos son reintentables, que se traduce a que) se
prueba sin base de datos en `pruebas/unitarias/test_errores_bd.py`.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.nucleo.errores import (
    ClaveIdempotenciaConflictiva,
    ReglaNegocioViolada,
    TurnoNoDisponible,
)
from app.nucleo.errores_bd import (
    SQLSTATE_VIOLACION_EXCLUSION,
    extraer_nombre_restriccion,
    extraer_sqlstate,
    traducir,
)

pytestmark = [pytest.mark.integracion, pytest.mark.seguridad, pytest.mark.asyncio]


async def _provocar(sesion: AsyncSession, sql: str, parametros: dict[str, object]):
    """Ejecuta SQL que debe fallar y devuelve la excepcion."""
    try:
        await sesion.execute(sa.text(sql), parametros)
        await sesion.flush()
    except SQLAlchemyError as exc:
        return exc
    pytest.fail("Se esperaba un error de base de datos y no se produjo.")


class TestTraduccionDeSolapamiento:
    async def test_el_solapamiento_se_traduce_a_turno_no_disponible(
        self, sesion, clinica, sede, paciente, segundo_paciente, profesional, servicio, manana
    ) -> None:
        """El mensaje debe ser comprensible para un paciente.

        Un `IntegrityError` sin traducir produce un 500; traducido, produce un
        409 con un texto que el paciente entiende y que le dice que hacer.
        """
        plantilla = (
            "INSERT INTO cita (clinica_id, sede_id, paciente_id, profesional_id, "
            "servicio_id, inicio, duracion_minutos, minutos_preparacion, estado, origen) "
            "VALUES (:clinica, :sede, :paciente, :profesional, :servicio, :inicio, "
            "30, 0, 'CONFIRMED', 'PANEL')"
        )
        comunes = {
            "clinica": clinica.id,
            "sede": sede.id,
            "profesional": profesional.id,
            "servicio": servicio.id,
            "inicio": manana,
        }
        await sesion.execute(sa.text(plantilla), {**comunes, "paciente": paciente.id})
        await sesion.flush()

        excepcion = await _provocar(sesion, plantilla, {**comunes, "paciente": segundo_paciente.id})

        assert extraer_sqlstate(excepcion) == SQLSTATE_VIOLACION_EXCLUSION
        assert extraer_nombre_restriccion(excepcion) == "cita_sin_solape_profesional"

        traducido = traducir(excepcion)
        assert isinstance(traducido, TurnoNoDisponible)
        assert traducido.codigo == "TURNO_NO_DISPONIBLE"
        assert traducido.estado_http == 409
        # El mensaje debe hablarle al paciente, no describir la restriccion.
        assert "disponible" in traducido.mensaje.lower()
        assert "gist" not in traducido.mensaje.lower()
        assert "constraint" not in traducido.mensaje.lower()

    async def test_el_solapamiento_de_consultorio_se_distingue(
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
        """Sala ocupada y profesional ocupado son problemas distintos.

        Al usuario le sirven mensajes distintos: uno se resuelve cambiando de
        sala y el otro cambiando de hora.
        """
        otro = (
            await sesion.execute(
                sa.text(
                    "INSERT INTO profesional (clinica_id, especialidad_id, nombre, "
                    "apellido, numero_registro_profesional, estado_disponibilidad, "
                    "acepta_pacientes_nuevos, minutos_preparacion_propio, activo) "
                    "VALUES (:clinica, :esp, 'Otro', 'De Prueba', :registro, "
                    "'DISPONIBLE', true, 0, true) RETURNING id"
                ),
                {"clinica": clinica.id, "esp": especialidad.id, "registro": f"T-{sufijo}"},
            )
        ).scalar_one()

        plantilla = (
            "INSERT INTO cita (clinica_id, sede_id, consultorio_id, paciente_id, "
            "profesional_id, servicio_id, inicio, duracion_minutos, "
            "minutos_preparacion, estado, origen) "
            "VALUES (:clinica, :sede, :consultorio, :paciente, :profesional, "
            ":servicio, :inicio, 30, 0, 'CONFIRMED', 'PANEL')"
        )
        comunes = {
            "clinica": clinica.id,
            "sede": sede.id,
            "consultorio": consultorio.id,
            "servicio": servicio.id,
            "inicio": manana,
        }
        await sesion.execute(
            sa.text(plantilla),
            {**comunes, "paciente": paciente.id, "profesional": profesional.id},
        )
        await sesion.flush()

        excepcion = await _provocar(
            sesion,
            plantilla,
            {**comunes, "paciente": segundo_paciente.id, "profesional": otro},
        )
        traducido = traducir(excepcion)
        assert isinstance(traducido, TurnoNoDisponible)
        assert "consultorio" in traducido.mensaje.lower()


class TestTraduccionDeIdempotencia:
    async def test_la_clave_repetida_se_traduce(
        self, sesion, clinica, sede, paciente, segundo_paciente, profesional, servicio, manana
    ) -> None:
        clave = f"idem-trad-{manana.timestamp()}"
        plantilla = (
            "INSERT INTO cita (clinica_id, sede_id, paciente_id, profesional_id, "
            "servicio_id, inicio, duracion_minutos, minutos_preparacion, estado, "
            "origen, clave_idempotencia) "
            "VALUES (:clinica, :sede, :paciente, :profesional, :servicio, :inicio, "
            "30, 0, 'CONFIRMED', 'WHATSAPP', :clave)"
        )
        comunes = {
            "clinica": clinica.id,
            "sede": sede.id,
            "profesional": profesional.id,
            "servicio": servicio.id,
            "clave": clave,
        }
        await sesion.execute(
            sa.text(plantilla),
            {**comunes, "paciente": paciente.id, "inicio": manana},
        )
        await sesion.flush()

        excepcion = await _provocar(
            sesion,
            plantilla,
            {
                **comunes,
                "paciente": segundo_paciente.id,
                # Hora distinta: el rechazo debe venir de la clave, no del solape.
                "inicio": manana + timedelta(hours=5),
            },
        )
        traducido = traducir(excepcion)
        assert isinstance(traducido, ClaveIdempotenciaConflictiva)
        assert "ya fue procesada" in traducido.mensaje.lower()


class TestTraduccionDeReglasDeNegocio:
    @pytest.mark.parametrize(
        ("columna", "valor", "fragmento_esperado"),
        [
            ("duracion_minutos", 0, "mayor que cero"),
            ("estado", "'HELD'", "expiracion"),
        ],
    )
    async def test_las_comprobaciones_check_se_traducen(
        self,
        sesion,
        clinica,
        sede,
        paciente,
        profesional,
        servicio,
        manana,
        columna: str,
        valor: object,
        fragmento_esperado: str,
    ) -> None:
        """Una violacion de `CHECK` debe explicar la regla, no el SQL."""
        duracion = valor if columna == "duracion_minutos" else 30
        estado = valor if columna == "estado" else "'CONFIRMED'"
        excepcion = await _provocar(
            sesion,
            "INSERT INTO cita (clinica_id, sede_id, paciente_id, profesional_id, "
            "servicio_id, inicio, duracion_minutos, minutos_preparacion, estado, origen) "
            f"VALUES (:clinica, :sede, :paciente, :profesional, :servicio, :inicio, "
            f"{duracion}, 0, {estado}, 'PANEL')",
            {
                "clinica": clinica.id,
                "sede": sede.id,
                "paciente": paciente.id,
                "profesional": profesional.id,
                "servicio": servicio.id,
                "inicio": manana,
            },
        )
        traducido = traducir(excepcion)
        assert isinstance(traducido, ReglaNegocioViolada)
        assert fragmento_esperado in traducido.mensaje.lower()
