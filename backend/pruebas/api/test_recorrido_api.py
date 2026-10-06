"""Recorrido del paciente, derivación interna y prolongación de una atención.

* La prolongación que pisa al siguiente paciente no se aplica sola: queda
  pendiente y recepción decide; el paciente movido conserva su cita.
* Sin choque, la prolongación se aplica al momento.
* La derivación crea la atención en el área de destino con la llegada ya
  registrada y la relación asistencial para el profesional de destino.
* El recorrido cuenta todo en orden y sin datos clínicos, y se audita.
* Sin permiso, sin sesión o en una clínica ajena: rechazado.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita
from app.modulos.auditoria.modelos import Auditoria
from app.modulos.organizacion.modelos import Clinica, Consultorio, Sede, Servicio
from app.modulos.pacientes.modelos import Paciente, RelacionAsistencial
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.auditoria import AccionAuditada
from app.nucleo.seguridad import hashear_contrasena
from pruebas.api.conftest import CONTRASENA, cabecera_bearer, conceder_permisos
from pruebas.conftest import INSTANTE_REFERENCIA

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]

PERMISOS = (
    "agenda.leer",
    "cita.crear",
    "cita.reprogramar",
    "cita.registrar_llegada",
    "cita.iniciar_atencion",
    "historia_clinica.escribir",
)


async def _cita(
    sesion: AsyncSession,
    *,
    clinica: Clinica,
    sede: Sede,
    servicio: Servicio,
    profesional: Profesional,
    paciente: Paciente,
    minutos_desde_referencia: int,
    en_atencion: bool = False,
) -> Cita:
    inicio = INSTANTE_REFERENCIA + timedelta(minutes=minutos_desde_referencia)
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
        confirmada_en=inicio - timedelta(days=1),
        llegada_en=inicio - timedelta(minutes=5) if en_atencion else None,
        atencion_iniciada_en=inicio if en_atencion else None,
    )
    sesion.add(cita)
    await sesion.flush()
    await sesion.refresh(cita)
    return cita


async def _otro_paciente(sesion: AsyncSession, clinica: Clinica) -> Paciente:
    sufijo = uuid.uuid4().hex[:6]
    otro = Paciente(
        clinica_id=clinica.id,
        nombre="Otro",
        apellido=f"Sintetico {sufijo}",
        tipo_documento="CEDULA",
        numero_documento=f"99{uuid.uuid4().int % 10**8:08d}",
    )
    sesion.add(otro)
    await sesion.flush()
    return otro


async def test_prolongar_con_choque_queda_pendiente_y_recepcion_mueve_al_siguiente(
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
    en_atencion = await _cita(
        sesion,
        clinica=clinica,
        sede=sede,
        servicio=servicio,
        profesional=profesional,
        paciente=paciente,
        minutos_desde_referencia=-10,
        en_atencion=True,
    )
    siguiente_paciente = await _otro_paciente(sesion, clinica)
    siguiente = await _cita(
        sesion,
        clinica=clinica,
        sede=sede,
        servicio=servicio,
        profesional=profesional,
        paciente=siguiente_paciente,
        minutos_desde_referencia=20,
    )
    await conceder_permisos(sesion, usuario, clinica, *PERMISOS, sedes=(sede.id,))
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    base = f"{api}/agenda/citas/{en_atencion.id}"

    sin_sesion = await cliente.post(f"{base}/prolongacion", json={"minutos": 20})
    assert sin_sesion.status_code == 401
    fuera_de_rango = await cliente.post(
        f"{base}/prolongacion", headers=cabeceras, json={"minutos": 500}
    )
    assert fuera_de_rango.status_code == 422

    pedida = await cliente.post(f"{base}/prolongacion", headers=cabeceras, json={"minutos": 20})
    assert pedida.status_code == 200, pedida.text
    cuerpo = pedida.json()
    assert cuerpo["aplicada"] is False
    assert [c["cita_id"] for c in cuerpo["conflictos"]] == [str(siguiente.id)]

    repetida = await cliente.post(f"{base}/prolongacion", headers=cabeceras, json={"minutos": 10})
    assert repetida.status_code == 409

    pendientes = await cliente.get(f"{api}/agenda/prolongaciones", headers=cabeceras)
    assert pendientes.status_code == 200
    assert [p["cita_id"] for p in pendientes.json()] == [str(en_atencion.id)]

    opciones = await cliente.get(f"{base}/prolongacion/opciones", headers=cabeceras)
    assert opciones.status_code == 200, opciones.text
    assert opciones.json()["minutos"] == 20

    sin_decidir = await cliente.post(
        f"{base}/prolongacion/resolucion", headers=cabeceras, json={"aprobar": True}
    )
    assert sin_decidir.status_code == 422 or sin_decidir.json()["codigo"] == "REGLA_NEGOCIO"

    mas_tarde = INSTANTE_REFERENCIA + timedelta(hours=2)
    aplicada = await cliente.post(
        f"{base}/prolongacion/resolucion",
        headers=cabeceras,
        json={
            "aprobar": True,
            "resoluciones": [{"cita_id": str(siguiente.id), "inicio": mas_tarde.isoformat()}],
        },
    )
    assert aplicada.status_code == 200, aplicada.text
    assert aplicada.json()["aplicada"] is True

    await sesion.refresh(en_atencion)
    await sesion.refresh(siguiente)
    assert en_atencion.duracion_minutos == 50
    assert siguiente.inicio == mas_tarde
    assert siguiente.estado == "RESCHEDULED"

    vacio = await cliente.get(f"{api}/agenda/prolongaciones", headers=cabeceras)
    assert vacio.json() == []

    recorrido = await cliente.get(
        f"{api}/agenda/pacientes/{paciente.id}/recorrido", headers=cabeceras
    )
    assert recorrido.status_code == 200
    eventos = [p["evento"] for p in recorrido.json()]
    assert eventos[-2:] == ["PROLONGACION_SOLICITADA", "PROLONGACION_APLICADA"]
    auditado = (
        await sesion.execute(
            sa.select(sa.func.count()).where(
                Auditoria.accion == AccionAuditada.RECORRIDO_CONSULTADO.value,
                Auditoria.paciente_id == paciente.id,
            )
        )
    ).scalar_one()
    assert auditado >= 1


async def test_prolongar_sin_choque_se_aplica_y_recepcion_puede_rechazar_otra(
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
    cita = await _cita(
        sesion,
        clinica=clinica,
        sede=sede,
        servicio=servicio,
        profesional=profesional,
        paciente=paciente,
        minutos_desde_referencia=-10,
        en_atencion=True,
    )
    await conceder_permisos(sesion, usuario, clinica, *PERMISOS, sedes=(sede.id,))
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    base = f"{api}/agenda/citas/{cita.id}"

    aplicada = await cliente.post(f"{base}/prolongacion", headers=cabeceras, json={"minutos": 15})
    assert aplicada.status_code == 200, aplicada.text
    assert aplicada.json()["aplicada"] is True
    await sesion.refresh(cita)
    assert cita.duracion_minutos == 45

    # Ahora sí choca con alguien: queda pendiente y recepción la rechaza.
    otro = await _otro_paciente(sesion, clinica)
    await _cita(
        sesion,
        clinica=clinica,
        sede=sede,
        servicio=servicio,
        profesional=profesional,
        paciente=otro,
        minutos_desde_referencia=40,
    )
    pendiente = await cliente.post(f"{base}/prolongacion", headers=cabeceras, json={"minutos": 30})
    assert pendiente.json()["aplicada"] is False
    sin_motivo = await cliente.post(
        f"{base}/prolongacion/resolucion", headers=cabeceras, json={"aprobar": False}
    )
    assert sin_motivo.status_code in (409, 422)
    rechazada = await cliente.post(
        f"{base}/prolongacion/resolucion",
        headers=cabeceras,
        json={"aprobar": False, "motivo_rechazo": "El siguiente paciente ya está en sala"},
    )
    assert rechazada.status_code == 200, rechazada.text
    await sesion.refresh(cita)
    assert cita.duracion_minutos == 45


async def test_derivacion_interna_crea_la_atencion_de_destino_con_relacion(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    servicio: Servicio,
    profesional: Profesional,
    paciente: Paciente,
    sufijo: str,
) -> None:
    origen = await _cita(
        sesion,
        clinica=clinica,
        sede=sede,
        servicio=servicio,
        profesional=profesional,
        paciente=paciente,
        minutos_desde_referencia=-10,
        en_atencion=True,
    )
    destino = Profesional(
        clinica_id=clinica.id,
        especialidad_id=profesional.especialidad_id,
        nombre="Destino",
        apellido="Sintetico",
        numero_registro_profesional=f"DST-{sufijo}",
    )
    consultorio = Consultorio(sede_id=sede.id, nombre=f"Sala {sufijo}")
    sesion.add_all([destino, consultorio])
    sesion.add(
        RelacionAsistencial(paciente_id=paciente.id, profesional_id=profesional.id, origen="CITA")
    )
    await sesion.flush()

    await conceder_permisos(
        sesion, usuario, clinica, "agenda.leer", "cita.registrar_llegada", sedes=(sede.id,)
    )
    sin_permiso = await cliente.post(
        f"{api}/agenda/citas/{origen.id}/derivacion",
        headers=await cabecera_bearer(cliente, usuario, clinica),
        json={"profesional_id": str(destino.id), "servicio_id": str(servicio.id)},
    )
    assert sin_permiso.status_code == 403

    await conceder_permisos(sesion, usuario, clinica, *PERMISOS, sedes=(sede.id,))
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    a_sala = await cliente.post(
        f"{api}/agenda/citas/{origen.id}/consultorio",
        headers=cabeceras,
        json={"consultorio_id": str(consultorio.id)},
    )
    assert a_sala.status_code == 200, a_sala.text

    mismo = await cliente.post(
        f"{api}/agenda/citas/{origen.id}/derivacion",
        headers=cabeceras,
        json={"profesional_id": str(profesional.id), "servicio_id": str(servicio.id)},
    )
    assert mismo.status_code == 422 or mismo.json()["codigo"] == "REGLA_NEGOCIO"

    derivada = await cliente.post(
        f"{api}/agenda/citas/{origen.id}/derivacion",
        headers=cabeceras,
        json={"profesional_id": str(destino.id), "servicio_id": str(servicio.id)},
    )
    assert derivada.status_code == 201, derivada.text
    nueva = await sesion.get(Cita, uuid.UUID(derivada.json()["id"]))
    assert nueva is not None
    assert nueva.profesional_id == destino.id
    assert nueva.llegada_en is not None
    relacion = (
        await sesion.execute(
            sa.select(sa.func.count()).where(
                RelacionAsistencial.paciente_id == paciente.id,
                RelacionAsistencial.profesional_id == destino.id,
                RelacionAsistencial.origen == "DERIVACION",
            )
        )
    ).scalar_one()
    assert relacion == 1

    salida = await cliente.post(f"{api}/agenda/citas/{origen.id}/salida", headers=cabeceras)
    assert salida.status_code == 200
    otra_salida = await cliente.post(f"{api}/agenda/citas/{origen.id}/salida", headers=cabeceras)
    assert otra_salida.status_code == 409

    recorrido = (
        await cliente.get(f"{api}/agenda/pacientes/{paciente.id}/recorrido", headers=cabeceras)
    ).json()
    eventos = [p["evento"] for p in recorrido]
    for esperado in ("INGRESO_CONSULTORIO", "DERIVACION_INTERNA", "DERIVADA_DESDE", "SALIDA"):
        assert esperado in eventos
    derivacion = next(p for p in recorrido if p["evento"] == "DERIVACION_INTERNA")
    assert "Destino Sintetico" in (derivacion["detalle"] or "")
    ingreso = next(p for p in recorrido if p["evento"] == "INGRESO_CONSULTORIO")
    assert ingreso["consultorio"] == f"Sala {sufijo}"

    # Otra clínica no ve el recorrido.
    ajena = Clinica(nombre="Clinica ajena", identificacion_fiscal=uuid.uuid4().hex[:12])
    sesion.add(ajena)
    await sesion.flush()
    intruso = Usuario(
        clinica_id=ajena.id,
        correo=f"intruso.{sufijo}@example.invalid",
        hash_contrasena=hashear_contrasena(CONTRASENA),
        nombre="Intruso",
        apellido="Sintetico",
    )
    sesion.add(intruso)
    await sesion.flush()
    await conceder_permisos(sesion, intruso, ajena, "agenda.leer", todas_las_sedes=True)
    visto = await cliente.get(
        f"{api}/agenda/pacientes/{paciente.id}/recorrido",
        headers=await cabecera_bearer(cliente, intruso, ajena),
    )
    assert visto.status_code == 200
    assert visto.json() == []
