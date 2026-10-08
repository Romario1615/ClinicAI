from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from sqlalchemy import select

from app.ia.proveedores_clinica import descifrar, leer_integracion
from app.mensajeria.adaptadores import RegistroCanales
from app.mensajeria.servicios import ServicioOutbox, SolicitudEnvio
from app.modulos.agenda.modelos import Cita
from app.modulos.agenda.repositorio import RepositorioAgenda
from app.modulos.documentos.esquemas import (
    ZONAS,
    Compartir,
    ContextoAtencion,
    EntregaSalida,
    Motivo,
    Partida,
    PresupuestoDesdePlan,
    RegistroNuevo,
    RegistroSalida,
)
from app.modulos.documentos.modelos import EntregaDocumento, RegistroPaciente
from app.modulos.documentos.servicios import ServicioRegistros, pdf_registro
from app.modulos.historia.especialidades import especialidades_permitidas, exige_modulo
from app.modulos.historia.modelos import Receta
from app.modulos.odontologia.modelos import PlanTratamiento
from app.modulos.odontologia.planes_servicios import ServicioPlanesTratamiento
from app.modulos.organizacion.modelos import Clinica, Especialidad, Sede, Servicio
from app.modulos.outbox.modelos import CanalOutbox, OutboxMensaje, TipoMensajeOutbox
from app.modulos.pacientes.modelos import Paciente
from app.modulos.pacientes.repositorio import RepositorioPacientes
from app.modulos.postconsulta.modelos import MAXIMO_INTENTOS
from app.modulos.postconsulta.rutas import Verificacion, _principal_paciente
from app.modulos.profesionales.modelos import Profesional
from app.nucleo.auditoria import AccionAuditada, ResultadoAuditoria, construir_entrada
from app.nucleo.autorizacion import NivelSensibilidad, Principal
from app.nucleo.dependencias import (
    Auditor,
    CifradorActual,
    ConfiguracionActual,
    Limitador,
    RelojActual,
    Sesion,
    exige_permiso,
)
from app.nucleo.errores import (
    ConflictoEstado,
    CredencialesInvalidas,
    DatosInvalidos,
    PermisoDenegado,
    RecursoNoEncontrado,
)

enrutador = APIRouter(tags=["documentos y estética"])
Leer = Annotated[Principal, Depends(exige_permiso("historia_clinica.leer"))]
Escribir = Annotated[Principal, Depends(exige_permiso("historia_clinica.escribir"))]
PREFIJO = "/historia/pacientes/{paciente_id}/registros"


@enrutador.get("/pacientes/{paciente_id}/contextos-atencion", response_model=list[ContextoAtencion])
async def contextos(
    paciente_id: uuid.UUID,
    principal: Annotated[Principal, Depends(exige_permiso("agenda.leer"))],
    sesion: Sesion,
) -> list[ContextoAtencion]:
    if await RepositorioPacientes(sesion).obtener(paciente_id, principal) is None:
        raise RecursoNoEncontrado("El paciente no está disponible.")
    consulta = (
        RepositorioAgenda(sesion)
        .consulta_autorizada(principal)
        .add_columns(Sede, Profesional, Servicio, Especialidad, Clinica)
        .join(Clinica, Clinica.id == Cita.clinica_id)
        .join(Sede, Sede.id == Cita.sede_id)
        .join(Profesional, Profesional.id == Cita.profesional_id)
        .join(Servicio, Servicio.id == Cita.servicio_id)
        .join(Especialidad, Especialidad.id == Profesional.especialidad_id)
        .where(Cita.paciente_id == paciente_id)
        .order_by(Cita.inicio.desc(), Cita.id)
        .limit(100)
    )
    # Un profesional solo puede documentar sobre sus propias citas (la misma
    # regla que aplica el alta de registros): ofrecer las de un colega acabaría
    # en un 404 al guardar.
    if principal.profesional_id is not None:
        consulta = consulta.where(Cita.profesional_id == principal.profesional_id)
    filas = await sesion.execute(consulta)
    return [
        ContextoAtencion(
            id=cita.id,
            inicio=cita.inicio,
            estado=cita.estado,
            sede_id=sede.id,
            sede=sede.nombre,
            zona_horaria=sede.zona_horaria or clinica.zona_horaria,
            especialidad_id=especialidad.id,
            especialidad=especialidad.nombre,
            profesional=f"{profesional.nombre} {profesional.apellido}",
            servicio=servicio.nombre,
        )
        for cita, sede, profesional, servicio, especialidad, clinica in filas
    ]


