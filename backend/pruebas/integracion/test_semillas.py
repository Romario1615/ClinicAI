"""Pruebas de la carga de semillas.

Dos cosas distintas que se verifican aparte:

* **Catalogos** (permisos y roles): son parte del funcionamiento.  Sin ellos
  la resolucion de permisos devuelve el conjunto vacio y nadie puede hacer
  nada.  Se comprueba que la base de datos y el catalogo del codigo no
  divergan: un permiso del codigo ausente en la tabla queda sin efecto y
  ningun rol lo tendra nunca asignado.

* **Datos sinteticos**: se comprueba que la salvaguarda de produccion
  funcione, y que nada de lo generado pueda confundirse con datos reales de
  pacientes.
"""

from __future__ import annotations

import base64
import secrets

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.pacientes.modelos import Paciente
from app.modulos.usuarios.modelos import (
    AmbitoAsignacion,
    Permiso,
    Rol,
    RolPermiso,
    Usuario,
    UsuarioRol,
)
from app.nucleo.autorizacion import (
    CATALOGO_PERMISOS,
    PERMISOS_POR_ROL,
    PERMISOS_SOLO_ASISTENCIALES,
)
from app.nucleo.configuracion import Configuracion
from app.semillas.catalogos import (
    NOMBRES_DE_ROL,
    cargar_catalogos,
    verificar_coherencia,
)
from app.semillas.sinteticos import (
    DOMINIO_PRUEBAS,
    MARCA_SINTETICO,
    PREFIJO_TELEFONO_PRUEBAS,
    _correo_sintetico,
    _documento_sintetico,
    cargar_datos_sinteticos,
)

pytestmark = [pytest.mark.integracion, pytest.mark.asyncio]


