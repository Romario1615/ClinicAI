"""Pruebas de la configuracion.

Lo que se verifica aqui no es que pydantic lea variables, sino que la
configuracion **rechace** las combinaciones peligrosas.  Un arranque que
acepta produccion con proveedores en modo simulado da una clinica que cree
enviar recordatorios y no los envia.
"""

from __future__ import annotations

import base64
import secrets
from typing import Any

import pytest
from pydantic import ValidationError

from app.nucleo.configuracion import Configuracion, Entorno

pytestmark = pytest.mark.unitaria


def _configuracion_produccion_valida(**sobreescrituras: Any) -> dict[str, Any]:
    """Configuracion minima que SI debe pasar la validacion de produccion."""
    base: dict[str, Any] = {
        "entorno": "produccion",
        "depuracion": False,
        "frontend_modo_simulado": False,
        "whatsapp_validar_firma": True,
        "modo_whatsapp": "cloud_api",
        "modo_calendario": "google",
        "modo_correo": "smtp",
        "antivirus_habilitado": True,
        "clave_secreta": secrets.token_urlsafe(64),
        "clave_cifrado_datos": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "postgres_contrasena": secrets.token_urlsafe(24),
        "origenes_cors": "https://clinica.example",
        "notificaciones_sin_datos_clinicos": True,
        "rag_exigir_fuente": True,
        "redactar_datos_sensibles": True,
        "proveedor_llm": "mock",
        "proveedor_embeddings": "mock",
        "frontend_url": "https://clinica.example",
    }
    base.update(sobreescrituras)
    return base


class TestValoresPorDefecto:
    def test_entorno_por_defecto_es_local(self) -> None:
        cfg = Configuracion(_env_file=None)
        assert cfg.entorno is Entorno.LOCAL
        assert not cfg.entorno.es_produccion

    def test_zona_horaria_inicial_es_guayaquil(self) -> None:
        cfg = Configuracion(_env_file=None)
        assert cfg.zona_horaria_por_defecto == "America/Guayaquil"

    def test_frontend_url_publica_tiene_default_local(self) -> None:
        cfg = Configuracion(_env_file=None)
        assert cfg.frontend_url == "http://localhost:4200"

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "/acceso",
            "ftp://clinic.example",
            "https://usuario:clave@clinic.example",
            "https://clinic.example?next=patient",
        ],
    )
    def test_frontend_url_invalida_se_rechaza(self, url: str) -> None:
        with pytest.raises(ValidationError, match="FRONTEND_URL"):
            Configuracion(_env_file=None, frontend_url=url)

    def test_solo_produccion_admite_datos_reales(self) -> None:
        """Ningun entorno salvo produccion debe contener datos de pacientes."""
        for entorno in Entorno:
            if entorno is Entorno.PRODUCCION:
                continue
            cfg = Configuracion(_env_file=None, entorno=entorno.value)
            assert not cfg.entorno.admite_datos_reales, (
                f"El entorno {entorno.value} no debe admitir datos reales."
            )


class TestZonaHoraria:
    def test_zona_horaria_invalida_falla_al_arrancar(self) -> None:
        """Una zona mal escrita debe fallar al arrancar, no al usar la agenda."""
        with pytest.raises(ValidationError, match="Zona horaria desconocida"):
            Configuracion(_env_file=None, zona_horaria_por_defecto="America/Guayaquill")

    @pytest.mark.parametrize(
        "zona", ["America/Guayaquil", "America/Bogota", "UTC", "Europe/Madrid"]
    )
    def test_zonas_validas_se_aceptan(self, zona: str) -> None:
        cfg = Configuracion(_env_file=None, zona_horaria_por_defecto=zona)
        assert cfg.zona_horaria_por_defecto == zona


class TestCoherencia:
    def test_solape_mayor_que_fragmento_es_invalido(self) -> None:
        """Un solape mayor o igual al tamano hace que la fragmentacion no avance."""
        with pytest.raises(ValidationError, match="rag_solape_fragmento"):
            Configuracion(_env_file=None, rag_tamano_fragmento=500, rag_solape_fragmento=500)

    def test_top_k_mayor_que_candidatos_es_invalido(self) -> None:
        with pytest.raises(ValidationError, match="rag_top_k"):
            Configuracion(_env_file=None, rag_top_k=20, rag_top_k_candidatos=10)

    def test_segundo_recordatorio_debe_ir_despues(self) -> None:
        """El segundo aviso va mas cerca de la cita que el primero."""
        with pytest.raises(ValidationError, match="recordatorio_horas_antes_2"):
            Configuracion(
                _env_file=None,
                recordatorio_horas_antes_1=3,
                recordatorio_horas_antes_2=24,
            )

    def test_hora_resumen_invalida(self) -> None:
        with pytest.raises(ValidationError, match="Hora invalida"):
            Configuracion(_env_file=None, hora_resumen_diario="25:00")

    def test_proveedor_anthropic_exige_clave(self) -> None:
        with pytest.raises(ValidationError, match="ANTHROPIC_API_KEY"):
            Configuracion(_env_file=None, proveedor_llm="anthropic", anthropic_api_key="")

    def test_variable_desconocida_se_rechaza(self) -> None:
        """Una errata en el nombre de una variable no debe pasar inadvertida."""
        with pytest.raises(ValidationError):
            Configuracion(_env_file=None, variable_que_no_existe="x")