async def auditar(
    auditor: Auditor,
    principal: Principal,
    reloj: RelojActual,
    fila: RegistroPaciente,
    accion: AccionAuditada,
) -> None:
    await auditor.registrar(
        [
            construir_entrada(
                accion=accion,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="registro_paciente",
                entidad_id=fila.id,
                paciente_id=fila.paciente_id,
                nivel_sensibilidad=NivelSensibilidad(fila.nivel_sensibilidad),
                version=fila.version,
            )
        ]
    )


@enrutador.get("/historia/faciograma/zonas", response_model=list[dict[str, str | int]])
async def zonas_faciales(
    principal: Annotated[Principal, Depends(exige_modulo("faciograma", "historia_clinica.leer"))],
) -> list[dict[str, str | int]]:
    del principal
    return [
        {"codigo": codigo, "nombre": nombre, "x": x, "y": y}
        for codigo, (nombre, x, y) in ZONAS.items()
    ]


@enrutador.get(PREFIJO, response_model=list[RegistroSalida])
async def listar(
    paciente_id: uuid.UUID,
    especialidad_id: uuid.UUID,
    principal: Leer,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    historico: bool = False,
    limite: Annotated[int, Query(ge=1, le=100)] = 50,
    desplazamiento: Annotated[int, Query(ge=0)] = 0,
    grupo: Literal["facial", "documentos"] | None = None,
) -> list[RegistroSalida]:
    servicio = ServicioRegistros(sesion, reloj)
    await servicio.acceso(principal, paciente_id)
    permitidas = await especialidades_permitidas(sesion, principal)
    modulos = next((m for e, m, _ in permitidas if e.id == especialidad_id), None)
    if modulos is None:
        raise RecursoNoEncontrado("La especialidad o módulo no está disponible.")
    consulta = servicio.consulta(principal, paciente_id).where(
        RegistroPaciente.especialidad_id == especialidad_id
    )
    if not historico:
        consulta = consulta.where(RegistroPaciente.vigente.is_(True))
    if "faciograma" not in modulos:
        consulta = consulta.where(RegistroPaciente.tipo != "FACIOGRAMA")
    if grupo is not None:
        consulta = consulta.where(
            RegistroPaciente.tipo == "FACIOGRAMA"
            if grupo == "facial"
            else RegistroPaciente.tipo != "FACIOGRAMA"
        )
    filas = list(
        await sesion.scalars(
            consulta.order_by(RegistroPaciente.creado_en.desc(), RegistroPaciente.id)
            .offset(desplazamiento)
            .limit(limite)
        )
    )
    resultados = []
    for fila in filas:
        await auditar(auditor, principal, reloj, fila, AccionAuditada.REGISTRO_PACIENTE_LEIDO)
        resultados.append(RegistroSalida.model_validate(fila))
    if not resultados:
        await auditor.registrar(
            [
                construir_entrada(
                    accion=AccionAuditada.REGISTRO_PACIENTE_LEIDO,
                    principal=principal,
                    ahora=reloj.ahora(),
                    entidad_tipo="registro_paciente",
                    paciente_id=paciente_id,
                    nivel_sensibilidad=NivelSensibilidad.CLINICO,
                    registros_devueltos=0,
                )
            ]
        )
    await sesion.commit()
    return resultados


@enrutador.post(PREFIJO, response_model=RegistroSalida, status_code=201)
async def crear(
    paciente_id: uuid.UUID,
    datos: RegistroNuevo,
    principal: Escribir,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
) -> RegistroSalida:
    fila = await ServicioRegistros(sesion, reloj).crear(principal, paciente_id, datos)
    await auditar(auditor, principal, reloj, fila, AccionAuditada.REGISTRO_PACIENTE_CREADO)
    await sesion.commit()
    return RegistroSalida.model_validate(fila)


