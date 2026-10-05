"""Pruebas de la lista de espera.

La carrera entre dos aceptaciones esta en `pruebas/concurrencia/`. Aqui se
verifica la logica de cola: a quien se ofrece, en que orden, y que pasa cuando
nadie responde.

Lo que mas importa:

* **Se ofrece a una sola persona a la vez.** Avisar a todos produce un ganador
  y varios avisos de «ya no esta disponible», y a la tercera vez el paciente
  deja de mirarlos.
* **Quien no puede llegar no recibe la oferta.** Ofrecer un hueco de dentro de
  veinte minutos a quien necesita cuatro horas produce una aceptacion y una
  inasistencia, que es peor que no ofrecerlo.
* **Quien nunca responde deja de bloquear la cola.** Cada oferta ignorada
  retiene el turno hasta que vence; el hueco se pierde igual, pero mas tarde y
  para todos.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita, CitaHistorial, EstadoCita
from app.modulos.lista_espera.modelos import (
    EntradaListaEspera,
    EstadoEspera,
    EstadoOferta,
    OfertaTurno,
    PrioridadEspera,
)
from app.modulos.lista_espera.servicios import (
    MAXIMO_OFERTAS_VENCIDAS,
    MAXIMO_PROFUNDIDAD_CADENA,
    ServicioListaEspera,
)
from app.modulos.pacientes.modelos import Consentimiento, TipoConsentimiento
from app.modulos.profesionales.modelos import Profesional, ProfesionalSede
from app.nucleo.auditoria import AccionAuditada
from app.nucleo.autorizacion import Ambito, Principal, TipoActor, principal_sistema
from app.nucleo.errores import (
    ConflictoEstado,
    OfertaExpirada,
    OfertaYaResuelta,
    PermisoDenegado,
    RecursoNoEncontrado,
)
from app.nucleo.reloj import RelojFijo

pytestmark = [pytest.mark.integracion, pytest.mark.asyncio]

AHORA = datetime(2026, 4, 15, 14, 0, tzinfo=UTC)


@pytest.fixture
def reloj_fijo() -> RelojFijo:
    return RelojFijo(AHORA)


@pytest.fixture
def servicio_espera(sesion: AsyncSession, reloj_fijo: RelojFijo) -> ServicioListaEspera:
    return ServicioListaEspera(sesion, reloj_fijo, minutos_vigencia_oferta=30)


@pytest.fixture
def principal_recepcion(clinica, sede) -> Principal:  # type: ignore[no-untyped-def]
    return Principal(
        actor_tipo=TipoActor.USUARIO,
        actor_id=uuid.uuid4(),
        clinica_id=clinica.id,
        permisos=frozenset({"lista_espera.gestionar", "cita.crear", "agenda.leer"}),
        ambito=Ambito(
            clinica_id=clinica.id,
            sedes=frozenset({sede.id}),
            todas_las_especialidades=True,
            todos_los_profesionales=True,
            todos_los_pacientes=True,
        ),
    )


@pytest_asyncio.fixture
async def turno_liberado(
    sesion: AsyncSession,
    clinica,  # type: ignore[no-untyped-def]
    sede,  # type: ignore[no-untyped-def]
    paciente,  # type: ignore[no-untyped-def]
    profesional,  # type: ignore[no-untyped-def]
    servicio,  # type: ignore[no-untyped-def]
) -> Cita:
    """Cita cancelada dentro de dos dias: el hueco que se ofrece."""
    cita = Cita(
        clinica_id=clinica.id,
        sede_id=sede.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        servicio_id=servicio.id,
        inicio=AHORA + timedelta(days=2),
        duracion_minutos=30,
        minutos_preparacion=15,
        estado=EstadoCita.CANCELLED.value,
        motivo_cancelacion="Liberada para la prueba",
        cancelada_en=AHORA,
    )
    sesion.add(cita)
    await sesion.flush()
    return cita


async def _consentir(sesion: AsyncSession, paciente_id: uuid.UUID) -> None:
    """Da consentimiento de comunicacion al paciente.

    Hace falta para que la oferta se **comunique**. Y solo una oferta
    comunicada puede contar en contra del paciente al vencer: penalizar a quien
    nunca recibio el mensaje lo sacaria de la lista de espera sin haber hecho
    nada mal.
    """
    sesion.add(
        Consentimiento(
            paciente_id=paciente_id,
            tipo=TipoConsentimiento.COMUNICACION_WHATSAPP.value,
            otorgado=True,
            version_texto="v1",
            texto_hash="0" * 64,
            canal="PANEL",
        )
    )
    await sesion.flush()


async def _anotar(
    servicio_espera: ServicioListaEspera,
    principal: Principal,
    paciente_id: uuid.UUID,
    sede_id: uuid.UUID,
    especialidad_id: uuid.UUID,
    **extra: object,
) -> EntradaListaEspera:
    return await servicio_espera.anotar(
        principal=principal,
        paciente_id=paciente_id,
        sede_id=sede_id,
        especialidad_id=especialidad_id,
        **extra,  # type: ignore[arg-type]
    )


# ===========================================================================
#  Alta y baja
# ===========================================================================
class TestAlta:
    async def test_se_anota_un_paciente(
        self,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        paciente,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
    ) -> None:
        entrada = await _anotar(
            servicio_espera, principal_recepcion, paciente.id, sede.id, especialidad.id
        )
        assert entrada.estado == EstadoEspera.ACTIVA.value
        assert entrada.ofertas_realizadas == 0

    async def test_cita_previa_valida_se_vincula_a_la_entrada(
        self,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        paciente,  # type: ignore[no-untyped-def]
        clinica,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
        servicio,  # type: ignore[no-untyped-def]
        sesion: AsyncSession,
    ) -> None:
        cita = Cita(
            clinica_id=clinica.id,
            sede_id=sede.id,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            servicio_id=servicio.id,
            inicio=AHORA + timedelta(days=5),
            duracion_minutos=30,
            minutos_preparacion=15,
            estado=EstadoCita.CONFIRMED.value,
            confirmada_en=AHORA,
        )
        sesion.add(cita)
        await sesion.flush()

        entrada = await _anotar(
            servicio_espera,
            principal_recepcion,
            paciente.id,
            sede.id,
            especialidad.id,
            servicio_id=servicio.id,
            cita_previa_id=cita.id,
        )

        assert entrada.cita_previa_id == cita.id

    async def test_no_se_vincula_una_cita_de_otro_paciente(
        self,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        paciente,  # type: ignore[no-untyped-def]
        segundo_paciente,  # type: ignore[no-untyped-def]
        clinica,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
        servicio,  # type: ignore[no-untyped-def]
        sesion: AsyncSession,
    ) -> None:
        cita = Cita(
            clinica_id=clinica.id,
            sede_id=sede.id,
            paciente_id=segundo_paciente.id,
            profesional_id=profesional.id,
            servicio_id=servicio.id,
            inicio=AHORA + timedelta(days=5),
            duracion_minutos=30,
            minutos_preparacion=15,
            estado=EstadoCita.CONFIRMED.value,
            confirmada_en=AHORA,
        )
        sesion.add(cita)
        await sesion.flush()

        with pytest.raises(RecursoNoEncontrado, match="cita previa"):
            await _anotar(
                servicio_espera,
                principal_recepcion,
                paciente.id,
                sede.id,
                especialidad.id,
                servicio_id=servicio.id,
                cita_previa_id=cita.id,
            )

    async def test_no_se_anota_dos_veces_a_la_misma_especialidad(
        self,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        paciente,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
    ) -> None:
        """Dos entradas del mismo paciente competirian entre si por los
        mismos huecos, y recibiria dos ofertas del mismo turno."""
        await _anotar(servicio_espera, principal_recepcion, paciente.id, sede.id, especialidad.id)
        with pytest.raises(Exception, match=r"ix_espera_sin_duplicados|ya"):
            await _anotar(
                servicio_espera, principal_recepcion, paciente.id, sede.id, especialidad.id
            )

    async def test_sin_permiso_no_se_anota(
        self,
        servicio_espera: ServicioListaEspera,
        clinica,  # type: ignore[no-untyped-def]
        paciente,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
    ) -> None:
        sin_permiso = Principal(
            actor_tipo=TipoActor.USUARIO,
            actor_id=uuid.uuid4(),
            clinica_id=clinica.id,
            permisos=frozenset({"agenda.leer"}),
            ambito=Ambito(clinica_id=clinica.id, todas_las_sedes=True),
        )
        with pytest.raises(PermisoDenegado):
            await _anotar(servicio_espera, sin_permiso, paciente.id, sede.id, especialidad.id)

    async def test_una_sede_fuera_de_ambito_responde_404(
        self,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        paciente,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
    ) -> None:
        """404 y no 403: un 403 confirmaria que esa sede existe."""
        with pytest.raises(RecursoNoEncontrado):
            await _anotar(
                servicio_espera, principal_recepcion, paciente.id, uuid.uuid4(), especialidad.id
            )

    async def test_cancelar_marca_la_entrada(
        self,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        paciente,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
    ) -> None:
        entrada = await _anotar(
            servicio_espera, principal_recepcion, paciente.id, sede.id, especialidad.id
        )
        cancelada = await servicio_espera.cancelar(
            entrada.id, principal=principal_recepcion, motivo="El paciente ya no lo necesita"
        )
        assert cancelada.estado == EstadoEspera.CANCELADA.value

    async def test_no_se_cancela_dos_veces(
        self,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        paciente,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
    ) -> None:
        entrada = await _anotar(
            servicio_espera, principal_recepcion, paciente.id, sede.id, especialidad.id
        )
        await servicio_espera.cancelar(entrada.id, principal=principal_recepcion)
        with pytest.raises(ConflictoEstado):
            await servicio_espera.cancelar(entrada.id, principal=principal_recepcion)


# ===========================================================================
#  A quien se ofrece
# ===========================================================================
class TestOferta:
    async def test_sin_nadie_esperando_no_se_ofrece(
        self,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        turno_liberado: Cita,
    ) -> None:
        """No es un error: la mayoria de las cancelaciones ocurren sin nadie
        esperando esa especialidad."""
        resultado = await servicio_espera.ofrecer_turno(
            turno_liberado, principal=principal_recepcion
        )
        assert resultado.oferta is None

    async def test_se_ofrece_al_primero_de_la_cola(
        self,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        turno_liberado: Cita,
        paciente,  # type: ignore[no-untyped-def]
        segundo_paciente,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
        reloj_fijo: RelojFijo,
    ) -> None:
        primero = await _anotar(
            servicio_espera, principal_recepcion, paciente.id, sede.id, especialidad.id
        )
        reloj_fijo.avanzar(minutes=5)
        await _anotar(
            servicio_espera, principal_recepcion, segundo_paciente.id, sede.id, especialidad.id
        )

        resultado = await servicio_espera.ofrecer_turno(
            turno_liberado, principal=principal_recepcion
        )

        assert resultado.oferta is not None
        assert resultado.oferta.lista_espera_id == primero.id
        assert resultado.auditoria[0].accion == AccionAuditada.OFERTA_ENVIADA

    async def test_la_prioridad_alta_va_primero(
        self,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        turno_liberado: Cita,
        paciente,  # type: ignore[no-untyped-def]
        segundo_paciente,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
        reloj_fijo: RelojFijo,
    ) -> None:
        """Aunque lleve menos tiempo esperando."""
        await _anotar(servicio_espera, principal_recepcion, paciente.id, sede.id, especialidad.id)
        reloj_fijo.avanzar(minutes=5)
        urgente = await _anotar(
            servicio_espera,
            principal_recepcion,
            segundo_paciente.id,
            sede.id,
            especialidad.id,
            prioridad=PrioridadEspera.ALTA.value,
        )

        resultado = await servicio_espera.ofrecer_turno(
            turno_liberado, principal=principal_recepcion
        )

        assert resultado.oferta is not None
        assert resultado.oferta.lista_espera_id == urgente.id

    async def test_no_se_ofrece_a_quien_no_puede_llegar(
        self,
        sesion: AsyncSession,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        clinica,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
        servicio,  # type: ignore[no-untyped-def]
    ) -> None:
        """Aceptar un hueco al que no se llega produce una inasistencia, que
        es peor que no recibir la oferta."""
        inminente = Cita(
            clinica_id=clinica.id,
            sede_id=sede.id,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            servicio_id=servicio.id,
            # Dentro de una hora.
            inicio=AHORA + timedelta(hours=1),
            duracion_minutos=30,
            minutos_preparacion=15,
            estado=EstadoCita.CANCELLED.value,
            motivo_cancelacion="Liberada",
            cancelada_en=AHORA,
        )
        sesion.add(inminente)
        await sesion.flush()

        # El paciente necesita cuatro horas de antelacion.
        await _anotar(
            servicio_espera,
            principal_recepcion,
            paciente.id,
            sede.id,
            especialidad.id,
            horas_antelacion_minima=4,
        )

        resultado = await servicio_espera.ofrecer_turno(inminente, principal=principal_recepcion)
        assert resultado.oferta is None

    async def test_no_se_ofrece_a_quien_espera_a_otro_profesional(
        self,
        sesion: AsyncSession,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        turno_liberado: Cita,
        paciente,  # type: ignore[no-untyped-def]
        clinica,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
    ) -> None:
        """Quien espera a un profesional concreto no acepta cualquier hueco.

        El profesional alternativo se crea de verdad y no se inventa un
        identificador: con uno inventado, la clave externa rechazaria la fila
        y la prueba pasaria por el motivo equivocado.
        """
        otro = Profesional(
            clinica_id=clinica.id,
            especialidad_id=especialidad.id,
            nombre="Otro",
            apellido="Profesional",
            numero_registro_profesional=f"REG-OTRO-{uuid.uuid4().hex[:6]}",
        )
        sesion.add(otro)
        await sesion.flush()

        # El alta ahora valida tambien que el profesional atienda en la sede.
        sesion.add(ProfesionalSede(profesional_id=otro.id, sede_id=sede.id))
        await sesion.flush()

        await _anotar(
            servicio_espera,
            principal_recepcion,
            paciente.id,
            sede.id,
            especialidad.id,
            profesional_id=otro.id,
        )
        resultado = await servicio_espera.ofrecer_turno(
            turno_liberado, principal=principal_recepcion
        )
        assert resultado.oferta is None

    async def test_respeta_las_fechas_disponibles_de_la_persona(
        self,
        sesion: AsyncSession,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        turno_liberado: Cita,
        paciente,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
    ) -> None:
        fecha_turno = turno_liberado.inicio.astimezone(ZoneInfo("America/Guayaquil")).date()
        entrada = await _anotar(
            servicio_espera,
            principal_recepcion,
            paciente.id,
            sede.id,
            especialidad.id,
            disponible_desde=fecha_turno + timedelta(days=1),
            disponible_hasta=fecha_turno + timedelta(days=5),
        )

        fuera_de_rango = await servicio_espera.ofrecer_turno(
            turno_liberado, principal=principal_recepcion
        )
        assert fuera_de_rango.oferta is None

        entrada.disponible_desde = fecha_turno
        entrada.disponible_hasta = fecha_turno
        await sesion.flush()
        dentro_de_rango = await servicio_espera.ofrecer_turno(
            turno_liberado, principal=principal_recepcion
        )
        assert dentro_de_rango.oferta is not None
        assert dentro_de_rango.oferta.lista_espera_id == entrada.id

    async def test_respeta_dias_y_franja_horaria_locales(
        self,
        sesion: AsyncSession,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        turno_liberado: Cita,
        paciente,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
    ) -> None:
        local = turno_liberado.inicio.astimezone(ZoneInfo("America/Guayaquil"))
        entrada = await _anotar(
            servicio_espera,
            principal_recepcion,
            paciente.id,
            sede.id,
            especialidad.id,
            preferencias={
                "dias_semana": [local.weekday()],
                "hora_desde": "11:00:00",
                "hora_hasta": "12:00:00",
            },
        )

        fuera_de_franja = await servicio_espera.ofrecer_turno(
            turno_liberado, principal=principal_recepcion
        )
        assert fuera_de_franja.oferta is None

        entrada.preferencias = {
            "dias_semana": [local.weekday()],
            "hora_desde": "08:00:00",
            "hora_hasta": "10:00:00",
        }
        await sesion.flush()
        dentro_de_franja = await servicio_espera.ofrecer_turno(
            turno_liberado, principal=principal_recepcion
        )
        assert dentro_de_franja.oferta is not None
        assert dentro_de_franja.oferta.lista_espera_id == entrada.id

    async def test_no_se_ofrece_dos_veces_el_mismo_turno(
        self,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        turno_liberado: Cita,
        paciente,  # type: ignore[no-untyped-def]
        segundo_paciente,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
    ) -> None:
        """Dos barridos simultaneos del worker no pueden ofrecer el mismo
        hueco a dos personas."""
        await _anotar(servicio_espera, principal_recepcion, paciente.id, sede.id, especialidad.id)
        await _anotar(
            servicio_espera, principal_recepcion, segundo_paciente.id, sede.id, especialidad.id
        )

        primera = await servicio_espera.ofrecer_turno(turno_liberado, principal=principal_recepcion)
        segunda = await servicio_espera.ofrecer_turno(turno_liberado, principal=principal_recepcion)

        assert primera.oferta is not None
        assert segunda.oferta is None


# ===========================================================================
#  Respuesta
# ===========================================================================
class TestRespuesta:
    @pytest_asyncio.fixture
    async def oferta_viva(
        self,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        turno_liberado: Cita,
        segundo_paciente,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
    ):  # type: ignore[no-untyped-def]
        await _anotar(
            servicio_espera,
            principal_recepcion,
            segundo_paciente.id,
            sede.id,
            especialidad.id,
        )
        resultado = await servicio_espera.ofrecer_turno(
            turno_liberado, principal=principal_recepcion
        )
        assert resultado.oferta is not None
        return resultado.oferta

    async def test_aceptar_crea_la_cita(
        self,
        sesion: AsyncSession,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        oferta_viva,  # type: ignore[no-untyped-def]
        turno_liberado: Cita,
        segundo_paciente,  # type: ignore[no-untyped-def]
    ) -> None:
        resultado = await servicio_espera.aceptar_oferta(
            oferta_viva.id, principal=principal_recepcion
        )

        assert resultado.cita is not None
        assert resultado.cita.estado == EstadoCita.CONFIRMED.value
        assert resultado.cita.paciente_id == segundo_paciente.id
        # Conserva el vinculo con el hueco original: es lo que permite
        # reconstruir la cadena de turnos liberados.
        assert resultado.cita.cita_origen_id == turno_liberado.id
        assert resultado.cita.origen == "LISTA_ESPERA"
        assert {e.accion for e in resultado.auditoria} == {
            AccionAuditada.OFERTA_ACEPTADA,
            AccionAuditada.CITA_CREADA,
        }

    async def test_aceptar_cierra_la_entrada(
        self,
        sesion: AsyncSession,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        oferta_viva,  # type: ignore[no-untyped-def]
    ) -> None:
        await servicio_espera.aceptar_oferta(oferta_viva.id, principal=principal_recepcion)

        entrada = await sesion.get(EntradaListaEspera, oferta_viva.lista_espera_id)
        assert entrada is not None
        assert entrada.estado == EstadoEspera.CUMPLIDA.value
        assert entrada.cita_resultante_id is not None

    async def test_aceptar_cita_temprana_cancela_la_previa_y_ofrece_su_hueco(
        self,
        sesion: AsyncSession,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        oferta_viva,  # type: ignore[no-untyped-def]
        turno_liberado: Cita,
        paciente,  # type: ignore[no-untyped-def]
        segundo_paciente,  # type: ignore[no-untyped-def]
        clinica,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
        servicio,  # type: ignore[no-untyped-def]
    ) -> None:
        # Quien ya tiene una cita más lejana recibe la primera oferta. La otra
        # persona de la cola debe recibir, dentro de la misma operación, el
        # horario que esa aceptación acaba de liberar.
        previa = Cita(
            clinica_id=clinica.id,
            sede_id=sede.id,
            paciente_id=segundo_paciente.id,
            profesional_id=profesional.id,
            servicio_id=servicio.id,
            inicio=AHORA + timedelta(days=5),
            duracion_minutos=30,
            minutos_preparacion=15,
            estado=EstadoCita.CONFIRMED.value,
            confirmada_en=AHORA,
        )
        sesion.add(previa)
        await sesion.flush()
        entrada_primera = await sesion.get(EntradaListaEspera, oferta_viva.lista_espera_id)
        assert entrada_primera is not None
        entrada_primera.servicio_id = servicio.id
        entrada_primera.cita_previa_id = previa.id
        await _anotar(
            servicio_espera,
            principal_recepcion,
            paciente.id,
            sede.id,
            servicio.especialidad_id,
            servicio_id=servicio.id,
        )

        resultado = await servicio_espera.aceptar_oferta(
            oferta_viva.id, principal=principal_recepcion
        )

        await sesion.refresh(previa)
        assert previa.estado == EstadoCita.CANCELLED.value
        assert previa.motivo_cancelacion and "lista de espera" in previa.motivo_cancelacion
        historial = await sesion.scalar(
            select(CitaHistorial).where(CitaHistorial.cita_id == previa.id)
        )
        assert historial is not None
        oferta_siguiente = await sesion.scalar(
            select(OfertaTurno).where(
                OfertaTurno.cita_liberada_id == previa.id,
                OfertaTurno.estado == EstadoOferta.OFRECIDA.value,
            )
        )
        assert oferta_siguiente is not None
        assert oferta_siguiente.lista_espera_id != entrada_primera.id
        assert any(a.accion == AccionAuditada.CITA_CANCELADA for a in resultado.auditoria)
        assert any(a.accion == AccionAuditada.OFERTA_ENVIADA for a in resultado.auditoria)

    async def test_si_el_turno_ofrecido_se_ocupa_la_cita_previa_se_conserva(
        self,
        sesion: AsyncSession,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        oferta_viva,  # type: ignore[no-untyped-def]
        turno_liberado: Cita,
        paciente,  # type: ignore[no-untyped-def]
        segundo_paciente,  # type: ignore[no-untyped-def]
        clinica,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
        servicio,  # type: ignore[no-untyped-def]
    ) -> None:
        previa = Cita(
            clinica_id=clinica.id,
            sede_id=sede.id,
            paciente_id=segundo_paciente.id,
            profesional_id=profesional.id,
            servicio_id=servicio.id,
            inicio=AHORA + timedelta(days=5),
            duracion_minutos=30,
            minutos_preparacion=15,
            estado=EstadoCita.CONFIRMED.value,
            confirmada_en=AHORA,
        )
        ocupante = Cita(
            clinica_id=clinica.id,
            sede_id=sede.id,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            servicio_id=servicio.id,
            inicio=turno_liberado.inicio,
            duracion_minutos=30,
            minutos_preparacion=15,
            estado=EstadoCita.CONFIRMED.value,
            confirmada_en=AHORA,
        )
        sesion.add_all([previa, ocupante])
        await sesion.flush()
        entrada = await sesion.get(EntradaListaEspera, oferta_viva.lista_espera_id)
        assert entrada is not None
        oferta_id = oferta_viva.id
        cita_liberada_id = turno_liberado.id
        entrada.servicio_id = servicio.id
        entrada.cita_previa_id = previa.id

        resultado = await servicio_espera.aceptar_oferta(oferta_id, principal=principal_recepcion)
        assert resultado.turno_ocupado
        await sesion.refresh(previa)
        await sesion.refresh(oferta_viva)
        await sesion.refresh(entrada)
        assert previa.estado == EstadoCita.CONFIRMED.value
        assert oferta_viva.estado == EstadoOferta.PERDIDA.value
        assert entrada.estado == EstadoEspera.ACTIVA.value
        assert (
            await sesion.scalar(
                select(Cita.id).where(
                    Cita.origen == "LISTA_ESPERA", Cita.cita_origen_id == cita_liberada_id
                )
            )
            is None
        )

    async def test_al_llegar_al_limite_no_se_ofrece_otro_eslabon(
        self,
        sesion: AsyncSession,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        oferta_viva,  # type: ignore[no-untyped-def]
        turno_liberado: Cita,
        paciente,  # type: ignore[no-untyped-def]
        segundo_paciente,  # type: ignore[no-untyped-def]
        clinica,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
        servicio,  # type: ignore[no-untyped-def]
    ) -> None:
        turno_liberado.profundidad_lista_espera = MAXIMO_PROFUNDIDAD_CADENA - 1
        previa = Cita(
            clinica_id=clinica.id,
            sede_id=sede.id,
            paciente_id=segundo_paciente.id,
            profesional_id=profesional.id,
            servicio_id=servicio.id,
            inicio=AHORA + timedelta(days=5),
            duracion_minutos=30,
            minutos_preparacion=15,
            estado=EstadoCita.CONFIRMED.value,
            confirmada_en=AHORA,
        )
        sesion.add(previa)
        await sesion.flush()
        entrada = await sesion.get(EntradaListaEspera, oferta_viva.lista_espera_id)
        assert entrada is not None
        entrada.servicio_id = servicio.id
        entrada.cita_previa_id = previa.id
        await _anotar(
            servicio_espera,
            principal_recepcion,
            paciente.id,
            sede.id,
            servicio.especialidad_id,
            servicio_id=servicio.id,
        )

        resultado = await servicio_espera.aceptar_oferta(
            oferta_viva.id, principal=principal_recepcion
        )

        assert resultado.cita is not None
        assert resultado.cita.profundidad_lista_espera == MAXIMO_PROFUNDIDAD_CADENA - 1
        assert previa.estado == EstadoCita.CANCELLED.value
        assert previa.profundidad_lista_espera == MAXIMO_PROFUNDIDAD_CADENA
        oferta_mas_profunda = await sesion.scalar(
            select(OfertaTurno.id).where(
                OfertaTurno.cita_liberada_id == previa.id,
                OfertaTurno.estado == EstadoOferta.OFRECIDA.value,
            )
        )
        assert oferta_mas_profunda is None

    async def test_no_se_acepta_dos_veces(
        self,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        oferta_viva,  # type: ignore[no-untyped-def]
    ) -> None:
        await servicio_espera.aceptar_oferta(oferta_viva.id, principal=principal_recepcion)
        with pytest.raises(OfertaYaResuelta):
            await servicio_espera.aceptar_oferta(oferta_viva.id, principal=principal_recepcion)

    async def test_una_oferta_vencida_no_se_acepta(
        self,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        oferta_viva,  # type: ignore[no-untyped-def]
        reloj_fijo: RelojFijo,
    ) -> None:
        """Ese turno pudo ofrecerse ya al siguiente de la cola."""
        reloj_fijo.avanzar(minutes=31)
        with pytest.raises(OfertaExpirada):
            await servicio_espera.aceptar_oferta(oferta_viva.id, principal=principal_recepcion)

    async def test_rechazar_devuelve_a_la_cola(
        self,
        sesion: AsyncSession,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        oferta_viva,  # type: ignore[no-untyped-def]
    ) -> None:
        """Rechazar no saca de la lista: sigue esperando un turno que le
        sirva. Sacarla obligaria a volver a apuntarse, y nadie lo hace."""
        await servicio_espera.rechazar_oferta(
            oferta_viva.id, principal=principal_recepcion, motivo="Ese dia no puede"
        )

        entrada = await sesion.get(EntradaListaEspera, oferta_viva.lista_espera_id)
        assert entrada is not None
        assert entrada.estado == EstadoEspera.ACTIVA.value

    async def test_tras_rechazar_el_turno_se_ofrece_al_siguiente(
        self,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        oferta_viva,  # type: ignore[no-untyped-def]
        turno_liberado: Cita,
        paciente,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
    ) -> None:
        await _anotar(servicio_espera, principal_recepcion, paciente.id, sede.id, especialidad.id)
        await servicio_espera.rechazar_oferta(oferta_viva.id, principal=principal_recepcion)

        siguiente = await servicio_espera.ofrecer_turno(
            turno_liberado, principal=principal_recepcion
        )
        assert siguiente.oferta is not None
        assert siguiente.oferta.id != oferta_viva.id

    async def test_cancelar_la_entrada_libera_la_oferta(
        self,
        sesion: AsyncSession,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        oferta_viva,  # type: ignore[no-untyped-def]
    ) -> None:
        """El turno vuelve a estar disponible de inmediato, en lugar de
        esperar a que venza el plazo de alguien que ya no lo quiere."""
        await servicio_espera.cancelar(oferta_viva.lista_espera_id, principal=principal_recepcion)

        await sesion.refresh(oferta_viva)
        assert oferta_viva.estado == EstadoOferta.PERDIDA.value


# ===========================================================================
#  Barrido de ofertas vencidas
# ===========================================================================
class TestBarrido:
    @pytest_asyncio.fixture
    async def oferta_vencida(
        self,
        servicio_espera: ServicioListaEspera,
        principal_recepcion: Principal,
        turno_liberado: Cita,
        segundo_paciente,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        especialidad,  # type: ignore[no-untyped-def]
        reloj_fijo: RelojFijo,
        sesion: AsyncSession,
    ):  # type: ignore[no-untyped-def]
        # Con consentimiento: estas pruebas miden la penalizacion por no
        # responder, y solo se penaliza a quien si recibio el aviso.
        await _consentir(sesion, segundo_paciente.id)
        await _anotar(
            servicio_espera,
            principal_recepcion,
            segundo_paciente.id,
            sede.id,
            especialidad.id,
        )
        resultado = await servicio_espera.ofrecer_turno(
            turno_liberado, principal=principal_recepcion
        )
        assert resultado.oferta is not None
        reloj_fijo.avanzar(minutes=31)
        return resultado.oferta

    async def test_el_barrido_vence_las_ofertas_sin_respuesta(
        self,
        sesion: AsyncSession,
        servicio_espera: ServicioListaEspera,
        oferta_vencida,  # type: ignore[no-untyped-def]
    ) -> None:
        """Sin este barrido, una oferta ignorada retiene el turno para
        siempre: el mismo problema que la lista de espera venia a resolver."""
        vencidas = await servicio_espera.expirar_ofertas_vencidas(principal=principal_sistema())

        assert len(vencidas) == 1
        await sesion.refresh(oferta_vencida)
        assert oferta_vencida.estado == EstadoOferta.EXPIRADA.value

    async def test_quien_deja_vencer_vuelve_a_la_cola(
        self,
        sesion: AsyncSession,
        servicio_espera: ServicioListaEspera,
        oferta_vencida,  # type: ignore[no-untyped-def]
    ) -> None:
        await servicio_espera.expirar_ofertas_vencidas(principal=principal_sistema())

        entrada = await sesion.get(EntradaListaEspera, oferta_vencida.lista_espera_id)
        assert entrada is not None
        assert entrada.estado == EstadoEspera.ACTIVA.value
        assert entrada.ofertas_vencidas == 1

    async def test_a_quien_nunca_responde_se_le_deja_de_ofrecer(
        self,
        sesion: AsyncSession,
        servicio_espera: ServicioListaEspera,
        oferta_vencida,  # type: ignore[no-untyped-def]
    ) -> None:
        """No es un castigo: cada oferta ignorada retiene un turno hasta que
        vence, y el hueco se pierde igual pero mas tarde y para todos."""
        entrada = await sesion.get(EntradaListaEspera, oferta_vencida.lista_espera_id)
        assert entrada is not None
        # Se la pone al borde del limite.
        entrada.ofertas_vencidas = MAXIMO_OFERTAS_VENCIDAS - 1
        await sesion.flush()

        await servicio_espera.expirar_ofertas_vencidas(principal=principal_sistema())

        await sesion.refresh(entrada)
        assert entrada.ofertas_vencidas == MAXIMO_OFERTAS_VENCIDAS
        assert entrada.estado == EstadoEspera.EXPIRADA.value

    async def test_sin_ofertas_vencidas_el_barrido_no_hace_nada(
        self, servicio_espera: ServicioListaEspera
    ) -> None:
        assert await servicio_espera.expirar_ofertas_vencidas(principal=principal_sistema()) == []

    async def test_el_barrido_exige_permiso_a_quien_no_es_el_sistema(
        self,
        servicio_espera: ServicioListaEspera,
        clinica,  # type: ignore[no-untyped-def]
    ) -> None:
        """Evita que un endpoint futuro exponga el barrido sin control."""
        cualquiera = Principal(
            actor_tipo=TipoActor.USUARIO,
            actor_id=uuid.uuid4(),
            clinica_id=clinica.id,
            permisos=frozenset(),
            ambito=Ambito(clinica_id=clinica.id),
        )
        with pytest.raises(PermisoDenegado):
            await servicio_espera.expirar_ofertas_vencidas(principal=cualquiera)
