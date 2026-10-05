"""Respuestas del paciente que se aplican sin una persona.

* «TOMADA» registra la toma pendiente más cercana, solo con el paciente
  identificado y dentro de la ventana del recordatorio.
* Una imagen se asocia como comprobante si hay exactamente un pago pendiente.
* En cualquier otro caso se deriva, como antes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.mensajeria.carga_whatsapp import CargaWebhook, MensajeEntranteCrudo
from app.modulos.agenda.modelos import Cita
from app.modulos.conversaciones.modelos import Conversacion
from app.modulos.conversaciones.servicios import ServicioConversaciones
from app.modulos.historia.modelos import Receta, RecetaMedicamento, Toma
from app.modulos.pacientes.modelos import Paciente
from app.modulos.pagos.modelos import Pago
from app.nucleo.reloj import RelojFijo

pytestmark = [pytest.mark.integracion, pytest.mark.asyncio]

AHORA = datetime(2026, 4, 15, 14, 0, tzinfo=UTC)
TELEFONO_PANEL = "+593 99 900 8888"
TELEFONO_WEBHOOK = "593999008888"


def _mensaje(texto: str | None, tipo: str = "text") -> CargaWebhook:
    return CargaWebhook(
        mensajes=(
            MensajeEntranteCrudo(
                external_id=f"wamid.respuesta-{uuid.uuid4().hex[:12]}",
                telefono=TELEFONO_WEBHOOK,
                tipo=tipo,
                texto=texto,
                recibido_en=AHORA,
                crudo={},
            ),
        ),
        estados=(),
    )


async def _conversacion(sesion: AsyncSession, clinica) -> Conversacion:
    return (
        await sesion.execute(
            sa.select(Conversacion).where(
                Conversacion.clinica_id == clinica.id, Conversacion.telefono == TELEFONO_WEBHOOK
            )
        )
    ).scalar_one()


async def _toma(
    sesion: AsyncSession, clinica, paciente: Paciente, profesional, programada: datetime
) -> Toma:
    receta = Receta(
        clinica_id=clinica.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        estado="CONFIRMADA",
        confirmada_en=AHORA - timedelta(days=1),
        confirmada_por=profesional.id,
    )
    sesion.add(receta)
    await sesion.flush()
    medicamento = RecetaMedicamento(
        receta_id=receta.id,
        nombre="Medicamento sintético",
        dosis="1",
        via="ORAL",
        frecuencia_horas=8,
    )
    sesion.add(medicamento)
    await sesion.flush()
    toma = Toma(
        receta_medicamento_id=medicamento.id, paciente_id=paciente.id, programada_en=programada
    )
    sesion.add(toma)
    await sesion.flush()
    return toma


async def test_tomada_registra_la_toma_del_paciente_identificado(
    sesion: AsyncSession, clinica, paciente: Paciente, profesional
) -> None:
    paciente.telefono_whatsapp = TELEFONO_PANEL
    await sesion.flush()
    toma = await _toma(sesion, clinica, paciente, profesional, AHORA - timedelta(minutes=20))
    servicio = ServicioConversaciones(sesion, RelojFijo(AHORA))

    resumen = await servicio.procesar(_mensaje("tomada"), clinica_id=clinica.id)
    await sesion.flush()

    assert resumen.tomas_registradas == 1
    await sesion.refresh(toma)
    assert toma.estado == "TOMADA"
    assert toma.registrada_por_tipo == "PACIENTE"
    assert (await _conversacion(sesion, clinica)).estado != "EN_HANDOFF"


async def test_tomada_sin_toma_en_la_ventana_se_deriva(
    sesion: AsyncSession, clinica, paciente: Paciente, profesional
) -> None:
    paciente.telefono_whatsapp = TELEFONO_PANEL
    await sesion.flush()
    lejana = await _toma(sesion, clinica, paciente, profesional, AHORA - timedelta(hours=6))
    servicio = ServicioConversaciones(sesion, RelojFijo(AHORA))

    resumen = await servicio.procesar(_mensaje("tomada"), clinica_id=clinica.id)
    await sesion.flush()

    assert resumen.tomas_registradas == 0
    assert resumen.derivados == 1
    await sesion.refresh(lejana)
    assert lejana.estado == "PENDIENTE"


async def test_imagen_con_un_pago_pendiente_pasa_a_comprobante_recibido(
    sesion: AsyncSession, clinica, sede, servicio, paciente: Paciente, profesional
) -> None:
    paciente.telefono_whatsapp = TELEFONO_PANEL
    cita = Cita(
        clinica_id=clinica.id,
        sede_id=sede.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        servicio_id=servicio.id,
        inicio=AHORA + timedelta(days=1),
        fin=AHORA + timedelta(days=1, minutes=30),
        duracion_minutos=30,
        estado="CONFIRMED",
        origen="PANEL",
    )
    sesion.add(cita)
    await sesion.flush()
    pago = Pago(
        clinica_id=clinica.id, cita_id=cita.id, importe=Decimal("25.00"), metodo="TRANSFERENCIA"
    )
    sesion.add(pago)
    await sesion.flush()
    conversaciones = ServicioConversaciones(sesion, RelojFijo(AHORA))

    resumen = await conversaciones.procesar(_mensaje(None, tipo="image"), clinica_id=clinica.id)
    await sesion.flush()

    assert resumen.comprobantes == 1
    await sesion.refresh(pago)
    assert pago.estado == "PROOF_RECEIVED"
    conversacion = await _conversacion(sesion, clinica)
    assert "validar en Pagos" in (conversacion.motivo_handoff or "")

    # Una segunda imagen ya no tiene pago pendiente: se deriva sin cambiar nada.
    otra = await conversaciones.procesar(_mensaje(None, tipo="image"), clinica_id=clinica.id)
    assert otra.comprobantes == 0
    assert otra.derivados == 1


async def test_el_agente_consulta_solo_los_pagos_de_su_paciente(
    sesion: AsyncSession,
    clinica,
    sede,
    servicio,
    paciente: Paciente,
    segundo_paciente: Paciente,
    profesional,
) -> None:
    from app.ia.herramientas.contrato import ContextoHerramienta  # noqa: PLC0415
    from app.ia.herramientas.pagos import (  # noqa: PLC0415
        ArgumentosPagosPaciente,
        GetPatientPayments,
    )
    from app.nucleo.autorizacion import Ambito, Principal, TipoActor  # noqa: PLC0415
    from app.nucleo.errores import PermisoDenegado  # noqa: PLC0415

    cita = Cita(
        clinica_id=clinica.id,
        sede_id=sede.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        servicio_id=servicio.id,
        inicio=AHORA + timedelta(days=2),
        fin=AHORA + timedelta(days=2, minutes=30),
        duracion_minutos=30,
        estado="CONFIRMED",
        origen="PANEL",
    )
    sesion.add(cita)
    await sesion.flush()
    sesion.add(
        Pago(clinica_id=clinica.id, cita_id=cita.id, importe=Decimal("40.00"), metodo="EFECTIVO")
    )
    await sesion.flush()

    agente = Principal(
        actor_tipo=TipoActor.AGENTE_IA,
        actor_id=None,
        clinica_id=clinica.id,
        permisos=frozenset({"agenda.leer", "pago.leer"}),
        ambito=Ambito(
            clinica_id=clinica.id,
            todas_las_sedes=True,
            todas_las_especialidades=True,
            todos_los_profesionales=True,
            todos_los_pacientes=False,
            pacientes=frozenset({paciente.id}),
        ),
    )
    contexto = ContextoHerramienta(agente, sesion, RelojFijo(AHORA))
    herramienta = GetPatientPayments()
    resultado = await herramienta.ejecutar(
        ArgumentosPagosPaciente(paciente_id=paciente.id), contexto
    )
    assert resultado.exito
    assert resultado.datos["pagos"][0]["importe"] == "40.00"
    assert resultado.datos["pagos"][0]["estado"] == "pendiente"
    assert "servicio" not in resultado.datos["pagos"][0]

    with pytest.raises(PermisoDenegado):
        await herramienta.ejecutar(
            ArgumentosPagosPaciente(paciente_id=segundo_paciente.id), contexto
        )
