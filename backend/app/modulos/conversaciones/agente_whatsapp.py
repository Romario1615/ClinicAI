"""El agente atiende WhatsApp (ADR-0025).

Que decide este modulo y que no
-------------------------------
Decide **con que permisos** actua el agente en un hilo y **como responde**.
No decide que herramienta usar (eso es `app/ia/conversacion.py`) ni si una
peticion es clinica (eso es `app/ia/herramientas/limites.py`, que se aplica
antes del bucle y siempre deriva).

La politica (decision del usuario, 2026-10-09):

* consultar (horarios, citas, pagos, conocimiento) basta con tener paciente
  resuelto;
* cambiar una cita exige que el numero sea de **un solo** paciente (no
  elegido de una lista: elegir no verifica, ADR-0020) **y** verificacion
  `TELEFONO` o superior. Sin eso el principal no lleva los permisos de
  escritura: la herramienta lo rechaza y el bucle deriva a recepcion.

La barrera es de permisos en el backend, no una instruccion al modelo.

Por que el turno corre en su propia transaccion
-----------------------------------------------
La agenda, ante una colision, deshace la transaccion entera. Si el turno
corriera en la del webhook, una colision borraria tambien el mensaje recibido.
Por eso `ServicioConversaciones` guarda el mensaje, el webhook confirma, y
solo despues se ejecutan los turnos pendientes, cada uno con su confirmacion.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ia.conocimiento_paciente import buscador_publicado
from app.ia.conversacion import ProveedorConversacional, ejecutar_turno
from app.ia.decisiones import ClasificadorIntencion
from app.ia.embeddings import ProveedorEmbeddings
from app.ia.herramientas.contrato import ContextoHerramienta
from app.ia.proveedores_clinica import leer_integracion
from app.mensajeria.adaptadores import RegistroCanales
from app.mensajeria.servicios import ServicioOutbox, SolicitudEnvio
from app.modulos.agenda.modelos import Cita
from app.modulos.conversaciones.identificacion import identificar
from app.modulos.conversaciones.modelos import Conversacion, EstadoConversacion
from app.modulos.outbox.modelos import CanalOutbox, TipoMensajeOutbox
from app.modulos.pacientes.modelos import Paciente
from app.nucleo.autorizacion import Ambito, NivelSensibilidad, Principal, TipoActor
from app.nucleo.configuracion import Configuracion
from app.nucleo.registro import obtener_logger
from app.nucleo.reloj import Reloj

logger = obtener_logger(__name__)

#: Codigo de la integracion por clinica (Configuracion > Integraciones).
INTEGRACION = "agente_whatsapp"

_PERMISOS_CONSULTA = frozenset(
    {"agenda.leer", "pago.leer", "conocimiento.leer", "conversacion.responder"}
)
_PERMISOS_CAMBIO = frozenset({"cita.crear", "cita.cancelar", "cita.reprogramar"})
_VERIFICADO = frozenset({"TELEFONO", "DOCUMENTO", "PRESENCIAL"})
#: Ventana de busqueda de horarios que el agente ofrece por defecto.
DIAS_BUSQUEDA = 7
#: Campos del resultado de una herramienta que el agente recuerda en el hilo.
_CAMPOS_MEMORIA = ("turnos", "cita_id", "inicio", "citas", "expira_en", "zona_horaria")

MENSAJE_BIENVENIDA = (
    "Gracias. ¿En qué le puedo ayudar? Puede escribir «buscar horarios», «mis citas», "
    "«mis pagos» o «hablar con una persona»."
)


async def habilitado(sesion: AsyncSession, clinica_id: uuid.UUID) -> bool:
    """¿La clinica encendio el agente? Apagado por defecto (ADR-0025)."""
    integracion = await leer_integracion(sesion, clinica_id, INTEGRACION)
    return integracion is not None and integracion.habilitada


async def responder(
    sesion: AsyncSession,
    reloj: Reloj,
    conversacion: Conversacion,
    texto: str,
    clave: str,
    *,
    autor_usuario_id: uuid.UUID | None = None,
) -> uuid.UUID | None:
    """Encola una respuesta de texto libre en el hilo.

    La clave de deduplicacion hace idempotente el reintento (de Meta o del
    doble clic): el mismo origen no produce dos respuestas. El origen dice
    quien escribio: el hilo (agente) o la persona del equipo.
    """
    return await ServicioOutbox(sesion, reloj, RegistroCanales()).encolar(
        SolicitudEnvio(
            tipo=TipoMensajeOutbox.RESPUESTA_CONVERSACION,
            canal=CanalOutbox.WHATSAPP,
            destino_tipo="CONVERSACION",
            destino_id=conversacion.id,
            clave_deduplicacion=clave,
            variables={"mensaje": texto},
            clinica_id=conversacion.clinica_id,
            entidad_origen_tipo="usuario" if autor_usuario_id else "conversacion",
            entidad_origen_id=autor_usuario_id or conversacion.id,
        )
    )


@dataclass(frozen=True, slots=True)
class AgenteWhatsapp:
    """Lo que el canal necesita para que el agente conteste.

    `proveedor` fabrica el modelo de cada turno: el determinista de
    demostracion o el LLM que la clinica configuro.
    """

    proveedor: Callable[[], ProveedorConversacional]
    clasificador: ClasificadorIntencion | None = None
    umbrales: tuple[float, float] = (0.35, 0.85)
    conocimiento: tuple[ProveedorEmbeddings, Configuracion] | None = None

    async def atender(
        self,
        sesion: AsyncSession,
        reloj: Reloj,
        conversacion_id: uuid.UUID,
        texto: str,
        mensaje_id: uuid.UUID,
    ) -> bool:
        """Un turno del agente sobre un mensaje ya guardado.

        Devuelve si contesto. No contesta si el hilo paso a manos del personal
        o se cerro entre la recepcion y el turno.
        """
        conversacion = await sesion.get(Conversacion, conversacion_id, with_for_update=True)
        if (
            conversacion is None
            or conversacion.paciente_id is None
            or conversacion.estado != EstadoConversacion.ABIERTA.value
        ):
            return False
        paciente = await sesion.get(Paciente, conversacion.paciente_id)
        if paciente is None:
            return False

        actor = await self._principal(sesion, reloj, conversacion, paciente)
        estado = dict(conversacion.agente or {})
        memoria: dict[str, Any] = dict(estado.get("memoria") or {})
        negocio = await self._negocio(sesion, reloj, paciente)
        contexto = ContextoHerramienta(actor, sesion, reloj, conversacion.id)
        resultado, herramientas = await ejecutar_turno(
            self.proveedor(),
            texto,
            memoria,
            negocio,
            contexto,
            clasificador=self.clasificador,
            umbral_clinico=self.umbrales[0],
            umbral_intencion=self.umbrales[1],
            buscar_conocimiento=(
                buscador_publicado(sesion, self.conocimiento[0], self.conocimiento[1], actor, reloj)
                if self.conocimiento is not None
                else None
            ),
        )
        # Una colision de agenda deshace la transaccion del turno (no la del
        # mensaje, ya confirmada). Se recupera el hilo y se contesta igual con
        # el mensaje seguro que tradujo la herramienta.
        if conversacion not in sesion or inspect(conversacion).expired:
            recuperada = await sesion.get(Conversacion, conversacion_id, with_for_update=True)
            if recuperada is None:
                return False
            conversacion = recuperada
        if resultado.exito:
            for campo in _CAMPOS_MEMORIA:
                if campo in resultado.datos:
                    memoria[campo] = resultado.datos[campo]
            if "hold_slot" in herramientas:
                memoria.pop("turnos", None)
            if "cancel_appointment" in herramientas:
                memoria.pop("cita_id", None)
        # Asignar un dict nuevo: mutar el JSONB en sitio no lo marca sucio.
        conversacion.agente = {"memoria": memoria, "negocio": negocio}
        conversacion.ultima_actividad_en = reloj.ahora()
        if resultado.mensaje:
            await responder(sesion, reloj, conversacion, resultado.mensaje, f"agente:{mensaje_id}")
        logger.info(
            "whatsapp.agente_turno",
            conversacion_id=str(conversacion.id),
            herramientas=herramientas,
            requiere_humano=resultado.requiere_humano,
        )
        return True

    async def _principal(
        self,
        sesion: AsyncSession,
        reloj: Reloj,
        conversacion: Conversacion,
        paciente: Paciente,
    ) -> Principal:
        """El agente actua por un paciente, con ambito de ese paciente solo."""
        permisos = _PERMISOS_CONSULTA
        if await puede_cambiar(sesion, reloj, conversacion, paciente):
            permisos = permisos | _PERMISOS_CAMBIO
        return Principal(
            actor_tipo=TipoActor.AGENTE_IA,
            actor_id=paciente.id,
            clinica_id=conversacion.clinica_id,
            permisos=permisos,
            ambito=Ambito(
                clinica_id=conversacion.clinica_id,
                todas_las_sedes=True,
                todas_las_especialidades=True,
                todos_los_profesionales=True,
                pacientes=frozenset({paciente.id}),
                todos_los_pacientes=False,
                nivel_maximo=NivelSensibilidad.ADMINISTRATIVO,
            ),
            paciente_id=paciente.id,
            origen="WHATSAPP",
        )

    async def _negocio(
        self, sesion: AsyncSession, reloj: Reloj, paciente: Paciente
    ) -> dict[str, Any]:
        """Contexto de busqueda: la sede, el servicio y el profesional habituales.

        Sin atenciones previas no hay referencia: el agente consulta citas y
        pagos, pero buscar horarios deriva a recepcion para la primera reserva.
        """
        ahora = reloj.ahora()
        negocio: dict[str, Any] = {
            "paciente_id": str(paciente.id),
            "desde": ahora.isoformat(),
            "hasta": (ahora + timedelta(days=DIAS_BUSQUEDA)).isoformat(),
        }
        ultima = (
            await sesion.execute(
                select(Cita)
                .where(Cita.paciente_id == paciente.id, Cita.clinica_id == paciente.clinica_id)
                .order_by(Cita.inicio.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if ultima is not None:
            negocio.update(
                sede_id=str(ultima.sede_id),
                servicio_id=str(ultima.servicio_id),
                profesional_id=str(ultima.profesional_id),
            )
        return negocio


async def puede_cambiar(
    sesion: AsyncSession, reloj: Reloj, conversacion: Conversacion, paciente: Paciente
) -> bool:
    """Numero de un solo paciente y verificacion suficiente (ADR-0025).

    Se recalcula en cada turno contra las fichas actuales: si mientras tanto
    aparece otra ficha con el mismo numero, el permiso de cambiar se pierde.
    """
    if paciente.nivel_verificacion not in _VERIFICADO:
        return False
    identidad = await identificar(
        sesion,
        clinica_id=conversacion.clinica_id,
        telefono=conversacion.telefono,
        ahora=reloj.ahora(),
    )
    return identidad.resuelto and identidad.paciente_id == paciente.id
