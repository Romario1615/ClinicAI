"""Pruebas de las primitivas de seguridad.

No se prueba que las librerias criptograficas funcionen: eso es su
responsabilidad.  Se prueba **como las usamos**, que es donde aparecen los
errores reales:

* que un tipo de token no valga para otra operacion,
* que el algoritmo no se tome del propio token,
* que el cifrado ligado a contexto no descifre en otra fila,
* que la verificacion de firma use el cuerpo crudo y tiempo constante.
"""

from __future__ import annotations

import base64
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pyotp
import pytest

from app.nucleo.errores import TokenInvalido
from app.nucleo.seguridad import (
    LONGITUD_MAXIMA_CONTRASENA,
    CifradorDatos,
    calcular_firma_hmac_sha256,
    crear_token_acceso,
    crear_token_refresco,
    decodificar_token,
    generar_codigos_recuperacion,
    generar_familia_sesion,
    generar_secreto_totp,
    generar_token_un_uso,
    hashear_contrasena,
    hashear_identificador,
    hashear_jti,
    url_provisionamiento_totp,
    validar_politica_contrasena,
    verificar_codigo_totp,
    verificar_contrasena,
    verificar_firma_hmac_sha256,
    verificar_token_un_uso,
)

pytestmark = pytest.mark.unitaria

