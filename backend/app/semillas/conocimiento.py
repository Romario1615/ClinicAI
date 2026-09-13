"""Documentos de conocimiento sinteticos.

Por que existe este archivo
---------------------------
Sin el, la base de conocimiento queda **vacia** en desarrollo: el RAG no se
puede demostrar, ni ejercitar a mano, ni usar para mirar si una consulta
devuelve lo que deberia. Es la misma carencia que tenian los consentimientos
-- sesenta pacientes con numero de WhatsApp y cero permisos para escribirles --
y se descubre igual: arrancando el sistema y viendo que no hay nada.

Que contiene, y que no
----------------------
Documentacion **administrativa y de preparacion**, que es lo que la
especificacion permite que el agente use (RF-M06). Ni protocolos clinicos de
tratamiento, ni nada que se parezca a una indicacion medica: el agente no da
asesoramiento clinico, y sembrar documentacion que lo invite seria contradecir
la regla desde los datos de prueba.

Los textos estan escritos como los escribiria una clinica. Se marcan con
`[SINTETICO]` en el titulo para que en cualquier volcado se vea de inmediato
que no son documentos reales.

El reparto de estados
---------------------
No todos quedan publicados, a proposito. Un conjunto donde todo es recuperable
no permite comprobar a mano que un borrador **no** aparece en una busqueda, ni
que un documento archivado deja de responder. Se siembran los cinco estados.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.ia.embeddings import ProveedorEmbeddings
from app.ia.saneamiento import analizar
from app.modulos.conocimiento.fragmentacion import fragmentar
from app.modulos.conocimiento.modelos import (
    EstadoDocumento,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeEmbedding,
    KnowledgeVersion,
    TipoDocumentoConocimiento,
)

MARCA_SINTETICO = "[SINTETICO]"


@dataclass(frozen=True, slots=True)
class ResumenConocimiento:
    documentos: int = 0
    fragmentos: int = 0
    publicados: int = 0

    def describir(self) -> str:
        return (
            f"  Documentos:     {self.documentos} "
            f"({self.publicados} recuperables por el agente)\n"
            f"  Fragmentos:     {self.fragmentos}"
        )


@dataclass(frozen=True, slots=True)
class _Semilla:
    titulo: str
    tipo: TipoDocumentoConocimiento
    estado: EstadoDocumento
    contenido: str
    # Dias hasta que caduque, contados desde el instante de carga. Nulo = sin
    # caducidad.
    vence_en_dias: int | None = None


# El corpus. Cinco estados representados, para poder comprobar a mano que solo
# los aprobados y publicados se recuperan.
DOCUMENTOS: tuple[_Semilla, ...] = (
    _Semilla(
        titulo="Preparacion para examenes de laboratorio",
        tipo=TipoDocumentoConocimiento.PREPARACION_EXAMEN,
        estado=EstadoDocumento.PUBLISHED,
        contenido=(
            "Preparacion para examenes de sangre.\n\n"
            "El paciente debe mantener ayuno de doce horas antes de la toma de "
            "muestra. Durante el ayuno puede beber agua sin limite. No se "
            "permite cafe, jugos, caramelos ni chicle, porque alteran los "
            "resultados de glucosa y perfil lipidico.\n\n"
            "Se recomienda evitar el ejercicio intenso las veinticuatro horas "
            "previas. Si toma medicacion habitual, consulte con el personal "
            "antes de suspenderla: no la suspenda por su cuenta.\n\n"
            "Presentese en el laboratorio con la orden medica y su documento "
            "de identidad."
        ),
    ),
    _Semilla(
        titulo="Preparacion para ecografia abdominal",
        tipo=TipoDocumentoConocimiento.PREPARACION_EXAMEN,
        estado=EstadoDocumento.PUBLISHED,
        contenido=(
            "Preparacion para ecografia abdominal.\n\n"
            "Se requiere vejiga llena. Beba un litro de agua una hora antes de "
            "la cita y no orine hasta finalizar el procedimiento.\n\n"
            "Evite bebidas gaseosas y alimentos que produzcan gases el dia "
            "previo. El examen dura aproximadamente veinte minutos y no "
            "requiere reposo posterior."
        ),
    ),
    _Semilla(
        titulo="Horarios de atencion",
        tipo=TipoDocumentoConocimiento.PREGUNTA_FRECUENTE,
        estado=EstadoDocumento.PUBLISHED,
        contenido=(
            "Horarios de atencion de la clinica.\n\n"
            "La consulta externa atiende de lunes a viernes de 08:00 a 17:00 y "
            "los sabados de 08:00 a 12:00. El laboratorio toma muestras de "
            "07:00 a 11:00 de lunes a sabado, sin necesidad de cita previa "
            "para examenes de rutina.\n\n"
            "Los feriados nacionales la clinica permanece cerrada. Las citas "
            "que caigan en feriado se reprograman con aviso previo."
        ),
    ),
    _Semilla(
        titulo="Politica de cancelacion de citas",
        tipo=TipoDocumentoConocimiento.POLITICA,
        estado=EstadoDocumento.PUBLISHED,
        contenido=(
            "Politica de cancelacion y reprogramacion de citas.\n\n"
            "Las cancelaciones se aceptan hasta veinticuatro horas antes del "
            "horario reservado, por telefono o respondiendo al mensaje de "
            "recordatorio.\n\n"
            "Una inasistencia sin aviso previo puede afectar la asignacion de "
            "turnos futuros. Si necesita reprogramar, el personal le ofrecera "
            "el primer horario disponible con el mismo profesional."
        ),
    ),
    _Semilla(
        titulo="Documentos requeridos para la atencion",
        tipo=TipoDocumentoConocimiento.INSTRUCTIVO,
        estado=EstadoDocumento.APPROVED,
        contenido=(
            "Documentos requeridos para la atencion.\n\n"
            "Presente su documento de identidad en cada visita. Si acude con "
            "orden medica, traigala impresa o en su telefono.\n\n"
            "Si tiene cobertura de seguro, presente el carne vigente antes de "
            "la consulta: la validacion posterior puede retrasar la "
            "facturacion. Los menores de edad deben acudir acompanados por un "
            "adulto responsable."
        ),
    ),
    _Semilla(
        titulo="Tarifario de consultas del trimestre",
        tipo=TipoDocumentoConocimiento.TARIFARIO,
        estado=EstadoDocumento.PUBLISHED,
        contenido=(
            "Tarifario de consultas.\n\n"
            "Los valores de consulta y procedimientos se publican al inicio de "
            "cada trimestre y se informan en recepcion. Consulte el valor "
            "vigente antes de agendar si no tiene cobertura de seguro.\n\n"
            "Los pagos se registran en el sistema con su comprobante. No se "
            "solicitan datos de tarjeta por telefono ni por mensaje."
        ),
        # Con caducidad, para poder comprobar a mano que un documento vencido
        # deja de recuperarse sin tocar nada mas.
        vence_en_dias=90,
    ),
    _Semilla(
        titulo="Instructivo de toma de muestras a domicilio",
        tipo=TipoDocumentoConocimiento.INSTRUCTIVO,
        estado=EstadoDocumento.PENDING_REVIEW,
        contenido=(
            "Toma de muestras a domicilio.\n\n"
            "El servicio se coordina con cuarenta y ocho horas de anticipacion "
            "y cubre el area urbana. Se aplica un recargo por desplazamiento "
            "que se informa al agendar.\n\n"
            "Este documento esta pendiente de revision y no debe usarse para "
            "responder consultas todavia."
        ),
    ),
    _Semilla(
        titulo="Borrador de preguntas frecuentes",
        tipo=TipoDocumentoConocimiento.PREGUNTA_FRECUENTE,
        estado=EstadoDocumento.DRAFT,
        contenido=(
            "Preguntas frecuentes en elaboracion.\n\n"
            "Este texto esta a medio escribir y contiene datos sin confirmar. "
            "Existe para comprobar que un borrador no es recuperable por el "
            "agente: si aparece en una busqueda, hay un fallo en el filtro."
        ),
    ),
    _Semilla(
        titulo="Horarios de atencion del ano anterior",
        tipo=TipoDocumentoConocimiento.PREGUNTA_FRECUENTE,
        estado=EstadoDocumento.ARCHIVED,
        contenido=(
            "Horarios de atencion (version anterior, archivada).\n\n"
            "La consulta externa atendia de lunes a viernes de 09:00 a 16:00. "
            "Este horario ya no rige. Existe para comprobar que un documento "
            "archivado no responde consultas: si aparece, el agente estaria "
            "dando un horario equivocado."
        ),
    ),
)


async def cargar_conocimiento(
    sesion: AsyncSession,
    *,
    clinica_id: uuid.UUID,
    embeddings: ProveedorEmbeddings,
    ahora: datetime,
    autor_id: uuid.UUID,
    tamano_fragmento: int = 900,
    solape_fragmento: int = 150,
) -> ResumenConocimiento:
    """Siembra los documentos y los indexa.

    No pasa por `ServicioConocimiento` porque ese servicio exige un principal
    y aplica la maquina de estados paso a paso; aqui se construyen los
    documentos ya en su estado final, que es lo que una semilla necesita.

    La coherencia con las reglas del servicio se mantiene a mano: los
    aprobados llevan constancia de aprobacion y version vigente, como exigen
    los `CHECK` del motor. Si esos `CHECK` cambian, esta carga falla -- que es
    justo lo que debe pasar.

    `autor_id` es **obligatorio** y no admite `None`. La primera version de
    esta carga lo dejaba opcional, y el `CHECK aprobado_con_responsable` la
    rechazo: un documento aprobado sin constancia de quien lo aprobo no
    permite responder «quien autorizo que el agente diga esto» (RF-M04). El
    motor hizo su trabajo; el parametro obligatorio impide repetir el
    descuido.
    """
    documentos = 0
    fragmentos_totales = 0
    publicados = 0

    for semilla in DOCUMENTOS:
        aprobado = semilla.estado in (
            EstadoDocumento.APPROVED,
            EstadoDocumento.PUBLISHED,
        )
        documento = KnowledgeDocument(
            clinic_id=clinica_id,
            titulo=f"{semilla.titulo} {MARCA_SINTETICO}",
            tipo=semilla.tipo.value,
            status=semilla.estado.value,
            version_vigente=1,
            responsable_id=autor_id,
            aprobado_por=autor_id if aprobado else None,
            aprobado_en=ahora if aprobado else None,
            archivado_en=ahora if semilla.estado is EstadoDocumento.ARCHIVED else None,
            sensitivity_level="N1",
            effective_from=ahora - timedelta(days=1),
            effective_until=(
                ahora + timedelta(days=semilla.vence_en_dias)
                if semilla.vence_en_dias is not None
                else None
            ),
            etiquetas=["sintetico"],
        )
        sesion.add(documento)
        await sesion.flush()

        analisis = analizar(semilla.contenido)
        sesion.add(
            KnowledgeVersion(
                document_id=documento.id,
                version=1,
                hash_sha256=hashlib.sha256(semilla.contenido.encode("utf-8")).hexdigest(),
                autor_id=autor_id,
                notas_cambio="Carga inicial de datos sinteticos.",
                resultado_analisis_inyeccion=analisis.a_dict(),
            )
        )

        piezas = fragmentar(semilla.contenido, tamano=tamano_fragmento, solape=solape_fragmento)
        filas: list[KnowledgeChunk] = []
        for pieza in piezas:
            fila = KnowledgeChunk(
                document_id=documento.id,
                version=1,
                indice_fragmento=pieza.indice,
                contenido=pieza.contenido,
                tokens=pieza.tokens_aproximados,
                clinic_id=clinica_id,
                status=semilla.estado.value,
                effective_from=documento.effective_from,
                effective_until=documento.effective_until,
                sensitivity_level=documento.sensitivity_level,
            )
            sesion.add(fila)
            filas.append(fila)
        await sesion.flush()

        vectores = await embeddings.vectorizar([f.contenido for f in filas])
        for fila, vector in zip(filas, vectores, strict=True):
            sesion.add(
                KnowledgeEmbedding(
                    chunk_id=fila.id,
                    modelo=embeddings.nombre_modelo,
                    dimension=embeddings.dimension,
                    embedding=vector,
                )
            )
        await sesion.flush()

        documentos += 1
        fragmentos_totales += len(filas)
        if aprobado:
            publicados += 1

    return ResumenConocimiento(
        documentos=documentos, fragmentos=fragmentos_totales, publicados=publicados
    )


__all__ = ["DOCUMENTOS", "MARCA_SINTETICO", "ResumenConocimiento", "cargar_conocimiento"]
