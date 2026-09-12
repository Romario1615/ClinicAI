"""Dos pacientes aceptan la misma oferta a la vez.

Es la prueba que da sentido a la lista de espera. Si la carrera se resolviera
mal, el sistema le diria a dos personas que el turno es suyo y una se
presentaria a una cita que no existe.

Como se prueba de verdad
------------------------
Con **conexiones separadas** y una `asyncio.Barrier` que las suelta en el
mismo instante. No con dobles, no con mocks de transaccion: lo que se verifica
es el comportamiento del bloqueo consultivo y del indice unico parcial de
PostgreSQL, y ninguno de los dos existe en un doble de prueba.

Cada participante abre su propia sesion. Compartir una sesion produciria una
sola transaccion, y entonces no habria carrera que observar.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Importar `app.modelos` registra TODOS los modelos en el metadata. Sin
# esto, `profesional.usuario_id` apunta a una tabla `usuario` que el mapeador
# no conoce y la configuracion falla con `NoReferencedTableError`.
import app.modelos  # noqa: F401
from app.modulos.agenda.modelos import Cita, EstadoCita
from app.modulos.lista_espera.modelos import (
    EntradaListaEspera,
    EstadoEspera,
    EstadoOferta,
    OfertaTurno,
)
from app.modulos.lista_espera.servicios import ServicioListaEspera
from app.modulos.organizacion.modelos import Clinica, Especialidad, Sede, Servicio
from app.modulos.pacientes.modelos import Paciente
from app.modulos.profesionales.modelos import Profesional
from app.nucleo.autorizacion import Ambito, Principal, TipoActor
from app.nucleo.configuracion import Configuracion
from app.nucleo.errores import OfertaYaResuelta
from app.nucleo.reloj import RelojFijo

pytestmark = [pytest.mark.concurrencia, pytest.mark.asyncio]

AHORA = datetime(2026, 4, 15, 14, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def fabrica_sesiones() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Fabrica de sesiones INDEPENDIENTES.

    `NullPool` a proposito: cada participante abre y cierra su conexion, de
    modo que ninguno hereda estado transaccional de otro.
    """
    motor = create_async_engine(Configuracion().url_base_datos, poolclass=sa.pool.NullPool)
    yield async_sessionmaker(bind=motor, expire_on_commit=False)
    await motor.dispose()


