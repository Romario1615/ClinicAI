"""Resolucion de identidad cuando un telefono corresponde a varios pacientes.

Por que estas pruebas son las que sostienen la decision
------------------------------------------------------
Se decidio que, ante un numero ambiguo, el sistema ofrezca la lista de
pacientes y espere a que quien escribe elija.  Esa decision solo es segura si
se cumplen a la vez cuatro cosas, y cada una tiene su prueba aqui:

1. **Sin eleccion no hay paciente resuelto.**  El estado por defecto sigue
   siendo «no se quien es», que es lo que impide actuar sobre el equivocado.
2. **Elegir no verifica identidad.**  El `nivel_verificacion` no cambia por
   haber pulsado «2».  Si cambiara, una pregunta de menu se habria convertido
   en una credencial.
3. **La lista se resuelve contra lo guardado, no contra una consulta nueva.**
   Entre la oferta y la respuesta puede aparecer otra ficha con ese telefono, y
   el «2» seleccionaria a otra persona.
4. **La lista no filtra mas de lo imprescindible.**  Quien tenga el aparato va
   a leer esos nombres, y un telefono puede estar perdido o reasignado.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.mensajeria.carga_whatsapp import CargaWebhook, MensajeEntranteCrudo
from app.modulos.conversaciones.identificacion import (
    MAXIMO_OPCIONES,
    MINUTOS_VIGENCIA_SELECCION,
    etiquetar,
    identificar,
    texto_de_opciones,
)
from app.modulos.conversaciones.modelos import Conversacion, EstadoConversacion
from app.modulos.conversaciones.servicios import ServicioConversaciones
from app.modulos.pacientes.modelos import Paciente
from app.nucleo.reloj import RelojFijo

pytestmark = [pytest.mark.integracion, pytest.mark.asyncio]

AHORA = datetime(2026, 4, 15, 14, 0, tzinfo=UTC)
#: El panel guarda el numero con espacios; el webhook entrega solo digitos.
TELEFONO_PANEL = "+593 99 900 7777"
TELEFONO_WEBHOOK = "593999007777"


@pytest.fixture
def reloj_fijo() -> RelojFijo:
    return RelojFijo(AHORA)


@pytest.fixture
def servicio(sesion: AsyncSession, reloj_fijo: RelojFijo) -> ServicioConversaciones:
    return ServicioConversaciones(sesion, reloj_fijo)


async def _crear_paciente(
    sesion: AsyncSession, clinica, nombre: str, apellido: str, sufijo: str
) -> Paciente:
    paciente = Paciente(
        clinica_id=clinica.id,
        tipo_documento="CEDULA",
        numero_documento=f"97{sufijo}",
        nombre=nombre,
        apellido=apellido,
        telefono_whatsapp=TELEFONO_PANEL,
    )
    sesion.add(paciente)
    await sesion.flush()
    return paciente


def _mensaje(texto: str, sufijo: str = "1") -> CargaWebhook:
    return CargaWebhook(
        mensajes=(
            MensajeEntranteCrudo(
                external_id=f"wamid.identidad-{sufijo}-{uuid.uuid4().hex[:8]}",
                telefono=TELEFONO_WEBHOOK,
                tipo="text",
                texto=texto,
                recibido_en=AHORA,
                crudo={},
            ),
        ),
        estados=(),
    )


async def _conversacion(sesion: AsyncSession, clinica) -> Conversacion:
    return (
        (
            await sesion.execute(
                sa.select(Conversacion).where(
                    Conversacion.clinica_id == clinica.id,
                    Conversacion.telefono == TELEFONO_WEBHOOK,
                )
            )
        )
        .scalars()
        .one()
    )


# ===========================================================================
#  La consulta
# ===========================================================================
class TestIdentificar:
    async def test_un_solo_paciente_se_resuelve_sin_preguntar(
        self, sesion: AsyncSession, clinica
    ) -> None:
        paciente = await _crear_paciente(sesion, clinica, "Irene", "Alberto", "0001")

        resultado = await identificar(
            sesion, clinica_id=clinica.id, telefono=TELEFONO_WEBHOOK, ahora=AHORA
        )

        assert resultado.resuelto
        assert resultado.paciente_id == paciente.id
        assert not resultado.hay_que_preguntar

    async def test_varios_pacientes_producen_opciones(self, sesion: AsyncSession, clinica) -> None:
        await _crear_paciente(sesion, clinica, "Ana", "Perez", "0002")
        await _crear_paciente(sesion, clinica, "Luis", "Perez", "0003")

        resultado = await identificar(
            sesion, clinica_id=clinica.id, telefono=TELEFONO_WEBHOOK, ahora=AHORA
        )

        assert not resultado.resuelto, "Sin eleccion no hay paciente resuelto."
        assert resultado.hay_que_preguntar
        assert resultado.opciones is not None
        assert len(resultado.opciones.candidatos) == 2

    async def test_un_numero_desconocido_no_produce_opciones(
        self, sesion: AsyncSession, clinica
    ) -> None:
        resultado = await identificar(
            sesion, clinica_id=clinica.id, telefono=TELEFONO_WEBHOOK, ahora=AHORA
        )
        assert not resultado.resuelto
        assert not resultado.hay_que_preguntar
        assert resultado.motivo_derivacion == "NUMERO_SIN_PACIENTE"

    async def test_demasiados_candidatos_no_se_enumeran(
        self, sesion: AsyncSession, clinica
    ) -> None:
        """Un numero en muchas fichas no es una familia.

        Es un dato mal cargado o un telefono compartido, y listar los nombres a
        quien tenga ese aparato es una fuga, no una ayuda.
        """
        for i in range(MAXIMO_OPCIONES + 1):
            await _crear_paciente(sesion, clinica, f"Nombre{i}", "Apellido", f"01{i:02d}")

        resultado = await identificar(
            sesion, clinica_id=clinica.id, telefono=TELEFONO_WEBHOOK, ahora=AHORA
        )

        assert not resultado.hay_que_preguntar
        assert resultado.motivo_derivacion == "DEMASIADOS_CANDIDATOS"

    async def test_el_numero_del_panel_y_el_del_webhook_se_comparan_normalizados(
        self, sesion: AsyncSession, clinica
    ) -> None:
        """El panel guarda «+593 99 900 7777»; el webhook entrega digitos.

        Comparar en crudo no encuentra a nadie. Es el mismo fallo que dejaba
        sin efecto una baja de consentimiento.
        """
        paciente = await _crear_paciente(sesion, clinica, "Irene", "Alberto", "0009")

        resultado = await identificar(
            sesion, clinica_id=clinica.id, telefono=TELEFONO_WEBHOOK, ahora=AHORA
        )
        assert resultado.paciente_id == paciente.id


# ===========================================================================
#  Lo que se le muestra a quien escribe
# ===========================================================================
class TestMinimizacion:
    async def test_la_etiqueta_es_nombre_de_pila_e_inicial(
        self, sesion: AsyncSession, clinica
    ) -> None:
        paciente = await _crear_paciente(sesion, clinica, "Maria Jose", "Gutierrez Salas", "0020")
        assert etiquetar(paciente) == "Maria G."

    async def test_el_texto_no_revela_documento_ni_apellido_completo(
        self, sesion: AsyncSession, clinica
    ) -> None:
        """Quien tenga el telefono va a leer esto.

        Un telefono puede estar perdido, prestado o reasignado. El documento
        permite suplantar en otros tramites; el apellido completo identifica a
        la familia.
        """
        await _crear_paciente(sesion, clinica, "Ana", "Perez", "0021")
        await _crear_paciente(sesion, clinica, "Luis", "Perez", "0022")

        resultado = await identificar(
            sesion, clinica_id=clinica.id, telefono=TELEFONO_WEBHOOK, ahora=AHORA
        )
        assert resultado.opciones is not None
        texto = texto_de_opciones(resultado.opciones)

        assert "Ana P." in texto
        assert "Perez" not in texto
        assert "970021" not in texto
        assert "970022" not in texto

    async def test_el_texto_no_menciona_nada_clinico(self, sesion: AsyncSession, clinica) -> None:
        """Regla 10: es un mensaje de WhatsApp y puede leerse en la pantalla de bloqueo."""
        await _crear_paciente(sesion, clinica, "Ana", "Perez", "0023")
        await _crear_paciente(sesion, clinica, "Luis", "Perez", "0024")

        resultado = await identificar(
            sesion, clinica_id=clinica.id, telefono=TELEFONO_WEBHOOK, ahora=AHORA
        )
        assert resultado.opciones is not None
        texto = texto_de_opciones(resultado.opciones).lower()

        for prohibida in ("diagnostic", "medicament", "dosis", "receta", "cita del"):
            assert prohibida not in texto


# ===========================================================================
#  El recorrido completo sobre el webhook
# ===========================================================================
class TestRecorrido:
    async def test_un_numero_ambiguo_provoca_la_pregunta_y_no_resuelve_nada(
        self, sesion: AsyncSession, clinica, servicio: ServicioConversaciones
    ) -> None:
        await _crear_paciente(sesion, clinica, "Ana", "Perez", "0030")
        await _crear_paciente(sesion, clinica, "Luis", "Perez", "0031")

        resumen = await servicio.procesar(_mensaje("cancelar"), clinica_id=clinica.id)
        await sesion.flush()

        assert resumen.preguntas_identidad == 1
        conversacion = await _conversacion(sesion, clinica)
        # Lo esencial: se pregunto y NO se resolvio nadie.
        assert conversacion.paciente_id is None
        assert conversacion.seleccion_pendiente is not None
        assert conversacion.estado == EstadoConversacion.EN_HANDOFF.value

    async def test_la_respuesta_resuelve_la_identidad(
        self, sesion: AsyncSession, clinica, servicio: ServicioConversaciones
    ) -> None:
        ana = await _crear_paciente(sesion, clinica, "Ana", "Perez", "0032")
        await _crear_paciente(sesion, clinica, "Luis", "Perez", "0033")

        await servicio.procesar(_mensaje("cancelar", "a"), clinica_id=clinica.id)
        await sesion.flush()
        resumen = await servicio.procesar(_mensaje("1", "b"), clinica_id=clinica.id)
        await sesion.flush()

        assert resumen.identidades_resueltas == 1
        conversacion = await _conversacion(sesion, clinica)
        assert conversacion.paciente_id == ana.id
        assert conversacion.seleccion_pendiente is None

    async def test_elegir_no_sube_el_nivel_de_verificacion(
        self, sesion: AsyncSession, clinica, servicio: ServicioConversaciones
    ) -> None:
        """Desambiguar no es verificar.

        Si el nivel subiera, una pregunta de menu se habria convertido en una
        credencial: bastaria con tener el telefono para pasar a `TELEFONO`.
        """
        ana = await _crear_paciente(sesion, clinica, "Ana", "Perez", "0034")
        await _crear_paciente(sesion, clinica, "Luis", "Perez", "0035")
        antes = ana.nivel_verificacion

        await servicio.procesar(_mensaje("cancelar", "c"), clinica_id=clinica.id)
        await sesion.flush()
        await servicio.procesar(_mensaje("1", "d"), clinica_id=clinica.id)
        await sesion.flush()
        await sesion.refresh(ana)

        assert ana.nivel_verificacion == antes == "NO_VERIFICADO"

    async def test_una_eleccion_fuera_de_rango_no_resuelve_nada(
        self, sesion: AsyncSession, clinica, servicio: ServicioConversaciones
    ) -> None:
        await _crear_paciente(sesion, clinica, "Ana", "Perez", "0036")
        await _crear_paciente(sesion, clinica, "Luis", "Perez", "0037")

        await servicio.procesar(_mensaje("cancelar", "e"), clinica_id=clinica.id)
        await sesion.flush()
        resumen = await servicio.procesar(_mensaje("9", "f"), clinica_id=clinica.id)
        await sesion.flush()

        assert resumen.identidades_resueltas == 0
        conversacion = await _conversacion(sesion, clinica)
        assert conversacion.paciente_id is None

    async def test_una_lista_caducada_no_resuelve_nada(
        self,
        sesion: AsyncSession,
        clinica,
        servicio: ServicioConversaciones,
        reloj_fijo: RelojFijo,
    ) -> None:
        """Un «2» de hoy responde a una pregunta que quien escribe ya no recuerda."""
        await _crear_paciente(sesion, clinica, "Ana", "Perez", "0038")
        await _crear_paciente(sesion, clinica, "Luis", "Perez", "0039")

        await servicio.procesar(_mensaje("cancelar", "g"), clinica_id=clinica.id)
        await sesion.flush()
        caducada = dict((await _conversacion(sesion, clinica)).seleccion_pendiente or {})

        reloj_fijo.avanzar(minutes=MINUTOS_VIGENCIA_SELECCION + 1)
        resumen = await servicio.procesar(_mensaje("1", "h"), clinica_id=clinica.id)
        await sesion.flush()

        assert resumen.identidades_resueltas == 0
        conversacion = await _conversacion(sesion, clinica)
        # Lo que importa: el «1» tardio NO resolvio a nadie.
        assert conversacion.paciente_id is None

        # Y en lugar de callar, se vuelve a preguntar con una lista nueva.
        # Descartar la caducada y no ofrecer nada dejaria a quien escribe sin
        # forma de continuar; ofrecerla otra vez le permite responder.
        assert conversacion.seleccion_pendiente is not None
        assert conversacion.seleccion_pendiente["expira_en"] > caducada["expira_en"]

    async def test_un_numero_de_un_solo_paciente_no_pregunta(
        self, sesion: AsyncSession, clinica, servicio: ServicioConversaciones
    ) -> None:
        paciente = await _crear_paciente(sesion, clinica, "Irene", "Alberto", "0040")

        resumen = await servicio.procesar(_mensaje("ayuda", "i"), clinica_id=clinica.id)
        await sesion.flush()

        assert resumen.preguntas_identidad == 0
        conversacion = await _conversacion(sesion, clinica)
        assert conversacion.paciente_id == paciente.id
