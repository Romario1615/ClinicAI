import uuid
from dataclasses import replace
from datetime import timedelta

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ia.conocimiento_paciente import buscador_publicado
from app.ia.conversacion import ProveedorDemostracion, ejecutar_turno
from app.ia.decisiones import ClasificadorIntencion
from app.ia.embeddings import ProveedorEmbeddings
from app.ia.herramientas.contrato import ContextoHerramienta
from app.ia.seleccion_llm import FabricaConversacional
from app.modulos.conversaciones.demo_esquemas import AbrirDemo, RespuestaDemo
from app.modulos.conversaciones.demo_modelos import SesionDemo
from app.modulos.conversaciones.modelos import Conversacion
from app.modulos.lista_espera.repositorio import RepositorioListaEspera
from app.modulos.organizacion.repositorio import RepositorioCatalogo
from app.modulos.pacientes.repositorio import RepositorioPacientes
from app.nucleo.autorizacion import NivelSensibilidad, Principal, TipoActor
from app.nucleo.configuracion import Configuracion
from app.nucleo.errores import DatosInvalidos, PermisoDenegado, RecursoNoEncontrado
from app.nucleo.operaciones import completar_operacion, iniciar_operacion
from app.nucleo.reloj import Reloj


async def abrir(
    sesion: AsyncSession, principal: Principal, reloj: Reloj, datos: AbrirDemo, clave: str
) -> RespuestaDemo:
    if principal.clinica_id is None or principal.actor_id is None:
        raise PermisoDenegado("La demostracion requiere una sesion de personal.")
    if datos.hasta - datos.desde > timedelta(days=7):
        raise DatosInvalidos("Seleccione hasta siete dias para la demostracion.")
    catalogo = RepositorioCatalogo(sesion)
    servicio = next(
        (s for s in await catalogo.listar_servicios(principal) if s.id == datos.servicio_id), None
    )
    if servicio is None:
        raise RecursoNoEncontrado("El servicio no existe.")
    await RepositorioListaEspera(sesion).validar_alta(
        principal,
        datos.paciente_id,
        datos.sede_id,
        servicio.especialidad_id,
        datos.servicio_id,
        datos.profesional_id,
    )
    operacion = await iniciar_operacion(
        sesion, principal, reloj, "demo.abrir", clave, datos.model_dump(mode="json")
    )
    if operacion.respuesta:
        return RespuestaDemo.model_validate(operacion.respuesta)
    hilo = Conversacion(
        clinica_id=principal.clinica_id,
        paciente_id=datos.paciente_id,
        canal="DEMO",
        # Es un identificador de simulacion, no un telefono ni un destinatario.
        telefono="demo:" + uuid.uuid4().hex[:27],
        estado="ABIERTA",
        asignado_a_usuario_id=principal.actor_id,
        ultima_actividad_en=reloj.ahora(),
    )
    sesion.add(hilo)
    await sesion.flush()
    demo = SesionDemo(
        conversacion_id=hilo.id,
        usuario_id=principal.actor_id,
        clinica_id=principal.clinica_id,
        paciente_id=datos.paciente_id,
        negocio=datos.model_dump(mode="json"),
        memoria={},
        expira_en=reloj.ahora() + timedelta(hours=2),
    )
    sesion.add(demo)
    await sesion.flush()
    respuesta = RespuestaDemo(
        sesion_id=demo.id,
        modo=datos.modo,
        mensaje=("Conversacion iniciada. Escriba 'buscar horarios', 'mis citas' o 'mis pagos'."),
    )
    completar_operacion(operacion, respuesta.model_dump(mode="json"), reloj)
    return respuesta


async def obtener(
    sesion: AsyncSession, principal: Principal, reloj: Reloj, identificador: uuid.UUID
) -> SesionDemo:
    consulta = (
        select(SesionDemo)
        .where(
            SesionDemo.id == identificador,
            SesionDemo.usuario_id == principal.actor_id,
            SesionDemo.clinica_id == principal.clinica_id,
            SesionDemo.expira_en > reloj.ahora(),
        )
        .with_for_update()
    )
    demo = (await sesion.execute(consulta)).scalar_one_or_none()
    if (
        demo is None
        or await RepositorioPacientes(sesion).obtener(demo.paciente_id, principal) is None
    ):
        raise RecursoNoEncontrado("La sesion no existe o ha caducado.")
    return demo


