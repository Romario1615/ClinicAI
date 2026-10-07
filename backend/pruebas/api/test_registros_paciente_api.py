"""CRUD con historial, PDF real y entrega privada; datos y proveedor sintéticos."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

import pytest
import pytest_asyncio
from httpx import AsyncClient
from pypdf import PdfReader
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.mensajeria.adaptadores import AdaptadorSandbox, RegistroCanales
from app.mensajeria.servicios import ResumenProceso, ServicioOutbox
from app.modulos.documentos.modelos import EntregaDocumento, RegistroPaciente
from app.modulos.historia.modelos import Receta
from app.modulos.odontologia.modelos import PlanTratamiento, ProcedimientoPlan
from app.modulos.organizacion.modelos import Clinica, Especialidad, Sede
from app.modulos.outbox.modelos import OutboxMensaje
from app.modulos.pacientes.modelos import Consentimiento, Paciente, RelacionAsistencial
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.reloj import RelojFijo
from pruebas.api.conftest import cabecera_bearer, conceder_permisos
from pruebas.api.test_postconsulta_api import _receta

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def acceso(
    cliente: AsyncClient,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
    profesional: Profesional,
    especialidad: Especialidad,
) -> dict[str, str]:
    especialidad.nombre = "Estética sintética"
    especialidad.codigo = "ESTETICA"
    paciente.fecha_nacimiento = date(1990, 4, 12)
    paciente.telefono_whatsapp = "+593999000001"
    sesion.add(
        RelacionAsistencial(paciente_id=paciente.id, profesional_id=profesional.id, origen="CITA")
    )
    await sesion.flush()
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "historia_clinica.leer",
        "historia_clinica.escribir",
        "receta.leer",
        "agenda.leer",
        sedes=(sede.id,),
    )
    return await cabecera_bearer(cliente, usuario, clinica)


def nuevo(especialidad: Especialidad, sede: Sede, **cambios: object) -> dict[str, object]:
    return {
        "clave_idempotencia": str(uuid.uuid4()),
        "tipo": "PRESUPUESTO",
        "titulo": "Presupuesto sintético",
        "especialidad_id": str(especialidad.id),
        "sede_id": str(sede.id),
        "motivo": "Registro inicial",
        "partidas": [
            {"descripcion": "Consulta sintética", "cantidad": "2", "precio_unitario": "12.35"}
        ],
        **cambios,
    }


async def test_crud_presupuesto_pdf_versionado_y_anulacion(
    cliente: AsyncClient,
    api: str,
    acceso: dict[str, str],
    especialidad: Especialidad,
    sede: Sede,
    paciente: Paciente,
    sesion: AsyncSession,
) -> None:
    ruta = f"{api}/historia/pacientes/{paciente.id}/registros"
    datos = nuevo(especialidad, sede)
    r = await cliente.post(ruta, json=datos, headers=acceso)
    assert r.status_code == 201, r.text
    original = r.json()
    assert (await cliente.post(ruta, json=datos, headers=acceso)).json()["id"] == original["id"]
    diferente = await cliente.post(ruta, json={**datos, "titulo": "Otro contenido"}, headers=acceso)
    assert diferente.status_code == 409
    pdf = await cliente.get(f"{ruta}/{original['id']}/pdf", headers=acceso)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    texto = " ".join(p.extract_text() for p in PdfReader(BytesIO(pdf.content)).pages)
    assert "24.70 USD" in texto and "Consulta sintética" in texto and paciente.nombre in texto
    assert pdf.headers["cache-control"] == "no-store"
    version = nuevo(
        especialidad,
        sede,
        raiz_id=original["raiz_id"],
        version_base=1,
        motivo="Corrección de conceptos",
    )
    segunda = await cliente.post(ruta, json=version, headers=acceso)
    assert segunda.status_code == 201, segunda.text
    assert segunda.json()["version"] == 2
    obsoleta = await cliente.post(
        ruta, json={**version, "clave_idempotencia": str(uuid.uuid4())}, headers=acceso
    )
    assert obsoleta.status_code == 409
    anulada = await cliente.post(
        f"{ruta}/{segunda.json()['id']}/anulacion",
        json={"motivo": "Anulado por paciente"},
        headers=acceso,
    )
    assert anulada.status_code == 200, anulada.text
    assert anulada.json()["version"] == 3 and anulada.json()["anulado"]
    historial = await cliente.get(
        ruta, params={"especialidad_id": str(especialidad.id), "historico": True}, headers=acceso
    )
    assert len(historial.json()) == 3
    fila = await sesion.get(RegistroPaciente, uuid.UUID(original["id"]))
    assert fila is not None and fila.contenido["partidas"] == datos["partidas"]


async def test_faciograma_persistente_zonas_y_pdf(
    cliente: AsyncClient,
    api: str,
    acceso: dict[str, str],
    especialidad: Especialidad,
    sede: Sede,
    paciente: Paciente,
) -> None:
    ruta = f"{api}/historia/pacientes/{paciente.id}/registros"
    datos = nuevo(
        especialidad,
        sede,
        tipo="FACIOGRAMA",
        partidas=[],
        zonas=[
            {
                "zona": "pomulo_derecho",
                "observacion": "Seguimiento sintético",
                "estado": "PLANIFICADO",
            }
        ],
    )
    respuesta = await cliente.post(ruta, json=datos, headers=acceso)
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["contenido"]["zonas"][0]["zona"] == "pomulo_derecho"
    pdf = await cliente.get(f"{ruta}/{respuesta.json()['id']}/pdf", headers=acceso)
    assert "Pómulo derecho" in PdfReader(BytesIO(pdf.content)).pages[0].extract_text()
    invalida = await cliente.post(
        ruta,
        json={
            **datos,
            "clave_idempotencia": str(uuid.uuid4()),
            "zonas": [{"zona": "inventada", "observacion": "Sintética"}],
        },
        headers=acceso,
    )
    assert invalida.status_code == 422


async def test_envio_consentimiento_deduplicacion_acceso_y_revocacion(
    cliente: AsyncClient,
    api: str,
    acceso: dict[str, str],
    especialidad: Especialidad,
    sede: Sede,
    paciente: Paciente,
    sesion: AsyncSession,
) -> None:
    ruta = f"{api}/historia/pacientes/{paciente.id}/registros"
    registro = (await cliente.post(ruta, json=nuevo(especialidad, sede), headers=acceso)).json()
    envio = {"clave_idempotencia": str(uuid.uuid4()), "identidad_destinatario_confirmada": True}
    sin_consentimiento = await cliente.post(
        f"{ruta}/{registro['id']}/whatsapp", json=envio, headers=acceso
    )
    assert sin_consentimiento.status_code in (403, 409), sin_consentimiento.text
    sesion.add(
        Consentimiento(
            paciente_id=paciente.id,
            tipo="DOCUMENTOS_WHATSAPP",
            otorgado=True,
            version_texto="v1",
            texto_hash="0" * 64,
            canal="PRESENCIAL",
        )
    )
    await sesion.flush()
    respuesta = await cliente.post(f"{ruta}/{registro['id']}/whatsapp", json=envio, headers=acceso)
    assert respuesta.status_code == 200, respuesta.text
    entrega = respuesta.json()
    repetido = await cliente.post(f"{ruta}/{registro['id']}/whatsapp", json=envio, headers=acceso)
    assert repetido.json()["enlace"] == entrega["enlace"]
    mensajes = list(
        await sesion.scalars(
            select(OutboxMensaje).where(
                OutboxMensaje.tipo == "DOCUMENTO_DISPONIBLE",
                OutboxMensaje.destino_id == paciente.id,
            )
        )
    )
    assert len(mensajes) == 1
    assert "Consulta sintética" not in str(mensajes[0].carga_util)
    token = entrega["enlace"].rsplit("/", 1)[1]
    verificado = await cliente.post(
        f"{api}/publico/documentos/{token}/acceso", json={"fecha_nacimiento": "1990-04-12"}
    )
    assert verificado.status_code == 200 and verificado.content.startswith(b"%PDF-")
    await cliente.post(
        f"{ruta}/{registro['id']}/anulacion",
        json={"motivo": "Retirado por corrección"},
        headers=acceso,
    )
    retirado = await cliente.post(
        f"{api}/publico/documentos/{token}/acceso", json={"fecha_nacimiento": "1990-04-12"}
    )
    assert retirado.status_code == 404


async def test_receta_pdf_solo_confirmada_y_rechaza_suspension(
    cliente: AsyncClient,
    api: str,
    acceso: dict[str, str],
    especialidad: Especialidad,
    sede: Sede,
    paciente: Paciente,
    sesion: AsyncSession,
    clinica: Clinica,
    profesional: Profesional,
    reloj: RelojFijo,
) -> None:
    receta = await _receta(sesion, clinica, paciente, profesional, reloj)
    ruta = f"{api}/historia/pacientes/{paciente.id}/registros"
    r = await cliente.post(
        ruta,
        json=nuevo(especialidad, sede, tipo="RECETA", receta_id=str(receta.id), partidas=[]),
        headers=acceso,
    )
    assert r.status_code == 201, r.text
    pdf = await cliente.get(f"{ruta}/{r.json()['id']}/pdf", headers=acceso)
    assert "Cada 8 horas" in PdfReader(BytesIO(pdf.content)).pages[0].extract_text()
    receta.estado = "SUSPENDIDA"
    receta.suspendida_en = reloj.ahora()
    receta.motivo_suspension = "Prueba de suspensión"
    await sesion.flush()
    assert (await cliente.get(f"{ruta}/{r.json()['id']}/pdf", headers=acceso)).status_code == 404


@pytest.mark.parametrize("accion", ["listar", "crear", "anular", "pdf", "whatsapp"])
async def test_rutas_exigen_sesion(
    cliente: AsyncClient,
    api: str,
    paciente: Paciente,
    especialidad: Especialidad,
    sede: Sede,
    accion: str,
) -> None:
    ruta = f"{api}/historia/pacientes/{paciente.id}/registros"
    if accion == "listar":
        r = await cliente.get(ruta, params={"especialidad_id": str(especialidad.id)})
    elif accion == "crear":
        r = await cliente.post(ruta, json=nuevo(especialidad, sede))
    elif accion == "pdf":
        r = await cliente.get(f"{ruta}/{uuid.uuid4()}/pdf")
    else:
        r = await cliente.post(
            f"{ruta}/{uuid.uuid4()}/{'anulacion' if accion == 'anular' else 'whatsapp'}",
            json={
                "motivo": "Registro de prueba",
                "clave_idempotencia": str(uuid.uuid4()),
                "identidad_destinatario_confirmada": True,
            },
        )
    assert r.status_code == 401


async def test_paciente_ajeno_no_se_enumera(
    cliente: AsyncClient,
    api: str,
    acceso: dict[str, str],
    paciente_ajeno: Paciente,
    especialidad: Especialidad,
    sede: Sede,
) -> None:
    r = await cliente.post(
        f"{api}/historia/pacientes/{paciente_ajeno.id}/registros",
        json=nuevo(especialidad, sede),
        headers=acceso,
    )
    assert r.status_code == 404


@pytest.mark.parametrize("caso", ["sede_ajena", "especialidad_ajena", "N3", "cita_ajena"])
async def test_contexto_y_sensibilidad_restringidos(
    cliente, api, acceso, especialidad, sede, paciente, caso
):
    cambios = {
        "sede_ajena": {"sede_id": str(uuid.uuid4())},
        "especialidad_ajena": {"especialidad_id": str(uuid.uuid4())},
        "N3": {"nivel_sensibilidad": "N3"},
        "cita_ajena": {"cita_id": str(uuid.uuid4())},
    }[caso]
    r = await cliente.post(
        f"{api}/historia/pacientes/{paciente.id}/registros",
        json=nuevo(especialidad, sede, **cambios),
        headers=acceso,
    )
    assert r.status_code == (403 if caso == "N3" else 404), r.text


@pytest.mark.parametrize(
    "accion", ["listar", "crear", "pdf", "anular", "whatsapp", "zonas", "contextos", "plan"]
)
async def test_sin_permiso_no_accede(
    cliente, api, sesion, usuario, clinica, paciente, especialidad, sede, accion
):
    await conceder_permisos(sesion, usuario, clinica, "paciente.leer_administrativo")
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    ruta = f"{api}/historia/pacientes/{paciente.id}/registros"
    if accion == "listar":
        r = await cliente.get(
            ruta, params={"especialidad_id": str(especialidad.id)}, headers=cabeceras
        )
    elif accion == "crear":
        r = await cliente.post(ruta, json=nuevo(especialidad, sede), headers=cabeceras)
    elif accion == "zonas":
        r = await cliente.get(f"{api}/historia/faciograma/zonas", headers=cabeceras)
    elif accion == "contextos":
        r = await cliente.get(
            f"{api}/pacientes/{paciente.id}/contextos-atencion", headers=cabeceras
        )
    elif accion == "pdf":
        r = await cliente.get(f"{ruta}/{uuid.uuid4()}/pdf", headers=cabeceras)
    elif accion == "plan":
        r = await cliente.post(
            f"{api}/historia/planes/{uuid.uuid4()}/presupuesto-documento",
            json={"clave_idempotencia": str(uuid.uuid4())},
            headers=cabeceras,
        )
    else:
        r = await cliente.post(
            f"{ruta}/{uuid.uuid4()}/{'anulacion' if accion == 'anular' else 'whatsapp'}",
            json={
                "motivo": "Registro de prueba",
                "clave_idempotencia": str(uuid.uuid4()),
                "identidad_destinatario_confirmada": True,
            },
            headers=cabeceras,
        )
    assert r.status_code == 403, r.text


@pytest.mark.parametrize(
    "caso", ["importe_negativo", "motivo_corto", "zonas_repetidas", "tipo_inventado"]
)
async def test_validacion_entrada(cliente, api, acceso, especialidad, sede, paciente, caso):
    cambios = {
        "importe_negativo": {
            "partidas": [{"descripcion": "Sintético", "cantidad": 1, "precio_unitario": -1}]
        },
        "motivo_corto": {"motivo": "a"},
        "tipo_inventado": {"tipo": "INVENTADO"},
        "zonas_repetidas": {
            "tipo": "FACIOGRAMA",
            "partidas": [],
            "zonas": [{"zona": "pomulo_derecho", "observacion": "Sintética"}] * 2,
        },
    }[caso]
    r = await cliente.post(
        f"{api}/historia/pacientes/{paciente.id}/registros",
        json=nuevo(especialidad, sede, **cambios),
        headers=acceso,
    )
    assert r.status_code == 422


@pytest.mark.parametrize("accion", ["pdf", "anular", "whatsapp", "listar", "contextos"])
async def test_paciente_ajeno_todas_las_operaciones(
    cliente, api, acceso, especialidad, paciente_ajeno, accion
):
    ruta = f"{api}/historia/pacientes/{paciente_ajeno.id}/registros"
    if accion == "listar":
        r = await cliente.get(
            ruta, params={"especialidad_id": str(especialidad.id)}, headers=acceso
        )
    elif accion == "contextos":
        r = await cliente.get(
            f"{api}/pacientes/{paciente_ajeno.id}/contextos-atencion", headers=acceso
        )
    elif accion == "pdf":
        r = await cliente.get(f"{ruta}/{uuid.uuid4()}/pdf", headers=acceso)
    else:
        datos = (
            {"motivo": "Anulación sintética"}
            if accion == "anular"
            else {
                "clave_idempotencia": str(uuid.uuid4()),
                "identidad_destinatario_confirmada": True,
            }
        )
        r = await cliente.post(
            f"{ruta}/{uuid.uuid4()}/{'anulacion' if accion == 'anular' else 'whatsapp'}",
            json=datos,
            headers=acceso,
        )
    assert r.status_code == 404, r.text


@pytest.mark.parametrize(
    "caso", ["caducado", "bloqueado", "clinica_inactiva", "revocado", "version_sustituida"]
)
async def test_enlace_se_invalida(
    cliente, api, acceso, especialidad, sede, paciente, sesion, reloj, clinica, caso
):
    ruta = f"{api}/historia/pacientes/{paciente.id}/registros"
    registro = (await cliente.post(ruta, json=nuevo(especialidad, sede), headers=acceso)).json()
    sesion.add(
        Consentimiento(
            paciente_id=paciente.id,
            tipo="DOCUMENTOS_WHATSAPP",
            otorgado=True,
            version_texto="v1",
            texto_hash="0" * 64,
            canal="PRESENCIAL",
        )
    )
    await sesion.flush()
    entrega = (
        await cliente.post(
            f"{ruta}/{registro['id']}/whatsapp",
            json={
                "clave_idempotencia": str(uuid.uuid4()),
                "identidad_destinatario_confirmada": True,
            },
            headers=acceso,
        )
    ).json()
    fila = await sesion.get(EntregaDocumento, uuid.UUID(entrega["id"]))
    if caso == "caducado":
        fila.expira_en = reloj.ahora() - timedelta(seconds=1)
    elif caso == "revocado":
        fila.anulada = True
    elif caso == "clinica_inactiva":
        clinica.activa = False
    elif caso == "version_sustituida":
        r = await cliente.post(
            ruta,
            json=nuevo(
                especialidad,
                sede,
                raiz_id=registro["raiz_id"],
                version_base=1,
                motivo="Corrección sintética",
            ),
            headers=acceso,
        )
        assert r.status_code == 201
    else:
        token = entrega["enlace"].rsplit("/", 1)[1]
        for _ in range(5):
            incorrecto = await cliente.post(
                f"{api}/publico/documentos/{token}/acceso", json={"fecha_nacimiento": "2000-01-01"}
            )
            assert incorrecto.status_code == 401
    await sesion.flush()
    token = entrega["enlace"].rsplit("/", 1)[1]
    r = await cliente.post(
        f"{api}/publico/documentos/{token}/acceso", json={"fecha_nacimiento": "1990-04-12"}
    )
    assert r.status_code == 404, r.text


async def test_borrador_de_receta_no_emite_pdf(
    cliente, api, acceso, especialidad, sede, paciente, sesion, clinica, profesional
):
    receta = Receta(
        clinica_id=clinica.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        estado="BORRADOR",
    )
    sesion.add(receta)
    await sesion.flush()
    r = await cliente.post(
        f"{api}/historia/pacientes/{paciente.id}/registros",
        json=nuevo(especialidad, sede, tipo="RECETA", receta_id=str(receta.id), partidas=[]),
        headers=acceso,
    )
    assert r.status_code == 404


async def test_grupos_separados_y_paginados(cliente, api, acceso, especialidad, sede, paciente):
    ruta = f"{api}/historia/pacientes/{paciente.id}/registros"
    for tipo in ("PRESUPUESTO", "COTIZACION", "FACIOGRAMA"):
        datos = nuevo(
            especialidad, sede, tipo=tipo, **({"partidas": []} if tipo == "FACIOGRAMA" else {})
        )
        assert (await cliente.post(ruta, json=datos, headers=acceso)).status_code == 201
    documentos = await cliente.get(
        ruta,
        params={"especialidad_id": str(especialidad.id), "grupo": "documentos", "limite": 1},
        headers=acceso,
    )
    segundo = await cliente.get(
        ruta,
        params={
            "especialidad_id": str(especialidad.id),
            "grupo": "documentos",
            "limite": 1,
            "desplazamiento": 1,
        },
        headers=acceso,
    )
    facial = await cliente.get(
        ruta, params={"especialidad_id": str(especialidad.id), "grupo": "facial"}, headers=acceso
    )
    assert documentos.json()[0]["id"] != segundo.json()[0]["id"]
    assert [r["tipo"] for r in facial.json()] == ["FACIOGRAMA"]


async def test_plan_propuesto_genera_documento_persistente(
    cliente, api, acceso, sesion, usuario, clinica, profesional, paciente, especialidad, sede, reloj
):
    especialidad.codigo = "ODONTOLOGIA"
    especialidad.nombre = "Odontología sintética"
    await conceder_permisos(sesion, usuario, clinica, "plan_tratamiento.leer")
    plan = PlanTratamiento(
        clinica_id=clinica.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        titulo="Plan sintético",
        estado="PROPUESTO",
        propuesto_en=reloj.ahora(),
    )
    sesion.add(plan)
    await sesion.flush()
    sesion.add(
        ProcedimientoPlan(
            plan_id=plan.id, descripcion="Procedimiento sintético", precio=Decimal("45.50"), fase=1
        )
    )
    await sesion.flush()
    r = await cliente.post(
        f"{api}/historia/planes/{plan.id}/presupuesto-documento",
        json={"clave_idempotencia": str(uuid.uuid4()), "sede_id": str(sede.id)},
        headers=acceso,
    )
    assert r.status_code == 201, r.text
    assert r.json()["contenido"]["partidas"][0]["precio_unitario"] == "45.50"
    assert str(plan.id) in r.json()["contenido"]["observaciones"]


@pytest.mark.parametrize(
    "operacion",
    [
        "UPDATE registro_paciente SET titulo='Cambio directo' WHERE id=:id",
        "DELETE FROM registro_paciente WHERE id=:id",
    ],
)
async def test_bd_rechaza_modificar_o_borrar_historia(
    cliente, api, acceso, especialidad, sede, paciente, sesion, operacion
):
    r = await cliente.post(
        f"{api}/historia/pacientes/{paciente.id}/registros",
        json=nuevo(especialidad, sede),
        headers=acceso,
    )
    assert r.status_code == 201
    with pytest.raises(DBAPIError):
        async with sesion.begin_nested():
            await sesion.execute(text(operacion), {"id": uuid.UUID(r.json()["id"])})
    fila = await sesion.get(RegistroPaciente, uuid.UUID(r.json()["id"]))
    assert fila.titulo == "Presupuesto sintético"


@pytest.mark.parametrize(
    "caso", ["vigente", "caducado", "anulado", "consentimiento_revocado", "clinica_inactiva"]
)
async def test_worker_solo_entrega_documento_valido_y_consentido(
    cliente, api, acceso, especialidad, sede, paciente, sesion, reloj, clinica, caso
):
    ruta = f"{api}/historia/pacientes/{paciente.id}/registros"
    registro = (await cliente.post(ruta, json=nuevo(especialidad, sede), headers=acceso)).json()
    consentimiento = Consentimiento(
        paciente_id=paciente.id,
        tipo="DOCUMENTOS_WHATSAPP",
        otorgado=True,
        version_texto="v1",
        texto_hash="0" * 64,
        canal="PRESENCIAL",
    )
    sesion.add(consentimiento)
    await sesion.flush()
    respuesta = await cliente.post(
        f"{ruta}/{registro['id']}/whatsapp",
        json={"clave_idempotencia": str(uuid.uuid4()), "identidad_destinatario_confirmada": True},
        headers=acceso,
    )
    assert respuesta.status_code == 200, respuesta.text
    entrega = await sesion.get(EntregaDocumento, uuid.UUID(respuesta.json()["id"]))
    if caso == "caducado":
        entrega.expira_en = reloj.ahora() - timedelta(seconds=1)
    elif caso == "anulado":
        await cliente.post(
            f"{ruta}/{registro['id']}/anulacion",
            json={"motivo": "Retirada sintética"},
            headers=acceso,
        )
    elif caso == "consentimiento_revocado":
        consentimiento.revocado_en = reloj.ahora()
    elif caso == "clinica_inactiva":
        clinica.activa = False
    await sesion.flush()
    mensaje = await sesion.get(OutboxMensaje, entrega.outbox_id)
    canal = AdaptadorSandbox()
    canales = RegistroCanales()
    canales.registrar("WHATSAPP", canal)
    resumen = await ServicioOutbox(sesion, reloj, canales)._entregar(
        mensaje, ResumenProceso(tomados=1)
    )
    if caso == "vigente":
        assert resumen.entregados == 1
        assert len(canal.enviados) == 1
        assert "Consulta sintética" not in canal.enviados[0].mensaje.texto
        assert mensaje.referencia_externa.startswith("sandbox-")
    else:
        assert resumen.descartados == 1
        assert not canal.enviados
        assert mensaje.estado == "DESCARTADO"
