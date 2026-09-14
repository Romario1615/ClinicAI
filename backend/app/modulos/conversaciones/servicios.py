"""Procesamiento de los mensajes entrantes de WhatsApp.

Que hace este servicio y que no
-------------------------------
Hace: deduplicar, abrir o continuar el hilo, guardar el mensaje, reconocer la
intencion y **ejecutar la baja de consentimiento**.

No hace: cancelar citas, confirmarlas, aceptar ofertas de lista de espera ni
registrar tomas de medicacion.  Esas intenciones se reconocen y se registran,
pero el mensaje se deriva a una persona.

Por que esa linea, y no mas automatizacion
------------------------------------------
Para ejecutar «CANCELAR» hay que responder antes a «la cita de quien».  Lo
unico que trae el webhook es un numero de telefono, y en este sistema un
telefono **no identifica a una persona**: el modelo de paciente lo dice
explicitamente, porque una madre gestiona las citas de sus tres hijos desde el
mismo numero.  Cancelar la cita equivocada de una familia es un dano real y no
es reversible desde el punto de vista del paciente que se queda sin atencion.

Ejecutarlo requiere resolver la identidad con algo mas que el numero, y esa
resolucion llega con las herramientas del agente, que trabajan con un
principal y un ambito (CLAUDE.md, regla 4).  Hasta entonces, derivar es el
comportamiento correcto, no una funcionalidad pendiente.

La excepcion es la baja
-----------------------
`BAJA` si se ejecuta de inmediato.  Es el unico caso donde no hacer nada es
peor que equivocarse: si alguien pide que dejen de escribirle y el sistema
espera a que una persona lo lea el lunes, sigue escribiendole el fin de
semana.  Y el error posible -- dar de baja a quien no queria -- se corrige
volviendo a dar de alta, mientras que el error contrario no se corrige.

Se da de baja a **todos** los pacientes que comparten ese numero, por el mismo
motivo: ante la duda, dejar de escribir.

Una nota sobre el formato del numero
------------------------------------
Toda comparacion contra `paciente.telefono_whatsapp` pasa por
`telefono_normalizado()`, que reduce la columna a digitos en el `WHERE`.  No es
una comodidad: el panel guarda el numero como lo escribio el personal
(«+593 99 900 0333») y el webhook entrega solo digitos («593999000333»).

Comparar las dos formas en crudo no encuentra a nadie, y la consecuencia real
era que **un paciente que respondia BAJA no quedaba dado de baja** y el sistema
le seguia escribiendo.  Se descubrio ejerciendo el sistema con las semillas
reales; la suite no lo veia porque sus fixtures guardaban el numero ya
normalizado.  Hay un indice funcional que sostiene esa consulta
(`ix_paciente_whatsapp_normalizado`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as insert_pg
from sqlalchemy.ext.asyncio import AsyncSession

from app.mensajeria.carga_whatsapp import CargaWebhook, MensajeEntranteCrudo
from app.mensajeria.destinatarios import normalizar_telefono
from app.modulos.conversaciones.identificacion import (
    Opciones,
    identificar,
    leer_eleccion,
    texto_de_opciones,
)
from app.modulos.conversaciones.intenciones import reconocer
from app.modulos.conversaciones.modelos import (
    Conversacion,
    EstadoConversacion,
    IntencionEntrante,
    MensajeEntrante,
)
from app.modulos.pacientes.modelos import (
    Consentimiento,
    Paciente,
    TipoConsentimiento,
    telefono_normalizado,
)
from app.nucleo.autorizacion import Principal
from app.nucleo.bd import ejecutar_escritura
from app.nucleo.registro import obtener_logger
from app.nucleo.reloj import Reloj

logger = obtener_logger(__name__)

# WhatsApp solo admite texto libre durante las 24 horas siguientes al ultimo
# mensaje del paciente. Fuera de esa ventana hay que usar plantilla aprobada.
HORAS_VENTANA_RESPUESTA = 24

# Intenciones que cambian el estado de una cita, de una oferta o de una toma.
# Se reconocen, se registran y se derivan. Ver el encabezado.
INTENCIONES_QUE_EXIGEN_PERSONA: frozenset[IntencionEntrante] = frozenset(
    {
        IntencionEntrante.CONFIRMAR,
        IntencionEntrante.CANCELAR,
        IntencionEntrante.ACEPTAR_OFERTA,
        IntencionEntrante.REGISTRAR_TOMA,
        # El alta tambien: reactivar el consentimiento exige registrar que
        # texto acepto el paciente y su version, y un «ALTA» suelto no
        # contiene esa evidencia. La revocacion no necesita evidencia; el
        # consentimiento si.
        IntencionEntrante.ALTA,
        IntencionEntrante.AYUDA,
        IntencionEntrante.DESCONOCIDA,
    }
)

MOTIVOS_HANDOFF: dict[IntencionEntrante, str] = {
    IntencionEntrante.CONFIRMAR: "El paciente confirma su cita por WhatsApp.",
    IntencionEntrante.CANCELAR: "El paciente pide cancelar su cita por WhatsApp.",
    IntencionEntrante.ACEPTAR_OFERTA: "El paciente acepta un turno ofrecido.",
    IntencionEntrante.REGISTRAR_TOMA: "El paciente informa de una toma.",
    IntencionEntrante.ALTA: "El paciente pide volver a recibir mensajes.",
    IntencionEntrante.AYUDA: "El paciente pide ayuda.",
    IntencionEntrante.DESCONOCIDA: "Mensaje que el sistema no interpreta.",
}


@dataclass(frozen=True, slots=True)
class ResumenEntrada:
    recibidos: int = 0
    duplicados: int = 0
    derivados: int = 0
    bajas: int = 0
    sin_clinica: int = 0
    #: Mensajes que provocaron ofrecer la lista de pacientes del numero.
    preguntas_identidad: int = 0
    #: Mensajes que resolvieron una identidad eligiendo de esa lista.
    identidades_resueltas: int = 0


class ServicioConversaciones:
    """Aplica un cuerpo de webhook ya verificado."""

    def __init__(self, sesion: AsyncSession, reloj: Reloj) -> None:
        self._sesion = sesion
        self._reloj = reloj

    async def procesar(self, carga: CargaWebhook, *, clinica_id: uuid.UUID) -> ResumenEntrada:
        resumen = ResumenEntrada()
        for crudo in carga.mensajes:
            resumen = await self._procesar_mensaje(crudo, clinica_id, resumen)
        return resumen

    async def _procesar_mensaje(
        self,
        crudo: MensajeEntranteCrudo,
        clinica_id: uuid.UUID,
        resumen: ResumenEntrada,
    ) -> ResumenEntrada:
        conversacion = await self._obtener_o_abrir(crudo, clinica_id)
        intencion = reconocer(crudo.texto)

        sentencia = (
            insert_pg(MensajeEntrante)
            .values(
                conversacion_id=conversacion.id,
                external_id=crudo.external_id,
                telefono_origen=crudo.telefono,
                tipo=crudo.tipo,
                texto=crudo.texto,
                carga_util=crudo.crudo,
                intencion=intencion.value,
                recibido_en=crudo.recibido_en,
            )
            .on_conflict_do_nothing(constraint="uq_mensaje_entrante_external_id")
            .returning(MensajeEntrante.id)
        )
        creado = (await self._sesion.execute(sentencia)).scalar_one_or_none()
        if creado is None:
            # Reintento de Meta sobre un mensaje ya procesado. No se vuelve a
            # actuar: es justo para esto que existe la restriccion unica.
            logger.info("whatsapp.mensaje_duplicado", external_id=crudo.external_id)
            return _con(resumen, duplicados=resumen.duplicados + 1)

        conversacion.ultima_actividad_en = crudo.recibido_en
        conversacion.ventana_expira_en = crudo.recibido_en + timedelta(
            hours=HORAS_VENTANA_RESPUESTA
        )
        resumen = _con(resumen, recibidos=resumen.recibidos + 1)

        if intencion is IntencionEntrante.BAJA:
            revocados = await self._revocar_consentimiento(
                clinica_id=clinica_id, telefono=crudo.telefono
            )
            # El hilo se cierra: el paciente pidio que dejen de escribirle, y
            # dejarlo abierto en la cola del personal invita a responderle.
            conversacion.estado = EstadoConversacion.CERRADA.value
            conversacion.cerrada_en = self._reloj.ahora()
            logger.info(
                "whatsapp.baja_aplicada",
                conversacion_id=str(conversacion.id),
                consentimientos_revocados=revocados,
            )
            return _con(resumen, bajas=resumen.bajas + 1)

        # --- Identidad ---
        #
        # Antes de derivar se intenta resolver de quien habla el hilo. Si ya
        # hay una lista ofrecida y este mensaje es la respuesta, se resuelve.
        # Si no hay identidad y el numero corresponde a varios pacientes, se
        # pregunta y se espera: sin eleccion no hay paciente y no se ejecuta
        # nada.
        resuelto = self._resolver_seleccion(conversacion, crudo.texto)
        if resuelto:
            return _con(resumen, identidades_resueltas=resumen.identidades_resueltas + 1)

        if conversacion.paciente_id is None and conversacion.seleccion_pendiente is None:
            preguntado = await self._preguntar_identidad(conversacion, clinica_id, crudo.telefono)
            if preguntado:
                return _con(resumen, preguntas_identidad=resumen.preguntas_identidad + 1)

        conversacion.estado = EstadoConversacion.EN_HANDOFF.value
        conversacion.motivo_handoff = MOTIVOS_HANDOFF.get(
            intencion, MOTIVOS_HANDOFF[IntencionEntrante.DESCONOCIDA]
        )
        return _con(resumen, derivados=resumen.derivados + 1)

    def _resolver_seleccion(self, conversacion: Conversacion, texto: str | None) -> bool:
        """Aplica la respuesta a una lista ya ofrecida.

        Devuelve si la identidad quedo resuelta con este mensaje.

        Elegir de la lista **no verifica identidad**: desambigua. El
        `nivel_verificacion` del paciente no cambia por haber pulsado «2», y
        sigue gobernando que se puede hacer despues. Confundir las dos cosas
        convertiria una pregunta de menu en una credencial.
        """
        opciones = Opciones.desde_json(conversacion.seleccion_pendiente)
        if opciones is None:
            return False

        ahora = self._reloj.ahora()
        if not opciones.vigente(ahora):
            # Caducada: se descarta en silencio y el mensaje sigue su curso
            # hacia una persona. Responder «esa lista ya vencio» a quien acaba
            # de escribir «2» no le dice nada util.
            conversacion.seleccion_pendiente = None
            logger.info("whatsapp.seleccion_caducada", conversacion_id=str(conversacion.id))
            return False

        numero = leer_eleccion(texto)
        if numero is None:
            return False

        paciente_id = opciones.elegir(numero)
        if paciente_id is None:
            # Un numero fuera de rango no se reintenta a ciegas: va a una
            # persona, que es quien puede aclararlo.
            logger.info(
                "whatsapp.seleccion_fuera_de_rango",
                conversacion_id=str(conversacion.id),
                opciones=len(opciones.candidatos),
            )
            return False

        conversacion.paciente_id = paciente_id
        conversacion.seleccion_pendiente = None
        conversacion.estado = EstadoConversacion.EN_HANDOFF.value
        conversacion.motivo_handoff = (
            "El paciente indico de quien habla. Continua la consulta original."
        )
        logger.info(
            "whatsapp.identidad_resuelta",
            conversacion_id=str(conversacion.id),
            paciente_id=str(paciente_id),
        )
        return True

    async def _preguntar_identidad(
        self, conversacion: Conversacion, clinica_id: uuid.UUID, telefono: str
    ) -> bool:
        """Ofrece la lista de pacientes del numero, si procede.

        Devuelve si se ofrecio. Cuando el numero corresponde a un solo paciente
        la identidad se resuelve sin preguntar nada; cuando no corresponde a
        ninguno, o a demasiados, se deriva sin enumerar.
        """
        ahora = self._reloj.ahora()
        resultado = await identificar(
            self._sesion, clinica_id=clinica_id, telefono=telefono, ahora=ahora
        )

        if resultado.resuelto:
            conversacion.paciente_id = resultado.paciente_id
            return False

        if not resultado.hay_que_preguntar:
            logger.info(
                "whatsapp.identidad_sin_resolver",
                conversacion_id=str(conversacion.id),
                motivo=resultado.motivo_derivacion,
            )
            return False

        opciones = resultado.opciones
        assert opciones is not None
        conversacion.seleccion_pendiente = opciones.a_json()
        conversacion.estado = EstadoConversacion.EN_HANDOFF.value
        conversacion.motivo_handoff = (
            f"Numero asociado a {len(opciones.candidatos)} pacientes. "
            "Se le pidio indicar a quien se refiere."
        )
        logger.info(
            "whatsapp.identidad_preguntada",
            conversacion_id=str(conversacion.id),
            candidatos=len(opciones.candidatos),
        )
        return True

    @staticmethod
    def texto_para_preguntar(conversacion: Conversacion) -> str | None:
        """Mensaje a enviar cuando hay una lista pendiente.

        Se expone aparte para que quien orqueste el envio decida cuando sale:
        este servicio no envia nada, escribe el estado.
        """
        opciones = Opciones.desde_json(conversacion.seleccion_pendiente)
        return texto_de_opciones(opciones) if opciones else None

    async def derivar_a_humano(
        self,
        conversacion_id: uuid.UUID,
        *,
        principal: Principal,
        motivo: str,
    ) -> bool:
        """Marca una conversacion para que la atienda una persona.

        Es la contraparte de `handoff_to_human`: la herramienta del agente no
        escribe en la base, invoca esto (CLAUDE.md, regla 4).

        Devuelve si hubo cambio.  Marcar una conversacion ya derivada no es un
        error -- el paciente puede insistir, y el segundo mensaje no tiene por
        que fallar --, pero tampoco reescribe el motivo: el primero es el que
        explica por que se derivo.

        El filtro por `clinica_id` del principal no es decorativo.  Sin el, un
        identificador de conversacion de otra clinica -- que un modelo de
        lenguaje puede producir por alucinacion o por inyeccion -- movería el
        estado de un hilo ajeno.
        """
        if principal.clinica_id is None:
            return False

        sentencia = (
            update(Conversacion)
            .where(
                Conversacion.id == conversacion_id,
                Conversacion.clinica_id == principal.clinica_id,
                Conversacion.estado == EstadoConversacion.ABIERTA.value,
            )
            .values(
                estado=EstadoConversacion.EN_HANDOFF.value,
                motivo_handoff=motivo[:255],
                ultima_actividad_en=self._reloj.ahora(),
            )
        )
        return await ejecutar_escritura(self._sesion, sentencia) > 0

    async def _obtener_o_abrir(
        self, crudo: MensajeEntranteCrudo, clinica_id: uuid.UUID
    ) -> Conversacion:
        consulta = select(Conversacion).where(
            Conversacion.clinica_id == clinica_id,
            Conversacion.canal == "WHATSAPP",
            Conversacion.telefono == crudo.telefono,
            Conversacion.estado != EstadoConversacion.CERRADA.value,
        )
        existente = (await self._sesion.execute(consulta)).scalars().first()
        if existente is not None:
            return existente

        conversacion = Conversacion(
            clinica_id=clinica_id,
            canal="WHATSAPP",
            telefono=crudo.telefono,
            paciente_id=await self._identificar_paciente(clinica_id, crudo.telefono),
            estado=EstadoConversacion.ABIERTA.value,
            ultima_actividad_en=crudo.recibido_en,
        )
        self._sesion.add(conversacion)
        await self._sesion.flush()
        return conversacion

    async def _identificar_paciente(self, clinica_id: uuid.UUID, telefono: str) -> uuid.UUID | None:
        """Paciente asociado al numero, solo si es inequivoco.

        Si el numero corresponde a mas de un paciente -- el caso del telefono
        familiar -- se deja sin identificar.  Elegir uno de los tres hijos
        atribuiria el hilo a la persona equivocada, y a partir de ahi todo lo
        que se registre en esa conversacion quedaria en la ficha de quien no
        escribio.

        La comparacion es sobre el numero **normalizado** en las dos partes.
        Comparar la columna en crudo no encontraba a nadie: el panel guarda
        «+593 99 900 0333» y el webhook entrega «593999000333».
        """
        consulta = select(Paciente.id).where(
            Paciente.clinica_id == clinica_id,
            telefono_normalizado() == normalizar_telefono(telefono),
        )
        candidatos = list((await self._sesion.execute(consulta.limit(2))).scalars().all())
        return candidatos[0] if len(candidatos) == 1 else None

    async def _revocar_consentimiento(self, *, clinica_id: uuid.UUID, telefono: str) -> int:
        """Revoca los consentimientos de comunicacion de ese numero.

        No borra la fila: marca `revocado_en`.  Hay que poder demostrar que
        hubo consentimiento durante el periodo en que se enviaron mensajes.
        """
        pacientes = select(Paciente.id).where(
            Paciente.clinica_id == clinica_id,
            telefono_normalizado() == normalizar_telefono(telefono),
        )
        sentencia = (
            update(Consentimiento)
            .where(
                Consentimiento.paciente_id.in_(pacientes),
                Consentimiento.tipo.in_(
                    [
                        TipoConsentimiento.COMUNICACION_WHATSAPP.value,
                        TipoConsentimiento.RECORDATORIOS_MEDICACION.value,
                    ]
                ),
                Consentimiento.revocado_en.is_(None),
            )
            .values(revocado_en=self._reloj.ahora())
        )
        return await ejecutar_escritura(self._sesion, sentencia)


def _con(resumen: ResumenEntrada, **cambios: int) -> ResumenEntrada:
    datos = {
        "recibidos": resumen.recibidos,
        "duplicados": resumen.duplicados,
        "derivados": resumen.derivados,
        "bajas": resumen.bajas,
        "sin_clinica": resumen.sin_clinica,
        "preguntas_identidad": resumen.preguntas_identidad,
        "identidades_resueltas": resumen.identidades_resueltas,
    }
    datos.update(cambios)
    return ResumenEntrada(**datos)


__all__ = [
    "HORAS_VENTANA_RESPUESTA",
    "INTENCIONES_QUE_EXIGEN_PERSONA",
    "MOTIVOS_HANDOFF",
    "ResumenEntrada",
    "ServicioConversaciones",
]
