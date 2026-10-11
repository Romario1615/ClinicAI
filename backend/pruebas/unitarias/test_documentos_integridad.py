"""Integridad de exportaciones; todos los datos son sintéticos."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from io import BytesIO

import pytest
from pypdf import PdfReader

from app.modulos.documentos.esquemas import PresupuestoDesdePlan
from app.modulos.documentos.fuente_pdf import fuente_pdf
from app.modulos.documentos.modelos import RegistroPaciente
from app.modulos.documentos.pdf import generar_pdf
from app.modulos.documentos.servicios import (
    documento_verificable,
    pdf_registro,
    presupuesto_del_plan,
    verificar_identidad,
)
from app.modulos.odontologia.modelos import PlanTratamiento, ProcedimientoPlan
from app.modulos.pacientes.modelos import Paciente
from app.nucleo.errores import DatosInvalidos


@pytest.mark.parametrize("documento", [None, "", "12", "   ", "AB-1", "ZZ€1"])
def test_identidad_sin_referencia_nunca_se_verifica(documento):
    paciente = Paciente(fecha_nacimiento=None, numero_documento=documento)
    assert documento_verificable(paciente) is None
    assert not verificar_identidad(paciente, date(1990, 1, 1), None)
    assert not verificar_identidad(paciente, None, "AB12")


def test_nacimiento_registrado_tiene_prioridad_sobre_documento():
    paciente = Paciente(fecha_nacimiento=date(1990, 4, 12), numero_documento="QA-AB12")
    assert verificar_identidad(paciente, date(1990, 4, 12), None)
    assert not verificar_identidad(paciente, None, "AB12")
    assert not verificar_identidad(paciente, date(1990, 1, 1), "AB12")


@pytest.mark.parametrize(
    "zona, esperado",
    [
        ("America/Guayaquil", "09/10/2026 21:30 -0500"),
        ("Europe/Madrid", "10/10/2026 04:30 +0200"),
        ("UTC", "10/10/2026 02:30 +0000"),
    ],
)
def test_pdf_fecha_local_y_ausencias_sin_inventar_duracion(zona, esperado):
    fila = RegistroPaciente(
        id=uuid.uuid4(),
        raiz_id=uuid.uuid4(),
        tipo="RECETA",
        titulo="Receta sintética",
        version=1,
        vigente=True,
        anulado=False,
        creado_en=datetime(2026, 10, 10, 2, 30, tzinfo=UTC),
        contenido={
            "clinica": "Clínica sintética",
            "paciente": "Paciente sintético",
            "profesional": "Profesional sintético",
            "documento": None,
            "medicamentos": [
                {
                    "nombre": "Producto sintético",
                    "dosis": "Texto de prueba: 5 μg",
                    "via": "Sintética",
                    "cuando_sea_necesario": True,
                    "duracion_dias": None,
                }
            ],
        },
    )
    texto = "\n".join(p.extract_text() for p in PdfReader(BytesIO(pdf_registro(fila, zona))).pages)
    assert f"Emitido: {esperado} ({zona})" in texto
    assert "Documento: No registrado" in texto and "None" not in texto
    assert "Duración: no indicada en la receta confirmada" in texto
    assert "Texto de prueba: 5 μg" in texto


def test_pdf_rechaza_zona_invalida():
    fila = RegistroPaciente(
        creado_en=datetime(2026, 10, 10, tzinfo=UTC), contenido={"zona_horaria": "Zona/Inexistente"}
    )
    with pytest.raises(DatosInvalidos, match="zona horaria"):
        pdf_registro(fila)


@pytest.mark.parametrize("campo", ["descripcion", "precio", "titulo", "observaciones", "partidas"])
def test_presupuesto_de_plan_rechaza_limites_sin_truncar(campo):
    plan = PlanTratamiento(
        id=uuid.uuid4(),
        titulo="Plan sintético",
        moneda="USD",
        nivel_sensibilidad="N2",
        observaciones="",
    )
    procedimiento = ProcedimientoPlan(
        descripcion="Concepto sintético", precio=Decimal("10.25"), estado="PENDIENTE"
    )
    procedimientos = [procedimiento]
    if campo == "descripcion":
        procedimiento.descripcion = "X" * 301
    elif campo == "precio":
        procedimiento.precio = Decimal("1000000")
    elif campo == "titulo":
        plan.titulo = "X" * 201
    elif campo == "observaciones":
        plan.observaciones = "X" * 4000
    elif campo == "partidas":
        procedimientos = [procedimiento] * 101
    with pytest.raises(DatosInvalidos, match="límites del presupuesto"):
        presupuesto_del_plan(
            plan,
            procedimientos,
            uuid.uuid4(),
            PresupuestoDesdePlan(clave_idempotencia=uuid.uuid4()),
        )


@pytest.mark.parametrize(
    "texto",
    ["Ancho " * 100, "WW" * 200, "\n\nÚltimo\n", "Opción\r\nSiguiente", "Unidad cm² μg ≤ ≥"],
)
def test_lineas_respetan_ancho_y_saltos(texto):
    fuente = fuente_pdf()
    filas = fuente.filas(texto)
    assert all(fuente.ancho(fila, 11) <= 511 for fila in filas)
    assert "".join("".join(filas).split()) == "".join(fuente.normalizar(texto).split())
    if texto.startswith("\n\n"):
        assert filas[:2] == ["", ""] and filas[-1] == ""


def test_pdf_mapa_conserva_texto_y_referencias_de_zonas():
    pdf = PdfReader(
        BytesIO(
            generar_pdf("Faciograma sintético", ["Texto μg"], {"pomulo_derecho": "OBSERVACION"})
        )
    )
    assert len(pdf.pages) == 2
    assert "Pómulo derecho" in pdf.pages[1].extract_text()
    assert "no son puntos de inyección" in pdf.pages[1].extract_text()
