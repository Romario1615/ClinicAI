"""Pruebas del contorno HTTP de la agenda.

Lo que se comprueba aqui, y no en las pruebas del servicio:

* **IDOR.** Que una cita de otra sede responda 404 y no 403, y que no se
  pueda leer, cancelar, reprogramar ni cerrar cambiando el identificador de
  la URL. Es el ataque mas barato contra una API de este tipo: no hace falta
  romper nada, solo probar identificadores.
* **Idempotencia.** Que repetir la creacion con la misma clave devuelva la
  cita ya creada y no una segunda.
* **Zonas horarias.** Que un instante sin zona se rechace en el borde
  (ADR-0010), en lugar de entrar y quedar interpretado como vengase.
* **Forma de la respuesta**: que el listado no arrastre las notas
  administrativas y que el total de la paginacion corresponda a los filtros
  aplicados.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita, EstadoCita
from app.modulos.organizacion.modelos import Clinica, Sede, Servicio
from app.modulos.pacientes.modelos import Paciente
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Usuario, UsuarioRol
from app.nucleo.reloj import RelojFijo
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.asyncio]

PERMISOS_RECEPCION = (
    "agenda.leer",
    "cita.crear",
    "cita.cancelar",
    "cita.reprogramar",
    "cita.completar",
    "cita.marcar_inasistencia",
)


def _ruta(api: str, sufijo: str = "") -> str:
    return f"{api}/agenda{sufijo}"


@pytest.fixture
def manana(reloj: RelojFijo) -> str:
    """Manana a las 15:00 UTC, en ISO-8601 con desplazamiento."""
    return (reloj.ahora() + timedelta(days=1, hours=1)).isoformat()


@pytest.fixture
def cuerpo_reserva(
    paciente: Paciente,
    profesional: Profesional,
    servicio: Servicio,
    sede: Sede,
    manana: str,
) -> dict[str, str]:
    return {
        "paciente_id": str(paciente.id),
        "profesional_id": str(profesional.id),
        "servicio_id": str(servicio.id),
        "sede_id": str(sede.id),
        "inicio": manana,
    }


async def _recepcion(
    cliente: AsyncClient,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
) -> dict[str, str]:
    """Usuario con permisos de recepcion y ambito sobre UNA sede."""
    await conceder_permisos(sesion, usuario, clinica, *PERMISOS_RECEPCION, sedes=(sede.id,))
    return await cabecera_bearer(cliente, usuario, clinica)


# ===========================================================================
#  Disponibilidad
# ===========================================================================
class TestDisponibilidad:
    async def test_devuelve_turnos_con_los_dos_finales(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        profesional: Profesional,
        servicio: Servicio,
        reloj: RelojFijo,
    ) -> None:
        """`fin_consulta` y `fin_bloque` no son lo mismo.

        El primero es lo que se le dice al paciente; el segundo incluye la
        preparacion y es lo que realmente se reserva. Mostrar el segundo diria
        que una consulta de 30 minutos dura 45.
        """
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)

        respuesta = await cliente.get(
            _ruta(api, "/disponibilidad"),
            headers=cabeceras,
            params={
                "profesional_id": str(profesional.id),
                "servicio_id": str(servicio.id),
                "sede_id": str(sede.id),
                "desde": (reloj.ahora() + timedelta(days=1)).isoformat(),
                "hasta": (reloj.ahora() + timedelta(days=2)).isoformat(),
            },
        )

        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo["zona_horaria"] == "America/Guayaquil"
        assert cuerpo["turnos"], "el horario amplio deberia producir turnos"
        turno = cuerpo["turnos"][0]
        assert turno["duracion_minutos"] == servicio.duracion_minutos
        assert turno["minutos_preparacion"] == servicio.minutos_preparacion
        assert turno["fin_consulta"] < turno["fin_bloque"]

    async def test_sin_permiso_de_agenda_se_deniega(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        profesional: Profesional,
        servicio: Servicio,
        reloj: RelojFijo,
    ) -> None:
        """La disponibilidad revela carga de trabajo y ausencias."""
        await conceder_permisos(sesion, usuario, clinica, "cita.crear", sedes=(sede.id,))
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.get(
            _ruta(api, "/disponibilidad"),
            headers=cabeceras,
            params={
                "profesional_id": str(profesional.id),
                "servicio_id": str(servicio.id),
                "sede_id": str(sede.id),
                "desde": (reloj.ahora() + timedelta(days=1)).isoformat(),
                "hasta": (reloj.ahora() + timedelta(days=2)).isoformat(),
            },
        )

        assert respuesta.status_code == 403

    async def test_una_sede_fuera_de_ambito_responde_404(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        otra_sede: Sede,
        profesional: Profesional,
        servicio: Servicio,
        reloj: RelojFijo,
    ) -> None:
        """404 y no 403: un 403 confirmaria que esa sede existe."""
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)

        respuesta = await cliente.get(
            _ruta(api, "/disponibilidad"),
            headers=cabeceras,
            params={
                "profesional_id": str(profesional.id),
                "servicio_id": str(servicio.id),
                "sede_id": str(otra_sede.id),
                "desde": (reloj.ahora() + timedelta(days=1)).isoformat(),
                "hasta": (reloj.ahora() + timedelta(days=2)).isoformat(),
            },
        )

        assert respuesta.status_code == 404

    async def test_un_instante_sin_zona_se_rechaza(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        profesional: Profesional,
        servicio: Servicio,
    ) -> None:
        """Un instante sin zona en una agenda medica desplaza citas (ADR-0010)."""
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)

        respuesta = await cliente.get(
            _ruta(api, "/disponibilidad"),
            headers=cabeceras,
            params={
                "profesional_id": str(profesional.id),
                "servicio_id": str(servicio.id),
                "sede_id": str(sede.id),
                "desde": "2026-04-16T09:00:00",
                "hasta": "2026-04-17T09:00:00",
            },
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "DATOS_INVALIDOS"
        assert "zona horaria" in respuesta.json()["mensaje"]

    async def test_una_ventana_demasiado_larga_se_rechaza(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        profesional: Profesional,
        servicio: Servicio,
        reloj: RelojFijo,
    ) -> None:
        """Proyectar un ano de agenda cargaria toda la ocupacion del periodo."""
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)

        respuesta = await cliente.get(
            _ruta(api, "/disponibilidad"),
            headers=cabeceras,
            params={
                "profesional_id": str(profesional.id),
                "servicio_id": str(servicio.id),
                "sede_id": str(sede.id),
                "desde": reloj.ahora().isoformat(),
                "hasta": (reloj.ahora() + timedelta(days=365)).isoformat(),
            },
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "DATOS_INVALIDOS"

    async def test_el_fin_anterior_al_inicio_se_rechaza(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        profesional: Profesional,
        servicio: Servicio,
        reloj: RelojFijo,
    ) -> None:
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)

        respuesta = await cliente.get(
            _ruta(api, "/disponibilidad"),
            headers=cabeceras,
            params={
                "profesional_id": str(profesional.id),
                "servicio_id": str(servicio.id),
                "sede_id": str(sede.id),
                "desde": (reloj.ahora() + timedelta(days=2)).isoformat(),
                "hasta": (reloj.ahora() + timedelta(days=1)).isoformat(),
            },
        )

        assert respuesta.status_code == 422


# ===========================================================================
#  Creacion
# ===========================================================================
class TestCreacion:
    async def test_crea_una_cita_confirmada(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        cuerpo_reserva: dict[str, str],
    ) -> None:
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)

        respuesta = await cliente.post(_ruta(api, "/citas"), headers=cabeceras, json=cuerpo_reserva)

        assert respuesta.status_code == 201
        cuerpo = respuesta.json()
        assert cuerpo["estado"] == EstadoCita.CONFIRMED.value
        assert cuerpo["expira_en"] is None
        # El esquema de salida es explicito: el listado no arrastra el texto
        # administrativo ni el rango de PostgreSQL.
        assert "notas_recepcion" not in cuerpo
        assert "rango" not in cuerpo
        assert "clave_idempotencia" not in cuerpo

    async def test_el_bloqueo_temporal_lleva_caducidad(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        cuerpo_reserva: dict[str, str],
    ) -> None:
        """Un bloqueo sin plazo retendria el turno para siempre."""
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)

        respuesta = await cliente.post(
            _ruta(api, "/citas/bloqueos"), headers=cabeceras, json=cuerpo_reserva
        )

        assert respuesta.status_code == 201
        cuerpo = respuesta.json()
        assert cuerpo["estado"] == EstadoCita.HELD.value
        assert cuerpo["expira_en"] is not None

    async def test_el_turno_ocupado_responde_409(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        cuerpo_reserva: dict[str, str],
    ) -> None:
        """Lo decide la restriccion de exclusion, no una comprobacion previa.

        Entre comprobar y escribir cabe otra reserva, y esa ventana es
        exactamente donde aparece la doble reserva (ADR-0009).
        """
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)
        primera = await cliente.post(_ruta(api, "/citas"), headers=cabeceras, json=cuerpo_reserva)
        assert primera.status_code == 201

        segunda = await cliente.post(_ruta(api, "/citas"), headers=cabeceras, json=cuerpo_reserva)

        assert segunda.status_code == 409

    async def test_la_misma_clave_de_idempotencia_no_crea_dos_citas(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        cuerpo_reserva: dict[str, str],
    ) -> None:
        """El caso real: la red corta la respuesta y el cliente reintenta."""
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)
        clave = {"Idempotency-Key": f"reserva-{uuid.uuid4().hex}"}

        primera = await cliente.post(
            _ruta(api, "/citas"), headers={**cabeceras, **clave}, json=cuerpo_reserva
        )
        segunda = await cliente.post(
            _ruta(api, "/citas"), headers={**cabeceras, **clave}, json=cuerpo_reserva
        )

        assert primera.status_code == 201
        assert segunda.status_code == 201
        assert primera.json()["id"] == segunda.json()["id"]

        total = (
            await sesion.execute(
                sa.select(sa.func.count()).select_from(Cita).where(Cita.clinica_id == clinica.id)
            )
        ).scalar_one()
        assert total == 1

    async def test_una_clave_de_idempotencia_invalida_se_rechaza(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        cuerpo_reserva: dict[str, str],
    ) -> None:
        """Sin limite, una clave de megabytes agota el almacenamiento."""
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)

        respuesta = await cliente.post(
            _ruta(api, "/citas"),
            headers={**cabeceras, "Idempotency-Key": "corta"},
            json=cuerpo_reserva,
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "DATOS_INVALIDOS"

    async def test_sin_permiso_de_creacion_se_deniega(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        cuerpo_reserva: dict[str, str],
    ) -> None:
        await conceder_permisos(sesion, usuario, clinica, "agenda.leer", sedes=(sede.id,))
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.post(_ruta(api, "/citas"), headers=cabeceras, json=cuerpo_reserva)

        assert respuesta.status_code == 403

    async def test_un_inicio_sin_zona_se_rechaza(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        cuerpo_reserva: dict[str, str],
    ) -> None:
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)

        respuesta = await cliente.post(
            _ruta(api, "/citas"),
            headers=cabeceras,
            json={**cuerpo_reserva, "inicio": "2026-04-16T10:00:00"},
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "DATOS_INVALIDOS"

    async def test_no_se_puede_elegir_el_origen_de_la_cita(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        cuerpo_reserva: dict[str, str],
    ) -> None:
        """Si viniera del cliente, se podrian falsear las metricas de canal.

        Y esas metricas son las que despues deciden donde invierte la clinica.
        """
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)

        respuesta = await cliente.post(
            _ruta(api, "/citas"),
            headers=cabeceras,
            json={**cuerpo_reserva, "origen": "WHATSAPP"},
        )

        assert respuesta.status_code == 422


# ===========================================================================
#  IDOR y ambito
# ===========================================================================
class TestAislamientoPorAmbito:
    @staticmethod
    async def _cita_en_sede_ajena(
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        otra_sede: Sede,
        cuerpo_reserva: dict[str, str],
    ) -> str:
        """Crea una cita en la sede ajena, con un usuario que si la alcanza."""
        rol = await conceder_permisos(
            sesion, usuario, clinica, *PERMISOS_RECEPCION, todas_las_sedes=True
        )
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)
        creada = await cliente.post(
            _ruta(api, "/citas"),
            headers=cabeceras,
            json={**cuerpo_reserva, "sede_id": str(otra_sede.id)},
        )
        assert creada.status_code == 201, creada.text

        # Se retira ese rol: a partir de aqui el usuario solo alcanza su sede.
        await sesion.execute(sa.delete(UsuarioRol).where(UsuarioRol.rol_id == rol.id))
        await sesion.flush()
        cita_id: str = creada.json()["id"]
        return cita_id

    async def test_no_se_lee_una_cita_de_otra_sede(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        otra_sede: Sede,
        cuerpo_reserva: dict[str, str],
    ) -> None:
        """404 y no 403: un 403 permitiria enumerar la agenda de la clinica."""
        cita_id = await self._cita_en_sede_ajena(
            cliente, api, sesion, usuario, clinica, otra_sede, cuerpo_reserva
        )
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)

        respuesta = await cliente.get(_ruta(api, f"/citas/{cita_id}"), headers=cabeceras)

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"

    @pytest.mark.parametrize(
        ("sufijo_ruta", "cuerpo"),
        [
            ("/confirmacion", None),
            ("/cancelacion", {"motivo": "Prueba de acceso indebido"}),
            ("/completado", None),
            ("/inasistencia", None),
            (
                "/reprogramacion",
                {"nuevo_inicio": "2026-04-20T15:00:00+00:00", "motivo": "Prueba"},
            ),
        ],
    )
    async def test_no_se_modifica_una_cita_de_otra_sede(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        otra_sede: Sede,
        cuerpo_reserva: dict[str, str],
        sufijo_ruta: str,
        cuerpo: dict[str, str] | None,
    ) -> None:
        """Cada transicion de estado, por separado.

        Basta con que una sola de ellas olvide el filtro de ambito para que la
        agenda de otra sede sea modificable desde fuera.
        """
        cita_id = await self._cita_en_sede_ajena(
            cliente, api, sesion, usuario, clinica, otra_sede, cuerpo_reserva
        )
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)

        respuesta = await cliente.post(
            _ruta(api, f"/citas/{cita_id}{sufijo_ruta}"),
            headers=cabeceras,
            json=cuerpo if cuerpo is not None else None,
        )

        assert respuesta.status_code == 404, respuesta.text

    async def test_el_listado_no_incluye_las_citas_de_otra_sede(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        otra_sede: Sede,
        cuerpo_reserva: dict[str, str],
    ) -> None:
        await self._cita_en_sede_ajena(
            cliente, api, sesion, usuario, clinica, otra_sede, cuerpo_reserva
        )
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)

        respuesta = await cliente.get(_ruta(api, "/citas"), headers=cabeceras)

        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo["elementos"] == []
        # El total tambien respeta el ambito: si contara sin filtrar, diria
        # cuantas citas tiene la clinica entera.
        assert cuerpo["total"] == 0

    async def test_una_cita_inexistente_responde_igual_que_una_ajena(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        otra_sede: Sede,
        cuerpo_reserva: dict[str, str],
    ) -> None:
        """Si se distinguieran, el 404 dejaria de proteger nada."""
        cita_id = await self._cita_en_sede_ajena(
            cliente, api, sesion, usuario, clinica, otra_sede, cuerpo_reserva
        )
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)

        ajena = await cliente.get(_ruta(api, f"/citas/{cita_id}"), headers=cabeceras)
        inexistente = await cliente.get(_ruta(api, f"/citas/{uuid.uuid4()}"), headers=cabeceras)

        assert ajena.status_code == inexistente.status_code == 404
        assert ajena.json()["codigo"] == inexistente.json()["codigo"]
        assert ajena.json()["mensaje"] == inexistente.json()["mensaje"]


# ===========================================================================
#  Ciclo de vida
# ===========================================================================
class TestCicloDeVida:
    async def test_bloquear_confirmar_y_cancelar(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        cuerpo_reserva: dict[str, str],
    ) -> None:
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)

        bloqueada = await cliente.post(
            _ruta(api, "/citas/bloqueos"), headers=cabeceras, json=cuerpo_reserva
        )
        cita_id = bloqueada.json()["id"]

        confirmada = await cliente.post(
            _ruta(api, f"/citas/{cita_id}/confirmacion"), headers=cabeceras
        )
        assert confirmada.status_code == 200
        assert confirmada.json()["estado"] == EstadoCita.CONFIRMED.value
        assert confirmada.json()["expira_en"] is None

        cancelada = await cliente.post(
            _ruta(api, f"/citas/{cita_id}/cancelacion"),
            headers=cabeceras,
            json={"motivo": "El paciente pidio anular"},
        )
        assert cancelada.status_code == 200
        assert cancelada.json()["estado"] == EstadoCita.CANCELLED.value
        assert cancelada.json()["motivo_cancelacion"] == "El paciente pidio anular"

    async def test_un_bloqueo_vencido_no_se_confirma(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        cuerpo_reserva: dict[str, str],
        reloj: RelojFijo,
        configuracion_minutos_bloqueo: int,
    ) -> None:
        """Ese turno pudo ofrecerse ya a otra persona.

        Confirmarlo dejaria dos pacientes citados a la misma hora por un
        camino que elude la restriccion de exclusion.
        """
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)
        bloqueada = await cliente.post(
            _ruta(api, "/citas/bloqueos"), headers=cabeceras, json=cuerpo_reserva
        )
        cita_id = bloqueada.json()["id"]

        reloj.avanzar(minutes=configuracion_minutos_bloqueo + 1)

        # Se vuelve a autenticar: adelantar el reloj caduca tambien el token de
        # acceso, y sin esto la prueba mediria la caducidad del token en lugar
        # de la del bloqueo. Es lo que haria el recepcionista que vuelve un
        # rato despues.
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.post(
            _ruta(api, f"/citas/{cita_id}/confirmacion"), headers=cabeceras
        )

        assert respuesta.status_code == 409
        assert respuesta.json()["codigo"] == "BLOQUEO_EXPIRADO"

    async def test_cancelar_sin_motivo_se_rechaza(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        cuerpo_reserva: dict[str, str],
    ) -> None:
        """Sin motivo no se puede explicar por que un paciente no fue atendido."""
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)
        creada = await cliente.post(_ruta(api, "/citas"), headers=cabeceras, json=cuerpo_reserva)
        cita_id = creada.json()["id"]

        respuesta = await cliente.post(
            _ruta(api, f"/citas/{cita_id}/cancelacion"),
            headers=cabeceras,
            json={"motivo": "  "},
        )

        assert respuesta.status_code == 422

    async def test_reprogramar_conserva_el_identificador(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        cuerpo_reserva: dict[str, str],
        reloj: RelojFijo,
    ) -> None:
        """Un solo identificador simplifica recordatorios y calendario externo."""
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)
        creada = await cliente.post(_ruta(api, "/citas"), headers=cabeceras, json=cuerpo_reserva)
        cita_id = creada.json()["id"]
        nuevo_inicio = (reloj.ahora() + timedelta(days=2, hours=1)).isoformat()

        respuesta = await cliente.post(
            _ruta(api, f"/citas/{cita_id}/reprogramacion"),
            headers=cabeceras,
            json={"nuevo_inicio": nuevo_inicio, "motivo": "El paciente lo pidio"},
        )

        assert respuesta.status_code == 200
        assert respuesta.json()["id"] == cita_id
        assert respuesta.json()["inicio"] != creada.json()["inicio"]

    async def test_una_transicion_invalida_responde_409(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        cuerpo_reserva: dict[str, str],
    ) -> None:
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)
        creada = await cliente.post(_ruta(api, "/citas"), headers=cabeceras, json=cuerpo_reserva)
        cita_id = creada.json()["id"]
        await cliente.post(
            _ruta(api, f"/citas/{cita_id}/cancelacion"),
            headers=cabeceras,
            json={"motivo": "Anulada"},
        )

        respuesta = await cliente.post(
            _ruta(api, f"/citas/{cita_id}/completado"), headers=cabeceras
        )

        assert respuesta.status_code == 409


# ===========================================================================
#  Listado
# ===========================================================================
class TestListado:
    async def test_el_detalle_incluye_las_notas_y_el_listado_no(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        cuerpo_reserva: dict[str, str],
    ) -> None:
        """Una exportacion de la agenda no debe arrastrar los comentarios
        administrativos sobre cada paciente."""
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)
        creada = await cliente.post(
            _ruta(api, "/citas"),
            headers=cabeceras,
            json={**cuerpo_reserva, "notas_recepcion": "Viene acompanado"},
        )
        cita_id = creada.json()["id"]

        listado = await cliente.get(_ruta(api, "/citas"), headers=cabeceras)
        detalle = await cliente.get(_ruta(api, f"/citas/{cita_id}"), headers=cabeceras)

        assert "Viene acompanado" not in listado.text
        assert detalle.json()["notas_recepcion"] == "Viene acompanado"

    async def test_el_total_corresponde_a_los_filtros_aplicados(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        paciente: Paciente,
        cuerpo_reserva: dict[str, str],
        reloj: RelojFijo,
    ) -> None:
        """Con filtros distintos, una pagina de tres citas diria «1 de 340»."""
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)
        for dias in (1, 2, 3):
            await cliente.post(
                _ruta(api, "/citas"),
                headers=cabeceras,
                json={
                    **cuerpo_reserva,
                    "inicio": (reloj.ahora() + timedelta(days=dias, hours=1)).isoformat(),
                },
            )

        sin_filtro = await cliente.get(_ruta(api, "/citas"), headers=cabeceras)
        otro_paciente = await cliente.get(
            _ruta(api, "/citas"),
            headers=cabeceras,
            params={"paciente_id": str(uuid.uuid4())},
        )

        assert sin_filtro.json()["total"] == 3
        assert otro_paciente.json()["total"] == 0
        assert otro_paciente.json()["elementos"] == []

    async def test_un_estado_desconocido_se_rechaza(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
    ) -> None:
        """Un estado mal escrito debe ser un 422, no un listado vacio.

        Un listado vacio se lee como «no hay citas» y esconde la errata.
        """
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)

        respuesta = await cliente.get(
            _ruta(api, "/citas"), headers=cabeceras, params={"estado": "CONFIRMADA"}
        )

        assert respuesta.status_code == 422

    async def test_la_paginacion_tiene_techo(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
    ) -> None:
        """Sin techo, una consulta sobre anos de historico agota la memoria."""
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)

        respuesta = await cliente.get(
            _ruta(api, "/citas"), headers=cabeceras, params={"limite": 10_000}
        )

        assert respuesta.status_code == 422
