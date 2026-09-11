"""Carga de los catalogos del sistema: permisos y roles base.

Estos datos NO son de prueba: son parte del funcionamiento.  Sin ellos, la
resolucion de permisos devuelve el conjunto vacio y nadie puede hacer nada.
Se cargan en todos los entornos, produccion incluida.

La carga es idempotente y **no destructiva**:

* Un permiso nuevo en el codigo se inserta.
* Un permiso cuya descripcion cambio se actualiza.
* Un permiso que ya no esta en el codigo se DEJA en la base de datos, con un
  aviso.  Borrarlo en cascada eliminaria sus filas de `rol_permiso`, y si el
  permiso volviera a aparecer en una version posterior los roles habrian
  perdido su asignacion en silencio.  Retirar un permiso de verdad es una
  operacion deliberada, con su migracion.

La fuente de verdad es `app.nucleo.autorizacion`.  Hay una prueba que
verifica que la tabla y el catalogo del codigo coincidan: si divergen, un
permiso del codigo podria no existir en la base y quedar sin efecto sin que
nadie lo note.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.usuarios.modelos import Permiso, Rol, RolPermiso
from app.nucleo.autorizacion import (
    CATALOGO_PERMISOS,
    PERMISOS_POR_ROL,
    PERMISOS_SOLO_ASISTENCIALES,
    validar_catalogo,
)

# Nombres legibles de los roles base, para la interfaz.
NOMBRES_DE_ROL: dict[str, tuple[str, str]] = {
    "superadministrador": (
        "Superadministrador",
        "Administra la plataforma. NO accede a informacion clinica: separar la "
        "administracion tecnica del acceso clinico evita que una cuenta "
        "tecnica comprometida exponga datos de pacientes.",
    ),
    "administrador_clinica": (
        "Administrador de clinica",
        "Gestiona la organizacion, el personal y la configuracion. Ve "
        "metadatos clinicos para poder auditar la operacion, pero no el "
        "contenido de las historias.",
    ),
    "recepcion": (
        "Recepcion",
        "Agenda, registra pacientes y gestiona pagos. Ve que existe una cita y "
        "con quien, no el motivo de consulta ni el diagnostico.",
    ),
    "profesional": (
        "Profesional",
        "Atiende pacientes. Unico rol que escribe historia clinica y recetas, "
        "y solo de los pacientes con los que tiene relacion asistencial.",
    ),
    "asistente": (
        "Asistente o enfermeria",
        "Apoya la atencion y el seguimiento de medicacion. Ve recetas y "
        "adherencia, no la evolucion clinica.",
    ),
    "auditor": (
        "Auditor",
        "Verifica quien accedio a que y cuando. Puede comprobar sin ver: lee "
        "la pista de auditoria y los metadatos, nunca el contenido clinico.",
    ),
}


@dataclass(slots=True)
class ResumenCarga:
    """Lo que hizo la carga. Se imprime para poder revisarlo."""

    permisos_creados: int = 0
    permisos_actualizados: int = 0
    roles_creados: int = 0
    roles_actualizados: int = 0
    asignaciones_creadas: int = 0
    asignaciones_retiradas: int = 0
    permisos_huerfanos: list[str] = field(default_factory=list)

    def describir(self) -> str:
        lineas = [
            f"Permisos:     {self.permisos_creados} creados, "
            f"{self.permisos_actualizados} actualizados",
            f"Roles:        {self.roles_creados} creados, {self.roles_actualizados} actualizados",
            f"Asignaciones: {self.asignaciones_creadas} creadas, "
            f"{self.asignaciones_retiradas} retiradas",
        ]
        if self.permisos_huerfanos:
            lineas.append(
                f"AVISO: {len(self.permisos_huerfanos)} permiso(s) en la base de "
                f"datos ya no existen en el codigo y se han conservado: "
                f"{', '.join(sorted(self.permisos_huerfanos))}"
            )
        return "\n".join(lineas)


async def cargar_catalogos(sesion: AsyncSession) -> ResumenCarga:
    """Sincroniza permisos, roles y asignaciones con el catalogo del codigo.

    No hace `commit`: el llamante decide el limite transaccional, para que la
    carga completa se aplique o no se aplique.  Una carga a medias dejaria
    roles sin permisos y usuarios sin poder trabajar.
    """
    problemas = validar_catalogo()
    if problemas:
        # Se aborta ANTES de escribir nada.  Cargar un catalogo incoherente
        # es peor que no cargarlo: produce roles con permisos que no existen
        # y el fallo aparece mucho despues, al denegar un acceso legitimo.
        raise ValueError(
            "El catalogo de autorizacion es incoherente y no se cargara:\n"
            + "\n".join(f"  - {p}" for p in problemas)
        )

    resumen = ResumenCarga()
    permisos_por_codigo = await _sincronizar_permisos(sesion, resumen)
    await _sincronizar_roles(sesion, permisos_por_codigo, resumen)
    return resumen


async def _sincronizar_permisos(sesion: AsyncSession, resumen: ResumenCarga) -> dict[str, Permiso]:
    existentes = {p.codigo: p for p in (await sesion.execute(select(Permiso))).scalars()}

    for definicion in CATALOGO_PERMISOS:
        actual = existentes.get(definicion.codigo)
        if actual is None:
            nuevo = Permiso(
                codigo=definicion.codigo,
                descripcion=definicion.descripcion,
                categoria=definicion.categoria,
                requiere_relacion_asistencial=definicion.requiere_relacion_asistencial,
                nivel_sensibilidad=definicion.nivel.value,
            )
            sesion.add(nuevo)
            existentes[definicion.codigo] = nuevo
            resumen.permisos_creados += 1
            continue

        cambio = False
        if actual.descripcion != definicion.descripcion:
            actual.descripcion = definicion.descripcion
            cambio = True
        if actual.categoria != definicion.categoria:
            actual.categoria = definicion.categoria
            cambio = True
        if actual.requiere_relacion_asistencial != definicion.requiere_relacion_asistencial:
            actual.requiere_relacion_asistencial = definicion.requiere_relacion_asistencial
            cambio = True
        if actual.nivel_sensibilidad != definicion.nivel.value:
            actual.nivel_sensibilidad = definicion.nivel.value
            cambio = True
        if cambio:
            resumen.permisos_actualizados += 1

    # Permisos que estan en la base y ya no en el codigo.  Se conservan.
    codigos_del_codigo = {d.codigo for d in CATALOGO_PERMISOS}
    resumen.permisos_huerfanos = sorted(set(existentes) - codigos_del_codigo)

    await sesion.flush()
    return existentes


async def _sincronizar_roles(
    sesion: AsyncSession,
    permisos_por_codigo: dict[str, Permiso],
    resumen: ResumenCarga,
) -> None:
    """Crea o actualiza los roles del sistema y sus asignaciones.

    Los roles del sistema tienen `clinica_id` nulo y `es_sistema` cierto: son
    comunes a todas las clinicas y no se pueden modificar desde la interfaz.
    Una clinica que necesite un rol propio crea uno nuevo, sin tocar estos.
    """
    existentes = {
        r.codigo: r
        for r in (await sesion.execute(select(Rol).where(Rol.clinica_id.is_(None)))).scalars()
    }

    for codigo, permisos_esperados in PERMISOS_POR_ROL.items():
        nombre, descripcion = NOMBRES_DE_ROL[codigo]
        rol = existentes.get(codigo)

        if rol is None:
            rol = Rol(
                clinica_id=None,
                codigo=codigo,
                nombre=nombre,
                descripcion=descripcion,
                es_sistema=True,
            )
            sesion.add(rol)
            await sesion.flush()
            resumen.roles_creados += 1
        elif rol.nombre != nombre or rol.descripcion != descripcion:
            rol.nombre = nombre
            rol.descripcion = descripcion
            resumen.roles_actualizados += 1

        # --- Asignaciones ---
        asignadas = {
            fila.permiso_id
            for fila in (
                await sesion.execute(select(RolPermiso).where(RolPermiso.rol_id == rol.id))
            ).scalars()
        }
        esperadas = {permisos_por_codigo[c].id for c in permisos_esperados}

        for permiso_id in esperadas - asignadas:
            sesion.add(RolPermiso(rol_id=rol.id, permiso_id=permiso_id))
            resumen.asignaciones_creadas += 1

        # Las asignaciones que sobran SI se retiran: un permiso que el codigo
        # ya no concede a un rol debe dejar de concederse de inmediato.  Es lo
        # contrario que con los permisos huerfanos, y la diferencia importa:
        # conservar un permiso sin usar no da acceso, conservar una asignacion
        # obsoleta si.
        for permiso_id in asignadas - esperadas:
            fila = (
                await sesion.execute(
                    select(RolPermiso).where(
                        RolPermiso.rol_id == rol.id,
                        RolPermiso.permiso_id == permiso_id,
                    )
                )
            ).scalar_one_or_none()
            if fila is not None:
                await sesion.delete(fila)
                resumen.asignaciones_retiradas += 1

    await sesion.flush()


async def verificar_coherencia(sesion: AsyncSession) -> list[str]:
    """Comprueba que la base de datos y el catalogo del codigo coincidan.

    Se ejecuta como prueba de integracion.  Detecta la divergencia silenciosa:
    un permiso que el codigo exige pero que no existe en la tabla queda sin
    efecto, y ningun rol lo tendra nunca asignado.
    """
    problemas: list[str] = []

    codigos_bd = set((await sesion.execute(select(Permiso.codigo))).scalars())
    codigos_codigo = {d.codigo for d in CATALOGO_PERMISOS}

    faltantes = codigos_codigo - codigos_bd
    if faltantes:
        problemas.append(
            f"Permisos del codigo ausentes en la base de datos: {sorted(faltantes)}. "
            "Ejecute la carga de catalogos."
        )

    # Roles administrativos sin permisos clinicos.
    for codigo_rol in ("superadministrador", "recepcion", "auditor"):
        rol = (
            await sesion.execute(
                select(Rol).where(Rol.codigo == codigo_rol, Rol.clinica_id.is_(None))
            )
        ).scalar_one_or_none()
        if rol is None:
            problemas.append(f"Falta el rol del sistema '{codigo_rol}'.")
            continue

        consulta = (
            select(Permiso.codigo)
            .join(RolPermiso, RolPermiso.permiso_id == Permiso.id)
            .where(RolPermiso.rol_id == rol.id)
        )
        concedidos = set((await sesion.execute(consulta)).scalars())
        clinicos = concedidos & PERMISOS_SOLO_ASISTENCIALES
        if clinicos:
            problemas.append(
                f"El rol '{codigo_rol}' tiene permisos clinicos en la base de "
                f"datos: {sorted(clinicos)}. Separar la administracion del "
                "acceso clinico es una decision de diseno."
            )

    return problemas
