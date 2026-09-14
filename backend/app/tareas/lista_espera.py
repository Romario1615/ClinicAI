"""Vence ofertas y continua la cola dentro de la misma transaccion."""

from typing import Any

from app.modulos.agenda.modelos import Cita
from app.modulos.auditoria.repositorio import RepositorioAuditoria
from app.modulos.lista_espera.servicios import ServicioListaEspera
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import principal_sistema
from app.nucleo.bd import GestorBaseDatos
from app.nucleo.reloj import Reloj


async def expirar_ofertas(ctx: dict[Any, Any], *_argumentos: Any, **_opciones: Any) -> int:
    gestor: GestorBaseDatos = ctx["gestor_bd"]
    reloj: Reloj = ctx["reloj"]
    cantidad = 0
    async for sesion in gestor.sesion():
        servicio = ServicioListaEspera(sesion, reloj)
        auditor = RepositorioAuditoria(sesion)
        vencidas = await servicio.expirar_ofertas_vencidas(principal=principal_sistema())
        for oferta in vencidas:
            cita = await sesion.get(Cita, oferta.cita_liberada_id)
            if cita is None:
                continue
            principal = principal_sistema(cita.clinica_id)
            await auditor.registrar(
                [
                    construir_entrada(
                        accion=AccionAuditada.OFERTA_EXPIRADA,
                        principal=principal,
                        ahora=reloj.ahora(),
                        entidad_tipo="oferta_turno",
                        entidad_id=oferta.id,
                    )
                ]
            )
            siguiente = await servicio.ofrecer_turno(cita, principal=principal)
            await auditor.registrar(siguiente.auditoria)
        await sesion.commit()
        cantidad = len(vencidas)
    return cantidad
