"""Procesamiento de los mensajes entrantes de WhatsApp.

Que hace este servicio y que no
-------------------------------
Hace: deduplicar, abrir o continuar el hilo, guardar el mensaje, reconocer la
intencion, ejecutar la baja de consentimiento y aplicar respuestas exactas de
seguimiento de tomas cuando el hilo identifica a un paciente sin ambiguedad.

No hace: cancelar citas, confirmarlas ni aceptar ofertas de lista de espera.
Esas intenciones se reconocen y se derivan a una persona. Los mensajes libres,
ambiguos o sobre cambios de tratamiento tambien se derivan.

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
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as insert_pg
from sqlalchemy.ext.asyncio import AsyncSession

from app.ia.decisiones import ClasificadorIntencion, Intencion
from app.mensajeria.carga_whatsapp import CargaWebhook, MensajeEntranteCrudo
from app.mensajeria.destinatarios import normalizar_telefono
from app.mensajeria.recordatorios import ENTIDAD_TOMA, ESTADO_CANCELADO, ESTADO_PROGRAMADO
from app.modulos.agenda.modelos import Cita
from app.modulos.auditoria.repositorio import RepositorioAuditoria
from app.modulos.conversaciones.identificacion import (
    Opciones,
    identificar,
    leer_eleccion,
    texto_de_opciones,
)
from app.modulos.conversaciones.intenciones import reconocer
from app.modulos.conversaciones.modelos import (
    AvisoRevisionTratamiento,
    Conversacion,
    EstadoConversacion,
    IntencionEntrante,
    MensajeEntrante,
)
from app.modulos.historia.modelos import EstadoReceta, EstadoToma, Receta, RecetaMedicamento, Toma
from app.modulos.outbox.modelos import EstadoOutbox, OutboxMensaje, Recordatorio, TipoMensajeOutbox
from app.modulos.pacientes.modelos import (
    Consentimiento,
    Paciente,
    TipoConsentimiento,
    telefono_normalizado,
)
from app.modulos.pagos.modelos import Pago
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import NivelSensibilidad, Principal, TipoActor, principal_sistema
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
        IntencionEntrante.RECORDAR_TOMA_DESPUES,
        IntencionEntrante.NO_PUDO_TOMAR,
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
    IntencionEntrante.RECORDAR_TOMA_DESPUES: "El paciente pidio posponer el recordatorio de una toma.",
    IntencionEntrante.NO_PUDO_TOMAR: (
        "El paciente informa que no pudo realizar una toma; requiere seguimiento del equipo."
    ),
    IntencionEntrante.PROBLEMA_TRATAMIENTO: (
        "REVISIÓN CLÍNICA · El paciente reporta un problema relacionado con su tratamiento. "
        "Leer el mensaje y responder desde el equipo clínico. El sistema no valora gravedad "
        "ni modifica la pauta."
    ),
    IntencionEntrante.ALTA: "El paciente pide volver a recibir mensajes.",
    IntencionEntrante.AYUDA: "El paciente pide hablar con la clinica o recibir ayuda.",
    IntencionEntrante.DESCONOCIDA: "Mensaje que el sistema no interpreta.",
}


# Etiquetas para la cola del personal cuando el modelo de decision reconoce la
# intencion de un mensaje libre. Orientan; no ejecutan nada.
MOTIVOS_TIPADOS: dict[Intencion, str] = {
    Intencion.BUSCAR_HORARIOS: "Quiere reservar una cita.",
    Intencion.CONSULTAR_CITAS: "Pregunta por sus citas.",
    Intencion.CANCELAR: "Parece querer cancelar (no se cancelo: confirme con el paciente).",
    Intencion.REPROGRAMAR: "Quiere cambiar la fecha de una cita.",
    Intencion.INFORMACION: "Pide informacion de la clinica.",
    Intencion.SEGUIMIENTO_TRATAMIENTO: "Pregunta por la siguiente fase de su tratamiento.",
    Intencion.BAJA_PROMOCIONES: (
        "Parece pedir la baja de promociones (no se aplico: confirme con el paciente)."
    ),
    Intencion.HABLAR_CON_PERSONA: "Pide hablar con una persona.",
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
    #: Tomas que el paciente confirmó respondiendo al recordatorio.
    tomas_registradas: int = 0
    #: Tomas que el paciente informó no haber podido realizar.
    tomas_omitidas: int = 0
    #: Recordatorios pospuestos por solicitud explícita del paciente.
    recordatorios_reprogramados: int = 0
    #: Imágenes asociadas como comprobante a un pago pendiente.
    comprobantes: int = 0


class ServicioConversaciones:
    """Aplica un cuerpo de webhook ya verificado."""

    def __init__(
        self,
        sesion: AsyncSession,
        reloj: Reloj,
        *,
        clasificador: ClasificadorIntencion | None = None,
        umbral_clinico: float = 0.35,
    ) -> None:
        self._sesion = sesion
        self._reloj = reloj
        # Solo se usa para **etiquetar** la derivacion de un mensaje que ya va
        # a una persona: urgente y clinico primero. Nunca ejecuta una accion;
        # cancelar o dar de baja siguen exigiendo la frase exacta.
        self._clasificador = clasificador
        self._umbral_clinico = umbral_clinico

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

        if intencion is IntencionEntrante.PROBLEMA_TRATAMIENTO:
            aviso = AvisoRevisionTratamiento(
                clinica_id=clinica_id,
                conversacion_id=conversacion.id,
                mensaje_entrante_id=creado,
            )
            self._sesion.add(aviso)
            await self._sesion.flush()
            await RepositorioAuditoria(self._sesion).registrar(
                [
                    construir_entrada(
                        accion=AccionAuditada.AVISO_TRATAMIENTO_CREADO,
                        principal=principal_sistema(clinica_id),
                        ahora=crudo.recibido_en,
                        entidad_tipo="aviso_revision_tratamiento",
                        entidad_id=aviso.id,
                        paciente_id=conversacion.paciente_id,
                        nivel_sensibilidad=NivelSensibilidad.CLINICO,
                    )
                ]
            )

        if intencion is IntencionEntrante.BAJA_PROMOCIONES:
            # Solo publicidad: los recordatorios de cita siguen llegando. Se
            # aplica con la frase exacta, nunca por probabilidad.
            revocados = await self._revocar_consentimiento(
                clinica_id=clinica_id,
                telefono=crudo.telefono,
                tipos=(TipoConsentimiento.PROMOCIONES,),
            )
            logger.info(
                "whatsapp.baja_promociones_aplicada",
                conversacion_id=str(conversacion.id),
                consentimientos_revocados=revocados,
            )
            return _con(resumen, bajas=resumen.bajas + 1)

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
        if intencion is not IntencionEntrante.PROBLEMA_TRATAMIENTO:
            resuelto = self._resolver_seleccion(conversacion, crudo.texto)
            if resuelto:
                return _con(resumen, identidades_resueltas=resumen.identidades_resueltas + 1)

            if conversacion.paciente_id is None and conversacion.seleccion_pendiente is None:
                preguntado = await self._preguntar_identidad(
                    conversacion, clinica_id, crudo.telefono
                )
                if preguntado:
                    return _con(resumen, preguntas_identidad=resumen.preguntas_identidad + 1)

        aplicado = await self._aplicar_sin_persona(
            conversacion, intencion, crudo, clinica_id, resumen
        )
        return aplicado or await self._derivar(conversacion, intencion, crudo, resumen)

    async def _derivar(
        self,
        conversacion: Conversacion,
        intencion: IntencionEntrante,
        crudo: MensajeEntranteCrudo,
        resumen: ResumenEntrada,
    ) -> ResumenEntrada:
        conversacion.estado = EstadoConversacion.EN_HANDOFF.value
        conversacion.motivo_handoff = MOTIVOS_HANDOFF.get(
            intencion, MOTIVOS_HANDOFF[IntencionEntrante.DESCONOCIDA]
        )
        if intencion is IntencionEntrante.DESCONOCIDA and crudo.texto:
            conversacion.motivo_handoff = await self._motivo_tipado(crudo.texto)
        return _con(resumen, derivados=resumen.derivados + 1)

    async def _aplicar_sin_persona(
        self,
        conversacion: Conversacion,
        intencion: IntencionEntrante,
        crudo: MensajeEntranteCrudo,
        clinica_id: uuid.UUID,
        resumen: ResumenEntrada,
    ) -> ResumenEntrada | None:
        """Respuestas del paciente que se aplican sin una persona.

        Solo con el paciente ya identificado en el hilo (un número puede ser
        de varias personas) y solo con un único destino posible. Devuelve
        `None` cuando no aplica: entonces se deriva como siempre.
        """
        if conversacion.paciente_id is None:
            return None
        respuesta_toma = await self._aplicar_respuesta_toma(
            conversacion, intencion, crudo, clinica_id, resumen
        )
        if respuesta_toma is not None:
            return respuesta_toma
        if crudo.tipo != "image":
            return None
        asociado = await self._asociar_comprobante(
            conversacion.paciente_id, clinica_id, crudo.external_id
        )
        conversacion.estado = EstadoConversacion.EN_HANDOFF.value
        if asociado:
            conversacion.motivo_handoff = "Comprobante de pago recibido: validar en Pagos."
            return _con(resumen, comprobantes=resumen.comprobantes + 1)
        conversacion.motivo_handoff = (
            "Envió una imagen (¿comprobante?) que no se pudo asociar a un pago."
        )
        return _con(resumen, derivados=resumen.derivados + 1)

    async def _aplicar_respuesta_toma(
        self,
        conversacion: Conversacion,
        intencion: IntencionEntrante,
        crudo: MensajeEntranteCrudo,
        clinica_id: uuid.UUID,
        resumen: ResumenEntrada,
    ) -> ResumenEntrada | None:
        paciente_id = conversacion.paciente_id
        if paciente_id is None:
            return None
        if intencion is IntencionEntrante.REGISTRAR_TOMA and await self._registrar_toma(
            paciente_id, clinica_id, crudo.recibido_en, tomada=True
        ):
            return _con(resumen, tomas_registradas=resumen.tomas_registradas + 1)
        if intencion is IntencionEntrante.NO_PUDO_TOMAR and await self._registrar_toma(
            paciente_id, clinica_id, crudo.recibido_en, tomada=False
        ):
            conversacion.estado = EstadoConversacion.EN_HANDOFF.value
            conversacion.motivo_handoff = MOTIVOS_HANDOFF[intencion]
            return _con(
                resumen,
                tomas_omitidas=resumen.tomas_omitidas + 1,
                derivados=resumen.derivados + 1,
            )
        if intencion is IntencionEntrante.RECORDAR_TOMA_DESPUES and await self._diferir_toma(
            paciente_id, clinica_id, crudo.recibido_en
        ):
            return _con(
                resumen,
                recordatorios_reprogramados=resumen.recordatorios_reprogramados + 1,
            )
        return None

    async def _toma_cercana(self, paciente_id: uuid.UUID, recibido_en: datetime) -> Toma | None:
        """Busca una toma pendiente cerca de su hora o del aviso pospuesto."""
        instante_recordatorio = func.coalesce(Toma.recordatorio_diferido_en, Toma.programada_en)
        return (
            await self._sesion.execute(
                select(Toma)
                .where(
                    Toma.paciente_id == paciente_id,
                    Toma.estado == EstadoToma.PENDIENTE.value,
                    instante_recordatorio >= recibido_en - timedelta(hours=3),
                    instante_recordatorio <= recibido_en + timedelta(minutes=30),
                )
                .order_by(func.abs(func.extract("epoch", instante_recordatorio - recibido_en)))
                .limit(1)
                .with_for_update()
            )
        ).scalar_one_or_none()

    async def _registrar_toma(
        self,
        paciente_id: uuid.UUID,
        clinica_id: uuid.UUID,
        recibido_en: datetime,
        *,
        tomada: bool,
    ) -> bool:
        """Registra TOMADA u OMITIDA sin cambiar la pauta prescrita.

        Ventana: tres horas antes hasta media hora después del aviso vigente.
        Una respuesta fuera de esa ventana no se asigna a una dosis por
        aproximacion; se deriva al equipo.
        """
        toma = await self._toma_cercana(paciente_id, recibido_en)
        if toma is None:
            return False
        toma.estado = EstadoToma.TOMADA.value if tomada else EstadoToma.OMITIDA.value
        toma.registrada_en = recibido_en
        toma.registrada_por_tipo = TipoActor.PACIENTE.value
        toma.registrada_por_id = paciente_id
        toma.nota_paciente = None if tomada else "El paciente informó que no pudo realizar la toma."
        # La toma se registra, pero jamás se mueve su hora prescrita. Cualquier
        # aviso diferido pendiente deja de aplicar al quedar TOMADA u OMITIDA.
        motivo = "Toma registrada por el paciente" if tomada else "Toma marcada como omitida"
        ahora = self._reloj.ahora()
        await self._sesion.execute(
            update(Recordatorio)
            .where(
                Recordatorio.entidad_tipo == ENTIDAD_TOMA,
                Recordatorio.entidad_id == toma.id,
                Recordatorio.estado == ESTADO_PROGRAMADO,
            )
            .values(
                estado=ESTADO_CANCELADO,
                cancelado_en=ahora,
                motivo_cancelacion=motivo,
            )
        )
        await self._sesion.execute(
            update(OutboxMensaje)
            .where(
                OutboxMensaje.entidad_origen_tipo == ENTIDAD_TOMA,
                OutboxMensaje.entidad_origen_id == toma.id,
                OutboxMensaje.estado == EstadoOutbox.PENDIENTE.value,
            )
            .values(
                estado=EstadoOutbox.DESCARTADO.value,
                ultimo_error=motivo,
                actualizado_en=ahora,
            )
        )
        await self._sesion.flush()
        await RepositorioAuditoria(self._sesion).registrar(
            [
                construir_entrada(
                    accion=AccionAuditada.TOMA_REGISTRADA,
                    principal=replace(principal_sistema(clinica_id), origen="WHATSAPP"),
                    ahora=recibido_en,
                    entidad_tipo="toma",
                    entidad_id=toma.id,
                    paciente_id=paciente_id,
                    nivel_sensibilidad=NivelSensibilidad.CLINICO,
                    tomada=tomada,
                    canal="WHATSAPP",
                )
            ]
        )
        logger.info(
            "whatsapp.toma_registrada" if tomada else "whatsapp.toma_omitida",
            toma_id=str(toma.id),
        )
        return True

    async def _diferir_toma(
        self, paciente_id: uuid.UUID, clinica_id: uuid.UUID, recibido_en: datetime
    ) -> bool:
        """Pospone 30 minutos el aviso, nunca la hora de la dosis."""
        toma = await self._toma_cercana(paciente_id, recibido_en)
        if toma is None:
            return False
        receta = (
            await self._sesion.execute(
                select(Receta)
                .join(RecetaMedicamento, RecetaMedicamento.receta_id == Receta.id)
                .where(
                    RecetaMedicamento.id == toma.receta_medicamento_id,
                    Receta.clinica_id == clinica_id,
                    Receta.paciente_id == paciente_id,
                    Receta.estado == EstadoReceta.CONFIRMADA.value,
                )
            )
        ).scalar_one_or_none()
        if receta is None:
            return False

        ahora = self._reloj.ahora()
        programado = max(ahora, recibido_en) + timedelta(minutes=30)
        # Una segunda posposición sustituye el aviso pendiente para evitar
        # dos mensajes para la misma toma.
        await self._sesion.execute(
            update(Recordatorio)
            .where(
                Recordatorio.entidad_tipo == ENTIDAD_TOMA,
                Recordatorio.entidad_id == toma.id,
                Recordatorio.tipo == TipoMensajeOutbox.TOMA_RECORDATORIO.value,
                Recordatorio.estado == ESTADO_PROGRAMADO,
            )
            .values(
                estado=ESTADO_CANCELADO,
                cancelado_en=ahora,
                motivo_cancelacion="El paciente pospuso el recordatorio.",
            )
        )
        await self._sesion.execute(
            update(OutboxMensaje)
            .where(
                OutboxMensaje.entidad_origen_tipo == ENTIDAD_TOMA,
                OutboxMensaje.entidad_origen_id == toma.id,
                OutboxMensaje.tipo == TipoMensajeOutbox.TOMA_RECORDATORIO.value,
                OutboxMensaje.estado == EstadoOutbox.PENDIENTE.value,
            )
            .values(
                estado=EstadoOutbox.DESCARTADO.value,
                ultimo_error="El paciente pospuso el recordatorio.",
                actualizado_en=ahora,
            )
        )
        toma.recordatorio_diferido_en = programado
        self._sesion.add(
            Recordatorio(
                tipo=TipoMensajeOutbox.TOMA_RECORDATORIO.value,
                clinica_id=receta.clinica_id,
                entidad_tipo=ENTIDAD_TOMA,
                entidad_id=toma.id,
                destinatario_tipo="PACIENTE",
                destinatario_id=paciente_id,
                programado_para=programado,
                estado=ESTADO_PROGRAMADO,
            )
        )
        await self._sesion.flush()
        logger.info("whatsapp.recordatorio_toma_pospuesto", toma_id=str(toma.id))
        return True

    async def _asociar_comprobante(
        self, paciente_id: uuid.UUID, clinica_id: uuid.UUID, external_id: str
    ) -> bool:
        """Pasa a «comprobante recibido» el único pago pendiente del paciente."""
        pendientes = list(
            (
                await self._sesion.execute(
                    select(Pago)
                    .join(Cita, Cita.id == Pago.cita_id)
                    .where(
                        Cita.paciente_id == paciente_id,
                        Pago.clinica_id == clinica_id,
                        Pago.estado.in_(["PENDING", "REJECTED"]),
                    )
                )
            ).scalars()
        )
        if len(pendientes) != 1:
            return False
        pago = pendientes[0]
        pago.estado = "PROOF_RECEIVED"
        pago.referencia = f"WhatsApp {external_id}"[:100]
        pago.comentario = "Comprobante enviado por el paciente por WhatsApp; falta validarlo."
        await self._sesion.flush()
        logger.info("whatsapp.comprobante_asociado", pago_id=str(pago.id))
        return True

    async def _motivo_tipado(self, texto: str) -> str:
        """Motivo de derivacion segun el modelo de decision, o el generico.

        La etiqueta ordena la cola del personal: una urgencia no puede quedar
        detras de diez preguntas por precios. El texto del paciente no se
        copia al motivo.
        """
        generico = MOTIVOS_HANDOFF[IntencionEntrante.DESCONOCIDA]
        if self._clasificador is None:
            return generico
        decision = await self._clasificador.clasificar(texto)
        if decision.urgencia >= self._umbral_clinico:
            return "PRIORIDAD: el mensaje parece describir una urgencia de salud."
        if decision.pregunta_clinica >= self._umbral_clinico:
            return "Consulta clinica: requiere respuesta de un profesional."
        return MOTIVOS_TIPADOS.get(decision.intencion, generico)

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

    async def _revocar_consentimiento(
        self,
        *,
        clinica_id: uuid.UUID,
        telefono: str,
        tipos: tuple[TipoConsentimiento, ...] = (
            TipoConsentimiento.COMUNICACION_WHATSAPP,
            TipoConsentimiento.RECORDATORIOS_MEDICACION,
            TipoConsentimiento.PROMOCIONES,
            TipoConsentimiento.DOCUMENTOS_WHATSAPP,
        ),
    ) -> int:
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
                Consentimiento.tipo.in_([tipo.value for tipo in tipos]),
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
