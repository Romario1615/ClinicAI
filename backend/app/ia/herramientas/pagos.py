"""Herramienta de pagos para el agente: solo consultar lo pendiente.

El paciente pregunta «¿cuánto debo?» por WhatsApp. La herramienta devuelve
importe, moneda, estado y fecha de la cita de los pagos sin cerrar de **ese**
paciente (el del ámbito de la conversación). No registra, valida ni cobra
nada: el comprobante se envía como imagen y lo valida una persona.

No devuelve el servicio ni el motivo de la cita: el nombre de un servicio
puede revelar la especialidad (CLAUDE.md, regla 10).
"""

from __future__ import annotations

import uuid
from typing import ClassVar

from pydantic import BaseModel

from app.ia.herramientas.contrato import ContextoHerramienta, Herramienta, ResultadoHerramienta
from app.modulos.pagos.repositorio import RepositorioPagos
from app.nucleo.errores import PermisoDenegado

ESTADOS_ABIERTOS = ("PENDING", "PROOF_RECEIVED", "UNDER_REVIEW", "REJECTED")
NOMBRES = {
    "PENDING": "pendiente",
    "PROOF_RECEIVED": "comprobante recibido, en validación",
    "UNDER_REVIEW": "en revisión",
    "REJECTED": "comprobante rechazado: envíe otro o consulte en la clínica",
}


class ArgumentosPagosPaciente(BaseModel):
    paciente_id: uuid.UUID


class GetPatientPayments(Herramienta):
    nombre: ClassVar[str] = "get_patient_payments"
    descripcion: ClassVar[str] = (
        "Lista los pagos sin cerrar de un paciente: importe, moneda, estado y fecha de la "
        "cita. No registra pagos ni pide datos de tarjeta. Para pagar, el paciente envía "
        "la foto del comprobante de transferencia por este chat."
    )
    argumentos: ClassVar[type[BaseModel]] = ArgumentosPagosPaciente
    permiso: ClassVar[str | None] = "pago.leer"
    escribe: ClassVar[bool] = False

    async def ejecutar(
        self, argumentos: BaseModel, contexto: ContextoHerramienta
    ) -> ResultadoHerramienta:
        if not isinstance(argumentos, ArgumentosPagosPaciente):
            raise TypeError("get_patient_payments espera ArgumentosPagosPaciente.")
        principal = contexto.principal
        ambito = principal.ambito
        if not ambito.todos_los_pacientes and argumentos.paciente_id not in ambito.pacientes:
            raise PermisoDenegado("Solo puede consultar los pagos de su propia ficha.")
        filas = await RepositorioPagos(contexto.sesion).abiertos_de_paciente(
            principal, argumentos.paciente_id, ESTADOS_ABIERTOS
        )
        pagos = [
            {
                "importe": str(importe),
                "moneda": moneda,
                "estado": NOMBRES.get(estado, estado),
                "cita": inicio.isoformat(),
            }
            for importe, moneda, estado, inicio in filas
        ]
        if not pagos:
            return ResultadoHerramienta(
                exito=True,
                mensaje="No tiene pagos pendientes.",
                datos={"pagos": []},
                codigo="SIN_PAGOS",
            )
        return ResultadoHerramienta(
            exito=True,
            mensaje=(
                f"Tiene {len(pagos)} pago(s) sin cerrar. Para pagar por transferencia, envíe "
                "aquí la foto del comprobante y el personal lo validará."
            ),
            datos={"pagos": pagos},
        )


HERRAMIENTAS_PAGOS: tuple[Herramienta, ...] = (GetPatientPayments(),)

__all__ = ["HERRAMIENTAS_PAGOS", "GetPatientPayments"]
