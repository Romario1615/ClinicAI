"""Pruebas del modelo de autorizacion.

Estas pruebas verifican las decisiones de seguridad de `docs/security.md`,
no solo que el codigo se ejecute:

* un ambito vacio no da acceso a nada,
* recepcion no tiene acceso clinico,
* el superadministrador no lee historias clinicas,
* el auditor puede verificar sin ver contenido,
* el principal del sistema no puede escribir datos clinicos.

Si alguna falla, la matriz documentada y la implementada han divergido, que
es precisamente como se cuelan los agujeros de autorizacion.
"""

from __future__ import annotations

import uuid

import pytest

from app.nucleo.autorizacion import (
    CATALOGO_PERMISOS,
    PERMISOS_POR_CODIGO,
    PERMISOS_POR_ROL,
    PERMISOS_SOLO_ASISTENCIALES,
    Ambito,
    NivelSensibilidad,
    NivelVerificacion,
    Principal,
    TipoActor,
    principal_anonimo,
    principal_sistema,
    validar_catalogo,
)

pytestmark = pytest.mark.unitaria


class TestCatalogo:
    def test_el_catalogo_es_coherente(self) -> None:
        """Ningun rol referencia un permiso inexistente.

        Una errata en el codigo de un permiso lo deja sin efecto y nadie se
        da cuenta hasta que alguien accede a lo que no debe.
        """
        problemas = validar_catalogo()
        assert problemas == [], "\n".join(problemas)

    def test_no_hay_permisos_duplicados(self) -> None:
        codigos = [p.codigo for p in CATALOGO_PERMISOS]
        assert len(codigos) == len(set(codigos))

    def test_todo_permiso_tiene_formato_recurso_accion(self) -> None:
        for permiso in CATALOGO_PERMISOS:
            assert "." in permiso.codigo, f"{permiso.codigo} no sigue recurso.accion"
            assert permiso.codigo.islower()

    def test_los_permisos_clinicos_exigen_relacion_asistencial(self) -> None:
        """Tener el rol no basta: hace falta vinculo con el paciente."""
        for codigo in PERMISOS_SOLO_ASISTENCIALES:
            definicion = PERMISOS_POR_CODIGO[codigo]
            assert definicion.requiere_relacion_asistencial, (
                f"{codigo} debe exigir relacion asistencial."
            )

    def test_los_permisos_clinicos_declaran_nivel_clinico(self) -> None:
        for codigo in PERMISOS_SOLO_ASISTENCIALES:
            definicion = PERMISOS_POR_CODIGO[codigo]
            assert definicion.nivel.cubre(NivelSensibilidad.CLINICO)


