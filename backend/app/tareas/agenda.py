"""Trabajos periodicos de la agenda.

Ahora mismo solo el barrido de bloqueos temporales vencidos. Sin el, un
paciente que abandona la conversacion de WhatsApp a medias deja el turno
retenido: la agenda pierde capacidad y nadie se entera, porque el turno no
aparece como libre ni como ocupado por una cita real.

Seguro con varios workers a la vez
----------------------------------
La consulta que selecciona los vencidos usa `FOR UPDATE SKIP LOCKED`: dos
procesos ejecutando el barrido al mismo tiempo se reparten los lotes en lugar
de pelearse por las mismas filas. Sin `SKIP LOCKED` el segundo worker se
quedaria esperando al primero y el barrido tardaria el doble; con `NOWAIT`
fallaria. Repartirse el trabajo es lo correcto.

El lote es limitado a proposito: un atasco acumulado -- el worker parado un
fin de semana -- produciria si no una transaccion enorme que mantiene
bloqueadas miles de filas de `cita` durante minutos, justo sobre la tabla que
la API necesita para reservar.
"""

from __future__ import annotations

from typing import Any

from app.modulos.agenda.repositorio import RepositorioAgenda
from app.modulos.agenda.servicios import ServicioAgenda
from app.modulos.auditoria.repositorio import RepositorioAuditoria
from app.nucleo.autorizacion import principal_sistema
from app.nucleo.bd import GestorBaseDatos
from app.nucleo.configuracion import Configuracion
from app.nucleo.registro import obtener_logger
from app.nucleo.reloj import Reloj

_logger = obtener_logger(__name__)

# Cuantos bloqueos se procesan por ejecucion. Ver la nota del encabezado.
TAMANO_LOTE = 200


async def expirar_bloqueos(ctx: dict[Any, Any], *_argumentos: Any, **_opciones: Any) -> int:
    """Libera los turnos cuyo bloqueo temporal caduco.

    Devuelve cuantos libero, para que el registro permita ver si el barrido
    va al dia o viene arrastrando cola.

    El principal es el del sistema, que **no** tiene permisos clinicos: un
    trabajo programado cancela bloqueos y no escribe notas ni confirma
    recetas. Esa restriccion es deliberada y tiene su propia prueba.

    El parametro se llama `ctx` y no `contexto`, y los argumentos variables
    no se usan: ambas cosas las impone el protocolo `WorkerCoroutine` de ARQ,
    que exige esa firma exacta -- incluido el nombre -- para aceptar la
    funcion. Es una de las excepciones de nomenclatura previstas en CLAUDE.md.
    """
    gestor: GestorBaseDatos = ctx["gestor_bd"]
    reloj: Reloj = ctx["reloj"]
    configuracion: Configuracion = ctx["configuracion"]

    liberados = 0
    async for sesion in gestor.sesion():
        servicio = ServicioAgenda(
            sesion,
            RepositorioAgenda(sesion),
            reloj,
            minutos_expiracion_held=configuracion.minutos_expiracion_held,
        )
        auditor = RepositorioAuditoria(sesion)

        resultados = await servicio.expirar_bloqueos_vencidos(
            principal=principal_sistema(),
            limite=TAMANO_LOTE,
        )
        for resultado in resultados:
            await auditor.registrar(resultado.auditoria)

        # La liberacion de los turnos y su auditoria se confirman juntas. Si
        # se confirmara solo lo primero, quedarian citas canceladas sin
        # constancia de por que, y la respuesta a "por que se anulo mi cita"
        # seria que no se sabe.
        await sesion.commit()
        liberados = len(resultados)

    if liberados:
        _logger.info("agenda.bloqueos_expirados", cantidad=liberados, lote=TAMANO_LOTE)
        if liberados == TAMANO_LOTE:
            # El lote salio lleno: es probable que queden mas esperando. Se
            # avisa porque significa que el barrido no va al dia, y un turno
            # retenido de mas es capacidad perdida de la clinica.
            _logger.warning(
                "agenda.bloqueos_expirados.lote_lleno",
                cantidad=liberados,
                nota="Quedan bloqueos vencidos sin procesar hasta la proxima ejecucion.",
            )
    return liberados


__all__ = ["TAMANO_LOTE", "expirar_bloqueos"]
