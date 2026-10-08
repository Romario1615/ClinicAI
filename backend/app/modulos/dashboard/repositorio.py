import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, case, cast, func, select
from sqlalchemy.dialects.postgresql import DATE
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita, EstadoCita
from app.modulos.agenda.repositorio import RepositorioAgenda
from app.modulos.dashboard.esquemas import (
    CeldaDemografica,
    CohorteRegistroPacientes,
    ConteoCitasPorDia,
    ConteoCitasPorDiaSemana,
    ConteoCitasPorHora,
    FiltroDashboard,
    ResumenAdherencia,
    ResumenDashboard,
    ResumenDemografico,
    ResumenEspera,
    ResumenRecuperacionTurnos,
    Retorno30Dias,
)
from app.modulos.dashboard.ocupacion_agenda import (
    ocupacion_no_calculada,
    resumir_ocupacion_agenda,
)
from app.modulos.historia.modelos import (
    AlertaAdherencia,
    NotaEvolucion,
    Receta,
    RecetaMedicamento,
    Toma,
)
from app.modulos.historia.repositorio import RepositorioHistoria
from app.modulos.lista_espera.modelos import EstadoOferta, OfertaTurno
from app.modulos.organizacion.modelos import (
    Clinica,
    Sede,
    Servicio,
)
from app.modulos.pacientes.modelos import Paciente
from app.modulos.pacientes.repositorio import RepositorioPacientes
from app.modulos.pagos.modelos import Pago
from app.modulos.profesionales.modelos import (
    Profesional,
)
from app.nucleo.autorizacion import Principal

_MINIMO_GRUPO_DEMOGRAFICO = 5
_MAYORIA_EDAD = 18
_LIMITE_EDAD_JOVEN = 30
_LIMITE_EDAD_ADULTO = 45
_LIMITE_EDAD_MAYOR = 60


async def _resumir_recuperacion_turnos(
    sesion: AsyncSession,
    principal: Principal,
    filtro: FiltroDashboard,
    *,
    sede_id: uuid.UUID | None,
    profesional_id: uuid.UUID | None,
    especialidad_id: uuid.UUID | None,
    servicio_id: uuid.UUID | None,
) -> tuple[int, int, int | None]:
    """Cuenta liberaciones y ofertas aceptadas dentro del ámbito autorizado."""
    consulta = (
        RepositorioAgenda(sesion)
        .consulta_autorizada(principal)
        .where(Cita.cancelada_en.is_not(None))
    )
    consulta = _aplicar_filtros(
        consulta,
        sede_id=sede_id,
        profesional_id=profesional_id,
        especialidad_id=especialidad_id,
        servicio_id=servicio_id,
        estado=None,
    )
    cancelaciones = consulta.subquery()
    liberados = int(
        (
            await sesion.execute(
                select(func.count())
                .select_from(cancelaciones)
                .where(
                    cancelaciones.c.cancelada_en >= filtro.desde,
                    cancelaciones.c.cancelada_en < filtro.hasta,
                )
            )
        ).scalar_one()
    )

    consulta_liberadas = (
        RepositorioAgenda(sesion)
        .consulta_autorizada(principal)
        .where(Cita.cancelada_en.is_not(None))
    )
    consulta_liberadas = _aplicar_filtros(
        consulta_liberadas,
        sede_id=sede_id,
        profesional_id=profesional_id,
        especialidad_id=especialidad_id,
        servicio_id=servicio_id,
        estado=None,
    )
    citas_liberadas = consulta_liberadas.subquery()
    demora_minutos = (
        func.extract("epoch", OfertaTurno.respondida_en - citas_liberadas.c.cancelada_en) / 60
    )
    filas = await sesion.execute(
        select(func.count(OfertaTurno.id), func.floor(func.avg(demora_minutos)))
        .select_from(
            citas_liberadas.join(
                OfertaTurno,
                OfertaTurno.cita_liberada_id == citas_liberadas.c.id,
            )
        )
        .where(
            OfertaTurno.estado == EstadoOferta.ACEPTADA.value,
            OfertaTurno.respondida_en >= filtro.desde,
            OfertaTurno.respondida_en < filtro.hasta,
            OfertaTurno.respondida_en >= citas_liberadas.c.cancelada_en,
        )
    )
    recuperados, promedio = filas.one()
    return int(liberados), int(recuperados), int(promedio) if promedio is not None else None


