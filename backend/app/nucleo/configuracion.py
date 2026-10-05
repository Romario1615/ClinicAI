"""Configuracion de la aplicacion.

Toda la configuracion entra por variables de entorno.  Ningun secreto vive en
el codigo ni en el repositorio (regla 2 de CLAUDE.md).

La pieza importante de este modulo no es leer variables: es la funcion
`_validar_produccion`.  Arrancar en produccion con un proveedor en modo
simulado, con la depuracion activa o con un secreto de ejemplo produce una
clinica que cree estar enviando recordatorios y no lo esta.  Por eso la
configuracion invalida **aborta el arranque** en lugar de registrar un aviso.
"""

from __future__ import annotations

import re
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Entorno(StrEnum):
    LOCAL = "local"
    DESARROLLO = "desarrollo"
    PREPRODUCCION = "preproduccion"
    PRODUCCION = "produccion"

    @property
    def es_produccion(self) -> bool:
        return self is Entorno.PRODUCCION

    @property
    def admite_datos_reales(self) -> bool:
        """Solo produccion puede contener datos de pacientes reales."""
        return self is Entorno.PRODUCCION


# El .env vive en la raiz del repositorio, no en `backend/`, porque tambien
# lo consumen docker compose y el frontend.  La ruta se resuelve a partir de
# la ubicacion de este modulo y no del directorio de trabajo: el backend se
# arranca desde `backend/`, el worker desde la raiz y las pruebas desde
# cualquier sitio, y una ruta relativa al directorio actual haria que la
# configuracion se cargara o no segun desde donde se invoque.
_RAIZ_REPOSITORIO = Path(__file__).resolve().parents[3]

# Longitud minima de la clave de firma de tokens.  256 bits es el tamano del
# bloque de HMAC-SHA256: una clave mas corta no aporta mas entropia de la que
# el algoritmo puede usar, y una mucho mas corta es atacable por fuerza bruta.
LONGITUD_MINIMA_CLAVE_SECRETA = 32