@enrutador.post(
    "/historia/planes/{plan_id}/presupuesto-documento",
    response_model=RegistroSalida,
    status_code=201,
)
async def presupuesto_desde_plan(
    plan_id: uuid.UUID,
    datos: PresupuestoDesdePlan,
    principal: Escribir,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
) -> RegistroSalida:
    plan = await sesion.scalar(
        select(PlanTratamiento).where(
            PlanTratamiento.id == plan_id, PlanTratamiento.clinica_id == principal.clinica_id
        )
    )
    if plan is None:
        raise RecursoNoEncontrado("El plan no está disponible.")
    planes = await ServicioPlanesTratamiento(sesion, reloj).listar(
        plan.paciente_id, principal=principal
    )
    seleccion = next(((p, procedimientos) for p, procedimientos in planes if p.id == plan_id), None)
    if seleccion is None or plan.estado not in {"PROPUESTO", "ACEPTADO"}:
        raise RecursoNoEncontrado("El plan no está propuesto o aceptado.")
    autor = await sesion.get(Profesional, plan.profesional_id)
    if autor is None:
        raise RecursoNoEncontrado("El profesional no está disponible.")
    permitidas = await especialidades_permitidas(sesion, principal)
    if not any(
        e.id == autor.especialidad_id and "planes" in modulos for e, modulos, _ in permitidas
    ):
        raise PermisoDenegado("Los planes de tratamiento no están disponibles en esa especialidad.")
    partidas = [
        Partida(descripcion=p.descripcion, cantidad=Decimal(1), precio_unitario=p.precio)
        for p in seleccion[1]
        if p.estado != "CANCELADO"
    ]
    if not partidas:
        raise DatosInvalidos("El plan no tiene procedimientos pendientes de presupuestar.")
    nuevo = RegistroNuevo(
        clave_idempotencia=datos.clave_idempotencia,
        tipo="PRESUPUESTO",
        titulo=plan.titulo,
        especialidad_id=autor.especialidad_id,
        sede_id=datos.sede_id,
        cita_id=datos.cita_id,
        motivo="Presupuesto del plan registrado",
        partidas=partidas,
        moneda=plan.moneda,
        nivel_sensibilidad="N3" if plan.nivel_sensibilidad == "N3" else "N2",
        observaciones=f"Plan de origen: {plan.id}. {plan.observaciones or ''}",
    )
    fila = await ServicioRegistros(sesion, reloj).crear(principal, plan.paciente_id, nuevo)
    await auditar(auditor, principal, reloj, fila, AccionAuditada.REGISTRO_PACIENTE_CREADO)
    await sesion.commit()
    return RegistroSalida.model_validate(fila)


@enrutador.post(PREFIJO + "/{registro_id}/anulacion", response_model=RegistroSalida)
async def anular(
    paciente_id: uuid.UUID,
    registro_id: uuid.UUID,
    datos: Motivo,
    principal: Escribir,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
) -> RegistroSalida:
    servicio = ServicioRegistros(sesion, reloj)
    await sesion.execute(
        select(Paciente.id)
        .where(Paciente.id == paciente_id, Paciente.clinica_id == principal.clinica_id)
        .with_for_update()
    )
    fila = await servicio.obtener(principal, paciente_id, registro_id, True)
    if not fila.vigente or fila.anulado:
        raise ConflictoEstado("El registro ya cambió o fue anulado.")
    fila.vigente = False
    await sesion.flush()
    copia = RegistroPaciente(
        clinica_id=fila.clinica_id,
        paciente_id=fila.paciente_id,
        profesional_id=fila.profesional_id,
        especialidad_id=fila.especialidad_id,
        sede_id=fila.sede_id,
        cita_id=fila.cita_id,
        raiz_id=fila.raiz_id,
        version=fila.version + 1,
        vigente=True,
        tipo=fila.tipo,
        titulo=fila.titulo,
        contenido=dict(fila.contenido),
        nivel_sensibilidad=fila.nivel_sensibilidad,
        anulado=True,
        motivo=datos.motivo,
        creado_por=principal.actor_id,
        creado_en=reloj.ahora(),
    )
    sesion.add(copia)
    await sesion.flush()
    await auditar(auditor, principal, reloj, copia, AccionAuditada.REGISTRO_PACIENTE_ANULADO)
    await sesion.commit()
    return RegistroSalida.model_validate(copia)


