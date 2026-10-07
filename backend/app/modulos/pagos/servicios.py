import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.repositorio import RepositorioAgenda
from app.modulos.auditoria.repositorio import RepositorioAuditoria
from app.modulos.pagos.esquemas import CambioPago, DatosCargoPago, DatosPago
from app.modulos.pagos.modelos import CargoPago, Pago, PagoComprobante, PagoHistorial
from app.modulos.pagos.repositorio import RepositorioPagos
from app.nucleo.almacen import AlmacenObjetos, ErrorAlmacen
from app.nucleo.archivos import sanear_comprobante
from app.nucleo.auditoria import AccionAuditada, EntradaAuditoria, construir_entrada
from app.nucleo.autorizacion import Principal
from app.nucleo.configuracion import Configuracion
from app.nucleo.errores import (
    ConflictoEstado,
    DatosInvalidos,
    PermisoDenegado,
    ProveedorExternoNoDisponible,
    RecursoNoEncontrado,
)
from app.nucleo.operaciones import completar_operacion, iniciar_operacion
from app.nucleo.reloj import Reloj
from app.nucleo.seguridad import CifradorDatos

TRANSICIONES: dict[str, frozenset[str]] = {
    "PENDING": frozenset({"PROOF_RECEIVED", "CONFIRMED", "REJECTED"}),
    "PROOF_RECEIVED": frozenset({"UNDER_REVIEW", "CONFIRMED", "REJECTED"}),
    "UNDER_REVIEW": frozenset({"CONFIRMED", "REJECTED"}),
    "REJECTED": frozenset({"PROOF_RECEIVED", "UNDER_REVIEW"}),
    "CONFIRMED": frozenset({"REFUND_PENDING"}),
    "REFUND_PENDING": frozenset(),
}


@dataclass(frozen=True, slots=True)
class DescargaComprobante:
    comprobante: PagoComprobante
    datos: bytes


