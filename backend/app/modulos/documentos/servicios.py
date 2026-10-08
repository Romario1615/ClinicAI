from __future__ import annotations

import hashlib
import uuid
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.repositorio import RepositorioAgenda
from app.modulos.documentos.esquemas import ZONAS, RegistroNuevo
from app.modulos.documentos.modelos import RegistroPaciente
from app.modulos.documentos.pdf import generar_pdf
from app.modulos.historia.especialidades import especialidades_permitidas
from app.modulos.historia.modelos import Receta, RecetaMedicamento
from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.pacientes.acceso_clinico import GuardiaClinica
from app.modulos.pacientes.modelos import Paciente
from app.modulos.profesionales.modelos import Profesional
from app.nucleo.autorizacion import Principal
from app.nucleo.errores import ConflictoEstado, DatosInvalidos, PermisoDenegado, RecursoNoEncontrado
from app.nucleo.reloj import Reloj


class ServicioRegistros:
    def __init__(self, sesion: AsyncSession, reloj: Reloj):
        self.sesion, self.reloj = sesion, reloj

    async def acceso(
        self, principal: Principal, paciente_id: uuid.UUID, escribir: bool = False
    ) -> Paciente:
        return await GuardiaClinica(self.sesion).acceso_clinico(
            principal,
            paciente_id,
            "historia_clinica.escribir" if escribir else "historia_clinica.leer",
            self.reloj.ahora(),
        )

    async def especialidad(
        self, principal: Principal, especialidad_id: uuid.UUID, facial: bool = False
    ) -> None:
        permitidas = await especialidades_permitidas(self.sesion, principal)
        if not any(
            e.id == especialidad_id and (not facial or "faciograma" in modulos)
            for e, modulos, _ in permitidas
        ):
            raise RecursoNoEncontrado("La especialidad o módulo no está disponible.")

    def consulta(
        self, principal: Principal, paciente_id: uuid.UUID
    ) -> Select[tuple[RegistroPaciente]]:
        consulta = select(RegistroPaciente).where(
            RegistroPaciente.clinica_id == principal.clinica_id,
            RegistroPaciente.paciente_id == paciente_id,
        )
        if not principal.tiene_permiso("historia_clinica.leer_sensible"):
            consulta = consulta.where(RegistroPaciente.nivel_sensibilidad != "N3")
        if not principal.ambito.todas_las_sedes:
            consulta = consulta.where(RegistroPaciente.sede_id.in_(principal.ambito.sedes))
        return consulta

    async def obtener(
        self,
        principal: Principal,
        paciente_id: uuid.UUID,
        registro_id: uuid.UUID,
        escribir: bool = False,
    ) -> RegistroPaciente:
        await self.acceso(principal, paciente_id, escribir)
        fila = await self.sesion.scalar(
            self.consulta(principal, paciente_id).where(RegistroPaciente.id == registro_id)
        )
        if fila is None:
            raise RecursoNoEncontrado("El registro no está disponible.")
        await self.especialidad(principal, fila.especialidad_id, fila.tipo == "FACIOGRAMA")
        if escribir and fila.profesional_id != principal.profesional_id:
            raise PermisoDenegado("Solo el profesional autor puede modificar este registro.")
        return fila

    async def crear(
        self, principal: Principal, paciente_id: uuid.UUID, datos: RegistroNuevo
    ) -> RegistroPaciente:
        paciente = await self.acceso(principal, paciente_id, True)
        if principal.profesional_id is None:
            raise PermisoDenegado("Se necesita un perfil profesional para emitir este registro.")
        await self.especialidad(principal, datos.especialidad_id, datos.tipo == "FACIOGRAMA")
        # Una fila de paciente serializa las versiones y los reintentos.
        await self.sesion.execute(
            select(Paciente.id).where(Paciente.id == paciente_id).with_for_update()
        )
        huella = hashlib.sha256(
            datos.model_dump_json(exclude={"clave_idempotencia"}).encode()
        ).hexdigest()
        repetido = await self.sesion.scalar(
            self.consulta(principal, paciente_id).where(
                RegistroPaciente.id == datos.clave_idempotencia
            )
        )
        if repetido:
            if repetido.profesional_id != principal.profesional_id:
                raise ConflictoEstado("La clave ya fue utilizada.")
            if repetido.contenido.get("solicitud_hash") != huella:
                raise ConflictoEstado("La clave ya se usó para otro contenido.")
            return repetido
        if await self.sesion.get(RegistroPaciente, datos.clave_idempotencia):
            raise ConflictoEstado("La clave ya fue utilizada.")
        actual = None
        if datos.raiz_id:
            actual = await self.sesion.scalar(
                self.consulta(principal, paciente_id)
                .where(
                    RegistroPaciente.raiz_id == datos.raiz_id, RegistroPaciente.vigente.is_(True)
                )
                .with_for_update()
            )
            if actual is None or actual.version != datos.version_base or actual.anulado:
                raise ConflictoEstado(
                    "El registro cambió o fue anulado. Recargue su versión vigente."
                )
            if (
                actual.tipo != datos.tipo
                or actual.especialidad_id != datos.especialidad_id
                or actual.profesional_id != principal.profesional_id
            ):
                raise PermisoDenegado(
                    "No puede cambiar el autor, tipo o especialidad de un registro."
                )
        sede_id, sede = await self._contexto(principal, paciente, datos)
        nivel: str = (
            "N3" if actual and actual.nivel_sensibilidad == "N3" else datos.nivel_sensibilidad
        )
        if nivel == "N3" and not principal.tiene_permiso("historia_clinica.leer_sensible"):
            raise PermisoDenegado("Se requiere permiso de datos clínicos sensibles.")
        clinica = await self.sesion.get(Clinica, paciente.clinica_id)
        autor = await self.sesion.get(Profesional, principal.profesional_id)
        assert clinica is not None and autor is not None
        contenido: dict[str, object] = {
            "solicitud_hash": huella,
            "zonas": [z.model_dump() for z in datos.zonas],
            "partidas": [p.model_dump(mode="json") for p in datos.partidas],
            "observaciones": datos.observaciones,
            "moneda": datos.moneda,
            "valido_hasta": datos.valido_hasta.isoformat() if datos.valido_hasta else None,
            "clinica": clinica.nombre,
            "clinica_contacto": " | ".join(filter(None, [clinica.telefono, clinica.correo])),
            "identificacion_fiscal": clinica.identificacion_fiscal,
            "paciente": f"{paciente.nombre} {paciente.apellido}",
            "documento": paciente.numero_documento,
            "profesional": f"{autor.nombre} {autor.apellido}",
            "registro_profesional": autor.numero_registro_profesional,
            "sede": sede.nombre if sede else None,
        }
        if datos.tipo == "RECETA":
            nivel_receta = await self._receta(principal, paciente_id, datos, contenido)
            if nivel_receta == "N3":
                nivel = "N3"
        if actual:
            actual.vigente = False
            await self.sesion.flush()
        fila = RegistroPaciente(
            id=datos.clave_idempotencia,
            clinica_id=paciente.clinica_id,
            paciente_id=paciente_id,
            profesional_id=principal.profesional_id,
            especialidad_id=datos.especialidad_id,
            cita_id=datos.cita_id,
            sede_id=sede_id,
            raiz_id=datos.raiz_id or datos.clave_idempotencia,
            version=datos.version_base + 1,
            tipo=datos.tipo,
            titulo=datos.titulo,
            motivo=datos.motivo,
            contenido=contenido,
            nivel_sensibilidad=nivel,
            creado_por=principal.actor_id,
            creado_en=self.reloj.ahora(),
        )
        self.sesion.add(fila)
        await self.sesion.flush()
        return fila

    async def _contexto(
        self, principal: Principal, paciente: Paciente, datos: RegistroNuevo
    ) -> tuple[uuid.UUID | None, Sede | None]:
        sede_id = datos.sede_id
        sede = None
        if datos.cita_id:
            cita = await RepositorioAgenda(self.sesion).obtener_cita(
                datos.cita_id, principal=principal
            )
            if cita is None or cita.paciente_id != paciente.id:
                raise RecursoNoEncontrado("La cita no pertenece al paciente o a su ámbito.")
            profesional = await self.sesion.get(Profesional, cita.profesional_id)
            if profesional is None or profesional.especialidad_id != datos.especialidad_id:
                raise DatosInvalidos("La especialidad debe coincidir con la cita.")
            if sede_id is not None and sede_id != cita.sede_id:
                raise DatosInvalidos("La sede debe coincidir con la cita.")
            sede_id = cita.sede_id
        if sede_id:
            sede = await self.sesion.scalar(
                select(Sede).where(
                    Sede.id == sede_id,
                    Sede.clinica_id == paciente.clinica_id,
                    Sede.anulado_en.is_(None),
                )
            )
            if sede is None or (
                not principal.ambito.todas_las_sedes and sede_id not in principal.ambito.sedes
            ):
                raise RecursoNoEncontrado("La sede no está disponible.")
        elif not principal.ambito.todas_las_sedes:
            raise DatosInvalidos("Seleccione una sede de su ámbito.")
        return sede_id, sede

    async def _receta(
        self,
        principal: Principal,
        paciente_id: uuid.UUID,
        datos: RegistroNuevo,
        contenido: dict[str, object],
    ) -> str:
        GuardiaClinica.exigir(principal, "receta.leer")
        receta = await self.sesion.scalar(
            select(Receta).where(
                Receta.id == datos.receta_id,
                Receta.paciente_id == paciente_id,
                Receta.clinica_id == principal.clinica_id,
                Receta.estado == "CONFIRMADA",
            )
        )
        if receta is None:
            raise RecursoNoEncontrado("Solo puede emitir recetas confirmadas vigentes.")
        if receta.nivel_sensibilidad == "N3" and not principal.tiene_permiso(
            "historia_clinica.leer_sensible"
        ):
            raise RecursoNoEncontrado("La receta no está disponible.")
        nivel = receta.nivel_sensibilidad
        firmante = await self.sesion.get(Profesional, receta.confirmada_por)
        if firmante is None:
            raise DatosInvalidos("La receta no tiene un firmante válido.")
        contenido.update(
            {
                "receta_id": str(receta.id),
                "confirmada_en": receta.confirmada_en.isoformat() if receta.confirmada_en else None,
                "profesional": f"{firmante.nombre} {firmante.apellido}",
                "registro_profesional": firmante.numero_registro_profesional,
                "observaciones": receta.indicaciones_generales or "",
            }
        )
        medicamentos = await self.sesion.scalars(
            select(RecetaMedicamento)
            .where(RecetaMedicamento.receta_id == receta.id)
            .order_by(RecetaMedicamento.id)
        )
        contenido["medicamentos"] = [
            {
                c: getattr(m, c)
                for c in (
                    "nombre",
                    "concentracion",
                    "dosis",
                    "via",
                    "cuando_sea_necesario",
                    "frecuencia_horas",
                    "duracion_dias",
                    "instrucciones",
                    "hora_primera_toma",
                )
            }
            for m in medicamentos
        ]
        return nivel


