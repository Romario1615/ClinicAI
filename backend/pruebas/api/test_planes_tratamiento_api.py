"""Ámbito clínico, borradores y propuesta del plan de tratamiento."""

from __future__ import annotations

import re
from datetime import date

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.modelos import Auditoria
from app.modulos.odontologia.modelos import EstadoPlan, PlanTratamiento, ProcedimientoPlan
from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.outbox.modelos import OutboxMensaje
from app.modulos.pacientes.modelos import Consentimiento, Paciente, RelacionAsistencial
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.auditoria import AccionAuditada
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]

PERMISOS_PLAN = ("plan_tratamiento.leer", "plan_tratamiento.escribir")


def _ruta(api: str, paciente_id: str) -> str:
    return f"{api}/odontologia/pacientes/{paciente_id}/planes-tratamiento"


def _plan() -> dict[str, object]:
    return {
        "titulo": "Rehabilitación del cuadrante inferior",
        "moneda": "USD",
        "procedimientos": [
            {
                "fase": 1,
                "orden": 1,
                "pieza": 36,
                "caras": "OM",
                "descripcion": "Restauración de molar",
                "precio": "85.00",
            }
        ],
    }


@pytest_asyncio.fixture
async def relacion_plan(
    sesion: AsyncSession, paciente: Paciente, profesional: Profesional
) -> RelacionAsistencial:
    fila = RelacionAsistencial(
        paciente_id=paciente.id, profesional_id=profesional.id, origen="CITA"
    )
    sesion.add(fila)
    await sesion.flush()
    return fila


@pytest_asyncio.fixture
async def cabeceras_plan(
    cliente: AsyncClient,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    profesional: Profesional,
) -> dict[str, str]:
    await conceder_permisos(sesion, usuario, clinica, *PERMISOS_PLAN, sedes=(sede.id,))
    return await cabecera_bearer(cliente, usuario, clinica)


async def test_sin_permiso_no_consulta_planes(
    cliente: AsyncClient,
    api: str,
    usuario: Usuario,
    clinica: Clinica,
    paciente: Paciente,
) -> None:
    respuesta = await cliente.get(
        _ruta(api, str(paciente.id)),
        headers=await cabecera_bearer(cliente, usuario, clinica),
    )
    assert respuesta.status_code == 403


