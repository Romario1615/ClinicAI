"""Rutas del calendario por HTTP.

Lo que estas pruebas protegen
-----------------------------
El agujero obvio de esta funcionalidad seria dejar que el identificador del
profesional viniera en la peticion: un profesional podria conectar su propio
calendario de Google a la agenda de un companero y quedarse con una copia
permanente de sus horarios de trabajo, o leer los de otro.

Todas las rutas derivan el profesional del **principal**. Estas pruebas
comprueban que no hay forma de pedir la conexion de otro, y que el intento
devuelve 404 y no 403 -- un 403 confirmaria que existe, y eso permite
enumerar.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.modelos import Auditoria
from app.modulos.calendario import oauth
from app.modulos.calendario.seleccion import PROVEEDOR_GOOGLE
from app.modulos.organizacion.modelos import Clinica, Especialidad, Sede
from app.modulos.profesionales.modelos import (
    CalendarioConexion,
    EstadoSincronizacion,
    Profesional,
)
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.auditoria import AccionAuditada
from app.nucleo.reloj import RelojFijo
from pruebas.api.conftest import cabecera_bearer, conceder_permisos
from pruebas.conftest import INSTANTE_REFERENCIA

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]

# El permiso lo tiene solo el rol profesional (ver `CATALOGO_PERMISOS`).
PERMISO_CALENDARIO = "profesional.conectar_calendario"


@pytest_asyncio.fixture
async def cabeceras_profesional(
    cliente: AsyncClient,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    profesional: Profesional,
) -> dict[str, str]:
    """Sesion de un profesional con su ficha asociada.

    La fixture `profesional` de la conftest liga `usuario_id` al usuario que
    inicia sesion, y eso es lo que hace que el principal lleve
    `profesional_id`. Sin ese campo, las rutas de aqui rechazan la peticion --
    y con razon: una cuenta sin ficha no tiene calendario propio.
    """
    await conceder_permisos(
        sesion, usuario, clinica, PERMISO_CALENDARIO, "agenda.leer", sedes=(sede.id,)
    )
    return await cabecera_bearer(cliente, usuario, clinica)


@pytest_asyncio.fixture
async def cabeceras_recepcion(
    cliente: AsyncClient,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
) -> dict[str, str]:
    """Sesion de recepcion: gestiona la agenda, pero no calendarios ajenos."""
    await conceder_permisos(sesion, usuario, clinica, "agenda.leer", "cita.crear", sedes=(sede.id,))
    return await cabecera_bearer(cliente, usuario, clinica)


@pytest_asyncio.fixture
async def conexion_propia(sesion: AsyncSession, profesional: Profesional) -> CalendarioConexion:
    """Conexion del profesional que inicia sesion en estas pruebas.

    Los tokens van cifrados con una cadena cualquiera: estas pruebas no los
    descifran, solo comprueban que la ruta no los devuelve.
    """
    registro = CalendarioConexion(
        profesional_id=profesional.id,
        proveedor=PROVEEDOR_GOOGLE,
        calendar_id="primary",
        token_acceso_cifrado="cifrado-opaco-de-prueba",
        token_refresco_cifrado="cifrado-opaco-de-prueba",
        estado_sincronizacion=EstadoSincronizacion.CONECTADO.value,
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


@pytest_asyncio.fixture
async def conexion_ajena(
    sesion: AsyncSession, clinica: Clinica, especialidad: Especialidad, sufijo: str
) -> CalendarioConexion:
    """Conexion de **otro** profesional de la misma clinica.

    Mismo ambito, distinto profesional: es el caso que un filtro por clinica
    dejaria pasar y que el filtro por profesional detiene.
    """
    otro = Profesional(
        clinica_id=clinica.id,
        especialidad_id=especialidad.id,
        nombre="Companero",
        apellido="De Prueba",
        numero_registro_profesional=f"REG-AJENO-{sufijo}",
    )
    sesion.add(otro)
    await sesion.flush()

    registro = CalendarioConexion(
        profesional_id=otro.id,
        proveedor=PROVEEDOR_GOOGLE,
        calendar_id="primary",
        token_acceso_cifrado="cifrado-opaco-de-prueba",
        token_refresco_cifrado="cifrado-opaco-de-prueba",
        estado_sincronizacion=EstadoSincronizacion.CONECTADO.value,
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


# ---------------------------------------------------------------------------
#  Autorizacion
# ---------------------------------------------------------------------------
async def test_sin_autenticacion_no_se_listan_conexiones(cliente: AsyncClient, api: str) -> None:
    respuesta = await cliente.get(f"{api}/calendario/conexiones")
    assert respuesta.status_code == 401


async def test_recepcion_no_puede_conectar_un_calendario(
    cliente: AsyncClient, api: str, cabeceras_recepcion: dict[str, str]
) -> None:
    """El permiso `profesional.conectar_calendario` solo lo tiene el profesional.

    Recepcion gestiona la agenda de todos, pero el calendario personal de un
    profesional no es suyo.
    """
    respuesta = await cliente.post(
        f"{api}/calendario/oauth/inicio", json={}, headers=cabeceras_recepcion
    )
    assert respuesta.status_code == 403


async def test_un_profesional_solo_ve_sus_conexiones(
    cliente: AsyncClient,
    api: str,
    cabeceras_profesional: dict[str, str],
    conexion_propia: CalendarioConexion,
    conexion_ajena: CalendarioConexion,
) -> None:
    """La ajena es de otro profesional de la MISMA clinica.

    Un filtro por clinica la dejaria pasar; el filtro es por profesional.
    """
    respuesta = await cliente.get(f"{api}/calendario/conexiones", headers=cabeceras_profesional)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    identificadores = {elemento["id"] for elemento in cuerpo["elementos"]}
    assert str(conexion_propia.id) in identificadores
    assert str(conexion_ajena.id) not in identificadores


async def test_la_conexion_ajena_devuelve_404_y_no_403(
    cliente: AsyncClient,
    api: str,
    cabeceras_profesional: dict[str, str],
    conexion_ajena: CalendarioConexion,
) -> None:
    """Un 403 confirmaria que existe, y eso permite enumerar.

    Desde fuera, la conexion de un companero es indistinguible de una
    inexistente.
    """
    respuesta = await cliente.get(
        f"{api}/calendario/conexiones/{conexion_ajena.id}/eventos",
        headers=cabeceras_profesional,
    )
    assert respuesta.status_code == 404

    inexistente = await cliente.get(
        f"{api}/calendario/conexiones/{uuid.uuid4()}/eventos",
        headers=cabeceras_profesional,
    )
    assert inexistente.status_code == 404

    # Se comparan codigo y mensaje, no el cuerpo entero: este ultimo lleva el
    # identificador de correlacion, que es distinto por peticion a proposito.
    def _visible(cuerpo: dict[str, object]) -> tuple[object, object]:
        return cuerpo.get("codigo"), cuerpo.get("mensaje")

    assert _visible(respuesta.json()) == _visible(inexistente.json())


async def test_no_se_puede_desconectar_la_conexion_de_otro(
    cliente: AsyncClient,
    api: str,
    cabeceras_profesional: dict[str, str],
    conexion_ajena: CalendarioConexion,
    sesion: AsyncSession,
) -> None:
    respuesta = await cliente.post(
        f"{api}/calendario/conexiones/{conexion_ajena.id}/desconexion",
        json={"motivo": "No deberia poder hacer esto."},
        headers=cabeceras_profesional,
    )
    assert respuesta.status_code == 404

    # Y sigue conectada: el intento no tuvo efecto.
    fila = await sesion.get(CalendarioConexion, conexion_ajena.id, populate_existing=True)
    assert fila is not None
    assert fila.estado_sincronizacion == EstadoSincronizacion.CONECTADO.value
    assert fila.token_refresco_cifrado is not None


# ---------------------------------------------------------------------------
#  Los tokens no salen por HTTP
# ---------------------------------------------------------------------------
async def test_la_respuesta_no_incluye_los_tokens(
    cliente: AsyncClient,
    api: str,
    cabeceras_profesional: dict[str, str],
    conexion_propia: CalendarioConexion,
) -> None:
    """Ni cifrados.

    Un token cifrado en una respuesta HTTP sigue siendo material sensible en
    un log de acceso, en la cache de un proxy y en el historial del navegador.
    """
    respuesta = await cliente.get(f"{api}/calendario/conexiones", headers=cabeceras_profesional)
    cuerpo = respuesta.text
    assert "cifrado-opaco-de-prueba" not in cuerpo
    assert "token" not in cuerpo.lower()


# ---------------------------------------------------------------------------
#  Inicio de OAuth
# ---------------------------------------------------------------------------
async def test_sin_credenciales_de_google_el_inicio_devuelve_503(
    cliente: AsyncClient, api: str, cabeceras_profesional: dict[str, str]
) -> None:
    """El entorno de pruebas no tiene `GOOGLE_CLIENT_ID`, y no se inventa.

    Se responde 503 con un mensaje que dice que usar en su lugar, en lugar de
    construir una URL que no lleva a ninguna parte.
    """
    respuesta = await cliente.post(
        f"{api}/calendario/oauth/inicio", json={}, headers=cabeceras_profesional
    )
    assert respuesta.status_code == 503
    assert "sandbox" in respuesta.text.lower()


# ---------------------------------------------------------------------------
#  Callback
# ---------------------------------------------------------------------------
async def test_el_callback_rechaza_un_estado_sin_firma(cliente: AsyncClient, api: str) -> None:
    """El callback no lleva autenticacion: lo unico que lo autoriza es el `state`."""
    respuesta = await cliente.get(
        f"{api}/calendario/oauth/callback",
        params={"code": "codigo-cualquiera", "state": "inventado"},
    )
    assert respuesta.status_code == 403


async def test_el_callback_rechaza_un_estado_firmado_con_otro_secreto(
    cliente: AsyncClient, api: str, profesional: Profesional
) -> None:
    """Es el ataque: apropiarse del calendario de otra persona.

    Un tercero que no conoce la clave del sistema no puede fabricar un `state`
    que nombre al profesional que quiera.
    """
    reloj = RelojFijo(INSTANTE_REFERENCIA)
    ajeno = oauth.firmar_estado(
        oauth.nuevo_estado(profesional.id, ahora=reloj.ahora()),
        "secreto-que-no-es-el-del-sistema",
    )
    respuesta = await cliente.get(
        f"{api}/calendario/oauth/callback",
        params={"code": "codigo-cualquiera", "state": ajeno},
    )
    assert respuesta.status_code == 403


async def test_el_callback_exige_codigo_y_estado(cliente: AsyncClient, api: str) -> None:
    """Sin los dos parametros no hay nada que validar."""
    assert (await cliente.get(f"{api}/calendario/oauth/callback")).status_code == 422
    assert (
        await cliente.get(f"{api}/calendario/oauth/callback", params={"code": "x"})
    ).status_code == 422


# ---------------------------------------------------------------------------
#  Eventos
# ---------------------------------------------------------------------------
async def test_el_listado_de_eventos_no_expone_datos_de_la_cita(
    cliente: AsyncClient,
    api: str,
    cabeceras_profesional: dict[str, str],
    conexion_propia: CalendarioConexion,
) -> None:
    """Sirve para diagnosticar la sincronizacion, no para ver la agenda.

    Devuelve estados; ni paciente, ni servicio, ni motivo (RF-I09).
    """
    respuesta = await cliente.get(
        f"{api}/calendario/conexiones/{conexion_propia.id}/eventos",
        headers=cabeceras_profesional,
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 0
    # El esquema de salida es explicito: no hay forma de que se cuele un campo.
    assert set(cuerpo) == {"elementos", "total"}


async def test_la_sincronizacion_manual_responde_un_resumen(
    cliente: AsyncClient,
    api: str,
    cabeceras_profesional: dict[str, str],
    conexion_propia: CalendarioConexion,
) -> None:
    """Existe porque el barrido periodico puede tardar.

    Un profesional que acaba de conectar su calendario espera verlo poblado,
    no enterarse en el proximo ciclo.
    """
    respuesta = await cliente.post(
        f"{api}/calendario/conexiones/{conexion_propia.id}/sincronizacion",
        headers=cabeceras_profesional,
    )
    assert respuesta.status_code == 200
    assert set(respuesta.json()) == {
        "creados",
        "actualizados",
        "eliminados",
        "recreados",
        "conflictos",
        "reintentables",
        "errores",
    }


async def test_la_desconexion_exige_motivo(
    cliente: AsyncClient,
    api: str,
    cabeceras_profesional: dict[str, str],
    conexion_propia: CalendarioConexion,
) -> None:
    """Un motivo de una palabra no explica nada; se exige un minimo."""
    respuesta = await cliente.post(
        f"{api}/calendario/conexiones/{conexion_propia.id}/desconexion",
        json={"motivo": "no"},
        headers=cabeceras_profesional,
    )
    assert respuesta.status_code == 422


async def test_la_desconexion_borra_los_tokens(
    cliente: AsyncClient,
    api: str,
    cabeceras_profesional: dict[str, str],
    conexion_propia: CalendarioConexion,
    sesion: AsyncSession,
) -> None:
    respuesta = await cliente.post(
        f"{api}/calendario/conexiones/{conexion_propia.id}/desconexion",
        json={"motivo": "Cambio de cuenta de correo."},
        headers=cabeceras_profesional,
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["estado_sincronizacion"] == (EstadoSincronizacion.DESCONECTADO.value)

    fila = await sesion.get(CalendarioConexion, conexion_propia.id, populate_existing=True)
    assert fila is not None
    assert fila.token_acceso_cifrado is None
    assert fila.token_refresco_cifrado is None


async def test_la_desconexion_queda_auditada(
    cliente: AsyncClient,
    api: str,
    cabeceras_profesional: dict[str, str],
    conexion_propia: CalendarioConexion,
    sesion: AsyncSession,
) -> None:
    await cliente.post(
        f"{api}/calendario/conexiones/{conexion_propia.id}/desconexion",
        json={"motivo": "Cambio de cuenta de correo."},
        headers=cabeceras_profesional,
    )
    accion = await sesion.scalar(
        sa.select(Auditoria.accion).where(
            Auditoria.accion == AccionAuditada.CALENDARIO_DESCONECTADO.value,
            Auditoria.entidad_id == conexion_propia.id,
        )
    )
    assert accion == AccionAuditada.CALENDARIO_DESCONECTADO.value


# ---------------------------------------------------------------------------
#  El `state` es de un solo uso
# ---------------------------------------------------------------------------
# Estas dos pruebas cubren la propiedad de seguridad que las demas solo
# comprueban a nivel de firma: que un `state` valido **no se puede reutilizar**.
# Sin ella, un valor filtrado del historial del navegador o de un log de
# referrer serviria para volver a asociar un calendario.
#
# Se sustituye el intercambio del codigo porque no hay credenciales de Google
# y no se inventan (CLAUDE.md, regla 3). Lo sustituido es la llamada al
# tercero; el consumo del `state`, el cifrado de los tokens y la escritura de
# la conexion son los reales.
async def test_el_callback_valido_crea_la_conexion_con_tokens_cifrados(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    profesional: Profesional,
    monkeypatch: pytest.MonkeyPatch,
    configuracion: object,
) -> None:
    from datetime import timedelta  # noqa: PLC0415

    from app.modulos.calendario import rutas as rutas_calendario  # noqa: PLC0415

    reloj = RelojFijo(INSTANTE_REFERENCIA)
    secreto = configuracion.clave_secreta.get_secret_value()  # type: ignore[attr-defined]
    firmado = oauth.firmar_estado(oauth.nuevo_estado(profesional.id, ahora=reloj.ahora()), secreto)

    async def _intercambio_simulado(**_argumentos: object) -> oauth.TokensObtenidos:
        return oauth.TokensObtenidos(
            token_acceso="acceso-que-no-debe-aparecer",
            token_refresco="refresco-que-no-debe-aparecer",
            expira_en=reloj.ahora() + timedelta(hours=1),
            alcances="https://www.googleapis.com/auth/calendar.events",
        )

    monkeypatch.setattr(rutas_calendario.oauth, "intercambiar_codigo", _intercambio_simulado)

    respuesta = await cliente.get(
        f"{api}/calendario/oauth/callback",
        params={"code": "codigo-sintetico", "state": firmado},
    )
    assert respuesta.status_code == 200, respuesta.text
    # Los tokens no salen en la respuesta.
    assert "acceso-que-no-debe-aparecer" not in respuesta.text
    assert "refresco-que-no-debe-aparecer" not in respuesta.text

    fila = (
        await sesion.execute(
            sa.select(CalendarioConexion).where(CalendarioConexion.profesional_id == profesional.id)
        )
    ).scalar_one()
    assert fila.estado_sincronizacion == EstadoSincronizacion.CONECTADO.value
    # Ni en la base en claro.
    assert "acceso-que-no-debe-aparecer" not in (fila.token_acceso_cifrado or "")
    assert "refresco-que-no-debe-aparecer" not in (fila.token_refresco_cifrado or "")


async def test_el_mismo_estado_no_se_puede_usar_dos_veces(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    profesional: Profesional,
    monkeypatch: pytest.MonkeyPatch,
    configuracion: object,
) -> None:
    """La garantia es la restriccion unica de `clave_idempotencia`.

    No una comprobacion previa en Python: dos pestanas del mismo flujo pueden
    llegar a la vez, y un `SELECT` antes del `INSERT` dejaria pasar las dos.
    """
    from datetime import timedelta  # noqa: PLC0415

    from app.modulos.calendario import rutas as rutas_calendario  # noqa: PLC0415

    reloj = RelojFijo(INSTANTE_REFERENCIA)
    secreto = configuracion.clave_secreta.get_secret_value()  # type: ignore[attr-defined]
    firmado = oauth.firmar_estado(oauth.nuevo_estado(profesional.id, ahora=reloj.ahora()), secreto)

    llamadas = 0

    async def _intercambio_simulado(**_argumentos: object) -> oauth.TokensObtenidos:
        nonlocal llamadas
        llamadas += 1
        return oauth.TokensObtenidos(
            token_acceso="acceso",
            token_refresco="refresco",
            expira_en=reloj.ahora() + timedelta(hours=1),
            alcances=None,
        )

    monkeypatch.setattr(rutas_calendario.oauth, "intercambiar_codigo", _intercambio_simulado)

    primera = await cliente.get(
        f"{api}/calendario/oauth/callback",
        params={"code": "codigo-sintetico", "state": firmado},
    )
    segunda = await cliente.get(
        f"{api}/calendario/oauth/callback",
        params={"code": "codigo-sintetico", "state": firmado},
    )

    assert primera.status_code == 200
    assert segunda.status_code == 403
    # El `state` se consume ANTES de canjear el codigo: el segundo intento no
    # llego a gastar una llamada al proveedor.
    assert llamadas == 1
