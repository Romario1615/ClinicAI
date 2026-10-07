"""Libro de gastos y flujo de caja.

* Sin sesion, 401; sin permiso, 403 auditado.
* El alta es idempotente: la misma clave con el mismo cuerpo devuelve el
  mismo gasto; con otro cuerpo, 409.
* El ambito manda: un gasto de otra sede o de toda la clinica no se ve ni se
  anula sin el ambito correspondiente (404, nunca 403).
* Un gasto no se edita ni se borra: se anula con motivo, una sola vez. La
  base de datos lo impide tambien frente a SQL directo.
* El flujo resta los gastos vigentes de los pagos confirmados del periodo.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita
from app.modulos.auditoria.modelos import Auditoria
from app.modulos.gastos.modelos import Gasto
from app.modulos.organizacion.modelos import Clinica, Sede, Servicio
from app.modulos.pacientes.modelos import Paciente
from app.modulos.pagos.modelos import Pago
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.auditoria import AccionAuditada
from pruebas.api.conftest import cabecera_bearer, conceder_permisos
from pruebas.conftest import INSTANTE_REFERENCIA

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]

# 09:00 en Guayaquil: el dia local de la prueba.
HOY = date(2026, 4, 15)


def _gasto(sede_id: uuid.UUID | None, **cambios: object) -> dict[str, object]:
    cuerpo: dict[str, object] = {
        "sede_id": str(sede_id) if sede_id else None,
        "fecha": HOY.isoformat(),
        "categoria": "INSUMOS",
        "descripcion": "Guantes de nitrilo, caja sintética",
        "proveedor": "Proveedor ficticio",
        "importe": "35.50",
        "metodo": "TRANSFERENCIA",
        "referencia": "FAC-0001",
    }
    cuerpo.update(cambios)
    return cuerpo


def _clave() -> dict[str, str]:
    return {"Idempotency-Key": f"gasto-{uuid.uuid4().hex}"}


async def test_sin_sesion_y_sin_permiso(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
) -> None:
    assert (await cliente.get(f"{api}/gastos")).status_code == 401

    await conceder_permisos(sesion, usuario, clinica, "agenda.leer", sedes=(sede.id,))
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    assert (await cliente.get(f"{api}/gastos", headers=cabeceras)).status_code == 403
    respuesta = await cliente.post(
        f"{api}/gastos", headers={**cabeceras, **_clave()}, json=_gasto(sede.id)
    )
    assert respuesta.status_code == 403
    denegaciones = await sesion.scalar(
        sa.select(sa.func.count())
        .select_from(Auditoria)
        .where(Auditoria.actor_id == usuario.id, Auditoria.resultado == "DENEGADO")
    )
    assert denegaciones >= 2


async def test_alta_idempotente_auditada_y_visible_en_el_libro(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
) -> None:
    await conceder_permisos(
        sesion, usuario, clinica, "gasto.leer", "gasto.registrar", sedes=(sede.id,)
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    clave = _clave()

    primera = await cliente.post(
        f"{api}/gastos", headers={**cabeceras, **clave}, json=_gasto(sede.id)
    )
    repetida = await cliente.post(
        f"{api}/gastos", headers={**cabeceras, **clave}, json=_gasto(sede.id)
    )
    distinta = await cliente.post(
        f"{api}/gastos", headers={**cabeceras, **clave}, json=_gasto(sede.id, importe="99.00")
    )

    assert primera.status_code == 201, primera.text
    assert repetida.status_code == 201
    assert repetida.json()["id"] == primera.json()["id"]
    assert distinta.status_code == 409
    cuerpo = primera.json()
    assert cuerpo["estado"] == "REGISTRADO"
    assert cuerpo["descripcion"] == "Guantes de nitrilo, caja sintética"
    assert Decimal(cuerpo["importe"]) == Decimal("35.50")
    assert "clinica_id" not in cuerpo

    libro = await cliente.get(f"{api}/gastos", headers=cabeceras)
    assert libro.status_code == 200
    assert libro.json()["total"] == 1
    assert Decimal(libro.json()["importe_total"]) == Decimal("35.50")

    auditadas = await sesion.scalar(
        sa.select(sa.func.count())
        .select_from(Auditoria)
        .where(
            Auditoria.accion == AccionAuditada.GASTO_REGISTRADO.value,
            Auditoria.entidad_id == uuid.UUID(cuerpo["id"]),
        )
    )
    assert auditadas == 1


@pytest.mark.parametrize(
    ("cambios", "estado"),
    [
        ({"fecha": (HOY + timedelta(days=1)).isoformat()}, 422),
        ({"importe": "0"}, 422),
        ({"importe": "-4.00"}, 422),
        ({"categoria": "VIAJES_PERSONALES"}, 422),
        ({"descripcion": "  "}, 422),
        ({"clinica_id": str(uuid.uuid4())}, 422),
    ],
)
async def test_entrada_invalida(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    cambios: dict[str, object],
    estado: int,
) -> None:
    await conceder_permisos(
        sesion, usuario, clinica, "gasto.leer", "gasto.registrar", sedes=(sede.id,)
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    respuesta = await cliente.post(
        f"{api}/gastos", headers={**cabeceras, **_clave()}, json=_gasto(sede.id, **cambios)
    )

    assert respuesta.status_code == estado, respuesta.text


async def test_el_ambito_decide_que_se_registra_ve_y_anula(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    otra_sede: Sede,
    paciente_ajeno: Paciente,
) -> None:
    # Gastos ya existentes: de la otra sede y de toda la clinica.
    ajeno_sede = Gasto(
        clinica_id=clinica.id,
        sede_id=otra_sede.id,
        fecha=HOY,
        categoria="ARRIENDO",
        descripcion="Arriendo de la otra sede",
        importe=Decimal("800.00"),
        metodo="TRANSFERENCIA",
    )
    general = Gasto(
        clinica_id=clinica.id,
        sede_id=None,
        fecha=HOY,
        categoria="NOMINA",
        descripcion="Nómina común",
        importe=Decimal("2000.00"),
        metodo="TRANSFERENCIA",
    )
    otra_clinica = Gasto(
        clinica_id=paciente_ajeno.clinica_id,
        sede_id=None,
        fecha=HOY,
        categoria="OTROS",
        descripcion="Gasto de otra clínica",
        importe=Decimal("10.00"),
        metodo="EFECTIVO",
    )
    sesion.add_all([ajeno_sede, general, otra_clinica])
    await sesion.flush()
    await conceder_permisos(
        sesion, usuario, clinica, "gasto.leer", "gasto.registrar", sedes=(sede.id,)
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    # Con ambito de una sede no se ve la otra ni lo general.
    libro = await cliente.get(f"{api}/gastos", headers=cabeceras)
    assert libro.json()["total"] == 0

    # Un gasto de toda la clinica exige ambito de todas las sedes.
    general_nuevo = await cliente.post(
        f"{api}/gastos", headers={**cabeceras, **_clave()}, json=_gasto(None)
    )
    assert general_nuevo.status_code == 422
    # Una sede fuera de ambito, o inexistente, es 404.
    for sede_id in (otra_sede.id, uuid.uuid4()):
        fuera = await cliente.post(
            f"{api}/gastos", headers={**cabeceras, **_clave()}, json=_gasto(sede_id)
        )
        assert fuera.status_code == 404
    # Anular lo ajeno es indistinguible de anular lo inexistente.
    for gasto_id in (ajeno_sede.id, general.id, otra_clinica.id, uuid.uuid4()):
        anulacion = await cliente.post(
            f"{api}/gastos/{gasto_id}/anulacion",
            headers=cabeceras,
            json={"motivo": "Prueba de ámbito ajeno"},
        )
        assert anulacion.status_code == 404


async def test_anular_una_sola_vez_con_motivo_y_sin_borrar(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
) -> None:
    await conceder_permisos(
        sesion, usuario, clinica, "gasto.leer", "gasto.registrar", todas_las_sedes=True
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    alta = await cliente.post(f"{api}/gastos", headers={**cabeceras, **_clave()}, json=_gasto(None))
    assert alta.status_code == 201, alta.text
    gasto_id = alta.json()["id"]

    corto = await cliente.post(
        f"{api}/gastos/{gasto_id}/anulacion", headers=cabeceras, json={"motivo": "no"}
    )
    anulado = await cliente.post(
        f"{api}/gastos/{gasto_id}/anulacion",
        headers=cabeceras,
        json={"motivo": "Factura registrada dos veces"},
    )
    otra_vez = await cliente.post(
        f"{api}/gastos/{gasto_id}/anulacion",
        headers=cabeceras,
        json={"motivo": "Segundo intento de anulación"},
    )

    assert corto.status_code == 422
    assert anulado.status_code == 200, anulado.text
    assert anulado.json()["estado"] == "ANULADO"
    assert anulado.json()["motivo_anulacion"] == "Factura registrada dos veces"
    assert otra_vez.status_code == 409

    vigentes = await cliente.get(f"{api}/gastos", headers=cabeceras)
    todos = await cliente.get(f"{api}/gastos", headers=cabeceras, params={"incluir_anulados": True})
    assert vigentes.json()["total"] == 0
    assert todos.json()["total"] == 1
    # El total del filtro solo suma lo vigente.
    assert Decimal(todos.json()["importe_total"]) == Decimal(0)


async def test_la_base_de_datos_impide_editar_o_borrar_un_gasto(
    sesion: AsyncSession, clinica: Clinica, sede: Sede
) -> None:
    gasto = Gasto(
        clinica_id=clinica.id,
        sede_id=sede.id,
        fecha=HOY,
        categoria="INSUMOS",
        descripcion="Material sintético",
        importe=Decimal("12.00"),
        metodo="EFECTIVO",
    )
    sesion.add(gasto)
    await sesion.flush()

    for sentencia in (
        sa.update(Gasto).where(Gasto.id == gasto.id).values(importe=Decimal("1.00")),
        sa.delete(Gasto).where(Gasto.id == gasto.id),
        # Anular a medias (sin motivo) tampoco: lo impide la restriccion.
        sa.update(Gasto).where(Gasto.id == gasto.id).values(estado="ANULADO"),
    ):
        # El error sale del bloque anidado: se deshace hasta el punto de
        # guardado y la prueba puede seguir con la siguiente sentencia.
        with pytest.raises(DBAPIError) as error:
            async with sesion.begin_nested():
                await sesion.execute(sentencia)
        assert error.value.orig is not None


async def test_flujo_de_caja_resta_gastos_vigentes_de_pagos_confirmados(
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
    instante = INSTANTE_REFERENCIA
    cita = Cita(
        clinica_id=clinica.id,
        sede_id=sede.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        servicio_id=servicio.id,
        inicio=instante - timedelta(hours=2),
        duracion_minutos=30,
        minutos_preparacion=0,
        estado="CONFIRMED",
        origen="PANEL",
        confirmada_en=instante - timedelta(days=1),
    )
    sesion.add(cita)
    await sesion.flush()
    sesion.add_all(
        [
            Pago(
                clinica_id=clinica.id,
                cita_id=cita.id,
                importe="150.00",
                moneda="USD",
                metodo="EFECTIVO",
                estado="CONFIRMED",
                creado_en=instante,
            ),
            # Pendiente: todavia no es dinero en caja.
            Pago(
                clinica_id=clinica.id,
                cita_id=cita.id,
                importe="70.00",
                moneda="USD",
                metodo="TRANSFERENCIA",
                estado="PENDING",
                creado_en=instante,
            ),
            Gasto(
                clinica_id=clinica.id,
                sede_id=sede.id,
                fecha=HOY,
                categoria="INSUMOS",
                descripcion="Resinas sintéticas",
                importe=Decimal("40.00"),
                metodo="EFECTIVO",
            ),
            Gasto(
                clinica_id=clinica.id,
                sede_id=sede.id,
                fecha=HOY - timedelta(days=1),
                categoria="LABORATORIO",
                descripcion="Laboratorio externo",
                importe=Decimal("20.00"),
                metodo="TRANSFERENCIA",
            ),
        ]
    )
    await sesion.flush()
    await conceder_permisos(sesion, usuario, clinica, "gasto.leer", sedes=(sede.id,))
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    periodo = {
        "desde": (HOY - timedelta(days=1)).isoformat(),
        "hasta": (HOY + timedelta(days=1)).isoformat(),
    }

    # Sin `pago.leer` no hay flujo: cruza con los cobros.
    assert (
        await cliente.get(f"{api}/gastos/flujo", headers=cabeceras, params=periodo)
    ).status_code == 403

    await conceder_permisos(sesion, usuario, clinica, "pago.leer", sedes=(sede.id,))
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    respuesta = await cliente.get(f"{api}/gastos/flujo", headers=cabeceras, params=periodo)

    assert respuesta.status_code == 200, respuesta.text
    flujo = respuesta.json()
    assert Decimal(flujo["ingresos"]) == Decimal("150.00")
    assert Decimal(flujo["gastos"]) == Decimal("60.00")
    assert Decimal(flujo["resultado"]) == Decimal("90.00")
    assert Decimal(flujo["margen_porcentaje"]) == Decimal("60.0")
    assert [c["categoria"] for c in flujo["por_categoria"]] == ["INSUMOS", "LABORATORIO"]
    por_dia = {d["fecha"]: d for d in flujo["por_dia"]}
    assert Decimal(por_dia[HOY.isoformat()]["resultado"]) == Decimal("110.00")
    assert Decimal(por_dia[(HOY - timedelta(days=1)).isoformat()]["resultado"]) == Decimal("-20.00")
    assert "Base de caja" in flujo["base"]

    invalido = await cliente.get(
        f"{api}/gastos/flujo",
        headers=cabeceras,
        params={"desde": HOY.isoformat(), "hasta": HOY.isoformat()},
    )
    assert invalido.status_code == 422