def _aplicar_filtros_receta(
    consulta: Select[Any],
    *,
    sede_id: uuid.UUID | None,
    profesional_id: uuid.UUID | None,
    especialidad_id: uuid.UUID | None,
    servicio_id: uuid.UUID | None,
) -> Select[Any]:
    if especialidad_id:
        consulta = consulta.join(Profesional, Profesional.id == Receta.profesional_id)
        consulta = consulta.where(Profesional.especialidad_id == especialidad_id)
    if profesional_id:
        consulta = consulta.where(Receta.profesional_id == profesional_id)
    if sede_id or servicio_id:
        consulta = consulta.join(NotaEvolucion, NotaEvolucion.id == Receta.nota_id).join(
            Cita, Cita.id == NotaEvolucion.cita_id
        )
    if sede_id:
        consulta = consulta.where(Cita.sede_id == sede_id)
    if servicio_id:
        consulta = consulta.where(Cita.servicio_id == servicio_id)
    return consulta


async def _resumir_adherencia(
    sesion: AsyncSession,
    principal: Principal,
    filtro: FiltroDashboard,
    ahora: datetime,
    *,
    sede_id: uuid.UUID | None,
    profesional_id: uuid.UUID | None,
    especialidad_id: uuid.UUID | None,
    servicio_id: uuid.UUID | None,
) -> ResumenAdherencia:
    """Agrega estados de dosis sin devolver identidad, medicamento ni nota clínica."""
    repositorio = RepositorioHistoria(sesion)
    consulta_tomas = (
        select(Toma.estado)
        .join(RecetaMedicamento, RecetaMedicamento.id == Toma.receta_medicamento_id)
        .join(Receta, Receta.id == RecetaMedicamento.receta_id)
        .where(Toma.programada_en >= filtro.desde, Toma.programada_en < filtro.hasta)
    )
    consulta_tomas = repositorio.consulta_receta_autorizada(
        consulta_tomas, principal=principal, ahora=ahora
    )
    consulta_tomas = _aplicar_filtros_receta(
        consulta_tomas,
        sede_id=sede_id,
        profesional_id=profesional_id,
        especialidad_id=especialidad_id,
        servicio_id=servicio_id,
    )
    tomas = consulta_tomas.subquery()
    conteos = await sesion.execute(
        select(
            func.count().filter(tomas.c.estado == "TOMADA"),
            func.count().filter(tomas.c.estado == "OMITIDA"),
        )
    )
    tomadas, omitidas = (int(valor) for valor in conteos.one())

    consulta_alertas = (
        select(AlertaAdherencia.id)
        .join(Receta, Receta.id == AlertaAdherencia.receta_id)
        .where(AlertaAdherencia.atendida_en.is_(None))
    )
    consulta_alertas = repositorio.consulta_receta_autorizada(
        consulta_alertas, principal=principal, ahora=ahora
    )
    consulta_alertas = _aplicar_filtros_receta(
        consulta_alertas,
        sede_id=sede_id,
        profesional_id=profesional_id,
        especialidad_id=especialidad_id,
        servicio_id=servicio_id,
    )
    alertas = consulta_alertas.subquery()
    pendientes = int((await sesion.execute(select(func.count()).select_from(alertas))).scalar_one())
    registradas = tomadas + omitidas
    porcentaje = round(tomadas * 100 / registradas, 1) if registradas else None
    return ResumenAdherencia(
        tomas_confirmadas=tomadas,
        tomas_omitidas=omitidas,
        porcentaje_registro_positivo=porcentaje,
        seguimientos_pendientes=pendientes,
    )


def _aplicar_filtros(
    consulta: Select[tuple[Cita]],
    *,
    sede_id: uuid.UUID | None,
    profesional_id: uuid.UUID | None,
    especialidad_id: uuid.UUID | None,
    servicio_id: uuid.UUID | None,
    estado: EstadoCita | None,
) -> Select[tuple[Cita]]:
    if sede_id:
        consulta = consulta.where(Cita.sede_id == sede_id)
    if profesional_id:
        consulta = consulta.where(Cita.profesional_id == profesional_id)
    if especialidad_id is not None or servicio_id is not None:
        consulta = consulta.join(Servicio, Servicio.id == Cita.servicio_id)
    if especialidad_id:
        consulta = consulta.where(Servicio.especialidad_id == especialidad_id)
    if servicio_id:
        consulta = consulta.where(Cita.servicio_id == servicio_id)
    if estado:
        consulta = consulta.where(Cita.estado == estado.value)
    return consulta


