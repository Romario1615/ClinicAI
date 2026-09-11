"""Acceso a datos de pacientes.

Que se devuelve y que no
------------------------
Este repositorio sirve la **ficha administrativa**: quien es el paciente, como
contactarlo, su documento. Nada clinico. El motivo de consulta, el
diagnostico y la medicacion viven en la historia clinica, con su propio
control de acceso por tipo de informacion (docs/security.md, seccion 1), y
recepcion no los ve.

La busqueda y sus limites
-------------------------
Buscar pacientes es, por su naturaleza, una consulta que expone datos
personales. Se acota de tres formas:

* **Ambito primero.** La condicion de clinica va siempre; con `clinica_id`
  ausente se devuelve vacio.
* **Longitud minima del termino.** Dos caracteres devolverian media clinica, y
  eso convierte el buscador en un volcado. Se exigen tres.
* **Techo duro de resultados.** Sin el, un termino generico traeria miles de
  filas y con ellas una lista de personas que nadie pidio.

La busqueda por documento es exacta y no parcial. Un documento parcial
permitiria enumerar cedulas probando prefijos.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.pacientes.modelos import Paciente
from app.nucleo.autorizacion import Principal

_NINGUNO = uuid.UUID(int=0)

LONGITUD_MINIMA_BUSQUEDA = 3
LIMITE_MAXIMO = 100


class RepositorioPacientes:
    """Consultas sobre pacientes, con filtro de ambito obligatorio."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def obtener(self, paciente_id: uuid.UUID, principal: Principal) -> Paciente | None:
        """Un paciente, si esta dentro del ambito.

        Fuera del ambito devuelve `None`, que la ruta traduce a 404. Un 403
        confirmaria que ese identificador corresponde a un paciente real de la
        clinica, y con eso se enumeran.
        """
        consulta = select(Paciente).where(Paciente.id == paciente_id, Paciente.anulado_en.is_(None))
        consulta = self._acotar(consulta, principal)
        return (await self._sesion.execute(consulta)).scalar_one_or_none()

    async def buscar(
        self,
        principal: Principal,
        *,
        termino: str | None = None,
        documento: str | None = None,
        limite: int = 25,
        desplazamiento: int = 0,
    ) -> list[Paciente]:
        consulta = self._consulta_base(principal, termino=termino, documento=documento)
        if consulta is None:
            return []

        limite_real = max(1, min(limite, LIMITE_MAXIMO))
        consulta = (
            consulta.order_by(Paciente.apellido, Paciente.nombre)
            .limit(limite_real)
            .offset(max(0, desplazamiento))
        )
        return list((await self._sesion.execute(consulta)).scalars())

    async def contar(
        self,
        principal: Principal,
        *,
        termino: str | None = None,
        documento: str | None = None,
    ) -> int:
        """Cuenta lo que `buscar` devolveria con los mismos filtros.

        Acepta exactamente los mismos filtros, no un subconjunto: con filtros
        distintos, una busqueda de tres resultados mostraria como total el
        numero de pacientes de la clinica.
        """
        consulta = self._consulta_base(principal, termino=termino, documento=documento)
        if consulta is None:
            return 0
        subconsulta = consulta.subquery()
        return int(
            (await self._sesion.execute(select(func.count()).select_from(subconsulta))).scalar_one()
        )

    def _consulta_base(
        self,
        principal: Principal,
        *,
        termino: str | None,
        documento: str | None,
    ) -> Select[Any] | None:
        """Consulta con ambito y filtros, o `None` si no puede devolver nada."""
        consulta = select(Paciente).where(Paciente.anulado_en.is_(None), Paciente.activo.is_(True))
        consulta = self._acotar(consulta, principal)

        if documento:
            # Exacta, no parcial: un prefijo permitiria enumerar documentos.
            return consulta.where(Paciente.numero_documento == documento.strip())

        if termino is not None:
            limpio = termino.strip()
            if len(limpio) < LONGITUD_MINIMA_BUSQUEDA:
                # Menos de tres caracteres devolverian media clinica. Se
                # responde vacio en lugar de lanzar un error: la interfaz
                # busca mientras se teclea, y un error por cada letra seria
                # ruido.
                return None
            patron = f"%{limpio}%"
            consulta = consulta.where(
                or_(
                    Paciente.nombre.ilike(patron),
                    Paciente.apellido.ilike(patron),
                    # Se usa `ilike` con parametro enlazado, nunca
                    # concatenacion de cadenas: el termino llega del usuario.
                    func.concat(Paciente.nombre, " ", Paciente.apellido).ilike(patron),
                )
            )

        return consulta

    def _acotar(self, consulta: Select[Any], principal: Principal) -> Select[Any]:
        """Aplica clinica y, si procede, la lista explicita de pacientes.

        El ambito de paciente existe para el caso del propio paciente
        escribiendo por WhatsApp: su principal solo alcanza su ficha. El
        personal de la clinica tiene el comodin.
        """
        if principal.clinica_id is None:
            return consulta.where(Paciente.clinica_id == _NINGUNO)

        consulta = consulta.where(Paciente.clinica_id == principal.clinica_id)

        ambito = principal.ambito
        if not ambito.todos_los_pacientes:
            if not ambito.pacientes:
                return consulta.where(Paciente.id == _NINGUNO)
            consulta = consulta.where(Paciente.id.in_(ambito.pacientes))

        return consulta


__all__ = ["LIMITE_MAXIMO", "LONGITUD_MINIMA_BUSQUEDA", "RepositorioPacientes"]
