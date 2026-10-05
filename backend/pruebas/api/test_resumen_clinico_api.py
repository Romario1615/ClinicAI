"""Resumen clínico para el profesional: acceso, contenido y redacción local."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ia.resumen_clinico import RedactorResumenClinico, _url_local
from app.modulos.historia.modelos import NotaEvolucion, Receta, RecetaMedicamento, Toma
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
        estado="CONFIRMADA",
        confirmada_en=ahora - timedelta(days=5),
        confirmada_por=profesional.id,
    )
    sesion.add(receta)
    await sesion.flush()
    medicamento = RecetaMedicamento(
        receta_id=receta.id,
        nombre="Medicamento sintético",
        dosis="1 unidad",
        via="ORAL",
        frecuencia_horas=12,
    )
    sesion.add(medicamento)
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
    profesional: Profesional,
) -> None:
    cabeceras = await _cabeceras(cliente, sesion, usuario, clinica, sede, "historia_clinica.leer")
    respuesta = await cliente.get(
        f"{api}/historia/pacientes/{paciente.id}/resumen-clinico", headers=cabeceras
    )
    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "RELACION_ASISTENCIAL_REQUERIDA"


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
    assert [a["descripcion"] for a in cuerpo["antecedentes"]] == ["Antecedente N2 sintético"]
    assert cuerpo["redaccion_disponible"] is False

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
    assert respuesta.status_code == 403


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
