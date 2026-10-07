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

from app.modulos.auditoria.modelos import Auditoria
from app.modulos.organizacion.modelos import Clinica
from app.modulos.usuarios.modelos import Rol, RolPermiso, Sesion, Usuario, UsuarioRol
from app.nucleo.configuracion import Entorno
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


ROLES_BASE = (
    "superadministrador",
    "administrador_clinica",
    "recepcion",
    "asistente",
    "auditor",
    "profesional",
)


async def _rol_del_sistema(sesion: AsyncSession, codigo: str) -> Rol:
    rol = await sesion.scalar(sa.select(Rol).where(Rol.codigo == codigo, Rol.clinica_id.is_(None)))
    if rol is None:
        rol = Rol(codigo=codigo, nombre=codigo.replace("_", " ").title(), es_sistema=True)
        sesion.add(rol)
        await sesion.flush()
    return rol


async def _asignar_rol_sintetico(sesion: AsyncSession, usuario: Usuario, codigo: str) -> None:
    rol = await _rol_del_sistema(sesion, codigo)
    sesion.add(UsuarioRol(usuario_id=usuario.id, rol_id=rol.id))
    usuario.apellido = f"{usuario.apellido} [SINTETICO]"
    await sesion.flush()


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
            },
        )

        assert respuesta.headers["X-Content-Type-Options"] == "nosniff"
        assert respuesta.headers["X-Frame-Options"] == "DENY"
        # Un par de tokens no puede quedarse en la cache de un proxy.
        assert respuesta.headers["Cache-Control"] == "no-store"
        assert respuesta.headers["X-Request-Id"]

    async def test_rol_que_exige_2fa_no_emite_tokens_si_no_esta_configurado(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        configuracion_rol_con_2fa: str,
    ) -> None:
        await conceder_permisos(
            sesion,
            usuario,
            clinica,
            "agenda.leer",
            codigo_rol=configuracion_rol_con_2fa,
        )

        respuesta = await cliente.post(
            _ruta(api, "/sesion"),
            json={"correo": usuario.correo, "contrasena": CONTRASENA},
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "SEGUNDO_FACTOR_REQUERIDO"
        assert "token_acceso" not in respuesta.json()
        assert "token_refresco" not in respuesta.json()
        sesiones_usuario = await sesion.scalar(
            sa.select(sa.func.count()).select_from(Sesion).where(Sesion.usuario_id == usuario.id)
        )
        assert sesiones_usuario == 0

    async def test_contrasena_incorrecta_devuelve_401_generico(
        self, cliente: AsyncClient, api: str, usuario: Usuario, clinica: Clinica
    ) -> None:
        respuesta = await cliente.post(
            _ruta(api, "/sesion"),
            json={
                "correo": usuario.correo,
                "contrasena": "incorrecta",
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
            },
        )
        sin_cuenta = await cliente.post(
            _ruta(api, "/sesion"),
            json={
                "correo": "nadie@example.invalid",
                "contrasena": "incorrecta",
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
                },
            )

        respuesta = await cliente.post(
            _ruta(api, "/sesion"),
            json={
                "correo": usuario.correo,
                "contrasena": CONTRASENA,
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
            },
        )

        assert respuesta.status_code == 503
        assert respuesta.json()["codigo"] == "PROVEEDOR_EXTERNO_NO_DISPONIBLE"


class TestAccesoLocalPorRoles:
    """Acceso rapido local: solo cuentas sinteticas, sin selector de usuario."""

    async def test_publica_los_seis_roles_base_con_cuentas_sinteticas(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        aplicacion,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(aplicacion.state.configuracion, "entorno", Entorno.LOCAL)
        for codigo in ROLES_BASE:
            await _asignar_rol_sintetico(sesion, usuario, codigo)

        respuesta = await cliente.get(_ruta(api, "/accesos-locales"))

        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo["habilitado"] is True
        assert [rol["codigo"] for rol in cuerpo["roles"]] == list(ROLES_BASE)
        assert [rol["nombre"] for rol in cuerpo["roles"]] == [
            "Superadministrador",
            "Administración de clínica",
            "Recepción",
            "Asistencia clínica",
            "Auditoría",
            "Profesional de salud",
        ]

    @pytest.mark.parametrize("codigo_rol", ROLES_BASE)
    async def test_inicia_sesion_y_resuelve_la_identidad_del_rol_elegido(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        aplicacion,
        configuracion,
        monkeypatch: pytest.MonkeyPatch,
        codigo_rol: str,
    ) -> None:
        monkeypatch.setattr(aplicacion.state.configuracion, "entorno", Entorno.LOCAL)
        # La API suite comparte una base que puede tener semillas sintéticas.
        # Aislamos la elección para que el rol pruebe esta cuenta concreta.
        await sesion.execute(
            sa.update(Usuario).where(Usuario.apellido.contains("[SINTETICO]")).values(activo=False)
        )
        usuario.correo = f"000-prueba-{usuario.id}@example.invalid"
        await _asignar_rol_sintetico(sesion, usuario, codigo_rol)

        respuesta = await cliente.post(_ruta(api, "/sesion-local"), json={"codigo_rol": codigo_rol})

        assert respuesta.status_code == 200
        tokens = respuesta.json()
        assert tokens["token_acceso"]
        assert tokens["token_refresco"]
        # El acceso local satisface el segundo factor para esta sesión
        # sintética; por eso no deja al navegador bloqueado en una pantalla
        # que exige un código de autenticación inexistente.
        assert tokens["requiere_segundo_factor"] is False
        sesion_emitida = await sesion.scalar(
            sa.select(Sesion).where(Sesion.usuario_id == usuario.id)
        )
        assert sesion_emitida is not None
        assert sesion_emitida.segundo_factor_cumplido is (
            codigo_rol in configuracion.lista_roles_con_2fa
        )
        identidad = await cliente.get(
            _ruta(api, "/yo"),
            headers={"Authorization": f"Bearer {tokens['token_acceso']}"},
        )
        assert identidad.status_code == 200
        assert identidad.json()["usuario_id"] == str(usuario.id)
        assert identidad.json()["roles"] == [codigo_rol]
        assert identidad.json()["segundo_factor_cumplido"] is (
            codigo_rol in configuracion.lista_roles_con_2fa
        )

        evento = await sesion.scalar(
            sa.select(Auditoria).where(
                Auditoria.accion == "login.rol_local",
                Auditoria.actor_id == usuario.id,
            )
        )
        assert evento is not None
        assert evento.metadatos == {"codigo_rol": codigo_rol, "cuenta_sintetica": True}
        assert respuesta.text.count("token_") == 2

    async def test_no_ofrece_cuentas_normales_inactivas_ni_roles_personalizados(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        aplicacion,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(aplicacion.state.configuracion, "entorno", Entorno.LOCAL)
        # Aísla esta aserción aunque la base compartida ya tenga semillas
        # sintéticas activas de otras pruebas o del entorno local.
        await sesion.execute(
            sa.update(Usuario).where(Usuario.apellido.contains("[SINTETICO]")).values(activo=False)
        )
        recepcion = await _rol_del_sistema(sesion, "recepcion")
        sesion.add(UsuarioRol(usuario_id=usuario.id, rol_id=recepcion.id))

        rol_auditor = await _rol_del_sistema(sesion, "auditor")
        inactivo = Usuario(
            clinica_id=clinica.id,
            correo="inactivo-sintetico@example.invalid",
            hash_contrasena=usuario.hash_contrasena,
            nombre="Cuenta",
            apellido="Inactiva [SINTETICO]",
            activo=False,
        )
        sesion.add(inactivo)
        await sesion.flush()
        sesion.add(UsuarioRol(usuario_id=inactivo.id, rol_id=rol_auditor.id))

        rol_clinica = Rol(
            clinica_id=clinica.id,
            codigo="profesional",
            nombre="Rol personalizado",
            es_sistema=False,
        )
        sesion.add(rol_clinica)
        personalizado = Usuario(
            clinica_id=clinica.id,
            correo="personalizado-sintetico@example.invalid",
            hash_contrasena=usuario.hash_contrasena,
            nombre="Cuenta",
            apellido="Personalizada [SINTETICO]",
        )
        sesion.add(personalizado)
        await sesion.flush()
        sesion.add(UsuarioRol(usuario_id=personalizado.id, rol_id=rol_clinica.id))

        respuesta = await cliente.get(_ruta(api, "/accesos-locales"))

        assert respuesta.status_code == 200
        assert respuesta.json() == {"habilitado": False, "roles": []}

    @pytest.mark.parametrize("entorno", [Entorno.PREPRODUCCION, Entorno.PRODUCCION])
    async def test_no_emite_accesos_locales_fuera_de_desarrollo(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        aplicacion,
        monkeypatch: pytest.MonkeyPatch,
        entorno: Entorno,
    ) -> None:
        await _asignar_rol_sintetico(sesion, usuario, "administrador_clinica")
        monkeypatch.setattr(aplicacion.state.configuracion, "entorno", entorno)

        accesos = await cliente.get(_ruta(api, "/accesos-locales"))
        inicio = await cliente.post(
            _ruta(api, "/sesion-local"), json={"codigo_rol": "administrador_clinica"}
        )

        assert accesos.status_code == 200
        assert accesos.json() == {"habilitado": False, "roles": []}
        assert inicio.status_code == 404
        assert inicio.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
        assert (
            await sesion.scalar(
                sa.select(sa.func.count())
                .select_from(Sesion)
                .where(Sesion.usuario_id == usuario.id)
            )
            == 0
        )

    async def test_rechaza_roles_no_disponibles_y_campos_desconocidos(
        self,
        cliente: AsyncClient,
        api: str,
        aplicacion,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(aplicacion.state.configuracion, "entorno", Entorno.LOCAL)

        desconocido = await cliente.post(
            _ruta(api, "/sesion-local"), json={"codigo_rol": "dueño_de_todo"}
        )
        campo_adicional = await cliente.post(
            _ruta(api, "/sesion-local"),
            json={"codigo_rol": "recepcion", "usuario_id": "elegido-por-el-cliente"},
        )

        assert desconocido.status_code == 404
        assert desconocido.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
        assert campo_adicional.status_code == 422
        assert "elegido-por-el-cliente" not in campo_adicional.text


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
