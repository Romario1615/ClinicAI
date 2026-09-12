"""Servicio de lista de espera.

La carrera que este modulo tiene que ganar
------------------------------------------
Dos pacientes aceptan la misma oferta en el mismo segundo. Uno tiene que
quedarse con la cita y el otro tiene que recibir «ese turno acaba de tomarse»
-- nunca los dos una confirmacion, y nunca los dos un rechazo.

Se resuelve con tres piezas que actuan juntas:

1. **Bloqueo consultivo** sobre el turno liberado
   (`pg_advisory_xact_lock`). Serializa a los que compiten por el mismo hueco
   sin bloquear al resto de la agenda. Se libera solo al terminar la
   transaccion -- con commit o con rollback --, lo que descarta la clase de
   fallo mas peligrosa de los bloqueos: quedarse tomado para siempre porque
   el proceso murio.

2. **Indice unico parcial** de una oferta activa por turno. Es la red que
   sigue en pie si alguien anade otro camino que no tome el bloqueo.

3. **La restriccion de exclusion de la agenda**, que ya impide dos citas
   solapadas. Aunque las dos aceptaciones llegaran a crear cita, la segunda
   fallaria ahi.

A quien se ofrece primero
-------------------------
Prioridad alta antes que normal, y dentro de cada grupo, quien lleva mas
tiempo esperando. **No** se ofrece a quien ya tiene una oferta en curso ni a
quien ha dejado vencer demasiadas: quien nunca responde bloquearia la cola y
el turno se perderia igual, solo que mas tarde.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita, EstadoCita
from app.modulos.lista_espera.modelos import (
    EntradaListaEspera,
    EstadoEspera,
    EstadoOferta,
    OfertaTurno,
    PrioridadEspera,
)
from app.nucleo.auditoria import AccionAuditada, EntradaAuditoria, construir_entrada
from app.nucleo.autorizacion import Principal
from app.nucleo.bd import tomar_bloqueo_consultivo
from app.nucleo.errores import (
    ConflictoEstado,
    OfertaExpirada,
    OfertaYaResuelta,
    PermisoDenegado,
    RecursoNoEncontrado,
)
from app.nucleo.errores_bd import traducir_o_propagar
from app.nucleo.reloj import Reloj

# Espacio de nombres del bloqueo consultivo. Separarlo evita que este uso
# colisione con otro que tome un bloqueo sobre un identificador parecido.
ESPACIO_BLOQUEO_OFERTA = 7301

# A quien deja vencer tantas ofertas se le deja de ofrecer. No es un castigo:
# cada oferta ignorada retiene el turno hasta que vence, y el hueco se pierde
# igual pero mas tarde y para todos.
MAXIMO_OFERTAS_VENCIDAS = 3


@dataclass(frozen=True, slots=True)
class ResultadoOferta:
    oferta: OfertaTurno | None = None
    cita: Cita | None = None
    auditoria: tuple[EntradaAuditoria, ...] = field(default_factory=tuple)


class ServicioListaEspera:
    """Alta en lista, oferta de turnos liberados y resolucion de la carrera."""

    def __init__(
        self,
        sesion: AsyncSession,
        reloj: Reloj,
        *,
        minutos_vigencia_oferta: int = 30,
    ) -> None:
        self._sesion = sesion
        self._reloj = reloj
        self._minutos = minutos_vigencia_oferta

    # ==================================================================
    #  Alta y baja
    # ==================================================================
    async def anotar(
        self,
        *,
        principal: Principal,
        paciente_id: uuid.UUID,
        sede_id: uuid.UUID,
        especialidad_id: uuid.UUID,
        servicio_id: uuid.UUID | None = None,
        profesional_id: uuid.UUID | None = None,
        prioridad: str = PrioridadEspera.NORMAL.value,
        horas_antelacion_minima: int = 4,
        preferencias: dict[str, object] | None = None,
        nota: str | None = None,
    ) -> EntradaListaEspera:
        """Anota a un paciente en la lista.

        El indice unico parcial impide anotarlo dos veces en la misma
        especialidad y sede mientras la entrada siga viva. Se traduce a un
        error de dominio: «ya esta en la lista» es informacion util, no un
        fallo.
        """
        self._exigir(principal, "lista_espera.gestionar")
        if principal.clinica_id is None:
            raise PermisoDenegado("La sesion no tiene clinica asociada.")
        if not principal.ambito.cubre_sede(sede_id):
            # 404 y no 403: un 403 confirmaria que la sede existe.
            raise RecursoNoEncontrado("La sede solicitada no existe.")

        entrada = EntradaListaEspera(
            clinica_id=principal.clinica_id,
            paciente_id=paciente_id,
            sede_id=sede_id,
            especialidad_id=especialidad_id,
            servicio_id=servicio_id,
            profesional_id=profesional_id,
            prioridad=prioridad,
            horas_antelacion_minima=horas_antelacion_minima,
            preferencias=preferencias,
            nota=nota,
            creado_por=principal.actor_id,
        )
        self._sesion.add(entrada)
        await self._flush()
        return entrada

    async def cancelar(
        self, entrada_id: uuid.UUID, *, principal: Principal, motivo: str | None = None
    ) -> EntradaListaEspera:
        self._exigir(principal, "lista_espera.gestionar")

        entrada = await self._obtener_entrada(entrada_id, principal)
        if entrada.estado in (EstadoEspera.CUMPLIDA.value, EstadoEspera.CANCELADA.value):
            raise ConflictoEstado(f"La entrada ya esta {entrada.estado.lower()}.")

        entrada.estado = EstadoEspera.CANCELADA.value
        entrada.nota = motivo or entrada.nota
        entrada.actualizado_por = principal.actor_id

        # Si tenia una oferta en curso, se marca perdida: el turno vuelve a
        # estar disponible para el siguiente de la cola de inmediato, en lugar
        # de esperar a que venza el plazo de alguien que ya no lo quiere.
        oferta = await self._oferta_activa_de(entrada.id)
        if oferta is not None:
            oferta.estado = EstadoOferta.PERDIDA.value
            oferta.respondida_en = self._reloj.ahora()

        await self._flush()
        return entrada

    # ==================================================================
    #  Oferta
    # ==================================================================
    async def ofrecer_turno(self, cita_liberada: Cita, *, principal: Principal) -> ResultadoOferta:
        """Ofrece un turno liberado al primero de la cola.

        Devuelve una oferta, o `None` si no hay nadie a quien ofrecerselo. Eso
        ultimo no es un error: la mayoria de las cancelaciones ocurren sin
        nadie esperando esa especialidad.
        """
        ahora = self._reloj.ahora()

        # Serializa a quien compita por ESTE turno, sin tocar el resto de la
        # agenda. Ver la nota del encabezado.
        await tomar_bloqueo_consultivo(
            self._sesion, espacio=ESPACIO_BLOQUEO_OFERTA, clave=str(cita_liberada.id)
        )

        # Con el bloqueo tomado, se comprueba que nadie se haya adelantado.
        if await self._existe_oferta_activa(cita_liberada.id):
            return ResultadoOferta()

        candidato = await self._siguiente_candidato(cita_liberada, ahora=ahora)
        if candidato is None:
            return ResultadoOferta()

        oferta = OfertaTurno(
            lista_espera_id=candidato.id,
            cita_liberada_id=cita_liberada.id,
            estado=EstadoOferta.OFRECIDA.value,
            expira_en=ahora + timedelta(minutes=self._minutos),
            creado_por=principal.actor_id,
        )
        self._sesion.add(oferta)

        candidato.estado = EstadoEspera.OFERTADA.value
        candidato.ofertas_realizadas += 1
        await self._flush()

        return ResultadoOferta(
            oferta=oferta,
            auditoria=(
                construir_entrada(
                    accion=AccionAuditada.OFERTA_ENVIADA,
                    principal=principal,
                    ahora=ahora,
                    entidad_tipo="oferta_turno",
                    entidad_id=oferta.id,
                    paciente_id=candidato.paciente_id,
                    sede_id=candidato.sede_id,
                ),
            ),
        )

    async def aceptar_oferta(
        self, oferta_id: uuid.UUID, *, principal: Principal
    ) -> ResultadoOferta:
        """Acepta una oferta y crea la cita.

        Es el punto donde se resuelve la carrera. Dos aceptaciones simultaneas
        del mismo turno: la primera que toma el bloqueo consultivo gana; la
        segunda, al entrar, encuentra la oferta ya resuelta y recibe
        `OfertaYaResuelta`.
        """
        ahora = self._reloj.ahora()

        oferta = await self._sesion.get(OfertaTurno, oferta_id, with_for_update=True)
        if oferta is None:
            raise RecursoNoEncontrado("La oferta solicitada no existe.")

        # El bloqueo va sobre el TURNO, no sobre la oferta: lo que se disputa
        # es el hueco, y dos ofertas distintas del mismo hueco no deberian
        # existir pero el bloqueo las serializa igual.
        await tomar_bloqueo_consultivo(
            self._sesion, espacio=ESPACIO_BLOQUEO_OFERTA, clave=str(oferta.cita_liberada_id)
        )

        if oferta.estado != EstadoOferta.OFRECIDA.value:
            raise OfertaYaResuelta(
                "Esta oferta ya fue respondida o el turno se asigno a otra persona."
            )
        if oferta.expira_en <= ahora:
            # Se marca vencida aqui mismo: dejarla OFRECIDA haria que el
            # barrido la volviera a mirar y que el turno siguiera retenido.
            oferta.estado = EstadoOferta.EXPIRADA.value
            await self._flush()
            raise OfertaExpirada("El plazo para aceptar este turno ya vencio.")

        entrada = await self._sesion.get(EntradaListaEspera, oferta.lista_espera_id)
        if entrada is None:  # pragma: sin cobertura - clave externa en cascada
            raise RecursoNoEncontrado("La entrada de lista de espera no existe.")

        liberada = await self._sesion.get(Cita, oferta.cita_liberada_id)
        if liberada is None:  # pragma: sin cobertura - clave externa en cascada
            raise RecursoNoEncontrado("El turno ofrecido ya no existe.")

        cita = Cita(
            clinica_id=liberada.clinica_id,
            sede_id=liberada.sede_id,
            consultorio_id=liberada.consultorio_id,
            paciente_id=entrada.paciente_id,
            profesional_id=liberada.profesional_id,
            servicio_id=entrada.servicio_id or liberada.servicio_id,
            inicio=liberada.inicio,
            duracion_minutos=liberada.duracion_minutos,
            minutos_preparacion=liberada.minutos_preparacion,
            estado=EstadoCita.CONFIRMED.value,
            origen="LISTA_ESPERA",
            confirmada_en=ahora,
            cita_origen_id=liberada.id,
            creado_por=principal.actor_id,
        )
        self._sesion.add(cita)

        # Se escribe la cita ANTES de cerrar la oferta. Si la restriccion de
        # exclusion rechaza el turno -- alguien lo tomo por otra via --, la
        # transaccion entera se deshace y la oferta queda como estaba, viva y
        # aceptable. Al reves, la oferta quedaria consumida sin cita.
        await self._flush()

        oferta.estado = EstadoOferta.ACEPTADA.value
        oferta.respondida_en = ahora
        oferta.cita_creada_id = cita.id
        entrada.estado = EstadoEspera.CUMPLIDA.value
        entrada.cita_resultante_id = cita.id
        await self._flush()

        return ResultadoOferta(
            oferta=oferta,
            cita=cita,
            auditoria=(
                construir_entrada(
                    accion=AccionAuditada.OFERTA_ACEPTADA,
                    principal=principal,
                    ahora=ahora,
                    entidad_tipo="oferta_turno",
                    entidad_id=oferta.id,
                    paciente_id=entrada.paciente_id,
                    sede_id=entrada.sede_id,
                ),
                construir_entrada(
                    accion=AccionAuditada.CITA_CREADA,
                    principal=principal,
                    ahora=ahora,
                    entidad_tipo="cita",
                    entidad_id=cita.id,
                    paciente_id=cita.paciente_id,
                    sede_id=cita.sede_id,
                    origen_cita="LISTA_ESPERA",
                ),
            ),
        )

    async def rechazar_oferta(
        self, oferta_id: uuid.UUID, *, principal: Principal, motivo: str | None = None
    ) -> ResultadoOferta:
        """Rechaza la oferta y devuelve a la persona a la cola.

        Rechazar **no** la saca de la lista: sigue esperando un turno que le
        sirva. Sacarla obligaria a volver a apuntarse, y en la practica nadie
        lo hace.
        """
        ahora = self._reloj.ahora()
        oferta = await self._sesion.get(OfertaTurno, oferta_id, with_for_update=True)
        if oferta is None:
            raise RecursoNoEncontrado("La oferta solicitada no existe.")
        if oferta.estado != EstadoOferta.OFRECIDA.value:
            raise OfertaYaResuelta("Esta oferta ya fue respondida.")

        oferta.estado = EstadoOferta.RECHAZADA.value
        oferta.respondida_en = ahora
        oferta.motivo_rechazo = motivo

        entrada = await self._sesion.get(EntradaListaEspera, oferta.lista_espera_id)
        if entrada is not None:
            entrada.estado = EstadoEspera.ACTIVA.value

        await self._flush()
        return ResultadoOferta(
            oferta=oferta,
            auditoria=(
                construir_entrada(
                    accion=AccionAuditada.OFERTA_RECHAZADA,
                    principal=principal,
                    ahora=ahora,
                    entidad_tipo="oferta_turno",
                    entidad_id=oferta.id,
                ),
            ),
        )

    async def expirar_ofertas_vencidas(
        self, *, principal: Principal, limite: int = 100
    ) -> list[OfertaTurno]:
        """Vence las ofertas sin respuesta y devuelve a la cola a sus duenos.

        Lo ejecuta el worker. Sin este barrido, una oferta ignorada retiene el
        turno para siempre y el hueco se pierde -- el mismo problema que la
        lista de espera venia a resolver.

        Se exige permiso aunque lo llame el worker: el principal del sistema
        lo tiene, y comprobarlo evita que un endpoint futuro exponga el
        barrido sin control por descuido.
        """
        if not principal.es_sistema:
            self._exigir(principal, "lista_espera.gestionar")

        ahora = self._reloj.ahora()
        vencidas = list(
            (
                await self._sesion.execute(
                    select(OfertaTurno)
                    .where(
                        OfertaTurno.estado == EstadoOferta.OFRECIDA.value,
                        OfertaTurno.expira_en <= ahora,
                    )
                    .order_by(OfertaTurno.expira_en)
                    .limit(limite)
                    .with_for_update(skip_locked=True)
                )
            ).scalars()
        )

        for oferta in vencidas:
            oferta.estado = EstadoOferta.EXPIRADA.value
            entrada = await self._sesion.get(EntradaListaEspera, oferta.lista_espera_id)
            if entrada is None:
                continue
            entrada.ofertas_vencidas += 1
            # A quien nunca responde se le deja de ofrecer: cada oferta
            # ignorada retiene un turno hasta que vence, y el hueco se pierde
            # igual pero mas tarde y para todos los demas.
            entrada.estado = (
                EstadoEspera.EXPIRADA.value
                if entrada.ofertas_vencidas >= MAXIMO_OFERTAS_VENCIDAS
                else EstadoEspera.ACTIVA.value
            )

        if vencidas:
            await self._flush()
        return vencidas

    # ==================================================================
    #  Auxiliares
    # ==================================================================
    async def _siguiente_candidato(
        self, cita: Cita, *, ahora: datetime
    ) -> EntradaListaEspera | None:
        """Primero de la cola que puede aceptar este turno.

        El orden es prioridad y despues antiguedad. El filtro de antelacion
        evita ofrecer un hueco de dentro de veinte minutos a quien necesita
        cuatro horas para llegar: aceptarlo y no presentarse es peor que no
        recibir la oferta.
        """
        limite_antelacion = (cita.inicio - ahora).total_seconds() / 3600

        consulta = (
            select(EntradaListaEspera)
            .where(
                EntradaListaEspera.estado == EstadoEspera.ACTIVA.value,
                EntradaListaEspera.sede_id == cita.sede_id,
                EntradaListaEspera.clinica_id == cita.clinica_id,
                EntradaListaEspera.horas_antelacion_minima <= limite_antelacion,
                EntradaListaEspera.ofertas_vencidas < MAXIMO_OFERTAS_VENCIDAS,
            )
            .order_by(
                # `ALTA` < `NORMAL` alfabeticamente, asi que el orden
                # ascendente coloca la prioridad alta primero. Es una
                # coincidencia afortunada, pero se deja explicito el intento
                # por si algun dia se anade otra prioridad.
                EntradaListaEspera.prioridad.asc(),
                EntradaListaEspera.creado_en.asc(),
            )
            .with_for_update(skip_locked=True)
            .limit(20)
        )
        candidatos = list((await self._sesion.execute(consulta)).scalars())

        for candidato in candidatos:
            if candidato.profesional_id and candidato.profesional_id != cita.profesional_id:
                continue
            if candidato.disponible_desde and cita.inicio.date() < candidato.disponible_desde:
                continue
            if candidato.disponible_hasta and cita.inicio.date() > candidato.disponible_hasta:
                continue
            return candidato
        return None

    async def _existe_oferta_activa(self, cita_id: uuid.UUID) -> bool:
        return (
            await self._sesion.execute(
                select(OfertaTurno.id).where(
                    OfertaTurno.cita_liberada_id == cita_id,
                    OfertaTurno.estado == EstadoOferta.OFRECIDA.value,
                )
            )
        ).first() is not None

    async def _oferta_activa_de(self, entrada_id: uuid.UUID) -> OfertaTurno | None:
        return (
            await self._sesion.execute(
                select(OfertaTurno).where(
                    OfertaTurno.lista_espera_id == entrada_id,
                    OfertaTurno.estado == EstadoOferta.OFRECIDA.value,
                )
            )
        ).scalar_one_or_none()

    async def _obtener_entrada(
        self, entrada_id: uuid.UUID, principal: Principal
    ) -> EntradaListaEspera:
        entrada = await self._sesion.get(EntradaListaEspera, entrada_id)
        if entrada is None or entrada.clinica_id != principal.clinica_id:
            raise RecursoNoEncontrado("La entrada solicitada no existe.")
        if not principal.ambito.cubre_sede(entrada.sede_id):
            raise RecursoNoEncontrado("La entrada solicitada no existe.")
        return entrada

    def _exigir(self, principal: Principal, permiso: str) -> None:
        if not principal.tiene_permiso(permiso):
            raise PermisoDenegado("No tiene permiso para gestionar la lista de espera.")

    async def _flush(self) -> None:
        try:
            await self._sesion.flush()
        except SQLAlchemyError as exc:
            await self._sesion.rollback()
            raise traducir_o_propagar(exc) from exc


__all__ = [
    "ESPACIO_BLOQUEO_OFERTA",
    "MAXIMO_OFERTAS_VENCIDAS",
    "ResultadoOferta",
    "ServicioListaEspera",
]
