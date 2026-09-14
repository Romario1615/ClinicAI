import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.repositorio import RepositorioAgenda
from app.modulos.auditoria.repositorio import RepositorioAuditoria
from app.modulos.pagos.esquemas import CambioPago, DatosPago
from app.modulos.pagos.modelos import Pago
from app.modulos.pagos.repositorio import RepositorioPagos
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import Principal
from app.nucleo.errores import ConflictoEstado, PermisoDenegado, RecursoNoEncontrado
from app.nucleo.operaciones import completar_operacion, iniciar_operacion
from app.nucleo.reloj import Reloj

TRANSICIONES: dict[str, frozenset[str]] = {
    "PENDING": frozenset({"PROOF_RECEIVED", "CONFIRMED", "REJECTED"}),
    "PROOF_RECEIVED": frozenset({"UNDER_REVIEW", "CONFIRMED", "REJECTED"}),
    "UNDER_REVIEW": frozenset({"CONFIRMED", "REJECTED"}),
    "REJECTED": frozenset({"PROOF_RECEIVED", "UNDER_REVIEW"}),
    "CONFIRMED": frozenset({"REFUND_PENDING"}),
    "REFUND_PENDING": frozenset(),
}


class ServicioPagos:
    def __init__(self, sesion: AsyncSession, reloj: Reloj) -> None:
        self.sesion = sesion
        self.reloj = reloj
        self.repo = RepositorioPagos(sesion)

    async def registrar(self, datos: DatosPago, principal: Principal, clave: str) -> Pago:
        if not principal.tiene_permiso("pago.registrar"):
            raise PermisoDenegado("No puede registrar pagos.")
        cita = await RepositorioAgenda(self.sesion).obtener_cita(datos.cita_id, principal=principal)
        if cita is None:
            raise RecursoNoEncontrado("La cita solicitada no existe.")
        operacion = await iniciar_operacion(
            self.sesion,
            principal,
            self.reloj,
            "pago.registrar",
            clave,
            datos.model_dump(mode="json"),
        )
        if operacion.respuesta:
            return await self._obtener(uuid.UUID(str(operacion.respuesta["id"])), principal)
        pago = Pago(
            clinica_id=cita.clinica_id,
            creado_por=principal.actor_id,
            **datos.model_dump(),
        )
        self.sesion.add(pago)
        try:
            await self.sesion.flush()
        except IntegrityError as exc:
            await self.sesion.rollback()
            raise ConflictoEstado("La cita ya tiene un pago registrado.") from exc
        await self._auditar(pago, principal, AccionAuditada.PAGO_REGISTRADO)
        completar_operacion(operacion, {"id": str(pago.id)}, self.reloj)
        return pago

    async def cambiar(
        self, pago_id: uuid.UUID, datos: CambioPago, principal: Principal, clave: str
    ) -> Pago:
        if not principal.tiene_permiso("pago.validar"):
            raise PermisoDenegado("No puede validar pagos.")
        pago = await self._obtener(pago_id, principal)
        operacion = await iniciar_operacion(
            self.sesion,
            principal,
            self.reloj,
            "pago.validar",
            clave,
            {"id": pago_id, **datos.model_dump()},
        )
        if operacion.respuesta:
            return pago
        if datos.estado not in TRANSICIONES[pago.estado]:
            raise ConflictoEstado("Ese cambio de estado no esta permitido.")
        pago.estado = datos.estado
        pago.comentario = datos.comentario
        pago.validado_por = principal.actor_id
        pago.validado_en = self.reloj.ahora()
        pago.actualizado_por = principal.actor_id
        await self.sesion.flush()
        await self._auditar(
            pago,
            principal,
            AccionAuditada.PAGO_RECHAZADO
            if datos.estado == "REJECTED"
            else AccionAuditada.PAGO_VALIDADO,
        )
        completar_operacion(operacion, {"id": str(pago.id)}, self.reloj)
        return pago

    async def _obtener(self, pago_id: uuid.UUID, principal: Principal) -> Pago:
        pago = await self.repo.obtener(pago_id, principal)
        if pago is None:
            raise RecursoNoEncontrado("El pago solicitado no existe.")
        return pago

    async def _auditar(self, pago: Pago, principal: Principal, accion: AccionAuditada) -> None:
        await RepositorioAuditoria(self.sesion).registrar(
            [
                construir_entrada(
                    accion=accion,
                    principal=principal,
                    ahora=self.reloj.ahora(),
                    entidad_tipo="pago",
                    entidad_id=pago.id,
                    metadatos={"estado": pago.estado},
                )
            ]
        )