async def _resumir_cohortes_registro(
    sesion: AsyncSession,
    principal: Principal,
    filtro: FiltroDashboard,
    *,
    sede_id: uuid.UUID | None,
    profesional_id: uuid.UUID | None,
    especialidad_id: uuid.UUID | None,
    servicio_id: uuid.UUID | None,
) -> tuple[int, int, list[CohorteRegistroPacientes]]:
    """Agrupa altas administrativas por mes y cruza solo citas visibles en el filtro.

    El resultado cuenta pacientes activos que el principal puede consultar. Una cita
    significa cualquier registro agendado dentro de las fechas y filtros actuales,
    sin importar su estado. El filtro de estado no llega aquí: vuelve ambiguo llamar
    "sin cita" a quien tiene una cita en un estado distinto.
    """
    pacientes = (
        RepositorioPacientes(sesion)
        .consulta_autorizada(principal)
        .where(Paciente.creado_en >= filtro.desde, Paciente.creado_en < filtro.hasta)
        .subquery()
    )
    consulta_citas = (
        RepositorioAgenda(sesion)
        .consulta_autorizada(principal)
        .where(Cita.inicio >= filtro.desde, Cita.inicio < filtro.hasta)
    )
    consulta_citas = _aplicar_filtros(
        consulta_citas,
        sede_id=sede_id,
        profesional_id=profesional_id,
        especialidad_id=especialidad_id,
        servicio_id=servicio_id,
        estado=None,
    )
    citas = consulta_citas.with_only_columns(Cita.id, Cita.paciente_id).subquery()
    mes_local = cast(
        func.date_trunc("month", func.timezone(Clinica.zona_horaria, pacientes.c.creado_en)),
        DATE,
    )
    filas = await sesion.execute(
        select(
            mes_local.label("mes"),
            func.count(func.distinct(pacientes.c.id)),
            func.count(func.distinct(pacientes.c.id)).filter(citas.c.id.is_not(None)),
        )
        .select_from(pacientes)
        .join(Clinica, Clinica.id == pacientes.c.clinica_id)
        .outerjoin(citas, citas.c.paciente_id == pacientes.c.id)
        .group_by(mes_local)
        .order_by(mes_local)
    )
    cohortes: list[CohorteRegistroPacientes] = []
    for mes, registrados, con_cita in filas:
        total_registrados = int(registrados)
        total_con_cita = int(con_cita)
        cohortes.append(
            CohorteRegistroPacientes(
                mes=mes,
                registrados=total_registrados,
                con_cita_en_filtros=total_con_cita,
                sin_cita_en_filtros=total_registrados - total_con_cita,
            )
        )
    total_registrados = sum(cohorte.registrados for cohorte in cohortes)
    sin_cita = sum(cohorte.sin_cita_en_filtros for cohorte in cohortes)
    return total_registrados, sin_cita, cohortes


def _celdas_demograficas(conteos: dict[str, int]) -> list[CeldaDemografica] | None:
    """Suprime grupos <5 y una segunda celda cuando la resta revelaría la primera."""
    if sum(conteos.values()) < _MINIMO_GRUPO_DEMOGRAFICO:
        return None

    suprimidas = {
        categoria
        for categoria, cantidad in conteos.items()
        if 0 < cantidad < _MINIMO_GRUPO_DEMOGRAFICO
    }
    if len(suprimidas) == 1:
        secundarias = [
            (categoria, cantidad)
            for categoria, cantidad in conteos.items()
            if cantidad >= _MINIMO_GRUPO_DEMOGRAFICO and categoria not in suprimidas
        ]
        if secundarias:
            categoria_menor, _ = min(secundarias, key=lambda par: (par[1], par[0]))
            suprimidas.add(categoria_menor)

    return [
        CeldaDemografica(
            categoria=categoria,
            pacientes=None if categoria in suprimidas else cantidad,
            suprimida=categoria in suprimidas,
        )
        for categoria, cantidad in conteos.items()
    ]


