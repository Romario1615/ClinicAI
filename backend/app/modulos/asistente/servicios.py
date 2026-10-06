"""Asistente interno del personal: agenda, resumen, conocimiento y borradores.

Qué puede y qué no
------------------
* Actúa **como quien escribe**: cada intención exige el permiso que exigiría
  la pantalla equivalente, y cada lectura clínica pasa por la relación
  asistencial y se audita.
* **No toma decisiones clínicas.** Ante «qué le receto» o «qué dosis» no
  responde: ofrece el resumen de la historia y los protocolos aprobados.
* **Responde citando** solo documentos aprobados y vigentes. Sin fuente, lo
  dice; no improvisa.
* **Escribe solo borradores**: un documento de conocimiento en `DRAFT` o una
  campaña en borrador, a nombre de quien lo pidió. Publicarlos sigue
  exigiendo la aprobación de una persona con permiso.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ia.embeddings import ProveedorEmbeddings
from app.ia.recuperador import MENSAJE_SIN_FUENTE, Recuperador, contexto_desde_principal
from app.modulos.agenda.modelos import Cita
from app.modulos.agenda.recorrido_repositorio import ESTADOS_ACTIVOS, RepositorioRecorrido
from app.modulos.agenda.recorrido_servicios import ServicioRecorrido
from app.modulos.agenda.repositorio import RepositorioAgenda
from app.modulos.agenda.servicios import ServicioAgenda
from app.modulos.asistente.intenciones import Intencion, Interpretacion, interpretar
from app.modulos.conocimiento.modelos import KnowledgeDocument, TipoDocumentoConocimiento
from app.modulos.conocimiento.servicios import ServicioConocimiento
from app.modulos.historia import resumen_clinico
from app.modulos.organizacion.modelos import Clinica, Consultorio, Servicio
from app.modulos.pacientes.modelos import Paciente
from app.modulos.promociones.esquemas import CampanaNueva
from app.modulos.promociones.servicios import ServicioPromociones
from app.nucleo.auditoria import AccionAuditada, EntradaAuditoria, construir_entrada
from app.nucleo.autorizacion import NivelSensibilidad, Principal
from app.nucleo.configuracion import Configuracion
from app.nucleo.errores import PermisoDenegado
from app.nucleo.reloj import Reloj

LARGO_FRAGMENTO = 420
MAX_FUENTES = 3
LARGO_MINIMO_BORRADOR = 10
LARGO_TITULO = 60


@dataclass(frozen=True, slots=True)
class Elemento:
    titulo: str
    detalle: str | None = None
    enlace: str | None = None


@dataclass(frozen=True, slots=True)
class Respuesta:
    intencion: Intencion
    texto: str
    elementos: tuple[Elemento, ...] = ()
    enlace: str | None = None
    sugerencias: tuple[str, ...] = ()
    auditoria: tuple[EntradaAuditoria, ...] = field(default_factory=tuple)


class RepositorioAsistente(RepositorioAgenda):
    async def citas_del_dia(
        self,
        principal: Principal,
        *,
        desde: datetime,
        hasta: datetime,
        profesional_id: uuid.UUID | None,
    ) -> list[tuple[Cita, str, str, str | None]]:
        """Citas activas del día con paciente, servicio y consultorio, dentro del ámbito."""
        consulta = (
            select(Cita, Paciente.nombre, Paciente.apellido, Servicio.nombre, Consultorio.nombre)
            .join(Paciente, Paciente.id == Cita.paciente_id)
            .join(Servicio, Servicio.id == Cita.servicio_id)
            .outerjoin(Consultorio, Consultorio.id == Cita.consultorio_id)
            .where(Cita.inicio >= desde, Cita.inicio < hasta, Cita.estado.in_(ESTADOS_ACTIVOS))
        )
        if profesional_id is not None:
            consulta = consulta.where(Cita.profesional_id == profesional_id)
        consulta = self._filtrar_por_ambito(consulta, principal).order_by(Cita.inicio)
        return [
            (fila[0], f"{fila[1]} {fila[2]}".strip(), fila[3], fila[4])
            for fila in (await self._sesion.execute(consulta)).all()
        ]

    async def zona_de_clinica(self, clinica_id: uuid.UUID | None) -> str:
        if clinica_id is None:
            return "America/Guayaquil"
        zona = (
            await self._sesion.execute(select(Clinica.zona_horaria).where(Clinica.id == clinica_id))
        ).scalar_one_or_none()
        return zona or "America/Guayaquil"

    async def titulos(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not ids:
            return {}
        filas = await self._sesion.execute(
            select(KnowledgeDocument.id, KnowledgeDocument.titulo).where(
                KnowledgeDocument.id.in_(ids)
            )
        )
        return {fila[0]: str(fila[1]) for fila in filas.all()}


class ServicioAsistente:
    def __init__(
        self,
        sesion: AsyncSession,
        reloj: Reloj,
        configuracion: Configuracion,
        embeddings: ProveedorEmbeddings,
        promociones: ServicioPromociones,
    ) -> None:
        self._sesion = sesion
        self._reloj = reloj
        self._configuracion = configuracion
        self._embeddings = embeddings
        self._promociones = promociones
        self._repo = RepositorioAsistente(sesion)

    async def responder(
        self, texto: str, *, principal: Principal, paciente_id: uuid.UUID | None = None
    ) -> Respuesta:
        if principal.es_agente or principal.clinica_id is None:
            raise PermisoDenegado("El asistente es solo para el personal de la clínica.")
        interpretacion = interpretar(texto)
        respuesta = await self._despachar(interpretacion, principal, paciente_id)
        registro = construir_entrada(
            accion=AccionAuditada.ASISTENTE_CONSULTADO,
            principal=principal,
            ahora=self._reloj.ahora(),
            entidad_tipo="asistente",
            entidad_id=None,
            paciente_id=paciente_id,
            intencion=respuesta.intencion.value,
        )
        return Respuesta(
            intencion=respuesta.intencion,
            texto=respuesta.texto,
            elementos=respuesta.elementos,
            enlace=respuesta.enlace,
            sugerencias=respuesta.sugerencias or self.sugerencias(principal),
            auditoria=(*respuesta.auditoria, registro),
        )

    def sugerencias(self, principal: Principal) -> tuple[str, ...]:
        opciones: list[str] = []
        if principal.tiene_permiso("agenda.leer"):
            opciones += ["Mi agenda de hoy", "¿Quién sigue?"]
        if principal.tiene_permiso("historia_clinica.leer"):
            opciones.append("Resumen del paciente")
        if principal.tiene_permiso("cita.reprogramar"):
            opciones.append("Peticiones de más tiempo")
        if principal.tiene_permiso("conocimiento.cargar"):
            opciones.append("Agrega al conocimiento: …")
        if principal.tiene_permiso("promocion.gestionar"):
            opciones.append("Crea una promoción: …")
        return tuple(opciones)

    async def _despachar(
        self, interpretacion: Interpretacion, principal: Principal, paciente_id: uuid.UUID | None
    ) -> Respuesta:
        intencion = interpretacion.intencion
        fijas = {
            Intencion.AYUDA: (
                "Puedo mostrarle su agenda, quién sigue, el resumen de un paciente y responder "
                "con los documentos aprobados de la clínica. También preparo borradores de "
                "conocimiento y de promociones para que alguien los apruebe. No tomo "
                "decisiones clínicas."
            ),
            Intencion.DECISION_CLINICA: (
                "Eso es una decisión clínica y la toma el profesional. Puedo mostrarle el "
                "resumen de la historia del paciente o buscar el protocolo aprobado: escriba "
                "«resumen» o «protocolo de …»."
            ),
        }
        if intencion in fijas:
            return Respuesta(intencion, fijas[intencion])
        if intencion in (Intencion.AGENDA, Intencion.SIGUIENTE):
            return await self._agenda(intencion, principal)
        if intencion is Intencion.RESUMEN:
            return await self._resumen(principal, paciente_id)
        manejadores = {
            Intencion.PROLONGACIONES: lambda: self._prolongaciones(principal),
            Intencion.BORRADOR_CONOCIMIENTO: lambda: self._borrador_conocimiento(
                principal, interpretacion.contenido
            ),
            Intencion.BORRADOR_PROMOCION: lambda: self._borrador_promocion(
                principal, interpretacion.contenido
            ),
        }
        manejador = manejadores.get(intencion)
        if manejador is not None:
            return await manejador()
        return await self._pregunta(principal, interpretacion.contenido)

    # ------------------------------------------------------------------
    async def _agenda(self, intencion: Intencion, principal: Principal) -> Respuesta:
        if not principal.tiene_permiso("agenda.leer"):
            return _sin_permiso(intencion, "la agenda")
        zona = ZoneInfo(await self._repo.zona_de_clinica(principal.clinica_id))
        ahora = self._reloj.ahora()
        inicio_dia = ahora.astimezone(zona).replace(hour=0, minute=0, second=0, microsecond=0)
        citas = await self._repo.citas_del_dia(
            principal,
            desde=inicio_dia,
            hasta=inicio_dia + timedelta(days=1),
            profesional_id=principal.profesional_id,
        )
        if intencion is Intencion.SIGUIENTE:
            esperando = [c for c in citas if c[0].llegada_en and not c[0].atencion_iniciada_en]
            proximas = [c for c in citas if c[0].inicio >= ahora - timedelta(minutes=15)]
            candidatas = esperando or proximas
            if not candidatas:
                return Respuesta(intencion, "No tiene más pacientes hoy.", enlace="/agenda")
            cita, paciente, servicio, consultorio = candidatas[0]
            estado = "ya llegó y le espera" if cita.llegada_en else "aún no ha llegado"
            return Respuesta(
                intencion,
                f"Sigue {paciente}, {estado}.",
                (_elemento_cita(cita, paciente, servicio, consultorio, zona),),
                enlace="/agenda",
            )
        if not citas:
            return Respuesta(intencion, "No tiene citas para hoy.", enlace="/agenda")
        return Respuesta(
            intencion,
            f"Hoy tiene {len(citas)} cita(s).",
            tuple(_elemento_cita(c, p, s, k, zona) for c, p, s, k in citas),
            enlace="/agenda",
        )

    async def _resumen(self, principal: Principal, paciente_id: uuid.UUID | None) -> Respuesta:
        if not principal.tiene_permiso("historia_clinica.leer"):
            return _sin_permiso(Intencion.RESUMEN, "la historia clínica")
        if paciente_id is None:
            return Respuesta(
                Intencion.RESUMEN,
                "Elija primero el paciente en el selector de arriba y vuelva a pedir el resumen.",
            )
        ahora = self._reloj.ahora()
        datos = await resumen_clinico.construir(
            self._sesion, principal, paciente_id, ahora, redaccion=False
        )
        elementos: list[Elemento] = []
        if datos.alergias:
            elementos.append(Elemento("Alergias", ", ".join(a.sustancia for a in datos.alergias)))
        else:
            elementos.append(Elemento("Alergias", "Sin alergias registradas"))
        elementos.append(
            Elemento(
                "Medicación activa",
                "; ".join(
                    " ".join(
                        p
                        for p in (
                            m.nombre,
                            m.dosis,
                            "cuando sea necesario"
                            if m.cuando_sea_necesario
                            else f"cada {m.frecuencia_horas} h"
                            if m.frecuencia_horas
                            else None,
                        )
                        if p
                    )
                    for m in datos.medicacion_activa
                )
                or "Sin medicación activa",
            )
        )
        for nota in datos.ultimas_notas[:3]:
            elementos.append(
                Elemento(
                    f"Nota del {nota.fecha:%d/%m/%Y}",
                    nota.motivo_consulta or nota.plan or None,
                )
            )
        for plan in datos.planes[:2]:
            elementos.append(Elemento(f"Plan: {plan.titulo}", plan.estado))
        entrada = construir_entrada(
            accion=AccionAuditada.HISTORIA_CONSULTADA,
            principal=principal,
            ahora=ahora,
            entidad_tipo="paciente",
            entidad_id=paciente_id,
            paciente_id=paciente_id,
            nivel_sensibilidad=NivelSensibilidad.CLINICO,
            vista="asistente_resumen",
        )
        return Respuesta(
            Intencion.RESUMEN,
            "Resumen de lo registrado en la historia, sin interpretación.",
            tuple(elementos),
            enlace=f"/historia-clinica?paciente={paciente_id}",
            auditoria=(entrada,),
        )

    async def _prolongaciones(self, principal: Principal) -> Respuesta:
        if not principal.tiene_permiso("cita.reprogramar"):
            return _sin_permiso(Intencion.PROLONGACIONES, "las peticiones de más tiempo")
        repo = RepositorioRecorrido(self._sesion)
        servicio = ServicioRecorrido(
            self._sesion, repo, ServicioAgenda(self._sesion, repo, self._reloj), self._reloj
        )
        pendientes = await servicio.pendientes(principal=principal)
        if not pendientes:
            return Respuesta(Intencion.PROLONGACIONES, "No hay peticiones de más tiempo.")
        return Respuesta(
            Intencion.PROLONGACIONES,
            f"Hay {len(pendientes)} petición(es) esperando su decisión.",
            tuple(
                Elemento(
                    f"{p.profesional} pide +{p.minutos} min",
                    f"Paciente en atención: {p.paciente}. Afecta a "
                    + (", ".join(c.paciente for c in p.conflictos) or "nadie"),
                    enlace="/agenda",
                )
                for p in pendientes
            ),
            enlace="/agenda",
        )

    async def _borrador_conocimiento(self, principal: Principal, contenido: str) -> Respuesta:
        if not principal.tiene_permiso("conocimiento.cargar"):
            return _sin_permiso(Intencion.BORRADOR_CONOCIMIENTO, "la base de conocimiento")
        if len(contenido) < LARGO_MINIMO_BORRADOR:
            return Respuesta(
                Intencion.BORRADOR_CONOCIMIENTO,
                "Escriba el contenido después de dos puntos. Ejemplo: «Agrega al conocimiento: "
                "los sábados atendemos de 8:00 a 13:00».",
            )
        servicio = ServicioConocimiento(
            self._sesion,
            self._reloj,
            self._embeddings,
            tamano_fragmento=self._configuracion.rag_tamano_fragmento,
            solape_fragmento=self._configuracion.rag_solape_fragmento,
        )
        titulo = _titulo(contenido)
        documento = await servicio.crear_documento(
            principal=principal,
            titulo=titulo,
            tipo=TipoDocumentoConocimiento.PREGUNTA_FRECUENTE.value,
        )
        resultado = await servicio.ingerir_texto(
            principal=principal,
            document_id=documento.id,
            contenido=contenido,
            notas_cambio="Borrador creado desde el asistente",
        )
        entrada = construir_entrada(
            accion=AccionAuditada.DOCUMENTO_CARGADO,
            principal=principal,
            ahora=self._reloj.ahora(),
            entidad_tipo="knowledge_document",
            entidad_id=documento.id,
            version=resultado.version,
            fragmentos=resultado.fragmentos,
            riesgo_inyeccion=resultado.riesgo_inyeccion.value,
            origen_asistente=True,
        )
        aviso = (
            " El texto tiene expresiones que parecen instrucciones y requerirá revisión."
            if resultado.requiere_revision
            else ""
        )
        return Respuesta(
            Intencion.BORRADOR_CONOCIMIENTO,
            f"Borrador «{titulo}» creado. Nadie lo verá hasta que se apruebe en Conocimiento."
            + aviso,
            enlace="/conocimiento",
            auditoria=(entrada,),
        )

    async def _borrador_promocion(self, principal: Principal, contenido: str) -> Respuesta:
        if not principal.tiene_permiso("promocion.gestionar"):
            return _sin_permiso(Intencion.BORRADOR_PROMOCION, "las promociones")
        if len(contenido) < LARGO_MINIMO_BORRADOR:
            return Respuesta(
                Intencion.BORRADOR_PROMOCION,
                "Escriba el texto después de dos puntos. Ejemplo: «Crea una promoción: limpieza "
                "dental con 20 % de descuento este mes».",
            )
        campana = await self._promociones.crear(
            CampanaNueva(nombre=_titulo(contenido), texto=contenido[:500]), principal
        )
        entrada = construir_entrada(
            accion=AccionAuditada.CAMPANA_CREADA,
            principal=principal,
            ahora=self._reloj.ahora(),
            entidad_tipo="campana_promocion",
            entidad_id=campana.id,
            origen_asistente=True,
        )
        return Respuesta(
            Intencion.BORRADOR_PROMOCION,
            f"Campaña «{campana.nombre}» creada en borrador. Revísela, elija el público y "
            "envíela a aprobación desde Promociones.",
            enlace="/promociones",
            auditoria=(entrada,),
        )

    async def _pregunta(self, principal: Principal, consulta: str) -> Respuesta:
        if not principal.tiene_permiso("conocimiento.leer"):
            return _sin_permiso(Intencion.PREGUNTA, "la base de conocimiento")
        ahora = self._reloj.ahora()
        resultado = await Recuperador(
            self._sesion,
            self._embeddings,
            top_k=MAX_FUENTES,
            candidatos=self._configuracion.rag_top_k_candidatos,
            peso_vectorial=self._configuracion.rag_peso_vectorial,
        ).recuperar(consulta=consulta, contexto=contexto_desde_principal(principal, ahora=ahora))
        entrada = construir_entrada(
            accion=(
                AccionAuditada.CONSULTA_RAG
                if resultado.hay_fuente
                else AccionAuditada.RAG_SIN_FUENTE
            ),
            principal=principal,
            ahora=ahora,
            entidad_tipo="knowledge_document",
            entidad_id=resultado.documentos[0] if resultado.documentos else None,
            fuentes=resultado.referencias,
            resultados=len(resultado.fragmentos),
        )
        if not resultado.hay_fuente:
            return Respuesta(
                Intencion.PREGUNTA,
                "No hay información aprobada sobre eso. Si debería estar, agréguela con "
                "«Agrega al conocimiento: …» y pida su aprobación.",
                auditoria=(entrada,),
            )
        titulos = await self._repo.titulos(resultado.documentos)
        return Respuesta(
            Intencion.PREGUNTA,
            "Esto dicen los documentos aprobados:",
            tuple(
                Elemento(
                    titulos.get(f.document_id, "Documento aprobado"),
                    _recortar(f.contenido),
                    enlace="/conocimiento",
                )
                for f in resultado.fragmentos[:MAX_FUENTES]
            ),
            auditoria=(entrada,),
        )


def _elemento_cita(
    cita: Cita, paciente: str, servicio: str, consultorio: str | None, zona: ZoneInfo
) -> Elemento:
    estado = (
        "en atención"
        if cita.atencion_iniciada_en
        else "esperando"
        if cita.llegada_en
        else "por llegar"
    )
    lugar = f" · {consultorio}" if consultorio else ""
    return Elemento(
        f"{cita.inicio.astimezone(zona):%H:%M} {paciente}",
        f"{servicio}{lugar} · {estado}",
        enlace="/agenda",
    )


def _titulo(contenido: str) -> str:
    linea = " ".join(contenido.split())
    return linea if len(linea) <= LARGO_TITULO else linea[: LARGO_TITULO - 3].rstrip() + "…"


def _recortar(texto: str) -> str:
    limpio = " ".join(texto.split())
    return limpio if len(limpio) <= LARGO_FRAGMENTO else limpio[: LARGO_FRAGMENTO - 1] + "…"


def _sin_permiso(intencion: Intencion, que: str) -> Respuesta:
    return Respuesta(intencion, f"Su rol no tiene acceso a {que}.")


__all__ = ["MENSAJE_SIN_FUENTE", "Elemento", "Respuesta", "ServicioAsistente"]
