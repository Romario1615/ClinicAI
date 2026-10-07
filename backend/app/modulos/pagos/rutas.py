import csv
import io
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, Query, Request, Response, UploadFile

from app.modulos.pagos.esquemas import (
    CambioPago,
    ComprobantePago,
    DatosCargoPago,
    DatosPago,
    EstadoPago,
    FechaVencimientoCargo,
    HistorialPago,
    ListaComprobantesPago,
    PaginaCargosPago,
    PaginaPagos,
    RespuestaCargoPago,
    RespuestaPago,
    TotalCargoPago,
)
from app.modulos.pagos.modelos import CargoPago, Pago, PagoComprobante
from app.modulos.pagos.repositorio import RepositorioPagos
from app.modulos.pagos.servicios import ServicioPagos
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import (
    AlmacenActual,
    Auditor,
    CifradorActual,
    ConfiguracionActual,
    RelojActual,
    Sesion,
    exige_permiso,
)
from app.nucleo.errores import ArchivoDemasiadoGrande, DatosInvalidos, RecursoNoEncontrado

enrutador = APIRouter(prefix="/pagos", tags=["pagos"])
DIAS_MAXIMOS_REPORTE = 366
PuedeLeer = Annotated[Principal, Depends(exige_permiso("pago.leer"))]
PuedeExportarReportes = Annotated[Principal, Depends(exige_permiso("reporte.exportar"))]
PuedeRegistrar = Annotated[Principal, Depends(exige_permiso("pago.registrar"))]
PuedeValidar = Annotated[Principal, Depends(exige_permiso("pago.validar"))]
Clave = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)]


def _salida_comprobante(comprobante: PagoComprobante) -> ComprobantePago:
    return ComprobantePago(
        id=comprobante.id,
        pago_id=comprobante.pago_id,
        tipo_mime=comprobante.tipo_mime,
        tamano_bytes=comprobante.tamano_bytes,
        antivirus=comprobante.antivirus,
        cargado_por=comprobante.cargado_por,
        cargado_en=comprobante.cargado_en,
        url_contenido=f"/api/v1/pagos/comprobantes/{comprobante.id}/contenido",
    )


def _salida_cargo(
    fila: tuple[CargoPago, str, datetime, Decimal, Decimal, bool],
) -> RespuestaCargoPago:
    cargo, paciente, inicio, confirmado, comprometido, vencido = fila
    total = cargo.total_acordado
    return RespuestaCargoPago(
        id=cargo.id,
        cita_id=cargo.cita_id,
        total_acordado=total,
        fecha_vencimiento=cargo.fecha_vencimiento,
        moneda=cargo.moneda,
        origen=cargo.origen,
        creado_en=cargo.creado_en,
        paciente=paciente,
        cita_inicio=inicio,
        total_confirmado=confirmado,
        total_comprometido=comprometido,
        saldo_pendiente=total - confirmado if total is not None else None,
        saldo_no_asignado=total - comprometido if total is not None else None,
        vencido=vencido,
    )


async def _salida_pago(pago: Pago, principal: Principal, sesion: Sesion) -> RespuestaPago:
    respuesta = RespuestaPago.model_validate(pago)
    if not pago.cargo_id:
        return respuesta
    repositorio = RepositorioPagos(sesion)
    cargo = await repositorio.cargo_visible(pago.cargo_id, principal)
    if cargo is None:
        return respuesta
    confirmado, comprometido = await repositorio.totales_cargo(cargo.id)
    total = cargo.total_acordado
    return respuesta.model_copy(
        update={
            "total_acordado": total,
            "total_confirmado": confirmado,
            "saldo_pendiente": total - confirmado if total is not None else None,
            "saldo_no_asignado": total - comprometido if total is not None else None,
        }
    )


@enrutador.get("/", response_model=PaginaPagos)
async def listar(
    principal: PuedeLeer,
    sesion: Sesion,
    limite: Annotated[int, Query(ge=1, le=100)] = 25,
    desplazamiento: Annotated[int, Query(ge=0)] = 0,
    estado: Annotated[EstadoPago | None, Query()] = None,
) -> PaginaPagos:
    filas, total = await RepositorioPagos(sesion).listar_detallado(
        principal, limite, desplazamiento, estado
    )
    return PaginaPagos(
        elementos=[
            RespuestaPago.model_validate(pago).model_copy(
                update={
                    "paciente": paciente,
                    "cita_inicio": inicio,
                    "total_acordado": total_acordado,
                    "total_confirmado": confirmado,
                    "saldo_pendiente": (
                        total_acordado - confirmado if total_acordado is not None else None
                    ),
                    "saldo_no_asignado": (
                        total_acordado - comprometido if total_acordado is not None else None
                    ),
                }
            )
            for pago, paciente, inicio, total_acordado, confirmado, comprometido in filas
        ],
        total=total,
    )