async def _resumir_demografia(
    sesion: AsyncSession,
    principal: Principal,
    filtro: FiltroDashboard,
    citas: Any,
) -> ResumenDemografico | None:
    """Resume pacientes con citas visibles; nunca devuelve edad exacta ni identidad."""
    autorizados = RepositorioPacientes(sesion).consulta_autorizada(principal).subquery()
    citas_seleccionadas = (
        select(citas.c.paciente_id).where(citas.c.paciente_id.is_not(None)).distinct().subquery()
    )
    poblacion = (
        select(
            autorizados.c.id,
            autorizados.c.sexo,
            autorizados.c.fecha_nacimiento,
            Clinica.zona_horaria.label("zona_horaria"),
        )
        .select_from(autorizados)
        .join(citas_seleccionadas, citas_seleccionadas.c.paciente_id == autorizados.c.id)
        .join(Clinica, Clinica.id == autorizados.c.clinica_id)
        .subquery()
    )
    fecha_corte_local = func.timezone(
        poblacion.c.zona_horaria,
        filtro.hasta - timedelta(microseconds=1),
    )
    edad = func.extract("year", func.age(fecha_corte_local, poblacion.c.fecha_nacimiento))
    grupo_edad = case(
        (poblacion.c.fecha_nacimiento.is_(None), "Sin fecha de nacimiento"),
        (edad < 0, "Fecha no válida"),
        (edad < _MAYORIA_EDAD, "0-17 años"),
        (edad < _LIMITE_EDAD_JOVEN, "18-29 años"),
        (edad < _LIMITE_EDAD_ADULTO, "30-44 años"),
        (edad < _LIMITE_EDAD_MAYOR, "45-59 años"),
        else_="60 o más",
    )
    grupo_sexo = case(
        (poblacion.c.sexo == "F", "Femenino"),
        (poblacion.c.sexo == "M", "Masculino"),
        (poblacion.c.sexo == "OTRO", "Otro"),
        else_="Sin registrar",
    )
    filas = await sesion.execute(
        select(
            grupo_edad.label("edad"),
            grupo_sexo.label("sexo"),
            func.count(func.distinct(poblacion.c.id)),
        )
        .select_from(poblacion)
        .group_by(grupo_edad, grupo_sexo)
    )
    edades = dict.fromkeys(
        (
            "0-17 años",
            "18-29 años",
            "30-44 años",
            "45-59 años",
            "60 o más",
            "Sin fecha de nacimiento",
            "Fecha no válida",
        ),
        0,
    )
    sexos = dict.fromkeys(("Femenino", "Masculino", "Otro", "Sin registrar"), 0)
    for grupo_edad_db, grupo_sexo_db, cantidad in filas:
        edades[str(grupo_edad_db)] += int(cantidad)
        sexos[str(grupo_sexo_db)] += int(cantidad)

    celdas_edades = _celdas_demograficas(edades)
    celdas_sexos = _celdas_demograficas(sexos)
    if celdas_edades is None or celdas_sexos is None:
        return None
    return ResumenDemografico(edades=celdas_edades, sexos=celdas_sexos)


def _retorno_30_dias_protegido(
    pacientes_seguimiento_completo: int,
    pacientes_que_regresaron: int,
) -> Retorno30Dias | None:
    """No revela cohortes ni desenlaces de uno a cuatro pacientes."""
    pacientes_sin_retorno = pacientes_seguimiento_completo - pacientes_que_regresaron
    if pacientes_seguimiento_completo < _MINIMO_GRUPO_DEMOGRAFICO:
        return None
    if 0 < pacientes_que_regresaron < _MINIMO_GRUPO_DEMOGRAFICO:
        return None
    if 0 < pacientes_sin_retorno < _MINIMO_GRUPO_DEMOGRAFICO:
        return None
    return Retorno30Dias(
        pacientes_seguimiento_completo=pacientes_seguimiento_completo,
        pacientes_que_regresaron=pacientes_que_regresaron,
        porcentaje=round(pacientes_que_regresaron * 100 / pacientes_seguimiento_completo, 1),
    )


