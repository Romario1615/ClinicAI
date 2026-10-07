"""El Formulario 033 N3 exige permiso clínico y permiso sensible simultáneos."""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.modelos import Auditoria
from app.modulos.historia.modelos import NotaEvolucion
from app.modulos.odontologia.modelos import Formulario033, Odontograma, RegistroPlaca
from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.pacientes.modelos import Paciente, RelacionAsistencial
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.auditoria import AccionAuditada
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def api_base(
    cliente: AsyncClient,
) -> tuple[AsyncClient, str]:
    api = "/api/v1"
    return cliente, api


@pytest.mark.parametrize(
    "permiso",
    ["historia_clinica.leer", "historia_clinica.leer_sensible"],
)
async def test_lectura_exige_permiso_clinico_y_sensible(
    api_base: tuple[AsyncClient, str],
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    paciente: Paciente,
    permiso: str,
) -> None:
    cliente, api = api_base
    await conceder_permisos(sesion, usuario, clinica, permiso)
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    respuesta = await cliente.get(
        f"{api}/odontologia/pacientes/{paciente.id}/formularios-033", headers=cabeceras
    )
    assert respuesta.status_code == 403


@pytest.mark.parametrize(
    "permiso",
    ["historia_clinica.escribir", "historia_clinica.leer_sensible"],
)
async def test_escritura_exige_permiso_de_escritura_y_sensible(
    api_base: tuple[AsyncClient, str],
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    paciente: Paciente,
    permiso: str,
) -> None:
    cliente, api = api_base
    await conceder_permisos(sesion, usuario, clinica, permiso)
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    respuesta = await cliente.post(
        f"{api}/odontologia/pacientes/{paciente.id}/formularios-033",
        headers=cabeceras,
        json=_captura_minima(),
    )
    assert respuesta.status_code == 403


@pytest.mark.parametrize(
    "permiso",
    ["historia_clinica.leer", "historia_clinica.leer_sensible"],
)
async def test_exportacion_exige_permiso_clinico_y_sensible(
    api_base: tuple[AsyncClient, str],
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    paciente: Paciente,
    permiso: str,
) -> None:
    cliente, api = api_base
    await conceder_permisos(sesion, usuario, clinica, permiso)
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    respuesta = await cliente.post(
        f"{api}/odontologia/pacientes/{paciente.id}/formularios-033/raiz-inexistente/exportacion",
        headers=cabeceras,
    )
    assert respuesta.status_code == 403


@pytest_asyncio.fixture
async def cabeceras_con_acceso_033(
    cliente: AsyncClient,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    profesional: Profesional,
    paciente: Paciente,
) -> dict[str, str]:
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
        "historia_clinica.leer_sensible",
        sedes=(sede.id,),
    )
    return await cabecera_bearer(cliente, usuario, clinica)


async def test_captura_consulta_versiona_y_conserva_inmutables_las_versiones(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    cabeceras_con_acceso_033: dict[str, str],
    sede: Sede,
    paciente: Paciente,
) -> None:
    ruta = f"{api}/odontologia/pacientes/{paciente.id}/formularios-033"
    creada = await cliente.post(
        ruta,
        headers=cabeceras_con_acceso_033,
        json=_captura_minima(str(sede.id)),
    )
    assert creada.status_code == 201, creada.text
    version_1 = creada.json()
    assert version_1["version"] == 1
    assert version_1["contexto_identidad"]["sede"] == sede.nombre
    assert version_1["contexto_identidad"]["nombres"] == paciente.nombre

    actual = await cliente.get(ruta, headers=cabeceras_con_acceso_033)
    assert actual.status_code == 200
    assert [fila["raiz_id"] for fila in actual.json()] == [version_1["raiz_id"]]

    ruta_raiz = f"{ruta}/{version_1['raiz_id']}"
    correccion = _captura_minima(str(sede.id))
    correccion["version_base"] = 1
    correccion["motivo"] = "Se amplía el hallazgo"
    datos_correccion = correccion["datos"]
    assert isinstance(datos_correccion, dict)
    datos_correccion["motivo_consulta"] = "Control y reevaluación clínica"
    respuesta_version = await cliente.post(
        f"{ruta_raiz}/versiones", headers=cabeceras_con_acceso_033, json=correccion
    )
    assert respuesta_version.status_code == 201, respuesta_version.text
    assert respuesta_version.json()["version"] == 2
    assert respuesta_version.json()["vigente"] is True

    exportacion = await cliente.post(
        f"{ruta_raiz}/exportacion?version=2", headers=cabeceras_con_acceso_033
    )
    assert exportacion.status_code == 204
    evento = await sesion.scalar(
        sa.select(Auditoria).where(
            Auditoria.accion == AccionAuditada.FORMULARIO_033_EXPORTADO.value,
            Auditoria.entidad_id == respuesta_version.json()["id"],
        )
    )
    assert evento is not None
    assert evento.paciente_id == paciente.id
    assert evento.nivel_sensibilidad == "N3"
    assert evento.metadatos == {"version": 2, "formato": "A4", "destino": "impresion_local"}

    obsoleta = await cliente.post(
        f"{ruta_raiz}/versiones", headers=cabeceras_con_acceso_033, json=correccion
    )
    assert obsoleta.status_code == 409
    versiones = await cliente.get(f"{ruta_raiz}/versiones", headers=cabeceras_con_acceso_033)
    assert versiones.status_code == 200
    assert [fila["version"] for fila in versiones.json()] == [2, 1]

    fila = await sesion.scalar(
        sa.select(Formulario033).where(
            Formulario033.raiz_id == version_1["raiz_id"], Formulario033.version == 1
        )
    )
    assert fila is not None and fila.vigente is False
    with pytest.raises(DBAPIError):
        async with sesion.begin_nested():
            await sesion.execute(
                sa.update(Formulario033)
                .where(Formulario033.id == fila.id)
                .values(contenido={"motivo_consulta": "intento de alteración"})
            )


