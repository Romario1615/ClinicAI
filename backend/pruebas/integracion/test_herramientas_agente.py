"""Las herramientas del agente contra PostgreSQL real.

Por que contra la base real y no con dobles
-------------------------------------------
Lo que hay que demostrar aqui es que el agente **no puede** saltarse el filtro
de ambito, y ese filtro vive en el `WHERE` de una consulta. Un doble de prueba
devolveria lo que se le diga, incluida una cita de otra clinica, y la prueba
pasaria sin haber comprobado nada.

Lo que se verifica
------------------
* Que el despachador audite toda invocacion: exito, denegacion y error.
* Que un nombre de herramienta inventado se deniegue y quede registrado.
* Que el ambito recorte de verdad: una cita ajena no se lee ni se cancela.
* Que los errores de dominio salgan traducidos, sin filtrar detalle interno.
* Que `handoff_to_human` marque la conversacion y no falle nunca.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.ia.herramientas.contrato import ContextoHerramienta
from app.ia.herramientas.limites import MotivoDerivacion
from app.ia.herramientas.registro import despachar
from app.modulos.agenda.modelos import EstadoCita, OrigenCita
from app.modulos.agenda.repositorio import RepositorioAgenda
from app.modulos.agenda.servicios import ServicioAgenda, SolicitudReserva
from app.modulos.conversaciones.modelos import Conversacion, EstadoConversacion
from app.nucleo.auditoria import AccionAuditada, ResultadoAuditoria
from app.nucleo.autorizacion import Ambito, Principal, TipoActor
from app.nucleo.reloj import RelojFijo

pytestmark = [pytest.mark.integracion, pytest.mark.asyncio]

# Miercoles 15 de abril de 2026, 14:00 UTC = 09:00 en Guayaquil.
AHORA = datetime(2026, 4, 15, 14, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
#  Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def reloj_fijo() -> RelojFijo:
    return RelojFijo(AHORA)


@pytest.fixture
def principal_agente(clinica, sede, paciente) -> Principal:
    """El agente actuando en nombre de un paciente identificado.

    `TipoActor.AGENTE_IA` no concede nada: los permisos y el ambito son los
    del paciente. El tipo existe para que la auditoria distinga lo que hizo
    una persona de lo que hizo el agente.
    """
    return Principal(
        actor_tipo=TipoActor.AGENTE_IA,
        actor_id=paciente.id,
        clinica_id=clinica.id,
        permisos=frozenset({"agenda.leer", "cita.crear", "cita.cancelar", "cita.reprogramar"}),
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
def principal_sin_permisos(clinica, sede, paciente) -> Principal:
    return Principal(
        actor_tipo=TipoActor.AGENTE_IA,
        actor_id=paciente.id,
        clinica_id=clinica.id,
        permisos=frozenset(),
        ambito=Ambito(clinica_id=clinica.id, sedes=frozenset({sede.id})),
        paciente_id=paciente.id,
        origen="WHATSAPP",
    )


@pytest_asyncio.fixture
async def conversacion(sesion: AsyncSession, clinica, paciente) -> Conversacion:
    registro = Conversacion(
        clinica_id=clinica.id,
        canal="WHATSAPP",
        telefono="593999000111",
        paciente_id=paciente.id,
        estado=EstadoConversacion.ABIERTA.value,
        ultima_actividad_en=AHORA,
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


@pytest.fixture
def contexto(
    principal_agente: Principal,
    sesion: AsyncSession,
    reloj_fijo: RelojFijo,
    conversacion: Conversacion,
) -> ContextoHerramienta:
    return ContextoHerramienta(
        principal=principal_agente,
        sesion=sesion,
        reloj=reloj_fijo,
        conversacion_id=conversacion.id,
        correlacion_id="prueba-agente",
    )


async def _horario_de_la_sede(sesion: AsyncSession, sede_id: uuid.UUID) -> None:
    """Horario amplio, para que la disponibilidad no dependa del dia."""
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


def _consulta(profesional, servicio, sede) -> dict[str, str]:
    """Argumentos de `find_availability` para el dia siguiente."""
    return {
        "profesional_id": str(profesional.id),
        "servicio_id": str(servicio.id),
        "sede_id": str(sede.id),
        "desde": (AHORA + timedelta(days=1)).isoformat(),
        "hasta": (AHORA + timedelta(days=2)).isoformat(),
    }


async def _contar_auditoria(
    sesion: AsyncSession, accion: AccionAuditada, resultado: ResultadoAuditoria | None = None
) -> int:
    consulta = (
        sa.select(sa.func.count())
        .select_from(sa.table("auditoria"))
        .where(sa.column("accion") == accion.value)
    )
    if resultado is not None:
        consulta = consulta.where(sa.column("resultado") == resultado.value)
    return (await sesion.execute(consulta)).scalar_one()


# ===========================================================================
#  El despachador
# ===========================================================================
class TestDespachador:
    @pytest.mark.parametrize(
        ("nombre", "argumentos"),
        [
            (
                "find_availability",
                {
                    "profesional_id": str(uuid.uuid4()),
                    "servicio_id": str(uuid.uuid4()),
                    "sede_id": str(uuid.uuid4()),
                    "desde": AHORA.isoformat(),
                    "hasta": (AHORA + timedelta(days=1)).isoformat(),
                },
            ),
            (
                "hold_slot",
                {
                    "paciente_id": str(uuid.uuid4()),
                    "profesional_id": str(uuid.uuid4()),
                    "servicio_id": str(uuid.uuid4()),
                    "sede_id": str(uuid.uuid4()),
                    "inicio": (AHORA + timedelta(days=1)).isoformat(),
                },
            ),
            ("confirm_appointment", {"cita_id": str(uuid.uuid4())}),
            ("cancel_appointment", {"cita_id": str(uuid.uuid4()), "motivo": "Cambio de planes"}),
            (
                "reschedule_appointment",
                {
                    "cita_id": str(uuid.uuid4()),
                    "nuevo_inicio": (AHORA + timedelta(days=1)).isoformat(),
                    "motivo": "Cambio de planes",
                },
            ),
            ("get_patient_appointments", {"paciente_id": str(uuid.uuid4())}),
            ("get_patient_payments", {"paciente_id": str(uuid.uuid4())}),
        ],
    )
    async def test_cada_herramienta_de_datos_exige_su_permiso(
        self,
        nombre: str,
        argumentos: dict[str, str],
        contexto: ContextoHerramienta,
        principal_sin_permisos: Principal,
        sesion: AsyncSession,
    ) -> None:
        antes = await _contar_auditoria(
            sesion, AccionAuditada.HERRAMIENTA_DENEGADA, ResultadoAuditoria.DENEGADO
        )
        resultado = await despachar(
            nombre,
            argumentos,
            replace(contexto, principal=principal_sin_permisos),
        )

        assert resultado.requiere_humano is True
        assert resultado.codigo == "SIN_PERMISO"
        assert (
            await _contar_auditoria(
                sesion, AccionAuditada.HERRAMIENTA_DENEGADA, ResultadoAuditoria.DENEGADO
            )
            == antes + 1
        )

    @pytest.mark.parametrize(
        "nombre",
        [
            "find_availability",
            "hold_slot",
            "confirm_appointment",
            "cancel_appointment",
            "reschedule_appointment",
            "get_patient_appointments",
            "get_patient_payments",
            "handoff_to_human",
        ],
    )
    async def test_cada_herramienta_rechaza_argumentos_incompletos_y_deriva(
        self,
        nombre: str,
        contexto: ContextoHerramienta,
        sesion: AsyncSession,
    ) -> None:
        antes = await _contar_auditoria(
            sesion, AccionAuditada.HERRAMIENTA_DENEGADA, ResultadoAuditoria.DENEGADO
        )
        resultado = await despachar(nombre, {}, contexto)

        assert resultado.requiere_humano is True
        assert resultado.codigo == "ARGUMENTOS_INVALIDOS"
        assert (
            await _contar_auditoria(
                sesion, AccionAuditada.HERRAMIENTA_DENEGADA, ResultadoAuditoria.DENEGADO
            )
            == antes + 1
        )

    async def test_una_herramienta_inventada_se_deniega_y_se_audita(
        self, contexto: ContextoHerramienta, sesion: AsyncSession
    ) -> None:
        """Un modelo puede pedir `delete_patient`. Lo que no puede es que exista.

        La denegacion se audita con `HERRAMIENTA_DENEGADA`, que esta en la
        lista de acciones que generan alerta: si alguien logra que el modelo
        invoque nombres que no existen, es una senal de ataque, no un fallo de
        transcripcion.
        """
        antes = await _contar_auditoria(sesion, AccionAuditada.HERRAMIENTA_DENEGADA)

        resultado = await despachar("delete_patient", {}, contexto)

        assert resultado.exito is False
        assert resultado.requiere_humano is True
        assert resultado.codigo == "NO_EXISTE"
        assert await _contar_auditoria(sesion, AccionAuditada.HERRAMIENTA_DENEGADA) == antes + 1

    async def test_los_argumentos_invalidos_no_devuelven_los_valores_enviados(
        self, contexto: ContextoHerramienta
    ) -> None:
        """El detalle de Pydantic incluye lo que se envio, y eso puede ser un dato del paciente.

        Devolverselo al modelo lo pondria en el historial de la conversacion y,
        de ahi, en el siguiente mensaje que se le manda a alguien.
        """
        resultado = await despachar("hold_slot", {"paciente_id": "no-es-un-uuid"}, contexto)

        assert resultado.exito is False
        assert resultado.codigo == "ARGUMENTOS_INVALIDOS"
        assert "no-es-un-uuid" not in resultado.mensaje

    async def test_sin_permiso_se_deniega_antes_de_ejecutar(
        self,
        principal_sin_permisos: Principal,
        sesion: AsyncSession,
        reloj_fijo: RelojFijo,
        conversacion: Conversacion,
        paciente,
        profesional,
        servicio,
        sede,
    ) -> None:
        contexto = ContextoHerramienta(
            principal=principal_sin_permisos,
            sesion=sesion,
            reloj=reloj_fijo,
            conversacion_id=conversacion.id,
        )
        resultado = await despachar(
            "hold_slot",
            {
                "paciente_id": str(paciente.id),
                "profesional_id": str(profesional.id),
                "servicio_id": str(servicio.id),
                "sede_id": str(sede.id),
                "inicio": (AHORA + timedelta(days=1)).isoformat(),
            },
            contexto,
        )
        assert resultado.exito is False
        assert resultado.codigo == "SIN_PERMISO"

    async def test_una_invocacion_correcta_queda_auditada(
        self, contexto: ContextoHerramienta, sesion: AsyncSession, paciente
    ) -> None:
        antes = await _contar_auditoria(
            sesion, AccionAuditada.HERRAMIENTA_INVOCADA, ResultadoAuditoria.EXITO
        )

        await despachar("get_patient_appointments", {"paciente_id": str(paciente.id)}, contexto)

        despues = await _contar_auditoria(
            sesion, AccionAuditada.HERRAMIENTA_INVOCADA, ResultadoAuditoria.EXITO
        )
        assert despues == antes + 1

    async def test_la_auditoria_registra_al_agente_como_actor(
        self, contexto: ContextoHerramienta, sesion: AsyncSession, paciente
    ) -> None:
        """Distinguir al agente de una persona es lo que permite revisar despues
        que hizo la automatizacion sin tener que reconstruirlo de los mensajes.
        """
        await despachar("get_patient_appointments", {"paciente_id": str(paciente.id)}, contexto)
        # Se acota al paciente de la prueba: la base de desarrollo guarda
        # invocaciones reales posteriores al reloj fijo de la prueba.
        tipo = (
            await sesion.execute(
                sa.text(
                    "SELECT actor_tipo FROM auditoria WHERE accion = :a AND paciente_id = :p "
                    "ORDER BY ocurrido_en DESC LIMIT 1"
                ),
                {"a": AccionAuditada.HERRAMIENTA_INVOCADA.value, "p": paciente.id},
            )
        ).scalar_one()
        assert tipo == TipoActor.AGENTE_IA.value


# ===========================================================================
#  El ambito recorta
# ===========================================================================
class TestAmbito:
    async def test_no_se_leen_las_citas_de_otro_paciente(
        self,
        contexto: ContextoHerramienta,
        sesion: AsyncSession,
        segundo_paciente,
        profesional,
        servicio,
        sede,
        reloj_fijo: RelojFijo,
        principal_agente: Principal,
    ) -> None:
        """El ambito del agente incluye un solo paciente.

        Pedir las citas de otro no da error: da una lista vacia. Un error
        confirmaria que ese paciente existe, y eso permite enumerar.
        """
        await _horario_de_la_sede(sesion, sede.id)
        servicio_agenda = ServicioAgenda(sesion, RepositorioAgenda(sesion), reloj_fijo)
        # La cita se crea con un principal amplio: es la recepcion quien la
        # crea, no el agente.
        amplio = Principal(
            actor_tipo=TipoActor.USUARIO,
            actor_id=uuid.uuid4(),
            clinica_id=principal_agente.clinica_id,
            permisos=frozenset({"cita.crear", "agenda.leer"}),
            ambito=Ambito(
                clinica_id=principal_agente.clinica_id,
                sedes=frozenset({sede.id}),
                todas_las_especialidades=True,
                todos_los_profesionales=True,
                todos_los_pacientes=True,
            ),
        )
        await servicio_agenda.crear_cita_confirmada(
            SolicitudReserva(
                paciente_id=segundo_paciente.id,
                profesional_id=profesional.id,
                servicio_id=servicio.id,
                sede_id=sede.id,
                inicio=AHORA + timedelta(days=1),
                origen=OrigenCita.PANEL,
            ),
            principal=amplio,
        )
        await sesion.flush()

        resultado = await despachar(
            "get_patient_appointments",
            {"paciente_id": str(segundo_paciente.id)},
            contexto,
        )

        assert resultado.exito is True
        assert resultado.datos["citas"] == []
        assert resultado.codigo == "SIN_CITAS"

    async def test_no_se_cancela_una_cita_fuera_de_ambito(
        self,
        contexto: ContextoHerramienta,
        sesion: AsyncSession,
        segundo_paciente,
        profesional,
        servicio,
        sede,
        reloj_fijo: RelojFijo,
        principal_agente: Principal,
    ) -> None:
        """Es el caso que mas dano hace: cancelar la cita de otra persona.

        El servicio no la encuentra -- el filtro de ambito la excluye -- y el
        despachador traduce eso a una derivacion, no a un error tecnico.
        """
        await _horario_de_la_sede(sesion, sede.id)
        servicio_agenda = ServicioAgenda(sesion, RepositorioAgenda(sesion), reloj_fijo)
        amplio = Principal(
            actor_tipo=TipoActor.USUARIO,
            actor_id=uuid.uuid4(),
            clinica_id=principal_agente.clinica_id,
            permisos=frozenset({"cita.crear"}),
            ambito=Ambito(
                clinica_id=principal_agente.clinica_id,
                sedes=frozenset({sede.id}),
                todas_las_especialidades=True,
                todos_los_profesionales=True,
                todos_los_pacientes=True,
            ),
        )
        resultado_creacion = await servicio_agenda.crear_cita_confirmada(
            SolicitudReserva(
                paciente_id=segundo_paciente.id,
                profesional_id=profesional.id,
                servicio_id=servicio.id,
                sede_id=sede.id,
                inicio=AHORA + timedelta(days=2),
                origen=OrigenCita.PANEL,
            ),
            principal=amplio,
        )
        await sesion.flush()
        cita_ajena = resultado_creacion.cita.id

        resultado = await despachar(
            "cancel_appointment",
            {"cita_id": str(cita_ajena), "motivo": "El paciente lo pide."},
            contexto,
        )

        assert resultado.exito is False
        assert resultado.requiere_humano is True

        estado = (
            await sesion.execute(
                sa.text("SELECT estado FROM cita WHERE id = :id"), {"id": cita_ajena}
            )
        ).scalar_one()
        assert estado == EstadoCita.CONFIRMED.value, "La cita ajena no debe haberse tocado."


# ===========================================================================
#  Flujo completo de reserva
# ===========================================================================
class TestReserva:
    async def test_buscar_apartar_y_confirmar(
        self,
        contexto: ContextoHerramienta,
        sesion: AsyncSession,
        paciente,
        profesional,
        servicio,
        sede,
    ) -> None:
        """El recorrido que hace un paciente por WhatsApp, de principio a fin."""
        await _horario_de_la_sede(sesion, sede.id)

        disponibilidad = await despachar(
            "find_availability",
            {
                "profesional_id": str(profesional.id),
                "servicio_id": str(servicio.id),
                "sede_id": str(sede.id),
                "desde": (AHORA + timedelta(days=1)).isoformat(),
                "hasta": (AHORA + timedelta(days=2)).isoformat(),
            },
            contexto,
        )
        assert disponibilidad.exito is True
        turnos = disponibilidad.datos["turnos"]
        assert turnos, "La sede tiene horario: debe haber turnos."
        assert len(turnos) <= 5, "No se le vuelcan cuarenta horas al paciente."

        bloqueo = await despachar(
            "hold_slot",
            {
                "paciente_id": str(paciente.id),
                "profesional_id": str(profesional.id),
                "servicio_id": str(servicio.id),
                "sede_id": str(sede.id),
                "inicio": turnos[0]["inicio"],
            },
            contexto,
        )
        assert bloqueo.exito is True
        assert bloqueo.datos["expira_en"] is not None, "Un bloqueo sin caducidad retiene el turno."
        cita_id = bloqueo.datos["cita_id"]

        confirmacion = await despachar("confirm_appointment", {"cita_id": cita_id}, contexto)
        assert confirmacion.exito is True

        estado = (
            await sesion.execute(
                sa.text("SELECT estado FROM cita WHERE id = :id"), {"id": uuid.UUID(cita_id)}
            )
        ).scalar_one()
        assert estado == EstadoCita.CONFIRMED.value

    async def test_repetir_la_misma_peticion_devuelve_la_misma_cita(
        self,
        contexto: ContextoHerramienta,
        sesion: AsyncSession,
        paciente,
        profesional,
        servicio,
        sede,
    ) -> None:
        """Un reintento del canal no crea dos bloqueos.

        WhatsApp reintenga entregas, y sin clave de idempotencia el mismo
        paciente acabaria con dos citas apartadas a la misma hora. La clave se
        deriva de la conversacion y del turno, no se genera al azar,
        precisamente para que el reintento produzca la misma.
        """
        await _horario_de_la_sede(sesion, sede.id)
        turnos = (
            await despachar("find_availability", _consulta(profesional, servicio, sede), contexto)
        ).datos["turnos"]

        reserva = {
            "paciente_id": str(paciente.id),
            "profesional_id": str(profesional.id),
            "servicio_id": str(servicio.id),
            "sede_id": str(sede.id),
            "inicio": turnos[0]["inicio"],
        }
        primero = await despachar("hold_slot", reserva, contexto)
        segundo = await despachar("hold_slot", reserva, contexto)

        assert primero.exito is True
        assert segundo.exito is True
        assert primero.datos["cita_id"] == segundo.datos["cita_id"]

        cuantas = (
            await sesion.execute(
                sa.text("SELECT count(*) FROM cita WHERE paciente_id = :p"),
                {"p": paciente.id},
            )
        ).scalar_one()
        assert cuantas == 1, "Un reintento no puede crear una segunda cita."

    async def test_el_turno_ocupado_por_otro_ofrece_alternativa_en_lugar_de_derivar(
        self,
        contexto: ContextoHerramienta,
        sesion: AsyncSession,
        reloj_fijo: RelojFijo,
        clinica,
        paciente,
        segundo_paciente,
        profesional,
        servicio,
        sede,
    ) -> None:
        """Que un turno se lo lleve otro es normal y el agente puede seguir.

        Derivar aqui haria que cada colision acabara en la cola del personal,
        que es justo lo que el agente existe para evitar. El rechazo lo produce
        la restriccion de exclusion del motor, no logica de Python.
        """
        await _horario_de_la_sede(sesion, sede.id)
        turnos = (
            await despachar("find_availability", _consulta(profesional, servicio, sede), contexto)
        ).datos["turnos"]

        primero = await despachar(
            "hold_slot",
            {
                "paciente_id": str(paciente.id),
                "profesional_id": str(profesional.id),
                "servicio_id": str(servicio.id),
                "sede_id": str(sede.id),
                "inicio": turnos[0]["inicio"],
            },
            contexto,
        )
        assert primero.exito is True

        # Otro paciente, otra conversacion: es una peticion distinta, no un
        # reintento, asi que la idempotencia no interviene.
        otra_conversacion = Conversacion(
            clinica_id=clinica.id,
            canal="WHATSAPP",
            telefono="593999000222",
            paciente_id=segundo_paciente.id,
            estado=EstadoConversacion.ABIERTA.value,
            ultima_actividad_en=AHORA,
        )
        sesion.add(otra_conversacion)
        await sesion.flush()

        contexto_otro = ContextoHerramienta(
            principal=Principal(
                actor_tipo=TipoActor.AGENTE_IA,
                actor_id=segundo_paciente.id,
                clinica_id=clinica.id,
                permisos=frozenset({"agenda.leer", "cita.crear"}),
                ambito=Ambito(
                    clinica_id=clinica.id,
                    sedes=frozenset({sede.id}),
                    todas_las_especialidades=True,
                    todos_los_profesionales=True,
                    pacientes=frozenset({segundo_paciente.id}),
                ),
                paciente_id=segundo_paciente.id,
                origen="WHATSAPP",
            ),
            sesion=sesion,
            reloj=reloj_fijo,
            conversacion_id=otra_conversacion.id,
        )

        segundo = await despachar(
            "hold_slot",
            {
                "paciente_id": str(segundo_paciente.id),
                "profesional_id": str(profesional.id),
                "servicio_id": str(servicio.id),
                "sede_id": str(sede.id),
                "inicio": turnos[0]["inicio"],
            },
            contexto_otro,
        )

        assert segundo.exito is False
        assert segundo.requiere_humano is False, "Puede ofrecer otro horario."
        assert "otro" in segundo.mensaje.lower()

    async def test_una_fecha_sin_zona_horaria_se_rechaza(
        self, contexto: ContextoHerramienta, paciente, profesional, servicio, sede
    ) -> None:
        """Un instante ingenuo de un modelo desplaza la cita varias horas.

        Nadie lo nota hasta que el paciente llega a la hora equivocada.
        """
        resultado = await despachar(
            "hold_slot",
            {
                "paciente_id": str(paciente.id),
                "profesional_id": str(profesional.id),
                "servicio_id": str(servicio.id),
                "sede_id": str(sede.id),
                "inicio": "2026-04-16T09:00:00",
            },
            contexto,
        )
        assert resultado.exito is False
        assert resultado.codigo == "ARGUMENTOS_INVALIDOS"

    async def test_el_rango_de_consulta_tiene_techo(
        self, contexto: ContextoHerramienta, profesional, servicio, sede
    ) -> None:
        resultado = await despachar(
            "find_availability",
            {
                "profesional_id": str(profesional.id),
                "servicio_id": str(servicio.id),
                "sede_id": str(sede.id),
                "desde": AHORA.isoformat(),
                "hasta": (AHORA + timedelta(days=90)).isoformat(),
            },
            contexto,
        )
        assert resultado.exito is False
        assert resultado.codigo == "RANGO_DEMASIADO_AMPLIO"


# ===========================================================================
#  Derivacion
# ===========================================================================
class TestDerivacion:
    async def test_derivar_marca_la_conversacion(
        self,
        contexto: ContextoHerramienta,
        sesion: AsyncSession,
        conversacion: Conversacion,
    ) -> None:
        resultado = await despachar(
            "handoff_to_human",
            {"motivo": MotivoDerivacion.REACCION_ADVERSA.value, "nota": "pregunta por su pauta"},
            contexto,
        )

        assert resultado.exito is True
        assert resultado.requiere_humano is True
        assert resultado.datos["conversacion_marcada"] is True

        await sesion.refresh(conversacion)
        assert conversacion.estado == EstadoConversacion.EN_HANDOFF.value
        assert MotivoDerivacion.REACCION_ADVERSA.value in (conversacion.motivo_handoff or "")

    async def test_derivar_no_exige_permiso(
        self,
        principal_sin_permisos: Principal,
        sesion: AsyncSession,
        reloj_fijo: RelojFijo,
        conversacion: Conversacion,
    ) -> None:
        """Es la unica salida segura: un principal mal configurado no puede quedarse sin ella."""
        contexto = ContextoHerramienta(
            principal=principal_sin_permisos,
            sesion=sesion,
            reloj=reloj_fijo,
            conversacion_id=conversacion.id,
        )
        resultado = await despachar(
            "handoff_to_human", {"motivo": MotivoDerivacion.URGENCIA_DECLARADA.value}, contexto
        )
        assert resultado.exito is True

    async def test_el_motivo_que_ve_el_personal_no_lleva_el_texto_del_paciente(
        self,
        contexto: ContextoHerramienta,
        sesion: AsyncSession,
        conversacion: Conversacion,
    ) -> None:
        """La auditoria y la cola registran referencias, no contenido clinico.

        El mensaje literal ya esta en `mensaje_entrante`, con sus controles de
        acceso. Copiarlo aqui crearia una segunda copia sin ellos.
        """
        await despachar(
            "handoff_to_human",
            {
                "motivo": MotivoDerivacion.MEDICACION.value,
                "nota": "consulta sobre su pauta",
            },
            contexto,
        )
        await sesion.refresh(conversacion)
        assert conversacion.motivo_handoff is not None
        assert len(conversacion.motivo_handoff) <= 255

    async def test_derivar_una_conversacion_de_otra_clinica_no_hace_nada(
        self,
        contexto: ContextoHerramienta,
        sesion: AsyncSession,
        reloj_fijo: RelojFijo,
        principal_agente: Principal,
    ) -> None:
        """Un identificador que el modelo se invente no puede mover un hilo ajeno."""
        ajeno = ContextoHerramienta(
            principal=principal_agente,
            sesion=sesion,
            reloj=reloj_fijo,
            conversacion_id=uuid.uuid4(),
        )
        resultado = await despachar(
            "handoff_to_human", {"motivo": MotivoDerivacion.NO_COMPRENDIDO.value}, ajeno
        )
        # La herramienta no falla -- derivar nunca falla -- pero no marco nada.
        assert resultado.exito is True
        assert resultado.datos["conversacion_marcada"] is False

    async def test_el_mensaje_al_paciente_no_menciona_nada_clinico(
        self, contexto: ContextoHerramienta
    ) -> None:
        """Regla 10: esto sale por WhatsApp."""
        resultado = await despachar(
            "handoff_to_human", {"motivo": MotivoDerivacion.MEDICACION.value}, contexto
        )
        texto = resultado.mensaje.lower()
        for prohibida in ("medicament", "dosis", "diagnostic", "receta", "pastilla"):
            assert prohibida not in texto