async def responder(
    sesion: AsyncSession,
    principal: Principal,
    reloj: Reloj,
    identificador: uuid.UUID,
    texto: str,
    clave: str,
    fabrica: FabricaConversacional,
    clasificador: ClasificadorIntencion | None = None,
    umbrales: tuple[float, float] = (0.35, 0.85),
    conocimiento: tuple[ProveedorEmbeddings, Configuracion] | None = None,
) -> RespuestaDemo:
    demo = await obtener(sesion, principal, reloj, identificador)
    registro = await iniciar_operacion(
        sesion, principal, reloj, "demo.mensaje", clave, {"id": identificador, "texto": texto}
    )
    if registro.respuesta:
        return RespuestaDemo.model_validate(registro.respuesta)
    hilo = await sesion.get(Conversacion, demo.conversacion_id)
    if hilo is None:
        raise RecursoNoEncontrado("La conversacion no existe.")
    if hilo.estado == "EN_HANDOFF":
        return RespuestaDemo(
            sesion_id=demo.id,
            modo=demo.negocio.get("modo", "simulado"),
            mensaje="Esta conversacion requiere atencion del personal. Inicie otra simulacion para continuar las pruebas.",
            requiere_humano=True,
        )
    actor = replace(
        principal,
        actor_tipo=TipoActor.AGENTE_IA,
        paciente_id=demo.paciente_id,
        ambito=replace(
            principal.ambito,
            pacientes=frozenset({demo.paciente_id}),
            todos_los_pacientes=False,
            nivel_maximo=NivelSensibilidad.ADMINISTRATIVO,
        ),
        permisos=principal.permisos
        & frozenset(
            {
                "agenda.leer",
                "cita.crear",
                "cita.cancelar",
                "cita.reprogramar",
                "conversacion.responder",
                "pago.leer",
            }
        ),
        origen="DEMO_LOCAL",
    )
    memoria = dict(demo.memoria)
    contexto = ContextoHerramienta(actor, sesion, reloj, demo.conversacion_id)
    resultado, herramientas = await ejecutar_turno(
        fabrica() if demo.negocio.get("modo") == "configurado" else ProveedorDemostracion(),
        texto,
        memoria,
        demo.negocio,
        contexto,
        clasificador=clasificador,
        umbral_clinico=umbrales[0],
        umbral_intencion=umbrales[1],
        buscar_conocimiento=(
            buscador_publicado(sesion, conocimiento[0], conocimiento[1], actor, reloj)
            if conocimiento is not None
            else None
        ),
    )
    # Una colision de agenda puede deshacer la transaccion. Recuperamos el
    # registro del canal sin perder la respuesta segura que tradujo la herramienta.
    if demo not in sesion or inspect(demo).expired:
        demo = await obtener(sesion, principal, reloj, identificador)
        registro = await iniciar_operacion(
            sesion, principal, reloj, "demo.mensaje", clave, {"id": identificador, "texto": texto}
        )
    if resultado.exito:
        for campo in ("turnos", "cita_id", "inicio", "citas", "expira_en", "zona_horaria"):
            if campo in resultado.datos:
                memoria[campo] = resultado.datos[campo]
        if "hold_slot" in herramientas:
            memoria.pop("turnos", None)
        if "cancel_appointment" in herramientas:
            memoria.pop("cita_id", None)
    demo.memoria = memoria
    respuesta = RespuestaDemo(
        sesion_id=demo.id,
        modo=str(demo.negocio.get("modo", "simulado")),
        mensaje=resultado.mensaje,
        requiere_humano=resultado.requiere_humano,
        herramientas=herramientas,
        datos=resultado.datos,
    )
    completar_operacion(registro, respuesta.model_dump(mode="json"), reloj)
    return respuesta
