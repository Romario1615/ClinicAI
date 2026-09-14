import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita
from app.modulos.auditoria.repositorio import RepositorioAuditoria
from app.modulos.lista_espera.esquemas import (
    AccionEspera,
    DatosEspera,
    PaginaEspera,
    RespuestaEspera,
)
from app.modulos.lista_espera.modelos import EntradaListaEspera, OfertaTurno
from app.modulos.lista_espera.repositorio import RepositorioListaEspera
from app.modulos.lista_espera.servicios import ServicioListaEspera
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import Principal, principal_sistema
from app.nucleo.errores import ConflictoEstado
from app.nucleo.operaciones import completar_operacion, iniciar_operacion
from app.nucleo.reloj import Reloj


async def listar_espera(
    sesion: AsyncSession, principal: Principal, limite: int, desplazamiento: int
) -> PaginaEspera:
    consulta = RepositorioListaEspera(sesion).consulta(principal)
    total = int(
        (await sesion.execute(select(func.count()).select_from(consulta.subquery()))).scalar_one()
    )
    filas = (
        (
            await sesion.execute(
                consulta.order_by(EntradaListaEspera.creado_en.desc(), EntradaListaEspera.id)
                .limit(limite)
                .offset(desplazamiento)
            )
        )
        .scalars()
        .all()
    )
    ofertas = (
        await sesion.execute(
            select(OfertaTurno, Cita.inicio)
            .join(Cita, Cita.id == OfertaTurno.cita_liberada_id)
            .where(
                OfertaTurno.lista_espera_id.in_([e.id for e in filas]),
                OfertaTurno.estado == "OFRECIDA",
            )
        )
    ).all()
    por_entrada = {o.lista_espera_id: (o, inicio) for o, inicio in ofertas}
    resultados = []
    for entrada in filas:
        respuesta = RespuestaEspera.model_validate(entrada)
        if entrada.id in por_entrada:
            oferta, inicio = por_entrada[entrada.id]
            respuesta.oferta_id = oferta.id
            respuesta.oferta_inicio = inicio
            respuesta.oferta_expira_en = oferta.expira_en
        resultados.append(respuesta)
    return PaginaEspera(elementos=resultados, total=total)


async def anotar(
    sesion: AsyncSession, principal: Principal, reloj: Reloj, datos: DatosEspera, clave: str
) -> RespuestaEspera:
    registro = await iniciar_operacion(
        sesion, principal, reloj, "lista_espera.alta", clave, datos.model_dump(mode="json")
    )
    if registro.respuesta:
        entrada = await RepositorioListaEspera(sesion).obtener(
            uuid.UUID(str(registro.respuesta["id"])), principal
        )
    else:
        entrada = await ServicioListaEspera(sesion, reloj).anotar(
            principal=principal, **datos.model_dump()
        )
        await RepositorioAuditoria(sesion).registrar(
            [
                construir_entrada(
                    accion=AccionAuditada.LISTA_ESPERA_ALTA,
                    principal=principal,
                    ahora=reloj.ahora(),
                    entidad_tipo="lista_espera",
                    entidad_id=entrada.id,
                    paciente_id=entrada.paciente_id,
                )
            ]
        )
        completar_operacion(registro, {"id": str(entrada.id)}, reloj)
    return RespuestaEspera.model_validate(entrada)


async def resolver(
    sesion: AsyncSession,
    principal: Principal,
    reloj: Reloj,
    entrada_id: uuid.UUID,
    datos: AccionEspera,
    clave: str,
) -> RespuestaEspera:
    entrada = await RepositorioListaEspera(sesion).obtener(entrada_id, principal)
    registro = await iniciar_operacion(
        sesion,
        principal,
        reloj,
        "lista_espera.resolver",
        clave,
        {"id": entrada_id, **datos.model_dump()},
    )
    if registro.respuesta:
        return RespuestaEspera.model_validate(entrada)
    servicio = ServicioListaEspera(sesion, reloj)
    oferta = await sesion.scalar(
        select(OfertaTurno).where(
            OfertaTurno.lista_espera_id == entrada.id, OfertaTurno.estado == "OFRECIDA"
        )
    )
    if datos.accion == "cancelar":
        await servicio.cancelar(entrada_id, principal=principal)
        await RepositorioAuditoria(sesion).registrar(
            [
                construir_entrada(
                    accion=AccionAuditada.OFERTA_RECHAZADA,
                    principal=principal,
                    ahora=reloj.ahora(),
                    entidad_tipo="lista_espera",
                    entidad_id=entrada_id,
                )
            ]
        )
    else:
        if oferta is None:
            raise ConflictoEstado("La entrada no tiene una oferta activa.")
        operacion = (
            servicio.aceptar_oferta if datos.accion == "aceptar" else servicio.rechazar_oferta
        )
        resultado = await operacion(oferta.id, principal=principal)
        await RepositorioAuditoria(sesion).registrar(resultado.auditoria)
    if oferta is not None and datos.accion in {"cancelar", "rechazar"}:
        liberada = await sesion.get(Cita, oferta.cita_liberada_id)
        if liberada is not None:
            siguiente = await servicio.ofrecer_turno(
                liberada, principal=principal_sistema(liberada.clinica_id)
            )
            await RepositorioAuditoria(sesion).registrar(siguiente.auditoria)
    completar_operacion(registro, {"id": str(entrada.id)}, reloj)
    return RespuestaEspera.model_validate(entrada)