async def _resumir_retorno_30_dias(
    sesion: AsyncSession,
    principal: Principal,
    filtro: FiltroDashboard,
    ahora: datetime,
    *,
    sede_id: uuid.UUID | None,
    profesional_id: uuid.UUID | None,
    especialidad_id: uuid.UUID | None,
    servicio_id: uuid.UUID | None,
) -> Retorno30Dias | None:
    """Mide retorno operativo; solo incluye cohortes con ventana completa de 720 horas.

    La cita índice es la primera atención completada del paciente en el periodo. Un
    retorno requiere otra atención completada, bajo el mismo ámbito y filtros, más
    tarde y hasta 30 días exactos después. La cohorte se limita al periodo; la ventana
    de retorno puede concluir después del periodo, pero no después de `ahora`.
    """
    consulta_atenciones = (
        RepositorioAgenda(sesion)
        .consulta_autorizada(principal)
        .where(Cita.estado == EstadoCita.COMPLETED.value)
    )
    consulta_atenciones = _aplicar_filtros(
        consulta_atenciones,
        sede_id=sede_id,
        profesional_id=profesional_id,
        especialidad_id=especialidad_id,
        servicio_id=servicio_id,
        estado=None,
    )
    atenciones = consulta_atenciones.subquery()
    primeras_en_periodo = (
        select(
            atenciones.c.paciente_id,
            func.min(atenciones.c.inicio).label("primera_en_periodo"),
        )
        .where(
            atenciones.c.paciente_id.is_not(None),
            atenciones.c.inicio >= filtro.desde,
            atenciones.c.inicio < filtro.hasta,
        )
        .group_by(atenciones.c.paciente_id)
        .subquery()
    )
    maduras = (
        select(
            primeras_en_periodo.c.paciente_id,
            primeras_en_periodo.c.primera_en_periodo,
        )
        .where(primeras_en_periodo.c.primera_en_periodo <= ahora - timedelta(days=30))
        .subquery()
    )
    pacientes_seguimiento_completo = int(
        (await sesion.execute(select(func.count()).select_from(maduras))).scalar_one()
    )
    if pacientes_seguimiento_completo < _MINIMO_GRUPO_DEMOGRAFICO:
        return None

    pacientes_que_regresaron = int(
        (
            await sesion.execute(
                select(func.count(func.distinct(maduras.c.paciente_id)))
                .select_from(
                    maduras.join(
                        atenciones,
                        atenciones.c.paciente_id == maduras.c.paciente_id,
                    )
                )
                .where(
                    atenciones.c.inicio > maduras.c.primera_en_periodo,
                    atenciones.c.inicio <= maduras.c.primera_en_periodo + timedelta(days=30),
                )
            )
        ).scalar_one()
    )
    return _retorno_30_dias_protegido(
        pacientes_seguimiento_completo,
        pacientes_que_regresaron,
    )


