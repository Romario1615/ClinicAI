"""Búsqueda en la base de conocimiento para responder a un paciente.

Solo documentos **publicados** y vigentes (`uso_agente`): publicar es la
decisión de que un documento es apto para responder a un paciente. El nivel se
acota a administrativo (N1): nunca clínico, aunque quien simule tenga más. El
filtro vive en el `WHERE` del recuperador, no aquí.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ia.conversacion import BuscadorConocimiento
from app.ia.embeddings import ProveedorEmbeddings
from app.ia.recuperador import Recuperador, contexto_desde_principal
from app.modulos.conocimiento.modelos import KnowledgeDocument
from app.nucleo.autorizacion import NivelSensibilidad, Principal
from app.nucleo.configuracion import Configuracion
from app.nucleo.reloj import Reloj

MAX_FUENTES = 3
LARGO_FRAGMENTO = 600


def buscador_publicado(
    sesion: AsyncSession,
    embeddings: ProveedorEmbeddings,
    configuracion: Configuracion,
    agente: Principal,
    reloj: Reloj,
) -> BuscadorConocimiento:
    async def buscar(texto: str) -> list[tuple[str, str]]:
        resultado = await Recuperador(
            sesion,
            embeddings,
            top_k=MAX_FUENTES,
            candidatos=configuracion.rag_top_k_candidatos,
            peso_vectorial=configuracion.rag_peso_vectorial,
        ).recuperar(
            consulta=texto,
            contexto=contexto_desde_principal(
                agente,
                ahora=reloj.ahora(),
                nivel_maximo=NivelSensibilidad.ADMINISTRATIVO,
                uso_agente=True,
            ),
        )
        if not resultado.hay_fuente:
            return []
        filas = await sesion.execute(
            select(KnowledgeDocument.id, KnowledgeDocument.titulo).where(
                KnowledgeDocument.id.in_(resultado.documentos)
            )
        )
        titulos = {fila[0]: str(fila[1]) for fila in filas.all()}
        return [
            (
                str(titulos.get(f.document_id, "Información de la clínica")),
                " ".join(f.contenido.split())[:LARGO_FRAGMENTO],
            )
            for f in resultado.fragmentos[:MAX_FUENTES]
        ]

    return buscar


__all__ = ["buscador_publicado"]