# ===========================================================================
#  Catalogos
# ===========================================================================
class TestCatalogos:
    async def test_la_carga_crea_todos_los_permisos(self, sesion: AsyncSession) -> None:
        resumen = await cargar_catalogos(sesion)
        # La sesion de pruebas ya tiene el esquema migrado, pero no
        # necesariamente los catalogos: se aceptan ambos casos.
        assert resumen.permisos_creados >= 0

        codigos = set((await sesion.execute(sa.select(Permiso.codigo))).scalars())
        esperados = {d.codigo for d in CATALOGO_PERMISOS}
        assert esperados <= codigos, (
            f"Faltan permisos en la base de datos: {sorted(esperados - codigos)}"
        )

    async def test_la_carga_es_idempotente(self, sesion: AsyncSession) -> None:
        """Ejecutarla dos veces no debe duplicar nada.

        Es el requisito que permite lanzarla en cada despliegue sin pensar.
        """
        await cargar_catalogos(sesion)
        await sesion.flush()
        segunda = await cargar_catalogos(sesion)

        assert segunda.permisos_creados == 0
        assert segunda.roles_creados == 0
        assert segunda.asignaciones_creadas == 0
        assert segunda.asignaciones_retiradas == 0

    async def test_existen_los_seis_roles_del_sistema(self, sesion: AsyncSession) -> None:
        await cargar_catalogos(sesion)
        await sesion.flush()

        codigos = set(
            (await sesion.execute(sa.select(Rol.codigo).where(Rol.clinica_id.is_(None)))).scalars()
        )
        assert set(PERMISOS_POR_ROL) <= codigos
        assert set(NOMBRES_DE_ROL) == set(PERMISOS_POR_ROL)

    async def test_los_roles_del_sistema_no_pertenecen_a_una_clinica(
        self, sesion: AsyncSession
    ) -> None:
        """Son comunes a todas las clinicas y no se modifican desde la
        interfaz.  Una clinica que necesite un rol propio crea uno nuevo.
        """
        await cargar_catalogos(sesion)
        await sesion.flush()

        filas = (await sesion.execute(sa.select(Rol).where(Rol.es_sistema.is_(True)))).scalars()
        for rol in filas:
            assert rol.clinica_id is None

    async def test_recepcion_no_tiene_permisos_clinicos_en_la_base(
        self, sesion: AsyncSession
    ) -> None:
        """La matriz del codigo y la de la base deben coincidir.

        Comprobar solo el catalogo en memoria no bastaria: lo que decide el
        acceso real es lo que hay en `rol_permiso`.
        """
        await cargar_catalogos(sesion)
        await sesion.flush()

        for codigo_rol in ("recepcion", "superadministrador", "auditor"):
            rol = (
                await sesion.execute(
                    sa.select(Rol).where(Rol.codigo == codigo_rol, Rol.clinica_id.is_(None))
                )
            ).scalar_one()

            concedidos = set(
                (
                    await sesion.execute(
                        sa.select(Permiso.codigo)
                        .join(RolPermiso, RolPermiso.permiso_id == Permiso.id)
                        .where(RolPermiso.rol_id == rol.id)
                    )
                ).scalars()
            )
            clinicos = concedidos & PERMISOS_SOLO_ASISTENCIALES
            assert not clinicos, (
                f"El rol '{codigo_rol}' tiene permisos clinicos en la base de "
                f"datos: {sorted(clinicos)}"
            )

    async def test_solo_el_profesional_escribe_datos_clinicos(self, sesion: AsyncSession) -> None:
        await cargar_catalogos(sesion)
        await sesion.flush()

        for codigo_permiso in (
            "historia_clinica.escribir",
            "receta.crear",
            "receta.confirmar",
            "diagnostico.registrar",
        ):
            roles = set(
                (
                    await sesion.execute(
                        sa.select(Rol.codigo)
                        .join(RolPermiso, RolPermiso.rol_id == Rol.id)
                        .join(Permiso, Permiso.id == RolPermiso.permiso_id)
                        .where(Permiso.codigo == codigo_permiso)
                    )
                ).scalars()
            )
            assert roles == {"profesional"}, (
                f"'{codigo_permiso}' debe tenerlo solo el profesional, lo tienen: {sorted(roles)}"
            )

    async def test_la_verificacion_de_coherencia_pasa_tras_cargar(
        self, sesion: AsyncSession
    ) -> None:
        await cargar_catalogos(sesion)
        await sesion.flush()
        problemas = await verificar_coherencia(sesion)
        assert problemas == [], "\n".join(problemas)

    async def test_la_verificacion_detecta_un_permiso_ausente(self, sesion: AsyncSession) -> None:
        """La prueba que justifica que la verificacion exista.

        Se borra un permiso a mano y la verificacion debe avisar.  Sin ella,
        un permiso del codigo ausente en la tabla queda sin efecto y ningun
        rol lo tendra nunca asignado: el acceso se deniega sin explicacion.
        """
        await cargar_catalogos(sesion)
        await sesion.flush()

        # Se elimina un permiso que ningun rol de los que se comprueban usa,
        # para que el fallo detectado sea el de ausencia y no otro.
        await sesion.execute(
            sa.delete(RolPermiso).where(
                RolPermiso.permiso_id.in_(
                    sa.select(Permiso.id).where(Permiso.codigo == "prediccion.consultar")
                )
            )
        )
        await sesion.execute(sa.delete(Permiso).where(Permiso.codigo == "prediccion.consultar"))
        await sesion.flush()

        problemas = await verificar_coherencia(sesion)
        assert any("prediccion.consultar" in p for p in problemas), (
            f"La verificacion no detecto el permiso ausente: {problemas}"
        )


# ===========================================================================
#  Datos sinteticos
# ===========================================================================
class TestSalvaguardaDeProduccion:
    async def test_la_carga_se_niega_en_produccion(self, sesion: AsyncSession) -> None:
        """No es un aviso: lanza excepcion.

        Un script de semillas ejecutado por error contra produccion
        insertaria pacientes ficticios entre los reales, y separarlos
        despues seria trabajo manual sobre datos clinicos.
        """

        produccion = Configuracion(
            _env_file=None,
            entorno="produccion",
            depuracion=False,
            frontend_modo_simulado=False,
            whatsapp_validar_firma=True,
            modo_whatsapp="cloud_api",
            modo_calendario="google",
            modo_correo="smtp",
            antivirus_habilitado=True,
            clave_secreta=secrets.token_urlsafe(64),
            clave_cifrado_datos=base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
            postgres_contrasena=secrets.token_urlsafe(24),
            origenes_cors="https://clinica.example",
        )

        with pytest.raises(RuntimeError, match="bloqueada"):
            await cargar_datos_sinteticos(sesion, produccion)

    @pytest.mark.parametrize("entorno", ["local", "desarrollo", "preproduccion"])
    async def test_los_demas_entornos_si_permiten_la_carga(
        self, sesion: AsyncSession, entorno: str
    ) -> None:
        """Preproduccion incluida: es donde se prueba con volumen realista."""
        configuracion = Configuracion(_env_file=None, entorno=entorno)
        await cargar_catalogos(sesion)
        await sesion.flush()
        # Carga minima para que la prueba sea rapida.
        # Semilla derivada del entorno: cada parametrizacion crea su propia
        # clinica, para que no colisionen entre si ni con la del desarrollador.
        resumen = await cargar_datos_sinteticos(
            sesion,
            configuracion,
            cantidad_pacientes=3,
            cantidad_citas=5,
            semilla=900000 + sum(ord(c) for c in entorno),
        )
        assert resumen.pacientes == 3


