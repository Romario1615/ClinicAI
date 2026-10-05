"""Rutas del catalogo de la organizacion.

El catálogo ofrece opciones de agenda sin pedir identificadores UUID a mano.
La ficha de clínica también admite lectura y edición dentro del ámbito de la
sesión; sedes, profesionales y servicios siguen siendo de solo lectura.

Por que exigen permiso si son "solo el catalogo"
------------------------------------------------
Porque no son publicos. La lista de profesionales de una clinica, sus
especialidades y sus sedes describen su plantilla y su estructura interna:
quien trabaja alli, en que se especializa y donde. Eso interesa a la
competencia y sirve para preparar un ataque de ingenieria social contra el
personal.

Se exige `agenda.leer`, que es el permiso mas comun del personal asistencial
y administrativo, y el ambito filtra el resultado: un recepcionista de una
sede ve su sede, no las demas.
"""

from __future__ import annotations

import uuid
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.exc import IntegrityError

from app.modulos.organizacion.esquemas import (
    ActualizarClinica,
    RespuestaClinica,
    RespuestaClinicaCatalogo,
    RespuestaConsultorio,
    RespuestaEspecialidad,
    RespuestaProfesional,
    RespuestaSede,
    RespuestaServicio,
)
from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.profesionales.modelos import Profesional
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import Auditor, RelojActual, RepoCatalogo, Sesion, exige_permiso
from app.nucleo.errores import ConflictoEstado, DatosInvalidos, RecursoNoEncontrado

enrutador = APIRouter(prefix="/catalogo", tags=["catalogo"])

PuedeLeerCatalogo = Annotated[Principal, Depends(exige_permiso("agenda.leer"))]
PuedeLeerClinica = Annotated[
    Principal,
    Depends(exige_permiso("clinica.leer", "agenda.leer", "configuracion.escribir")),
]
PuedeLeerConfiguracionClinica = Annotated[
    Principal, Depends(exige_permiso("clinica.leer", "clinica.escribir"))
]
PuedeEditarClinica = Annotated[Principal, Depends(exige_permiso("clinica.escribir"))]
MAX_NOMBRE_CLINICA = 200
MIN_LONGITUD_IDIOMA = 2
MAX_LONGITUD_IDIOMA = 8
LONGITUD_CODIGO_MONEDA = 3
MAX_LONGITUD_CORREO = 200
MAX_LONGITUD_IDENTIFICACION_FISCAL = 50
MAX_LONGITUD_TELEFONO = 32


def _zona_efectiva(sede: Sede, clinica: Clinica | None) -> str:
    """Zona de la sede, o la de la clinica si la sede no la fija.

    Se resuelve aqui y no en el cliente. Si el cliente tuviera que combinar
    dos respuestas para saber en que huso mostrar una hora, bastaria un
    descuido para mostrar la agenda desplazada, y una hora mal en una agenda
    medica significa un paciente que llega cuando no le esperan.
    """
    return sede.zona_horaria or (clinica.zona_horaria if clinica else "America/Guayaquil")


@enrutador.get(
    "/clinica",
    response_model=RespuestaClinicaCatalogo,
    summary="Datos de la clinica del solicitante",
    responses={404: {"description": "El principal no tiene clinica asociada"}},
)
async def obtener_clinica(
    principal: PuedeLeerClinica,
    repo: RepoCatalogo,
) -> RespuestaClinicaCatalogo:
    """Devuelve **la** clinica del principal, no una cualquiera por su id.

    No se acepta un identificador en la ruta a proposito: no existe ningun
    caso legitimo en el que alguien pida los datos de otra clinica, y un
    endpoint con parametro invitaria a probar identificadores.
    """
    clinica = await repo.obtener_clinica(principal)
    if clinica is None:
        raise RecursoNoEncontrado("No hay una clinica asociada a esta sesion.")
    return RespuestaClinicaCatalogo(
        id=clinica.id,
        nombre=clinica.nombre,
        zona_horaria=clinica.zona_horaria,
        idioma=clinica.idioma,
        moneda=clinica.moneda,
        telefono=clinica.telefono,
        correo=clinica.correo,
    )