class TestMatrizDePermisos:
    """Comprueba las decisiones de docs/security.md, seccion 2."""

    def test_recepcion_no_accede_a_informacion_clinica(self) -> None:
        """Recepcion ve que hay una cita, no por que.

        Es una regla de negocio, no una preferencia de interfaz.
        """
        recepcion = PERMISOS_POR_ROL["recepcion"]
        assert "historia_clinica.leer" not in recepcion
        assert "historia_clinica.escribir" not in recepcion
        assert "historia_clinica.leer_sensible" not in recepcion
        assert "receta.leer" not in recepcion
        assert "diagnostico.registrar" not in recepcion
        # Pero si puede operar la agenda
        assert "cita.crear" in recepcion
        assert "paciente.leer_administrativo" in recepcion

    def test_superadministrador_no_accede_a_historia_clinica(self) -> None:
        """Separa la administracion tecnica del acceso clinico.

        Una cuenta tecnica comprometida no debe exponer datos de pacientes.
        """
        superadmin = PERMISOS_POR_ROL["superadministrador"]
        assert not (superadmin & PERMISOS_SOLO_ASISTENCIALES)
        assert "rol.asignar" in superadmin

    def test_administrador_clinica_no_accede_a_contenido_clinico(self) -> None:
        admin = PERMISOS_POR_ROL["administrador_clinica"]
        assert "historia_clinica.leer" not in admin
        assert "receta.crear" not in admin
        # Ve metadatos para poder auditar la operacion
        assert "historia_clinica.leer_metadatos" in admin

    def test_auditor_verifica_sin_ver(self) -> None:
        """El auditor comprueba quien accedio a que, sin leer el contenido."""
        auditor = PERMISOS_POR_ROL["auditor"]
        assert "auditoria.leer" in auditor
        assert "historia_clinica.leer_metadatos" in auditor
        assert not (auditor & PERMISOS_SOLO_ASISTENCIALES)

    def test_auditor_no_modifica_nada(self) -> None:
        """Separacion de funciones: quien audita no altera datos."""
        auditor = PERMISOS_POR_ROL["auditor"]
        for permiso in auditor:
            accion = permiso.split(".", 1)[1]
            assert accion not in {
                "crear",
                "editar",
                "escribir",
                "cancelar",
                "reprogramar",
                "confirmar",
                "validar",
                "aprobar",
                "archivar",
                "asignar",
                "desactivar",
                "registrar",
                "gestionar",
                "responder",
                "tomar",
            }, f"El auditor no debe poder '{permiso}'."

    def test_solo_el_profesional_escribe_datos_clinicos(self) -> None:
        for codigo in (
            "historia_clinica.escribir",
            "diagnostico.registrar",
            "receta.crear",
            "receta.confirmar",
        ):
            con_permiso = [rol for rol, permisos in PERMISOS_POR_ROL.items() if codigo in permisos]
            assert con_permiso == ["profesional"], (
                f"'{codigo}' solo debe tenerlo el profesional, pero lo tienen: {con_permiso}"
            )

    def test_asistente_no_lee_historia_pero_si_recetas(self) -> None:
        """El asistente ayuda con la medicacion sin leer la evolucion clinica."""
        asistente = PERMISOS_POR_ROL["asistente"]
        assert "historia_clinica.leer" not in asistente
        assert "receta.leer" in asistente
        assert "alerta_adherencia.atender" in asistente

    def test_todos_los_roles_base_existen(self) -> None:
        esperados = {
            "superadministrador",
            "administrador_clinica",
            "recepcion",
            "profesional",
            "asistente",
            "auditor",
        }
        assert set(PERMISOS_POR_ROL) == esperados


class TestAmbito:
    def test_ambito_vacio_no_da_acceso(self) -> None:
        """El valor por defecto es el mas restrictivo.

        Un `usuario_rol` al que se olvido asignar ambito no debe convertirse
        en superusuario por omision.
        """
        ambito = Ambito()
        assert ambito.esta_vacio
        assert not ambito.cubre_sede(uuid.uuid4())
        assert not ambito.cubre_paciente(uuid.uuid4())
        assert not ambito.cubre_profesional(uuid.uuid4())

    def test_ambito_por_lista_cubre_solo_lo_listado(self) -> None:
        sede_propia = uuid.uuid4()
        sede_ajena = uuid.uuid4()
        ambito = Ambito(sedes=frozenset({sede_propia}))
        assert ambito.cubre_sede(sede_propia)
        assert not ambito.cubre_sede(sede_ajena)

    def test_comodin_debe_concederse_explicitamente(self) -> None:
        ambito = Ambito(todas_las_sedes=True)
        assert ambito.cubre_sede(uuid.uuid4())
        assert not ambito.esta_vacio

    def test_identificador_nulo_se_considera_cubierto(self) -> None:
        """Un recurso sin sede asignada (global de la clinica) no se filtra."""
        assert Ambito().cubre_sede(None)
        assert Ambito().cubre_especialidad(None)

    def test_nivel_de_sensibilidad_es_jerarquico(self) -> None:
        assert NivelSensibilidad.CLINICO_SENSIBLE.cubre(NivelSensibilidad.CLINICO)
        assert NivelSensibilidad.CLINICO.cubre(NivelSensibilidad.ADMINISTRATIVO)
        assert not NivelSensibilidad.ADMINISTRATIVO.cubre(NivelSensibilidad.CLINICO)
        assert not NivelSensibilidad.CLINICO.cubre(NivelSensibilidad.CLINICO_SENSIBLE)

    def test_ambito_administrativo_no_cubre_nivel_clinico(self) -> None:
        ambito = Ambito(nivel_maximo=NivelSensibilidad.ADMINISTRATIVO)
        assert ambito.cubre_nivel(NivelSensibilidad.ADMINISTRATIVO)
        assert not ambito.cubre_nivel(NivelSensibilidad.CLINICO)