class ServicioPagos:
    def __init__(
        self,
        sesion: AsyncSession,
        reloj: Reloj,
        almacen: AlmacenObjetos | None = None,
        cifrador: CifradorDatos | None = None,
        configuracion: Configuracion | None = None,
    ) -> None:
        self.sesion = sesion
        self.reloj = reloj
        self.repo = RepositorioPagos(sesion)
        self._almacen = almacen
        self._cifrador = cifrador
        self._configuracion = configuracion

    async def registrar(self, datos: DatosPago, principal: Principal, clave: str) -> Pago:
        if not principal.tiene_permiso("pago.registrar"):
            raise PermisoDenegado("No puede registrar pagos.")
        cita = await RepositorioAgenda(self.sesion).obtener_cita_para_actualizar(
            datos.cita_id, principal=principal
        )
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

        cargo, crear_cargo, conciliar_cargo = await self._preparar_cargo(
            cita.id, cita.clinica_id, datos, principal
        )

        comprometido = await self.repo.total_comprometido(cargo.id)
        if cargo.total_acordado is None or comprometido + datos.importe > cargo.total_acordado:
            raise ConflictoEstado("El abono supera el saldo disponible del cargo pactado.")
        pago = Pago(
            clinica_id=cita.clinica_id,
            cargo_id=cargo.id,
            creado_por=principal.actor_id,
            **datos.model_dump(exclude={"total_acordado", "fecha_vencimiento"}),
        )
        self.sesion.add(pago)
        try:
            await self.sesion.flush()
        except IntegrityError as exc:
            await self.sesion.rollback()
            raise ConflictoEstado("No se pudo registrar el abono para este cargo.") from exc
        self.sesion.add(
            PagoHistorial(
                pago_id=pago.id,
                estado_anterior=None,
                estado_nuevo=pago.estado,
                actor_id=principal.actor_id,
                secuencia=1,
                ocurrido_en=self.reloj.ahora(),
            )
        )
        await self._auditar(pago, principal, AccionAuditada.PAGO_REGISTRADO)
        if crear_cargo:
            await self._auditar_cargo(cargo, principal, AccionAuditada.CARGO_PAGO_CREADO)
        elif conciliar_cargo:
            await self._auditar_cargo(cargo, principal, AccionAuditada.CARGO_PAGO_CONCILIADO)
        completar_operacion(operacion, {"id": str(pago.id)}, self.reloj)
        return pago

    async def _preparar_cargo(
        self,
        cita_id: uuid.UUID,
        clinica_id: uuid.UUID,
        datos: DatosPago,
        principal: Principal,
    ) -> tuple[CargoPago, bool, bool]:
        cargo = await self.repo.cargo_por_cita(cita_id, clinica_id, bloquear=True)
        if cargo is None:
            if datos.total_acordado is None:
                raise DatosInvalidos("Indique el total pactado antes de registrar el primer abono.")
            cargo = CargoPago(
                clinica_id=clinica_id,
                cita_id=cita_id,
                total_acordado=datos.total_acordado,
                fecha_vencimiento=datos.fecha_vencimiento,
                moneda="USD",
                origen="PACTADO",
                creado_por=principal.actor_id,
            )
            self.sesion.add(cargo)
            await self.sesion.flush()
            return cargo, True, False

        if cargo.total_acordado is None:
            if datos.total_acordado is None:
                raise DatosInvalidos(
                    "Este cargo histórico no tiene total conocido. Indique el total pactado para conciliarlo."
                )
            comprometido = await self.repo.total_comprometido(cargo.id)
            if datos.total_acordado < comprometido + datos.importe:
                raise ConflictoEstado(
                    "El total pactado no puede ser menor que los pagos ya registrados más este abono."
                )
            cargo.total_acordado = datos.total_acordado
            cargo.fecha_vencimiento = datos.fecha_vencimiento
            cargo.origen = "PACTADO"
            cargo.creado_por = principal.actor_id
            await self.sesion.flush()
            return cargo, False, True

        if datos.total_acordado is not None and datos.total_acordado != cargo.total_acordado:
            raise ConflictoEstado("El total pactado de este cargo es inmutable.")
        if (
            datos.fecha_vencimiento is not None
            and datos.fecha_vencimiento != cargo.fecha_vencimiento
        ):
            raise ConflictoEstado("La fecha de vencimiento del cargo es inmutable.")
        return cargo, False, False

    async def crear_cargo(
        self, datos: DatosCargoPago, principal: Principal, clave: str
    ) -> CargoPago:
        if not principal.tiene_permiso("pago.registrar"):
            raise PermisoDenegado("No puede crear cargos de pago.")
        cita = await RepositorioAgenda(self.sesion).obtener_cita_para_actualizar(
            datos.cita_id, principal=principal
        )
        if cita is None:
            raise RecursoNoEncontrado("La cita solicitada no existe.")
        operacion = await iniciar_operacion(
            self.sesion,
            principal,
            self.reloj,
            "cargo_pago.crear",
            clave,
            datos.model_dump(mode="json"),
        )
        if operacion.respuesta:
            return await self._cargo_visible(uuid.UUID(str(operacion.respuesta["id"])), principal)
        if await self.repo.cargo_por_cita(cita.id, cita.clinica_id, bloquear=True) is not None:
            raise ConflictoEstado("La cita ya tiene un cargo de pago.")
        cargo = CargoPago(
            clinica_id=cita.clinica_id,
            cita_id=cita.id,
            total_acordado=datos.total_acordado,
            fecha_vencimiento=datos.fecha_vencimiento,
            moneda="USD",
            origen="PACTADO",
            creado_por=principal.actor_id,
        )
        self.sesion.add(cargo)
        try:
            await self.sesion.flush()
        except IntegrityError as exc:
            await self.sesion.rollback()
            raise ConflictoEstado("La cita ya tiene un cargo de pago.") from exc
        await self._auditar_cargo(cargo, principal, AccionAuditada.CARGO_PAGO_CREADO)
        completar_operacion(operacion, {"id": str(cargo.id)}, self.reloj)
        return cargo

    async def conciliar_cargo(
        self,
        cargo_id: uuid.UUID,
        total_acordado: Decimal,
        principal: Principal,
        fecha_vencimiento: date | None = None,
    ) -> CargoPago:
        if not principal.tiene_permiso("pago.validar"):
            raise PermisoDenegado("No puede conciliar el total pactado.")
        visible = await self._cargo_visible(cargo_id, principal)
        cita = await RepositorioAgenda(self.sesion).obtener_cita_para_actualizar(
            visible.cita_id, principal=principal
        )
        if cita is None:
            raise RecursoNoEncontrado("El cargo solicitado no existe.")
        cargo = await self._cargo_visible(cargo_id, principal, bloquear=True)
        if cargo.cita_id != cita.id:
            raise RecursoNoEncontrado("El cargo solicitado no existe.")
        if cargo.total_acordado is not None:
            if cargo.total_acordado == total_acordado and (
                fecha_vencimiento is None or cargo.fecha_vencimiento == fecha_vencimiento
            ):
                return cargo
            raise ConflictoEstado("El total pactado de este cargo ya quedó fijado.")
        comprometido = await self.repo.total_comprometido(cargo.id)
        if total_acordado < comprometido:
            raise ConflictoEstado("El total no puede ser menor que los pagos ya registrados.")
        cargo.total_acordado = total_acordado
        cargo.fecha_vencimiento = fecha_vencimiento
        cargo.origen = "PACTADO"
        cargo.creado_por = principal.actor_id
        await self.sesion.flush()
        await self._auditar_cargo(cargo, principal, AccionAuditada.CARGO_PAGO_CONCILIADO)
        return cargo

    async def fijar_vencimiento(
        self, cargo_id: uuid.UUID, fecha_vencimiento: date, principal: Principal
    ) -> CargoPago:
        if not principal.tiene_permiso("pago.validar"):
            raise PermisoDenegado("No puede fijar el vencimiento de un cargo.")
        visible = await self._cargo_visible(cargo_id, principal)
        cita = await RepositorioAgenda(self.sesion).obtener_cita_para_actualizar(
            visible.cita_id, principal=principal
        )
        if cita is None:
            raise RecursoNoEncontrado("El cargo solicitado no existe.")
        cargo = await self._cargo_visible(cargo_id, principal, bloquear=True)
        if cargo.cita_id != cita.id:
            raise RecursoNoEncontrado("El cargo solicitado no existe.")
        if cargo.fecha_vencimiento is not None:
            if cargo.fecha_vencimiento == fecha_vencimiento:
                return cargo
            raise ConflictoEstado("El vencimiento de este cargo ya quedó fijado.")
        cargo.fecha_vencimiento = fecha_vencimiento
        await self.sesion.flush()
        await self._auditar_cargo(cargo, principal, AccionAuditada.CARGO_PAGO_VENCIMIENTO_FIJADO)
        return cargo

    async def cambiar(
        self, pago_id: uuid.UUID, datos: CambioPago, principal: Principal, clave: str
    ) -> Pago:
        if not principal.tiene_permiso("pago.validar"):
            raise PermisoDenegado("No puede validar pagos.")
        visible = await self.repo.visible(pago_id, principal)
        if visible is None:
            raise RecursoNoEncontrado("El pago solicitado no existe.")
        cita = await RepositorioAgenda(self.sesion).obtener_cita_para_actualizar(
            visible.cita_id, principal=principal
        )
        if cita is None:
            raise RecursoNoEncontrado("El pago solicitado no existe.")
        cargo = await self.repo.cargo_por_cita(cita.id, cita.clinica_id, bloquear=True)
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
        if pago.estado == "REJECTED" and datos.estado != "REJECTED":
            if cargo is None or cargo.total_acordado is None:
                raise ConflictoEstado("Concilie el total histórico antes de reactivar este pago.")
            comprometido = await self.repo.total_comprometido(cargo.id)
            if comprometido + pago.importe > cargo.total_acordado:
                raise ConflictoEstado(
                    "Reactivar este pago superaría el saldo disponible del cargo."
                )
        estado_anterior = pago.estado
        pago.estado = datos.estado
        pago.comentario = datos.comentario
        pago.validado_por = principal.actor_id
        pago.validado_en = self.reloj.ahora()
        pago.actualizado_por = principal.actor_id
        self.sesion.add(
            PagoHistorial(
                pago_id=pago.id,
                estado_anterior=estado_anterior,
                estado_nuevo=pago.estado,
                comentario=datos.comentario,
                actor_id=principal.actor_id,
                secuencia=await self.repo.proxima_secuencia_historial(pago.id),
                ocurrido_en=self.reloj.ahora(),
            )
        )
        await self.sesion.flush()
        await self._auditar(
            pago,
            principal,
            AccionAuditada.PAGO_RECHAZADO
            if datos.estado == "REJECTED"
            else AccionAuditada.PAGO_VALIDADO,
            estado_anterior=estado_anterior,
        )
        completar_operacion(operacion, {"id": str(pago.id)}, self.reloj)
        return pago

    async def subir_comprobante(
        self, pago_id: uuid.UUID, contenido: bytes, principal: Principal
    ) -> tuple[PagoComprobante, tuple[EntradaAuditoria, ...]]:
        if not principal.tiene_permiso("pago.registrar"):
            raise PermisoDenegado("No puede adjuntar comprobantes de pago.")
        almacen, cifrador, configuracion = self._dependencias_archivos()
        visible = await self.repo.visible(pago_id, principal)
        if visible is None:
            raise RecursoNoEncontrado("El pago solicitado no existe.")
        cita = await RepositorioAgenda(self.sesion).obtener_cita_para_actualizar(
            visible.cita_id, principal=principal
        )
        if cita is None:
            raise RecursoNoEncontrado("El pago solicitado no existe.")
        cargo = await self.repo.cargo_por_cita(cita.id, cita.clinica_id, bloquear=True)
        pago = await self._obtener(pago_id, principal)
        if pago.estado not in {"PENDING", "REJECTED"}:
            raise ConflictoEstado("Solo se adjunta evidencia a pagos pendientes o rechazados.")
        if pago.estado == "REJECTED":
            if cargo is None or cargo.total_acordado is None:
                raise ConflictoEstado("Concilie el total histórico antes de reactivar este pago.")
            comprometido = await self.repo.total_comprometido(cargo.id)
            if comprometido + pago.importe > cargo.total_acordado:
                raise ConflictoEstado(
                    "Reactivar este pago superaría el saldo disponible del cargo."
                )
        saneado = await sanear_comprobante(contenido, configuracion)
        comprobante_id = uuid.uuid4()
        clave = f"{principal.clinica_id}/pagos/{pago.id}/{comprobante_id}"
        comprobante = PagoComprobante(
            id=comprobante_id,
            pago_id=pago.id,
            tipo_mime=saneado.tipo_mime,
            tamano_bytes=len(saneado.datos),
            sha256=saneado.sha256,
            clave_objeto=clave,
            antivirus=saneado.antivirus.value,
            cargado_por=principal.actor_id,
            cargado_en=self.reloj.ahora(),
        )
        self.sesion.add(comprobante)
        await self.sesion.flush()
        cifrado = cifrador.cifrar_bytes(saneado.datos, contexto=comprobante.id.bytes)
        try:
            await almacen.guardar(clave, cifrado)
        except (ErrorAlmacen, OSError) as exc:
            await self.sesion.rollback()
            raise ProveedorExternoNoDisponible(
                "No se pudo guardar el comprobante. Inténtelo de nuevo."
            ) from exc

        estado_anterior = pago.estado
        pago.estado = "PROOF_RECEIVED"
        pago.actualizado_por = principal.actor_id
        self.sesion.add(
            PagoHistorial(
                pago_id=pago.id,
                estado_anterior=estado_anterior,
                estado_nuevo=pago.estado,
                comentario="Se adjuntó un comprobante para revisión.",
                actor_id=principal.actor_id,
                secuencia=await self.repo.proxima_secuencia_historial(pago.id),
                ocurrido_en=self.reloj.ahora(),
            )
        )
        await self.sesion.flush()
        entrada = construir_entrada(
            accion=AccionAuditada.PAGO_COMPROBANTE_CARGADO,
            principal=principal,
            ahora=self.reloj.ahora(),
            entidad_tipo="pago_comprobante",
            entidad_id=comprobante.id,
            pago_id=str(pago.id),
            tipo_mime=comprobante.tipo_mime,
            tamano_bytes=comprobante.tamano_bytes,
            antivirus=comprobante.antivirus,
        )
        await self._auditar(
            pago,
            principal,
            AccionAuditada.PAGO_COMPROBANTE_CARGADO,
            estado_anterior=estado_anterior,
        )
        return comprobante, (entrada,)

    async def descargar_comprobante(
        self, comprobante_id: uuid.UUID, principal: Principal
    ) -> tuple[DescargaComprobante, tuple[EntradaAuditoria, ...]]:
        almacen, cifrador, _configuracion = self._dependencias_archivos()
        comprobante = await self.repo.comprobante_visible(comprobante_id, principal)
        if comprobante is None:
            raise RecursoNoEncontrado("El comprobante solicitado no existe.")
        try:
            cifrado = await almacen.leer(comprobante.clave_objeto)
        except (ErrorAlmacen, OSError) as exc:
            raise ProveedorExternoNoDisponible(
                "El comprobante no está disponible en este momento."
            ) from exc
        datos = cifrador.descifrar_bytes(cifrado, contexto=comprobante.id.bytes)
        entrada = construir_entrada(
            accion=AccionAuditada.PAGO_COMPROBANTE_CONSULTADO,
            principal=principal,
            ahora=self.reloj.ahora(),
            entidad_tipo="pago_comprobante",
            entidad_id=comprobante.id,
            tipo_mime=comprobante.tipo_mime,
            tamano_bytes=comprobante.tamano_bytes,
        )
        return DescargaComprobante(comprobante, datos), (entrada,)

    def _dependencias_archivos(self) -> tuple[AlmacenObjetos, CifradorDatos, Configuracion]:
        if self._almacen is None or self._cifrador is None or self._configuracion is None:
            raise RuntimeError(
                "El servicio de comprobantes requiere almacén, cifrador y configuración."
            )
        return self._almacen, self._cifrador, self._configuracion

    async def _obtener(self, pago_id: uuid.UUID, principal: Principal) -> Pago:
        pago = await self.repo.obtener(pago_id, principal)
        if pago is None:
            raise RecursoNoEncontrado("El pago solicitado no existe.")
        return pago

    async def _cargo_visible(
        self, cargo_id: uuid.UUID, principal: Principal, *, bloquear: bool = False
    ) -> CargoPago:
        cargo = await self.repo.cargo_visible(cargo_id, principal, bloquear=bloquear)
        if cargo is None:
            raise RecursoNoEncontrado("El cargo solicitado no existe.")
        return cargo

    async def _auditar_cargo(
        self, cargo: CargoPago, principal: Principal, accion: AccionAuditada
    ) -> None:
        await RepositorioAuditoria(self.sesion).registrar(
            [
                construir_entrada(
                    accion=accion,
                    principal=principal,
                    ahora=self.reloj.ahora(),
                    entidad_tipo="cargo_pago",
                    entidad_id=cargo.id,
                    cita_id=str(cargo.cita_id),
                    total_acordado=(
                        str(cargo.total_acordado) if cargo.total_acordado is not None else None
                    ),
                    fecha_vencimiento=(
                        cargo.fecha_vencimiento.isoformat() if cargo.fecha_vencimiento else None
                    ),
                )
            ]
        )

    async def _auditar(
        self,
        pago: Pago,
        principal: Principal,
        accion: AccionAuditada,
        *,
        estado_anterior: str | None = None,
    ) -> None:
        await RepositorioAuditoria(self.sesion).registrar(
            [
                construir_entrada(
                    accion=accion,
                    principal=principal,
                    ahora=self.reloj.ahora(),
                    entidad_tipo="pago",
                    entidad_id=pago.id,
                    estado_anterior=estado_anterior,
                    estado_nuevo=pago.estado,
                )
            ]
        )