@enrutador.get(
    "/clinica/configuracion",
    response_model=RespuestaClinica,
    summary="Datos completos de la clinica para su configuracion",
)
async def obtener_configuracion_clinica(
    principal: PuedeLeerConfiguracionClinica,
    repo: RepoCatalogo,
) -> RespuestaClinica:
    """Lee los datos fiscales solo desde la pantalla de administracion."""
    clinica = await repo.obtener_clinica(principal)
    if clinica is None:
        raise RecursoNoEncontrado("No hay una clinica asociada a esta sesion.")
    return RespuestaClinica(
        id=clinica.id,
        nombre=clinica.nombre,
        zona_horaria=clinica.zona_horaria,
        idioma=clinica.idioma,
        moneda=clinica.moneda,
        identificacion_fiscal=clinica.identificacion_fiscal,
        telefono=clinica.telefono,
        correo=clinica.correo,
    )


@enrutador.put("/clinica", response_model=RespuestaClinica)
async def actualizar_clinica(
    datos: ActualizarClinica,
    principal: PuedeEditarClinica,
    repo: RepoCatalogo,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> RespuestaClinica:
    """Actualiza solo la clínica asociada a la sesión, sin aceptar un ID."""
    clinica = await repo.obtener_clinica(principal)
    if clinica is None:
        raise RecursoNoEncontrado("No hay una clinica asociada a esta sesion.")
    nombre = datos.nombre.strip()
    zona = datos.zona_horaria.strip()
    idioma = datos.idioma.strip().lower()
    moneda = datos.moneda.strip().upper()
    correo = datos.correo.strip() if datos.correo else None
    identificacion_fiscal = (
        datos.identificacion_fiscal.strip() if datos.identificacion_fiscal else None
    )
    telefono = datos.telefono.strip() if datos.telefono else None
    if not nombre or len(nombre) > MAX_NOMBRE_CLINICA:
        raise DatosInvalidos("El nombre debe tener entre 1 y 200 caracteres.")
    if not MIN_LONGITUD_IDIOMA <= len(idioma) <= MAX_LONGITUD_IDIOMA or not idioma.isalpha():
        raise DatosInvalidos("El idioma debe ser un código de 2 a 8 letras.")
    if len(moneda) != LONGITUD_CODIGO_MONEDA or not moneda.isalpha():
        raise DatosInvalidos("La moneda debe ser un código de tres letras.")
    if correo and (len(correo) > MAX_LONGITUD_CORREO or "@" not in correo):
        raise DatosInvalidos("Ingrese un correo válido.")
    if identificacion_fiscal and len(identificacion_fiscal) > MAX_LONGITUD_IDENTIFICACION_FISCAL:
        raise DatosInvalidos("La identificación fiscal no puede superar 50 caracteres.")
    if telefono and len(telefono) > MAX_LONGITUD_TELEFONO:
        raise DatosInvalidos("El teléfono no puede superar 32 caracteres.")
    try:
        ZoneInfo(zona)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise DatosInvalidos("Seleccione una zona horaria IANA válida.") from exc
    clinica.nombre = nombre
    clinica.identificacion_fiscal = identificacion_fiscal or None
    clinica.zona_horaria = zona
    clinica.idioma = idioma
    clinica.moneda = moneda
    clinica.telefono = telefono or None
    clinica.correo = correo
    try:
        await sesion.flush()
    except IntegrityError as exc:
        await sesion.rollback()
        raise ConflictoEstado("La identificación fiscal ya está registrada.") from exc
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.CLINICA_MODIFICADA,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="clinica",
                entidad_id=clinica.id,
            )
        ]
    )
    await sesion.commit()
    return RespuestaClinica(
        id=clinica.id,
        nombre=clinica.nombre,
        zona_horaria=clinica.zona_horaria,
        idioma=clinica.idioma,
        moneda=clinica.moneda,
        identificacion_fiscal=clinica.identificacion_fiscal,
        telefono=clinica.telefono,
        correo=clinica.correo,
    )


@enrutador.get(
    "/sedes",
    response_model=list[RespuestaSede],
    summary="Sedes dentro del ambito del solicitante",
)
async def listar_sedes(
    principal: PuedeLeerCatalogo,
    repo: RepoCatalogo,
) -> list[RespuestaSede]:
    clinica = await repo.obtener_clinica(principal)
    sedes = await repo.listar_sedes(principal)
    return [
        RespuestaSede(
            id=sede.id,
            nombre=sede.nombre,
            direccion=sede.direccion,
            telefono=sede.telefono,
            zona_horaria=_zona_efectiva(sede, clinica),
            minutos_antelacion_minima=sede.minutos_antelacion_minima,
        )
        for sede in sedes
    ]


