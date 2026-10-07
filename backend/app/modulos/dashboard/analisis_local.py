"""Lecturas descriptivas del tablero que no dependen de un modelo externo."""

from app.modulos.dashboard.esquemas import ResumenDashboard

UMBRAL_ESPERA_MINUTOS = 15


def _hallazgo_adherencia(resumen: ResumenDashboard) -> str | None:
    datos = resumen.adherencia
    if datos is None or not (
        datos.tomas_confirmadas or datos.tomas_omitidas or datos.seguimientos_pendientes
    ):
        return None
    seguimientos = (
        "1 seguimiento pendiente"
        if datos.seguimientos_pendientes == 1
        else f"{datos.seguimientos_pendientes} seguimientos pendientes"
    )
    return (
        f"Registro de medicación: {datos.tomas_confirmadas} tomas confirmadas, "
        f"{datos.tomas_omitidas} omitidas y {seguimientos}."
    )


def generar_hallazgos(resumen: ResumenDashboard) -> list[str]:
    """Resume señales operativas agregadas y propone comprobaciones administrativas.

    No infiere causas, no predice resultados y no emite recomendaciones clínicas.
    Los importes solo aparecen cuando el resumen ya los autorizó.
    """
    if resumen.total_citas == 0:
        hallazgos = [
            "No hay citas registradas en el periodo seleccionado. Comprueba las fechas o amplía el periodo."
        ]
        if (
            resumen.recuperacion_turnos.turnos_liberados is not None
            and resumen.recuperacion_turnos.turnos_liberados > 0
        ):
            hallazgos.append(
                f"Se liberaron {resumen.recuperacion_turnos.turnos_liberados} turnos y se "
                f"recuperaron {resumen.recuperacion_turnos.turnos_recuperados} mediante lista de espera."
            )
        hallazgo = _hallazgo_adherencia(resumen)
        if hallazgo is not None:
            hallazgos.append(hallazgo)
        return hallazgos

    citas = "cita" if resumen.total_citas == 1 else "citas"
    pacientes = "paciente distinto" if resumen.pacientes == 1 else "pacientes distintos"
    verbo_cita = "registró" if resumen.total_citas == 1 else "registraron"
    hallazgos = [
        f"Se {verbo_cita} {resumen.total_citas} {citas} de {resumen.pacientes} {pacientes}."
    ]

    inasistencias = resumen.citas.get("NO_SHOW", 0)
    if inasistencias:
        porcentaje = round(inasistencias * 100 / resumen.total_citas)
        hallazgos.append(
            f"Hay {inasistencias} inasistencias ({porcentaje}% de las citas); revisa la confirmación y los recordatorios."
        )

    if resumen.espera.espera_mayor_15_minutos:
        cantidad = resumen.espera.espera_mayor_15_minutos
        personas = "persona" if cantidad == 1 else "personas"
        verbo = "supera" if cantidad == 1 else "superan"
        hallazgos.append(
            f"{cantidad} {personas} en espera {verbo} {UMBRAL_ESPERA_MINUTOS} minutos; "
            "conviene revisar primero esos casos en Agenda."
        )
    elif resumen.espera.personas_en_espera:
        cantidad = resumen.espera.personas_en_espera
        personas = "persona" if cantidad == 1 else "personas"
        hallazgos.append(
            f"Hay {cantidad} {personas} en sala sin iniciar atención; revisa la cola actual en Agenda."
        )
    elif (
        resumen.espera.promedio_minutos is not None
        and resumen.espera.promedio_minutos > UMBRAL_ESPERA_MINUTOS
    ):
        hallazgos.append(
            f"La espera promedio fue de {resumen.espera.promedio_minutos} minutos; revisa la distribución de turnos."
        )

    recuperacion = resumen.recuperacion_turnos
    if recuperacion.turnos_liberados is not None and recuperacion.turnos_liberados > 0:
        hallazgos.append(
            f"Se liberaron {recuperacion.turnos_liberados} turnos y se recuperaron "
            f"{recuperacion.turnos_recuperados} mediante lista de espera."
        )

    hallazgo_adherencia = _hallazgo_adherencia(resumen)
    if hallazgo_adherencia is not None:
        hallazgos.append(hallazgo_adherencia)

    if resumen.pagos is not None:
        importes_en_revision = sum(
            (
                resumen.pagos.get(estado, 0)
                for estado in ("PENDING", "PROOF_RECEIVED", "UNDER_REVIEW")
            ),
            start=0,
        )
        if importes_en_revision:
            hallazgos.append(
                f"Los pagos pendientes o en revisión suman USD {importes_en_revision:.2f}; consulta la bandeja de Pagos."
            )

    if len(hallazgos) == 1:
        hallazgos.append(
            "No aparecen alertas de espera, inasistencia ni pagos por revisar en las métricas disponibles."
        )
    return hallazgos[:4]
