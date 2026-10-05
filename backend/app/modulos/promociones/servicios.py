"""Servicio de campanas de promociones.

Reglas que hace cumplir
-----------------------
* **Consentimiento propio.** Solo pacientes con `PROMOCIONES` vigente. El
  outbox lo vuelve a comprobar al encolar: dos barreras, una por consulta y
  otra por mensaje.
* **Una persona aprueba.** La imagen generada es una propuesta; nada sale sin
  `promocion.aprobar`, imagen y aprobacion registradas (lo exige tambien una
  restriccion de la base).
* **Nada clinico.** El segmento solo filtra por sede y antiguedad de la
  ultima visita completada. La plantilla solo admite nombre y texto de la
  oferta.
* **Sin duplicados.** Cada envio usa la clave `promo:<hash(campana, paciente)>`.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ia.imagenes_generativas import GeneradorImagenes, validar_prompt
from app.mensajeria.plantillas import obtener as obtener_plantilla
from app.mensajeria.servicios import ServicioOutbox, SolicitudEnvio
from app.modulos.agenda.modelos import Cita, EstadoCita
from app.modulos.outbox.modelos import CanalOutbox, TipoMensajeOutbox
from app.modulos.pacientes.modelos import Consentimiento, Paciente, TipoConsentimiento
from app.modulos.promociones.esquemas import CambiosCampana, CampanaNueva, Segmento
from app.modulos.promociones.modelos import CampanaPromocion, EstadoCampana, OrigenImagen
from app.nucleo.almacen import AlmacenObjetos, ErrorAlmacen
from app.nucleo.archivos import sanear_imagen
from app.nucleo.autorizacion import Principal
from app.nucleo.configuracion import Configuracion
from app.nucleo.errores import (
    ConflictoEstado,
    ConsentimientoRequerido,
    DatosInvalidos,
    PermisoDenegado,
    ProveedorExternoNoDisponible,
    RecursoNoEncontrado,
)
from app.nucleo.reloj import Reloj
from app.nucleo.seguridad import CifradorDatos

# Tope por campana: una audiencia mayor se divide. Evita una transaccion
# enorme y una rafaga que agote la cuota de marketing de Meta.
MAXIMO_DESTINATARIOS = 5000


class ServicioPromociones:
    def __init__(
        self,
        sesion: AsyncSession,
        reloj: Reloj,
        almacen: AlmacenObjetos,
        cifrador: CifradorDatos,
        configuracion: Configuracion,
        generador: GeneradorImagenes,
    ) -> None:
        self._sesion = sesion
        self._reloj = reloj
        self._almacen = almacen
        self._cifrador = cifrador
        self._configuracion = configuracion
        self._generador = generador

    # ------------------------------------------------------------------
    #  Lectura
    # ------------------------------------------------------------------
    async def listar(self, principal: Principal) -> list[CampanaPromocion]:
        consulta = (
            select(CampanaPromocion)
            .where(CampanaPromocion.clinica_id == principal.clinica_id)
            .order_by(CampanaPromocion.creado_en.desc())
            .limit(100)
        )
        return list((await self._sesion.execute(consulta)).scalars())

    async def obtener(
        self, campana_id: uuid.UUID, principal: Principal, *, bloquear: bool = False
    ) -> CampanaPromocion:
        consulta = select(CampanaPromocion).where(
            CampanaPromocion.id == campana_id,
            CampanaPromocion.clinica_id == principal.clinica_id,
        )
        if bloquear:
            consulta = consulta.with_for_update()
        campana = (await self._sesion.execute(consulta)).scalar_one_or_none()
        if campana is None:
            raise RecursoNoEncontrado("La campana solicitada no existe.")
        return campana

    @staticmethod
    def vista_previa(campana: CampanaPromocion) -> str:
        """El mensaje tal como lo leera un paciente de ejemplo."""
        return obtener_plantilla(TipoMensajeOutbox.PROMOCION).redactar(
            nombre="(nombre del paciente)", texto_promocion=campana.texto
        )

    # ------------------------------------------------------------------
    #  Borrador
    # ------------------------------------------------------------------
    async def crear(self, datos: CampanaNueva, principal: Principal) -> CampanaPromocion:
        if principal.clinica_id is None:
            raise PermisoDenegado("La cuenta no tiene clinica asignada.")
        await self._validar_sede(datos.segmento, principal)
        campana = CampanaPromocion(
            clinica_id=principal.clinica_id,
            nombre=datos.nombre.strip(),
            texto=datos.texto,
            plantilla_meta=datos.plantilla_meta,
            estado=EstadoCampana.BORRADOR.value,
            segmento=datos.segmento.model_dump(mode="json", exclude_none=True),
            creado_por=principal.actor_id,
        )
        self._sesion.add(campana)
        await self._sesion.flush()
        return campana

    async def modificar(
        self, campana_id: uuid.UUID, cambios: CambiosCampana, principal: Principal
    ) -> CampanaPromocion:
        campana = await self._borrador(campana_id, principal)
        if cambios.nombre is not None:
            campana.nombre = cambios.nombre.strip()
        if cambios.texto is not None:
            campana.texto = cambios.texto
        if cambios.plantilla_meta is not None:
            campana.plantilla_meta = cambios.plantilla_meta
        if cambios.segmento is not None:
            await self._validar_sede(cambios.segmento, principal)
            campana.segmento = cambios.segmento.model_dump(mode="json", exclude_none=True)
        campana.actualizado_por = principal.actor_id
        await self._sesion.flush()
        return campana

    # ------------------------------------------------------------------
    #  Imagen
    # ------------------------------------------------------------------
    async def subir_imagen(
        self, campana_id: uuid.UUID, contenido: bytes, principal: Principal
    ) -> CampanaPromocion:
        campana = await self._borrador(campana_id, principal)
        saneada = await sanear_imagen(contenido, self._configuracion)
        if saneada.tipo_mime not in {"image/jpeg", "image/png"}:
            # La cabecera de las plantillas de WhatsApp solo admite JPEG y PNG.
            raise DatosInvalidos("WhatsApp solo admite imagenes JPEG o PNG en la cabecera.")
        await self._guardar_imagen(campana, saneada.datos, saneada.tipo_mime)
        campana.imagen_origen = OrigenImagen.SUBIDA.value
        campana.imagen_proveedor = None
        campana.imagen_prompt = None
        campana.actualizado_por = principal.actor_id
        await self._sesion.flush()
        return campana

    async def generar_imagen(
        self, campana_id: uuid.UUID, descripcion: str, principal: Principal
    ) -> CampanaPromocion:
        """Pide una imagen al modelo. Queda como propuesta del borrador."""
        campana = await self._borrador(campana_id, principal)
        prompt = validar_prompt(descripcion)
        generada = await self._generador.generar(prompt)
        # El resultado de un tercero pasa por el mismo saneado que una subida.
        saneada = await sanear_imagen(generada.datos, self._configuracion)
        await self._guardar_imagen(campana, saneada.datos, saneada.tipo_mime)
        campana.imagen_origen = OrigenImagen.GENERADA.value
        campana.imagen_proveedor = generada.proveedor
        campana.imagen_prompt = prompt
        campana.actualizado_por = principal.actor_id
        await self._sesion.flush()
        return campana

    async def leer_imagen(self, campana_id: uuid.UUID, principal: Principal) -> tuple[bytes, str]:
        campana = await self.obtener(campana_id, principal)
        if not campana.imagen_clave or not campana.imagen_mime:
            raise RecursoNoEncontrado("La campana no tiene imagen.")
        return await self._leer(campana), campana.imagen_mime

    # ------------------------------------------------------------------
    #  Aprobacion, envio y cancelacion
    # ------------------------------------------------------------------
    async def aprobar(self, campana_id: uuid.UUID, principal: Principal) -> CampanaPromocion:
        campana = await self._borrador(campana_id, principal)
        if not campana.imagen_clave:
            raise ConflictoEstado("Agregue o genere la imagen antes de aprobar la campana.")
        campana.estado = EstadoCampana.APROBADA.value
        campana.aprobada_por = principal.actor_id
        campana.aprobada_en = self._reloj.ahora()
        await self._sesion.flush()
        return campana

    async def enviar(
        self,
        campana_id: uuid.UUID,
        principal: Principal,
        *,
        outbox: ServicioOutbox,
        subir_medio: Any | None,
        programada_para: datetime | None = None,
    ) -> CampanaPromocion:
        """Encola un mensaje por destinatario. La entrega la hace el worker.

        `subir_medio` es el metodo del adaptador de WhatsApp que sube la imagen
        y devuelve su media id; se llama una vez por campana.
        """
        campana = await self.obtener(campana_id, principal, bloquear=True)
        if campana.estado != EstadoCampana.APROBADA.value:
            raise ConflictoEstado("Solo se envia una campana aprobada.")
        ahora = self._reloj.ahora()
        if programada_para is not None and programada_para < ahora - timedelta(minutes=1):
            raise DatosInvalidos("La fecha de envio ya paso.")

        if subir_medio is not None and campana.imagen_media_id is None:
            datos = await self._leer(campana)
            campana.imagen_media_id = await subir_medio(datos, campana.imagen_mime or "image/png")

        destinatarios = await self._destinatarios(campana, principal)
        if len(destinatarios) > MAXIMO_DESTINATARIOS:
            raise ConflictoEstado(
                f"La audiencia supera {MAXIMO_DESTINATARIOS} pacientes. Divida la campana por sede."
            )
        encolados = omitidos = 0
        for paciente_id, nombre in destinatarios:
            try:
                creado = await outbox.encolar(
                    SolicitudEnvio(
                        tipo=TipoMensajeOutbox.PROMOCION,
                        canal=CanalOutbox.WHATSAPP,
                        destino_tipo="PACIENTE",
                        destino_id=paciente_id,
                        clave_deduplicacion=_clave_envio(campana.id, paciente_id),
                        variables={"nombre": nombre, "texto_promocion": campana.texto},
                        clinica_id=campana.clinica_id,
                        entidad_origen_tipo="campana_promocion",
                        entidad_origen_id=campana.id,
                        programado_para=programada_para,
                        plantilla_meta=campana.plantilla_meta,
                        imagen_cabecera=campana.imagen_media_id,
                    )
                )
            except ConsentimientoRequerido:
                # Revocado entre la consulta y el encolado: se respeta.
                omitidos += 1
                continue
            if creado is None:
                omitidos += 1
            else:
                encolados += 1

        campana.estado = EstadoCampana.ENVIADA.value
        campana.enviada_en = ahora
        campana.programada_para = programada_para
        campana.encolados = encolados
        campana.omitidos = omitidos
        campana.actualizado_por = principal.actor_id
        await self._sesion.flush()
        return campana

    async def cancelar(
        self, campana_id: uuid.UUID, motivo: str, principal: Principal
    ) -> CampanaPromocion:
        campana = await self.obtener(campana_id, principal, bloquear=True)
        if campana.estado not in (EstadoCampana.BORRADOR.value, EstadoCampana.APROBADA.value):
            raise ConflictoEstado(
                "Una campana enviada no se cancela: los mensajes ya estan en la cola."
            )
        campana.estado = EstadoCampana.CANCELADA.value
        campana.cancelada_en = self._reloj.ahora()
        campana.motivo_cancelacion = motivo.strip()
        campana.actualizado_por = principal.actor_id
        await self._sesion.flush()
        return campana

    # ------------------------------------------------------------------
    #  Audiencia
    # ------------------------------------------------------------------
    async def contar_audiencia(self, campana_id: uuid.UUID, principal: Principal) -> int:
        campana = await self.obtener(campana_id, principal)
        consulta = self._consulta_audiencia(campana).with_only_columns(func.count(Paciente.id))
        return int((await self._sesion.execute(consulta)).scalar_one())

    async def _destinatarios(
        self, campana: CampanaPromocion, principal: Principal
    ) -> list[tuple[uuid.UUID, str]]:
        del principal
        consulta = (
            self._consulta_audiencia(campana).order_by(Paciente.id).limit(MAXIMO_DESTINATARIOS + 1)
        )
        return [(fila.id, fila.nombre) for fila in (await self._sesion.execute(consulta)).all()]

    def _consulta_audiencia(self, campana: CampanaPromocion) -> Select[Any]:
        ahora = self._reloj.ahora()
        segmento = Segmento.model_validate(campana.segmento or {})
        consentimiento = exists().where(
            Consentimiento.paciente_id == Paciente.id,
            Consentimiento.tipo == TipoConsentimiento.PROMOCIONES.value,
            Consentimiento.otorgado.is_(True),
            Consentimiento.revocado_en.is_(None),
        )
        consulta = select(Paciente.id, Paciente.nombre).where(
            Paciente.clinica_id == campana.clinica_id,
            Paciente.anulado_en.is_(None),
            Paciente.telefono_whatsapp.is_not(None),
            consentimiento,
        )
        if segmento.sede_id is not None:
            consulta = consulta.where(
                exists().where(Cita.paciente_id == Paciente.id, Cita.sede_id == segmento.sede_id)
            )
        ultima_visita = (
            select(func.max(Cita.inicio))
            .where(
                Cita.paciente_id == Paciente.id,
                Cita.estado == EstadoCita.COMPLETED.value,
            )
            .scalar_subquery()
        )
        if segmento.sin_visita_hace_dias:
            limite = ahora - timedelta(days=segmento.sin_visita_hace_dias)
            consulta = consulta.where(and_(ultima_visita.is_not(None), ultima_visita <= limite))
        if segmento.visita_en_ultimos_dias:
            limite = ahora - timedelta(days=segmento.visita_en_ultimos_dias)
            consulta = consulta.where(ultima_visita >= limite)
        return consulta

    # ------------------------------------------------------------------
    #  Apoyo
    # ------------------------------------------------------------------
    async def _borrador(self, campana_id: uuid.UUID, principal: Principal) -> CampanaPromocion:
        campana = await self.obtener(campana_id, principal, bloquear=True)
        if campana.estado != EstadoCampana.BORRADOR.value:
            raise ConflictoEstado("Solo se modifica una campana en borrador.")
        return campana

    async def _validar_sede(self, segmento: Segmento, principal: Principal) -> None:
        if segmento.sede_id is not None and not principal.ambito.cubre_sede(segmento.sede_id):
            raise RecursoNoEncontrado("La sede solicitada no existe.")

    async def _guardar_imagen(self, campana: CampanaPromocion, datos: bytes, mime: str) -> None:
        version = uuid.uuid4()
        clave = f"{campana.clinica_id}/promociones/{campana.id}/{version}"
        cifrado = self._cifrador.cifrar_bytes(datos, contexto=campana.id.bytes)
        try:
            await self._almacen.guardar(clave, cifrado)
        except (ErrorAlmacen, OSError) as exc:
            raise ProveedorExternoNoDisponible("No se pudo guardar la imagen.") from exc
        campana.imagen_clave = clave
        campana.imagen_mime = mime
        campana.imagen_sha256 = hashlib.sha256(datos).hexdigest()
        # Una imagen nueva invalida el medio ya subido a WhatsApp.
        campana.imagen_media_id = None

    async def _leer(self, campana: CampanaPromocion) -> bytes:
        try:
            cifrado = await self._almacen.leer(campana.imagen_clave or "")
        except (ErrorAlmacen, OSError, ValueError) as exc:
            raise ProveedorExternoNoDisponible("La imagen no esta disponible.") from exc
        return self._cifrador.descifrar_bytes(cifrado, contexto=campana.id.bytes)


def _clave_envio(campana_id: uuid.UUID, paciente_id: uuid.UUID) -> str:
    """Clave de deduplicacion de 64 caracteres (limite de la columna del outbox).

    Hash estable de campana y paciente: el mismo par produce siempre la misma
    clave, asi que reencolar la campana no duplica ningun mensaje.
    """
    huella = hashlib.sha256(f"{campana_id}:{paciente_id}".encode()).hexdigest()
    return f"promo:{huella[:58]}"


__all__ = ["MAXIMO_DESTINATARIOS", "ServicioPromociones"]
