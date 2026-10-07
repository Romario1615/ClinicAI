"""Pruebas de las garantias clinicas, contra PostgreSQL real.

Estas tres reglas pueden hacer dano a un paciente si se incumplen, y por eso
viven en el motor y no en Python. Lo que se verifica aqui es que **el motor**
las hace cumplir, no que el servicio las recuerde: se escribe directamente
contra las tablas, saltandose cualquier capa de servicio, que es exactamente
lo que haria un script de migracion de datos o una tarea de mantenimiento
escrita con prisa.

1. Una nota clinica no se modifica ni se borra.
2. Solo una receta confirmada genera calendario de tomas.
3. Un medicamento «cuando sea necesario» no genera tomas programadas.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.historia.modelos import (
    AlertaAdherencia,
    Diagnostico,
    EstadoReceta,
    EstadoToma,
    NotaEvolucion,
    Receta,
    RecetaMedicamento,
    Toma,
)

pytestmark = [pytest.mark.integracion, pytest.mark.seguridad, pytest.mark.asyncio]

AHORA = datetime(2026, 4, 15, 14, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
#  Fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def nota(sesion: AsyncSession, clinica, paciente, profesional) -> NotaEvolucion:  # type: ignore[no-untyped-def]
    """Primera version de una nota.

    `raiz_id` apunta a si misma: asi `WHERE raiz_id = X` devuelve el hilo
    completo, incluida la original, sin una columna anulable de por medio.
    """
    registro = NotaEvolucion(
        clinica_id=clinica.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        # `raiz_id` se omite a proposito: lo rellena el disparador BEFORE
        # INSERT con el propio identificador. Fijarlo despues seria imposible,
        # porque el disparador de inmutabilidad rechaza el UPDATE.
        version=1,
        vigente=True,
        motivo_consulta="Control de prueba",
        subjetivo="Texto de prueba sin contenido clinico real.",
    )
    sesion.add(registro)
    await sesion.flush()
    assert registro.raiz_id == registro.id, "el disparador no relleno la raiz"
    return registro


@pytest_asyncio.fixture
async def receta_borrador(sesion: AsyncSession, clinica, paciente, profesional) -> Receta:  # type: ignore[no-untyped-def]
    registro = Receta(
        clinica_id=clinica.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        estado=EstadoReceta.BORRADOR.value,
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


@pytest_asyncio.fixture
async def medicamento_pauta_fija(
    sesion: AsyncSession, receta_borrador: Receta
) -> RecetaMedicamento:
    registro = RecetaMedicamento(
        receta_id=receta_borrador.id,
        nombre="Medicamento de ejemplo A",
        dosis="1 comprimido",
        via="ORAL",
        cuando_sea_necesario=False,
        frecuencia_horas=12,
        duracion_dias=7,
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


@pytest_asyncio.fixture
async def medicamento_prn(sesion: AsyncSession, receta_borrador: Receta) -> RecetaMedicamento:
    registro = RecetaMedicamento(
        receta_id=receta_borrador.id,
        nombre="Medicamento de ejemplo B",
        dosis="1 comprimido",
        via="ORAL",
        cuando_sea_necesario=True,
        frecuencia_horas=None,
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


async def _confirmar(sesion: AsyncSession, receta: Receta, profesional_id: uuid.UUID) -> None:
    receta.estado = EstadoReceta.CONFIRMADA.value
    receta.confirmada_en = AHORA
    receta.confirmada_por = profesional_id
    await sesion.flush()


# ===========================================================================
#  Regla 1: la historia clinica es append-only
# ===========================================================================
class TestNotaInmutable:
    async def test_no_se_puede_modificar_el_contenido(
        self, sesion: AsyncSession, nota: NotaEvolucion
    ) -> None:
        """Corregir una nota crea una version nueva; no reescribe la anterior.

        Se intenta con SQL directo, saltandose el servicio: es lo que haria
        un script de mantenimiento, y es justo el caso que el disparador tiene
        que cubrir.
        """
        with pytest.raises(DBAPIError, match="no se modifica"):
            await sesion.execute(
                sa.text("UPDATE nota_evolucion SET subjetivo = 'texto alterado' WHERE id = :id"),
                {"id": nota.id},
            )
        await sesion.rollback()

    async def test_no_se_puede_borrar(self, sesion: AsyncSession, nota: NotaEvolucion) -> None:
        with pytest.raises(DBAPIError, match="no se borra"):
            await sesion.execute(
                sa.text("DELETE FROM nota_evolucion WHERE id = :id"), {"id": nota.id}
            )
        await sesion.rollback()

    async def test_si_se_puede_marcar_como_no_vigente(
        self, sesion: AsyncSession, nota: NotaEvolucion
    ) -> None:
        """La unica modificacion permitida.

        Es la que hace falta para crear la version siguiente. Sin esta
        excepcion, el versionado seria imposible: habria que borrar y
        reinsertar, que es justo lo que el disparador impide.
        """
        await sesion.execute(
            sa.text("UPDATE nota_evolucion SET vigente = false WHERE id = :id"),
            {"id": nota.id},
        )
        await sesion.flush()

        vigente = (
            await sesion.execute(
                sa.text("SELECT vigente FROM nota_evolucion WHERE id = :id"), {"id": nota.id}
            )
        ).scalar_one()
        assert vigente is False

    async def test_no_se_puede_cambiar_el_contenido_al_marcar_no_vigente(
        self, sesion: AsyncSession, nota: NotaEvolucion
    ) -> None:
        """La excepcion es estrecha a proposito.

        Si permitiera cualquier UPDATE que ademas pusiera `vigente = false`,
        seria una puerta trasera para reescribir el contenido.
        """
        with pytest.raises(DBAPIError, match="no se modifica"):
            await sesion.execute(
                sa.text(
                    "UPDATE nota_evolucion SET vigente = false, subjetivo = 'alterado' "
                    "WHERE id = :id"
                ),
                {"id": nota.id},
            )
        await sesion.rollback()

    async def test_una_version_nueva_exige_motivo(
        self,
        sesion: AsyncSession,
        nota: NotaEvolucion,
        clinica,
        paciente,
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        """Sin motivo no se puede explicar por que cambio una nota clinica."""
        sesion.add(
            NotaEvolucion(
                clinica_id=clinica.id,
                paciente_id=paciente.id,
                profesional_id=profesional.id,
                raiz_id=nota.raiz_id,
                version=2,
                vigente=False,
                motivo_modificacion=None,
                subjetivo="Correccion",
            )
        )
        with pytest.raises(IntegrityError, match="modificacion_exige_motivo"):
            await sesion.flush()
        await sesion.rollback()

    async def test_solo_una_version_vigente_por_nota(
        self,
        sesion: AsyncSession,
        nota: NotaEvolucion,
        clinica,
        paciente,
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        """Dos versiones vigentes harian ambigua cual es la nota actual.

        Y en una historia clinica, «cual es la version actual» no admite
        ambiguedad.
        """
        sesion.add(
            NotaEvolucion(
                clinica_id=clinica.id,
                paciente_id=paciente.id,
                profesional_id=profesional.id,
                raiz_id=nota.raiz_id,
                version=2,
                vigente=True,
                motivo_modificacion="Correccion de la fecha indicada",
                subjetivo="Correccion",
            )
        )
        with pytest.raises(IntegrityError, match="ix_nota_vigente_unica"):
            await sesion.flush()
        await sesion.rollback()

    async def test_el_versionado_completo_funciona(
        self,
        sesion: AsyncSession,
        nota: NotaEvolucion,
        clinica,
        paciente,
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        """Recorrido real: marcar la anterior y crear la siguiente."""
        raiz = nota.raiz_id

        await sesion.execute(
            sa.text("UPDATE nota_evolucion SET vigente = false WHERE id = :id"),
            {"id": nota.id},
        )
        segunda = NotaEvolucion(
            clinica_id=clinica.id,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            raiz_id=raiz,
            version=2,
            vigente=True,
            motivo_modificacion="Se corrigio la fecha de control indicada",
            subjetivo="Texto corregido.",
        )
        sesion.add(segunda)
        await sesion.flush()

        # `populate_existing` refresca los objetos que ya estan en el mapa de
        # identidad. Sin el, la primera version vendria de la memoria de
        # Python con `vigente = True` y la prueba mediria la cache en lugar
        # del estado de la base -- que es justo lo que se quiere comprobar.
        versiones = list(
            (
                await sesion.execute(
                    sa.select(NotaEvolucion)
                    .where(NotaEvolucion.raiz_id == raiz)
                    .order_by(NotaEvolucion.version)
                    .execution_options(populate_existing=True)
                )
            ).scalars()
        )
        assert [v.version for v in versiones] == [1, 2]
        # La version anterior conserva su contenido intacto.
        assert versiones[0].subjetivo == "Texto de prueba sin contenido clinico real."
        assert versiones[1].subjetivo == "Texto corregido."
        assert [v.vigente for v in versiones] == [False, True]

    async def test_el_diagnostico_se_ata_a_la_version(
        self, sesion: AsyncSession, nota: NotaEvolucion
    ) -> None:
        """Un diagnostico que cambiara retroactivamente en el historico haria
        imposible reconstruir que se sabia en cada momento."""
        sesion.add(
            Diagnostico(
                nota_id=nota.id,
                codigo_cie10="Z00.0",
                descripcion="Examen general de rutina (ejemplo)",
                principal=True,
            )
        )
        await sesion.flush()

        total = (
            await sesion.execute(
                sa.select(sa.func.count())
                .select_from(Diagnostico)
                .where(Diagnostico.nota_id == nota.id)
            )
        ).scalar_one()
        assert total == 1


# ===========================================================================
#  Regla 2: solo una receta confirmada genera tomas
# ===========================================================================
class TestRecetaConfirmada:
    async def test_un_borrador_no_genera_tomas(
        self,
        sesion: AsyncSession,
        medicamento_pauta_fija: RecetaMedicamento,
        paciente,  # type: ignore[no-untyped-def]
    ) -> None:
        """Avisar desde un borrador seria decirle al paciente que tome algo
        que nadie le ha indicado todavia."""
        sesion.add(
            Toma(
                receta_medicamento_id=medicamento_pauta_fija.id,
                paciente_id=paciente.id,
                programada_en=AHORA + timedelta(hours=12),
            )
        )
        with pytest.raises(DBAPIError, match="Solo una receta confirmada"):
            await sesion.flush()
        await sesion.rollback()

    async def test_una_receta_confirmada_si_genera_tomas(
        self,
        sesion: AsyncSession,
        receta_borrador: Receta,
        medicamento_pauta_fija: RecetaMedicamento,
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        await _confirmar(sesion, receta_borrador, profesional.id)

        sesion.add(
            Toma(
                receta_medicamento_id=medicamento_pauta_fija.id,
                paciente_id=paciente.id,
                programada_en=AHORA + timedelta(hours=12),
            )
        )
        await sesion.flush()

        # Acotado a este medicamento. Contar la tabla entera medía el estado de
        # la base de desarrollo -- contra la que corre esta suite -- y no lo que
        # la prueba afirma; pasaba solo mientras no hubiera datos sembrados.
        total = (
            await sesion.execute(
                sa.select(sa.func.count())
                .select_from(Toma)
                .where(Toma.receta_medicamento_id == medicamento_pauta_fija.id)
            )
        ).scalar_one()
        assert total == 1

    async def test_el_contenido_de_una_receta_confirmada_no_se_reescribe(
        self,
        sesion: AsyncSession,
        receta_borrador: Receta,
        medicamento_pauta_fija: RecetaMedicamento,
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        await _confirmar(sesion, receta_borrador, profesional.id)
        medicamento_pauta_fija.dosis = "2 comprimidos"

        with pytest.raises(DBAPIError, match="no se edita ni se elimina"):
            await sesion.flush()
        await sesion.rollback()

    async def test_una_receta_no_se_elimina_en_vez_de_conservar_el_historial(
        self,
        sesion: AsyncSession,
        receta_borrador: Receta,
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        await _confirmar(sesion, receta_borrador, profesional.id)
        await sesion.delete(receta_borrador)

        with pytest.raises(DBAPIError, match="Una receta no se elimina"):
            await sesion.flush()
        await sesion.rollback()

    async def test_una_receta_firmada_no_se_puede_reabrir(
        self,
        sesion: AsyncSession,
        receta_borrador: Receta,
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        await _confirmar(sesion, receta_borrador, profesional.id)
        receta_borrador.estado = EstadoReceta.BORRADOR.value

        with pytest.raises(DBAPIError, match="estado_receta_transicion_invalida"):
            await sesion.flush()
        await sesion.rollback()

    async def test_la_firma_no_se_registra_antes_de_confirmar(
        self,
        sesion: AsyncSession,
        receta_borrador: Receta,
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        receta_borrador.confirmada_en = AHORA
        receta_borrador.confirmada_por = profesional.id

        with pytest.raises(DBAPIError, match="receta_firma_fuera_de_transicion"):
            await sesion.flush()
        await sesion.rollback()

    async def test_no_se_inserta_un_borrador_con_firma_anticipada(
        self,
        sesion: AsyncSession,
        receta_borrador: Receta,
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        sesion.add(
            Receta(
                clinica_id=receta_borrador.clinica_id,
                paciente_id=receta_borrador.paciente_id,
                profesional_id=receta_borrador.profesional_id,
                estado=EstadoReceta.BORRADOR.value,
                confirmada_en=AHORA,
                confirmada_por=profesional.id,
            )
        )

        with pytest.raises(IntegrityError, match="borrador_sin_firma"):
            await sesion.flush()
        await sesion.rollback()

    async def test_confirmar_exige_responsable(
        self, sesion: AsyncSession, receta_borrador: Receta
    ) -> None:
        """Una receta confirmada sin responsable no tendria a quien atribuirse."""
        receta_borrador.estado = EstadoReceta.CONFIRMADA.value
        with pytest.raises(IntegrityError, match="confirmada_exige_responsable"):
            await sesion.flush()
        await sesion.rollback()

    async def test_suspender_exige_motivo(
        self, sesion: AsyncSession, receta_borrador: Receta
    ) -> None:
        receta_borrador.estado = EstadoReceta.SUSPENDIDA.value
        receta_borrador.suspendida_en = AHORA
        with pytest.raises(IntegrityError, match="suspension_exige_motivo"):
            await sesion.flush()
        await sesion.rollback()

    async def test_suspender_exige_instante(
        self, sesion: AsyncSession, receta_borrador: Receta
    ) -> None:
        receta_borrador.estado = EstadoReceta.SUSPENDIDA.value
        receta_borrador.motivo_suspension = "Motivo sintetico de prueba"
        with pytest.raises(IntegrityError, match="suspension_exige_instante"):
            await sesion.flush()
        await sesion.rollback()


# ===========================================================================
#  Regla 3: un PRN no tiene horarios fijos
# ===========================================================================
class TestMedicamentoPRN:
    async def test_un_prn_no_puede_llevar_frecuencia(
        self, sesion: AsyncSession, receta_borrador: Receta
    ) -> None:
        """Es una contradiccion: si hay que tomarlo cada ocho horas, no es
        «cuando sea necesario»."""
        sesion.add(
            RecetaMedicamento(
                receta_id=receta_borrador.id,
                nombre="Medicamento de ejemplo",
                dosis="1 comprimido",
                via="ORAL",
                cuando_sea_necesario=True,
                frecuencia_horas=8,
            )
        )
        with pytest.raises(IntegrityError, match="prn_sin_frecuencia"):
            await sesion.flush()
        await sesion.rollback()

    async def test_una_pauta_fija_exige_frecuencia(
        self, sesion: AsyncSession, receta_borrador: Receta
    ) -> None:
        """Sin frecuencia no se puede generar el calendario, y la linea
        quedaria como una indicacion que el sistema no puede recordar."""
        sesion.add(
            RecetaMedicamento(
                receta_id=receta_borrador.id,
                nombre="Medicamento de ejemplo",
                dosis="1 comprimido",
                via="ORAL",
                cuando_sea_necesario=False,
                frecuencia_horas=None,
            )
        )
        with pytest.raises(IntegrityError, match="pauta_fija_exige_frecuencia"):
            await sesion.flush()
        await sesion.rollback()

    async def test_un_prn_no_genera_tomas_ni_con_receta_confirmada(
        self,
        sesion: AsyncSession,
        receta_borrador: Receta,
        medicamento_prn: RecetaMedicamento,
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        """La regla que mas importa de las tres.

        Convertir un PRN en pauta fija es un error de medicacion: el paciente
        recibiria recordatorios para tomar algo que solo debia tomar si lo
        necesitaba.
        """
        await _confirmar(sesion, receta_borrador, profesional.id)

        sesion.add(
            Toma(
                receta_medicamento_id=medicamento_prn.id,
                paciente_id=paciente.id,
                programada_en=AHORA + timedelta(hours=8),
            )
        )
        with pytest.raises(DBAPIError, match="cuando sea necesario"):
            await sesion.flush()
        await sesion.rollback()

    @pytest.mark.parametrize("frecuencia", [0, 200])
    async def test_una_frecuencia_absurda_se_rechaza(
        self, sesion: AsyncSession, receta_borrador: Receta, frecuencia: int
    ) -> None:
        """Cero horas produciria un calendario infinito; 200 no es una pauta."""
        sesion.add(
            RecetaMedicamento(
                receta_id=receta_borrador.id,
                nombre="Medicamento de ejemplo",
                dosis="1 comprimido",
                via="ORAL",
                cuando_sea_necesario=False,
                frecuencia_horas=frecuencia,
            )
        )
        with pytest.raises(IntegrityError, match="frecuencia_razonable"):
            await sesion.flush()
        await sesion.rollback()


# ===========================================================================
#  Tomas y alertas
# ===========================================================================
class TestTomas:
    @pytest_asyncio.fixture
    async def medicamento_confirmado(
        self,
        sesion: AsyncSession,
        receta_borrador: Receta,
        medicamento_pauta_fija: RecetaMedicamento,
        profesional,  # type: ignore[no-untyped-def]
    ) -> RecetaMedicamento:
        await _confirmar(sesion, receta_borrador, profesional.id)
        return medicamento_pauta_fija

    async def test_no_se_duplica_una_toma_del_mismo_instante(
        self,
        sesion: AsyncSession,
        medicamento_confirmado: RecetaMedicamento,
        paciente,  # type: ignore[no-untyped-def]
    ) -> None:
        """Regenerar el calendario por error duplicaria los recordatorios.

        Y dos recordatorios de la misma toma llevan a tomar la dosis dos
        veces, o a dejar de mirar los avisos.
        """
        instante = AHORA + timedelta(hours=12)
        for _ in range(2):
            sesion.add(
                Toma(
                    receta_medicamento_id=medicamento_confirmado.id,
                    paciente_id=paciente.id,
                    programada_en=instante,
                )
            )
        with pytest.raises(IntegrityError, match="uq_toma_medicamento_instante"):
            await sesion.flush()
        await sesion.rollback()

    async def test_registrar_una_toma_exige_instante(
        self,
        sesion: AsyncSession,
        medicamento_confirmado: RecetaMedicamento,
        paciente,  # type: ignore[no-untyped-def]
    ) -> None:
        """Una toma marcada sin cuando no sirve para medir adherencia."""
        sesion.add(
            Toma(
                receta_medicamento_id=medicamento_confirmado.id,
                paciente_id=paciente.id,
                programada_en=AHORA + timedelta(hours=12),
                estado=EstadoToma.TOMADA.value,
                registrada_en=None,
            )
        )
        with pytest.raises(IntegrityError, match="registro_exige_instante"):
            await sesion.flush()
        await sesion.rollback()

    async def test_cancelar_una_toma_futura_no_exige_instante(
        self,
        sesion: AsyncSession,
        medicamento_confirmado: RecetaMedicamento,
        paciente,  # type: ignore[no-untyped-def]
    ) -> None:
        """Cancelar es lo que ocurre al modificar la receta: las tomas futuras
        pendientes se anulan, y no hay ningun instante de registro."""
        sesion.add(
            Toma(
                receta_medicamento_id=medicamento_confirmado.id,
                paciente_id=paciente.id,
                programada_en=AHORA + timedelta(days=3),
                estado=EstadoToma.CANCELADA.value,
            )
        )
        await sesion.flush()


class TestAlertas:
    @pytest_asyncio.fixture
    async def alerta(
        self,
        sesion: AsyncSession,
        receta_borrador: Receta,
        clinica,  # type: ignore[no-untyped-def]
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
    ) -> AlertaAdherencia:
        registro = AlertaAdherencia(
            clinica_id=clinica.id,
            paciente_id=paciente.id,
            receta_id=receta_borrador.id,
            profesional_id=profesional.id,
            tomas_omitidas=4,
            tomas_esperadas=14,
            periodo_desde=AHORA - timedelta(days=7),
            periodo_hasta=AHORA,
        )
        sesion.add(registro)
        await sesion.flush()
        return registro

    async def test_solo_una_alerta_abierta_por_receta(
        self,
        sesion: AsyncSession,
        alerta: AlertaAdherencia,
        clinica,  # type: ignore[no-untyped-def]
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        """Repetirla cada dia convertiria el aviso en ruido, y el profesional
        dejaria de mirarlo."""
        sesion.add(
            AlertaAdherencia(
                clinica_id=clinica.id,
                paciente_id=paciente.id,
                receta_id=alerta.receta_id,
                profesional_id=profesional.id,
                tomas_omitidas=5,
                tomas_esperadas=16,
                periodo_desde=AHORA - timedelta(days=8),
                periodo_hasta=AHORA,
            )
        )
        with pytest.raises(IntegrityError, match="ix_alerta_abierta_unica"):
            await sesion.flush()
        await sesion.rollback()

    async def test_una_alerta_se_atiende_pero_no_se_reescribe(
        self, sesion: AsyncSession, alerta: AlertaAdherencia
    ) -> None:
        """Si los recuentos pudieran cambiarse, el registro dejaria de servir
        para revisar despues que se vio y cuando."""
        with pytest.raises(DBAPIError, match="no se reescribe"):
            await sesion.execute(
                sa.text("UPDATE alerta_adherencia SET tomas_omitidas = 0 WHERE id = :id"),
                {"id": alerta.id},
            )
        await sesion.rollback()

    async def test_atenderla_si_esta_permitido(
        self,
        sesion: AsyncSession,
        alerta: AlertaAdherencia,
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        await sesion.execute(
            sa.text(
                "UPDATE alerta_adherencia SET atendida_en = :ahora, atendida_por = :quien, "
                "nota_profesional = :nota WHERE id = :id"
            ),
            {
                "ahora": AHORA,
                "quien": profesional.id,
                "nota": "Se conversa con el paciente sobre el horario de las tomas.",
                "id": alerta.id,
            },
        )
        await sesion.flush()

        atendida = (
            await sesion.execute(
                sa.text("SELECT atendida_en FROM alerta_adherencia WHERE id = :id"),
                {"id": alerta.id},
            )
        ).scalar_one()
        assert atendida is not None

    async def test_un_periodo_invertido_se_rechaza(
        self,
        sesion: AsyncSession,
        receta_borrador: Receta,
        clinica,  # type: ignore[no-untyped-def]
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        sesion.add(
            AlertaAdherencia(
                clinica_id=clinica.id,
                paciente_id=paciente.id,
                receta_id=receta_borrador.id,
                profesional_id=profesional.id,
                tomas_omitidas=1,
                tomas_esperadas=2,
                periodo_desde=AHORA,
                periodo_hasta=AHORA - timedelta(days=1),
            )
        )
        with pytest.raises(IntegrityError, match="periodo_coherente"):
            await sesion.flush()
        await sesion.rollback()