def pdf_registro(fila: RegistroPaciente) -> bytes:
    c = fila.contenido
    lineas = [
        str(c.get("clinica", "")),
        str(c.get("clinica_contacto", "")),
        f"Identificación fiscal: {c.get('identificacion_fiscal') or 'No registrada'}",
        f"Paciente: {c.get('paciente')} | Documento: {c.get('documento')}",
        f"Profesional: {c.get('profesional')} | Registro: {c.get('registro_profesional') or 'No registrado'}",
        f"Sede: {c.get('sede') or 'Sin cita asociada'}",
        f"Referencia: {fila.raiz_id} | Versión: {fila.version}",
        f"Emitido: {fila.creado_en.isoformat()}",
        "ANULADO"
        if fila.anulado
        else "HISTÓRICO: sustituido por una versión posterior"
        if not fila.vigente
        else "",
        "",
    ]
    total = Decimal("0")
    partidas = c.get("partidas", [])
    if isinstance(partidas, list):
        for p in partidas:
            if isinstance(p, dict):
                subtotal = (
                    Decimal(str(p["cantidad"])) * Decimal(str(p["precio_unitario"]))
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                total += subtotal
                lineas.extend(
                    [
                        str(p["descripcion"]),
                        f"   {p['cantidad']} x {p['precio_unitario']} = {subtotal} {c.get('moneda')}",
                    ]
                )
        if partidas:
            lineas.extend(
                [
                    "",
                    f"TOTAL: {total:.2f} {c.get('moneda')}",
                    f"Válido hasta: {c.get('valido_hasta') or 'Sin fecha indicada'}",
                    "Presupuesto orientativo. No es una factura ni acredita pago.",
                ]
            )
    zonas = c.get("zonas", [])
    if isinstance(zonas, list):
        for z in zonas:
            if isinstance(z, dict):
                lineas.extend(
                    [
                        f"{ZONAS[str(z['zona'])][0]} | {z['estado']}",
                        str(z["observacion"]),
                        str(z.get("procedimiento") or ""),
                    ]
                )
    medicamentos = c.get("medicamentos", [])
    if isinstance(medicamentos, list):
        for m in medicamentos:
            if isinstance(m, dict):
                pauta = (
                    "Cuando sea necesario"
                    if m["cuando_sea_necesario"]
                    else f"Cada {m['frecuencia_horas']} horas"
                )
                lineas.extend(
                    [
                        f"{m['nombre']} {m.get('concentracion') or ''}",
                        f"Dosis: {m['dosis']} | Vía: {m['via']} | {pauta}",
                        f"Duración: {m['duracion_dias']} días",
                        f"Primera toma: {m.get('hora_primera_toma') or 'Según la indicación del profesional'}",
                        str(m.get("instrucciones") or ""),
                    ]
                )
    lineas.extend(
        [
            "",
            str(c.get("observaciones") or ""),
            "",
            "Registro del profesional. Este PDF no incorpora firma electrónica certificada.",
        ]
    )
    mapa = (
        {str(z["zona"]): str(z["estado"]) for z in zonas if isinstance(z, dict)}
        if fila.tipo == "FACIOGRAMA" and isinstance(zonas, list)
        else None
    )
    return generar_pdf(fila.titulo, lineas, mapa)
