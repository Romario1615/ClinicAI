"""Indicadores del panel por rol.

Para qué sirve
--------------
Cada persona abre el panel y ve **lo suyo**: recepción, la cola del día y lo
que hay que llamar; el profesional, sus citas y lo que tiene pendiente de
firmar; administración, además, pagos, usuarios, conocimiento y campañas.

Cómo se decide qué ve cada uno
------------------------------
No hay un «panel de recepción» ni un «panel de profesional»: hay bloques, y
cada bloque se calcula **solo** si el principal tiene el permiso de lectura
de ese módulo. Un rol creado por la clínica con una mezcla de permisos ve
exactamente la mezcla que le corresponde. El ámbito (sedes, profesionales,
pacientes) se aplica con las mismas consultas autorizadas que usan los
listados del módulo, no con un filtro propio.

Solo se devuelven **conteos e importes agregados**: ningún nombre, documento
ni dato clínico. Por eso esta lectura no se audita como acceso a fichas.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import Select, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita
from app.modulos.agenda.repositorio import RepositorioAgenda
from app.modulos.conocimiento.modelos import KnowledgeDocument
from app.modulos.conversaciones.modelos import Conversacion
from app.modulos.historia.modelos import AlertaAdherencia, Receta
from app.modulos.lista_espera.modelos import EntradaListaEspera
from app.modulos.lista_espera.repositorio import RepositorioListaEspera
from app.modulos.odontologia.modelos import PlanTratamiento
from app.modulos.pacientes.modelos import Paciente
from app.modulos.pagos.modelos import Pago
from app.modulos.promociones.modelos import CampanaPromocion
from app.modulos.usuarios.modelos import Rol, Usuario
from app.nucleo.autorizacion import NivelSensibilidad, Principal
from app.nucleo.dependencias import PrincipalActual, Sesion
from app.nucleo.errores import DatosInvalidos, PermisoDenegado

enrutador = APIRouter(prefix="/dashboard", tags=["dashboard"])


class IndicadoresAgenda(BaseModel):
    citas_hoy: int
    por_confirmar_hoy: int
    en_sala: int
    en_atencion: int
    atendidas_hoy: int
    inasistencias_hoy: int
    citas_proximos_7_dias: int


class IndicadoresMisCitas(BaseModel):
    citas_hoy: int
    pendientes_hoy: int
    proxima_inicio: AwareDatetime | None


class IndicadoresPacientes(BaseModel):
    total: int
    nuevos_30_dias: int
    sin_verificar: int
    sin_whatsapp: int


class IndicadoresListaEspera(BaseModel):
    en_espera: int
    con_oferta: int


class IndicadoresPagos(BaseModel):
    pendientes: int
    por_validar: int
    confirmado_30_dias: Decimal


class IndicadoresClinico(BaseModel):
    recetas_por_confirmar: int
    planes_propuestos: int
    planes_en_curso: int


class IndicadoresAdherencia(BaseModel):
    alertas_abiertas: int


class IndicadoresMensajes(BaseModel):
    derivadas_a_persona: int
    abiertas: int


class IndicadoresConocimiento(BaseModel):
    borradores: int
    en_revision: int
    vigentes: int


class IndicadoresPromociones(BaseModel):
    borradores: int
    aprobadas_sin_enviar: int
    enviadas_30_dias: int


class IndicadoresUsuarios(BaseModel):
    activos: int
    inactivos: int
    roles: int


class Indicadores(BaseModel):
    """Bloques del panel. `None` = el rol no alcanza ese módulo."""

    agenda: IndicadoresAgenda | None = None
    mis_citas: IndicadoresMisCitas | None = None
    pacientes: IndicadoresPacientes | None = None
    lista_espera: IndicadoresListaEspera | None = None
    pagos: IndicadoresPagos | None = None
    clinico: IndicadoresClinico | None = None
    adherencia: IndicadoresAdherencia | None = None
    mensajes: IndicadoresMensajes | None = None
    conocimiento: IndicadoresConocimiento | None = None
    promociones: IndicadoresPromociones | None = None
    usuarios: IndicadoresUsuarios | None = None


async def _contar(sesion: AsyncSession, consulta: Select) -> int:  # type: ignore[type-arg]
    sub = consulta.subquery()
    return int((await sesion.execute(select(func.count()).select_from(sub))).scalar_one())


async def _agenda(
    sesion: AsyncSession,
    principal: Principal,
    desde: AwareDatetime,
    hasta: AwareDatetime,
    resultado: Indicadores,
) -> None:
    if not principal.tiene_permiso("agenda.leer"):
        return
    base = RepositorioAgenda(sesion).consulta_autorizada(principal)
    hoy = base.where(Cita.inicio >= desde, Cita.inicio < hasta)
    vivas = hoy.where(Cita.estado.notin_(["CANCELLED"]))
    resultado.agenda = IndicadoresAgenda(
        citas_hoy=await _contar(sesion, vivas),
        por_confirmar_hoy=await _contar(sesion, hoy.where(Cita.estado.in_(["PENDING", "HELD"]))),
        en_sala=await _contar(
            sesion,
            vivas.where(Cita.llegada_en.is_not(None), Cita.atencion_iniciada_en.is_(None)),
        ),
        en_atencion=await _contar(
            sesion,
            vivas.where(Cita.atencion_iniciada_en.is_not(None), Cita.completada_en.is_(None)),
        ),
        atendidas_hoy=await _contar(sesion, hoy.where(Cita.estado == "COMPLETED")),
        inasistencias_hoy=await _contar(sesion, hoy.where(Cita.estado == "NO_SHOW")),
        citas_proximos_7_dias=await _contar(
            sesion,
            base.where(
                Cita.inicio >= hasta,
                Cita.inicio < hasta + timedelta(days=7),
                Cita.estado.notin_(["CANCELLED"]),
            ),
        ),
    )
    if principal.profesional_id is not None:
        mias = base.where(Cita.profesional_id == principal.profesional_id)
        mias_hoy = mias.where(
            Cita.inicio >= desde, Cita.inicio < hasta, Cita.estado.notin_(["CANCELLED"])
        )
        proxima = (
            await sesion.execute(
                select(func.min(Cita.inicio)).where(
                    Cita.id.in_(select(mias.subquery().c.id)),
                    Cita.inicio >= func.now(),
                    Cita.estado.in_(["PENDING", "HELD", "CONFIRMED", "RESCHEDULED"]),
                )
            )
        ).scalar_one()
        resultado.mis_citas = IndicadoresMisCitas(
            citas_hoy=await _contar(sesion, mias_hoy),
            pendientes_hoy=await _contar(
                sesion, mias_hoy.where(Cita.completada_en.is_(None), Cita.estado != "NO_SHOW")
            ),
            proxima_inicio=proxima,
        )


async def _clinico(sesion: AsyncSession, principal: Principal, resultado: Indicadores) -> None:
    clinica = principal.clinica_id
    # Lo clinico propio: lo que el profesional tiene que firmar o seguir.
    if principal.profesional_id is not None and clinica is not None:
        clinico = IndicadoresClinico(
            recetas_por_confirmar=0, planes_propuestos=0, planes_en_curso=0
        )
        if principal.tiene_permiso("receta.confirmar"):
            clinico.recetas_por_confirmar = await _contar(
                sesion,
                select(Receta.id).where(
                    Receta.clinica_id == clinica,
                    Receta.profesional_id == principal.profesional_id,
                    Receta.estado == "BORRADOR",
                ),
            )
        if principal.tiene_permiso("plan_tratamiento.leer"):
            planes = select(PlanTratamiento.id).where(
                PlanTratamiento.clinica_id == clinica,
                PlanTratamiento.profesional_id == principal.profesional_id,
            )
            clinico.planes_propuestos = await _contar(
                sesion, planes.where(PlanTratamiento.estado == "PROPUESTO")
            )
            clinico.planes_en_curso = await _contar(
                sesion, planes.where(PlanTratamiento.estado == "ACEPTADO")
            )
        if principal.tiene_permiso("receta.confirmar") or principal.tiene_permiso(
            "plan_tratamiento.leer"
        ):
            resultado.clinico = clinico


async def calcular(
    sesion: AsyncSession, principal: Principal, desde: AwareDatetime, hasta: AwareDatetime
) -> Indicadores:
    clinica = principal.clinica_id
    resultado = Indicadores()
    hace_30 = hasta - timedelta(days=31)

    await _agenda(sesion, principal, desde, hasta, resultado)

    if principal.tiene_permiso("paciente.leer_administrativo") and clinica is not None:
        pacientes = select(Paciente.id).where(
            Paciente.clinica_id == clinica,
            Paciente.anulado_en.is_(None),
            Paciente.activo.is_(True),
        )
        if not principal.ambito.todos_los_pacientes:
            pacientes = pacientes.where(Paciente.id.in_(principal.ambito.pacientes))
        resultado.pacientes = IndicadoresPacientes(
            total=await _contar(sesion, pacientes),
            nuevos_30_dias=await _contar(sesion, pacientes.where(Paciente.creado_en >= hace_30)),
            sin_verificar=await _contar(
                sesion, pacientes.where(Paciente.nivel_verificacion == "NO_VERIFICADO")
            ),
            sin_whatsapp=await _contar(
                sesion, pacientes.where(Paciente.telefono_whatsapp.is_(None))
            ),
        )

    if principal.tiene_permiso("lista_espera.gestionar"):
        espera = RepositorioListaEspera(sesion).consulta(principal)

        resultado.lista_espera = IndicadoresListaEspera(
            en_espera=await _contar(sesion, espera.where(EntradaListaEspera.estado == "ACTIVA")),
            con_oferta=await _contar(sesion, espera.where(EntradaListaEspera.estado == "OFERTADA")),
        )

    if principal.tiene_permiso("pago.leer") and clinica is not None:
        pagos = select(Pago.id).where(Pago.clinica_id == clinica)
        confirmado = (
            await sesion.execute(
                select(func.coalesce(func.sum(Pago.importe), 0)).where(
                    Pago.clinica_id == clinica,
                    Pago.estado == "CONFIRMED",
                    func.coalesce(Pago.actualizado_en, Pago.creado_en) >= hace_30,
                )
            )
        ).scalar_one()
        resultado.pagos = IndicadoresPagos(
            pendientes=await _contar(sesion, pagos.where(Pago.estado == "PENDING")),
            por_validar=await _contar(
                sesion, pagos.where(Pago.estado.in_(["PROOF_RECEIVED", "UNDER_REVIEW"]))
            ),
            confirmado_30_dias=Decimal(confirmado),
        )

    await _clinico(sesion, principal, resultado)

    if principal.tiene_permiso("adherencia.leer") and clinica is not None:
        resultado.adherencia = IndicadoresAdherencia(
            alertas_abiertas=await _contar(
                sesion,
                select(AlertaAdherencia.id).where(
                    AlertaAdherencia.clinica_id == clinica, AlertaAdherencia.atendida_en.is_(None)
                ),
            )
        )

    if principal.tiene_permiso("conversacion.leer") and clinica is not None:
        # Mismo criterio que la bandeja de atención: solo WhatsApp (el simulador
        # no cuenta) y solo lo que el ámbito permite ver. Si no, la tarjeta
        # anuncia conversaciones que la bandeja no muestra.
        conversaciones = select(Conversacion.id).where(
            Conversacion.clinica_id == clinica, Conversacion.canal == "WHATSAPP"
        )
        ambito = principal.ambito
        if not ambito.cubre_nivel(NivelSensibilidad.CLINICO):
            conversaciones = conversaciones.where(false())
        elif not ambito.todos_los_pacientes:
            conversaciones = conversaciones.where(
                Conversacion.paciente_id.in_(ambito.pacientes) if ambito.pacientes else false()
            )
        resultado.mensajes = IndicadoresMensajes(
            derivadas_a_persona=await _contar(
                sesion, conversaciones.where(Conversacion.estado == "EN_HANDOFF")
            ),
            abiertas=await _contar(sesion, conversaciones.where(Conversacion.estado == "ABIERTA")),
        )

    if principal.tiene_permiso("conocimiento.leer") and clinica is not None:
        documentos = select(KnowledgeDocument.id).where(KnowledgeDocument.clinic_id == clinica)
        resultado.conocimiento = IndicadoresConocimiento(
            borradores=await _contar(sesion, documentos.where(KnowledgeDocument.status == "DRAFT")),
            en_revision=await _contar(
                sesion, documentos.where(KnowledgeDocument.status == "PENDING_REVIEW")
            ),
            vigentes=await _contar(
                sesion,
                documentos.where(
                    or_(
                        KnowledgeDocument.status == "APPROVED",
                        KnowledgeDocument.status == "PUBLISHED",
                    )
                ),
            ),
        )

    if principal.tiene_permiso("promocion.gestionar") and clinica is not None:
        campanas = select(CampanaPromocion.id).where(CampanaPromocion.clinica_id == clinica)
        resultado.promociones = IndicadoresPromociones(
            borradores=await _contar(sesion, campanas.where(CampanaPromocion.estado == "BORRADOR")),
            aprobadas_sin_enviar=await _contar(
                sesion, campanas.where(CampanaPromocion.estado == "APROBADA")
            ),
            enviadas_30_dias=await _contar(
                sesion,
                campanas.where(
                    CampanaPromocion.estado == "ENVIADA", CampanaPromocion.enviada_en >= hace_30
                ),
            ),
        )

    if principal.tiene_permiso("usuario.leer") and clinica is not None:
        usuarios = select(Usuario.id).where(Usuario.clinica_id == clinica)
        resultado.usuarios = IndicadoresUsuarios(
            activos=await _contar(sesion, usuarios.where(Usuario.activo.is_(True))),
            inactivos=await _contar(sesion, usuarios.where(Usuario.activo.is_(False))),
            roles=await _contar(
                sesion,
                select(Rol.id).where(
                    Rol.codigo != "superadministrador",
                    or_(Rol.clinica_id == clinica, Rol.clinica_id.is_(None)),
                ),
            ),
        )

    return resultado


@enrutador.get("/indicadores", response_model=Indicadores)
async def indicadores(
    principal: PrincipalActual,
    sesion: Sesion,
    desde: AwareDatetime,
    hasta: AwareDatetime,
) -> Indicadores:
    """Conteos del día y del módulo según los permisos del rol que pregunta."""
    if principal.es_agente:
        raise PermisoDenegado("El agente no consulta indicadores del panel.")
    if not timedelta(0) < hasta - desde <= timedelta(days=2):
        raise DatosInvalidos("El día consultado debe durar entre 1 minuto y 48 horas.")
    return await calcular(sesion, principal, desde, hasta)


__all__ = ["Indicadores", "calcular", "enrutador"]
