"""Ciclo de vida de un documento de conocimiento e ingesta.

La regla que gobierna este modulo
---------------------------------
**Solo un documento aprobado y vigente es recuperable por el agente**
(RF-M05). Y aprobar es un acto de una persona, con nombre y fecha: el
`CHECK aprobado_con_responsable` lo exige en el motor, no solo aqui.

El motivo no es burocratico. Lo que hay en la base de conocimiento es lo que
el agente le va a decir a un paciente. Si un borrador a medio escribir fuera
recuperable, el agente responderia con el borrador -- y nadie sabria que lo
hizo hasta que alguien se quejara.

Por que el estado se copia a los fragmentos
-------------------------------------------
`knowledge_chunks` repite `status`, la vigencia y el nivel de sensibilidad del
documento (ADR-0013). Esa copia es lo que permite que el filtro del RAG viva en
un unico `WHERE` sin uniones.

El precio es mantenerla sincronizada, y se paga **aqui**: cada cambio de
estado o de vigencia propaga a los fragmentos **en la misma transaccion**. Si
se propagara despues, o en otra transaccion, existiria una ventana en la que
un documento archivado seguiria siendo recuperable. Hay una prueba que archiva
un documento y comprueba que sus fragmentos dejan de aparecer.

Sobre la inyeccion de prompt
----------------------------
Al ingerir se analiza el texto (ADR-0014) y el resultado se guarda. Un riesgo
alto **bloquea la aprobacion** hasta que una persona lo revise de forma
explicita: no se rechaza el documento -- un protocolo legitimo puede contener
la frase «ignore las indicaciones previas si hay fiebre» --, se detiene la
aprobacion automatica.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ia.embeddings import ProveedorEmbeddings
from app.ia.saneamiento import RiesgoInyeccion, analizar
from app.modulos.conocimiento.fragmentacion import fragmentar
from app.modulos.conocimiento.modelos import (
    EstadoDocumento,
    EstadoIngesta,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeEmbedding,
    KnowledgeIngestionJob,
    KnowledgeVersion,
)
from app.nucleo.autorizacion import Principal
from app.nucleo.bd import ejecutar_escritura
from app.nucleo.errores import (
    DocumentoNoAprobado,
    IngestaNoDisponible,
    RecursoNoEncontrado,
    ReglaNegocioViolada,
    TransicionEstadoInvalida,
)
from app.nucleo.registro import obtener_logger
from app.nucleo.reloj import Reloj

logger = obtener_logger(__name__)

# Transiciones permitidas. Un diccionario explicito y no una serie de `if`:
# asi la maquina de estados se lee entera de un vistazo, y anadir un estado
# obliga a decidir desde donde se llega a el.
TRANSICIONES: dict[str, frozenset[str]] = {
    EstadoDocumento.DRAFT.value: frozenset(
        {EstadoDocumento.PENDING_REVIEW.value, EstadoDocumento.ARCHIVED.value}
    ),
    EstadoDocumento.PENDING_REVIEW.value: frozenset(
        {
            EstadoDocumento.APPROVED.value,
            # Vuelve a borrador si el revisor pide cambios.
            EstadoDocumento.DRAFT.value,
            EstadoDocumento.ARCHIVED.value,
        }
    ),
    EstadoDocumento.APPROVED.value: frozenset(
        {
            EstadoDocumento.PUBLISHED.value,
            # Retirar de circulacion para corregir. Es el camino que hace
            # falta cuando alguien detecta un error en un protocolo ya
            # aprobado -- «dice 8 horas de ayuno y son 12».
            #
            # Sin el, la unica salida seria archivar y crear un documento
            # nuevo, lo que pierde la identidad y el historial de versiones
            # por corregir una cifra. Y mientras tanto el agente seguiria
            # citando el dato equivocado.
            #
            # Volver a borrador retira los fragmentos de la recuperacion en el
            # acto, porque heredan el estado.
            EstadoDocumento.DRAFT.value,
            EstadoDocumento.ARCHIVED.value,
        }
    ),
    EstadoDocumento.PUBLISHED.value: frozenset(
        {EstadoDocumento.DRAFT.value, EstadoDocumento.ARCHIVED.value}
    ),
    # Terminal. Un documento archivado no vuelve: se crea uno nuevo. Permitir
    # el regreso haria que la fecha de archivado dejara de significar nada.
    EstadoDocumento.ARCHIVED.value: frozenset(),
}

# Tamano de lote al vectorizar. Los modelos reales son mucho mas eficientes
# por lotes, y uno demasiado grande agota la memoria con documentos largos.
LOTE_EMBEDDINGS = 32


@dataclass(frozen=True, slots=True)
class ResultadoIngesta:
    document_id: uuid.UUID
    version: int
    fragmentos: int
    embeddings: int
    riesgo_inyeccion: RiesgoInyeccion
    # Cierto si el analisis encontro algo que exige revision humana antes de
    # aprobar. No impide ingerir: impide aprobar.
    requiere_revision: bool


class ServicioConocimiento:
    """Carga, versionado, aprobacion y archivado de documentos."""

    def __init__(
        self,
        sesion: AsyncSession,
        reloj: Reloj,
        embeddings: ProveedorEmbeddings,
        *,
        tamano_fragmento: int = 900,
        solape_fragmento: int = 150,
    ) -> None:
        self._sesion = sesion
        self._reloj = reloj
        self._embeddings = embeddings
        self._tamano = tamano_fragmento
        self._solape = solape_fragmento

    # ------------------------------------------------------------------
    #  Documento
    # ------------------------------------------------------------------
    async def crear_documento(
        self,
        *,
        principal: Principal,
        titulo: str,
        tipo: str,
        sensibilidad: str = "N1",
        branch_id: uuid.UUID | None = None,
        specialty_id: uuid.UUID | None = None,
        service_id: uuid.UUID | None = None,
        responsable_id: uuid.UUID | None = None,
        etiquetas: list[str] | None = None,
        effective_from: datetime | None = None,
        effective_until: datetime | None = None,
    ) -> KnowledgeDocument:
        """Crea el documento en `DRAFT`.

        Nace siempre en borrador, sin excepcion: no hay forma de crear un
        documento ya aprobado. Aprobar exige un paso propio con constancia de
        quien lo hizo.
        """
        if principal.clinica_id is None:
            raise ReglaNegocioViolada("El principal no tiene clinica asociada.")

        documento = KnowledgeDocument(
            clinic_id=principal.clinica_id,
            titulo=titulo.strip(),
            tipo=tipo,
            status=EstadoDocumento.DRAFT.value,
            version_vigente=0,
            responsable_id=responsable_id or principal.actor_id,
            sensitivity_level=sensibilidad,
            etiquetas=etiquetas,
            branch_id=branch_id,
            specialty_id=specialty_id,
            service_id=service_id,
            effective_from=effective_from,
            effective_until=effective_until,
        )
        self._sesion.add(documento)
        await self._sesion.flush()
        logger.info(
            "conocimiento.documento_creado",
            document_id=str(documento.id),
            tipo=tipo,
        )
        return documento

    async def cambiar_estado(
        self,
        *,
        principal: Principal,
        document_id: uuid.UUID,
        nuevo_estado: EstadoDocumento,
        motivo: str | None = None,
    ) -> KnowledgeDocument:
        """Aplica una transicion de estado y propaga a los fragmentos.

        La propagacion va en la **misma transaccion**. Si fuera despues,
        habria una ventana en la que un documento archivado seguiria siendo
        recuperable por el agente.
        """
        documento = await self._obtener(principal, document_id)
        permitidas = TRANSICIONES.get(documento.status, frozenset())
        if nuevo_estado.value not in permitidas:
            raise TransicionEstadoInvalida(
                f"Un documento en {documento.status} no puede pasar a "
                f"{nuevo_estado.value}. Transiciones validas: {sorted(permitidas) or 'ninguna'}."
            )

        ahora = self._reloj.ahora()

        if nuevo_estado in (EstadoDocumento.APPROVED, EstadoDocumento.PUBLISHED):
            await self._exigir_aprobable(documento)
            documento.aprobado_por = principal.actor_id
            documento.aprobado_en = ahora
        if nuevo_estado is EstadoDocumento.ARCHIVED:
            documento.archivado_en = ahora
        if nuevo_estado is EstadoDocumento.DRAFT:
            # Vuelve a borrador: se retira la constancia de aprobacion, porque
            # ya no describe el estado actual y dejarla haria creer que sigue
            # aprobado.
            documento.aprobado_por = None
            documento.aprobado_en = None

        anterior = documento.status
        documento.status = nuevo_estado.value
        await self._propagar_a_fragmentos(documento)
        await self._sesion.flush()

        logger.info(
            "conocimiento.estado_cambiado",
            document_id=str(document_id),
            de=anterior,
            a=nuevo_estado.value,
            motivo=motivo,
        )
        return documento

    async def _exigir_aprobable(self, documento: KnowledgeDocument) -> None:
        """Comprueba que el documento pueda aprobarse.

        Dos condiciones, y las dos existen por un caso concreto:

        * **Tiene una version ingerida.** Aprobar un documento sin fragmentos
          lo deja aprobado y vacio: el agente lo cuenta como fuente y no
          devuelve nada.
        * **Su analisis de inyeccion no es de riesgo alto.** Si lo es, alguien
          tiene que revisarlo y marcarlo de forma explicita.
        """
        if documento.version_vigente <= 0:
            raise DocumentoNoAprobado(
                "El documento no tiene ninguna version ingerida. Cargue el contenido "
                "antes de aprobarlo."
            )

        version = (
            await self._sesion.execute(
                select(KnowledgeVersion).where(
                    KnowledgeVersion.document_id == documento.id,
                    KnowledgeVersion.version == documento.version_vigente,
                )
            )
        ).scalar_one_or_none()
        if version is None:
            raise DocumentoNoAprobado("No se encuentra la version vigente del documento.")

        analisis = version.resultado_analisis_inyeccion or {}
        if analisis.get("riesgo") == RiesgoInyeccion.ALTO.value and not analisis.get(
            "revisado_por"
        ):
            raise DocumentoNoAprobado(
                "El analisis detecto contenido que podria alterar el comportamiento del "
                "agente. Una persona debe revisarlo y marcarlo como revisado antes de "
                "aprobar el documento."
            )

    async def marcar_revisado(
        self, *, principal: Principal, document_id: uuid.UUID, version: int, nota: str
    ) -> KnowledgeVersion:
        """Registra que una persona reviso el contenido marcado como riesgoso.

        Es el desbloqueo explicito de `_exigir_aprobable`. Se guarda quien y
        cuando dentro del propio analisis, junto a los hallazgos: ante la
        pregunta «quien dijo que este texto era aceptable» hay respuesta.
        """
        fila = (
            await self._sesion.execute(
                select(KnowledgeVersion)
                .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeVersion.document_id)
                .where(
                    KnowledgeVersion.document_id == document_id,
                    KnowledgeVersion.version == version,
                    KnowledgeDocument.clinic_id == principal.clinica_id,
                )
            )
        ).scalar_one_or_none()
        if fila is None:
            raise RecursoNoEncontrado("La version del documento no existe.")

        analisis = dict(fila.resultado_analisis_inyeccion or {})
        analisis["revisado_por"] = str(principal.actor_id)
        analisis["revisado_en"] = self._reloj.ahora().isoformat()
        analisis["nota_revision"] = nota
        fila.resultado_analisis_inyeccion = analisis
        await self._sesion.flush()

        logger.warning(
            "conocimiento.riesgo_revisado_manualmente",
            document_id=str(document_id),
            version=version,
        )
        return fila

    # ------------------------------------------------------------------
    #  Ingesta
    # ------------------------------------------------------------------
    async def ingerir_texto(
        self,
        *,
        principal: Principal,
        document_id: uuid.UUID,
        contenido: str,
        nombre_archivo: str | None = None,
        notas_cambio: str | None = None,
    ) -> ResultadoIngesta:
        """Prepara y procesa una version dentro de la sesion actual.

        Los endpoints separan ambas fases y confirman la preparacion antes de
        invocar embeddings. Este metodo conserva una entrada simple para
        semillas y pruebas de integracion.
        """
        trabajo = await self.preparar_ingesta(
            principal=principal,
            document_id=document_id,
            contenido=contenido,
            nombre_archivo=nombre_archivo,
            notas_cambio=notas_cambio,
        )
        return await self.procesar_ingesta(
            principal=principal, document_id=document_id, version=trabajo.version
        )

    async def preparar_ingesta(
        self,
        *,
        principal: Principal,
        document_id: uuid.UUID,
        contenido: str,
        nombre_archivo: str | None = None,
        notas_cambio: str | None = None,
    ) -> KnowledgeIngestionJob:
        """Guarda fuente, version y trabajo antes de generar embeddings.

        El endpoint confirma esta fase por separado. Si el proceso se reinicia
        durante el indexado, el trabajo pendiente y su texto quedan disponibles
        para repetirlo con la misma carga.
        """
        documento = await self._obtener_bloqueado(principal, document_id)
        if documento.status == EstadoDocumento.ARCHIVED.value:
            raise TransicionEstadoInvalida(
                "Un documento archivado no admite versiones nuevas. Cree uno nuevo."
            )
        if documento.status in {
            EstadoDocumento.APPROVED.value,
            EstadoDocumento.PUBLISHED.value,
        }:
            raise TransicionEstadoInvalida(
                "Retire el documento a borrador antes de cargar una version nueva. "
                "La nueva version debe pasar por revision y aprobacion antes de responder consultas."
            )

        texto = contenido.strip()
        if not texto:
            raise ReglaNegocioViolada("El contenido del documento esta vacio.")

        hash_contenido = hashlib.sha256(texto.encode("utf-8")).hexdigest()
        ultima = await self._sesion.scalar(
            select(KnowledgeVersion)
            .where(KnowledgeVersion.document_id == document_id)
            .order_by(KnowledgeVersion.version.desc())
            .limit(1)
            .with_for_update()
        )
        if ultima is not None and ultima.hash_sha256 == hash_contenido:
            trabajo_existente = await self._sesion.scalar(
                select(KnowledgeIngestionJob)
                .where(
                    KnowledgeIngestionJob.document_id == document_id,
                    KnowledgeIngestionJob.version == ultima.version,
                )
                .with_for_update()
            )
            if trabajo_existente is not None and (
                trabajo_existente.estado == EstadoIngesta.COMPLETADA.value
                or ultima.contenido_texto is not None
            ):
                return trabajo_existente

        numero = (ultima.version if ultima is not None else 0) + 1

        analisis = analizar(texto)
        version = KnowledgeVersion(
            document_id=document_id,
            version=numero,
            nombre_archivo=nombre_archivo,
            hash_sha256=hash_contenido,
            contenido_texto=texto,
            autor_id=principal.actor_id,
            notas_cambio=notas_cambio,
            resultado_analisis_inyeccion=analisis.a_dict(),
        )
        self._sesion.add(version)

        trabajo = KnowledgeIngestionJob(
            document_id=document_id,
            version=numero,
            estado=EstadoIngesta.PENDIENTE.value,
            paso_actual="pendiente",
        )
        self._sesion.add(trabajo)
        await self._sesion.flush()
        return trabajo

    async def procesar_ingesta(
        self, *, principal: Principal, document_id: uuid.UUID, version: int
    ) -> ResultadoIngesta:
        """Procesa o reanuda una version sin duplicar fragmentos.

        El documento y el trabajo quedan bloqueados durante el procesamiento.
        Ante dos reintentos simultaneos, el segundo devuelve el resultado que
        completo el primero.
        """
        documento = await self._obtener_bloqueado(principal, document_id)
        trabajo = await self._sesion.scalar(
            select(KnowledgeIngestionJob)
            .where(
                KnowledgeIngestionJob.document_id == document_id,
                KnowledgeIngestionJob.version == version,
            )
            .with_for_update()
        )
        fila_version = await self._sesion.scalar(
            select(KnowledgeVersion)
            .where(
                KnowledgeVersion.document_id == document_id,
                KnowledgeVersion.version == version,
            )
            .with_for_update()
        )
        if trabajo is None or fila_version is None:
            raise RecursoNoEncontrado("El trabajo de ingesta no existe.")

        analisis_guardado = fila_version.resultado_analisis_inyeccion or {}
        riesgo = RiesgoInyeccion(
            str(analisis_guardado.get("riesgo", RiesgoInyeccion.NINGUNO.value))
        )
        requiere_revision = riesgo is RiesgoInyeccion.ALTO and not analisis_guardado.get(
            "revisado_por"
        )
        if trabajo.estado == EstadoIngesta.COMPLETADA.value:
            return ResultadoIngesta(
                document_id=document_id,
                version=version,
                fragmentos=trabajo.fragmentos_generados,
                embeddings=trabajo.embeddings_generados,
                riesgo_inyeccion=riesgo,
                requiere_revision=requiere_revision,
            )
        if fila_version.contenido_texto is None:
            raise IngestaNoDisponible(
                "No se conserva el texto necesario para reintentar esta version. Vuelva a cargarla."
            )

        texto = fila_version.contenido_texto
        trabajo.estado = EstadoIngesta.EN_PROCESO.value
        trabajo.paso_actual = "fragmentacion_embeddings"
        trabajo.error = None
        trabajo.intentos += 1
        await self._sesion.flush()

        try:
            async with self._sesion.begin_nested():
                fragmentos = await self._indexar(documento, version, texto)
                documento.version_vigente = version
                await self._propagar_a_fragmentos(documento)
                trabajo.estado = EstadoIngesta.COMPLETADA.value
                trabajo.paso_actual = None
                trabajo.fragmentos_generados = fragmentos
                trabajo.embeddings_generados = fragmentos
                trabajo.error = None
                trabajo.finalizado_en = self._reloj.ahora()
                # El texto fuente se retiene solo mientras sirva para reintentar.
                fila_version.contenido_texto = None
                await self._sesion.flush()
        except Exception as exc:
            trabajo.estado = EstadoIngesta.FALLIDA.value
            trabajo.paso_actual = "fragmentacion_embeddings"
            trabajo.error = "No se pudo generar el indice; vuelva a intentar la carga."
            trabajo.finalizado_en = self._reloj.ahora()
            await self._sesion.flush()
            await self._sesion.commit()
            logger.warning(
                "conocimiento.ingesta_fallida",
                document_id=str(document_id),
                version=version,
                tipo_error=type(exc).__name__,
            )
            raise IngestaNoDisponible(
                "No se pudo completar la indexacion. Puede reintentar la carga del documento."
            ) from exc

        if riesgo is RiesgoInyeccion.ALTO:
            # Nivel `warning`: alguien subio un documento con texto que intenta
            # manipular al agente. Puede ser legitimo, pero nadie deberia
            # enterarse por casualidad.
            logger.warning(
                "conocimiento.riesgo_inyeccion_detectado",
                document_id=str(document_id),
                version=version,
            )

        logger.info(
            "conocimiento.version_ingerida",
            document_id=str(document_id),
            version=version,
            fragmentos=fragmentos,
        )
        return ResultadoIngesta(
            document_id=document_id,
            version=version,
            fragmentos=fragmentos,
            embeddings=fragmentos,
            riesgo_inyeccion=riesgo,
            requiere_revision=requiere_revision,
        )

    async def _indexar(self, documento: KnowledgeDocument, version: int, texto: str) -> int:
        """Fragmenta, vectoriza y guarda. Devuelve cuantos fragmentos creo.

        Borra primero los fragmentos de esa misma version. Reingerir la misma
        version ocurre al reintentar un trabajo fallido, y sin el borrado
        chocaria con la restriccion unica -- o peor, duplicaria fragmentos si
        cambiara el numero de ellos.
        """
        await ejecutar_escritura(
            self._sesion,
            delete(KnowledgeChunk).where(
                KnowledgeChunk.document_id == documento.id,
                KnowledgeChunk.version == version,
            ),
        )

        piezas = fragmentar(texto, tamano=self._tamano, solape=self._solape)
        if not piezas:
            return 0

        filas: list[KnowledgeChunk] = []
        for pieza in piezas:
            fila = KnowledgeChunk(
                document_id=documento.id,
                version=version,
                indice_fragmento=pieza.indice,
                contenido=pieza.contenido,
                tokens=pieza.tokens_aproximados,
                # Los metadatos se copian del documento: es la desnormalizacion
                # que sostiene el filtro del RAG (ADR-0013).
                clinic_id=documento.clinic_id,
                branch_id=documento.branch_id,
                specialty_id=documento.specialty_id,
                service_id=documento.service_id,
                status=documento.status,
                effective_from=documento.effective_from,
                effective_until=documento.effective_until,
                sensitivity_level=documento.sensitivity_level,
                vigente=version == documento.version_vigente,
            )
            self._sesion.add(fila)
            filas.append(fila)
        await self._sesion.flush()

        for inicio in range(0, len(filas), LOTE_EMBEDDINGS):
            lote = filas[inicio : inicio + LOTE_EMBEDDINGS]
            vectores = await self._embeddings.vectorizar([f.contenido for f in lote])
            for fila, vector in zip(lote, vectores, strict=True):
                self._sesion.add(
                    KnowledgeEmbedding(
                        chunk_id=fila.id,
                        modelo=self._embeddings.nombre_modelo,
                        dimension=self._embeddings.dimension,
                        embedding=vector,
                    )
                )
        await self._sesion.flush()
        return len(filas)

    # ------------------------------------------------------------------
    #  Mantenimiento
    # ------------------------------------------------------------------
    async def reindexar_embeddings(self, *, limite_lotes: int | None = None) -> int:
        """Genera los vectores que faltan para el modelo configurado.

        Al cambiar de modelo (por ejemplo, de `mock` al real) los fragmentos
        existentes se quedan sin vector de ese modelo y la mitad semántica de
        la búsqueda no los encuentra. El texto no cambia: solo se añaden
        vectores. Es idempotente; lo ya indexado con el modelo no se repite.
        Devuelve cuántos vectores creó.
        """
        modelo = self._embeddings.nombre_modelo
        creados = 0
        lotes = 0
        while limite_lotes is None or lotes < limite_lotes:
            ya_indexados = select(KnowledgeEmbedding.chunk_id).where(
                KnowledgeEmbedding.modelo == modelo
            )
            pendientes = (
                await self._sesion.execute(
                    select(KnowledgeChunk.id, KnowledgeChunk.contenido)
                    .where(KnowledgeChunk.id.not_in(ya_indexados))
                    .order_by(KnowledgeChunk.id)
                    .limit(LOTE_EMBEDDINGS)
                )
            ).all()
            if not pendientes:
                break
            vectores = await self._embeddings.vectorizar([fila.contenido for fila in pendientes])
            for fila, vector in zip(pendientes, vectores, strict=True):
                self._sesion.add(
                    KnowledgeEmbedding(
                        chunk_id=fila.id,
                        modelo=modelo,
                        dimension=self._embeddings.dimension,
                        embedding=vector,
                    )
                )
            await self._sesion.flush()
            creados += len(pendientes)
            lotes += 1
        logger.info("conocimiento.reindexado", modelo=modelo, vectores=creados)
        return creados

    # ------------------------------------------------------------------
    #  Auxiliares
    # ------------------------------------------------------------------
    async def _obtener_bloqueado(
        self, principal: Principal, document_id: uuid.UUID
    ) -> KnowledgeDocument:
        """Resuelve y bloquea un documento dentro de la clinica autorizada."""
        documento = (
            await self._sesion.execute(
                select(KnowledgeDocument)
                .where(
                    KnowledgeDocument.id == document_id,
                    KnowledgeDocument.clinic_id == principal.clinica_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if documento is None:
            raise RecursoNoEncontrado("El documento no existe.")
        return documento

    async def _obtener(self, principal: Principal, document_id: uuid.UUID) -> KnowledgeDocument:
        """Documento de la clinica del principal, o 404.

        El filtro por clinica va en la consulta y no despues: un documento de
        otra clinica es indistinguible de uno inexistente, igual que en el
        resto del sistema.
        """
        documento = (
            await self._sesion.execute(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.id == document_id,
                    KnowledgeDocument.clinic_id == principal.clinica_id,
                )
            )
        ).scalar_one_or_none()
        if documento is None:
            raise RecursoNoEncontrado("El documento no existe.")
        return documento

    async def _propagar_a_fragmentos(self, documento: KnowledgeDocument) -> int:
        """Copia estado, vigencia, sensibilidad y version activa a sus fragmentos.

        Es el precio de la desnormalizacion, y se paga en un solo sitio. Toca
        **todas** las versiones y no solo la vigente: si una version antigua
        conservara `status = 'PUBLISHED'` tras archivar el documento, seguiria
        siendo recuperable.
        """
        return await ejecutar_escritura(
            self._sesion,
            update(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == documento.id)
            .values(
                status=documento.status,
                effective_from=documento.effective_from,
                effective_until=documento.effective_until,
                sensitivity_level=documento.sensitivity_level,
                branch_id=documento.branch_id,
                specialty_id=documento.specialty_id,
                service_id=documento.service_id,
                vigente=KnowledgeChunk.version == documento.version_vigente,
            ),
        )


__all__ = [
    "LOTE_EMBEDDINGS",
    "TRANSICIONES",
    "ResultadoIngesta",
    "ServicioConocimiento",
]
