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
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita, EstadoCita
from app.modulos.odontologia.modelos import PlanTratamiento, ProcedimientoPlan
from app.modulos.organizacion.modelos import Clinica, Consultorio, Sede, Servicio
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
    "cita.registrar_llegada",
    "cita.iniciar_atencion",
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


async def _inicio_ofrecido_para_serie(
    cliente: AsyncClient,
    api: str,
    cabeceras: dict[str, str],
    cuerpo: dict[str, str],
) -> str:
    """Elige la hora ofrecida más cercana a la preferencia inicial del test."""
    zona = ZoneInfo("America/Guayaquil")
    preferido = datetime.fromisoformat(cuerpo["inicio"]).astimezone(zona)
    desde = datetime.combine(preferido.date(), datetime.min.time(), tzinfo=zona)
    hasta = datetime.combine(preferido.date() + timedelta(days=1), datetime.min.time(), tzinfo=zona)
    respuesta = await cliente.get(
        _ruta(api, "/disponibilidad"),
        headers=cabeceras,
        params={
            "profesional_id": cuerpo["profesional_id"],
            "servicio_id": cuerpo["servicio_id"],
            "sede_id": cuerpo["sede_id"],
            "desde": desde.isoformat(),
            "hasta": hasta.isoformat(),
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    turnos = respuesta.json()["turnos"]
    assert turnos, "La fixture de la sede debe ofrecer al menos un turno"
    return min(
        turnos,
        key=lambda turno: abs(datetime.fromisoformat(turno["inicio"]).astimezone(zona) - preferido),
    )["inicio"]


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
    async def test_recepcion_no_puede_agendar_un_procedimiento_de_plan_n3(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        paciente: Paciente,
        profesional: Profesional,
        servicio: Servicio,
        cuerpo_reserva: dict[str, str],
    ) -> None:
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)
        plan = PlanTratamiento(
            clinica_id=clinica.id,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            titulo="Plan sensible",
            estado="ACEPTADO",
            moneda="USD",
            nivel_sensibilidad="N3",
            aceptado_en=datetime(2026, 10, 1, tzinfo=UTC),
            aceptacion_medio="DOCUMENTO_FIRMADO",
            aceptacion_referencia="Constancia sensible",
            aceptacion_registrada_por=usuario.id,
            creado_por=usuario.id,
        )
        sesion.add(plan)
        await sesion.flush()
        procedimiento = ProcedimientoPlan(
            plan_id=plan.id,
            fase=1,
            orden=1,
            servicio_id=servicio.id,
            descripcion="Procedimiento sensible",
            precio="50.00",
            estado="PENDIENTE",
            creado_por=usuario.id,
        )
        sesion.add(procedimiento)
        await sesion.flush()

        respuesta = await cliente.post(
            _ruta(api, "/citas"),
            headers=cabeceras,
            json={**cuerpo_reserva, "procedimiento_plan_id": str(procedimiento.id)},
        )

        assert respuesta.status_code == 404
        await sesion.refresh(procedimiento)
        assert procedimiento.cita_id is None

    async def test_reservar_procedimiento_lo_vincula_al_plan_en_la_misma_operacion(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        paciente: Paciente,
        profesional: Profesional,
        servicio: Servicio,
        cuerpo_reserva: dict[str, str],
    ) -> None:
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)
        plan = PlanTratamiento(
            clinica_id=clinica.id,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            titulo="Plan dental aceptado",
            estado="ACEPTADO",
            moneda="USD",
            aceptado_en=datetime(2026, 10, 1, tzinfo=UTC),
            aceptacion_medio="DOCUMENTO_FIRMADO",
            aceptacion_referencia="Constancia de prueba",
            aceptacion_registrada_por=usuario.id,
            creado_por=usuario.id,
        )
        sesion.add(plan)
        await sesion.flush()
        procedimiento = ProcedimientoPlan(
            plan_id=plan.id,
            fase=1,
            orden=1,
            servicio_id=servicio.id,
            descripcion="Procedimiento de prueba",
            precio="50.00",
            estado="PENDIENTE",
            creado_por=usuario.id,
        )
        sesion.add(procedimiento)
        await sesion.flush()

        respuesta = await cliente.post(
            _ruta(api, "/citas"),
            headers=cabeceras,
            json={**cuerpo_reserva, "procedimiento_plan_id": str(procedimiento.id)},
        )

        assert respuesta.status_code == 201, respuesta.text
        await sesion.refresh(procedimiento)
        assert procedimiento.cita_id == uuid.UUID(respuesta.json()["id"])

        duplicada = await cliente.post(
            _ruta(api, "/citas"),
            headers=cabeceras,
            json={**cuerpo_reserva, "procedimiento_plan_id": str(procedimiento.id)},
        )
        assert duplicada.status_code == 409

        cancelacion = await cliente.post(
            _ruta(api, f"/citas/{procedimiento.cita_id}/cancelacion"),
            headers=cabeceras,
            json={"motivo": "Reagendar la fase de prueba"},
        )
        assert cancelacion.status_code == 200, cancelacion.text
        await sesion.refresh(procedimiento)
        assert procedimiento.cita_id is None

    async def test_no_vincula_una_fase_a_una_cita_de_otro_paciente(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        paciente: Paciente,
        profesional: Profesional,
        servicio: Servicio,
        cuerpo_reserva: dict[str, str],
    ) -> None:
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)
        otro_paciente = Paciente(
            clinica_id=clinica.id,
            tipo_documento="CEDULA",
            numero_documento=f"8{uuid.uuid4().hex[:9]}",
            nombre="Otro",
            apellido="Paciente de prueba",
        )
        sesion.add(otro_paciente)
        await sesion.flush()
        plan = PlanTratamiento(
            clinica_id=clinica.id,
            paciente_id=otro_paciente.id,
            profesional_id=profesional.id,
            titulo="Plan de otro paciente",
            estado="ACEPTADO",
            moneda="USD",
            aceptado_en=datetime(2026, 10, 1, tzinfo=UTC),
            aceptacion_medio="DOCUMENTO_FIRMADO",
            aceptacion_referencia="Constancia de prueba",
            aceptacion_registrada_por=usuario.id,
            creado_por=usuario.id,
        )
        sesion.add(plan)
        await sesion.flush()
        procedimiento = ProcedimientoPlan(
            plan_id=plan.id,
            fase=1,
            orden=1,
            servicio_id=servicio.id,
            descripcion="Procedimiento de otro paciente",
            precio="50.00",
            creado_por=usuario.id,
        )
        sesion.add(procedimiento)
        await sesion.flush()

        respuesta = await cliente.post(
            _ruta(api, "/citas"),
            headers=cabeceras,
            json={**cuerpo_reserva, "procedimiento_plan_id": str(procedimiento.id)},
        )

        assert respuesta.status_code == 404
        await sesion.refresh(procedimiento)
        assert procedimiento.cita_id is None

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

    async def test_crea_una_serie_semanal_y_repetirla_no_duplica_citas(
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
        clave = {"Idempotency-Key": f"serie-{uuid.uuid4().hex}"}
        inicio = await _inicio_ofrecido_para_serie(cliente, api, cabeceras, cuerpo_reserva)
        datos = {
            **cuerpo_reserva,
            "inicio": inicio,
            "frecuencia": "SEMANAL",
            "cantidad": 3,
        }

        primera = await cliente.post(
            _ruta(api, "/citas/series"), headers={**cabeceras, **clave}, json=datos
        )
        segunda = await cliente.post(
            _ruta(api, "/citas/series"), headers={**cabeceras, **clave}, json=datos
        )

        assert primera.status_code == 201, primera.text
        assert segunda.status_code == 201, segunda.text
        resultado = primera.json()
        assert resultado["frecuencia"] == "SEMANAL"
        assert resultado["cantidad"] == 3
        assert len(resultado["citas"]) == 3
        assert resultado == segunda.json()
        assert {cita["serie_recurrente_id"] for cita in resultado["citas"]} == {
            resultado["serie_id"]
        }
        assert {cita["origen"] for cita in resultado["citas"]} == {"RECURRENTE"}

        total = (
            await sesion.execute(
                sa.select(sa.func.count())
                .select_from(Cita)
                .where(Cita.serie_recurrente_id == uuid.UUID(resultado["serie_id"]))
            )
        ).scalar_one()
        assert total == 3

    async def test_una_fecha_ocupada_rechaza_la_serie_sin_guardar_parciales(
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
        inicio = await _inicio_ofrecido_para_serie(cliente, api, cabeceras, cuerpo_reserva)
        cuerpo_disponible = {**cuerpo_reserva, "inicio": inicio}
        fecha_ocupada = datetime.fromisoformat(inicio) + timedelta(days=7)
        ocupada = await cliente.post(
            _ruta(api, "/citas"),
            headers=cabeceras,
            json={**cuerpo_disponible, "inicio": fecha_ocupada.isoformat()},
        )
        assert ocupada.status_code == 201, ocupada.text

        respuesta = await cliente.post(
            _ruta(api, "/citas/series"),
            headers=cabeceras,
            json={**cuerpo_disponible, "frecuencia": "SEMANAL", "cantidad": 3},
        )

        assert respuesta.status_code == 409
        total_series = (
            await sesion.execute(
                sa.select(sa.func.count())
                .select_from(Cita)
                # Solo las del paciente de la prueba: la base de desarrollo
                # guarda series reales de otros recorridos.
                .where(
                    Cita.serie_recurrente_id.is_not(None),
                    Cita.paciente_id == uuid.UUID(cuerpo_reserva["paciente_id"]),
                )
            )
        ).scalar_one()
        assert total_series == 0

    async def test_clave_reutilizada_con_otra_cantidad_es_conflictiva(
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
        clave = {"Idempotency-Key": f"serie-{uuid.uuid4().hex}"}
        inicio = await _inicio_ofrecido_para_serie(cliente, api, cabeceras, cuerpo_reserva)
        datos = {
            **cuerpo_reserva,
            "inicio": inicio,
            "frecuencia": "SEMANAL",
            "cantidad": 3,
        }
        primera = await cliente.post(
            _ruta(api, "/citas/series"), headers={**cabeceras, **clave}, json=datos
        )
        distinta = await cliente.post(
            _ruta(api, "/citas/series"),
            headers={**cabeceras, **clave},
            json={**datos, "cantidad": 2},
        )

        assert primera.status_code == 201, primera.text
        assert distinta.status_code == 409
        assert distinta.json()["codigo"] == "CLAVE_IDEMPOTENCIA_CONFLICTIVA"

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

    @pytest.mark.parametrize("sufijo_ruta", ["/citas", "/citas/bloqueos"])
    async def test_un_paciente_de_otra_clinica_responde_404(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        cuerpo_reserva: dict[str, str],
        paciente_ajeno: Paciente,
        sufijo_ruta: str,
    ) -> None:
        """`cita.paciente_id` es una FK simple: el servicio valida la clinica.

        La respuesta es la misma que para un paciente inexistente.
        """
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)

        ajeno = await cliente.post(
            _ruta(api, sufijo_ruta),
            headers=cabeceras,
            json={**cuerpo_reserva, "paciente_id": str(paciente_ajeno.id)},
        )
        inexistente = await cliente.post(
            _ruta(api, sufijo_ruta),
            headers=cabeceras,
            json={**cuerpo_reserva, "paciente_id": str(uuid.uuid4())},
        )

        assert ajeno.status_code == inexistente.status_code == 404, ajeno.text
        assert ajeno.json()["codigo"] == inexistente.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
        assert ajeno.json()["mensaje"] == inexistente.json()["mensaje"]
        assert await _citas_del_paciente(sesion, paciente_ajeno.id) == 0


# ===========================================================================
#  Series recurrentes: autenticacion, permiso, ambito y entrada
# ===========================================================================
_SERIE_VALIDA = {"frecuencia": "SEMANAL", "cantidad": 2}


async def _filas_de_serie(sesion: AsyncSession, clinica_id: uuid.UUID) -> int:
    """Citas de una serie en la clinica de la prueba; acotado para no depender del resto."""
    return int(
        (
            await sesion.execute(
                sa.select(sa.func.count())
                .select_from(Cita)
                .where(Cita.serie_recurrente_id.is_not(None), Cita.clinica_id == clinica_id)
            )
        ).scalar_one()
    )


async def _citas_del_paciente(sesion: AsyncSession, paciente_id: uuid.UUID) -> int:
    return int(
        (
            await sesion.execute(
                sa.select(sa.func.count()).select_from(Cita).where(Cita.paciente_id == paciente_id)
            )
        ).scalar_one()
    )


class TestSeriesAccesoYValidacion:
    """Lista de CLAUDE.md §5.6 para POST /agenda/citas/series.

    En cada rechazo se comprueba ademas que no quedo ninguna fila de serie: la
    operacion es «todas o ninguna» tambien cuando se rechaza antes de empezar.
    """

    async def test_sin_autenticacion_responde_401(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        clinica: Clinica,
        cuerpo_reserva: dict[str, str],
    ) -> None:
        respuesta = await cliente.post(
            _ruta(api, "/citas/series"), json={**cuerpo_reserva, **_SERIE_VALIDA}
        )

        assert respuesta.status_code == 401
        assert respuesta.json()["codigo"] == "NO_AUTENTICADO"
        assert await _filas_de_serie(sesion, clinica.id) == 0

    async def test_solo_con_lectura_de_agenda_responde_403(
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
        inicio = await _inicio_ofrecido_para_serie(cliente, api, cabeceras, cuerpo_reserva)

        respuesta = await cliente.post(
            _ruta(api, "/citas/series"),
            headers=cabeceras,
            json={**cuerpo_reserva, "inicio": inicio, **_SERIE_VALIDA},
        )

        assert respuesta.status_code == 403
        assert await _filas_de_serie(sesion, clinica.id) == 0

    async def test_una_sede_fuera_de_ambito_responde_404_como_una_inexistente(
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
        """La otra sede es de la misma clinica pero el rol solo alcanza una."""
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)

        fuera = await cliente.post(
            _ruta(api, "/citas/series"),
            headers=cabeceras,
            json={**cuerpo_reserva, "sede_id": str(otra_sede.id), **_SERIE_VALIDA},
        )
        inexistente = await cliente.post(
            _ruta(api, "/citas/series"),
            headers=cabeceras,
            json={**cuerpo_reserva, "sede_id": str(uuid.uuid4()), **_SERIE_VALIDA},
        )

        assert fuera.status_code == inexistente.status_code == 404, fuera.text
        assert fuera.json()["mensaje"] == inexistente.json()["mensaje"]
        assert await _filas_de_serie(sesion, clinica.id) == 0

    async def test_un_paciente_de_otra_clinica_responde_404_sin_crear_citas(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        cuerpo_reserva: dict[str, str],
        paciente_ajeno: Paciente,
    ) -> None:
        """El IDOR heredado de POST /citas, multiplicado por 53 citas confirmadas."""
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)
        inicio = await _inicio_ofrecido_para_serie(cliente, api, cabeceras, cuerpo_reserva)
        datos = {**cuerpo_reserva, "inicio": inicio, "frecuencia": "SEMANAL", "cantidad": 53}

        ajeno = await cliente.post(
            _ruta(api, "/citas/series"),
            headers={**cabeceras, "Idempotency-Key": f"serie-{uuid.uuid4().hex}"},
            json={**datos, "paciente_id": str(paciente_ajeno.id)},
        )
        inexistente = await cliente.post(
            _ruta(api, "/citas/series"),
            headers=cabeceras,
            json={**datos, "paciente_id": str(uuid.uuid4())},
        )

        assert ajeno.status_code == inexistente.status_code == 404, ajeno.text
        assert ajeno.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
        assert ajeno.json()["mensaje"] == inexistente.json()["mensaje"]
        assert await _citas_del_paciente(sesion, paciente_ajeno.id) == 0
        assert await _filas_de_serie(sesion, clinica.id) == 0
        assert await _filas_de_serie(sesion, paciente_ajeno.clinica_id) == 0

    @pytest.mark.parametrize(
        "cambios",
        [
            pytest.param({"frecuencia": "ANUAL", "cantidad": 2}, id="frecuencia-desconocida"),
            pytest.param({"frecuencia": "SEMANAL", "cantidad": 1}, id="una-sola-cita"),
            pytest.param({"frecuencia": "SEMANAL", "cantidad": 54}, id="semanal-54"),
            pytest.param({"frecuencia": "QUINCENAL", "cantidad": 28}, id="quincenal-28"),
            pytest.param({"frecuencia": "MENSUAL", "cantidad": 14}, id="mensual-14"),
            pytest.param({"frecuencia": "SEMANAL"}, id="sin-cantidad"),
            pytest.param({"cantidad": 2}, id="sin-frecuencia"),
            pytest.param(
                {**_SERIE_VALIDA, "procedimiento_plan_id": "00000000-0000-4000-8000-000000000001"},
                id="procedimiento-de-plan",
            ),
            pytest.param({**_SERIE_VALIDA, "inicio": "2026-04-16T10:00:00"}, id="inicio-sin-zona"),
            pytest.param({**_SERIE_VALIDA, "origen": "WHATSAPP"}, id="origen-del-cliente"),
            pytest.param({**_SERIE_VALIDA, "paciente_id": "no-es-un-uuid"}, id="paciente-invalido"),
        ],
    )
    async def test_una_entrada_invalida_responde_422(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        cuerpo_reserva: dict[str, str],
        cambios: dict[str, object],
    ) -> None:
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)
        inicio = await _inicio_ofrecido_para_serie(cliente, api, cabeceras, cuerpo_reserva)

        respuesta = await cliente.post(
            _ruta(api, "/citas/series"),
            headers=cabeceras,
            json={**cuerpo_reserva, "inicio": inicio, **cambios},
        )

        assert respuesta.status_code == 422, respuesta.text
        assert respuesta.json()["codigo"] == "DATOS_INVALIDOS"
        assert await _filas_de_serie(sesion, clinica.id) == 0

    async def test_los_maximos_por_frecuencia_se_aceptan(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        cuerpo_reserva: dict[str, str],
    ) -> None:
        """QUINCENAL 27 es el techo: un año de citas cada dos semanas."""
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)
        inicio = await _inicio_ofrecido_para_serie(cliente, api, cabeceras, cuerpo_reserva)

        respuesta = await cliente.post(
            _ruta(api, "/citas/series"),
            headers=cabeceras,
            json={**cuerpo_reserva, "inicio": inicio, "frecuencia": "QUINCENAL", "cantidad": 27},
        )

        assert respuesta.status_code == 201, respuesta.text
        citas = respuesta.json()["citas"]
        assert len(citas) == 27
        primera = datetime.fromisoformat(citas[0]["inicio"])
        ultima = datetime.fromisoformat(citas[-1]["inicio"])
        assert ultima - primera == timedelta(days=14 * 26)
        assert await _filas_de_serie(sesion, clinica.id) == 27


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
            ("/llegada", None),
            ("/inicio-atencion", None),
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
    async def test_llegada_inicio_espera_y_cierre_quedan_registrados(
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
        creada = await cliente.post(
            _ruta(api, "/citas/bloqueos"), headers=cabeceras, json=cuerpo_reserva
        )
        assert creada.status_code == 201, creada.text
        cita_id = creada.json()["id"]
        confirmada = await cliente.post(
            _ruta(api, f"/citas/{cita_id}/confirmacion"), headers=cabeceras
        )
        assert confirmada.status_code == 200

        sin_llegada = await cliente.post(
            _ruta(api, f"/citas/{cita_id}/inicio-atencion"), headers=cabeceras
        )
        assert sin_llegada.status_code == 409
        assert sin_llegada.json()["codigo"] == "CONFLICTO_ESTADO"

        llegada = await cliente.post(_ruta(api, f"/citas/{cita_id}/llegada"), headers=cabeceras)
        assert llegada.status_code == 200, llegada.text
        instante_llegada = datetime.fromisoformat(llegada.json()["llegada_en"])
        assert llegada.json()["atencion_iniciada_en"] is None

        duplicada = await cliente.post(_ruta(api, f"/citas/{cita_id}/llegada"), headers=cabeceras)
        assert duplicada.status_code == 409

        inasistencia = await cliente.post(
            _ruta(api, f"/citas/{cita_id}/inasistencia"), headers=cabeceras
        )
        assert inasistencia.status_code == 409

        inicio = await cliente.post(
            _ruta(api, f"/citas/{cita_id}/inicio-atencion"), headers=cabeceras
        )
        assert inicio.status_code == 200, inicio.text
        instante_inicio = datetime.fromisoformat(inicio.json()["atencion_iniciada_en"])
        assert instante_inicio >= instante_llegada

        completada = await cliente.post(
            _ruta(api, f"/citas/{cita_id}/completado"), headers=cabeceras
        )
        assert completada.status_code == 200
        assert completada.json()["completada_en"] is not None

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
        actualizada = respuesta.json()
        inicio = datetime.fromisoformat(actualizada["inicio"])
        fin = datetime.fromisoformat(actualizada["fin"])
        duracion = actualizada["duracion_minutos"] + actualizada["minutos_preparacion"]
        assert (fin - inicio).total_seconds() == duracion * 60

    async def test_reprogramar_puede_asignar_un_consultorio(
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
        """La nueva sala se valida dentro de la sede y queda en la cita."""
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)
        consultorio = Consultorio(sede_id=sede.id, nombre=f"Consultorio {uuid.uuid4().hex[:8]}")
        sesion.add(consultorio)
        await sesion.flush()
        creada = await cliente.post(_ruta(api, "/citas"), headers=cabeceras, json=cuerpo_reserva)
        cita_id = creada.json()["id"]
        nuevo_inicio = (reloj.ahora() + timedelta(days=2, hours=1)).isoformat()

        respuesta = await cliente.post(
            _ruta(api, f"/citas/{cita_id}/reprogramacion"),
            headers=cabeceras,
            json={
                "nuevo_inicio": nuevo_inicio,
                "nuevo_consultorio_id": str(consultorio.id),
                "motivo": "Cambio de sala",
            },
        )

        assert respuesta.status_code == 200
        assert respuesta.json()["consultorio_id"] == str(consultorio.id)

    async def test_reprogramar_al_mismo_horario_se_rechaza(
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
        cita = creada.json()

        respuesta = await cliente.post(
            _ruta(api, f"/citas/{cita['id']}/reprogramacion"),
            headers=cabeceras,
            json={"nuevo_inicio": cita["inicio"], "motivo": "Solicitud sintetica"},
        )

        assert respuesta.status_code == 422
        assert "horario o recurso distinto" in respuesta.json()["mensaje"].lower()

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


# ===========================================================================
#  Exportación de informes
# ===========================================================================
class TestExportarResumen:
    async def test_exporta_agregados_locales_sin_identidad_de_paciente(
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
        await conceder_permisos(
            sesion,
            usuario,
            clinica,
            *PERMISOS_RECEPCION,
            "reporte.exportar",
            sedes=(sede.id,),
        )
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)
        creada = await cliente.post(_ruta(api, "/citas"), headers=cabeceras, json=cuerpo_reserva)
        assert creada.status_code == 201, creada.text
        sede.zona_horaria = "Pacific/Kiritimati"
        await sesion.flush()

        respuesta = await cliente.get(
            _ruta(api, "/resumen.csv"),
            headers=cabeceras,
            params={
                "desde": reloj.ahora().isoformat(),
                "hasta": (reloj.ahora() + timedelta(days=3)).isoformat(),
                "sede_id": str(sede.id),
            },
        )

        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.headers["content-type"].startswith("text/csv")
        assert (
            'attachment; filename="resumen-agenda.csv"' in respuesta.headers["content-disposition"]
        )
        contenido = respuesta.content.decode("utf-8-sig")
        assert contenido.startswith("Fecha local;Estado;Citas\r\n")
        inicio_local = datetime.fromisoformat(creada.json()["inicio"]).astimezone(
            ZoneInfo("Pacific/Kiritimati")
        )
        assert f"{inicio_local.date()};CONFIRMED;1\r\n" in contenido
        assert str(paciente.id) not in contenido
        assert paciente.nombre not in contenido

    async def test_exige_permiso_de_exportacion(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        reloj: RelojFijo,
    ) -> None:
        await conceder_permisos(sesion, usuario, clinica, *PERMISOS_RECEPCION, sedes=(sede.id,))
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.get(
            _ruta(api, "/resumen.csv"),
            headers=cabeceras,
            params={
                "desde": reloj.ahora().isoformat(),
                "hasta": (reloj.ahora() + timedelta(days=1)).isoformat(),
            },
        )

        assert respuesta.status_code == 403

    async def test_no_exporta_citas_de_otra_sede(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        otra_sede: Sede,
        cuerpo_reserva: dict[str, str],
        reloj: RelojFijo,
    ) -> None:
        await TestAislamientoPorAmbito._cita_en_sede_ajena(
            cliente, api, sesion, usuario, clinica, otra_sede, cuerpo_reserva
        )
        await conceder_permisos(
            sesion,
            usuario,
            clinica,
            *PERMISOS_RECEPCION,
            "reporte.exportar",
            sedes=(sede.id,),
        )
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.get(
            _ruta(api, "/resumen.csv"),
            headers=cabeceras,
            params={
                "desde": reloj.ahora().isoformat(),
                "hasta": (reloj.ahora() + timedelta(days=3)).isoformat(),
            },
        )

        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.content.decode("utf-8-sig") == "Fecha local;Estado;Citas\r\n"


# ===========================================================================
#  Consultorio
# ===========================================================================
class TestConsultorio:
    """La sala de una cita tiene que ser de la sede de la cita.

    Sin esa comprobacion, el identificador de una sala ajena quedaba grabado
    en la cita y la restriccion de exclusion por consultorio bloqueaba turnos
    de otra sede -- o de otra clinica -- sin que nadie lo viera.
    """

    async def _consultorio(
        self, sesion: AsyncSession, sede: Sede, *, activo: bool = True
    ) -> Consultorio:
        sala = Consultorio(sede_id=sede.id, nombre=f"Sillon {uuid.uuid4().hex[:6]}", activo=activo)
        sesion.add(sala)
        await sesion.flush()
        return sala

    async def test_reserva_con_consultorio_de_la_sede(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        cuerpo_reserva: dict[str, str],
    ) -> None:
        sala = await self._consultorio(sesion, sede)
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)

        respuesta = await cliente.post(
            _ruta(api, "/citas"),
            headers=cabeceras,
            json={**cuerpo_reserva, "consultorio_id": str(sala.id)},
        )

        assert respuesta.status_code == 201, respuesta.text
        assert respuesta.json()["consultorio_id"] == str(sala.id)

    async def test_consultorio_de_otra_sede_responde_404(
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
        ajena = await self._consultorio(sesion, otra_sede)
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)

        respuesta = await cliente.post(
            _ruta(api, "/citas"),
            headers=cabeceras,
            json={**cuerpo_reserva, "consultorio_id": str(ajena.id)},
        )

        assert respuesta.status_code == 404
        total = await sesion.scalar(
            sa.select(sa.func.count()).select_from(Cita).where(Cita.consultorio_id == ajena.id)
        )
        assert total == 0

    async def test_consultorio_inexistente_responde_404(
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
            json={**cuerpo_reserva, "consultorio_id": str(uuid.uuid4())},
        )

        assert respuesta.status_code == 404

    async def test_consultorio_inactivo_se_rechaza(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        cuerpo_reserva: dict[str, str],
    ) -> None:
        sala = await self._consultorio(sesion, sede, activo=False)
        cabeceras = await _recepcion(cliente, sesion, usuario, clinica, sede)

        respuesta = await cliente.post(
            _ruta(api, "/citas"),
            headers=cabeceras,
            json={**cuerpo_reserva, "consultorio_id": str(sala.id)},
        )

        assert respuesta.status_code == 422
