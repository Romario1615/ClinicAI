"""Resumen clínico para el profesional: acceso, contenido y redacción local."""

from __future__ import annotations

import uuid
from datetime import timedelta

import httpx
import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ia.resumen_clinico import Redaccion, RedactorResumenClinico, _url_local
from app.modulos.auditoria.modelos import Auditoria
from app.modulos.historia.modelos import NotaEvolucion, Receta, RecetaMedicamento, Toma
from app.modulos.odontologia.modelos import PlanTratamiento
from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.pacientes.modelos import Alergia, Antecedente, Paciente, RelacionAsistencial
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.configuracion import Configuracion
from app.nucleo.errores import ProveedorExternoNoDisponible, ReglaNegocioViolada
from app.nucleo.reloj import RelojFijo
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def historia_sintetica(
    sesion: AsyncSession,
    clinica: Clinica,
    paciente: Paciente,
    profesional: Profesional,
    reloj: RelojFijo,
) -> None:
    ahora = reloj.ahora()
    sesion.add_all(
        [
            Alergia(
                paciente_id=paciente.id,
                sustancia="Sustancia sintética",
                severidad="GRAVE",
                registrado_por=profesional.id,
            ),
            Antecedente(
                paciente_id=paciente.id,
                categoria="PERSONAL",
                descripcion="Antecedente N2 sintético",
                registrado_por=profesional.id,
            ),
            Antecedente(
                paciente_id=paciente.id,
                categoria="PERSONAL",
                descripcion="Antecedente N3 sintético",
                registrado_por=profesional.id,
                nivel_sensibilidad="N3",
            ),
        ]
    )
    receta = Receta(
        clinica_id=clinica.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        estado="BORRADOR",
    )
    sesion.add(receta)
    await sesion.flush()
    # Las líneas solo se agregan en borrador; después se firma, como en la clínica.
    medicamento = RecetaMedicamento(
        receta_id=receta.id,
        nombre="Medicamento sintético",
        dosis="1 unidad",
        via="ORAL",
        frecuencia_horas=12,
    )
    sesion.add(medicamento)
    await sesion.flush()
    receta.estado = "CONFIRMADA"
    receta.confirmada_en = ahora - timedelta(days=5)
    receta.confirmada_por = profesional.id
    await sesion.flush()
    sesion.add_all(
        [
            Toma(
                receta_medicamento_id=medicamento.id,
                paciente_id=paciente.id,
                programada_en=ahora - timedelta(days=2),
                estado="TOMADA",
                registrada_en=ahora - timedelta(days=2),
            ),
            Toma(
                receta_medicamento_id=medicamento.id,
                paciente_id=paciente.id,
                programada_en=ahora - timedelta(days=1),
                estado="OMITIDA",
                registrada_en=ahora - timedelta(days=1),
            ),
            NotaEvolucion(
                clinica_id=clinica.id,
                paciente_id=paciente.id,
                profesional_id=profesional.id,
                motivo_consulta="Control sintético",
                plan="Revisar en dos semanas",
            ),
            NotaEvolucion(
                clinica_id=clinica.id,
                paciente_id=paciente.id,
                profesional_id=profesional.id,
                nivel_sensibilidad="N3",
                motivo_consulta="Nota N3 sintética",
                plan="Plan de nota N3 sintética",
            ),
        ]
    )
    await sesion.flush()


async def _cabeceras(
    cliente: AsyncClient,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    *permisos: str,
) -> dict[str, str]:
    await conceder_permisos(sesion, usuario, clinica, *permisos, sedes=(sede.id,))
    return await cabecera_bearer(cliente, usuario, clinica)


async def test_sin_relacion_asistencial_no_hay_resumen(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
    paciente_ajeno: Paciente,
    profesional: Profesional,
) -> None:
    cabeceras = await _cabeceras(cliente, sesion, usuario, clinica, sede, "historia_clinica.leer")
    respuesta = await cliente.get(
        f"{api}/historia/pacientes/{paciente.id}/resumen-clinico", headers=cabeceras
    )
    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    inexistente = await cliente.get(
        f"{api}/historia/pacientes/{uuid.uuid4()}/resumen-clinico", headers=cabeceras
    )
    assert inexistente.status_code == 404
    assert {k: v for k, v in inexistente.json().items() if k != "correlacion_id"} == {
        k: v for k, v in respuesta.json().items() if k != "correlacion_id"
    }
    fuera_de_clinica = await cliente.get(
        f"{api}/historia/pacientes/{paciente_ajeno.id}/resumen-clinico", headers=cabeceras
    )
    assert fuera_de_clinica.status_code == 404
    assert {k: v for k, v in fuera_de_clinica.json().items() if k != "correlacion_id"} == {
        k: v for k, v in respuesta.json().items() if k != "correlacion_id"
    }


