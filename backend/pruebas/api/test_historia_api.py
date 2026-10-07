"""Pruebas del contorno HTTP de la historia clinica.

Es la superficie mas sensible de la API. Lo que se verifica aqui:

* **La relacion asistencial se exige tambien por HTTP.** Tener el permiso y
  llamar al endpoint correcto no basta.
* **Toda lectura deja auditoria.** Es la unica forma de responder a «quien vio
  mi historia».
* **Una correccion sin motivo se rechaza en el borde**, antes de llegar al
  servicio.
* **Un PRN con frecuencia se rechaza con un mensaje que dice que hacer**, no
  con un error de integridad de la base.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.modelos import Auditoria
from app.modulos.historia.modelos import EstadoToma, NotaEvolucion, Receta, RecetaMedicamento, Toma
from app.modulos.organizacion.modelos import Clinica, Especialidad, Sede
from app.modulos.outbox.modelos import Recordatorio
from app.modulos.pacientes.modelos import AvisoAccesoEmergencia, Paciente, RelacionAsistencial
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.auditoria import AccionAuditada
from app.nucleo.seguridad import hashear_contrasena
from pruebas.api.conftest import CONTRASENA, cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]

PERMISOS_MEDICO = (
    "historia_clinica.leer",
    "historia_clinica.escribir",
    "diagnostico.registrar",
    "receta.crear",
    "receta.confirmar",
    "receta.leer",
    "adherencia.leer",
    "alerta_adherencia.atender",
)


def _ruta(api: str, sufijo: str) -> str:
    return f"{api}/historia{sufijo}"


@pytest_asyncio.fixture
async def relacion(
    sesion: AsyncSession, paciente: Paciente, profesional: Profesional
) -> RelacionAsistencial:
    registro = RelacionAsistencial(
        paciente_id=paciente.id, profesional_id=profesional.id, origen="CITA"
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


@pytest_asyncio.fixture
async def cabeceras_medico(
    cliente: AsyncClient,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    profesional: Profesional,
) -> dict[str, str]:
    """Usuario con permisos clinicos, ligado al profesional de las pruebas.

    El vinculo `usuario -> profesional` es lo que hace que el principal lleve
    `profesional_id`, y eso es lo que activa la comprobacion de relacion
    asistencial. Sin el, la prueba no mediria ese control.
    """
    await conceder_permisos(sesion, usuario, clinica, *PERMISOS_MEDICO, sedes=(sede.id,))
    return await cabecera_bearer(cliente, usuario, clinica)


def _cuerpo_nota(
    paciente: Paciente, profesional: Profesional, **extra: object
) -> dict[str, object]:
    base: dict[str, object] = {
        "paciente_id": str(paciente.id),
        "profesional_id": str(profesional.id),
        "tipo": "EVOLUCION",
        "motivo_consulta": "Control de prueba",
        "subjetivo": "Texto de prueba sin contenido clinico real.",
    }
    base.update(extra)
    return base


# ===========================================================================
#  Permisos y relacion asistencial
# ===========================================================================
class TestAcceso:
    async def test_acceso_emergencia_es_temporal_auditado_y_notifica_sin_datos_del_paciente(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        profesional: Profesional,
        paciente: Paciente,
    ) -> None:
        await conceder_permisos(
            sesion,
            usuario,
            clinica,
            "acceso_emergencia.solicitar",
            "auditoria.leer",
            "historia_clinica.leer",
            sedes=(sede.id,),
        )
        headers = await cabecera_bearer(cliente, usuario, clinica)
        ruta = _ruta(api, f"/pacientes/{paciente.id}/acceso-emergencia")
        respuesta = await cliente.post(
            ruta,
            headers=headers,
            json={"motivo": "Cobertura clínica urgente durante ausencia del profesional asignado."},
        )
        assert respuesta.status_code == 201, respuesta.text
        creado = respuesta.json()
        relacion = await sesion.get(RelacionAsistencial, creado["relacion_id"])
        assert relacion is not None
        assert relacion.origen == "EMERGENCIA"
        assert (
            relacion.motivo
            == "Cobertura clínica urgente durante ausencia del profesional asignado."
        )
        assert (relacion.vigente_hasta - relacion.creado_en).total_seconds() == 30 * 60

        # El vínculo concede la lectura que antes se denegaba, pero la
        # notificación administrativa no incluye paciente ni motivo.
        historia = await cliente.get(_ruta(api, f"/pacientes/{paciente.id}/notas"), headers=headers)
        assert historia.status_code == 200, historia.text
        cuenta = await cliente.get(_ruta(api, "/avisos-acceso-emergencia/cuenta"), headers=headers)
        avisos = await cliente.get(_ruta(api, "/avisos-acceso-emergencia"), headers=headers)
        assert cuenta.json() == {"cantidad": 1}
        assert avisos.status_code == 200
        assert paciente.id.hex not in avisos.text.replace("-", "")
        assert relacion.motivo not in avisos.text
        aviso_id = avisos.json()[0]["id"]
        aviso = await sesion.get(AvisoAccesoEmergencia, uuid.UUID(aviso_id))
        assert aviso is not None
        assert aviso.profesional_id == profesional.id

        repetido = await cliente.post(
            ruta,
            headers=headers,
            json={"motivo": "Cobertura clínica urgente durante ausencia del profesional asignado."},
        )
        assert repetido.status_code == 409

        revisado = await cliente.post(
            _ruta(api, f"/avisos-acceso-emergencia/{aviso_id}/revision"), headers=headers
        )
        assert revisado.status_code == 204
        assert (
            await cliente.get(_ruta(api, "/avisos-acceso-emergencia/cuenta"), headers=headers)
        ).json() == {"cantidad": 0}
        assert (
            await sesion.scalar(
                sa.select(sa.func.count())
                .select_from(Auditoria)
                .where(Auditoria.accion == AccionAuditada.ACCESO_EMERGENCIA.value)
            )
            == 1
        )

    async def test_sin_permiso_clinico_se_deniega(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        paciente: Paciente,
        paciente_ajeno: Paciente,
    ) -> None:
        """Recepcion no ve la historia clinica."""
        await conceder_permisos(
            sesion,
            usuario,
            clinica,
            "agenda.leer",
            "paciente.leer_administrativo",
            sedes=(sede.id,),
        )
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.get(
            _ruta(api, f"/pacientes/{paciente.id}/notas"), headers=cabeceras
        )

        assert respuesta.status_code == 404
        inexistente = await cliente.get(
            _ruta(api, f"/pacientes/{uuid.uuid4()}/notas"), headers=cabeceras
        )
        assert inexistente.status_code == 404
        assert {k: v for k, v in inexistente.json().items() if k != "correlacion_id"} == {
            k: v for k, v in respuesta.json().items() if k != "correlacion_id"
        }
        fuera_de_clinica = await cliente.get(
            _ruta(api, f"/pacientes/{paciente_ajeno.id}/notas"), headers=cabeceras
        )
        assert fuera_de_clinica.status_code == 404
        assert {k: v for k, v in fuera_de_clinica.json().items() if k != "correlacion_id"} == {
            k: v for k, v in respuesta.json().items() if k != "correlacion_id"
        }

    async def test_sin_relacion_asistencial_se_deniega(
        self,
        cliente: AsyncClient,
        api: str,
        cabeceras_medico: dict[str, str],
        paciente: Paciente,
        paciente_ajeno: Paciente,
        profesional: Profesional,
    ) -> None:
        """El permiso no basta: hace falta vinculo con ESE paciente.

        Sin este control, cualquier medico de la clinica leeria la historia de
        cualquier paciente. Es el acceso indebido mas frecuente y el mas
        dificil de justificar despues, porque quien lo hace si tiene permiso
        para leer historias.
        """
        respuesta = await cliente.post(
            _ruta(api, "/notas"),
            headers=cabeceras_medico,
            json=_cuerpo_nota(paciente, profesional),
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
        inexistente = await cliente.get(
            _ruta(api, f"/pacientes/{uuid.uuid4()}/notas"), headers=cabeceras_medico
        )
        assert inexistente.status_code == 404
        assert {k: v for k, v in inexistente.json().items() if k != "correlacion_id"} == {
            k: v for k, v in respuesta.json().items() if k != "correlacion_id"
        }
        fuera_de_clinica = await cliente.get(
            _ruta(api, f"/pacientes/{paciente_ajeno.id}/notas"), headers=cabeceras_medico
        )
        assert fuera_de_clinica.status_code == 404
        assert {k: v for k, v in fuera_de_clinica.json().items() if k != "correlacion_id"} == {
            k: v for k, v in respuesta.json().items() if k != "correlacion_id"
        }

    async def test_con_relacion_si_se_escribe(
        self,
        cliente: AsyncClient,
        api: str,
        cabeceras_medico: dict[str, str],
        relacion: RelacionAsistencial,
        paciente: Paciente,
        profesional: Profesional,
    ) -> None:
        respuesta = await cliente.post(
            _ruta(api, "/notas"),
            headers=cabeceras_medico,
            json=_cuerpo_nota(paciente, profesional),
        )

        assert respuesta.status_code == 201, respuesta.text
        cuerpo = respuesta.json()
        assert cuerpo["version"] == 1
        assert cuerpo["vigente"] is True
        assert cuerpo["raiz_id"] == cuerpo["id"]
        assert cuerpo["nivel_sensibilidad"] == "N2"

    async def test_nota_n3_requiere_permiso_se_filtra_y_audita_nivel(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        profesional: Profesional,
        paciente: Paciente,
        relacion: RelacionAsistencial,
        cabeceras_medico: dict[str, str],
    ) -> None:
        cuerpo_n3 = _cuerpo_nota(
            paciente,
            profesional,
            nivel_sensibilidad="N3",
            subjetivo="Contenido sensible sintético.",
        )
        denegada = await cliente.post(
            _ruta(api, "/notas"), headers=cabeceras_medico, json=cuerpo_n3
        )
        assert denegada.status_code == 403
        assert (
            await sesion.scalar(
                sa.select(sa.func.count())
                .select_from(NotaEvolucion)
                .where(NotaEvolucion.paciente_id == paciente.id)
            )
            == 0
        )

        await conceder_permisos(
            sesion,
            usuario,
            clinica,
            "historia_clinica.leer_sensible",
            sedes=(sede.id,),
        )
        creada = await cliente.post(_ruta(api, "/notas"), headers=cabeceras_medico, json=cuerpo_n3)
        assert creada.status_code == 201, creada.text
        nota_id = uuid.UUID(creada.json()["id"])
        assert creada.json()["nivel_sensibilidad"] == "N3"

        registro = await sesion.get(NotaEvolucion, nota_id)
        assert registro is not None and registro.nivel_sensibilidad == "N3"
        auditoria_alta = await sesion.scalar(
            sa.select(Auditoria)
            .where(Auditoria.accion == AccionAuditada.NOTA_CREADA.value)
            .where(Auditoria.entidad_id == nota_id)
        )
        assert auditoria_alta is not None
        assert auditoria_alta.nivel_sensibilidad == "N3"

        lector = Usuario(
            clinica_id=clinica.id,
            correo=f"lector-{uuid.uuid4().hex[:8]}@example.invalid",
            hash_contrasena=usuario.hash_contrasena,
            nombre="Lector",
            apellido="De Prueba",
        )
        sesion.add(lector)
        await sesion.flush()
        await conceder_permisos(
            sesion,
            lector,
            clinica,
            "historia_clinica.leer",
            sedes=(sede.id,),
        )
        cabeceras_lector = await cabecera_bearer(cliente, lector, clinica)

        lectura = await cliente.get(
            _ruta(api, f"/pacientes/{paciente.id}/notas"), headers=cabeceras_lector
        )
        assert lectura.status_code == 200, lectura.text
        assert lectura.json() == []
        historico = await cliente.get(
            _ruta(api, f"/pacientes/{paciente.id}/notas?incluir_historico=true"),
            headers=cabeceras_lector,
        )
        assert historico.status_code == 200, historico.text
        assert historico.json() == []

        auditoria_lectura = await sesion.scalar(
            sa.select(Auditoria)
            .where(Auditoria.accion == AccionAuditada.HISTORIA_CONSULTADA.value)
            .where(Auditoria.actor_id == lector.id)
        )
        assert auditoria_lectura is not None
        assert auditoria_lectura.nivel_sensibilidad == "N2"

    async def test_no_se_firma_una_nota_a_nombre_de_otro_profesional(
        self,
        cliente: AsyncClient,
        api: str,
        cabeceras_medico: dict[str, str],
        relacion: RelacionAsistencial,
        paciente: Paciente,
        sesion: AsyncSession,
        clinica: Clinica,
        especialidad: Especialidad,
    ) -> None:
        """El autor sale de la sesion. Antes se aceptaba cualquier profesional_id."""
        otro = Profesional(
            clinica_id=clinica.id,
            especialidad_id=especialidad.id,
            nombre="Otra",
            apellido="Persona",
            numero_registro_profesional=f"REG-{uuid.uuid4().hex[:8]}",
        )
        sesion.add(otro)
        await sesion.flush()

        respuesta = await cliente.post(
            _ruta(api, "/notas"),
            headers=cabeceras_medico,
            json=_cuerpo_nota(paciente, otro),
        )

        assert respuesta.status_code == 403
        total = await sesion.scalar(
            sa.select(sa.func.count())
            .select_from(NotaEvolucion)
            .where(NotaEvolucion.profesional_id == otro.id)
        )
        assert total == 0

    async def test_la_cita_de_otro_paciente_no_se_asocia(
        self,
        cliente: AsyncClient,
        api: str,
        cabeceras_medico: dict[str, str],
        relacion: RelacionAsistencial,
        paciente: Paciente,
        profesional: Profesional,
    ) -> None:
        respuesta = await cliente.post(
            _ruta(api, "/notas"),
            headers=cabeceras_medico,
            json=_cuerpo_nota(paciente, profesional, cita_id=str(uuid.uuid4())),
        )
        assert respuesta.status_code == 404


# ===========================================================================
#  Auditoria
# ===========================================================================
class TestAuditoria:
    async def test_leer_la_historia_deja_registro(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        cabeceras_medico: dict[str, str],
        relacion: RelacionAsistencial,
        usuario: Usuario,
        paciente: Paciente,
    ) -> None:
        """Sin este registro, el acceso por curiosidad no deja rastro."""
        respuesta = await cliente.get(
            _ruta(api, f"/pacientes/{paciente.id}/notas"), headers=cabeceras_medico
        )
        assert respuesta.status_code == 200

        entradas = list(
            (
                await sesion.execute(
                    sa.select(Auditoria).where(
                        Auditoria.accion == AccionAuditada.HISTORIA_CONSULTADA.value,
                        Auditoria.paciente_id == paciente.id,
                    )
                )
            ).scalars()
        )
        assert len(entradas) == 1
        assert entradas[0].actor_id == usuario.id
        assert entradas[0].nivel_sensibilidad == "N2"

    async def test_la_auditoria_no_lleva_contenido_clinico(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        cabeceras_medico: dict[str, str],
        relacion: RelacionAsistencial,
        paciente: Paciente,
        profesional: Profesional,
    ) -> None:
        """La auditoria registra referencias, nunca el texto de la nota.

        Si lo llevara, la tabla de auditoria seria una segunda copia de la
        historia clinica sin su control de acceso.
        """
        await cliente.post(
            _ruta(api, "/notas"),
            headers=cabeceras_medico,
            json=_cuerpo_nota(
                paciente, profesional, subjetivo="Texto que no debe aparecer en auditoria."
            ),
        )

        filas = list(
            (
                await sesion.execute(
                    # Acotada al paciente de la prueba (E-25): la base de desarrollo
                    # puede tener otras notas sinteticas.
                    sa.select(Auditoria).where(
                        Auditoria.accion == AccionAuditada.NOTA_CREADA.value,
                        Auditoria.paciente_id == paciente.id,
                    )
                )
            ).scalars()
        )
        assert len(filas) == 1
        assert "Texto que no debe aparecer" not in str(filas[0].metadatos or {})


# ===========================================================================
#  Versionado
# ===========================================================================
class TestCorreccion:
    @pytest_asyncio.fixture
    async def nota_creada(
        self,
        cliente: AsyncClient,
        api: str,
        cabeceras_medico: dict[str, str],
        relacion: RelacionAsistencial,
        paciente: Paciente,
        profesional: Profesional,
    ) -> dict[str, object]:
        respuesta = await cliente.post(
            _ruta(api, "/notas"),
            headers=cabeceras_medico,
            json=_cuerpo_nota(paciente, profesional),
        )
        assert respuesta.status_code == 201, respuesta.text
        cuerpo: dict[str, object] = respuesta.json()
        return cuerpo

    async def test_corregir_sin_motivo_se_rechaza_en_el_borde(
        self,
        cliente: AsyncClient,
        api: str,
        cabeceras_medico: dict[str, str],
        nota_creada: dict[str, object],
        paciente: Paciente,
        profesional: Profesional,
    ) -> None:
        respuesta = await cliente.post(
            _ruta(api, f"/notas/{nota_creada['raiz_id']}/correccion"),
            headers=cabeceras_medico,
            json=_cuerpo_nota(paciente, profesional),
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "DATOS_INVALIDOS"

    async def test_corregir_no_reduce_una_nota_n3(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        cabeceras_medico: dict[str, str],
        relacion: RelacionAsistencial,
        paciente: Paciente,
        profesional: Profesional,
    ) -> None:
        await conceder_permisos(
            sesion,
            usuario,
            clinica,
            "historia_clinica.leer_sensible",
            sedes=(sede.id,),
        )
        creada = await cliente.post(
            _ruta(api, "/notas"),
            headers=cabeceras_medico,
            json=_cuerpo_nota(paciente, profesional, nivel_sensibilidad="N3"),
        )
        assert creada.status_code == 201, creada.text
        cuerpo = _cuerpo_nota(paciente, profesional)
        cuerpo["motivo"] = "Corrección de prueba"
        corregida = await cliente.post(
            _ruta(api, f"/notas/{creada.json()['raiz_id']}/correccion"),
            headers=cabeceras_medico,
            json=cuerpo,
        )
        assert corregida.status_code == 200, corregida.text
        assert corregida.json()["nivel_sensibilidad"] == "N3"

        versiones = list(
            (
                await sesion.execute(
                    sa.select(NotaEvolucion)
                    .where(NotaEvolucion.raiz_id == uuid.UUID(creada.json()["raiz_id"]))
                    .order_by(NotaEvolucion.version)
                )
            ).scalars()
        )
        assert [nota.nivel_sensibilidad for nota in versiones] == ["N3", "N3"]

    async def test_un_motivo_demasiado_corto_se_rechaza(
        self,
        cliente: AsyncClient,
        api: str,
        cabeceras_medico: dict[str, str],
        nota_creada: dict[str, object],
        paciente: Paciente,
        profesional: Profesional,
    ) -> None:
        """«ok» no explica nada, y ante una reclamacion la pregunta es por que
        cambio la nota."""
        respuesta = await cliente.post(
            _ruta(api, f"/notas/{nota_creada['raiz_id']}/correccion"),
            headers=cabeceras_medico,
            json=_cuerpo_nota(paciente, profesional, motivo="ok"),
        )
        assert respuesta.status_code == 422

    async def test_corregir_crea_version_y_conserva_la_anterior(
        self,
        cliente: AsyncClient,
        api: str,
        cabeceras_medico: dict[str, str],
        nota_creada: dict[str, object],
        paciente: Paciente,
        profesional: Profesional,
    ) -> None:
        respuesta = await cliente.post(
            _ruta(api, f"/notas/{nota_creada['raiz_id']}/correccion"),
            headers=cabeceras_medico,
            json=_cuerpo_nota(
                paciente,
                profesional,
                subjetivo="Texto corregido.",
                motivo="Se corrigio la fecha de control indicada",
            ),
        )

        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["version"] == 2

        vigentes = await cliente.get(
            _ruta(api, f"/pacientes/{paciente.id}/notas"), headers=cabeceras_medico
        )
        completas = await cliente.get(
            _ruta(api, f"/pacientes/{paciente.id}/notas?incluir_historico=true"),
            headers=cabeceras_medico,
        )

        assert len(vigentes.json()) == 1
        assert len(completas.json()) == 2
        # La version anterior conserva su texto original.
        assert any(
            n["subjetivo"] == "Texto de prueba sin contenido clinico real."
            for n in completas.json()
        )

    async def test_una_nota_inexistente_responde_404(
        self,
        cliente: AsyncClient,
        api: str,
        cabeceras_medico: dict[str, str],
        relacion: RelacionAsistencial,
        paciente: Paciente,
        profesional: Profesional,
    ) -> None:
        respuesta = await cliente.post(
            _ruta(api, f"/notas/{uuid.uuid4()}/correccion"),
            headers=cabeceras_medico,
            json=_cuerpo_nota(paciente, profesional, motivo="Correccion de prueba"),
        )
        assert respuesta.status_code == 404


# ===========================================================================
#  Recetas
# ===========================================================================
class TestRecetas:
    def _cuerpo_receta(
        self, paciente: Paciente, profesional: Profesional, **medicamento: object
    ) -> dict[str, object]:
        base: dict[str, object] = {
            "nombre": "Medicamento de ejemplo",
            "dosis": "1 comprimido",
            "via": "ORAL",
            "frecuencia_horas": 12,
            "duracion_dias": 3,
        }
        base.update(medicamento)
        return {
            "paciente_id": str(paciente.id),
            "profesional_id": str(profesional.id),
            "medicamentos": [base],
        }

    async def test_n3_exige_permiso_y_se_devuelve_a_quien_tiene_permiso(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        cabeceras_medico: dict[str, str],
        relacion: RelacionAsistencial,
        paciente: Paciente,
        profesional: Profesional,
    ) -> None:
        cuerpo = self._cuerpo_receta(paciente, profesional)
        cuerpo["nivel_sensibilidad"] = "N3"
        denegada = await cliente.post(_ruta(api, "/recetas"), headers=cabeceras_medico, json=cuerpo)
        assert denegada.status_code == 403

        await conceder_permisos(
            sesion,
            usuario,
            clinica,
            "historia_clinica.leer_sensible",
            sedes=(sede.id,),
        )
        creada = await cliente.post(_ruta(api, "/recetas"), headers=cabeceras_medico, json=cuerpo)
        assert creada.status_code == 201, creada.text
        receta_id = uuid.UUID(creada.json()["id"])
        assert creada.json()["nivel_sensibilidad"] == "N3"

        lectura = await cliente.get(
            _ruta(api, f"/pacientes/{paciente.id}/recetas"), headers=cabeceras_medico
        )
        assert lectura.status_code == 200, lectura.text
        assert [item["id"] for item in lectura.json()] == [str(receta_id)]
        auditoria_lectura = await sesion.scalar(
            sa.select(Auditoria)
            .where(Auditoria.accion == AccionAuditada.RECETA_LEIDA.value)
            .where(Auditoria.entidad_id == receta_id)
        )
        assert auditoria_lectura is not None
        assert auditoria_lectura.nivel_sensibilidad == "N3"

        confirmada = await cliente.post(
            _ruta(api, f"/recetas/{receta_id}/confirmacion"),
            headers=cabeceras_medico,
            json={"profesional_id": str(profesional.id)},
        )
        assert confirmada.status_code == 200, confirmada.text
        versionada = await cliente.post(
            _ruta(api, f"/recetas/{receta_id}/versiones"),
            headers=cabeceras_medico,
            json={
                "profesional_id": str(profesional.id),
                "motivo": "Actualización revisada en consulta",
                "indicaciones_generales": "Pauta revisada.",
                "medicamentos": [
                    {
                        "nombre": "Medicamento de ejemplo",
                        "dosis": "1 comprimido",
                        "via": "ORAL",
                        "frecuencia_horas": 12,
                        "duracion_dias": 3,
                    }
                ],
            },
        )
        assert versionada.status_code == 201, versionada.text
        assert versionada.json()["receta"]["nivel_sensibilidad"] == "N3"

        usuario_sin_permiso_sensible = Usuario(
            clinica_id=clinica.id,
            correo=f"solo-n2-{uuid.uuid4().hex}@example.invalid",
            hash_contrasena=hashear_contrasena(CONTRASENA),
            nombre="Usuario",
            apellido="N2",
        )
        sesion.add(usuario_sin_permiso_sensible)
        await sesion.flush()
        await conceder_permisos(
            sesion,
            usuario_sin_permiso_sensible,
            clinica,
            "receta.leer",
            sedes=(sede.id,),
        )
        cabeceras_solo_n2 = await cabecera_bearer(cliente, usuario_sin_permiso_sensible, clinica)
        filtrada = await cliente.get(
            _ruta(api, f"/pacientes/{paciente.id}/recetas"), headers=cabeceras_solo_n2
        )
        assert filtrada.status_code == 200, filtrada.text
        assert filtrada.json() == []

    async def test_un_prn_con_frecuencia_se_rechaza_con_mensaje_util(
        self,
        cliente: AsyncClient,
        api: str,
        cabeceras_medico: dict[str, str],
        relacion: RelacionAsistencial,
        paciente: Paciente,
        profesional: Profesional,
    ) -> None:
        """Se rechaza en el borde, no con un error de integridad de la base.

        La restriccion CHECK existe y es la garantia real, pero un 500 con
        «viola la restriccion prn_sin_frecuencia» no le dice nada a quien
        escribe la receta.
        """
        respuesta = await cliente.post(
            _ruta(api, "/recetas"),
            headers=cabeceras_medico,
            json=self._cuerpo_receta(
                paciente, profesional, cuando_sea_necesario=True, frecuencia_horas=8
            ),
        )

        assert respuesta.status_code == 422
        assert "cuando sea necesario" in respuesta.text.lower()

    async def test_una_pauta_fija_sin_frecuencia_se_rechaza(
        self,
        cliente: AsyncClient,
        api: str,
        cabeceras_medico: dict[str, str],
        relacion: RelacionAsistencial,
        paciente: Paciente,
        profesional: Profesional,
    ) -> None:
        respuesta = await cliente.post(
            _ruta(api, "/recetas"),
            headers=cabeceras_medico,
            json=self._cuerpo_receta(paciente, profesional, frecuencia_horas=None),
        )
        assert respuesta.status_code == 422

    async def test_una_receta_nace_en_borrador(
        self,
        cliente: AsyncClient,
        api: str,
        cabeceras_medico: dict[str, str],
        relacion: RelacionAsistencial,
        paciente: Paciente,
        profesional: Profesional,
    ) -> None:
        respuesta = await cliente.post(
            _ruta(api, "/recetas"),
            headers=cabeceras_medico,
            json=self._cuerpo_receta(paciente, profesional),
        )

        assert respuesta.status_code == 201, respuesta.text
        assert respuesta.json()["estado"] == "BORRADOR"
        assert respuesta.json()["confirmada_en"] is None
        assert respuesta.json()["nivel_sensibilidad"] == "N2"

    async def test_confirmar_genera_las_tomas(
        self,
        cliente: AsyncClient,
        api: str,
        cabeceras_medico: dict[str, str],
        relacion: RelacionAsistencial,
        paciente: Paciente,
        profesional: Profesional,
    ) -> None:
        """3 dias cada 12 horas = 6 tomas."""
        creada = await cliente.post(
            _ruta(api, "/recetas"),
            headers=cabeceras_medico,
            json=self._cuerpo_receta(paciente, profesional),
        )
        receta_id = creada.json()["id"]

        respuesta = await cliente.post(
            _ruta(api, f"/recetas/{receta_id}/confirmacion"),
            headers=cabeceras_medico,
            json={"profesional_id": str(profesional.id)},
        )

        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["tomas_generadas"] == 6
        assert respuesta.json()["receta"]["estado"] == "CONFIRMADA"

    async def test_versionar_conserva_historial_y_reemplaza_solo_tomas_futuras(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        reloj,
        cabeceras_medico: dict[str, str],
        relacion: RelacionAsistencial,
        paciente: Paciente,
        profesional: Profesional,
        usuario: Usuario,
        clinica: Clinica,
    ) -> None:
        creada = await cliente.post(
            _ruta(api, "/recetas"),
            headers=cabeceras_medico,
            json=self._cuerpo_receta(paciente, profesional),
        )
        assert creada.status_code == 201, creada.text
        receta_anterior_id = creada.json()["id"]
        confirmada = await cliente.post(
            _ruta(api, f"/recetas/{receta_anterior_id}/confirmacion"),
            headers=cabeceras_medico,
            json={"profesional_id": str(profesional.id)},
        )
        assert confirmada.status_code == 200, confirmada.text

        # Dos tomas ya vencieron; las demas siguen siendo futuras. Renovar la
        # sesión permite probar el flujo sin depender del TTL del token.
        reloj.avanzar(hours=24)
        cabeceras_medico = await cabecera_bearer(cliente, usuario, clinica)
        versionada = await cliente.post(
            _ruta(api, f"/recetas/{receta_anterior_id}/versiones"),
            headers=cabeceras_medico,
            json={
                "profesional_id": str(profesional.id),
                "motivo": "Ajuste indicado en la consulta de seguimiento",
                "indicaciones_generales": "Nueva pauta revisada.",
                "medicamentos": [
                    {
                        "nombre": "Medicamento de ejemplo",
                        "dosis": "1 comprimido",
                        "via": "ORAL",
                        "frecuencia_horas": 12,
                        "duracion_dias": 3,
                    }
                ],
            },
        )

        assert versionada.status_code == 201, versionada.text
        cuerpo = versionada.json()
        receta_nueva_id = cuerpo["receta"]["id"]
        assert receta_nueva_id != receta_anterior_id
        assert cuerpo["receta"]["estado"] == "CONFIRMADA"
        assert cuerpo["receta"]["receta_anterior_id"] == receta_anterior_id
        assert cuerpo["tomas_canceladas"] == 4
        assert cuerpo["tomas_generadas"] == 6

        anterior = await sesion.get(Receta, uuid.UUID(receta_anterior_id))
        nueva = await sesion.get(Receta, uuid.UUID(receta_nueva_id))
        assert anterior is not None and anterior.estado == "SUSPENDIDA"
        assert anterior.motivo_suspension == "Ajuste indicado en la consulta de seguimiento"
        assert nueva is not None and nueva.receta_anterior_id == anterior.id

        estados_anteriores = (
            (
                await sesion.execute(
                    sa.select(Toma.estado)
                    .join(RecetaMedicamento, RecetaMedicamento.id == Toma.receta_medicamento_id)
                    .where(RecetaMedicamento.receta_id == anterior.id)
                )
            )
            .scalars()
            .all()
        )
        assert estados_anteriores.count(EstadoToma.PENDIENTE.value) == 2
        assert estados_anteriores.count(EstadoToma.CANCELADA.value) == 4

        total_nuevo = await sesion.scalar(
            sa.select(sa.func.count())
            .select_from(Toma)
            .join(RecetaMedicamento, RecetaMedicamento.id == Toma.receta_medicamento_id)
            .where(RecetaMedicamento.receta_id == nueva.id)
        )
        assert total_nuevo == 6

        recordatorios_anteriores = (
            (
                await sesion.execute(
                    sa.select(Recordatorio.estado).where(
                        Recordatorio.entidad_tipo == "TOMA",
                        Recordatorio.entidad_id.in_(
                            sa.select(Toma.id)
                            .join(
                                RecetaMedicamento,
                                RecetaMedicamento.id == Toma.receta_medicamento_id,
                            )
                            .where(RecetaMedicamento.receta_id == anterior.id)
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(recordatorios_anteriores) == 6
        assert set(recordatorios_anteriores) == {"CANCELADO"}

        recordatorios_nuevos = await sesion.scalar(
            sa.select(sa.func.count())
            .select_from(Recordatorio)
            .join(
                Toma,
                sa.and_(
                    Recordatorio.entidad_tipo == "TOMA",
                    Recordatorio.entidad_id == Toma.id,
                ),
            )
            .join(RecetaMedicamento, RecetaMedicamento.id == Toma.receta_medicamento_id)
            .where(
                RecetaMedicamento.receta_id == nueva.id,
                Recordatorio.estado == "PROGRAMADO",
            )
        )
        assert recordatorios_nuevos == 6

        acciones = (
            (
                await sesion.execute(
                    sa.select(Auditoria.accion).where(
                        Auditoria.entidad_id.in_([anterior.id, nueva.id]),
                        Auditoria.accion.in_(
                            [
                                AccionAuditada.RECETA_MODIFICADA.value,
                                AccionAuditada.RECETA_CONFIRMADA.value,
                                AccionAuditada.TOMAS_CANCELADAS.value,
                                AccionAuditada.TOMAS_GENERADAS.value,
                            ]
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert set(acciones) == {
            AccionAuditada.RECETA_MODIFICADA.value,
            AccionAuditada.RECETA_CONFIRMADA.value,
            AccionAuditada.TOMAS_CANCELADAS.value,
            AccionAuditada.TOMAS_GENERADAS.value,
        }

    async def test_un_prn_genera_cero_tomas_y_eso_esta_bien(
        self,
        cliente: AsyncClient,
        api: str,
        cabeceras_medico: dict[str, str],
        relacion: RelacionAsistencial,
        paciente: Paciente,
        profesional: Profesional,
    ) -> None:
        """Cero no es un fallo: convertir un PRN en pauta fija seria un error
        de medicacion. La interfaz muestra el numero para que quede claro."""
        creada = await cliente.post(
            _ruta(api, "/recetas"),
            headers=cabeceras_medico,
            json=self._cuerpo_receta(
                paciente,
                profesional,
                cuando_sea_necesario=True,
                frecuencia_horas=None,
                duracion_dias=None,
            ),
        )
        receta_id = creada.json()["id"]

        respuesta = await cliente.post(
            _ruta(api, f"/recetas/{receta_id}/confirmacion"),
            headers=cabeceras_medico,
            json={"profesional_id": str(profesional.id)},
        )

        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["tomas_generadas"] == 0

    async def test_confirmar_dos_veces_responde_409(
        self,
        cliente: AsyncClient,
        api: str,
        cabeceras_medico: dict[str, str],
        relacion: RelacionAsistencial,
        paciente: Paciente,
        profesional: Profesional,
    ) -> None:
        creada = await cliente.post(
            _ruta(api, "/recetas"),
            headers=cabeceras_medico,
            json=self._cuerpo_receta(paciente, profesional),
        )
        receta_id = creada.json()["id"]
        cuerpo = {"profesional_id": str(profesional.id)}

        await cliente.post(
            _ruta(api, f"/recetas/{receta_id}/confirmacion"), headers=cabeceras_medico, json=cuerpo
        )
        segunda = await cliente.post(
            _ruta(api, f"/recetas/{receta_id}/confirmacion"), headers=cabeceras_medico, json=cuerpo
        )

        assert segunda.status_code == 409

    async def test_suspender_exige_motivo(
        self,
        cliente: AsyncClient,
        api: str,
        cabeceras_medico: dict[str, str],
        relacion: RelacionAsistencial,
        paciente: Paciente,
        profesional: Profesional,
    ) -> None:
        creada = await cliente.post(
            _ruta(api, "/recetas"),
            headers=cabeceras_medico,
            json=self._cuerpo_receta(paciente, profesional),
        )
        receta_id = creada.json()["id"]

        respuesta = await cliente.post(
            _ruta(api, f"/recetas/{receta_id}/suspension"),
            headers=cabeceras_medico,
            json={"motivo": "no"},
        )
        assert respuesta.status_code == 422

    async def test_suspender_cancela_las_tomas_futuras(
        self,
        cliente: AsyncClient,
        api: str,
        cabeceras_medico: dict[str, str],
        relacion: RelacionAsistencial,
        paciente: Paciente,
        profesional: Profesional,
    ) -> None:
        creada = await cliente.post(
            _ruta(api, "/recetas"),
            headers=cabeceras_medico,
            json=self._cuerpo_receta(paciente, profesional),
        )
        receta_id = creada.json()["id"]
        await cliente.post(
            _ruta(api, f"/recetas/{receta_id}/confirmacion"),
            headers=cabeceras_medico,
            json={"profesional_id": str(profesional.id)},
        )

        respuesta = await cliente.post(
            _ruta(api, f"/recetas/{receta_id}/suspension"),
            headers=cabeceras_medico,
            json={"motivo": "El paciente refiere molestias"},
        )

        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["tomas_canceladas"] == 6
        assert respuesta.json()["receta"]["estado"] == "SUSPENDIDA"

    async def test_la_receta_de_otro_paciente_no_se_alcanza(
        self,
        cliente: AsyncClient,
        api: str,
        cabeceras_medico: dict[str, str],
        profesional: Profesional,
    ) -> None:
        # Firmante propio: lo que se mide es la receta inexistente, no la firma.
        respuesta = await cliente.post(
            _ruta(api, f"/recetas/{uuid.uuid4()}/confirmacion"),
            headers=cabeceras_medico,
            json={"profesional_id": str(profesional.id)},
        )
        assert respuesta.status_code == 404

    async def test_alerta_se_lista_y_se_atiende_por_http_con_auditoria(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        reloj,
        cabeceras_medico: dict[str, str],
        usuario: Usuario,
        clinica: Clinica,
        relacion: RelacionAsistencial,
        paciente: Paciente,
        profesional: Profesional,
    ) -> None:
        creada = await cliente.post(
            _ruta(api, "/recetas"),
            headers=cabeceras_medico,
            json=self._cuerpo_receta(paciente, profesional),
        )
        receta_id = creada.json()["id"]
        confirmada = await cliente.post(
            _ruta(api, f"/recetas/{receta_id}/confirmacion"),
            headers=cabeceras_medico,
            json={"profesional_id": str(profesional.id)},
        )
        assert confirmada.status_code == 200, confirmada.text
        reloj.avanzar(days=4)
        # Avanzar el reloj tambien vence el token de acceso; renovar la sesion
        # permite evaluar la receta con la identidad aun dentro de vigencia.
        cabeceras_medico = await cabecera_bearer(cliente, usuario, clinica)

        lectura = await cliente.get(
            _ruta(api, f"/recetas/{receta_id}/adherencia"),
            headers=cabeceras_medico,
            params={"dias": 10},
        )
        assert lectura.status_code == 405, lectura.text
        listado_sin_evaluar = await cliente.get(
            _ruta(api, "/adherencia/alertas"), headers=cabeceras_medico
        )
        assert listado_sin_evaluar.status_code == 200
        assert listado_sin_evaluar.json() == []

        evaluacion = await cliente.post(
            _ruta(api, f"/recetas/{receta_id}/adherencia"),
            headers=cabeceras_medico,
            params={"dias": 10},
        )
        assert evaluacion.status_code == 200, evaluacion.text
        alerta_id = evaluacion.json()["alerta"]["id"]
        listado = await cliente.get(_ruta(api, "/adherencia/alertas"), headers=cabeceras_medico)
        assert listado.status_code == 200, listado.text
        assert [alerta["id"] for alerta in listado.json()] == [alerta_id]

        atendida = await cliente.post(
            _ruta(api, f"/adherencia/alertas/{alerta_id}/atencion"),
            headers=cabeceras_medico,
            json={"nota_profesional": "Se reviso el registro con el paciente."},
        )
        assert atendida.status_code == 204, atendida.text
        listado_vacio = await cliente.get(
            _ruta(api, "/adherencia/alertas"), headers=cabeceras_medico
        )
        assert listado_vacio.status_code == 200
        assert listado_vacio.json() == []

        acciones = set(
            (
                await sesion.execute(
                    sa.select(Auditoria.accion).where(
                        Auditoria.accion.in_(
                            (
                                AccionAuditada.ALERTA_ADHERENCIA_CREADA.value,
                                AccionAuditada.ALERTA_ADHERENCIA_ATENDIDA.value,
                            )
                        )
                    )
                )
            ).scalars()
        )
        assert acciones == {
            AccionAuditada.ALERTA_ADHERENCIA_CREADA.value,
            AccionAuditada.ALERTA_ADHERENCIA_ATENDIDA.value,
        }