@enrutador.get(
    "/consultorios",
    response_model=list[RespuestaConsultorio],
    summary="Consultorios de las sedes alcanzables",
)
async def listar_consultorios(
    principal: PuedeLeerCatalogo,
    repo: RepoCatalogo,
    sede_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[RespuestaConsultorio]:
    consultorios = await repo.listar_consultorios(principal, sede_id=sede_id)
    return [
        RespuestaConsultorio(
            id=consultorio.id,
            sede_id=consultorio.sede_id,
            nombre=consultorio.nombre,
            tipo=consultorio.tipo,
            capacidad=consultorio.capacidad,
        )
        for consultorio in consultorios
    ]


@enrutador.get(
    "/especialidades",
    response_model=list[RespuestaEspecialidad],
    summary="Especialidades dentro del ambito",
)
async def listar_especialidades(
    principal: PuedeLeerCatalogo,
    repo: RepoCatalogo,
) -> list[RespuestaEspecialidad]:
    especialidades = await repo.listar_especialidades(principal)
    return [
        RespuestaEspecialidad(
            id=especialidad.id,
            nombre=especialidad.nombre,
            codigo=especialidad.codigo,
            descripcion=especialidad.descripcion,
        )
        for especialidad in especialidades
    ]


@enrutador.get(
    "/servicios",
    response_model=list[RespuestaServicio],
    summary="Servicios ofrecidos",
)
async def listar_servicios(
    principal: PuedeLeerCatalogo,
    repo: RepoCatalogo,
    especialidad_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[RespuestaServicio]:
    servicios = await repo.listar_servicios(principal, especialidad_id=especialidad_id)
    return [
        RespuestaServicio(
            id=servicio.id,
            especialidad_id=servicio.especialidad_id,
            nombre=servicio.nombre,
            descripcion=servicio.descripcion,
            duracion_minutos=servicio.duracion_minutos,
            minutos_preparacion=servicio.minutos_preparacion,
            precio=servicio.precio,
            moneda=servicio.moneda,
        )
        for servicio in servicios
    ]


@enrutador.get(
    "/profesionales",
    response_model=list[RespuestaProfesional],
    summary="Profesionales dentro del ambito",
)
async def listar_profesionales(
    principal: PuedeLeerCatalogo,
    repo: RepoCatalogo,
    especialidad_id: Annotated[uuid.UUID | None, Query()] = None,
    sede_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[RespuestaProfesional]:
    """Lista profesionales, sin duplicados.

    Un profesional puede atender en varias sedes. El filtro por sede usa
    `EXISTS` en el repositorio y no una union, precisamente para que el
    desplegable no muestre a la misma persona repetida una vez por sede.
    """
    profesionales = await repo.listar_profesionales(
        principal, especialidad_id=especialidad_id, sede_id=sede_id
    )
    return [_a_respuesta_profesional(profesional) for profesional in profesionales]


@enrutador.get(
    "/profesionales/{profesional_id}",
    response_model=RespuestaProfesional,
    summary="Ficha de un profesional",
    responses={404: {"description": "No existe, o esta fuera del ambito"}},
)
async def obtener_profesional(
    principal: PuedeLeerCatalogo,
    repo: RepoCatalogo,
    profesional_id: Annotated[uuid.UUID, Path()],
) -> RespuestaProfesional:
    profesional = await repo.obtener_profesional(profesional_id, principal)
    if profesional is None:
        raise RecursoNoEncontrado("El profesional solicitado no existe.")
    return _a_respuesta_profesional(profesional)


def _a_respuesta_profesional(profesional: Profesional) -> RespuestaProfesional:
    # Se construye campo por campo en lugar de `from_attributes`: el modelo
    # lleva `telefono_whatsapp` y `correo_calendario`, y serializarlo entero
    # confiando en recordar excluirlos es la forma habitual de filtrar datos
    # al anadir un campo meses despues.
    return RespuestaProfesional(
        id=profesional.id,
        especialidad_id=profesional.especialidad_id,
        nombre=profesional.nombre,
        apellido=profesional.apellido,
        numero_registro_profesional=profesional.numero_registro_profesional,
        estado_disponibilidad=profesional.estado_disponibilidad,
        minutos_preparacion_propio=profesional.minutos_preparacion_propio,
    )


__all__ = ["enrutador"]
