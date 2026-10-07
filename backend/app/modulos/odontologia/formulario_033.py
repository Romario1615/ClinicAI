"""Captura clínica versionada del Formulario MSP 033/2021.

Las rutas aplican permiso por rol, módulo dental asignado y relación con el
paciente. Los datos de identidad se obtienen del registro maestro; las fuentes
clínicas opcionales se enlazan por sus versiones inmutables.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy import select

from app.modulos.agenda.modelos import Cita
from app.modulos.historia.especialidades import exige_modulo
from app.modulos.historia.modelos import NotaEvolucion
from app.modulos.odontologia.formulario_033_esquemas import (
    Formulario033Datos,
    Formulario033Entrada,
    Formulario033Salida,
    Formulario033VersionEntrada,
)
from app.modulos.odontologia.modelos import Formulario033, Odontograma, RegistroPlaca
from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.pacientes.acceso_clinico import GuardiaClinica
from app.modulos.pacientes.modelos import Paciente
from app.modulos.profesionales.modelos import Profesional
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import NivelSensibilidad, Principal
from app.nucleo.dependencias import Auditor, RelojActual, Sesion
from app.nucleo.errores import ConflictoEstado, DatosInvalidos, PermisoDenegado, RecursoNoEncontrado

enrutador_formulario_033 = APIRouter(prefix="/odontologia", tags=["formulario 033"])
DIAS_MAXIMOS_EDAD_DIAS = 30
MESES_MAXIMOS_EDAD_MESES = 24
PuedeLeer033 = Annotated[
    Principal,
    Depends(
        exige_modulo(
            "odontograma",
            "historia_clinica.leer",
            "historia_clinica.leer_sensible",
            exigir_todos=True,
        )
    ),
]
PuedeEscribir033 = Annotated[
    Principal,
    Depends(
        exige_modulo(
            "odontograma",
            "historia_clinica.escribir",
            "historia_clinica.leer_sensible",
            exigir_todos=True,
        )
    ),
]


def _salida(fila: Formulario033) -> Formulario033Salida:
    return Formulario033Salida(
        id=fila.id,
        raiz_id=fila.raiz_id,
        version=fila.version,
        vigente=fila.vigente,
        motivo_modificacion=fila.motivo_modificacion,
        paciente_id=fila.paciente_id,
        profesional_id=fila.profesional_id,
        sede_id=fila.sede_id,
        cita_id=fila.cita_id,
        nota_id=fila.nota_id,
        odontograma_id=fila.odontograma_id,
        registro_placa_id=fila.registro_placa_id,
        contexto_identidad=fila.contexto_identidad,
        datos=Formulario033Datos.model_validate(fila.contenido),
        creado_en=fila.creado_en,
    )


async def _paciente_bloqueado(
    sesion: Sesion,
    reloj: RelojActual,
    principal: Principal,
    paciente_id: uuid.UUID,
    permiso: str,
) -> Paciente:
    paciente = await GuardiaClinica(sesion).acceso_clinico(
        principal, paciente_id, permiso, reloj.ahora()
    )
    fila = await sesion.scalar(
        select(Paciente)
        .where(
            Paciente.id == paciente.id,
            Paciente.clinica_id == principal.clinica_id,
            Paciente.anulado_en.is_(None),
        )
        .with_for_update()
    )
    if fila is None:
        raise RecursoNoEncontrado("El paciente solicitado no existe.")
    return fila


def _profesional(principal: Principal) -> uuid.UUID:
    if principal.profesional_id is None:
        raise PermisoDenegado("Solo un profesional puede registrar el Formulario 033.")
    return principal.profesional_id


async def _validar_fuentes(
    sesion: Sesion,
    principal: Principal,
    paciente: Paciente,
    ahora: datetime,
    *,
    sede_id: uuid.UUID | None,
    cita_id: uuid.UUID | None,
    nota_id: uuid.UUID | None,
    odontograma_id: uuid.UUID | None,
    registro_placa_id: uuid.UUID | None,
) -> tuple[uuid.UUID, dict[str, object]]:
    """Comprueba referencias y congela identidad, sin aceptar datos maestros del cliente."""
    clinica_id = paciente.clinica_id
    identidad = await sesion.scalar(select(Clinica).where(Clinica.id == clinica_id))
    profesional_id = _profesional(principal)
    profesional = await sesion.scalar(
        select(Profesional).where(
            Profesional.id == profesional_id,
            Profesional.clinica_id == clinica_id,
            Profesional.activo.is_(True),
        )
    )
    if identidad is None or profesional is None:
        raise RecursoNoEncontrado("El recurso solicitado no existe.")

    cita = await _validar_cita(sesion, paciente, profesional_id, cita_id)
    if cita is not None:
        if sede_id is not None and sede_id != cita.sede_id:
            raise DatosInvalidos("La sede debe coincidir con la sede de la atención.")
        sede_id = cita.sede_id
    if sede_id is None:
        raise DatosInvalidos("Seleccione la sede donde se realizó la atención.")
    sede = await _validar_sede(sesion, principal, clinica_id, sede_id)
    fuentes: tuple[
        tuple[type[NotaEvolucion] | type[Odontograma] | type[RegistroPlaca], uuid.UUID | None], ...
    ] = (
        (NotaEvolucion, nota_id),
        (Odontograma, odontograma_id),
        (RegistroPlaca, registro_placa_id),
    )
    for modelo, identificador in fuentes:
        await _validar_fuente(sesion, modelo, identificador, paciente.id, clinica_id)
    if cita is not None and nota_id is not None:
        await _validar_nota_atencion(sesion, nota_id, cita.id)

    edad, unidad_edad = _edad_y_unidad(paciente.fecha_nacimiento, ahora.date())
    contexto: dict[str, object] = {
        "clinica": identidad.nombre,
        "identificacion_fiscal_clinica": identidad.identificacion_fiscal,
        "sede": sede.nombre,
        "direccion_sede": sede.direccion,
        "unicodigo": None,
        "historia_clinica": paciente.numero_documento,
        "tipo_documento": paciente.tipo_documento,
        "nombres": paciente.nombre,
        "apellidos": paciente.apellido,
        "sexo": paciente.sexo,
        "edad": edad,
        "unidad_edad": unidad_edad,
        "numero_archivo": None,
        "hoja": 1,
        "profesional": f"{profesional.nombre} {profesional.apellido}",
        "registro_profesional": profesional.numero_registro_profesional,
        "capturado_en": ahora.isoformat(),
    }
    return sede.id, contexto


def _edad_y_unidad(fecha_nacimiento: date | None, hoy: date) -> tuple[int | None, str | None]:
    if fecha_nacimiento is None:
        return None, None
    if fecha_nacimiento > hoy:
        raise DatosInvalidos("La fecha de nacimiento del paciente está en el futuro.")
    dias = (hoy - fecha_nacimiento).days
    meses = (hoy.year - fecha_nacimiento.year) * 12 + hoy.month - fecha_nacimiento.month
    if hoy.day < fecha_nacimiento.day:
        meses -= 1
    if dias < DIAS_MAXIMOS_EDAD_DIAS:
        return dias, "D"
    if meses < MESES_MAXIMOS_EDAD_MESES:
        return meses, "M"
    anios = hoy.year - fecha_nacimiento.year
    if (hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day):
        anios -= 1
    return anios, "A"


async def _validar_nota_atencion(sesion: Sesion, nota_id: uuid.UUID, cita_id: uuid.UUID) -> None:
    nota = await sesion.scalar(select(NotaEvolucion).where(NotaEvolucion.id == nota_id))
    if nota is not None and nota.cita_id is not None and nota.cita_id != cita_id:
        raise DatosInvalidos("La nota clínica pertenece a otra atención.")


async def _validar_cita(
    sesion: Sesion,
    paciente: Paciente,
    profesional_id: uuid.UUID,
    cita_id: uuid.UUID | None,
) -> Cita | None:
    if cita_id is None:
        return None
    cita = await sesion.scalar(
        select(Cita)
        .where(
            Cita.id == cita_id,
            Cita.paciente_id == paciente.id,
            Cita.clinica_id == paciente.clinica_id,
            Cita.profesional_id == profesional_id,
        )
        .with_for_update()
    )
    if cita is None:
        raise RecursoNoEncontrado("La atención solicitada no existe.")
    return cita


async def _validar_sede(
    sesion: Sesion,
    principal: Principal,
    clinica_id: uuid.UUID,
    sede_id: uuid.UUID,
) -> Sede:
    if not principal.ambito.cubre_sede(sede_id):
        raise RecursoNoEncontrado("La sede solicitada no existe.")
    sede = await sesion.scalar(
        select(Sede).where(
            Sede.id == sede_id,
            Sede.clinica_id == clinica_id,
            Sede.activa.is_(True),
            Sede.anulado_en.is_(None),
        )
    )
    if sede is None:
        raise RecursoNoEncontrado("La sede solicitada no existe.")
    return sede


async def _validar_fuente(
    sesion: Sesion,
    modelo: type[NotaEvolucion] | type[Odontograma] | type[RegistroPlaca],
    identificador: uuid.UUID | None,
    paciente_id: uuid.UUID,
    clinica_id: uuid.UUID,
) -> None:
    if identificador is None:
        return
    fila = await sesion.scalar(
        select(modelo).where(
            modelo.id == identificador,
            modelo.paciente_id == paciente_id,
            modelo.clinica_id == clinica_id,
        )
    )
    if fila is None:
        raise RecursoNoEncontrado("La fuente clínica solicitada no existe.")


def _nueva_fila(
    *,
    principal: Principal,
    paciente: Paciente,
    datos: Formulario033Datos,
    sede_id: uuid.UUID,
    contexto: dict[str, object],
    cita_id: uuid.UUID | None,
    nota_id: uuid.UUID | None,
    odontograma_id: uuid.UUID | None,
    registro_placa_id: uuid.UUID | None,
    version: int,
    motivo: str | None = None,
    raiz_id: uuid.UUID | None = None,
) -> Formulario033:
    valores: dict[str, object] = {
        "clinica_id": paciente.clinica_id,
        "paciente_id": paciente.id,
        "sede_id": sede_id,
        "profesional_id": _profesional(principal),
        "cita_id": cita_id,
        "nota_id": nota_id,
        "odontograma_id": odontograma_id,
        "registro_placa_id": registro_placa_id,
        "version": version,
        "vigente": True,
        "motivo_modificacion": motivo,
        "contexto_identidad": contexto,
        "contenido": datos.model_dump(mode="json"),
        "creado_por": principal.actor_id,
    }
    if raiz_id is not None:
        valores["raiz_id"] = raiz_id
    return Formulario033(**valores)


@enrutador_formulario_033.get(
    "/pacientes/{paciente_id}/formularios-033",
    response_model=list[Formulario033Salida],
    summary="Listar los Formularios 033 vigentes del paciente",
)
async def listar_formularios_033(
    principal: PuedeLeer033,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    paciente_id: Annotated[uuid.UUID, Path()],
) -> list[Formulario033Salida]:
    await GuardiaClinica(sesion).acceso_clinico(
        principal, paciente_id, "historia_clinica.leer", reloj.ahora()
    )
    filas = list(
        (
            await sesion.scalars(
                select(Formulario033)
                .where(
                    Formulario033.clinica_id == principal.clinica_id,
                    Formulario033.paciente_id == paciente_id,
                    Formulario033.vigente.is_(True),
                )
                .order_by(Formulario033.creado_en.desc())
                .limit(100)
            )
        ).all()
    )
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.FORMULARIO_033_CONSULTADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="formulario_033",
                entidad_id=fila.id,
                paciente_id=paciente_id,
                nivel_sensibilidad=NivelSensibilidad.CLINICO_SENSIBLE,
                version=fila.version,
            )
            for fila in filas
        ]
        or [
            construir_entrada(
                accion=AccionAuditada.FORMULARIO_033_CONSULTADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="paciente",
                entidad_id=paciente_id,
                paciente_id=paciente_id,
                nivel_sensibilidad=NivelSensibilidad.CLINICO_SENSIBLE,
                formularios_devueltos=0,
            )
        ]
    )
    await sesion.commit()
    return [_salida(fila) for fila in filas]


@enrutador_formulario_033.post(
    "/pacientes/{paciente_id}/formularios-033",
    response_model=Formulario033Salida,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una captura clínica 033/2021",
)
async def crear_formulario_033(
    principal: PuedeEscribir033,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    paciente_id: Annotated[uuid.UUID, Path()],
    datos: Formulario033Entrada,
) -> Formulario033Salida:
    paciente = await _paciente_bloqueado(
        sesion, reloj, principal, paciente_id, "historia_clinica.escribir"
    )
    sede_id, contexto = await _validar_fuentes(
        sesion,
        principal,
        paciente,
        ahora=reloj.ahora(),
        sede_id=datos.sede_id,
        cita_id=datos.cita_id,
        nota_id=datos.nota_id,
        odontograma_id=datos.odontograma_id,
        registro_placa_id=datos.registro_placa_id,
    )
    if datos.cita_id is not None:
        existente = await sesion.scalar(
            select(Formulario033.id).where(
                Formulario033.cita_id == datos.cita_id,
                Formulario033.vigente.is_(True),
            )
        )
        if existente is not None:
            raise ConflictoEstado("Esta atención ya tiene un Formulario 033 vigente.")
    fila = _nueva_fila(
        principal=principal,
        paciente=paciente,
        datos=datos.datos,
        sede_id=sede_id,
        contexto=contexto,
        cita_id=datos.cita_id,
        nota_id=datos.nota_id,
        odontograma_id=datos.odontograma_id,
        registro_placa_id=datos.registro_placa_id,
        version=1,
    )
    sesion.add(fila)
    await sesion.flush()
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.FORMULARIO_033_CREADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="formulario_033",
                entidad_id=fila.id,
                paciente_id=paciente_id,
                nivel_sensibilidad=NivelSensibilidad.CLINICO_SENSIBLE,
                version=1,
            )
        ]
    )
    await sesion.commit()
    return _salida(fila)


@enrutador_formulario_033.get(
    "/pacientes/{paciente_id}/formularios-033/{raiz_id}",
    response_model=Formulario033Salida,
    summary="Consultar una versión de Formulario 033",
)
async def obtener_formulario_033(
    principal: PuedeLeer033,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    paciente_id: Annotated[uuid.UUID, Path()],
    raiz_id: Annotated[uuid.UUID, Path()],
    version: Annotated[int | None, Query(ge=1)] = None,
) -> Formulario033Salida:
    await GuardiaClinica(sesion).acceso_clinico(
        principal, paciente_id, "historia_clinica.leer", reloj.ahora()
    )
    consulta = select(Formulario033).where(
        Formulario033.raiz_id == raiz_id,
        Formulario033.paciente_id == paciente_id,
        Formulario033.clinica_id == principal.clinica_id,
    )
    consulta = (
        consulta.where(Formulario033.version == version)
        if version is not None
        else consulta.where(Formulario033.vigente.is_(True))
    )
    fila = await sesion.scalar(consulta)
    if fila is None:
        raise RecursoNoEncontrado("El formulario solicitado no existe.")
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.FORMULARIO_033_CONSULTADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="formulario_033",
                entidad_id=fila.id,
                paciente_id=paciente_id,
                nivel_sensibilidad=NivelSensibilidad.CLINICO_SENSIBLE,
                version=fila.version,
            )
        ]
    )
    await sesion.commit()
    return _salida(fila)


@enrutador_formulario_033.post(
    "/pacientes/{paciente_id}/formularios-033/{raiz_id}/exportacion",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Autorizar y auditar la exportación imprimible de un Formulario 033",
)
async def auditar_exportacion_formulario_033(
    principal: PuedeLeer033,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    paciente_id: Annotated[uuid.UUID, Path()],
    raiz_id: Annotated[uuid.UUID, Path()],
    version: Annotated[int | None, Query(ge=1)] = None,
) -> Response:
    """Registra la impresión después de revalidar relación, clínica y permiso N3."""
    await GuardiaClinica(sesion).acceso_clinico(
        principal, paciente_id, "historia_clinica.leer", reloj.ahora()
    )
    consulta = select(Formulario033).where(
        Formulario033.raiz_id == raiz_id,
        Formulario033.paciente_id == paciente_id,
        Formulario033.clinica_id == principal.clinica_id,
    )
    consulta = (
        consulta.where(Formulario033.version == version)
        if version is not None
        else consulta.where(Formulario033.vigente.is_(True))
    )
    fila = await sesion.scalar(consulta)
    if fila is None:
        raise RecursoNoEncontrado("El formulario solicitado no existe.")
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.FORMULARIO_033_EXPORTADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="formulario_033",
                entidad_id=fila.id,
                paciente_id=paciente_id,
                nivel_sensibilidad=NivelSensibilidad.CLINICO_SENSIBLE,
                version=fila.version,
                formato="A4",
                destino="impresion_local",
            )
        ]
    )
    await sesion.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@enrutador_formulario_033.get(
    "/pacientes/{paciente_id}/formularios-033/{raiz_id}/versiones",
    response_model=list[Formulario033Salida],
    summary="Consultar el historial de versiones del Formulario 033",
)
async def listar_versiones_formulario_033(
    principal: PuedeLeer033,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    paciente_id: Annotated[uuid.UUID, Path()],
    raiz_id: Annotated[uuid.UUID, Path()],
) -> list[Formulario033Salida]:
    await GuardiaClinica(sesion).acceso_clinico(
        principal, paciente_id, "historia_clinica.leer", reloj.ahora()
    )
    filas = list(
        (
            await sesion.scalars(
                select(Formulario033)
                .where(
                    Formulario033.raiz_id == raiz_id,
                    Formulario033.paciente_id == paciente_id,
                    Formulario033.clinica_id == principal.clinica_id,
                )
                .order_by(Formulario033.version.desc())
            )
        ).all()
    )
    if not filas:
        raise RecursoNoEncontrado("El formulario solicitado no existe.")
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.FORMULARIO_033_CONSULTADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="formulario_033",
                entidad_id=fila.id,
                paciente_id=paciente_id,
                nivel_sensibilidad=NivelSensibilidad.CLINICO_SENSIBLE,
                version=fila.version,
            )
            for fila in filas
        ]
    )
    await sesion.commit()
    return [_salida(fila) for fila in filas]


@enrutador_formulario_033.post(
    "/pacientes/{paciente_id}/formularios-033/{raiz_id}/versiones",
    response_model=Formulario033Salida,
    status_code=status.HTTP_201_CREATED,
    summary="Corregir una captura creando una versión nueva",
    responses={409: {"description": "La versión base dejó de ser vigente"}},
)
async def versionar_formulario_033(
    principal: PuedeEscribir033,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    paciente_id: Annotated[uuid.UUID, Path()],
    raiz_id: Annotated[uuid.UUID, Path()],
    datos: Formulario033VersionEntrada,
) -> Formulario033Salida:
    paciente = await _paciente_bloqueado(
        sesion, reloj, principal, paciente_id, "historia_clinica.escribir"
    )
    actual = await sesion.scalar(
        select(Formulario033)
        .where(
            Formulario033.raiz_id == raiz_id,
            Formulario033.paciente_id == paciente.id,
            Formulario033.clinica_id == paciente.clinica_id,
            Formulario033.vigente.is_(True),
        )
        .with_for_update()
    )
    if actual is None:
        raise RecursoNoEncontrado("El formulario solicitado no existe.")
    if actual.version != datos.version_base:
        raise ConflictoEstado(
            "El formulario cambió desde que se abrió. Recargue la versión vigente.",
            detalles={"version_vigente": actual.version},
        )
    sede_id = datos.sede_id or actual.sede_id
    cita_id = datos.cita_id or actual.cita_id
    nota_id = datos.nota_id or actual.nota_id
    odontograma_id = datos.odontograma_id or actual.odontograma_id
    registro_placa_id = datos.registro_placa_id or actual.registro_placa_id
    sede_id_validada, contexto = await _validar_fuentes(
        sesion,
        principal,
        paciente,
        ahora=reloj.ahora(),
        sede_id=sede_id,
        cita_id=cita_id,
        nota_id=nota_id,
        odontograma_id=odontograma_id,
        registro_placa_id=registro_placa_id,
    )
    actual.vigente = False
    fila = _nueva_fila(
        principal=principal,
        paciente=paciente,
        datos=datos.datos,
        sede_id=sede_id_validada,
        contexto=contexto,
        cita_id=cita_id,
        nota_id=nota_id,
        odontograma_id=odontograma_id,
        registro_placa_id=registro_placa_id,
        version=actual.version + 1,
        motivo=datos.motivo,
        raiz_id=actual.raiz_id,
    )
    sesion.add(fila)
    await sesion.flush()
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.FORMULARIO_033_VERSIONADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="formulario_033",
                entidad_id=fila.id,
                paciente_id=paciente_id,
                nivel_sensibilidad=NivelSensibilidad.CLINICO,
                version=fila.version,
                version_anterior=actual.version,
            )
        ]
    )
    await sesion.commit()
    return _salida(fila)


__all__ = ["enrutador_formulario_033"]
