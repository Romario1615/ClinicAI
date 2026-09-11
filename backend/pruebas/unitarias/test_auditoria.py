"""Pruebas de la auditoria.

Lo que se verifica:

* que el actor se tome del principal y no de un argumento (una auditoria que
  atribuye mal una accion es peor que no tenerla),
* que no se pueda auditar contenido clinico ni secretos,
* que las acciones sensibles generen alerta y no solo queden registradas.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.nucleo.auditoria import (
    ACCIONES_CON_ALERTA,
    AccionAuditada,
    ErrorMetadatosAuditoria,
    ResultadoAuditoria,
    construir_entrada,
    validar_metadatos,
)
from app.nucleo.autorizacion import (
    Ambito,
    NivelSensibilidad,
    Principal,
    TipoActor,
    principal_sistema,
)

pytestmark = [pytest.mark.unitaria, pytest.mark.seguridad]

AHORA = datetime(2026, 4, 15, 14, 0, tzinfo=UTC)


def _principal_profesional() -> Principal:
    return Principal(
        actor_tipo=TipoActor.USUARIO,
        actor_id=uuid.uuid4(),
        clinica_id=uuid.uuid4(),
        permisos=frozenset({"historia_clinica.leer"}),
        ambito=Ambito(todas_las_sedes=True),
        profesional_id=uuid.uuid4(),
        origen="WEB",
    )


class TestConstruccionDeEntrada:
    def test_el_actor_se_toma_del_principal(self) -> None:
        """No es un argumento a proposito.

        Si el actor fuera un parametro, un error de programacion podria
        atribuir una accion a otro usuario y dejar la auditoria mintiendo.
        """
        principal = _principal_profesional()
        entrada = construir_entrada(
            accion=AccionAuditada.HISTORIA_CONSULTADA,
            principal=principal,
            ahora=AHORA,
            paciente_id=uuid.uuid4(),
        )
        assert entrada.actor_id == principal.actor_id
        assert entrada.actor_tipo is TipoActor.USUARIO
        assert entrada.clinica_id == principal.clinica_id

    def test_el_origen_viene_del_principal(self) -> None:
        principal = _principal_profesional()
        entrada = construir_entrada(
            accion=AccionAuditada.CITA_CREADA, principal=principal, ahora=AHORA
        )
        assert entrada.origen == "WEB"

    def test_el_trabajo_programado_se_registra_como_sistema(self) -> None:
        entrada = construir_entrada(
            accion=AccionAuditada.OFERTA_ENVIADA,
            principal=principal_sistema(uuid.uuid4()),
            ahora=AHORA,
        )
        assert entrada.actor_tipo is TipoActor.SISTEMA
        assert entrada.origen == "WORKER"

    def test_el_agente_se_registra_como_agente(self) -> None:
        """Distinguir lo que hizo el agente de lo que hizo una persona."""
        agente = Principal(
            actor_tipo=TipoActor.AGENTE_IA,
            actor_id=None,
            clinica_id=uuid.uuid4(),
            permisos=frozenset({"agenda.leer"}),
            ambito=Ambito(todas_las_sedes=True),
            origen="WHATSAPP",
        )
        entrada = construir_entrada(
            accion=AccionAuditada.HERRAMIENTA_INVOCADA, principal=agente, ahora=AHORA
        )
        assert entrada.actor_tipo is TipoActor.AGENTE_IA
        assert entrada.origen == "WHATSAPP"

    def test_se_registra_el_nivel_de_sensibilidad(self) -> None:
        entrada = construir_entrada(
            accion=AccionAuditada.ACCESO_SENSIBLE,
            principal=_principal_profesional(),
            ahora=AHORA,
            paciente_id=uuid.uuid4(),
            nivel_sensibilidad=NivelSensibilidad.CLINICO_SENSIBLE,
        )
        assert entrada.nivel_sensibilidad is NivelSensibilidad.CLINICO_SENSIBLE

    def test_un_acceso_denegado_se_registra(self) -> None:
        """Los intentos fallidos son la senal mas util ante un incidente."""
        entrada = construir_entrada(
            accion=AccionAuditada.PERMISO_DENEGADO,
            principal=_principal_profesional(),
            ahora=AHORA,
            resultado=ResultadoAuditoria.DENEGADO,
        )
        assert entrada.resultado is ResultadoAuditoria.DENEGADO


class TestMetadatosProhibidos:
    """La auditoria registra referencias, no contenido clinico.

    Si guardara el contenido, seria una segunda copia de la historia clinica
    sin sus restricciones de acceso, y la mayor fuga del sistema.
    """

    @pytest.mark.parametrize(
        "clave",
        [
            "contenido",
            "nota",
            "diagnostico",
            "diagnosticos",
            "motivo_consulta",
            "medicamento_nombre",
            "dosis",
            "indicaciones",
            "antecedentes",
            "alergias",
            "mensaje",
            "texto",
            "contrasena",
            "token",
            "clave",
            "secreto",
        ],
    )
    def test_se_rechazan_las_claves_prohibidas(self, clave: str) -> None:
        with pytest.raises(ErrorMetadatosAuditoria, match="no admiten"):
            validar_metadatos({clave: "cualquier valor"})

    def test_el_error_falla_en_lugar_de_redactar(self) -> None:
        """Falla de forma explicita, no en silencio.

        Redactar sin avisar dejaria una auditoria incompleta y la impresion
        de que si se guardo el dato.
        """
        with pytest.raises(ErrorMetadatosAuditoria) as excinfo:
            construir_entrada(
                accion=AccionAuditada.NOTA_CREADA,
                principal=_principal_profesional(),
                ahora=AHORA,
                diagnostico="cualquier diagnostico",
            )
        assert "referencias" in str(excinfo.value)

    def test_se_admiten_referencias_y_contadores(self) -> None:
        entrada = construir_entrada(
            accion=AccionAuditada.TOMAS_GENERADAS,
            principal=_principal_profesional(),
            ahora=AHORA,
            receta_id=str(uuid.uuid4()),
            cantidad_tomas=42,
            frecuencia_tipo="CADA_N_HORAS",
        )
        assert entrada.metadatos["cantidad_tomas"] == 42
        assert entrada.metadatos["frecuencia_tipo"] == "CADA_N_HORAS"

    def test_metadatos_vacios_son_validos(self) -> None:
        validar_metadatos({})


class TestAlertas:
    @pytest.mark.parametrize("accion", sorted(ACCIONES_CON_ALERTA, key=str))
    def test_las_acciones_sensibles_generan_alerta(self, accion: AccionAuditada) -> None:
        """Descubrirlas en una revision mensual llega tarde."""
        entrada = construir_entrada(accion=accion, principal=_principal_profesional(), ahora=AHORA)
        assert entrada.requiere_alerta

    def test_una_accion_rutinaria_no_genera_alerta(self) -> None:
        entrada = construir_entrada(
            accion=AccionAuditada.CITA_CREADA,
            principal=_principal_profesional(),
            ahora=AHORA,
        )
        assert not entrada.requiere_alerta

    def test_las_acciones_criticas_estan_en_la_lista(self) -> None:
        """Comprueba que no se haya olvidado ninguna de las importantes."""
        for accion in (
            AccionAuditada.TOKEN_REUTILIZADO,
            AccionAuditada.ACCESO_EMERGENCIA,
            AccionAuditada.WEBHOOK_FIRMA_INVALIDA,
            AccionAuditada.INYECCION_DETECTADA,
            AccionAuditada.HERRAMIENTA_DENEGADA,
        ):
            assert accion in ACCIONES_CON_ALERTA, (
                f"{accion} debe generar alerta, no solo quedar registrada."
            )


class TestCatalogoDeAcciones:
    def test_los_codigos_son_unicos(self) -> None:
        valores = [a.value for a in AccionAuditada]
        assert len(valores) == len(set(valores))

    def test_existen_acciones_de_lectura(self) -> None:
        """Lo habitual es auditar solo escrituras.

        Pero la pregunta que importa ante una queja de privacidad es «quien
        vio esto», no «quien lo cambio».
        """
        lecturas = [
            AccionAuditada.HISTORIA_CONSULTADA,
            AccionAuditada.PACIENTE_CONSULTADO,
            AccionAuditada.CONSULTA_RAG,
            AccionAuditada.PREDICCION_CONSULTADA,
        ]
        for accion in lecturas:
            assert accion in AccionAuditada

    def test_el_formato_es_recurso_accion(self) -> None:
        for accion in AccionAuditada:
            assert "." in accion.value, f"{accion.name} no sigue recurso.accion"
