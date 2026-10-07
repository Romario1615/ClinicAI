"""Consentimientos de comunicación registrados en el mostrador.

Que se guarda como evidencia
----------------------------
La version del texto que el paciente acepto y el **hash SHA-256 de ese texto
exacto**, mas quien lo registro y por que canal. Ante una reclamacion la
pregunta es «que texto acepto», y una version sin hash no prueba que el texto
no cambiara despues.

Textos provisionales
--------------------
Los textos de este catalogo son **borradores operativos**: falta su revision
legal (limitacion E-2). Cambiar un texto exige subir su version; el hash de
lo ya aceptado no cambia.

Alcance
-------
Solo consentimientos de comunicacion (WhatsApp, recordatorios de medicacion,
promociones). El de tratamiento de datos y el de compartir con terceros
necesitan texto legal aprobado y quedan fuera de esta pantalla.

La revocacion no borra la fila: marca `revocado_en` (hay que poder probar que
hubo consentimiento mientras se enviaron mensajes).
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.modulos.pacientes.modelos import Consentimiento, TipoConsentimiento
from app.modulos.pacientes.repositorio import RepositorioPacientes
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import NivelSensibilidad, Principal
from app.nucleo.dependencias import Auditor, RelojActual, Sesion, exige_permiso
from app.nucleo.errores import ConflictoEstado, DatosInvalidos, RecursoNoEncontrado


@dataclass(frozen=True, slots=True)
class TextoConsentimiento:
    version: str
    titulo: str
    texto: str

    @property
    def hash(self) -> str:
        return hashlib.sha256(self.texto.encode("utf-8")).hexdigest()


TEXTOS: dict[TipoConsentimiento, TextoConsentimiento] = {
    TipoConsentimiento.DOCUMENTOS_WHATSAPP: TextoConsentimiento(
        "2026-10-v1",
        "Documentos por WhatsApp",
        "Acepto recibir avisos genéricos por WhatsApp con enlaces temporales para consultar "
        "mis presupuestos, cotizaciones y recetas. Para abrir el PDF debo verificar mi identidad. "
        "Puedo revocar este permiso en la clínica o responder BAJA en cualquier momento.",
    ),
    TipoConsentimiento.COMUNICACION_WHATSAPP: TextoConsentimiento(
        "2026-10-v1",
        "Avisos de citas por WhatsApp",
        "Acepto recibir por WhatsApp confirmaciones, recordatorios y cambios de mis citas. "
        "Los mensajes no incluyen diagnósticos ni medicamentos. Puedo darme de baja "
        "respondiendo BAJA en cualquier momento.",
    ),
    TipoConsentimiento.RECORDATORIOS_MEDICACION: TextoConsentimiento(
        "2026-10-v1",
        "Recordatorios de tomas",
        "Acepto recibir por WhatsApp recordatorios de las tomas que indicó mi profesional. "
        "El mensaje no nombra el medicamento. Puedo darme de baja respondiendo BAJA.",
    ),
    TipoConsentimiento.PROMOCIONES: TextoConsentimiento(
        "2026-10-v1",
        "Ofertas y promociones",
        "Acepto recibir por WhatsApp ofertas y promociones de la clínica. Mis datos de salud "
        "no se usan para elegir qué ofertas recibo. Puedo darme de baja respondiendo "
        "BAJA PROMOCIONES sin perder los avisos de mis citas.",
    ),
}

CANALES = frozenset({"PANEL", "PRESENCIAL"})


# ---------------------------------------------------------------------------
#  Esquemas
# ---------------------------------------------------------------------------
class TextoSalida(BaseModel):
    tipo: TipoConsentimiento
    version: str
    titulo: str
    texto: str


class EstadoConsentimiento(BaseModel):
    tipo: TipoConsentimiento
    titulo: str
    vigente: bool
    version_texto: str | None
    otorgado_en: datetime | None
    revocado_en: datetime | None
    canal: str | None


class Otorgamiento(BaseModel):
    """El personal confirma que el paciente aceptó **esta** versión del texto."""

    model_config = ConfigDict(extra="forbid")

    tipo: TipoConsentimiento
    version_texto: str
    canal: str = "PRESENCIAL"
    confirmo_lectura: bool


# ---------------------------------------------------------------------------
#  Rutas
# ---------------------------------------------------------------------------
enrutador = APIRouter(prefix="/pacientes", tags=["consentimientos"])
PuedeVer = Annotated[Principal, Depends(exige_permiso("paciente.leer_administrativo"))]
PuedeGestionar = Annotated[Principal, Depends(exige_permiso("consentimiento.gestionar"))]


@enrutador.get("/consentimientos/textos", response_model=list[TextoSalida])
async def textos(principal: PuedeVer) -> list[TextoSalida]:
    del principal
    return [
        TextoSalida(tipo=tipo, version=t.version, titulo=t.titulo, texto=t.texto)
        for tipo, t in TEXTOS.items()
    ]


async def _paciente(sesion: Sesion, principal: Principal, paciente_id: uuid.UUID) -> None:
    if await RepositorioPacientes(sesion).obtener(paciente_id, principal) is None:
        raise RecursoNoEncontrado("El paciente solicitado no existe.")


async def _vigentes(sesion: Sesion, paciente_id: uuid.UUID) -> dict[str, Consentimiento]:
    filas = (
        await sesion.execute(
            select(Consentimiento)
            .where(Consentimiento.paciente_id == paciente_id)
            .order_by(Consentimiento.otorgado_en.desc())
        )
    ).scalars()
    # Por tipo: la vigente si existe; si no, la mas reciente. No se decide
    # solo por fecha: dos registros en el mismo instante empatarian.
    ultimos: dict[str, Consentimiento] = {}
    for fila in filas:
        previa = ultimos.get(fila.tipo)
        vigente = fila.otorgado and fila.revocado_en is None
        if previa is None or (vigente and previa.revocado_en is not None):
            ultimos[fila.tipo] = fila
    return ultimos


def _estado(tipo: TipoConsentimiento, fila: Consentimiento | None) -> EstadoConsentimiento:
    vigente = bool(fila and fila.otorgado and fila.revocado_en is None)
    return EstadoConsentimiento(
        tipo=tipo,
        titulo=TEXTOS[tipo].titulo,
        vigente=vigente,
        version_texto=fila.version_texto if fila else None,
        otorgado_en=fila.otorgado_en if fila else None,
        revocado_en=fila.revocado_en if fila else None,
        canal=fila.canal if fila else None,
    )


@enrutador.get("/{paciente_id}/consentimientos", response_model=list[EstadoConsentimiento])
async def listar(
    principal: PuedeVer,
    sesion: Sesion,
    paciente_id: Annotated[uuid.UUID, Path()],
) -> list[EstadoConsentimiento]:
    await _paciente(sesion, principal, paciente_id)
    ultimos = await _vigentes(sesion, paciente_id)
    return [_estado(tipo, ultimos.get(tipo.value)) for tipo in TEXTOS]


@enrutador.post(
    "/{paciente_id}/consentimientos",
    response_model=EstadoConsentimiento,
    status_code=201,
    responses={409: {"description": "Ya hay un consentimiento vigente de ese tipo"}},
)
async def otorgar(
    principal: PuedeGestionar,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    paciente_id: Annotated[uuid.UUID, Path()],
    datos: Otorgamiento,
) -> EstadoConsentimiento:
    texto = TEXTOS.get(datos.tipo)
    if texto is None:
        raise DatosInvalidos("Ese consentimiento no se registra desde el panel.")
    if not datos.confirmo_lectura:
        raise DatosInvalidos("Confirme que el paciente leyó y aceptó el texto.")
    if datos.version_texto != texto.version:
        raise ConflictoEstado("El texto cambió. Muestre al paciente la versión vigente.")
    if datos.canal not in CANALES:
        raise DatosInvalidos("Canal no válido para un registro en el panel.")
    await _paciente(sesion, principal, paciente_id)
    actual = (await _vigentes(sesion, paciente_id)).get(datos.tipo.value)
    if actual is not None and actual.otorgado and actual.revocado_en is None:
        raise ConflictoEstado("El paciente ya tiene ese consentimiento vigente.")

    ahora = reloj.ahora()
    fila = Consentimiento(
        paciente_id=paciente_id,
        tipo=datos.tipo.value,
        otorgado=True,
        version_texto=texto.version,
        texto_hash=texto.hash,
        canal=datos.canal,
        otorgado_en=ahora,
        evidencia={"registrado_por": str(principal.actor_id), "origen": "panel"},
        creado_por=principal.actor_id,
    )
    sesion.add(fila)
    await sesion.flush()
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.CONSENTIMIENTO_OTORGADO,
                principal=principal,
                ahora=ahora,
                entidad_tipo="consentimiento",
                entidad_id=fila.id,
                paciente_id=paciente_id,
                nivel_sensibilidad=NivelSensibilidad.ADMINISTRATIVO,
                tipo_consentimiento=datos.tipo.value,
                version_consentimiento=texto.version,
            )
        ]
    )
    await sesion.commit()
    return _estado(datos.tipo, fila)


@enrutador.post(
    "/{paciente_id}/consentimientos/{tipo}/revocacion",
    response_model=EstadoConsentimiento,
)
async def revocar(
    principal: PuedeGestionar,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    paciente_id: Annotated[uuid.UUID, Path()],
    tipo: Annotated[TipoConsentimiento, Path()],
) -> EstadoConsentimiento:
    if tipo not in TEXTOS:
        raise DatosInvalidos("Ese consentimiento no se gestiona desde el panel.")
    await _paciente(sesion, principal, paciente_id)
    actual = (await _vigentes(sesion, paciente_id)).get(tipo.value)
    if actual is None or actual.revocado_en is not None or not actual.otorgado:
        raise ConflictoEstado("No hay un consentimiento vigente de ese tipo.")
    ahora = reloj.ahora()
    actual.revocado_en = ahora
    await sesion.flush()
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.CONSENTIMIENTO_REVOCADO,
                principal=principal,
                ahora=ahora,
                entidad_tipo="consentimiento",
                entidad_id=actual.id,
                paciente_id=paciente_id,
                nivel_sensibilidad=NivelSensibilidad.ADMINISTRATIVO,
                tipo_consentimiento=tipo.value,
            )
        ]
    )
    await sesion.commit()
    return _estado(tipo, actual)


__all__ = ["TEXTOS", "enrutador"]
