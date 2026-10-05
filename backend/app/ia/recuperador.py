"""Recuperacion de conocimiento para el agente.

Une el proveedor de embeddings, el repositorio autorizado y el saneamiento, y
aplica la regla que mas condiciona el comportamiento del agente:

**Si no hay fuente aprobada, la respuesta es que no hay informacion aprobada,
mas la oferta de derivar a un humano. Nunca se improvisa** (RF-O06, CLAUDE.md
seccion 8).

Por que esa regla y no «responde lo mejor que puedas»
------------------------------------------------------
Un modelo al que se le pide responder sin fuente responde igualmente, y lo
hace con el mismo tono de seguridad. En una clinica eso significa que un
paciente puede recibir una instruccion de preparacion de examen inventada, con
la voz de la institucion detras. El paciente no tiene forma de distinguirla de
una correcta.

El coste es que el agente dice «no lo se» mas a menudo de lo que a nadie le
gustaria. Es la direccion correcta del error.

Que devuelve este modulo, y que no
----------------------------------
Devuelve **fragmentos y su contexto ya envuelto como dato citado**, listo para
un prompt. No llama a ningun modelo de lenguaje: eso vive en el agente. La
separacion permite probar la recuperacion -- que es donde estan las fugas --
sin depender de un LLM.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.ia.embeddings import ProveedorEmbeddings
from app.ia.saneamiento import envolver_como_dato
from app.modulos.conocimiento.repositorio import (
    ContextoAutorizacion,
    FragmentoRecuperado,
    RepositorioConocimiento,
)
from app.nucleo.autorizacion import NivelSensibilidad, Principal
from app.nucleo.registro import obtener_logger

logger = obtener_logger(__name__)

# Consulta mas corta que esto no se busca. «si», «ok» o un emoji no son una
# consulta, y lanzar una busqueda hibrida con eso devuelve ruido con
# apariencia de fuente.
LONGITUD_MINIMA_CONSULTA = 3

# Tope de la consulta. Una consulta enorme suele ser un pegado accidental, y
# vectorizarla entera diluye el significado hasta no parecerse a nada.
LONGITUD_MAXIMA_CONSULTA = 1000

MENSAJE_SIN_FUENTE = (
    "No tengo informacion aprobada sobre eso. Puedo derivarle con el personal "
    "de la clinica para que se lo confirmen."
)


@dataclass(frozen=True, slots=True)
class ResultadoRecuperacion:
    """Lo recuperado, con todo lo necesario para auditar la respuesta."""

    fragmentos: list[FragmentoRecuperado]
    # Contexto listo para el prompt, ya envuelto como dato citado y saneado.
    # Vacio si no hubo fuentes.
    contexto: str
    consulta_normalizada: str

    @property
    def hay_fuente(self) -> bool:
        return bool(self.fragmentos)

    @property
    def referencias(self) -> list[str]:
        """Fuentes usadas, para registrar con la respuesta (RF-O04).

        Una respuesta fundamentada cuya fundamentacion no se puede comprobar
        despues no es fundamentada: es una afirmacion.
        """
        return [f.referencia for f in self.fragmentos]

    @property
    def documentos(self) -> list[uuid.UUID]:
        """Documentos distintos que respaldan la respuesta, sin repetir."""
        vistos: list[uuid.UUID] = []
        for fragmento in self.fragmentos:
            if fragmento.document_id not in vistos:
                vistos.append(fragmento.document_id)
        return vistos


def contexto_desde_principal(
    principal: Principal,
    *,
    ahora: datetime,
    nivel_maximo: NivelSensibilidad | None = None,
    uso_agente: bool = False,
) -> ContextoAutorizacion:
    """Traduce el principal al contexto de autorizacion de la busqueda.

    El nivel de sensibilidad se puede acotar por debajo del que el principal
    tiene, pero **nunca por encima**: el parametro sirve para que el agente
    busque con menos privilegio que la persona -- por ejemplo al responder por
    WhatsApp, donde la identidad no esta verificada --, no para ampliarlo.
    """
    if principal.clinica_id is None:
        raise ValueError("Un principal sin clinica no puede buscar conocimiento.")

    nivel = principal.ambito.nivel_maximo
    if nivel_maximo is not None and not nivel_maximo.cubre(nivel):
        # Se pidio un nivel menor: se respeta. Si se pidiera uno mayor, se
        # ignora y se conserva el del principal.
        nivel = nivel_maximo

    return ContextoAutorizacion(
        clinica_id=principal.clinica_id,
        sedes=None if principal.ambito.todas_las_sedes else frozenset(principal.ambito.sedes),
        especialidades=(
            None
            if principal.ambito.todas_las_especialidades
            else frozenset(principal.ambito.especialidades)
        ),
        nivel_maximo=nivel,
        ahora=ahora,
        actor_id=principal.actor_id,
        role_ids=principal.role_ids,
        uso_agente=uso_agente,
    )


class Recuperador:
    """Busca conocimiento autorizado y prepara el contexto del agente."""

    def __init__(
        self,
        sesion: AsyncSession,
        embeddings: ProveedorEmbeddings,
        *,
        top_k: int = 8,
        candidatos: int = 40,
        peso_vectorial: float = 0.6,
    ) -> None:
        self._repositorio = RepositorioConocimiento(sesion)
        self._embeddings = embeddings
        self._top_k = top_k
        self._candidatos = candidatos
        self._peso_vectorial = peso_vectorial

    async def recuperar(
        self, *, consulta: str, contexto: ContextoAutorizacion
    ) -> ResultadoRecuperacion:
        """Busca y devuelve el contexto citado.

        Un resultado vacio **no es un error**: es la respuesta correcta cuando
        no hay documentacion aprobada que cubra la pregunta, y quien llama
        debe usar `MENSAJE_SIN_FUENTE` en lugar de improvisar.
        """
        normalizada = " ".join(consulta.split())[:LONGITUD_MAXIMA_CONSULTA]
        if len(normalizada) < LONGITUD_MINIMA_CONSULTA:
            return ResultadoRecuperacion(
                fragmentos=[], contexto="", consulta_normalizada=normalizada
            )

        vector = await self._embeddings.vectorizar_consulta(normalizada)
        fragmentos = await self._repositorio.buscar_conocimiento_autorizado(
            consulta=normalizada,
            vector=vector,
            modelo_embeddings=self._embeddings.nombre_modelo,
            contexto=contexto,
            limite=self._top_k,
            candidatos=self._candidatos,
            peso_vectorial=self._peso_vectorial,
        )

        # El contenido se envuelve como dato citado ANTES de salir de aqui, no
        # en quien construye el prompt. Si se dejara para despues, cada nuevo
        # sitio que use el recuperador tendria que acordarse de hacerlo, y el
        # que se olvidara pasaria el texto crudo al modelo (ADR-0014).
        envuelto = envolver_como_dato([(f.referencia, f.contenido) for f in fragmentos])

        logger.info(
            "rag.consulta",
            clinica_id=str(contexto.clinica_id),
            fragmentos=len(fragmentos),
            documentos=len({f.document_id for f in fragmentos}),
            # La consulta NO se registra: puede contener el motivo por el que
            # un paciente pregunta, y un log de aplicacion no es sitio para
            # eso. Se registra su longitud, que basta para diagnosticar.
            longitud_consulta=len(normalizada),
        )
        if not fragmentos:
            logger.info("rag.sin_fuente", clinica_id=str(contexto.clinica_id))

        return ResultadoRecuperacion(
            fragmentos=fragmentos,
            contexto=envuelto,
            consulta_normalizada=normalizada,
        )


__all__ = [
    "LONGITUD_MAXIMA_CONSULTA",
    "LONGITUD_MINIMA_CONSULTA",
    "MENSAJE_SIN_FUENTE",
    "Recuperador",
    "ResultadoRecuperacion",
    "contexto_desde_principal",
]
