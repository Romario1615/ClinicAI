"""Especialidad desde la que se revisa una historia clínica.

Para qué sirve
--------------
Una clínica atiende varias especialidades y cada una usa partes distintas de
la historia: el odontólogo trabaja con odontograma, periodoncia y planes; la
dermatóloga no. Cuando el odontólogo abre la historia no debe activarse lo de
dermatología ni ver sus notas.

Qué se comparte y qué no
------------------------
* **Notas de evolución**: se ven solo las escritas por profesionales de la
  especialidad desde la que se revisa. La especialidad de una nota es la de
  su autor, que no cambia: no hace falta una columna nueva.
* **Datos de seguridad** (alergias, medicamentos y recetas vigentes): se
  comparten entre especialidades. Ocultar una alergia porque la registró
  otra área es un riesgo clínico, no una protección.
* **Módulos** (odontograma, periodoncia, planes, imágenes): cada especialidad
  tiene los suyos. Los configura administración desde Catálogo y el backend
  los niega a quien no revisa desde una especialidad que los tenga.

Desde qué especialidades revisa cada persona
--------------------------------------------
* Un profesional, desde la suya y desde las que se le asignaron
  **explícitamente** en su ámbito. El comodín «todas las especialidades» no
  le abre las ajenas: es la forma habitual de crear roles y concedería, sin
  querer, ver la historia de cualquier área.
* El resto del personal clínico (dirección médica, auditoría), desde las que
  cubre su ámbito.

La configuración de módulos se guarda en `configuracion_clinica` con la clave
``modulos_historia`` y el mismo versionado que el resto: cambiarla deja la
versión anterior.
"""

from __future__ import annotations

import unicodedata
import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.organizacion.modelos import ConfiguracionClinica, Especialidad
from app.modulos.profesionales.modelos import Profesional
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import Auditor, RelojActual, Sesion, exige_permiso
from app.nucleo.errores import DatosInvalidos, PermisoDenegado, RecursoNoEncontrado

CLAVE = "modulos_historia"

Modulo = Literal["odontograma", "periodoncia", "planes", "imagenes", "faciograma"]
MODULOS: dict[str, tuple[str, str]] = {
    "faciograma": ("Faciograma", "Mapa facial con observaciones, zonas y seguimiento de estética."),
    "odontograma": ("Odontograma", "Estado por pieza y superficie, con historial por diente."),
    "periodoncia": ("Periodoncia · placa", "Índice de placa y controles periodontales."),
    "planes": ("Planes de tratamiento", "Presupuesto por fases y seguimiento del tratamiento."),
    "imagenes": ("Imágenes y radiografías", "Fotos clínicas, antes y después, y radiografías."),
}
DENTALES: tuple[str, ...] = ("odontograma", "periodoncia", "planes", "imagenes")
GENERALES: tuple[str, ...] = ("imagenes",)


def _sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c)).lower()


def modulos_por_omision(especialidad: Especialidad) -> tuple[str, ...]:
    """Módulos iniciales dentales, faciales para estética/dermatología y generales."""
    codigo = (especialidad.codigo or "").upper()
    if codigo.startswith("ODO") or "odont" in _sin_tildes(especialidad.nombre):
        return DENTALES
    if codigo.startswith(("EST", "DERM", "PLA")) or any(
        p in _sin_tildes(especialidad.nombre) for p in ("estetic", "dermat", "plastica")
    ):
        return ("faciograma", "imagenes")
    return GENERALES


async def _vigente(sesion: AsyncSession, clinica_id: uuid.UUID) -> ConfiguracionClinica | None:
    return (
        await sesion.execute(
            select(ConfiguracionClinica).where(
                ConfiguracionClinica.clinica_id == clinica_id,
                ConfiguracionClinica.clave == CLAVE,
                ConfiguracionClinica.vigente.is_(True),
            )
        )
    ).scalar_one_or_none()


async def _especialidades_de_clinica(
    sesion: AsyncSession, clinica_id: uuid.UUID
) -> list[Especialidad]:
    return list(
        (
            await sesion.execute(
                select(Especialidad)
                .where(Especialidad.clinica_id == clinica_id)
                .order_by(Especialidad.nombre)
            )
        ).scalars()
    )