async def test_crear_proponer_y_leer_conserva_procedimientos_y_auditoria(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    cabeceras_plan: dict[str, str],
    relacion_plan: RelacionAsistencial,
    paciente: Paciente,
) -> None:
    ruta = _ruta(api, str(paciente.id))
    creado = await cliente.post(ruta, headers=cabeceras_plan, json=_plan())
    assert creado.status_code == 201, creado.text
    cuerpo = creado.json()
    assert cuerpo["estado"] == "BORRADOR"
    assert cuerpo["procedimientos"][0]["pieza"] == 36
    assert cuerpo["procedimientos"][0]["caras"] == "OM"
    assert cuerpo["procedimientos"][0]["precio"] == "85.00"

    propuesto = await cliente.post(
        f"{api}/odontologia/planes-tratamiento/{cuerpo['id']}/propuesta",
        headers=cabeceras_plan,
    )
    assert propuesto.status_code == 200, propuesto.text
    assert propuesto.json()["estado"] == "PROPUESTO"
    assert propuesto.json()["propuesto_en"]

    listado = await cliente.get(ruta, headers=cabeceras_plan)
    assert listado.status_code == 200
    assert listado.json()[0]["id"] == cuerpo["id"]
    assert listado.json()[0]["procedimientos"][0]["descripcion"] == "Restauración de molar"

    filas = list(
        (
            await sesion.execute(
                sa.select(PlanTratamiento).where(PlanTratamiento.paciente_id == paciente.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(filas) == 1
    assert filas[0].estado == EstadoPlan.PROPUESTO.value
    assert (
        len(
            (
                await sesion.execute(
                    sa.select(ProcedimientoPlan).where(ProcedimientoPlan.plan_id == filas[0].id)
                )
            )
            .scalars()
            .all()
        )
        == 1
    )
    acciones = set((await sesion.execute(sa.select(Auditoria.accion))).scalars())
    assert {
        AccionAuditada.PLAN_CREADO.value,
        AccionAuditada.PLAN_ESTADO_CAMBIADO.value,
        AccionAuditada.PLAN_CONSULTADO.value,
    } <= acciones


async def test_plan_n3_exige_permiso_y_audita_su_nivel(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    cabeceras_plan: dict[str, str],
    relacion_plan: RelacionAsistencial,
    paciente: Paciente,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
) -> None:
    ruta = _ruta(api, str(paciente.id))
    cuerpo = {**_plan(), "nivel_sensibilidad": "N3"}
    denegado = await cliente.post(ruta, headers=cabeceras_plan, json=cuerpo)
    assert denegado.status_code == 403

    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "historia_clinica.leer_sensible",
        sedes=(sede.id,),
    )
    cabeceras_sensibles = await cabecera_bearer(cliente, usuario, clinica)
    creado = await cliente.post(ruta, headers=cabeceras_sensibles, json=cuerpo)
    assert creado.status_code == 201, creado.text
    assert creado.json()["nivel_sensibilidad"] == "N3"

    propuesto = await cliente.post(
        f"{api}/odontologia/planes-tratamiento/{creado.json()['id']}/propuesta",
        headers=cabeceras_sensibles,
    )
    assert propuesto.status_code == 200, propuesto.text
    assert propuesto.json()["nivel_sensibilidad"] == "N3"

    listado = await cliente.get(ruta, headers=cabeceras_sensibles)
    assert listado.status_code == 200
    assert listado.json()[0]["nivel_sensibilidad"] == "N3"
    niveles = list(
        (
            await sesion.execute(
                sa.select(Auditoria.nivel_sensibilidad).where(
                    Auditoria.paciente_id == paciente.id,
                    Auditoria.accion.in_(
                        [
                            AccionAuditada.PLAN_CREADO.value,
                            AccionAuditada.PLAN_ESTADO_CAMBIADO.value,
                            AccionAuditada.PLAN_CONSULTADO.value,
                        ]
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(niveles) == 3 and set(niveles) == {"N3"}


async def test_plan_n3_se_filtra_y_no_se_puede_mutar_sin_permiso(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    cabeceras_plan: dict[str, str],
    relacion_plan: RelacionAsistencial,
    paciente: Paciente,
    profesional: Profesional,
    clinica: Clinica,
    usuario: Usuario,
) -> None:
    plan = PlanTratamiento(
        clinica_id=clinica.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        titulo="Borrador clínico sensible",
        estado=EstadoPlan.BORRADOR.value,
        moneda="USD",
        nivel_sensibilidad="N3",
        creado_por=usuario.id,
    )
    sesion.add(plan)
    await sesion.flush()
    procedimiento = ProcedimientoPlan(
        plan_id=plan.id,
        fase=1,
        orden=1,
        descripcion="Procedimiento sensible",
        precio="85.00",
        creado_por=usuario.id,
    )
    sesion.add(procedimiento)
    await sesion.flush()

    ruta = _ruta(api, str(paciente.id))
    listado = await cliente.get(ruta, headers=cabeceras_plan)
    propuesta = await cliente.post(
        f"{api}/odontologia/planes-tratamiento/{plan.id}/propuesta",
        headers=cabeceras_plan,
    )
    assert listado.status_code == 200 and listado.json() == []
    assert propuesta.status_code == 404
    eventos = list(
        (
            await sesion.execute(
                sa.select(Auditoria.nivel_sensibilidad).where(
                    Auditoria.paciente_id == paciente.id,
                    Auditoria.accion == AccionAuditada.PLAN_CONSULTADO.value,
                )
            )
        )
        .scalars()
        .all()
    )
    assert eventos == ["N3"]


@pytest.mark.parametrize(
    ("pieza", "caras"),
    [("99", "O"), ("36", "Q"), ("36", "OO")],
)
async def test_rechaza_pieza_o_caras_fdi_invalidas(
    cliente: AsyncClient,
    api: str,
    cabeceras_plan: dict[str, str],
    relacion_plan: RelacionAsistencial,
    paciente: Paciente,
    pieza: str,
    caras: str,
) -> None:
    cuerpo = _plan()
    cuerpo["procedimientos"] = [
        {"descripcion": "Restauración dental", "pieza": pieza, "caras": caras}
    ]
    respuesta = await cliente.post(
        _ruta(api, str(paciente.id)), headers=cabeceras_plan, json=cuerpo
    )
    assert respuesta.status_code == 422


async def test_no_permite_proponer_dos_veces(
    cliente: AsyncClient,
    api: str,
    cabeceras_plan: dict[str, str],
    relacion_plan: RelacionAsistencial,
    paciente: Paciente,
) -> None:
    creado = await cliente.post(_ruta(api, str(paciente.id)), headers=cabeceras_plan, json=_plan())
    url = f"{api}/odontologia/planes-tratamiento/{creado.json()['id']}/propuesta"
    assert (await cliente.post(url, headers=cabeceras_plan)).status_code == 200
    segunda = await cliente.post(url, headers=cabeceras_plan)
    assert segunda.status_code == 422


@pytest.mark.parametrize(
    "cambio",
    [
        {"titulo": "   "},
        {"procedimientos": [{"descripcion": "  "}]},
        {
            "procedimientos": [
                {"fase": 1, "orden": 1, "descripcion": "Primera"},
                {"fase": 1, "orden": 1, "descripcion": "Segunda"},
            ]
        },
    ],
)
async def test_rechaza_plan_sin_contenido_util_o_con_orden_duplicado(
    cliente: AsyncClient,
    api: str,
    cabeceras_plan: dict[str, str],
    relacion_plan: RelacionAsistencial,
    paciente: Paciente,
    cambio: dict[str, object],
) -> None:
    cuerpo = {**_plan(), **cambio}
    respuesta = await cliente.post(
        _ruta(api, str(paciente.id)), headers=cabeceras_plan, json=cuerpo
    )
    assert respuesta.status_code == 422


# ===========================================================================
#  Aceptacion, ejecucion y cancelacion
# ===========================================================================
async def _plan_propuesto(
    cliente: AsyncClient, api: str, paciente: Paciente, cabeceras: dict[str, str]
) -> dict[str, object]:
    creado = await cliente.post(_ruta(api, str(paciente.id)), headers=cabeceras, json=_plan())
    assert creado.status_code == 201, creado.text
    plan_id = creado.json()["id"]
    propuesto = await cliente.post(
        f"{api}/odontologia/planes-tratamiento/{plan_id}/propuesta", headers=cabeceras
    )
    assert propuesto.status_code == 200, propuesto.text
    cuerpo: dict[str, object] = propuesto.json()
    return cuerpo


async def _aceptar(
    cliente: AsyncClient, api: str, plan_id: object, cabeceras: dict[str, str]
) -> AsyncClient:
    respuesta = await cliente.post(
        f"{api}/odontologia/planes-tratamiento/{plan_id}/aceptacion",
        headers=cabeceras,
        json={"medio": "DOCUMENTO_FIRMADO", "referencia": "Hoja de consentimiento 2026-0042"},
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta  # type: ignore[return-value]


async def test_no_se_completa_un_procedimiento_sin_aceptacion(
    cliente: AsyncClient,
    api: str,
    cabeceras_plan: dict[str, str],
    relacion_plan: RelacionAsistencial,
    paciente: Paciente,
) -> None:
    """Sin constancia de aceptacion del paciente no se ejecuta ni se cobra nada."""
    plan = await _plan_propuesto(cliente, api, paciente, cabeceras_plan)
    procedimiento = plan["procedimientos"][0]["id"]  # type: ignore[index]

    respuesta = await cliente.post(
        f"{api}/odontologia/procedimientos/{procedimiento}/completado",
        headers=cabeceras_plan,
        json={},
    )

    assert respuesta.status_code == 409


async def test_aceptacion_exige_referencia_del_documento(
    cliente: AsyncClient,
    api: str,
    cabeceras_plan: dict[str, str],
    relacion_plan: RelacionAsistencial,
    paciente: Paciente,
) -> None:
    plan = await _plan_propuesto(cliente, api, paciente, cabeceras_plan)
    respuesta = await cliente.post(
        f"{api}/odontologia/planes-tratamiento/{plan['id']}/aceptacion",
        headers=cabeceras_plan,
        json={"medio": "DOCUMENTO_FIRMADO", "referencia": "  "},
    )
    assert respuesta.status_code == 422


async def test_completar_actualiza_odontograma_y_cierra_el_plan(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    relacion_plan: RelacionAsistencial,
    paciente: Paciente,
) -> None:
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        *PERMISOS_PLAN,
        "odontograma.leer",
        "odontograma.escribir",
        sedes=(sede.id,),
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    plan = await _plan_propuesto(cliente, api, paciente, cabeceras)
    aceptado = (await _aceptar(cliente, api, plan["id"], cabeceras)).json()
    assert aceptado["estado"] == "ACEPTADO"
    assert aceptado["aceptacion_medio"] == "DOCUMENTO_FIRMADO"
    procedimiento = aceptado["procedimientos"][0]["id"]

    control_pasado = await cliente.post(
        f"{api}/odontologia/procedimientos/{procedimiento}/completado",
        headers=cabeceras,
        json={"control_recomendado_en": "2026-04-14"},
    )
    assert control_pasado.status_code == 422, control_pasado.text

    completado = await cliente.post(
        f"{api}/odontologia/procedimientos/{procedimiento}/completado",
        headers=cabeceras,
        json={
            "hallazgo_resultante": "OBTURACION_RESINA",
            "control_recomendado_en": "2026-04-16",
        },
    )

    assert completado.status_code == 200, completado.text
    cuerpo = completado.json()
    assert cuerpo["estado"] == "COMPLETADO"
    assert cuerpo["procedimientos"][0]["estado"] == "COMPLETADO"
    assert cuerpo["procedimientos"][0]["control_recomendado_en"] == "2026-04-16"
    assert cuerpo["procedimientos"][0]["control_atendido_en"] is None

    control = await cliente.post(
        f"{api}/odontologia/procedimientos/{procedimiento}/control/atencion",
        headers=cabeceras,
        json={"nota": "Control realizado; evolución estable."},
    )
    assert control.status_code == 200, control.text
    procedimiento_actualizado = control.json()["procedimientos"][0]
    assert procedimiento_actualizado["control_atendido_en"] is not None
    assert procedimiento_actualizado["control_nota"] == "Control realizado; evolución estable."
    repetir_control = await cliente.post(
        f"{api}/odontologia/procedimientos/{procedimiento}/control/atencion",
        headers=cabeceras,
        json={},
    )
    assert repetir_control.status_code == 409, repetir_control.text

    odontograma = await cliente.get(
        f"{api}/odontologia/pacientes/{paciente.id}/odontograma", headers=cabeceras
    )
    assert odontograma.status_code == 200, odontograma.text
    pieza = odontograma.json()["piezas"]["36"]
    assert pieza["caras"] == {"O": "OBTURACION_RESINA", "M": "OBTURACION_RESINA"}
    assert odontograma.json()["procedimiento_id"] == procedimiento

    acciones = set((await sesion.execute(sa.select(Auditoria.accion))).scalars())
    assert AccionAuditada.PROCEDIMIENTO_COMPLETADO.value in acciones
    assert AccionAuditada.CONTROL_TRATAMIENTO_ATENDIDO.value in acciones
    assert AccionAuditada.ODONTOGRAMA_VERSIONADO.value in acciones


async def test_base_rechaza_programar_control_en_procedimiento_pendiente(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    cabeceras_plan: dict[str, str],
    relacion_plan: RelacionAsistencial,
    paciente: Paciente,
) -> None:
    plan = await _plan_propuesto(cliente, api, paciente, cabeceras_plan)
    procedimiento_id = plan["procedimientos"][0]["id"]  # type: ignore[index]

    with pytest.raises(sa.exc.IntegrityError):
        async with sesion.begin_nested():
            await sesion.execute(
                sa.text(
                    "UPDATE procedimiento_plan SET control_recomendado_en = :fecha WHERE id = :id"
                ),
                {"fecha": date(2026, 4, 16), "id": procedimiento_id},
            )


async def test_cancelar_plan_conserva_motivo_y_bloquea_cambios(
    cliente: AsyncClient,
    api: str,
    cabeceras_plan: dict[str, str],
    relacion_plan: RelacionAsistencial,
    paciente: Paciente,
) -> None:
    plan = await _plan_propuesto(cliente, api, paciente, cabeceras_plan)
    cancelado = await cliente.post(
        f"{api}/odontologia/planes-tratamiento/{plan['id']}/cancelacion",
        headers=cabeceras_plan,
        json={"motivo": "El paciente prefiere otra alternativa"},
    )
    assert cancelado.status_code == 200, cancelado.text
    cuerpo = cancelado.json()
    assert cuerpo["estado"] == "CANCELADO"
    assert cuerpo["motivo_cancelacion"] == "El paciente prefiere otra alternativa"
    assert cuerpo["procedimientos"][0]["estado"] == "CANCELADO"

    otra_vez = await cliente.post(
        f"{api}/odontologia/planes-tratamiento/{plan['id']}/aceptacion",
        headers=cabeceras_plan,
        json={"medio": "DOCUMENTO_FIRMADO", "referencia": "Hoja 1"},
    )
    assert otra_vez.status_code == 409


async def test_procedimiento_de_otro_paciente_sin_relacion_no_se_completa(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    cabeceras_plan: dict[str, str],
    relacion_plan: RelacionAsistencial,
    paciente: Paciente,
) -> None:
    """IDOR: al revocar la relacion asistencial, el identificador no basta."""
    plan = await _plan_propuesto(cliente, api, paciente, cabeceras_plan)
    await _aceptar(cliente, api, plan["id"], cabeceras_plan)
    relacion_plan.revocada_en = sa.func.now()
    await sesion.flush()

    respuesta = await cliente.post(
        f"{api}/odontologia/procedimientos/{plan['procedimientos'][0]['id']}/completado",  # type: ignore[index]
        headers=cabeceras_plan,
        json={},
    )
    assert respuesta.status_code == 404


async def _plan_dos_fases(
    cliente: AsyncClient, api: str, paciente: Paciente, cabeceras: dict[str, str]
) -> dict[str, object]:
    datos = _plan()
    datos["procedimientos"] = [
        {
            "fase": 1,
            "orden": 1,
            "pieza": 36,
            "caras": "O",
            "descripcion": "Fase inicial",
            "precio": "40.00",
        },
        {"fase": 2, "orden": 1, "pieza": 36, "descripcion": "Fase siguiente", "precio": "200.00"},
    ]
    creado = await cliente.post(_ruta(api, str(paciente.id)), headers=cabeceras, json=datos)
    assert creado.status_code == 201, creado.text
    plan_id = creado.json()["id"]
    await cliente.post(
        f"{api}/odontologia/planes-tratamiento/{plan_id}/propuesta", headers=cabeceras
    )
    respuesta = await _aceptar(cliente, api, plan_id, cabeceras)
    cuerpo: dict[str, object] = respuesta.json()
    return cuerpo


@pytest.mark.parametrize("con_consentimiento", [True, False])
async def test_al_cerrar_una_fase_se_invita_a_agendar_la_siguiente(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    cabeceras_plan: dict[str, str],
    relacion_plan: RelacionAsistencial,
    paciente: Paciente,
    con_consentimiento: bool,
) -> None:
    """Seguimiento sin IA y sin datos clinicos en el mensaje.

    Sin consentimiento de WhatsApp no sale nada, y el procedimiento se
    completa igual: un aviso nunca bloquea un acto clinico.
    """
    if con_consentimiento:
        sesion.add(
            Consentimiento(
                paciente_id=paciente.id,
                tipo="COMUNICACION_WHATSAPP",
                otorgado=True,
                version_texto="v1",
                texto_hash="0" * 64,
                canal="PRESENCIAL",
            )
        )
        await sesion.flush()
    plan = await _plan_dos_fases(cliente, api, paciente, cabeceras_plan)
    fase_uno = next(p for p in plan["procedimientos"] if p["fase"] == 1)  # type: ignore[union-attr]

    completado = await cliente.post(
        f"{api}/odontologia/procedimientos/{fase_uno['id']}/completado",
        headers=cabeceras_plan,
        json={},
    )
    assert completado.status_code == 200, completado.text
    assert completado.json()["estado"] == "ACEPTADO"

    mensajes = list(
        (
            await sesion.execute(
                sa.select(OutboxMensaje).where(
                    OutboxMensaje.tipo == "SEGUIMIENTO_TRATAMIENTO",
                    OutboxMensaje.destino_id == paciente.id,
                )
            )
        )
        .scalars()
        .all()
    )
    if not con_consentimiento:
        assert mensajes == []
        return
    assert len(mensajes) == 1
    texto = mensajes[0].carga_util["texto"]
    assert "Fase" not in texto
    # La clínica sintética incluye un sufijo numérico; buscar "36" como
    # subcadena daba un falso positivo cuando coincidía con ese identificador.
    assert re.search(r"\b36\b", texto) is None
    assert set(mensajes[0].carga_util["variables"]) == {"nombre", "clinica"}


# ===========================================================================
#  Plantillas
# ===========================================================================
async def test_plantillas_se_crean_listan_y_retiran(
    cliente: AsyncClient,
    api: str,
    cabeceras_plan: dict[str, str],
) -> None:
    ruta = f"{api}/odontologia/plantillas-plan"
    datos = {
        "nombre": "Corona sobre endodoncia",
        "procedimientos": [
            {"fase": 1, "orden": 1, "descripcion": "Endodoncia", "precio": "180.00"},
            {"fase": 2, "orden": 1, "descripcion": "Corona", "precio": "250.00"},
        ],
    }
    creada = await cliente.post(ruta, headers=cabeceras_plan, json=datos)
    assert creada.status_code == 201, creada.text
    assert len(creada.json()["procedimientos"]) == 2

    repetida = await cliente.post(ruta, headers=cabeceras_plan, json=datos)
    assert repetida.status_code == 409

    vacia = await cliente.post(
        ruta, headers=cabeceras_plan, json={"nombre": "Vacia", "procedimientos": []}
    )
    assert vacia.status_code == 422

    listado = await cliente.get(ruta, headers=cabeceras_plan)
    assert [p["nombre"] for p in listado.json()] == ["Corona sobre endodoncia"]

    retirada = await cliente.post(
        f"{ruta}/{creada.json()['id']}/retiro",
        headers=cabeceras_plan,
        json={"motivo": "Se actualizan los precios"},
    )
    assert retirada.status_code == 200
    assert (await cliente.get(ruta, headers=cabeceras_plan)).json() == []

    # Retirada, el nombre queda libre para una version nueva.
    otra = await cliente.post(ruta, headers=cabeceras_plan, json=datos)
    assert otra.status_code == 201


async def test_plantillas_exigen_permiso(
    cliente: AsyncClient, api: str, usuario: Usuario, clinica: Clinica
) -> None:
    respuesta = await cliente.get(
        f"{api}/odontologia/plantillas-plan",
        headers=await cabecera_bearer(cliente, usuario, clinica),
    )
    assert respuesta.status_code == 403
