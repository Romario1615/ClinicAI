"""Resolucion del dato de contacto del destinatario.

Se prueba contra la base real porque lo que resuelve es una lectura por clave
primaria sobre tres tablas distintas, y el caso que importa -- el destinatario
que existe pero no tiene dato de contacto para ese canal -- solo aparece con
filas de verdad.

La decision que se verifica aqui es que el telefono se busca **al entregar** y
no se copia al encolar: ver el encabezado de `app/mensajeria/destinatarios.py`.

La normalizacion del numero es una funcion pura y se prueba en
`pruebas/unitarias/test_normalizacion_telefono.py`.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.mensajeria.destinatarios import DestinatarioNoResoluble, ResolutorContacto
from app.modelos import Clinica, Paciente, Profesional, Usuario
from app.modulos.outbox.modelos import CanalOutbox

pytestmark = [pytest.mark.integracion, pytest.mark.asyncio]


@pytest.fixture
def resolutor(sesion: AsyncSession) -> ResolutorContacto:
    return ResolutorContacto(sesion)


@pytest_asyncio.fixture
async def paciente_completo(sesion: AsyncSession, clinica: Clinica, sufijo: str) -> Paciente:
    registro = Paciente(
        clinica_id=clinica.id,
        tipo_documento="CEDULA",
        numero_documento=f"3{sufijo[:9]}",
        # Nombre compuesto a proposito: el mensaje debe encabezar con el
        # primero, no con los cuatro.
        nombre="Maria Fernanda",
        apellido="De Prueba Ficticia",
        telefono_whatsapp="+593 99 900 0333",
        correo=f"paciente-{sufijo}@example.invalid",
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


# ---------------------------------------------------------------------------
#  Paciente
# ---------------------------------------------------------------------------
async def test_se_resuelve_el_whatsapp_del_paciente(
    resolutor: ResolutorContacto, paciente_completo: Paciente
) -> None:
    contacto = await resolutor.resolver(
        destino_tipo="PACIENTE", destino_id=paciente_completo.id, canal=CanalOutbox.WHATSAPP
    )
    assert contacto.valor == "593999000333"
    # Solo el primer nombre: «Hola Maria Fernanda De Prueba Ficticia» en una
    # pantalla de bloqueo identifica al destinatario ante quien pase al lado.
    assert contacto.nombre == "Maria"


async def test_se_resuelve_el_correo_del_paciente(
    resolutor: ResolutorContacto, paciente_completo: Paciente
) -> None:
    contacto = await resolutor.resolver(
        destino_tipo="PACIENTE", destino_id=paciente_completo.id, canal=CanalOutbox.CORREO
    )
    assert contacto.valor.endswith("@example.invalid")


async def test_un_paciente_sin_whatsapp_no_es_resoluble(
    resolutor: ResolutorContacto, paciente: Paciente
) -> None:
    """El paciente base de las fixtures no tiene telefono.

    El procesador lo marca FALLIDO: no mejora reintentando, alguien tiene que
    pedirle el numero.
    """
    with pytest.raises(DestinatarioNoResoluble, match="WhatsApp"):
        await resolutor.resolver(
            destino_tipo="PACIENTE", destino_id=paciente.id, canal=CanalOutbox.WHATSAPP
        )


async def test_un_paciente_sin_correo_no_es_resoluble(
    resolutor: ResolutorContacto, paciente: Paciente
) -> None:
    with pytest.raises(DestinatarioNoResoluble, match="correo"):
        await resolutor.resolver(
            destino_tipo="PACIENTE", destino_id=paciente.id, canal=CanalOutbox.CORREO
        )


async def test_el_canal_calendario_no_aplica_a_un_paciente(
    resolutor: ResolutorContacto, paciente_completo: Paciente
) -> None:
    """El calendario refleja la agenda del profesional, no la del paciente."""
    with pytest.raises(DestinatarioNoResoluble, match="no aplicable"):
        await resolutor.resolver(
            destino_tipo="PACIENTE",
            destino_id=paciente_completo.id,
            canal=CanalOutbox.CALENDARIO,
        )


async def test_un_paciente_que_no_existe_no_es_resoluble(
    resolutor: ResolutorContacto,
) -> None:
    with pytest.raises(DestinatarioNoResoluble, match="no existe"):
        await resolutor.resolver(
            destino_tipo="PACIENTE", destino_id=uuid.uuid4(), canal=CanalOutbox.WHATSAPP
        )


# ---------------------------------------------------------------------------
#  Profesional
# ---------------------------------------------------------------------------
async def test_se_resuelve_el_whatsapp_del_profesional(
    resolutor: ResolutorContacto, sesion: AsyncSession, profesional: Profesional
) -> None:
    """Camino del resumen diario y del aviso de cambio de agenda."""
    profesional.telefono_whatsapp = "+593999000444"
    await sesion.flush()

    contacto = await resolutor.resolver(
        destino_tipo="PROFESIONAL", destino_id=profesional.id, canal=CanalOutbox.WHATSAPP
    )
    assert contacto.valor == "593999000444"
    assert contacto.nombre == "Profesional"


async def test_se_resuelve_el_correo_del_profesional(
    resolutor: ResolutorContacto, sesion: AsyncSession, profesional: Profesional, sufijo: str
) -> None:
    profesional.correo_calendario = f"profesional-{sufijo}@example.invalid"
    await sesion.flush()

    contacto = await resolutor.resolver(
        destino_tipo="PROFESIONAL", destino_id=profesional.id, canal=CanalOutbox.CORREO
    )
    assert contacto.valor.endswith("@example.invalid")


async def test_un_profesional_sin_contacto_no_es_resoluble(
    resolutor: ResolutorContacto, profesional: Profesional
) -> None:
    with pytest.raises(DestinatarioNoResoluble):
        await resolutor.resolver(
            destino_tipo="PROFESIONAL", destino_id=profesional.id, canal=CanalOutbox.WHATSAPP
        )
    with pytest.raises(DestinatarioNoResoluble):
        await resolutor.resolver(
            destino_tipo="PROFESIONAL", destino_id=profesional.id, canal=CanalOutbox.CORREO
        )


async def test_un_profesional_que_no_existe_no_es_resoluble(
    resolutor: ResolutorContacto,
) -> None:
    with pytest.raises(DestinatarioNoResoluble, match="no existe"):
        await resolutor.resolver(
            destino_tipo="PROFESIONAL", destino_id=uuid.uuid4(), canal=CanalOutbox.CORREO
        )


# ---------------------------------------------------------------------------
#  Usuario
# ---------------------------------------------------------------------------
async def test_se_resuelve_el_correo_del_usuario(
    resolutor: ResolutorContacto, usuario: Usuario
) -> None:
    """Camino de la verificacion de correo y de la recuperacion de acceso.

    El correo de un usuario es obligatorio en el modelo, asi que este canal
    siempre resuelve.
    """
    contacto = await resolutor.resolver(
        destino_tipo="USUARIO", destino_id=usuario.id, canal=CanalOutbox.CORREO
    )
    assert contacto.valor == usuario.correo
    assert contacto.nombre == "Usuario"


async def test_se_resuelve_el_telefono_del_usuario(
    resolutor: ResolutorContacto, sesion: AsyncSession, usuario: Usuario
) -> None:
    usuario.telefono = "+593999000555"
    await sesion.flush()

    contacto = await resolutor.resolver(
        destino_tipo="USUARIO", destino_id=usuario.id, canal=CanalOutbox.WHATSAPP
    )
    assert contacto.valor == "593999000555"


async def test_un_usuario_sin_telefono_no_es_resoluble_por_whatsapp(
    resolutor: ResolutorContacto, usuario: Usuario
) -> None:
    with pytest.raises(DestinatarioNoResoluble, match="telefono"):
        await resolutor.resolver(
            destino_tipo="USUARIO", destino_id=usuario.id, canal=CanalOutbox.WHATSAPP
        )


async def test_el_canal_calendario_no_aplica_a_un_usuario(
    resolutor: ResolutorContacto, usuario: Usuario
) -> None:
    with pytest.raises(DestinatarioNoResoluble, match="no aplicable"):
        await resolutor.resolver(
            destino_tipo="USUARIO", destino_id=usuario.id, canal=CanalOutbox.CALENDARIO
        )


async def test_un_usuario_que_no_existe_no_es_resoluble(
    resolutor: ResolutorContacto,
) -> None:
    with pytest.raises(DestinatarioNoResoluble, match="no existe"):
        await resolutor.resolver(
            destino_tipo="USUARIO", destino_id=uuid.uuid4(), canal=CanalOutbox.CORREO
        )


# ---------------------------------------------------------------------------
#  Tipo desconocido
# ---------------------------------------------------------------------------
async def test_un_tipo_de_destinatario_desconocido_no_es_resoluble(
    resolutor: ResolutorContacto,
) -> None:
    """La tabla admite tambien 'CLINICA', que no tiene contacto propio.

    Falla de forma explicita en lugar de devolver una cadena vacia: enviar a
    un destino vacio produce un rechazo del proveedor que nadie sabe explicar.
    """
    with pytest.raises(DestinatarioNoResoluble, match="no soportado"):
        await resolutor.resolver(
            destino_tipo="CLINICA", destino_id=uuid.uuid4(), canal=CanalOutbox.CORREO
        )
