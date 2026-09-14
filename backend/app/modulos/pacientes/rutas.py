"""Rutas de pacientes.

Solo la ficha administrativa. Nada clinico: el motivo de consulta, el
diagnostico y la medicacion viven en la historia clinica, con su propio
control de acceso por tipo de informacion, y recepcion no los ve
(docs/security.md, seccion 1).

La consulta de un paciente se audita
------------------------------------
Leer la ficha de un paciente deja una entrada `paciente.consultado`. Es un
requisito de trazabilidad y tiene una consecuencia practica: ante la pregunta
«quien vio mis datos», hay respuesta. Sin ese registro, un acceso indebido por
curiosidad -- el caso mas frecuente en una clinica, y el mas dificil de
detectar -- no deja rastro.

El **listado** no se audita fila por fila, solo la busqueda con su termino.
Auditar cada fila de cada busqueda llenaria la tabla de auditoria de ruido y
haria inutilizable la consulta que de verdad importa: quien abrio la ficha
completa de una persona concreta.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, Request

from app.modulos.pacientes.esquemas import (
    DatosPaciente,
    PaginaPacientes,
    RespuestaPaciente,
    RespuestaPacienteDetalle,
)
from app.modulos.pacientes.modelos import Paciente
from app.modulos.pacientes.repositorio import LIMITE_MAXIMO, LONGITUD_MINIMA_BUSQUEDA
from app.modulos.pacientes.servicios import guardar_paciente
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import NivelSensibilidad, Principal
from app.nucleo.dependencias import (
    Auditor,
    RelojActual,
    RepoPacientes,
    Sesion,
    exige_permiso,
)
from app.nucleo.errores import RecursoNoEncontrado

enrutador = APIRouter(prefix="/pacientes", tags=["pacientes"])

PuedeLeerPacientes = Annotated[Principal, Depends(exige_permiso("paciente.leer_administrativo"))]
PuedeCrearPacientes = Annotated[Principal, Depends(exige_permiso("paciente.crear"))]
PuedeEditarPacientes = Annotated[Principal, Depends(exige_permiso("paciente.editar"))]
ClaveEscritura = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)]


@enrutador.post("/", response_model=RespuestaPaciente, status_code=201)
async def crear_paciente(
    datos: DatosPaciente,
    principal: PuedeCrearPacientes,
    sesion: Sesion,
    reloj: RelojActual,
    clave: ClaveEscritura,
) -> RespuestaPaciente:
    paciente = await guardar_paciente(sesion, principal, reloj, datos, clave)
    await sesion.commit()
    return _a_respuesta(paciente)


@enrutador.put("/{paciente_id}", response_model=RespuestaPaciente)
async def editar_paciente(
    paciente_id: uuid.UUID,
    datos: DatosPaciente,
    principal: PuedeEditarPacientes,
    sesion: Sesion,
    reloj: RelojActual,
    clave: ClaveEscritura,
) -> RespuestaPaciente:
    paciente = await guardar_paciente(sesion, principal, reloj, datos, clave, paciente_id)
    await sesion.commit()
    return _a_respuesta(paciente)


def _a_respuesta(paciente: Paciente) -> RespuestaPaciente:
    return RespuestaPaciente(
        id=paciente.id,
        tipo_documento=paciente.tipo_documento,
        numero_documento=paciente.numero_documento,
        nombre=paciente.nombre,
        apellido=paciente.apellido,
        fecha_nacimiento=paciente.fecha_nacimiento,
        telefono_whatsapp=paciente.telefono_whatsapp,
        correo=paciente.correo,
        nivel_verificacion=paciente.nivel_verificacion,
    )


@enrutador.get(
    "/",
    response_model=PaginaPacientes,
    summary="Buscar pacientes",
    responses={403: {"description": "Sin permiso para leer datos de pacientes"}},
)
async def buscar_pacientes(
    principal: PuedeLeerPacientes,
    repo: RepoPacientes,
    termino: Annotated[
        str | None,
        Query(
            max_length=100,
            description=(
                f"Busca en nombre y apellido. Se ignora con menos de "
                f"{LONGITUD_MINIMA_BUSQUEDA} caracteres."
            ),
        ),
    ] = None,
    documento: Annotated[
        str | None,
        Query(max_length=32, description="Coincidencia exacta, nunca parcial."),
    ] = None,
    limite: Annotated[int, Query(ge=1, le=LIMITE_MAXIMO)] = 25,
    desplazamiento: Annotated[int, Query(ge=0)] = 0,
) -> PaginaPacientes:
    """Busca pacientes dentro del ambito del solicitante.

    Sin termino ni documento devuelve la primera pagina del listado, siempre
    acotada por el ambito y por el techo de resultados.

    Un termino de menos de tres caracteres devuelve vacio en lugar de error:
    la interfaz busca mientras se teclea, y un error por cada letra seria
    ruido. Pero devolver resultados con una o dos letras convertiria el
    buscador en un volcado de la clinica.

    El documento se busca por coincidencia **exacta**. Una busqueda parcial
    permitiria enumerar cedulas probando prefijos.
    """
    elementos = await repo.buscar(
        principal,
        termino=termino,
        documento=documento,
        limite=limite,
        desplazamiento=desplazamiento,
    )
    total = await repo.contar(principal, termino=termino, documento=documento)

    return PaginaPacientes(
        elementos=[_a_respuesta(paciente) for paciente in elementos],
        total=total,
        limite=limite,
        desplazamiento=desplazamiento,
        termino_ignorado=(
            termino is not None
            and documento is None
            and len(termino.strip()) < LONGITUD_MINIMA_BUSQUEDA
        ),
    )


@enrutador.get(
    "/{paciente_id}",
    response_model=RespuestaPacienteDetalle,
    summary="Ficha administrativa de un paciente",
    responses={404: {"description": "No existe, o esta fuera del ambito"}},
)
async def obtener_paciente(
    peticion: Request,
    principal: PuedeLeerPacientes,
    repo: RepoPacientes,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
    paciente_id: Annotated[uuid.UUID, Path()],
) -> RespuestaPacienteDetalle:
    """Devuelve la ficha y **deja constancia de quien la consulto**.

    Un paciente fuera del ambito responde 404, igual que uno inexistente. Un
    403 confirmaria que ese identificador corresponde a un paciente real de la
    clinica, y con eso se enumeran.
    """
    paciente = await repo.obtener(paciente_id, principal)
    if paciente is None:
        raise RecursoNoEncontrado("El paciente solicitado no existe.")

    entrada = construir_entrada(
        accion=AccionAuditada.PACIENTE_CONSULTADO,
        principal=principal,
        ahora=reloj.ahora(),
        entidad_tipo="paciente",
        entidad_id=paciente.id,
        paciente_id=paciente.id,
        nivel_sensibilidad=NivelSensibilidad.ADMINISTRATIVO,
        ip=peticion.client.host if peticion.client else None,
        correlacion_id=getattr(peticion.state, "correlacion_id", None),
    )
    await auditor.registrar([entrada])
    await sesion.commit()

    return RespuestaPacienteDetalle(
        **_a_respuesta(paciente).model_dump(),
        sexo=paciente.sexo,
        direccion=paciente.direccion,
        activo=paciente.activo,
    )


__all__ = ["enrutador"]