@pytest_asyncio.fixture
async def escenario(
    fabrica_sesiones: async_sessionmaker[AsyncSession],
) -> AsyncIterator[dict[str, uuid.UUID]]:
    """Crea y confirma el escenario, y lo limpia al terminar.

    Se confirma de verdad -- no hay transaccion envolvente -- porque los
    participantes son conexiones distintas y no verian datos sin confirmar.
    La limpieza es explicita y va en orden inverso a las claves externas.
    """
    sufijo = uuid.uuid4().hex[:8]
    ids: dict[str, uuid.UUID] = {}

    async with fabrica_sesiones() as sesion, sesion.begin():
        clinica = Clinica(
            nombre=f"Clinica Concurrencia {sufijo}",
            identificacion_fiscal=f"PRUEBA-CONC-{sufijo}",
            zona_horaria="America/Guayaquil",
        )
        sesion.add(clinica)
        await sesion.flush()

        sede = Sede(clinica_id=clinica.id, nombre=f"Sede {sufijo}")
        especialidad = Especialidad(clinica_id=clinica.id, nombre=f"Especialidad {sufijo}")
        sesion.add_all([sede, especialidad])
        await sesion.flush()

        servicio = Servicio(
            clinica_id=clinica.id,
            especialidad_id=especialidad.id,
            nombre=f"Servicio {sufijo}",
            duracion_minutos=30,
            minutos_preparacion=15,
        )
        profesional = Profesional(
            clinica_id=clinica.id,
            especialidad_id=especialidad.id,
            nombre="Profesional",
            apellido="Concurrencia",
            numero_registro_profesional=f"REG-{sufijo}",
        )
        pacientes = [
            Paciente(
                clinica_id=clinica.id,
                tipo_documento="CEDULA",
                numero_documento=f"9{sufijo[:4]}{indice:04d}",
                nombre=f"Paciente{indice}",
                apellido="Concurrencia",
            )
            for indice in range(2)
        ]
        sesion.add_all([servicio, profesional, *pacientes])
        await sesion.flush()

        # Cita cancelada: es el turno que queda libre y se ofrece.
        liberada = Cita(
            clinica_id=clinica.id,
            sede_id=sede.id,
            paciente_id=pacientes[0].id,
            profesional_id=profesional.id,
            servicio_id=servicio.id,
            inicio=AHORA + timedelta(days=2),
            duracion_minutos=30,
            minutos_preparacion=15,
            estado=EstadoCita.CANCELLED.value,
            motivo_cancelacion="Liberada para la prueba",
            cancelada_en=AHORA,
        )
        sesion.add(liberada)
        await sesion.flush()

        # Dos personas esperando, con una oferta cada una sobre EL MISMO
        # turno. En produccion el indice unico parcial impide crear la
        # segunda; aqui se crean a proposito con estados distintos para poder
        # provocar la carrera de aceptacion.
        entradas = [
            EntradaListaEspera(
                clinica_id=clinica.id,
                paciente_id=paciente.id,
                sede_id=sede.id,
                especialidad_id=especialidad.id,
                servicio_id=servicio.id,
                estado=EstadoEspera.OFERTADA.value,
                horas_antelacion_minima=1,
            )
            for paciente in pacientes
        ]
        sesion.add_all(entradas)
        await sesion.flush()

        ofertas = [
            OfertaTurno(
                lista_espera_id=entrada.id,
                cita_liberada_id=liberada.id,
                # La primera OFRECIDA, la segunda tambien: el indice unico
                # parcial lo impediria, asi que se crea la segunda como
                # RECHAZADA y se cambia despues con SQL directo. Ver la nota
                # de la prueba.
                estado=EstadoOferta.OFRECIDA.value if indice == 0 else EstadoOferta.RECHAZADA.value,
                respondida_en=None if indice == 0 else AHORA,
                expira_en=AHORA + timedelta(hours=1),
            )
            for indice, entrada in enumerate(entradas)
        ]
        sesion.add_all(ofertas)
        await sesion.flush()

        ids = {
            "clinica": clinica.id,
            "sede": sede.id,
            "liberada": liberada.id,
            "oferta_a": ofertas[0].id,
            "oferta_b": ofertas[1].id,
            "entrada_a": entradas[0].id,
            "entrada_b": entradas[1].id,
        }

    yield ids

    # Limpieza explicita, en orden inverso a las claves externas.
    async with fabrica_sesiones() as sesion, sesion.begin():
        for tabla, columna in [
            ("oferta_turno", "cita_liberada_id"),
            ("lista_espera", "clinica_id"),
            ("cita", "clinica_id"),
        ]:
            valor = ids["liberada"] if columna == "cita_liberada_id" else ids["clinica"]
            await sesion.execute(
                sa.text(f"DELETE FROM {tabla} WHERE {columna} = :valor"), {"valor": valor}
            )
        for tabla in ("profesional", "servicio", "paciente", "especialidad", "sede", "clinica"):
            columna = "id" if tabla == "clinica" else "clinica_id"
            await sesion.execute(
                sa.text(f"DELETE FROM {tabla} WHERE {columna} = :valor"),
                {"valor": ids["clinica"]},
            )


def _principal(clinica_id: uuid.UUID, sede_id: uuid.UUID) -> Principal:
    return Principal(
        actor_tipo=TipoActor.USUARIO,
        actor_id=uuid.uuid4(),
        clinica_id=clinica_id,
        permisos=frozenset({"lista_espera.gestionar", "cita.crear"}),
        ambito=Ambito(
            clinica_id=clinica_id,
            sedes=frozenset({sede_id}),
            todas_las_especialidades=True,
            todos_los_profesionales=True,
            todos_los_pacientes=True,
        ),
    )