async def resumir(
    sesion: AsyncSession,
    principal: Principal,
    filtro: FiltroDashboard,
    sede_id: uuid.UUID | None = None,
    profesional_id: uuid.UUID | None = None,
    especialidad_id: uuid.UUID | None = None,
    servicio_id: uuid.UUID | None = None,
    estado: EstadoCita | None = None,
    *,
    ahora: datetime,
    incluir_metricas_pacientes: bool = True,
    # False omite la ocupación de agenda, que recorre cada día del periodo por
    # profesional: los análisis local y con IA no la usan.
    incluir_ocupacion: bool = True,
) -> ResumenDashboard:
    consulta = (
        RepositorioAgenda(sesion)
        .consulta_autorizada(principal)
        .where(Cita.inicio >= filtro.desde, Cita.inicio < filtro.hasta)
    )
    consulta = _aplicar_filtros(
        consulta,
        sede_id=sede_id,
        profesional_id=profesional_id,
        especialidad_id=especialidad_id,
        servicio_id=servicio_id,
        estado=estado,
    )
    citas = consulta.subquery()
    filas = await sesion.execute(select(citas.c.estado, func.count()).group_by(citas.c.estado))
    estados = {str(estado): int(cantidad) for estado, cantidad in filas}
    zona_local = func.coalesce(Sede.zona_horaria, Clinica.zona_horaria)
    inicio_local = func.timezone(zona_local, citas.c.inicio)
    agrupacion_local = (
        select(
            cast(inicio_local, DATE).label("fecha"),
            func.extract("hour", inicio_local).label("hora"),
            func.extract("dow", inicio_local).label("dia_postgres"),
            func.count().label("total"),
        )
        .select_from(citas)
        .join(Sede, Sede.id == citas.c.sede_id)
        .join(Clinica, Clinica.id == citas.c.clinica_id)
        .group_by(
            cast(inicio_local, DATE),
            func.extract("hour", inicio_local),
            func.extract("dow", inicio_local),
        )
        .subquery()
    )
    grupos_locales = await sesion.execute(
        select(
            agrupacion_local.c.fecha,
            agrupacion_local.c.hora,
            agrupacion_local.c.dia_postgres,
            agrupacion_local.c.total,
        )
    )
    tendencia: dict[date, int] = {}
    por_hora: dict[int, int] = {}
    por_dia: dict[int, int] = {}
    for fecha_local, hora, dia_postgres, total in grupos_locales:
        tendencia[fecha_local] = tendencia.get(fecha_local, 0) + int(total)
        hora_local = int(hora)
        dia_iso = ((int(dia_postgres) + 6) % 7) + 1
        por_hora[hora_local] = por_hora.get(hora_local, 0) + int(total)
        por_dia[dia_iso] = por_dia.get(dia_iso, 0) + int(total)
    pacientes = (
        await sesion.execute(select(func.count(func.distinct(citas.c.paciente_id))))
    ).scalar_one()
    pacientes_nuevos: int | None = None
    pacientes_recurrentes: int | None = None
    pacientes_registrados: int | None = None
    pacientes_registrados_sin_cita: int | None = None
    cohortes_registro: list[CohorteRegistroPacientes] | None = None
    if estado is None:
        consulta_atenciones = (
            RepositorioAgenda(sesion)
            .consulta_autorizada(principal)
            .where(Cita.estado == EstadoCita.COMPLETED.value)
        )
        consulta_atenciones = _aplicar_filtros(
            consulta_atenciones,
            sede_id=sede_id,
            profesional_id=profesional_id,
            especialidad_id=especialidad_id,
            servicio_id=servicio_id,
            estado=None,
        )
        atenciones = consulta_atenciones.subquery()
        primeras_atenciones = (
            select(atenciones.c.paciente_id, func.min(atenciones.c.inicio).label("primera"))
            .group_by(atenciones.c.paciente_id)
            .subquery()
        )
        pacientes_atendidos_en_periodo = (
            select(atenciones.c.paciente_id)
            .where(atenciones.c.inicio >= filtro.desde, atenciones.c.inicio < filtro.hasta)
            .distinct()
            .subquery()
        )
        conteo_pacientes = await sesion.execute(
            select(
                func.count().filter(primeras_atenciones.c.primera >= filtro.desde),
                func.count().filter(primeras_atenciones.c.primera < filtro.desde),
            ).select_from(
                primeras_atenciones.join(
                    pacientes_atendidos_en_periodo,
                    pacientes_atendidos_en_periodo.c.paciente_id
                    == primeras_atenciones.c.paciente_id,
                )
            )
        )
        pacientes_nuevos, pacientes_recurrentes = (int(valor) for valor in conteo_pacientes.one())
        (
            pacientes_registrados,
            pacientes_registrados_sin_cita,
            cohortes_registro,
        ) = await _resumir_cohortes_registro(
            sesion,
            principal,
            filtro,
            sede_id=sede_id,
            profesional_id=profesional_id,
            especialidad_id=especialidad_id,
            servicio_id=servicio_id,
        )
    adherencia: ResumenAdherencia | None = None
    if estado is None and principal.tiene_permiso("adherencia.leer"):
        adherencia = await _resumir_adherencia(
            sesion,
            principal,
            filtro,
            ahora,
            sede_id=sede_id,
            profesional_id=profesional_id,
            especialidad_id=especialidad_id,
            servicio_id=servicio_id,
        )
    consulta_esperas = (
        RepositorioAgenda(sesion)
        .consulta_autorizada(principal)
        .where(Cita.llegada_en >= filtro.desde, Cita.llegada_en < filtro.hasta)
    )
    consulta_esperas = _aplicar_filtros(
        consulta_esperas,
        sede_id=sede_id,
        profesional_id=profesional_id,
        especialidad_id=especialidad_id,
        servicio_id=servicio_id,
        estado=estado,
    )
    esperas = consulta_esperas.subquery()
    espera_minutos = func.floor(
        func.extract("epoch", esperas.c.atencion_iniciada_en - esperas.c.llegada_en) / 60
    )
    promedio_espera = (
        await sesion.execute(
            select(func.floor(func.avg(espera_minutos))).where(
                esperas.c.atencion_iniciada_en.is_not(None)
            )
        )
    ).scalar_one()
    en_espera = esperas.c.atencion_iniciada_en.is_(None)
    conteos_espera = await sesion.execute(
        select(
            func.count().filter(en_espera),
            func.count().filter(
                en_espera & (func.now() - esperas.c.llegada_en >= timedelta(minutes=15))
            ),
        )
    )
    personas_en_espera, espera_mayor_15 = conteos_espera.one()
    recuperacion: tuple[int | None, int | None, int | None] = (None, None, None)
    if estado is None:
        recuperacion = await _resumir_recuperacion_turnos(
            sesion,
            principal,
            filtro,
            sede_id=sede_id,
            profesional_id=profesional_id,
            especialidad_id=especialidad_id,
            servicio_id=servicio_id,
        )
    pagos = None
    # Ver indicadores de agenda no concede acceso a importes.
    if principal.tiene_permiso("pago.leer"):
        cobros = await sesion.execute(
            select(Pago.estado, func.sum(Pago.importe))
            .where(Pago.cita_id.in_(select(citas.c.id)), Pago.clinica_id == principal.clinica_id)
            .group_by(Pago.estado)
        )
        pagos = {str(estado): importe for estado, importe in cobros}
    return ResumenDashboard(
        desde=filtro.desde,
        hasta=filtro.hasta,
        citas=estados,
        total_citas=sum(estados.values()),
        pacientes=pacientes,
        pacientes_nuevos=pacientes_nuevos,
        pacientes_recurrentes=pacientes_recurrentes,
        pacientes_registrados=pacientes_registrados,
        pacientes_registrados_sin_cita=pacientes_registrados_sin_cita,
        cohortes_registro=cohortes_registro,
        demografia=(
            await _resumir_demografia(sesion, principal, filtro, citas)
            if incluir_metricas_pacientes
            else None
        ),
        retorno_30_dias=(
            await _resumir_retorno_30_dias(
                sesion,
                principal,
                filtro,
                ahora,
                sede_id=sede_id,
                profesional_id=profesional_id,
                especialidad_id=especialidad_id,
                servicio_id=servicio_id,
            )
            if estado is None and incluir_metricas_pacientes
            else None
        ),
        espera=ResumenEspera(
            promedio_minutos=int(promedio_espera) if promedio_espera is not None else None,
            personas_en_espera=int(personas_en_espera),
            espera_mayor_15_minutos=int(espera_mayor_15),
        ),
        recuperacion_turnos=ResumenRecuperacionTurnos(
            turnos_liberados=recuperacion[0],
            turnos_recuperados=recuperacion[1],
            promedio_minutos_para_recuperar=recuperacion[2],
        ),
        ocupacion_agenda=(
            await resumir_ocupacion_agenda(
                sesion,
                principal,
                filtro,
                sede_id=sede_id,
                profesional_id=profesional_id,
                especialidad_id=especialidad_id,
                servicio_id=servicio_id,
                estado=estado,
            )
            if incluir_ocupacion
            else ocupacion_no_calculada()
        ),
        adherencia=adherencia,
        pagos=pagos,
        tendencia_diaria=[
            ConteoCitasPorDia(fecha=fecha, total=total)
            for fecha, total in sorted(tendencia.items(), key=lambda par: par[0])
        ],
        por_hora=[
            ConteoCitasPorHora(hora=hora, total=total) for hora, total in sorted(por_hora.items())
        ],
        por_dia_semana=[
            ConteoCitasPorDiaSemana(dia=dia, total=total) for dia, total in sorted(por_dia.items())
        ],
    )
