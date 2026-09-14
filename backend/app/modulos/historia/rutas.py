"""Rutas de la historia clinica.

Toda lectura de historia se audita
----------------------------------
El servicio devuelve la entrada de auditoria junto con los datos, y esta capa
la escribe y confirma **antes** de responder. No es una formalidad: es la
unica forma de contestar a «quien vio mi historia», y el acceso por
curiosidad -- el caso mas frecuente en una clinica -- no deja otro rastro.

Que se puede hacer y que no
---------------------------
Hay tres capas antes de tocar un dato clinico, y ninguna sustituye a las
otras:

1. `exige_permiso` responde «esta persona puede ejecutar esta operacion».
2. El servicio comprueba la **relacion asistencial**: «tiene vinculo con ESTE
   paciente». El permiso solo no basta.
3. El repositorio filtra por ambito en el `WHERE`.

Una nota o una receta fuera de alcance devuelven **404**, igual que una
inexistente. Un 403 confirmaria que ese identificador corresponde a un
registro real.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from app.modulos.historia.esquemas import (
    ConfirmacionReceta,
    CorreccionNota,
    MedicamentoSalida,
    NotaEntrada,
    NotaSalida,
    RecetaEntrada,
    RecetaSalida,
    RegistroToma,
    ResultadoConfirmacion,
    ResultadoSuspension,
    SuspensionReceta,
    TomaSalida,
)
from app.modulos.historia.modelos import NotaEvolucion, Receta, RecetaMedicamento
from app.modulos.historia.repositorio import RepositorioHistoria
from app.modulos.historia.servicios import DatosMedicamento, DatosNota
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import (
    Auditor,
    RepoHistoria,
    ServicioDeHistoria,
    Sesion,
    exige_permiso,
)
from app.nucleo.errores import ErrorDominio

enrutador = APIRouter(prefix="/historia", tags=["historia clinica"])

PuedeLeer = Annotated[Principal, Depends(exige_permiso("historia_clinica.leer"))]
PuedeEscribir = Annotated[Principal, Depends(exige_permiso("historia_clinica.escribir"))]
PuedeCrearReceta = Annotated[Principal, Depends(exige_permiso("receta.crear"))]
PuedeConfirmarReceta = Annotated[Principal, Depends(exige_permiso("receta.confirmar"))]
PuedeLeerReceta = Annotated[Principal, Depends(exige_permiso("receta.leer"))]


def _a_nota(nota: NotaEvolucion) -> NotaSalida:
    return NotaSalida(
        id=nota.id,
        raiz_id=nota.raiz_id,
        version=nota.version,
        vigente=nota.vigente,
        motivo_modificacion=nota.motivo_modificacion,
        paciente_id=nota.paciente_id,
        profesional_id=nota.profesional_id,
        cita_id=nota.cita_id,
        tipo=nota.tipo,
        motivo_consulta=nota.motivo_consulta,
        subjetivo=nota.subjetivo,
        objetivo=nota.objetivo,
        analisis=nota.analisis,
        plan=nota.plan,
        signos_vitales=nota.signos_vitales,
        creado_en=nota.creado_en,
    )


def _a_receta(receta: Receta, medicamentos: list[RecetaMedicamento]) -> RecetaSalida:
    return RecetaSalida(
        id=receta.id,
        paciente_id=receta.paciente_id,
        profesional_id=receta.profesional_id,
        estado=receta.estado,
        confirmada_en=receta.confirmada_en,
        suspendida_en=receta.suspendida_en,
        motivo_suspension=receta.motivo_suspension,
        indicaciones_generales=receta.indicaciones_generales,
        creado_en=receta.creado_en,
        medicamentos=[
            MedicamentoSalida(
                id=m.id,
                nombre=m.nombre,
                concentracion=m.concentracion,
                forma=m.forma,
                dosis=m.dosis,
                via=m.via,
                cuando_sea_necesario=m.cuando_sea_necesario,
                frecuencia_horas=m.frecuencia_horas,
                duracion_dias=m.duracion_dias,
                instrucciones=m.instrucciones,
            )
            for m in medicamentos
        ],
    )


def _a_datos_nota(datos: NotaEntrada) -> DatosNota:
    return DatosNota(
        paciente_id=datos.paciente_id,
        profesional_id=datos.profesional_id,
        tipo=datos.tipo,
        motivo_consulta=datos.motivo_consulta,
        subjetivo=datos.subjetivo,
        objetivo=datos.objetivo,
        analisis=datos.analisis,
        plan=datos.plan,
        signos_vitales=dict(datos.signos_vitales) if datos.signos_vitales else None,
        cita_id=datos.cita_id,
        diagnosticos=tuple(
            (d.codigo_cie10, d.descripcion, d.principal, d.presuntivo) for d in datos.diagnosticos
        ),
    )


# ===========================================================================
#  Notas
# ===========================================================================
@enrutador.get(
    "/pacientes/{paciente_id}/notas",
    response_model=list[NotaSalida],
    summary="Historia clinica de un paciente",
    responses={
        403: {"description": "Sin permiso, o sin relacion asistencial con el paciente"},
    },
)
async def leer_historia(
    principal: PuedeLeer,
    servicio: ServicioDeHistoria,
    sesion: Sesion,
    auditor: Auditor,
    paciente_id: Annotated[uuid.UUID, Path()],
    incluir_historico: Annotated[
        bool,
        Query(description="Incluye las versiones anteriores de cada nota, no solo la vigente."),
    ] = False,
) -> list[NotaSalida]:
    """Devuelve la historia y **deja constancia de quien la consulto**.

    La auditoria se confirma antes de responder. Si se escribiera despues y
    la respuesta fallara al serializarse, el acceso habria ocurrido sin
    registro.
    """
    notas, auditoria = await servicio.leer_historia(
        paciente_id, principal=principal, incluir_historico=incluir_historico
    )
    await auditor.registrar(auditoria)
    await sesion.commit()
    return [_a_nota(nota) for nota in notas]


@enrutador.post(
    "/notas",
    response_model=NotaSalida,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una nota de evolucion",
    responses={403: {"description": "Sin permiso o sin relacion asistencial"}},
)
async def crear_nota(
    principal: PuedeEscribir,
    datos: NotaEntrada,
    servicio: ServicioDeHistoria,
    sesion: Sesion,
    auditor: Auditor,
) -> NotaSalida:
    resultado = await servicio.crear_nota(_a_datos_nota(datos), principal=principal)
    await auditor.registrar(resultado.auditoria)
    await sesion.commit()
    if resultado.nota is None:  # pragma: sin cobertura - el servicio devuelve nota o lanza
        raise ErrorDominio("No se pudo crear la nota.")
    return _a_nota(resultado.nota)


@enrutador.post(
    "/notas/{raiz_id}/correccion",
    response_model=NotaSalida,
    summary="Corregir una nota creando una version nueva",
    responses={
        404: {"description": "No existe, o esta fuera de alcance"},
        422: {"description": "Falta el motivo de la correccion"},
    },
)
async def corregir_nota(
    principal: PuedeEscribir,
    datos: CorreccionNota,
    servicio: ServicioDeHistoria,
    sesion: Sesion,
    auditor: Auditor,
    raiz_id: Annotated[uuid.UUID, Path()],
) -> NotaSalida:
    """Crea la version siguiente. **No reescribe nada.**

    La version anterior conserva su contenido y sigue siendo consultable con
    `incluir_historico`. El motivo es obligatorio: ante una reclamacion la
    pregunta es por que cambio, no si cambio.
    """
    resultado = await servicio.versionar_nota(
        raiz_id, _a_datos_nota(datos), principal=principal, motivo=datos.motivo
    )
    await auditor.registrar(resultado.auditoria)
    await sesion.commit()
    if resultado.nota is None:  # pragma: sin cobertura - el servicio devuelve nota o lanza
        raise ErrorDominio("No se pudo corregir la nota.")
    return _a_nota(resultado.nota)


# ===========================================================================
#  Recetas
# ===========================================================================
@enrutador.get(
    "/pacientes/{paciente_id}/recetas",
    response_model=list[RecetaSalida],
    summary="Recetas de un paciente",
)
async def listar_recetas(
    principal: PuedeLeerReceta,
    repo: RepoHistoria,
    servicio: ServicioDeHistoria,
    paciente_id: Annotated[uuid.UUID, Path()],
    solo_vigentes: Annotated[bool, Query()] = False,
) -> list[RecetaSalida]:
    ahora = servicio.ahora()
    recetas = await repo.listar_recetas(
        principal=principal, paciente_id=paciente_id, ahora=ahora, solo_vigentes=solo_vigentes
    )
    salida: list[RecetaSalida] = []
    for receta in recetas:
        medicamentos = await repo.medicamentos_de(receta.id)
        salida.append(_a_receta(receta, medicamentos))
    return salida


@enrutador.post(
    "/recetas",
    response_model=RecetaSalida,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una receta en borrador",
)
async def crear_receta(
    principal: PuedeCrearReceta,
    datos: RecetaEntrada,
    servicio: ServicioDeHistoria,
    repo: RepoHistoria,
    sesion: Sesion,
    auditor: Auditor,
) -> RecetaSalida:
    """Crea la receta **en borrador**, nunca confirmada.

    La confirmacion es un acto distinto del profesional, y es la que convierte
    un texto en una indicacion vigente con recordatorios.
    """
    resultado = await servicio.crear_receta(
        principal=principal,
        paciente_id=datos.paciente_id,
        profesional_id=datos.profesional_id,
        nota_id=datos.nota_id,
        indicaciones_generales=datos.indicaciones_generales,
        medicamentos=[
            DatosMedicamento(
                nombre=m.nombre,
                dosis=m.dosis,
                via=m.via,
                cuando_sea_necesario=m.cuando_sea_necesario,
                frecuencia_horas=m.frecuencia_horas,
                duracion_dias=m.duracion_dias,
                hora_primera_toma=m.hora_primera_toma,
                concentracion=m.concentracion,
                forma=m.forma,
                instrucciones=m.instrucciones,
            )
            for m in datos.medicamentos
        ],
    )
    await auditor.registrar(resultado.auditoria)
    await sesion.commit()

    if resultado.receta is None:  # pragma: sin cobertura - el servicio devuelve receta o lanza
        raise ErrorDominio("No se pudo crear la receta.")
    medicamentos = await repo.medicamentos_de(resultado.receta.id)
    return _a_receta(resultado.receta, medicamentos)


@enrutador.post(
    "/recetas/{receta_id}/confirmacion",
    response_model=ResultadoConfirmacion,
    summary="Confirmar una receta y generar el calendario de tomas",
    responses={
        404: {"description": "No existe, o esta fuera de alcance"},
        409: {"description": "La receta no esta en borrador"},
        422: {"description": "La pauta generaria demasiadas tomas"},
    },
)
async def confirmar_receta(
    principal: PuedeConfirmarReceta,
    datos: ConfirmacionReceta,
    servicio: ServicioDeHistoria,
    repo: RepoHistoria,
    sesion: Sesion,
    auditor: Auditor,
    receta_id: Annotated[uuid.UUID, Path()],
) -> ResultadoConfirmacion:
    """Confirma y genera las tomas.

    Es el **unico** camino que crea tomas, y un disparador de la base lo
    respalda: insertar una toma de una receta sin confirmar se rechaza.

    `tomas_generadas` puede ser cero legitimamente: una receta que solo
    contiene medicamentos «cuando sea necesario» no genera ninguna, porque
    convertir un PRN en pauta fija seria un error de medicacion.
    """
    resultado = await servicio.confirmar_receta(
        receta_id, principal=principal, profesional_id=datos.profesional_id
    )
    await auditor.registrar(resultado.auditoria)
    await sesion.commit()

    if resultado.receta is None:  # pragma: sin cobertura - el servicio devuelve receta o lanza
        raise ErrorDominio("No se pudo confirmar la receta.")
    medicamentos = await repo.medicamentos_de(resultado.receta.id)
    return ResultadoConfirmacion(
        receta=_a_receta(resultado.receta, medicamentos),
        tomas_generadas=resultado.tomas_generadas,
    )


@enrutador.post(
    "/recetas/{receta_id}/suspension",
    response_model=ResultadoSuspension,
    summary="Suspender una receta y cancelar sus tomas futuras",
    responses={
        404: {"description": "No existe, o esta fuera de alcance"},
        409: {"description": "La receta ya esta suspendida"},
    },
)
async def suspender_receta(
    principal: PuedeConfirmarReceta,
    datos: SuspensionReceta,
    servicio: ServicioDeHistoria,
    repo: RepoHistoria,
    sesion: Sesion,
    auditor: Auditor,
    receta_id: Annotated[uuid.UUID, Path()],
) -> ResultadoSuspension:
    """Suspende y cancela las tomas **futuras** pendientes.

    Las pasadas no se tocan: son el registro de lo que ocurrio, y
    reescribirlo falsearia el historico de adherencia que el profesional mira
    para decidir si el tratamiento funciona.
    """
    resultado = await servicio.suspender_receta(receta_id, principal=principal, motivo=datos.motivo)
    await auditor.registrar(resultado.auditoria)
    await sesion.commit()

    if resultado.receta is None:  # pragma: sin cobertura - el servicio devuelve receta o lanza
        raise ErrorDominio("No se pudo suspender la receta.")
    medicamentos = await repo.medicamentos_de(resultado.receta.id)
    return ResultadoSuspension(
        receta=_a_receta(resultado.receta, medicamentos),
        tomas_canceladas=resultado.tomas_canceladas,
    )


# ===========================================================================
#  Tomas
# ===========================================================================
@enrutador.get(
    "/pacientes/{paciente_id}/tomas",
    response_model=list[TomaSalida],
    summary="Calendario de tomas de un paciente",
    responses={
        403: {"description": "Sin permiso, o sin relacion asistencial con el paciente"},
        422: {"description": "Rango invalido"},
    },
)
async def listar_tomas(
    principal: Annotated[Principal, Depends(exige_permiso("adherencia.leer", "receta.leer"))],
    servicio: ServicioDeHistoria,
    sesion: Sesion,
    paciente_id: Annotated[uuid.UUID, Path()],
    dias: Annotated[int, Query(ge=1, le=31)] = 7,
) -> list[TomaSalida]:
    """Tomas programadas alrededor de hoy, con el nombre de su medicamento.

    Es una lectura administrativa del calendario, **no** una valoracion: no
    dice si el tratamiento funciona ni si hay que cambiarlo. Esa lectura es del
    profesional (CLAUDE.md, regla 5).

    La ventana se centra en el momento actual y no empieza en el: quien atiende
    necesita ver lo que quedo atras sin registrar, que es justo lo que importa
    de la adherencia, y no solo lo que viene.
    """
    ahora = servicio.ahora()
    filas = await RepositorioHistoria(sesion).listar_tomas(
        principal=principal,
        paciente_id=paciente_id,
        desde=ahora - timedelta(days=dias),
        hasta=ahora + timedelta(days=dias),
        ahora=ahora,
    )
    return [
        TomaSalida(
            id=toma.id,
            receta_medicamento_id=medicamento.id,
            medicamento=medicamento.nombre,
            programada_en=toma.programada_en,
            estado=toma.estado,
            registrada_en=toma.registrada_en,
        )
        for toma, medicamento in filas
    ]


@enrutador.post(
    "/tomas/{toma_id}/registro",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Registrar que una toma se hizo o se omitio",
    responses={
        404: {"description": "No existe, o esta fuera de alcance"},
        409: {"description": "La toma ya se registro"},
        422: {"description": "La hora de la toma todavia no llego"},
    },
)
async def registrar_toma(
    principal: Annotated[Principal, Depends(exige_permiso("adherencia.leer", "receta.leer"))],
    datos: RegistroToma,
    servicio: ServicioDeHistoria,
    sesion: Sesion,
    auditor: Auditor,
    toma_id: Annotated[uuid.UUID, Path()],
) -> None:
    """Lo registra el personal o el propio paciente.

    No se acepta una toma futura: marcar como tomada una dosis que todavia no
    toca produce un registro de adherencia falso, y ese registro es lo que el
    profesional mira para decidir.
    """
    resultado = await servicio.registrar_toma(
        toma_id,
        principal=principal,
        tomada=datos.tomada,
        nota_paciente=datos.nota_paciente,
    )
    await auditor.registrar(resultado.auditoria)
    await sesion.commit()


@enrutador.get(
    "/recetas/{receta_id}/adherencia",
    summary="Evaluar la adherencia de una receta",
    responses={404: {"description": "No existe, o esta fuera de alcance"}},
)
async def evaluar_adherencia(
    principal: Annotated[Principal, Depends(exige_permiso("adherencia.leer"))],
    servicio: ServicioDeHistoria,
    sesion: Sesion,
    receta_id: Annotated[uuid.UUID, Path()],
    dias: Annotated[int, Query(ge=1, le=90)] = 7,
) -> dict[str, object]:
    """Cuenta omisiones y crea la alerta si procede.

    **No interpreta nada clinicamente.** Devuelve cuantas tomas se omitieron
    sobre las esperadas; no concluye que el tratamiento haya fallado ni
    sugiere cambiarlo. Esa lectura es del profesional (CLAUDE.md, regla 5).
    """
    alerta = await servicio.evaluar_adherencia(receta_id, principal=principal, dias=dias)
    await sesion.commit()

    if alerta is None:
        return {
            "alerta": None,
            "motivo": (
                "No hay suficientes tomas en el periodo, o la proporcion de omisiones no "
                "alcanza el umbral, o ya existe una alerta abierta para esta receta."
            ),
        }
    return {
        "alerta": {
            "id": str(alerta.id),
            "severidad": alerta.severidad,
            "tomas_omitidas": alerta.tomas_omitidas,
            "tomas_esperadas": alerta.tomas_esperadas,
            "periodo_desde": alerta.periodo_desde.isoformat(),
            "periodo_hasta": alerta.periodo_hasta.isoformat(),
        }
    }


__all__ = ["enrutador"]
