"""Pruebas de la dependencia de autorizacion.

`exige_permiso` es la pieza que decide quien puede llamar a cada endpoint. Se
prueba contra endpoints de sonda montados aqui mismo en lugar de contra una
ruta real del sistema, por dos motivos:

* Aisla el fallo. Si una prueba falla, el problema esta en la autorizacion y
  no en la logica del endpoint que se estuviera usando de excusa.
* No caduca. Una prueba escrita sobre `POST /citas` deja de cubrir esto en
  cuanto ese endpoint cambia de permiso o desaparece.

Los endpoints de sonda usan la dependencia **real**, no una copia: si
`exige_permiso` cambia, estas pruebas lo notan.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.modelos import Auditoria
from app.modulos.organizacion.modelos import Clinica
from app.modulos.usuarios.modelos import RolPermiso, Usuario
from app.nucleo.auditoria import AccionAuditada, ResultadoAuditoria
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import exige_permiso
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]

PERMISO_LECTURA = "paciente.leer_administrativo"
PERMISO_ESCRITURA = "cita.crear"


# Las dependencias se declaran a nivel de modulo, no dentro de la fixture.
#
# Con `from __future__ import annotations` las anotaciones son cadenas, y
# FastAPI las resuelve contra los globales del modulo: un alias definido como
# variable local no existe ahi, y el parametro acaba interpretado como cuerpo
# de la peticion. El sintoma es un 422 desconcertante en vez de un 200.
#
# Se usa `Annotated[...]` y no un valor por omision porque es la forma que
# usan las rutas reales, de modo que las sondas ejercitan el mismo camino.
DepLectura = Annotated[Principal, Depends(exige_permiso(PERMISO_LECTURA))]
DepCualquiera = Annotated[Principal, Depends(exige_permiso(PERMISO_LECTURA, PERMISO_ESCRITURA))]
DepAmbos = Annotated[
    Principal,
    Depends(exige_permiso(PERMISO_LECTURA, PERMISO_ESCRITURA, exigir_todos=True)),
]


@pytest.fixture
def aplicacion_con_sondas(aplicacion: FastAPI) -> FastAPI:
    """Anade endpoints que solo existen para probar la autorizacion."""

    @aplicacion.get("/sonda/lectura")
    async def solo_lectura(principal: DepLectura) -> dict[str, str]:
        return {"actor": str(principal.actor_id)}

    @aplicacion.get("/sonda/cualquiera")
    async def cualquiera_de_los_dos(principal: DepCualquiera) -> dict[str, str]:
        return {"actor": str(principal.actor_id)}

    @aplicacion.get("/sonda/ambos")
    async def los_dos(principal: DepAmbos) -> dict[str, str]:
        return {"actor": str(principal.actor_id)}

    return aplicacion


@pytest_asyncio.fixture
async def sonda(aplicacion_con_sondas: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=aplicacion_con_sondas),
        base_url="http://pruebas.invalid",
    ) as http:
        yield http


async def _denegaciones(sesion: AsyncSession, usuario: Usuario) -> list[Auditoria]:
    filas = await sesion.execute(
        sa.select(Auditoria).where(
            Auditoria.actor_id == usuario.id,
            Auditoria.accion == AccionAuditada.PERMISO_DENEGADO.value,
        )
    )
    return list(filas.scalars())


class TestPermiso:
    async def test_con_el_permiso_se_pasa(
        self,
        sonda: AsyncClient,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
    ) -> None:
        await conceder_permisos(sesion, usuario, clinica, PERMISO_LECTURA)
        cabeceras = await cabecera_bearer(sonda, usuario, clinica)

        respuesta = await sonda.get("/sonda/lectura", headers=cabeceras)

        assert respuesta.status_code == 200
        assert respuesta.json()["actor"] == str(usuario.id)

    async def test_sin_el_permiso_se_deniega_con_403(
        self,
        sonda: AsyncClient,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
    ) -> None:
        """Autenticado no es autorizado: 401 y 403 no son lo mismo."""
        await conceder_permisos(sesion, usuario, clinica, PERMISO_ESCRITURA)
        cabeceras = await cabecera_bearer(sonda, usuario, clinica)

        respuesta = await sonda.get("/sonda/lectura", headers=cabeceras)

        assert respuesta.status_code == 403
        cuerpo = respuesta.json()
        assert cuerpo["codigo"] == "PERMISO_DENEGADO"
        assert cuerpo["detalles"]["permiso_requerido"] == [PERMISO_LECTURA]

    async def test_un_usuario_sin_rol_no_pasa(
        self, sonda: AsyncClient, usuario: Usuario, clinica: Clinica
    ) -> None:
        """Sin rol el conjunto de permisos es vacio, y vacio no da acceso."""
        cabeceras = await cabecera_bearer(sonda, usuario, clinica)

        respuesta = await sonda.get("/sonda/lectura", headers=cabeceras)

        assert respuesta.status_code == 403

    async def test_sin_token_se_responde_401_y_no_403(self, sonda: AsyncClient) -> None:
        """El orden importa: primero quien eres, despues que puedes.

        Un 403 sin token confirmaria que el endpoint existe y que el unico
        obstaculo es el permiso.
        """
        respuesta = await sonda.get("/sonda/lectura")

        assert respuesta.status_code == 401
        assert respuesta.json()["codigo"] == "NO_AUTENTICADO"

    async def test_con_varios_permisos_basta_uno(
        self,
        sonda: AsyncClient,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
    ) -> None:
        await conceder_permisos(sesion, usuario, clinica, PERMISO_ESCRITURA)
        cabeceras = await cabecera_bearer(sonda, usuario, clinica)

        assert (await sonda.get("/sonda/cualquiera", headers=cabeceras)).status_code == 200

    async def test_con_exigir_todos_no_basta_uno(
        self,
        sonda: AsyncClient,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
    ) -> None:
        await conceder_permisos(sesion, usuario, clinica, PERMISO_ESCRITURA)
        cabeceras = await cabecera_bearer(sonda, usuario, clinica)

        respuesta = await sonda.get("/sonda/ambos", headers=cabeceras)

        assert respuesta.status_code == 403
        assert set(respuesta.json()["detalles"]["permiso_requerido"]) == {
            PERMISO_LECTURA,
            PERMISO_ESCRITURA,
        }

    async def test_con_exigir_todos_y_los_dos_permisos_se_pasa(
        self,
        sonda: AsyncClient,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
    ) -> None:
        await conceder_permisos(sesion, usuario, clinica, PERMISO_LECTURA, PERMISO_ESCRITURA)
        cabeceras = await cabecera_bearer(sonda, usuario, clinica)

        assert (await sonda.get("/sonda/ambos", headers=cabeceras)).status_code == 200

    async def test_retirar_el_permiso_cierra_el_acceso_de_inmediato(
        self,
        sonda: AsyncClient,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
    ) -> None:
        """Con el mismo token: los permisos no viajan dentro."""
        rol = await conceder_permisos(sesion, usuario, clinica, PERMISO_LECTURA)
        cabeceras = await cabecera_bearer(sonda, usuario, clinica)
        assert (await sonda.get("/sonda/lectura", headers=cabeceras)).status_code == 200

        await sesion.execute(sa.delete(RolPermiso).where(RolPermiso.rol_id == rol.id))
        await sesion.flush()

        assert (await sonda.get("/sonda/lectura", headers=cabeceras)).status_code == 403

    async def test_exige_permiso_sin_codigos_es_un_error_de_programacion(self) -> None:
        """Un endpoint sin permiso declarado queda abierto.

        Falla al construir la aplicacion y no en tiempo de peticion, que es
        cuando ya habria servido datos.
        """
        with pytest.raises(ValueError, match="al menos un codigo"):
            exige_permiso()


class TestSegundoFactor:
    async def test_el_rol_con_2fa_pendiente_no_opera(
        self,
        sonda: AsyncClient,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        configuracion_rol_con_2fa: str,
    ) -> None:
        """Tener el permiso no basta si el segundo factor esta pendiente.

        El token se emite para que el cliente pueda pedir el codigo; es aqui
        donde se le impide operar con el.
        """
        await conceder_permisos(
            sesion,
            usuario,
            clinica,
            PERMISO_LECTURA,
            codigo_rol=configuracion_rol_con_2fa,
        )

        # Se inicia sesion sin codigo: el usuario no tiene 2FA configurado,
        # asi que el servicio rechaza el login por completo.
        respuesta = await sonda.post(
            "/api/v1/autenticacion/sesion",
            json={
                "correo": usuario.correo,
                "contrasena": "ContrasenaDePrueba123",
                "clinica_id": str(clinica.id),
            },
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "SEGUNDO_FACTOR_REQUERIDO"


class TestAuditoriaDeDenegaciones:
    async def test_la_denegacion_queda_registrada(
        self,
        sonda: AsyncClient,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
    ) -> None:
        """Sin este registro, sondear datos ajenos de forma sistematica seria
        invisible: el atacante recibe un 403 y no queda rastro."""
        await conceder_permisos(sesion, usuario, clinica, PERMISO_ESCRITURA)
        cabeceras = await cabecera_bearer(sonda, usuario, clinica)

        await sonda.get("/sonda/lectura", headers=cabeceras)

        filas = await _denegaciones(sesion, usuario)
        assert len(filas) == 1
        assert filas[0].resultado == ResultadoAuditoria.DENEGADO.value
        assert filas[0].motivo is not None
        assert PERMISO_LECTURA in filas[0].motivo
        assert filas[0].metadatos is not None
        assert filas[0].metadatos["ruta"] == "/sonda/lectura"
        assert filas[0].correlacion_id

    async def test_el_acceso_concedido_no_genera_denegacion(
        self,
        sonda: AsyncClient,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
    ) -> None:
        await conceder_permisos(sesion, usuario, clinica, PERMISO_LECTURA)
        cabeceras = await cabecera_bearer(sonda, usuario, clinica)

        await sonda.get("/sonda/lectura", headers=cabeceras)

        assert await _denegaciones(sesion, usuario) == []
