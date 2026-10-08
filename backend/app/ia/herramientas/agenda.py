"""Las seis herramientas de agenda del agente.

Los nombres estan en ingles porque la especificacion los fija de forma
normativa (CLAUDE.md, seccion 2).  Todo lo demas -- mensajes, comentarios,
codigos de error -- va en espanol.

Lo que estas herramientas **no** hacen
--------------------------------------
No ejecutan SQL.  No abren transacciones.  No deciden si el solicitante tiene
permiso.  Llaman a `ServicioAgenda` con el principal que reciben y dejan que
la capa de servicios aplique permiso, ambito y las reglas de negocio.  Si una
de ellas empezara a consultar la base directamente, la prueba de arquitectura
de `pruebas/unitarias/test_arquitectura_agente.py` fallaria, y debe fallar:
seria una segunda via de acceso sin el filtro de ambito.

Una consecuencia practica: aqui no hay comprobaciones de seguridad duplicadas.
Duplicarlas parece prudente y no lo es -- crea dos sitios donde arreglar un
fallo y garantiza que alguien arregle solo uno.

Sobre el bloqueo temporal
-------------------------
`hold_slot` existe por como funciona una conversacion: entre que el paciente
ve una hora y responde «esa me viene bien» pasan minutos, y sin bloqueo otro
paciente puede quedarse el turno en ese hueco.  El bloqueo caduca solo; si el
paciente abandona la conversacion, el turno vuelve a estar libre sin que nadie
intervenga.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, ClassVar, TypeVar

from pydantic import BaseModel, Field, field_validator

from app.ia.herramientas.contrato import (
    ContextoHerramienta,
    Herramienta,
    ResultadoHerramienta,
)
from app.modulos.agenda.modelos import EstadoCita, OrigenCita
from app.modulos.agenda.repositorio import RepositorioAgenda
from app.modulos.agenda.servicios import ServicioAgenda, SolicitudReserva
from app.nucleo.configuracion import Configuracion
from app.nucleo.idempotencia import calcular_clave_deduplicacion

# Techo del rango que el agente puede consultar de una vez.  Es mas estrecho
# que el del panel: una conversacion propone horas concretas, y devolver tres
# meses de turnos produce una respuesta que nadie lee.
DIAS_MAXIMOS_CONSULTA_AGENTE = 14

# Cuantos turnos se le devuelven al modelo como maximo.  No es una limitacion
# tecnica: es que un mensaje de WhatsApp con cuarenta horas no ayuda a nadie.
TURNOS_MAXIMOS = 5

# El agente nunca cancela con menos margen que este sin pasar por una persona.
# La politica real la fija la clinica; este es el valor por defecto y se puede
# configurar.
HORAS_ANTELACION_CANCELACION = 24

T = TypeVar("T", bound=BaseModel)


def _servicio(contexto: ContextoHerramienta) -> ServicioAgenda:
    """Construye el servicio de agenda con la sesion del contexto.

    Se construye por invocacion en lugar de inyectarse para que la herramienta
    no pueda quedarse con una sesion de otra peticion, que es el tipo de fuga
    que en un canal conversacional mezclaria datos de dos pacientes.
    """
    configuracion = Configuracion()
    return ServicioAgenda(
        contexto.sesion,
        RepositorioAgenda(contexto.sesion),
        contexto.reloj,
        minutos_expiracion_held=configuracion.minutos_expiracion_held,
    )


def _exige_zona(valor: datetime) -> datetime:
    """Rechaza un instante sin zona horaria.

    Un `datetime` ingenuo procedente de un modelo de lenguaje es una fuente de
    error especialmente mala: el modelo no sabe en que zona esta la clinica y
    el sistema tampoco puede adivinarlo, asi que la cita acabaria desplazada
    unas horas sin que nadie lo note hasta que el paciente llegue.
    """
    if valor.tzinfo is None or valor.tzinfo.utcoffset(valor) is None:
        raise ValueError(
            "La fecha debe incluir zona horaria (por ejemplo 2026-04-16T09:00:00-05:00)."
        )
    return valor


# ---------------------------------------------------------------------------
#  find_availability
# ---------------------------------------------------------------------------
class ArgumentosDisponibilidad(BaseModel):
    """Argumentos de negocio. Ninguno identifica a quien pregunta."""

    profesional_id: uuid.UUID
    servicio_id: uuid.UUID
    sede_id: uuid.UUID
    desde: datetime
    hasta: datetime

    _zona_desde = field_validator("desde")(_exige_zona)
    _zona_hasta = field_validator("hasta")(_exige_zona)


class FindAvailability(Herramienta):
    nombre: ClassVar[str] = "find_availability"
    descripcion: ClassVar[str] = (
        "Consulta los turnos libres de un profesional para un servicio en una sede. "
        "Devuelve como maximo cinco horarios. No reserva nada."
    )
    argumentos: ClassVar[type[BaseModel]] = ArgumentosDisponibilidad
    permiso: ClassVar[str | None] = "agenda.leer"
    escribe: ClassVar[bool] = False

    async def ejecutar(
        self, argumentos: BaseModel, contexto: ContextoHerramienta
    ) -> ResultadoHerramienta:
        datos = _comprobar(argumentos, ArgumentosDisponibilidad)

        if datos.hasta <= datos.desde:
            return ResultadoHerramienta(
                exito=False,
                mensaje="El rango de fechas consultado no es valido.",
                codigo="RANGO_INVALIDO",
            )
        if (datos.hasta - datos.desde) > timedelta(days=DIAS_MAXIMOS_CONSULTA_AGENTE):
            return ResultadoHerramienta(
                exito=False,
                mensaje=(
                    f"Solo puedo consultar {DIAS_MAXIMOS_CONSULTA_AGENTE} dias seguidos. "
                    "Digame que semana le interesa."
                ),
                codigo="RANGO_DEMASIADO_AMPLIO",
            )

        repositorio = RepositorioAgenda(contexto.sesion)
        resultado = await _servicio(contexto).consultar_disponibilidad(
            principal=contexto.principal,
            profesional_id=datos.profesional_id,
            servicio_id=datos.servicio_id,
            sede_id=datos.sede_id,
            desde=datos.desde,
            hasta=datos.hasta,
        )
        # La zona de la sede, para que el agente pueda decir «las diez de la
        # manana» y no un instante con desplazamiento UTC.
        zona = await repositorio.obtener_zona_horaria(datos.sede_id)

        # Se ofrece `fin_consulta`, no `fin`. El intervalo reservado incluye la
        # preparacion, y decirle al paciente que su consulta de 30 minutos dura
        # 40 le hace calcular mal a que hora sale.
        turnos = [
            {
                "inicio": turno.inicio.isoformat(),
                "fin": turno.fin_consulta.isoformat(),
            }
            for turno in resultado.turnos[:TURNOS_MAXIMOS]
        ]
        if not turnos:
            return ResultadoHerramienta(
                exito=True,
                mensaje="No hay horarios libres en esas fechas.",
                datos={"turnos": [], "zona_horaria": zona},
                codigo="SIN_TURNOS",
            )

        return ResultadoHerramienta(
            exito=True,
            mensaje=f"Hay {len(turnos)} horarios disponibles.",
            datos={
                "turnos": turnos,
                "zona_horaria": zona,
                "hay_mas": len(resultado.turnos) > TURNOS_MAXIMOS,
            },
        )


# ---------------------------------------------------------------------------
#  hold_slot
# ---------------------------------------------------------------------------
class ArgumentosBloqueo(BaseModel):
    paciente_id: uuid.UUID
    profesional_id: uuid.UUID
    servicio_id: uuid.UUID
    sede_id: uuid.UUID
    inicio: datetime

    _zona_inicio = field_validator("inicio")(_exige_zona)


class HoldSlot(Herramienta):
    nombre: ClassVar[str] = "hold_slot"
    descripcion: ClassVar[str] = (
        "Reserva temporalmente un turno mientras el paciente decide. El bloqueo "
        "caduca solo; si el paciente no confirma, el turno vuelve a estar libre."
    )
    argumentos: ClassVar[type[BaseModel]] = ArgumentosBloqueo
    permiso: ClassVar[str | None] = "cita.crear"
    escribe: ClassVar[bool] = True

    async def ejecutar(
        self, argumentos: BaseModel, contexto: ContextoHerramienta
    ) -> ResultadoHerramienta:
        datos = _comprobar(argumentos, ArgumentosBloqueo)

        resultado = await _servicio(contexto).bloquear_turno(
            SolicitudReserva(
                paciente_id=datos.paciente_id,
                profesional_id=datos.profesional_id,
                servicio_id=datos.servicio_id,
                sede_id=datos.sede_id,
                inicio=datos.inicio,
                origen=OrigenCita.PANEL
                if contexto.principal.origen == "WEB" and not contexto.principal.es_agente
                else OrigenCita.WHATSAPP,
                clave_idempotencia=_clave(contexto, "hold", datos.inicio),
            ),
            principal=contexto.principal,
        )
        cita = resultado.cita
        return ResultadoHerramienta(
            exito=True,
            mensaje="He apartado ese horario. Confirmemelo para dejarlo en firme.",
            datos={
                "cita_id": str(cita.id),
                "inicio": cita.inicio.isoformat(),
                "expira_en": cita.expira_en.isoformat() if cita.expira_en else None,
            },
        )


# ---------------------------------------------------------------------------
#  confirm_appointment
# ---------------------------------------------------------------------------
class ArgumentosCita(BaseModel):
    cita_id: uuid.UUID


class ConfirmAppointment(Herramienta):
    nombre: ClassVar[str] = "confirm_appointment"
    descripcion: ClassVar[str] = "Confirma en firme una cita que estaba apartada o pendiente."
    argumentos: ClassVar[type[BaseModel]] = ArgumentosCita
    permiso: ClassVar[str | None] = "cita.crear"
    escribe: ClassVar[bool] = True

    async def ejecutar(
        self, argumentos: BaseModel, contexto: ContextoHerramienta
    ) -> ResultadoHerramienta:
        datos = _comprobar(argumentos, ArgumentosCita)
        resultado = await _servicio(contexto).confirmar_cita(
            datos.cita_id, principal=contexto.principal
        )
        return ResultadoHerramienta(
            exito=True,
            mensaje="Su cita queda confirmada.",
            datos={
                "cita_id": str(resultado.cita.id),
                "inicio": resultado.cita.inicio.isoformat(),
            },
        )


# ---------------------------------------------------------------------------
#  cancel_appointment
# ---------------------------------------------------------------------------
class ArgumentosCancelacion(BaseModel):
    cita_id: uuid.UUID
    # El motivo lo exige la base de datos. Se limita en longitud porque va a
    # una columna y porque un texto largo generado por un modelo no aporta.
    motivo: str = Field(min_length=1, max_length=280)

    @field_validator("motivo")
    @classmethod
    def _sin_vacio(cls, valor: str) -> str:
        limpio = valor.strip()
        if not limpio:
            raise ValueError("El motivo no puede estar vacio.")
        return limpio


class CancelAppointment(Herramienta):
    nombre: ClassVar[str] = "cancel_appointment"
    descripcion: ClassVar[str] = (
        "Cancela una cita. Exige motivo. No se puede cancelar con menos de "
        f"{HORAS_ANTELACION_CANCELACION} horas de antelacion sin pasar por una persona."
    )
    argumentos: ClassVar[type[BaseModel]] = ArgumentosCancelacion
    permiso: ClassVar[str | None] = "cita.cancelar"
    escribe: ClassVar[bool] = True

    async def ejecutar(
        self, argumentos: BaseModel, contexto: ContextoHerramienta
    ) -> ResultadoHerramienta:
        datos = _comprobar(argumentos, ArgumentosCancelacion)
        resultado = await _servicio(contexto).cancelar_cita(
            datos.cita_id,
            principal=contexto.principal,
            motivo=datos.motivo,
            horas_antelacion_minima=HORAS_ANTELACION_CANCELACION,
        )
        return ResultadoHerramienta(
            exito=True,
            mensaje="Su cita queda cancelada.",
            datos={"cita_id": str(resultado.cita.id)},
        )


# ---------------------------------------------------------------------------
#  reschedule_appointment
# ---------------------------------------------------------------------------
class ArgumentosReprogramacion(BaseModel):
    cita_id: uuid.UUID
    nuevo_inicio: datetime
    motivo: str = Field(min_length=1, max_length=280)

    _zona_nuevo = field_validator("nuevo_inicio")(_exige_zona)

    @field_validator("motivo")
    @classmethod
    def _sin_vacio(cls, valor: str) -> str:
        limpio = valor.strip()
        if not limpio:
            raise ValueError("El motivo no puede estar vacio.")
        return limpio


class RescheduleAppointment(Herramienta):
    nombre: ClassVar[str] = "reschedule_appointment"
    descripcion: ClassVar[str] = (
        "Mueve una cita a otro horario con el mismo profesional. Exige motivo."
    )
    argumentos: ClassVar[type[BaseModel]] = ArgumentosReprogramacion
    permiso: ClassVar[str | None] = "cita.reprogramar"
    escribe: ClassVar[bool] = True

    async def ejecutar(
        self, argumentos: BaseModel, contexto: ContextoHerramienta
    ) -> ResultadoHerramienta:
        datos = _comprobar(argumentos, ArgumentosReprogramacion)
        resultado = await _servicio(contexto).reprogramar_cita(
            datos.cita_id,
            principal=contexto.principal,
            nuevo_inicio=datos.nuevo_inicio,
            motivo=datos.motivo,
        )
        return ResultadoHerramienta(
            exito=True,
            mensaje="He movido su cita al nuevo horario.",
            datos={
                "cita_id": str(resultado.cita.id),
                "inicio": resultado.cita.inicio.isoformat(),
            },
        )


# ---------------------------------------------------------------------------
#  get_patient_appointments
# ---------------------------------------------------------------------------
class ArgumentosCitasPaciente(BaseModel):
    paciente_id: uuid.UUID
    # Solo futuras por defecto: el historico de citas de un paciente es
    # informacion que el agente no necesita para reservar y que un canal
    # conversacional no deberia volcar.
    incluir_pasadas: bool = False


class GetPatientAppointments(Herramienta):
    nombre: ClassVar[str] = "get_patient_appointments"
    descripcion: ClassVar[str] = (
        "Lista las citas futuras de un paciente: fecha, hora y estado. "
        "No devuelve motivo de consulta ni ningun dato clinico."
    )
    argumentos: ClassVar[type[BaseModel]] = ArgumentosCitasPaciente
    permiso: ClassVar[str | None] = "agenda.leer"
    escribe: ClassVar[bool] = False

    async def ejecutar(
        self, argumentos: BaseModel, contexto: ContextoHerramienta
    ) -> ResultadoHerramienta:
        datos = _comprobar(argumentos, ArgumentosCitasPaciente)

        repositorio = RepositorioAgenda(contexto.sesion)
        ahora = contexto.reloj.ahora()
        citas = await repositorio.listar_citas(
            principal=contexto.principal,
            paciente_id=datos.paciente_id,
            desde=None if datos.incluir_pasadas else ahora,
            estados=[
                EstadoCita.HELD.value,
                EstadoCita.PENDING.value,
                EstadoCita.CONFIRMED.value,
                EstadoCita.RESCHEDULED.value,
            ],
            limite=TURNOS_MAXIMOS,
        )

        # Solo lo imprescindible para hablar de una cita. Ni servicio ni notas:
        # el nombre de un servicio puede revelar la especialidad, y la
        # especialidad revela la condicion (CLAUDE.md, regla 10).
        listado = [
            {
                "cita_id": str(cita.id),
                "inicio": cita.inicio.isoformat(),
                "estado": cita.estado,
            }
            for cita in citas
        ]
        if not listado:
            return ResultadoHerramienta(
                exito=True,
                mensaje="No encuentro citas proximas a su nombre.",
                datos={"citas": []},
                codigo="SIN_CITAS",
            )
        return ResultadoHerramienta(
            exito=True,
            mensaje=f"Tiene {len(listado)} cita(s) proxima(s).",
            datos={"citas": listado},
        )


# ---------------------------------------------------------------------------
#  Apoyo
# ---------------------------------------------------------------------------
def _comprobar(argumentos: BaseModel, esperado: type[T]) -> T:
    """Confirma que los argumentos son del tipo que la herramienta declara.

    El despachador ya valida contra el esquema, asi que llegar aqui con otro
    tipo significa que alguien invoco la herramienta directamente saltandose
    el registro.  Fallar aqui lo hace visible en lugar de producir un
    `AttributeError` tres lineas mas abajo.
    """
    if not isinstance(argumentos, esperado):
        raise TypeError(
            f"Esta herramienta espera {esperado.__name__} y recibio "
            f"{type(argumentos).__name__}. Invoquela a traves del registro."
        )
    return argumentos


def _clave(contexto: ContextoHerramienta, accion: str, instante: datetime) -> str | None:
    """Clave de idempotencia derivada de la conversacion y el turno.

    Sin ella, un reintento del canal -- que en WhatsApp ocurre -- crearia dos
    bloqueos sobre el mismo turno para el mismo paciente.  Se deriva de datos
    estables en lugar de generarse al azar precisamente para que el reintento
    produzca la misma clave.

    Se pasa por el derivador con hash en lugar de concatenar el texto: la
    marca de tiempo en ISO contiene el `+` del desplazamiento horario, y el
    alfabeto que admite `validar_clave_cliente` no lo incluye. El hash da una
    clave del alfabeto correcto y de longitud fija.
    """
    if contexto.conversacion_id is None:
        return None
    return calcular_clave_deduplicacion(
        "agente", accion, str(contexto.conversacion_id), instante.isoformat()
    )


HERRAMIENTAS_AGENDA: tuple[Herramienta, ...] = (
    FindAvailability(),
    HoldSlot(),
    ConfirmAppointment(),
    CancelAppointment(),
    RescheduleAppointment(),
    GetPatientAppointments(),
)


def describir_catalogo() -> list[dict[str, Any]]:
    """Catalogo en la forma que espera un proveedor de herramientas."""
    return [
        {
            "name": h.nombre,
            "description": h.descripcion,
            "input_schema": h.argumentos.model_json_schema(),
        }
        for h in HERRAMIENTAS_AGENDA
    ]
