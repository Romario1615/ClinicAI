"""Pruebas del contorno HTTP de autenticacion.

Lo que se comprueba aqui y no en las pruebas del servicio:

* El **codigo de estado** y la **forma del cuerpo** de cada error, que es el
  contrato con el frontend.
* Que la respuesta **no filtre** lo que no debe: ni el hash de la contrasena,
  ni el secreto de segundo factor, ni el valor rechazado en un error de
  validacion.
* Que el contador de intentos fallidos **sobreviva** a la excepcion. Es el
  fallo mas facil de introducir en esta capa: si el manejador de errores
  deshiciera la transaccion, el bloqueo por fuerza bruta no se activaria
  nunca y la suite del servicio seguiria en verde.
* Que las cabeceras de seguridad y el identificador de correlacion esten en
  todas las respuestas, incluidas las de error.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.organizacion.modelos import Clinica
from app.modulos.usuarios.modelos import RolPermiso, Usuario
from app.nucleo.reloj import RelojFijo
from pruebas.api.conftest import (
    CONTRASENA,
    RedisEnMemoria,
    cabecera_bearer,
    conceder_permisos,
    iniciar_sesion,
)

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


def _ruta(api: str, sufijo: str) -> str:
    return f"{api}/autenticacion{sufijo}"


# ===========================================================================
#  Inicio de sesion
# ===========================================================================
class TestInicioSesion:
    async def test_credenciales_correctas_devuelven_el_par_de_tokens(
        self, cliente: AsyncClient, api: str, usuario: Usuario, clinica: Clinica
    ) -> None:
        respuesta = await cliente.post(
            _ruta(api, "/sesion"),
            json={
                "correo": usuario.correo,
                "contrasena": CONTRASENA,
                "clinica_id": str(clinica.id),
            },
        )

        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo["tipo_token"] == "Bearer"
        assert cuerpo["token_acceso"]
        assert cuerpo["token_refresco"]
        assert cuerpo["requiere_segundo_factor"] is False

        # La respuesta no lleva nada del modelo de usuario.
        texto = respuesta.text
        assert "hash_contrasena" not in texto
        assert "secreto_2fa" not in texto
        assert CONTRASENA not in texto

    async def test_la_respuesta_lleva_las_cabeceras_de_seguridad(
        self, cliente: AsyncClient, api: str, usuario: Usuario, clinica: Clinica
    ) -> None:
        respuesta = await cliente.post(
            _ruta(api, "/sesion"),
            json={
                "correo": usuario.correo,
                "contrasena": CONTRASENA,
                "clinica_id": str(clinica.id),
            },
        )

        assert respuesta.headers["X-Content-Type-Options"] == "nosniff"
        assert respuesta.headers["X-Frame-Options"] == "DENY"
        # Un par de tokens no puede quedarse en la cache de un proxy.
        assert respuesta.headers["Cache-Control"] == "no-store"
        assert respuesta.headers["X-Request-Id"]

    async def test_contrasena_incorrecta_devuelve_401_generico(
        self, cliente: AsyncClient, api: str, usuario: Usuario, clinica: Clinica
    ) -> None:
        respuesta = await cliente.post(
            _ruta(api, "/sesion"),
            json={
                "correo": usuario.correo,
                "contrasena": "incorrecta",
                "clinica_id": str(clinica.id),
            },
        )

        assert respuesta.status_code == 401
        cuerpo = respuesta.json()
        assert cuerpo["codigo"] == "CREDENCIALES_INVALIDAS"
        assert "correlacion_id" in cuerpo
        assert respuesta.headers["WWW-Authenticate"] == "Bearer"

    async def test_correo_inexistente_responde_exactamente_igual(
        self, cliente: AsyncClient, api: str, usuario: Usuario, clinica: Clinica
    ) -> None:
        """Si se distinguieran, se podria enumerar al personal de la clinica."""
        con_cuenta = await cliente.post(
            _ruta(api, "/sesion"),
            json={
                "correo": usuario.correo,
                "contrasena": "incorrecta",
                "clinica_id": str(clinica.id),
            },
        )
        sin_cuenta = await cliente.post(
            _ruta(api, "/sesion"),
            json={
                "correo": "nadie@example.invalid",
                "contrasena": "incorrecta",
                "clinica_id": str(clinica.id),
            },
        )

        assert con_cuenta.status_code == sin_cuenta.status_code == 401
        assert con_cuenta.json()["codigo"] == sin_cuenta.json()["codigo"]
        assert con_cuenta.json()["mensaje"] == sin_cuenta.json()["mensaje"]

    async def test_el_contador_de_intentos_sobrevive_al_error(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
    ) -> None:
        """El fallo mas facil de introducir en esta capa.

        Si el manejador de errores deshiciera la transaccion, el contador
        volveria a cero en cada intento y el bloqueo por fuerza bruta no se
        activaria jamas, con toda la suite del servicio en verde.
        """
        for _ in range(3):
            await cliente.post(
                _ruta(api, "/sesion"),
                json={
                    "correo": usuario.correo,
                    "contrasena": "incorrecta",
                    "clinica_id": str(clinica.id),
                },
            )

        await sesion.refresh(usuario)
        assert usuario.intentos_fallidos == 3

    async def test_el_bloqueo_responde_401_con_codigo_propio(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        configuracion_max_intentos: int,
    ) -> None:
        for _ in range(configuracion_max_intentos):
            await cliente.post(
                _ruta(api, "/sesion"),
                json={
                    "correo": usuario.correo,
                    "contrasena": "incorrecta",
                    "clinica_id": str(clinica.id),
                },
            )

        respuesta = await cliente.post(
            _ruta(api, "/sesion"),
            json={
                "correo": usuario.correo,
                "contrasena": CONTRASENA,
                "clinica_id": str(clinica.id),
            },
        )

        # 401 y no 423 a proposito: el codigo HTTP es el mismo para todo
        # fallo de autenticacion, de modo que observarlo desde fuera no
        # distinga "esta cuenta existe y esta bloqueada" de "credenciales
        # incorrectas". Quien necesita distinguirlo -- el frontend -- lo hace
        # por `codigo`, que es el discriminador estable del contrato.
        assert respuesta.status_code == 401
        assert respuesta.json()["codigo"] == "CUENTA_BLOQUEADA"
        assert respuesta.headers["WWW-Authenticate"] == "Bearer"

    async def test_datos_invalidos_devuelven_422_sin_reflejar_el_valor(
        self, cliente: AsyncClient, api: str, clinica: Clinica
    ) -> None:
        """Pydantic incluye el valor rechazado en `input`; aqui no sale.

        Ese valor puede ser la contrasena o el documento de un paciente, y
        devolverlo lo pondria tambien en los registros de cualquier proxy
        intermedio.
        """
        respuesta = await cliente.post(
            _ruta(api, "/sesion"),
            json={
                "correo": "esto-no-es-un-correo",
                "contrasena": "ContrasenaSecretaDePrueba",
                "clinica_id": str(clinica.id),
            },
        )

        assert respuesta.status_code == 422
        cuerpo = respuesta.json()
        assert cuerpo["codigo"] == "DATOS_INVALIDOS"
        assert any(c["campo"].endswith("correo") for c in cuerpo["detalles"]["campos"])
        assert "ContrasenaSecretaDePrueba" not in respuesta.text
        assert "esto-no-es-un-correo" not in respuesta.text

    async def test_un_campo_de_mas_se_rechaza(
        self, cliente: AsyncClient, api: str, usuario: Usuario, clinica: Clinica
    ) -> None:
        """`extra="forbid"`: un campo desconocido suele ser una errata.

        Aceptarlo en silencio deja al cliente creyendo que envio algo que el
        servidor nunca leyo.
        """
        respuesta = await cliente.post(
            _ruta(api, "/sesion"),
            json={
                "correo": usuario.correo,
                "contrasena": CONTRASENA,
                "clinica_id": str(clinica.id),
                "es_administrador": True,
            },
        )

        assert respuesta.status_code == 422

    async def test_el_limite_de_intentos_devuelve_429_con_retry_after(
        self,
        cliente: AsyncClient,
        api: str,
        usuario: Usuario,
        clinica: Clinica,
        configuracion_limite_login: int,
    ) -> None:
        cuerpo = {
            "correo": usuario.correo,
            "contrasena": "incorrecta",
            "clinica_id": str(clinica.id),
        }
        ultima = None
        for _ in range(configuracion_limite_login + 1):
            ultima = await cliente.post(_ruta(api, "/sesion"), json=cuerpo)

        assert ultima is not None
        assert ultima.status_code == 429
        assert ultima.json()["codigo"] == "LIMITE_TASA_EXCEDIDO"
        assert int(ultima.headers["Retry-After"]) >= 1

    async def test_sin_contador_el_login_falla_cerrado(
        self,
        cliente: AsyncClient,
        api: str,
        usuario: Usuario,
        clinica: Clinica,
        redis_falso: RedisEnMemoria,
    ) -> None:
        """Sin limitador, aceptar intentos abriria la fuerza bruta sin tope.

        Se prefiere que nadie pueda entrar durante la caida a que cualquiera
        pueda probar contrasenas sin limite (ver `app/nucleo/limite_tasa.py`).
        """
        redis_falso.fallo = ConnectionError("Redis no responde")

        respuesta = await cliente.post(
            _ruta(api, "/sesion"),
            json={
                "correo": usuario.correo,
                "contrasena": CONTRASENA,
                "clinica_id": str(clinica.id),
            },
        )

        assert respuesta.status_code == 503
        assert respuesta.json()["codigo"] == "PROVEEDOR_EXTERNO_NO_DISPONIBLE"


# ===========================================================================
#  Rotacion y cierre
# ===========================================================================
class TestRotacionYCierre:
    async def test_el_refresco_devuelve_un_par_nuevo(
        self, cliente: AsyncClient, api: str, usuario: Usuario, clinica: Clinica
    ) -> None:
        tokens = await iniciar_sesion(cliente, usuario, clinica)

        respuesta = await cliente.post(
            _ruta(api, "/refresco"), json={"token_refresco": tokens["token_refresco"]}
        )

        assert respuesta.status_code == 200
        nuevos = respuesta.json()
        assert nuevos["token_refresco"] != tokens["token_refresco"]
        assert nuevos["token_acceso"] != tokens["token_acceso"]

    async def test_reutilizar_el_refresco_devuelve_401_y_mata_la_familia(
        self, cliente: AsyncClient, api: str, usuario: Usuario, clinica: Clinica
    ) -> None:
        tokens = await iniciar_sesion(cliente, usuario, clinica)
        primero = await cliente.post(
            _ruta(api, "/refresco"), json={"token_refresco": tokens["token_refresco"]}
        )
        assert primero.status_code == 200

        repetido = await cliente.post(
            _ruta(api, "/refresco"), json={"token_refresco": tokens["token_refresco"]}
        )
        assert repetido.status_code == 401
        assert repetido.json()["codigo"] == "TOKEN_INVALIDO"

        # El par emitido justo antes tampoco sirve: cayo la familia entera.
        posterior = await cliente.post(
            _ruta(api, "/refresco"),
            json={"token_refresco": primero.json()["token_refresco"]},
        )
        assert posterior.status_code == 401

    async def test_un_token_de_acceso_no_sirve_como_refresco(
        self, cliente: AsyncClient, api: str, usuario: Usuario, clinica: Clinica
    ) -> None:
        tokens = await iniciar_sesion(cliente, usuario, clinica)

        respuesta = await cliente.post(
            _ruta(api, "/refresco"), json={"token_refresco": tokens["token_acceso"]}
        )
        assert respuesta.status_code == 401

    async def test_cerrar_sesion_invalida_el_refresco(
        self, cliente: AsyncClient, api: str, usuario: Usuario, clinica: Clinica
    ) -> None:
        tokens = await iniciar_sesion(cliente, usuario, clinica)

        cierre = await cliente.post(
            _ruta(api, "/cierre"), json={"token_refresco": tokens["token_refresco"]}
        )
        assert cierre.status_code == 204

        reintento = await cliente.post(
            _ruta(api, "/refresco"), json={"token_refresco": tokens["token_refresco"]}
        )
        assert reintento.status_code == 401

    async def test_cerrar_una_sesion_que_no_consta_devuelve_204(
        self, cliente: AsyncClient, api: str, usuario: Usuario, clinica: Clinica
    ) -> None:
        """Distinguirlo permitiria comprobar si un token robado sigue vivo."""
        tokens = await iniciar_sesion(cliente, usuario, clinica)
        await cliente.post(_ruta(api, "/cierre"), json={"token_refresco": tokens["token_refresco"]})

        segunda = await cliente.post(
            _ruta(api, "/cierre"), json={"token_refresco": tokens["token_refresco"]}
        )
        assert segunda.status_code == 204


# ===========================================================================
#  Identidad y autorizacion
# ===========================================================================
class TestIdentidad:
    async def test_devuelve_permisos_y_ambito(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
    ) -> None:
        await conceder_permisos(
            sesion, usuario, clinica, "paciente.leer_administrativo", "cita.crear"
        )
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.get(_ruta(api, "/yo"), headers=cabeceras)

        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo["usuario_id"] == str(usuario.id)
        assert cuerpo["correo"] == usuario.correo
        assert set(cuerpo["permisos"]) == {"paciente.leer_administrativo", "cita.crear"}
        assert cuerpo["ambito"]["clinica_id"] == str(clinica.id)
        assert cuerpo["ambito"]["todas_las_sedes"] is False
        # El esquema de salida es explicito: nada del modelo de usuario.
        assert "hash_contrasena" not in respuesta.text
        assert "secreto_2fa_cifrado" not in respuesta.text
        assert "intentos_fallidos" not in respuesta.text

    async def test_sin_cabecera_devuelve_401(self, cliente: AsyncClient, api: str) -> None:
        respuesta = await cliente.get(_ruta(api, "/yo"))

        assert respuesta.status_code == 401
        assert respuesta.json()["codigo"] == "NO_AUTENTICADO"
        assert respuesta.headers["WWW-Authenticate"] == "Bearer"

    @pytest.mark.parametrize(
        "cabecera",
        [
            "",
            "Bearer",
            "Bearer ",
            "Basic dXN1YXJpbzpjbGF2ZQ==",
            "token-suelto-sin-esquema",
        ],
    )
    async def test_cabeceras_mal_formadas_devuelven_401(
        self, cliente: AsyncClient, api: str, cabecera: str
    ) -> None:
        respuesta = await cliente.get(_ruta(api, "/yo"), headers={"Authorization": cabecera})
        assert respuesta.status_code == 401

    async def test_un_token_manipulado_devuelve_401(
        self, cliente: AsyncClient, api: str, usuario: Usuario, clinica: Clinica
    ) -> None:
        tokens = await iniciar_sesion(cliente, usuario, clinica)
        cabeza, carga, firma = tokens["token_acceso"].split(".")
        manipulado = f"{cabeza}.{carga}.{'a' * len(firma)}"

        respuesta = await cliente.get(
            _ruta(api, "/yo"), headers={"Authorization": f"Bearer {manipulado}"}
        )
        assert respuesta.status_code == 401

    async def test_el_token_caduca(
        self,
        cliente: AsyncClient,
        api: str,
        usuario: Usuario,
        clinica: Clinica,
        reloj: RelojFijo,
    ) -> None:
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)
        assert (await cliente.get(_ruta(api, "/yo"), headers=cabeceras)).status_code == 200

        reloj.avanzar(minutes=16)

        assert (await cliente.get(_ruta(api, "/yo"), headers=cabeceras)).status_code == 401

    async def test_desactivar_la_cuenta_invalida_el_token_en_uso(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
    ) -> None:
        """Sin esto, dar de baja a alguien no le quita el acceso hasta que
        caduque el token, y en datos clinicos ese retraso importa."""
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)
        assert (await cliente.get(_ruta(api, "/yo"), headers=cabeceras)).status_code == 200

        usuario.activo = False
        await sesion.flush()

        assert (await cliente.get(_ruta(api, "/yo"), headers=cabeceras)).status_code == 401

    async def test_retirar_un_permiso_surte_efecto_sin_token_nuevo(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
    ) -> None:
        """Los permisos se leen de la base en cada peticion, no del token."""
        rol = await conceder_permisos(sesion, usuario, clinica, "paciente.leer_administrativo")
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        antes = await cliente.get(_ruta(api, "/yo"), headers=cabeceras)
        assert "paciente.leer_administrativo" in antes.json()["permisos"]

        await sesion.execute(sa.delete(RolPermiso).where(RolPermiso.rol_id == rol.id))
        await sesion.flush()

        despues = await cliente.get(_ruta(api, "/yo"), headers=cabeceras)
        assert despues.json()["permisos"] == []


# ===========================================================================
#  Sondas de salud
# ===========================================================================
class TestSalud:
    async def test_vivo_responde_sin_autenticacion(self, cliente: AsyncClient) -> None:
        respuesta = await cliente.get("/salud/vivo")
        assert respuesta.status_code == 200
        assert respuesta.json() == {"estado": "vivo"}

    async def test_listo_responde(self, cliente: AsyncClient) -> None:
        respuesta = await cliente.get("/salud/listo")
        assert respuesta.status_code == 200
        assert respuesta.json()["estado"] == "listo"
