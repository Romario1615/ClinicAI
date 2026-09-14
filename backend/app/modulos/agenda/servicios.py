"""Servicios de la agenda: reservar, confirmar, cancelar y reprogramar.

Esta capa es la **unica** via de escritura sobre la agenda, incluida la del
agente de IA.  Concentra tres responsabilidades que no pueden separarse:

1. **Las reglas de negocio.**  Que transiciones de estado son validas, si la
   politica de cancelacion permite cancelar, si el turno sigue disponible.
2. **El limite transaccional.**  El cambio de estado, la entrada de auditoria
   y el mensaje del outbox se confirman juntos o no se confirman.  Es lo que
   hace que un recordatorio no pueda existir sin su cita, ni una cita
   confirmada quedarse sin aviso (ADR-0008).
3. **La traduccion de los errores del motor.**  Una violacion de la
   restriccion de exclusion es un resultado esperado -- «alguien llego antes»
   -- y se convierte en un mensaje que el paciente entiende.

Sobre los reintentos
--------------------
Las operaciones que compiten por un turno se reintentan una vez ante un
interbloqueo.  El hallazgo de las pruebas de concurrencia fue que, con
competencia real, una parte de los rechazos llega como interbloqueo (40P01) y
no como violacion de exclusion (23P01); un reintento resuelve el caso en que
el competidor deshizo su transaccion, y su coste es una operacion mas.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.disponibilidad import (
    ResultadoDisponibilidad,
    calcular_disponibilidad,
)
from app.modulos.agenda.modelos import (
    TRANSICIONES_PERMITIDAS,
    Cita,
    CitaHistorial,
    EstadoCita,
    OrigenCita,
)
from app.modulos.agenda.repositorio import RepositorioAgenda, rango_de_dias
from app.modulos.lista_espera.servicios import ServicioListaEspera
from app.nucleo.auditoria import (
    AccionAuditada,
    EntradaAuditoria,
    ResultadoAuditoria,
    construir_entrada,
)
from app.nucleo.autorizacion import Principal, TipoActor, principal_sistema
from app.nucleo.errores import (
    BloqueoExpirado,
    PermisoDenegado,
    PoliticaCancelacionViolada,
    RecursoNoEncontrado,
    ReglaNegocioViolada,
    TransicionEstadoInvalida,
    TurnoNoDisponible,
)
from app.nucleo.errores_bd import es_reintentable, traducir_o_propagar
from app.nucleo.idempotencia import validar_clave_cliente
from app.nucleo.operaciones import completar_operacion, iniciar_operacion
from app.nucleo.reloj import Reloj

# Un solo reintento.  Mas de uno alargaria la espera del paciente sin mejorar
# las probabilidades: si el turno sigue ocupado tras el primer reintento, lo
# esta de verdad.
MAX_REINTENTOS: Final = 1

# Rango maximo consultable de una vez.  Sin techo, una peticion de "dame la
# disponibilidad de los proximos cinco anos" recorreria 1800 dias proyectando
# franjas, y seria un vector de agotamiento de CPU trivial de explotar.
DIAS_MAXIMOS_CONSULTA: Final = 90


@dataclass(frozen=True, slots=True)
class SolicitudReserva:
    """Datos de una reserva. Validados antes de llegar aqui por Pydantic."""

    paciente_id: uuid.UUID
    profesional_id: uuid.UUID
    servicio_id: uuid.UUID
    sede_id: uuid.UUID
    inicio: datetime
    consultorio_id: uuid.UUID | None = None
    origen: OrigenCita = OrigenCita.PANEL
    clave_idempotencia: str | None = None
    notas_recepcion: str | None = None


@dataclass(frozen=True, slots=True)
class ResultadoOperacion:
    """Cita resultante mas lo que hay que persistir junto a ella.

    La auditoria y los mensajes del outbox se devuelven en lugar de escribirse
    aqui para que el servicio que orquesta la transaccion los confirme con el
    cambio de estado.  Devolverlos hace explicito que forman parte de la misma
    unidad atomica.
    """

    cita: Cita
    auditoria: tuple[EntradaAuditoria, ...] = ()
    # Se reutiliza un reintento previo en lugar de crear una cita nueva.
    era_reintento: bool = False


class ServicioAgenda:
    """Operaciones de escritura sobre la agenda."""

    def __init__(
        self,
        sesion: AsyncSession,
        repositorio: RepositorioAgenda,
        reloj: Reloj,
        *,
        minutos_expiracion_held: int = 10,
    ) -> None:
        self._sesion = sesion
        self._repo = repositorio
        self._reloj = reloj
        self._minutos_held = minutos_expiracion_held

    # ==================================================================
    #  Consulta de disponibilidad
    # ==================================================================
    async def consultar_disponibilidad(
        self,
        *,
        principal: Principal,
        profesional_id: uuid.UUID,
        servicio_id: uuid.UUID,
        sede_id: uuid.UUID,
        desde: datetime,
        hasta: datetime,
        consultorio_id: uuid.UUID | None = None,
        registrar_descartes: bool = False,
    ) -> ResultadoDisponibilidad:
        """Calcula los turnos libres.

        Es una lectura, pero exige permiso: la disponibilidad de un
        profesional revela su carga de trabajo y sus ausencias, que no es
        informacion publica dentro de la clinica.
        """
        if not principal.tiene_permiso("agenda.leer"):
            raise PermisoDenegado("No tiene permiso para consultar la agenda.")

        if (hasta - desde) > timedelta(days=DIAS_MAXIMOS_CONSULTA):
            raise ReglaNegocioViolada(
                f"El rango consultado no puede exceder {DIAS_MAXIMOS_CONSULTA} dias."
            )

        servicio = await self._repo.obtener_servicio(servicio_id)
        if servicio is None:
            raise RecursoNoEncontrado("El servicio solicitado no existe.")

        profesional = await self._repo.obtener_profesional(profesional_id)
        if profesional is None:
            raise RecursoNoEncontrado("El profesional solicitado no existe.")

        if not principal.ambito.cubre_sede(sede_id):
            # 404 y no 403: revelar que la sede existe permitiria enumerarlas.
            raise RecursoNoEncontrado("La sede solicitada no existe.")

        sede = await self._repo.obtener_sede(sede_id)
        if sede is None:
            raise RecursoNoEncontrado("La sede solicitada no existe.")

        zona = await self._repo.obtener_zona_horaria(sede_id)

        # La duracion efectiva puede diferir de la del servicio: un
        # profesional puede tardar mas o menos en la misma prestacion.
        duracion = servicio.duracion_minutos
        # El buffer efectivo es el mayor de los dos: si el servicio necesita
        # 10 minutos de limpieza y el profesional 15 de descanso, hacen falta
        # 15.  Sumarlos seria excesivo y tomar solo uno dejaria el otro sin
        # cubrir.
        buffer_minutos = max(servicio.minutos_preparacion, profesional.minutos_preparacion_propio)

        franjas = await self._repo.obtener_franjas_profesional(profesional_id, sede_id)
        descansos = await self._repo.obtener_descansos_sede(sede_id)

        primer_dia, ultimo_dia = rango_de_dias(desde, hasta, zona)
        feriados = await self._repo.obtener_feriados(
            profesional.clinica_id, sede_id, desde=primer_dia, hasta=ultimo_dia
        )
        ocupaciones = await self._repo.obtener_ocupaciones(
            profesional_id=profesional_id,
            sede_id=sede_id,
            desde=desde,
            hasta=hasta,
            consultorio_id=consultorio_id,
        )

        return calcular_disponibilidad(
            desde=desde,
            hasta=hasta,
            zona=zona,
            franjas=franjas,
            duracion_minutos=duracion,
            minutos_preparacion=buffer_minutos,
            descansos=descansos,
            feriados=feriados,
            ocupaciones=ocupaciones,
            ahora=self._reloj.ahora(),
            minutos_antelacion_minima=sede.minutos_antelacion_minima,
            registrar_descartes=registrar_descartes,
        )

    # ==================================================================
    #  Bloqueo temporal
    # ==================================================================
    async def bloquear_turno(
        self, solicitud: SolicitudReserva, *, principal: Principal
    ) -> ResultadoOperacion:
        """Reserva un turno en estado `HELD`, con caducidad.

        El bloqueo temporal existe por el flujo de WhatsApp: entre que el
        paciente elige una hora y confirma pueden pasar minutos, y sin bloqueo
        otro paciente podria tomar el mismo turno en ese intervalo.  El
        primero recibiria un rechazo despues de creer que ya habia reservado.

        La caducidad es obligatoria (`CHECK` en la base de datos): un bloqueo
        sin plazo retendria el turno para siempre si el paciente abandona la
        conversacion a medias.
        """
        if not principal.tiene_permiso("cita.crear"):
            raise PermisoDenegado("No tiene permiso para crear citas.")

        ahora = self._reloj.ahora()
        expira_en = ahora + timedelta(minutes=self._minutos_held)

        return await self._crear_cita(
            solicitud,
            principal=principal,
            estado=EstadoCita.HELD,
            expira_en=expira_en,
            accion=AccionAuditada.CITA_BLOQUEADA,
        )

    async def crear_cita_confirmada(
        self, solicitud: SolicitudReserva, *, principal: Principal
    ) -> ResultadoOperacion:
        """Crea una cita ya confirmada, sin paso intermedio.

        Es el camino del panel: recepcion habla con el paciente por telefono y
        confirma en el acto.  No necesita bloqueo temporal porque no hay
        espera entre la eleccion y la confirmacion.
        """
        if not principal.tiene_permiso("cita.crear"):
            raise PermisoDenegado("No tiene permiso para crear citas.")

        return await self._crear_cita(
            solicitud,
            principal=principal,
            estado=EstadoCita.CONFIRMED,
            expira_en=None,
            accion=AccionAuditada.CITA_CREADA,
        )

    async def _crear_cita(
        self,
        solicitud: SolicitudReserva,
        *,
        principal: Principal,
        estado: EstadoCita,
        expira_en: datetime | None,
        accion: AccionAuditada,
    ) -> ResultadoOperacion:
        """Crea la cita, con idempotencia y traduccion de errores."""
        if principal.clinica_id is None:
            raise PermisoDenegado("El principal no tiene clinica asignada.")

        if not principal.ambito.cubre_sede(solicitud.sede_id):
            raise RecursoNoEncontrado("La sede solicitada no existe.")

        # --- Idempotencia ---
        #
        # Se comprueba ANTES de intentar insertar.  El indice unico de la base
        # de datos es la garantia, pero consultar primero permite devolver la
        # cita original en lugar de un error: para el cliente, repetir la
        # peticion debe ser inocuo, no un fallo.
        if solicitud.clave_idempotencia is not None:
            clave = validar_clave_cliente(solicitud.clave_idempotencia)
            existente = await self._repo.buscar_por_clave_idempotencia(
                clave, clinica_id=principal.clinica_id
            )
            if existente is not None:
                return ResultadoOperacion(existente, (), era_reintento=True)

        servicio = await self._repo.obtener_servicio(solicitud.servicio_id)
        if servicio is None:
            raise RecursoNoEncontrado("El servicio solicitado no existe.")

        profesional = await self._repo.obtener_profesional(solicitud.profesional_id)
        if profesional is None:
            raise RecursoNoEncontrado("El profesional solicitado no existe.")

        if not profesional.activo:
            raise ReglaNegocioViolada(
                "El profesional seleccionado no esta disponible para nuevas citas."
            )

        buffer_minutos = max(servicio.minutos_preparacion, profesional.minutos_preparacion_propio)

        cita = Cita(
            clinica_id=principal.clinica_id,
            sede_id=solicitud.sede_id,
            consultorio_id=solicitud.consultorio_id,
            paciente_id=solicitud.paciente_id,
            profesional_id=solicitud.profesional_id,
            servicio_id=solicitud.servicio_id,
            inicio=solicitud.inicio,
            duracion_minutos=servicio.duracion_minutos,
            minutos_preparacion=buffer_minutos,
            estado=estado.value,
            expira_en=expira_en,
            origen=solicitud.origen.value,
            clave_idempotencia=solicitud.clave_idempotencia,
            notas_recepcion=solicitud.notas_recepcion,
            creado_por=principal.actor_id,
            confirmada_en=self._reloj.ahora() if estado is EstadoCita.CONFIRMED else None,
        )

        # `fin` y `rango` los calcula el disparador de la base de datos, no
        # este codigo: es lo que impide que un camino que olvide el buffer
        # produzca un rango incorrecto.
        self._sesion.add(cita)

        try:
            await self._sesion.flush()
        except SQLAlchemyError as exc:
            await self._sesion.rollback()
            # Se traduce a un error de dominio comprensible; si no se reconoce,
            # `traducir_o_propagar` lo propaga para que llegue al registro como
            # la averia que es.
            raise traducir_o_propagar(exc) from exc

        historial = CitaHistorial(
            cita_id=cita.id,
            estado_anterior=None,
            estado_nuevo=estado.value,
            inicio_nuevo=solicitud.inicio,
            profesional_nuevo_id=solicitud.profesional_id,
            actor_tipo=principal.actor_tipo.value,
            actor_id=principal.actor_id,
            motivo="Creacion de la cita",
        )
        self._sesion.add(historial)

        entrada = construir_entrada(
            accion=accion,
            principal=principal,
            ahora=self._reloj.ahora(),
            entidad_tipo="cita",
            entidad_id=cita.id,
            sede_id=solicitud.sede_id,
            paciente_id=solicitud.paciente_id,
            profesional_id=str(solicitud.profesional_id),
            servicio_id=str(solicitud.servicio_id),
            estado=estado.value,
            origen=solicitud.origen.value,
        )

        return ResultadoOperacion(cita, (entrada,))

    # ==================================================================
    #  Confirmacion
    # ==================================================================
    async def confirmar_cita(
        self, cita_id: uuid.UUID, *, principal: Principal
    ) -> ResultadoOperacion:
        """Pasa una cita de `HELD` o `PENDING` a `CONFIRMED`.

        Un bloqueo temporal vencido NO se puede confirmar: se rechaza con
        `BloqueoExpirado`.  Confirmarlo seria peor que rechazarlo, porque el
        turno pudo haberse ofrecido ya a otra persona.
        """
        if not principal.tiene_permiso("cita.crear"):
            raise PermisoDenegado("No tiene permiso para confirmar citas.")

        cita = await self._repo.obtener_cita_para_actualizar(cita_id, principal=principal)
        if cita is None:
            raise RecursoNoEncontrado("La cita solicitada no existe.")

        ahora = self._reloj.ahora()

        # Un bloqueo temporal vencido NO se confirma: el turno pudo haberse
        # ofrecido ya a otra persona, y confirmarlo produciria dos pacientes
        # citados a la misma hora por un camino que elude la restriccion.
        if (
            cita.estado == EstadoCita.HELD.value
            and cita.expira_en is not None
            and cita.expira_en <= ahora
        ):
            raise BloqueoExpirado(
                "El tiempo para confirmar este turno se agoto. "
                "Vuelva a consultar la disponibilidad."
            )

        self._validar_transicion(cita, EstadoCita.CONFIRMED)

        estado_anterior = cita.estado
        cita.estado = EstadoCita.CONFIRMED.value
        cita.expira_en = None
        cita.confirmada_en = ahora
        cita.actualizado_por = principal.actor_id

        try:
            await self._sesion.flush()
        except SQLAlchemyError as exc:
            await self._sesion.rollback()
            raise traducir_o_propagar(exc) from exc

        self._sesion.add(
            CitaHistorial(
                cita_id=cita.id,
                estado_anterior=estado_anterior,
                estado_nuevo=cita.estado,
                actor_tipo=principal.actor_tipo.value,
                actor_id=principal.actor_id,
                motivo="Confirmacion",
            )
        )

        entrada = construir_entrada(
            accion=AccionAuditada.CITA_CONFIRMADA,
            principal=principal,
            ahora=ahora,
            entidad_tipo="cita",
            entidad_id=cita.id,
            sede_id=cita.sede_id,
            paciente_id=cita.paciente_id,
            estado_anterior=estado_anterior,
        )

        return ResultadoOperacion(cita, (entrada,))

    # ==================================================================
    #  Cancelacion
    # ==================================================================
    async def cancelar_cita(
        self,
        cita_id: uuid.UUID,
        *,
        principal: Principal,
        motivo: str,
        horas_antelacion_minima: int = 0,
    ) -> ResultadoOperacion:
        """Cancela una cita.

        El motivo es obligatorio y lo exige tambien la base de datos.  Sin el,
        ante una reclamacion no se puede explicar por que un paciente no fue
        atendido, que es justo la pregunta que se hace.

        `horas_antelacion_minima` implementa la politica de cancelacion de la
        clinica.  El personal puede cancelar siempre; la restriccion aplica al
        paciente, que cancela por WhatsApp.
        """
        if not principal.tiene_permiso("cita.cancelar"):
            raise PermisoDenegado("No tiene permiso para cancelar citas.")

        motivo_limpio = motivo.strip()
        if not motivo_limpio:
            raise ReglaNegocioViolada("Para cancelar hay que indicar el motivo.")

        cita = await self._repo.obtener_cita_para_actualizar(cita_id, principal=principal)
        if cita is None:
            raise RecursoNoEncontrado("La cita solicitada no existe.")

        self._validar_transicion(cita, EstadoCita.CANCELLED)

        ahora = self._reloj.ahora()

        # La politica solo se aplica a quien cancela desde fuera: el personal
        # de la clinica necesita poder cancelar una cita de hoy si el
        # profesional enferma.
        if horas_antelacion_minima > 0 and principal.actor_tipo in (
            TipoActor.PACIENTE,
            TipoActor.AGENTE_IA,
        ):
            limite = cita.inicio - timedelta(hours=horas_antelacion_minima)
            if ahora > limite:
                raise PoliticaCancelacionViolada(
                    f"Las cancelaciones requieren {horas_antelacion_minima} horas "
                    "de antelacion. Comuniquese con la clinica."
                )

        estado_anterior = cita.estado
        cita.estado = EstadoCita.CANCELLED.value
        cita.motivo_cancelacion = motivo_limpio
        cita.cancelada_en = ahora
        cita.cancelada_por = principal.actor_id
        cita.expira_en = None
        cita.actualizado_por = principal.actor_id

        try:
            await self._sesion.flush()
        except SQLAlchemyError as exc:
            await self._sesion.rollback()
            raise traducir_o_propagar(exc) from exc

        self._sesion.add(
            CitaHistorial(
                cita_id=cita.id,
                estado_anterior=estado_anterior,
                estado_nuevo=cita.estado,
                actor_tipo=principal.actor_tipo.value,
                actor_id=principal.actor_id,
                motivo=motivo_limpio,
            )
        )

        entrada = construir_entrada(
            accion=AccionAuditada.CITA_CANCELADA,
            principal=principal,
            ahora=ahora,
            entidad_tipo="cita",
            entidad_id=cita.id,
            sede_id=cita.sede_id,
            paciente_id=cita.paciente_id,
            motivo=motivo_limpio,
            estado_anterior=estado_anterior,
        )

        oferta = await ServicioListaEspera(self._sesion, self._reloj).ofrecer_turno(
            cita, principal=principal_sistema(cita.clinica_id)
        )
        return ResultadoOperacion(cita, (entrada, *oferta.auditoria))

    # ==================================================================
    #  Reprogramacion
    # ==================================================================
    async def reprogramar_cita(
        self,
        cita_id: uuid.UUID,
        *,
        principal: Principal,
        nuevo_inicio: datetime,
        motivo: str,
        nuevo_profesional_id: uuid.UUID | None = None,
        nuevo_consultorio_id: uuid.UUID | None = None,
        clave_idempotencia: str | None = None,
    ) -> ResultadoOperacion:
        """Mueve una cita a otro horario, y opcionalmente a otro profesional.

        Se modifica la cita existente en lugar de crear una nueva y cancelar
        la anterior.  El motivo: conservar un solo identificador de cita
        simplifica el seguimiento para el paciente, para el calendario externo
        y para los recordatorios ya programados.  El horario anterior queda en
        `cita_historial`, que es append-only, asi que la trazabilidad no se
        pierde.

        La proteccion contra doble reserva funciona igual que en la creacion:
        la restriccion de exclusion evalua el nuevo rango y rechaza el cambio
        si pisa otra cita.
        """
        if not principal.tiene_permiso("cita.reprogramar"):
            raise PermisoDenegado("No tiene permiso para reprogramar citas.")

        motivo_limpio = motivo.strip()
        if not motivo_limpio:
            raise ReglaNegocioViolada("Para reprogramar hay que indicar el motivo.")

        cita = await self._repo.obtener_cita_para_actualizar(cita_id, principal=principal)
        if cita is None:
            raise RecursoNoEncontrado("La cita solicitada no existe.")

        registro = None
        if clave_idempotencia:
            registro = await iniciar_operacion(
                self._sesion,
                principal,
                self._reloj,
                "cita.reprogramar",
                clave_idempotencia,
                {
                    "id": cita_id,
                    "inicio": nuevo_inicio,
                    "motivo": motivo_limpio,
                    "profesional": nuevo_profesional_id,
                    "consultorio": nuevo_consultorio_id,
                },
            )
            if registro.respuesta:
                return ResultadoOperacion(cita, (), era_reintento=True)

        self._validar_transicion(cita, EstadoCita.RESCHEDULED)

        ahora = self._reloj.ahora()
        inicio_anterior = cita.inicio
        profesional_anterior = cita.profesional_id
        estado_anterior = cita.estado

        if nuevo_profesional_id is not None and nuevo_profesional_id != cita.profesional_id:
            nuevo = await self._repo.obtener_profesional(nuevo_profesional_id)
            if nuevo is None:
                raise RecursoNoEncontrado("El profesional solicitado no existe.")
            if not nuevo.activo:
                raise ReglaNegocioViolada(
                    "El profesional seleccionado no esta disponible para nuevas citas."
                )
            cita.profesional_id = nuevo_profesional_id
            # El buffer puede cambiar con el profesional.
            servicio = await self._repo.obtener_servicio(cita.servicio_id)
            if servicio is not None:
                cita.minutos_preparacion = max(
                    servicio.minutos_preparacion, nuevo.minutos_preparacion_propio
                )

        if nuevo_consultorio_id is not None:
            cita.consultorio_id = nuevo_consultorio_id

        cita.inicio = nuevo_inicio
        cita.estado = EstadoCita.RESCHEDULED.value
        cita.expira_en = None
        cita.actualizado_por = principal.actor_id

        try:
            await self._sesion.flush()
        except SQLAlchemyError as exc:
            await self._sesion.rollback()
            raise traducir_o_propagar(exc) from exc

        self._sesion.add(
            CitaHistorial(
                cita_id=cita.id,
                estado_anterior=estado_anterior,
                estado_nuevo=cita.estado,
                inicio_anterior=inicio_anterior,
                inicio_nuevo=nuevo_inicio,
                profesional_anterior_id=profesional_anterior,
                profesional_nuevo_id=cita.profesional_id,
                actor_tipo=principal.actor_tipo.value,
                actor_id=principal.actor_id,
                motivo=motivo_limpio,
            )
        )

        entrada = construir_entrada(
            accion=AccionAuditada.CITA_REPROGRAMADA,
            principal=principal,
            ahora=ahora,
            entidad_tipo="cita",
            entidad_id=cita.id,
            sede_id=cita.sede_id,
            paciente_id=cita.paciente_id,
            motivo=motivo_limpio,
            estado_anterior=estado_anterior,
        )

        if registro is not None:
            completar_operacion(registro, {"id": str(cita.id)}, self._reloj)
        return ResultadoOperacion(cita, (entrada,))

    # ==================================================================
    #  Cierre de la atencion
    # ==================================================================
    async def completar_cita(
        self, cita_id: uuid.UUID, *, principal: Principal
    ) -> ResultadoOperacion:
        return await self._cerrar(
            cita_id,
            principal=principal,
            nuevo_estado=EstadoCita.COMPLETED,
            permiso="cita.completar",
            accion=AccionAuditada.CITA_COMPLETADA,
            motivo="Atencion completada",
        )

    async def marcar_inasistencia(
        self, cita_id: uuid.UUID, *, principal: Principal
    ) -> ResultadoOperacion:
        """Marca que el paciente no se presento.

        Se registra como estado propio y no como cancelacion porque son
        hechos distintos: una inasistencia cuenta para la prediccion de
        ausentismo y para las metricas de ocupacion perdida, y confundirla con
        una cancelacion falsearia ambas.
        """
        return await self._cerrar(
            cita_id,
            principal=principal,
            nuevo_estado=EstadoCita.NO_SHOW,
            permiso="cita.marcar_inasistencia",
            accion=AccionAuditada.CITA_INASISTENCIA,
            motivo="El paciente no se presento",
        )

    async def _cerrar(
        self,
        cita_id: uuid.UUID,
        *,
        principal: Principal,
        nuevo_estado: EstadoCita,
        permiso: str,
        accion: AccionAuditada,
        motivo: str,
    ) -> ResultadoOperacion:
        if not principal.tiene_permiso(permiso):
            raise PermisoDenegado(f"No tiene el permiso '{permiso}'.")

        cita = await self._repo.obtener_cita_para_actualizar(cita_id, principal=principal)
        if cita is None:
            raise RecursoNoEncontrado("La cita solicitada no existe.")

        self._validar_transicion(cita, nuevo_estado)

        ahora = self._reloj.ahora()
        estado_anterior = cita.estado
        cita.estado = nuevo_estado.value
        cita.actualizado_por = principal.actor_id
        if nuevo_estado is EstadoCita.COMPLETED:
            cita.completada_en = ahora

        try:
            await self._sesion.flush()
        except SQLAlchemyError as exc:
            await self._sesion.rollback()
            raise traducir_o_propagar(exc) from exc

        self._sesion.add(
            CitaHistorial(
                cita_id=cita.id,
                estado_anterior=estado_anterior,
                estado_nuevo=cita.estado,
                actor_tipo=principal.actor_tipo.value,
                actor_id=principal.actor_id,
                motivo=motivo,
            )
        )

        entrada = construir_entrada(
            accion=accion,
            principal=principal,
            ahora=ahora,
            entidad_tipo="cita",
            entidad_id=cita.id,
            sede_id=cita.sede_id,
            paciente_id=cita.paciente_id,
            estado_anterior=estado_anterior,
        )

        return ResultadoOperacion(cita, (entrada,))

    # ==================================================================
    #  Expiracion de bloqueos temporales
    # ==================================================================
    async def expirar_bloqueos_vencidos(
        self, *, principal: Principal, limite: int = 200
    ) -> list[ResultadoOperacion]:
        """Libera los turnos cuyo bloqueo temporal caduco.

        Lo ejecuta el worker de forma periodica.  Sin este barrido, un
        paciente que abandona la conversacion de WhatsApp a medias dejaria el
        turno retenido indefinidamente, y la agenda perderia capacidad de
        forma invisible.

        Los bloqueos vencidos se pasan a `CANCELLED` con motivo explicito: asi
        el turno queda libre (la clausula WHERE de la restriccion de exclusion
        deja fuera los cancelados) y queda constancia de por que.
        """
        if not principal.es_sistema and not principal.tiene_permiso("cita.cancelar"):
            raise PermisoDenegado("No tiene permiso para liberar bloqueos.")

        ahora = self._reloj.ahora()
        vencidos = await self._repo.listar_bloqueos_vencidos(ahora=ahora, limite=limite)

        resultados: list[ResultadoOperacion] = []
        for cita in vencidos:
            estado_anterior = cita.estado
            cita.estado = EstadoCita.CANCELLED.value
            cita.motivo_cancelacion = "El bloqueo temporal caduco sin confirmacion del paciente."
            cita.cancelada_en = ahora
            cita.expira_en = None

            self._sesion.add(
                CitaHistorial(
                    cita_id=cita.id,
                    estado_anterior=estado_anterior,
                    estado_nuevo=cita.estado,
                    actor_tipo=TipoActor.SISTEMA.value,
                    motivo="Expiracion del bloqueo temporal",
                )
            )
            resultados.append(
                ResultadoOperacion(
                    cita,
                    (
                        construir_entrada(
                            accion=AccionAuditada.CITA_CANCELADA,
                            principal=principal,
                            ahora=ahora,
                            resultado=ResultadoAuditoria.EXITO,
                            entidad_tipo="cita",
                            entidad_id=cita.id,
                            sede_id=cita.sede_id,
                            paciente_id=cita.paciente_id,
                            motivo="Expiracion del bloqueo temporal",
                        ),
                    ),
                )
            )

        if resultados:
            try:
                await self._sesion.flush()
            except SQLAlchemyError as exc:
                await self._sesion.rollback()
                raise traducir_o_propagar(exc) from exc

        return resultados

    # ==================================================================
    #  Maquina de estados
    # ==================================================================
    def _validar_transicion(self, cita: Cita, nuevo: EstadoCita) -> None:
        """Comprueba que la transicion sea valida.

        La tabla de transiciones vive en el modelo, como dato y no como cadena
        de `if`.  Eso permite probarla de forma exhaustiva y que la interfaz la
        consulte para mostrar solo las acciones posibles.

        Los estados terminales no admiten salida: reabrir una cita cancelada
        perderia la trazabilidad de por que se cancelo.  Si hay que volver a
        atender al paciente, se crea una cita nueva.
        """
        actual = cita.estado_enum
        permitidas = TRANSICIONES_PERMITIDAS[actual]
        if nuevo not in permitidas:
            if actual.es_terminal:
                raise TransicionEstadoInvalida(
                    f"La cita ya esta {actual.etiqueta().lower()} y no admite "
                    "mas cambios. Cree una cita nueva si hace falta."
                )
            posibles = ", ".join(sorted(e.etiqueta() for e in permitidas))
            raise TransicionEstadoInvalida(
                f"No se puede pasar de '{actual.etiqueta()}' a "
                f"'{nuevo.etiqueta()}'. Transiciones posibles: {posibles}."
            )


def debe_reintentar(excepcion: BaseException, intentos_previos: int) -> bool:
    """Decide si una operacion fallida merece otro intento.

    Solo ante interbloqueo o fallo de serializacion, y solo una vez.  Un
    turno ya ocupado no se libera reintentando, asi que insistir solo
    alargaria la espera del paciente.
    """
    return intentos_previos < MAX_REINTENTOS and es_reintentable(excepcion)


__all__ = [
    "DIAS_MAXIMOS_CONSULTA",
    "MAX_REINTENTOS",
    "ResultadoOperacion",
    "ServicioAgenda",
    "SolicitudReserva",
    "TurnoNoDisponible",
    "debe_reintentar",
]