CLAVE = "clave-de-prueba-suficientemente-larga-para-firmar-tokens"
ALGORITMO = "HS256"
AHORA = datetime(2026, 4, 15, 14, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
#  Contrasenas
# ---------------------------------------------------------------------------
class TestContrasenas:
    def test_hash_y_verificacion(self) -> None:
        hash_ = hashear_contrasena("ContrasenaSegura123")
        assert verificar_contrasena("ContrasenaSegura123", hash_)

    def test_contrasena_incorrecta_no_verifica(self) -> None:
        hash_ = hashear_contrasena("ContrasenaSegura123")
        assert not verificar_contrasena("ContrasenaSegura124", hash_)

    def test_el_hash_usa_argon2id(self) -> None:
        """Argon2id, no PBKDF2 ni bcrypt: resistencia a ataques con GPU."""
        assert hashear_contrasena("ContrasenaSegura123").startswith("$argon2id$")

    def test_dos_hashes_de_la_misma_contrasena_difieren(self) -> None:
        """Sal aleatoria: dos usuarios con la misma contrasena no coinciden."""
        a = hashear_contrasena("ContrasenaSegura123")
        b = hashear_contrasena("ContrasenaSegura123")
        assert a != b
        assert verificar_contrasena("ContrasenaSegura123", a)
        assert verificar_contrasena("ContrasenaSegura123", b)

    def test_hash_malformado_no_lanza(self) -> None:
        """La ruta de inicio de sesion no debe romperse ante un hash corrupto."""
        assert not verificar_contrasena("cualquiera", "no-es-un-hash")

    def test_contrasena_excesiva_se_rechaza(self) -> None:
        """Sin limite superior, hashear megabytes es una denegacion de servicio."""
        with pytest.raises(ValueError, match="excede"):
            hashear_contrasena("a" * (LONGITUD_MAXIMA_CONTRASENA + 1))

    def test_verificacion_de_contrasena_excesiva_devuelve_falso(self) -> None:
        hash_ = hashear_contrasena("ContrasenaSegura123")
        assert not verificar_contrasena("a" * 5000, hash_)

    @pytest.mark.parametrize(
        ("contrasena", "cantidad_problemas"),
        [
            ("ContrasenaSegura123", 0),
            ("corta1A", 1),  # longitud
            ("todominusculas123", 1),  # falta mayuscula
            ("TODOMAYUSCULAS123", 1),  # falta minuscula
            ("SinNumerosAquiVale", 1),  # falta numero
            ("corta", 3),  # longitud, mayuscula y numero
        ],
    )
    def test_politica_devuelve_todos_los_problemas(
        self, contrasena: str, cantidad_problemas: int
    ) -> None:
        """Se devuelven todos a la vez, no el primero.

        Descubrirlos de uno en uno lleva al usuario a elegir la contrasena
        minima que pasa, que es peor.
        """
        assert len(validar_politica_contrasena(contrasena)) == cantidad_problemas

    def test_politica_rechaza_contrasena_comun(self) -> None:
        problemas = validar_politica_contrasena("Contrasena123")
        assert any("comun" in p for p in problemas)


# ---------------------------------------------------------------------------
#  Tokens
# ---------------------------------------------------------------------------
class TestTokens:
    def test_ciclo_completo_de_token_de_acceso(self) -> None:
        usuario = uuid.uuid4()
        clinica = uuid.uuid4()
        familia = generar_familia_sesion()

        token, jti = crear_token_acceso(
            clave_secreta=CLAVE,
            algoritmo=ALGORITMO,
            usuario_id=usuario,
            clinica_id=clinica,
            familia=familia,
            segundo_factor_cumplido=True,
            ahora=AHORA,
            minutos=15,
        )
        contenido = decodificar_token(
            token,
            clave_secreta=CLAVE,
            algoritmo=ALGORITMO,
            tipo_esperado="acceso",
            ahora=AHORA,
        )
        assert contenido.usuario_id == usuario
        assert contenido.clinica_id == clinica
        assert contenido.jti == jti
        assert contenido.familia == familia
        assert contenido.segundo_factor_cumplido
        assert contenido.expira_en == AHORA + timedelta(minutes=15)

    def test_el_token_no_contiene_permisos(self) -> None:
        """Los permisos se resuelven en servidor en cada peticion.

        Si viajaran en el token, un permiso revocado seguiria siendo valido
        durante toda la vida del token.  En datos clinicos eso es
        inaceptable.
        """
        token, _ = crear_token_acceso(
            clave_secreta=CLAVE,
            algoritmo=ALGORITMO,
            usuario_id=uuid.uuid4(),
            clinica_id=None,
            familia="f",
            segundo_factor_cumplido=False,
            ahora=AHORA,
            minutos=15,
        )
        # Se inspecciona el contenido sin validar la caducidad: aqui interesa
        # que campos viajan, no si el token esta vigente.
        carga = jwt.decode(token, CLAVE, algorithms=[ALGORITMO], options={"verify_exp": False})
        for prohibido in ("permisos", "roles", "scopes", "ambito", "permissions"):
            assert prohibido not in carga

    def test_token_de_refresco_no_acredita_segundo_factor(self) -> None:
        """Refrescar no debe saltarse el segundo factor."""
        token, _ = crear_token_refresco(
            clave_secreta=CLAVE,
            algoritmo=ALGORITMO,
            usuario_id=uuid.uuid4(),
            clinica_id=None,
            familia="f",
            ahora=AHORA,
            dias=7,
        )
        contenido = decodificar_token(
            token,
            clave_secreta=CLAVE,
            algoritmo=ALGORITMO,
            tipo_esperado="refresco",
            ahora=AHORA,
        )
        assert not contenido.segundo_factor_cumplido

    def test_token_de_refresco_no_vale_como_token_de_acceso(self) -> None:
        """Confusion de tipo de token: firma valida, uso indebido."""
        token, _ = crear_token_refresco(
            clave_secreta=CLAVE,
            algoritmo=ALGORITMO,
            usuario_id=uuid.uuid4(),
            clinica_id=None,
            familia="f",
            ahora=AHORA,
            dias=7,
        )
        with pytest.raises(TokenInvalido, match="tipo de token"):
            decodificar_token(
                token,
                clave_secreta=CLAVE,
                algoritmo=ALGORITMO,
                tipo_esperado="acceso",
                ahora=AHORA,
            )

    def test_token_expirado_se_rechaza(self) -> None:
        token, _ = crear_token_acceso(
            clave_secreta=CLAVE,
            algoritmo=ALGORITMO,
            usuario_id=uuid.uuid4(),
            clinica_id=None,
            familia="f",
            segundo_factor_cumplido=False,
            ahora=AHORA - timedelta(hours=2),
            minutos=15,
        )
        with pytest.raises(TokenInvalido, match="expirado"):
            decodificar_token(
                token,
                clave_secreta=CLAVE,
                algoritmo=ALGORITMO,
                tipo_esperado="acceso",
                ahora=AHORA,
            )

    def test_firma_con_otra_clave_se_rechaza(self) -> None:
        token, _ = crear_token_acceso(
            clave_secreta="otra-clave-distinta-y-suficientemente-larga",
            algoritmo=ALGORITMO,
            usuario_id=uuid.uuid4(),
            clinica_id=None,
            familia="f",
            segundo_factor_cumplido=False,
            ahora=AHORA,
            minutos=15,
        )
        with pytest.raises(TokenInvalido):
            decodificar_token(
                token,
                clave_secreta=CLAVE,
                algoritmo=ALGORITMO,
                tipo_esperado="acceso",
                ahora=AHORA,
            )

    def test_token_sin_firma_se_rechaza(self) -> None:
        """Ataque de confusion de algoritmo: `alg: none`.

        Se rechaza porque el algoritmo esperado se fija en una lista de uno y
        no se toma de la cabecera del token.
        """
        carga = {
            "sub": str(uuid.uuid4()),
            "typ": "acceso",
            "jti": "x",
            "fam": "f",
            "mfa": True,
            "iat": int(AHORA.timestamp()),
            "exp": int((AHORA + timedelta(hours=1)).timestamp()),
        }
        token_sin_firma = jwt.encode(carga, key="", algorithm="none")
        with pytest.raises(TokenInvalido):
            decodificar_token(
                token_sin_firma,
                clave_secreta=CLAVE,
                algoritmo=ALGORITMO,
                tipo_esperado="acceso",
                ahora=AHORA,
            )

    def test_token_manipulado_se_rechaza(self) -> None:
        token, _ = crear_token_acceso(
            clave_secreta=CLAVE,
            algoritmo=ALGORITMO,
            usuario_id=uuid.uuid4(),
            clinica_id=None,
            familia="f",
            segundo_factor_cumplido=False,
            ahora=AHORA,
            minutos=15,
        )
        cabecera, cuerpo, firma = token.split(".")
        manipulado = f"{cabecera}.{cuerpo[:-4]}AAAA.{firma}"
        with pytest.raises(TokenInvalido):
            decodificar_token(
                manipulado,
                clave_secreta=CLAVE,
                algoritmo=ALGORITMO,
                tipo_esperado="acceso",
                ahora=AHORA,
            )

    def test_token_sin_campos_obligatorios_se_rechaza(self) -> None:
        token = jwt.encode({"sub": str(uuid.uuid4())}, CLAVE, algorithm=ALGORITMO)
        with pytest.raises(TokenInvalido):
            decodificar_token(
                token,
                clave_secreta=CLAVE,
                algoritmo=ALGORITMO,
                tipo_esperado="acceso",
                ahora=AHORA,
            )

    def test_jti_se_almacena_con_hash(self) -> None:
        """La tabla de sesiones guarda el hash, no el jti.

        Un volcado de la base de datos no debe entregar tokens utilizables.
        """
        jti = "identificador-de-token"
        hash_ = hashear_jti(jti)
        assert hash_ != jti
        assert len(hash_) == 64
        assert hashear_jti(jti) == hash_

    def test_familias_de_sesion_son_distintas(self) -> None:
        familias = {generar_familia_sesion() for _ in range(200)}
        assert len(familias) == 200


class TestTokensDeUnUso:
    def test_ciclo_completo(self) -> None:
        token, hash_ = generar_token_un_uso()
        assert verificar_token_un_uso(token, hash_)

    def test_token_incorrecto_no_verifica(self) -> None:
        _, hash_ = generar_token_un_uso()
        otro, _ = generar_token_un_uso()
        assert not verificar_token_un_uso(otro, hash_)

    def test_el_claro_no_se_puede_derivar_del_hash(self) -> None:
        token, hash_ = generar_token_un_uso()
        assert token not in hash_


# ---------------------------------------------------------------------------
#  Cifrado
# ---------------------------------------------------------------------------
class TestCifradorDatos:
    def test_ciclo_completo(self) -> None:
        cifrador = CifradorDatos(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
        secreto = "token-oauth-de-calendario"
        assert cifrador.descifrar(cifrador.cifrar(secreto)) == secreto

    def test_el_texto_cifrado_no_contiene_el_claro(self) -> None:
        cifrador = CifradorDatos("clave-de-prueba")
        cifrado = cifrador.cifrar("token-oauth-de-calendario")
        assert "token-oauth" not in cifrado

    def test_dos_cifrados_del_mismo_texto_difieren(self) -> None:
        """Nonce aleatorio por operacion.

        Sin esto, dos profesionales con el mismo token tendrian el mismo
        texto cifrado, lo que revela informacion.
        """
        cifrador = CifradorDatos("clave-de-prueba")
        assert cifrador.cifrar("mismo") != cifrador.cifrar("mismo")

    def test_alteracion_del_texto_cifrado_falla(self) -> None:
        """AES-GCM es autenticado: alterarlo falla en lugar de devolver basura."""
        cifrador = CifradorDatos("clave-de-prueba")
        cifrado = cifrador.cifrar("token-oauth")
        alterado = cifrado[:-6] + ("A" if cifrado[-6] != "A" else "B") + cifrado[-5:]
        with pytest.raises(ValueError, match="descifrado fallo"):
            cifrador.descifrar(alterado)

    def test_contexto_liga_el_cifrado_a_su_fila(self) -> None:
        """Un token copiado de una fila a otra no debe descifrar.

        El contexto es el identificador del profesional: sin el, mover el
        valor cifrado de un profesional a otro daria acceso a su calendario.
        """
        cifrador = CifradorDatos("clave-de-prueba")
        profesional_a = uuid.uuid4().bytes
        profesional_b = uuid.uuid4().bytes

        cifrado = cifrador.cifrar("token-de-a", contexto=profesional_a)
        assert cifrador.descifrar(cifrado, contexto=profesional_a) == "token-de-a"

        with pytest.raises(ValueError, match="descifrado fallo"):
            cifrador.descifrar(cifrado, contexto=profesional_b)

    def test_otra_clave_no_descifra(self) -> None:
        cifrado = CifradorDatos("clave-original").cifrar("secreto")
        with pytest.raises(ValueError, match="descifrado fallo"):
            CifradorDatos("clave-distinta").descifrar(cifrado)

    def test_dato_truncado_falla_con_mensaje_claro(self) -> None:
        cifrador = CifradorDatos("clave-de-prueba")
        with pytest.raises(ValueError, match="truncado"):
            cifrador.descifrar(base64.urlsafe_b64encode(b"corto").decode())

    def test_dato_no_base64_falla_con_mensaje_claro(self) -> None:
        cifrador = CifradorDatos("clave-de-prueba")
        with pytest.raises(ValueError, match="formato valido"):
            cifrador.descifrar("no es base64 valido !!!")

    def test_acepta_clave_fernet_y_cadena_libre(self) -> None:
        """La clave del entorno puede venir en cualquiera de los dos formatos."""
        for clave in (
            base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
            "una-frase-de-paso-cualquiera",
        ):
            cifrador = CifradorDatos(clave)
            assert cifrador.descifrar(cifrador.cifrar("x")) == "x"


# ---------------------------------------------------------------------------
#  Segundo factor
# ---------------------------------------------------------------------------
class TestSegundoFactor:
    def test_codigo_valido_se_acepta(self) -> None:
        secreto = generar_secreto_totp()
        codigo = pyotp.TOTP(secreto).now()
        assert verificar_codigo_totp(secreto, codigo)

    def test_codigo_con_espacios_se_normaliza(self) -> None:
        """Los gestores de contrasenas pegan el codigo con un espacio."""
        secreto = generar_secreto_totp()
        codigo = pyotp.TOTP(secreto).now()
        assert verificar_codigo_totp(secreto, f"{codigo[:3]} {codigo[3:]}")

    def test_codigo_incorrecto_se_rechaza(self) -> None:
        secreto = generar_secreto_totp()
        correcto = pyotp.TOTP(secreto).now()
        incorrecto = "000000" if correcto != "000000" else "111111"
        assert not verificar_codigo_totp(secreto, incorrecto)

    @pytest.mark.parametrize("entrada", ["", "12345", "1234567", "abcdef", "12 34 5"])
    def test_formato_invalido_se_rechaza_sin_excepcion(self, entrada: str) -> None:
        assert not verificar_codigo_totp(generar_secreto_totp(), entrada)

    def test_secreto_invalido_no_lanza(self) -> None:
        assert not verificar_codigo_totp("no-es-base32-valido!", "123456")

    def test_url_de_provisionamiento(self) -> None:
        url = url_provisionamiento_totp(
            generar_secreto_totp(), correo="medico@example.invalid", emisor="Clinica"
        )
        assert url.startswith("otpauth://totp/")
        assert "Clinica" in url

    def test_codigos_de_recuperacion(self) -> None:
        """Sin ellos, perder el telefono deja al profesional fuera del sistema."""
        codigos = generar_codigos_recuperacion(8)
        assert len(codigos) == 8
        claros = [c for c, _ in codigos]
        assert len(set(claros)) == 8
        for claro, hash_ in codigos:
            assert claro not in hash_
            assert len(hash_) == 64


# ---------------------------------------------------------------------------
#  Firma de webhooks
# ---------------------------------------------------------------------------
class TestFirmaWebhook:
    SECRETO = "secreto-de-la-aplicacion-de-meta"

    def test_firma_valida_se_acepta(self) -> None:
        cuerpo = b'{"entry":[{"id":"123"}]}'
        firma = calcular_firma_hmac_sha256(cuerpo=cuerpo, secreto=self.SECRETO)
        assert verificar_firma_hmac_sha256(
            cuerpo=cuerpo, firma_recibida=firma, secreto=self.SECRETO
        )

    def test_firma_sin_prefijo_se_acepta(self) -> None:
        cuerpo = b'{"a":1}'
        firma = calcular_firma_hmac_sha256(cuerpo=cuerpo, secreto=self.SECRETO)
        sin_prefijo = firma.removeprefix("sha256=")
        assert verificar_firma_hmac_sha256(
            cuerpo=cuerpo, firma_recibida=sin_prefijo, secreto=self.SECRETO
        )

    def test_cuerpo_alterado_invalida_la_firma(self) -> None:
        cuerpo = b'{"monto":10}'
        firma = calcular_firma_hmac_sha256(cuerpo=cuerpo, secreto=self.SECRETO)
        assert not verificar_firma_hmac_sha256(
            cuerpo=b'{"monto":1000}', firma_recibida=firma, secreto=self.SECRETO
        )

    def test_la_firma_depende_del_cuerpo_exacto(self) -> None:
        """Se firma el cuerpo crudo, no el JSON reserializado.

        Reserializar cambia espaciado y orden de claves, y la firma deja de
        coincidir.  Es el error mas comun al implementar este webhook.
        """
        compacto = b'{"a":1,"b":2}'
        espaciado = b'{"a": 1, "b": 2}'
        firma = calcular_firma_hmac_sha256(cuerpo=compacto, secreto=self.SECRETO)
        assert not verificar_firma_hmac_sha256(
            cuerpo=espaciado, firma_recibida=firma, secreto=self.SECRETO
        )

    def test_otro_secreto_invalida_la_firma(self) -> None:
        cuerpo = b'{"a":1}'
        firma = calcular_firma_hmac_sha256(cuerpo=cuerpo, secreto="otro-secreto")
        assert not verificar_firma_hmac_sha256(
            cuerpo=cuerpo, firma_recibida=firma, secreto=self.SECRETO
        )

    @pytest.mark.parametrize("firma", ["", "   ", "sha256=", "basura", "sha1=abc"])
    def test_firmas_malformadas_se_rechazan_sin_excepcion(self, firma: str) -> None:
        """La ruta del webhook debe responder 403, nunca un error 500."""
        assert not verificar_firma_hmac_sha256(
            cuerpo=b"{}", firma_recibida=firma, secreto=self.SECRETO
        )

    def test_sin_secreto_configurado_se_rechaza(self) -> None:
        """Sin secreto no se puede validar, asi que no se acepta nada.

        Lo contrario -- aceptar todo cuando falta el secreto -- convertiria un
        despliegue mal configurado en un webhook abierto.
        """
        cuerpo = b"{}"
        assert not verificar_firma_hmac_sha256(cuerpo=cuerpo, firma_recibida="sha256=x", secreto="")


class TestHashIdentificador:
    def test_es_estable_y_no_reversible(self) -> None:
        telefono = "+593999999999"
        hash_ = hashear_identificador(telefono, sal="clinica")
        assert hash_ == hashear_identificador(telefono, sal="clinica")
        assert telefono not in hash_

    def test_distinta_sal_produce_distinto_hash(self) -> None:
        """Impide correlacionar el mismo telefono entre clinicas distintas."""
        telefono = "+593999999999"
        assert hashear_identificador(telefono, sal="a") != hashear_identificador(telefono, sal="b")