async def test_resumen_estructurado_y_n3_solo_con_permiso_sensible(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
    profesional: Profesional,
    historia_sintetica: None,
) -> None:
    sesion.add(
        RelacionAsistencial(paciente_id=paciente.id, profesional_id=profesional.id, origen="CITA")
    )
    await sesion.flush()
    cabeceras = await _cabeceras(cliente, sesion, usuario, clinica, sede, "historia_clinica.leer")
    respuesta = await cliente.get(
        f"{api}/historia/pacientes/{paciente.id}/resumen-clinico", headers=cabeceras
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["alergias"][0]["severidad"] == "GRAVE"
    assert cuerpo["medicacion_activa"][0]["nombre"] == "Medicamento sintético"
    assert cuerpo["adherencia"]["tomadas"] == 1
    assert cuerpo["adherencia"]["omitidas"] == 1
    assert cuerpo["ultimas_notas"][0]["plan"] == "Revisar en dos semanas"
    assert all(nota["nivel_sensibilidad"] == "N2" for nota in cuerpo["ultimas_notas"])
    assert [a["descripcion"] for a in cuerpo["antecedentes"]] == ["Antecedente N2 sintético"]
    assert [a["nivel_sensibilidad"] for a in cuerpo["antecedentes"]] == ["N2"]
    assert cuerpo["redaccion_disponible"] is False

    cabeceras_n3 = await _cabeceras(
        cliente,
        sesion,
        usuario,
        clinica,
        sede,
        "historia_clinica.leer",
        "historia_clinica.leer_sensible",
    )
    con_sensible = await cliente.get(
        f"{api}/historia/pacientes/{paciente.id}/resumen-clinico", headers=cabeceras_n3
    )
    assert con_sensible.status_code == 200, con_sensible.text
    assert any(
        nota["nivel_sensibilidad"] == "N3" and nota["plan"] == "Plan de nota N3 sintética"
        for nota in con_sensible.json()["ultimas_notas"]
    )
    antecedentes = con_sensible.json()["antecedentes"]
    assert {(a["descripcion"], a["nivel_sensibilidad"]) for a in antecedentes} == {
        ("Antecedente N2 sintético", "N2"),
        ("Antecedente N3 sintético", "N3"),
    }
    auditoria_historia = (
        await sesion.scalars(
            sa.select(Auditoria).where(
                Auditoria.paciente_id == paciente.id,
                Auditoria.accion == "historia_clinica.consultada",
            )
        )
    ).all()
    assert any(evento.nivel_sensibilidad == "N3" for evento in auditoria_historia)

    sin_ia = await cliente.post(
        f"{api}/historia/pacientes/{paciente.id}/resumen-clinico/redaccion", headers=cabeceras
    )
    assert sin_ia.status_code == 422
    assert "IA local" in sin_ia.json()["mensaje"]


async def test_sin_permiso_de_historia_no_hay_resumen(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
) -> None:
    cabeceras = await _cabeceras(
        cliente, sesion, usuario, clinica, sede, "paciente.leer_administrativo"
    )
    respuesta = await cliente.get(
        f"{api}/historia/pacientes/{paciente.id}/resumen-clinico", headers=cabeceras
    )
    assert respuesta.status_code == 404
    inexistente = await cliente.get(
        f"{api}/historia/pacientes/{uuid.uuid4()}/resumen-clinico", headers=cabeceras
    )
    assert inexistente.status_code == 404
    assert {k: v for k, v in inexistente.json().items() if k != "correlacion_id"} == {
        k: v for k, v in respuesta.json().items() if k != "correlacion_id"
    }


async def test_profesional_gestiona_alergias_y_antecedentes_con_auditoria(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
    profesional: Profesional,
) -> None:
    cabeceras = await _cabeceras(
        cliente,
        sesion,
        usuario,
        clinica,
        sede,
        "historia_clinica.leer",
        "historia_clinica.escribir",
    )
    sin_relacion = await cliente.post(
        f"{api}/historia/pacientes/{paciente.id}/anamnesis/alergias",
        headers=cabeceras,
        json={"sustancia": "Penicilina", "severidad": "GRAVE"},
    )
    assert sin_relacion.status_code == 404
    sesion.add(
        RelacionAsistencial(paciente_id=paciente.id, profesional_id=profesional.id, origen="CITA")
    )
    await sesion.flush()

    alergia = await cliente.post(
        f"{api}/historia/pacientes/{paciente.id}/anamnesis/alergias",
        headers=cabeceras,
        json={
            "sustancia": "  Penicilina  ",
            "tipo_reaccion": "Urticaria",
            "severidad": "GRAVE",
        },
    )
    assert alergia.status_code == 201, alergia.text
    assert alergia.json()["sustancia"] == "Penicilina"
    duplicada = await cliente.post(
        f"{api}/historia/pacientes/{paciente.id}/anamnesis/alergias",
        headers=cabeceras,
        json={"sustancia": "penicilina", "severidad": "GRAVE"},
    )
    assert duplicada.status_code == 409

    antecedente = await cliente.post(
        f"{api}/historia/pacientes/{paciente.id}/anamnesis/antecedentes",
        headers=cabeceras,
        json={"categoria": "FAMILIAR", "descripcion": "Antecedente familiar sintético"},
    )
    assert antecedente.status_code == 201, antecedente.text
    resumen = await cliente.get(
        f"{api}/historia/pacientes/{paciente.id}/resumen-clinico", headers=cabeceras
    )
    assert resumen.status_code == 200, resumen.text
    assert [fila["sustancia"] for fila in resumen.json()["alergias"]] == ["Penicilina"]
    assert any(
        fila["descripcion"] == "Antecedente familiar sintético"
        for fila in resumen.json()["antecedentes"]
    )
    n3_sin_permiso = await cliente.post(
        f"{api}/historia/pacientes/{paciente.id}/anamnesis/antecedentes",
        headers=cabeceras,
        json={
            "categoria": "PERSONAL",
            "descripcion": "Antecedente sensible sintético",
            "nivel_sensibilidad": "N3",
        },
    )
    assert n3_sin_permiso.status_code == 403

    cabeceras_sensibles = await _cabeceras(
        cliente,
        sesion,
        usuario,
        clinica,
        sede,
        "historia_clinica.leer",
        "historia_clinica.escribir",
        "historia_clinica.leer_sensible",
    )
    n3 = await cliente.post(
        f"{api}/historia/pacientes/{paciente.id}/anamnesis/antecedentes",
        headers=cabeceras_sensibles,
        json={
            "categoria": "PERSONAL",
            "descripcion": "Antecedente sensible sintético",
            "nivel_sensibilidad": "N3",
        },
    )
    assert n3.status_code == 201, n3.text
    assert n3.json()["nivel_sensibilidad"] == "N3"

    desactivada = await cliente.post(
        f"{api}/historia/pacientes/{paciente.id}/anamnesis/alergias/{alergia.json()['id']}/desactivacion",
        headers=cabeceras,
        json={"motivo": "El profesional confirmó que fue un registro duplicado"},
    )
    assert desactivada.status_code == 200, desactivada.text
    assert desactivada.json()["id"] == alergia.json()["id"]
    resumen_actual = await cliente.get(
        f"{api}/historia/pacientes/{paciente.id}/resumen-clinico", headers=cabeceras
    )
    assert resumen_actual.status_code == 200
    assert resumen_actual.json()["alergias"] == []

    alergia_db = await sesion.get(Alergia, alergia.json()["id"])
    assert alergia_db is not None
    assert alergia_db.activa is False
    assert (
        alergia_db.motivo_desactivacion == "El profesional confirmó que fue un registro duplicado"
    )
    eventos = list(
        (
            await sesion.scalars(
                sa.select(Auditoria).where(
                    Auditoria.paciente_id == paciente.id,
                    Auditoria.accion.in_(("anamnesis.registrada", "alergia.desactivada")),
                )
            )
        ).all()
    )
    assert [evento.accion for evento in eventos].count("anamnesis.registrada") == 3
    assert [evento.accion for evento in eventos].count("alergia.desactivada") == 1
    assert all("Penicilina" not in str(evento.metadatos) for evento in eventos)
    assert all("Antecedente sensible sintético" not in str(evento.metadatos) for evento in eventos)
    assert any(evento.nivel_sensibilidad == "N3" for evento in eventos)


async def test_redaccion_local_no_recibe_registros_n3(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
    profesional: Profesional,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sesion.add_all(
        [
            RelacionAsistencial(
                paciente_id=paciente.id, profesional_id=profesional.id, origen="CITA"
            ),
            Antecedente(
                paciente_id=paciente.id,
                categoria="PERSONAL",
                descripcion="Antecedente N2 sintético",
                registrado_por=profesional.id,
                nivel_sensibilidad="N2",
            ),
            Antecedente(
                paciente_id=paciente.id,
                categoria="PERSONAL",
                descripcion="Antecedente N3 sintético",
                registrado_por=profesional.id,
                nivel_sensibilidad="N3",
            ),
            NotaEvolucion(
                clinica_id=clinica.id,
                paciente_id=paciente.id,
                profesional_id=profesional.id,
                motivo_consulta="Nota N2 sintética",
                plan="Plan de nota N2 sintética",
            ),
            NotaEvolucion(
                clinica_id=clinica.id,
                paciente_id=paciente.id,
                profesional_id=profesional.id,
                nivel_sensibilidad="N3",
                motivo_consulta="Nota N3 sintética",
                plan="Plan de nota N3 sintética",
            ),
            PlanTratamiento(
                clinica_id=clinica.id,
                paciente_id=paciente.id,
                profesional_id=profesional.id,
                titulo="Plan N2 sintético",
                nivel_sensibilidad="N2",
            ),
            PlanTratamiento(
                clinica_id=clinica.id,
                paciente_id=paciente.id,
                profesional_id=profesional.id,
                titulo="Plan N3 sintético",
                nivel_sensibilidad="N3",
            ),
        ]
    )
    await sesion.flush()
    cabeceras = await _cabeceras(
        cliente,
        sesion,
        usuario,
        clinica,
        sede,
        "historia_clinica.leer",
        "historia_clinica.leer_sensible",
    )
    recibida: dict[str, object] = {}

    class RedactorFalso:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def disponible(self) -> bool:
            return True

        async def redactar(self, datos: dict[str, object]) -> Redaccion:
            recibida.update(datos)
            return Redaccion(texto="Resumen de prueba.", modelo="local-sintetico")

    monkeypatch.setattr(
        "app.modulos.historia.resumen_clinico.RedactorResumenClinico", RedactorFalso
    )
    respuesta = await cliente.post(
        f"{api}/historia/pacientes/{paciente.id}/resumen-clinico/redaccion",
        headers=cabeceras,
    )

    assert respuesta.status_code == 200, respuesta.text
    antecedentes = recibida["antecedentes"]
    assert isinstance(antecedentes, list)
    assert [a["descripcion"] for a in antecedentes if isinstance(a, dict)] == [
        "Antecedente N2 sintético"
    ]
    notas = recibida["ultimas_notas"]
    assert isinstance(notas, list)
    assert [nota["plan"] for nota in notas if isinstance(nota, dict)] == [
        "Plan de nota N2 sintética"
    ]
    planes = recibida["planes"]
    assert isinstance(planes, list)
    assert [plan["titulo"] for plan in planes if isinstance(plan, dict)] == ["Plan N2 sintético"]


async def test_el_redactor_solo_usa_ia_local() -> None:
    assert _url_local("http://localhost:11434")
    assert _url_local("http://192.168.1.20:11434")
    assert _url_local("http://ollama:11434")
    assert not _url_local("https://api.ejemplo.com")
    assert not _url_local("http://8.8.8.8:11434")

    apagado = RedactorResumenClinico(Configuracion(proveedor_resumen_clinico="desactivado"))
    with pytest.raises(ReglaNegocioViolada):
        await apagado.redactar({})

    externo = RedactorResumenClinico(
        Configuracion(proveedor_resumen_clinico="ollama", ollama_url="https://api.ejemplo.com")
    )
    with pytest.raises(ReglaNegocioViolada):
        await externo.redactar({})

    recibido: dict[str, object] = {}

    def responder(peticion: httpx.Request) -> httpx.Response:
        recibido["cuerpo"] = peticion.content.decode()
        return httpx.Response(200, json={"response": "Alergias: Sustancia sintética."})

    cliente = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    local = RedactorResumenClinico(
        Configuracion(proveedor_resumen_clinico="ollama", ollama_url="http://localhost:11434"),
        cliente,
    )
    redaccion = await local.redactar({"alergias": [{"sustancia": "Sustancia sintética"}]})
    assert redaccion.texto.startswith("Alergias")
    assert "<datos>" in str(recibido["cuerpo"])
    assert "No diagnostiques" in str(recibido["cuerpo"])

    vacio = RedactorResumenClinico(
        Configuracion(proveedor_resumen_clinico="ollama", ollama_url="http://localhost:11434"),
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"response": ""}))
        ),
    )
    with pytest.raises(ProveedorExternoNoDisponible):
        await vacio.redactar({})
    caido = RedactorResumenClinico(
        Configuracion(proveedor_resumen_clinico="ollama", ollama_url="http://localhost:11434"),
        httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))),
    )
    with pytest.raises(ProveedorExternoNoDisponible):
        await caido.redactar({})
