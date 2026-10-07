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

from sqlalchemy import Select, case, func, literal, or_, select
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
from app.modulos.profesionales.modelos import Profesional
from app.nucleo.autorizacion import Principal

_NINGUNO = uuid.UUID(int=0)
_MINIMO_TOMAS_PARA_CANDIDATA = 4
_UMBRAL_CANDIDATA = 0.25


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
        especialidades: frozenset[uuid.UUID] | None = None,
        limite: int = 50,
    ) -> list[NotaEvolucion]:
        """Notas del paciente; con `especialidades`, solo las de sus autores.

        La especialidad de una nota es la de quien la escribió. Un conjunto
        vacío no devuelve nada: sin especialidad desde la que revisar no hay
        notas que mostrar.
        """
        consulta = select(NotaEvolucion).where(NotaEvolucion.paciente_id == paciente_id)
        if not incluir_historico:
            consulta = consulta.where(NotaEvolucion.vigente.is_(True))
        if especialidades is not None:
            consulta = consulta.where(
                NotaEvolucion.profesional_id.in_(
                    select(Profesional.id).where(Profesional.especialidad_id.in_(especialidades))
                )
            )
        consulta = self._acotar(consulta, principal, ahora)
        if not principal.tiene_permiso("historia_clinica.leer_sensible"):
            consulta = consulta.where(NotaEvolucion.nivel_sensibilidad != "N3")

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

    async def listar_tomas(
        self,
        *,
        principal: Principal,
        paciente_id: uuid.UUID,
        desde: datetime,
        hasta: datetime,
        ahora: datetime,
        limite: int = 200,
    ) -> list[tuple[Toma, RecetaMedicamento]]:
        """Tomas programadas de un paciente en una ventana, con su medicamento.

        Pasa por `_acotar_receta`, el mismo filtro que el resto del modulo: el
        acceso a la medicacion de alguien exige ambito **y** relacion
        asistencial, igual que su historia. Una via de consulta que no lo
        aplicara seria una fuga por la puerta de al lado.

        Se devuelve el medicamento junto a la toma porque una toma sin saber de
        que es no le sirve a nadie, y resolverlo despues obligaria a una
        consulta por fila.

        El limite tiene techo: una pauta larga produce cientos de tomas y una
        consulta sin cota agotaria la memoria del proceso.
        """
        limite = max(1, min(limite, 500))
        consulta = (
            select(Toma, RecetaMedicamento)
            .join(RecetaMedicamento, RecetaMedicamento.id == Toma.receta_medicamento_id)
            .join(Receta, Receta.id == RecetaMedicamento.receta_id)
            .where(
                Toma.paciente_id == paciente_id,
                Toma.programada_en >= desde,
                Toma.programada_en < hasta,
            )
        )
        consulta = self._acotar_receta(consulta, principal, ahora)
        consulta = consulta.order_by(Toma.programada_en).limit(limite)
        return [(fila[0], fila[1]) for fila in (await self._sesion.execute(consulta)).all()]

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

    async def listar_alertas_abiertas(
        self, *, principal: Principal, ahora: datetime, limite: int = 100
    ) -> list[AlertaAdherencia]:
        consulta = (
            select(AlertaAdherencia)
            .join(Receta, Receta.id == AlertaAdherencia.receta_id)
            .where(AlertaAdherencia.atendida_en.is_(None))
        )
        consulta = self._acotar_receta(consulta, principal, ahora)
        consulta = consulta.order_by(
            AlertaAdherencia.severidad.desc(), AlertaAdherencia.creado_en
        ).limit(max(1, min(limite, 200)))
        return list((await self._sesion.execute(consulta)).scalars())

    async def obtener_alerta(
        self, alerta_id: uuid.UUID, *, principal: Principal, ahora: datetime, bloquear: bool = False
    ) -> AlertaAdherencia | None:
        consulta = (
            select(AlertaAdherencia)
            .join(Receta, Receta.id == AlertaAdherencia.receta_id)
            .where(AlertaAdherencia.id == alerta_id)
        )
        consulta = self._acotar_receta(consulta, principal, ahora)
        if bloquear:
            consulta = consulta.with_for_update(of=AlertaAdherencia)
        return (await self._sesion.execute(consulta)).scalar_one_or_none()

    async def recetas_candidatas_adherencia(
        self, *, desde: datetime, hasta: datetime, limite: int = 200
    ) -> list[tuple[uuid.UUID, uuid.UUID]]:
        omitida = case(
            (Toma.estado.in_((EstadoToma.OMITIDA.value, EstadoToma.PENDIENTE.value)), 1),
            else_=0,
        )
        consulta = (
            select(Receta.id, Receta.clinica_id)
            .join(RecetaMedicamento, RecetaMedicamento.receta_id == Receta.id)
            .join(Toma, Toma.receta_medicamento_id == RecetaMedicamento.id)
            .where(
                Receta.estado == EstadoReceta.CONFIRMADA.value,
                Toma.estado != EstadoToma.CANCELADA.value,
                Toma.programada_en >= desde,
                Toma.programada_en <= hasta,
                ~select(literal(1))
                .select_from(AlertaAdherencia)
                .where(
                    AlertaAdherencia.receta_id == Receta.id,
                    AlertaAdherencia.atendida_en.is_(None),
                )
                .exists(),
            )
            .group_by(Receta.id, Receta.clinica_id)
            .having(func.count(Toma.id) >= _MINIMO_TOMAS_PARA_CANDIDATA)
            .having(func.sum(omitida) >= func.count(Toma.id) * _UMBRAL_CANDIDATA)
            .order_by(Receta.id)
            .limit(max(1, min(limite, 500)))
        )
        return [(fila[0], fila[1]) for fila in (await self._sesion.execute(consulta)).all()]

    # ------------------------------------------------------------------
    #  Filtros
    # ------------------------------------------------------------------
    def _acotar(self, consulta: Select[Any], principal: Principal, ahora: datetime) -> Select[Any]:
        """Ambito y relacion asistencial sobre `nota_evolucion`."""
        if principal.clinica_id is None:
            return consulta.where(NotaEvolucion.clinica_id == _NINGUNO)
        consulta = consulta.where(NotaEvolucion.clinica_id == principal.clinica_id)
        if not principal.tiene_permiso("historia_clinica.leer_sensible"):
            consulta = consulta.where(NotaEvolucion.nivel_sensibilidad != "N3")

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
        if not principal.tiene_permiso("historia_clinica.leer_sensible"):
            consulta = consulta.where(Receta.nivel_sensibilidad != "N3")

        ambito = principal.ambito
        if not ambito.todos_los_pacientes:
            if not ambito.pacientes:
                return consulta.where(Receta.paciente_id == _NINGUNO)
            consulta = consulta.where(Receta.paciente_id.in_(ambito.pacientes))

        return self._exigir_relacion(consulta, Receta.paciente_id, principal, ahora)

    def consulta_receta_autorizada(
        self, consulta: Select[Any], *, principal: Principal, ahora: datetime
    ) -> Select[Any]:
        """Aplica a una consulta el ámbito y la relación asistencial de recetas.

        Expuesto para informes agregados de otros módulos: reutiliza la misma
        frontera clínica que el detalle de la historia, sin devolver filas a
        esos módulos ni duplicar su política de acceso.
        """
        return self._acotar_receta(consulta, principal, ahora)

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
