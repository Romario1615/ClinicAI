"""Resolucion de identidad cuando un telefono corresponde a varios pacientes.

El problema
-----------
Un telefono **no identifica a una persona**.  Una madre gestiona las citas de
sus tres hijos desde el mismo numero, y hasta ahora el sistema respondia a esa
ambiguedad no identificando a nadie: toda la conversacion se derivaba a una
persona (ADR-0017).

La decision
-----------
Se consulta que pacientes tienen ese numero, se ofrecen como opciones
numeradas y **se espera a que quien escribe elija**.  Sin eleccion no hay
paciente resuelto y no se ejecuta nada.

Tres limites que esta decision no contradice
--------------------------------------------
**1. Elegir de una lista NO es verificar identidad.**  Es desambiguar.  El
`nivel_verificacion` del paciente no cambia por haber pulsado «2», y sigue
gobernando que se puede hacer despues.  Confundir las dos cosas convertiria una
pregunta de menu en una credencial.

**2. La lista se minimiza.**  Quien tenga el telefono en la mano va a leer esos
nombres, y un telefono puede estar perdido, prestado o reasignado.  Se muestra
el nombre de pila y la inicial del apellido: suficiente para que una madre
distinga a sus hijos, y lo menos posible para quien no deberia estar leyendo.
Nunca el documento, ni la fecha de nacimiento, ni nada clinico.

**3. Demasiados candidatos no se listan.**  Si un numero aparece en muchas
fichas -- el telefono de una residencia, o un dato mal cargado -- enumerarlos
seria un volcado de nombres a quien sea que tenga ese aparato.  Por encima del
tope se deriva a una persona.

La eleccion caduca
------------------
Una lista ofrecida ayer y respondida hoy con «2» es una respuesta a una
pregunta que quien escribe ya no recuerda.  Y las opciones se guardan con su
orden: reconstruir la lista al recibir la respuesta podria devolver otro orden
-- por una ficha nueva, por ejemplo -- y el «2» seleccionaria a otra persona.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.mensajeria.destinatarios import normalizar_telefono
from app.modulos.pacientes.modelos import Paciente, telefono_normalizado

#: Cuantos candidatos se pueden ofrecer como opciones.
#:
#: Por encima de esto no se enumera: un numero que aparece en ocho fichas no es
#: una familia, es un dato mal cargado o un telefono compartido, y listar ocho
#: nombres a quien tenga ese aparato es una fuga, no una ayuda.
MAXIMO_OPCIONES: Final[int] = 5

#: Cuanto vive una lista ofrecida.
MINUTOS_VIGENCIA_SELECCION: Final[int] = 15

#: Respuestas que cuentan como elegir una opcion.
#:
#: Coincidencia exacta, igual que el resto del reconocimiento de intencion: una
#: interpretacion probabilistica de «el segundo creo» no es base para decidir
#: sobre quien se actua.
_ELECCION = re.compile(r"^\s*([1-9])\s*$")


@dataclass(frozen=True, slots=True)
class Candidato:
    """Un paciente que comparte el numero, con la etiqueta que se le muestra."""

    paciente_id: uuid.UUID
    etiqueta: str


@dataclass(frozen=True, slots=True)
class Opciones:
    """Lista ofrecida, tal como se guarda y como se vuelve a leer."""

    candidatos: tuple[Candidato, ...]
    expira_en: datetime

    def vigente(self, ahora: datetime) -> bool:
        return ahora < self.expira_en

    def elegir(self, numero: int) -> uuid.UUID | None:
        """Resuelve la opcion por su posicion **en la lista guardada**.

        No se recalcula la lista: entre la oferta y la respuesta puede haberse
        creado una ficha nueva con ese mismo telefono, y entonces el «2» de
        quien escribe seleccionaria a otra persona.
        """
        if 1 <= numero <= len(self.candidatos):
            return self.candidatos[numero - 1].paciente_id
        return None

    def a_json(self) -> dict[str, Any]:
        return {
            "expira_en": self.expira_en.isoformat(),
            "candidatos": [
                {"paciente_id": str(c.paciente_id), "etiqueta": c.etiqueta} for c in self.candidatos
            ],
        }

    @classmethod
    def desde_json(cls, datos: dict[str, Any] | None) -> Opciones | None:
        if not datos or not datos.get("candidatos"):
            return None
        return cls(
            candidatos=tuple(
                Candidato(uuid.UUID(c["paciente_id"]), c["etiqueta"]) for c in datos["candidatos"]
            ),
            expira_en=datetime.fromisoformat(datos["expira_en"]),
        )


class ResultadoIdentificacion:
    """Qué hacer tras mirar quién hay detrás de un número."""

    __slots__ = ("motivo_derivacion", "opciones", "paciente_id")

    def __init__(
        self,
        *,
        paciente_id: uuid.UUID | None = None,
        opciones: Opciones | None = None,
        motivo_derivacion: str | None = None,
    ) -> None:
        self.paciente_id = paciente_id
        self.opciones = opciones
        self.motivo_derivacion = motivo_derivacion

    @property
    def resuelto(self) -> bool:
        return self.paciente_id is not None

    @property
    def hay_que_preguntar(self) -> bool:
        return self.opciones is not None


def etiquetar(paciente: Paciente) -> str:
    """Nombre de pila mas la inicial del apellido.

    Lo minimo que permite a una madre distinguir a sus hijos, y lo menos
    posible para quien tenga ese telefono sin deberlo tener.  Nunca el
    documento ni la fecha de nacimiento: son datos que permiten suplantar en
    otros tramites.
    """
    nombre = (paciente.nombre or "").strip().split(" ")[0]
    apellido = (paciente.apellido or "").strip()
    inicial = f" {apellido[0]}." if apellido else ""
    return f"{nombre}{inicial}".strip() or "Paciente sin nombre registrado"


async def identificar(
    sesion: AsyncSession,
    *,
    clinica_id: uuid.UUID,
    telefono: str,
    ahora: datetime,
) -> ResultadoIdentificacion:
    """Resuelve el paciente de un numero, o prepara la pregunta.

    La comparacion es sobre el numero **normalizado** en ambos lados: el panel
    guarda «+593 99 900 0333» y el webhook entrega «593999000333».
    """
    consulta = (
        select(Paciente)
        .where(
            Paciente.clinica_id == clinica_id,
            Paciente.activo.is_(True),
            telefono_normalizado() == normalizar_telefono(telefono),
        )
        .order_by(Paciente.creado_en)
        .limit(MAXIMO_OPCIONES + 1)
    )
    pacientes = list((await sesion.execute(consulta)).scalars().all())

    if not pacientes:
        return ResultadoIdentificacion(motivo_derivacion="NUMERO_SIN_PACIENTE")

    if len(pacientes) == 1:
        return ResultadoIdentificacion(paciente_id=pacientes[0].id)

    if len(pacientes) > MAXIMO_OPCIONES:
        # Enumerar aqui seria volcar nombres a quien tenga el aparato.
        return ResultadoIdentificacion(motivo_derivacion="DEMASIADOS_CANDIDATOS")

    return ResultadoIdentificacion(
        opciones=Opciones(
            candidatos=tuple(Candidato(p.id, etiquetar(p)) for p in pacientes),
            expira_en=ahora + timedelta(minutes=MINUTOS_VIGENCIA_SELECCION),
        )
    )


def texto_de_opciones(opciones: Opciones) -> str:
    """El mensaje que se le envia a quien escribe.

    Sin datos clinicos y sin documentos (CLAUDE.md, regla 10): es un mensaje de
    WhatsApp y puede leerse en una pantalla de bloqueo.
    """
    lineas = [f"{i}. {c.etiqueta}" for i, c in enumerate(opciones.candidatos, start=1)]
    return (
        "Este numero esta asociado a varias personas. "
        "Responda con el numero de la opcion para indicarme a quien se refiere:\n"
        + "\n".join(lineas)
    )


def leer_eleccion(texto: str | None) -> int | None:
    """Interpreta la respuesta a la lista. Solo un digito suelto cuenta."""
    if not texto:
        return None
    coincidencia = _ELECCION.match(texto)
    return int(coincidencia.group(1)) if coincidencia else None
