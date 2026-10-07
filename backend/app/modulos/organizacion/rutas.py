"""Rutas del catalogo de la organizacion.

El catálogo ofrece opciones de agenda sin pedir identificadores UUID a mano.
La ficha de clínica admite edición y los consultorios se gestionan dentro del
ámbito de cada sede; los demás recursos de este catálogo son de solo lectura.

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
from decimal import Decimal
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.modulos.organizacion.esquemas import (
    ActualizarClinica,
    ActualizarSede,
    CrearConsultorio,
    CrearEspecialidad,
    CrearServicio,
    DatosConsultorio,
    DatosEspecialidad,
    DatosServicio,
    EstadoConsultorio,
    EstadoRecurso,
    RespuestaClinica,
    RespuestaClinicaCatalogo,
    RespuestaConsultorio,
    RespuestaEspecialidad,
    RespuestaProfesional,
    RespuestaSede,
    RespuestaServicio,
    RespuestaServicioGestion,
)
from app.modulos.organizacion.modelos import Clinica, Consultorio, Especialidad, Sede, Servicio
from app.modulos.profesionales.modelos import Profesional
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import Auditor, RelojActual, RepoCatalogo, Sesion, exige_permiso
from app.nucleo.errores import ConflictoEstado, DatosInvalidos, RecursoNoEncontrado

enrutador = APIRouter(prefix="/catalogo", tags=["catalogo"])

PuedeLeerCatalogo = Annotated[
    Principal, Depends(exige_permiso("agenda.leer", "profesional.gestionar"))
]
PuedeLeerClinica = Annotated[
    Principal,
    Depends(
        exige_permiso(
            "clinica.leer",
            "agenda.leer",
            "configuracion.escribir",
            "plan_tratamiento.leer",
        )
    ),
]
PuedeLeerConfiguracionClinica = Annotated[
    Principal, Depends(exige_permiso("clinica.leer", "clinica.escribir"))
]
PuedeEditarClinica = Annotated[Principal, Depends(exige_permiso("clinica.escribir"))]
PuedeGestionarSedes = Annotated[Principal, Depends(exige_permiso("sede.gestionar"))]
PuedeGestionarEspecialidades = Annotated[
    Principal, Depends(exige_permiso("especialidad.gestionar"))
]
PuedeGestionarServicios = Annotated[Principal, Depends(exige_permiso("servicio.gestionar"))]
MAX_NOMBRE_CLINICA = 200
MIN_LONGITUD_IDIOMA = 2
MAX_LONGITUD_IDIOMA = 8
LONGITUD_CODIGO_MONEDA = 3
MAX_LONGITUD_CORREO = 200
MAX_LONGITUD_IDENTIFICACION_FISCAL = 50
MAX_LONGITUD_TELEFONO = 32
MAX_NOMBRE_CONSULTORIO = 100
MAX_CAPACIDAD_CONSULTORIO = 100
MAX_NOMBRE_ESPECIALIDAD = 150
MAX_CODIGO_ESPECIALIDAD = 32
MAX_NOMBRE_SERVICIO = 200
MAX_DURACION_SERVICIO = 1440
MAX_PREPARACION_SERVICIO = 1440
MAX_PRECIO_SERVICIO = Decimal("9999999999.99")
DECIMALES_PRECIO = 2


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
    "/sedes/gestion",
    response_model=list[RespuestaSede],
    summary="Sedes que el solicitante puede administrar",
)
async def listar_sedes_gestion(
    principal: PuedeGestionarSedes,
    sesion: Sesion,
) -> list[RespuestaSede]:
    if principal.clinica_id is None:
        return []
    consulta = select(Sede).where(
        Sede.clinica_id == principal.clinica_id,
        Sede.anulado_en.is_(None),
        Sede.activa.is_(True),
    )
    if not principal.ambito.todas_las_sedes:
        if not principal.ambito.sedes:
            return []
        consulta = consulta.where(Sede.id.in_(principal.ambito.sedes))
    sedes = list((await sesion.execute(consulta.order_by(Sede.nombre))).scalars())
    clinica = await sesion.get(Clinica, principal.clinica_id)
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


@enrutador.put("/sedes/{sede_id}", response_model=RespuestaSede)
async def actualizar_sede(
    sede_id: uuid.UUID,
    datos: ActualizarSede,
    principal: PuedeGestionarSedes,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> RespuestaSede:
    sede = await sesion.get(Sede, sede_id)
    if (
        sede is None
        or sede.anulado_en is not None
        or not sede.activa
        or not _sede_en_ambito(sede, principal)
    ):
        raise RecursoNoEncontrado("No se encontró la sede dentro de su ámbito.")
    try:
        ZoneInfo(datos.zona_horaria)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise DatosInvalidos("Seleccione una zona horaria IANA válida.") from exc

    sede.nombre = datos.nombre
    sede.direccion = datos.direccion or None
    sede.telefono = datos.telefono or None
    sede.zona_horaria = datos.zona_horaria
    sede.minutos_antelacion_minima = datos.minutos_antelacion_minima
    try:
        await sesion.flush()
    except IntegrityError as exc:
        await sesion.rollback()
        raise ConflictoEstado("Ya existe una sede con ese nombre en la clínica.") from exc
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.SEDE_MODIFICADA,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="sede",
                entidad_id=sede.id,
                sede_id=sede.id,
            )
        ]
    )
    clinica = await sesion.get(Clinica, sede.clinica_id)
    respuesta = RespuestaSede(
        id=sede.id,
        nombre=sede.nombre,
        direccion=sede.direccion,
        telefono=sede.telefono,
        zona_horaria=_zona_efectiva(sede, clinica),
        minutos_antelacion_minima=sede.minutos_antelacion_minima,
    )
    await sesion.commit()
    return respuesta


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
            activo=consultorio.activo,
        )
        for consultorio in consultorios
    ]


def _sede_en_ambito(sede: Sede, principal: Principal) -> bool:
    return principal.clinica_id == sede.clinica_id and (
        principal.ambito.todas_las_sedes or sede.id in principal.ambito.sedes
    )


def _validar_datos_consultorio(datos: DatosConsultorio) -> str:
    nombre = datos.nombre.strip()
    if not nombre or len(nombre) > MAX_NOMBRE_CONSULTORIO:
        raise DatosInvalidos("El nombre debe tener entre 1 y 100 caracteres.")
    if not 1 <= datos.capacidad <= MAX_CAPACIDAD_CONSULTORIO:
        raise DatosInvalidos("La capacidad debe estar entre 1 y 100.")
    return nombre


def _respuesta_consultorio(consultorio: Consultorio) -> RespuestaConsultorio:
    return RespuestaConsultorio(
        id=consultorio.id,
        sede_id=consultorio.sede_id,
        nombre=consultorio.nombre,
        tipo=consultorio.tipo,
        capacidad=consultorio.capacidad,
        activo=consultorio.activo,
    )


@enrutador.get(
    "/consultorios/gestion",
    response_model=list[RespuestaConsultorio],
    summary="Inventario de consultorios, incluidos los inactivos",
)
async def listar_consultorios_gestion(
    principal: PuedeGestionarSedes,
    sesion: Sesion,
    sede_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[RespuestaConsultorio]:
    consulta = (
        select(Consultorio)
        .join(Sede, Sede.id == Consultorio.sede_id)
        .where(Consultorio.anulado_en.is_(None), Sede.anulado_en.is_(None))
    )
    if principal.clinica_id is None:
        return []
    consulta = consulta.where(Sede.clinica_id == principal.clinica_id)
    if not principal.ambito.todas_las_sedes:
        if not principal.ambito.sedes:
            return []
        consulta = consulta.where(Sede.id.in_(principal.ambito.sedes))
    if sede_id is not None:
        consulta = consulta.where(Sede.id == sede_id)
    consultorios = list(
        (await sesion.execute(consulta.order_by(Sede.nombre, Consultorio.nombre))).scalars()
    )
    return [_respuesta_consultorio(consultorio) for consultorio in consultorios]


@enrutador.post("/consultorios", response_model=RespuestaConsultorio, status_code=201)
async def crear_consultorio(
    datos: CrearConsultorio,
    principal: PuedeGestionarSedes,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> RespuestaConsultorio:
    sede = await sesion.get(Sede, datos.sede_id)
    if (
        sede is None
        or sede.anulado_en is not None
        or not sede.activa
        or not _sede_en_ambito(sede, principal)
    ):
        raise RecursoNoEncontrado("No se encontró la sede dentro de su ámbito.")
    nombre = _validar_datos_consultorio(datos)
    consultorio = Consultorio(
        sede_id=sede.id,
        nombre=nombre,
        tipo=datos.tipo,
        capacidad=datos.capacidad,
    )
    sesion.add(consultorio)
    try:
        await sesion.flush()
    except IntegrityError as exc:
        await sesion.rollback()
        raise ConflictoEstado("Ya existe un consultorio con ese nombre en la sede.") from exc
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.CONSULTORIO_CREADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="consultorio",
                entidad_id=consultorio.id,
                sede_id=sede.id,
            )
        ]
    )
    await sesion.commit()
    return _respuesta_consultorio(consultorio)


@enrutador.put("/consultorios/{consultorio_id}", response_model=RespuestaConsultorio)
async def actualizar_consultorio(
    consultorio_id: uuid.UUID,
    datos: DatosConsultorio,
    principal: PuedeGestionarSedes,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> RespuestaConsultorio:
    consultorio = await sesion.get(Consultorio, consultorio_id)
    if consultorio is None or consultorio.anulado_en is not None:
        raise RecursoNoEncontrado("No se encontró el consultorio dentro de su ámbito.")
    sede = await sesion.get(Sede, consultorio.sede_id)
    if sede is None or not _sede_en_ambito(sede, principal):
        raise RecursoNoEncontrado("No se encontró el consultorio dentro de su ámbito.")
    consultorio.nombre = _validar_datos_consultorio(datos)
    consultorio.tipo = datos.tipo
    consultorio.capacidad = datos.capacidad
    try:
        await sesion.flush()
    except IntegrityError as exc:
        await sesion.rollback()
        raise ConflictoEstado("Ya existe un consultorio con ese nombre en la sede.") from exc
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.CONSULTORIO_MODIFICADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="consultorio",
                entidad_id=consultorio.id,
                sede_id=sede.id,
            )
        ]
    )
    await sesion.commit()
    return _respuesta_consultorio(consultorio)


@enrutador.patch("/consultorios/{consultorio_id}/estado", response_model=RespuestaConsultorio)
async def cambiar_estado_consultorio(
    consultorio_id: uuid.UUID,
    datos: EstadoConsultorio,
    principal: PuedeGestionarSedes,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> RespuestaConsultorio:
    consultorio = await sesion.get(Consultorio, consultorio_id)
    if consultorio is None or consultorio.anulado_en is not None:
        raise RecursoNoEncontrado("No se encontró el consultorio dentro de su ámbito.")
    sede = await sesion.get(Sede, consultorio.sede_id)
    if sede is None or not _sede_en_ambito(sede, principal):
        raise RecursoNoEncontrado("No se encontró el consultorio dentro de su ámbito.")
    consultorio.activo = datos.activo
    await sesion.flush()
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.CONSULTORIO_MODIFICADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="consultorio",
                entidad_id=consultorio.id,
                sede_id=sede.id,
                activo=datos.activo,
            )
        ]
    )
    await sesion.commit()
    return _respuesta_consultorio(consultorio)


def _respuesta_especialidad(especialidad: Especialidad) -> RespuestaEspecialidad:
    return RespuestaEspecialidad(
        id=especialidad.id,
        nombre=especialidad.nombre,
        codigo=especialidad.codigo,
        descripcion=especialidad.descripcion,
        activa=especialidad.activa,
    )


def _respuesta_servicio_gestion(servicio: Servicio) -> RespuestaServicioGestion:
    return RespuestaServicioGestion(
        id=servicio.id,
        especialidad_id=servicio.especialidad_id,
        nombre=servicio.nombre,
        descripcion=servicio.descripcion,
        duracion_minutos=servicio.duracion_minutos,
        minutos_preparacion=servicio.minutos_preparacion,
        precio=servicio.precio,
        moneda=servicio.moneda,
        activo=servicio.activo,
        requiere_pago_previo=servicio.requiere_pago_previo,
        instrucciones_preparacion=servicio.instrucciones_preparacion,
        tipo_consultorio_requerido=servicio.tipo_consultorio_requerido,
    )


def _validar_especialidad(datos: DatosEspecialidad) -> tuple[str, str | None, str | None]:
    nombre = datos.nombre.strip()
    codigo = datos.codigo.strip().upper() if datos.codigo else None
    descripcion = datos.descripcion.strip() if datos.descripcion else None
    if not nombre or len(nombre) > MAX_NOMBRE_ESPECIALIDAD:
        raise DatosInvalidos("El nombre debe tener entre 1 y 150 caracteres.")
    if codigo and (len(codigo) > MAX_CODIGO_ESPECIALIDAD or not codigo.replace("-", "").isalnum()):
        raise DatosInvalidos(
            "El código debe usar letras, números o guiones y no superar 32 caracteres."
        )
    return nombre, codigo or None, descripcion or None


def _validar_servicio(datos: DatosServicio) -> tuple[str, str | None, str | None, str]:
    nombre = datos.nombre.strip()
    descripcion = datos.descripcion.strip() if datos.descripcion else None
    instrucciones = (
        datos.instrucciones_preparacion.strip() if datos.instrucciones_preparacion else None
    )
    moneda = datos.moneda.strip().upper()
    if not nombre or len(nombre) > MAX_NOMBRE_SERVICIO:
        raise DatosInvalidos("El nombre debe tener entre 1 y 200 caracteres.")
    if not 1 <= datos.duracion_minutos <= MAX_DURACION_SERVICIO:
        raise DatosInvalidos("La duración debe estar entre 1 y 1440 minutos.")
    if not 0 <= datos.minutos_preparacion <= MAX_PREPARACION_SERVICIO:
        raise DatosInvalidos("La preparación debe estar entre 0 y 1440 minutos.")
    if datos.precio is not None:
        if not datos.precio.is_finite():
            raise DatosInvalidos("El precio debe ser un número finito.")
        exponente = datos.precio.as_tuple().exponent
        if not isinstance(exponente, int) or exponente < -DECIMALES_PRECIO:
            raise DatosInvalidos("El precio admite como máximo dos decimales.")
        if not Decimal("0") <= datos.precio <= MAX_PRECIO_SERVICIO:
            raise DatosInvalidos(
                "El precio no puede ser negativo ni superar 10 enteros y 2 decimales."
            )
    if len(moneda) != LONGITUD_CODIGO_MONEDA or not moneda.isalpha():
        raise DatosInvalidos("La moneda debe ser un código de tres letras.")
    return nombre, descripcion or None, instrucciones or None, moneda


@enrutador.get(
    "/especialidades/gestion",
    response_model=list[RespuestaEspecialidad],
    summary="Inventario de especialidades, incluidas las inactivas",
)
async def listar_especialidades_gestion(
    principal: PuedeGestionarEspecialidades,
    sesion: Sesion,
) -> list[RespuestaEspecialidad]:
    if principal.clinica_id is None:
        return []
    filas = (
        await sesion.execute(
            select(Especialidad)
            .where(
                Especialidad.clinica_id == principal.clinica_id,
                Especialidad.anulado_en.is_(None),
            )
            .order_by(Especialidad.nombre)
        )
    ).scalars()
    return [_respuesta_especialidad(item) for item in filas]


@enrutador.post("/especialidades", response_model=RespuestaEspecialidad, status_code=201)
async def crear_especialidad(
    datos: CrearEspecialidad,
    principal: PuedeGestionarEspecialidades,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> RespuestaEspecialidad:
    if principal.clinica_id is None:
        raise RecursoNoEncontrado("No hay una clínica asociada a esta sesión.")
    clinica = await sesion.get(Clinica, principal.clinica_id)
    if clinica is None or not clinica.activa or clinica.anulado_en is not None:
        raise RecursoNoEncontrado("No hay una clínica activa asociada a esta sesión.")
    nombre, codigo, descripcion = _validar_especialidad(datos)
    especialidad = Especialidad(
        clinica_id=clinica.id, nombre=nombre, codigo=codigo, descripcion=descripcion
    )
    sesion.add(especialidad)
    try:
        await sesion.flush()
    except IntegrityError as exc:
        await sesion.rollback()
        raise ConflictoEstado("Ya existe una especialidad con ese nombre en la clínica.") from exc
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.ESPECIALIDAD_CREADA,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="especialidad",
                entidad_id=especialidad.id,
            )
        ]
    )
    await sesion.commit()
    return _respuesta_especialidad(especialidad)


@enrutador.put("/especialidades/{especialidad_id}", response_model=RespuestaEspecialidad)
async def actualizar_especialidad(
    especialidad_id: uuid.UUID,
    datos: DatosEspecialidad,
    principal: PuedeGestionarEspecialidades,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> RespuestaEspecialidad:
    especialidad = (
        await sesion.execute(
            select(Especialidad)
            .where(
                Especialidad.id == especialidad_id,
                Especialidad.clinica_id == principal.clinica_id,
                Especialidad.anulado_en.is_(None),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if especialidad is None:
        raise RecursoNoEncontrado("No se encontró la especialidad dentro de su clínica.")
    especialidad.nombre, especialidad.codigo, especialidad.descripcion = _validar_especialidad(
        datos
    )
    try:
        await sesion.flush()
    except IntegrityError as exc:
        await sesion.rollback()
        raise ConflictoEstado("Ya existe una especialidad con ese nombre en la clínica.") from exc
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.ESPECIALIDAD_MODIFICADA,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="especialidad",
                entidad_id=especialidad.id,
            )
        ]
    )
    await sesion.commit()
    return _respuesta_especialidad(especialidad)


@enrutador.patch("/especialidades/{especialidad_id}/estado", response_model=RespuestaEspecialidad)
async def cambiar_estado_especialidad(
    especialidad_id: uuid.UUID,
    datos: EstadoRecurso,
    principal: PuedeGestionarEspecialidades,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> RespuestaEspecialidad:
    especialidad = (
        await sesion.execute(
            select(Especialidad)
            .where(
                Especialidad.id == especialidad_id,
                Especialidad.clinica_id == principal.clinica_id,
                Especialidad.anulado_en.is_(None),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if especialidad is None:
        raise RecursoNoEncontrado("No se encontró la especialidad dentro de su clínica.")
    if not datos.activo:
        tiene_servicios_activos = await sesion.scalar(
            select(Servicio.id)
            .where(
                Servicio.especialidad_id == especialidad.id,
                Servicio.activo.is_(True),
                Servicio.anulado_en.is_(None),
            )
            .limit(1)
        )
        if tiene_servicios_activos is not None:
            raise ConflictoEstado("Desactive primero los servicios activos de esta especialidad.")
    especialidad.activa = datos.activo
    await sesion.flush()
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.ESPECIALIDAD_MODIFICADA,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="especialidad",
                entidad_id=especialidad.id,
                activa=datos.activo,
            )
        ]
    )
    await sesion.commit()
    return _respuesta_especialidad(especialidad)


@enrutador.get(
    "/servicios/gestion",
    response_model=list[RespuestaServicioGestion],
    summary="Inventario de servicios, incluidos los inactivos",
)
async def listar_servicios_gestion(
    principal: PuedeGestionarServicios,
    sesion: Sesion,
) -> list[RespuestaServicioGestion]:
    if principal.clinica_id is None:
        return []
    filas = (
        await sesion.execute(
            select(Servicio)
            .where(Servicio.clinica_id == principal.clinica_id, Servicio.anulado_en.is_(None))
            .order_by(Servicio.nombre)
        )
    ).scalars()
    return [_respuesta_servicio_gestion(item) for item in filas]


@enrutador.post("/servicios", response_model=RespuestaServicioGestion, status_code=201)
async def crear_servicio(
    datos: CrearServicio,
    principal: PuedeGestionarServicios,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> RespuestaServicioGestion:
    if principal.clinica_id is None:
        raise RecursoNoEncontrado("No hay una clínica asociada a esta sesión.")
    especialidad = (
        await sesion.execute(
            select(Especialidad)
            .where(
                Especialidad.id == datos.especialidad_id,
                Especialidad.clinica_id == principal.clinica_id,
                Especialidad.activa.is_(True),
                Especialidad.anulado_en.is_(None),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if especialidad is None:
        raise RecursoNoEncontrado("No se encontró una especialidad activa dentro de su clínica.")
    nombre, descripcion, instrucciones, moneda = _validar_servicio(datos)
    servicio = Servicio(
        clinica_id=principal.clinica_id,
        especialidad_id=especialidad.id,
        nombre=nombre,
        descripcion=descripcion,
        duracion_minutos=datos.duracion_minutos,
        minutos_preparacion=datos.minutos_preparacion,
        precio=datos.precio,
        moneda=moneda,
        requiere_pago_previo=datos.requiere_pago_previo,
        instrucciones_preparacion=instrucciones,
        tipo_consultorio_requerido=datos.tipo_consultorio_requerido,
    )
    sesion.add(servicio)
    try:
        await sesion.flush()
    except IntegrityError as exc:
        await sesion.rollback()
        raise ConflictoEstado("Ya existe un servicio con ese nombre en la clínica.") from exc
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.SERVICIO_CREADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="servicio",
                entidad_id=servicio.id,
            )
        ]
    )
    await sesion.commit()
    return _respuesta_servicio_gestion(servicio)


@enrutador.put("/servicios/{servicio_id}", response_model=RespuestaServicioGestion)
async def actualizar_servicio(
    servicio_id: uuid.UUID,
    datos: DatosServicio,
    principal: PuedeGestionarServicios,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> RespuestaServicioGestion:
    servicio = (
        await sesion.execute(
            select(Servicio).where(
                Servicio.id == servicio_id,
                Servicio.clinica_id == principal.clinica_id,
                Servicio.anulado_en.is_(None),
            )
        )
    ).scalar_one_or_none()
    if servicio is None:
        raise RecursoNoEncontrado("No se encontró el servicio dentro de su clínica.")
    if datos.especialidad_id != servicio.especialidad_id:
        raise DatosInvalidos("La especialidad de un servicio existente no se puede cambiar.")
    nombre, descripcion, instrucciones, moneda = _validar_servicio(datos)
    servicio.nombre = nombre
    servicio.descripcion = descripcion
    servicio.duracion_minutos = datos.duracion_minutos
    servicio.minutos_preparacion = datos.minutos_preparacion
    servicio.precio = datos.precio
    servicio.moneda = moneda
    servicio.requiere_pago_previo = datos.requiere_pago_previo
    servicio.instrucciones_preparacion = instrucciones
    servicio.tipo_consultorio_requerido = datos.tipo_consultorio_requerido
    try:
        await sesion.flush()
    except IntegrityError as exc:
        await sesion.rollback()
        raise ConflictoEstado("Ya existe un servicio con ese nombre en la clínica.") from exc
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.SERVICIO_MODIFICADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="servicio",
                entidad_id=servicio.id,
            )
        ]
    )
    await sesion.commit()
    return _respuesta_servicio_gestion(servicio)


@enrutador.patch("/servicios/{servicio_id}/estado", response_model=RespuestaServicioGestion)
async def cambiar_estado_servicio(
    servicio_id: uuid.UUID,
    datos: EstadoRecurso,
    principal: PuedeGestionarServicios,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> RespuestaServicioGestion:
    servicio = (
        await sesion.execute(
            select(Servicio).where(
                Servicio.id == servicio_id,
                Servicio.clinica_id == principal.clinica_id,
                Servicio.anulado_en.is_(None),
            )
        )
    ).scalar_one_or_none()
    if servicio is None:
        raise RecursoNoEncontrado("No se encontró el servicio dentro de su clínica.")
    servicio.activo = datos.activo
    await sesion.flush()
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.SERVICIO_MODIFICADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="servicio",
                entidad_id=servicio.id,
                activo=datos.activo,
            )
        ]
    )
    await sesion.commit()
    return _respuesta_servicio_gestion(servicio)


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
