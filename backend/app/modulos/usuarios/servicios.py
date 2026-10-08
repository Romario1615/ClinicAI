"""Servicios de autenticacion y resolucion de permisos.

Este modulo decide quien es cada peticion y que puede hacer.  Es la pieza mas
sensible del sistema: un error aqui no produce un fallo visible, produce
acceso indebido silencioso.

Decisiones y su motivo
----------------------
**El token no lleva permisos.**  Lleva el identificador del usuario y poco
mas.  Los permisos se resuelven de la base de datos en cada peticion.  Si
viajaran en el token, revocar un permiso no surtiria efecto hasta que el token
caducara, y en datos clinicos eso es inaceptable: un profesional despedido
seguiria leyendo historias clinicas durante quince minutos.

**Rotacion con deteccion de reutilizacion.**  Cada token de refresco se usa
una sola vez.  Si uno ya usado vuelve a presentarse, alguien tiene una copia
robada: se revoca toda la familia de sesiones, no solo ese token.  Revocar
solo el presentado dejaria al atacante con la cadena viva si fue el primero
en usarlo.

**Respuestas indistinguibles.**  Correo inexistente y contrasena incorrecta
devuelven lo mismo.  Distinguirlos permitiria enumerar las cuentas del
personal de la clinica.

**El bloqueo cuenta por cuenta Y por origen.**  Solo por cuenta, un atacante
prueba una contrasena en mil cuentas sin activar ningun bloqueo; solo por
origen, se evade con direcciones rotatorias.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.organizacion.modelos import Clinica
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.especialidades import especialidades_de_usuarios
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
from app.nucleo.auditoria import (
    AccionAuditada,
    EntradaAuditoria,
    ResultadoAuditoria,
    construir_entrada,
)
from app.nucleo.autorizacion import (
    PERMISOS_SOLO_ASISTENCIALES,
    Ambito,
    NivelSensibilidad,
    Principal,
    TipoActor,
    TipoAmbito,
)
from app.nucleo.errores import (
    CredencialesInvalidas,
    CuentaBloqueada,
    DatosInvalidos,
    RecursoNoEncontrado,
    SegundoFactorInvalido,
    SegundoFactorRequerido,
    TokenInvalido,
    TokenRevocado,
)
from app.nucleo.reloj import Reloj
from app.nucleo.seguridad import (
    CifradorDatos,
    ContenidoToken,
    crear_token_acceso,
    crear_token_refresco,
    decodificar_token,
    generar_familia_sesion,
    hashear_contrasena,
    hashear_jti,
    requiere_rehash,
    validar_politica_contrasena,
    verificar_codigo_totp,
    verificar_contrasena,
)


@dataclass(frozen=True, slots=True)
class ParTokens:
    """Tokens emitidos tras un inicio de sesion o una rotacion."""

    token_acceso: str
    token_refresco: str
    expira_en: datetime
    # Cierto si el usuario tiene 2FA obligatorio y todavia no lo ha cumplido.
    # El token de acceso se emite igualmente para que el cliente pueda pedir
    # el codigo, pero no sirve para operar: las dependencias lo rechazan.
    requiere_segundo_factor: bool = False


@dataclass(frozen=True, slots=True)
class ResultadoAutenticacion:
    tokens: ParTokens | None
    auditoria: tuple[EntradaAuditoria, ...]


class ServicioAutenticacion:
    """Inicio de sesion, rotacion de tokens y resolucion de permisos."""

    def __init__(
        self,
        sesion: AsyncSession,
        reloj: Reloj,
        *,
        clave_secreta: str,
        algoritmo: str,
        minutos_token_acceso: int,
        dias_token_refresco: int,
        max_intentos_login: int,
        minutos_bloqueo_login: int,
        roles_con_2fa: frozenset[str],
        cifrador: CifradorDatos,
        permite_acceso_local_demo: bool = False,
    ) -> None:
        self._sesion = sesion
        self._reloj = reloj
        self._clave = clave_secreta
        self._algoritmo = algoritmo
        self._minutos_acceso = minutos_token_acceso
        self._dias_refresco = dias_token_refresco
        self._max_intentos = max_intentos_login
        self._minutos_bloqueo = minutos_bloqueo_login
        self._roles_con_2fa = roles_con_2fa
        self._cifrador = cifrador
        self._permite_acceso_local_demo = permite_acceso_local_demo

    async def _usuarios_acceso_local(self) -> dict[str, Usuario]:
        """El listado y el ingreso eligen la misma cuenta sintetica por rol."""
        if not self._permite_acceso_local_demo:
            return {}

        roles_habilitados = (
            "superadministrador",
            "administrador_clinica",
            "recepcion",
            "asistente",
            "auditor",
            "profesional",
        )
        consulta = (
            select(Rol.codigo, Usuario)
            .join(UsuarioRol, UsuarioRol.rol_id == Rol.id)
            .join(Usuario, Usuario.id == UsuarioRol.usuario_id)
            .where(
                Rol.codigo.in_(roles_habilitados),
                Rol.es_sistema.is_(True),
                Rol.clinica_id.is_(None),
                Usuario.activo.is_(True),
                Usuario.apellido.contains("[SINTETICO]"),
            )
            .order_by(Usuario.correo, Usuario.id)
        )
        disponibles: dict[str, Usuario] = {}
        for codigo, usuario in await self._sesion.execute(consulta):
            disponibles.setdefault(codigo, usuario)
        return {
            codigo: disponibles[codigo] for codigo in roles_habilitados if codigo in disponibles
        }

    async def roles_acceso_local(self) -> list[str]:
        """Lista roles con cuentas sinteticas disponibles para acceso local."""
        return list(await self._usuarios_acceso_local())

    async def detalles_accesos_locales(self) -> list[tuple[str, str | None]]:
        usuarios = await self._usuarios_acceso_local()
        especialidades = await especialidades_de_usuarios(
            self._sesion, [u.id for u in usuarios.values()]
        )
        return [(codigo, especialidades.get(u.id)) for codigo, u in usuarios.items()]

    async def especialidad_usuario(self, usuario: Usuario) -> str | None:
        especialidades = await especialidades_de_usuarios(
            self._sesion, [usuario.id], clinica_id=usuario.clinica_id
        )
        return especialidades.get(usuario.id)

    async def iniciar_sesion_rol_local(
        self,
        *,
        codigo_rol: str,
        ip: str | None = None,
        agente_usuario: str | None = None,
    ) -> ResultadoAutenticacion:
        """Inicia una sesion de rol con una cuenta marcada como sintetica.

        Esta ruta no acepta una cuenta elegida por el cliente. Solo admite los
        roles locales conocidos, y resuelve una cuenta activa con el marcador
        `[SINTETICO]`. El acceso solo se habilita en local/desarrollo desde la
        configuracion de la aplicacion.
        """
        usuario = (await self._usuarios_acceso_local()).get(codigo_rol)
        if usuario is None:
            raise RecursoNoEncontrado("El acceso local solicitado no esta disponible.")

        ahora = self._reloj.ahora()

        usuario.ultimo_acceso_en = ahora
        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
        # Los accesos de desarrollo pueden entrar a los roles que normalmente
        # requieren 2FA, usando exclusivamente una cuenta de datos sinteticos.
        exige_2fa = await self._exige_segundo_factor(usuario)
        tokens = await self._emitir_tokens(
            usuario,
            ahora=ahora,
            familia=generar_familia_sesion(),
            segundo_factor_cumplido=exige_2fa,
            requiere_segundo_factor=exige_2fa,
            ip=ip,
            agente_usuario=agente_usuario,
            sesion_anterior_id=None,
        )
        self._registrar_acceso(
            usuario.correo.lower(),
            usuario.clinica_id,
            ResultadoAcceso.EXITO,
            ip,
            agente_usuario,
            ahora,
            usuario_id=usuario.id,
        )
        principal = await self.resolver_principal_de_usuario(
            usuario, segundo_factor_cumplido=exige_2fa
        )
        entrada = construir_entrada(
            accion=AccionAuditada.LOGIN_ROL_LOCAL,
            principal=principal,
            ahora=ahora,
            entidad_tipo="usuario",
            entidad_id=usuario.id,
            ip=ip,
            codigo_rol=codigo_rol,
            cuenta_sintetica=True,
        )
        return ResultadoAutenticacion(tokens, (entrada,))

    # ==================================================================
    #  Inicio de sesion
    # ==================================================================
    async def iniciar_sesion(
        self,
        *,
        correo: str,
        contrasena: str,
        ip: str | None = None,
        agente_usuario: str | None = None,
        codigo_2fa: str | None = None,
    ) -> ResultadoAutenticacion:
        """Autentica y emite tokens.

        El orden de las comprobaciones esta pensado para no filtrar
        informacion:

        1. Se busca la cuenta.  Si no existe, se verifica una contrasena
           contra un hash falso de todas formas.  Sin ese paso, la respuesta
           llegaria antes para un correo inexistente que para uno real, y el
           tiempo de respuesta revelaria que cuentas existen.
        2. Se comprueba el bloqueo antes de la contrasena, para que un ataque
           de fuerza bruta no siga consumiendo ciclos de Argon2id.
        3. El segundo factor se comprueba al final, cuando ya se sabe que la
           contrasena es correcta.
        """
        ahora = self._reloj.ahora()
        correo_normalizado = correo.strip().lower()

        usuario = await self._buscar_usuario(correo_normalizado)
        clinica_id = usuario.clinica_id if usuario is not None else None

        # Comparacion de tiempo equivalente aunque la cuenta no exista.
        # `verificar_contrasena` con un hash valido cuesta lo mismo que el
        # caso real, asi que el tiempo de respuesta no distingue.
        if usuario is None:
            verificar_contrasena(contrasena, _HASH_SENUELO)
            return self._fallo_de_acceso(
                correo_normalizado,
                clinica_id,
                ResultadoAcceso.CREDENCIAL_INVALIDA,
                ip,
                agente_usuario,
                ahora,
            )

        if not usuario.activo:
            return self._fallo_de_acceso(
                correo_normalizado,
                clinica_id,
                ResultadoAcceso.CUENTA_INACTIVA,
                ip,
                agente_usuario,
                ahora,
                usuario_id=usuario.id,
            )

        if usuario.bloqueado_hasta is not None and usuario.bloqueado_hasta > ahora:
            minutos = max(1, int((usuario.bloqueado_hasta - ahora).total_seconds() // 60))
            self._registrar_acceso(
                correo_normalizado,
                clinica_id,
                ResultadoAcceso.BLOQUEADO,
                ip,
                agente_usuario,
                ahora,
                usuario_id=usuario.id,
            )
            raise CuentaBloqueada(
                f"La cuenta esta bloqueada temporalmente. Intente de nuevo en {minutos} minuto(s)."
            )

        if not verificar_contrasena(contrasena, usuario.hash_contrasena):
            usuario.intentos_fallidos += 1
            if usuario.intentos_fallidos >= self._max_intentos:
                usuario.bloqueado_hasta = ahora + timedelta(minutes=self._minutos_bloqueo)
            return self._fallo_de_acceso(
                correo_normalizado,
                clinica_id,
                ResultadoAcceso.CREDENCIAL_INVALIDA,
                ip,
                agente_usuario,
                ahora,
                usuario_id=usuario.id,
            )

        # --- Contrasena correcta ---
        #
        # Se actualiza el hash si los parametros de Argon2id se endurecieron
        # desde el ultimo inicio de sesion.  Es el unico momento en que la
        # contrasena en claro esta disponible para recalcularlo.
        if requiere_rehash(usuario.hash_contrasena):
            usuario.hash_contrasena = hashear_contrasena(contrasena)

        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
        usuario.ultimo_acceso_en = ahora

        # --- Segundo factor ---
        exige_2fa = await self._exige_segundo_factor(usuario)
        segundo_factor_cumplido = False

        if exige_2fa:
            if not usuario.dosfa_habilitado or usuario.secreto_2fa_cifrado is None:
                # El rol exige 2FA pero el usuario no lo ha configurado.  No
                # se le deja entrar sin mas: se le obliga a configurarlo.
                self._registrar_acceso(
                    correo_normalizado,
                    clinica_id,
                    ResultadoAcceso.SEGUNDO_FACTOR_FALLIDO,
                    ip,
                    agente_usuario,
                    ahora,
                    usuario_id=usuario.id,
                )
                raise SegundoFactorRequerido(
                    "Su rol exige segundo factor de autenticacion y todavia no "
                    "lo ha configurado. Contacte con el administrador."
                )

            if codigo_2fa is None:
                raise SegundoFactorRequerido(
                    "Introduzca el codigo de su aplicacion de autenticacion."
                )

            secreto = self._cifrador.descifrar(
                usuario.secreto_2fa_cifrado, contexto=usuario.id.bytes
            )
            if not verificar_codigo_totp(secreto, codigo_2fa):
                usuario.intentos_fallidos += 1
                if usuario.intentos_fallidos >= self._max_intentos:
                    usuario.bloqueado_hasta = ahora + timedelta(minutes=self._minutos_bloqueo)
                self._registrar_acceso(
                    correo_normalizado,
                    clinica_id,
                    ResultadoAcceso.SEGUNDO_FACTOR_FALLIDO,
                    ip,
                    agente_usuario,
                    ahora,
                    usuario_id=usuario.id,
                )
                raise SegundoFactorInvalido("El codigo introducido no es valido.")

            segundo_factor_cumplido = True

        tokens = await self._emitir_tokens(
            usuario,
            ahora=ahora,
            familia=generar_familia_sesion(),
            segundo_factor_cumplido=segundo_factor_cumplido,
            requiere_segundo_factor=exige_2fa,
            ip=ip,
            agente_usuario=agente_usuario,
            sesion_anterior_id=None,
        )

        self._registrar_acceso(
            correo_normalizado,
            clinica_id,
            ResultadoAcceso.EXITO,
            ip,
            agente_usuario,
            ahora,
            usuario_id=usuario.id,
        )

        principal = await self.resolver_principal_de_usuario(
            usuario, segundo_factor_cumplido=segundo_factor_cumplido
        )
        entrada = construir_entrada(
            accion=AccionAuditada.LOGIN_EXITOSO,
            principal=principal,
            ahora=ahora,
            entidad_tipo="usuario",
            entidad_id=usuario.id,
            ip=ip,
        )

        return ResultadoAutenticacion(tokens, (entrada,))

    # ==================================================================
    #  Rotacion de tokens
    # ==================================================================
    async def refrescar_sesion(
        self,
        *,
        token_refresco: str,
        ip: str | None = None,
        agente_usuario: str | None = None,
    ) -> ResultadoAutenticacion:
        """Rota el token de refresco y emite un par nuevo.

        Aqui esta la deteccion de robo de token.  Si el refresco presentado ya
        se habia usado, hay dos copias circulando: la del usuario legitimo y
        la del atacante.  No se puede saber quien es quien, asi que se revoca
        la familia completa y ambos tienen que volver a iniciar sesion.  Es
        molesto para el usuario legitimo y es la unica respuesta segura.
        """
        ahora = self._reloj.ahora()

        contenido = decodificar_token(
            token_refresco,
            clave_secreta=self._clave,
            algoritmo=self._algoritmo,
            tipo_esperado="refresco",
            ahora=ahora,
        )

        hash_jti = hashear_jti(contenido.jti)
        fila = (
            await self._sesion.execute(
                select(Sesion).where(Sesion.jti_refresco_hash == hash_jti).with_for_update()
            )
        ).scalar_one_or_none()

        if fila is None:
            # El token esta firmado pero no consta: la sesion se purgo o el
            # token es de otra instalacion.
            raise TokenInvalido("La sesion no existe o ya fue cerrada.")

        if fila.revocada_en is not None:
            raise TokenRevocado("La sesion fue revocada. Inicie sesion de nuevo.")

        if fila.usada_en is not None:
            # ===============================================================
            #  Reutilizacion detectada
            # ===============================================================
            await self._revocar_familia(
                fila.familia, motivo=MotivoRevocacion.REUTILIZACION_DETECTADA, ahora=ahora
            )
            principal = await self.resolver_principal_por_id(fila.usuario_id)
            entrada = construir_entrada(
                accion=AccionAuditada.TOKEN_REUTILIZADO,
                principal=principal,
                ahora=ahora,
                resultado=ResultadoAuditoria.DENEGADO,
                entidad_tipo="sesion",
                entidad_id=fila.id,
                ip=ip,
                motivo=(
                    "Se presento un token de refresco ya utilizado. Se revoco "
                    "la familia de sesiones completa."
                ),
                familia=fila.familia,
            )
            # Genera alerta: `TOKEN_REUTILIZADO` esta en ACCIONES_CON_ALERTA.
            return ResultadoAutenticacion(None, (entrada,))

        usuario = (
            await self._sesion.execute(select(Usuario).where(Usuario.id == fila.usuario_id))
        ).scalar_one_or_none()
        if usuario is None or not usuario.activo or not await self._clinica_habilitada(usuario):
            await self._revocar_familia(
                fila.familia, motivo=MotivoRevocacion.USUARIO_DESACTIVADO, ahora=ahora
            )
            raise TokenRevocado("La cuenta ya no esta activa.")

        # Se marca el refresco como usado ANTES de emitir el nuevo.  Si algo
        # fallara despues, el token queda inutilizable, que es el lado seguro
        # del error.
        fila.usada_en = ahora

        exige_2fa = await self._exige_segundo_factor(usuario)

        tokens = await self._emitir_tokens(
            usuario,
            ahora=ahora,
            familia=fila.familia,
            # El segundo factor se hereda de la sesion anterior: obligar a
            # reintroducir el codigo en cada rotacion, cada quince minutos,
            # llevaria al personal a desactivar el 2FA.
            segundo_factor_cumplido=fila.segundo_factor_cumplido,
            requiere_segundo_factor=exige_2fa,
            ip=ip,
            agente_usuario=agente_usuario,
            sesion_anterior_id=fila.id,
        )

        principal = await self.resolver_principal_de_usuario(
            usuario, segundo_factor_cumplido=fila.segundo_factor_cumplido
        )
        entrada = construir_entrada(
            accion=AccionAuditada.TOKEN_REFRESCADO,
            principal=principal,
            ahora=ahora,
            entidad_tipo="sesion",
            entidad_id=fila.id,
            ip=ip,
        )

        return ResultadoAutenticacion(tokens, (entrada,))

    async def cerrar_sesion(
        self, *, token_refresco: str, revocar_familia: bool = False
    ) -> tuple[EntradaAuditoria, ...]:
        """Revoca la sesion actual, u opcionalmente todas las del dispositivo.

        `revocar_familia` sirve al boton de «cerrar sesion en todos los
        dispositivos»: revoca la cadena completa de rotaciones.
        """
        ahora = self._reloj.ahora()
        contenido = decodificar_token(
            token_refresco,
            clave_secreta=self._clave,
            algoritmo=self._algoritmo,
            tipo_esperado="refresco",
            ahora=ahora,
        )

        hash_jti = hashear_jti(contenido.jti)
        fila = (
            await self._sesion.execute(select(Sesion).where(Sesion.jti_refresco_hash == hash_jti))
        ).scalar_one_or_none()

        if fila is None:
            # Cerrar una sesion que no consta no es un error: el resultado
            # deseado -- que el token no sirva -- ya se cumple.
            return ()

        if revocar_familia:
            await self._revocar_familia(
                fila.familia, motivo=MotivoRevocacion.CIERRE_SESION, ahora=ahora
            )
        else:
            fila.revocada_en = ahora
            fila.motivo_revocacion = MotivoRevocacion.CIERRE_SESION.value

        principal = await self.resolver_principal_por_id(fila.usuario_id)
        return (
            construir_entrada(
                accion=AccionAuditada.LOGOUT,
                principal=principal,
                ahora=ahora,
                entidad_tipo="sesion",
                entidad_id=fila.id,
                familia_revocada=revocar_familia,
            ),
        )

    async def revocar_todas_las_sesiones(
        self, usuario_id: uuid.UUID, *, motivo: MotivoRevocacion
    ) -> int:
        """Revoca todas las sesiones vivas de un usuario.

        Se invoca al desactivar la cuenta y al cambiar la contrasena.  Sin
        esto, desactivar a un usuario no le quitaria el acceso hasta que
        caducara su token, y en datos clinicos ese retraso importa.
        """
        ahora = self._reloj.ahora()
        filas = (
            await self._sesion.execute(
                select(Sesion).where(
                    Sesion.usuario_id == usuario_id,
                    Sesion.revocada_en.is_(None),
                )
            )
        ).scalars()
        contador = 0
        for fila in filas:
            fila.revocada_en = ahora
            fila.motivo_revocacion = motivo.value
            contador += 1
        return contador

    # ==================================================================
    #  Resolucion del principal
    # ==================================================================
    async def resolver_principal_desde_token(self, token_acceso: str) -> Principal:
        """Construye el principal a partir de un token de acceso.

        Los permisos se leen de la base de datos, no del token.  Cuesta una
        consulta por peticion y es lo que hace que revocar un permiso surta
        efecto de inmediato.
        """
        contenido: ContenidoToken = decodificar_token(
            token_acceso,
            clave_secreta=self._clave,
            algoritmo=self._algoritmo,
            tipo_esperado="acceso",
            ahora=self._reloj.ahora(),
        )

        usuario = (
            await self._sesion.execute(select(Usuario).where(Usuario.id == contenido.usuario_id))
        ).scalar_one_or_none()

        if usuario is None or not usuario.activo or not await self._clinica_habilitada(usuario):
            raise TokenRevocado("La cuenta ya no esta activa.")

        # Revocar solo el refresco deja vivo su token de acceso durante hasta
        # quince minutos. La familia conserva exactamente un refresco actual
        # no usado mientras la sesión siga activa; exigirlo hace que cierre de
        # sesión, reasignación de clínica y desactivación corten el acceso al
        # momento, también ante un JWT ya emitido.
        sesion_activa = await self._sesion.scalar(
            select(Sesion.id)
            .where(
                Sesion.usuario_id == usuario.id,
                Sesion.familia == contenido.familia,
                Sesion.usada_en.is_(None),
                Sesion.revocada_en.is_(None),
                Sesion.expira_en > self._reloj.ahora(),
            )
            .limit(1)
        )
        if sesion_activa is None:
            raise TokenRevocado("La sesión ya fue revocada.")

        return await self.resolver_principal_de_usuario(
            usuario,
            segundo_factor_cumplido=contenido.segundo_factor_cumplido,
        )

    async def cargar_usuario(self, usuario_id: uuid.UUID) -> Usuario | None:
        """Carga la fila de usuario.

        Existe para que las rutas no hagan SQL (CLAUDE.md, seccion 4): el
        endpoint de identidad necesita nombre y correo, que no viajan en el
        principal porque este solo lleva lo que hace falta para autorizar.
        """
        return (
            await self._sesion.execute(select(Usuario).where(Usuario.id == usuario_id))
        ).scalar_one_or_none()

    async def cambiar_contrasena(
        self, usuario_id: uuid.UUID, contrasena_actual: str, contrasena_nueva: str
    ) -> EntradaAuditoria:
        """Actualiza la contrasena y revoca todas las sesiones activas."""
        usuario = await self.cargar_usuario(usuario_id)
        if (
            usuario is None
            or not usuario.activo
            or not verificar_contrasena(contrasena_actual, usuario.hash_contrasena)
        ):
            raise CredencialesInvalidas("La contraseña actual no es correcta.")
        problemas = validar_politica_contrasena(contrasena_nueva)
        if problemas:
            raise DatosInvalidos(" ".join(problemas))
        if verificar_contrasena(contrasena_nueva, usuario.hash_contrasena):
            raise DatosInvalidos("La nueva contraseña debe ser distinta a la actual.")
        usuario.hash_contrasena = hashear_contrasena(contrasena_nueva)
        usuario.debe_cambiar_contrasena = False
        await self.revocar_todas_las_sesiones(usuario_id, motivo=MotivoRevocacion.CAMBIO_CONTRASENA)
        principal = await self.resolver_principal_de_usuario(usuario)
        return construir_entrada(
            accion=AccionAuditada.CONTRASENA_CAMBIADA,
            principal=principal,
            ahora=self._reloj.ahora(),
            entidad_tipo="usuario",
            entidad_id=usuario.id,
            sesiones_revocadas=True,
        )

    async def resolver_principal_por_id(self, usuario_id: uuid.UUID) -> Principal:
        usuario = (
            await self._sesion.execute(select(Usuario).where(Usuario.id == usuario_id))
        ).scalar_one_or_none()
        if usuario is None:
            # Principal minimo para poder auditar la accion de todas formas:
            # perder el registro por no encontrar al usuario seria peor.
            return Principal(
                actor_tipo=TipoActor.USUARIO,
                actor_id=usuario_id,
                clinica_id=None,
                permisos=frozenset(),
                ambito=Ambito(),
            )
        return await self.resolver_principal_de_usuario(usuario)

    async def resolver_principal_de_usuario(
        self, usuario: Usuario, *, segundo_factor_cumplido: bool = False
    ) -> Principal:
        """Carga permisos y ambito de un usuario.

        Es la consulta del camino caliente: se ejecuta en cada peticion
        autenticada.  Se resuelve en dos consultas -- permisos y ambitos --
        en lugar de una con varias uniones, porque una sola produciria el
        producto cartesiano de permisos por ambitos y multiplicaria las filas
        sin aportar nada.
        """
        ahora = self._reloj.ahora()
        hoy = ahora.date()

        # --- Roles vigentes ---
        consulta_roles = (
            select(UsuarioRol, Rol)
            .join(Rol, Rol.id == UsuarioRol.rol_id)
            .where(UsuarioRol.usuario_id == usuario.id)
        )
        asignaciones = (await self._sesion.execute(consulta_roles)).all()

        vigentes = [
            (usuario_rol, rol)
            for usuario_rol, rol in asignaciones
            if (usuario_rol.vigente_desde is None or usuario_rol.vigente_desde <= hoy)
            and (usuario_rol.vigente_hasta is None or usuario_rol.vigente_hasta >= hoy)
        ]

        perfil = await self._perfil_profesional_de(usuario.id)
        profesional_id = (
            perfil.id
            if perfil is not None
            and perfil.clinica_id == usuario.clinica_id
            and perfil.activo
            and perfil.anulado_en is None
            else None
        )

        if not vigentes:
            # Sin rol vigente no hay permisos.  Un usuario recien creado o con
            # el rol caducado no accede a nada, que es el lado seguro.
            return Principal(
                actor_tipo=TipoActor.USUARIO,
                actor_id=usuario.id,
                clinica_id=usuario.clinica_id,
                permisos=frozenset(),
                ambito=Ambito(clinica_id=usuario.clinica_id),
                segundo_factor_cumplido=segundo_factor_cumplido,
                requiere_segundo_factor=False,
                profesional_id=profesional_id,
                role_ids=frozenset(),
            )

        ids_rol = [rol.id for _, rol in vigentes]
        codigos_rol = frozenset(rol.codigo for _, rol in vigentes)

        # --- Permisos ---
        consulta_permisos = (
            select(Permiso.codigo)
            .join(RolPermiso, RolPermiso.permiso_id == Permiso.id)
            .where(RolPermiso.rol_id.in_(ids_rol))
        )
        permisos = frozenset((await self._sesion.execute(consulta_permisos)).scalars())
        if profesional_id is None and (perfil is not None or "profesional" in codigos_rol):
            # Un perfil desactivado o incoherente no se convierte en personal
            # clinico sin relacion asistencial al perder su identificador.
            permisos -= PERMISOS_SOLO_ASISTENCIALES | {
                "adherencia.leer",
                "alerta_adherencia.atender",
                "acceso_emergencia.solicitar",
            }

        # --- Ambito ---
        ids_usuario_rol = [ur.id for ur, _ in vigentes]
        consulta_ambitos = select(AmbitoAsignacion).where(
            AmbitoAsignacion.usuario_rol_id.in_(ids_usuario_rol)
        )
        ambitos = list((await self._sesion.execute(consulta_ambitos)).scalars())

        ambito = self._construir_ambito(ambitos, clinica_id=usuario.clinica_id)
        if (
            profesional_id is not None
            and perfil is not None
            and ("profesional" in codigos_rol or permisos & PERMISOS_SOLO_ASISTENCIALES)
            and not (codigos_rol & {"administrador_clinica", "superadministrador"})
        ):
            ambito = replace(
                ambito,
                todas_las_especialidades=False,
                especialidades=ambito.especialidades | {perfil.especialidad_id},
            )

        return Principal(
            actor_tipo=TipoActor.USUARIO,
            actor_id=usuario.id,
            clinica_id=usuario.clinica_id,
            permisos=permisos,
            ambito=ambito,
            segundo_factor_cumplido=segundo_factor_cumplido,
            requiere_segundo_factor=bool(codigos_rol & self._roles_con_2fa),
            roles=codigos_rol,
            role_ids=frozenset(ids_rol),
            # Sin esto, la comprobacion de relacion asistencial de la historia
            # clinica no se ejecuta nunca por HTTP.
            profesional_id=profesional_id,
            origen="API",
        )

    def _construir_ambito(
        self, asignaciones: list[AmbitoAsignacion], *, clinica_id: uuid.UUID
    ) -> Ambito:
        """Compone el ambito a partir de las filas de asignacion.

        Las exclusiones (`incluir=False`) se aplican DESPUES de las
        inclusiones y siempre ganan.  Es la semantica segura: ante reglas
        contradictorias -- «todas las sedes» mas «no la sede Norte» -- se
        deniega.

        Se acumula por tipo en diccionarios en lugar de con una cadena de
        ramas.  Anadir una dimension de ambito nueva pasa a ser una entrada
        mas en la tupla de dimensiones, sin tocar esta logica.
        """
        # Dimensiones que admiten comodin, inclusion y exclusion.
        dimensiones = (
            TipoAmbito.SEDE.value,
            TipoAmbito.ESPECIALIDAD.value,
            TipoAmbito.PROFESIONAL.value,
            TipoAmbito.PACIENTE.value,
        )
        incluidos: dict[str, set[uuid.UUID]] = {d: set() for d in dimensiones}
        excluidos: dict[str, set[uuid.UUID]] = {d: set() for d in dimensiones}
        comodin: dict[str, bool] = dict.fromkeys(dimensiones, False)
        nivel = NivelSensibilidad.ADMINISTRATIVO

        for asignacion in asignaciones:
            tipo = asignacion.tipo

            if tipo == TipoAmbito.TIPO_INFORMACION.value:
                if asignacion.incluir:
                    # Se toma el mayor nivel concedido entre todos los roles.
                    nivel = max(nivel, NivelSensibilidad.CLINICO, key=lambda n: n.orden)
                continue

            if tipo not in incluidos:
                # Tipo desconocido: se ignora en lugar de fallar.  Un valor
                # nuevo en la base de datos no debe impedir que el usuario
                # entre, y la restriccion CHECK de la tabla ya limita los
                # valores posibles.
                continue

            if asignacion.valor_id is None:
                if asignacion.incluir:
                    comodin[tipo] = True
                continue

            destino = incluidos if asignacion.incluir else excluidos
            destino[tipo].add(asignacion.valor_id)

        # Una exclusion desactiva el comodin de su dimension.
        #
        # «Todas las sedes menos la Norte» no se puede representar con un
        # booleano, asi que se degrada a la lista explicita de inclusiones.
        # Es mas restrictivo de lo que el administrador pidio -- puede quedar
        # vacio -- y por eso es el lado seguro: denegar de mas es preferible
        # a conceder de mas sobre datos clinicos.
        for dimension in dimensiones:
            if excluidos[dimension]:
                comodin[dimension] = False
                incluidos[dimension] -= excluidos[dimension]

        return Ambito(
            clinica_id=clinica_id,
            sedes=frozenset(incluidos[TipoAmbito.SEDE.value]),
            todas_las_sedes=comodin[TipoAmbito.SEDE.value],
            especialidades=frozenset(incluidos[TipoAmbito.ESPECIALIDAD.value]),
            todas_las_especialidades=comodin[TipoAmbito.ESPECIALIDAD.value],
            profesionales=frozenset(incluidos[TipoAmbito.PROFESIONAL.value]),
            todos_los_profesionales=comodin[TipoAmbito.PROFESIONAL.value],
            pacientes=frozenset(incluidos[TipoAmbito.PACIENTE.value]),
            todos_los_pacientes=comodin[TipoAmbito.PACIENTE.value],
            nivel_maximo=nivel,
        )

    # ==================================================================
    #  Auxiliares
    # ==================================================================
    async def _perfil_profesional_de(self, usuario_id: uuid.UUID) -> Profesional | None:
        """Profesional ligado a este usuario, si lo hay.

        Es lo que activa la comprobacion de **relacion asistencial** en la
        historia clinica: sin `profesional_id` en el principal, ese control no
        se ejecuta y cualquier usuario con el permiso leeria la historia de
        cualquier paciente.

        Un usuario sin profesional -- recepcion, administracion, auditoria --
        devuelve `None`, y entonces la relacion asistencial no aplica: su
        acceso se controla por permiso y por auditoria.
        """
        return (
            await self._sesion.execute(
                select(Profesional).where(
                    Profesional.usuario_id == usuario_id,
                )
            )
        ).scalar_one_or_none()

    async def _buscar_usuario(self, correo: str) -> Usuario | None:
        return (
            await self._sesion.execute(select(Usuario).where(func.lower(Usuario.correo) == correo))
        ).scalar_one_or_none()

    async def _exige_segundo_factor(self, usuario: Usuario) -> bool:
        consulta = (
            select(Rol.codigo)
            .join(UsuarioRol, UsuarioRol.rol_id == Rol.id)
            .where(UsuarioRol.usuario_id == usuario.id)
        )
        codigos = set((await self._sesion.execute(consulta)).scalars())
        return bool(codigos & self._roles_con_2fa)

    async def _emitir_tokens(
        self,
        usuario: Usuario,
        *,
        ahora: datetime,
        familia: str,
        segundo_factor_cumplido: bool,
        requiere_segundo_factor: bool,
        ip: str | None,
        agente_usuario: str | None,
        sesion_anterior_id: uuid.UUID | None,
    ) -> ParTokens:
        if not await self._clinica_habilitada(usuario):
            raise CredencialesInvalidas("La clínica no tiene acceso habilitado.")
        token_acceso, _ = crear_token_acceso(
            clave_secreta=self._clave,
            algoritmo=self._algoritmo,
            usuario_id=usuario.id,
            clinica_id=usuario.clinica_id,
            familia=familia,
            segundo_factor_cumplido=segundo_factor_cumplido,
            ahora=ahora,
            minutos=self._minutos_acceso,
        )
        token_refresco, jti_refresco = crear_token_refresco(
            clave_secreta=self._clave,
            algoritmo=self._algoritmo,
            usuario_id=usuario.id,
            clinica_id=usuario.clinica_id,
            familia=familia,
            ahora=ahora,
            dias=self._dias_refresco,
        )

        self._sesion.add(
            Sesion(
                usuario_id=usuario.id,
                jti_refresco_hash=hashear_jti(jti_refresco),
                familia=familia,
                sesion_anterior_id=sesion_anterior_id,
                ip=ip,
                agente_usuario=agente_usuario,
                segundo_factor_cumplido=segundo_factor_cumplido,
                creada_en=ahora,
                expira_en=ahora + timedelta(days=self._dias_refresco),
            )
        )

        return ParTokens(
            token_acceso=token_acceso,
            token_refresco=token_refresco,
            expira_en=ahora + timedelta(minutes=self._minutos_acceso),
            requiere_segundo_factor=requiere_segundo_factor and not segundo_factor_cumplido,
        )

    async def _revocar_familia(
        self, familia: str, *, motivo: MotivoRevocacion, ahora: datetime
    ) -> None:
        filas = (
            await self._sesion.execute(
                select(Sesion).where(Sesion.familia == familia, Sesion.revocada_en.is_(None))
            )
        ).scalars()
        for fila in filas:
            fila.revocada_en = ahora
            fila.motivo_revocacion = motivo.value

    def _registrar_acceso(
        self,
        correo: str,
        clinica_id: uuid.UUID | None,
        resultado: ResultadoAcceso,
        ip: str | None,
        agente_usuario: str | None,
        ahora: datetime,
        *,
        usuario_id: uuid.UUID | None = None,
    ) -> None:
        """Registra el intento.

        Se guarda el correo intentado aunque la cuenta no exista: saber que
        alguien probo cien correos distintos es informacion util para detectar
        un ataque.  La contrasena intentada NO se guarda bajo ninguna
        circunstancia.
        """
        self._sesion.add(
            HistorialAcceso(
                usuario_id=usuario_id,
                clinica_id=clinica_id,
                correo_intentado=correo,
                resultado=resultado.value,
                ip=ip,
                agente_usuario=agente_usuario,
                ocurrido_en=ahora,
            )
        )

    async def _clinica_habilitada(self, usuario: Usuario) -> bool:
        return bool(
            await self._sesion.scalar(
                select(Clinica.id).where(
                    Clinica.id == usuario.clinica_id,
                    Clinica.activa.is_(True),
                    Clinica.anulado_en.is_(None),
                )
            )
        )

    def _fallo_de_acceso(
        self,
        correo: str,
        clinica_id: uuid.UUID | None,
        resultado: ResultadoAcceso,
        ip: str | None,
        agente_usuario: str | None,
        ahora: datetime,
        *,
        usuario_id: uuid.UUID | None = None,
    ) -> ResultadoAutenticacion:
        """Registra el fallo y lanza el error generico.

        El mensaje es identico para correo inexistente, contrasena incorrecta y
        cuenta inactiva.  Distinguirlos permitiria enumerar las cuentas del
        personal de la clinica, y saber quien trabaja ahi ya es informacion
        util para un atacante.
        """
        self._registrar_acceso(
            correo, clinica_id, resultado, ip, agente_usuario, ahora, usuario_id=usuario_id
        )
        raise CredencialesInvalidas("Correo o contrasena incorrectos.")


# Hash de una contrasena aleatoria, usado para igualar el tiempo de respuesta
# cuando la cuenta no existe.  Sin esto, un correo inexistente responderia
# antes que uno real y el tiempo revelaria que cuentas existen.
#
# Se calcula una sola vez al importar el modulo: hacerlo en cada intento
# anadiria el coste sin aportar nada.
_HASH_SENUELO: str = hashear_contrasena(uuid.uuid4().hex + uuid.uuid4().hex)


__all__ = [
    "ParTokens",
    "ResultadoAutenticacion",
    "ServicioAutenticacion",
]
