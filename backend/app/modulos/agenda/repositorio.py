"""Acceso a datos de la agenda.

Reglas de esta capa, que no se negocian:

* **Nunca hace `commit`.**  El limite transaccional lo decide el servicio.  Es
  lo que permite que el cambio de estado de una cita y su entrada en el outbox
  se confirmen juntos o no se confirmen (ADR-0008).
* **Aplica el filtro de ambito.**  El permiso lo comprueba la ruta; el filtro
  de filas se aplica aqui.  Comprobar solo el permiso es el error que
  convierte un sistema con roles en un sistema sin control de acceso real.
* **Nunca compone SQL por concatenacion.**  Todo va con parametros enlazados.

Sobre el filtro de ambito
-------------------------
Los metodos de lectura exigen un `Principal` y no admiten omitirlo.  Si fuera
opcional, un olvido produciria una consulta sin filtro que devuelve datos de
toda la clinica, y el fallo no se notaria en desarrollo -- donde suele haber
una sola sede -- sino en produccion.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Select, and_, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.disponibilidad import (
    DescansoLocal,
    FeriadoLocal,
    FranjaLocal,
    Intervalo,
    MotivoNoDisponible,
    Ocupacion,
)
from app.modulos.agenda.modelos import (
    _ESTADOS_QUE_OCUPAN,
    BloqueoAgenda,
    Cita,
)
from app.modulos.organizacion.modelos import (
    Clinica,
    Consultorio,
    Descanso,
    Feriado,
    HorarioAtencion,
    Sede,
    Servicio,
)
from app.modulos.profesionales.modelos import AgendaPlantilla, Profesional
from app.nucleo.autorizacion import Principal

_ESTADOS_OCUPADOS_SQL = tuple(e.value for e in _ESTADOS_QUE_OCUPAN)


# Identificador que no puede existir. Fuerza un resultado vacio de forma
# explicita, que es mas seguro que devolver la consulta sin filtrar.
_NINGUNO = uuid.UUID(int=0)


class RepositorioAgenda:
    """Consultas de la agenda, con filtro de ambito obligatorio."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    # ------------------------------------------------------------------
    #  Filtro de ambito
    # ------------------------------------------------------------------
    def _filtrar_por_ambito(self, consulta: Select[Any], principal: Principal) -> Select[Any]:
        """Anade las condiciones de ambito a una consulta sobre `cita`.

        El orden de las condiciones importa poco para el planificador, pero la
        de clinica va primera porque es la que mas filas descarta y la que
        nunca debe faltar: sin ella, una consulta podria cruzar clinicas.

        Las cuatro dimensiones se aplican con la MISMA regla
        ----------------------------------------------------
        Sin comodin y con la lista vacia, el resultado es vacio. No "sin
        restriccion".

        Conviene insistir porque la version anterior de este metodo no lo
        hacia: escribia `if not ambito.todos_los_profesionales and
        ambito.profesionales`, de modo que un ambito de profesional **vacio**
        no filtraba nada y el principal veia las citas de todos. La condicion
        parecia defensiva y era justo lo contrario. Lo mismo con pacientes.

        La dimension de especialidad faltaba por completo: un profesional de
        una especialidad veia las citas de todas las demas.
        """
        if principal.clinica_id is None:
            # Sin clinica no hay nada que ver.  Devolver una consulta que no
            # coincide con ninguna fila es mas seguro que devolver todo.
            return consulta.where(Cita.clinica_id == uuid.UUID(int=0))

        consulta = consulta.where(Cita.clinica_id == principal.clinica_id)

        ambito = principal.ambito
        if not ambito.todas_las_sedes:
            if not ambito.sedes:
                return consulta.where(Cita.sede_id == _NINGUNO)
            consulta = consulta.where(Cita.sede_id.in_(ambito.sedes))

        if not ambito.todos_los_profesionales:
            if not ambito.profesionales:
                return consulta.where(Cita.profesional_id == _NINGUNO)
            consulta = consulta.where(Cita.profesional_id.in_(ambito.profesionales))

        if not ambito.todos_los_pacientes:
            if not ambito.pacientes:
                return consulta.where(Cita.paciente_id == _NINGUNO)
            consulta = consulta.where(Cita.paciente_id.in_(ambito.pacientes))

        if not ambito.todas_las_especialidades:
            if not ambito.especialidades:
                return consulta.where(Cita.servicio_id == _NINGUNO)
            # `Cita` no lleva `especialidad_id`: la especialidad vive en
            # `servicio`. Se usa EXISTS y no una union porque la union
            # arrastraria las columnas de `servicio` a una consulta que solo
            # necesita filtrar, y con `DISTINCT` de por medio cambiaria el
            # plan del ordenamiento por `inicio`.
            consulta = consulta.where(
                select(literal(1))
                .select_from(Servicio)
                .where(
                    Servicio.id == Cita.servicio_id,
                    Servicio.especialidad_id.in_(ambito.especialidades),
                )
                .exists()
            )

        return consulta

    # ------------------------------------------------------------------
    #  Lecturas de citas
    # ------------------------------------------------------------------
    def consulta_autorizada(self, principal: Principal) -> Select[Any]:
        """Base compartida por informes y pagos: conserva las cuatro dimensiones."""
        return self._filtrar_por_ambito(select(Cita), principal)

    async def obtener_cita(self, cita_id: uuid.UUID, *, principal: Principal) -> Cita | None:
        """Devuelve una cita si cae dentro del ambito del principal.

        Devuelve `None` tanto si no existe como si existe fuera del ambito.
        La ruta traduce ambos casos a 404: un 403 confirmaria que el
        identificador existe y permitiria enumerar pacientes probando
        identificadores (proteccion contra IDOR).
        """
        consulta = self._filtrar_por_ambito(select(Cita).where(Cita.id == cita_id), principal)
        return (await self._sesion.execute(consulta)).scalar_one_or_none()

    async def obtener_cita_para_actualizar(
        self, cita_id: uuid.UUID, *, principal: Principal
    ) -> Cita | None:
        """Igual que `obtener_cita`, pero bloqueando la fila.

        `FOR UPDATE` serializa las modificaciones concurrentes sobre la misma
        cita: dos operaciones simultaneas de cancelar y reprogramar no pueden
        leer el mismo estado y decidir cada una por su cuenta.

        Sin el bloqueo, ambas verian `CONFIRMED`, ambas considerarian valida su
        transicion y la ultima en escribir ganaria, perdiendo el efecto de la
        otra sin dejar rastro del conflicto.
        """
        consulta = self._filtrar_por_ambito(
            select(Cita).where(Cita.id == cita_id), principal
        ).with_for_update()
        return (await self._sesion.execute(consulta)).scalar_one_or_none()

    async def buscar_por_clave_idempotencia(
        self, clave: str, *, clinica_id: uuid.UUID
    ) -> Cita | None:
        """Busca una cita creada con una clave de idempotencia concreta.

        No usa el filtro de ambito: se invoca antes de crear, para detectar un
        reintento del mismo cliente, y la clinica ya viene del contexto de la
        peticion.
        """
        consulta = select(Cita).where(
            Cita.clinica_id == clinica_id,
            Cita.clave_idempotencia == clave,
        )
        return (await self._sesion.execute(consulta)).scalar_one_or_none()

    async def listar_citas(
        self,
        *,
        principal: Principal,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        profesional_id: uuid.UUID | None = None,
        paciente_id: uuid.UUID | None = None,
        sede_id: uuid.UUID | None = None,
        estados: Sequence[str] | None = None,
        limite: int = 100,
        desplazamiento: int = 0,
    ) -> list[Cita]:
        """Lista citas con filtros, siempre dentro del ambito.

        `limite` tiene un techo duro: una consulta sin limite sobre la agenda
        de una clinica con anos de historico devolveria decenas de miles de
        filas y agotaria la memoria del proceso.
        """
        limite = max(1, min(limite, 500))

        consulta = select(Cita)
        if desde is not None:
            consulta = consulta.where(Cita.inicio >= desde)
        if hasta is not None:
            consulta = consulta.where(Cita.inicio < hasta)
        if profesional_id is not None:
            consulta = consulta.where(Cita.profesional_id == profesional_id)
        if paciente_id is not None:
            consulta = consulta.where(Cita.paciente_id == paciente_id)
        if sede_id is not None:
            consulta = consulta.where(Cita.sede_id == sede_id)
        if estados:
            consulta = consulta.where(Cita.estado.in_(estados))

        consulta = self._filtrar_por_ambito(consulta, principal)
        consulta = consulta.order_by(Cita.inicio).limit(limite).offset(desplazamiento)

        return list((await self._sesion.execute(consulta)).scalars())

    async def contar_citas(
        self,
        *,
        principal: Principal,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        profesional_id: uuid.UUID | None = None,
        paciente_id: uuid.UUID | None = None,
        sede_id: uuid.UUID | None = None,
        estados: Sequence[str] | None = None,
    ) -> int:
        """Cuenta las citas que `listar_citas` devolveria con esos mismos filtros.

        Acepta exactamente los mismos filtros que `listar_citas`, y no un
        subconjunto. Con un subconjunto, un listado paginado de las citas de
        un profesional mostraria como total el de toda la clinica: el usuario
        veria "1 de 340" en una pagina con tres filas y la paginacion pediria
        paginas que siempre vuelven vacias.
        """
        consulta = select(func.count()).select_from(Cita)
        if desde is not None:
            consulta = consulta.where(Cita.inicio >= desde)
        if hasta is not None:
            consulta = consulta.where(Cita.inicio < hasta)
        if profesional_id is not None:
            consulta = consulta.where(Cita.profesional_id == profesional_id)
        if paciente_id is not None:
            consulta = consulta.where(Cita.paciente_id == paciente_id)
        if sede_id is not None:
            consulta = consulta.where(Cita.sede_id == sede_id)
        if estados:
            consulta = consulta.where(Cita.estado.in_(estados))
        consulta = self._filtrar_por_ambito(consulta, principal)
        return int((await self._sesion.execute(consulta)).scalar_one())

    # ------------------------------------------------------------------
    #  Datos para el calculo de disponibilidad
    # ------------------------------------------------------------------
    async def obtener_zona_horaria(self, sede_id: uuid.UUID) -> str:
        """Zona horaria efectiva de una sede.

        La de la sede si la tiene, y si no la de la clinica.  Permite sedes en
        husos distintos sin obligar a repetir el valor en la sede habitual.
        """
        consulta = (
            select(func.coalesce(Sede.zona_horaria, Clinica.zona_horaria))
            .join(Clinica, Clinica.id == Sede.clinica_id)
            .where(Sede.id == sede_id)
        )
        zona = (await self._sesion.execute(consulta)).scalar_one_or_none()
        if zona is None:
            raise ValueError(f"La sede {sede_id} no existe.")
        return str(zona)

    async def obtener_franjas_profesional(
        self, profesional_id: uuid.UUID, sede_id: uuid.UUID
    ) -> list[FranjaLocal]:
        """Franjas de trabajo del profesional en una sede.

        Si el profesional no tiene plantilla propia, se usan los horarios de
        atencion de la sede.  Asi un profesional nuevo puede agendarse desde el
        primer dia sin tener que configurarle un horario, y la clinica decide
        si quiere granularidad por persona.
        """
        consulta = select(AgendaPlantilla).where(
            AgendaPlantilla.profesional_id == profesional_id,
            AgendaPlantilla.sede_id == sede_id,
        )
        plantillas = list((await self._sesion.execute(consulta)).scalars())

        if plantillas:
            return [
                FranjaLocal(
                    dia_semana=p.dia_semana,
                    hora_inicio=_a_hora(p.hora_inicio),
                    hora_fin=_a_hora(p.hora_fin),
                    granularidad_minutos=p.granularidad_minutos,
                    vigente_desde=_a_fecha(p.vigente_desde),
                    vigente_hasta=_a_fecha(p.vigente_hasta),
                )
                for p in plantillas
            ]

        return await self.obtener_franjas_sede(sede_id)

    async def obtener_franjas_sede(self, sede_id: uuid.UUID) -> list[FranjaLocal]:
        consulta = select(HorarioAtencion).where(
            HorarioAtencion.propietario_tipo == "SEDE",
            HorarioAtencion.propietario_id == sede_id,
        )
        horarios = list((await self._sesion.execute(consulta)).scalars())
        return [
            FranjaLocal(
                dia_semana=h.dia_semana,
                hora_inicio=h.hora_inicio,
                hora_fin=h.hora_fin,
                granularidad_minutos=h.granularidad_minutos,
                vigente_desde=h.vigente_desde,
                vigente_hasta=h.vigente_hasta,
            )
            for h in horarios
        ]

    async def obtener_descansos_sede(self, sede_id: uuid.UUID) -> list[DescansoLocal]:
        consulta = (
            select(Descanso, HorarioAtencion.dia_semana)
            .join(HorarioAtencion, HorarioAtencion.id == Descanso.horario_atencion_id)
            .where(
                HorarioAtencion.propietario_tipo == "SEDE",
                HorarioAtencion.propietario_id == sede_id,
            )
        )
        filas = (await self._sesion.execute(consulta)).all()
        return [
            DescansoLocal(
                dia_semana=dia_semana,
                hora_inicio=descanso.hora_inicio,
                hora_fin=descanso.hora_fin,
                motivo=descanso.motivo,
            )
            for descanso, dia_semana in filas
        ]

    async def obtener_feriados(
        self, clinica_id: uuid.UUID, sede_id: uuid.UUID, *, desde: date, hasta: date
    ) -> list[FeriadoLocal]:
        """Feriados aplicables a una sede en un rango de fechas.

        Incluye los de la clinica (`sede_id` nulo) y los propios de la sede.
        Los recurrentes anuales se devuelven siempre, sin filtrar por fecha:
        su ano de creacion es irrelevante y filtrarlo los excluiria.
        """
        consulta = select(Feriado).where(
            Feriado.clinica_id == clinica_id,
            or_(Feriado.sede_id.is_(None), Feriado.sede_id == sede_id),
            or_(
                Feriado.recurrente_anual.is_(True),
                and_(Feriado.fecha >= desde, Feriado.fecha <= hasta),
            ),
        )
        feriados = list((await self._sesion.execute(consulta)).scalars())
        return [
            FeriadoLocal(
                fecha=f.fecha,
                nombre=f.nombre,
                recurrente_anual=f.recurrente_anual,
                hora_inicio=f.hora_inicio,
                hora_fin=f.hora_fin,
            )
            for f in feriados
        ]

    async def obtener_ocupaciones(
        self,
        *,
        profesional_id: uuid.UUID,
        sede_id: uuid.UUID,
        desde: datetime,
        hasta: datetime,
        consultorio_id: uuid.UUID | None = None,
        excluir_cita_id: uuid.UUID | None = None,
    ) -> list[Ocupacion]:
        """Citas y bloqueos que ocupan tiempo en el rango.

        `excluir_cita_id` sirve al reagendamiento: al mover una cita, su propio
        horario actual no debe contar como ocupado, o el sistema diria que no
        hay hueco para la cita que ya esta ahi.

        Las citas se leen con su columna `rango`, que ya incluye el tiempo de
        preparacion.  Leer `inicio` y sumar la duracion en Python duplicaria la
        logica del disparador y podria divergir de ella.
        """
        ocupaciones: list[Ocupacion] = []

        # --- Citas del profesional ---
        consulta_citas = select(Cita).where(
            Cita.profesional_id == profesional_id,
            Cita.estado.in_(_ESTADOS_OCUPADOS_SQL),
            Cita.inicio < hasta,
            Cita.fin > desde,
        )
        if excluir_cita_id is not None:
            consulta_citas = consulta_citas.where(Cita.id != excluir_cita_id)

        for cita in (await self._sesion.execute(consulta_citas)).scalars():
            ocupaciones.append(
                Ocupacion(
                    Intervalo(cita.inicio, cita.fin),
                    MotivoNoDisponible.CITA_EXISTENTE,
                    referencia_id=cita.id,
                )
            )

        # --- Citas del consultorio, si se pidio uno concreto ---
        if consultorio_id is not None:
            consulta_sala = select(Cita).where(
                Cita.consultorio_id == consultorio_id,
                Cita.profesional_id != profesional_id,
                Cita.estado.in_(_ESTADOS_OCUPADOS_SQL),
                Cita.inicio < hasta,
                Cita.fin > desde,
            )
            if excluir_cita_id is not None:
                consulta_sala = consulta_sala.where(Cita.id != excluir_cita_id)
            for cita in (await self._sesion.execute(consulta_sala)).scalars():
                ocupaciones.append(
                    Ocupacion(
                        Intervalo(cita.inicio, cita.fin),
                        MotivoNoDisponible.CITA_EXISTENTE,
                        referencia_id=cita.id,
                        detalle="Consultorio ocupado",
                    )
                )

        # --- Bloqueos ---
        #
        # Se incluyen los del profesional, los de la sede completa y los del
        # consultorio.  Un bloqueo de sede (mantenimiento, corte de luz) afecta
        # a todos los profesionales que atienden ahi.
        condiciones_bloqueo = [BloqueoAgenda.profesional_id == profesional_id]
        condiciones_bloqueo.append(
            and_(BloqueoAgenda.profesional_id.is_(None), BloqueoAgenda.sede_id == sede_id)
        )
        if consultorio_id is not None:
            condiciones_bloqueo.append(BloqueoAgenda.consultorio_id == consultorio_id)

        consulta_bloqueos = select(BloqueoAgenda).where(
            or_(*condiciones_bloqueo),
            BloqueoAgenda.inicio < hasta,
            BloqueoAgenda.fin > desde,
        )
        for bloqueo in (await self._sesion.execute(consulta_bloqueos)).scalars():
            ocupaciones.append(
                Ocupacion(
                    Intervalo(bloqueo.inicio, bloqueo.fin),
                    MotivoNoDisponible.BLOQUEO,
                    referencia_id=bloqueo.id,
                    detalle=bloqueo.motivo or bloqueo.tipo,
                )
            )

        return ocupaciones

    async def obtener_servicio(self, servicio_id: uuid.UUID) -> Servicio | None:
        return (
            await self._sesion.execute(select(Servicio).where(Servicio.id == servicio_id))
        ).scalar_one_or_none()

    async def obtener_profesional(self, profesional_id: uuid.UUID) -> Profesional | None:
        return (
            await self._sesion.execute(select(Profesional).where(Profesional.id == profesional_id))
        ).scalar_one_or_none()

    async def obtener_sede(self, sede_id: uuid.UUID) -> Sede | None:
        return (
            await self._sesion.execute(select(Sede).where(Sede.id == sede_id))
        ).scalar_one_or_none()

    async def obtener_consultorio(self, consultorio_id: uuid.UUID) -> Consultorio | None:
        return (
            await self._sesion.execute(select(Consultorio).where(Consultorio.id == consultorio_id))
        ).scalar_one_or_none()

    # ------------------------------------------------------------------
    #  Bloqueos temporales vencidos
    # ------------------------------------------------------------------
    async def listar_bloqueos_vencidos(self, *, ahora: datetime, limite: int = 200) -> list[Cita]:
        """Citas en `HELD` cuyo plazo ya paso.

        Las procesa el barrido del worker.  Se limita el lote para que un
        atasco acumulado no produzca una transaccion enorme que bloquee la
        tabla durante minutos.
        """
        consulta = (
            select(Cita)
            .where(Cita.estado == "HELD", Cita.expira_en <= ahora)
            .order_by(Cita.expira_en)
            .limit(limite)
            .with_for_update(skip_locked=True)
        )
        return list((await self._sesion.execute(consulta)).scalars())


# ---------------------------------------------------------------------------
#  Conversiones
# ---------------------------------------------------------------------------
# `AgendaPlantilla` guarda las horas como texto porque su migracion las
# declaro asi.  Estas funciones aislan esa peculiaridad para que el resto del
# codigo trabaje siempre con `time` y `date`.
def _a_hora(valor: object) -> time:
    if isinstance(valor, time):
        return valor
    partes = str(valor).split(":")
    return time(int(partes[0]), int(partes[1]) if len(partes) > 1 else 0)


def _a_fecha(valor: object) -> date | None:
    if valor is None:
        return None
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor))


def rango_de_dias(desde: datetime, hasta: datetime, zona: str) -> tuple[date, date]:
    """Fechas locales que cubre un rango de instantes.

    Se amplia un dia por cada extremo: un dia local puede empezar antes o
    acabar despues del rango en UTC.  Sin la holgura, la consulta de feriados
    perderia el del primer o del ultimo dia.
    """
    tz = ZoneInfo(zona)
    return (
        desde.astimezone(tz).date() - timedelta(days=1),
        hasta.astimezone(tz).date() + timedelta(days=1),
    )
