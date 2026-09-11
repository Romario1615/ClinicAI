"""Pruebas del servicio de autenticacion y de resolucion de permisos.

Se ejecutan contra PostgreSQL real porque lo que se comprueba aqui no es solo
logica de Python: la rotacion de tokens depende de `SELECT ... FOR UPDATE`, el
historial de accesos usa columnas `INET`, y la resolucion de ambito sale de
varias consultas con union.

Lo que se verifica, agrupado por el riesgo que cubre:

* **Enumeracion de cuentas.**  Correo inexistente, contrasena incorrecta y
  cuenta desactivada tienen que responder exactamente lo mismo.
* **Fuerza bruta.**  El bloqueo tiene que activarse y tiene que impedir la
  entrada incluso con la contrasena correcta.
* **Robo de token de refresco.**  Presentar dos veces el mismo refresco tiene
  que revocar la familia entera, no solo el token presentado.
* **Revocacion inmediata de permisos.**  Quitar un permiso o caducar un rol
  tiene que surtir efecto en la peticion siguiente, sin esperar a que caduque
  el token de acceso.
* **Ambito.**  Una exclusion gana a un comodin, y un ambito vacio no da
  acceso a nada.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pyotp
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.organizacion.modelos import Clinica, Especialidad, Sede
from app.modulos.usuarios.modelos import (
    AmbitoAsignacion,
    HistorialAcceso,
    MotivoRevocacion,
    Permiso,
    ResultadoAcceso,
    Rol,
    RolPermiso,
    Sesion,
    Usuario,
    UsuarioRol,
)
from app.modulos.usuarios.servicios import ParTokens, ServicioAutenticacion
from app.nucleo.auditoria import AccionAuditada, ResultadoAuditoria
from app.nucleo.autorizacion import (
    CATALOGO_PERMISOS,
    NivelSensibilidad,
    TipoActor,
    TipoAmbito,
)
from app.nucleo.errores import (
    CredencialesInvalidas,
    CuentaBloqueada,
    SegundoFactorInvalido,
    SegundoFactorRequerido,
    TokenInvalido,
    TokenRevocado,
)
from app.nucleo.reloj import RelojFijo
from app.nucleo.seguridad import (
    CifradorDatos,
    crear_token_acceso,
    crear_token_refresco,
    generar_secreto_totp,
    hashear_contrasena,
)
from pruebas.integracion.conftest import INSTANTE_REFERENCIA

pytestmark = [pytest.mark.integracion, pytest.mark.seguridad, pytest.mark.asyncio]


CONTRASENA = "ContrasenaDePrueba123"
# Claves de prueba. No son secretos: no abren nada fuera de esta suite y la
# base de datos de desarrollo no comparte clave con ningun entorno real.
CLAVE_SECRETA = "clave-de-pruebas-que-no-abre-nada-fuera-de-la-suite-0123456789"
CLAVE_CIFRADO = "clave-de-cifrado-solo-para-la-suite-de-pruebas-0123456789"
ALGORITMO = "HS256"
MINUTOS_ACCESO = 15
DIAS_REFRESCO = 7
MAX_INTENTOS = 3
MINUTOS_BLOQUEO = 15
ROL_CON_2FA = "administrador_clinica"


# ---------------------------------------------------------------------------
#  Fixtures y utilidades
# ---------------------------------------------------------------------------
@pytest.fixture
def reloj() -> RelojFijo:
    """Reloj propio de estas pruebas: la expiracion se adelanta a mano."""
    return RelojFijo(INSTANTE_REFERENCIA)


@pytest.fixture
def cifrador() -> CifradorDatos:
    return CifradorDatos(CLAVE_CIFRADO)


@pytest.fixture
def servicio_auth(
    sesion: AsyncSession, reloj: RelojFijo, cifrador: CifradorDatos
) -> ServicioAutenticacion:
    return ServicioAutenticacion(
        sesion,
        reloj,
        clave_secreta=CLAVE_SECRETA,
        algoritmo=ALGORITMO,
        minutos_token_acceso=MINUTOS_ACCESO,
        dias_token_refresco=DIAS_REFRESCO,
        max_intentos_login=MAX_INTENTOS,
        minutos_bloqueo_login=MINUTOS_BLOQUEO,
        roles_con_2fa=frozenset({ROL_CON_2FA}),
        cifrador=cifrador,
    )


@pytest_asyncio.fixture
async def cuenta(sesion: AsyncSession, clinica: Clinica, sufijo: str) -> Usuario:
    """Usuario con contrasena conocida, aparte del `usuario` del conftest."""
    registro = Usuario(
        clinica_id=clinica.id,
        correo=f"auth-{sufijo}@example.invalid",
        hash_contrasena=hashear_contrasena(CONTRASENA),
        nombre="Cuenta",
        apellido="De Prueba",
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


async def _permiso(sesion: AsyncSession, codigo: str) -> Permiso:
    """Devuelve el permiso, creandolo desde el catalogo si aun no esta.

    Los datos salen de `CATALOGO_PERMISOS`, no de literales inventados aqui:
    si el catalogo cambia de categoria o de nivel de sensibilidad, la prueba
    usa el valor nuevo en lugar de fijar uno que ya no existe.
    """
    existente = (
        await sesion.execute(sa.select(Permiso).where(Permiso.codigo == codigo))
    ).scalar_one_or_none()
    if existente is not None:
        return existente

    definicion = next(d for d in CATALOGO_PERMISOS if d.codigo == codigo)
    creado = Permiso(
        codigo=definicion.codigo,
        descripcion=definicion.descripcion,
        categoria=definicion.categoria,
        requiere_relacion_asistencial=definicion.requiere_relacion_asistencial,
        nivel_sensibilidad=definicion.nivel.value,
    )
    sesion.add(creado)
    await sesion.flush()
    return creado


async def _crear_rol(
    sesion: AsyncSession,
    clinica: Clinica,
    codigo: str,
    *,
    permisos: tuple[str, ...] = (),
) -> Rol:
    rol = Rol(clinica_id=clinica.id, codigo=codigo, nombre=codigo.replace("_", " ").title())
    sesion.add(rol)
    await sesion.flush()

    for codigo_permiso in permisos:
        permiso = await _permiso(sesion, codigo_permiso)
        sesion.add(RolPermiso(rol_id=rol.id, permiso_id=permiso.id))
    await sesion.flush()
    return rol


async def _asignar_rol(
    sesion: AsyncSession,
    usuario: Usuario,
    rol: Rol,
    *,
    vigente_desde: date | None = None,
    vigente_hasta: date | None = None,
) -> UsuarioRol:
    asignacion = UsuarioRol(
        usuario_id=usuario.id,
        rol_id=rol.id,
        vigente_desde=vigente_desde,
        vigente_hasta=vigente_hasta,
    )
    sesion.add(asignacion)
    await sesion.flush()
    return asignacion


async def _historial(sesion: AsyncSession, correo: str) -> list[HistorialAcceso]:
    filas = await sesion.execute(
        sa.select(HistorialAcceso)
        .where(HistorialAcceso.correo_intentado == correo)
        .order_by(HistorialAcceso.ocurrido_en, HistorialAcceso.id)
    )
    return list(filas.scalars())


async def _sesiones(sesion: AsyncSession, usuario: Usuario) -> list[Sesion]:
    filas = await sesion.execute(
        sa.select(Sesion)
        .where(Sesion.usuario_id == usuario.id)
        .order_by(Sesion.creada_en, Sesion.id)
    )
    return list(filas.scalars())


async def _agotar_intentos(
    servicio_auth: ServicioAutenticacion,
    cuenta: Usuario,
    clinica: Clinica,
    reloj: RelojFijo,
) -> None:
    """Falla el login hasta activar el bloqueo.

    El reloj avanza un segundo entre intentos. No es cosmetico: con el reloj
    fijo todas las filas del historial comparten `ocurrido_en` y la clave
    primaria es un UUID aleatorio, asi que no habria un orden estable con el
    que afirmar cual fue el ultimo intento.
    """
    for _ in range(MAX_INTENTOS):
        reloj.avanzar(seconds=1)
        with pytest.raises(CredencialesInvalidas):
            await servicio_auth.iniciar_sesion(
                correo=cuenta.correo, contrasena="incorrecta", clinica_id=clinica.id
            )


def _refresco_sin_fila(usuario: Usuario, reloj: RelojFijo) -> str:
    """Refresco bien firmado pero sin fila en la tabla de sesiones."""
    token, _ = crear_token_refresco(
        clave_secreta=CLAVE_SECRETA,
        algoritmo=ALGORITMO,
        usuario_id=usuario.id,
        clinica_id=usuario.clinica_id,
        familia="familia-que-no-consta",
        ahora=reloj.ahora(),
        dias=DIAS_REFRESCO,
    )
    return token


# ===========================================================================
#  Inicio de sesion
# ===========================================================================
class TestInicioDeSesion:
    async def test_credenciales_correctas_emiten_tokens_y_dejan_sesion(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        clinica: Clinica,
        reloj: RelojFijo,
    ) -> None:
        resultado = await servicio_auth.iniciar_sesion(
            correo=cuenta.correo,
            contrasena=CONTRASENA,
            clinica_id=clinica.id,
            ip="203.0.113.10",
            agente_usuario="pytest",
        )
        await sesion.flush()

        assert resultado.tokens is not None
        assert isinstance(resultado.tokens, ParTokens)
        assert resultado.tokens.token_acceso != resultado.tokens.token_refresco
        assert resultado.tokens.expira_en == reloj.ahora() + timedelta(minutes=MINUTOS_ACCESO)
        assert resultado.tokens.requiere_segundo_factor is False

        # Queda una unica sesion viva, ni usada ni revocada.
        filas = await _sesiones(sesion, cuenta)
        assert len(filas) == 1
        assert filas[0].usada_en is None
        assert filas[0].revocada_en is None
        assert filas[0].sesion_anterior_id is None
        assert filas[0].expira_en == reloj.ahora() + timedelta(days=DIAS_REFRESCO)

        # El refresco se guarda hasheado: el token en claro no esta en la fila.
        assert resultado.tokens.token_refresco not in filas[0].jti_refresco_hash

        assert [e.accion for e in resultado.auditoria] == [AccionAuditada.LOGIN_EXITOSO]
        historial = await _historial(sesion, cuenta.correo)
        assert [h.resultado for h in historial] == [ResultadoAcceso.EXITO.value]
        assert historial[0].usuario_id == cuenta.id
        assert cuenta.ultimo_acceso_en == reloj.ahora()

    async def test_el_correo_se_normaliza(
        self,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        clinica: Clinica,
    ) -> None:
        resultado = await servicio_auth.iniciar_sesion(
            correo=f"  {cuenta.correo.upper()}  ",
            contrasena=CONTRASENA,
            clinica_id=clinica.id,
        )
        assert resultado.tokens is not None

    async def test_contrasena_incorrecta_cuenta_el_intento(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        clinica: Clinica,
    ) -> None:
        with pytest.raises(CredencialesInvalidas):
            await servicio_auth.iniciar_sesion(
                correo=cuenta.correo, contrasena="incorrecta", clinica_id=clinica.id
            )
        await sesion.flush()

        assert cuenta.intentos_fallidos == 1
        assert cuenta.bloqueado_hasta is None
        historial = await _historial(sesion, cuenta.correo)
        assert [h.resultado for h in historial] == [ResultadoAcceso.CREDENCIAL_INVALIDA.value]
        # La contrasena intentada no se guarda en ningun campo del historial.
        assert all("incorrecta" not in h.correo_intentado for h in historial)
        assert all("incorrecta" not in str(h.metadatos or {}) for h in historial)

    async def test_correo_inexistente_responde_igual_que_contrasena_incorrecta(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        clinica: Clinica,
    ) -> None:
        """Sin esto se podria enumerar al personal de la clinica."""
        with pytest.raises(CredencialesInvalidas) as inexistente:
            await servicio_auth.iniciar_sesion(
                correo="nadie@example.invalid", contrasena=CONTRASENA, clinica_id=clinica.id
            )
        with pytest.raises(CredencialesInvalidas) as incorrecta:
            await servicio_auth.iniciar_sesion(
                correo=cuenta.correo, contrasena="incorrecta", clinica_id=clinica.id
            )

        assert str(inexistente.value) == str(incorrecta.value)
        assert inexistente.value.codigo == incorrecta.value.codigo
        assert inexistente.value.estado_http == incorrecta.value.estado_http

        await sesion.flush()
        # El intento contra la cuenta inexistente queda registrado sin usuario.
        historial = await _historial(sesion, "nadie@example.invalid")
        assert len(historial) == 1
        assert historial[0].usuario_id is None

    async def test_cuenta_de_otra_clinica_no_autentica(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        sufijo: str,
    ) -> None:
        """El correo es unico por clinica, no globalmente."""
        otra = Clinica(
            nombre=f"Otra Clinica {sufijo}",
            identificacion_fiscal=f"PRUEBA-OTRA-{sufijo}",
            zona_horaria="America/Guayaquil",
        )
        sesion.add(otra)
        await sesion.flush()

        with pytest.raises(CredencialesInvalidas):
            await servicio_auth.iniciar_sesion(
                correo=cuenta.correo, contrasena=CONTRASENA, clinica_id=otra.id
            )

    async def test_cuenta_desactivada_no_se_distingue_de_credencial_invalida(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        clinica: Clinica,
    ) -> None:
        cuenta.activo = False
        await sesion.flush()

        with pytest.raises(CredencialesInvalidas):
            await servicio_auth.iniciar_sesion(
                correo=cuenta.correo, contrasena=CONTRASENA, clinica_id=clinica.id
            )
        await sesion.flush()

        # El motivo real si queda en el historial interno, para el operador.
        historial = await _historial(sesion, cuenta.correo)
        assert [h.resultado for h in historial] == [ResultadoAcceso.CUENTA_INACTIVA.value]
        assert await _sesiones(sesion, cuenta) == []


class TestBloqueoPorIntentos:
    async def test_se_bloquea_al_alcanzar_el_maximo(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        clinica: Clinica,
        reloj: RelojFijo,
    ) -> None:
        await _agotar_intentos(servicio_auth, cuenta, clinica, reloj)
        await sesion.flush()

        assert cuenta.intentos_fallidos == MAX_INTENTOS
        assert cuenta.bloqueado_hasta == reloj.ahora() + timedelta(minutes=MINUTOS_BLOQUEO)

    async def test_el_bloqueo_impide_entrar_con_la_contrasena_correcta(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        clinica: Clinica,
        reloj: RelojFijo,
    ) -> None:
        """Si la contrasena correcta saltara el bloqueo, el bloqueo no serviria."""
        await _agotar_intentos(servicio_auth, cuenta, clinica, reloj)

        reloj.avanzar(seconds=1)
        with pytest.raises(CuentaBloqueada) as excepcion:
            await servicio_auth.iniciar_sesion(
                correo=cuenta.correo, contrasena=CONTRASENA, clinica_id=clinica.id
            )
        assert "minuto" in str(excepcion.value)

        await sesion.flush()
        assert await _sesiones(sesion, cuenta) == []
        historial = await _historial(sesion, cuenta.correo)
        assert historial[-1].resultado == ResultadoAcceso.BLOQUEADO.value

    async def test_el_bloqueo_expira_y_el_contador_se_limpia(
        self,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        clinica: Clinica,
        reloj: RelojFijo,
    ) -> None:
        await _agotar_intentos(servicio_auth, cuenta, clinica, reloj)

        reloj.avanzar(minutes=MINUTOS_BLOQUEO + 1)
        resultado = await servicio_auth.iniciar_sesion(
            correo=cuenta.correo, contrasena=CONTRASENA, clinica_id=clinica.id
        )

        assert resultado.tokens is not None
        # Si el contador no se limpiara, el siguiente fallo volveria a
        # bloquear de inmediato.
        assert cuenta.intentos_fallidos == 0
        assert cuenta.bloqueado_hasta is None


class TestSegundoFactor:
    @pytest_asyncio.fixture
    async def cuenta_sensible(
        self, sesion: AsyncSession, cuenta: Usuario, clinica: Clinica
    ) -> Usuario:
        rol = await _crear_rol(sesion, clinica, ROL_CON_2FA)
        await _asignar_rol(sesion, cuenta, rol)
        return cuenta

    @staticmethod
    async def _configurar_2fa(
        sesion: AsyncSession, usuario: Usuario, cifrador: CifradorDatos
    ) -> str:
        secreto = generar_secreto_totp()
        usuario.dosfa_habilitado = True
        usuario.secreto_2fa_cifrado = cifrador.cifrar(secreto, contexto=usuario.id.bytes)
        await sesion.flush()
        return secreto

    async def test_rol_sensible_sin_2fa_configurado_no_entra(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta_sensible: Usuario,
        clinica: Clinica,
    ) -> None:
        """No se le deja pasar «por ahora»: se le obliga a configurarlo."""
        with pytest.raises(SegundoFactorRequerido) as excepcion:
            await servicio_auth.iniciar_sesion(
                correo=cuenta_sensible.correo,
                contrasena=CONTRASENA,
                clinica_id=clinica.id,
            )
        assert "configurado" in str(excepcion.value)

        await sesion.flush()
        assert await _sesiones(sesion, cuenta_sensible) == []

    async def test_sin_codigo_se_pide_el_codigo(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta_sensible: Usuario,
        cifrador: CifradorDatos,
        clinica: Clinica,
    ) -> None:
        await self._configurar_2fa(sesion, cuenta_sensible, cifrador)

        with pytest.raises(SegundoFactorRequerido):
            await servicio_auth.iniciar_sesion(
                correo=cuenta_sensible.correo,
                contrasena=CONTRASENA,
                clinica_id=clinica.id,
            )
        await sesion.flush()
        assert await _sesiones(sesion, cuenta_sensible) == []

    async def test_codigo_invalido_cuenta_como_intento_fallido(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta_sensible: Usuario,
        cifrador: CifradorDatos,
        clinica: Clinica,
    ) -> None:
        """Sin contar el fallo, seis digitos se agotan por fuerza bruta."""
        await self._configurar_2fa(sesion, cuenta_sensible, cifrador)

        with pytest.raises(SegundoFactorInvalido):
            await servicio_auth.iniciar_sesion(
                correo=cuenta_sensible.correo,
                contrasena=CONTRASENA,
                clinica_id=clinica.id,
                codigo_2fa="000000",
            )
        await sesion.flush()

        assert cuenta_sensible.intentos_fallidos == 1
        historial = await _historial(sesion, cuenta_sensible.correo)
        assert historial[-1].resultado == ResultadoAcceso.SEGUNDO_FACTOR_FALLIDO.value

    async def test_codigo_valido_entra_y_marca_el_segundo_factor(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta_sensible: Usuario,
        cifrador: CifradorDatos,
        clinica: Clinica,
    ) -> None:
        secreto = await self._configurar_2fa(sesion, cuenta_sensible, cifrador)

        # El codigo se genera con la hora de pared a proposito: TOTP se valida
        # contra el reloj real del servidor y del telefono del usuario, no
        # contra el reloj inyectado de la aplicacion.  Ver
        # docs/known-limitations.md.
        resultado = await servicio_auth.iniciar_sesion(
            correo=cuenta_sensible.correo,
            contrasena=CONTRASENA,
            clinica_id=clinica.id,
            codigo_2fa=pyotp.TOTP(secreto).now(),
        )
        await sesion.flush()

        assert resultado.tokens is not None
        assert resultado.tokens.requiere_segundo_factor is False
        filas = await _sesiones(sesion, cuenta_sensible)
        assert filas[0].segundo_factor_cumplido is True

    async def test_el_secreto_cifrado_no_descifra_con_otro_contexto(
        self, cifrador: CifradorDatos, cuenta: Usuario
    ) -> None:
        """El cifrado esta ligado a su fila: copiarlo a otra no sirve."""
        secreto = generar_secreto_totp()
        cifrado = cifrador.cifrar(secreto, contexto=cuenta.id.bytes)

        assert cifrador.descifrar(cifrado, contexto=cuenta.id.bytes) == secreto
        with pytest.raises(ValueError, match="descifrado fallo"):
            cifrador.descifrar(cifrado, contexto=uuid.uuid4().bytes)


# ===========================================================================
#  Rotacion de tokens
# ===========================================================================
@pytest_asyncio.fixture
async def tokens(
    sesion: AsyncSession,
    servicio_auth: ServicioAutenticacion,
    cuenta: Usuario,
    clinica: Clinica,
) -> ParTokens:
    resultado = await servicio_auth.iniciar_sesion(
        correo=cuenta.correo, contrasena=CONTRASENA, clinica_id=clinica.id
    )
    await sesion.flush()
    assert resultado.tokens is not None
    return resultado.tokens


class TestRotacionDeTokens:
    async def test_el_refresco_emite_un_par_nuevo_y_encadena_la_sesion(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        tokens: ParTokens,
        reloj: RelojFijo,
    ) -> None:
        reloj.avanzar(minutes=10)
        resultado = await servicio_auth.refrescar_sesion(token_refresco=tokens.token_refresco)
        await sesion.flush()

        assert resultado.tokens is not None
        assert resultado.tokens.token_refresco != tokens.token_refresco
        assert [e.accion for e in resultado.auditoria] == [AccionAuditada.TOKEN_REFRESCADO]

        filas = await _sesiones(sesion, cuenta)
        assert len(filas) == 2
        anterior, nueva = filas
        assert anterior.usada_en == reloj.ahora()
        assert nueva.usada_en is None
        assert nueva.familia == anterior.familia
        assert nueva.sesion_anterior_id == anterior.id

    async def test_reutilizar_un_refresco_revoca_la_familia_entera(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        tokens: ParTokens,
    ) -> None:
        """El caso del token robado: no se puede saber cual copia es legitima."""
        primero = await servicio_auth.refrescar_sesion(token_refresco=tokens.token_refresco)
        await sesion.flush()
        assert primero.tokens is not None

        # El atacante -- o el usuario legitimo -- presenta el viejo otra vez.
        reutilizacion = await servicio_auth.refrescar_sesion(token_refresco=tokens.token_refresco)
        await sesion.flush()

        assert reutilizacion.tokens is None
        entrada = reutilizacion.auditoria[0]
        assert entrada.accion == AccionAuditada.TOKEN_REUTILIZADO
        assert entrada.resultado == ResultadoAuditoria.DENEGADO
        assert entrada.requiere_alerta is True

        filas = await _sesiones(sesion, cuenta)
        assert len(filas) == 2
        assert all(f.revocada_en is not None for f in filas)
        assert all(
            f.motivo_revocacion == MotivoRevocacion.REUTILIZACION_DETECTADA.value for f in filas
        )

        # Y el par emitido justo antes tampoco sirve ya.
        with pytest.raises(TokenRevocado):
            await servicio_auth.refrescar_sesion(token_refresco=primero.tokens.token_refresco)

    async def test_un_token_de_acceso_no_sirve_para_refrescar(
        self, servicio_auth: ServicioAutenticacion, tokens: ParTokens
    ) -> None:
        with pytest.raises(TokenInvalido):
            await servicio_auth.refrescar_sesion(token_refresco=tokens.token_acceso)

    async def test_un_refresco_que_no_consta_se_rechaza(
        self, servicio_auth: ServicioAutenticacion, cuenta: Usuario, reloj: RelojFijo
    ) -> None:
        """Firmado con la clave correcta pero sin fila: sesion purgada."""
        with pytest.raises(TokenInvalido, match="no existe"):
            await servicio_auth.refrescar_sesion(token_refresco=_refresco_sin_fila(cuenta, reloj))

    async def test_el_refresco_caducado_se_rechaza(
        self, servicio_auth: ServicioAutenticacion, tokens: ParTokens, reloj: RelojFijo
    ) -> None:
        reloj.avanzar(days=DIAS_REFRESCO + 1)
        with pytest.raises(TokenInvalido):
            await servicio_auth.refrescar_sesion(token_refresco=tokens.token_refresco)

    async def test_desactivar_la_cuenta_corta_la_cadena(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        tokens: ParTokens,
    ) -> None:
        cuenta.activo = False
        await sesion.flush()

        with pytest.raises(TokenRevocado):
            await servicio_auth.refrescar_sesion(token_refresco=tokens.token_refresco)
        await sesion.flush()

        filas = await _sesiones(sesion, cuenta)
        assert filas[0].motivo_revocacion == MotivoRevocacion.USUARIO_DESACTIVADO.value

    async def test_el_segundo_factor_se_hereda_en_la_rotacion(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        tokens: ParTokens,
    ) -> None:
        """Pedir el codigo cada quince minutos llevaria a desactivar el 2FA."""
        filas = await _sesiones(sesion, cuenta)
        filas[0].segundo_factor_cumplido = True
        await sesion.flush()

        await servicio_auth.refrescar_sesion(token_refresco=tokens.token_refresco)
        await sesion.flush()

        filas = await _sesiones(sesion, cuenta)
        assert filas[-1].segundo_factor_cumplido is True


# ===========================================================================
#  Cierre de sesion
# ===========================================================================
class TestCierreDeSesion:
    async def test_cerrar_revoca_la_sesion_presentada(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        tokens: ParTokens,
        reloj: RelojFijo,
    ) -> None:
        auditoria = await servicio_auth.cerrar_sesion(token_refresco=tokens.token_refresco)
        await sesion.flush()

        assert [e.accion for e in auditoria] == [AccionAuditada.LOGOUT]
        filas = await _sesiones(sesion, cuenta)
        assert filas[0].revocada_en == reloj.ahora()
        assert filas[0].motivo_revocacion == MotivoRevocacion.CIERRE_SESION.value

        with pytest.raises(TokenRevocado):
            await servicio_auth.refrescar_sesion(token_refresco=tokens.token_refresco)

    async def test_cerrar_la_familia_revoca_toda_la_cadena(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        tokens: ParTokens,
    ) -> None:
        rotado = await servicio_auth.refrescar_sesion(token_refresco=tokens.token_refresco)
        await sesion.flush()
        assert rotado.tokens is not None

        await servicio_auth.cerrar_sesion(
            token_refresco=rotado.tokens.token_refresco, revocar_familia=True
        )
        await sesion.flush()

        filas = await _sesiones(sesion, cuenta)
        assert len(filas) == 2
        assert all(f.revocada_en is not None for f in filas)

    async def test_cerrar_una_sesion_inexistente_no_es_un_error(
        self, servicio_auth: ServicioAutenticacion, cuenta: Usuario, reloj: RelojFijo
    ) -> None:
        """El resultado deseado -- que el token no sirva -- ya se cumple."""
        assert (
            await servicio_auth.cerrar_sesion(token_refresco=_refresco_sin_fila(cuenta, reloj))
            == ()
        )

    async def test_revocar_todas_las_sesiones_cuenta_las_afectadas(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        clinica: Clinica,
        tokens: ParTokens,
    ) -> None:
        # Segunda sesion, como desde otro dispositivo.
        await servicio_auth.iniciar_sesion(
            correo=cuenta.correo, contrasena=CONTRASENA, clinica_id=clinica.id
        )
        await sesion.flush()

        afectadas = await servicio_auth.revocar_todas_las_sesiones(
            cuenta.id, motivo=MotivoRevocacion.CAMBIO_CONTRASENA
        )
        await sesion.flush()

        assert afectadas == 2
        filas = await _sesiones(sesion, cuenta)
        assert all(f.motivo_revocacion == MotivoRevocacion.CAMBIO_CONTRASENA.value for f in filas)

        # Una segunda pasada no vuelve a contar las mismas.
        repetida = await servicio_auth.revocar_todas_las_sesiones(
            cuenta.id, motivo=MotivoRevocacion.CAMBIO_CONTRASENA
        )
        assert repetida == 0


# ===========================================================================
#  Resolucion del principal
# ===========================================================================
class TestResolucionDelPrincipal:
    async def test_los_permisos_se_leen_de_la_base_no_del_token(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        clinica: Clinica,
    ) -> None:
        """Quitar un permiso surte efecto sin esperar a que caduque el token."""
        rol = await _crear_rol(
            sesion,
            clinica,
            f"rol_prueba_{uuid.uuid4().hex[:8]}",
            permisos=("paciente.leer_administrativo",),
        )
        await _asignar_rol(sesion, cuenta, rol)

        resultado = await servicio_auth.iniciar_sesion(
            correo=cuenta.correo, contrasena=CONTRASENA, clinica_id=clinica.id
        )
        await sesion.flush()
        assert resultado.tokens is not None
        token = resultado.tokens.token_acceso

        principal = await servicio_auth.resolver_principal_desde_token(token)
        assert "paciente.leer_administrativo" in principal.permisos
        assert principal.actor_tipo == TipoActor.USUARIO
        assert principal.actor_id == cuenta.id
        assert principal.clinica_id == clinica.id
        assert rol.codigo in principal.roles

        # Se retira el permiso del rol. El token no cambia.
        await sesion.execute(sa.delete(RolPermiso).where(RolPermiso.rol_id == rol.id))
        await sesion.flush()

        principal = await servicio_auth.resolver_principal_desde_token(token)
        assert "paciente.leer_administrativo" not in principal.permisos

    async def test_un_rol_caducado_no_concede_nada(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        clinica: Clinica,
        reloj: RelojFijo,
    ) -> None:
        rol = await _crear_rol(
            sesion,
            clinica,
            f"rol_caducado_{uuid.uuid4().hex[:8]}",
            permisos=("paciente.leer_administrativo",),
        )
        await _asignar_rol(
            sesion, cuenta, rol, vigente_hasta=reloj.ahora().date() - timedelta(days=1)
        )

        principal = await servicio_auth.resolver_principal_de_usuario(cuenta)
        assert principal.permisos == frozenset()

    async def test_un_rol_que_aun_no_empieza_no_concede_nada(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        clinica: Clinica,
        reloj: RelojFijo,
    ) -> None:
        rol = await _crear_rol(
            sesion,
            clinica,
            f"rol_futuro_{uuid.uuid4().hex[:8]}",
            permisos=("paciente.leer_administrativo",),
        )
        await _asignar_rol(
            sesion, cuenta, rol, vigente_desde=reloj.ahora().date() + timedelta(days=1)
        )

        principal = await servicio_auth.resolver_principal_de_usuario(cuenta)
        assert principal.permisos == frozenset()

    async def test_sin_rol_el_ambito_queda_vacio(
        self, servicio_auth: ServicioAutenticacion, cuenta: Usuario, clinica: Clinica
    ) -> None:
        principal = await servicio_auth.resolver_principal_de_usuario(cuenta)

        assert principal.permisos == frozenset()
        assert principal.ambito.clinica_id == clinica.id
        assert principal.ambito.todas_las_sedes is False
        assert principal.ambito.sedes == frozenset()
        assert principal.ambito.cubre_sede(uuid.uuid4()) is False

    async def test_token_de_cuenta_desactivada_se_rechaza(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        tokens: ParTokens,
    ) -> None:
        cuenta.activo = False
        await sesion.flush()

        with pytest.raises(TokenRevocado):
            await servicio_auth.resolver_principal_desde_token(tokens.token_acceso)

    async def test_un_token_firmado_con_otra_clave_se_rechaza(
        self, servicio_auth: ServicioAutenticacion, cuenta: Usuario, reloj: RelojFijo
    ) -> None:
        ajeno, _ = crear_token_acceso(
            clave_secreta="otra-clave-distinta-de-la-del-servicio-0123456789",
            algoritmo=ALGORITMO,
            usuario_id=cuenta.id,
            clinica_id=cuenta.clinica_id,
            familia="f",
            segundo_factor_cumplido=False,
            ahora=reloj.ahora(),
            minutos=MINUTOS_ACCESO,
        )
        with pytest.raises(TokenInvalido):
            await servicio_auth.resolver_principal_desde_token(ajeno)

    async def test_el_token_de_acceso_caduca(
        self, servicio_auth: ServicioAutenticacion, tokens: ParTokens, reloj: RelojFijo
    ) -> None:
        reloj.avanzar(minutes=MINUTOS_ACCESO + 1)
        with pytest.raises(TokenInvalido):
            await servicio_auth.resolver_principal_desde_token(tokens.token_acceso)

    async def test_usuario_desconocido_devuelve_principal_minimo_auditable(
        self, servicio_auth: ServicioAutenticacion
    ) -> None:
        """Perder el registro de auditoria seria peor que auditar sin nombre."""
        desconocido = uuid.uuid4()
        principal = await servicio_auth.resolver_principal_por_id(desconocido)

        assert principal.actor_id == desconocido
        assert principal.permisos == frozenset()
        assert principal.clinica_id is None


# ===========================================================================
#  Ambito
# ===========================================================================
class TestAmbito:
    @pytest_asyncio.fixture
    async def asignacion(
        self, sesion: AsyncSession, cuenta: Usuario, clinica: Clinica
    ) -> UsuarioRol:
        rol = await _crear_rol(
            sesion,
            clinica,
            f"rol_ambito_{uuid.uuid4().hex[:8]}",
            permisos=("paciente.leer_administrativo",),
        )
        return await _asignar_rol(sesion, cuenta, rol)

    async def test_el_comodin_cubre_toda_la_dimension(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        asignacion: UsuarioRol,
    ) -> None:
        sesion.add(
            AmbitoAsignacion(
                usuario_rol_id=asignacion.id, tipo=TipoAmbito.SEDE.value, valor_id=None
            )
        )
        await sesion.flush()

        principal = await servicio_auth.resolver_principal_de_usuario(cuenta)
        assert principal.ambito.todas_las_sedes is True
        assert principal.ambito.cubre_sede(uuid.uuid4()) is True

    async def test_la_inclusion_explicita_solo_cubre_lo_listado(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        asignacion: UsuarioRol,
        sede: Sede,
    ) -> None:
        sesion.add(
            AmbitoAsignacion(
                usuario_rol_id=asignacion.id, tipo=TipoAmbito.SEDE.value, valor_id=sede.id
            )
        )
        await sesion.flush()

        principal = await servicio_auth.resolver_principal_de_usuario(cuenta)
        assert principal.ambito.todas_las_sedes is False
        assert principal.ambito.cubre_sede(sede.id) is True
        assert principal.ambito.cubre_sede(uuid.uuid4()) is False

    async def test_una_exclusion_desactiva_el_comodin_de_su_dimension(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        asignacion: UsuarioRol,
        sede: Sede,
    ) -> None:
        """«Todas las sedes menos la Norte» se degrada a la lista explicita.

        Queda mas restrictivo de lo que el administrador pidio -- puede quedar
        vacio -- y ese es el lado seguro sobre datos clinicos.
        """
        sesion.add_all(
            [
                AmbitoAsignacion(
                    usuario_rol_id=asignacion.id, tipo=TipoAmbito.SEDE.value, valor_id=None
                ),
                AmbitoAsignacion(
                    usuario_rol_id=asignacion.id,
                    tipo=TipoAmbito.SEDE.value,
                    valor_id=sede.id,
                    incluir=False,
                ),
            ]
        )
        await sesion.flush()

        principal = await servicio_auth.resolver_principal_de_usuario(cuenta)
        assert principal.ambito.todas_las_sedes is False
        assert principal.ambito.cubre_sede(sede.id) is False
        assert principal.ambito.cubre_sede(uuid.uuid4()) is False

    async def test_la_exclusion_gana_a_la_inclusion_del_mismo_valor(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        asignacion: UsuarioRol,
        especialidad: Especialidad,
    ) -> None:
        sesion.add_all(
            [
                AmbitoAsignacion(
                    usuario_rol_id=asignacion.id,
                    tipo=TipoAmbito.ESPECIALIDAD.value,
                    valor_id=especialidad.id,
                ),
                AmbitoAsignacion(
                    usuario_rol_id=asignacion.id,
                    tipo=TipoAmbito.ESPECIALIDAD.value,
                    valor_id=especialidad.id,
                    incluir=False,
                ),
            ]
        )
        await sesion.flush()

        principal = await servicio_auth.resolver_principal_de_usuario(cuenta)
        assert principal.ambito.cubre_especialidad(especialidad.id) is False

    async def test_el_tipo_de_informacion_eleva_el_nivel_maximo(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        asignacion: UsuarioRol,
    ) -> None:
        antes = await servicio_auth.resolver_principal_de_usuario(cuenta)
        assert antes.ambito.nivel_maximo == NivelSensibilidad.ADMINISTRATIVO

        sesion.add(
            AmbitoAsignacion(
                usuario_rol_id=asignacion.id,
                tipo=TipoAmbito.TIPO_INFORMACION.value,
                valor_id=None,
            )
        )
        await sesion.flush()

        despues = await servicio_auth.resolver_principal_de_usuario(cuenta)
        assert despues.ambito.nivel_maximo == NivelSensibilidad.CLINICO
        assert despues.ambito.cubre_nivel(NivelSensibilidad.CLINICO) is True

    async def test_un_tipo_sin_dimension_propia_se_ignora_sin_romper(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        asignacion: UsuarioRol,
        clinica: Clinica,
    ) -> None:
        """`CLINICA` esta permitido en la tabla pero no filtra ninguna lista.

        El ambito se compone por dimensiones conocidas; un tipo que no tiene
        dimension propia se ignora en lugar de fallar.  Si fallara, anadir un
        tipo nuevo a la tabla dejaria fuera del sistema a quien lo tuviera
        asignado.
        """
        sesion.add(
            AmbitoAsignacion(
                usuario_rol_id=asignacion.id,
                tipo=TipoAmbito.CLINICA.value,
                valor_id=clinica.id,
            )
        )
        await sesion.flush()

        principal = await servicio_auth.resolver_principal_de_usuario(cuenta)
        assert principal.ambito.clinica_id == clinica.id
        assert principal.ambito.sedes == frozenset()
        assert "paciente.leer_administrativo" in principal.permisos

    async def test_la_base_rechaza_un_tipo_de_ambito_fuera_del_catalogo(
        self, sesion: AsyncSession, asignacion: UsuarioRol
    ) -> None:
        """La lista de tipos validos la impone la base, no solo Python."""
        sesion.add(
            AmbitoAsignacion(
                usuario_rol_id=asignacion.id, tipo="DIMENSION_INVENTADA", valor_id=None
            )
        )
        with pytest.raises(IntegrityError, match="tipo_ambito_valido"):
            await sesion.flush()
        await sesion.rollback()

    async def test_la_base_rechaza_una_exclusion_sin_destino(
        self, sesion: AsyncSession, asignacion: UsuarioRol
    ) -> None:
        """Excluir «todas las sedes» dejaria el ambito vacio de forma confusa."""
        sesion.add(
            AmbitoAsignacion(
                usuario_rol_id=asignacion.id,
                tipo=TipoAmbito.SEDE.value,
                valor_id=None,
                incluir=False,
            )
        )
        with pytest.raises(IntegrityError, match="exclusion_exige_destino"):
            await sesion.flush()
        await sesion.rollback()

    async def test_dos_roles_suman_permisos_y_ambitos(
        self,
        sesion: AsyncSession,
        servicio_auth: ServicioAutenticacion,
        cuenta: Usuario,
        clinica: Clinica,
        asignacion: UsuarioRol,
        sede: Sede,
        especialidad: Especialidad,
    ) -> None:
        sesion.add(
            AmbitoAsignacion(
                usuario_rol_id=asignacion.id, tipo=TipoAmbito.SEDE.value, valor_id=sede.id
            )
        )
        segundo_rol = await _crear_rol(
            sesion, clinica, f"rol_extra_{uuid.uuid4().hex[:8]}", permisos=("cita.crear",)
        )
        segunda = await _asignar_rol(sesion, cuenta, segundo_rol)
        sesion.add(
            AmbitoAsignacion(
                usuario_rol_id=segunda.id,
                tipo=TipoAmbito.ESPECIALIDAD.value,
                valor_id=especialidad.id,
            )
        )
        await sesion.flush()

        principal = await servicio_auth.resolver_principal_de_usuario(cuenta)
        assert {"paciente.leer_administrativo", "cita.crear"} <= principal.permisos
        assert principal.ambito.cubre_sede(sede.id) is True
        assert principal.ambito.cubre_especialidad(especialidad.id) is True