def respuesta_pdf(fila: RegistroPaciente) -> Response:
    return Response(
        pdf_registro(fila),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="ClinicAI-{fila.tipo.lower()}-{fila.id.hex[:12]}-v{fila.version}.pdf"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        },
    )


async def exigir_vigente(sesion: Sesion, fila: RegistroPaciente) -> None:
    if not fila.vigente or fila.anulado:
        raise RecursoNoEncontrado("El documento ya no está disponible.")
    if fila.tipo == "RECETA":
        receta = await sesion.scalar(
            select(Receta).where(
                Receta.id == uuid.UUID(str(fila.contenido["receta_id"])),
                Receta.paciente_id == fila.paciente_id,
                Receta.clinica_id == fila.clinica_id,
                Receta.estado == "CONFIRMADA",
            )
        )
        if receta is None:
            raise RecursoNoEncontrado("La receta fue suspendida o sustituida.")


@enrutador.get(
    PREFIJO + "/{registro_id}/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def descargar(
    paciente_id: uuid.UUID,
    registro_id: uuid.UUID,
    principal: Leer,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
) -> Response:
    fila = await ServicioRegistros(sesion, reloj).obtener(principal, paciente_id, registro_id)
    # Exportar una receta suspendida como vigente sería inseguro.
    if fila.tipo == "RECETA":
        await exigir_vigente(sesion, fila)
    await auditar(auditor, principal, reloj, fila, AccionAuditada.REGISTRO_PACIENTE_LEIDO)
    await sesion.commit()
    return respuesta_pdf(fila)


@enrutador.post(PREFIJO + "/{registro_id}/whatsapp", response_model=EntregaSalida)
async def compartir(
    paciente_id: uuid.UUID,
    registro_id: uuid.UUID,
    datos: Compartir,
    principal: Escribir,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    cifrador: CifradorActual,
    configuracion: ConfiguracionActual,
) -> EntregaSalida:
    servicio = ServicioRegistros(sesion, reloj)
    fila = await servicio.obtener(principal, paciente_id, registro_id)
    await exigir_vigente(sesion, fila)
    if fila.tipo == "FACIOGRAMA" or fila.nivel_sensibilidad == "N3":
        raise PermisoDenegado("El mapa facial y los documentos N3 se entregan en la clínica.")
    paciente = await servicio.acceso(principal, paciente_id, True)
    if not paciente.telefono_whatsapp:
        raise DatosInvalidos("El paciente no tiene teléfono WhatsApp registrado.")
    await sesion.execute(select(Paciente.id).where(Paciente.id == paciente_id).with_for_update())
    clave = str(datos.clave_idempotencia)
    entrega = await sesion.scalar(
        select(EntregaDocumento).where(EntregaDocumento.clave_idempotencia == clave)
    )
    contexto = f"documento:{fila.clinica_id}:{fila.id}".encode()
    if entrega:
        if entrega.registro_id != fila.id or entrega.anulada or entrega.expira_en <= reloj.ahora():
            raise ConflictoEstado("La clave de envío ya fue utilizada.")
        token = cifrador.descifrar(entrega.token_cifrado, contexto=contexto)
    else:
        token = secrets.token_urlsafe(32)
        entrega = EntregaDocumento(
            id=uuid.uuid4(),
            registro_id=fila.id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            token_cifrado=cifrador.cifrar(token, contexto=contexto),
            expira_en=reloj.ahora() + timedelta(days=datos.dias_validez),
            clave_idempotencia=clave,
            creado_por=principal.actor_id,
            creado_en=reloj.ahora(),
        )
        enlace = f"{configuracion.frontend_url.rstrip('/')}/documentos/{token}"
        entrega.outbox_id = await ServicioOutbox(sesion, reloj, RegistroCanales()).encolar(
            SolicitudEnvio(
                tipo=TipoMensajeOutbox.DOCUMENTO_DISPONIBLE,
                canal=CanalOutbox.WHATSAPP,
                destino_tipo="PACIENTE",
                destino_id=paciente_id,
                clave_deduplicacion=f"documento:{entrega.id.hex}",
                variables={
                    "nombre": paciente.nombre,
                    "clinica": str(fila.contenido["clinica"]),
                    "enlace": enlace,
                    "dias": str(datos.dias_validez),
                },
                clinica_id=fila.clinica_id,
                entidad_origen_tipo="entrega_documento",
                entidad_origen_id=entrega.id,
            )
        )
        if entrega.outbox_id is None:
            raise ConflictoEstado("El envío está desactivado; no se ha enviado el documento.")
        sesion.add(entrega)
        await sesion.flush()
        await auditar(auditor, principal, reloj, fila, AccionAuditada.DOCUMENTO_COMPARTIDO)
    mensaje = await sesion.get(OutboxMensaje, entrega.outbox_id) if entrega.outbox_id else None
    modo = configuracion.modo_whatsapp
    integracion = await leer_integracion(sesion, fila.clinica_id, "whatsapp")
    if (
        integracion
        and integracion.habilitada
        and integracion.ajustes.get("id_numero_telefono")
        and descifrar(cifrador, fila.clinica_id, "whatsapp", "token_acceso", integracion)
    ):
        modo = "cloud_api"
    await sesion.commit()
    return EntregaSalida(
        id=entrega.id,
        enlace=f"{configuracion.frontend_url.rstrip('/')}/documentos/{token}",
        expira_en=entrega.expira_en,
        estado=mensaje.estado if mensaje else "PENDIENTE",
        modo=modo,
    )


