"""El agente atiende WhatsApp (ADR-0025).

Lo que estas pruebas sostienen
------------------------------
* Con la integracion `agente_whatsapp` apagada nada cambia: se deriva.
* Consultar basta con tener paciente resuelto.
* Cambiar una cita exige numero de un solo paciente **y** verificacion
  `TELEFONO` o superior. Sin eso la herramienta se rechaza por permisos y la
  conversacion pasa a recepcion; no se crea ninguna cita.
* Una conversacion en manos del personal no la contesta el agente.
* La respuesta sale por el outbox como texto libre y solo dentro de la ventana
  de 24 horas.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.ia.conversacion import ProveedorDemostracion
from app.mensajeria.adaptadores import AdaptadorSandbox, RegistroCanales
from app.mensajeria.carga_whatsapp import CargaWebhook, MensajeEntranteCrudo
from app.mensajeria.servicios import ServicioOutbox
from app.modulos.agenda.modelos import Cita
from app.modulos.conversaciones.agente_whatsapp import INTEGRACION, AgenteWhatsapp
from app.modulos.conversaciones.modelos import Conversacion, EstadoConversacion
from app.modulos.conversaciones.servicios import ServicioConversaciones
from app.modulos.organizacion.modelos import ConfiguracionClinica
from app.modulos.outbox.modelos import EstadoOutbox, OutboxMensaje, TipoMensajeOutbox
from app.modulos.pacientes.modelos import Paciente
from app.nucleo.reloj import RelojFijo

pytestmark = [pytest.mark.integracion, pytest.mark.asyncio]

# Miercoles 15 de abril de 2026, 14:00 UTC = 09:00 en Guayaquil.
AHORA = datetime(2026, 4, 15, 14, 0, tzinfo=UTC)
TELEFONO_PANEL = "+593 99 900 8181"
TELEFONO_WEBHOOK = "593999008181"


@pytest.fixture
def reloj_fijo() -> RelojFijo:
    return RelojFijo(AHORA)


def _servicio(sesion: AsyncSession, reloj: RelojFijo) -> ServicioConversaciones:
    return ServicioConversaciones(
        sesion, reloj, agente=AgenteWhatsapp(proveedor=ProveedorDemostracion)
    )


async def _habilitar(sesion: AsyncSession, clinica, habilitada: bool = True) -> None:
    sesion.add(
        ConfiguracionClinica(
            clinica_id=clinica.id,
            clave=f"integracion.{INTEGRACION}",
            valor={"habilitada": habilitada, "ajustes": {}, "secretos_cifrados": {}},
        )
    )
    await sesion.flush()


async def _horario_de_la_sede(sesion: AsyncSession, sede_id: uuid.UUID) -> None:
    for dia in range(1, 8):
        await sesion.execute(
            sa.text(
                "INSERT INTO horario_atencion (propietario_tipo, propietario_id, "
                "dia_semana, hora_inicio, hora_fin, granularidad_minutos) "
                "VALUES ('SEDE', :sede, :dia, '00:00', '23:59', 15)"
            ),
            {"sede": sede_id, "dia": dia},
        )
    await sesion.flush()


async def _paciente(
    sesion: AsyncSession, clinica, sufijo: str, verificacion: str = "TELEFONO"
) -> Paciente:
    paciente = Paciente(
        clinica_id=clinica.id,
        tipo_documento="CEDULA",
        numero_documento=f"96{sufijo}",
        nombre="Paciente",
        apellido=f"Agente {sufijo}",
        telefono_whatsapp=TELEFONO_PANEL,
        nivel_verificacion=verificacion,
        verificado_en=AHORA if verificacion != "NO_VERIFICADO" else None,
    )
    sesion.add(paciente)
    await sesion.flush()
    return paciente


async def _cita_previa(sesion, clinica, sede, profesional, servicio, paciente) -> Cita:
    """La ultima atencion da al agente sede, servicio y profesional habituales."""
    cita = Cita(
        clinica_id=clinica.id,
        sede_id=sede.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        servicio_id=servicio.id,
        inicio=AHORA - timedelta(days=30),
        duracion_minutos=30,
        minutos_preparacion=0,
        estado="COMPLETED",
        origen="PANEL",
    )
    sesion.add(cita)
    await sesion.flush()
    return cita


async def _turno(servicio: ServicioConversaciones, texto: str, clinica) -> None:
    """Como el webhook: guarda el mensaje y despues da su turno al agente."""
    await servicio.procesar(_mensaje(texto), clinica_id=clinica.id)
    await servicio.responder_pendientes()


def _mensaje(texto: str) -> CargaWebhook:
    return CargaWebhook(
        mensajes=[
            MensajeEntranteCrudo(
                external_id=f"wamid.agente-{uuid.uuid4().hex[:12]}",
                telefono=TELEFONO_WEBHOOK,
                tipo="text",
                texto=texto,
                recibido_en=AHORA,
                crudo={},
            ),
        ],
        estados=[],
    )


async def _conversacion(sesion: AsyncSession, clinica) -> Conversacion:
    return (
        (
            await sesion.execute(
                sa.select(Conversacion).where(
                    Conversacion.clinica_id == clinica.id,
                    Conversacion.telefono == TELEFONO_WEBHOOK,
                )
            )
        )
        .scalars()
        .one()
    )


async def _respuestas(sesion: AsyncSession, conversacion: Conversacion) -> list[OutboxMensaje]:
    return list(
        (
            await sesion.execute(
                sa.select(OutboxMensaje)
                .where(
                    OutboxMensaje.destino_tipo == "CONVERSACION",
                    OutboxMensaje.destino_id == conversacion.id,
                )
                .order_by(OutboxMensaje.creado_en)
            )
        )
        .scalars()
        .all()
    )


async def _citas_retenidas(sesion: AsyncSession, paciente: Paciente) -> int:
    return (
        await sesion.execute(
            sa.select(sa.func.count())
            .select_from(Cita)
            .where(Cita.paciente_id == paciente.id, Cita.estado == "HELD")
        )
    ).scalar_one()


class TestActivacion:
    async def test_apagado_deriva_como_siempre(
        self, sesion, reloj_fijo, clinica, sede, profesional, servicio
    ) -> None:
        paciente = await _paciente(sesion, clinica, "0001")
        await _cita_previa(sesion, clinica, sede, profesional, servicio, paciente)

        await _turno(_servicio(sesion, reloj_fijo), "mis citas", clinica)

        conversacion = await _conversacion(sesion, clinica)
        assert conversacion.estado == EstadoConversacion.EN_HANDOFF.value
        assert await _respuestas(sesion, conversacion) == []

    async def test_sin_agente_configurado_en_el_servicio_tambien_deriva(
        self, sesion, reloj_fijo, clinica, sede, profesional, servicio
    ) -> None:
        await _habilitar(sesion, clinica)
        paciente = await _paciente(sesion, clinica, "0002")
        await _cita_previa(sesion, clinica, sede, profesional, servicio, paciente)

        await ServicioConversaciones(sesion, reloj_fijo).procesar(
            _mensaje("mis citas"), clinica_id=clinica.id
        )

        assert (await _conversacion(sesion, clinica)).estado == EstadoConversacion.EN_HANDOFF.value


class TestConsulta:
    async def test_mis_citas_responde_por_el_outbox_y_no_deriva(
        self, sesion, reloj_fijo, clinica, sede, profesional, servicio
    ) -> None:
        await _habilitar(sesion, clinica)
        paciente = await _paciente(sesion, clinica, "0003", verificacion="NO_VERIFICADO")
        await _cita_previa(sesion, clinica, sede, profesional, servicio, paciente)

        await _turno(_servicio(sesion, reloj_fijo), "mis citas", clinica)

        conversacion = await _conversacion(sesion, clinica)
        assert conversacion.estado == EstadoConversacion.ABIERTA.value
        respuestas = await _respuestas(sesion, conversacion)
        assert len(respuestas) == 1
        assert respuestas[0].tipo == TipoMensajeOutbox.RESPUESTA_CONVERSACION.value
        assert respuestas[0].carga_util["texto"]
        actor = (
            await sesion.execute(
                sa.text(
                    "SELECT actor_tipo FROM auditoria WHERE accion = 'agente.herramienta_invocada' "
                    "AND paciente_id = :p ORDER BY ocurrido_en DESC LIMIT 1"
                ),
                {"p": paciente.id},
            )
        ).scalar_one()
        assert actor == "AGENTE_IA"

    async def test_sin_cita_previa_buscar_horarios_deriva_sin_error(
        self, sesion, reloj_fijo, clinica
    ) -> None:
        await _habilitar(sesion, clinica)
        await _paciente(sesion, clinica, "0004")

        await _turno(_servicio(sesion, reloj_fijo), "buscar horarios", clinica)

        assert (await _conversacion(sesion, clinica)).estado == EstadoConversacion.EN_HANDOFF.value


class TestCambios:
    async def test_verificado_con_numero_propio_aparta_el_horario(
        self, sesion, reloj_fijo, clinica, sede, profesional, servicio
    ) -> None:
        await _habilitar(sesion, clinica)
        await _horario_de_la_sede(sesion, sede.id)
        paciente = await _paciente(sesion, clinica, "0005", verificacion="TELEFONO")
        await _cita_previa(sesion, clinica, sede, profesional, servicio, paciente)
        servicio_conv = _servicio(sesion, reloj_fijo)

        await _turno(servicio_conv, "buscar horarios", clinica)
        conversacion = await _conversacion(sesion, clinica)
        assert conversacion.agente and conversacion.agente["memoria"].get("turnos")

        await _turno(servicio_conv, "1", clinica)

        assert await _citas_retenidas(sesion, paciente) == 1
        assert conversacion.estado == EstadoConversacion.ABIERTA.value
        assert len(await _respuestas(sesion, conversacion)) == 2

    async def test_sin_verificar_consulta_pero_el_cambio_va_a_recepcion(
        self, sesion, reloj_fijo, clinica, sede, profesional, servicio
    ) -> None:
        await _habilitar(sesion, clinica)
        await _horario_de_la_sede(sesion, sede.id)
        paciente = await _paciente(sesion, clinica, "0006", verificacion="NO_VERIFICADO")
        await _cita_previa(sesion, clinica, sede, profesional, servicio, paciente)
        servicio_conv = _servicio(sesion, reloj_fijo)

        await _turno(servicio_conv, "buscar horarios", clinica)
        conversacion = await _conversacion(sesion, clinica)
        assert conversacion.estado == EstadoConversacion.ABIERTA.value

        await _turno(servicio_conv, "1", clinica)

        assert await _citas_retenidas(sesion, paciente) == 0
        assert conversacion.estado == EstadoConversacion.EN_HANDOFF.value

    async def test_numero_compartido_no_cambia_aunque_el_elegido_este_verificado(
        self, sesion, reloj_fijo, clinica, sede, profesional, servicio
    ) -> None:
        await _habilitar(sesion, clinica)
        await _horario_de_la_sede(sesion, sede.id)
        elegido = await _paciente(sesion, clinica, "0007", verificacion="DOCUMENTO")
        await _paciente(sesion, clinica, "0008", verificacion="DOCUMENTO")
        await _cita_previa(sesion, clinica, sede, profesional, servicio, elegido)
        servicio_conv = _servicio(sesion, reloj_fijo)
        # Numero de dos pacientes: se resuelve eligiendo, que no verifica.
        await _turno(servicio_conv, "hola", clinica)
        conversacion = await _conversacion(sesion, clinica)
        assert conversacion.seleccion_pendiente is not None
        candidatos = conversacion.seleccion_pendiente["candidatos"]
        numero = 1 + next(
            i for i, c in enumerate(candidatos) if c["paciente_id"] == str(elegido.id)
        )
        await servicio_conv.procesar(_mensaje(str(numero)), clinica_id=clinica.id)
        assert conversacion.paciente_id == elegido.id
        # Con el agente activo, elegir deja la conversacion abierta para
        # consultar; elegir sigue sin verificar (ADR-0020).
        assert conversacion.estado == EstadoConversacion.ABIERTA.value

        await _turno(servicio_conv, "buscar horarios", clinica)
        assert conversacion.estado == EstadoConversacion.ABIERTA.value, "consultar si puede"
        await _turno(servicio_conv, "1", clinica)

        assert await _citas_retenidas(sesion, elegido) == 0
        assert conversacion.estado == EstadoConversacion.EN_HANDOFF.value


class TestTraspaso:
    async def test_conversacion_en_manos_del_personal_no_la_contesta_el_agente(
        self, sesion, reloj_fijo, clinica, sede, profesional, servicio
    ) -> None:
        await _habilitar(sesion, clinica)
        paciente = await _paciente(sesion, clinica, "0009")
        await _cita_previa(sesion, clinica, sede, profesional, servicio, paciente)
        servicio_conv = _servicio(sesion, reloj_fijo)
        await _turno(servicio_conv, "hablar con una persona", clinica)
        conversacion = await _conversacion(sesion, clinica)
        assert conversacion.estado == EstadoConversacion.EN_HANDOFF.value
        antes = len(await _respuestas(sesion, conversacion))

        await _turno(servicio_conv, "mis citas", clinica)

        assert len(await _respuestas(sesion, conversacion)) == antes


class TestEntrega:
    async def test_se_entrega_como_texto_dentro_de_la_ventana(
        self, sesion, reloj_fijo, clinica, sede, profesional, servicio
    ) -> None:
        await _habilitar(sesion, clinica)
        paciente = await _paciente(sesion, clinica, "0010")
        await _cita_previa(sesion, clinica, sede, profesional, servicio, paciente)
        await _turno(_servicio(sesion, reloj_fijo), "mis citas", clinica)
        conversacion = await _conversacion(sesion, clinica)
        respuesta = (await _respuestas(sesion, conversacion))[0]
        sandbox = AdaptadorSandbox("WHATSAPP")
        canales = RegistroCanales()
        canales.registrar("WHATSAPP", sandbox)

        await ServicioOutbox(sesion, reloj_fijo, canales)._entregar(respuesta, _resumen())

        assert respuesta.estado == EstadoOutbox.ENTREGADO.value
        enviado = sandbox.enviados[-1].mensaje
        assert enviado.libre
        assert enviado.destino == TELEFONO_WEBHOOK
        assert enviado.texto == respuesta.carga_util["texto"]

    async def test_fuera_de_la_ventana_queda_fallido_sin_reintento(
        self, sesion, reloj_fijo, clinica, sede, profesional, servicio
    ) -> None:
        await _habilitar(sesion, clinica)
        paciente = await _paciente(sesion, clinica, "0011")
        await _cita_previa(sesion, clinica, sede, profesional, servicio, paciente)
        await _turno(_servicio(sesion, reloj_fijo), "mis citas", clinica)
        conversacion = await _conversacion(sesion, clinica)
        respuesta = (await _respuestas(sesion, conversacion))[0]
        sandbox = AdaptadorSandbox("WHATSAPP")
        canales = RegistroCanales()
        canales.registrar("WHATSAPP", sandbox)
        tarde = RelojFijo(AHORA + timedelta(hours=25))

        await ServicioOutbox(sesion, tarde, canales)._entregar(respuesta, _resumen())

        assert respuesta.estado == EstadoOutbox.FALLIDO.value
        assert "24" in (respuesta.ultimo_error or "")
        assert sandbox.enviados == []


def _resumen():
    from app.mensajeria.servicios import ResumenProceso  # noqa: PLC0415

    return ResumenProceso()
