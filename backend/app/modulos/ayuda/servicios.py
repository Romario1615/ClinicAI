"""Composicion de los manuales de ayuda.

La regla central: **una seccion solo aparece si el rol la habilita y la
sesion tambien**. Se cruzan los permisos del rol con los efectivos del
principal porque son dos preguntas distintas: el rol dice para que fue
pensado; el principal, lo que la persona puede hacer hoy. Si una clinica
retira un permiso a un rol, el manual deja de describir esa tarea en la
siguiente consulta.
"""

from __future__ import annotations

from app.modulos.ayuda.esquemas import (
    ManualSalida,
    PermisoSalida,
    SeccionSalida,
    TipoManual,
)
from app.modulos.ayuda.manuales import (
    CAPACIDADES,
    LIMITES_COMUNES_PERSONALIZADO,
    MANUALES_SISTEMA,
    NEGACIONES,
    Seccion,
)
from app.modulos.ayuda.repositorio import RolConPermisos
from app.nucleo.autorizacion import PERMISOS_POR_CODIGO, Principal


def _permisos_salida(codigos: frozenset[str]) -> list[PermisoSalida]:
    return [
        PermisoSalida(
            codigo=codigo,
            descripcion=PERMISOS_POR_CODIGO[codigo].descripcion
            if codigo in PERMISOS_POR_CODIGO
            else codigo,
        )
        for codigo in sorted(codigos)
    ]


def _seccion_salida(seccion: Seccion, permisos_efectivos: frozenset[str]) -> SeccionSalida:
    return SeccionSalida(
        clave=seccion.clave,
        titulo=seccion.titulo,
        ruta=seccion.ruta,
        proposito=seccion.proposito,
        pasos=list(seccion.pasos),
        limites=list(seccion.limites),
        # Solo los permisos que la persona tiene: una seccion con «alguno»
        # no presume de los que le faltan.
        permisos=_permisos_salida(seccion.permisos & permisos_efectivos),
    )


def construir_manual(rol: RolConPermisos, principal: Principal) -> ManualSalida:
    """Manual de un rol para quien consulta."""
    efectivos = rol.permisos & principal.permisos
    roles = frozenset({rol.codigo}) & principal.roles

    manual_sistema = MANUALES_SISTEMA.get(rol.codigo) if rol.es_sistema else None
    if manual_sistema is not None:
        secciones = [
            _seccion_salida(seccion, efectivos)
            for seccion in manual_sistema.secciones
            if seccion.aplica(efectivos, roles)
        ]
        return ManualSalida(
            rol_codigo=rol.codigo,
            rol_nombre=rol.nombre,
            tipo=TipoManual.SISTEMA,
            titulo=manual_sistema.titulo,
            introduccion=manual_sistema.introduccion,
            responsabilidades=list(manual_sistema.responsabilidades),
            limites=list(manual_sistema.limites),
            secciones=secciones,
        )

    secciones = [
        _seccion_salida(seccion, efectivos)
        for seccion in CAPACIDADES
        if seccion.aplica(efectivos, roles)
    ]
    descripcion = (rol.descripcion or "").strip()
    introduccion = (
        f"«{rol.nombre}» es un rol propio de su clínica. "
        + (f"Su propósito, según la clínica: {descripcion} " if descripcion else "")
        + f"Este manual reúne las {len(secciones)} tareas que sus permisos habilitan."
    )
    return ManualSalida(
        rol_codigo=rol.codigo,
        rol_nombre=rol.nombre,
        tipo=TipoManual.PERSONALIZADO,
        titulo=f"Manual del rol {rol.nombre}",
        introduccion=introduccion,
        responsabilidades=[seccion.proposito for seccion in secciones],
        limites=[texto for codigo, texto in NEGACIONES if codigo not in efectivos]
        + list(LIMITES_COMUNES_PERSONALIZADO),
        secciones=secciones,
    )


def construir_manuales(roles: list[RolConPermisos], principal: Principal) -> list[ManualSalida]:
    return [construir_manual(rol, principal) for rol in roles]
