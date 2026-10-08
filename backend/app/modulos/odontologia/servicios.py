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
from app.modulos.profesionales.ambito_clinico import autores_en_ambito
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
            Odontograma.profesional_id.in_(autores_en_ambito(principal, "odontograma")),
        )
        if not principal.tiene_permiso("historia_clinica.leer_sensible"):
            consulta = consulta.where(Odontograma.nivel_sensibilidad != "N3")
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
                Odontograma.profesional_id.in_(autores_en_ambito(principal, "odontograma")),
            )
            .order_by(Odontograma.version.desc())
        )
        if not principal.tiene_permiso("historia_clinica.leer_sensible"):
            consulta = consulta.where(Odontograma.nivel_sensibilidad != "N3")
        return list((await self._sesion.execute(consulta)).scalars().all())

    async def crear(
        self,
        paciente_id: uuid.UUID,
        contenido: ContenidoOdontograma,
        *,
        principal: Principal,
        nivel_sensibilidad: str = "N2",
    ) -> Odontograma:
        paciente = await self._bloquear_paciente(paciente_id, principal, "odontograma.escribir")
        actual = await self._vigente(paciente_id, principal.clinica_id)
        if actual is not None:
            raise ConflictoEstado(
                "El paciente ya tiene un odontograma. Registre una versión nueva."
            )
        profesional_id = self._profesional(principal)
        nivel = self._validar_sensibilidad(nivel_sensibilidad, principal)
        fila = Odontograma(
            clinica_id=paciente.clinica_id,
            paciente_id=paciente.id,
            profesional_id=profesional_id,
            version=1,
            vigente=True,
            denticion=contenido.denticion.value,
            piezas=contenido.model_dump(mode="json")["piezas"],
            nivel_sensibilidad=nivel,
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
        nivel_sensibilidad: str = "N2",
    ) -> Odontograma:
        paciente = await self._bloquear_paciente(paciente_id, principal, "odontograma.escribir")
        actual = await self._vigente(
            paciente_id, paciente.clinica_id, bloquear=True, principal=principal
        )
        if actual is None:
            raise RecursoNoEncontrado("El paciente todavía no tiene un odontograma.")
        if actual.version != version_base:
            raise ConflictoEstado(
                "El odontograma cambió desde que se abrió. Recargue la versión vigente.",
                detalles={"version_vigente": actual.version},
            )
        if actual.nivel_sensibilidad == "N3" and not principal.tiene_permiso(
            "historia_clinica.leer_sensible"
        ):
            raise PermisoDenegado("Se requiere permiso de lectura clínica sensible para editar N3.")

        profesional_id = self._profesional(principal)
        nivel = self._validar_sensibilidad(nivel_sensibilidad, principal)
        if actual.nivel_sensibilidad == "N3":
            nivel = "N3"
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
            nivel_sensibilidad=nivel,
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
        actual = await self._vigente(
            paciente_id, paciente.clinica_id, bloquear=True, principal=principal
        )
        if (
            actual is not None
            and actual.nivel_sensibilidad == "N3"
            and not principal.tiene_permiso("historia_clinica.leer_sensible")
        ):
            raise PermisoDenegado("Se requiere permiso de lectura clínica sensible para editar N3.")
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
            nivel_sensibilidad=actual.nivel_sensibilidad if actual else "N2",
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
        self,
        paciente_id: uuid.UUID,
        clinica_id: uuid.UUID | None,
        *,
        bloquear: bool = False,
        principal: Principal | None = None,
    ) -> Odontograma | None:
        consulta = select(Odontograma).where(
            Odontograma.paciente_id == paciente_id,
            Odontograma.clinica_id == clinica_id,
            Odontograma.vigente.is_(True),
        )
        if bloquear:
            consulta = consulta.with_for_update()
        if principal is not None:
            permitida = consulta.where(
                Odontograma.profesional_id.in_(autores_en_ambito(principal, "odontograma"))
            )
            actual = (await self._sesion.execute(permitida)).scalar_one_or_none()
            if actual is not None:
                return actual
            # Un odontograma ajeno no es ausencia: no se puede crear encima
            # de él ni provocar un conflicto del índice único del paciente.
            if await self._sesion.scalar(consulta.with_only_columns(Odontograma.id)) is not None:
                raise RecursoNoEncontrado("El odontograma solicitado no existe.")
            return None
        return (await self._sesion.execute(consulta)).scalar_one_or_none()

    @staticmethod
    def _profesional(principal: Principal) -> uuid.UUID:
        if principal.profesional_id is None:
            raise PermisoDenegado("Se requiere una cuenta profesional para registrar hallazgos.")
        return principal.profesional_id

    @staticmethod
    def _validar_sensibilidad(nivel: str, principal: Principal) -> str:
        if nivel not in {"N2", "N3"}:
            raise PermisoDenegado("El nivel de sensibilidad clínica no es válido.")
        if nivel == "N3" and not principal.tiene_permiso("historia_clinica.leer_sensible"):
            raise PermisoDenegado("Se requiere permiso de lectura clínica sensible para usar N3.")
        return nivel


__all__ = ["ServicioOdontograma"]
