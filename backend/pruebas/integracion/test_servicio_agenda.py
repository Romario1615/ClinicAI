"""Pruebas del servicio de agenda contra PostgreSQL real.

Se prueba el flujo completo: consultar disponibilidad, bloquear, confirmar,
reprogramar, cancelar y cerrar.  Contra la base de datos real porque las
garantias que importan -- la restriccion de exclusion, el disparador que
calcula `fin`, el bloqueo de fila del `FOR UPDATE` -- no existen en un doble
de prueba.

Lo que se verifica, mas alla de que el codigo se ejecute:

* Que la maquina de estados rechace las transiciones invalidas.
* Que un bloqueo temporal vencido no se pueda confirmar.
* Que la idempotencia devuelva la cita original y no un error.
* Que el ambito filtre: una cita de otra sede no se ve ni se modifica.
* Que cada operacion deje su rastro en el historial.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.modelos import Clinica, Especialidad, Paciente, Profesional, Sede, Servicio
from app.modulos.agenda.modelos import Cita, CitaHistorial, EstadoCita, OrigenCita
from app.modulos.agenda.repositorio import RepositorioAgenda
from app.modulos.agenda.servicios import ServicioAgenda, SolicitudReserva
from app.modulos.outbox.modelos import Recordatorio
from app.nucleo.auditoria import AccionAuditada
from app.nucleo.autorizacion import Ambito, Principal, TipoActor, principal_sistema
from app.nucleo.errores import (
    BloqueoExpirado,
    PermisoDenegado,
    PoliticaCancelacionViolada,
    RecursoNoEncontrado,
    ReglaNegocioViolada,
    TransicionEstadoInvalida,
    TurnoNoDisponible,
)
from app.nucleo.reloj import RelojFijo

pytestmark = [pytest.mark.integracion, pytest.mark.asyncio]

# Miercoles 15 de abril de 2026, 14:00 UTC = 09:00 en Guayaquil.
AHORA = datetime(2026, 4, 15, 14, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
#  Fixtures propias
# ---------------------------------------------------------------------------
@pytest.fixture
def reloj_fijo() -> RelojFijo:
    return RelojFijo(AHORA)


@pytest.fixture
def principal_recepcion(clinica, sede) -> Principal:
    """Principal con los permisos de recepcion y ambito sobre una sede."""
    return Principal(
        actor_tipo=TipoActor.USUARIO,
        actor_id=uuid.uuid4(),
        clinica_id=clinica.id,
        permisos=frozenset(
            {
                "agenda.leer",
                "cita.crear",
                "cita.cancelar",
                "cita.reprogramar",
                "cita.completar",
                "cita.marcar_inasistencia",
            }
        ),
        ambito=Ambito(
            clinica_id=clinica.id,
            sedes=frozenset({sede.id}),
            # El comodin de especialidad es obligatorio, igual que en el rol
            # real: sin el, el ambito de especialidad queda vacio y vacio
            # significa ningun acceso, asi que no veria ninguna cita.
            todas_las_especialidades=True,
            todos_los_profesionales=True,
            todos_los_pacientes=True,
        ),
        origen="WEB",
    )


@pytest.fixture
def principal_sin_permisos(clinica, sede) -> Principal:
    return Principal(
        actor_tipo=TipoActor.USUARIO,
        actor_id=uuid.uuid4(),
        clinica_id=clinica.id,
        permisos=frozenset(),
        ambito=Ambito(clinica_id=clinica.id, sedes=frozenset({sede.id})),
    )


@pytest.fixture
def principal_paciente(clinica, sede, paciente) -> Principal:
    """Paciente actuando por WhatsApp, a traves del agente."""
    return Principal(
        actor_tipo=TipoActor.PACIENTE,
        actor_id=paciente.id,
        clinica_id=clinica.id,
        permisos=frozenset({"agenda.leer", "cita.crear", "cita.cancelar"}),
        ambito=Ambito(
            clinica_id=clinica.id,
            sedes=frozenset({sede.id}),
            todas_las_especialidades=True,
            todos_los_profesionales=True,
            pacientes=frozenset({paciente.id}),
        ),
        paciente_id=paciente.id,
        origen="WHATSAPP",
    )


@pytest.fixture
def servicio_agenda(sesion: AsyncSession, reloj_fijo: RelojFijo) -> ServicioAgenda:
    return ServicioAgenda(sesion, RepositorioAgenda(sesion), reloj_fijo)


@pytest.fixture
def solicitud(clinica, sede, paciente, profesional, servicio) -> SolicitudReserva:
    """Reserva para manana a las 10:00 locales (15:00 UTC)."""
    return SolicitudReserva(
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        servicio_id=servicio.id,
        sede_id=sede.id,
        inicio=AHORA + timedelta(days=1, hours=1),
        origen=OrigenCita.PANEL,
    )


async def _horario_de_la_sede(sesion: AsyncSession, sede_id: uuid.UUID) -> None:
    """Crea un horario de atencion amplio para la sede.

    De lunes a domingo, de 00:00 a 23:59, para que las pruebas de reserva no
    dependan de acertar con el dia de la semana.  Las reglas de horario tienen
    sus propias pruebas en el motor de disponibilidad.
    """
    for dia in range(1, 8):
        await sesion.execute(
            sa.text(
                "INSERT INTO horario_atencion (propietario_tipo, propietario_id, "
                "dia_semana, hora_inicio, hora_fin, granularidad_minutos) "
                "VALUES ('SEDE', :sede, :dia, '00:00', '23:59', 15)"
            ),
            {"sede": sede_id, "dia": dia},
        )
    await sesion.flush()


# ===========================================================================
#  Permisos y ambito
# ===========================================================================
class TestPermisos:
    async def test_sin_permiso_no_se_puede_crear(
        self, servicio_agenda, solicitud, principal_sin_permisos
    ) -> None:
        with pytest.raises(PermisoDenegado, match="crear citas"):
            await servicio_agenda.crear_cita_confirmada(solicitud, principal=principal_sin_permisos)

    async def test_sin_permiso_no_se_puede_consultar_la_agenda(
        self, servicio_agenda, solicitud, principal_sin_permisos
    ) -> None:
        """La disponibilidad revela la carga de trabajo del profesional.

        No es informacion publica dentro de la clinica, asi que consultarla
        exige permiso aunque sea una lectura.
        """
        with pytest.raises(PermisoDenegado, match="consultar la agenda"):
            await servicio_agenda.consultar_disponibilidad(
                principal=principal_sin_permisos,
                profesional_id=solicitud.profesional_id,
                servicio_id=solicitud.servicio_id,
                sede_id=solicitud.sede_id,
                desde=AHORA,
                hasta=AHORA + timedelta(days=1),
            )

    async def test_una_sede_fuera_de_ambito_responde_no_encontrado(
        self, servicio_agenda, solicitud, clinica, principal_recepcion
    ) -> None:
        """404 y no 403.

        Un 403 confirmaria que la sede existe y permitiria enumerarlas
        probando identificadores.
        """
        ajena = Principal(
            actor_tipo=TipoActor.USUARIO,
            actor_id=uuid.uuid4(),
            clinica_id=clinica.id,
            permisos=principal_recepcion.permisos,
            # Ambito sobre una sede distinta de la de la solicitud.
            ambito=Ambito(clinica_id=clinica.id, sedes=frozenset({uuid.uuid4()})),
        )
        with pytest.raises(RecursoNoEncontrado, match="sede"):
            await servicio_agenda.crear_cita_confirmada(solicitud, principal=ajena)

    async def test_una_cita_de_otra_sede_no_se_ve(
        self, sesion, servicio_agenda, solicitud, clinica, principal_recepcion
    ) -> None:
        """El filtro de ambito se aplica en el repositorio, no solo el permiso.

        Comprobar solo el permiso es el error que convierte un sistema con
        roles en un sistema sin control de acceso real.
        """
        resultado = await servicio_agenda.crear_cita_confirmada(
            solicitud, principal=principal_recepcion
        )
        cita_id = resultado.cita.id

        otra_sede = Principal(
            actor_tipo=TipoActor.USUARIO,
            actor_id=uuid.uuid4(),
            clinica_id=clinica.id,
            permisos=principal_recepcion.permisos,
            ambito=Ambito(clinica_id=clinica.id, sedes=frozenset({uuid.uuid4()})),
        )
        repo = RepositorioAgenda(sesion)
        assert await repo.obtener_cita(cita_id, principal=otra_sede) is None
        # Pero si se ve con el ambito correcto.
        assert await repo.obtener_cita(cita_id, principal=principal_recepcion) is not None


# ===========================================================================
#  Creacion
# ===========================================================================
class TestCreacion:
    async def test_crear_cita_confirmada(
        self, sesion, servicio_agenda, solicitud, principal_recepcion, servicio
    ) -> None:
        resultado = await servicio_agenda.crear_cita_confirmada(
            solicitud, principal=principal_recepcion
        )
        cita = resultado.cita

        assert cita.estado == EstadoCita.CONFIRMED.value
        assert cita.confirmada_en == AHORA
        assert cita.expira_en is None
        assert cita.duracion_minutos == servicio.duracion_minutos
        # El buffer efectivo es el mayor entre el del servicio y el del
        # profesional; aqui el profesional no tiene propio.
        assert cita.minutos_preparacion == servicio.minutos_preparacion

        avisos = (
            (
                await sesion.execute(
                    sa.select(Recordatorio).where(
                        Recordatorio.entidad_tipo == "CITA",
                        Recordatorio.entidad_id == cita.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(avisos) == 2
        assert all(aviso.estado == "PROGRAMADO" for aviso in avisos)

    async def test_el_disparador_calcula_fin_y_rango(
        self, sesion, servicio_agenda, solicitud, principal_recepcion, servicio
    ) -> None:
        """El calculo vive en el motor, no en este codigo."""
        resultado = await servicio_agenda.crear_cita_confirmada(
            solicitud, principal=principal_recepcion
        )
        await sesion.refresh(resultado.cita)
        total = servicio.duracion_minutos + servicio.minutos_preparacion
        assert resultado.cita.fin == solicitud.inicio + timedelta(minutes=total)

    async def test_la_creacion_deja_rastro_en_el_historial(
        self, sesion, servicio_agenda, solicitud, principal_recepcion
    ) -> None:
        resultado = await servicio_agenda.crear_cita_confirmada(
            solicitud, principal=principal_recepcion
        )
        await sesion.flush()
        filas = (
            (
                await sesion.execute(
                    sa.select(CitaHistorial).where(CitaHistorial.cita_id == resultado.cita.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(filas) == 1
        assert filas[0].estado_anterior is None
        assert filas[0].estado_nuevo == EstadoCita.CONFIRMED.value

    async def test_la_creacion_produce_auditoria(
        self, servicio_agenda, solicitud, principal_recepcion
    ) -> None:
        """La auditoria se devuelve, no se escribe aqui.

        Asi el servicio que orquesta la transaccion la confirma junto al
        cambio de estado, y queda explicito que forman una unidad atomica.
        """
        resultado = await servicio_agenda.crear_cita_confirmada(
            solicitud, principal=principal_recepcion
        )
        assert len(resultado.auditoria) == 1
        entrada = resultado.auditoria[0]
        assert entrada.accion is AccionAuditada.CITA_CREADA
        assert entrada.entidad_id == resultado.cita.id
        assert entrada.paciente_id == solicitud.paciente_id
        # La auditoria registra referencias, nunca contenido clinico.
        assert "diagnostico" not in entrada.metadatos

    async def test_un_profesional_inactivo_se_rechaza(
        self, sesion, servicio_agenda, solicitud, principal_recepcion, profesional
    ) -> None:
        profesional.activo = False
        await sesion.flush()
        with pytest.raises(ReglaNegocioViolada, match="no esta disponible"):
            await servicio_agenda.crear_cita_confirmada(solicitud, principal=principal_recepcion)

    async def test_un_servicio_inexistente_se_rechaza(
        self, servicio_agenda, solicitud, principal_recepcion
    ) -> None:

        with pytest.raises(RecursoNoEncontrado, match="servicio"):
            await servicio_agenda.crear_cita_confirmada(
                replace(solicitud, servicio_id=uuid.uuid4()), principal=principal_recepcion
            )

    async def test_el_solapamiento_se_traduce_a_turno_no_disponible(
        self, servicio_agenda, solicitud, principal_recepcion, segundo_paciente
    ) -> None:
        """El error del motor llega al usuario como un mensaje util.

        Sin traduccion, el segundo paciente recibiria un 500 en lugar de «ese
        turno ya no esta disponible».
        """

        await servicio_agenda.crear_cita_confirmada(solicitud, principal=principal_recepcion)

        with pytest.raises(TurnoNoDisponible) as excinfo:
            await servicio_agenda.crear_cita_confirmada(
                replace(solicitud, paciente_id=segundo_paciente.id),
                principal=principal_recepcion,
            )
        assert "disponible" in excinfo.value.mensaje.lower()
        assert excinfo.value.estado_http == 409


# ===========================================================================
#  Idempotencia
# ===========================================================================
class TestIdempotencia:
    async def test_la_misma_clave_devuelve_la_cita_original(
        self, servicio_agenda, solicitud, principal_recepcion
    ) -> None:
        """Repetir la peticion debe ser inocuo, no un error.

        Es el caso del doble clic y del reintento de webhook: el cliente no
        puede distinguir «no llego» de «llego y se perdio la respuesta», asi
        que reintenta.  Devolverle un error lo dejaria sin saber si tiene cita.
        """

        con_clave = replace(solicitud, clave_idempotencia="reserva-unica-001")

        primera = await servicio_agenda.crear_cita_confirmada(
            con_clave, principal=principal_recepcion
        )
        segunda = await servicio_agenda.crear_cita_confirmada(
            con_clave, principal=principal_recepcion
        )

        assert segunda.cita.id == primera.cita.id
        assert segunda.era_reintento
        assert not primera.era_reintento

    async def test_una_clave_invalida_se_rechaza(
        self, servicio_agenda, solicitud, principal_recepcion
    ) -> None:
        """Sin limite de longitud, la clave seria un vector de agotamiento."""

        with pytest.raises(ValueError, match="8 y 200"):
            await servicio_agenda.crear_cita_confirmada(
                replace(solicitud, clave_idempotencia="corta"),
                principal=principal_recepcion,
            )


# ===========================================================================
#  Bloqueo temporal
# ===========================================================================
class TestAmbitoVacio:
    """El ambito vacio significa ningun acceso, en TODAS las dimensiones.

    Esta clase existe por un fallo real. El filtro de ambito de la agenda
    escribia `if not ambito.todos_los_profesionales and ambito.profesionales`,
    de modo que un ambito de profesional **vacio** no filtraba nada y el
    principal veia las citas de todos. La condicion parecia defensiva y hacia
    lo contrario. Lo mismo con pacientes, y la dimension de especialidad no se
    aplicaba en absoluto.

    Se prueba dimension por dimension: basta con que una sola vuelva a
    invertirse para que la agenda de la clinica entera quede expuesta.
    """

    @staticmethod
    def _principal(clinica, sede, **ambito) -> Principal:  # type: ignore[no-untyped-def]
        base = {
            "clinica_id": clinica.id,
            "sedes": frozenset({sede.id}),
            "todas_las_especialidades": True,
            "todos_los_profesionales": True,
            "todos_los_pacientes": True,
        }
        base.update(ambito)
        return Principal(
            actor_tipo=TipoActor.USUARIO,
            actor_id=uuid.uuid4(),
            clinica_id=clinica.id,
            permisos=frozenset({"agenda.leer", "cita.crear"}),
            ambito=Ambito(**base),
        )

    @pytest.fixture
    async def cita_creada(self, servicio_agenda, solicitud, principal_recepcion, sesion, sede):  # type: ignore[no-untyped-def]
        await _horario_de_la_sede(sesion, sede.id)
        resultado = await servicio_agenda.crear_cita_confirmada(
            solicitud, principal=principal_recepcion
        )
        return resultado.cita

    async def test_con_ambito_completo_la_cita_se_ve(
        self, servicio_agenda, cita_creada, clinica, sede
    ) -> None:  # type: ignore[no-untyped-def]
        """Control: sin esta, las demas pruebas pasarian por el motivo equivocado."""
        principal = self._principal(clinica, sede)
        citas = await servicio_agenda._repo.listar_citas(principal=principal)
        assert cita_creada.id in {c.id for c in citas}

    async def test_sin_profesionales_no_se_ve_ninguna_cita(
        self, servicio_agenda, cita_creada, clinica, sede
    ) -> None:  # type: ignore[no-untyped-def]
        principal = self._principal(clinica, sede, todos_los_profesionales=False)
        citas = await servicio_agenda._repo.listar_citas(principal=principal)
        assert citas == []

    async def test_sin_pacientes_no_se_ve_ninguna_cita(
        self, servicio_agenda, cita_creada, clinica, sede
    ) -> None:  # type: ignore[no-untyped-def]
        principal = self._principal(clinica, sede, todos_los_pacientes=False)
        citas = await servicio_agenda._repo.listar_citas(principal=principal)
        assert citas == []

    async def test_sin_especialidades_no_se_ve_ninguna_cita(
        self, servicio_agenda, cita_creada, clinica, sede
    ) -> None:  # type: ignore[no-untyped-def]
        """La dimension que faltaba por completo.

        Un profesional de una especialidad veia las citas de todas las demas.
        """
        principal = self._principal(clinica, sede, todas_las_especialidades=False)
        citas = await servicio_agenda._repo.listar_citas(principal=principal)
        assert citas == []

    async def test_sin_sedes_no_se_ve_ninguna_cita(
        self, servicio_agenda, cita_creada, clinica, sede
    ) -> None:  # type: ignore[no-untyped-def]
        principal = self._principal(clinica, sede, sedes=frozenset())
        citas = await servicio_agenda._repo.listar_citas(principal=principal)
        assert citas == []

    async def test_el_total_respeta_el_ambito_igual_que_el_listado(
        self, servicio_agenda, cita_creada, clinica, sede
    ) -> None:  # type: ignore[no-untyped-def]
        """Si el total no filtrara, diria cuantas citas tiene la clinica."""
        principal = self._principal(clinica, sede, todas_las_especialidades=False)
        assert await servicio_agenda._repo.contar_citas(principal=principal) == 0

    async def test_una_especialidad_concreta_solo_ve_lo_suyo(
        self, servicio_agenda, cita_creada, clinica, sede, especialidad
    ) -> None:  # type: ignore[no-untyped-def]
        propia = self._principal(
            clinica,
            sede,
            todas_las_especialidades=False,
            especialidades=frozenset({especialidad.id}),
        )
        ajena = self._principal(
            clinica,
            sede,
            todas_las_especialidades=False,
            especialidades=frozenset({uuid.uuid4()}),
        )

        assert cita_creada.id in {
            c.id for c in await servicio_agenda._repo.listar_citas(principal=propia)
        }
        assert await servicio_agenda._repo.listar_citas(principal=ajena) == []


class TestBloqueoTemporal:
    async def test_el_bloqueo_caduca(self, servicio_agenda, solicitud, principal_recepcion) -> None:
        """El plazo es obligatorio y lo exige la base de datos.

        Un bloqueo sin caducidad retendria el turno para siempre si el
        paciente abandona la conversacion a medias.
        """
        resultado = await servicio_agenda.bloquear_turno(solicitud, principal=principal_recepcion)
        assert resultado.cita.estado == EstadoCita.HELD.value
        assert resultado.cita.expira_en == AHORA + timedelta(minutes=10)

    async def test_un_bloqueo_se_puede_confirmar_dentro_del_plazo(
        self, servicio_agenda, solicitud, principal_recepcion
    ) -> None:
        bloqueo = await servicio_agenda.bloquear_turno(solicitud, principal=principal_recepcion)
        confirmada = await servicio_agenda.confirmar_cita(
            bloqueo.cita.id, principal=principal_recepcion
        )
        assert confirmada.cita.estado == EstadoCita.CONFIRMED.value
        assert confirmada.cita.expira_en is None

    async def test_un_bloqueo_vencido_no_se_puede_confirmar(
        self, sesion, solicitud, principal_recepcion, reloj_fijo
    ) -> None:
        """Confirmarlo seria peor que rechazarlo.

        El turno pudo haberse ofrecido ya a otra persona, y confirmarlo
        produciria dos pacientes citados a la misma hora por un camino que
        elude la restriccion de exclusion.
        """
        servicio = ServicioAgenda(sesion, RepositorioAgenda(sesion), reloj_fijo)
        bloqueo = await servicio.bloquear_turno(solicitud, principal=principal_recepcion)

        # Se adelanta el reloj mas alla del plazo.
        reloj_fijo.avanzar(minutes=11)

        with pytest.raises(BloqueoExpirado, match="se agoto"):
            await servicio.confirmar_cita(bloqueo.cita.id, principal=principal_recepcion)

    async def test_el_barrido_libera_los_bloqueos_vencidos(
        self, sesion, solicitud, principal_recepcion, reloj_fijo
    ) -> None:
        """Sin el barrido, la agenda perderia capacidad de forma invisible."""

        servicio = ServicioAgenda(sesion, RepositorioAgenda(sesion), reloj_fijo)
        bloqueo = await servicio.bloquear_turno(solicitud, principal=principal_recepcion)
        await sesion.flush()

        reloj_fijo.avanzar(minutes=11)
        liberados = await servicio.expirar_bloqueos_vencidos(
            principal=principal_sistema(principal_recepcion.clinica_id)
        )

        identificadores = {r.cita.id for r in liberados}
        assert bloqueo.cita.id in identificadores
        await sesion.refresh(bloqueo.cita)
        assert bloqueo.cita.estado == EstadoCita.CANCELLED.value
        assert "caduco" in (bloqueo.cita.motivo_cancelacion or "")

    async def test_tras_liberarse_el_turno_vuelve_a_estar_libre(
        self, sesion, solicitud, principal_recepcion, reloj_fijo, segundo_paciente
    ) -> None:
        """Es lo que hace util el barrido: el turno se puede reasignar."""

        servicio = ServicioAgenda(sesion, RepositorioAgenda(sesion), reloj_fijo)
        await servicio.bloquear_turno(solicitud, principal=principal_recepcion)
        await sesion.flush()

        reloj_fijo.avanzar(minutes=11)
        await servicio.expirar_bloqueos_vencidos(
            principal=principal_sistema(principal_recepcion.clinica_id)
        )
        await sesion.flush()

        # El mismo turno debe poder asignarse a otra persona.
        nueva = await servicio.crear_cita_confirmada(
            replace(solicitud, paciente_id=segundo_paciente.id),
            principal=principal_recepcion,
        )
        assert nueva.cita.estado == EstadoCita.CONFIRMED.value


# ===========================================================================
#  Maquina de estados
# ===========================================================================
class TestMaquinaDeEstados:
    async def test_no_se_puede_confirmar_una_cita_cancelada(
        self, servicio_agenda, solicitud, principal_recepcion
    ) -> None:
        creada = await servicio_agenda.crear_cita_confirmada(
            solicitud, principal=principal_recepcion
        )
        await servicio_agenda.cancelar_cita(
            creada.cita.id, principal=principal_recepcion, motivo="Prueba"
        )
        with pytest.raises(TransicionEstadoInvalida, match="no admite"):
            await servicio_agenda.confirmar_cita(creada.cita.id, principal=principal_recepcion)

    async def test_no_se_puede_cancelar_dos_veces(
        self, sesion, servicio_agenda, solicitud, principal_recepcion
    ) -> None:
        creada = await servicio_agenda.crear_cita_confirmada(
            solicitud, principal=principal_recepcion
        )
        await servicio_agenda.cancelar_cita(
            creada.cita.id, principal=principal_recepcion, motivo="Primera"
        )
        avisos = (
            (
                await sesion.execute(
                    sa.select(Recordatorio).where(Recordatorio.entidad_id == creada.cita.id)
                )
            )
            .scalars()
            .all()
        )
        assert avisos and all(aviso.estado == "CANCELADO" for aviso in avisos)
        with pytest.raises(TransicionEstadoInvalida):
            await servicio_agenda.cancelar_cita(
                creada.cita.id, principal=principal_recepcion, motivo="Segunda"
            )

    async def test_el_mensaje_de_error_dice_que_se_puede_hacer(
        self, servicio_agenda, solicitud, principal_recepcion
    ) -> None:
        """Un error que solo dice «no puedes» deja al usuario atascado."""
        creada = await servicio_agenda.crear_cita_confirmada(
            solicitud, principal=principal_recepcion
        )
        await servicio_agenda.completar_cita(creada.cita.id, principal=principal_recepcion)
        with pytest.raises(TransicionEstadoInvalida) as excinfo:
            await servicio_agenda.reprogramar_cita(
                creada.cita.id,
                principal=principal_recepcion,
                nuevo_inicio=solicitud.inicio + timedelta(days=1),
                motivo="Prueba",
            )
        assert "cree una cita nueva" in excinfo.value.mensaje.lower()

    async def test_una_cita_completada_no_admite_cambios(
        self, servicio_agenda, solicitud, principal_recepcion
    ) -> None:
        creada = await servicio_agenda.crear_cita_confirmada(
            solicitud, principal=principal_recepcion
        )
        await servicio_agenda.completar_cita(creada.cita.id, principal=principal_recepcion)
        with pytest.raises(TransicionEstadoInvalida):
            await servicio_agenda.cancelar_cita(
                creada.cita.id, principal=principal_recepcion, motivo="Tarde"
            )

    async def test_la_inasistencia_es_un_estado_propio(
        self, servicio_agenda, solicitud, principal_recepcion
    ) -> None:
        """No es una cancelacion.

        Una inasistencia cuenta para la prediccion de ausentismo y para la
        ocupacion perdida; confundirla con una cancelacion falsearia ambas
        metricas.
        """
        creada = await servicio_agenda.crear_cita_confirmada(
            solicitud, principal=principal_recepcion
        )
        resultado = await servicio_agenda.marcar_inasistencia(
            creada.cita.id, principal=principal_recepcion
        )
        assert resultado.cita.estado == EstadoCita.NO_SHOW.value
        assert resultado.cita.motivo_cancelacion is None


# ===========================================================================
#  Cancelacion
# ===========================================================================
class TestCancelacion:
    async def test_el_motivo_es_obligatorio(
        self, servicio_agenda, solicitud, principal_recepcion
    ) -> None:
        """Sin motivo no se puede explicar por que no fue atendido.

        Es justo la pregunta que se hace ante una reclamacion.
        """
        creada = await servicio_agenda.crear_cita_confirmada(
            solicitud, principal=principal_recepcion
        )
        with pytest.raises(ReglaNegocioViolada, match="motivo"):
            await servicio_agenda.cancelar_cita(
                creada.cita.id, principal=principal_recepcion, motivo="   "
            )

    async def test_la_politica_de_antelacion_aplica_al_paciente(
        self, sesion, solicitud, principal_paciente, reloj_fijo, principal_recepcion
    ) -> None:
        """El paciente no puede cancelar con menos antelacion que la politica."""

        servicio = ServicioAgenda(sesion, RepositorioAgenda(sesion), reloj_fijo)
        # Cita dentro de dos horas.
        cercana = replace(solicitud, inicio=AHORA + timedelta(hours=2))
        creada = await servicio.crear_cita_confirmada(cercana, principal=principal_recepcion)

        with pytest.raises(PoliticaCancelacionViolada, match="24 horas"):
            await servicio.cancelar_cita(
                creada.cita.id,
                principal=principal_paciente,
                motivo="Ya no puedo asistir",
                horas_antelacion_minima=24,
            )

    async def test_el_personal_puede_cancelar_sin_antelacion(
        self, sesion, solicitud, principal_recepcion, reloj_fijo
    ) -> None:
        """La politica restringe al paciente, no a la clinica.

        Si el profesional enferma, recepcion tiene que poder cancelar las
        citas de hoy.
        """

        servicio = ServicioAgenda(sesion, RepositorioAgenda(sesion), reloj_fijo)
        cercana = replace(solicitud, inicio=AHORA + timedelta(hours=2))
        creada = await servicio.crear_cita_confirmada(cercana, principal=principal_recepcion)

        resultado = await servicio.cancelar_cita(
            creada.cita.id,
            principal=principal_recepcion,
            motivo="El profesional esta enfermo",
            horas_antelacion_minima=24,
        )
        assert resultado.cita.estado == EstadoCita.CANCELLED.value

    async def test_la_cancelacion_libera_el_turno(
        self, servicio_agenda, solicitud, principal_recepcion, segundo_paciente
    ) -> None:
        """Es la base de la lista de espera."""

        creada = await servicio_agenda.crear_cita_confirmada(
            solicitud, principal=principal_recepcion
        )
        await servicio_agenda.cancelar_cita(
            creada.cita.id, principal=principal_recepcion, motivo="Liberacion"
        )
        # El mismo turno para otra persona.
        nueva = await servicio_agenda.crear_cita_confirmada(
            replace(solicitud, paciente_id=segundo_paciente.id),
            principal=principal_recepcion,
        )
        assert nueva.cita.estado == EstadoCita.CONFIRMED.value


# ===========================================================================
#  Reprogramacion
# ===========================================================================
class TestReprogramacion:
    async def test_reprogramar_reemplaza_los_avisos_vigentes(
        self, sesion, servicio_agenda, solicitud, principal_recepcion
    ) -> None:
        creada = await servicio_agenda.crear_cita_confirmada(
            solicitud, principal=principal_recepcion
        )
        await servicio_agenda.reprogramar_cita(
            creada.cita.id,
            principal=principal_recepcion,
            nuevo_inicio=solicitud.inicio + timedelta(days=2),
            motivo="Cambio solicitado",
        )
        avisos = (
            (
                await sesion.execute(
                    sa.select(Recordatorio)
                    .where(Recordatorio.entidad_id == creada.cita.id)
                    .order_by(Recordatorio.programado_para)
                )
            )
            .scalars()
            .all()
        )
        assert len(avisos) == 4
        assert [aviso.estado for aviso in avisos].count("CANCELADO") == 2
        assert [aviso.estado for aviso in avisos].count("PROGRAMADO") == 2

    async def test_reprogramar_conserva_el_identificador(
        self, servicio_agenda, solicitud, principal_recepcion
    ) -> None:
        """Se modifica la cita, no se crea otra.

        Conservar un solo identificador simplifica el seguimiento para el
        paciente, para el calendario externo y para los recordatorios ya
        programados.  El horario anterior queda en el historial, que es
        append-only, asi que la trazabilidad no se pierde.
        """
        creada = await servicio_agenda.crear_cita_confirmada(
            solicitud, principal=principal_recepcion
        )
        nuevo_inicio = solicitud.inicio + timedelta(days=2)
        resultado = await servicio_agenda.reprogramar_cita(
            creada.cita.id,
            principal=principal_recepcion,
            nuevo_inicio=nuevo_inicio,
            motivo="El paciente lo pidio",
        )
        assert resultado.cita.id == creada.cita.id
        assert resultado.cita.inicio == nuevo_inicio
        assert resultado.cita.estado == EstadoCita.RESCHEDULED.value

    async def test_el_historial_conserva_el_horario_anterior(
        self, sesion, servicio_agenda, solicitud, principal_recepcion
    ) -> None:
        """Ante una reclamacion, la pregunta es a que hora estaba antes."""
        creada = await servicio_agenda.crear_cita_confirmada(
            solicitud, principal=principal_recepcion
        )
        inicio_original = creada.cita.inicio
        nuevo_inicio = inicio_original + timedelta(days=2)
        await servicio_agenda.reprogramar_cita(
            creada.cita.id,
            principal=principal_recepcion,
            nuevo_inicio=nuevo_inicio,
            motivo="Cambio solicitado",
        )
        await sesion.flush()

        filas = (
            (
                await sesion.execute(
                    sa.select(CitaHistorial)
                    .where(CitaHistorial.cita_id == creada.cita.id)
                    .order_by(CitaHistorial.ocurrido_en)
                )
            )
            .scalars()
            .all()
        )
        # El reloj fijo da el mismo instante a creación y reprogramación.
        # SQL no garantiza el orden de filas empatadas: identificar el evento
        # evita depender de la posición física o de un UUID aleatorio.
        cambios = [fila for fila in filas if fila.estado_nuevo == EstadoCita.RESCHEDULED.value]
        assert len(cambios) == 1
        reprogramacion = cambios[0]
        assert reprogramacion.inicio_anterior == inicio_original
        assert reprogramacion.inicio_nuevo == nuevo_inicio
        assert reprogramacion.motivo == "Cambio solicitado"

    async def test_reprogramar_a_un_turno_ocupado_se_rechaza(
        self, servicio_agenda, solicitud, principal_recepcion, segundo_paciente
    ) -> None:
        """La restriccion de exclusion evalua el nuevo rango igual que en la
        creacion.
        """

        primera = await servicio_agenda.crear_cita_confirmada(
            solicitud, principal=principal_recepcion
        )
        # Otra cita tres horas mas tarde.
        objetivo = solicitud.inicio + timedelta(hours=3)
        await servicio_agenda.crear_cita_confirmada(
            replace(solicitud, paciente_id=segundo_paciente.id, inicio=objetivo),
            principal=principal_recepcion,
        )

        with pytest.raises(TurnoNoDisponible):
            await servicio_agenda.reprogramar_cita(
                primera.cita.id,
                principal=principal_recepcion,
                nuevo_inicio=objetivo,
                motivo="Intento de colision",
            )

    async def test_el_motivo_es_obligatorio(
        self, servicio_agenda, solicitud, principal_recepcion
    ) -> None:
        creada = await servicio_agenda.crear_cita_confirmada(
            solicitud, principal=principal_recepcion
        )
        with pytest.raises(ReglaNegocioViolada, match="motivo"):
            await servicio_agenda.reprogramar_cita(
                creada.cita.id,
                principal=principal_recepcion,
                nuevo_inicio=solicitud.inicio + timedelta(days=1),
                motivo="",
            )


# ===========================================================================
#  Disponibilidad contra datos reales
# ===========================================================================
class TestDisponibilidadIntegrada:
    async def test_la_disponibilidad_excluye_las_citas_existentes(
        self, sesion, servicio_agenda, solicitud, principal_recepcion, sede
    ) -> None:
        """El ciclo completo: horario, cita, y el turno desaparece.

        Se reserva **un turno que el sistema ofrecio**, no una hora elegida a
        mano.  Es el flujo real de cualquier cliente, y evita que la prueba
        dependa de acertar con la rejilla: con el servicio de 30 minutos mas
        10 de preparacion, los turnos van cada 45 (40 redondeado a la
        granularidad de 15), asi que una hora en punto arbitraria no tiene por
        que estar ofertada.
        """

        await _horario_de_la_sede(sesion, sede.id)

        desde = solicitud.inicio - timedelta(hours=1)
        hasta = solicitud.inicio + timedelta(hours=3)

        comunes = {
            "principal": principal_recepcion,
            "profesional_id": solicitud.profesional_id,
            "servicio_id": solicitud.servicio_id,
            "sede_id": solicitud.sede_id,
            "desde": desde,
            "hasta": hasta,
        }

        antes = await servicio_agenda.consultar_disponibilidad(**comunes)
        assert len(antes) > 0, "La sede tiene horario: debe haber turnos."

        # Se toma uno del medio: el primero podria quedar fuera por la
        # antelacion minima en otra configuracion.
        elegido = antes.turnos[len(antes.turnos) // 2]

        await servicio_agenda.crear_cita_confirmada(
            replace(solicitud, inicio=elegido.inicio), principal=principal_recepcion
        )
        await sesion.flush()

        despues = await servicio_agenda.consultar_disponibilidad(**comunes)
        inicios_despues = {t.inicio for t in despues.turnos}

        assert elegido.inicio not in inicios_despues, (
            "El turno reservado debe desaparecer de la disponibilidad."
        )
        assert len(despues) < len(antes)

    async def test_los_turnos_ofrecidos_son_reservables(
        self, sesion, servicio_agenda, solicitud, principal_recepcion, sede
    ) -> None:
        """Propiedad de extremo a extremo: lo ofrecido se puede reservar.

        Es la invariante que une el motor con la base de datos.  Si el motor
        ofreciera un turno que la restriccion de exclusion rechaza, el
        paciente veria una opcion que falla al elegirla, y no habria forma de
        explicarle por que.

        Se reservan TODOS los turnos ofrecidos, uno tras otro.  Cada reserva
        cambia la disponibilidad, asi que se recalcula en cada paso.
        """

        await _horario_de_la_sede(sesion, sede.id)

        desde = solicitud.inicio - timedelta(hours=1)
        hasta = solicitud.inicio + timedelta(hours=3)
        comunes = {
            "principal": principal_recepcion,
            "profesional_id": solicitud.profesional_id,
            "servicio_id": solicitud.servicio_id,
            "sede_id": solicitud.sede_id,
            "desde": desde,
            "hasta": hasta,
        }

        reservados = 0
        while True:
            disponibles = await servicio_agenda.consultar_disponibilidad(**comunes)
            if not disponibles:
                break
            turno = disponibles.turnos[0]
            # Debe poder reservarse sin que la base de datos lo rechace.
            resultado = await servicio_agenda.crear_cita_confirmada(
                replace(solicitud, inicio=turno.inicio), principal=principal_recepcion
            )
            assert resultado.cita.estado == EstadoCita.CONFIRMED.value
            await sesion.flush()
            reservados += 1
            # Cota de seguridad: si el bucle no converge, hay un error en el
            # calculo y es mejor fallar que colgarse.
            assert reservados <= 20, "La disponibilidad no se agota: revise el motor."

        assert reservados > 0, "Deberia haberse reservado al menos un turno."

    async def test_un_rango_excesivo_se_rechaza(
        self, servicio_agenda, solicitud, principal_recepcion
    ) -> None:
        """Sin techo, pedir cinco anos seria un vector de agotamiento de CPU."""
        with pytest.raises(ReglaNegocioViolada, match="dias"):
            await servicio_agenda.consultar_disponibilidad(
                principal=principal_recepcion,
                profesional_id=solicitud.profesional_id,
                servicio_id=solicitud.servicio_id,
                sede_id=solicitud.sede_id,
                desde=AHORA,
                hasta=AHORA + timedelta(days=365),
            )

    async def test_sin_horario_no_hay_turnos(
        self, servicio_agenda, solicitud, principal_recepcion
    ) -> None:
        """Una sede sin horario configurado no ofrece nada.

        Es el comportamiento seguro: inventar un horario por defecto
        produciria citas a horas en las que no hay nadie.
        """
        resultado = await servicio_agenda.consultar_disponibilidad(
            principal=principal_recepcion,
            profesional_id=solicitud.profesional_id,
            servicio_id=solicitud.servicio_id,
            sede_id=solicitud.sede_id,
            desde=AHORA,
            hasta=AHORA + timedelta(days=2),
        )
        assert len(resultado) == 0


class TestSeriesRecurrentes:
    async def test_crea_todas_las_citas_de_la_serie_en_el_mismo_horario_local(
        self, sesion, servicio_agenda, solicitud, principal_recepcion, sede
    ) -> None:
        await _horario_de_la_sede(sesion, sede.id)
        solicitud_serie = await _solicitud_en_horario_disponible(
            servicio_agenda, solicitud, principal_recepcion
        )

        resultado = await servicio_agenda.crear_serie_confirmada(
            solicitud_serie,
            principal=principal_recepcion,
            frecuencia="SEMANAL",
            cantidad=3,
        )

        assert resultado.serie_id is not None
        assert len(resultado.citas) == 3
        assert len(resultado.auditoria) == 3
        assert {cita.serie_recurrente_id for cita in resultado.citas} == {resultado.serie_id}
        assert {cita.origen for cita in resultado.citas} == {OrigenCita.RECURRENTE.value}
        horarios_locales = {
            (
                cita.inicio.astimezone(ZoneInfo("America/Guayaquil")).hour,
                cita.inicio.astimezone(ZoneInfo("America/Guayaquil")).minute,
            )
            for cita in resultado.citas
        }
        assert len(horarios_locales) == 1
        assert [cita.inicio for cita in resultado.citas] == sorted(
            cita.inicio for cita in resultado.citas
        )

    async def test_una_ocurrencia_ocupada_impide_guardar_toda_la_serie(
        self,
        sesion,
        servicio_agenda,
        solicitud,
        principal_recepcion,
        segundo_paciente,
        sede,
    ) -> None:
        await _horario_de_la_sede(sesion, sede.id)
        solicitud_serie = await _solicitud_en_horario_disponible(
            servicio_agenda, solicitud, principal_recepcion
        )
        fecha_ocupada = solicitud_serie.inicio + timedelta(days=7)
        await servicio_agenda.crear_cita_confirmada(
            replace(solicitud_serie, paciente_id=segundo_paciente.id, inicio=fecha_ocupada),
            principal=principal_recepcion,
        )

        with pytest.raises(TurnoNoDisponible, match="no está disponible"):
            await servicio_agenda.crear_serie_confirmada(
                solicitud_serie,
                principal=principal_recepcion,
                frecuencia="SEMANAL",
                cantidad=3,
            )

        series = (
            await sesion.execute(
                sa.select(sa.func.count())
                .select_from(Cita)
                # Solo las del paciente de la prueba: la base de desarrollo
                # guarda series reales de otros recorridos.
                .where(
                    Cita.serie_recurrente_id.is_not(None),
                    Cita.paciente_id == solicitud_serie.paciente_id,
                )
            )
        ).scalar_one()
        assert series == 0

    async def test_crear_una_serie_no_exige_permiso_de_lectura_de_agenda(
        self, sesion, servicio_agenda, solicitud, principal_recepcion, sede
    ) -> None:
        await _horario_de_la_sede(sesion, sede.id)
        solicitud_serie = await _solicitud_en_horario_disponible(
            servicio_agenda, solicitud, principal_recepcion
        )
        principal_creacion = replace(principal_recepcion, permisos=frozenset({"cita.crear"}))

        resultado = await servicio_agenda.crear_serie_confirmada(
            solicitud_serie,
            principal=principal_creacion,
            frecuencia="SEMANAL",
            cantidad=2,
        )

        assert len(resultado.citas) == 2

    async def test_una_cita_previa_de_otra_duracion_no_impide_la_serie(
        self,
        sesion,
        servicio_agenda,
        solicitud,
        principal_recepcion,
        segundo_paciente,
        sede,
        clinica,
        especialidad,
        sufijo,
    ) -> None:
        """La serie comprueba huecos libres, no la rejilla de turnos de cada día.

        Una cita previa de 70 minutos el primer jueves desplaza la rejilla de
        ese día (10:15, 11:00, 11:45) respecto de la de los jueves sin citas
        (09:00, 09:45, 10:30...).  Las 10:15 de los jueves siguientes están
        libres aunque no sean un turno ofrecido, y la serie debe aceptarse:
        antes se rechazaba con 409 en cuanto la agenda tenía carga.
        """
        await _franjas_laborables(sesion, sede.id)
        largo = Servicio(
            clinica_id=clinica.id,
            especialidad_id=especialidad.id,
            nombre=f"Servicio largo {sufijo}",
            duracion_minutos=60,
            minutos_preparacion=10,
        )
        sesion.add(largo)
        await sesion.flush()
        await servicio_agenda.crear_cita_confirmada(
            replace(
                solicitud,
                paciente_id=segundo_paciente.id,
                servicio_id=largo.id,
                inicio=datetime.combine(JUEVES, time(9), tzinfo=GUAYAQUIL),
            ),
            principal=principal_recepcion,
        )
        oferta = await servicio_agenda.consultar_disponibilidad(
            principal=principal_recepcion,
            profesional_id=solicitud.profesional_id,
            servicio_id=solicitud.servicio_id,
            sede_id=solicitud.sede_id,
            desde=datetime.combine(JUEVES, time.min, tzinfo=GUAYAQUIL),
            hasta=datetime.combine(JUEVES + timedelta(days=8), time.min, tzinfo=GUAYAQUIL),
        )
        ofrecidos = {t.inicio.astimezone(GUAYAQUIL).replace(tzinfo=None) for t in oferta.turnos}
        # Precondición: la rejilla del primer jueves está desplazada.
        assert datetime(2026, 4, 16, 10, 15) in ofrecidos
        assert datetime(2026, 4, 23, 10, 15) not in ofrecidos

        resultado = await servicio_agenda.crear_serie_confirmada(
            replace(solicitud, inicio=datetime.combine(JUEVES, time(10, 15), tzinfo=GUAYAQUIL)),
            principal=principal_recepcion,
            frecuencia="SEMANAL",
            cantidad=3,
        )

        assert [c.inicio.astimezone(GUAYAQUIL).replace(tzinfo=None) for c in resultado.citas] == [
            datetime(2026, 4, 16, 10, 15),
            datetime(2026, 4, 23, 10, 15),
            datetime(2026, 4, 30, 10, 15),
        ]

    async def test_una_fecha_que_pisa_una_cita_sigue_rechazando_la_serie(
        self,
        sesion,
        servicio_agenda,
        solicitud,
        principal_recepcion,
        segundo_paciente,
        sede,
    ) -> None:
        """La contención no relaja la ocupación: un solape parcial se rechaza."""
        await _franjas_laborables(sesion, sede.id)
        await servicio_agenda.crear_cita_confirmada(
            replace(
                solicitud,
                paciente_id=segundo_paciente.id,
                inicio=datetime.combine(JUEVES + timedelta(days=7), time(10, 30), tzinfo=GUAYAQUIL),
            ),
            principal=principal_recepcion,
        )

        with pytest.raises(TurnoNoDisponible, match="23/04/2026 10:15"):
            await servicio_agenda.crear_serie_confirmada(
                replace(solicitud, inicio=datetime.combine(JUEVES, time(10, 15), tzinfo=GUAYAQUIL)),
                principal=principal_recepcion,
                frecuencia="SEMANAL",
                cantidad=3,
            )
        assert await _filas_de_serie(sesion, solicitud.paciente_id) == 0

    async def test_una_fecha_fuera_de_la_franja_rechaza_la_serie(
        self, sesion, servicio_agenda, solicitud, principal_recepcion, sede
    ) -> None:
        """12:30 + 40 minutos sobrepasa el cierre de las 13:00."""
        await _franjas_laborables(sesion, sede.id)

        with pytest.raises(TurnoNoDisponible, match="16/04/2026 12:30"):
            await servicio_agenda.crear_serie_confirmada(
                replace(solicitud, inicio=datetime.combine(JUEVES, time(12, 30), tzinfo=GUAYAQUIL)),
                principal=principal_recepcion,
                frecuencia="SEMANAL",
                cantidad=2,
            )
        assert await _filas_de_serie(sesion, solicitud.paciente_id) == 0

    async def test_una_fecha_dentro_de_la_antelacion_minima_rechaza_la_serie(
        self, sesion, servicio_agenda, solicitud, principal_recepcion, sede
    ) -> None:
        """La sede exige 60 minutos de antelación; dentro de 30 está libre pero no vale."""
        await _horario_de_la_sede(sesion, sede.id)

        with pytest.raises(TurnoNoDisponible, match="no está disponible"):
            await servicio_agenda.crear_serie_confirmada(
                replace(solicitud, inicio=AHORA + timedelta(minutes=30)),
                principal=principal_recepcion,
                frecuencia="SEMANAL",
                cantidad=2,
            )
        assert await _filas_de_serie(sesion, solicitud.paciente_id) == 0

    async def test_mensual_con_franjas_de_lunes_a_viernes_conserva_el_dia_de_la_semana(
        self, sesion, servicio_agenda, solicitud, principal_recepcion, sede
    ) -> None:
        """MENSUAL = cada cuatro semanas: siempre jueves, siempre dentro de franja.

        Con «el mismo número de día» la segunda fecha sería el sábado 16/05,
        fuera de las franjas de lunes a viernes, y la serie fallaba con 409.
        """
        await _franjas_laborables(sesion, sede.id)

        resultado = await servicio_agenda.crear_serie_confirmada(
            replace(solicitud, inicio=datetime.combine(JUEVES, time(10), tzinfo=GUAYAQUIL)),
            principal=principal_recepcion,
            frecuencia="MENSUAL",
            cantidad=4,
        )

        locales = [cita.inicio.astimezone(GUAYAQUIL) for cita in resultado.citas]
        assert [local.date() for local in locales] == [
            date(2026, 4, 16),
            date(2026, 5, 14),
            date(2026, 6, 11),
            date(2026, 7, 9),
        ]
        assert {local.isoweekday() for local in locales} == {4}
        assert {(local.hour, local.minute) for local in locales} == {(10, 0)}
        assert await _filas_de_serie(sesion, solicitud.paciente_id) == 4


# ===========================================================================
#  Recursos de otra clinica y pacientes fuera del ambito (IDOR)
# ===========================================================================
@dataclass(frozen=True)
class _OtraClinica:
    clinica: Clinica
    sede: Sede
    servicio: Servicio
    profesional: Profesional
    paciente: Paciente


@pytest_asyncio.fixture
async def otra_clinica(sesion: AsyncSession, sufijo: str) -> _OtraClinica:
    """Una segunda clinica completa, con datos sinteticos."""
    clinica = Clinica(
        nombre=f"Clinica Ajena {sufijo}",
        identificacion_fiscal=f"AJENA-{sufijo}",
        zona_horaria="America/Guayaquil",
    )
    sesion.add(clinica)
    await sesion.flush()
    especialidad = Especialidad(clinica_id=clinica.id, nombre=f"Especialidad Ajena {sufijo}")
    sede = Sede(clinica_id=clinica.id, nombre=f"Sede Ajena {sufijo}", direccion="Calle Ficticia 9")
    paciente = Paciente(
        clinica_id=clinica.id,
        tipo_documento="SIN_DOCUMENTO",
        nombre="Paciente",
        apellido=f"De Otra Clinica {sufijo}",
    )
    sesion.add_all([especialidad, sede, paciente])
    await sesion.flush()
    servicio = Servicio(
        clinica_id=clinica.id,
        especialidad_id=especialidad.id,
        nombre=f"Servicio Ajeno {sufijo}",
        duracion_minutos=30,
        minutos_preparacion=10,
    )
    profesional = Profesional(
        clinica_id=clinica.id,
        especialidad_id=especialidad.id,
        nombre="Profesional",
        apellido=f"Ajeno {sufijo}",
    )
    sesion.add_all([servicio, profesional])
    await sesion.flush()
    await _horario_de_la_sede(sesion, sede.id)
    return _OtraClinica(clinica, sede, servicio, profesional, paciente)


class TestRecursosDeOtraClinica:
    """`cita` solo tiene FK simples: el servicio valida clinica y ambito.

    Un recurso de otra clinica responde 404 con el mismo mensaje que uno
    inexistente, y no se escribe ninguna fila.
    """

    @pytest.mark.parametrize("metodo", ["crear_cita_confirmada", "bloquear_turno"])
    async def test_un_paciente_de_otra_clinica_responde_no_encontrado(
        self,
        sesion,
        servicio_agenda,
        solicitud,
        principal_recepcion,
        sede,
        otra_clinica,
        metodo,
    ) -> None:
        await _horario_de_la_sede(sesion, sede.id)

        with pytest.raises(RecursoNoEncontrado, match="paciente"):
            await getattr(servicio_agenda, metodo)(
                replace(solicitud, paciente_id=otra_clinica.paciente.id),
                principal=principal_recepcion,
            )

        assert await _citas_del_paciente(sesion, otra_clinica.paciente.id) == 0

    async def test_una_serie_para_un_paciente_de_otra_clinica_no_crea_ninguna_cita(
        self, sesion, servicio_agenda, solicitud, principal_recepcion, sede, otra_clinica
    ) -> None:
        await _horario_de_la_sede(sesion, sede.id)
        solicitud_serie = await _solicitud_en_horario_disponible(
            servicio_agenda, solicitud, principal_recepcion
        )

        with pytest.raises(RecursoNoEncontrado, match="paciente"):
            await servicio_agenda.crear_serie_confirmada(
                replace(solicitud_serie, paciente_id=otra_clinica.paciente.id),
                principal=principal_recepcion,
                frecuencia="SEMANAL",
                cantidad=53,
            )

        assert await _filas_de_serie(sesion, otra_clinica.paciente.id) == 0
        assert await _citas_del_paciente(sesion, otra_clinica.paciente.id) == 0

    async def test_un_paciente_fuera_del_ambito_responde_no_encontrado(
        self,
        sesion,
        servicio_agenda,
        solicitud,
        principal_paciente,
        segundo_paciente,
        sede,
    ) -> None:
        """El principal de un paciente (canal WhatsApp) solo reserva para si mismo.

        `hold_slot` recibe `paciente_id` como argumento del modelo; sin esta
        comprobacion, el agente podria apartar turnos a nombre de otro.
        """
        await _horario_de_la_sede(sesion, sede.id)
        ajena = replace(solicitud, paciente_id=segundo_paciente.id)

        with pytest.raises(RecursoNoEncontrado, match="paciente"):
            await servicio_agenda.bloquear_turno(ajena, principal=principal_paciente)
        with pytest.raises(RecursoNoEncontrado, match="paciente"):
            await servicio_agenda.crear_serie_confirmada(
                ajena, principal=principal_paciente, frecuencia="SEMANAL", cantidad=2
            )

        assert await _citas_del_paciente(sesion, segundo_paciente.id) == 0
        # Para si mismo, si puede.
        propia = await servicio_agenda.bloquear_turno(solicitud, principal=principal_paciente)
        assert propia.cita.paciente_id == solicitud.paciente_id

    async def test_paciente_ajeno_e_inexistente_responden_igual(
        self, servicio_agenda, solicitud, principal_recepcion, otra_clinica
    ) -> None:
        """Si los mensajes se distinguieran, el 404 dejaria de proteger nada."""
        with pytest.raises(RecursoNoEncontrado) as ajeno:
            await servicio_agenda.crear_cita_confirmada(
                replace(solicitud, paciente_id=otra_clinica.paciente.id),
                principal=principal_recepcion,
            )
        with pytest.raises(RecursoNoEncontrado) as inexistente:
            await servicio_agenda.crear_cita_confirmada(
                replace(solicitud, paciente_id=uuid.uuid4()),
                principal=principal_recepcion,
            )

        assert str(ajeno.value) == str(inexistente.value)

    @pytest.mark.parametrize(
        ("campo", "recurso", "texto"),
        [
            ("servicio_id", "servicio", "servicio"),
            ("profesional_id", "profesional", "profesional"),
        ],
    )
    async def test_servicio_o_profesional_de_otra_clinica_responde_no_encontrado(
        self,
        sesion,
        servicio_agenda,
        solicitud,
        principal_recepcion,
        sede,
        otra_clinica,
        campo,
        recurso,
        texto,
    ) -> None:
        await _horario_de_la_sede(sesion, sede.id)
        ajeno_id = getattr(otra_clinica, recurso).id
        ajena = replace(solicitud, **{campo: ajeno_id})

        with pytest.raises(RecursoNoEncontrado, match=texto):
            await servicio_agenda.crear_cita_confirmada(ajena, principal=principal_recepcion)
        with pytest.raises(RecursoNoEncontrado, match=texto):
            await servicio_agenda.crear_serie_confirmada(
                ajena, principal=principal_recepcion, frecuencia="SEMANAL", cantidad=2
            )
        with pytest.raises(RecursoNoEncontrado, match=texto):
            await servicio_agenda.consultar_disponibilidad(
                principal=principal_recepcion,
                profesional_id=ajena.profesional_id,
                servicio_id=ajena.servicio_id,
                sede_id=ajena.sede_id,
                desde=AHORA,
                hasta=AHORA + timedelta(days=1),
            )

        assert await _citas_del_paciente(sesion, solicitud.paciente_id) == 0

    async def test_una_sede_de_otra_clinica_no_pasa_con_el_comodin_de_sedes(
        self, sesion, servicio_agenda, solicitud, principal_recepcion, otra_clinica
    ) -> None:
        """«Todas las sedes» son las de su clinica, no las de cualquiera."""
        con_comodin = replace(
            principal_recepcion,
            ambito=replace(principal_recepcion.ambito, todas_las_sedes=True),
        )
        ajena = replace(solicitud, sede_id=otra_clinica.sede.id)

        with pytest.raises(RecursoNoEncontrado, match="sede"):
            await servicio_agenda.crear_cita_confirmada(ajena, principal=con_comodin)
        with pytest.raises(RecursoNoEncontrado, match="sede"):
            await servicio_agenda.bloquear_turno(ajena, principal=con_comodin)
        with pytest.raises(RecursoNoEncontrado, match="sede"):
            await servicio_agenda.crear_serie_confirmada(
                ajena, principal=con_comodin, frecuencia="SEMANAL", cantidad=2
            )
        with pytest.raises(RecursoNoEncontrado, match="sede"):
            await servicio_agenda.consultar_disponibilidad(
                principal=con_comodin,
                profesional_id=solicitud.profesional_id,
                servicio_id=solicitud.servicio_id,
                sede_id=otra_clinica.sede.id,
                desde=AHORA,
                hasta=AHORA + timedelta(days=1),
            )

        assert await _citas_del_paciente(sesion, solicitud.paciente_id) == 0

    async def test_reprogramar_a_un_profesional_de_otra_clinica_responde_no_encontrado(
        self, sesion, servicio_agenda, solicitud, principal_recepcion, sede, otra_clinica
    ) -> None:
        await _horario_de_la_sede(sesion, sede.id)
        creada = await servicio_agenda.crear_cita_confirmada(
            solicitud, principal=principal_recepcion
        )

        with pytest.raises(RecursoNoEncontrado, match="profesional"):
            await servicio_agenda.reprogramar_cita(
                creada.cita.id,
                nuevo_inicio=solicitud.inicio + timedelta(hours=2),
                motivo="Cambio de profesional",
                nuevo_profesional_id=otra_clinica.profesional.id,
                principal=principal_recepcion,
            )


# Jueves 16 de abril de 2026: el dia siguiente a AHORA, laborable.
JUEVES = date(2026, 4, 16)
GUAYAQUIL = ZoneInfo("America/Guayaquil")


async def _franjas_laborables(
    sesion: AsyncSession,
    sede_id: uuid.UUID,
    *,
    hora_inicio: time = time(9),
    hora_fin: time = time(13),
) -> None:
    """Horario de lunes a viernes, de 09:00 a 13:00, granularidad de 15."""
    for dia in range(1, 6):
        await sesion.execute(
            sa.text(
                "INSERT INTO horario_atencion (propietario_tipo, propietario_id, "
                "dia_semana, hora_inicio, hora_fin, granularidad_minutos) "
                "VALUES ('SEDE', :sede, :dia, :inicio, :fin, 15)"
            ),
            {"sede": sede_id, "dia": dia, "inicio": hora_inicio, "fin": hora_fin},
        )
    await sesion.flush()


async def _filas_de_serie(sesion: AsyncSession, paciente_id: uuid.UUID) -> int:
    """Citas de una serie del paciente; acota por paciente para no depender del resto de la base."""
    return int(
        (
            await sesion.execute(
                sa.select(sa.func.count())
                .select_from(Cita)
                .where(Cita.serie_recurrente_id.is_not(None), Cita.paciente_id == paciente_id)
            )
        ).scalar_one()
    )


async def _citas_del_paciente(sesion: AsyncSession, paciente_id: uuid.UUID) -> int:
    return int(
        (
            await sesion.execute(
                sa.select(sa.func.count()).select_from(Cita).where(Cita.paciente_id == paciente_id)
            )
        ).scalar_one()
    )


async def _solicitud_en_horario_disponible(
    servicio_agenda: ServicioAgenda,
    solicitud: SolicitudReserva,
    principal: Principal,
) -> SolicitudReserva:
    """Usa un turno ofrecido por el motor, no una hora asumida por el test."""
    zona = ZoneInfo("America/Guayaquil")
    dia = solicitud.inicio.astimezone(zona).date()
    desde = datetime.combine(dia, time.min, tzinfo=zona)
    hasta = datetime.combine(dia + timedelta(days=1), time.min, tzinfo=zona)
    turnos = await servicio_agenda.consultar_disponibilidad(
        principal=principal,
        profesional_id=solicitud.profesional_id,
        servicio_id=solicitud.servicio_id,
        sede_id=solicitud.sede_id,
        desde=desde,
        hasta=hasta,
        consultorio_id=solicitud.consultorio_id,
    )
    assert turnos.turnos, "La fixture de la sede debe ofrecer al menos un turno"
    objetivo = solicitud.inicio.astimezone(zona)
    turno = min(
        turnos.turnos,
        key=lambda disponible: abs(disponible.inicio.astimezone(zona) - objetivo),
    )
    return replace(solicitud, inicio=turno.inicio)