class TestValidacionProduccion:
    """Cada caso corresponde a un fallo invisible desde la interfaz."""

    def test_configuracion_produccion_correcta_se_acepta(self) -> None:
        cfg = Configuracion(_env_file=None, **_configuracion_produccion_valida())
        assert cfg.entorno.es_produccion

    @pytest.mark.parametrize(
        ("campo", "valor", "fragmento_esperado"),
        [
            ("depuracion", True, "DEPURACION"),
            ("frontend_modo_simulado", True, "FRONTEND_MODO_SIMULADO"),
            ("whatsapp_validar_firma", False, "WHATSAPP_VALIDAR_FIRMA"),
            ("modo_whatsapp", "sandbox", "MODO_WHATSAPP"),
            ("modo_calendario", "sandbox", "MODO_CALENDARIO"),
            ("modo_correo", "consola", "MODO_CORREO"),
            ("antivirus_habilitado", False, "ANTIVIRUS_HABILITADO"),
            ("frontend_url", "http://clinic.example", "FRONTEND_URL"),
            ("origenes_cors", "*", "comodin"),
            ("origenes_cors", "http://clinica.example", "sin TLS"),
            ("notificaciones_sin_datos_clinicos", False, "diagnosticos"),
            ("rag_exigir_fuente", False, "RAG_EXIGIR_FUENTE"),
            ("redactar_datos_sensibles", False, "REDACTAR_DATOS_SENSIBLES"),
        ],
    )
    def test_produccion_rechaza_configuracion_peligrosa(
        self, campo: str, valor: Any, fragmento_esperado: str
    ) -> None:
        datos = _configuracion_produccion_valida(**{campo: valor})
        with pytest.raises(ValidationError) as excinfo:
            Configuracion(_env_file=None, **datos)
        assert fragmento_esperado in str(excinfo.value), (
            f"El error no menciona '{fragmento_esperado}'. "
            "El mensaje debe decir exactamente que hay que corregir."
        )

    def test_produccion_rechaza_clave_secreta_corta(self) -> None:
        datos = _configuracion_produccion_valida(clave_secreta="corta")
        with pytest.raises(ValidationError, match="al menos 32 caracteres"):
            Configuracion(_env_file=None, **datos)

    def test_produccion_rechaza_valor_de_ejemplo(self) -> None:
        """El marcador de .env.example no debe llegar a produccion."""
        datos = _configuracion_produccion_valida(
            clave_secreta="<generar-una-clave-de-mas-de-treinta-y-dos-caracteres>"
        )
        with pytest.raises(ValidationError, match="valor de ejemplo"):
            Configuracion(_env_file=None, **datos)

    def test_produccion_exige_clave_de_cifrado(self) -> None:
        datos = _configuracion_produccion_valida(clave_cifrado_datos="")
        with pytest.raises(ValidationError, match="CLAVE_CIFRADO_DATOS"):
            Configuracion(_env_file=None, **datos)

    def test_local_permite_configuracion_de_desarrollo(self) -> None:
        """Las mismas opciones que produccion rechaza son validas en local."""
        cfg = Configuracion(
            _env_file=None,
            entorno="local",
            depuracion=True,
            modo_whatsapp="sandbox",
            modo_calendario="sandbox",
            modo_correo="consola",
            frontend_modo_simulado=True,
        )
        assert cfg.modo_whatsapp == "sandbox"

    def test_error_de_produccion_enumera_todos_los_fallos(self) -> None:
        """El mensaje lista todo lo que hay que corregir, no solo el primero.

        Corregir de uno en uno, con un reinicio por cada fallo, hace inviable
        un despliegue.
        """
        datos = _configuracion_produccion_valida(
            depuracion=True,
            modo_whatsapp="sandbox",
            modo_correo="consola",
        )
        with pytest.raises(ValidationError) as excinfo:
            Configuracion(_env_file=None, **datos)
        mensaje = str(excinfo.value)
        assert "DEPURACION" in mensaje
        assert "MODO_WHATSAPP" in mensaje
        assert "MODO_CORREO" in mensaje


class TestPropiedadesDerivadas:
    def test_url_base_datos_se_construye(self) -> None:
        cfg = Configuracion(
            _env_file=None,
            postgres_host="pg",
            postgres_puerto=5432,
            postgres_bd="clinica",
            postgres_usuario="usuario",
            postgres_contrasena="secreta",
        )
        assert cfg.url_base_datos == "postgresql+asyncpg://usuario:secreta@pg:5432/clinica"

    def test_url_sincrona_usa_psycopg(self) -> None:
        cfg = Configuracion(_env_file=None, postgres_contrasena="x")
        assert "psycopg" in cfg.url_base_datos_sincrona
        assert "asyncpg" not in cfg.url_base_datos_sincrona

    def test_bd_url_explicita_tiene_prioridad(self) -> None:
        cfg = Configuracion(
            _env_file=None,
            bd_url="postgresql+asyncpg://otro:clave@host:6000/otra",
            postgres_host="ignorado",
        )
        assert cfg.url_base_datos.endswith("/otra")

    def test_listas_se_parsean_sin_espacios(self) -> None:
        cfg = Configuracion(
            _env_file=None,
            origenes_cors="http://a.test , http://b.test",
            roles_con_2fa_obligatorio="auditor , superadministrador",
        )
        assert cfg.lista_origenes_cors == ["http://a.test", "http://b.test"]
        assert cfg.lista_roles_con_2fa == ["auditor", "superadministrador"]

    def test_tamano_maximo_en_bytes(self) -> None:
        cfg = Configuracion(_env_file=None, max_tamano_archivo_mb=20)
        assert cfg.max_tamano_archivo_bytes == 20 * 1024 * 1024

    def test_secretos_no_se_exponen_al_representar(self) -> None:
        """Un `repr` de la configuracion no debe filtrar secretos a los logs."""
        cfg = Configuracion(
            _env_file=None,
            clave_secreta="valor-super-secreto-de-prueba",
            postgres_contrasena="contrasena-de-prueba",
        )
        texto = repr(cfg)
        assert "valor-super-secreto-de-prueba" not in texto
        assert "contrasena-de-prueba" not in texto