class TestNivelVerificacion:
    def test_es_jerarquico(self) -> None:
        assert NivelVerificacion.DOCUMENTO.alcanza(NivelVerificacion.TELEFONO)
        assert NivelVerificacion.PRESENCIAL.alcanza(NivelVerificacion.DOCUMENTO)
        assert not NivelVerificacion.TELEFONO.alcanza(NivelVerificacion.DOCUMENTO)

    def test_el_telefono_no_alcanza_para_datos_clinicos(self) -> None:
        """Un telefono puede ser familiar, prestado, robado o reasignado.

        Es la regla que impide que quien escriba desde el numero de un
        paciente obtenga su historia clinica.
        """
        assert not NivelVerificacion.TELEFONO.alcanza(NivelVerificacion.DOCUMENTO)
        assert not NivelVerificacion.NO_VERIFICADO.alcanza(NivelVerificacion.DOCUMENTO)


class TestPrincipal:
    def test_principal_anonimo_no_tiene_permisos(self) -> None:
        principal = principal_anonimo()
        assert principal.permisos == frozenset()
        assert principal.ambito.esta_vacio
        assert not principal.tiene_permiso("agenda.leer")

    def test_principal_del_sistema_no_escribe_datos_clinicos(self) -> None:
        """Un trabajo programado no escribe notas ni confirma recetas."""
        sistema = principal_sistema(uuid.uuid4())
        assert not (sistema.permisos & PERMISOS_SOLO_ASISTENCIALES)
        assert sistema.es_sistema
        # Pero si opera la agenda y la lista de espera
        assert sistema.tiene_permiso("lista_espera.gestionar")
        assert sistema.tiene_permiso("cita.cancelar")

    def test_principal_del_sistema_no_eleva_nivel_de_sensibilidad(self) -> None:
        sistema = principal_sistema(uuid.uuid4())
        assert sistema.ambito.nivel_maximo is NivelSensibilidad.ADMINISTRATIVO
        assert not sistema.ambito.cubre_nivel(NivelSensibilidad.CLINICO)

    def test_segundo_factor_pendiente_no_se_considera_cumplido(self) -> None:
        """Un token emitido antes de completar el 2FA no debe dar acceso."""
        principal = Principal(
            actor_tipo=TipoActor.USUARIO,
            actor_id=uuid.uuid4(),
            clinica_id=uuid.uuid4(),
            permisos=frozenset({"auditoria.leer"}),
            ambito=Ambito(todas_las_sedes=True),
            requiere_segundo_factor=True,
            segundo_factor_cumplido=False,
        )
        assert not principal.cumple_segundo_factor

    def test_segundo_factor_no_exigido_se_considera_cumplido(self) -> None:
        principal = Principal(
            actor_tipo=TipoActor.USUARIO,
            actor_id=uuid.uuid4(),
            clinica_id=uuid.uuid4(),
            permisos=frozenset(),
            ambito=Ambito(),
            requiere_segundo_factor=False,
        )
        assert principal.cumple_segundo_factor

    def test_el_agente_se_distingue_en_auditoria(self) -> None:
        """El tipo de actor no otorga privilegios, solo trazabilidad."""
        agente = Principal(
            actor_tipo=TipoActor.AGENTE_IA,
            actor_id=None,
            clinica_id=uuid.uuid4(),
            permisos=frozenset({"agenda.leer"}),
            ambito=Ambito(todas_las_sedes=True),
        )
        assert agente.es_agente
        assert not agente.tiene_permiso("historia_clinica.leer")

    def test_el_principal_es_inmutable(self) -> None:
        """No debe poder ampliarse a mitad de una peticion."""
        principal = principal_anonimo()
        with pytest.raises((AttributeError, TypeError)):
            principal.permisos = frozenset({"historia_clinica.leer"})  # type: ignore[misc]
