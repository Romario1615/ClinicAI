"""Administración y captura versionada de formularios de anamnesis."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.modulos.historia.anamnesis_esquemas import (
    CapturaAnamnesisEntrada,
    PlantillaAnamnesisEntrada,
    PlantillaAnamnesisSalida,
    PreguntaAnamnesis,
    RespuestaAnamnesisSalida,
)
from app.modulos.historia.autorizacion import PuedeLeerHistoriaDiscreta
from app.modulos.historia.modelos import (
    EstadoPlantillaAnamnesis,
    PlantillaAnamnesis,
    RespuestaAnamnesis,
)
from app.modulos.historia.rutas import _exigir_acceso_anamnesis, _exigir_profesional
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import NivelSensibilidad, Principal
from app.nucleo.dependencias import Auditor, RelojActual, Sesion, exige_permiso
from app.nucleo.errores import (
    ConflictoEstado,
    DatosInvalidos,
    PermisoDenegado,
    RecursoNoEncontrado,
)

enrutador = APIRouter(prefix="/historia", tags=["anamnesis"])
PuedeConfigurar = Annotated[Principal, Depends(exige_permiso("configuracion.escribir"))]
PuedeEscribir = Annotated[Principal, Depends(exige_permiso("historia_clinica.escribir"))]


def _clinica(principal: Principal) -> uuid.UUID:
    if principal.clinica_id is None:
        raise RecursoNoEncontrado("La configuración solicitada no existe.")
    return principal.clinica_id


def _salida_plantilla(plantilla: PlantillaAnamnesis) -> PlantillaAnamnesisSalida:
    return PlantillaAnamnesisSalida(
        id=plantilla.id,
        nombre=plantilla.nombre,
        version=plantilla.version,
        estado=plantilla.estado,
        nivel_sensibilidad=plantilla.nivel_sensibilidad,
        preguntas=[PreguntaAnamnesis.model_validate(pregunta) for pregunta in plantilla.preguntas],
        creada_en=plantilla.creado_en,
        publicada_en=plantilla.publicada_en,
    )


async def _auditar_plantilla(
    auditor: Auditor,
    *,
    accion: AccionAuditada,
    principal: Principal,
    ahora: datetime,
    plantilla: PlantillaAnamnesis,
) -> None:
    await auditor.registrar(
        [
            construir_entrada(
                accion=accion,
                principal=principal,
                ahora=ahora,
                entidad_tipo="plantilla_anamnesis",
                entidad_id=plantilla.id,
                nivel_sensibilidad=NivelSensibilidad.ADMINISTRATIVO,
                version=plantilla.version,
                plantilla_id=str(plantilla.id),
            )
        ]
    )


def _exigir_permiso_n3(principal: Principal, nivel: str, *, denegar: bool = False) -> None:
    if nivel != "N3" or principal.tiene_permiso("historia_clinica.leer_sensible"):
        return
    if denegar:
        raise PermisoDenegado("Se requiere permiso clínico sensible para este formulario.")
    raise RecursoNoEncontrado("El recurso solicitado no existe.")


@enrutador.get("/anamnesis/plantillas", response_model=list[PlantillaAnamnesisSalida])
async def listar_plantillas(
    principal: PuedeConfigurar,
    sesion: Sesion,
) -> list[PlantillaAnamnesisSalida]:
    clinica_id = _clinica(principal)
    plantillas = await sesion.scalars(
        select(PlantillaAnamnesis)
        .where(PlantillaAnamnesis.clinica_id == clinica_id)
        .order_by(func.lower(PlantillaAnamnesis.nombre), PlantillaAnamnesis.version.desc())
    )
    return [_salida_plantilla(item) for item in plantillas]


@enrutador.post(
    "/anamnesis/plantillas",
    response_model=PlantillaAnamnesisSalida,
    status_code=status.HTTP_201_CREATED,
)
async def crear_plantilla(
    datos: PlantillaAnamnesisEntrada,
    principal: PuedeConfigurar,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
) -> PlantillaAnamnesisSalida:
    clinica_id = _clinica(principal)
    nombre = datos.nombre.strip()
    existente = await sesion.scalar(
        select(PlantillaAnamnesis.id).where(
            PlantillaAnamnesis.clinica_id == clinica_id,
            func.lower(PlantillaAnamnesis.nombre) == nombre.casefold(),
        )
    )
    if existente is not None:
        raise ConflictoEstado("Ya existe una plantilla con ese nombre; cree una nueva versión.")
    plantilla = PlantillaAnamnesis(
        clinica_id=clinica_id,
        nombre=nombre,
        version=1,
        estado=EstadoPlantillaAnamnesis.BORRADOR.value,
        nivel_sensibilidad=datos.nivel_sensibilidad,
        preguntas=[pregunta.model_dump(mode="json") for pregunta in datos.preguntas],
        creado_por=principal.actor_id,
    )
    sesion.add(plantilla)
    try:
        await sesion.flush()
    except IntegrityError as exc:
        await sesion.rollback()
        raise ConflictoEstado("Ya existe una plantilla con ese nombre.") from exc
    await _auditar_plantilla(
        auditor,
        accion=AccionAuditada.PLANTILLA_ANAMNESIS_CREADA,
        principal=principal,
        ahora=reloj.ahora(),
        plantilla=plantilla,
    )
    await sesion.commit()
    return _salida_plantilla(plantilla)


@enrutador.patch("/anamnesis/plantillas/{plantilla_id}", response_model=PlantillaAnamnesisSalida)
async def editar_plantilla(
    datos: PlantillaAnamnesisEntrada,
    plantilla_id: Annotated[uuid.UUID, Path()],
    principal: PuedeConfigurar,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
) -> PlantillaAnamnesisSalida:
    plantilla = await sesion.scalar(
        select(PlantillaAnamnesis)
        .where(
            PlantillaAnamnesis.id == plantilla_id,
            PlantillaAnamnesis.clinica_id == _clinica(principal),
        )
        .with_for_update()
    )
    if plantilla is None:
        raise RecursoNoEncontrado("La plantilla solicitada no existe.")
    if plantilla.estado != EstadoPlantillaAnamnesis.BORRADOR.value:
        raise ConflictoEstado("Las versiones publicadas no se editan; cree una nueva versión.")
    conflicto_nombre = None
    if datos.nombre.casefold() != plantilla.nombre.casefold():
        conflicto_nombre = await sesion.scalar(
            select(PlantillaAnamnesis.id).where(
                PlantillaAnamnesis.clinica_id == plantilla.clinica_id,
                func.lower(PlantillaAnamnesis.nombre) == datos.nombre.casefold(),
                PlantillaAnamnesis.id != plantilla.id,
            )
        )
    if conflicto_nombre is not None:
        raise ConflictoEstado("Ya existe otra plantilla con ese nombre.")
    plantilla.nombre = datos.nombre
    plantilla.nivel_sensibilidad = datos.nivel_sensibilidad
    plantilla.preguntas = [pregunta.model_dump(mode="json") for pregunta in datos.preguntas]
    plantilla.actualizado_por = principal.actor_id
    await _auditar_plantilla(
        auditor,
        accion=AccionAuditada.PLANTILLA_ANAMNESIS_MODIFICADA,
        principal=principal,
        ahora=reloj.ahora(),
        plantilla=plantilla,
    )
    await sesion.commit()
    return _salida_plantilla(plantilla)


@enrutador.post(
    "/anamnesis/plantillas/{plantilla_id}/nueva-version",
    response_model=PlantillaAnamnesisSalida,
    status_code=status.HTTP_201_CREATED,
)
async def crear_nueva_version(
    plantilla_id: Annotated[uuid.UUID, Path()],
    principal: PuedeConfigurar,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
) -> PlantillaAnamnesisSalida:
    origen = await sesion.scalar(
        select(PlantillaAnamnesis)
        .where(
            PlantillaAnamnesis.id == plantilla_id,
            PlantillaAnamnesis.clinica_id == _clinica(principal),
        )
        .with_for_update()
    )
    if origen is None:
        raise RecursoNoEncontrado("La plantilla solicitada no existe.")
    if origen.estado != EstadoPlantillaAnamnesis.PUBLICADA.value:
        raise ConflictoEstado("Solo puede versionarse una plantilla publicada.")
    version = (
        int(
            await sesion.scalar(
                select(func.max(PlantillaAnamnesis.version)).where(
                    PlantillaAnamnesis.clinica_id == origen.clinica_id,
                    func.lower(PlantillaAnamnesis.nombre) == origen.nombre.casefold(),
                )
            )
            or origen.version
        )
        + 1
    )
    nueva = PlantillaAnamnesis(
        clinica_id=origen.clinica_id,
        nombre=origen.nombre,
        version=version,
        estado=EstadoPlantillaAnamnesis.BORRADOR.value,
        nivel_sensibilidad=origen.nivel_sensibilidad,
        preguntas=[dict(pregunta) for pregunta in origen.preguntas],
        creado_por=principal.actor_id,
    )
    sesion.add(nueva)
    await sesion.flush()
    await _auditar_plantilla(
        auditor,
        accion=AccionAuditada.PLANTILLA_ANAMNESIS_CREADA,
        principal=principal,
        ahora=reloj.ahora(),
        plantilla=nueva,
    )
    await sesion.commit()
    return _salida_plantilla(nueva)


@enrutador.post(
    "/anamnesis/plantillas/{plantilla_id}/publicacion",
    response_model=PlantillaAnamnesisSalida,
)
async def publicar_plantilla(
    plantilla_id: Annotated[uuid.UUID, Path()],
    principal: PuedeConfigurar,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
) -> PlantillaAnamnesisSalida:
    plantilla = await sesion.scalar(
        select(PlantillaAnamnesis)
        .where(
            PlantillaAnamnesis.id == plantilla_id,
            PlantillaAnamnesis.clinica_id == _clinica(principal),
        )
        .with_for_update()
    )
    if plantilla is None:
        raise RecursoNoEncontrado("La plantilla solicitada no existe.")
    if plantilla.estado != EstadoPlantillaAnamnesis.BORRADOR.value:
        raise ConflictoEstado("Solo se pueden publicar borradores.")
    ahora = reloj.ahora()
    anteriores = await sesion.scalars(
        select(PlantillaAnamnesis)
        .where(
            PlantillaAnamnesis.clinica_id == plantilla.clinica_id,
            func.lower(PlantillaAnamnesis.nombre) == plantilla.nombre.casefold(),
            PlantillaAnamnesis.estado == EstadoPlantillaAnamnesis.PUBLICADA.value,
            PlantillaAnamnesis.id != plantilla.id,
        )
        .with_for_update()
    )
    for anterior in anteriores:
        anterior.estado = EstadoPlantillaAnamnesis.RETIRADA.value
        anterior.actualizado_por = principal.actor_id
    # La unicidad parcial permite una sola plantilla PUBLICADA por nombre.
    # Separar el retiro de la versión anterior de la promoción evita que el
    # orden de UPDATE que elija el ORM choque transitoriamente con ese índice.
    await sesion.flush()
    plantilla.estado = EstadoPlantillaAnamnesis.PUBLICADA.value
    plantilla.publicada_en = ahora
    plantilla.actualizado_por = principal.actor_id
    try:
        await sesion.flush()
    except IntegrityError as exc:
        await sesion.rollback()
        raise ConflictoEstado("Otra versión de esta plantilla se publicó al mismo tiempo.") from exc
    await _auditar_plantilla(
        auditor,
        accion=AccionAuditada.PLANTILLA_ANAMNESIS_PUBLICADA,
        principal=principal,
        ahora=ahora,
        plantilla=plantilla,
    )
    await sesion.commit()
    return _salida_plantilla(plantilla)


@enrutador.get(
    "/pacientes/{paciente_id}/anamnesis/plantillas-activas",
    response_model=list[PlantillaAnamnesisSalida],
)
async def plantillas_activas(
    paciente_id: Annotated[uuid.UUID, Path()],
    principal: PuedeLeerHistoriaDiscreta,
    sesion: Sesion,
    reloj: RelojActual,
) -> list[PlantillaAnamnesisSalida]:
    _exigir_profesional(principal)
    await _exigir_acceso_anamnesis(sesion, principal, paciente_id, reloj.ahora())
    plantillas = await sesion.scalars(
        select(PlantillaAnamnesis)
        .where(
            PlantillaAnamnesis.clinica_id == principal.clinica_id,
            PlantillaAnamnesis.estado == EstadoPlantillaAnamnesis.PUBLICADA.value,
        )
        .order_by(func.lower(PlantillaAnamnesis.nombre))
    )
    disponibles = [
        plantilla
        for plantilla in plantillas
        if plantilla.nivel_sensibilidad != "N3"
        or principal.tiene_permiso("historia_clinica.leer_sensible")
    ]
    return [_salida_plantilla(plantilla) for plantilla in disponibles]


def _validar_valor(pregunta: PreguntaAnamnesis, valor: object) -> object:
    if pregunta.tipo in {"texto", "texto_largo"}:
        if not isinstance(valor, str):
            raise DatosInvalidos(f"La respuesta de «{pregunta.etiqueta}» debe ser texto.")
        valor = valor.strip()
        maximo = 500 if pregunta.tipo == "texto" else 4000
        if len(valor) > maximo or (pregunta.obligatoria and not valor):
            raise DatosInvalidos(f"La respuesta de «{pregunta.etiqueta}» no es válida.")
    elif pregunta.tipo == "booleano":
        if not isinstance(valor, bool):
            raise DatosInvalidos(f"La respuesta de «{pregunta.etiqueta}» debe ser sí o no.")
    elif pregunta.tipo == "seleccion":
        if not isinstance(valor, str) or valor not in pregunta.opciones:
            raise DatosInvalidos(f"Seleccione una opción válida para «{pregunta.etiqueta}».")
    elif pregunta.tipo == "seleccion_multiple":
        if (
            not isinstance(valor, list)
            or not all(isinstance(item, str) for item in valor)
            or len(valor) > len(pregunta.opciones)
            or len(valor) != len(set(valor))
            or any(item not in pregunta.opciones for item in valor)
            or (pregunta.obligatoria and not valor)
        ):
            raise DatosInvalidos(f"Seleccione opciones válidas para «{pregunta.etiqueta}».")
    return valor


def _validar_respuestas(
    plantilla: PlantillaAnamnesis, respuestas: dict[str, object]
) -> dict[str, object]:
    preguntas = [PreguntaAnamnesis.model_validate(item) for item in plantilla.preguntas]
    por_id = {pregunta.id: pregunta for pregunta in preguntas}
    if respuestas.keys() - por_id.keys():
        raise DatosInvalidos("La captura contiene preguntas que no pertenecen a esta versión.")
    normalizadas: dict[str, object] = {}
    for pregunta in preguntas:
        valor = respuestas.get(pregunta.id)
        if pregunta.id not in respuestas or valor is None:
            if pregunta.obligatoria:
                raise DatosInvalidos(f"La pregunta «{pregunta.etiqueta}» es obligatoria.")
            continue
        normalizadas[pregunta.id] = _validar_valor(pregunta, valor)
    return normalizadas


@enrutador.post(
    "/pacientes/{paciente_id}/anamnesis/respuestas",
    response_model=RespuestaAnamnesisSalida,
    status_code=status.HTTP_201_CREATED,
)
async def registrar_respuestas(
    paciente_id: Annotated[uuid.UUID, Path()],
    datos: CapturaAnamnesisEntrada,
    principal: PuedeEscribir,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
) -> RespuestaAnamnesisSalida:
    profesional_id = _exigir_profesional(principal)
    ahora = reloj.ahora()
    await _exigir_acceso_anamnesis(sesion, principal, paciente_id, ahora)
    plantilla = await sesion.scalar(
        select(PlantillaAnamnesis).where(
            PlantillaAnamnesis.id == datos.plantilla_id,
            PlantillaAnamnesis.clinica_id == principal.clinica_id,
            PlantillaAnamnesis.estado == EstadoPlantillaAnamnesis.PUBLICADA.value,
        )
    )
    if plantilla is None:
        raise RecursoNoEncontrado("La plantilla activa solicitada no existe.")
    _exigir_permiso_n3(principal, plantilla.nivel_sensibilidad, denegar=True)
    respuestas = _validar_respuestas(plantilla, datos.respuestas)
    captura = RespuestaAnamnesis(
        clinica_id=plantilla.clinica_id,
        paciente_id=paciente_id,
        plantilla_id=plantilla.id,
        version_plantilla=plantilla.version,
        profesional_id=profesional_id,
        respuestas=respuestas,
        registrada_en=ahora,
        creado_por=principal.actor_id,
    )
    sesion.add(captura)
    await sesion.flush()
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.ANAMNESIS_REGISTRADA,
                principal=principal,
                ahora=ahora,
                entidad_tipo="respuesta_anamnesis",
                entidad_id=captura.id,
                paciente_id=paciente_id,
                nivel_sensibilidad=NivelSensibilidad.CLINICO_SENSIBLE
                if plantilla.nivel_sensibilidad == "N3"
                else NivelSensibilidad.CLINICO,
                plantilla_id=str(plantilla.id),
                version=plantilla.version,
                cantidad_campos=len(respuestas),
            )
        ]
    )
    await sesion.commit()
    return RespuestaAnamnesisSalida(
        id=captura.id,
        plantilla_id=plantilla.id,
        plantilla=plantilla.nombre,
        version_plantilla=plantilla.version,
        nivel_sensibilidad=plantilla.nivel_sensibilidad,
        preguntas=[PreguntaAnamnesis.model_validate(item) for item in plantilla.preguntas],
        respuestas=captura.respuestas,
        registrada_en=captura.registrada_en,
    )


@enrutador.get(
    "/pacientes/{paciente_id}/anamnesis/respuestas",
    response_model=list[RespuestaAnamnesisSalida],
)
async def listar_respuestas(
    paciente_id: Annotated[uuid.UUID, Path()],
    principal: PuedeLeerHistoriaDiscreta,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
) -> list[RespuestaAnamnesisSalida]:
    _exigir_profesional(principal)
    await _exigir_acceso_anamnesis(sesion, principal, paciente_id, reloj.ahora())
    consulta = (
        select(RespuestaAnamnesis, PlantillaAnamnesis)
        .join(PlantillaAnamnesis, PlantillaAnamnesis.id == RespuestaAnamnesis.plantilla_id)
        .where(
            RespuestaAnamnesis.clinica_id == principal.clinica_id,
            RespuestaAnamnesis.paciente_id == paciente_id,
        )
        .order_by(RespuestaAnamnesis.registrada_en.desc())
    )
    filas = (await sesion.execute(consulta)).all()
    visibles: list[RespuestaAnamnesisSalida] = []
    for captura, plantilla in filas:
        if plantilla.nivel_sensibilidad == "N3" and not principal.tiene_permiso(
            "historia_clinica.leer_sensible"
        ):
            continue
        visibles.append(
            RespuestaAnamnesisSalida(
                id=captura.id,
                plantilla_id=plantilla.id,
                plantilla=plantilla.nombre,
                version_plantilla=captura.version_plantilla,
                nivel_sensibilidad=plantilla.nivel_sensibilidad,
                preguntas=[PreguntaAnamnesis.model_validate(item) for item in plantilla.preguntas],
                respuestas=captura.respuestas,
                registrada_en=captura.registrada_en,
            )
        )
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.HISTORIA_CONSULTADA,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="respuestas_anamnesis",
                paciente_id=paciente_id,
                nivel_sensibilidad=(
                    NivelSensibilidad.CLINICO_SENSIBLE
                    if any(item.nivel_sensibilidad == "N3" for item in visibles)
                    else NivelSensibilidad.CLINICO
                ),
                cantidad=len(visibles),
            )
        ]
    )
    await sesion.commit()
    return visibles


__all__ = ["enrutador"]
