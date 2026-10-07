"""Servicio de imagenes de paciente.

Flujo de una subida
-------------------
1. Permiso y alcance (perfil: administrativo; clinica: permiso propio,
   ambito y relacion asistencial).
2. Saneado: tamano, tipo real, metadatos fuera, antivirus.
3. Fila en la base con un identificador generado aqui, porque el cifrado se
   liga a el (`contexto`) y tiene que conocerse antes de subir el objeto.
4. Objeto cifrado al almacen. Si el almacen falla, la transaccion se deshace:
   no queda una fila apuntando a un objeto inexistente.

El orden inverso (objeto primero) dejaria objetos huerfanos cuando falla la
base; este deja, en el peor caso, un objeto cifrado sin fila si falla el
`commit` final. Es el fallo menos danino: no se ve, no se descifra sin la
fila y no rompe ninguna pantalla.

Descargas
---------
Siempre por el API. Cada descarga de una imagen clinica deja su entrada de
auditoria, que es la unica forma de responder «quien vio esta radiografia».
La foto de perfil no se audita en cada visualizacion: es N1, aparece en
listados y auditar cada miniatura enterraria los accesos que importan.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita
from app.modulos.imagenes.modelos import ImagenPaciente, TipoImagen
from app.modulos.odontologia.vocabulario import es_pieza_valida
from app.modulos.pacientes.acceso_clinico import GuardiaClinica
from app.nucleo.almacen import AlmacenObjetos, ErrorAlmacen
from app.nucleo.archivos import sanear_imagen
from app.nucleo.auditoria import AccionAuditada, EntradaAuditoria, construir_entrada
from app.nucleo.autorizacion import NivelSensibilidad, Principal
from app.nucleo.configuracion import Configuracion
from app.nucleo.errores import (
    DatosInvalidos,
    PermisoDenegado,
    ProveedorExternoNoDisponible,
    RecursoNoEncontrado,
)
from app.nucleo.reloj import Reloj
from app.nucleo.seguridad import CifradorDatos

PERMISO_LEER_CLINICA = "imagen_clinica.leer"
PERMISO_CARGAR_CLINICA = "imagen_clinica.cargar"
PERMISO_LEER_PERFIL = "paciente.leer_administrativo"
PERMISO_CAMBIAR_PERFIL = "paciente.editar"
MAXIMO_LISTADO = 200


@dataclass(frozen=True, slots=True)
class DatosSubida:
    paciente_id: uuid.UUID
    tipo: TipoImagen
    contenido: bytes
    piezas: tuple[int, ...] = ()
    tomada_en: date | None = None
    descripcion: str | None = None
    cita_id: uuid.UUID | None = None
    procedimiento_id: uuid.UUID | None = None
    nivel_sensibilidad: str = "N2"


@dataclass(frozen=True, slots=True)
class Descarga:
    imagen: ImagenPaciente
    datos: bytes


class ServicioImagenes:
    def __init__(
        self,
        sesion: AsyncSession,
        reloj: Reloj,
        almacen: AlmacenObjetos,
        cifrador: CifradorDatos,
        configuracion: Configuracion,
    ) -> None:
        self._sesion = sesion
        self._reloj = reloj
        self._almacen = almacen
        self._cifrador = cifrador
        self._configuracion = configuracion
        self._guardia = GuardiaClinica(sesion)

    # ------------------------------------------------------------------
    #  Alcance
    # ------------------------------------------------------------------
    async def _alcance(
        self, principal: Principal, paciente_id: uuid.UUID, tipo: TipoImagen, *, escribir: bool
    ) -> None:
        if tipo.es_clinica:
            permiso = PERMISO_CARGAR_CLINICA if escribir else PERMISO_LEER_CLINICA
            await self._guardia.acceso_clinico(principal, paciente_id, permiso, self._reloj.ahora())
            return
        permiso = PERMISO_CAMBIAR_PERFIL if escribir else PERMISO_LEER_PERFIL
        self._guardia.exigir(principal, permiso)
        await self._guardia.paciente(principal, paciente_id)

    # ------------------------------------------------------------------
    #  Subida
    # ------------------------------------------------------------------
    async def subir(
        self, datos: DatosSubida, *, principal: Principal
    ) -> tuple[ImagenPaciente, tuple[EntradaAuditoria, ...]]:
        await self._alcance(principal, datos.paciente_id, datos.tipo, escribir=True)
        if datos.tipo.es_clinica:
            nivel = NivelSensibilidad(datos.nivel_sensibilidad)
            if nivel not in {NivelSensibilidad.CLINICO, NivelSensibilidad.CLINICO_SENSIBLE}:
                raise DatosInvalidos("Una imagen clínica debe ser N2 o N3.")
            if nivel == NivelSensibilidad.CLINICO_SENSIBLE and not principal.tiene_permiso(
                "historia_clinica.leer_sensible"
            ):
                raise PermisoDenegado("Se requiere permiso clínico sensible para registrar N3.")
        else:
            nivel = NivelSensibilidad.ADMINISTRATIVO

        if datos.cita_id is not None:
            cita = (
                await self._sesion.execute(
                    select(Cita.id).where(
                        Cita.id == datos.cita_id,
                        Cita.paciente_id == datos.paciente_id,
                        Cita.clinica_id == principal.clinica_id,
                    )
                )
            ).scalar_one_or_none()
            if cita is None:
                raise RecursoNoEncontrado("La cita solicitada no existe para este paciente.")

        piezas = tuple(sorted(set(datos.piezas)))
        invalidas = [pieza for pieza in piezas if not es_pieza_valida(pieza)]
        if invalidas:
            raise DatosInvalidos(f"Piezas dentales no validas (FDI): {invalidas}.")
        if datos.tipo is TipoImagen.PERFIL and piezas:
            raise DatosInvalidos("La foto de perfil no se asocia a piezas dentales.")

        if datos.procedimiento_id is not None:
            await self._exigir_procedimiento_del_paciente(
                datos.procedimiento_id, datos.paciente_id, principal
            )

        saneada = await sanear_imagen(datos.contenido, self._configuracion)
        ahora = self._reloj.ahora()
        identificador = uuid.uuid4()
        clave = f"{principal.clinica_id}/{datos.paciente_id}/{identificador}"

        imagen = ImagenPaciente(
            id=identificador,
            clinica_id=principal.clinica_id,
            paciente_id=datos.paciente_id,
            tipo=datos.tipo.value,
            nivel_sensibilidad=nivel.value,
            piezas=list(piezas),
            tomada_en=datos.tomada_en,
            descripcion=(datos.descripcion or "").strip() or None,
            cita_id=datos.cita_id,
            procedimiento_id=datos.procedimiento_id,
            profesional_id=principal.profesional_id,
            tipo_mime=saneada.tipo_mime,
            tamano_bytes=len(saneada.datos),
            sha256=saneada.sha256,
            clave_objeto=clave,
            antivirus=saneada.antivirus.value,
            creado_por=principal.actor_id,
        )
        self._sesion.add(imagen)
        await self._sesion.flush()

        cifrado = self._cifrador.cifrar_bytes(saneada.datos, contexto=identificador.bytes)
        try:
            await self._almacen.guardar(clave, cifrado)
        except (ErrorAlmacen, OSError) as exc:
            await self._sesion.rollback()
            raise ProveedorExternoNoDisponible(
                "No se pudo guardar la imagen. Intentelo de nuevo en unos minutos."
            ) from exc

        accion = (
            AccionAuditada.IMAGEN_CARGADA
            if datos.tipo.es_clinica
            else AccionAuditada.FOTO_PERFIL_ACTUALIZADA
        )
        entrada = construir_entrada(
            accion=accion,
            principal=principal,
            ahora=ahora,
            entidad_tipo="imagen_paciente",
            entidad_id=identificador,
            paciente_id=datos.paciente_id,
            nivel_sensibilidad=NivelSensibilidad(imagen.nivel_sensibilidad),
            tipo_imagen=datos.tipo.value,
            tamano_bytes=imagen.tamano_bytes,
            antivirus=saneada.antivirus.value,
        )
        return imagen, (entrada,)

    # ------------------------------------------------------------------
    #  Lectura
    # ------------------------------------------------------------------
    async def listar_clinicas(
        self,
        paciente_id: uuid.UUID,
        *,
        principal: Principal,
        tipo: TipoImagen | None = None,
        pieza: int | None = None,
        procedimiento_id: uuid.UUID | None = None,
    ) -> tuple[list[ImagenPaciente], tuple[EntradaAuditoria, ...]]:
        """Metadatos de las imagenes clinicas. Ver la galeria ya es un acceso."""
        await self._guardia.acceso_clinico(
            principal, paciente_id, PERMISO_LEER_CLINICA, self._reloj.ahora()
        )
        consulta = select(ImagenPaciente).where(
            ImagenPaciente.paciente_id == paciente_id,
            ImagenPaciente.clinica_id == principal.clinica_id,
            ImagenPaciente.tipo != TipoImagen.PERFIL.value,
            ImagenPaciente.anulado_en.is_(None),
        )
        if not principal.tiene_permiso("historia_clinica.leer_sensible"):
            consulta = consulta.where(ImagenPaciente.nivel_sensibilidad != "N3")
        if tipo is not None:
            consulta = consulta.where(ImagenPaciente.tipo == tipo.value)
        if procedimiento_id is not None:
            consulta = consulta.where(ImagenPaciente.procedimiento_id == procedimiento_id)
        if pieza is not None:
            # `= ANY(piezas)`: el indice es la pieza FDI, no una condicion booleana.
            consulta = consulta.where(literal(pieza) == func.any(ImagenPaciente.piezas))
        consulta = consulta.order_by(
            ImagenPaciente.tomada_en.desc().nulls_last(), ImagenPaciente.creado_en.desc()
        ).limit(MAXIMO_LISTADO)
        imagenes = list((await self._sesion.execute(consulta)).scalars())

        entrada = construir_entrada(
            accion=AccionAuditada.IMAGEN_CONSULTADA,
            principal=principal,
            ahora=self._reloj.ahora(),
            entidad_tipo="paciente",
            entidad_id=paciente_id,
            paciente_id=paciente_id,
            nivel_sensibilidad=(
                NivelSensibilidad.CLINICO_SENSIBLE
                if any(
                    imagen.nivel_sensibilidad == NivelSensibilidad.CLINICO_SENSIBLE.value
                    for imagen in imagenes
                )
                else NivelSensibilidad.CLINICO
            ),
            operacion="listado",
            imagenes_devueltas=len(imagenes),
        )
        return imagenes, (entrada,)

    async def foto_perfil(
        self, paciente_id: uuid.UUID, *, principal: Principal
    ) -> ImagenPaciente | None:
        await self._alcance(principal, paciente_id, TipoImagen.PERFIL, escribir=False)
        consulta = (
            select(ImagenPaciente)
            .where(
                ImagenPaciente.paciente_id == paciente_id,
                ImagenPaciente.clinica_id == principal.clinica_id,
                ImagenPaciente.tipo == TipoImagen.PERFIL.value,
                ImagenPaciente.anulado_en.is_(None),
            )
            .order_by(ImagenPaciente.creado_en.desc())
            .limit(1)
        )
        return (await self._sesion.execute(consulta)).scalar_one_or_none()

    async def _exigir_procedimiento_del_paciente(
        self, procedimiento_id: uuid.UUID, paciente_id: uuid.UUID, principal: Principal
    ) -> None:
        """La foto solo se liga a un procedimiento de un plan de ESE paciente."""
        from app.modulos.odontologia.modelos import (  # noqa: PLC0415 - evita ciclo de imports
            PlanTratamiento,
            ProcedimientoPlan,
        )

        consulta = (
            select(ProcedimientoPlan.id)
            .join(PlanTratamiento, PlanTratamiento.id == ProcedimientoPlan.plan_id)
            .where(
                ProcedimientoPlan.id == procedimiento_id,
                PlanTratamiento.paciente_id == paciente_id,
                PlanTratamiento.clinica_id == principal.clinica_id,
            )
        )
        if not principal.tiene_permiso("historia_clinica.leer_sensible"):
            consulta = consulta.where(PlanTratamiento.nivel_sensibilidad != "N3")
        encontrado = (await self._sesion.execute(consulta)).scalar_one_or_none()
        if encontrado is None:
            raise RecursoNoEncontrado("El procedimiento indicado no existe para este paciente.")

    async def _obtener(self, imagen_id: uuid.UUID, principal: Principal) -> ImagenPaciente:
        consulta = select(ImagenPaciente).where(
            ImagenPaciente.id == imagen_id,
            ImagenPaciente.clinica_id == principal.clinica_id,
        )
        if not principal.tiene_permiso("historia_clinica.leer_sensible"):
            consulta = consulta.where(ImagenPaciente.nivel_sensibilidad != "N3")
        imagen = (await self._sesion.execute(consulta)).scalar_one_or_none()
        if imagen is None:
            raise RecursoNoEncontrado("La imagen solicitada no existe.")
        return imagen

    async def descargar(
        self, imagen_id: uuid.UUID, *, principal: Principal
    ) -> tuple[Descarga, tuple[EntradaAuditoria, ...]]:
        imagen = await self._obtener(imagen_id, principal)
        tipo = TipoImagen(imagen.tipo)
        # El alcance se comprueba con el paciente REAL de la imagen, no con
        # uno que venga en la peticion: es lo que cierra el IDOR.
        await self._alcance(principal, imagen.paciente_id, tipo, escribir=False)
        if imagen.esta_anulado:
            raise RecursoNoEncontrado("La imagen solicitada no existe.")

        try:
            cifrado = await self._almacen.leer(imagen.clave_objeto)
        except (ErrorAlmacen, OSError) as exc:
            raise ProveedorExternoNoDisponible(
                "La imagen no esta disponible en este momento."
            ) from exc
        datos = self._cifrador.descifrar_bytes(cifrado, contexto=imagen.id.bytes)

        auditoria: tuple[EntradaAuditoria, ...] = ()
        if tipo.es_clinica:
            auditoria = (
                construir_entrada(
                    accion=AccionAuditada.IMAGEN_CONSULTADA,
                    principal=principal,
                    ahora=self._reloj.ahora(),
                    entidad_tipo="imagen_paciente",
                    entidad_id=imagen.id,
                    paciente_id=imagen.paciente_id,
                    nivel_sensibilidad=NivelSensibilidad(imagen.nivel_sensibilidad),
                    operacion="descarga",
                ),
            )
        return Descarga(imagen=imagen, datos=datos), auditoria

    # ------------------------------------------------------------------
    #  Anulacion
    # ------------------------------------------------------------------
    async def anular(
        self, imagen_id: uuid.UUID, motivo: str, *, principal: Principal
    ) -> tuple[ImagenPaciente, tuple[EntradaAuditoria, ...]]:
        """Retira una imagen de la vista. No borra el objeto ni la fila."""
        motivo_limpio = motivo.strip()
        if len(motivo_limpio) < 5:  # noqa: PLR2004
            raise DatosInvalidos("Indique el motivo de la anulacion.")
        imagen = await self._obtener(imagen_id, principal)
        await self._alcance(principal, imagen.paciente_id, TipoImagen(imagen.tipo), escribir=True)
        if imagen.esta_anulado:
            raise RecursoNoEncontrado("La imagen solicitada no existe.")

        ahora = self._reloj.ahora()
        imagen.anulado_en = ahora
        imagen.anulado_por = principal.actor_id
        imagen.motivo_anulacion = motivo_limpio
        await self._sesion.flush()

        entrada = construir_entrada(
            accion=AccionAuditada.IMAGEN_ANULADA,
            principal=principal,
            ahora=ahora,
            entidad_tipo="imagen_paciente",
            entidad_id=imagen.id,
            paciente_id=imagen.paciente_id,
            nivel_sensibilidad=NivelSensibilidad(imagen.nivel_sensibilidad),
            motivo=motivo_limpio,
        )
        return imagen, (entrada,)


__all__ = ["DatosSubida", "Descarga", "ServicioImagenes"]
