"""Modelos de usuarios, roles, permisos, ambito y sesiones.

La pieza no obvia de este modulo es `AmbitoAsignacion`.  Un sistema de roles
sin ambito responde «que puede hacer este usuario», pero no «sobre que datos»,
y en una clinica multi-sede esa segunda pregunta es la que protege la
privacidad: un medico con permiso de lectura de historia clinica no debe leer
la historia de un paciente de otra sede con el que no tiene relacion.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.nucleo.bd import Base, MezclaAuditoria, MezclaIdentificador


class ResultadoAcceso(StrEnum):
    EXITO = "EXITO"
    CREDENCIAL_INVALIDA = "CREDENCIAL_INVALIDA"
    CUENTA_INACTIVA = "CUENTA_INACTIVA"
    BLOQUEADO = "BLOQUEADO"
    SEGUNDO_FACTOR_FALLIDO = "SEGUNDO_FACTOR_FALLIDO"


class MotivoRevocacion(StrEnum):
    CIERRE_SESION = "CIERRE_SESION"
    ROTACION = "ROTACION"
    REUTILIZACION_DETECTADA = "REUTILIZACION_DETECTADA"
    CAMBIO_CONTRASENA = "CAMBIO_CONTRASENA"
    USUARIO_DESACTIVADO = "USUARIO_DESACTIVADO"
    REVOCACION_ADMINISTRATIVA = "REVOCACION_ADMINISTRATIVA"
    EXPIRACION = "EXPIRACION"


# ---------------------------------------------------------------------------
#  Usuario
# ---------------------------------------------------------------------------
class Usuario(Base, MezclaIdentificador, MezclaAuditoria):
    """Cuenta de una persona del personal de la clinica.

    Los pacientes **no** son usuarios: no tienen cuenta ni contrasena.
    Interactuan por WhatsApp y su identidad se resuelve por el canal mas la
    verificacion adicional.  Mezclar ambos conceptos obligaria a que la tabla
    de usuarios tuviera permisos, contrasenas y bloqueos para pacientes que
    nunca inician sesion, y aumentaria la superficie de ataque sin motivo.
    """

    __tablename__ = "usuario"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    correo: Mapped[str] = mapped_column(String(200))
    hash_contrasena: Mapped[str] = mapped_column(String(255))
    nombre: Mapped[str] = mapped_column(String(100))
    apellido: Mapped[str] = mapped_column(String(100))
    telefono: Mapped[str | None] = mapped_column(String(32), default=None)

    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    correo_verificado_en: Mapped[datetime | None] = mapped_column(default=None)
    debe_cambiar_contrasena: Mapped[bool] = mapped_column(Boolean, default=False)
    ultimo_acceso_en: Mapped[datetime | None] = mapped_column(default=None)

    # --- Bloqueo por intentos fallidos ---
    intentos_fallidos: Mapped[int] = mapped_column(SmallInteger, default=0)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(default=None)

    # --- Segundo factor ---
    # El secreto TOTP se almacena cifrado con AES-GCM, no en claro: un
    # volcado de la base de datos no debe permitir generar codigos validos.
    secreto_2fa_cifrado: Mapped[str | None] = mapped_column(Text, default=None)
    dosfa_habilitado: Mapped[bool] = mapped_column("2fa_habilitado", Boolean, default=False)
    dosfa_confirmado_en: Mapped[datetime | None] = mapped_column("2fa_confirmado_en", default=None)

    roles: Mapped[list[UsuarioRol]] = relationship(back_populates="usuario", lazy="raise")

    __table_args__ = (
        # El correo es unico POR CLINICA, no globalmente: un profesional
        # puede colaborar con dos clinicas distintas del mismo grupo.
        UniqueConstraint("clinica_id", "correo", name="uq_usuario_clinica_id_correo"),
        CheckConstraint("intentos_fallidos >= 0", name="intentos_no_negativos"),
        CheckConstraint(
            'NOT "2fa_habilitado" OR secreto_2fa_cifrado IS NOT NULL',
            name="2fa_exige_secreto",
        ),
        Index("ix_usuario_clinica_activo", "clinica_id", "activo"),
    )

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombre} {self.apellido}"


class CodigoRecuperacion2FA(Base, MezclaIdentificador, MezclaAuditoria):
    """Codigos de un solo uso para recuperar el acceso sin el telefono.

    Sin ellos, perder el dispositivo con el segundo factor obligatorio deja a
    un profesional fuera del sistema y obliga a una intervencion manual con
    verificacion de identidad fuera de banda.
    """

    __tablename__ = "codigo_recuperacion_2fa"

    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"))
    # Solo el hash.  El codigo en claro se muestra una unica vez.
    hash_codigo: Mapped[str] = mapped_column(String(64))
    usado_en: Mapped[datetime | None] = mapped_column(default=None)

    __table_args__ = (
        UniqueConstraint(
            "usuario_id", "hash_codigo", name="uq_codigo_recuperacion_usuario_id_hash"
        ),
        Index(
            "ix_codigo_recuperacion_disponibles",
            "usuario_id",
            postgresql_where=text("usado_en IS NULL"),
        ),
    )


# ---------------------------------------------------------------------------
#  Roles y permisos
# ---------------------------------------------------------------------------
class Permiso(Base, MezclaIdentificador):
    """Catalogo de permisos.

    Se persiste, aunque el catalogo tambien vive en `app.nucleo.autorizacion`,
    por dos razones: permite que la interfaz liste y describa los permisos sin
    consultar el codigo, y permite que un rol propio de la clinica referencie
    permisos por clave externa, con integridad garantizada.

    Una prueba comprueba que la tabla y el catalogo del codigo coinciden.  Si
    divergen, un permiso del codigo podria no existir en la base y quedar sin
    efecto sin que nadie lo note.
    """

    __tablename__ = "permiso"

    codigo: Mapped[str] = mapped_column(String(100))
    descripcion: Mapped[str] = mapped_column(String(255))
    categoria: Mapped[str] = mapped_column(String(50))
    # Si es cierto, tener el permiso no basta: hace falta vinculo asistencial
    # con el paciente concreto.
    requiere_relacion_asistencial: Mapped[bool] = mapped_column(Boolean, default=False)
    nivel_sensibilidad: Mapped[str] = mapped_column(String(4), default="N1")

    __table_args__ = (
        UniqueConstraint("codigo", name="uq_permiso_codigo"),
        CheckConstraint("nivel_sensibilidad IN ('N0', 'N1', 'N2', 'N3')", name="nivel_valido"),
    )


class Rol(Base, MezclaIdentificador, MezclaAuditoria):
    """Agrupacion de permisos.

    `clinica_id` nulo identifica los roles del sistema (los seis roles base),
    que son comunes a todas las clinicas y no se pueden modificar.
    """

    __tablename__ = "rol"

    clinica_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clinica.id", ondelete="CASCADE"), default=None
    )
    codigo: Mapped[str] = mapped_column(String(50))
    nombre: Mapped[str] = mapped_column(String(100))
    descripcion: Mapped[str | None] = mapped_column(Text, default=None)
    es_sistema: Mapped[bool] = mapped_column(Boolean, default=False)

    permisos: Mapped[list[RolPermiso]] = relationship(
        back_populates="rol", lazy="raise", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Dos indices unicos parciales en lugar de uno compuesto: los roles
        # del sistema tienen clinica_id nulo, y en PostgreSQL los nulos no
        # colisionan en un indice unico, asi que un UNIQUE(clinica_id, codigo)
        # permitiria varios roles de sistema con el mismo codigo.
        Index(
            "ix_rol_sistema_codigo",
            "codigo",
            unique=True,
            postgresql_where=text("clinica_id IS NULL"),
        ),
        Index(
            "ix_rol_clinica_codigo",
            "clinica_id",
            "codigo",
            unique=True,
            postgresql_where=text("clinica_id IS NOT NULL"),
        ),
        CheckConstraint("NOT es_sistema OR clinica_id IS NULL", name="rol_sistema_sin_clinica"),
    )


class RolPermiso(Base):
    """Relacion entre rol y permiso."""

    __tablename__ = "rol_permiso"

    rol_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rol.id", ondelete="CASCADE"), primary_key=True
    )
    permiso_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("permiso.id", ondelete="RESTRICT"), primary_key=True
    )

    rol: Mapped[Rol] = relationship(back_populates="permisos", lazy="raise")
    permiso: Mapped[Permiso] = relationship(lazy="raise")


class UsuarioRol(Base, MezclaIdentificador, MezclaAuditoria):
    """Asignacion de un rol a un usuario, con vigencia.

    La vigencia permite cubrir una baja o una suplencia sin tener que
    acordarse de revocar el rol despues.  Un rol que se olvida revocado es
    una de las formas mas comunes de acceso indebido persistente.
    """

    __tablename__ = "usuario_rol"

    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"))
    rol_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rol.id", ondelete="RESTRICT"))
    otorgado_por: Mapped[uuid.UUID | None] = mapped_column(default=None)
    vigente_desde: Mapped[date | None] = mapped_column(Date, default=None)
    vigente_hasta: Mapped[date | None] = mapped_column(Date, default=None)

    usuario: Mapped[Usuario] = relationship(back_populates="roles", lazy="raise")
    rol: Mapped[Rol] = relationship(lazy="raise")
    ambitos: Mapped[list[AmbitoAsignacion]] = relationship(
        back_populates="usuario_rol", lazy="raise", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("usuario_id", "rol_id", name="uq_usuario_rol_usuario_id_rol_id"),
        CheckConstraint(
            "vigente_hasta IS NULL OR vigente_desde IS NULL OR vigente_hasta >= vigente_desde",
            name="vigencia_coherente",
        ),
    )


class AmbitoAsignacion(Base, MezclaIdentificador, MezclaAuditoria):
    """Limita un rol asignado a un subconjunto de datos.

    `valor_id` nulo con `incluir` cierto significa «todos los de este tipo».
    Es el comodin, y hay que concederlo de forma explicita: la ausencia de
    filas no se interpreta como acceso total, sino como acceso nulo.

    `incluir=false` permite listas de exclusion: «todas las sedes menos la
    Norte».  Se evalua despues de las inclusiones, de modo que una exclusion
    siempre gana.  Es la semantica segura: ante reglas contradictorias, se
    deniega.
    """

    __tablename__ = "ambito_asignacion"

    usuario_rol_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuario_rol.id", ondelete="CASCADE")
    )
    tipo: Mapped[str] = mapped_column(String(24))
    valor_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    incluir: Mapped[bool] = mapped_column(Boolean, default=True)

    usuario_rol: Mapped[UsuarioRol] = relationship(back_populates="ambitos", lazy="raise")

    __table_args__ = (
        CheckConstraint(
            "tipo IN ('CLINICA', 'SEDE', 'ESPECIALIDAD', 'PROFESIONAL', "
            "'PACIENTE', 'TIPO_INFORMACION')",
            name="tipo_ambito_valido",
        ),
        # Una exclusion sin destino concreto no significa nada: excluir
        # "todas las sedes" dejaria el ambito vacio de forma confusa.  Se
        # prohibe para que el error se vea al escribir, no al denegar acceso.
        CheckConstraint("incluir OR valor_id IS NOT NULL", name="exclusion_exige_destino"),
        Index("ix_ambito_usuario_rol_tipo", "usuario_rol_id", "tipo"),
    )


# ---------------------------------------------------------------------------
#  Sesiones y accesos
# ---------------------------------------------------------------------------
class Sesion(Base, MezclaIdentificador):
    """Token de refresco emitido, con su estado.

    Cada refresco se usa una sola vez.  Al rotarlo se inserta una fila nueva y
    la anterior queda marcada como usada.  Si un refresco ya usado vuelve a
    presentarse, significa que alguien tiene una copia robada: se revoca toda
    la `familia`, no solo ese token.  Revocar solo el token presentado dejaria
    al atacante con la cadena viva si fue el primero en usarlo.
    """

    __tablename__ = "sesion"

    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"))
    # Hash del jti, no el jti.  Un volcado de la base no entrega tokens
    # utilizables.
    jti_refresco_hash: Mapped[str] = mapped_column(String(64))
    familia: Mapped[str] = mapped_column(String(64))
    # Cadena de rotacion: apunta a la sesion de la que proviene.
    sesion_anterior_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sesion.id", ondelete="SET NULL"), default=None
    )

    ip: Mapped[str | None] = mapped_column(INET, default=None)
    agente_usuario: Mapped[str | None] = mapped_column(String(512), default=None)
    segundo_factor_cumplido: Mapped[bool] = mapped_column(Boolean, default=False)

    creada_en: Mapped[datetime] = mapped_column(server_default=text("now()"))
    expira_en: Mapped[datetime] = mapped_column()
    usada_en: Mapped[datetime | None] = mapped_column(default=None)
    revocada_en: Mapped[datetime | None] = mapped_column(default=None)
    motivo_revocacion: Mapped[str | None] = mapped_column(String(32), default=None)

    __table_args__ = (
        UniqueConstraint("jti_refresco_hash", name="uq_sesion_jti_refresco_hash"),
        # Indice parcial sobre las sesiones vivas: es la consulta del camino
        # caliente (validar un refresco) y el indice completo crece sin
        # limite con el historico.
        Index(
            "ix_sesion_activas",
            "usuario_id",
            "familia",
            postgresql_where=text("revocada_en IS NULL AND usada_en IS NULL"),
        ),
        Index("ix_sesion_familia", "familia"),
        CheckConstraint(
            "revocada_en IS NULL OR motivo_revocacion IS NOT NULL",
            name="revocacion_con_motivo",
        ),
    )

    def esta_viva(self, ahora: datetime) -> bool:
        return self.revocada_en is None and self.usada_en is None and self.expira_en > ahora


class HistorialAcceso(Base, MezclaIdentificador):
    """Registro de intentos de inicio de sesion, exitosos y fallidos.

    Los fallidos son los que importan: son la senal de un ataque de fuerza
    bruta o de relleno de credenciales.  Se guarda el correo intentado aunque
    no exista la cuenta, porque saber que alguien probo cien correos es
    informacion, pero **no** se guarda la contrasena intentada bajo ninguna
    circunstancia.
    """

    __tablename__ = "historial_acceso"

    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="SET NULL"), default=None
    )
    clinica_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    correo_intentado: Mapped[str] = mapped_column(String(200))
    resultado: Mapped[str] = mapped_column(String(32))
    ip: Mapped[str | None] = mapped_column(INET, default=None)
    agente_usuario: Mapped[str | None] = mapped_column(String(512), default=None)
    ocurrido_en: Mapped[datetime] = mapped_column(server_default=text("now()"))
    metadatos: Mapped[dict[str, object] | None] = mapped_column(JSONB, default=None)

    __table_args__ = (
        Index("ix_historial_acceso_usuario", "usuario_id", "ocurrido_en"),
        # Indice para la deteccion de fuerza bruta por origen.
        Index("ix_historial_acceso_ip", "ip", "ocurrido_en"),
        Index("ix_historial_acceso_correo", "correo_intentado", "ocurrido_en"),
        CheckConstraint(
            "resultado IN ('EXITO', 'CREDENCIAL_INVALIDA', 'CUENTA_INACTIVA', "
            "'BLOQUEADO', 'SEGUNDO_FACTOR_FALLIDO')",
            name="resultado_valido",
        ),
    )


class TokenUnUso(Base, MezclaIdentificador):
    """Token de verificacion de correo o de recuperacion de contrasena.

    Se almacena el hash, nunca el token.  El proposito va en `tipo` para que
    un token de verificacion de correo no sirva para restablecer la
    contrasena: son dos operaciones con consecuencias muy distintas.
    """

    __tablename__ = "token_un_uso"

    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"))
    tipo: Mapped[str] = mapped_column(String(32))
    hash_token: Mapped[str] = mapped_column(String(64))
    creado_en: Mapped[datetime] = mapped_column(server_default=text("now()"))
    expira_en: Mapped[datetime] = mapped_column()
    usado_en: Mapped[datetime | None] = mapped_column(default=None)
    ip_uso: Mapped[str | None] = mapped_column(INET, default=None)

    __table_args__ = (
        UniqueConstraint("hash_token", name="uq_token_un_uso_hash_token"),
        CheckConstraint(
            "tipo IN ('VERIFICACION_CORREO', 'RECUPERACION_CONTRASENA')",
            name="tipo_token_valido",
        ),
        Index(
            "ix_token_un_uso_pendientes",
            "usuario_id",
            "tipo",
            postgresql_where=text("usado_en IS NULL"),
        ),
    )
