"""Listado de pagos: se reconoce cada pago por paciente y fecha, y se filtra por estado."""

from __future__ import annotations

import struct
import zlib
from datetime import date, timedelta

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita
from app.modulos.auditoria.modelos import Auditoria
from app.modulos.organizacion.modelos import Clinica, Sede, Servicio
from app.modulos.pacientes.modelos import Paciente
from app.modulos.pagos.modelos import CargoPago, Pago, PagoComprobante, PagoHistorial
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.auditoria import AccionAuditada
from pruebas.api.conftest import cabecera_bearer, conceder_permisos
from pruebas.conftest import INSTANTE_REFERENCIA

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


def _trozo_png(tipo: bytes, contenido: bytes) -> bytes:
    cuerpo = tipo + contenido
    return struct.pack(">I", len(contenido)) + cuerpo + struct.pack(">I", zlib.crc32(cuerpo))


def _png_comprobante() -> bytes:
    cabecera = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    pixeles = zlib.compress(b"\x00\x21\x43\x65\xff")
    return (
        b"\x89PNG\r\n\x1a\n"
        + _trozo_png(b"IHDR", cabecera)
        + _trozo_png(b"IDAT", pixeles)
        + _trozo_png(b"IEND", b"")
    )


async def test_listado_con_paciente_fecha_y_filtro(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    servicio: Servicio,
    profesional: Profesional,
    paciente: Paciente,
) -> None:
    inicio = INSTANTE_REFERENCIA + timedelta(days=1)
    cita = Cita(
        clinica_id=clinica.id,
        sede_id=sede.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        servicio_id=servicio.id,
        inicio=inicio,
        duracion_minutos=30,
        minutos_preparacion=0,
        estado="CONFIRMED",
        origen="PANEL",
        confirmada_en=INSTANTE_REFERENCIA,
    )
    sesion.add(cita)
    await sesion.flush()
    await conceder_permisos(
        sesion, usuario, clinica, "pago.leer", "pago.registrar", sedes=(sede.id,)
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    creado = await cliente.post(
        f"{api}/pagos/",
        json={
            "cita_id": str(cita.id),
            "importe": "20.00",
            "total_acordado": "20.00",
            "metodo": "EFECTIVO",
        },
        headers={**cabeceras, "Idempotency-Key": "listado-pagos-0001"},
    )
    assert creado.status_code == 201, creado.text

    pendientes = await cliente.get(f"{api}/pagos/", params={"estado": "PENDING"}, headers=cabeceras)
    assert pendientes.status_code == 200
    (pago,) = pendientes.json()["elementos"]
    assert pago["paciente"] == f"{paciente.nombre} {paciente.apellido}"
    assert pago["cita_inicio"].startswith(inicio.isoformat()[:16])
    assert pago["total_acordado"] == "20.00"
    assert pago["saldo_pendiente"] == "20.00"
    assert pago["saldo_no_asignado"] == "0.00"

    confirmados = await cliente.get(
        f"{api}/pagos/", params={"estado": "CONFIRMED"}, headers=cabeceras
    )
    assert confirmados.json() == {"elementos": [], "total": 0}
    invalido = await cliente.get(f"{api}/pagos/", params={"estado": "OTRO"}, headers=cabeceras)
    assert invalido.status_code == 422


async def test_exportar_resumen_financiero_local_agrega_y_respeta_ambito(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    otra_sede: Sede,
    servicio: Servicio,
    profesional: Profesional,
    paciente: Paciente,
) -> None:
    instante = INSTANTE_REFERENCIA.replace(hour=4, minute=30)
    citas = [
        Cita(
            clinica_id=clinica.id,
            sede_id=sede_id,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            servicio_id=servicio.id,
            inicio=instante + timedelta(minutes=desplazamiento_minutos),
            duracion_minutos=30,
            minutos_preparacion=0,
            estado="CONFIRMED",
            origen="PANEL",
            confirmada_en=INSTANTE_REFERENCIA,
        )
        for sede_id, desplazamiento_minutos in (
            (sede.id, 0),
            (sede.id, -30),
            (otra_sede.id, -60),
        )
    ]
    sesion.add_all(citas)
    await sesion.flush()
    sesion.add_all(
        [
            Pago(
                clinica_id=clinica.id,
                cita_id=citas[0].id,
                importe="20.00",
                moneda="USD",
                metodo="EFECTIVO",
                estado="CONFIRMED",
                creado_en=instante,
            ),
            Pago(
                clinica_id=clinica.id,
                cita_id=citas[1].id,
                importe="5.00",
                moneda="USD",
                metodo="TRANSFERENCIA",
                estado="PENDING",
                creado_en=instante,
            ),
            Pago(
                clinica_id=clinica.id,
                cita_id=citas[2].id,
                importe="900.00",
                moneda="USD",
                metodo="EFECTIVO",
                estado="CONFIRMED",
                creado_en=instante,
            ),
        ]
    )
    await sesion.flush()
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "pago.leer",
        "reporte.exportar",
        sedes=(sede.id,),
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    fecha_local = (instante + timedelta(hours=-5)).date()

    respuesta = await cliente.get(
        f"{api}/pagos/resumen.csv",
        params={
            "desde": fecha_local.isoformat(),
            "hasta": (fecha_local + timedelta(days=1)).isoformat(),
        },
        headers=cabeceras,
    )

    assert respuesta.status_code == 200, respuesta.text
    texto = respuesta.content.decode("utf-8-sig")
    assert (
        "Fecha local;Estado;Método;Moneda;Transacciones;Importe registrado;Importe confirmado"
        in texto
    )
    assert f"{fecha_local};CONFIRMED;EFECTIVO;USD;1;20.00;20.00" in texto
    assert f"{fecha_local};PENDING;TRANSFERENCIA;USD;1;5.00;0" in texto
    assert "900.00" not in texto
    assert paciente.nombre not in texto
    assert "resumen-pagos-" in respuesta.headers["content-disposition"]
    evento = await sesion.scalar(
        sa.select(Auditoria).where(
            Auditoria.accion == AccionAuditada.REPORTE_EXPORTADO,
            Auditoria.entidad_tipo == "resumen_pagos",
        )
    )
    assert evento is not None
    assert evento.metadatos is not None
    assert evento.metadatos["tipo_informe"] == "pagos_diarios_estado_metodo"

    hasta_invalido = await cliente.get(
        f"{api}/pagos/resumen.csv",
        params={"desde": fecha_local.isoformat(), "hasta": fecha_local.isoformat()},
        headers=cabeceras,
    )
    assert hasta_invalido.status_code == 422


async def test_historial_registra_transiciones_comentarios_y_es_inmutable(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    otra_sede: Sede,
    servicio: Servicio,
    profesional: Profesional,
    paciente: Paciente,
) -> None:
    inicio = INSTANTE_REFERENCIA + timedelta(days=1)
    cita = Cita(
        clinica_id=clinica.id,
        sede_id=sede.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        servicio_id=servicio.id,
        inicio=inicio,
        duracion_minutos=30,
        minutos_preparacion=0,
        estado="CONFIRMED",
        origen="PANEL",
        confirmada_en=INSTANTE_REFERENCIA,
    )
    sesion.add(cita)
    await sesion.flush()
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "pago.leer",
        "pago.registrar",
        "pago.validar",
        sedes=(sede.id,),
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    creado = await cliente.post(
        f"{api}/pagos/",
        json={
            "cita_id": str(cita.id),
            "importe": "20.00",
            "total_acordado": "20.00",
            "metodo": "TRANSFERENCIA",
        },
        headers={**cabeceras, "Idempotency-Key": "historial-pago-0001"},
    )
    assert creado.status_code == 201, creado.text
    pago_id = creado.json()["id"]

    recibido = await cliente.post(
        f"{api}/pagos/{pago_id}/estado",
        json={"estado": "PROOF_RECEIVED", "comentario": "Se recibió el comprobante"},
        headers={**cabeceras, "Idempotency-Key": "historial-pago-recibido"},
    )
    assert recibido.status_code == 200, recibido.text
    cambio = await cliente.post(
        f"{api}/pagos/{pago_id}/estado",
        json={"estado": "UNDER_REVIEW", "comentario": "Comprobante contrastado"},
        headers={**cabeceras, "Idempotency-Key": "historial-pago-rev-1"},
    )
    assert cambio.status_code == 200, cambio.text
    repetido = await cliente.post(
        f"{api}/pagos/{pago_id}/estado",
        json={"estado": "UNDER_REVIEW", "comentario": "Comprobante contrastado"},
        headers={**cabeceras, "Idempotency-Key": "historial-pago-rev-1"},
    )
    assert repetido.status_code == 200

    historial = await cliente.get(f"{api}/pagos/{pago_id}/historial", headers=cabeceras)
    assert historial.status_code == 200, historial.text
    eventos = historial.json()["elementos"]
    assert [(e["estado_anterior"], e["estado_nuevo"]) for e in eventos] == [
        (None, "PENDING"),
        ("PENDING", "PROOF_RECEIVED"),
        ("PROOF_RECEIVED", "UNDER_REVIEW"),
    ]
    assert [e["secuencia"] for e in eventos] == [1, 2, 3]
    assert eventos[2]["comentario"] == "Comprobante contrastado"
    assert all(e["actor_id"] == str(usuario.id) for e in eventos)

    evento_id = sa.select(PagoHistorial.id).where(PagoHistorial.pago_id == pago_id).limit(1)
    with pytest.raises(DBAPIError):
        async with sesion.begin_nested():
            await sesion.execute(
                sa.update(PagoHistorial)
                .where(PagoHistorial.id.in_(evento_id))
                .values(estado_nuevo="REJECTED")
            )
    with pytest.raises(DBAPIError):
        async with sesion.begin_nested():
            await sesion.execute(sa.delete(PagoHistorial).where(PagoHistorial.id.in_(evento_id)))

    cita.sede_id = otra_sede.id
    await sesion.flush()
    fuera_de_ambito = await cliente.get(f"{api}/pagos/{pago_id}/historial", headers=cabeceras)
    assert fuera_de_ambito.status_code == 404


async def test_comprobante_se_valida_cifra_audita_y_se_descarga_dentro_del_ambito(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    otra_sede: Sede,
    servicio: Servicio,
    profesional: Profesional,
    paciente: Paciente,
) -> None:
    cita = Cita(
        clinica_id=clinica.id,
        sede_id=sede.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        servicio_id=servicio.id,
        inicio=INSTANTE_REFERENCIA + timedelta(days=1),
        duracion_minutos=30,
        minutos_preparacion=0,
        estado="CONFIRMED",
        origen="PANEL",
        confirmada_en=INSTANTE_REFERENCIA,
    )
    sesion.add(cita)
    await sesion.flush()
    await conceder_permisos(
        sesion, usuario, clinica, "pago.leer", "pago.registrar", sedes=(sede.id,)
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    alta = await cliente.post(
        f"{api}/pagos/",
        json={
            "cita_id": str(cita.id),
            "importe": "25.00",
            "total_acordado": "25.00",
            "metodo": "TRANSFERENCIA",
        },
        headers={**cabeceras, "Idempotency-Key": "pago-comprobante-alta"},
    )
    assert alta.status_code == 201, alta.text
    pago_id = alta.json()["id"]

    carga = await cliente.post(
        f"{api}/pagos/{pago_id}/comprobantes",
        headers=cabeceras,
        files={"archivo": ("transferencia.png", _png_comprobante(), "image/png")},
    )
    assert carga.status_code == 201, carga.text
    comprobante = carga.json()
    assert comprobante["tipo_mime"] == "image/png"
    assert comprobante["tamano_bytes"] == len(_png_comprobante())
    assert comprobante["antivirus"] == "NO_DISPONIBLE"
    assert comprobante["cargado_por"] == str(usuario.id)

    pagos = (await cliente.get(f"{api}/pagos/", headers=cabeceras)).json()["elementos"]
    assert pagos[0]["estado"] == "PROOF_RECEIVED"
    listado = await cliente.get(f"{api}/pagos/{pago_id}/comprobantes", headers=cabeceras)
    assert listado.status_code == 200
    assert listado.json()["elementos"][0]["id"] == comprobante["id"]

    descarga = await cliente.get(comprobante["url_contenido"], headers=cabeceras)
    assert descarga.status_code == 200
    assert descarga.headers["content-disposition"].startswith("attachment;")
    assert descarga.headers["cache-control"] == "private, no-store"
    assert descarga.content == _png_comprobante()

    eventos = (await cliente.get(f"{api}/pagos/{pago_id}/historial", headers=cabeceras)).json()[
        "elementos"
    ]
    assert [(e["estado_anterior"], e["estado_nuevo"]) for e in eventos] == [
        (None, "PENDING"),
        ("PENDING", "PROOF_RECEIVED"),
    ]
    acciones = set((await sesion.execute(sa.select(Auditoria.accion))).scalars())
    assert AccionAuditada.PAGO_COMPROBANTE_CARGADO.value in acciones
    assert AccionAuditada.PAGO_COMPROBANTES_LISTADOS.value in acciones
    assert AccionAuditada.PAGO_COMPROBANTE_CONSULTADO.value in acciones

    with pytest.raises(DBAPIError):
        async with sesion.begin_nested():
            await sesion.execute(
                sa.update(PagoComprobante)
                .where(PagoComprobante.id == comprobante["id"])
                .values(antivirus="LIMPIO")
            )
    with pytest.raises(DBAPIError):
        async with sesion.begin_nested():
            await sesion.execute(
                sa.delete(PagoComprobante).where(PagoComprobante.id == comprobante["id"])
            )

    cita.sede_id = otra_sede.id
    await sesion.flush()
    fuera_de_ambito = await cliente.get(comprobante["url_contenido"], headers=cabeceras)
    assert fuera_de_ambito.status_code == 404
    listado_fuera_de_ambito = await cliente.get(
        f"{api}/pagos/{pago_id}/comprobantes", headers=cabeceras
    )
    historial_fuera_de_ambito = await cliente.get(
        f"{api}/pagos/{pago_id}/historial", headers=cabeceras
    )
    assert listado_fuera_de_ambito.status_code == 404
    assert historial_fuera_de_ambito.status_code == 404


async def test_comprobante_rechaza_contenido_que_no_es_pdf_ni_imagen(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    servicio: Servicio,
    profesional: Profesional,
    paciente: Paciente,
) -> None:
    cita = Cita(
        clinica_id=clinica.id,
        sede_id=sede.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        servicio_id=servicio.id,
        inicio=INSTANTE_REFERENCIA + timedelta(days=1),
        duracion_minutos=30,
        minutos_preparacion=0,
        estado="CONFIRMED",
        origen="PANEL",
        confirmada_en=INSTANTE_REFERENCIA,
    )
    sesion.add(cita)
    await sesion.flush()
    await conceder_permisos(
        sesion, usuario, clinica, "pago.leer", "pago.registrar", sedes=(sede.id,)
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    pago = await cliente.post(
        f"{api}/pagos/",
        json={
            "cita_id": str(cita.id),
            "importe": "25.00",
            "total_acordado": "25.00",
            "metodo": "EFECTIVO",
        },
        headers={**cabeceras, "Idempotency-Key": "pago-comprobante-invalido"},
    )
    respuesta = await cliente.post(
        f"{api}/pagos/{pago.json()['id']}/comprobantes",
        headers=cabeceras,
        files={"archivo": ("falso.pdf", b"<script>alert(1)</script>", "application/pdf")},
    )
    assert respuesta.status_code == 415
    assert (await cliente.get(f"{api}/pagos/", headers=cabeceras)).json()["elementos"][0][
        "estado"
    ] == "PENDING"


async def test_cargo_admite_abonos_sin_superar_total_y_expone_saldos(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    servicio: Servicio,
    profesional: Profesional,
    paciente: Paciente,
) -> None:
    cita = Cita(
        clinica_id=clinica.id,
        sede_id=sede.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        servicio_id=servicio.id,
        inicio=INSTANTE_REFERENCIA + timedelta(days=2),
        duracion_minutos=30,
        minutos_preparacion=0,
        estado="CONFIRMED",
        origen="PANEL",
        confirmada_en=INSTANTE_REFERENCIA,
    )
    sesion.add(cita)
    await sesion.flush()
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "pago.leer",
        "pago.registrar",
        "pago.validar",
        sedes=(sede.id,),
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    total_omitido = await cliente.post(
        f"{api}/pagos/",
        json={"cita_id": str(cita.id), "importe": "20.00", "metodo": "EFECTIVO"},
        headers={**cabeceras, "Idempotency-Key": "cargo-abono-sin-total"},
    )
    assert total_omitido.status_code == 422
    alta_cargo = await cliente.post(
        f"{api}/pagos/cargos/",
        json={"cita_id": str(cita.id), "total_acordado": "100.00"},
        headers={**cabeceras, "Idempotency-Key": "cargo-abonos-alta-001"},
    )
    assert alta_cargo.status_code == 201, alta_cargo.text
    assert alta_cargo.json()["saldo_pendiente"] == "100.00"
    assert alta_cargo.json()["saldo_no_asignado"] == "100.00"

    abonos = []
    for indice, importe in enumerate(("30.00", "20.00"), start=1):
        respuesta = await cliente.post(
            f"{api}/pagos/",
            json={
                "cita_id": str(cita.id),
                "importe": importe,
                "total_acordado": "100.00",
                "metodo": "EFECTIVO",
            },
            headers={**cabeceras, "Idempotency-Key": f"cargo-abono-{indice:03d}"},
        )
        assert respuesta.status_code == 201, respuesta.text
        abonos.append(respuesta.json())

    excedido = await cliente.post(
        f"{api}/pagos/",
        json={
            "cita_id": str(cita.id),
            "importe": "51.00",
            "total_acordado": "100.00",
            "metodo": "EFECTIVO",
        },
        headers={**cabeceras, "Idempotency-Key": "cargo-abono-excede"},
    )
    assert excedido.status_code == 409

    confirmar = await cliente.post(
        f"{api}/pagos/{abonos[0]['id']}/estado",
        json={"estado": "CONFIRMED", "comentario": "Efectivo recibido"},
        headers={**cabeceras, "Idempotency-Key": "cargo-abono-confirmar"},
    )
    assert confirmar.status_code == 200, confirmar.text
    cargos = await cliente.get(f"{api}/pagos/cargos/", headers=cabeceras)
    assert cargos.status_code == 200, cargos.text
    (cargo,) = cargos.json()["elementos"]
    assert cargo["total_confirmado"] == "30.00"
    assert cargo["total_comprometido"] == "50.00"
    assert cargo["saldo_pendiente"] == "70.00"
    assert cargo["saldo_no_asignado"] == "50.00"

    rechazar = await cliente.post(
        f"{api}/pagos/{abonos[1]['id']}/estado",
        json={"estado": "REJECTED", "comentario": "Abono duplicado"},
        headers={**cabeceras, "Idempotency-Key": "cargo-abono-rechazado"},
    )
    assert rechazar.status_code == 200, rechazar.text
    actualizado = await cliente.get(f"{api}/pagos/cargos/", headers=cabeceras)
    (cargo_actualizado,) = actualizado.json()["elementos"]
    assert cargo_actualizado["total_comprometido"] == "30.00"
    assert cargo_actualizado["saldo_no_asignado"] == "70.00"

    abono_siguiente = await cliente.post(
        f"{api}/pagos/",
        json={
            "cita_id": str(cita.id),
            "importe": "70.00",
            "total_acordado": "100.00",
            "metodo": "EFECTIVO",
        },
        headers={**cabeceras, "Idempotency-Key": "cargo-abono-liberado"},
    )
    assert abono_siguiente.status_code == 201, abono_siguiente.text
    reactivar = await cliente.post(
        f"{api}/pagos/{abonos[1]['id']}/estado",
        json={"estado": "UNDER_REVIEW", "comentario": "Intento de reactivación"},
        headers={**cabeceras, "Idempotency-Key": "cargo-abono-reactivado"},
    )
    assert reactivar.status_code == 409


async def test_cargo_no_se_expone_ni_concilia_fuera_de_la_sede_autorizada(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    otra_sede: Sede,
    servicio: Servicio,
    profesional: Profesional,
    paciente: Paciente,
) -> None:
    cita = Cita(
        clinica_id=clinica.id,
        sede_id=sede.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        servicio_id=servicio.id,
        inicio=INSTANTE_REFERENCIA + timedelta(days=3),
        duracion_minutos=30,
        minutos_preparacion=0,
        estado="CONFIRMED",
        origen="PANEL",
        confirmada_en=INSTANTE_REFERENCIA,
    )
    sesion.add(cita)
    await sesion.flush()
    await conceder_permisos(
        sesion, usuario, clinica, "pago.leer", "pago.registrar", "pago.validar", sedes=(sede.id,)
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    alta = await cliente.post(
        f"{api}/pagos/cargos/",
        json={"cita_id": str(cita.id), "total_acordado": "80.00"},
        headers={**cabeceras, "Idempotency-Key": "cargo-sede-alta-001"},
    )
    assert alta.status_code == 201, alta.text
    cita.sede_id = otra_sede.id
    await sesion.flush()

    listado = await cliente.get(
        f"{api}/pagos/cargos/", params={"cita_id": str(cita.id)}, headers=cabeceras
    )
    assert listado.status_code == 200
    assert listado.json() == {"elementos": [], "total": 0}
    conciliacion = await cliente.patch(
        f"{api}/pagos/cargos/{alta.json()['id']}/total",
        json={"total_acordado": "80.00"},
        headers=cabeceras,
    )
    assert conciliacion.status_code == 404


async def test_total_historico_se_concilia_una_vez_y_se_puede_repetir(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    servicio: Servicio,
    profesional: Profesional,
    paciente: Paciente,
) -> None:
    cita = Cita(
        clinica_id=clinica.id,
        sede_id=sede.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        servicio_id=servicio.id,
        inicio=INSTANTE_REFERENCIA + timedelta(days=2),
        duracion_minutos=30,
        minutos_preparacion=0,
        estado="CONFIRMED",
        origen="PANEL",
        confirmada_en=INSTANTE_REFERENCIA,
    )
    sesion.add(cita)
    await sesion.flush()
    await conceder_permisos(
        sesion, usuario, clinica, "pago.leer", "pago.registrar", "pago.validar", sedes=(sede.id,)
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    historico = CargoPago(
        clinica_id=clinica.id,
        cita_id=cita.id,
        total_acordado=None,
        moneda="USD",
        origen="HISTORICO_SIN_TOTAL",
    )
    sesion.add(historico)
    await sesion.flush()
    sesion.add(
        Pago(
            clinica_id=clinica.id,
            cita_id=cita.id,
            cargo_id=historico.id,
            importe="20.00",
            moneda="USD",
            metodo="EFECTIVO",
            estado="CONFIRMED",
            creado_por=usuario.id,
        )
    )
    await sesion.flush()

    listado = await cliente.get(f"{api}/pagos/cargos/", headers=cabeceras)
    assert listado.status_code == 200, listado.text
    (fila,) = listado.json()["elementos"]
    assert fila["total_acordado"] is None
    assert fila["saldo_pendiente"] is None

    conciliado = await cliente.patch(
        f"{api}/pagos/cargos/{historico.id}/total",
        json={"total_acordado": "60.00", "fecha_vencimiento": "2026-05-01"},
        headers=cabeceras,
    )
    assert conciliado.status_code == 200, conciliado.text
    assert conciliado.json()["saldo_pendiente"] == "40.00"
    assert conciliado.json()["fecha_vencimiento"] == "2026-05-01"
    repetido = await cliente.patch(
        f"{api}/pagos/cargos/{historico.id}/total",
        json={"total_acordado": "60.00"},
        headers=cabeceras,
    )
    assert repetido.status_code == 200, repetido.text
    distinto = await cliente.patch(
        f"{api}/pagos/cargos/{historico.id}/total",
        json={"total_acordado": "70.00"},
        headers=cabeceras,
    )
    assert distinto.status_code == 409
    acciones = list((await sesion.execute(sa.select(Auditoria.accion))).scalars())
    assert acciones.count(AccionAuditada.CARGO_PAGO_CONCILIADO.value) == 1


async def test_vencimientos_se_fijan_una_vez_y_filtran_saldo_realmente_pendiente(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    servicio: Servicio,
    profesional: Profesional,
    paciente: Paciente,
) -> None:
    cita = Cita(
        clinica_id=clinica.id,
        sede_id=sede.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        servicio_id=servicio.id,
        inicio=INSTANTE_REFERENCIA + timedelta(days=2),
        duracion_minutos=30,
        minutos_preparacion=0,
        estado="CONFIRMED",
        origen="PANEL",
        confirmada_en=INSTANTE_REFERENCIA,
    )
    sesion.add(cita)
    await sesion.flush()
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "pago.leer",
        "pago.registrar",
        "pago.validar",
        sedes=(sede.id,),
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    alta = await cliente.post(
        f"{api}/pagos/cargos/",
        json={"cita_id": str(cita.id), "total_acordado": "100.00"},
        headers={**cabeceras, "Idempotency-Key": "cargo-vencimiento-alta"},
    )
    assert alta.status_code == 201, alta.text
    cargo_id = alta.json()["id"]
    fecha_pasada = (date.today() - timedelta(days=2)).isoformat()

    fijado = await cliente.patch(
        f"{api}/pagos/cargos/{cargo_id}/vencimiento",
        json={"fecha_vencimiento": fecha_pasada},
        headers=cabeceras,
    )
    assert fijado.status_code == 200, fijado.text
    assert fijado.json()["fecha_vencimiento"] == fecha_pasada
    assert fijado.json()["vencido"] is True

    repetido = await cliente.patch(
        f"{api}/pagos/cargos/{cargo_id}/vencimiento",
        json={"fecha_vencimiento": fecha_pasada},
        headers=cabeceras,
    )
    assert repetido.status_code == 200
    cambiado = await cliente.patch(
        f"{api}/pagos/cargos/{cargo_id}/vencimiento",
        json={"fecha_vencimiento": date.today().isoformat()},
        headers=cabeceras,
    )
    assert cambiado.status_code == 409

    vencidos = await cliente.get(
        f"{api}/pagos/cargos/", params={"vencidos": True}, headers=cabeceras
    )
    assert vencidos.status_code == 200, vencidos.text
    assert vencidos.json()["total"] == 1
    assert vencidos.json()["elementos"][0]["id"] == cargo_id

    pago = await cliente.post(
        f"{api}/pagos/",
        json={
            "cita_id": str(cita.id),
            "importe": "100.00",
            "total_acordado": "100.00",
            "metodo": "EFECTIVO",
        },
        headers={**cabeceras, "Idempotency-Key": "cargo-vencimiento-pago"},
    )
    assert pago.status_code == 201, pago.text
    confirmado = await cliente.post(
        f"{api}/pagos/{pago.json()['id']}/estado",
        json={"estado": "CONFIRMED", "comentario": "Pago recibido"},
        headers={**cabeceras, "Idempotency-Key": "cargo-vencimiento-confirmar"},
    )
    assert confirmado.status_code == 200, confirmado.text
    sin_vencidos = await cliente.get(
        f"{api}/pagos/cargos/", params={"vencidos": True}, headers=cabeceras
    )
    assert sin_vencidos.status_code == 200
    assert sin_vencidos.json() == {"elementos": [], "total": 0}

    acciones = list((await sesion.execute(sa.select(Auditoria.accion))).scalars())
    assert acciones.count(AccionAuditada.CARGO_PAGO_VENCIMIENTO_FIJADO.value) == 1
