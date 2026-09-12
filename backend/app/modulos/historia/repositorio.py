"""Acceso a datos de la historia clinica.

Tres filtros, no uno
--------------------
Leer una historia clinica exige cumplir **tres** condiciones, y las tres se
aplican en SQL:

1. **Ambito.** La clinica siempre; y la lista de pacientes cuando el principal
   no tiene el comodin -- que es el caso del propio paciente escribiendo por
   WhatsApp.
2. **Relacion asistencial.** Un profesional solo alcanza a los pacientes con
   los que tiene un vinculo vigente: una cita atendida, una derivacion, una
   asignacion explicita. Sin este filtro, cualquier medico de la clinica
   leeria la historia de cualquier paciente, que es exactamente el acceso
   indebido mas frecuente y el mas dificil de justificar despues.
3. **Vigencia de la version.** Salvo que se pida el historico, solo la version
   `vigente`.

La relacion asistencial se comprueba con EXISTS y no con una union: un
paciente puede tener varias relaciones con el mismo profesional -- una por
cita -- y una union multiplicaria las filas de la historia por el numero de
relaciones.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.historia.modelos import (
    AlertaAdherencia,
    EstadoReceta,
    EstadoToma,
    NotaEvolucion,
    Receta,
    RecetaMedicamento,
    Toma,
)
from app.modulos.pacientes.modelos import RelacionAsistencial
from app.nucleo.autorizacion import Principal

_NINGUNO = uuid.UUID(int=0)


class RepositorioHistoria:
    """Consultas de la historia clinica, con los tres filtros obligatorios."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    # ------------------------------------------------------------------
    #  Relacion asistencial
    # ------------------------------------------------------------------
    async def tiene_relacion_asistencial(
        self, *, paciente_id: uuid.UUID, profesional_id: uuid.UUID, ahora: datetime
    ) -> bool:
        """Cierto si el vinculo existe y sigue vigente.

        «Vigente» significa no revocada y sin fecha de fin, o con fecha de fin
        futura. Una relacion caducada no da acceso: la derivacion de hace dos
        anos termino.
        """
        consulta = select(literal(1)).where(
            RelacionAsistencial.paciente_id == paciente_id,
            RelacionAsistencial.profesional_id == profesional_id,
            RelacionAsistencial.revocada_en.is_(None),
            or_(
                RelacionAsistencial.vigente_hasta.is_(None),
                RelacionAsistencial.vigente_hasta > ahora,
            ),
        )
        return (await self._sesion.execute(consulta.limit(1))).first() is not None

    # ------------------------------------------------------------------
    #  Notas
    # ------------------------------------------------------------------
    async def listar_notas(
        self,
        *,
        principal: Principal,
        paciente_id: uuid.UUID,
        ahora: datetime,
        incluir_historico: bool = False,
        limite: int = 50,
    ) -> list[NotaEvolucion]:
        consulta = select(NotaEvolucion).where(NotaEvolucion.paciente_id == paciente_id)
        if not incluir_historico:
            consulta = consulta.where(NotaEvolucion.vigente.is_(True))
        consulta = self._acotar(consulta, principal, ahora)

        consulta = consulta.order_by(
            NotaEvolucion.creado_en.desc(), NotaEvolucion.version.desc()
        ).limit(max(1, min(limite, 200)))
        return list((await self._sesion.execute(consulta)).scalars())

    async def obtener_nota(
        self, nota_id: uuid.UUID, *, principal: Principal, ahora: datetime
    ) -> NotaEvolucion | None:
        consulta = select(NotaEvolucion).where(NotaEvolucion.id == nota_id)
        consulta = self._acotar(consulta, principal, ahora)
        return (await self._sesion.execute(consulta)).scalar_one_or_none()

    async def obtener_version_vigente(
        self, raiz_id: uuid.UUID, *, principal: Principal, ahora: datetime
    ) -> NotaEvolucion | None:
        """Version actual de un hilo de nota.

        Se pide con `FOR UPDATE` porque quien la lee suele ir a crear la
        siguiente version, y entre leer y escribir cabe otra correccion. Sin
        el bloqueo, dos correcciones simultaneas produciran dos filas con
        `version = 2` -- la restriccion unica rechaza la segunda, pero el
        usuario ve un error de integridad en lugar de un mensaje util.
        """
        consulta = select(NotaEvolucion).where(
            NotaEvolucion.raiz_id == raiz_id, NotaEvolucion.vigente.is_(True)
        )
        consulta = self._acotar(consulta, principal, ahora)
        return (await self._sesion.execute(consulta.with_for_update())).scalar_one_or_none()

    # ------------------------------------------------------------------
    #  Recetas
    # ------------------------------------------------------------------
    async def listar_recetas(
        self,
        *,
        principal: Principal,
        paciente_id: uuid.UUID,
        ahora: datetime,
        solo_vigentes: bool = False,
    ) -> list[Receta]:
        consulta = select(Receta).where(Receta.paciente_id == paciente_id)
        if solo_vigentes:
            consulta = consulta.where(Receta.estado == EstadoReceta.CONFIRMADA.value)
        consulta = self._acotar_receta(consulta, principal, ahora)
        return list(
            (await self._sesion.execute(consulta.order_by(Receta.creado_en.desc()))).scalars()
        )

    async def obtener_receta(
        self, receta_id: uuid.UUID, *, principal: Principal, ahora: datetime, bloquear: bool = False
    ) -> Receta | None:
        consulta = select(Receta).where(Receta.id == receta_id)
        consulta = self._acotar_receta(consulta, principal, ahora)
        if bloquear:
            consulta = consulta.with_for_update()
        return (await self._sesion.execute(consulta)).scalar_one_or_none()

    async def medicamentos_de(self, receta_id: uuid.UUID) -> list[RecetaMedicamento]:
        return list(
            (
                await self._sesion.execute(
                    select(RecetaMedicamento)
                    .where(RecetaMedicamento.receta_id == receta_id)
                    .order_by(RecetaMedicamento.nombre)
                )
            ).scalars()
        )

    # ------------------------------------------------------------------
    #  Tomas
    # ------------------------------------------------------------------
    async def tomas_futuras_pendientes(
        self, receta_id: uuid.UUID, *, desde: datetime
    ) -> list[Toma]:
        """Tomas aun por ocurrir de una receta.

        Son las que hay que cancelar cuando la receta se modifica o se
        suspende. Las pasadas **no** se tocan: forman el registro de lo que
        ocurrio, y reescribirlo seria falsear el historico de adherencia.
        """
        consulta = (
            select(Toma)
            .join(RecetaMedicamento, RecetaMedicamento.id == Toma.receta_medicamento_id)
            .where(
                RecetaMedicamento.receta_id == receta_id,
                Toma.estado == EstadoToma.PENDIENTE.value,
                Toma.programada_en > desde,
            )
            .with_for_update(of=Toma)
        )
        return list((await self._sesion.execute(consulta)).scalars())

    async def contar_tomas(
        self, receta_id: uuid.UUID, *, desde: datetime, hasta: datetime
    ) -> tuple[int, int]:
        """Devuelve (esperadas, omitidas) en la ventana.

        «Esperadas» son las que ya deberian haber ocurrido: pendientes
        incluidas, porque una toma pendiente cuya hora ya paso es una toma que
        no se registro. Contar solo las resueltas daria una adherencia
        artificialmente perfecta a quien nunca responde.
        """
        base = (
            select(Toma.estado)
            .join(RecetaMedicamento, RecetaMedicamento.id == Toma.receta_medicamento_id)
            .where(
                RecetaMedicamento.receta_id == receta_id,
                Toma.programada_en >= desde,
                Toma.programada_en <= hasta,
                Toma.estado != EstadoToma.CANCELADA.value,
            )
        )
        estados = list((await self._sesion.execute(base)).scalars())
        esperadas = len(estados)
        omitidas = sum(
            1
            for estado in estados
            if estado in (EstadoToma.OMITIDA.value, EstadoToma.PENDIENTE.value)
        )
        return esperadas, omitidas

    async def alerta_abierta(self, receta_id: uuid.UUID) -> AlertaAdherencia | None:
        return (
            await self._sesion.execute(
                select(AlertaAdherencia).where(
                    AlertaAdherencia.receta_id == receta_id,
                    AlertaAdherencia.atendida_en.is_(None),
                )
            )
        ).scalar_one_or_none()

    # ------------------------------------------------------------------
    #  Filtros
    # ------------------------------------------------------------------
    def _acotar(self, consulta: Select[Any], principal: Principal, ahora: datetime) -> Select[Any]:
        """Ambito y relacion asistencial sobre `nota_evolucion`."""
        if principal.clinica_id is None:
            return consulta.where(NotaEvolucion.clinica_id == _NINGUNO)
        consulta = consulta.where(NotaEvolucion.clinica_id == principal.clinica_id)

        ambito = principal.ambito
        if not ambito.todos_los_pacientes:
            if not ambito.pacientes:
                return consulta.where(NotaEvolucion.paciente_id == _NINGUNO)
            consulta = consulta.where(NotaEvolucion.paciente_id.in_(ambito.pacientes))

        return self._exigir_relacion(consulta, NotaEvolucion.paciente_id, principal, ahora)

    def _acotar_receta(
        self, consulta: Select[Any], principal: Principal, ahora: datetime
    ) -> Select[Any]:
        if principal.clinica_id is None:
            return consulta.where(Receta.clinica_id == _NINGUNO)
        consulta = consulta.where(Receta.clinica_id == principal.clinica_id)

        ambito = principal.ambito
        if not ambito.todos_los_pacientes:
            if not ambito.pacientes:
                return consulta.where(Receta.paciente_id == _NINGUNO)
            consulta = consulta.where(Receta.paciente_id.in_(ambito.pacientes))

        return self._exigir_relacion(consulta, Receta.paciente_id, principal, ahora)

    def _exigir_relacion(
        self,
        consulta: Select[Any],
        columna_paciente: Any,
        principal: Principal,
        ahora: datetime,
    ) -> Select[Any]:
        """Anade la condicion de relacion asistencial, cuando aplica.

        **No aplica cuando el principal es el propio paciente**: nadie
        necesita una derivacion para leer su propia historia. Tampoco cuando
        el principal no es un profesional -- un auditor revisando accesos no
        tiene relaciones asistenciales y su acceso se controla por permiso y
        por auditoria, no por vinculo.
        """
        if principal.profesional_id is None:
            return consulta

        # EXISTS y no union: un paciente puede tener varias relaciones con el
        # mismo profesional -- una por cita --, y la union multiplicaria las
        # filas de la historia por el numero de relaciones.
        return consulta.where(
            select(literal(1))
            .select_from(RelacionAsistencial)
            .where(
                RelacionAsistencial.paciente_id == columna_paciente,
                RelacionAsistencial.profesional_id == principal.profesional_id,
                RelacionAsistencial.revocada_en.is_(None),
                or_(
                    RelacionAsistencial.vigente_hasta.is_(None),
                    RelacionAsistencial.vigente_hasta > ahora,
                ),
            )
            .exists()
        )


__all__ = ["RepositorioHistoria"]