async def modulos_de_clinica(
    sesion: AsyncSession, clinica_id: uuid.UUID
) -> list[tuple[Especialidad, tuple[str, ...]]]:
    """Cada especialidad de la clínica con sus módulos de historia."""
    fila = await _vigente(sesion, clinica_id)
    guardado = dict(fila.valor) if fila else {}
    resultado = []
    for especialidad in await _especialidades_de_clinica(sesion, clinica_id):
        valor = guardado.get(str(especialidad.id))
        modulos = (
            tuple(m for m in valor if isinstance(m, str) and m in modulos_por_omision(especialidad))
            if isinstance(valor, list)
            else modulos_por_omision(especialidad)
        )
        resultado.append((especialidad, modulos))
    return resultado


async def especialidades_permitidas(
    sesion: AsyncSession, principal: Principal
) -> list[tuple[Especialidad, tuple[str, ...], bool]]:
    """Especialidades desde las que este principal puede revisar historias.

    Devuelve (especialidad, módulos, es_la_propia). La propia va primero.
    """
    if principal.clinica_id is None or principal.es_agente:
        return []
    ambito = principal.ambito
    propia: uuid.UUID | None = None
    if principal.profesional_id is not None:
        propia = (
            await sesion.execute(
                select(Profesional.especialidad_id).where(
                    Profesional.id == principal.profesional_id,
                    Profesional.clinica_id == principal.clinica_id,
                )
            )
        ).scalar_one_or_none()
    resultado = []
    for especialidad, modulos in await modulos_de_clinica(sesion, principal.clinica_id):
        es_propia = especialidad.id == propia
        if principal.profesional_id is not None:
            permitida = es_propia or especialidad.id in ambito.especialidades
        else:
            permitida = ambito.cubre_especialidad(especialidad.id)
        if permitida and (es_propia or especialidad.activa):
            # Consultar otra área no acredita para usar sus herramientas.
            habilitados = (
                tuple(m for m in modulos if m == "imagenes")
                if principal.profesional_id is not None and not es_propia
                else modulos
            )
            resultado.append((especialidad, habilitados, es_propia))
    resultado.sort(key=lambda fila: (not fila[2], fila[0].nombre))
    return resultado


async def especialidades_de_notas(
    sesion: AsyncSession, principal: Principal, especialidad_id: uuid.UUID | None
) -> frozenset[uuid.UUID]:
    """Especialidades cuyas notas se devuelven al revisar una historia.

    Sin indicar una, un profesional revisa desde la suya y el resto del
    personal, desde todas las que puede. Pedir una ajena se rechaza.
    """
    permitidas = await especialidades_permitidas(sesion, principal)
    if especialidad_id is not None:
        if not any(e.id == especialidad_id for e, _, _ in permitidas):
            raise PermisoDenegado("No puede revisar la historia desde esa especialidad.")
        return frozenset({especialidad_id})
    propias = [e.id for e, _, es_propia in permitidas if es_propia]
    if propias:
        return frozenset(propias)
    return frozenset(e.id for e, _, _ in permitidas)


def exige_modulo(
    modulo: Modulo,
    *permisos: str,
    exigir_todos: bool = False,
) -> Callable[..., Coroutine[Any, Any, Principal]]:
    """Permiso **y** una especialidad permitida que use el módulo."""
    base = exige_permiso(*permisos, exigir_todos=exigir_todos)

    async def dependencia(
        sesion: Sesion,
        # Valor por defecto y no `Annotated`: con las anotaciones diferidas,
        # FastAPI no resolvería `base`, que es local a esta función.
        principal: Principal = Depends(base),  # noqa: B008
    ) -> Principal:
        permitidas = await especialidades_permitidas(sesion, principal)
        if not any(modulo in modulos for _, modulos, _ in permitidas):
            raise PermisoDenegado(f"«{MODULOS[modulo][0]}» no está activo en su especialidad.")
        return principal

    return dependencia


# ---------------------------------------------------------------------------
#  Rutas
# ---------------------------------------------------------------------------
enrutador = APIRouter(tags=["historia clinica"])

PuedeRevisar = Annotated[
    Principal,
    Depends(
        exige_permiso(
            "historia_clinica.leer",
            "odontograma.leer",
            "plan_tratamiento.leer",
            "imagen_clinica.leer",
        )
    ),
]
PuedeGestionar = Annotated[Principal, Depends(exige_permiso("especialidad.gestionar"))]


class ModuloSalida(BaseModel):
    codigo: str
    nombre: str
    descripcion: str


class EspecialidadHistoriaSalida(BaseModel):
    id: uuid.UUID
    nombre: str
    modulos: list[str]
    propia: bool


