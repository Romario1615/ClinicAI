"""Pruebas del catalogo y de pacientes.

Estos endpoints parecen inofensivos -- "solo el catalogo" -- y son justo
donde una fuga pasa desapercibida. La lista de profesionales de una clinica
describe su plantilla; la de pacientes, a sus pacientes. Lo que se verifica
aqui es que **el ambito filtra en todos ellos**, uno por uno, porque basta con
que un solo endpoint lo olvide.

Tambien se comprueba lo que **no** sale: la identificacion fiscal de la
clinica, el telefono personal del profesional, y el hecho de que un paciente
fuera de ambito responda igual que uno inexistente.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.modelos import Auditoria
from app.modulos.organizacion.modelos import Clinica, Consultorio, Especialidad, Sede, Servicio
from app.modulos.pacientes.modelos import Paciente
from app.modulos.profesionales.modelos import Profesional, ProfesionalSede
from app.modulos.usuarios.modelos import AmbitoAsignacion, Usuario, UsuarioRol
from app.nucleo.auditoria import AccionAuditada
from app.nucleo.autorizacion import TipoAmbito
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


def _ruta(api: str, sufijo: str) -> str:
    return f"{api}{sufijo}"


# ===========================================================================
#  Catalogo
# ===========================================================================
class TestCatalogo:
    async def test_la_clinica_no_expone_la_identificacion_fiscal(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
    ) -> None:
        """El esquema de salida es explicito: solo sale lo declarado."""
        await conceder_permisos(sesion, usuario, clinica, "agenda.leer", sedes=(sede.id,))
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.get(_ruta(api, "/catalogo/clinica"), headers=cabeceras)

        assert respuesta.status_code == 200
        assert respuesta.json()["id"] == str(clinica.id)
        assert clinica.identificacion_fiscal is not None
        assert clinica.identificacion_fiscal not in respuesta.text
        assert "identificacion_fiscal" not in respuesta.text

    async def test_sin_permiso_el_catalogo_se_deniega(
        self,
        cliente: AsyncClient,
        api: str,
        usuario: Usuario,
        clinica: Clinica,
    ) -> None:
        """No es informacion publica: describe la plantilla de la clinica."""
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.get(_ruta(api, "/catalogo/sedes"), headers=cabeceras)

        assert respuesta.status_code == 403

    async def test_solo_se_ven_las_sedes_del_ambito(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        otra_sede: Sede,
    ) -> None:
        await conceder_permisos(sesion, usuario, clinica, "agenda.leer", sedes=(sede.id,))
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.get(_ruta(api, "/catalogo/sedes"), headers=cabeceras)

        identificadores = [s["id"] for s in respuesta.json()]
        assert identificadores == [str(sede.id)]
        assert str(otra_sede.id) not in respuesta.text

    async def test_con_el_comodin_se_ven_todas_las_sedes(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        otra_sede: Sede,
    ) -> None:
        await conceder_permisos(sesion, usuario, clinica, "agenda.leer", todas_las_sedes=True)
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.get(_ruta(api, "/catalogo/sedes"), headers=cabeceras)

        identificadores = {s["id"] for s in respuesta.json()}
        assert {str(sede.id), str(otra_sede.id)} <= identificadores

    async def test_la_sede_devuelve_la_zona_efectiva(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
    ) -> None:
        """La sede de las pruebas no fija zona: hereda la de la clinica.

        Se resuelve en el servidor para que el cliente no tenga que combinar
        dos respuestas y arriesgarse a mostrar la agenda en otro huso.
        """
        assert sede.zona_horaria is None
        await conceder_permisos(sesion, usuario, clinica, "agenda.leer", sedes=(sede.id,))
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.get(_ruta(api, "/catalogo/sedes"), headers=cabeceras)

        assert respuesta.json()[0]["zona_horaria"] == clinica.zona_horaria

    async def test_el_profesional_no_expone_su_contacto_personal(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        profesional: Profesional,
    ) -> None:
        """Un desplegable de la agenda no necesita su WhatsApp."""
        profesional.telefono_whatsapp = "+59399999999"
        profesional.correo_calendario = "profesional@example.invalid"
        await sesion.flush()

        await conceder_permisos(sesion, usuario, clinica, "agenda.leer", sedes=(sede.id,))
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.get(_ruta(api, "/catalogo/profesionales"), headers=cabeceras)

        assert respuesta.status_code == 200
        assert "+59399999999" not in respuesta.text
        assert "profesional@example.invalid" not in respuesta.text
        assert "telefono_whatsapp" not in respuesta.text

    async def test_un_profesional_en_dos_sedes_no_sale_duplicado(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        otra_sede: Sede,
        profesional: Profesional,
    ) -> None:
        """Con una union en lugar de EXISTS saldria una vez por sede.

        El desplegable mostraria a la misma persona repetida, y quien agenda
        no sabria cual elegir.
        """
        sesion.add_all(
            [
                ProfesionalSede(profesional_id=profesional.id, sede_id=sede.id, principal=True),
                ProfesionalSede(profesional_id=profesional.id, sede_id=otra_sede.id),
            ]
        )
        await sesion.flush()

        await conceder_permisos(sesion, usuario, clinica, "agenda.leer", todas_las_sedes=True)
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.get(_ruta(api, "/catalogo/profesionales"), headers=cabeceras)

        identificadores = [p["id"] for p in respuesta.json()]
        assert identificadores.count(str(profesional.id)) == 1

    async def test_pedir_una_sede_ajena_devuelve_lista_vacia(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        otra_sede: Sede,
        profesional: Profesional,
    ) -> None:
        """Vacio y no error: pedir una sede ajena tiene que ser
        indistinguible de pedir una sede sin profesionales."""
        sesion.add(ProfesionalSede(profesional_id=profesional.id, sede_id=otra_sede.id))
        await sesion.flush()

        await conceder_permisos(sesion, usuario, clinica, "agenda.leer", sedes=(sede.id,))
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.get(
            _ruta(api, "/catalogo/profesionales"),
            headers=cabeceras,
            params={"sede_id": str(otra_sede.id)},
        )

        assert respuesta.status_code == 200
        assert respuesta.json() == []

    async def test_los_servicios_se_filtran_por_especialidad(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        especialidad: Especialidad,
        servicio: Servicio,
    ) -> None:
        await conceder_permisos(sesion, usuario, clinica, "agenda.leer", sedes=(sede.id,))
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        propios = await cliente.get(
            _ruta(api, "/catalogo/servicios"),
            headers=cabeceras,
            params={"especialidad_id": str(especialidad.id)},
        )
        ajenos = await cliente.get(
            _ruta(api, "/catalogo/servicios"),
            headers=cabeceras,
            params={"especialidad_id": str(uuid.uuid4())},
        )

        assert [s["id"] for s in propios.json()] == [str(servicio.id)]
        assert ajenos.json() == []

    async def test_sin_ambito_de_especialidad_no_hay_servicios(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        servicio: Servicio,
    ) -> None:
        """Ambito vacio significa ningun acceso, no acceso a todo.

        Es la propiedad central del modelo de autorizacion: los comodines hay
        que concederlos de forma explicita. Si el conjunto vacio se
        interpretara como "sin restriccion", cualquier rol mal configurado
        veria la clinica entera.
        """
        await conceder_permisos(
            sesion,
            usuario,
            clinica,
            "agenda.leer",
            sedes=(sede.id,),
            todas_las_especialidades=False,
        )
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.get(_ruta(api, "/catalogo/servicios"), headers=cabeceras)

        assert respuesta.status_code == 200
        assert respuesta.json() == []
        assert str(servicio.id) not in respuesta.text

    async def test_los_consultorios_de_otra_sede_no_se_ven(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        otra_sede: Sede,
    ) -> None:
        propio = Consultorio(sede_id=sede.id, nombre="Consultorio propio")
        ajeno = Consultorio(sede_id=otra_sede.id, nombre="Consultorio ajeno")
        sesion.add_all([propio, ajeno])
        await sesion.flush()

        await conceder_permisos(sesion, usuario, clinica, "agenda.leer", sedes=(sede.id,))
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.get(_ruta(api, "/catalogo/consultorios"), headers=cabeceras)

        identificadores = [c["id"] for c in respuesta.json()]
        assert identificadores == [str(propio.id)]
        assert "Consultorio ajeno" not in respuesta.text

    async def test_un_profesional_fuera_de_ambito_responde_404(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        profesional: Profesional,
    ) -> None:
        """404 y no 403: un 403 confirmaria que ese profesional existe."""
        await conceder_permisos(
            sesion,
            usuario,
            clinica,
            "agenda.leer",
            sedes=(sede.id,),
            # Ambito de profesional vacio: no alcanza a ninguno.
            todos_los_profesionales=False,
        )
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.get(
            _ruta(api, f"/catalogo/profesionales/{profesional.id}"), headers=cabeceras
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"


# ===========================================================================
#  Pacientes
# ===========================================================================
class TestPacientes:
    async def test_sin_permiso_no_se_leen_pacientes(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
    ) -> None:
        await conceder_permisos(sesion, usuario, clinica, "agenda.leer", sedes=(sede.id,))
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.get(_ruta(api, "/pacientes/"), headers=cabeceras)

        assert respuesta.status_code == 403

    async def test_la_busqueda_encuentra_por_nombre_y_apellido(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        paciente: Paciente,
    ) -> None:
        await conceder_permisos(sesion, usuario, clinica, "paciente.leer_administrativo")
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.get(
            _ruta(api, "/pacientes/"), headers=cabeceras, params={"termino": "Prueba"}
        )

        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert str(paciente.id) in [p["id"] for p in cuerpo["elementos"]]
        assert cuerpo["total"] >= 1
        assert cuerpo["termino_ignorado"] is False

    async def test_un_termino_demasiado_corto_se_ignora_y_se_avisa(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        paciente: Paciente,
    ) -> None:
        """Sin el aviso, la interfaz diria "sin resultados".

        Y el usuario creeria que ese paciente no existe, cuando en realidad
        nunca se busco.
        """
        await conceder_permisos(sesion, usuario, clinica, "paciente.leer_administrativo")
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.get(
            _ruta(api, "/pacientes/"), headers=cabeceras, params={"termino": "ab"}
        )

        cuerpo = respuesta.json()
        assert cuerpo["elementos"] == []
        assert cuerpo["total"] == 0
        assert cuerpo["termino_ignorado"] is True

    async def test_la_busqueda_por_documento_es_exacta(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        paciente: Paciente,
    ) -> None:
        """Una busqueda parcial permitiria enumerar cedulas por prefijo."""
        await conceder_permisos(sesion, usuario, clinica, "paciente.leer_administrativo")
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)
        documento = paciente.numero_documento
        assert documento is not None

        exacta = await cliente.get(
            _ruta(api, "/pacientes/"), headers=cabeceras, params={"documento": documento}
        )
        parcial = await cliente.get(
            _ruta(api, "/pacientes/"), headers=cabeceras, params={"documento": documento[:4]}
        )

        assert [p["id"] for p in exacta.json()["elementos"]] == [str(paciente.id)]
        assert parcial.json()["elementos"] == []

    async def test_el_ambito_de_paciente_acota_la_busqueda(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        paciente: Paciente,
        sufijo: str,
    ) -> None:
        """Es el caso del propio paciente escribiendo por WhatsApp.

        Su principal solo alcanza su ficha; el personal tiene el comodin.
        """
        otro = Paciente(
            clinica_id=clinica.id,
            tipo_documento="CEDULA",
            numero_documento=f"8{sufijo[:9]}",
            nombre="Otro",
            apellido="Paciente",
        )
        sesion.add(otro)
        await sesion.flush()

        # Ambito limitado a un paciente concreto.
        rol = await conceder_permisos(
            sesion,
            usuario,
            clinica,
            "paciente.leer_administrativo",
            todos_los_pacientes=False,
        )
        asignacion = (
            await sesion.execute(sa.select(UsuarioRol).where(UsuarioRol.rol_id == rol.id))
        ).scalar_one()
        sesion.add(
            AmbitoAsignacion(
                usuario_rol_id=asignacion.id,
                tipo=TipoAmbito.PACIENTE.value,
                valor_id=paciente.id,
            )
        )
        await sesion.flush()

        cabeceras = await cabecera_bearer(cliente, usuario, clinica)
        respuesta = await cliente.get(_ruta(api, "/pacientes/"), headers=cabeceras)

        identificadores = [p["id"] for p in respuesta.json()["elementos"]]
        assert identificadores == [str(paciente.id)]
        assert respuesta.json()["total"] == 1

    async def test_un_paciente_fuera_de_ambito_responde_igual_que_uno_inexistente(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        paciente: Paciente,
    ) -> None:
        """Si se distinguieran, el 404 dejaria de proteger nada."""
        await conceder_permisos(
            sesion,
            usuario,
            clinica,
            "paciente.leer_administrativo",
            todos_los_pacientes=False,
        )
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        ajeno = await cliente.get(_ruta(api, f"/pacientes/{paciente.id}"), headers=cabeceras)
        inexistente = await cliente.get(_ruta(api, f"/pacientes/{uuid.uuid4()}"), headers=cabeceras)

        assert ajeno.status_code == inexistente.status_code == 404
        assert ajeno.json()["codigo"] == inexistente.json()["codigo"]
        assert ajeno.json()["mensaje"] == inexistente.json()["mensaje"]

    async def test_abrir_una_ficha_deja_auditoria(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        paciente: Paciente,
    ) -> None:
        """Ante «quien vio mis datos» tiene que haber respuesta.

        Sin este registro, un acceso por curiosidad -- el caso mas frecuente
        en una clinica -- no deja rastro.
        """
        await conceder_permisos(sesion, usuario, clinica, "paciente.leer_administrativo")
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.get(_ruta(api, f"/pacientes/{paciente.id}"), headers=cabeceras)
        assert respuesta.status_code == 200

        entradas = list(
            (
                await sesion.execute(
                    sa.select(Auditoria).where(
                        Auditoria.entidad_id == paciente.id,
                        Auditoria.accion == AccionAuditada.PACIENTE_CONSULTADO.value,
                    )
                )
            ).scalars()
        )
        assert len(entradas) == 1
        assert entradas[0].actor_id == usuario.id
        assert entradas[0].paciente_id == paciente.id
        assert entradas[0].nivel_sensibilidad == "N1"

    async def test_el_listado_no_audita_fila_por_fila(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        paciente: Paciente,
    ) -> None:
        """Auditar cada fila de cada busqueda ahogaria la consulta util.

        La que importa es quien abrio la ficha completa de una persona.
        """
        await conceder_permisos(sesion, usuario, clinica, "paciente.leer_administrativo")
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        await cliente.get(
            _ruta(api, "/pacientes/"), headers=cabeceras, params={"termino": "Prueba"}
        )

        entradas = (
            await sesion.execute(
                sa.select(sa.func.count())
                .select_from(Auditoria)
                .where(Auditoria.accion == AccionAuditada.PACIENTE_CONSULTADO.value)
            )
        ).scalar_one()
        assert entradas == 0

    async def test_la_ficha_no_incluye_datos_de_proceso_interno(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        paciente: Paciente,
    ) -> None:
        """`verificado_por` y `preferencias_horario` no son de la ficha."""
        await conceder_permisos(sesion, usuario, clinica, "paciente.leer_administrativo")
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.get(_ruta(api, f"/pacientes/{paciente.id}"), headers=cabeceras)

        assert respuesta.status_code == 200
        for campo in ("verificado_por", "verificado_en", "preferencias_horario", "creado_por"):
            assert campo not in respuesta.text, campo
