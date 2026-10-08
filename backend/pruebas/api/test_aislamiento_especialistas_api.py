"""Aislamiento entre especialistas, autoría y delegación; datos sintéticos."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita
from app.modulos.historia.modelos import (
    NotaEvolucion,
    PlantillaAnamnesis,
    Receta,
    RecetaMedicamento,
    RespuestaAnamnesis,
)
from app.modulos.imagenes.modelos import ImagenPaciente
from app.modulos.odontologia.modelos import (
    Formulario033,
    Odontograma,
    PlanTratamiento,
    RegistroPlaca,
)
from app.modulos.organizacion.modelos import Clinica, Especialidad, Sede, Servicio
from app.modulos.pacientes.modelos import Paciente, RelacionAsistencial
from app.modulos.profesionales.modelos import DelegacionFirma, Profesional
from app.modulos.usuarios.modelos import AmbitoAsignacion, Usuario, UsuarioRol
from app.nucleo.autorizacion import TipoAmbito
from app.nucleo.reloj import RelojFijo
from pruebas.api.conftest import cabecera_bearer, conceder_permisos
from pruebas.api.test_formulario_033_permisos_api import _captura_minima
from pruebas.api.test_historia_api import TestRecetas as CasosReceta
from pruebas.api.test_historia_api import _cuerpo_nota
from pruebas.api.test_imagenes_api import _png_sintetico

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def acceso_especialista(
    cliente: AsyncClient,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
    profesional: Profesional,
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
        "receta.leer",
        "receta.crear",
        "receta.confirmar",
        "imagen_clinica.leer",
        "imagen_clinica.cargar",
        "odontograma.leer",
        "odontograma.escribir",
        "plan_tratamiento.leer",
        "plan_tratamiento.escribir",
        "agenda.leer",
        sedes=(sede.id,),
        todas_las_especialidades=True,
    )
    return await cabecera_bearer(cliente, usuario, clinica)


@pytest_asyncio.fixture
async def colega(sesion: AsyncSession, clinica: Clinica, especialidad: Especialidad) -> Profesional:
    registro = Profesional(
        clinica_id=clinica.id,
        especialidad_id=especialidad.id,
        nombre="Colega",
        apellido="Sintético",
        numero_registro_profesional=uuid.uuid4().hex,
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


@pytest_asyncio.fixture
async def otro_especialista(sesion: AsyncSession, clinica: Clinica) -> Profesional:
    especialidad = Especialidad(
        clinica_id=clinica.id, nombre="Dermatología sintética", codigo="DERM"
    )
    sesion.add(especialidad)
    await sesion.flush()
    registro = Profesional(
        clinica_id=clinica.id,
        especialidad_id=especialidad.id,
        nombre="Otra especialista",
        apellido="Sintética",
        numero_registro_profesional=uuid.uuid4().hex,
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


async def test_ambito_efectivo_y_grant_explicito_se_revalidan_con_el_mismo_token(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    acceso_especialista: dict[str, str],
    especialidad: Especialidad,
    otro_especialista: Profesional,
) -> None:
    ruta = f"{api}/autenticacion/yo"
    actual = await cliente.get(ruta, headers=acceso_especialista)
    assert actual.status_code == 200, actual.text
    assert actual.json()["ambito"]["todas_las_especialidades"] is False
    assert actual.json()["ambito"]["especialidades"] == [str(especialidad.id)]
    asignacion = await sesion.scalar(select(UsuarioRol).where(UsuarioRol.usuario_id == usuario.id))
    assert asignacion is not None
    grant = AmbitoAsignacion(
        usuario_rol_id=asignacion.id,
        tipo=TipoAmbito.ESPECIALIDAD.value,
        valor_id=otro_especialista.especialidad_id,
    )
    sesion.add(grant)
    await sesion.flush()
    con_grant = await cliente.get(f"{api}/historia/especialidades", headers=acceso_especialista)
    assert {e["id"] for e in con_grant.json()} == {
        str(especialidad.id),
        str(otro_especialista.especialidad_id),
    }
    await sesion.delete(grant)
    await sesion.flush()
    sin_grant = await cliente.get(f"{api}/historia/especialidades", headers=acceso_especialista)
    assert [e["id"] for e in sin_grant.json()] == [str(especialidad.id)]


@pytest.mark.parametrize("misma_especialidad", [True, False])
async def test_nadie_corrige_notas_de_otro_autor(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    paciente: Paciente,
    profesional: Profesional,
    colega: Profesional,
    otro_especialista: Profesional,
    acceso_especialista: dict[str, str],
    misma_especialidad: bool,
) -> None:
    autor = colega if misma_especialidad else otro_especialista
    nota = NotaEvolucion(
        clinica_id=paciente.clinica_id,
        paciente_id=paciente.id,
        profesional_id=autor.id,
        motivo_consulta="Observación sintética reservada",
        tipo="EVOLUCION",
    )
    sesion.add(nota)
    await sesion.flush()
    consulta = await cliente.get(
        f"{api}/historia/pacientes/{paciente.id}/notas", headers=acceso_especialista
    )
    assert [n["id"] for n in consulta.json()] == ([str(nota.id)] if misma_especialidad else [])
    correccion = await cliente.post(
        f"{api}/historia/notas/{nota.raiz_id}/correccion",
        headers=acceso_especialista,
        json={**_cuerpo_nota(paciente, profesional), "motivo": "Intento de corrección ajena"},
    )
    assert correccion.status_code == (403 if misma_especialidad else 404), correccion.text
    await sesion.refresh(nota)
    assert nota.vigente and nota.profesional_id == autor.id
    assert (
        await sesion.scalar(
            select(func.count())
            .select_from(NotaEvolucion)
            .where(NotaEvolucion.raiz_id == nota.raiz_id)
        )
        == 1
    )


@pytest.mark.parametrize("misma_especialidad", [True, False])
async def test_imagenes_se_filtran_y_solo_el_creador_las_anula(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    paciente: Paciente,
    colega: Profesional,
    otro_especialista: Profesional,
    acceso_especialista: dict[str, str],
    misma_especialidad: bool,
) -> None:
    autor = colega if misma_especialidad else otro_especialista
    imagen = ImagenPaciente(
        clinica_id=paciente.clinica_id,
        paciente_id=paciente.id,
        profesional_id=autor.id,
        tipo="FOTO_EXTRAORAL",
        nivel_sensibilidad="N2",
        descripcion="Imagen sintética",
        tipo_mime="image/png",
        tamano_bytes=1,
        sha256="0" * 64,
        clave_objeto="sintetica-no-descargar",
        antivirus="NO_DISPONIBLE",
    )
    sesion.add(imagen)
    await sesion.flush()
    lista = await cliente.get(
        f"{api}/pacientes/{paciente.id}/imagenes", headers=acceso_especialista
    )
    assert lista.status_code == 200, lista.text
    assert [i["id"] for i in lista.json()] == ([str(imagen.id)] if misma_especialidad else [])
    anulacion = await cliente.patch(
        f"{api}/imagenes/{imagen.id}/anulacion",
        headers=acceso_especialista,
        json={"motivo": "Intento de anulación ajena"},
    )
    assert anulacion.status_code == (403 if misma_especialidad else 404), anulacion.text
    if not misma_especialidad:
        descarga = await cliente.get(
            f"{api}/imagenes/{imagen.id}/contenido", headers=acceso_especialista
        )
        assert descarga.status_code == 404, descarga.text
    await sesion.refresh(imagen)
    assert imagen.anulado_en is None


@pytest.mark.parametrize("operacion", ["confirmacion", "suspension", "versiones"])
async def test_receta_ajena_no_se_modifica_ni_se_firma_como_propia(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    paciente: Paciente,
    profesional: Profesional,
    colega: Profesional,
    acceso_especialista: dict[str, str],
    reloj: RelojFijo,
    operacion: str,
) -> None:
    receta = Receta(
        clinica_id=paciente.clinica_id,
        paciente_id=paciente.id,
        profesional_id=colega.id,
        estado="BORRADOR",
    )
    sesion.add(receta)
    await sesion.flush()
    if operacion != "confirmacion":
        receta.estado = "CONFIRMADA"
        receta.confirmada_en = reloj.ahora()
        receta.confirmada_por = colega.id
        await sesion.flush()
    payload: dict[str, object] = {"profesional_id": str(profesional.id)}
    if operacion == "suspension":
        payload = {"motivo": "Intento de suspensión ajena"}
    elif operacion == "versiones":
        payload.update(
            motivo="Intento de reemplazo ajeno",
            medicamentos=CasosReceta()._cuerpo_receta(paciente, profesional)["medicamentos"],
        )
    listado = await cliente.get(
        f"{api}/historia/pacientes/{paciente.id}/recetas", headers=acceso_especialista
    )
    assert listado.json()[0]["puede_gestionar"] is False
    resultado = await cliente.post(
        f"{api}/historia/recetas/{receta.id}/{operacion}",
        headers=acceso_especialista,
        json=payload,
    )
    assert resultado.status_code == 403, resultado.text
    await sesion.refresh(receta)
    assert receta.profesional_id == colega.id
    assert receta.estado == ("BORRADOR" if operacion == "confirmacion" else "CONFIRMADA")
    assert (
        await sesion.scalar(
            select(func.count()).select_from(Receta).where(Receta.paciente_id == paciente.id)
        )
        == 1
    )


async def test_recetas_vigentes_compartidas_y_delegacion_no_concede_notas_ajenas(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    paciente: Paciente,
    profesional: Profesional,
    otro_especialista: Profesional,
    acceso_especialista: dict[str, str],
    reloj: RelojFijo,
) -> None:
    receta = Receta(
        clinica_id=paciente.clinica_id,
        paciente_id=paciente.id,
        profesional_id=otro_especialista.id,
        estado="BORRADOR",
    )
    sesion.add(receta)
    await sesion.flush()
    sesion.add(
        RecetaMedicamento(
            receta_id=receta.id,
            nombre="Medicamento sintético",
            dosis="1 unidad",
            via="ORAL",
            frecuencia_horas=12,
            duracion_dias=1,
        )
    )
    await sesion.flush()
    ruta = f"{api}/historia/pacientes/{paciente.id}/recetas"
    assert (await cliente.get(ruta, headers=acceso_especialista)).json() == []
    delegacion = DelegacionFirma(
        clinica_id=paciente.clinica_id,
        delegante_id=otro_especialista.id,
        delegado_id=profesional.id,
        vigente_desde=reloj.ahora() - timedelta(hours=1),
        vigente_hasta=reloj.ahora() + timedelta(days=1),
        motivo="Cobertura sintética autorizada",
    )
    sesion.add(delegacion)
    await sesion.flush()
    lista = await cliente.get(ruta, headers=acceso_especialista)
    assert lista.json()[0]["puede_gestionar"] is True
    firmada = await cliente.post(
        f"{api}/historia/recetas/{receta.id}/confirmacion",
        headers=acceso_especialista,
        json={"profesional_id": str(otro_especialista.id)},
    )
    assert firmada.status_code == 200, firmada.text
    assert firmada.json()["receta"]["profesional_id"] == str(otro_especialista.id)
    assert firmada.json()["tomas_generadas"] == 2
    delegacion.revocada_en = reloj.ahora()
    await sesion.flush()
    lectura = await cliente.get(ruta, headers=acceso_especialista)
    assert lectura.json()[0]["puede_gestionar"] is False
    assert lectura.json()[0]["estado"] == "CONFIRMADA"
    suspension = await cliente.post(
        f"{api}/historia/recetas/{receta.id}/suspension",
        headers=acceso_especialista,
        json={"motivo": "Delegación ya revocada"},
    )
    assert suspension.status_code == 403, suspension.text
    # La delegación de firma no amplía las especialidades de historia.
    propias = await cliente.get(f"{api}/historia/especialidades", headers=acceso_especialista)
    assert str(otro_especialista.especialidad_id) not in propias.text


async def test_planes_y_odontograma_ajenos_no_se_exponen_por_id(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    paciente: Paciente,
    otro_especialista: Profesional,
    acceso_especialista: dict[str, str],
) -> None:
    plan = PlanTratamiento(
        clinica_id=paciente.clinica_id,
        paciente_id=paciente.id,
        profesional_id=otro_especialista.id,
        titulo="Plan sintético ajeno",
    )
    odontograma = Odontograma(
        clinica_id=paciente.clinica_id,
        paciente_id=paciente.id,
        profesional_id=otro_especialista.id,
        denticion="PERMANENTE",
        piezas={},
    )
    sesion.add_all([plan, odontograma])
    await sesion.flush()
    lista = await cliente.get(
        f"{api}/odontologia/pacientes/{paciente.id}/planes-tratamiento", headers=acceso_especialista
    )
    assert lista.json() == []
    presupuesto = await cliente.post(
        f"{api}/historia/planes/{plan.id}/presupuesto-documento",
        headers=acceso_especialista,
        json={"clave_idempotencia": str(uuid.uuid4())},
    )
    assert presupuesto.status_code == 404, presupuesto.text
    ruta = f"{api}/odontologia/pacientes/{paciente.id}/odontograma"
    lectura = await cliente.get(ruta, headers=acceso_especialista)
    assert lectura.status_code == 200 and lectura.json() is None
    versiones = await cliente.get(f"{ruta}/versiones", headers=acceso_especialista)
    assert versiones.status_code == 200 and versiones.json() == []
    correccion = await cliente.post(
        f"{ruta}/versiones",
        headers=acceso_especialista,
        json={
            "version_base": 1,
            "motivo": "No se cambia el registro ajeno",
            "denticion": "PERMANENTE",
            "piezas": {},
        },
    )
    assert correccion.status_code == 404, correccion.text
    await sesion.refresh(odontograma)
    assert odontograma.vigente


@pytest.mark.parametrize("misma_especialidad", [True, False])
async def test_formulario_033_reserva_especialidad_y_autoria(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    paciente: Paciente,
    sede: Sede,
    colega: Profesional,
    otro_especialista: Profesional,
    acceso_especialista: dict[str, str],
    misma_especialidad: bool,
) -> None:
    autor = colega if misma_especialidad else otro_especialista
    formulario = Formulario033(
        clinica_id=paciente.clinica_id,
        paciente_id=paciente.id,
        sede_id=sede.id,
        profesional_id=autor.id,
        contexto_identidad={},
        contenido=_captura_minima()["datos"],
    )
    sesion.add(formulario)
    await sesion.flush()
    ruta = f"{api}/odontologia/pacientes/{paciente.id}/formularios-033"
    lista = await cliente.get(ruta, headers=acceso_especialista)
    assert lista.status_code == 200, lista.text
    assert [f["id"] for f in lista.json()] == ([str(formulario.id)] if misma_especialidad else [])
    version = await cliente.post(
        f"{ruta}/{formulario.raiz_id}/versiones",
        headers=acceso_especialista,
        json={
            **_captura_minima(str(sede.id)),
            "version_base": 1,
            "motivo": "Intento de corregir el formulario ajeno",
        },
    )
    assert version.status_code == (403 if misma_especialidad else 404), version.text
    if not misma_especialidad:
        for sufijo in ("", "/versiones"):
            r = await cliente.get(
                f"{ruta}/{formulario.raiz_id}{sufijo}", headers=acceso_especialista
            )
            assert r.status_code == 404, r.text
        exportacion = await cliente.post(
            f"{ruta}/{formulario.raiz_id}/exportacion", headers=acceso_especialista
        )
        assert exportacion.status_code == 404, exportacion.text
    await sesion.refresh(formulario)
    assert formulario.vigente


@pytest.mark.parametrize("estado", ["inactivo", "anulado"])
async def test_perfil_desactivado_no_hereda_acceso_de_asistencia(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    paciente: Paciente,
    profesional: Profesional,
    acceso_especialista: dict[str, str],
    reloj: RelojFijo,
    estado: str,
) -> None:
    if estado == "inactivo":
        profesional.activo = False
    else:
        profesional.anulado_en = reloj.ahora()
    await sesion.flush()
    for ruta in (
        f"historia/pacientes/{paciente.id}/notas",
        f"historia/pacientes/{paciente.id}/recetas",
        f"pacientes/{paciente.id}/imagenes",
        f"odontologia/pacientes/{paciente.id}/odontograma",
    ):
        respuesta = await cliente.get(f"{api}/{ruta}", headers=acceso_especialista)
        esperado = 404 if ruta.endswith("/notas") else 403
        assert respuesta.status_code == esperado, respuesta.text


async def test_resumen_clinico_no_filtra_notas_ni_planes_de_otra_especialidad(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    paciente: Paciente,
    profesional: Profesional,
    otro_especialista: Profesional,
    acceso_especialista: dict[str, str],
) -> None:
    for autor in (profesional, otro_especialista):
        sesion.add(
            NotaEvolucion(
                clinica_id=paciente.clinica_id,
                paciente_id=paciente.id,
                profesional_id=autor.id,
                motivo_consulta=f"Nota sintética {autor.id}",
            )
        )
        sesion.add(
            PlanTratamiento(
                clinica_id=paciente.clinica_id,
                paciente_id=paciente.id,
                profesional_id=autor.id,
                titulo=f"Plan sintético {autor.id}",
            )
        )
    await sesion.flush()
    respuesta = await cliente.get(
        f"{api}/historia/pacientes/{paciente.id}/resumen-clinico", headers=acceso_especialista
    )
    assert respuesta.status_code == 200, respuesta.text
    assert [n["motivo_consulta"] for n in respuesta.json()["ultimas_notas"]] == [
        f"Nota sintética {profesional.id}"
    ]
    assert [p["titulo"] for p in respuesta.json()["planes"]] == [f"Plan sintético {profesional.id}"]
    assert str(otro_especialista.id) not in respuesta.text


async def test_anamnesis_y_periodoncia_respetan_el_area_del_autor(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    paciente: Paciente,
    profesional: Profesional,
    otro_especialista: Profesional,
    acceso_especialista: dict[str, str],
    reloj: RelojFijo,
) -> None:
    plantilla = PlantillaAnamnesis(
        clinica_id=paciente.clinica_id,
        nombre="Plantilla sintética de prueba",
        estado="PUBLICADA",
        publicada_en=reloj.ahora(),
        preguntas=[{"id": "contexto", "etiqueta": "Contexto", "tipo": "texto"}],
    )
    sesion.add(plantilla)
    await sesion.flush()
    propias = []
    for autor in (profesional, otro_especialista):
        respuesta = RespuestaAnamnesis(
            clinica_id=paciente.clinica_id,
            paciente_id=paciente.id,
            profesional_id=autor.id,
            plantilla_id=plantilla.id,
            version_plantilla=1,
            respuestas={"contexto": str(autor.id)},
        )
        placa = RegistroPlaca(
            clinica_id=paciente.clinica_id,
            paciente_id=paciente.id,
            profesional_id=autor.id,
            piezas_evaluadas=[16],
            superficies_con_placa={},
            total_superficies=4,
            total_con_placa=0,
            porcentaje=Decimal("0.00"),
        )
        sesion.add_all([respuesta, placa])
        await sesion.flush()
        if autor.id == profesional.id:
            propias = [str(respuesta.id), str(placa.id)]
    for ruta, esperado in zip(
        (
            f"historia/pacientes/{paciente.id}/anamnesis/respuestas",
            f"odontologia/pacientes/{paciente.id}/indice-placa",
        ),
        propias,
        strict=True,
    ):
        consulta = await cliente.get(f"{api}/{ruta}", headers=acceso_especialista)
        assert consulta.status_code == 200, consulta.text
        assert [fila["id"] for fila in consulta.json()] == [esperado]


@pytest.mark.parametrize("tipo", ["nota", "imagen", "documento"])
async def test_compartir_especialidad_no_permite_firmar_en_la_cita_del_colega(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    paciente: Paciente,
    profesional: Profesional,
    colega: Profesional,
    especialidad: Especialidad,
    servicio: Servicio,
    sede: Sede,
    acceso_especialista: dict[str, str],
    reloj: RelojFijo,
    tipo: str,
) -> None:
    cita = Cita(
        clinica_id=paciente.clinica_id,
        paciente_id=paciente.id,
        profesional_id=colega.id,
        servicio_id=servicio.id,
        sede_id=sede.id,
        estado="CONFIRMED",
        inicio=reloj.ahora() + timedelta(days=1),
        duracion_minutos=30,
        fin=reloj.ahora() + timedelta(days=1, minutes=30),
        clave_idempotencia=str(uuid.uuid4()),
        origen="PANEL",
    )
    sesion.add(cita)
    await sesion.flush()
    if tipo == "nota":
        resultado = await cliente.post(
            f"{api}/historia/notas",
            headers=acceso_especialista,
            json={
                **_cuerpo_nota(paciente, profesional),
                "cita_id": str(cita.id),
            },
        )
    elif tipo == "imagen":
        resultado = await cliente.post(
            f"{api}/pacientes/{paciente.id}/imagenes",
            headers=acceso_especialista,
            data={"tipo": "FOTO_EXTRAORAL", "cita_id": str(cita.id)},
            files={"archivo": ("sintetica.png", _png_sintetico(), "image/png")},
        )
    else:
        resultado = await cliente.post(
            f"{api}/historia/pacientes/{paciente.id}/registros",
            headers=acceso_especialista,
            json={
                "clave_idempotencia": str(uuid.uuid4()),
                "tipo": "PRESUPUESTO",
                "titulo": "Sintético",
                "especialidad_id": str(especialidad.id),
                "cita_id": str(cita.id),
                "sede_id": str(sede.id),
                "motivo": "Contexto sintético",
                "partidas": [{"descripcion": "Consulta", "cantidad": "1", "precio_unitario": "10"}],
            },
        )
    assert resultado.status_code == 404, resultado.text


async def test_editar_el_perfil_no_traslada_notas_historicas_a_otra_area(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    paciente: Paciente,
    clinica: Clinica,
    usuario: Usuario,
    sede: Sede,
    profesional: Profesional,
    otro_especialista: Profesional,
    acceso_especialista: dict[str, str],
) -> None:
    await conceder_permisos(sesion, usuario, clinica, "profesional.gestionar", sedes=(sede.id,))
    asignacion = await sesion.scalar(
        select(UsuarioRol).where(UsuarioRol.usuario_id == usuario.id).limit(1)
    )
    assert asignacion is not None
    sesion.add(
        AmbitoAsignacion(
            usuario_rol_id=asignacion.id,
            tipo=TipoAmbito.ESPECIALIDAD.value,
            valor_id=otro_especialista.especialidad_id,
        )
    )
    sesion.add(
        NotaEvolucion(
            clinica_id=paciente.clinica_id,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            motivo_consulta="Historia de su área original",
        )
    )
    await sesion.flush()
    original = profesional.especialidad_id
    resultado = await cliente.put(
        f"{api}/profesionales/gestion/{profesional.id}",
        headers=acceso_especialista,
        json={
            "especialidad_id": str(otro_especialista.especialidad_id),
            "nombre": profesional.nombre,
            "apellido": profesional.apellido,
            "sede_ids": [str(sede.id)],
            "sede_principal_id": str(sede.id),
        },
    )
    assert resultado.status_code == 409, resultado.text
    await sesion.refresh(profesional)
    assert profesional.especialidad_id == original