@enrutador.post(
    "/publico/documentos/{token}/acceso",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def acceso_publico(
    token: Annotated[str, Path(min_length=20, max_length=100)],
    datos: Verificacion,
    peticion: Request,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    limitador: Limitador,
) -> Response:
    origen = peticion.client.host if peticion.client else "desconocido"
    await limitador.exigir(f"documentos:ip:{origen}", limite=10, fallar_cerrado=True)
    huella = hashlib.sha256(token.encode()).hexdigest()
    entrega = await sesion.scalar(
        select(EntregaDocumento).where(EntregaDocumento.token_hash == huella).with_for_update()
    )
    no_disponible = RecursoNoEncontrado(
        "El documento ya no está disponible. Solicite un enlace nuevo a la clínica."
    )
    if (
        entrega is None
        or entrega.anulada
        or entrega.expira_en <= reloj.ahora()
        or entrega.intentos_fallidos >= MAXIMO_INTENTOS
    ):
        raise no_disponible
    fila = await sesion.get(RegistroPaciente, entrega.registro_id)
    if fila is None:
        raise no_disponible
    await exigir_vigente(sesion, fila)
    paciente = await sesion.get(Paciente, fila.paciente_id)
    clinica = await sesion.get(Clinica, fila.clinica_id)
    if paciente is None or clinica is None or not clinica.activa:
        raise no_disponible
    if datos.fecha_nacimiento is None and not datos.ultimos_digitos_documento:
        raise DatosInvalidos(
            "Indique su fecha de nacimiento o los últimos cuatro caracteres del documento."
        )
    coincide = (
        datos.fecha_nacimiento == paciente.fecha_nacimiento
        if paciente.fecha_nacimiento
        else hmac.compare_digest(
            (datos.ultimos_digitos_documento or "").upper(),
            (paciente.numero_documento or "")[-4:].upper(),
        )
    )
    actor = _principal_paciente(paciente)
    if not coincide:
        entrega.intentos_fallidos += 1
        await auditor.registrar(
            [
                construir_entrada(
                    accion=AccionAuditada.DOCUMENTO_ACCESO_FALLIDO,
                    principal=actor,
                    ahora=reloj.ahora(),
                    resultado=ResultadoAuditoria.DENEGADO,
                    entidad_tipo="entrega_documento",
                    entidad_id=entrega.id,
                    paciente_id=paciente.id,
                )
            ]
        )
        await sesion.commit()
        raise CredencialesInvalidas("Los datos no coinciden o el enlace está bloqueado.")
    await auditar(auditor, actor, reloj, fila, AccionAuditada.REGISTRO_PACIENTE_LEIDO)
    await sesion.commit()
    return respuesta_pdf(fila)