@enrutador.get("/cargos/", response_model=PaginaCargosPago)
async def listar_cargos(
    principal: PuedeLeer,
    sesion: Sesion,
    limite: Annotated[int, Query(ge=1, le=100)] = 25,
    desplazamiento: Annotated[int, Query(ge=0)] = 0,
    cita_id: Annotated[uuid.UUID | None, Query()] = None,
    vencidos: Annotated[bool, Query()] = False,
) -> PaginaCargosPago:
    filas, total = await RepositorioPagos(sesion).listar_cargos(
        principal, limite, desplazamiento, cita_id, vencidos
    )
    return PaginaCargosPago(elementos=[_salida_cargo(fila) for fila in filas], total=total)


@enrutador.get(
    "/resumen.csv",
    response_class=Response,
    summary="Exportar resumen diario de pagos sin datos de pacientes",
    responses={
        403: {"description": "Se requieren permisos de pagos y exportación"},
        422: {"description": "El periodo solicitado no es válido"},
    },
)
async def exportar_resumen_pagos(
    peticion: Request,
    principal: PuedeLeer,
    _permiso_reporte: PuedeExportarReportes,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
    desde: Annotated[date, Query(description="Primer día local incluido.")],
    hasta: Annotated[date, Query(description="Último día local exclusivo.")],
    sede_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Response:
    """Exporta conteos e importes agrupados; nunca exporta filas de pacientes."""
    dias = (hasta - desde).days
    if dias < 1 or dias > DIAS_MAXIMOS_REPORTE:
        raise DatosInvalidos("El periodo debe ser de 1 a 366 días; hasta es exclusivo.")

    filas = await RepositorioPagos(sesion).resumen_diario_exportable(
        principal, desde, hasta, sede_id
    )
    salida = io.StringIO(newline="")
    escritor = csv.writer(salida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(
        (
            "Fecha local",
            "Estado",
            "Método",
            "Moneda",
            "Transacciones",
            "Importe registrado",
            "Importe confirmado",
        )
    )
    escritor.writerows(
        (
            fecha.isoformat(),
            estado,
            metodo,
            moneda,
            cantidad,
            f"{registrado:.2f}",
            f"{confirmado:.2f}",
        )
        for fecha, estado, metodo, moneda, cantidad, registrado, confirmado in filas
    )

    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.REPORTE_EXPORTADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="resumen_pagos",
                ip=peticion.client.host if peticion.client else None,
                correlacion_id=getattr(peticion.state, "correlacion_id", None),
                tipo_informe="pagos_diarios_estado_metodo",
                desde=desde.isoformat(),
                hasta=hasta.isoformat(),
                sede_id=sede_id,
                filas=len(filas),
            )
        ]
    )
    await sesion.commit()

    return Response(
        content=("\ufeff" + salida.getvalue()).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="resumen-pagos-{desde}-{hasta}.csv"'
        },
    )


@enrutador.post("/cargos/", response_model=RespuestaCargoPago, status_code=201)
async def crear_cargo(
    datos: DatosCargoPago,
    principal: PuedeRegistrar,
    sesion: Sesion,
    reloj: RelojActual,
    clave: Clave,
) -> RespuestaCargoPago:
    cargo = await ServicioPagos(sesion, reloj).crear_cargo(datos, principal, clave)
    filas, _total = await RepositorioPagos(sesion).listar_cargos(principal, 1, 0, cargo.cita_id)
    await sesion.commit()
    return _salida_cargo(filas[0])


@enrutador.patch("/cargos/{cargo_id}/total", response_model=RespuestaCargoPago)
async def conciliar_cargo(
    cargo_id: uuid.UUID,
    datos: TotalCargoPago,
    principal: PuedeValidar,
    sesion: Sesion,
    reloj: RelojActual,
) -> RespuestaCargoPago:
    cargo = await ServicioPagos(sesion, reloj).conciliar_cargo(
        cargo_id, datos.total_acordado, principal, datos.fecha_vencimiento
    )
    filas, _total = await RepositorioPagos(sesion).listar_cargos(principal, 1, 0, cargo.cita_id)
    await sesion.commit()
    return _salida_cargo(filas[0])


