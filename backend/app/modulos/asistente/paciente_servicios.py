"""Agente del expediente: herramientas de WhatsApp y confirmación del operador."""

from __future__ import annotations

import re
import uuid
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.ia.conocimiento_paciente import buscador_publicado
from app.ia.conversacion import ProveedorDemostracion, ejecutar_turno
from app.ia.decisiones import ClasificadorIntencion
from app.ia.embeddings import ProveedorEmbeddings
from app.ia.herramientas.contrato import ContextoHerramienta, ResultadoHerramienta
from app.ia.herramientas.registro import despachar, herramienta
from app.ia.saneamiento import normalizar
from app.ia.seleccion_llm import FabricaConversacional
from app.modulos.asistente.paciente_modelos import SesionAgentePaciente
from app.modulos.asistente.paciente_repositorio import RepositorioAgentePaciente
from app.modulos.asistente.servicios import ServicioAsistente
from app.modulos.auditoria.repositorio import RepositorioAuditoria
from app.modulos.lista_espera.repositorio import RepositorioListaEspera
from app.modulos.organizacion.repositorio import RepositorioCatalogo
from app.nucleo.autorizacion import Principal
from app.nucleo.configuracion import Configuracion
from app.nucleo.errores import ConflictoEstado, DatosInvalidos, PermisoDenegado, RecursoNoEncontrado
from app.nucleo.huella_ambito import huella_ambito
from app.nucleo.reloj import Reloj

PERMISOS_OPERATIVOS = frozenset(
    {
        "agenda.leer",
        "cita.crear",
        "cita.cancelar",
        "cita.reprogramar",
        "pago.leer",
        "conversacion.responder",
    }
)
NOMBRES = {
    "hold_slot": "Apartar horario",
    "confirm_appointment": "Confirmar cita",
    "cancel_appointment": "Cancelar cita",
    "reschedule_appointment": "Reprogramar cita",
}


def acotar(principal: Principal, paciente_id: uuid.UUID) -> Principal:
    """Reduce el ámbito; nunca concede permisos o amplía ninguna dimensión."""
    return replace(
        principal,
        paciente_id=paciente_id,
        origen="WEB",
        ambito=replace(
            principal.ambito, pacientes=frozenset({paciente_id}), todos_los_pacientes=False
        ),
    )


