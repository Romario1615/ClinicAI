"""Listado del calendario de tomas.

Por que existe esta consulta y que tiene que garantizar
------------------------------------------------------
La pantalla de medicacion necesita ver las tomas de un paciente alrededor de
hoy. Es una via de lectura nueva sobre datos clinicos, asi que lo que hay que
demostrar es que **aplica el mismo filtro que el resto del modulo**: ambito mas
relacion asistencial. Una consulta que se saltara eso seria una fuga por la
puerta de al lado, con los controles de la puerta principal intactos.

La ventana se centra en el momento actual y no empieza en el: quien atiende
necesita ver lo que quedo atras sin registrar -- que es justo lo que mide la
adherencia -- y no solo lo que viene.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.historia.repositorio import RepositorioHistoria
from app.modulos.historia.servicios import (
    DatosMedicamento,
    ServicioHistoria,
)
from app.modulos.pacientes.modelos import RelacionAsistencial
from app.nucleo.autorizacion import Ambito, Principal, TipoActor
from app.nucleo.reloj import RelojFijo

pytestmark = [pytest.mark.integracion, pytest.mark.asyncio]

AHORA = datetime(2026, 4, 15, 14, 0, tzinfo=UTC)


@pytest.fixture
def reloj_fijo() -> RelojFijo:
    return RelojFijo(AHORA)


def _principal(clinica_id, profesional_id, *, todos_los_pacientes: bool = True) -> Principal:
    return Principal(
        actor_tipo=TipoActor.USUARIO,
        actor_id=uuid.uuid4(),
        clinica_id=clinica_id,
        permisos=frozenset({"receta.crear", "receta.confirmar", "receta.leer", "adherencia.leer"}),
        ambito=Ambito(
            clinica_id=clinica_id,
            todas_las_sedes=True,
            todas_las_especialidades=True,
            todos_los_profesionales=True,
            todos_los_pacientes=todos_los_pacientes,
        ),
        profesional_id=profesional_id,
    )


@pytest.fixture
async def relacion(sesion: AsyncSession, paciente, profesional):
    """Sin relacion asistencial no se puede escribir ni leer la medicacion.

    Tener el permiso no basta: es este vinculo el que autoriza el acceso a un
    paciente concreto, y crearlo aqui es lo que permite probar la via feliz.
    """
    registro = RelacionAsistencial(
        paciente_id=paciente.id, profesional_id=profesional.id, origen="CITA"
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


@pytest.fixture
async def receta_confirmada(
    sesion: AsyncSession, clinica, paciente, profesional, relacion, reloj_fijo: RelojFijo
):
    """Pauta fija de 3 dias cada 12 horas, mas un PRN que no genera tomas."""
    principal = _principal(clinica.id, profesional.id)
    servicio = ServicioHistoria(sesion, RepositorioHistoria(sesion), reloj_fijo)
    creada = await servicio.crear_receta(
        principal=principal,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        medicamentos=[
            DatosMedicamento(
                nombre="Medicamento de ejemplo A",
                dosis="1 unidad",
                via="ORAL",
                frecuencia_horas=12,
                duracion_dias=3,
            ),
            DatosMedicamento(
                nombre="Medicamento de ejemplo C",
                dosis="1 unidad",
                via="ORAL",
                cuando_sea_necesario=True,
            ),
        ],
    )
    assert creada.receta is not None
    await servicio.confirmar_receta(
        creada.receta.id, principal=principal, profesional_id=profesional.id
    )
    await sesion.flush()
    return creada.receta


class TestAlcance:
    async def test_el_ambito_vacio_no_devuelve_ninguna_toma(
        self, sesion: AsyncSession, clinica, paciente, profesional, receta_confirmada
    ) -> None:
        """Ambito vacio significa ningun acceso, no acceso total.

        Es el valor por defecto mas restrictivo del sistema. Un rol al que se
        olvido asignar ambito no puede convertirse en superusuario por omision.
        """
        sin_ambito = Principal(
            actor_tipo=TipoActor.USUARIO,
            actor_id=uuid.uuid4(),
            clinica_id=clinica.id,
            permisos=frozenset({"receta.leer", "adherencia.leer"}),
            ambito=Ambito(clinica_id=clinica.id),
            profesional_id=profesional.id,
        )
        filas = await RepositorioHistoria(sesion).listar_tomas(
            principal=sin_ambito,
            paciente_id=paciente.id,
            desde=AHORA - timedelta(days=7),
            hasta=AHORA + timedelta(days=7),
            ahora=AHORA,
        )
        assert filas == []

    async def test_un_paciente_fuera_del_ambito_no_devuelve_tomas(
        self,
        sesion: AsyncSession,
        clinica,
        paciente,
        segundo_paciente,
        profesional,
        receta_confirmada,
    ) -> None:
        """Pedir la medicacion de otro no da error: da una lista vacia.

        Un error confirmaria que ese paciente existe, y eso permite enumerar.
        """
        acotado = Principal(
            actor_tipo=TipoActor.USUARIO,
            actor_id=uuid.uuid4(),
            clinica_id=clinica.id,
            permisos=frozenset({"receta.leer", "adherencia.leer"}),
            ambito=Ambito(
                clinica_id=clinica.id,
                todas_las_sedes=True,
                todas_las_especialidades=True,
                todos_los_profesionales=True,
                pacientes=frozenset({segundo_paciente.id}),
            ),
            profesional_id=profesional.id,
        )
        filas = await RepositorioHistoria(sesion).listar_tomas(
            principal=acotado,
            paciente_id=paciente.id,
            desde=AHORA - timedelta(days=7),
            hasta=AHORA + timedelta(days=7),
            ahora=AHORA,
        )
        assert filas == []


class TestContenido:
    async def test_devuelve_las_tomas_con_el_nombre_de_su_medicamento(
        self, sesion: AsyncSession, clinica, paciente, profesional, receta_confirmada
    ) -> None:
        """Una toma sin saber de que es no le sirve a nadie.

        Resolverlo despues obligaria a una consulta por fila.
        """
        filas = await RepositorioHistoria(sesion).listar_tomas(
            principal=_principal(clinica.id, profesional.id),
            paciente_id=paciente.id,
            desde=AHORA - timedelta(days=7),
            hasta=AHORA + timedelta(days=7),
            ahora=AHORA,
        )
        assert filas, "La receta confirmada genera tomas."
        nombres = {medicamento.nombre for _, medicamento in filas}
        assert nombres == {"Medicamento de ejemplo A"}

    async def test_el_prn_no_aparece_porque_no_genera_tomas(
        self, sesion: AsyncSession, clinica, paciente, profesional, receta_confirmada
    ) -> None:
        """La garantia clinica, vista desde esta consulta.

        Si el «cuando sea necesario» apareciera aqui con una hora, la pantalla
        lo mostraria como pauta fija.
        """
        filas = await RepositorioHistoria(sesion).listar_tomas(
            principal=_principal(clinica.id, profesional.id),
            paciente_id=paciente.id,
            desde=AHORA - timedelta(days=30),
            hasta=AHORA + timedelta(days=30),
            ahora=AHORA,
        )
        assert all(not medicamento.cuando_sea_necesario for _, medicamento in filas)

    async def test_las_tomas_salen_ordenadas_por_hora(
        self, sesion: AsyncSession, clinica, paciente, profesional, receta_confirmada
    ) -> None:
        """Sin orden, la pantalla mezclaria el lunes con el miercoles."""
        filas = await RepositorioHistoria(sesion).listar_tomas(
            principal=_principal(clinica.id, profesional.id),
            paciente_id=paciente.id,
            desde=AHORA - timedelta(days=7),
            hasta=AHORA + timedelta(days=7),
            ahora=AHORA,
        )
        horas = [toma.programada_en for toma, _ in filas]
        assert horas == sorted(horas)

    async def test_la_ventana_recorta(
        self, sesion: AsyncSession, clinica, paciente, profesional, receta_confirmada
    ) -> None:
        """Una ventana anterior a la receta no devuelve nada."""
        filas = await RepositorioHistoria(sesion).listar_tomas(
            principal=_principal(clinica.id, profesional.id),
            paciente_id=paciente.id,
            desde=AHORA - timedelta(days=60),
            hasta=AHORA - timedelta(days=30),
            ahora=AHORA,
        )
        assert filas == []

    async def test_el_limite_tiene_techo_duro(
        self, sesion: AsyncSession, clinica, paciente, profesional, receta_confirmada
    ) -> None:
        """Una pauta larga produce cientos de tomas.

        Una consulta sin cota devolveria decenas de miles de filas y agotaria
        la memoria del proceso.
        """
        filas = await RepositorioHistoria(sesion).listar_tomas(
            principal=_principal(clinica.id, profesional.id),
            paciente_id=paciente.id,
            desde=AHORA - timedelta(days=7),
            hasta=AHORA + timedelta(days=7),
            ahora=AHORA,
            limite=10_000,
        )
        assert len(filas) <= 500