@enrutador.patch("/cargos/{cargo_id}/vencimiento", response_model=RespuestaCargoPago)
async def fijar_vencimiento_cargo(
    cargo_id: uuid.UUID,
    datos: FechaVencimientoCargo,
    principal: PuedeValidar,
    sesion: Sesion,
    reloj: RelojActual,
) -> RespuestaCargoPago:
    cargo = await ServicioPagos(sesion, reloj).fijar_vencimiento(
        cargo_id, datos.fecha_vencimiento, principal
    )
    filas, _total = await RepositorioPagos(sesion).listar_cargos(principal, 1, 0, cargo.cita_id)
    await sesion.commit()
    return _salida_cargo(filas[0])


@enrutador.get("/{pago_id}/historial", response_model=HistorialPago)
async def historial(
    pago_id: uuid.UUID,
    principal: PuedeLeer,
    sesion: Sesion,
) -> HistorialPago:
    repositorio = RepositorioPagos(sesion)
    if await repositorio.visible(pago_id, principal) is None:
        raise RecursoNoEncontrado("El pago solicitado no existe.")
    return HistorialPago(elementos=await repositorio.historial(pago_id))


@enrutador.get("/{pago_id}/comprobantes", response_model=ListaComprobantesPago)
async def listar_comprobantes(
    pago_id: uuid.UUID,
    principal: PuedeLeer,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
) -> ListaComprobantesPago:
    repositorio = RepositorioPagos(sesion)
    if await repositorio.visible(pago_id, principal) is None:
        raise RecursoNoEncontrado("El pago solicitado no existe.")
    filas = await repositorio.comprobantes(pago_id)
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.PAGO_COMPROBANTES_LISTADOS,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="pago",
                entidad_id=pago_id,
                comprobantes_devueltos=len(filas),
            )
        ]
    )
    await sesion.commit()
    return ListaComprobantesPago(elementos=[_salida_comprobante(fila) for fila in filas])


@enrutador.post("/{pago_id}/comprobantes", response_model=ComprobantePago, status_code=201)
async def subir_comprobante(
    pago_id: uuid.UUID,
    principal: PuedeRegistrar,
    sesion: Sesion,
    reloj: RelojActual,
    almacen: AlmacenActual,
    cifrador: CifradorActual,
    configuracion: ConfiguracionActual,
    auditor: Auditor,
    archivo: Annotated[UploadFile, File()],
) -> ComprobantePago:
    try:
        contenido = await archivo.read(configuracion.max_tamano_archivo_bytes + 1)
    finally:
        await archivo.close()
    if len(contenido) > configuracion.max_tamano_archivo_bytes:
        raise ArchivoDemasiadoGrande("El comprobante supera el límite configurado.")
    servicio = ServicioPagos(sesion, reloj, almacen, cifrador, configuracion)
    comprobante, entradas = await servicio.subir_comprobante(pago_id, contenido, principal)
    await auditor.registrar(list(entradas))
    await sesion.commit()
    return _salida_comprobante(comprobante)


@enrutador.get("/comprobantes/{comprobante_id}/contenido", response_class=Response)
async def descargar_comprobante(
    comprobante_id: uuid.UUID,
    principal: PuedeLeer,
    sesion: Sesion,
    reloj: RelojActual,
    almacen: AlmacenActual,
    cifrador: CifradorActual,
    configuracion: ConfiguracionActual,
    auditor: Auditor,
) -> Response:
    servicio = ServicioPagos(sesion, reloj, almacen, cifrador, configuracion)
    descarga, entradas = await servicio.descargar_comprobante(comprobante_id, principal)
    await auditor.registrar(list(entradas))
    await sesion.commit()
    extension = {
        "application/pdf": "pdf",
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }[descarga.comprobante.tipo_mime]
    return Response(
        content=descarga.datos,
        media_type=descarga.comprobante.tipo_mime,
        headers={
            "Content-Disposition": f'attachment; filename="comprobante-{descarga.comprobante.id}.{extension}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@enrutador.post("/", response_model=RespuestaPago, status_code=201)
async def registrar(
    datos: DatosPago,
    principal: PuedeRegistrar,
    sesion: Sesion,
    reloj: RelojActual,
    clave: Clave,
) -> RespuestaPago:
    pago = await ServicioPagos(sesion, reloj).registrar(datos, principal, clave)
    respuesta = await _salida_pago(pago, principal, sesion)
    await sesion.commit()
    return respuesta


@enrutador.post("/{pago_id}/estado", response_model=RespuestaPago)
async def cambiar(
    pago_id: uuid.UUID,
    datos: CambioPago,
    principal: PuedeValidar,
    sesion: Sesion,
    reloj: RelojActual,
    clave: Clave,
) -> RespuestaPago:
    pago = await ServicioPagos(sesion, reloj).cambiar(pago_id, datos, principal, clave)
    respuesta = await _salida_pago(pago, principal, sesion)
    await sesion.commit()
    return respuesta
