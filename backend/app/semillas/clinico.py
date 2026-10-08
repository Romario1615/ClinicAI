"""Siembra historia clinica y recetas sinteticas para desarrollo.

Por que esto existe y por que hasta ahora no
--------------------------------------------
La base de desarrollo tenia 200 pacientes, 641 citas y **cero notas, cero
recetas y cero tomas**.  Una pantalla de historia clinica sobre esa base no se
puede verificar: muestra el estado vacio siempre, y el estado vacio es el unico
camino que se ejercita.  Es el mismo hallazgo que la base de conocimiento vacia
de la Fase 6.

Sobre la regla 3 de CLAUDE.md
-----------------------------
«Nunca inventar ... nombres de medicamentos aplicados a un paciente concreto ni
datos clinicos.»  Esa regla y la regla 1 —solo datos sinteticos en desarrollo—
se leen juntas y no se contradicen: lo prohibido es fabricar un hecho clinico
que pueda confundirse con uno real.

Se sigue la convencion que ya usan las pruebas de la Fase 7: los medicamentos
se llaman **«Medicamento de ejemplo A»**, nunca un farmaco real.  Ningun texto
de este modulo describe una condicion, un sintoma ni una indicacion que alguien
pudiera tomar por clinicamente cierta.  Los campos SOAP llevan texto que dice
explicitamente que es de demostracion.

Que se siembra, y por que cada cosa
-----------------------------------
No es volumen por volumen.  Cada caso existe para que un camino concreto de la
interfaz y del motor quede ejercitado:

* **Una nota con version corregida** — el versionado append-only es la garantia
  central de la historia clinica, y sin una nota corregida nadie ve nunca la
  version anterior ni el motivo del cambio.
* **Una receta confirmada con pauta fija** — es el unico camino que genera
  calendario de tomas.
* **Una receta con medicamento «cuando sea necesario»** — para que se vea que
  un PRN **no** produce horarios fijos, que es una garantia clinica con
  disparador propio.
* **Una receta en borrador** — una receta sin confirmar no genera nada, y quien
  la escribio necesita verla pendiente.
* **Una receta suspendida** — con su motivo, porque suspender conserva el
  historial en lugar de borrarlo.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.historia.modelos import NotaEvolucion, Receta, RecetaMedicamento
from app.modulos.historia.repositorio import RepositorioHistoria
from app.modulos.historia.servicios import (
    DatosMedicamento,
    DatosNota,
    ServicioHistoria,
)
from app.modulos.pacientes.modelos import Paciente, RelacionAsistencial
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Rol, Usuario, UsuarioRol
from app.nucleo.autorizacion import (
    Ambito,
    NivelSensibilidad,
    Principal,
    TipoActor,
)
from app.nucleo.reloj import Reloj, RelojFijo

# Marcador en todo texto libre. Si una de estas filas apareciera en una base
# real, se ve de un vistazo y se puede localizar con una sola consulta.
MARCA = "[SINTETICO]"

# Los nombres de medicamento NO son farmacos reales, y es deliberado
# (CLAUDE.md, regla 3). La misma convencion que usan las pruebas de la Fase 7.
MEDICAMENTO_A = "Medicamento de ejemplo A"
MEDICAMENTO_B = "Medicamento de ejemplo B"
MEDICAMENTO_PRN = "Medicamento de ejemplo C (cuando sea necesario)"
MEDICAMENTO_ADHERENCIA = "Medicamento de ejemplo para seguimiento [SINTETICO]"

# Los cuatro estados de receta que la interfaz tiene que saber mostrar. Se
# reparten en ciclo para no depender de cuantas parejas haya.
_CASOS_DE_RECETA = 4
_CASO_CONFIRMADA = 0
_CASO_PRN = 1
_CASO_BORRADOR = 2
# Una de cada tres notas se corrige, para que el versionado se vea en la interfaz.
_CADA_CUANTAS_CORRECCIONES = 3


@dataclass(frozen=True, slots=True)
class ResumenClinico:
    notas: int = 0
    correcciones: int = 0
    recetas: int = 0
    confirmadas: int = 0
    suspendidas: int = 0
    tomas: int = 0

    def describir(self) -> str:
        return (
            f"  Notas de evolucion: {self.notas} ({self.correcciones} con correccion)\n"
            f"  Recetas: {self.recetas} "
            f"({self.confirmadas} confirmadas, {self.suspendidas} suspendidas)\n"
            f"  Tomas programadas: {self.tomas}"
        )


def _principal_sembrador(clinica_id: uuid.UUID, profesional_id: uuid.UUID) -> Principal:
    """Principal con los permisos clinicos del profesional que firma.

    No es un superusuario: lleva exactamente los permisos que la operacion
    necesita y el `profesional_id`, que es lo que resuelve la relacion
    asistencial. Sembrar con un principal sin restricciones ocultaria que la
    relacion asistencial es obligatoria, y ese control se comprobaria solo en
    las pruebas y nunca en el uso real.
    """
    return Principal(
        actor_tipo=TipoActor.USUARIO,
        actor_id=profesional_id,
        clinica_id=clinica_id,
        permisos=frozenset(
            {
                "historia_clinica.leer",
                "historia_clinica.escribir",
                "receta.crear",
                "receta.confirmar",
                "receta.leer",
                "adherencia.leer",
            }
        ),
        ambito=Ambito(
            clinica_id=clinica_id,
            todas_las_sedes=True,
            todas_las_especialidades=True,
            todos_los_profesionales=True,
            todos_los_pacientes=True,
            nivel_maximo=NivelSensibilidad.CLINICO_SENSIBLE,
        ),
        profesional_id=profesional_id,
        origen="SEMILLA",
    )


async def cargar_clinico(
    sesion: AsyncSession,
    *,
    clinica_id: uuid.UUID,
    reloj: Reloj,
) -> ResumenClinico:
    """Siembra historia clinica sintetica en la clinica indicada.

    Trabaja **a traves de la capa de servicios**, no con inserciones directas.
    Es mas lento y es lo correcto: asi las filas sembradas pasan por las mismas
    validaciones, disparadores y reglas de negocio que las reales. Un sembrador
    que inserta a mano puede crear estados que el sistema jamas produciria, y
    entonces la interfaz se prueba contra datos imposibles.
    """
    if await _ya_sembrado(sesion, clinica_id):
        local = await _asegurar_historico_acceso_local(sesion, clinica_id=clinica_id, reloj=reloj)
        adherencia = await _sembrar_caso_adherencia(sesion, clinica_id=clinica_id, reloj=reloj)
        return _sumar(local, adherencia)

    parejas = await _parejas(sesion, clinica_id)
    if not parejas:
        return ResumenClinico()

    servicio = ServicioHistoria(sesion, RepositorioHistoria(sesion), reloj)
    resumen = ResumenClinico()

    for indice, (paciente_id, profesional_id) in enumerate(parejas):
        principal = _principal_sembrador(clinica_id, profesional_id)
        resumen = await _sembrar_pareja(
            servicio,
            principal=principal,
            paciente_id=paciente_id,
            profesional_id=profesional_id,
            indice=indice,
            resumen=resumen,
        )

    local = await _asegurar_historico_acceso_local(sesion, clinica_id=clinica_id, reloj=reloj)
    adherencia = await _sembrar_caso_adherencia(sesion, clinica_id=clinica_id, reloj=reloj)
    # Todo lo que esta llamada escribió entra en el resumen, también la receta
    # del caso de adherencia: el resumen es lo que se informa al terminar y lo
    # que las pruebas comparan con la base.
    return _sumar(resumen, local, adherencia)


async def _asegurar_historico_acceso_local(
    sesion: AsyncSession, *, clinica_id: uuid.UUID, reloj: Reloj
) -> ResumenClinico:
    """Hace visible una historia versionada al profesional del acceso local.

    Las relaciones de la clínica pueden pertenecer a varios profesionales;
    solo uno es el que resuelve el botón local de acceso. Sin un caso de prueba
    dentro de su ámbito, el resto de los datos clínicos puede existir y aun así
    la pantalla quedar vacía para E2E y revisión manual.
    """
    pareja = await _pareja_profesional_acceso_local(sesion, clinica_id)
    if pareja is None:
        return ResumenClinico()
    paciente_id, profesional_id = pareja
    anterior = await sesion.scalar(
        select(func.count())
        .select_from(NotaEvolucion)
        .where(
            NotaEvolucion.paciente_id == paciente_id,
            NotaEvolucion.profesional_id == profesional_id,
            NotaEvolucion.vigente.is_(False),
        )
    )
    if anterior:
        return ResumenClinico()

    principal = _principal_sembrador(clinica_id, profesional_id)
    servicio = ServicioHistoria(sesion, RepositorioHistoria(sesion), reloj)
    nota = await servicio.crear_nota(
        DatosNota(
            paciente_id=paciente_id,
            profesional_id=profesional_id,
            tipo="EVOLUCION",
            motivo_consulta=f"Control de rutina {MARCA}",
            subjetivo=f"Texto de demostración {MARCA}. No describe una condición real.",
            objetivo=f"Texto de demostración {MARCA}. Sin hallazgos clínicos reales.",
            analisis=f"Texto de demostración {MARCA}.",
            plan=f"Texto de demostración {MARCA}.",
        ),
        principal=principal,
    )
    if nota.nota is None:
        return ResumenClinico()
    await servicio.versionar_nota(
        nota.nota.raiz_id,
        datos=DatosNota(
            paciente_id=paciente_id,
            profesional_id=profesional_id,
            tipo="EVOLUCION",
            motivo_consulta=f"Control de rutina {MARCA}",
            subjetivo=f"Texto corregido de demostración {MARCA}.",
            objetivo=f"Texto corregido de demostración {MARCA}.",
            analisis=f"Texto corregido de demostración {MARCA}.",
            plan=f"Texto corregido de demostración {MARCA}.",
        ),
        principal=principal,
        motivo=f"Corrección de demostración {MARCA}: se completó el registro.",
    )
    return ResumenClinico(notas=1, correcciones=1)


async def _sembrar_caso_adherencia(
    sesion: AsyncSession, *, clinica_id: uuid.UUID, reloj: Reloj
) -> ResumenClinico:
    """Deja una pauta sintetica con tomas pasadas para ejercitar el aviso.

    La receta se crea dos dias antes mediante el servicio de dominio, no con
    fechas insertadas a mano. Solo existe en la base local de desarrollo y se
    identifica por un nombre que dice explicitamente que es sintética.

    Devuelve lo que escribió: la receta creada y confirmada, sus tomas y las
    recetas del caso que tuvo que suspender al reubicarlo.
    """
    pareja = await _pareja_profesional_acceso_local(sesion, clinica_id)
    if pareja is None:
        return ResumenClinico()
    paciente_id, profesional_id = pareja

    existentes = await sesion.execute(
        select(Receta)
        .join(RecetaMedicamento, RecetaMedicamento.receta_id == Receta.id)
        .where(
            Receta.clinica_id == clinica_id,
            RecetaMedicamento.nombre == MEDICAMENTO_ADHERENCIA,
        )
    )
    recetas_existentes = list(existentes.scalars().unique())
    if any(
        receta.paciente_id == paciente_id and receta.profesional_id == profesional_id
        for receta in recetas_existentes
    ):
        return ResumenClinico()

    reloj_historico = RelojFijo(reloj.ahora() - timedelta(days=2))
    servicio = ServicioHistoria(sesion, RepositorioHistoria(sesion), reloj_historico)
    # Si una version anterior del sembrador dejó el caso bajo otra pareja,
    # suspenderla por la capa de dominio antes de crear el caso en el ámbito
    # del profesional de acceso local. Se conserva toda la historia.
    suspendidas = 0
    for receta in recetas_existentes:
        if receta.estado != "CONFIRMADA":
            continue
        await servicio.suspender_receta(
            receta.id,
            principal=_principal_sembrador(clinica_id, receta.profesional_id),
            motivo=f"Reubicacion del escenario sintetico {MARCA}.",
        )
        suspendidas += 1
    principal = _principal_sembrador(clinica_id, profesional_id)
    creada = await servicio.crear_receta(
        principal=principal,
        paciente_id=paciente_id,
        profesional_id=profesional_id,
        medicamentos=[
            DatosMedicamento(
                nombre=MEDICAMENTO_ADHERENCIA,
                dosis="1 unidad",
                via="ORAL",
                frecuencia_horas=6,
                duracion_dias=1,
                instrucciones=f"Escenario sintetico de seguimiento {MARCA}.",
            )
        ],
        indicaciones_generales=f"Escenario sintetico de adherencia {MARCA}.",
    )
    if creada.receta is None:
        return ResumenClinico(suspendidas=suspendidas)
    confirmacion = await servicio.confirmar_receta(
        creada.receta.id, principal=principal, profesional_id=profesional_id
    )
    return ResumenClinico(
        recetas=1,
        confirmadas=1,
        suspendidas=suspendidas,
        tomas=confirmacion.tomas_generadas,
    )


async def _pareja_profesional_acceso_local(
    sesion: AsyncSession, clinica_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID] | None:
    """Pareja del mismo profesional que resuelve el botón local de acceso.

    El recorrido E2E usa la primera cuenta sintética del rol profesional por
    correo, igual que iniciar_sesion_rol_local. Elegir otra relación activa
    puede crear un caso clínico válido pero invisible para ese usuario.

    La cuenta se busca **dentro de la clínica sembrada**.  Buscarla en toda la
    base hacía que el caso dependiera de las demás clínicas: si la primera
    cuenta por correo era de otra, esta clínica se quedaba sin caso y el
    resultado de la siembra cambiaba según lo que hubiera cargado antes.  Con
    una sola clínica sintética, que es la base local habitual, la cuenta es la
    misma que resuelve el acceso local.
    """
    identidad = (
        await sesion.execute(
            select(Profesional.id)
            .join(Usuario, Usuario.id == Profesional.usuario_id)
            .join(UsuarioRol, UsuarioRol.usuario_id == Usuario.id)
            .join(Rol, Rol.id == UsuarioRol.rol_id)
            .where(
                Usuario.clinica_id == clinica_id,
                Profesional.clinica_id == clinica_id,
                Rol.codigo == "profesional",
                Rol.es_sistema.is_(True),
                Rol.clinica_id.is_(None),
                Usuario.activo.is_(True),
                Usuario.apellido.contains(MARCA),
                Profesional.activo.is_(True),
            )
            .order_by(Usuario.correo)
            .limit(1)
        )
    ).scalar_one_or_none()
    if identidad is None:
        return None

    relacion = (
        await sesion.execute(
            select(RelacionAsistencial.paciente_id)
            .join(Paciente, Paciente.id == RelacionAsistencial.paciente_id)
            .where(
                Paciente.clinica_id == clinica_id,
                Paciente.activo.is_(True),
                RelacionAsistencial.profesional_id == identidad,
                RelacionAsistencial.revocada_en.is_(None),
                RelacionAsistencial.vigente_hasta.is_(None),
            )
            .order_by(RelacionAsistencial.creado_en)
            .limit(1)
        )
    ).scalar_one_or_none()
    return (relacion, identidad) if relacion is not None else None


async def _sembrar_pareja(
    servicio: ServicioHistoria,
    *,
    principal: Principal,
    paciente_id: uuid.UUID,
    profesional_id: uuid.UUID,
    indice: int,
    resumen: ResumenClinico,
) -> ResumenClinico:
    """Siembra el caso que le toca a esta pareja paciente-profesional.

    Los casos se reparten en ciclo para que la base contenga los cuatro
    estados de receta y al menos una nota corregida, sin depender de cuantas
    parejas haya.
    """
    nota = await servicio.crear_nota(
        DatosNota(
            paciente_id=paciente_id,
            profesional_id=profesional_id,
            tipo="EVOLUCION",
            motivo_consulta=f"Control de rutina {MARCA}",
            subjetivo=(
                f"Texto de demostracion {MARCA}. Este campo contiene lo que refiere "
                "el paciente. No describe ninguna condicion real."
            ),
            objetivo=(
                f"Texto de demostracion {MARCA}. Aqui van los hallazgos de la "
                "exploracion. Sin contenido clinico real."
            ),
            analisis=f"Texto de demostracion {MARCA}. Valoracion del profesional.",
            plan=f"Texto de demostracion {MARCA}. Plan acordado con el paciente.",
        ),
        principal=principal,
    )
    resumen = _con(resumen, notas=resumen.notas + 1)

    # Una nota corregida: sin ella nadie ve nunca la version anterior ni el
    # motivo del cambio, que es la garantia central de la historia clinica.
    if indice % _CADA_CUANTAS_CORRECCIONES == 0 and nota.nota is not None:
        await servicio.versionar_nota(
            nota.nota.raiz_id,
            datos=DatosNota(
                paciente_id=paciente_id,
                profesional_id=profesional_id,
                tipo="EVOLUCION",
                motivo_consulta=f"Control de rutina {MARCA}",
                subjetivo=(
                    f"Texto de demostracion corregido {MARCA}. La version anterior "
                    "se conserva con su autor y su fecha."
                ),
                objetivo=f"Texto de demostracion corregido {MARCA}.",
                analisis=f"Texto de demostracion corregido {MARCA}.",
                plan=f"Texto de demostracion corregido {MARCA}.",
            ),
            principal=principal,
            motivo=f"Correccion de demostracion {MARCA}: se completo el registro.",
        )
        resumen = _con(resumen, correcciones=resumen.correcciones + 1)

    caso = indice % _CASOS_DE_RECETA
    if caso == _CASO_CONFIRMADA:
        return await _receta_confirmada(servicio, principal, paciente_id, profesional_id, resumen)
    if caso == _CASO_PRN:
        return await _receta_prn(servicio, principal, paciente_id, profesional_id, resumen)
    if caso == _CASO_BORRADOR:
        return await _receta_borrador(servicio, principal, paciente_id, profesional_id, resumen)
    return await _receta_suspendida(servicio, principal, paciente_id, profesional_id, resumen)


async def _receta_confirmada(
    servicio: ServicioHistoria,
    principal: Principal,
    paciente_id: uuid.UUID,
    profesional_id: uuid.UUID,
    resumen: ResumenClinico,
) -> ResumenClinico:
    """Pauta fija confirmada: el unico camino que genera calendario de tomas."""
    creada = await servicio.crear_receta(
        principal=principal,
        paciente_id=paciente_id,
        profesional_id=profesional_id,
        medicamentos=[
            DatosMedicamento(
                nombre=MEDICAMENTO_A,
                dosis="1 unidad",
                via="ORAL",
                frecuencia_horas=12,
                duracion_dias=7,
                instrucciones=f"Instruccion de demostracion {MARCA}.",
            ),
            DatosMedicamento(
                nombre=MEDICAMENTO_B,
                dosis="1 unidad",
                via="ORAL",
                frecuencia_horas=24,
                duracion_dias=5,
            ),
        ],
        indicaciones_generales=f"Indicaciones de demostracion {MARCA}.",
    )
    resumen = _con(resumen, recetas=resumen.recetas + 1)
    if creada.receta is None:
        return resumen

    confirmada = await servicio.confirmar_receta(
        creada.receta.id, principal=principal, profesional_id=profesional_id
    )
    return _con(
        resumen,
        confirmadas=resumen.confirmadas + 1,
        tomas=resumen.tomas + confirmada.tomas_generadas,
    )


async def _receta_prn(
    servicio: ServicioHistoria,
    principal: Principal,
    paciente_id: uuid.UUID,
    profesional_id: uuid.UUID,
    resumen: ResumenClinico,
) -> ResumenClinico:
    """«Cuando sea necesario»: confirmada y sin horarios fijos.

    Es una garantia clinica con disparador propio. Sin un caso sembrado, nadie
    ve en la interfaz la diferencia entre una pauta fija y una a demanda, que
    es justo la distincion que un error de medicacion borra.
    """
    creada = await servicio.crear_receta(
        principal=principal,
        paciente_id=paciente_id,
        profesional_id=profesional_id,
        medicamentos=[
            DatosMedicamento(
                nombre=MEDICAMENTO_PRN,
                dosis="1 unidad",
                via="ORAL",
                cuando_sea_necesario=True,
                instrucciones=f"Solo si lo necesita. Demostracion {MARCA}.",
            )
        ],
    )
    resumen = _con(resumen, recetas=resumen.recetas + 1)
    if creada.receta is None:
        return resumen

    confirmada = await servicio.confirmar_receta(
        creada.receta.id, principal=principal, profesional_id=profesional_id
    )
    return _con(
        resumen,
        confirmadas=resumen.confirmadas + 1,
        tomas=resumen.tomas + confirmada.tomas_generadas,
    )


async def _receta_borrador(
    servicio: ServicioHistoria,
    principal: Principal,
    paciente_id: uuid.UUID,
    profesional_id: uuid.UUID,
    resumen: ResumenClinico,
) -> ResumenClinico:
    """Sin confirmar: no genera nada, y quien la escribio necesita verla."""
    await servicio.crear_receta(
        principal=principal,
        paciente_id=paciente_id,
        profesional_id=profesional_id,
        medicamentos=[
            DatosMedicamento(
                nombre=MEDICAMENTO_A,
                dosis="1 unidad",
                via="ORAL",
                frecuencia_horas=8,
                duracion_dias=3,
            )
        ],
        indicaciones_generales=f"Pendiente de confirmar. Demostracion {MARCA}.",
    )
    return _con(resumen, recetas=resumen.recetas + 1)


async def _receta_suspendida(
    servicio: ServicioHistoria,
    principal: Principal,
    paciente_id: uuid.UUID,
    profesional_id: uuid.UUID,
    resumen: ResumenClinico,
) -> ResumenClinico:
    """Suspendida con motivo: el historial se conserva, no se borra."""
    creada = await servicio.crear_receta(
        principal=principal,
        paciente_id=paciente_id,
        profesional_id=profesional_id,
        medicamentos=[
            DatosMedicamento(
                nombre=MEDICAMENTO_B,
                dosis="1 unidad",
                via="ORAL",
                frecuencia_horas=24,
                duracion_dias=10,
            )
        ],
    )
    resumen = _con(resumen, recetas=resumen.recetas + 1)
    if creada.receta is None:
        return resumen

    confirmada = await servicio.confirmar_receta(
        creada.receta.id, principal=principal, profesional_id=profesional_id
    )
    resumen = _con(
        resumen,
        confirmadas=resumen.confirmadas + 1,
        tomas=resumen.tomas + confirmada.tomas_generadas,
    )
    await servicio.suspender_receta(
        creada.receta.id,
        principal=principal,
        motivo=f"Suspension de demostracion {MARCA}.",
    )
    return _con(resumen, suspendidas=resumen.suspendidas + 1)


# ---------------------------------------------------------------------------
#  Apoyo
# ---------------------------------------------------------------------------
async def _ya_sembrado(sesion: AsyncSession, clinica_id: uuid.UUID) -> bool:
    """Cierto si esta clinica ya tiene notas sembradas.

    Sembrar dos veces duplicaria historia clinica, y la historia clinica es
    append-only: lo duplicado no se puede limpiar borrandolo.
    """
    existentes = await sesion.scalar(
        select(func.count())
        .select_from(NotaEvolucion)
        .join(Paciente, Paciente.id == NotaEvolucion.paciente_id)
        .where(Paciente.clinica_id == clinica_id)
    )
    return bool(existentes)


async def _parejas(
    sesion: AsyncSession, clinica_id: uuid.UUID, limite: int = 12
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Parejas paciente-profesional con relacion asistencial ya establecida.

    No se inventan relaciones: se usan las que las semillas de agenda ya
    crearon. Fabricar una relacion asistencial para poder escribir una nota
    invertiria el control -- es la relacion la que autoriza la escritura, no al
    reves.
    """
    filas = (
        await sesion.execute(
            select(RelacionAsistencial.paciente_id, RelacionAsistencial.profesional_id)
            .join(Paciente, Paciente.id == RelacionAsistencial.paciente_id)
            .where(
                Paciente.clinica_id == clinica_id,
                Paciente.activo.is_(True),
                RelacionAsistencial.vigente_hasta.is_(None),
            )
            .order_by(RelacionAsistencial.creado_en)
            .limit(limite)
        )
    ).all()
    return [(fila[0], fila[1]) for fila in filas]


def _sumar(*resumenes: ResumenClinico) -> ResumenClinico:
    """Suma campo a campo lo que escribió cada paso de la siembra."""
    return ResumenClinico(
        notas=sum(r.notas for r in resumenes),
        correcciones=sum(r.correcciones for r in resumenes),
        recetas=sum(r.recetas for r in resumenes),
        confirmadas=sum(r.confirmadas for r in resumenes),
        suspendidas=sum(r.suspendidas for r in resumenes),
        tomas=sum(r.tomas for r in resumenes),
    )


def _con(resumen: ResumenClinico, **cambios: int) -> ResumenClinico:
    datos = {
        "notas": resumen.notas,
        "correcciones": resumen.correcciones,
        "recetas": resumen.recetas,
        "confirmadas": resumen.confirmadas,
        "suspendidas": resumen.suspendidas,
        "tomas": resumen.tomas,
        **cambios,
    }
    return ResumenClinico(**datos)


__all__ = [
    "MEDICAMENTO_A",
    "MEDICAMENTO_B",
    "MEDICAMENTO_PRN",
    "ResumenClinico",
    "cargar_clinico",
]
