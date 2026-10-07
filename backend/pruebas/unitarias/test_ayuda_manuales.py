"""Los manuales de ayuda son propios de cada rol y nunca prometen de mas.

Estas pruebas son el criterio de aceptacion de la tarea 11.1 traducido a
comprobaciones: un manual por rol del sistema, sin texto compartido entre
manuales, sin secciones que el rol no pueda usar y sin rutas inexistentes.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter
from pathlib import Path

import pytest

from app.modulos.ayuda.esquemas import TipoManual
from app.modulos.ayuda.manuales import CAPACIDADES, MANUALES_SISTEMA, Seccion
from app.modulos.ayuda.repositorio import RolConPermisos
from app.modulos.ayuda.rutas import _personal_verificado
from app.modulos.ayuda.servicios import construir_manual, construir_manuales
from app.nucleo.autorizacion import (
    PERMISOS_POR_CODIGO,
    PERMISOS_POR_ROL,
    Ambito,
    Principal,
    TipoActor,
)
from app.nucleo.errores import PermisoDenegado, SegundoFactorRequerido

pytestmark = pytest.mark.unitaria

RAIZ_REPOSITORIO = Path(__file__).resolve().parents[3]
RUTAS_ANGULAR = RAIZ_REPOSITORIO / "frontend" / "src" / "app" / "app.routes.ts"


def _todas_las_secciones() -> list[Seccion]:
    secciones = [s for m in MANUALES_SISTEMA.values() for s in m.secciones]
    return secciones + list(CAPACIDADES)


def _principal(roles: set[str], permisos: frozenset[str]) -> Principal:
    return Principal(
        actor_tipo=TipoActor.USUARIO,
        actor_id=uuid.uuid4(),
        clinica_id=uuid.uuid4(),
        permisos=permisos,
        ambito=Ambito(),
        roles=frozenset(roles),
    )


def _rol(
    codigo: str, permisos: frozenset[str], *, sistema: bool, descripcion: str | None = None
) -> RolConPermisos:
    return RolConPermisos(
        id=uuid.uuid4(),
        codigo=codigo,
        nombre=codigo.replace("_", " ").capitalize(),
        descripcion=descripcion,
        es_sistema=sistema,
        permisos=permisos,
    )


def test_hay_un_manual_por_cada_rol_del_sistema() -> None:
    assert set(MANUALES_SISTEMA) == set(PERMISOS_POR_ROL)


@pytest.mark.parametrize("rol", sorted(MANUALES_SISTEMA))
def test_cada_seccion_del_rol_es_alcanzable_con_sus_permisos(rol: str) -> None:
    """Un manual que describe algo que el rol no puede hacer es un 403 anunciado."""
    permisos = PERMISOS_POR_ROL[rol]
    for seccion in MANUALES_SISTEMA[rol].secciones:
        assert seccion.aplica(permisos, frozenset({rol})), (
            f"La seccion {seccion.clave} de {rol} exige {sorted(seccion.permisos)} y el rol no lo tiene"
        )


@pytest.mark.parametrize("rol", sorted(MANUALES_SISTEMA))
def test_cada_manual_tiene_contenido_suficiente(rol: str) -> None:
    manual = MANUALES_SISTEMA[rol]
    assert len(manual.secciones) >= 5
    assert manual.responsabilidades
    assert manual.limites
    for seccion in manual.secciones:
        assert seccion.pasos, f"{seccion.clave} no tiene pasos"
        assert seccion.clave.split(".")[0], seccion.clave


def test_ningun_titulo_ni_paso_se_repite_entre_manuales() -> None:
    """La tarea 11.1 prohibe reutilizar contenido entre manuales."""
    secciones = _todas_las_secciones()
    titulos = Counter(s.titulo for s in secciones)
    pasos = Counter(p for s in secciones for p in s.pasos)
    claves = Counter(s.clave for s in secciones)

    assert [t for t, n in titulos.items() if n > 1] == []
    assert [p for p, n in pasos.items() if n > 1] == []
    assert [c for c, n in claves.items() if n > 1] == []


def test_las_introducciones_son_distintas() -> None:
    textos = [m.introduccion for m in MANUALES_SISTEMA.values()]
    assert len(set(textos)) == len(textos)


def test_todo_permiso_citado_existe_en_el_catalogo() -> None:
    citados = {p for s in _todas_las_secciones() for p in s.permisos}
    assert citados - set(PERMISOS_POR_CODIGO) == set()


def test_las_rutas_citadas_existen_en_el_frontend() -> None:
    """Un enlace del manual a una pantalla que no existe acaba en el panel sin explicacion."""
    rutas = {
        f"/{ruta}" for ruta in re.findall(r"path:\s*'([^':*]+)'", RUTAS_ANGULAR.read_text("utf-8"))
    }
    citadas = {s.ruta for s in _todas_las_secciones() if s.ruta}
    assert citadas - rutas == set()


def test_los_roles_administrativos_no_reciben_secciones_clinicas() -> None:
    clinicos = {"historia_clinica.leer", "receta.crear", "odontograma.escribir"}
    for rol in ("superadministrador", "administrador_clinica", "recepcion", "auditor"):
        for seccion in MANUALES_SISTEMA[rol].secciones:
            assert not (seccion.requiere & clinicos), (rol, seccion.clave)


def test_la_seccion_desaparece_si_la_sesion_pierde_el_permiso() -> None:
    """El rol dice para que se penso; la sesion, lo que se puede hoy."""
    permisos_rol = PERMISOS_POR_ROL["recepcion"]
    rol = _rol("recepcion", permisos_rol, sistema=True)
    completo = construir_manual(rol, _principal({"recepcion"}, permisos_rol))
    sin_cobros = construir_manual(rol, _principal({"recepcion"}, permisos_rol - {"pago.registrar"}))

    claves_completo = {s.clave for s in completo.secciones}
    claves_sin_cobros = {s.clave for s in sin_cobros.secciones}
    assert "recepcion.cobros" in claves_completo
    assert "recepcion.cobros" not in claves_sin_cobros
    assert completo.tipo is TipoManual.SISTEMA


def test_las_secciones_solo_muestran_los_permisos_que_se_tienen() -> None:
    permisos = frozenset({"agenda.leer", "cita.reprogramar"})
    rol = _rol("coordinacion", permisos, sistema=False)
    manual = construir_manual(rol, _principal({"coordinacion"}, permisos))

    cambios = next(s for s in manual.secciones if s.clave == "capacidad.mover")
    assert [p.codigo for p in cambios.permisos] == ["agenda.leer", "cita.reprogramar"]
    assert all(p.descripcion for p in cambios.permisos)


def test_el_portal_de_plataforma_exige_el_rol_y_no_un_permiso() -> None:
    permisos = PERMISOS_POR_ROL["superadministrador"]
    rol = _rol("superadministrador", permisos, sistema=True)

    con_rol = construir_manual(rol, _principal({"superadministrador"}, permisos))
    # Una sesion que tuviera los mismos permisos sin el rol no ve el portal.
    sin_rol = construir_manual(rol, _principal(set(), permisos))

    assert "plataforma.alta" in {s.clave for s in con_rol.secciones}
    assert "plataforma.alta" not in {s.clave for s in sin_rol.secciones}


def test_un_rol_personalizado_recibe_un_manual_compuesto_con_sus_permisos() -> None:
    permisos = frozenset({"agenda.leer", "cita.crear", "paciente.leer_administrativo", "pago.leer"})
    rol = _rol(
        "caja_y_turnos",
        permisos,
        sistema=False,
        descripcion="Atiende la caja y da turnos en horario de tarde.",
    )
    manual = construir_manual(rol, _principal({"caja_y_turnos"}, permisos))

    claves = {s.clave for s in manual.secciones}
    assert manual.tipo is TipoManual.PERSONALIZADO
    assert {
        "capacidad.agenda",
        "capacidad.citas",
        "capacidad.pacientes",
        "capacidad.cobros",
    } <= claves
    assert "capacidad.historia" not in claves
    assert "capacidad.cobros_registro" not in claves
    assert "Atiende la caja" in manual.introduccion
    assert "No consulta el contenido de la historia clínica." in manual.limites
    assert "No registra pagos." in manual.limites
    assert "No reserva citas nuevas." not in manual.limites
    for seccion in manual.secciones:
        assert {p.codigo for p in seccion.permisos} <= permisos


def test_un_rol_personalizado_sin_permisos_no_inventa_tareas() -> None:
    rol = _rol("vacio", frozenset(), sistema=False)
    manual = construir_manual(rol, _principal({"vacio"}, frozenset()))

    assert manual.secciones == []
    assert "0 tareas" in manual.introduccion


def test_un_rol_personalizado_con_codigo_de_sistema_no_hereda_su_manual() -> None:
    """Una clinica podria llamar «recepcion» a un rol propio: no por eso es el del sistema."""
    permisos = frozenset({"agenda.leer"})
    rol = _rol("recepcion", permisos, sistema=False)
    manual = construir_manual(rol, _principal({"recepcion"}, permisos))

    assert manual.tipo is TipoManual.PERSONALIZADO
    assert manual.titulo != MANUALES_SISTEMA["recepcion"].titulo


def test_varios_roles_dan_varios_manuales_en_orden() -> None:
    permisos = PERMISOS_POR_ROL["auditor"] | PERMISOS_POR_ROL["recepcion"]
    roles = [
        _rol("auditor", PERMISOS_POR_ROL["auditor"], sistema=True),
        _rol("recepcion", PERMISOS_POR_ROL["recepcion"], sistema=True),
    ]
    manuales = construir_manuales(roles, _principal({"auditor", "recepcion"}, permisos))

    assert [m.rol_codigo for m in manuales] == ["auditor", "recepcion"]


def test_la_ruta_exige_segundo_factor_y_rechaza_al_agente() -> None:
    pendiente = Principal(
        actor_tipo=TipoActor.USUARIO,
        actor_id=uuid.uuid4(),
        clinica_id=uuid.uuid4(),
        permisos=frozenset(),
        ambito=Ambito(),
        requiere_segundo_factor=True,
        segundo_factor_cumplido=False,
    )
    agente = Principal(
        actor_tipo=TipoActor.AGENTE_IA,
        actor_id=uuid.uuid4(),
        clinica_id=uuid.uuid4(),
        permisos=frozenset(),
        ambito=Ambito(),
    )

    with pytest.raises(SegundoFactorRequerido):
        _personal_verificado(pendiente)
    with pytest.raises(PermisoDenegado):
        _personal_verificado(agente)
    cumplido = _principal({"recepcion"}, frozenset())
    assert _personal_verificado(cumplido) is cumplido