class Configuracion(BaseSettings):
    """Configuracion completa, validada al arrancar."""

    model_config = SettingsConfigDict(
        # Se declaran las dos ubicaciones: la raiz del repositorio y el
        # directorio actual.  La ultima tiene prioridad, lo que permite a una
        # prueba o a un despliegue poner un .env propio junto al proceso.
        env_file=(_RAIZ_REPOSITORIO / ".env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        # Una variable desconocida en .env suele ser una errata en el nombre
        # de otra que si importa.  Ignorarla en silencio deja la variable real
        # en su valor por defecto sin que nadie se entere.
        extra="forbid",
    )

    # --- Entorno ----------------------------------------------------------
    entorno: Entorno = Entorno.LOCAL
    depuracion: bool = True
    nivel_log: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    formato_log: Literal["json", "consola"] = "json"
    redactar_datos_sensibles: bool = True
    zona_horaria_por_defecto: str = "America/Guayaquil"
    idioma_por_defecto: str = "es"

    # --- Base de datos ----------------------------------------------------
    # 127.0.0.1 y no "localhost": en Windows este ultimo resuelve primero a
    # ::1 y el reenvio IPv6 de WSL2 no relaya los puertos de los
    # contenedores, con lo que la conexion se cuelga en lugar de fallar.
    postgres_host: str = "127.0.0.1"
    postgres_puerto: int = 5432
    postgres_bd: str = "clinica"
    postgres_usuario: str = "clinica"
    postgres_contrasena: SecretStr = SecretStr("")
    bd_url: str = ""
    bd_pool_tamano: Annotated[int, Field(ge=1, le=100)] = 10
    bd_pool_desborde: Annotated[int, Field(ge=0, le=200)] = 20
    postgres_bd_pruebas: str = "clinica_pruebas"

    # --- Redis ------------------------------------------------------------
    redis_host: str = "127.0.0.1"
    redis_puerto: int = 6379
    redis_bd: Annotated[int, Field(ge=0, le=15)] = 0
    redis_contrasena: SecretStr = SecretStr("")
    redis_url: str = ""

    # --- Seguridad --------------------------------------------------------
    clave_secreta: SecretStr = SecretStr("")
    algoritmo_jwt: Literal["HS256", "HS384", "HS512"] = "HS256"
    minutos_token_acceso: Annotated[int, Field(ge=1, le=120)] = 15
    dias_token_refresco: Annotated[int, Field(ge=1, le=90)] = 7
    clave_cifrado_datos: SecretStr = SecretStr("")
    max_intentos_login: Annotated[int, Field(ge=3, le=20)] = 5
    minutos_bloqueo_login: Annotated[int, Field(ge=1, le=1440)] = 15
    roles_con_2fa_obligatorio: str = "superadministrador,administrador_clinica,auditor"
    origenes_cors: str = "http://localhost:4200"
    limite_peticiones_por_minuto: Annotated[int, Field(ge=1)] = 120
    limite_login_por_minuto: Annotated[int, Field(ge=1)] = 10

    # --- Proveedor de LLM -------------------------------------------------
    proveedor_llm: Literal["anthropic", "ollama", "mock"] = "mock"
    anthropic_api_key: SecretStr = SecretStr("")
    modelo_llm: str = "claude-sonnet-5"
    llm_max_tokens: Annotated[int, Field(ge=64, le=32000)] = 2048
    llm_temperatura: Annotated[float, Field(ge=0.0, le=1.0)] = 0.2
    # Profundidad de razonamiento del modelo. `low` es lo adecuado para elegir
    # entre siete herramientas administrativas: el limite clinico no depende de
    # lo que el modelo razone, se evalua antes del bucle.
    llm_esfuerzo: Literal["low", "medium", "high", "xhigh", "max"] = "low"
    llm_timeout_segundos: Annotated[int, Field(ge=1, le=300)] = 30
    ollama_url: str = "http://localhost:11434"

    # --- Decisiones tipadas (Jev, TypeSafe AI) ----------------------------
    # `reglas` es el sandbox sin red. Con `jev`, el texto del mensaje (sin
    # identificadores) sale a TypeSafe AI: requiere acuerdo de encargo.
    proveedor_decisiones: Literal["jev", "reglas"] = "reglas"
    typesafe_api_key: SecretStr = SecretStr("")
    typesafe_modelo: str = "jev-latest"
    typesafe_timeout_segundos: Annotated[float, Field(ge=0.2, le=30)] = 3.0
    # Probabilidad clinica a partir de la cual se deriva a una persona. Baja
    # a proposito: un falso positivo cuesta una derivacion; un falso negativo,
    # que el agente conteste algo clinico.
    decisiones_umbral_clinico: Annotated[float, Field(ge=0.05, le=0.9)] = 0.35
    # Confianza minima para resolver una intencion simple sin llamar al LLM.
    decisiones_umbral_intencion: Annotated[float, Field(ge=0.5, le=1.0)] = 0.85

    # --- Generacion de imagenes para promociones ---------------------------
    # `sandbox` dibuja localmente. `openai` usa una API compatible con
    # /images/generations; la URL permite apuntar a otro proveedor compatible.
    proveedor_imagenes: Literal["openai", "sandbox"] = "sandbox"
    imagenes_api_url: str = "https://api.openai.com/v1"
    imagenes_api_key: SecretStr = SecretStr("")
    imagenes_modelo: str = "gpt-image-1"

    # --- Embeddings -------------------------------------------------------
    proveedor_embeddings: Literal["fastembed", "ollama", "mock"] = "fastembed"
    modelo_embeddings: str = "intfloat/multilingual-e5-small"
    dimension_embeddings: Annotated[int, Field(ge=64, le=4096)] = 384
    ruta_cache_embeddings: Path = Path("D:/cache/fastembed")

    # --- RAG --------------------------------------------------------------
    rag_top_k: Annotated[int, Field(ge=1, le=50)] = 8
    rag_top_k_candidatos: Annotated[int, Field(ge=1, le=500)] = 40
    rag_umbral_similitud: Annotated[float, Field(ge=0.0, le=1.0)] = 0.35
    rag_peso_vectorial: Annotated[float, Field(ge=0.0, le=1.0)] = 0.6
    rag_tamano_fragmento: Annotated[int, Field(ge=100, le=8000)] = 900
    rag_solape_fragmento: Annotated[int, Field(ge=0, le=2000)] = 150
    rag_exigir_fuente: bool = True

    # --- WhatsApp ---------------------------------------------------------
    modo_whatsapp: Literal["cloud_api", "sandbox"] = "sandbox"
    whatsapp_id_numero_telefono: str = ""
    whatsapp_id_cuenta_negocio: str = ""
    whatsapp_token_acceso: SecretStr = SecretStr("")
    whatsapp_token_verificacion: SecretStr = SecretStr("")
    whatsapp_secreto_app: SecretStr = SecretStr("")
    whatsapp_version_api: str = "v21.0"
    whatsapp_validar_firma: bool = True

    # --- Google Calendar --------------------------------------------------
    modo_calendario: Literal["google", "sandbox"] = "sandbox"
    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")
    google_redirect_uri: str = "http://localhost:8000/api/v1/calendario/oauth/callback"
    google_scopes: str = "https://www.googleapis.com/auth/calendar.events"

    # --- Correo -----------------------------------------------------------
    modo_correo: Literal["smtp", "consola", "mock"] = "consola"
    smtp_host: str = ""
    smtp_puerto: int = 587
    smtp_usuario: str = ""
    smtp_contrasena: SecretStr = SecretStr("")
    smtp_tls: bool = True
    correo_remitente: str = "no-responder@example.invalid"
    nombre_remitente: str = "Clinica"

    # --- Tareas y outbox --------------------------------------------------
    worker_concurrencia: Annotated[int, Field(ge=1, le=64)] = 4
    outbox_intervalo_segundos: Annotated[int, Field(ge=1, le=600)] = 10
    outbox_max_intentos: Annotated[int, Field(ge=1, le=20)] = 6
    outbox_retroceso_base_segundos: Annotated[int, Field(ge=1, le=3600)] = 30
    minutos_expiracion_held: Annotated[int, Field(ge=1, le=120)] = 10
    minutos_expiracion_oferta: Annotated[int, Field(ge=1, le=1440)] = 30

    # --- Recordatorios ----------------------------------------------------
    recordatorio_horas_antes_1: Annotated[int, Field(ge=1, le=168)] = 24
    recordatorio_horas_antes_2: Annotated[int, Field(ge=1, le=168)] = 3
    hora_resumen_diario: str = "07:00"
    notificaciones_sin_datos_clinicos: bool = True

    # --- Archivos ---------------------------------------------------------
    almacenamiento_archivos: Literal["local", "s3"] = "local"
    ruta_almacenamiento_local: Path = Path("./almacenamiento")
    max_tamano_archivo_mb: Annotated[int, Field(ge=1, le=200)] = 20
    tipos_archivo_permitidos: str = "application/pdf,image/png,image/jpeg,image/webp"
    antivirus_habilitado: bool = False
    clamav_host: str = "localhost"
    clamav_puerto: int = 3310
    # Almacen S3 compatible (MinIO en desarrollo). Solo con
    # `almacenamiento_archivos = "s3"`. Las credenciales entran por entorno.
    s3_endpoint: str = ""
    s3_bucket: str = "clinica-archivos"
    s3_region: str = "us-east-1"
    s3_clave_acceso: str = ""
    s3_clave_secreta: SecretStr = SecretStr("")

    # --- Observabilidad ---------------------------------------------------
    metricas_habilitadas: bool = True
    ruta_metricas: str = "/metrics"
    sentry_dsn: str = ""

    # --- Frontend ---------------------------------------------------------
    api_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:4200"
    frontend_modo_simulado: bool = True

    @field_validator("frontend_url")
    @classmethod
    def validar_frontend_url(cls, valor: str) -> str:
        partes = urlsplit(valor.strip())
        if (
            partes.scheme not in {"http", "https"}
            or not partes.netloc
            or partes.username is not None
            or partes.password is not None
            or partes.query
            or partes.fragment
        ):
            raise ValueError(
                "FRONTEND_URL debe ser una URL HTTP(S) absoluta sin credenciales, "
                "consulta ni fragmento."
            )
        return valor.strip().rstrip("/")

    # ------------------------------------------------------------------
    #  Propiedades derivadas
    # ------------------------------------------------------------------
    @property
    def url_base_datos(self) -> str:
        """Cadena de conexion asincrona."""
        if self.bd_url:
            return self.bd_url
        contrasena = self.postgres_contrasena.get_secret_value()
        return (
            f"postgresql+asyncpg://{self.postgres_usuario}:{contrasena}"
            f"@{self.postgres_host}:{self.postgres_puerto}/{self.postgres_bd}"
        )

    @property
    def url_base_datos_sincrona(self) -> str:
        """Cadena de conexion sincrona, para Alembic y las semillas."""
        return self.url_base_datos.replace("postgresql+asyncpg://", "postgresql+psycopg://")

    @property
    def url_redis(self) -> str:
        if self.redis_url:
            return self.redis_url
        contrasena = self.redis_contrasena.get_secret_value()
        credencial = f":{contrasena}@" if contrasena else ""
        return f"redis://{credencial}{self.redis_host}:{self.redis_puerto}/{self.redis_bd}"

    @property
    def lista_origenes_cors(self) -> list[str]:
        return [o.strip() for o in self.origenes_cors.split(",") if o.strip()]

    @property
    def lista_roles_con_2fa(self) -> list[str]:
        return [r.strip() for r in self.roles_con_2fa_obligatorio.split(",") if r.strip()]

    @property
    def lista_tipos_archivo(self) -> list[str]:
        return [t.strip() for t in self.tipos_archivo_permitidos.split(",") if t.strip()]

    @property
    def max_tamano_archivo_bytes(self) -> int:
        return self.max_tamano_archivo_mb * 1024 * 1024

    # ------------------------------------------------------------------
    #  Validadores
    # ------------------------------------------------------------------
    @field_validator("zona_horaria_por_defecto")
    @classmethod
    def _validar_zona_horaria(cls, valor: str) -> str:
        """Una zona horaria mal escrita rompe toda la agenda.

        Se valida al arrancar, no la primera vez que alguien consulta la
        disponibilidad.
        """
        try:
            ZoneInfo(valor)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(
                f"Zona horaria desconocida: '{valor}'. Use un identificador de la "
                "base de datos IANA, por ejemplo 'America/Guayaquil'."
            ) from exc
        return valor

    @field_validator("hora_resumen_diario")
    @classmethod
    def _validar_hora(cls, valor: str) -> str:
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", valor):
            raise ValueError(f"Hora invalida: '{valor}'. Formato esperado HH:MM en 24 horas.")
        return valor

    @model_validator(mode="after")
    def _validar_coherencia(self) -> Configuracion:
        if self.rag_solape_fragmento >= self.rag_tamano_fragmento:
            raise ValueError(
                "rag_solape_fragmento debe ser menor que rag_tamano_fragmento; si no, "
                "la fragmentacion no avanza y repite el mismo texto indefinidamente."
            )
        if self.rag_top_k > self.rag_top_k_candidatos:
            raise ValueError(
                "rag_top_k no puede superar rag_top_k_candidatos: no se pueden "
                "devolver mas resultados de los que se recuperan."
            )
        if self.recordatorio_horas_antes_2 >= self.recordatorio_horas_antes_1:
            raise ValueError(
                "recordatorio_horas_antes_2 debe ser menor que "
                "recordatorio_horas_antes_1: el segundo aviso va mas cerca de la cita."
            )
        if self.proveedor_llm == "anthropic" and not self.anthropic_api_key.get_secret_value():
            raise ValueError(
                "proveedor_llm=anthropic exige ANTHROPIC_API_KEY en el entorno. "
                "La clave nunca se escribe en el codigo ni en .env.example."
            )
        self._validar_produccion()
        return self

    def _validar_produccion(self) -> None:  # noqa: PLR0912
        """Impide arrancar en produccion con configuracion de desarrollo.

        Cada comprobacion corresponde a un fallo que, si pasara inadvertido,
        seria invisible desde la interfaz pero grave en operacion: una clinica
        que cree enviar recordatorios y no los envia, o una API abierta a
        cualquier origen.
        """
        if not self.entorno.es_produccion:
            return

        fallos: list[str] = []

        if self.depuracion:
            fallos.append("DEPURACION=true expone trazas internas en las respuestas de error")
        if self.frontend_modo_simulado:
            fallos.append("FRONTEND_MODO_SIMULADO=true haria que la interfaz use datos falsos")
        if not self.frontend_url.startswith("https://"):
            fallos.append("FRONTEND_URL debe usar HTTPS en produccion")
        if not self.whatsapp_validar_firma:
            fallos.append("WHATSAPP_VALIDAR_FIRMA=false aceptaria webhooks de cualquier origen")
        if self.modo_whatsapp == "sandbox":
            fallos.append("MODO_WHATSAPP=sandbox: no se enviaria ningun mensaje real")
        if self.modo_calendario == "sandbox":
            fallos.append("MODO_CALENDARIO=sandbox: no se sincronizaria ningun calendario")
        if self.modo_correo != "smtp":
            fallos.append("MODO_CORREO distinto de smtp: no se enviaria ningun correo real")
        if not self.antivirus_habilitado:
            fallos.append("ANTIVIRUS_HABILITADO=false: los archivos subidos no se analizarian")

        # --- Secretos ---
        clave = self.clave_secreta.get_secret_value()
        if len(clave) < LONGITUD_MINIMA_CLAVE_SECRETA:
            fallos.append(
                f"CLAVE_SECRETA debe tener al menos {LONGITUD_MINIMA_CLAVE_SECRETA} caracteres"
            )
        if clave.startswith("<") or "generar" in clave.lower():
            fallos.append("CLAVE_SECRETA conserva el valor de ejemplo de .env.example")

        cifrado = self.clave_cifrado_datos.get_secret_value()
        if not cifrado:
            fallos.append("CLAVE_CIFRADO_DATOS es obligatoria: cifra los tokens OAuth")
        elif cifrado.startswith("<") or "generar" in cifrado.lower():
            fallos.append("CLAVE_CIFRADO_DATOS conserva el valor de ejemplo")

        if not self.postgres_contrasena.get_secret_value() and not self.bd_url:
            fallos.append("POSTGRES_CONTRASENA es obligatoria")

        # --- CORS ---
        if "*" in self.origenes_cors:
            fallos.append("ORIGENES_CORS con comodin permite peticiones de cualquier sitio")
        for origen in self.lista_origenes_cors:
            if origen.startswith("http://") and "localhost" not in origen:
                fallos.append(f"ORIGENES_CORS contiene un origen sin TLS: {origen}")

        # --- Reglas de seguridad clinica que no se pueden desactivar ---
        if not self.notificaciones_sin_datos_clinicos:
            fallos.append(
                "NOTIFICACIONES_SIN_DATOS_CLINICOS=false enviaria diagnosticos o "
                "medicamentos a la pantalla bloqueada del telefono"
            )
        if not self.rag_exigir_fuente:
            fallos.append(
                "RAG_EXIGIR_FUENTE=false permitiria al agente responder sin fuente aprobada"
            )
        if not self.redactar_datos_sensibles:
            fallos.append(
                "REDACTAR_DATOS_SENSIBLES=false escribiria datos de pacientes en los logs"
            )

        if fallos:
            detalle = "\n".join(f"  - {f}" for f in fallos)
            raise ValueError(
                "Configuracion invalida para ENTORNO=produccion.\n"
                f"{detalle}\n"
                "El arranque se aborta a proposito: un aviso en el log dejaria el "
                "sistema en marcha con un fallo invisible desde la interfaz."
            )


@lru_cache(maxsize=1)
def obtener_configuracion() -> Configuracion:
    """Configuracion en cache.

    Se usa como dependencia de FastAPI.  En las pruebas se sustituye con
    `app.dependency_overrides` o se limpia la cache con `.cache_clear()`.
    """
    return Configuracion()
