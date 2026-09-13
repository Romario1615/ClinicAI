"""Contrato de las herramientas del agente.

Por que existe esta capa
------------------------
El agente no habla con la base de datos.  Tampoco habla con los servicios
directamente.  Habla con estas herramientas, y son ellas las que llaman a la
capa de servicios con el principal del solicitante (CLAUDE.md, regla 4).

La diferencia no es estilistica.  Un modelo de lenguaje produce texto, y ese
texto puede venir influido por lo que alguien escribio en un mensaje o en un
PDF indexado.  Si el texto pudiera elegir *sobre que datos* opera, una
inyeccion de prompt bastaria para leer la agenda de otra clinica.  Aqui el
texto solo elige **que** herramienta y **con que argumentos de negocio**; el
**quien** viene del token o del canal verificado y el modelo no puede tocarlo.

De ahi las tres propiedades que esta capa garantiza y que hay pruebas que
verifican:

1. **El principal nunca sale de los argumentos.**  `ContextoHerramienta` lo
   recibe de quien orquesta, y los esquemas de argumentos no admiten ningun
   campo de identidad.  Una prueba recorre los esquemas y lo comprueba.
2. **Toda invocacion queda auditada**, tanto la que se ejecuta como la que se
   deniega.  Una herramienta que falla en silencio es una herramienta que
   nadie puede investigar despues.
3. **Los errores se traducen a un resultado, no se propagan.**  El agente
   recibe un texto que puede leerle al paciente; nunca una traza ni el
   mensaje interno de una excepcion, que puede revelar estructura.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.nucleo.autorizacion import NivelSensibilidad, Principal
from app.nucleo.reloj import Reloj


@dataclass(frozen=True, slots=True)
class ContextoHerramienta:
    """Todo lo que una herramienta necesita y que el modelo no decide.

    El principal viaja aqui, separado de los argumentos, para que la
    separacion sea estructural y no una convencion que se pueda olvidar.
    """

    principal: Principal
    sesion: AsyncSession
    reloj: Reloj
    # Identificador de la conversacion, cuando la invocacion viene de un canal
    # conversacional.  Se registra en auditoria para poder reconstruir que
    # pidio el paciente antes de cada operacion.
    conversacion_id: uuid.UUID | None = None
    correlacion_id: str | None = None


@dataclass(frozen=True, slots=True)
class ResultadoHerramienta:
    """Lo que la herramienta devuelve al orquestador.

    `mensaje` es texto apto para leerselo al paciente.  `datos` es la
    estructura que el orquestador puede usar para componer una respuesta mas
    rica.  Nunca lleva contenido clinico: las herramientas de agenda operan
    sobre horarios, no sobre motivos de consulta.
    """

    exito: bool
    mensaje: str
    datos: dict[str, Any] = field(default_factory=dict)
    # Cierto cuando el agente debe dejar de intentar y pasar a una persona.
    requiere_humano: bool = False
    # Codigo estable para las pruebas y para el registro. No se le muestra al
    # paciente.
    codigo: str | None = None


class Herramienta(ABC):
    """Una herramienta invocable por el agente.

    Los nombres estan en ingles por decision normativa de la especificacion
    (CLAUDE.md, seccion 2): son parte del contrato con el modelo y no se
    traducen.
    """

    #: Nombre con el que el modelo la invoca.
    nombre: ClassVar[str]
    #: Descripcion que se le da al modelo. Es prompt, asi que importa.
    descripcion: ClassVar[str]
    #: Esquema de los argumentos de negocio. Nunca contiene identidad.
    argumentos: ClassVar[type[BaseModel]]
    #: Permiso que la herramienta exige. `None` solo para las que no tocan
    #: datos de la clinica, como la derivacion a un humano.
    permiso: ClassVar[str | None] = None
    #: Cierto si la herramienta modifica estado. Las de escritura se auditan
    #: con la entidad afectada; las de lectura, con el filtro aplicado.
    escribe: ClassVar[bool] = False
    #: Nivel maximo de informacion que la herramienta puede devolver.
    nivel: ClassVar[NivelSensibilidad] = NivelSensibilidad.ADMINISTRATIVO

    @abstractmethod
    async def ejecutar(
        self, argumentos: BaseModel, contexto: ContextoHerramienta
    ) -> ResultadoHerramienta:
        """Ejecuta la operacion. No captura errores de dominio: los deja subir.

        Quien orquesta los traduce, para que la traduccion sea una sola y no
        una por herramienta.
        """
