import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from app.ia.proveedores_clinica import decisiones_de_clinica, fabrica_de_clinica
from app.ia.seleccion_llm import FabricaConversacional
from app.modulos.conversaciones import demo_servicios
from app.modulos.conversaciones.demo_esquemas import AbrirDemo, MensajeDemo, RespuestaDemo
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import (
    CifradorActual,
    ConfiguracionActual,
    RelojActual,
    Sesion,
    exige_permiso,
)
from app.nucleo.errores import RecursoNoEncontrado


def solo_local(configuracion: ConfiguracionActual) -> None:
    if configuracion.entorno.value != "local":
        raise RecursoNoEncontrado("La demostracion solo esta disponible en el entorno local.")


enrutador = APIRouter(
    prefix="/agente-demo", tags=["demostracion del agente"], dependencies=[Depends(solo_local)]
)
PuedeSimular = Annotated[Principal, Depends(exige_permiso("conversacion.responder"))]


def _fabrica(peticion: Request) -> FabricaConversacional:
    """La fabrica que construyo el arranque, segun `PROVEEDOR_LLM`."""
    fabrica: FabricaConversacional = peticion.app.state.fabrica_conversacional
    return fabrica


Clave = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)]


@enrutador.post("/sesiones", response_model=RespuestaDemo, status_code=201)
async def abrir(
    datos: AbrirDemo,
    principal: PuedeSimular,
    sesion: Sesion,
    reloj: RelojActual,
    clave: Clave,
) -> RespuestaDemo:
    respuesta = await demo_servicios.abrir(sesion, principal, reloj, datos, clave)
    await sesion.commit()
    return respuesta


@enrutador.post("/sesiones/{identificador}/mensajes", response_model=RespuestaDemo)
async def responder(
    peticion: Request,
    identificador: uuid.UUID,
    datos: MensajeDemo,
    principal: PuedeSimular,
    sesion: Sesion,
    reloj: RelojActual,
    clave: Clave,
    configuracion: ConfiguracionActual,
    cifrador: CifradorActual,
) -> RespuestaDemo:
    # Cada clinica decide con su cuenta de JEV y redacta con su LLM; sin
    # configuracion propia se usa lo del entorno.
    clinica_id = principal.clinica_id
    if clinica_id is None:
        raise RecursoNoEncontrado("La sesion no tiene una clinica asociada.")
    decisiones = await decisiones_de_clinica(
        sesion, cifrador, configuracion, clinica_id, peticion.app.state.clasificador
    )
    fabrica = await fabrica_de_clinica(
        sesion, cifrador, configuracion, clinica_id, _fabrica(peticion)
    )
    respuesta = await demo_servicios.responder(
        sesion,
        principal,
        reloj,
        identificador,
        datos.texto,
        clave,
        fabrica,
        decisiones.clasificador,
        (decisiones.umbral_clinico, decisiones.umbral_intencion),
        (peticion.app.state.embeddings, configuracion),
    )
    await sesion.commit()
    return respuesta
