"""Lectura segura y versionado append-only del odontograma."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.odontologia.esquemas import ContenidoOdontograma
from app.modulos.odontologia.modelos import Odontograma
from app.modulos.odontologia.vocabulario import (
    PIEZAS_PERMANENTES,
    Denticion,
    HallazgoCara,
    HallazgoPieza,
)
from app.modulos.pacientes.acceso_clinico import GuardiaClinica
from app.modulos.pacientes.modelos import Paciente
from app.nucleo.autorizacion import Principal
from app.nucleo.errores import ConflictoEstado, PermisoDenegado, RecursoNoEncontrado
from app.nucleo.reloj import Reloj


class ServicioOdontograma:
    """Aplica permisos, ámbito, relación asistencial y concurrencia."""

    def __init__(self, sesion: AsyncSession, reloj: Reloj) -> None:
        self._sesion = sesion
        self._reloj = reloj
        self._guardia = GuardiaClinica(sesion)

    async def obtener(
        self,
        paciente_id: uuid.UUID,
        *,
        principal: Principal,
        version: int | None = None,
    ) -> Odontograma | None:
        await self._guardia.acceso_clinico(
            principal, paciente_id, "odontograma.leer", self._reloj.ahora()
        )
        consulta = select(Odontograma).where(
            Odontograma.paciente_id == paciente_id,
            Odontograma.clinica_id == principal.clinica_id,
        )
        if version is None:
            consulta = consulta.where(Odontograma.vigente.is_(True))
        else:
            consulta = consulta.where(Odontograma.version == version)
        return (await self._sesion.execute(consulta)).scalar_one_or_none()

    async def listar_versiones(
        self, paciente_id: uuid.UUID, *, principal: Principal
    ) -> list[Odontograma]:
        await self._guardia.acceso_clinico(
            principal, paciente_id, "odontograma.leer", self._reloj.ahora()
        )
        consulta = (
            select(Odontograma)
            .where(
                Odontograma.paciente_id == paciente_id,
                Odontograma.clinica_id == principal.clinica_id,
            )
            .order_by(Odontograma.version.desc())
        )
        return list((await self._sesion.execute(consulta)).scalars().all())

    async def crear(
        self,
        paciente_id: uuid.UUID,
        contenido: ContenidoOdontograma,
        *,
        principal: Principal,
    ) -> Odontograma:
        paciente = await self._bloquear_paciente(paciente_id, principal, "odontograma.escribir")
        actual = await self._vigente(paciente_id, principal.clinica_id)
        if actual is not None:
            raise ConflictoEstado(
                "El paciente ya tiene un odontograma. Registre una versión nueva."
            )
        profesional_id = self._profesional(principal)
        fila = Odontograma(
            clinica_id=paciente.clinica_id,
            paciente_id=paciente.id,
            profesional_id=profesional_id,
            version=1,
            vigente=True,
            denticion=contenido.denticion.value,
            piezas=contenido.model_dump(mode="json")["piezas"],
            creado_por=principal.actor_id,
        )
        self._sesion.add(fila)
        await self._sesion.flush()
        return fila

    async def versionar(
        self,
        paciente_id: uuid.UUID,
        contenido: ContenidoOdontograma,
        *,
        version_base: int,
        motivo: str,
        principal: Principal,
    ) -> Odontograma:
        paciente = await self._bloquear_paciente(paciente_id, principal, "odontograma.escribir")
        actual = await self._vigente(paciente_id, paciente.clinica_id, bloquear=True)
        if actual is None:
            raise RecursoNoEncontrado("El paciente todavía no tiene un odontograma.")
        if actual.version != version_base:
            raise ConflictoEstado(
                "El odontograma cambió desde que se abrió. Recargue la versión vigente.",
                detalles={"version_vigente": actual.version},
            )

        profesional_id = self._profesional(principal)
        actual.vigente = False
        siguiente = Odontograma(
            clinica_id=paciente.clinica_id,
            paciente_id=paciente.id,
            profesional_id=profesional_id,
            version=actual.version + 1,
            vigente=True,
            denticion=contenido.denticion.value,
            piezas=contenido.model_dump(mode="json")["piezas"],
            motivo_modificacion=motivo.strip(),
            creado_por=principal.actor_id,
        )
        self._sesion.add(siguiente)
        await self._sesion.flush()
        return siguiente

    async def aplicar_hallazgo(
        self,
        paciente_id: uuid.UUID,
        *,
        pieza: int,
        caras: str | None,
        hallazgo: HallazgoPieza | HallazgoCara,
        procedimiento_id: uuid.UUID,
        motivo: str,
        principal: Principal,
    ) -> Odontograma:
        """Version nueva con el resultado de un procedimiento completado.

        Copia la version vigente y cambia solo la pieza tratada. Si el
        paciente aun no tiene odontograma, crea la primera version con la
        denticion que corresponde a la pieza. El contenido resultante se
        valida con el mismo esquema que una edicion manual.
        """
        paciente = await self._bloquear_paciente(paciente_id, principal, "odontograma.escribir")
        actual = await self._vigente(paciente_id, paciente.clinica_id, bloquear=True)
        profesional_id = self._profesional(principal)

        if actual is None:
            denticion = (
                Denticion.PERMANENTE.value
                if pieza in PIEZAS_PERMANENTES
                else Denticion.TEMPORAL.value
            )
            piezas: dict[str, dict[str, object]] = {}
        else:
            denticion = actual.denticion
            piezas = {codigo: dict(valor) for codigo, valor in (actual.piezas or {}).items()}

        clave = str(pieza)
        estado: dict[str, object] = dict(piezas.get(clave, {}))
        previas = estado.get("caras")
        caras_estado: dict[str, str] = dict(previas) if isinstance(previas, dict) else {}
        if isinstance(hallazgo, HallazgoPieza):
            estado["pieza"] = hallazgo.value
            if hallazgo is HallazgoPieza.AUSENTE:
                caras_estado = {}
        else:
            if not caras:
                raise ConflictoEstado("Un hallazgo por cara necesita las caras del procedimiento.")
            for cara in caras:
                caras_estado[cara] = hallazgo.value
        estado["caras"] = caras_estado
        piezas[clave] = estado

        # Una pieza de la otra denticion convierte el registro en mixto.
        es_permanente = pieza in PIEZAS_PERMANENTES
        if (denticion == Denticion.PERMANENTE.value and not es_permanente) or (
            denticion == Denticion.TEMPORAL.value and es_permanente
        ):
            denticion = Denticion.MIXTA.value
        contenido = ContenidoOdontograma.model_validate({"denticion": denticion, "piezas": piezas})

        if actual is not None:
            actual.vigente = False
        fila = Odontograma(
            clinica_id=paciente.clinica_id,
            paciente_id=paciente.id,
            profesional_id=profesional_id,
            version=(actual.version + 1) if actual else 1,
            vigente=True,
            denticion=contenido.denticion.value,
            piezas=contenido.model_dump(mode="json")["piezas"],
            motivo_modificacion=motivo if actual else None,
            procedimiento_id=procedimiento_id,
            creado_por=principal.actor_id,
        )
        self._sesion.add(fila)
        await self._sesion.flush()
        return fila

    async def _bloquear_paciente(
        self, paciente_id: uuid.UUID, principal: Principal, permiso: str
    ) -> Paciente:
        paciente = await self._guardia.acceso_clinico(
            principal, paciente_id, permiso, self._reloj.ahora()
        )
        # Serializa incluso la creación de la primera versión, cuando todavía
        # no existe una fila de odontograma sobre la que tomar el bloqueo.
        consulta = (
            select(Paciente)
            .where(
                Paciente.id == paciente.id,
                Paciente.clinica_id == principal.clinica_id,
                Paciente.anulado_en.is_(None),
            )
            .with_for_update()
        )
        bloqueado = (await self._sesion.execute(consulta)).scalar_one_or_none()
        if bloqueado is None:
            raise RecursoNoEncontrado("El paciente solicitado no existe.")
        return bloqueado

    async def _vigente(
        self, paciente_id: uuid.UUID, clinica_id: uuid.UUID | None, *, bloquear: bool = False
    ) -> Odontograma | None:
        consulta = select(Odontograma).where(
            Odontograma.paciente_id == paciente_id,
            Odontograma.clinica_id == clinica_id,
            Odontograma.vigente.is_(True),
        )
        if bloquear:
            consulta = consulta.with_for_update()
        return (await self._sesion.execute(consulta)).scalar_one_or_none()

    @staticmethod
    def _profesional(principal: Principal) -> uuid.UUID:
        if principal.profesional_id is None:
            raise PermisoDenegado("Se requiere una cuenta profesional para registrar hallazgos.")
        return principal.profesional_id


__all__ = ["ServicioOdontograma"]
