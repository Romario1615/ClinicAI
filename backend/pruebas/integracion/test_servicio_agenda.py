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
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import CitaHistorial, EstadoCita, OrigenCita
from app.modulos.agenda.repositorio import RepositorioAgenda
from app.modulos.agenda.servicios import ServicioAgenda, SolicitudReserva
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
        self, servicio_agenda, solicitud, principal_recepcion
    ) -> None:
        creada = await servicio_agenda.crear_cita_confirmada(
            solicitud, principal=principal_recepcion
        )
        await servicio_agenda.cancelar_cita(
            creada.cita.id, principal=principal_recepcion, motivo="Primera"
        )
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
        reprogramacion = filas[-1]
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
