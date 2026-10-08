from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.historia.especialidades import especialidades_permitidas
from app.modulos.imagenes.adjuntos_modelos import FotoRegistro
from app.modulos.imagenes.adjuntos_repositorio import DESTINOS, RepositorioFotosRegistro
from app.modulos.pacientes.acceso_clinico import GuardiaClinica
from app.nucleo.almacen import AlmacenObjetos, ErrorAlmacen
from app.nucleo.archivos import sanear_imagen
from app.nucleo.autorizacion import NivelSensibilidad, Principal
from app.nucleo.configuracion import Configuracion
from app.nucleo.errores import (
    ConflictoEstado,
    DatosInvalidos,
    PermisoDenegado,
    ProveedorExternoNoDisponible,
    RecursoNoEncontrado,
)
from app.nucleo.reloj import Reloj
from app.nucleo.seguridad import CifradorDatos

MAX_FOTOS = 20


class ServicioFotosRegistro:
    @staticmethod
    def niveles_permitidos(principal: Principal, tipo: str) -> tuple[str, ...]:
        # Las imágenes asistenciales siguen la sensibilidad de la historia:
        # permiso clínico y permiso adicional N3. El nivel del ámbito RAG
        # conserva su control independiente para documentos de conocimiento.
        if DESTINOS[tipo].clinico:
            return (
                ("N2", "N3")
                if principal.tiene_permiso("historia_clinica.leer_sensible")
                else ("N2",)
            )
        return tuple(n.value for n in NivelSensibilidad if principal.ambito.cubre_nivel(n))

    def __init__(self, sesion: AsyncSession, reloj: Reloj):
        self.sesion, self.reloj = sesion, reloj
        self.repo = RepositorioFotosRegistro(sesion, reloj.ahora())

    async def acceso(
        self, principal: Principal, tipo: str, id_registro: uuid.UUID, escribir: bool = False
    ) -> Any:
        destino = DESTINOS.get(tipo)
        if destino is None:
            raise RecursoNoEncontrado("Este tipo de registro no admite fotografías.")
        permisos = destino.escribir if escribir else destino.leer
        if principal.es_agente or not any(principal.tiene_permiso(p) for p in permisos):
            raise PermisoDenegado("No tiene permiso para las fotos de este registro.")
        fila = await self.repo.destino(tipo, id_registro, principal, bloquear=escribir)
        if fila is None:
            raise RecursoNoEncontrado("El registro no está disponible.")
        if destino.clinico:
            permiso = "imagen_clinica.cargar" if escribir else "imagen_clinica.leer"
            await GuardiaClinica(self.sesion).acceso_clinico(
                principal, fila.paciente_id, permiso, self.reloj.ahora()
            )
            especialidades = await especialidades_permitidas(self.sesion, principal)
            if not any("imagenes" in modulos for _, modulos, _ in especialidades):
                raise PermisoDenegado("Las imágenes no están habilitadas para su especialidad.")
            if destino.modulo and not any(
                destino.modulo in modulos for _, modulos, _ in especialidades
            ):
                raise PermisoDenegado("La herramienta no pertenece a su especialidad.")
            if tipo == "registro" and not any(
                e.id == fila.especialidad_id
                and (fila.tipo != "FACIOGRAMA" or "faciograma" in modulos)
                for e, modulos, _ in especialidades
            ):
                raise RecursoNoEncontrado("La especialidad del registro no está disponible.")
            if escribir and fila.profesional_id != principal.profesional_id:
                raise PermisoDenegado("Solo el autor adjunta fotografías a su registro.")
        if escribir and (
            getattr(fila, "anulado", False)
            or getattr(fila, "anulado_en", None) is not None
            or getattr(fila, "vigente", True) is False
        ):
            raise ConflictoEstado("El registro está anulado o es una versión histórica.")
        if (
            escribir
            and tipo == "periodontograma"
            and not await self.repo.periodontograma_vigente(fila)
        ):
            raise ConflictoEstado("Adjunte las fotografías a la versión vigente del control.")
        return fila

    async def subir(
        self,
        principal: Principal,
        tipo: str,
        id_registro: uuid.UUID,
        id_foto: uuid.UUID,
        contenido: bytes,
        descripcion: str | None,
        configuracion: Configuracion,
        almacen: AlmacenObjetos,
        cifrador: CifradorDatos,
    ) -> FotoRegistro:
        destino = await self.acceso(principal, tipo, id_registro, True)
        clinica_id = self.clinica_destino(tipo, destino)
        saneada = await sanear_imagen(contenido, configuracion)
        repetido = await self.repo.por_id(id_foto)
        if repetido:
            if (
                repetido.clinica_id != clinica_id
                or repetido.tipo_registro != tipo
                or repetido.registro_id != id_registro
                or repetido.creado_por != principal.actor_id
                or repetido.sha256 != saneada.sha256
                or repetido.descripcion != descripcion
                or repetido.anulado_en is not None
            ):
                raise ConflictoEstado("La clave de fotografía ya se utilizó.")
            return repetido
        if len(await self.repo.listar(tipo, id_registro, clinica_id)) >= MAX_FOTOS:
            raise DatosInvalidos("El registro admite hasta veinte fotografías vigentes.")
        nivel = getattr(destino, "nivel_sensibilidad", "N2" if DESTINOS[tipo].clinico else "N1")
        if tipo == "conocimiento":
            nivel = destino.sensitivity_level
        if tipo == "formulario033":
            nivel = "N3"
        if tipo == "anamnesis":
            nivel = await self.repo.nivel_anamnesis(destino.plantilla_id)
        clave = f"{clinica_id}/registros/{tipo}/{id_registro}/{id_foto}"
        fila = FotoRegistro(
            id=id_foto,
            clinica_id=clinica_id,
            tipo_registro=tipo,
            registro_id=id_registro,
            paciente_id=getattr(destino, "paciente_id", None) if DESTINOS[tipo].clinico else None,
            nivel_sensibilidad=nivel,
            clave_objeto=clave,
            tipo_mime=saneada.tipo_mime,
            tamano_bytes=len(saneada.datos),
            sha256=saneada.sha256,
            descripcion=descripcion,
            creado_por=principal.actor_id,
            creado_en=self.reloj.ahora(),
        )
        await self.repo.agregar(fila)
        try:
            await almacen.guardar(
                clave, cifrador.cifrar_bytes(saneada.datos, contexto=id_foto.bytes)
            )
        except (ErrorAlmacen, OSError) as exc:
            raise ProveedorExternoNoDisponible(
                "No se pudo guardar la fotografía. Puede reintentar la carga."
            ) from exc
        return fila

    async def foto(
        self,
        principal: Principal,
        tipo: str,
        id_registro: uuid.UUID,
        id_foto: uuid.UUID,
        escribir: bool = False,
    ) -> FotoRegistro:
        destino = await self.acceso(principal, tipo, id_registro, escribir)
        clinica_id = self.clinica_destino(tipo, destino)
        fila = await self.repo.obtener(id_foto, clinica_id)
        if fila is None or fila.tipo_registro != tipo or fila.registro_id != id_registro:
            raise RecursoNoEncontrado("La fotografía no está disponible.")
        if fila.nivel_sensibilidad not in self.niveles_permitidos(principal, tipo):
            raise RecursoNoEncontrado("La fotografía no está disponible.")
        if (
            fila.paciente_id is not None
            and fila.nivel_sensibilidad == "N3"
            and not principal.tiene_permiso("historia_clinica.leer_sensible")
        ):
            raise RecursoNoEncontrado("La fotografía no está disponible.")
        return fila

    @staticmethod
    def clinica_destino(tipo: str, destino: Any) -> uuid.UUID:
        return uuid.UUID(
            str(
                destino.id
                if tipo == "clinica"
                else destino.clinic_id
                if tipo == "conocimiento"
                else destino.clinica_id
            )
        )