class ModulosEspecialidadSalida(BaseModel):
    id: uuid.UUID
    nombre: str
    activa: bool
    modulos: list[str]
    disponibles: list[str] = Field(default_factory=list)


class ConfiguracionModulosSalida(BaseModel):
    catalogo: list[ModuloSalida]
    especialidades: list[ModulosEspecialidadSalida]


class CambioModulos(BaseModel):
    modulos: list[Modulo] = Field(max_length=len(MODULOS))
    motivo: str = Field(min_length=5, max_length=300)


@enrutador.get("/historia/especialidades", response_model=list[EspecialidadHistoriaSalida])
async def mis_especialidades(
    principal: PuedeRevisar, sesion: Sesion
) -> list[EspecialidadHistoriaSalida]:
    """Desde qué especialidades puede revisar historias quien pregunta."""
    return [
        EspecialidadHistoriaSalida(
            id=especialidad.id, nombre=especialidad.nombre, modulos=list(modulos), propia=propia
        )
        for especialidad, modulos, propia in await especialidades_permitidas(sesion, principal)
    ]


def _catalogo() -> list[ModuloSalida]:
    return [
        ModuloSalida(codigo=codigo, nombre=nombre, descripcion=descripcion)
        for codigo, (nombre, descripcion) in MODULOS.items()
    ]


@enrutador.get(
    "/catalogo/especialidades/modulos-historia", response_model=ConfiguracionModulosSalida
)
async def ver_modulos(principal: PuedeGestionar, sesion: Sesion) -> ConfiguracionModulosSalida:
    if principal.clinica_id is None:
        raise DatosInvalidos("La sesión no pertenece a una clínica.")
    return ConfiguracionModulosSalida(
        catalogo=_catalogo(),
        especialidades=[
            ModulosEspecialidadSalida(
                id=e.id,
                nombre=e.nombre,
                activa=e.activa,
                modulos=list(modulos),
                disponibles=list(modulos_por_omision(e)),
            )
            for e, modulos in await modulos_de_clinica(sesion, principal.clinica_id)
        ],
    )


@enrutador.put(
    "/catalogo/especialidades/{especialidad_id}/modulos-historia",
    response_model=ModulosEspecialidadSalida,
)
async def cambiar_modulos(
    principal: PuedeGestionar,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    especialidad_id: Annotated[uuid.UUID, Path()],
    cambio: CambioModulos,
) -> ModulosEspecialidadSalida:
    clinica_id = principal.clinica_id
    if clinica_id is None:
        raise DatosInvalidos("La sesión no pertenece a una clínica.")
    especialidad = await sesion.get(Especialidad, especialidad_id)
    if especialidad is None or especialidad.clinica_id != clinica_id:
        raise RecursoNoEncontrado("La especialidad indicada no existe.")
    # Orden del catálogo y sin repetidos, para que dos guardados iguales lo sean.
    if any(m not in modulos_por_omision(especialidad) for m in cambio.modulos):
        raise DatosInvalidos(
            "Las herramientas deben corresponder a la especialidad: odontograma y periodoncia para odontología; faciograma para estética."
        )
    modulos = [m for m in MODULOS if m in cambio.modulos]

    actual = await _vigente(sesion, clinica_id)
    valor = dict(actual.valor) if actual else {}
    valor[str(especialidad_id)] = modulos
    version = 1
    if actual is not None:
        version = actual.version + 1
        await sesion.execute(
            update(ConfiguracionClinica)
            .where(ConfiguracionClinica.id == actual.id)
            .values(vigente=False)
        )
        await sesion.flush()
    sesion.add(
        ConfiguracionClinica(
            clinica_id=clinica_id,
            clave=CLAVE,
            valor=valor,
            version=version,
            vigente=True,
            creado_por=principal.actor_id,
        )
    )
    await sesion.flush()
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.ESPECIALIDAD_MODULOS_CAMBIADOS,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="especialidad",
                entidad_id=especialidad_id,
                motivo=cambio.motivo,
                modulos_activos=modulos,
            )
        ]
    )
    await sesion.commit()
    return ModulosEspecialidadSalida(
        id=especialidad.id,
        nombre=especialidad.nombre,
        activa=especialidad.activa,
        modulos=modulos,
        disponibles=list(modulos_por_omision(especialidad)),
    )


__all__ = [
    "CLAVE",
    "MODULOS",
    "enrutador",
    "especialidades_de_notas",
    "especialidades_permitidas",
    "exige_modulo",
    "modulos_de_clinica",
]