async def test_vincula_fuentes_clinicas_del_paciente_y_rechaza_fuentes_ajenas(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    cabeceras_con_acceso_033: dict[str, str],
    clinica: Clinica,
    sede: Sede,
    profesional: Profesional,
    paciente: Paciente,
    sufijo: str,
) -> None:
    nota = NotaEvolucion(
        clinica_id=clinica.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        tipo="EVOLUCION",
        motivo_consulta="Control sintético",
        creado_por=None,
    )
    odontograma = Odontograma(
        clinica_id=clinica.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        denticion="PERMANENTE",
        piezas={},
    )
    placa = RegistroPlaca(
        clinica_id=clinica.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        piezas_evaluadas=[16],
        superficies_con_placa={"16": ["V"]},
        total_superficies=4,
        total_con_placa=1,
        porcentaje=Decimal("25.00"),
    )
    sesion.add_all([nota, odontograma, placa])
    await sesion.flush()

    ruta = f"{api}/odontologia/pacientes/{paciente.id}/formularios-033"
    datos = _captura_minima(str(sede.id))
    datos.update(
        {
            "nota_id": str(nota.id),
            "odontograma_id": str(odontograma.id),
            "registro_placa_id": str(placa.id),
        }
    )
    creada = await cliente.post(ruta, headers=cabeceras_con_acceso_033, json=datos)
    assert creada.status_code == 201, creada.text
    assert creada.json()["nota_id"] == str(nota.id)
    assert creada.json()["odontograma_id"] == str(odontograma.id)
    assert creada.json()["registro_placa_id"] == str(placa.id)

    paciente_ajeno = Paciente(
        clinica_id=clinica.id,
        tipo_documento="CEDULA",
        numero_documento=f"8{sufijo[:9]}",
        nombre="Paciente Ajeno",
        apellido="Sintético",
    )
    sesion.add(paciente_ajeno)
    await sesion.flush()
    fuente_ajena = Odontograma(
        clinica_id=clinica.id,
        paciente_id=paciente_ajeno.id,
        profesional_id=profesional.id,
        denticion="PERMANENTE",
        piezas={},
    )
    sesion.add(fuente_ajena)
    await sesion.flush()
    datos_ajenos = _captura_minima(str(sede.id))
    datos_ajenos["odontograma_id"] = str(fuente_ajena.id)
    rechazada = await cliente.post(ruta, headers=cabeceras_con_acceso_033, json=datos_ajenos)
    assert rechazada.status_code == 404


def _captura_minima(sede_id: str = "00000000-0000-0000-0000-000000000001") -> dict[str, object]:
    regiones = [
        "LABIOS",
        "MEJILLAS",
        "MAXILAR_SUPERIOR",
        "MAXILAR_INFERIOR",
        "LENGUA",
        "PALADAR",
        "PISO_DE_LA_BOCA",
        "CARRILLOS",
        "GLANDULAS_SALIVALES",
        "OROFARINGE",
        "ATM",
        "GANGLIOS",
        "OTROS",
    ]
    piezas = [16, 17, 55, 11, 21, 51, 26, 27, 65, 36, 37, 75, 31, 41, 71, 46, 47, 85]
    return {
        "sede_id": sede_id,
        "datos": {
            "motivo_consulta": "Control clínico sintético",
            "embarazada": None,
            "enfermedad_actual": None,
            "antecedentes_personales": [],
            "antecedentes_familiares": [],
            "constantes_vitales": {},
            "examen_estomatognatico": [
                {"region": region, "hallazgo": "NO_EVALUADO"} for region in regiones
            ],
            "indicadores_salud_bucal": {"sitios": [{"pieza": pieza} for pieza in piezas]},
            "indices_cpo_ceo": {},
            "examenes_complementarios": [],
            "diagnosticos": [],
            "sesiones_tratamiento": [],
        },
    }
