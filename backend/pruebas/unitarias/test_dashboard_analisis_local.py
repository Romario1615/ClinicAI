"""El análisis local del panel describe solo agregados operativos."""

from datetime import UTC, datetime
from decimal import Decimal

from app.modulos.dashboard.analisis_local import generar_hallazgos
from app.modulos.dashboard.esquemas import ResumenDashboard


def _resumen(
    *,
    citas: dict[str, int] | None = None,
    total: int = 0,
    pacientes: int = 0,
    personas_en_espera: int = 0,
    espera_mayor_15: int = 0,
    promedio: int | None = None,
    turnos_liberados: int | None = 0,
    turnos_recuperados: int | None = 0,
    promedio_recuperacion: int | None = None,
    adherencia: dict[str, int | float | None] | None = None,
    pagos: dict[str, Decimal] | None = None,
) -> ResumenDashboard:
    return ResumenDashboard(
        desde=datetime(2026, 10, 1, tzinfo=UTC),
        hasta=datetime(2026, 10, 2, tzinfo=UTC),
        citas=citas or {},
        total_citas=total,
        pacientes=pacientes,
        pacientes_nuevos=None,
        pacientes_recurrentes=None,
        espera={
            "promedio_minutos": promedio,
            "personas_en_espera": personas_en_espera,
            "espera_mayor_15_minutos": espera_mayor_15,
        },
        recuperacion_turnos={
            "turnos_liberados": turnos_liberados,
            "turnos_recuperados": turnos_recuperados,
            "promedio_minutos_para_recuperar": promedio_recuperacion,
        },
        ocupacion_agenda={
            "minutos_disponibles": 0,
            "minutos_ocupados": 0,
            "porcentaje": None,
            "detalle": "Sin horarios para la prueba.",
        },
        adherencia=adherencia,
        pagos=pagos,
        tendencia_diaria=[],
        por_hora=[],
        por_dia_semana=[],
    )


def test_sin_citas_pide_revisar_el_periodo() -> None:
    assert "amplía el periodo" in generar_hallazgos(_resumen())[0]


def test_identifica_inasistencia_y_espera_prioritaria() -> None:
    hallazgos = generar_hallazgos(
        _resumen(
            citas={"CONFIRMED": 8, "NO_SHOW": 2},
            total=10,
            pacientes=9,
            personas_en_espera=3,
            espera_mayor_15=1,
        )
    )
    assert any("2 inasistencias (20%" in item for item in hallazgos)
    assert any("1 persona en espera supera 15 minutos" in item for item in hallazgos)


def test_muestra_espera_promedio_sin_inventar_pacientes() -> None:
    hallazgos = generar_hallazgos(
        _resumen(citas={"COMPLETED": 2}, total=2, pacientes=2, promedio=22)
    )
    assert any("espera promedio fue de 22 minutos" in item for item in hallazgos)
    assert len(hallazgos) <= 4


def test_resume_turnos_liberados_y_recuperados_sin_inferir_causas() -> None:
    hallazgos = generar_hallazgos(
        _resumen(
            citas={"CONFIRMED": 2},
            total=2,
            pacientes=2,
            turnos_liberados=4,
            turnos_recuperados=3,
        )
    )
    assert any("Se liberaron 4 turnos y se recuperaron 3" in item for item in hallazgos)


def test_resume_adherencia_como_registro_administrativo() -> None:
    hallazgos = generar_hallazgos(
        _resumen(
            citas={"CONFIRMED": 2},
            total=2,
            pacientes=2,
            adherencia={
                "tomas_confirmadas": 8,
                "tomas_omitidas": 2,
                "porcentaje_registro_positivo": 80,
                "seguimientos_pendientes": 1,
            },
        )
    )
    assert any(
        "8 tomas confirmadas, 2 omitidas y 1 seguimiento pendiente" in item for item in hallazgos
    )


def test_no_expone_importes_si_el_principal_no_tiene_ese_permiso() -> None:
    hallazgos = generar_hallazgos(_resumen(citas={"CONFIRMED": 1}, total=1, pacientes=1))
    assert all("USD" not in item for item in hallazgos)


def test_resume_importes_en_revision_solo_si_vienen_autorizados() -> None:
    hallazgos = generar_hallazgos(
        _resumen(
            citas={"CONFIRMED": 1},
            total=1,
            pacientes=1,
            pagos={"PENDING": Decimal("24.50"), "CONFIRMED": Decimal("40.00")},
        )
    )
    assert any("USD 24.50" in item for item in hallazgos)
    assert all("USD 40.00" not in item for item in hallazgos)
