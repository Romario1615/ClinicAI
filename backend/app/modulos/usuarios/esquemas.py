"""Esquemas de entrada y salida de autenticacion.

Regla que se aplica sin excepcion (CLAUDE.md, seccion 4): **los esquemas de
salida son explicitos**. Nunca se serializa un modelo de SQLAlchemy, ni se
usa `from_attributes` sobre `Usuario`. Un modelo tiene `hash_contrasena`,
`secreto_2fa_cifrado` e `intentos_fallidos`; serializarlo entero y confiar en
recordar excluirlos es la forma habitual de filtrar credenciales al anadir un
campo meses despues.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.nucleo.seguridad import validar_politica_contrasena

# La contrasena no se valida de forma estricta al iniciar sesion: la politica
# se aplica al establecerla. Aqui solo se acota la longitud para no pasar
# megabytes a Argon2id, que es un vector de agotamiento de CPU.
LONGITUD_MAXIMA_CONTRASENA = 256

# Correo: comprobacion sintactica, no de entregabilidad.
#
# No se usa `EmailStr`. `email-validator` rechaza los dominios de uso
# reservado, y `example.invalid` es exactamente uno de ellos -- el que este
# proyecto **exige** para todo dato sintetico (CLAUDE.md, regla 1). Con
# `EmailStr`, ninguna cuenta de prueba podria iniciar sesion, y el fallo
# aparece como un 422 por "dominio reservado" que no dice nada.
#
# Ademas, al iniciar sesion no interesa si el dominio existe: interesa buscar
# una fila. Validar entregabilidad aqui solo puede rechazar direcciones que ya
# estan guardadas y son validas para la clinica.
PATRON_CORREO = r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$"
LONGITUD_MAXIMA_CORREO = 200

CorreoElectronico = Annotated[
    str,
    Field(min_length=3, max_length=LONGITUD_MAXIMA_CORREO, pattern=PATRON_CORREO),
]


class PeticionInicioSesion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correo: CorreoElectronico
    contrasena: Annotated[str, Field(min_length=1, max_length=LONGITUD_MAXIMA_CONTRASENA)]
    # Opcional: solo lo envian los roles con segundo factor obligatorio.
    codigo_2fa: Annotated[str | None, Field(default=None, max_length=16)]

    @field_validator("codigo_2fa")
    @classmethod
    def _limpiar_codigo(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        limpio = valor.strip().replace(" ", "")
        return limpio or None


class PeticionRefresco(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token_refresco: Annotated[str, Field(min_length=1, max_length=4096)]


class PeticionCierreSesion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token_refresco: Annotated[str, Field(min_length=1, max_length=4096)]
    # «Cerrar sesion en todos los dispositivos»: revoca la cadena entera de
    # rotaciones, no solo la sesion presentada.
    todos_los_dispositivos: bool = False


class CambioContrasena(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contrasena_actual: Annotated[str, Field(min_length=1, max_length=LONGITUD_MAXIMA_CONTRASENA)]
    contrasena_nueva: Annotated[str, Field(min_length=12, max_length=128)]

    @field_validator("contrasena_nueva")
    @classmethod
    def _politica_contrasena(cls, valor: str) -> str:
        problemas = validar_politica_contrasena(valor)
        if problemas:
            raise ValueError(" ".join(problemas))
        return valor


class CrearUsuarioClinica(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    correo: CorreoElectronico
    contrasena_inicial: Annotated[str, Field(min_length=12, max_length=128)]
    nombre: Annotated[str, Field(min_length=1, max_length=100)]
    apellido: Annotated[str, Field(min_length=1, max_length=100)]
    roles: Annotated[list[uuid.UUID], Field(min_length=1, max_length=8)]
    profesional_id: uuid.UUID | None = None

    @field_validator("contrasena_inicial")
    @classmethod
    def _politica_contrasena(cls, valor: str) -> str:
        problemas = validar_politica_contrasena(valor)
        if problemas:
            raise ValueError(" ".join(problemas))
        return valor

    @field_validator("roles")
    @classmethod
    def _roles_sin_repetir(cls, valor: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(valor) != len(set(valor)):
            raise ValueError("No repita roles en la asignacion.")
        return valor


class ActualizarRolesUsuario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roles: Annotated[list[uuid.UUID], Field(min_length=1, max_length=8)]
    profesional_id: uuid.UUID | None = None

    @field_validator("roles")
    @classmethod
    def _roles_sin_repetir(cls, valor: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(valor) != len(set(valor)):
            raise ValueError("No repita roles en la asignacion.")
        return valor


class ActualizarEstadoUsuario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activo: bool


class EditarDatosUsuario(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nombre: str = Field(min_length=1, max_length=100)
    apellido: str = Field(min_length=1, max_length=100)
    correo: str = Field(min_length=3, max_length=200, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class CrearRolClinica(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    codigo: Annotated[str, Field(min_length=2, max_length=50, pattern=r"^[a-z][a-z0-9_]+$")]
    nombre: Annotated[str, Field(min_length=2, max_length=100)]
    descripcion: Annotated[str | None, Field(default=None, max_length=1000)]
    permisos: Annotated[list[str], Field(min_length=1, max_length=80)]

    @field_validator("permisos")
    @classmethod
    def _permisos_sin_repetir(cls, valor: list[str]) -> list[str]:
        if len(valor) != len(set(valor)):
            raise ValueError("No repita permisos en el rol.")
        return valor


class PermisoDisponible(BaseModel):
    codigo: str
    descripcion: str
    categoria: str


class RolDisponible(BaseModel):
    id: uuid.UUID
    codigo: str
    nombre: str
    descripcion: str | None
    es_sistema: bool
    permisos: list[str]


class UsuarioAdministrado(BaseModel):
    id: uuid.UUID
    correo: str
    nombre: str
    apellido: str
    activo: bool
    roles: list[str]
    profesional_id: uuid.UUID | None = None
    especialidad: str | None = None
    ultimo_acceso_en: datetime | None


class ProfesionalDisponible(BaseModel):
    id: uuid.UUID
    nombre: str
    apellido: str
    especialidad: str | None = None


class PeticionAccesoLocal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo_rol: str = Field(min_length=1, max_length=50)


class RolAccesoLocal(BaseModel):
    codigo: str
    nombre: str
    especialidad: str | None = None


class RespuestaAccesosLocales(BaseModel):
    habilitado: bool
    roles: list[RolAccesoLocal]


class RespuestaTokens(BaseModel):
    """Par de tokens emitido.

    El refresco viaja en el cuerpo y no en una cookie. El motivo y el riesgo
    residual que eso implica estan en `docs/decisiones/0016-entrega-de-tokens.md`:
    en resumen, la defensa contra el robo de refresco no es ocultarlo, sino
    la rotacion con deteccion de reutilizacion, que revoca la familia entera
    en cuanto aparecen dos copias del mismo token.
    """

    model_config = ConfigDict(extra="forbid")

    token_acceso: str
    token_refresco: str
    # No es una credencial: es el esquema de autorizacion que el cliente
    # debe usar con `token_acceso`.
    tipo_token: str = "Bearer"  # noqa: S105
    expira_en: datetime
    # Cierto cuando el rol exige segundo factor y la sesion aun no lo cumplio.
    # El token se emite igualmente para que el cliente pueda pedir el codigo,
    # pero no sirve para operar: las dependencias lo rechazan.
    requiere_segundo_factor: bool = False


class ResumenAmbito(BaseModel):
    """Ambito del principal, para que la interfaz sepa que ofrecer.

    Es informativo. **No es un control de seguridad**: el backend vuelve a
    filtrar por ambito en cada consulta. Un guard de frontend construido con
    esto evita mostrar botones inutiles, nada mas.
    """

    model_config = ConfigDict(extra="forbid")

    clinica_id: uuid.UUID | None
    sedes: list[uuid.UUID]
    todas_las_sedes: bool
    especialidades: list[uuid.UUID]
    todas_las_especialidades: bool
    profesionales: list[uuid.UUID]
    todos_los_profesionales: bool
    todos_los_pacientes: bool
    nivel_maximo: str


class RespuestaIdentidad(BaseModel):
    """Quien es el usuario autenticado y que puede hacer."""

    model_config = ConfigDict(extra="forbid")

    usuario_id: uuid.UUID
    especialidad: str | None = None
    correo: str
    nombre: str
    apellido: str
    clinica_id: uuid.UUID | None
    roles: list[str]
    permisos: list[str]
    ambito: ResumenAmbito
    requiere_segundo_factor: bool
    segundo_factor_cumplido: bool
    dosfa_habilitado: bool
    debe_cambiar_contrasena: bool
    ultimo_acceso_en: datetime | None
    # Profesional vinculado a la cuenta, si lo hay. La interfaz lo necesita
    # para proponer «firmo yo» al crear una receta; el servidor no se fia de
    # el: la firma se valida contra la sesion.
    profesional_id: uuid.UUID | None = None


__all__ = [
    "PeticionAccesoLocal",
    "PeticionCierreSesion",
    "PeticionInicioSesion",
    "PeticionRefresco",
    "RespuestaAccesosLocales",
    "RespuestaIdentidad",
    "RespuestaTokens",
    "ResumenAmbito",
]