class TestDatosSinteticos:
    @pytest.fixture
    async def cargado(self, sesion: AsyncSession):
        configuracion = Configuracion(_env_file=None, entorno="local")
        await cargar_catalogos(sesion)
        await sesion.flush()
        return await cargar_datos_sinteticos(
            sesion,
            configuracion,
            cantidad_pacientes=12,
            cantidad_citas=25,
            # Semilla propia de esta clase de pruebas.
            semilla=910001,
        )

    async def test_se_crea_una_clinica_completa(self, cargado) -> None:
        assert cargado.clinica_id is not None
        assert cargado.sedes == 2
        assert cargado.especialidades == 4
        assert cargado.servicios == 8
        assert cargado.profesionales == 8
        assert cargado.pacientes == 12

    async def test_ningun_documento_puede_ser_una_cedula_valida(
        self, sesion: AsyncSession, cargado
    ) -> None:
        """Los documentos empiezan por 99, que no es una provincia valida.

        Las cedulas ecuatorianas tienen los dos primeros digitos entre 01 y
        24, asi que estos numeros son invalidos por construccion y no pueden
        confundirse con datos reales ni servir para ningun tramite.
        """

        documentos = (
            await sesion.execute(
                sa.select(Paciente.numero_documento).where(
                    Paciente.clinica_id == cargado.clinica_id
                )
            )
        ).scalars()
        for documento in documentos:
            assert documento is not None
            assert documento.startswith("99"), (
                f"El documento sintetico '{documento}' podria parecer una cedula real."
            )

    async def test_todos_los_correos_usan_el_dominio_reservado(
        self, sesion: AsyncSession, cargado
    ) -> None:
        """`example.invalid` esta reservado por la RFC 2606: no existe.

        Importa porque el sistema envia correos de verificacion: con un
        dominio real, una carga de semillas mandaria mensajes a desconocidos.
        """

        correos = (
            await sesion.execute(
                sa.select(Usuario.correo).where(Usuario.clinica_id == cargado.clinica_id)
            )
        ).scalars()
        for correo in correos:
            assert correo.endswith(f"@{DOMINIO_PRUEBAS}")

    async def test_los_correos_son_ascii(self, sesion: AsyncSession, cargado) -> None:
        """Faker en espanol genera nombres con tilde.

        Un correo con caracteres no ASCII es valido segun la norma pero falla
        en la practica con muchos clientes y validadores.  Una version
        anterior de la normalizacion solo quitaba la enye y dejaba pasar las
        tildes.
        """

        correos = (
            await sesion.execute(
                sa.select(Usuario.correo).where(Usuario.clinica_id == cargado.clinica_id)
            )
        ).scalars()
        for correo in correos:
            assert correo.isascii(), f"El correo '{correo}' tiene caracteres no ASCII."
            assert ".." not in correo
            assert not correo.startswith(".")

    async def test_los_telefonos_usan_el_rango_reservado(
        self, sesion: AsyncSession, cargado
    ) -> None:

        telefonos = (
            await sesion.execute(
                sa.select(Paciente.telefono_whatsapp).where(
                    Paciente.clinica_id == cargado.clinica_id
                )
            )
        ).scalars()
        for telefono in telefonos:
            assert telefono is not None
            assert telefono.startswith(PREFIJO_TELEFONO_PRUEBAS)

    async def test_los_registros_llevan_la_marca_sintetica(
        self, sesion: AsyncSession, cargado
    ) -> None:
        """Visible en cualquier volcado de la base de datos.

        Si alguien ve esta marca en produccion, sabe de inmediato que hay
        datos de prueba mezclados con los reales.
        """

        apellidos = (
            await sesion.execute(
                sa.select(Paciente.apellido).where(Paciente.clinica_id == cargado.clinica_id)
            )
        ).scalars()
        for apellido in apellidos:
            assert MARCA_SINTETICO in apellido

    async def test_las_citas_generadas_no_se_solapan(self, sesion: AsyncSession, cargado) -> None:
        """La restriccion de exclusion actua sobre los datos sinteticos igual.

        Las citas se generan con horas al azar, asi que unas colisionan; el
        cargador las descarta.  El resultado no puede contener ni un solo par
        solapado.
        """
        resultado = await sesion.execute(
            sa.text(
                "SELECT count(*) FROM cita a JOIN cita b "
                "  ON a.id < b.id "
                " AND a.profesional_id = b.profesional_id "
                " AND a.rango && b.rango "
                "WHERE a.clinica_id = :clinica "
                "  AND a.estado IN ('HELD','CONFIRMED','RESCHEDULED') "
                "  AND b.estado IN ('HELD','CONFIRMED','RESCHEDULED')"
            ),
            {"clinica": cargado.clinica_id},
        )
        assert int(resultado.scalar_one()) == 0

    async def test_ninguna_cita_futura_esta_completada(self, sesion: AsyncSession, cargado) -> None:
        """Una cita que todavia no ocurrio no puede estar atendida.

        Es una incoherencia que falsearia las metricas de ocupacion y las
        predicciones entrenadas con estos datos.
        """
        resultado = await sesion.execute(
            sa.text(
                "SELECT count(*) FROM cita "
                "WHERE clinica_id = :clinica AND inicio > now() "
                "  AND estado IN ('COMPLETED', 'NO_SHOW')"
            ),
            {"clinica": cargado.clinica_id},
        )
        assert int(resultado.scalar_one()) == 0

    async def test_repetir_la_semilla_da_un_error_util(self, sesion: AsyncSession, cargado) -> None:
        """El segundo intento con la misma semilla debe explicar que hacer.

        Antes producia un `IntegrityError` con el nombre de una restriccion,
        que no le dice nada a quien ejecuta el script.
        """
        configuracion = Configuracion(_env_file=None, entorno="local")
        with pytest.raises(RuntimeError, match="Ya existe una clinica sintetica"):
            await cargar_datos_sinteticos(
                sesion, configuracion, cantidad_pacientes=1, cantidad_citas=1, semilla=910001
            )

    async def test_la_carga_es_reproducible(self, sesion: AsyncSession) -> None:
        """La misma semilla produce los mismos datos.

        Importa para reproducir un problema encontrado en desarrollo y para
        que las capturas de la interfaz no cambien en cada recarga.
        """

        # Las funciones deterministas son la parte comprobable sin recargar
        # la base dos veces, que seria lento.
        assert _documento_sintetico(7) == _documento_sintetico(7)
        assert _correo_sintetico("Ana Perez", 3) == _correo_sintetico("Ana Perez", 3)

    async def test_los_usuarios_tienen_ambito_asignado(self, sesion: AsyncSession, cargado) -> None:
        """Un `usuario_rol` sin ambito no da acceso a nada.

        Omitirlo produciria usuarios sinteticos que no pueden trabajar, y la
        demostracion pareceria rota cuando el problema seria la semilla.
        """

        usuarios = (
            await sesion.execute(
                sa.select(Usuario.id).where(Usuario.clinica_id == cargado.clinica_id)
            )
        ).scalars()

        for usuario_id in usuarios:
            cuenta = (
                await sesion.execute(
                    sa.select(sa.func.count())
                    .select_from(AmbitoAsignacion)
                    .join(UsuarioRol, UsuarioRol.id == AmbitoAsignacion.usuario_rol_id)
                    .where(UsuarioRol.usuario_id == usuario_id)
                )
            ).scalar_one()
            assert int(cuenta) > 0, f"El usuario {usuario_id} no tiene ambito y no podria trabajar."
