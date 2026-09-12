"""Sincronizacion de la agenda con el calendario externo del profesional.

La regla de la que se deriva todo lo demas
------------------------------------------
**La agenda interna es la fuente de verdad. El calendario externo es un
reflejo.** (CLAUDE.md, seccion 6; RF-I08.)

Eso decide cada caso dudoso sin tener que pensarlo dos veces:

* Si el proveedor no responde, la cita **ya esta** confirmada en la base. El
  reflejo se reintenta; nadie pierde su turno porque Google estuviera caido.
* Si el profesional borra el evento desde su telefono, la cita **sigue
  existiendo** y el evento se vuelve a crear. Borrar el reflejo no cancela la
  atencion de un paciente.
* Si el profesional **mueve** el evento de hora, no se pisa: se marca
  conflicto. Ese cambio es intencionado y puede significar que el profesional
  no estara disponible; resolverlo exige una persona, porque puede implicar
  reprogramar a un paciente.

Los tokens
----------
Se guardan cifrados con AES-GCM y con el `profesional_id` como contexto
autenticado. Eso significa que un token copiado de una fila a otra **no
descifra**: si alguien con acceso a la base intenta mover la conexion de un
profesional a otro para leer su calendario, obtiene un error de
autenticacion, no los datos.

Los tokens nunca aparecen en un log, ni en un `repr`, ni en una respuesta
HTTP. `Credenciales.__repr__` esta sobrescrito para que ni un traceback los
vuelque.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita, EstadoCita
from app.modulos.calendario.adaptadores import (
    AdaptadorCalendario,
    Credenciales,
    RegistroCalendarios,
    RespuestaCalendario,
    ResultadoCalendario,
)
from app.modulos.calendario.eventos import EventoExterno, construir_evento
from app.modulos.organizacion.modelos import Consultorio, Sede
from app.modulos.profesionales.modelos import (
    CalendarioConexion,
    CalendarioEvento,
    EstadoEventoCalendario,
    EstadoSincronizacion,
)
from app.nucleo.errores import RecursoNoEncontrado
from app.nucleo.registro import obtener_logger
from app.nucleo.reloj import Reloj
from app.nucleo.seguridad import CifradorDatos

logger = obtener_logger(__name__)

# Estados de cita que deben tener reflejo en el calendario. Una cita cancelada
# o con inasistencia libera el hueco: dejar su evento haria que el profesional
# viera ocupado un horario disponible, que es el problema inverso y igual de
# malo.
ESTADOS_CON_REFLEJO: frozenset[str] = frozenset(
    {
        EstadoCita.HELD.value,
        EstadoCita.CONFIRMED.value,
        EstadoCita.RESCHEDULED.value,
    }
)

# Intentos por evento antes de dejarlo en ERROR para revision humana.
MAXIMO_INTENTOS_EVENTO = 5

# Margen con el que se renueva un token antes de que caduque. Renovar justo al
# vencer deja una ventana en la que las peticiones en curso fallan.
MARGEN_RENOVACION = timedelta(minutes=10)


@dataclass(frozen=True, slots=True)
class ResumenSincronizacion:
    creados: int = 0
    actualizados: int = 0
    eliminados: int = 0
    recreados: int = 0
    conflictos: int = 0
    reintentables: int = 0
    errores: int = 0
    sin_conexion: int = 0
    token_vencido: int = 0


class ServicioCalendario:
    """Mantiene el reflejo de la agenda en el calendario del profesional."""

    def __init__(
        self,
        sesion: AsyncSession,
        reloj: Reloj,
        cifrador: CifradorDatos,
        proveedores: RegistroCalendarios,
        *,
        url_sistema: str = "http://localhost:4200",
    ) -> None:
        self._sesion = sesion
        self._reloj = reloj
        self._cifrador = cifrador
        self._proveedores = proveedores
        self._url_sistema = url_sistema

    # ------------------------------------------------------------------
    #  Ciclo de vida de la conexion
    # ------------------------------------------------------------------
    async def conectar(
        self,
        *,
        profesional_id: uuid.UUID,
        proveedor: str,
        calendar_id: str,
        token_acceso: str,
        token_refresco: str,
        expira_en: datetime | None,
        alcances: str | None,
    ) -> CalendarioConexion:
        """Guarda o actualiza la conexion con los tokens cifrados.

        Es idempotente por `(profesional, proveedor, calendar_id)`: repetir el
        flujo de OAuth -- porque el profesional volvio a autorizar, o porque
        se perdio el token de refresco -- actualiza la conexion existente en
        lugar de crear una segunda. Dos conexiones al mismo calendario
        duplicarian cada evento.
        """
        contexto = self._contexto(profesional_id)
        existente = (
            await self._sesion.execute(
                select(CalendarioConexion).where(
                    CalendarioConexion.profesional_id == profesional_id,
                    CalendarioConexion.proveedor == proveedor,
                    CalendarioConexion.calendar_id == calendar_id,
                )
            )
        ).scalar_one_or_none()

        conexion = existente or CalendarioConexion(
            profesional_id=profesional_id,
            proveedor=proveedor,
            calendar_id=calendar_id,
        )
        conexion.token_acceso_cifrado = self._cifrador.cifrar(token_acceso, contexto=contexto)
        conexion.token_refresco_cifrado = self._cifrador.cifrar(token_refresco, contexto=contexto)
        conexion.expira_en = expira_en
        conexion.alcances = alcances
        conexion.estado_sincronizacion = EstadoSincronizacion.CONECTADO.value
        conexion.ultimo_error = None

        if existente is None:
            self._sesion.add(conexion)
        await self._sesion.flush()

        logger.info(
            "calendario.conectado",
            profesional_id=str(profesional_id),
            proveedor=proveedor,
        )
        return conexion

    async def desconectar(self, *, conexion_id: uuid.UUID, motivo: str) -> CalendarioConexion:
        """Desconecta y **borra los tokens** de la base.

        Se ponen a nulo en lugar de dejarlos: un token que ya no se usa y
        sigue guardado es solo superficie de ataque. La fila se conserva
        porque los eventos ya creados la referencian y hay que poder explicar
        de donde salieron.

        Los eventos **no se borran del calendario del profesional**. Es su
        calendario: dejarlo limpio suena ordenado, pero borrar de golpe meses
        de su agenda al desconectar una integracion es una sorpresa
        desagradable y no reversible. Quedan como estaban.
        """
        conexion = await self._sesion.get(CalendarioConexion, conexion_id)
        if conexion is None:
            raise RecursoNoEncontrado("La conexion de calendario no existe.")

        conexion.token_acceso_cifrado = None
        conexion.token_refresco_cifrado = None
        conexion.expira_en = None
        conexion.estado_sincronizacion = EstadoSincronizacion.DESCONECTADO.value
        conexion.ultimo_error = motivo
        await self._sesion.flush()

        logger.info("calendario.desconectado", conexion_id=str(conexion_id))
        return conexion

    async def marcar_token_vencido(self, conexion: CalendarioConexion, detalle: str) -> None:
        """Marca la conexion como vencida, sin borrar el token de refresco.

        La distincion importa: `DESCONECTADO` no necesita accion,
        `TOKEN_VENCIDO` si. Confundirlos hace que un profesional pierda la
        sincronizacion sin que nadie se entere -- que es justo lo que el
        modelo advierte en su docstring.
        """
        conexion.estado_sincronizacion = EstadoSincronizacion.TOKEN_VENCIDO.value
        conexion.ultimo_error = detalle
        await self._sesion.flush()
        # Nivel `warning`: exige que alguien vuelva a autorizar. Silenciarlo
        # deja la agenda del profesional desincronizada indefinidamente.
        logger.warning(
            "calendario.token_vencido",
            conexion_id=str(conexion.id),
            profesional_id=str(conexion.profesional_id),
        )

    # ------------------------------------------------------------------
    #  Reflejo de una cita
    # ------------------------------------------------------------------
    async def registrar_cita(self, cita: Cita) -> list[CalendarioEvento]:
        """Crea las filas de evento pendientes para las conexiones activas.

        **No habla con el proveedor.** Se llama dentro de la transaccion de
        negocio que confirma la cita, y salir a la red ahi significaria que un
        timeout de Google puede hacer fallar la reserva de un paciente. La
        entrega la hace el worker despues (RF-I08).
        """
        conexiones = (
            (
                await self._sesion.execute(
                    select(CalendarioConexion).where(
                        CalendarioConexion.profesional_id == cita.profesional_id,
                        CalendarioConexion.estado_sincronizacion.in_(
                            [
                                EstadoSincronizacion.CONECTADO.value,
                                EstadoSincronizacion.TOKEN_VENCIDO.value,
                            ]
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )

        creados: list[CalendarioEvento] = []
        for conexion in conexiones:
            ya = (
                await self._sesion.execute(
                    select(CalendarioEvento).where(
                        CalendarioEvento.cita_id == cita.id,
                        CalendarioEvento.calendario_conexion_id == conexion.id,
                    )
                )
            ).scalar_one_or_none()
            if ya is not None:
                # La restriccion unica ya lo impediria; comprobarlo antes
                # evita abortar la transaccion de negocio por un reflejo.
                ya.estado = EstadoEventoCalendario.PENDIENTE.value
                ya.intentos = 0
                continue

            evento = CalendarioEvento(
                cita_id=cita.id,
                profesional_id=cita.profesional_id,
                calendario_conexion_id=conexion.id,
                calendar_id=conexion.calendar_id,
                estado=EstadoEventoCalendario.PENDIENTE.value,
            )
            self._sesion.add(evento)
            creados.append(evento)

        await self._sesion.flush()
        return creados

    async def detectar_citas_sin_reflejo(self, *, limite: int = 100) -> int:
        """Crea las filas de evento que faltan, comparando con la agenda.

        Por que por deteccion y no desde el servicio de agenda
        -----------------------------------------------------
        Seria mas directo que `ServicioAgenda.confirmar` llamara a
        `registrar_cita`. Se hace al reves a proposito, por dos motivos:

        1. **RF-I08.** El anti doble-reserva y el ciclo de estados de la
           agenda estan verificados bajo concurrencia real. Anadirles una
           dependencia del calendario introduce una via por la que un fallo
           del reflejo podria afectar a la reserva de un paciente. La agenda
           no sabe que existen los calendarios, y eso es una propiedad que
           conviene conservar.

        2. Cubre las citas **anteriores** a la conexion. Un profesional que
           conecta su calendario hoy espera ver su agenda de la semana que
           viene, no solo lo que se reserve a partir de ahora. Un enganche en
           la confirmacion no daria eso; esta deteccion si, sin codigo extra.

        El coste es latencia: el reflejo aparece en el siguiente barrido, no
        en el instante de confirmar. Para un calendario es aceptable.
        """
        conexiones = (
            (
                await self._sesion.execute(
                    select(CalendarioConexion).where(
                        CalendarioConexion.estado_sincronizacion
                        == EstadoSincronizacion.CONECTADO.value
                    )
                )
            )
            .scalars()
            .all()
        )
        if not conexiones:
            return 0

        creados = 0
        ahora = self._reloj.ahora()
        for conexion in conexiones:
            # Solo citas futuras. Reflejar el pasado llenaria el calendario
            # del profesional de historico que no le sirve para nada, y
            # gastaria cuota del proveedor en eventos que nadie mirara.
            faltantes = (
                (
                    await self._sesion.execute(
                        select(Cita)
                        .where(
                            Cita.profesional_id == conexion.profesional_id,
                            Cita.estado.in_(ESTADOS_CON_REFLEJO),
                            Cita.inicio >= ahora,
                            ~select(CalendarioEvento.id)
                            .where(
                                CalendarioEvento.cita_id == Cita.id,
                                CalendarioEvento.calendario_conexion_id == conexion.id,
                            )
                            .exists(),
                        )
                        .order_by(Cita.inicio)
                        .limit(limite)
                    )
                )
                .scalars()
                .all()
            )
            for cita in faltantes:
                self._sesion.add(
                    CalendarioEvento(
                        cita_id=cita.id,
                        profesional_id=cita.profesional_id,
                        calendario_conexion_id=conexion.id,
                        calendar_id=conexion.calendar_id,
                        estado=EstadoEventoCalendario.PENDIENTE.value,
                    )
                )
                creados += 1

        if creados:
            await self._sesion.flush()
            logger.info("calendario.reflejos_detectados", cantidad=creados)
        return creados

    async def sincronizar_pendientes(self, *, limite: int = 50) -> ResumenSincronizacion:
        """Publica en el proveedor los eventos pendientes.

        Corre en el worker, en su propia transaccion. Un fallo de un evento no
        arrastra a los demas.
        """
        consulta = (
            select(CalendarioEvento)
            .where(
                CalendarioEvento.estado.in_(
                    [
                        EstadoEventoCalendario.PENDIENTE.value,
                        EstadoEventoCalendario.ELIMINADO_EXTERNAMENTE.value,
                    ]
                )
            )
            .order_by(CalendarioEvento.creado_en)
            .limit(limite)
            .with_for_update(skip_locked=True)
        )
        eventos = list((await self._sesion.execute(consulta)).scalars().all())

        resumen = ResumenSincronizacion()
        for evento in eventos:
            resumen = await self._sincronizar_uno(evento, resumen)
        return resumen

    async def _sincronizar_uno(
        self, evento: CalendarioEvento, resumen: ResumenSincronizacion
    ) -> ResumenSincronizacion:
        """Publica un evento y aplica el desenlace.

        Se limita a decidir si hay con que publicar y a delegar el resultado.
        El reparto por desenlace no es estetico: cada rama tiene una regla
        propia -- recrear, no sobrescribir, marcar la conexion -- y leerlas
        mezcladas es como se acaba aplicando la equivocada.
        """
        contexto = await self._contexto_de_envio(evento)
        if contexto is None:
            return _con(resumen, sin_conexion=resumen.sin_conexion + 1)
        conexion, credenciales, adaptador = contexto

        cita = await self._sesion.get(Cita, evento.cita_id)
        if cita is None:
            # La cita desaparecio (borrado en cascada). El reflejo sobra.
            evento.estado = EstadoEventoCalendario.ERROR.value
            evento.ultimo_error = "La cita de origen ya no existe."
            return _con(resumen, errores=resumen.errores + 1)

        # Una cita que ya no ocupa el hueco no debe seguir reflejada: el
        # profesional veria ocupado un horario libre.
        if cita.estado not in ESTADOS_CON_REFLEJO:
            return await self._eliminar_reflejo(evento, credenciales, adaptador, resumen)

        payload = await self._payload(cita)
        evento.intentos += 1

        if evento.external_event_id is None:
            respuesta = await adaptador.crear(credenciales, payload)
        else:
            respuesta = await adaptador.actualizar(
                credenciales, evento.external_event_id, payload, etag=evento.etag
            )

        return await self._aplicar_desenlace(
            evento=evento,
            conexion=conexion,
            credenciales=credenciales,
            adaptador=adaptador,
            payload=payload,
            respuesta=respuesta,
            resumen=resumen,
        )

    async def _contexto_de_envio(
        self, evento: CalendarioEvento
    ) -> tuple[CalendarioConexion, Credenciales, AdaptadorCalendario] | None:
        """Conexion, credenciales y adaptador, o `None` si falta alguno."""
        conexion = await self._sesion.get(CalendarioConexion, evento.calendario_conexion_id)
        if conexion is None:
            return None
        credenciales = self._credenciales(conexion)
        adaptador = self._proveedores.obtener(conexion.proveedor)
        if credenciales is None or adaptador is None:
            return None
        return conexion, credenciales, adaptador

    async def _aplicar_desenlace(
        self,
        *,
        evento: CalendarioEvento,
        conexion: CalendarioConexion,
        credenciales: Credenciales,
        adaptador: AdaptadorCalendario,
        payload: EventoExterno,
        respuesta: RespuestaCalendario,
        resumen: ResumenSincronizacion,
    ) -> ResumenSincronizacion:
        if respuesta.resultado is ResultadoCalendario.OK:
            return self._aplicar_exito(evento, conexion, respuesta, resumen)

        if respuesta.resultado is ResultadoCalendario.NO_ENCONTRADO:
            return await self._recrear(evento, credenciales, adaptador, payload, resumen)

        if respuesta.resultado is ResultadoCalendario.CONFLICTO:
            # NO se sobrescribe. El profesional movio el evento a proposito, y
            # pisarlo destruiria esa decision -- que puede significar que no
            # estara disponible y que hay que reprogramar a un paciente.
            evento.estado = EstadoEventoCalendario.CONFLICTO.value
            evento.etag = respuesta.etag
            evento.ultimo_error = respuesta.detalle or "Cambio externo sin resolver."
            logger.warning(
                "calendario.conflicto",
                evento_id=str(evento.id),
                cita_id=str(evento.cita_id),
                profesional_id=str(evento.profesional_id),
            )
            return _con(resumen, conflictos=resumen.conflictos + 1)

        if respuesta.resultado is ResultadoCalendario.TOKEN_VENCIDO:
            await self.marcar_token_vencido(
                conexion, respuesta.detalle or "El proveedor rechazo el token."
            )
            evento.estado = EstadoEventoCalendario.PENDIENTE.value
            evento.ultimo_error = respuesta.detalle
            return _con(resumen, token_vencido=resumen.token_vencido + 1)

        return self._aplicar_fallo(evento, conexion, respuesta, resumen)

    def _aplicar_exito(
        self,
        evento: CalendarioEvento,
        conexion: CalendarioConexion,
        respuesta: RespuestaCalendario,
        resumen: ResumenSincronizacion,
    ) -> ResumenSincronizacion:
        ahora = self._reloj.ahora()
        nuevo = evento.external_event_id is None
        evento.external_event_id = respuesta.external_event_id or evento.external_event_id
        evento.etag = respuesta.etag
        evento.estado = EstadoEventoCalendario.SINCRONIZADO.value
        evento.sincronizado_en = ahora
        evento.ultimo_error = None
        conexion.ultima_sincronizacion_en = ahora
        if nuevo:
            return _con(resumen, creados=resumen.creados + 1)
        return _con(resumen, actualizados=resumen.actualizados + 1)

    def _aplicar_fallo(
        self,
        evento: CalendarioEvento,
        conexion: CalendarioConexion,
        respuesta: RespuestaCalendario,
        resumen: ResumenSincronizacion,
    ) -> ResumenSincronizacion:
        """Fallo temporal o permanente.

        Un evento que agota los intentos queda en ERROR y **no desaparece**:
        significa que la agenda externa de un profesional esta desincronizada
        y alguien tiene que mirarla.
        """
        detalle = respuesta.detalle or "sin detalle"
        if (
            respuesta.resultado is ResultadoCalendario.FALLO_PERMANENTE
            or evento.intentos >= MAXIMO_INTENTOS_EVENTO
        ):
            evento.estado = EstadoEventoCalendario.ERROR.value
            evento.ultimo_error = detalle
            conexion.estado_sincronizacion = EstadoSincronizacion.ERROR.value
            conexion.ultimo_error = detalle
            logger.error(
                "calendario.evento_fallido",
                evento_id=str(evento.id),
                intentos=evento.intentos,
                motivo=detalle,
            )
            return _con(resumen, errores=resumen.errores + 1)

        evento.estado = EstadoEventoCalendario.PENDIENTE.value
        evento.ultimo_error = detalle
        return _con(resumen, reintentables=resumen.reintentables + 1)

    async def _recrear(
        self,
        evento: CalendarioEvento,
        credenciales: Credenciales,
        adaptador: AdaptadorCalendario,
        payload: EventoExterno,
        resumen: ResumenSincronizacion,
    ) -> ResumenSincronizacion:
        """Vuelve a crear un evento que el profesional borro a mano.

        La cita sigue en pie, asi que el reflejo se restablece: el calendario
        es el reflejo, no la fuente (RF-I08). Borrar el evento en el telefono
        no cancela la atencion de un paciente.
        """
        logger.info(
            "calendario.evento_borrado_externamente",
            evento_id=str(evento.id),
            cita_id=str(evento.cita_id),
        )
        respuesta = await adaptador.crear(credenciales, payload)
        if respuesta.resultado is ResultadoCalendario.OK:
            evento.external_event_id = respuesta.external_event_id
            evento.etag = respuesta.etag
            evento.estado = EstadoEventoCalendario.SINCRONIZADO.value
            evento.sincronizado_en = self._reloj.ahora()
            evento.ultimo_error = None
            return _con(resumen, recreados=resumen.recreados + 1)

        evento.estado = EstadoEventoCalendario.PENDIENTE.value
        evento.ultimo_error = respuesta.detalle or "No se pudo recrear el evento."
        return _con(resumen, reintentables=resumen.reintentables + 1)

    async def _eliminar_reflejo(
        self,
        evento: CalendarioEvento,
        credenciales: Credenciales,
        adaptador: AdaptadorCalendario,
        resumen: ResumenSincronizacion,
    ) -> ResumenSincronizacion:
        """Retira del calendario una cita que ya no ocupa el hueco."""
        if evento.external_event_id is None:
            # Nunca llego a publicarse. No hay nada que retirar.
            evento.estado = EstadoEventoCalendario.SINCRONIZADO.value
            evento.sincronizado_en = self._reloj.ahora()
            return _con(resumen, eliminados=resumen.eliminados + 1)

        respuesta = await adaptador.eliminar(credenciales, evento.external_event_id)
        if respuesta.resultado is ResultadoCalendario.OK:
            evento.estado = EstadoEventoCalendario.SINCRONIZADO.value
            evento.sincronizado_en = self._reloj.ahora()
            evento.ultimo_error = None
            return _con(resumen, eliminados=resumen.eliminados + 1)

        evento.estado = EstadoEventoCalendario.PENDIENTE.value
        evento.ultimo_error = respuesta.detalle or "No se pudo retirar el evento."
        return _con(resumen, reintentables=resumen.reintentables + 1)

    # ------------------------------------------------------------------
    #  Reconciliacion
    # ------------------------------------------------------------------
    async def reconciliar(self, *, limite: int = 100) -> ResumenSincronizacion:
        """Compara lo sincronizado con lo que el proveedor dice que hay.

        Detecta lo que ningun error de escritura revela: que el evento
        desaparecio o cambio **mientras el sistema no miraba**. Sin este
        barrido, un evento borrado en el telefono del profesional se quedaria
        marcado SINCRONIZADO para siempre y su agenda externa mostraria el
        hueco como libre.
        """
        consulta = (
            select(CalendarioEvento)
            .where(
                CalendarioEvento.estado == EstadoEventoCalendario.SINCRONIZADO.value,
                CalendarioEvento.external_event_id.is_not(None),
            )
            .order_by(CalendarioEvento.sincronizado_en)
            .limit(limite)
        )
        eventos = list((await self._sesion.execute(consulta)).scalars().all())

        resumen = ResumenSincronizacion()
        for evento in eventos:
            conexion = await self._sesion.get(CalendarioConexion, evento.calendario_conexion_id)
            if conexion is None:
                resumen = _con(resumen, sin_conexion=resumen.sin_conexion + 1)
                continue
            credenciales = self._credenciales(conexion)
            adaptador = self._proveedores.obtener(conexion.proveedor)
            if credenciales is None or adaptador is None:
                resumen = _con(resumen, sin_conexion=resumen.sin_conexion + 1)
                continue

            cita = await self._sesion.get(Cita, evento.cita_id)
            if cita is None or cita.estado not in ESTADOS_CON_REFLEJO:
                continue

            assert evento.external_event_id is not None
            estado = await adaptador.consultar(credenciales, evento.external_event_id)

            if not estado.existe:
                # Se marca y se deja que `sincronizar_pendientes` lo recree.
                # Recrearlo aqui mezclaria lectura y escritura en el mismo
                # barrido, y un fallo a medias dejaria el estado indefinido.
                evento.estado = EstadoEventoCalendario.ELIMINADO_EXTERNAMENTE.value
                evento.ultimo_error = "El evento ya no existe en el proveedor."
                evento.intentos = 0
                logger.info(
                    "calendario.reconciliacion.evento_ausente",
                    evento_id=str(evento.id),
                    cita_id=str(evento.cita_id),
                )
                resumen = _con(resumen, eliminados=resumen.eliminados + 1)
                continue

            if estado.etag is not None and estado.etag != evento.etag:
                evento.estado = EstadoEventoCalendario.CONFLICTO.value
                evento.ultimo_error = (
                    "El evento cambio en el proveedor. No se sobrescribe: requiere revision humana."
                )
                evento.etag = estado.etag
                logger.warning(
                    "calendario.reconciliacion.conflicto",
                    evento_id=str(evento.id),
                    cita_id=str(evento.cita_id),
                )
                resumen = _con(resumen, conflictos=resumen.conflictos + 1)

        return resumen

    # ------------------------------------------------------------------
    #  Auxiliares
    # ------------------------------------------------------------------
    @staticmethod
    def _contexto(profesional_id: uuid.UUID) -> bytes:
        """Contexto autenticado del cifrado: liga el token a su profesional.

        Un token copiado de la fila de un profesional a la de otro no
        descifra. Es lo que convierte un acceso de lectura a la base en algo
        que no basta para usar los tokens de otro.
        """
        return f"calendario:{profesional_id}".encode()

    def _credenciales(self, conexion: CalendarioConexion) -> Credenciales | None:
        if not conexion.token_acceso_cifrado or not conexion.token_refresco_cifrado:
            return None
        contexto = self._contexto(conexion.profesional_id)
        try:
            return Credenciales(
                token_acceso=self._cifrador.descifrar(
                    conexion.token_acceso_cifrado, contexto=contexto
                ),
                token_refresco=self._cifrador.descifrar(
                    conexion.token_refresco_cifrado, contexto=contexto
                ),
                calendar_id=conexion.calendar_id,
            )
        except ValueError:
            # El dato fue alterado, o la clave de cifrado cambio. No se
            # reintenta: seguir intentando con un token ilegible no mejora, y
            # el mensaje tiene que llegar a una persona.
            logger.error(
                "calendario.token_ilegible",
                conexion_id=str(conexion.id),
                nota="El token no descifra. Revise CLAVE_SECRETA o vuelva a conectar.",
            )
            return None

    async def _payload(self, cita: Cita) -> EventoExterno:
        """Evento neutro de una cita.

        Toma solo la ubicacion fisica. No consulta el servicio ni el paciente:
        no se puede filtrar lo que no se lee (RF-I09).
        """
        consultorio_nombre: str | None = None
        sede_nombre: str | None = None
        if cita.consultorio_id is not None:
            fila = (
                await self._sesion.execute(
                    select(Consultorio.nombre, Sede.nombre)
                    .join(Sede, Sede.id == Consultorio.sede_id)
                    .where(Consultorio.id == cita.consultorio_id)
                )
            ).first()
            if fila is not None:
                consultorio_nombre, sede_nombre = fila
        if sede_nombre is None:
            # `cita.sede_id` no es opcional, asi que siempre hay sede: se
            # consulta cuando la cita no tiene consultorio asignado, o cuando
            # la union anterior no devolvio fila.
            sede_nombre = await self._sesion.scalar(
                select(Sede.nombre).where(Sede.id == cita.sede_id)
            )

        return construir_evento(
            cita_id=cita.id,
            inicio=cita.inicio,
            fin=cita.fin,
            consultorio=consultorio_nombre,
            sede=sede_nombre,
            url_sistema=self._url_sistema,
        )


def _con(resumen: ResumenSincronizacion, **cambios: int) -> ResumenSincronizacion:
    datos = {
        "creados": resumen.creados,
        "actualizados": resumen.actualizados,
        "eliminados": resumen.eliminados,
        "recreados": resumen.recreados,
        "conflictos": resumen.conflictos,
        "reintentables": resumen.reintentables,
        "errores": resumen.errores,
        "sin_conexion": resumen.sin_conexion,
        "token_vencido": resumen.token_vencido,
    }
    datos.update(cambios)
    return ResumenSincronizacion(**datos)


__all__ = [
    "ESTADOS_CON_REFLEJO",
    "MARGEN_RENOVACION",
    "MAXIMO_INTENTOS_EVENTO",
    "ResumenSincronizacion",
    "ServicioCalendario",
]
