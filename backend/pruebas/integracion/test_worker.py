"""Pruebas del arranque del worker.

Estas comprobaciones parecen triviales y no lo son: son las unicas que
detectan los fallos de cableado antes del despliegue. Un nombre de funcion mal
escrito en `cron_jobs`, un `on_startup` que no deja el gestor de base de datos
en el contexto o unos ajustes de Redis mal formados no producen ningun error
al importar el modulo -- producen un worker que arranca, se queda quieto y no
ejecuta nada, que es el fallo mas caro de diagnosticar porque no hay
excepcion que seguir.

El barrido en si tiene sus propias pruebas en `test_tareas_agenda.py`. Aqui
solo se verifica que el worker sepa encontrarlo y ejecutarlo.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.nucleo.bd import GestorBaseDatos
from app.nucleo.configuracion import Configuracion
from app.nucleo.reloj import Reloj
from app.tareas.agenda import expirar_bloqueos
from app.tareas.contexto import al_arrancar, al_parar
from app.tareas.worker import ConfiguracionWorker

pytestmark = [pytest.mark.integracion, pytest.mark.asyncio]


class TestConfiguracionDelWorker:
    async def test_los_trabajos_periodicos_apuntan_a_funciones_registradas(self) -> None:
        """Un cron que apunta a una funcion no registrada nunca se ejecuta.

        ARQ no avisa: el worker arranca, el cron dispara y no encuentra nada
        que llamar. Sin esta comprobacion, el sintoma seria que los bloqueos
        dejan de liberarse y nadie sabe por que.
        """
        registradas = {f.__name__ for f in ConfiguracionWorker.functions}

        for trabajo in ConfiguracionWorker.cron_jobs:
            # ARQ antepone "cron:" al nombre del trabajo; lo que hay que
            # comparar es la corrutina que ejecutara.
            nombre = trabajo.coroutine.__name__
            assert nombre in registradas, (
                f"El cron '{trabajo.name}' llama a '{nombre}', que no esta en "
                "`functions`: no se ejecutara."
            )

    async def test_el_barrido_de_bloqueos_esta_programado(self) -> None:
        nombres = {t.coroutine.__name__ for t in ConfiguracionWorker.cron_jobs}
        assert expirar_bloqueos.__name__ in nombres

    async def test_los_periodicos_son_unicos_entre_replicas(self) -> None:
        """Sin `unique`, cada replica ejecutaria el mismo cron.

        No romperia los datos -- el barrido usa `FOR UPDATE SKIP LOCKED` --
        pero multiplicaria las consultas sin repartir mas trabajo.
        """
        for trabajo in ConfiguracionWorker.cron_jobs:
            assert trabajo.unique is True, trabajo.name

    async def test_no_se_reintentan_los_trabajos(self) -> None:
        """Reintentar un error de programacion solo repite el error.

        Los reintentos que importan -- los envios a terceros -- los gestiona el
        outbox con su propio contador y su retroceso (ADR-0008).
        """
        assert ConfiguracionWorker.max_tries == 1
        for trabajo in ConfiguracionWorker.cron_jobs:
            assert trabajo.max_tries == 1, trabajo.name

    async def test_los_ajustes_de_redis_se_resuelven(self) -> None:
        """Una configuracion invalida debe romper al importar, no en el
        primer trabajo, media hora despues y dentro de un reintento."""
        ajustes = ConfiguracionWorker.redis_settings
        configuracion = Configuracion()

        assert ajustes.host == configuracion.redis_host
        assert ajustes.port == configuracion.redis_puerto


class TestCicloDeVida:
    async def test_el_arranque_deja_el_contexto_completo(self) -> None:
        """Si faltara una clave, el trabajo fallaria con un `KeyError` opaco."""
        ctx: dict[Any, Any] = {}
        try:
            await al_arrancar(ctx)

            assert isinstance(ctx["configuracion"], Configuracion)
            assert isinstance(ctx["reloj"], Reloj)
            assert isinstance(ctx["gestor_bd"], GestorBaseDatos)
        finally:
            await al_parar(ctx)

    async def test_el_worker_puede_ejecutar_su_trabajo_de_verdad(self) -> None:
        """Recorrido completo: arrancar, ejecutar el barrido, parar.

        Usa la base de datos real y no un doble. Sin bloqueos vencidos no
        cambia nada, y ese es justo el caso que interesa comprobar: que el
        trabajo se ejecuta sin error cuando no hay trabajo que hacer, que es
        lo que ocurrira la mayor parte de las veces.
        """
        ctx: dict[Any, Any] = {}
        try:
            await al_arrancar(ctx)
            liberados = await expirar_bloqueos(ctx)
            assert liberados >= 0
        finally:
            await al_parar(ctx)

    async def test_parar_sin_haber_arrancado_no_falla(self) -> None:
        """Si ARQ aborta el arranque a medias, el apagado sigue ejecutandose."""
        await al_parar({})
