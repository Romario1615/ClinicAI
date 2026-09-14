"""Escrituras administrativas autorizadas, auditadas e idempotentes."""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.repositorio import RepositorioAuditoria
from app.modulos.pacientes.esquemas import DatosPaciente
from app.modulos.pacientes.modelos import Paciente
from app.modulos.pacientes.repositorio import RepositorioPacientes
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import Principal
from app.nucleo.errores import ConflictoEstado, DatosInvalidos, PermisoDenegado, RecursoNoEncontrado
from app.nucleo.operaciones import completar_operacion, iniciar_operacion
from app.nucleo.reloj import Reloj


async def guardar_paciente(
    sesion: AsyncSession,
    principal: Principal,
    reloj: Reloj,
    datos: DatosPaciente,
    clave: str,
    paciente_id: uuid.UUID | None = None,
) -> Paciente:
    permiso = "paciente.editar" if paciente_id else "paciente.crear"
    if not principal.tiene_permiso(permiso) or principal.clinica_id is None:
        raise PermisoDenegado("No puede guardar pacientes.")
    if paciente_id is None and not principal.ambito.todos_los_pacientes:
        raise PermisoDenegado("El alta requiere ambito administrativo de pacientes.")
    if datos.fecha_nacimiento and datos.fecha_nacimiento > reloj.ahora().date():
        raise DatosInvalidos("La fecha de nacimiento no puede estar en el futuro.")
    repo = RepositorioPacientes(sesion)
    paciente = await repo.obtener(paciente_id, principal) if paciente_id else None
    if paciente_id and paciente is None:
        raise RecursoNoEncontrado("El paciente solicitado no existe.")
    operacion = await iniciar_operacion(
        sesion,
        principal,
        reloj,
        permiso,
        clave,
        {"paciente_id": paciente_id, **datos.model_dump(mode="json")},
    )
    if operacion.respuesta:
        anterior = await repo.obtener(uuid.UUID(str(operacion.respuesta["id"])), principal)
        if anterior is None:
            raise RecursoNoEncontrado("El paciente solicitado no existe.")
        return anterior
    if paciente is None:
        paciente = Paciente(clinica_id=principal.clinica_id, creado_por=principal.actor_id)
        sesion.add(paciente)
    elif paciente.telefono_whatsapp != datos.telefono_whatsapp:
        # Cambiar el telefono invalida la comprobacion de ese canal.
        paciente.whatsapp_verificado_en = None
        if paciente.nivel_verificacion == "TELEFONO":
            paciente.nivel_verificacion = "NO_VERIFICADO"
            paciente.verificado_en = None
            paciente.verificado_por = None
    for nombre, valor in datos.model_dump().items():
        setattr(paciente, nombre, valor)
    paciente.actualizado_por = principal.actor_id
    try:
        await sesion.flush()
    except IntegrityError as exc:
        await sesion.rollback()
        raise ConflictoEstado("Ya existe un paciente con ese documento.") from exc
    await RepositorioAuditoria(sesion).registrar(
        [
            construir_entrada(
                accion=AccionAuditada.PACIENTE_MODIFICADO
                if paciente_id
                else AccionAuditada.PACIENTE_CREADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="paciente",
                entidad_id=paciente.id,
                paciente_id=paciente.id,
            )
        ]
    )
    completar_operacion(operacion, {"id": str(paciente.id)}, reloj)
    return paciente
