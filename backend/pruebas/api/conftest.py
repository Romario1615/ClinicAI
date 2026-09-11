"""Fixtures de las pruebas de API.

Se levanta la aplicacion real -- middleware, manejadores de error,
dependencias y rutas -- contra PostgreSQL real, y se la habla por ASGI sin
abrir un puerto. Lo que se prueba aqui es el contorno HTTP: codigos de estado,
forma del cuerpo, cabeceras y, sobre todo, **quien puede llamar a que**.

Aislamiento
-----------
Cada prueba corre dentro de una transaccion que se deshace al terminar, igual
que las de integracion. Para conseguirlo hay que interceptar dos caminos
distintos hacia la base de datos:

1. La dependencia `obtener_sesion`, que usan las rutas.
2. `GestorBaseDatos.sesion()`, que usa la auditoria de accesos denegados --
   deliberadamente fuera de la transaccion de la peticion, para que el
   registro sobreviva al error.

Si solo se interceptara el primero, cada prueba de permiso denegado dejaria
filas de auditoria reales en la base de desarrollo. Se sustituye el gestor
entero por uno que devuelve siempre la sesion de la prueba.

Redis
-----
Se usa un doble en memoria en lugar de Redis real. El limitador ya tiene sus
propias pruebas; aqui interesa que las rutas lo invoquen con la clave y el
limite correctos, y un contador en memoria lo demuestra igual de bien sin
hacer la suite dependiente del estado de un contenedor compartido.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import PREFIJO_API, crear_aplicacion
from app.modulos.organizacion.modelos import Clinica
from app.modulos.usuarios.modelos import Permiso, Rol, RolPermiso, Usuario, UsuarioRol
from app.nucleo.autorizacion import CATALOGO_PERMISOS
from app.nucleo.bd import GestorBaseDatos
from app.nucleo.configuracion import Configuracion
from app.nucleo.dependencias import obtener_sesion
from app.nucleo.reloj import RelojFijo
from app.nucleo.seguridad import hashear_contrasena
from pruebas.conftest import INSTANTE_REFERENCIA

CONTRASENA = "ContrasenaDePrueba123"


# ---------------------------------------------------------------------------
#  Dobles
# ---------------------------------------------------------------------------
class RedisEnMemoria:
    """Contador de ventana deslizante en memoria.

    Reproduce solo lo que el limitador necesita de `EVAL`: podar, contar y
    anadir. No pretende ser Redis; pretende que la ruta reciba la misma
    respuesta que recibiria de Redis.
    """

    def __init__(self) -> None:
        self.eventos: dict[str, list[int]] = {}
        # Cuando es distinto de None, `eval` lanza esa excepcion. Sirve para
        # comprobar que el login falla cerrado si el contador no responde.
        self.fallo: Exception | None = None

    async def eval(self, script: str, numkeys: int, *args: str) -> list[int]:
        if self.fallo is not None:
            raise self.fallo

        clave, ahora_ms, ventana_ms, limite, evento = (
            args[0],
            int(args[1]),
            int(args[2]),
            int(args[3]),
            int(args[4]),
        )
        vivos = [m for m in self.eventos.get(clave, []) if m > ahora_ms - ventana_ms]
        if len(vivos) >= limite:
            self.eventos[clave] = vivos
            espera = (min(vivos) + ventana_ms) - ahora_ms
            return [0, 0, espera]

        vivos.append(evento // 1000)
        self.eventos[clave] = vivos
        return [1, limite - len(vivos), 0]


class GestorDeUnaSesion(GestorBaseDatos):
    """Gestor que siempre entrega la sesion de la prueba.

    Hereda de `GestorBaseDatos` para satisfacer las anotaciones de tipo, pero
    no construye motor propio: todo pasa por la sesion aislada de la prueba.
    """

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion_prueba = sesion

    async def sesion(self) -> AsyncIterator[AsyncSession]:  # type: ignore[override]
        yield self._sesion_prueba

    async def extensiones_faltantes(self) -> set[str]:
        return set()

    async def cerrar(self) -> None:
        return None


# ---------------------------------------------------------------------------
#  Infraestructura
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def configuracion() -> Configuracion:
    return Configuracion()


@pytest_asyncio.fixture(scope="session")
async def motor(configuracion: Configuracion) -> AsyncIterator[sa.ext.asyncio.AsyncEngine]:
    creado = create_async_engine(configuracion.url_base_datos, poolclass=sa.pool.NullPool)
    yield creado
    await creado.dispose()


@pytest_asyncio.fixture
async def sesion(motor: sa.ext.asyncio.AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Sesion aislada: lo que escriba la peticion se deshace al terminar.

    La ruta hace `commit`, pero con `join_transaction_mode="create_savepoint"`
    ese commit solo confirma el savepoint interno; al deshacer la transaccion
    externa no queda nada en la base.
    """
    async with motor.connect() as conexion:
        transaccion = await conexion.begin()
        fabrica = async_sessionmaker(
            bind=conexion,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        sesion_prueba = fabrica()
        try:
            yield sesion_prueba
        finally:
            await sesion_prueba.close()
            await transaccion.rollback()


@pytest.fixture
def reloj() -> RelojFijo:
    return RelojFijo(INSTANTE_REFERENCIA)


@pytest.fixture
def configuracion_max_intentos(configuracion: Configuracion) -> int:
    """Intentos permitidos antes del bloqueo, tal como los tiene el entorno.

    Se lee de la configuracion en lugar de fijar un numero: si alguien
    endurece la politica, la prueba sigue midiendo la politica vigente en
    lugar de una que ya no existe.
    """
    return configuracion.max_intentos_login


@pytest.fixture
def configuracion_limite_login(configuracion: Configuracion) -> int:
    return configuracion.limite_login_por_minuto


@pytest.fixture
def configuracion_rol_con_2fa(configuracion: Configuracion) -> str:
    """Primer rol de la lista de roles con segundo factor obligatorio."""
    return configuracion.lista_roles_con_2fa[0]


@pytest.fixture
def redis_falso() -> RedisEnMemoria:
    return RedisEnMemoria()


@pytest.fixture
def aplicacion(
    configuracion: Configuracion,
    sesion: AsyncSession,
    reloj: RelojFijo,
    redis_falso: RedisEnMemoria,
) -> FastAPI:
    app = crear_aplicacion(
        configuracion,
        reloj=reloj,
        gestor_bd=GestorDeUnaSesion(sesion),
        cliente_redis=redis_falso,
        # Reconfigurar structlog en cada prueba sobrescribiria la captura de
        # registros de pytest y ralentizaria la suite sin aportar nada.
        configurar_logs=False,
    )

    async def _sesion_de_prueba() -> AsyncIterator[AsyncSession]:
        yield sesion

    app.dependency_overrides[obtener_sesion] = _sesion_de_prueba
    return app


@pytest_asyncio.fixture
async def cliente(aplicacion: FastAPI) -> AsyncIterator[AsyncClient]:
    """Cliente HTTP sobre ASGI, sin abrir ningun puerto.

    No se ejecuta el ciclo de vida de la aplicacion a proposito: cerraria el
    motor compartido entre pruebas y la comprobacion de extensiones al
    arrancar no aporta nada aqui.
    """
    async with AsyncClient(
        transport=ASGITransport(app=aplicacion),
        base_url="http://pruebas.invalid",
    ) as http:
        yield http


@pytest.fixture
def api() -> str:
    """Prefijo de la API, para no repetirlo en cada prueba."""
    return PREFIJO_API


# ---------------------------------------------------------------------------
#  Datos sinteticos
# ---------------------------------------------------------------------------
@pytest.fixture
def sufijo() -> str:
    return uuid.uuid4().hex[:8]


@pytest_asyncio.fixture
async def clinica(sesion: AsyncSession, sufijo: str) -> Clinica:
    registro = Clinica(
        nombre=f"Clinica de Prueba {sufijo}",
        identificacion_fiscal=f"PRUEBA-API-{sufijo}",
        zona_horaria="America/Guayaquil",
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


@pytest_asyncio.fixture
async def usuario(sesion: AsyncSession, clinica: Clinica, sufijo: str) -> Usuario:
    registro = Usuario(
        clinica_id=clinica.id,
        correo=f"api-{sufijo}@example.invalid",
        hash_contrasena=hashear_contrasena(CONTRASENA),
        nombre="Usuario",
        apellido="De Prueba",
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


async def conceder_permisos(
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    *codigos: str,
    codigo_rol: str | None = None,
) -> Rol:
    """Crea un rol con esos permisos y se lo asigna al usuario.

    Los permisos salen de `CATALOGO_PERMISOS`, no de literales: una prueba que
    inventa un codigo de permiso pasa aunque el catalogo real ya no lo tenga,
    y entonces deja de probar nada.
    """
    rol = Rol(
        clinica_id=clinica.id,
        codigo=codigo_rol or f"rol_api_{uuid.uuid4().hex[:8]}",
        nombre="Rol de prueba",
    )
    sesion.add(rol)
    await sesion.flush()

    for codigo in codigos:
        existente = (
            await sesion.execute(sa.select(Permiso).where(Permiso.codigo == codigo))
        ).scalar_one_or_none()
        if existente is None:
            definicion = next(d for d in CATALOGO_PERMISOS if d.codigo == codigo)
            existente = Permiso(
                codigo=definicion.codigo,
                descripcion=definicion.descripcion,
                categoria=definicion.categoria,
                requiere_relacion_asistencial=definicion.requiere_relacion_asistencial,
                nivel_sensibilidad=definicion.nivel.value,
            )
            sesion.add(existente)
            await sesion.flush()
        sesion.add(RolPermiso(rol_id=rol.id, permiso_id=existente.id))

    sesion.add(UsuarioRol(usuario_id=usuario.id, rol_id=rol.id))
    await sesion.flush()
    return rol


async def iniciar_sesion(
    cliente: AsyncClient, usuario: Usuario, clinica: Clinica
) -> dict[str, Any]:
    """Inicia sesion y devuelve el cuerpo de la respuesta."""
    respuesta = await cliente.post(
        f"{PREFIJO_API}/autenticacion/sesion",
        json={
            "correo": usuario.correo,
            "contrasena": CONTRASENA,
            "clinica_id": str(usuario.clinica_id),
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo: dict[str, Any] = respuesta.json()
    return cuerpo


async def cabecera_bearer(
    cliente: AsyncClient, usuario: Usuario, clinica: Clinica
) -> dict[str, str]:
    tokens = await iniciar_sesion(cliente, usuario, clinica)
    return {"Authorization": f"Bearer {tokens['token_acceso']}"}