class ServicioAgentePaciente:
    def __init__(
        self,
        sesion: AsyncSession,
        reloj: Reloj,
        configuracion: Configuracion,
        embeddings: ProveedorEmbeddings,
        fabrica: FabricaConversacional,
        asistente: ServicioAsistente,
        clasificador: ClasificadorIntencion | None = None,
    ):
        self.repo = RepositorioAgentePaciente(sesion)
        self.reloj, self.configuracion, self.embeddings, self.fabrica, self.asistente = (
            reloj,
            configuracion,
            embeddings,
            fabrica,
            asistente,
        )
        self.clasificador = clasificador

    async def acceso(self, principal: Principal, paciente_id: uuid.UUID) -> Principal:
        if principal.es_agente or not principal.tiene_permiso("paciente.leer_administrativo"):
            raise PermisoDenegado(
                "El agente del expediente requiere acceso del personal a la ficha."
            )
        if await self.repo.paciente(principal, paciente_id) is None:
            raise RecursoNoEncontrado("La ficha no está disponible.")
        return acotar(principal, paciente_id)

    async def abrir(
        self, principal: Principal, paciente_id: uuid.UUID, cita_id: uuid.UUID | None
    ) -> SesionAgentePaciente:
        actor = await self.acceso(principal, paciente_id)
        fila = SesionAgentePaciente(
            clinica_id=principal.clinica_id,
            usuario_id=principal.actor_id,
            paciente_id=paciente_id,
            negocio={
                "paciente_id": str(paciente_id),
                "_autorizacion": huella_ambito(actor),
                "_modo": "local"
                if isinstance(self.fabrica(), ProveedorDemostracion)
                else "configurado",
            },
            memoria={},
            propuesta=None,
            creado_en=self.reloj.ahora(),
            expira_en=self.reloj.ahora() + timedelta(hours=2),
        )
        if cita_id:
            await self.elegir_cita(actor, fila, cita_id)
        await self.repo.agregar(fila)
        return fila

    async def obtener(
        self, principal: Principal, paciente_id: uuid.UUID, id_hilo: uuid.UUID
    ) -> tuple[Principal, SesionAgentePaciente]:
        actor = await self.acceso(principal, paciente_id)
        fila = await self.repo.hilo(principal, paciente_id, id_hilo, self.reloj.ahora())
        if fila is None:
            raise RecursoNoEncontrado("La conversación no está disponible o caducó.")
        if fila.negocio.get("_autorizacion") != huella_ambito(actor):
            raise ConflictoEstado(
                "Sus accesos cambiaron. Abra una nueva conversación desde esta ficha."
            )
        return actor, fila

    async def elegir_cita(
        self, actor: Principal, fila: SesionAgentePaciente, cita_id: uuid.UUID
    ) -> None:
        if fila.propuesta:
            raise ConflictoEstado(
                "Confirme o descarte la propuesta antes de seleccionar otra cita."
            )
        if not actor.tiene_permiso("agenda.leer"):
            raise PermisoDenegado("No tiene permiso para consultar citas.")
        cita = await self.repo.cita(actor, fila.paciente_id, cita_id)
        if cita is None:
            raise RecursoNoEncontrado("La cita no pertenece al paciente y ámbito de esta ficha.")
        fila.negocio = {
            **{k: v for k, v in fila.negocio.items() if k.startswith("_")},
            "paciente_id": str(fila.paciente_id),
            "profesional_id": str(cita.profesional_id),
            "servicio_id": str(cita.servicio_id),
            "sede_id": str(cita.sede_id),
            "desde": self.reloj.ahora().isoformat(),
            "hasta": (self.reloj.ahora() + timedelta(days=7)).isoformat(),
        }
        fila.memoria = {
            "cita_id": str(cita.id),
            "inicio": cita.inicio.isoformat(),
            "zona_horaria": await self.repo.zona(cita.sede_id),
        }
        fila.propuesta = None

    async def configurar(
        self, actor: Principal, fila: SesionAgentePaciente, datos: dict[str, Any]
    ) -> None:
        if fila.propuesta:
            raise ConflictoEstado("Confirme o descarte la propuesta antes de cambiar la búsqueda.")
        if not actor.tiene_permiso("agenda.leer"):
            raise PermisoDenegado("No tiene permiso de agenda.")
        catalogo = RepositorioCatalogo(self.repo.sesion)
        servicio = next(
            (
                s
                for s in await catalogo.listar_servicios(actor)
                if str(s.id) == str(datos["servicio_id"])
            ),
            None,
        )
        if servicio is None:
            raise RecursoNoEncontrado("El servicio no está disponible.")
        await RepositorioListaEspera(self.repo.sesion).validar_alta(
            actor,
            fila.paciente_id,
            datos["sede_id"],
            servicio.especialidad_id,
            datos["servicio_id"],
            datos["profesional_id"],
        )
        fila.negocio = {
            **{k: v for k, v in fila.negocio.items() if k.startswith("_")},
            "paciente_id": str(fila.paciente_id),
            **{k: v.isoformat() if isinstance(v, datetime) else str(v) for k, v in datos.items()},
        }
        fila.memoria = {"zona_horaria": await self.repo.zona(datos["sede_id"])}
        fila.propuesta = None

    async def verificar_argumentos(
        self, actor: Principal, fila: SesionAgentePaciente, nombre: str, argumentos: dict[str, Any]
    ) -> dict[str, Any]:
        tool = herramienta(nombre)
        if tool is None or (tool.permiso and not actor.tiene_permiso(tool.permiso)):
            raise PermisoDenegado("Esta herramienta no está concedida a su rol.")
        try:
            validos = tool.argumentos.model_validate(argumentos).model_dump(mode="json")
        except ValidationError as exc:
            raise DatosInvalidos("La herramienta recibió argumentos inválidos.") from exc
        if "paciente_id" in validos and validos["paciente_id"] != str(fila.paciente_id):
            raise PermisoDenegado("La conversación está vinculada a otro paciente.")
        if (
            "cita_id" in validos
            and await self.repo.cita(actor, fila.paciente_id, uuid.UUID(validos["cita_id"])) is None
        ):
            raise RecursoNoEncontrado("La cita no pertenece a este expediente.")
        if nombre in {"find_availability", "hold_slot"}:
            for campo in ("servicio_id", "profesional_id", "sede_id"):
                if validos[campo] != fila.negocio.get(campo):
                    raise DatosInvalidos("Seleccione el contexto de agenda antes de esta gestión.")
        if nombre in {"hold_slot", "reschedule_appointment"}:
            inicio = datetime.fromisoformat(str(validos.get("inicio", validos.get("nuevo_inicio"))))
            if not any(
                datetime.fromisoformat(t["inicio"]) == inicio
                for t in fila.memoria.get("turnos", [])
            ):
                raise DatosInvalidos("Elija un horario ofrecido por el servidor.")
        if "cita_id" in validos and validos["cita_id"] != fila.memoria.get("cita_id"):
            raise DatosInvalidos("Seleccione primero la cita que desea gestionar.")
        if nombre == "reschedule_appointment":
            cita = await self.repo.cita(actor, fila.paciente_id, uuid.UUID(validos["cita_id"]))
            if cita is None or any(
                str(getattr(cita, k)) != fila.negocio.get(k)
                for k in ("sede_id", "servicio_id", "profesional_id")
            ):
                raise DatosInvalidos(
                    "Los horarios deben corresponder a la sede, servicio y profesional de la cita seleccionada."
                )
        return validos

    @staticmethod
    def actualizar_memoria(
        fila: SesionAgentePaciente, resultado: ResultadoHerramienta, nombre: str
    ) -> None:
        if not resultado.exito:
            return
        memoria = dict(fila.memoria)
        for campo in ("turnos", "cita_id", "inicio", "citas", "expira_en", "zona_horaria"):
            if campo in resultado.datos:
                memoria[campo] = resultado.datos[campo]
        if nombre == "hold_slot":
            memoria.pop("turnos", None)
        if nombre == "cancel_appointment":
            memoria.pop("cita_id", None)
        fila.memoria = memoria

    async def responder(
        self, actor: Principal, fila: SesionAgentePaciente, texto: str, clave: str
    ) -> ResultadoHerramienta:
        if fila.propuesta:
            raise ConflictoEstado(
                "Confirme o descarte la propuesta pendiente antes de otra gestión."
            )
        limpio = normalizar(texto).strip(" .!¿?¡")
        if limpio.startswith("protocolo"):
            respuesta = await self.asistente.responder(
                texto, principal=actor, paciente_id=fila.paciente_id
            )
            await RepositorioAuditoria(self.repo.sesion).registrar(respuesta.auditoria)
            return ResultadoHerramienta(
                True,
                respuesta.texto,
                {
                    "elementos": [
                        {"titulo": e.titulo, "detalle": e.detalle, "enlace": e.enlace}
                        for e in respuesta.elementos
                    ]
                },
            )
        if limpio in {
            "resumen",
            "resumen clinico",
            "resumen de la historia",
            "historial",
            "alergias",
            "antecedentes",
            "medicacion",
        }:
            respuesta = await self.asistente.responder(
                "resumen", principal=actor, paciente_id=fila.paciente_id
            )
            # Esta salida clínica queda local. No entra en la memoria del proveedor LLM.
            await RepositorioAuditoria(self.repo.sesion).registrar(respuesta.auditoria)
            return ResultadoHerramienta(
                True,
                respuesta.texto,
                {
                    "elementos": [
                        {"titulo": e.titulo, "detalle": e.detalle, "enlace": e.enlace}
                        for e in respuesta.elementos
                    ]
                },
            )
        if not fila.memoria.get("cita_id") and (
            limpio == "confirmar" or limpio.startswith(("cancelar:", "reprogramar:"))
        ):
            return ResultadoHerramienta(
                False,
                "Consulte Mis citas y pulse Usar esta cita antes de preparar esta gestión.",
            )
        if (
            limpio
            in {
                "buscar horarios",
                "disponibilidad",
                "buscar",
                "horarios",
                "reservar",
                "quiero una cita",
            }
            and "servicio_id" not in fila.negocio
        ):
            return ResultadoHerramienta(
                False,
                "Seleccione una cita de este paciente o configure sede, servicio, profesional y fechas para buscar horarios.",
            )
        operativo = replace(actor, permisos=actor.permisos & PERMISOS_OPERATIVOS)
        contexto = ContextoHerramienta(
            operativo, self.repo.sesion, self.reloj, correlacion_id=clave
        )

        async def invocar(
            nombre: str, argumentos: dict[str, Any], ctx: ContextoHerramienta
        ) -> ResultadoHerramienta:
            validos = await self.verificar_argumentos(actor, fila, nombre, argumentos)
            tool = herramienta(nombre)
            if tool and tool.escribe and nombre != "handoff_to_human":
                fila.propuesta = {
                    "id": str(uuid.uuid4()),
                    "nombre": nombre,
                    "argumentos": validos,
                    "expira_en": (self.reloj.ahora() + timedelta(minutes=5)).isoformat(),
                }
                return ResultadoHerramienta(
                    False,
                    "Propuesta preparada. Revise los datos y confirme la acción para este paciente.",
                    codigo="CONFIRMACION_PENDIENTE",
                )
            resultado = await despachar(nombre, validos, ctx)
            self.actualizar_memoria(fila, resultado, nombre)
            return resultado

        cambio = re.fullmatch(r"reprogramar\s*:\s*([1-5])\s*:\s*(.+)", texto, flags=re.IGNORECASE)
        if cambio:
            indice = int(cambio.group(1)) - 1
            turnos = fila.memoria.get("turnos", [])
            if not fila.memoria.get("cita_id") or indice >= len(turnos):
                raise DatosInvalidos(
                    "Seleccione una cita y consulte horarios antes de reprogramar."
                )
            return await invocar(
                "reschedule_appointment",
                {
                    "cita_id": fila.memoria["cita_id"],
                    "nuevo_inicio": turnos[indice]["inicio"],
                    "motivo": cambio.group(2).strip(),
                },
                contexto,
            )

        resultado, _ = await ejecutar_turno(
            self.fabrica(),
            texto,
            dict(fila.memoria),
            {k: v for k, v in fila.negocio.items() if not k.startswith("_")},
            contexto,
            clasificador=self.clasificador,
            buscar_conocimiento=buscador_publicado(
                self.repo.sesion, self.embeddings, self.configuracion, operativo, self.reloj
            ),
            invocar=invocar,
        )
        return resultado

    async def confirmar(
        self,
        actor: Principal,
        fila: SesionAgentePaciente,
        propuesta_id: uuid.UUID,
        aceptar: bool,
        clave: str,
    ) -> ResultadoHerramienta:
        propuesta = fila.propuesta
        if not propuesta or propuesta["id"] != str(propuesta_id):
            raise ConflictoEstado("La propuesta ya fue resuelta o cambió.")
        if not aceptar:
            fila.propuesta = None
            return ResultadoHerramienta(
                True, "Propuesta descartada. El registro conserva su estado."
            )
        if datetime.fromisoformat(propuesta["expira_en"]) <= self.reloj.ahora():
            raise ConflictoEstado("La propuesta caducó. Descártela y consulte datos actuales.")
        argumentos = await self.verificar_argumentos(
            actor, fila, propuesta["nombre"], propuesta["argumentos"]
        )
        paciente_id, id_hilo = fila.paciente_id, fila.id
        resultado = await despachar(
            propuesta["nombre"],
            argumentos,
            ContextoHerramienta(
                replace(actor, permisos=actor.permisos & PERMISOS_OPERATIVOS),
                self.repo.sesion,
                self.reloj,
                correlacion_id=clave,
            ),
        )
        if inspect(fila).expired:
            recuperada = await self.repo.hilo(actor, paciente_id, id_hilo, self.reloj.ahora())
            if (
                recuperada is None
                or not recuperada.propuesta
                or recuperada.propuesta["id"] != str(propuesta_id)
            ):
                raise ConflictoEstado(
                    "La conversación cambió mientras se verificaba la disponibilidad."
                )
            fila = recuperada
        fila.propuesta = None
        self.actualizar_memoria(fila, resultado, propuesta["nombre"])
        return resultado
