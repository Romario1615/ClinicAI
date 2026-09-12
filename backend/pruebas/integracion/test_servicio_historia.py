"""Pruebas del servicio clinico.

Complementan las de `test_historia_clinica.py`: aquellas verifican que el
motor hace cumplir las garantias; estas, que el servicio se comporta bien
**antes** de llegar al motor, y que lo que devuelve es correcto.

Lo que mas importa aqui:

* La relacion asistencial. Sin ella, cualquier medico de la clinica leeria la
  historia de cualquier paciente: es el acceso indebido mas frecuente y el
  mas dificil de justificar despues.
* El agente de IA no puede escribir. Se comprueba con un principal de tipo
  agente, no confiando en que nadie le anada la herramienta.
* Suspender una receta cancela las tomas **futuras** y deja intactas las
  pasadas, que son el registro de lo que ocurrio.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.historia.modelos import EstadoReceta, EstadoToma, NotaEvolucion, Toma
from app.modulos.historia.repositorio import RepositorioHistoria
from app.modulos.historia.servicios import (
    MAXIMO_TOMAS_POR_MEDICAMENTO,
    DatosMedicamento,
    DatosNota,
    ServicioHistoria,
)
from app.modulos.pacientes.modelos import RelacionAsistencial
from app.nucleo.auditoria import AccionAuditada
from app.nucleo.autorizacion import Ambito, Principal, TipoActor
from app.nucleo.errores import (
    ConflictoEstado,
    MotivoModificacionRequerido,
    OperacionClinicaNoPermitida,
    PermisoDenegado,
    RecursoNoEncontrado,
    ReglaNegocioViolada,
    RelacionAsistencialRequerida,
)
from app.nucleo.reloj import RelojFijo

pytestmark = [pytest.mark.integracion, pytest.mark.seguridad, pytest.mark.asyncio]

AHORA = datetime(2026, 4, 15, 14, 0, tzinfo=UTC)

PERMISOS_CLINICOS = frozenset(
    {
        "historia_clinica.leer",
        "historia_clinica.escribir",
        "diagnostico.registrar",
        "receta.crear",
        "receta.confirmar",
        "receta.leer",
        "adherencia.leer",
    }
)


# ---------------------------------------------------------------------------
#  Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def reloj_fijo() -> RelojFijo:
    return RelojFijo(AHORA)


@pytest.fixture
def servicio_historia(sesion: AsyncSession, reloj_fijo: RelojFijo) -> ServicioHistoria:
    return ServicioHistoria(sesion, RepositorioHistoria(sesion), reloj_fijo)


@pytest.fixture
def principal_medico(clinica, sede, profesional) -> Principal:  # type: ignore[no-untyped-def]
    """Profesional con permisos clinicos completos.

    Lleva `profesional_id`, que es lo que activa la comprobacion de relacion
    asistencial.
    """
    return Principal(
        actor_tipo=TipoActor.USUARIO,
        actor_id=uuid.uuid4(),
        clinica_id=clinica.id,
        permisos=PERMISOS_CLINICOS,
        ambito=Ambito(
            clinica_id=clinica.id,
            sedes=frozenset({sede.id}),
            todas_las_especialidades=True,
            todos_los_profesionales=True,
            todos_los_pacientes=True,
        ),
        profesional_id=profesional.id,
    )


@pytest.fixture
def principal_agente(clinica) -> Principal:  # type: ignore[no-untyped-def]
    """Agente de IA con TODOS los permisos clinicos concedidos por error.

    El caso que la prueba cubre no es "el agente no tiene permisos" -- eso es
    trivial --, sino "aunque alguien se los conceda, sigue sin poder escribir".
    """
    return Principal(
        actor_tipo=TipoActor.AGENTE_IA,
        actor_id=uuid.uuid4(),
        clinica_id=clinica.id,
        permisos=PERMISOS_CLINICOS,
        ambito=Ambito(clinica_id=clinica.id, todos_los_pacientes=True),
    )


@pytest_asyncio.fixture
async def relacion(sesion: AsyncSession, paciente, profesional) -> RelacionAsistencial:  # type: ignore[no-untyped-def]
    registro = RelacionAsistencial(
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        origen="CITA",
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


def _datos_nota(paciente_id: uuid.UUID, profesional_id: uuid.UUID, **extra: object) -> DatosNota:
    base: dict[str, object] = {
        "paciente_id": paciente_id,
        "profesional_id": profesional_id,
        "tipo": "EVOLUCION",
        "motivo_consulta": "Control de prueba",
        "subjetivo": "Texto de prueba sin contenido clinico real.",
    }
    base.update(extra)
    return DatosNota(**base)  # type: ignore[arg-type]


# ===========================================================================
#  Relacion asistencial
# ===========================================================================
class TestRelacionAsistencial:
    async def test_sin_relacion_no_se_escribe(
        self,
        servicio_historia: ServicioHistoria,
        principal_medico: Principal,
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        """El permiso no basta: hace falta vinculo con ESE paciente.

        Sin este control, cualquier medico de la clinica escribiria en la
        historia de cualquier paciente.
        """
        with pytest.raises(RelacionAsistencialRequerida):
            await servicio_historia.crear_nota(
                _datos_nota(paciente.id, profesional.id), principal=principal_medico
            )

    async def test_con_relacion_si_se_escribe(
        self,
        servicio_historia: ServicioHistoria,
        principal_medico: Principal,
        relacion: RelacionAsistencial,
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        resultado = await servicio_historia.crear_nota(
            _datos_nota(paciente.id, profesional.id), principal=principal_medico
        )
        assert resultado.nota is not None
        assert resultado.nota.version == 1
        # El disparador rellena la raiz con el propio identificador.
        assert resultado.nota.raiz_id == resultado.nota.id

    async def test_una_relacion_revocada_no_da_acceso(
        self,
        sesion: AsyncSession,
        servicio_historia: ServicioHistoria,
        principal_medico: Principal,
        relacion: RelacionAsistencial,
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        relacion.revocada_en = AHORA
        await sesion.flush()

        with pytest.raises(RelacionAsistencialRequerida):
            await servicio_historia.crear_nota(
                _datos_nota(paciente.id, profesional.id), principal=principal_medico
            )

    async def test_una_relacion_caducada_no_da_acceso(
        self,
        sesion: AsyncSession,
        servicio_historia: ServicioHistoria,
        principal_medico: Principal,
        relacion: RelacionAsistencial,
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        """La derivacion de hace dos anos termino."""
        relacion.vigente_hasta = AHORA - timedelta(days=1)
        await sesion.flush()

        with pytest.raises(RelacionAsistencialRequerida):
            await servicio_historia.crear_nota(
                _datos_nota(paciente.id, profesional.id), principal=principal_medico
            )

    async def test_quien_no_es_profesional_no_necesita_relacion(
        self,
        sesion: AsyncSession,
        servicio_historia: ServicioHistoria,
        clinica,  # type: ignore[no-untyped-def]
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        """Un auditor no tiene relaciones asistenciales.

        Su acceso se controla por permiso y por auditoria, no por vinculo:
        exigirle una relacion le impediria revisar precisamente los accesos
        que tiene que revisar.
        """
        auditor = Principal(
            actor_tipo=TipoActor.USUARIO,
            actor_id=uuid.uuid4(),
            clinica_id=clinica.id,
            permisos=frozenset({"historia_clinica.leer"}),
            ambito=Ambito(clinica_id=clinica.id, todos_los_pacientes=True),
            profesional_id=None,
        )

        notas, auditoria = await servicio_historia.leer_historia(paciente.id, principal=auditor)
        assert notas == []
        assert auditoria[0].accion == AccionAuditada.HISTORIA_CONSULTADA


# ===========================================================================
#  La IA no escribe ni interpreta
# ===========================================================================
class TestFronteraDeLaIA:
    @pytest.mark.parametrize(
        "operacion",
        ["crear_nota", "versionar_nota", "crear_receta", "confirmar_receta", "suspender_receta"],
    )
    async def test_el_agente_no_puede_escribir_aunque_tenga_permisos(
        self,
        servicio_historia: ServicioHistoria,
        principal_agente: Principal,
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
        operacion: str,
    ) -> None:
        """La restriccion no es una instruccion al modelo: es una puerta.

        Al agente se le conceden aqui TODOS los permisos clinicos a proposito.
        La prueba no comprueba que le falten permisos -- eso seria trivial --,
        sino que aunque alguien se los conceda por error, sigue sin poder
        escribir informacion clinica (CLAUDE.md, regla 5).
        """
        datos = _datos_nota(paciente.id, profesional.id)

        with pytest.raises(OperacionClinicaNoPermitida):
            if operacion == "crear_nota":
                await servicio_historia.crear_nota(datos, principal=principal_agente)
            elif operacion == "versionar_nota":
                await servicio_historia.versionar_nota(
                    uuid.uuid4(), datos, principal=principal_agente, motivo="x"
                )
            elif operacion == "crear_receta":
                await servicio_historia.crear_receta(
                    principal=principal_agente,
                    paciente_id=paciente.id,
                    profesional_id=profesional.id,
                    medicamentos=[
                        DatosMedicamento(nombre="X", dosis="1", via="ORAL", frecuencia_horas=12)
                    ],
                )
            elif operacion == "confirmar_receta":
                await servicio_historia.confirmar_receta(
                    uuid.uuid4(), principal=principal_agente, profesional_id=profesional.id
                )
            else:
                await servicio_historia.suspender_receta(
                    uuid.uuid4(), principal=principal_agente, motivo="x"
                )

    async def test_el_agente_tampoco_lee_la_historia(
        self,
        servicio_historia: ServicioHistoria,
        principal_agente: Principal,
        paciente,  # type: ignore[no-untyped-def]
    ) -> None:
        with pytest.raises(OperacionClinicaNoPermitida):
            await servicio_historia.leer_historia(paciente.id, principal=principal_agente)


# ===========================================================================
#  Versionado
# ===========================================================================
class TestVersionado:
    @pytest_asyncio.fixture
    async def nota_inicial(
        self,
        servicio_historia: ServicioHistoria,
        principal_medico: Principal,
        relacion: RelacionAsistencial,
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
    ) -> NotaEvolucion:
        resultado = await servicio_historia.crear_nota(
            _datos_nota(paciente.id, profesional.id), principal=principal_medico
        )
        assert resultado.nota is not None
        return resultado.nota

    async def test_corregir_sin_motivo_se_rechaza(
        self,
        servicio_historia: ServicioHistoria,
        principal_medico: Principal,
        nota_inicial: NotaEvolucion,
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        with pytest.raises(MotivoModificacionRequerido):
            await servicio_historia.versionar_nota(
                nota_inicial.raiz_id,
                _datos_nota(paciente.id, profesional.id),
                principal=principal_medico,
                motivo="   ",
            )

    async def test_corregir_crea_version_y_conserva_la_anterior(
        self,
        sesion: AsyncSession,
        servicio_historia: ServicioHistoria,
        principal_medico: Principal,
        nota_inicial: NotaEvolucion,
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        raiz = nota_inicial.raiz_id
        resultado = await servicio_historia.versionar_nota(
            raiz,
            _datos_nota(paciente.id, profesional.id, subjetivo="Texto corregido."),
            principal=principal_medico,
            motivo="Se corrigio la fecha de control indicada",
        )

        assert resultado.nota is not None
        assert resultado.nota.version == 2
        assert resultado.auditoria[0].accion == AccionAuditada.NOTA_VERSIONADA

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
        assert len(versiones) == 2
        assert versiones[0].subjetivo == "Texto de prueba sin contenido clinico real."
        assert versiones[0].vigente is False
        assert versiones[1].subjetivo == "Texto corregido."
        assert versiones[1].motivo_modificacion is not None

    async def test_leer_la_historia_deja_auditoria(
        self,
        servicio_historia: ServicioHistoria,
        principal_medico: Principal,
        nota_inicial: NotaEvolucion,
        paciente,  # type: ignore[no-untyped-def]
    ) -> None:
        """Es la unica forma de responder a «quien vio mis datos»."""
        notas, auditoria = await servicio_historia.leer_historia(
            paciente.id, principal=principal_medico
        )

        assert len(notas) == 1
        assert auditoria[0].accion == AccionAuditada.HISTORIA_CONSULTADA
        assert auditoria[0].paciente_id == paciente.id
        assert auditoria[0].nivel_sensibilidad is not None

    async def test_el_historico_devuelve_todas_las_versiones(
        self,
        servicio_historia: ServicioHistoria,
        principal_medico: Principal,
        nota_inicial: NotaEvolucion,
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        await servicio_historia.versionar_nota(
            nota_inicial.raiz_id,
            _datos_nota(paciente.id, profesional.id, subjetivo="Corregido"),
            principal=principal_medico,
            motivo="Correccion",
        )

        vigentes, _ = await servicio_historia.leer_historia(paciente.id, principal=principal_medico)
        completas, _ = await servicio_historia.leer_historia(
            paciente.id, principal=principal_medico, incluir_historico=True
        )

        assert len(vigentes) == 1
        assert len(completas) == 2


# ===========================================================================
#  Recetas y tomas
# ===========================================================================
class TestRecetas:
    @pytest_asyncio.fixture
    async def receta_con_pauta(
        self,
        servicio_historia: ServicioHistoria,
        principal_medico: Principal,
        relacion: RelacionAsistencial,
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
    ):  # type: ignore[no-untyped-def]
        resultado = await servicio_historia.crear_receta(
            principal=principal_medico,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            medicamentos=[
                DatosMedicamento(
                    nombre="Medicamento de ejemplo A",
                    dosis="1 comprimido",
                    via="ORAL",
                    frecuencia_horas=12,
                    duracion_dias=3,
                ),
                DatosMedicamento(
                    nombre="Medicamento de ejemplo B",
                    dosis="1 comprimido",
                    via="ORAL",
                    cuando_sea_necesario=True,
                ),
            ],
        )
        assert resultado.receta is not None
        return resultado.receta

    async def test_una_receta_nace_en_borrador(self, receta_con_pauta) -> None:  # type: ignore[no-untyped-def]
        """Nunca confirmada de entrada: la confirmacion es un acto distinto."""
        assert receta_con_pauta.estado == EstadoReceta.BORRADOR.value
        assert receta_con_pauta.confirmada_en is None

    async def test_un_borrador_no_tiene_tomas(self, sesion: AsyncSession, receta_con_pauta) -> None:  # type: ignore[no-untyped-def]
        total = (await sesion.execute(sa.select(sa.func.count()).select_from(Toma))).scalar_one()
        assert total == 0

    async def test_confirmar_genera_las_tomas_de_la_pauta_fija(
        self,
        sesion: AsyncSession,
        servicio_historia: ServicioHistoria,
        principal_medico: Principal,
        receta_con_pauta,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        """Y **ninguna** para el PRN.

        3 dias cada 12 horas = 6 tomas. El «cuando sea necesario» no genera
        ninguna: convertirlo en pauta fija seria un error de medicacion.
        """
        resultado = await servicio_historia.confirmar_receta(
            receta_con_pauta.id, principal=principal_medico, profesional_id=profesional.id
        )

        assert resultado.tomas_generadas == 6
        assert resultado.receta is not None
        assert resultado.receta.estado == EstadoReceta.CONFIRMADA.value
        assert {e.accion for e in resultado.auditoria} == {
            AccionAuditada.RECETA_CONFIRMADA,
            AccionAuditada.TOMAS_GENERADAS,
        }

        # Ninguna toma corresponde al PRN.
        filas = list((await sesion.execute(sa.select(Toma))).scalars())
        assert len(filas) == 6

    async def test_no_se_confirma_dos_veces(
        self,
        servicio_historia: ServicioHistoria,
        principal_medico: Principal,
        receta_con_pauta,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        await servicio_historia.confirmar_receta(
            receta_con_pauta.id, principal=principal_medico, profesional_id=profesional.id
        )
        with pytest.raises(ConflictoEstado):
            await servicio_historia.confirmar_receta(
                receta_con_pauta.id, principal=principal_medico, profesional_id=profesional.id
            )

    async def test_suspender_cancela_las_futuras_y_respeta_las_pasadas(
        self,
        sesion: AsyncSession,
        servicio_historia: ServicioHistoria,
        principal_medico: Principal,
        receta_con_pauta,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
        reloj_fijo: RelojFijo,
    ) -> None:
        """Las pasadas son el registro de lo que ocurrio.

        Reescribirlo falsearia el historico de adherencia, que es justo lo que
        el profesional mira para decidir si el tratamiento funciona.
        """
        await servicio_historia.confirmar_receta(
            receta_con_pauta.id, principal=principal_medico, profesional_id=profesional.id
        )

        # Se avanza un dia: dos tomas quedan en el pasado.
        reloj_fijo.avanzar(days=1)
        resultado = await servicio_historia.suspender_receta(
            receta_con_pauta.id,
            principal=principal_medico,
            motivo="El paciente refiere molestias",
        )

        assert resultado.tomas_canceladas > 0

        estados = list(
            (
                await sesion.execute(
                    sa.select(Toma.estado, Toma.programada_en).order_by(Toma.programada_en)
                )
            ).all()
        )
        ahora = reloj_fijo.ahora()
        for estado, programada in estados:
            if programada <= ahora:
                assert estado == EstadoToma.PENDIENTE.value, "una toma pasada se altero"
            else:
                assert estado == EstadoToma.CANCELADA.value

    async def test_suspender_sin_motivo_se_rechaza(
        self,
        servicio_historia: ServicioHistoria,
        principal_medico: Principal,
        receta_con_pauta,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        await servicio_historia.confirmar_receta(
            receta_con_pauta.id, principal=principal_medico, profesional_id=profesional.id
        )
        with pytest.raises(ReglaNegocioViolada):
            await servicio_historia.suspender_receta(
                receta_con_pauta.id, principal=principal_medico, motivo="  "
            )

    async def test_una_receta_sin_medicamentos_se_rechaza(
        self,
        servicio_historia: ServicioHistoria,
        principal_medico: Principal,
        relacion: RelacionAsistencial,
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        with pytest.raises(ReglaNegocioViolada):
            await servicio_historia.crear_receta(
                principal=principal_medico,
                paciente_id=paciente.id,
                profesional_id=profesional.id,
                medicamentos=[],
            )

    async def test_una_pauta_desmedida_se_rechaza(
        self,
        servicio_historia: ServicioHistoria,
        principal_medico: Principal,
        relacion: RelacionAsistencial,
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        """«Cada hora durante un ano» son 8.760 filas.

        El limite obliga a revisar la pauta en lugar de llenar la tabla en
        silencio.
        """
        resultado = await servicio_historia.crear_receta(
            principal=principal_medico,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            medicamentos=[
                DatosMedicamento(
                    nombre="Medicamento de ejemplo",
                    dosis="1",
                    via="ORAL",
                    frecuencia_horas=1,
                    duracion_dias=365,
                )
            ],
        )
        assert resultado.receta is not None

        with pytest.raises(ReglaNegocioViolada, match=str(MAXIMO_TOMAS_POR_MEDICAMENTO)):
            await servicio_historia.confirmar_receta(
                resultado.receta.id, principal=principal_medico, profesional_id=profesional.id
            )


class TestRegistroDeTomas:
    @pytest_asyncio.fixture
    async def receta_confirmada(
        self,
        servicio_historia: ServicioHistoria,
        principal_medico: Principal,
        relacion: RelacionAsistencial,
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
    ):  # type: ignore[no-untyped-def]
        creada = await servicio_historia.crear_receta(
            principal=principal_medico,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            medicamentos=[
                DatosMedicamento(
                    nombre="Medicamento de ejemplo",
                    dosis="1 comprimido",
                    via="ORAL",
                    frecuencia_horas=8,
                    duracion_dias=5,
                )
            ],
        )
        assert creada.receta is not None
        await servicio_historia.confirmar_receta(
            creada.receta.id, principal=principal_medico, profesional_id=profesional.id
        )
        return creada.receta

    async def test_no_se_registra_una_toma_futura(
        self,
        sesion: AsyncSession,
        servicio_historia: ServicioHistoria,
        principal_medico: Principal,
        receta_confirmada,  # type: ignore[no-untyped-def]
    ) -> None:
        """Marcar como tomada una dosis que todavia no toca produce un
        registro de adherencia falso, y ese registro es lo que el profesional
        mira para decidir."""
        toma = (
            await sesion.execute(sa.select(Toma).order_by(Toma.programada_en).limit(1))
        ).scalar_one()

        with pytest.raises(ReglaNegocioViolada, match="todavia no llego"):
            await servicio_historia.registrar_toma(toma.id, principal=principal_medico, tomada=True)

    async def test_se_registra_una_toma_pasada(
        self,
        sesion: AsyncSession,
        servicio_historia: ServicioHistoria,
        principal_medico: Principal,
        receta_confirmada,  # type: ignore[no-untyped-def]
        reloj_fijo: RelojFijo,
    ) -> None:
        toma = (
            await sesion.execute(sa.select(Toma).order_by(Toma.programada_en).limit(1))
        ).scalar_one()
        reloj_fijo.fijar(toma.programada_en + timedelta(minutes=5))

        resultado = await servicio_historia.registrar_toma(
            toma.id, principal=principal_medico, tomada=True, nota_paciente="Sin molestias"
        )

        assert resultado.auditoria[0].accion == AccionAuditada.TOMA_REGISTRADA
        await sesion.refresh(toma)
        assert toma.estado == EstadoToma.TOMADA.value
        assert toma.registrada_en is not None

    async def test_no_se_registra_dos_veces(
        self,
        sesion: AsyncSession,
        servicio_historia: ServicioHistoria,
        principal_medico: Principal,
        receta_confirmada,  # type: ignore[no-untyped-def]
        reloj_fijo: RelojFijo,
    ) -> None:
        toma = (
            await sesion.execute(sa.select(Toma).order_by(Toma.programada_en).limit(1))
        ).scalar_one()
        reloj_fijo.fijar(toma.programada_en + timedelta(minutes=5))

        await servicio_historia.registrar_toma(toma.id, principal=principal_medico, tomada=True)
        with pytest.raises(ConflictoEstado):
            await servicio_historia.registrar_toma(
                toma.id, principal=principal_medico, tomada=False
            )

    async def test_una_toma_de_otro_paciente_no_se_alcanza(
        self,
        sesion: AsyncSession,
        servicio_historia: ServicioHistoria,
        clinica,  # type: ignore[no-untyped-def]
        receta_confirmada,  # type: ignore[no-untyped-def]
        reloj_fijo: RelojFijo,
    ) -> None:
        """Es el caso del paciente que escribe por WhatsApp: su principal solo
        alcanza su propia ficha."""
        toma = (
            await sesion.execute(sa.select(Toma).order_by(Toma.programada_en).limit(1))
        ).scalar_one()
        reloj_fijo.fijar(toma.programada_en + timedelta(minutes=5))

        otro = Principal(
            actor_tipo=TipoActor.PACIENTE,
            actor_id=uuid.uuid4(),
            clinica_id=clinica.id,
            permisos=frozenset(),
            ambito=Ambito(clinica_id=clinica.id, pacientes=frozenset({uuid.uuid4()})),
        )

        with pytest.raises(RecursoNoEncontrado):
            await servicio_historia.registrar_toma(toma.id, principal=otro, tomada=True)


class TestAdherencia:
    @pytest_asyncio.fixture
    async def receta_con_omisiones(
        self,
        sesion: AsyncSession,
        servicio_historia: ServicioHistoria,
        principal_medico: Principal,
        relacion: RelacionAsistencial,
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
        reloj_fijo: RelojFijo,
    ):  # type: ignore[no-untyped-def]
        creada = await servicio_historia.crear_receta(
            principal=principal_medico,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            medicamentos=[
                DatosMedicamento(
                    nombre="Medicamento de ejemplo",
                    dosis="1",
                    via="ORAL",
                    frecuencia_horas=12,
                    duracion_dias=5,
                )
            ],
        )
        assert creada.receta is not None
        await servicio_historia.confirmar_receta(
            creada.receta.id, principal=principal_medico, profesional_id=profesional.id
        )
        # Se avanza al final del tratamiento: todas las tomas quedan en el
        # pasado y ninguna se registro, que es el caso de omision total.
        reloj_fijo.avanzar(days=6)
        return creada.receta

    async def test_las_omisiones_producen_alerta(
        self,
        servicio_historia: ServicioHistoria,
        principal_medico: Principal,
        receta_con_omisiones,  # type: ignore[no-untyped-def]
    ) -> None:
        """Una toma pendiente cuya hora ya paso es una toma que no se
        registro. Contar solo las resueltas daria adherencia perfecta a quien
        nunca responde."""
        alerta = await servicio_historia.evaluar_adherencia(
            receta_con_omisiones.id, principal=principal_medico, dias=10
        )

        assert alerta is not None
        assert alerta.tomas_omitidas == alerta.tomas_esperadas
        assert alerta.severidad == "URGENTE"

    async def test_no_se_crea_una_segunda_alerta_abierta(
        self,
        servicio_historia: ServicioHistoria,
        principal_medico: Principal,
        receta_con_omisiones,  # type: ignore[no-untyped-def]
    ) -> None:
        """Repetirla cada dia convertiria el aviso en ruido."""
        primera = await servicio_historia.evaluar_adherencia(
            receta_con_omisiones.id, principal=principal_medico, dias=10
        )
        segunda = await servicio_historia.evaluar_adherencia(
            receta_con_omisiones.id, principal=principal_medico, dias=10
        )

        assert primera is not None
        assert segunda is None

    async def test_con_pocas_tomas_no_se_alerta(
        self,
        servicio_historia: ServicioHistoria,
        principal_medico: Principal,
        relacion: RelacionAsistencial,
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
        reloj_fijo: RelojFijo,
    ) -> None:
        """Con dos tomas, una omision da el 50 % y produciria una alerta por
        un dato sin valor."""
        creada = await servicio_historia.crear_receta(
            principal=principal_medico,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            medicamentos=[
                DatosMedicamento(
                    nombre="Medicamento de ejemplo",
                    dosis="1",
                    via="ORAL",
                    frecuencia_horas=24,
                    duracion_dias=2,
                )
            ],
        )
        assert creada.receta is not None
        await servicio_historia.confirmar_receta(
            creada.receta.id, principal=principal_medico, profesional_id=profesional.id
        )
        reloj_fijo.avanzar(days=3)

        alerta = await servicio_historia.evaluar_adherencia(
            creada.receta.id, principal=principal_medico, dias=10
        )
        assert alerta is None


class TestPermisos:
    async def test_sin_permiso_no_se_escribe(
        self,
        servicio_historia: ServicioHistoria,
        clinica,  # type: ignore[no-untyped-def]
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        recepcion = Principal(
            actor_tipo=TipoActor.USUARIO,
            actor_id=uuid.uuid4(),
            clinica_id=clinica.id,
            permisos=frozenset({"agenda.leer", "cita.crear"}),
            ambito=Ambito(clinica_id=clinica.id, todos_los_pacientes=True),
        )
        with pytest.raises(PermisoDenegado):
            await servicio_historia.crear_nota(
                _datos_nota(paciente.id, profesional.id), principal=recepcion
            )

    async def test_registrar_diagnostico_exige_su_propio_permiso(
        self,
        servicio_historia: ServicioHistoria,
        relacion: RelacionAsistencial,
        clinica,  # type: ignore[no-untyped-def]
        sede,  # type: ignore[no-untyped-def]
        paciente,  # type: ignore[no-untyped-def]
        profesional,  # type: ignore[no-untyped-def]
    ) -> None:
        """Escribir una nota y codificar un diagnostico son actos distintos."""
        sin_diagnostico = Principal(
            actor_tipo=TipoActor.USUARIO,
            actor_id=uuid.uuid4(),
            clinica_id=clinica.id,
            permisos=frozenset({"historia_clinica.escribir"}),
            ambito=Ambito(clinica_id=clinica.id, todos_los_pacientes=True),
            profesional_id=profesional.id,
        )

        with pytest.raises(PermisoDenegado, match="diagnostico"):
            await servicio_historia.crear_nota(
                _datos_nota(
                    paciente.id,
                    profesional.id,
                    diagnosticos=(("Z00.0", "Examen general de rutina", True, True),),
                ),
                principal=sin_diagnostico,
            )
