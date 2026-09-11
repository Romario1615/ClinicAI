"""Pruebas del barrido de bloqueos temporales vencidos.

Es un trabajo corto y su ausencia es cara: sin el, cada paciente que abandona
la conversacion de WhatsApp a medias deja un turno retenido. La agenda pierde
capacidad de forma invisible, porque ese turno no aparece ni como libre ni
como una cita real.

Lo que se verifica:

* Que cancele **solo** lo vencido. El limite exacto importa: un bloqueo que
  vence dentro de un segundo todavia es valido, y cancelarlo le quitaria el
  turno a alguien que esta a punto de confirmar.
* Que el turno quede realmente libre despues, comprobado reservandolo.
* Que deje auditoria, para que «por que se anulo mi cita» tenga respuesta.
* Que el principal del sistema **no** tenga permisos clinicos.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita, CitaHistorial, EstadoCita, OrigenCita
from app.modulos.agenda.repositorio import RepositorioAgenda
from app.modulos.agenda.servicios import ServicioAgenda, SolicitudReserva
from app.modulos.auditoria.modelos import Auditoria
from app.nucleo.auditoria import AccionAuditada
from app.nucleo.autorizacion import Ambito, Principal, TipoActor, principal_sistema
from app.nucleo.errores import PermisoDenegado
from app.nucleo.reloj import RelojFijo
from app.tareas.agenda import TAMANO_LOTE, expirar_bloqueos

pytestmark = [pytest.mark.integracion, pytest.mark.asyncio]

AHORA = datetime(2026, 4, 15, 14, 0, tzinfo=UTC)
MINUTOS_BLOQUEO = 10


@pytest.fixture
def reloj_fijo() -> RelojFijo:
    return RelojFijo(AHORA)


@pytest.fixture
def principal_recepcion(clinica, sede) -> Principal:  # type: ignore[no-untyped-def]
    return Principal(
        actor_tipo=TipoActor.USUARIO,
        actor_id=uuid.uuid4(),
        clinica_id=clinica.id,
        permisos=frozenset({"agenda.leer", "cita.crear", "cita.cancelar"}),
        ambito=Ambito(
            clinica_id=clinica.id,
            sedes=frozenset({sede.id}),
            todos_los_profesionales=True,
            todos_los_pacientes=True,
        ),
    )


@pytest.fixture
def servicio_agenda(sesion: AsyncSession, reloj_fijo: RelojFijo) -> ServicioAgenda:
    return ServicioAgenda(
        sesion,
        RepositorioAgenda(sesion),
        reloj_fijo,
        minutos_expiracion_held=MINUTOS_BLOQUEO,
    )


class _GestorDeUnaSesion:
    """Entrega siempre la sesion aislada de la prueba.

    El trabajo abre su propia sesion con el gestor, que es lo correcto en
    produccion: cada ejecucion es una unidad de trabajo independiente. Aqui se
    sustituye para que todo ocurra dentro de la transaccion que la prueba
    deshace al terminar.
    """

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def sesion(self):  # type: ignore[no-untyped-def]
        yield self._sesion


async def _bloquear(
    servicio_agenda: ServicioAgenda,
    principal: Principal,
    *,
    paciente_id: uuid.UUID,
    profesional_id: uuid.UUID,
    servicio_id: uuid.UUID,
    sede_id: uuid.UUID,
    inicio: datetime,
) -> Cita:
    resultado = await servicio_agenda.bloquear_turno(
        SolicitudReserva(
            paciente_id=paciente_id,
            profesional_id=profesional_id,
            servicio_id=servicio_id,
            sede_id=sede_id,
            inicio=inicio,
            origen=OrigenCita.WHATSAPP,
        ),
        principal=principal,
    )
    return resultado.cita


class TestBarridoDeBloqueos:
    async def test_cancela_lo_vencido_y_respeta_lo_vigente(
        self,
        sesion: AsyncSession,
        servicio_agenda: ServicioAgenda,
        reloj_fijo: RelojFijo,
        principal_recepcion: Principal,
        clinica,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        paciente,  # type: ignore[no-untyped-def]
        segundo_paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
        servicio,  # type: ignore[no-untyped-def]
    ) -> None:
        """El limite exacto importa.

        Cancelar un bloqueo que todavia no vencio le quitaria el turno a
        alguien que esta a punto de confirmar.
        """
        vencido = await _bloquear(
            servicio_agenda,
            principal_recepcion,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            servicio_id=servicio.id,
            sede_id=sede.id,
            inicio=AHORA + timedelta(days=1),
        )
        # El segundo se crea despues de adelantar el reloj, de modo que su
        # plazo empieza mas tarde y siga vigente cuando corra el barrido.
        reloj_fijo.avanzar(minutes=MINUTOS_BLOQUEO)
        vigente = await _bloquear(
            servicio_agenda,
            principal_recepcion,
            paciente_id=segundo_paciente.id,
            profesional_id=profesional.id,
            servicio_id=servicio.id,
            sede_id=sede.id,
            inicio=AHORA + timedelta(days=2),
        )
        # Justo en el instante en que el primero ya vencio y el segundo no.
        reloj_fijo.avanzar(seconds=1)

        liberados = await expirar_bloqueos(
            {
                "gestor_bd": _GestorDeUnaSesion(sesion),
                "reloj": reloj_fijo,
                "configuracion": _configuracion_falsa(),
            }
        )

        assert liberados == 1
        await sesion.refresh(vencido)
        await sesion.refresh(vigente)
        assert vencido.estado == EstadoCita.CANCELLED.value
        assert vencido.expira_en is None
        assert vencido.motivo_cancelacion is not None
        assert vigente.estado == EstadoCita.HELD.value

    async def test_el_turno_queda_realmente_libre(
        self,
        sesion: AsyncSession,
        servicio_agenda: ServicioAgenda,
        reloj_fijo: RelojFijo,
        principal_recepcion: Principal,
        sede,  # type: ignore[no-untyped-def]
        paciente,  # type: ignore[no-untyped-def]
        segundo_paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
        servicio,  # type: ignore[no-untyped-def]
    ) -> None:
        """La comprobacion que importa de verdad.

        Que la fila diga `CANCELLED` no basta: lo que hace falta es que la
        restriccion de exclusion deje de considerarla, y eso solo se verifica
        reservando el mismo turno otra vez.
        """
        inicio = AHORA + timedelta(days=1)
        await _bloquear(
            servicio_agenda,
            principal_recepcion,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            servicio_id=servicio.id,
            sede_id=sede.id,
            inicio=inicio,
        )
        reloj_fijo.avanzar(minutes=MINUTOS_BLOQUEO + 1)

        await expirar_bloqueos(
            {
                "gestor_bd": _GestorDeUnaSesion(sesion),
                "reloj": reloj_fijo,
                "configuracion": _configuracion_falsa(),
            }
        )

        segunda = await _bloquear(
            servicio_agenda,
            principal_recepcion,
            paciente_id=segundo_paciente.id,
            profesional_id=profesional.id,
            servicio_id=servicio.id,
            sede_id=sede.id,
            inicio=inicio,
        )
        assert segunda.estado == EstadoCita.HELD.value

    async def test_deja_auditoria_e_historial(
        self,
        sesion: AsyncSession,
        servicio_agenda: ServicioAgenda,
        reloj_fijo: RelojFijo,
        principal_recepcion: Principal,
        sede,  # type: ignore[no-untyped-def]
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
        servicio,  # type: ignore[no-untyped-def]
    ) -> None:
        """«Por que se anulo mi cita» tiene que tener respuesta."""
        cita = await _bloquear(
            servicio_agenda,
            principal_recepcion,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            servicio_id=servicio.id,
            sede_id=sede.id,
            inicio=AHORA + timedelta(days=1),
        )
        reloj_fijo.avanzar(minutes=MINUTOS_BLOQUEO + 1)

        await expirar_bloqueos(
            {
                "gestor_bd": _GestorDeUnaSesion(sesion),
                "reloj": reloj_fijo,
                "configuracion": _configuracion_falsa(),
            }
        )

        entradas = list(
            (
                await sesion.execute(
                    sa.select(Auditoria).where(
                        Auditoria.entidad_id == cita.id,
                        Auditoria.accion == AccionAuditada.CITA_CANCELADA.value,
                    )
                )
            ).scalars()
        )
        assert len(entradas) == 1
        assert entradas[0].actor_tipo == TipoActor.SISTEMA.value
        assert entradas[0].motivo is not None

        historial = list(
            (
                await sesion.execute(
                    sa.select(CitaHistorial).where(CitaHistorial.cita_id == cita.id)
                )
            ).scalars()
        )
        assert any(h.estado_nuevo == EstadoCita.CANCELLED.value for h in historial)

    async def test_sin_bloqueos_vencidos_no_hace_nada(
        self, sesion: AsyncSession, reloj_fijo: RelojFijo
    ) -> None:
        liberados = await expirar_bloqueos(
            {
                "gestor_bd": _GestorDeUnaSesion(sesion),
                "reloj": reloj_fijo,
                "configuracion": _configuracion_falsa(),
            }
        )
        assert liberados == 0

    async def test_el_lote_esta_acotado(self) -> None:
        """Un atasco acumulado no puede producir una transaccion enorme.

        Bloquearia miles de filas de `cita` durante minutos, justo sobre la
        tabla que la API necesita para reservar.
        """
        assert 0 < TAMANO_LOTE <= 500


class TestPermisos:
    async def test_el_principal_del_sistema_no_tiene_permisos_clinicos(self) -> None:
        """Un trabajo programado cancela bloqueos; no escribe historia clinica.

        La restriccion no es una convencion: el principal del sistema no lleva
        esos permisos, asi que la capacidad no existe.
        """
        sistema = principal_sistema()

        assert sistema.tiene_permiso("cita.cancelar")
        for prohibido in (
            "historia_clinica.escribir",
            "historia_clinica.leer",
            "receta.crear",
            "receta.confirmar",
        ):
            assert not sistema.tiene_permiso(prohibido), prohibido

    async def test_un_principal_sin_permiso_no_puede_barrer(
        self,
        servicio_agenda: ServicioAgenda,
        clinica,  # type: ignore[no-untyped-def]
    ) -> None:
        sin_permisos = Principal(
            actor_tipo=TipoActor.USUARIO,
            actor_id=uuid.uuid4(),
            clinica_id=clinica.id,
            permisos=frozenset(),
            ambito=Ambito(clinica_id=clinica.id),
        )

        with pytest.raises(PermisoDenegado):
            await servicio_agenda.expirar_bloqueos_vencidos(principal=sin_permisos)


def _configuracion_falsa() -> object:
    """Configuracion minima: el trabajo solo lee `minutos_expiracion_held`."""

    class _Configuracion:
        minutos_expiracion_held = MINUTOS_BLOQUEO

    return _Configuracion()
