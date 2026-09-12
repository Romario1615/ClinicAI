"""Lectura del catalogo de la organizacion.

Solo lectura. Crear y modificar sedes, especialidades y servicios es
administracion de la clinica y llega mas adelante; lo que hace falta ahora es
que la interfaz pueda ofrecer las opciones existentes en lugar de pedir que
alguien teclee identificadores UUID a mano.

El filtro de ambito es obligatorio y no opcional
------------------------------------------------
Cada consulta recibe el `Principal` y filtra por su clinica **siempre**, y por
sus sedes cuando el ambito no incluye el comodin. No hay una variante "sin
filtro" ni un parametro para desactivarlo: si existiera, tarde o temprano
alguien la usaria en un endpoint por comodidad y esa seria la fuga.

Con `clinica_id` ausente en el principal se devuelve el conjunto vacio, no
todo. Un principal sin clinica es un error de programacion o un actor del
sistema mal construido, y el lado seguro de un error es no mostrar nada.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Select, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.organizacion.modelos import (
    Clinica,
    Consultorio,
    Especialidad,
    Sede,
    Servicio,
)
from app.modulos.profesionales.modelos import Profesional, ProfesionalSede
from app.nucleo.autorizacion import Principal

# Identificador que no puede existir. Se usa para forzar un resultado vacio
# de forma explicita, que es mas seguro que devolver la consulta sin filtrar.
_NINGUNO = uuid.UUID(int=0)


class RepositorioCatalogo:
    """Consultas del catalogo, siempre dentro del ambito del principal."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    # ------------------------------------------------------------------
    #  Clinica
    # ------------------------------------------------------------------
    async def obtener_clinica(self, principal: Principal) -> Clinica | None:
        """La clinica del principal. Nunca otra."""
        if principal.clinica_id is None:
            return None
        return (
            await self._sesion.execute(
                select(Clinica).where(
                    Clinica.id == principal.clinica_id,
                    Clinica.anulado_en.is_(None),
                )
            )
        ).scalar_one_or_none()

    # ------------------------------------------------------------------
    #  Sedes y consultorios
    # ------------------------------------------------------------------
    async def listar_sedes(self, principal: Principal) -> list[Sede]:
        consulta = select(Sede).where(Sede.anulado_en.is_(None), Sede.activa.is_(True))
        consulta = self._acotar_a_clinica(consulta, Sede.clinica_id, principal)

        ambito = principal.ambito
        if not ambito.todas_las_sedes:
            if not ambito.sedes:
                return []
            consulta = consulta.where(Sede.id.in_(ambito.sedes))

        return list((await self._sesion.execute(consulta.order_by(Sede.nombre))).scalars())

    async def listar_consultorios(
        self, principal: Principal, *, sede_id: uuid.UUID | None = None
    ) -> list[Consultorio]:
        """Consultorios de las sedes que el principal alcanza.

        Se unen con `Sede` en lugar de filtrar por `sede_id` directamente:
        `Consultorio` no lleva `clinica_id`, y sin la union una sede de otra
        clinica con el mismo identificador de consultorio pasaria el filtro.
        """
        consulta = (
            select(Consultorio)
            .join(Sede, Sede.id == Consultorio.sede_id)
            .where(
                Consultorio.anulado_en.is_(None),
                Consultorio.activo.is_(True),
                Sede.anulado_en.is_(None),
            )
        )
        consulta = self._acotar_a_clinica(consulta, Sede.clinica_id, principal)
        consulta = self._acotar_a_sedes(consulta, Consultorio.sede_id, principal)

        if sede_id is not None:
            consulta = consulta.where(Consultorio.sede_id == sede_id)

        return list((await self._sesion.execute(consulta.order_by(Consultorio.nombre))).scalars())

    # ------------------------------------------------------------------
    #  Especialidades y servicios
    # ------------------------------------------------------------------
    async def listar_especialidades(self, principal: Principal) -> list[Especialidad]:
        consulta = select(Especialidad).where(
            Especialidad.anulado_en.is_(None), Especialidad.activa.is_(True)
        )
        consulta = self._acotar_a_clinica(consulta, Especialidad.clinica_id, principal)

        ambito = principal.ambito
        if not ambito.todas_las_especialidades:
            if not ambito.especialidades:
                return []
            consulta = consulta.where(Especialidad.id.in_(ambito.especialidades))

        return list((await self._sesion.execute(consulta.order_by(Especialidad.nombre))).scalars())

    async def listar_servicios(
        self, principal: Principal, *, especialidad_id: uuid.UUID | None = None
    ) -> list[Servicio]:
        consulta = select(Servicio).where(Servicio.anulado_en.is_(None), Servicio.activo.is_(True))
        consulta = self._acotar_a_clinica(consulta, Servicio.clinica_id, principal)

        ambito = principal.ambito
        if not ambito.todas_las_especialidades:
            if not ambito.especialidades:
                return []
            consulta = consulta.where(Servicio.especialidad_id.in_(ambito.especialidades))

        if especialidad_id is not None:
            consulta = consulta.where(Servicio.especialidad_id == especialidad_id)

        return list((await self._sesion.execute(consulta.order_by(Servicio.nombre))).scalars())

    # ------------------------------------------------------------------
    #  Profesionales
    # ------------------------------------------------------------------
    async def listar_profesionales(
        self,
        principal: Principal,
        *,
        especialidad_id: uuid.UUID | None = None,
        sede_id: uuid.UUID | None = None,
    ) -> list[Profesional]:
        """Profesionales que el principal alcanza.

        El filtro por sede se hace con `EXISTS` sobre `profesional_sede` y no
        con una union. El motivo es concreto: un profesional puede atender en
        varias sedes, y una union produciria una fila por sede -- el mismo
        profesional repetido tantas veces como sedes tenga. El desplegable de
        la interfaz lo mostraria duplicado.
        """
        consulta = select(Profesional).where(
            Profesional.anulado_en.is_(None), Profesional.activo.is_(True)
        )
        consulta = self._acotar_a_clinica(consulta, Profesional.clinica_id, principal)

        ambito = principal.ambito
        if not ambito.todos_los_profesionales:
            if not ambito.profesionales:
                return []
            consulta = consulta.where(Profesional.id.in_(ambito.profesionales))

        # El ambito de especialidad se aplica igual que en especialidades y
        # servicios: vacio significa ningun acceso, no "sin restriccion".
        #
        # Antes esta rama solo filtraba cuando la lista tenia elementos, de
        # modo que un ambito de especialidad vacio devolvia CERO especialidades
        # y CERO servicios pero TODOS los profesionales. La misma condicion
        # producia dos respuestas distintas segun el endpoint, que es la peor
        # propiedad posible en un modelo de autorizacion: deja de ser
        # predecible.
        if not ambito.todas_las_especialidades:
            if not ambito.especialidades:
                return []
            consulta = consulta.where(Profesional.especialidad_id.in_(ambito.especialidades))

        if especialidad_id is not None:
            consulta = consulta.where(Profesional.especialidad_id == especialidad_id)

        sedes_pedidas = self._sedes_efectivas(principal, sede_id)
        if sedes_pedidas is not None:
            if not sedes_pedidas:
                return []
            # `literal(1)` y no una columna concreta: `profesional_sede`
            # es una tabla de union con clave compuesta y no tiene columna
            # `id`, y a un EXISTS le da igual lo que se seleccione.
            consulta = consulta.where(
                select(literal(1))
                .select_from(ProfesionalSede)
                .where(
                    ProfesionalSede.profesional_id == Profesional.id,
                    ProfesionalSede.sede_id.in_(sedes_pedidas),
                )
                .exists()
            )

        return list(
            (
                await self._sesion.execute(
                    consulta.order_by(Profesional.apellido, Profesional.nombre)
                )
            ).scalars()
        )

    async def obtener_profesional(
        self, profesional_id: uuid.UUID, principal: Principal
    ) -> Profesional | None:
        consulta = select(Profesional).where(
            Profesional.id == profesional_id, Profesional.anulado_en.is_(None)
        )
        consulta = self._acotar_a_clinica(consulta, Profesional.clinica_id, principal)

        ambito = principal.ambito
        if not ambito.todos_los_profesionales:
            if not ambito.profesionales:
                return None
            consulta = consulta.where(Profesional.id.in_(ambito.profesionales))

        if not ambito.todas_las_especialidades:
            if not ambito.especialidades:
                return None
            consulta = consulta.where(Profesional.especialidad_id.in_(ambito.especialidades))

        return (await self._sesion.execute(consulta)).scalar_one_or_none()

    # ------------------------------------------------------------------
    #  Auxiliares de ambito
    # ------------------------------------------------------------------
    def _acotar_a_clinica(
        self, consulta: Select[Any], columna: Any, principal: Principal
    ) -> Select[Any]:
        """Condicion de clinica. Nunca falta."""
        if principal.clinica_id is None:
            return consulta.where(columna == _NINGUNO)
        return consulta.where(columna == principal.clinica_id)

    def _acotar_a_sedes(
        self, consulta: Select[Any], columna: Any, principal: Principal
    ) -> Select[Any]:
        ambito = principal.ambito
        if ambito.todas_las_sedes:
            return consulta
        if not ambito.sedes:
            return consulta.where(columna == _NINGUNO)
        return consulta.where(columna.in_(ambito.sedes))

    def _sedes_efectivas(
        self, principal: Principal, sede_id: uuid.UUID | None
    ) -> set[uuid.UUID] | None:
        """Sedes por las que hay que filtrar, o `None` si no hay que filtrar.

        Cuando el cliente pide una sede concreta, se intersecta con el ambito.
        Si la sede pedida no esta en el ambito el resultado es el conjunto
        vacio -- y por tanto una lista vacia --, no un error: pedir una sede
        ajena tiene que ser indistinguible de pedir una sede sin
        profesionales.
        """
        ambito = principal.ambito

        if sede_id is not None:
            if ambito.todas_las_sedes or sede_id in ambito.sedes:
                return {sede_id}
            return set()

        if ambito.todas_las_sedes:
            return None
        return set(ambito.sedes)


__all__ = ["RepositorioCatalogo"]
