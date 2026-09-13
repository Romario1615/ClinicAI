"""`handoff_to_human`: la salida del agente hacia una persona.

Es la herramienta mas importante del conjunto, y la unica que no puede fallar.
Todo lo que el agente no debe resolver -- una decision clinica, un sintoma, una
urgencia, un mensaje que no entendio -- sale por aqui.  Si esta herramienta
devolviera un error, el paciente se quedaria sin respuesta justo en el caso en
que mas la necesita, asi que esta escrita para no tener caminos de fallo:
marca la conversacion y devuelve el texto que corresponde al motivo.

Lo que registra y lo que no
---------------------------
Registra el **motivo** de la derivacion, no el texto del paciente.  Guardar el
mensaje original en la auditoria crearia una copia de informacion clinica en
una tabla pensada para referencias, sin las restricciones de acceso de la
historia clinica (ver `CLAVES_PROHIBIDAS_METADATOS` en `nucleo/auditoria.py`).
El mensaje ya esta en `mensaje_entrante`, que es su sitio.

El aviso al personal tampoco lleva contenido
--------------------------------------------
Lo que ve el personal es «conversacion X necesita atencion, motivo
REACCION_ADVERSA».  Abrir la conversacion y leerla es un acto deliberado que
queda auditado, y eso es preferible a empujar el texto a una notificacion que
puede acabar en la pantalla de bloqueo de un telefono (regla 10).
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field

from app.ia.herramientas.contrato import (
    ContextoHerramienta,
    Herramienta,
    ResultadoHerramienta,
)
from app.ia.herramientas.limites import MotivoDerivacion, explicar
from app.modulos.conversaciones.servicios import ServicioConversaciones


class ArgumentosDerivacion(BaseModel):
    """Solo el motivo y una nota corta para el personal.

    No hay campo para el texto del paciente: lo que dijo ya esta guardado, y
    pedirselo al modelo invitaria a que lo reescriba, que es como se pierde la
    version literal de lo que de verdad se dijo.
    """

    motivo: MotivoDerivacion
    # Nota operativa, no clinica: «pregunta por el turno del jueves». El limite
    # de longitud es corto a proposito.
    nota: str = Field(default="", max_length=200)


class HandoffToHuman(Herramienta):
    nombre: ClassVar[str] = "handoff_to_human"
    descripcion: ClassVar[str] = (
        "Pasa la conversacion a una persona de la clinica. Usala siempre que la "
        "consulta sea clinica, urgente, sobre medicacion, sobre otra persona, o "
        "cuando no estes seguro de haber entendido. Ante la duda, usala."
    )
    argumentos: ClassVar[type[BaseModel]] = ArgumentosDerivacion
    # No exige permiso: derivar a una persona no accede a ningun dato. Exigirlo
    # significaria que un principal mal configurado se quedaria sin la unica
    # salida segura que tiene.
    permiso: ClassVar[str | None] = None
    escribe: ClassVar[bool] = True

    async def ejecutar(
        self, argumentos: BaseModel, contexto: ContextoHerramienta
    ) -> ResultadoHerramienta:
        if not isinstance(argumentos, ArgumentosDerivacion):
            raise TypeError("handoff_to_human espera ArgumentosDerivacion.")

        marcada = False
        if contexto.conversacion_id is not None:
            servicio = ServicioConversaciones(contexto.sesion, contexto.reloj)
            marcada = await servicio.derivar_a_humano(
                contexto.conversacion_id,
                principal=contexto.principal,
                motivo=_motivo_para_el_personal(argumentos),
            )

        return ResultadoHerramienta(
            exito=True,
            mensaje=explicar(argumentos.motivo),
            datos={
                "motivo": argumentos.motivo.value,
                "nota": argumentos.nota,
                "conversacion_marcada": marcada,
            },
            requiere_humano=True,
            codigo="DERIVADO",
        )


def _motivo_para_el_personal(argumentos: ArgumentosDerivacion) -> str:
    """Lo que ve quien abre la cola de conversaciones pendientes.

    Lleva el motivo, que es lo que permite priorizar, y la nota operativa si
    el agente la escribio.  No lleva el texto del paciente: ese esta en
    `mensaje_entrante` y leerlo es un acto deliberado que queda auditado.
    """
    if argumentos.nota.strip():
        return f"{argumentos.motivo.value}: {argumentos.nota.strip()}"
    return argumentos.motivo.value


HERRAMIENTA_DERIVACION = HandoffToHuman()