class TestAceptacionConcurrente:
    async def test_dos_aceptaciones_simultaneas_producen_una_sola_cita(
        self,
        fabrica_sesiones: async_sessionmaker[AsyncSession],
        escenario: dict[str, uuid.UUID],
    ) -> None:
        """La carrera real.

        Las dos ofertas se ponen en `OFRECIDA` con SQL directo, saltandose el
        indice unico parcial mediante una desactivacion momentanea: lo que se
        quiere medir aqui es el **bloqueo consultivo**, y con el indice activo
        la segunda oferta ni siquiera existiria. En produccion las dos
        defensas actuan juntas; aqui se aisla la segunda.
        """
        # Se fuerza la situacion imposible para poder medir el bloqueo.
        async with fabrica_sesiones() as sesion, sesion.begin():
            await sesion.execute(sa.text("DROP INDEX IF EXISTS ix_oferta_activa_unica"))
            await sesion.execute(
                sa.text(
                    "UPDATE oferta_turno SET estado = 'OFRECIDA', respondida_en = NULL "
                    "WHERE id = :id"
                ),
                {"id": escenario["oferta_b"]},
            )

        barrera = asyncio.Barrier(2)
        resultados: list[str] = []

        async def aceptar(oferta_id: uuid.UUID) -> None:
            async with fabrica_sesiones() as sesion:
                servicio = ServicioListaEspera(sesion, RelojFijo(AHORA))
                principal = _principal(escenario["clinica"], escenario["sede"])
                await barrera.wait()
                try:
                    async with sesion.begin():
                        await servicio.aceptar_oferta(oferta_id, principal=principal)
                    resultados.append("aceptada")
                except OfertaYaResuelta:
                    resultados.append("ya_resuelta")
                except Exception as exc:
                    resultados.append(type(exc).__name__)

        try:
            await asyncio.gather(aceptar(escenario["oferta_a"]), aceptar(escenario["oferta_b"]))

            # Lo que importa no es el reparto exacto de resultados, sino el
            # invariante: **una sola cita** sobre ese turno.
            async with fabrica_sesiones() as sesion:
                citas = (
                    await sesion.execute(
                        sa.text(
                            "SELECT count(*) FROM cita WHERE cita_origen_id = :id "
                            "AND estado IN ('CONFIRMED', 'HELD', 'RESCHEDULED')"
                        ),
                        {"id": escenario["liberada"]},
                    )
                ).scalar_one()
                aceptadas = (
                    await sesion.execute(
                        sa.text(
                            "SELECT count(*) FROM oferta_turno "
                            "WHERE cita_liberada_id = :id AND estado = 'ACEPTADA'"
                        ),
                        {"id": escenario["liberada"]},
                    )
                ).scalar_one()

            assert citas == 1, f"se crearon {citas} citas sobre el mismo turno"
            assert aceptadas == 1, f"{aceptadas} ofertas quedaron aceptadas"
            assert resultados.count("aceptada") == 1, resultados
        finally:
            # Se restaura el indice para no dejar el esquema alterado para las
            # demas pruebas.
            async with fabrica_sesiones() as sesion, sesion.begin():
                await sesion.execute(
                    sa.text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS ix_oferta_activa_unica "
                        "ON oferta_turno (cita_liberada_id) WHERE estado = 'OFRECIDA'"
                    )
                )

    async def test_el_indice_unico_impide_dos_ofertas_del_mismo_turno(
        self,
        fabrica_sesiones: async_sessionmaker[AsyncSession],
        escenario: dict[str, uuid.UUID],
    ) -> None:
        """La primera defensa, con el indice en su sitio.

        Sin ella, dos barridos simultaneos del worker ofrecerian el mismo
        hueco a dos personas, y las dos lo aceptarian: una se quedaria sin
        cita despues de que el sistema le dijera que era suya.
        """
        async with fabrica_sesiones() as sesion:
            with pytest.raises(IntegrityError, match="ix_oferta_activa_unica"):
                async with sesion.begin():
                    await sesion.execute(
                        sa.text(
                            "UPDATE oferta_turno SET estado = 'OFRECIDA', "
                            "respondida_en = NULL WHERE id = :id"
                        ),
                        {"id": escenario["oferta_b"]},
                    )
