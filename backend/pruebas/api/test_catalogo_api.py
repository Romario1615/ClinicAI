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

    async def test_lector_de_plan_puede_obtener_datos_publicos_de_su_clinica(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
    ) -> None:
        await conceder_permisos(sesion, usuario, clinica, "plan_tratamiento.leer", sedes=(sede.id,))
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.get(_ruta(api, "/catalogo/clinica"), headers=cabeceras)

        assert respuesta.status_code == 200
        assert respuesta.json()["id"] == str(clinica.id)
        assert respuesta.json()["nombre"] == clinica.nombre
        assert "identificacion_fiscal" not in respuesta.json()

    async def test_gestionar_sedes_filtra_ambito_y_edita_con_auditoria(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        otra_sede: Sede,
    ) -> None:
        await conceder_permisos(sesion, usuario, clinica, "sede.gestionar", sedes=(sede.id,))
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        lista = await cliente.get(_ruta(api, "/catalogo/sedes/gestion"), headers=cabeceras)
        assert lista.status_code == 200
        assert [item["id"] for item in lista.json()] == [str(sede.id)]
        assert str(otra_sede.id) not in lista.text

        respuesta = await cliente.put(
            _ruta(api, f"/catalogo/sedes/{sede.id}"),
            headers=cabeceras,
            json={
                "nombre": "Sede Norte",
                "direccion": "Av. Salud 456",
                "telefono": "+593 2 555 0101",
                "zona_horaria": "America/Guayaquil",
                "minutos_antelacion_minima": 90,
            },
        )
        assert respuesta.status_code == 200
        assert respuesta.json() == {
            "id": str(sede.id),
            "nombre": "Sede Norte",
            "direccion": "Av. Salud 456",
            "telefono": "+593 2 555 0101",
            "zona_horaria": "America/Guayaquil",
            "minutos_antelacion_minima": 90,
        }
        await sesion.refresh(sede)
        assert sede.nombre == "Sede Norte"
        assert sede.minutos_antelacion_minima == 90
        acciones = list(
            (
                await sesion.execute(
                    sa.select(Auditoria.accion).where(Auditoria.entidad_id == sede.id)
                )
            ).scalars()
        )
        assert acciones.count(AccionAuditada.SEDE_MODIFICADA.value) == 1

    async def test_gestionar_sede_de_otra_sede_devuelve_404(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        otra_sede: Sede,
    ) -> None:
        await conceder_permisos(sesion, usuario, clinica, "sede.gestionar", sedes=(sede.id,))
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.put(
            _ruta(api, f"/catalogo/sedes/{otra_sede.id}"),
            headers=cabeceras,
            json={
                "nombre": "Intento de edición",
                "direccion": None,
                "telefono": None,
                "zona_horaria": "America/Guayaquil",
                "minutos_antelacion_minima": 60,
            },
        )

        assert respuesta.status_code == 404
        await sesion.refresh(otra_sede)
        assert otra_sede.nombre.startswith("Sede Ajena")

    async def test_sede_rechaza_zona_horaria_invalida_y_nombre_duplicado(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        otra_sede: Sede,
    ) -> None:
        await conceder_permisos(
            sesion,
            usuario,
            clinica,
            "sede.gestionar",
            sedes=(sede.id, otra_sede.id),
        )
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)
        datos = {
            "nombre": "Sede nueva",
            "direccion": None,
            "telefono": None,
            "zona_horaria": "America/Guayaquil",
            "minutos_antelacion_minima": 60,
        }

        zona_invalida = await cliente.put(
            _ruta(api, f"/catalogo/sedes/{sede.id}"),
            headers=cabeceras,
            json={**datos, "zona_horaria": "Zona/Ficticia"},
        )
        assert zona_invalida.status_code == 422

        duplicada = await cliente.put(
            _ruta(api, f"/catalogo/sedes/{sede.id}"),
            headers=cabeceras,
            json={**datos, "nombre": otra_sede.nombre},
        )
        assert duplicada.status_code == 409

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

    async def test_gestion_de_consultorios_crea_edita_y_desactiva_con_auditoria(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
    ) -> None:
        await conceder_permisos(sesion, usuario, clinica, "sede.gestionar", sedes=(sede.id,))
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        creada = await cliente.post(
            _ruta(api, "/catalogo/consultorios"),
            headers=cabeceras,
            json={
                "sede_id": str(sede.id),
                "nombre": "Sala nueva",
                "tipo": "IMAGEN",
                "capacidad": 2,
            },
        )
        assert creada.status_code == 201
        consultorio_id = creada.json()["id"]
        assert creada.json()["activo"] is True

        editada = await cliente.put(
            _ruta(api, f"/catalogo/consultorios/{consultorio_id}"),
            headers=cabeceras,
            json={"nombre": "Sala radiología", "tipo": "IMAGEN", "capacidad": 3},
        )
        assert editada.status_code == 200
        assert editada.json()["nombre"] == "Sala radiología"
        assert editada.json()["capacidad"] == 3

        inactiva = await cliente.patch(
            _ruta(api, f"/catalogo/consultorios/{consultorio_id}/estado"),
            headers=cabeceras,
            json={"activo": False},
        )
        assert inactiva.status_code == 200
        assert inactiva.json()["activo"] is False
        gestion = await cliente.get(
            _ruta(api, "/catalogo/consultorios/gestion"),
            headers=cabeceras,
            params={"sede_id": str(sede.id)},
        )
        assert {c["id"] for c in gestion.json()} == {consultorio_id}
        assert gestion.json()[0]["activo"] is False
        acciones = list(
            (
                await sesion.execute(
                    sa.select(Auditoria.accion).where(
                        Auditoria.entidad_id == uuid.UUID(consultorio_id)
                    )
                )
            ).scalars()
        )
        assert acciones.count(AccionAuditada.CONSULTORIO_CREADO.value) == 1
        assert acciones.count(AccionAuditada.CONSULTORIO_MODIFICADO.value) == 2

    async def test_gestion_consultorios_no_admite_sede_fuera_del_ambito(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        otra_sede: Sede,
    ) -> None:
        await conceder_permisos(sesion, usuario, clinica, "sede.gestionar", sedes=(sede.id,))
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.post(
            _ruta(api, "/catalogo/consultorios"),
            headers=cabeceras,
            json={
                "sede_id": str(otra_sede.id),
                "nombre": "No autorizado",
                "tipo": "CONSULTA",
                "capacidad": 1,
            },
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"

    async def test_consultorio_rechaza_capacidad_invalida(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
    ) -> None:
        await conceder_permisos(sesion, usuario, clinica, "sede.gestionar", sedes=(sede.id,))
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.post(
            _ruta(api, "/catalogo/consultorios"),
            headers=cabeceras,
            json={
                "sede_id": str(sede.id),
                "nombre": "Sala inválida",
                "tipo": "CONSULTA",
                "capacidad": 0,
            },
        )

        assert respuesta.status_code == 422

    async def test_gestion_catalogo_crea_edita_y_archiva_especialidad_y_servicio(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
    ) -> None:
        await conceder_permisos(
            sesion,
            usuario,
            clinica,
            "especialidad.gestionar",
            "servicio.gestionar",
            todas_las_sedes=True,
        )
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        especialidad = await cliente.post(
            _ruta(api, "/catalogo/especialidades"),
            headers=cabeceras,
            json={
                "nombre": "Ortodoncia avanzada",
                "codigo": "ORT-AV",
                "descripcion": "Tratamientos de prueba",
            },
        )
        assert especialidad.status_code == 201
        especialidad_id = especialidad.json()["id"]
        assert especialidad.json()["codigo"] == "ORT-AV"

        servicio = await cliente.post(
            _ruta(api, "/catalogo/servicios"),
            headers=cabeceras,
            json={
                "especialidad_id": especialidad_id,
                "nombre": "Alineadores transparentes",
                "descripcion": "Servicio sintético de prueba",
                "duracion_minutos": 45,
                "minutos_preparacion": 10,
                "precio": "125.50",
                "moneda": "usd",
                "requiere_pago_previo": True,
                "instrucciones_preparacion": "Llegar diez minutos antes",
                "tipo_consultorio_requerido": "CONSULTA",
            },
        )
        assert servicio.status_code == 201
        servicio_id = servicio.json()["id"]
        assert servicio.json()["moneda"] == "USD"
        assert servicio.json()["precio"] == "125.50"

        especialidad_actualizada = await cliente.put(
            _ruta(api, f"/catalogo/especialidades/{especialidad_id}"),
            headers=cabeceras,
            json={
                "nombre": "Ortodoncia",
                "codigo": "ORT",
                "descripcion": "Especialidad actualizada",
            },
        )
        assert especialidad_actualizada.status_code == 200
        assert especialidad_actualizada.json()["nombre"] == "Ortodoncia"

        servicio_actualizado = await cliente.put(
            _ruta(api, f"/catalogo/servicios/{servicio_id}"),
            headers=cabeceras,
            json={
                "especialidad_id": especialidad_id,
                "nombre": "Alineadores",
                "descripcion": "Descripción actualizada",
                "duracion_minutos": 60,
                "minutos_preparacion": 5,
                "precio": "130.00",
                "moneda": "USD",
                "requiere_pago_previo": False,
                "instrucciones_preparacion": None,
                "tipo_consultorio_requerido": "PROCEDIMIENTOS",
            },
        )
        assert servicio_actualizado.status_code == 200
        assert servicio_actualizado.json()["duracion_minutos"] == 60

        conflicto = await cliente.patch(
            _ruta(api, f"/catalogo/especialidades/{especialidad_id}/estado"),
            headers=cabeceras,
            json={"activo": False},
        )
        assert conflicto.status_code == 409

        estado_servicio = await cliente.patch(
            _ruta(api, f"/catalogo/servicios/{servicio_id}/estado"),
            headers=cabeceras,
            json={"activo": False},
        )
        assert estado_servicio.status_code == 200
        estado_especialidad = await cliente.patch(
            _ruta(api, f"/catalogo/especialidades/{especialidad_id}/estado"),
            headers=cabeceras,
            json={"activo": False},
        )
        assert estado_especialidad.status_code == 200

        inventario_especialidades = await cliente.get(
            _ruta(api, "/catalogo/especialidades/gestion"), headers=cabeceras
        )
        inventario_servicios = await cliente.get(
            _ruta(api, "/catalogo/servicios/gestion"), headers=cabeceras
        )
        assert (
            next(e for e in inventario_especialidades.json() if e["id"] == especialidad_id)[
                "activa"
            ]
            is False
        )
        assert (
            next(s for s in inventario_servicios.json() if s["id"] == servicio_id)["activo"]
            is False
        )

        auditorias = list(
            (
                await sesion.execute(
                    sa.select(Auditoria.accion, Auditoria.entidad_id).where(
                        Auditoria.entidad_id.in_(
                            [uuid.UUID(especialidad_id), uuid.UUID(servicio_id)]
                        )
                    )
                )
            ).all()
        )
        acciones = [accion for accion, _ in auditorias]
        assert acciones.count(AccionAuditada.ESPECIALIDAD_CREADA.value) == 1
        assert acciones.count(AccionAuditada.ESPECIALIDAD_MODIFICADA.value) == 2
        assert acciones.count(AccionAuditada.SERVICIO_CREADO.value) == 1
        assert acciones.count(AccionAuditada.SERVICIO_MODIFICADO.value) == 2

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

    async def test_ficha_respeta_el_paciente_asignado_y_oculta_otros_ids(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        paciente: Paciente,
        sufijo: str,
    ) -> None:
        """IDOR: el alcance permite un paciente, no los demás identificadores.

        Incluye el caso más sensible de otra clínica y exige que su respuesta
        sea indistinguible de un UUID que no existe.
        """
        rol = await conceder_permisos(
            sesion,
            usuario,
            clinica,
            "paciente.leer_administrativo",
            todos_los_pacientes=False,
        )

        otro_local = Paciente(
            clinica_id=clinica.id,
            tipo_documento="CEDULA",
            numero_documento=f"7{sufijo[:9]}",
            nombre="Paciente",
            apellido="Fuera de ámbito",
        )
        otra_clinica = Clinica(
            nombre=f"Clínica ajena {sufijo}",
            identificacion_fiscal=f"AJENA-{sufijo}",
            zona_horaria="America/Guayaquil",
        )
        sesion.add_all([otro_local, otra_clinica])
        await sesion.flush()
        otro_externo = Paciente(
            clinica_id=otra_clinica.id,
            tipo_documento="CEDULA",
            numero_documento=f"6{sufijo[:9]}",
            nombre="Paciente",
            apellido="Otra clínica",
        )
        sesion.add(otro_externo)

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

        propio = await cliente.get(_ruta(api, f"/pacientes/{paciente.id}"), headers=cabeceras)
        ajeno_local = await cliente.get(
            _ruta(api, f"/pacientes/{otro_local.id}"), headers=cabeceras
        )
        ajeno_externo = await cliente.get(
            _ruta(api, f"/pacientes/{otro_externo.id}"), headers=cabeceras
        )
        inexistente = await cliente.get(_ruta(api, f"/pacientes/{uuid.uuid4()}"), headers=cabeceras)

        assert propio.status_code == 200
        for respuesta in (ajeno_local, ajeno_externo):
            assert respuesta.status_code == 404
            assert respuesta.json()["codigo"] == inexistente.json()["codigo"]
            assert respuesta.json()["mensaje"] == inexistente.json()["mensaje"]

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

        # Se mide el **incremento**, no el total. Contar la tabla entera acopla
        # la prueba a que nadie haya abierto nunca una ficha en la base de
        # desarrollo, contra la que corre esta suite; pasaba por el estado del
        # entorno y no por lo que afirma.
        consulta = (
            sa.select(sa.func.count())
            .select_from(Auditoria)
            .where(Auditoria.accion == AccionAuditada.PACIENTE_CONSULTADO.value)
        )
        antes = (await sesion.execute(consulta)).scalar_one()

        await cliente.get(
            _ruta(api, "/pacientes/"), headers=cabeceras, params={"termino": "Prueba"}
        )

        despues = (await sesion.execute(consulta)).scalar_one()
        assert despues == antes

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
