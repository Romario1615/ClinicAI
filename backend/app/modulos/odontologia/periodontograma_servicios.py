from __future__ import annotations

import hashlib
import uuid
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.documentos.pdf import generar_pdf
from app.modulos.odontologia.periodontograma_esquemas import (
    PeriodontogramaNuevo,
    PeriodontogramaSalida,
    PiezaPeriodontal,
    resumir_piezas,
)
from app.modulos.odontologia.periodontograma_modelos import Periodontograma
from app.modulos.odontologia.periodontograma_repositorio import RepositorioPeriodontograma
from app.modulos.pacientes.acceso_clinico import GuardiaClinica
from app.nucleo.autorizacion import Principal
from app.nucleo.errores import ConflictoEstado, DatosInvalidos, PermisoDenegado, RecursoNoEncontrado
from app.nucleo.reloj import Reloj


class ServicioPeriodontograma:
    def __init__(self, sesion: AsyncSession, reloj: Reloj):
        self.repo = RepositorioPeriodontograma(sesion)
        self.guardia = GuardiaClinica(sesion)
        self.reloj = reloj

    async def acceso(
        self, principal: Principal, paciente_id: uuid.UUID, escribir: bool = False
    ) -> None:
        await self.guardia.acceso_clinico(
            principal,
            paciente_id,
            "odontograma.escribir" if escribir else "odontograma.leer",
            self.reloj.ahora(),
        )

    def salida(
        self, fila: Periodontograma, principal: Principal, ultima: int
    ) -> PeriodontogramaSalida:
        piezas = {k: PiezaPeriodontal.model_validate(v) for k, v in fila.piezas.items()}
        return PeriodontogramaSalida(
            id=fila.id,
            raiz_id=fila.raiz_id,
            version=fila.version,
            paciente_id=fila.paciente_id,
            profesional_id=fila.profesional_id,
            especialidad_id=fila.especialidad_id,
            sede_id=fila.sede_id,
            cita_id=fila.cita_id,
            fecha_examen=fila.fecha_examen,
            piezas=piezas,
            observaciones=fila.observaciones,
            motivo=fila.motivo,
            nivel_sensibilidad=fila.nivel_sensibilidad,
            anulado=fila.anulado,
            vigente=fila.version == ultima,
            puede_editar=(
                fila.version == ultima
                and not fila.anulado
                and fila.profesional_id == principal.profesional_id
                and principal.tiene_permiso("odontograma.escribir")
            ),
            creado_en=fila.creado_en,
            resumen=resumir_piezas(piezas),
        )

    async def listar(
        self, principal: Principal, paciente_id: uuid.UUID
    ) -> list[PeriodontogramaSalida]:
        await self.acceso(principal, paciente_id)
        filas = await self.repo.listar(principal, paciente_id)
        # No ocultar la existencia de una corrección N3 marcando una versión N2 como vigente.
        ultimas = {r: await self.repo.ultima_version(r) for r in {f.raiz_id for f in filas}}
        return [self.salida(f, principal, ultimas[f.raiz_id]) for f in filas]

    async def obtener(
        self, principal: Principal, paciente_id: uuid.UUID, id_registro: uuid.UUID
    ) -> Periodontograma:
        await self.acceso(principal, paciente_id)
        fila = await self.repo.obtener(principal, paciente_id, id_registro)
        if fila is None:
            raise RecursoNoEncontrado("El control periodontal no está disponible.")
        return fila

    async def crear(
        self, principal: Principal, paciente_id: uuid.UUID, datos: PeriodontogramaNuevo
    ) -> PeriodontogramaSalida:
        await self.acceso(principal, paciente_id, True)
        if principal.profesional_id is None:
            raise PermisoDenegado("Solo un profesional de odontología registra mediciones.")
        hoy = (
            self.reloj.ahora()
            .astimezone(ZoneInfo(await self.repo.zona(principal.clinica_id)))
            .date()
        )
        if datos.fecha_examen > hoy:
            raise DatosInvalidos("La fecha del examen no puede estar en el futuro.")
        await self.repo.bloquear_paciente(paciente_id)
        huella = hashlib.sha256(
            datos.model_dump_json(exclude={"clave_idempotencia"}).encode()
        ).hexdigest()
        repetido = await self.repo.obtener(principal, paciente_id, datos.clave_idempotencia)
        if repetido:
            if (
                repetido.profesional_id != principal.profesional_id
                or repetido.solicitud_hash != huella
            ):
                raise ConflictoEstado("La clave se utilizó para otro registro.")
            return self.salida(
                repetido, principal, await self.repo.ultima_version(repetido.raiz_id)
            )
        if await self.repo.id_ocupado(datos.clave_idempotencia):
            raise ConflictoEstado("La clave ya fue utilizada.")
        anterior = None
        if datos.version_anterior_id:
            anterior = await self.repo.obtener(principal, paciente_id, datos.version_anterior_id)
            if anterior is None:
                raise RecursoNoEncontrado("El control anterior no está disponible.")
            if anterior.profesional_id != principal.profesional_id:
                raise PermisoDenegado("Solo el autor puede corregir o anular su control.")
            if (
                anterior.anulado
                or await self.repo.ultima_version(anterior.raiz_id) != anterior.version
            ):
                raise ConflictoEstado(
                    "El control cambió o fue anulado. Recargue su última versión."
                )
            if datos.cita_id != anterior.cita_id or datos.sede_id != anterior.sede_id:
                raise DatosInvalidos("Una corrección debe conservar la cita y sede originales.")
        profesional = await self.repo.profesional(principal.profesional_id)
        if (
            profesional is None
            or profesional.clinica_id != principal.clinica_id
            or not profesional.activo
        ):
            raise PermisoDenegado("El perfil profesional no está activo.")
        sede_id = await self.contexto(principal, paciente_id, profesional.id, datos)
        nivel = (
            "N3" if anterior and anterior.nivel_sensibilidad == "N3" else datos.nivel_sensibilidad
        )
        if nivel == "N3" and not principal.tiene_permiso("historia_clinica.leer_sensible"):
            raise PermisoDenegado("Se requiere acceso a datos clínicos sensibles.")
        fila = Periodontograma(
            id=datos.clave_idempotencia,
            clinica_id=principal.clinica_id,
            paciente_id=paciente_id,
            profesional_id=profesional.id,
            especialidad_id=profesional.especialidad_id,
            sede_id=sede_id,
            cita_id=datos.cita_id,
            raiz_id=anterior.raiz_id if anterior else datos.clave_idempotencia,
            version=anterior.version + 1 if anterior else 1,
            fecha_examen=anterior.fecha_examen
            if datos.anulado and anterior
            else datos.fecha_examen,
            piezas=anterior.piezas
            if datos.anulado and anterior
            else {k: v.model_dump() for k, v in datos.piezas.items()},
            observaciones=anterior.observaciones
            if datos.anulado and anterior
            else datos.observaciones,
            motivo=datos.motivo.strip(),
            nivel_sensibilidad=nivel,
            anulado=datos.anulado,
            solicitud_hash=huella,
            creado_por=principal.actor_id,
            creado_en=self.reloj.ahora(),
        )
        await self.repo.agregar(fila)
        return self.salida(fila, principal, fila.version)

    async def contexto(
        self,
        principal: Principal,
        paciente_id: uuid.UUID,
        profesional_id: uuid.UUID,
        datos: PeriodontogramaNuevo,
    ) -> uuid.UUID | None:
        sede_id = datos.sede_id
        if datos.cita_id:
            cita = await self.repo.cita(principal, datos.cita_id)
            if (
                cita is None
                or cita.paciente_id != paciente_id
                or cita.profesional_id != profesional_id
            ):
                raise RecursoNoEncontrado("La cita no pertenece al paciente y profesional.")
            if sede_id is not None and sede_id != cita.sede_id:
                raise DatosInvalidos("La sede debe coincidir con la cita.")
            sede_id = cita.sede_id
        if sede_id:
            sede = await self.repo.sede(principal, sede_id)
            if sede is None or (
                not principal.ambito.todas_las_sedes and sede_id not in principal.ambito.sedes
            ):
                raise RecursoNoEncontrado("La sede no está disponible.")
        elif not principal.ambito.todas_las_sedes:
            raise DatosInvalidos("Seleccione una sede de su ámbito.")
        return sede_id

    async def pdf(
        self, principal: Principal, paciente_id: uuid.UUID, id_registro: uuid.UUID
    ) -> bytes:
        fila = await self.obtener(principal, paciente_id, id_registro)
        resumen = self.salida(fila, principal, await self.repo.ultima_version(fila.raiz_id)).resumen
        lineas = [
            f"Paciente: {paciente_id}",
            f"Examen: {fila.fecha_examen} | Versión {fila.version}",
            f"Profesional: {fila.profesional_id}",
            f"Estado: {'Anulado' if fila.anulado else 'Registro de mediciones'}",
            f"Sondeados: {resumen.sitios_sondados}/{resumen.sitios_posibles}",
            f"Profundidad media: {resumen.profundidad_media} mm",
            f"Sangrado: {resumen.sangrado_positivos}/{resumen.sangrado_evaluados} sitios",
            "PS: profundidad; MG: margen positivo apical, negativo coronal; NIC = PS + MG.",
            "V: vestibular; L: palatino/lingual; M/C/D: mesial/central/distal.",
            "-- significa sin evaluar. No constituye diagnóstico automatizado.",
        ]
        for codigo, pieza in sorted(fila.piezas.items()):
            lineas.append(
                f"Pieza {codigo}: {'ausente' if pieza['ausente'] else 'implante' if pieza['implante'] else 'presente'} | Movilidad {pieza['movilidad']} | Furcación {pieza['furcacion']}"
            )
            for sitio, valores in pieza["sitios"].items():
                ps, mg = valores.get("profundidad"), valores.get("margen")
                nic = round(ps + mg, 2) if ps is not None and mg is not None else "--"

                def indicador(v: bool | None) -> str:
                    return "--" if v is None else "Sí" if v else "No"

                lineas.append(
                    f"{sitio}: PS {ps if ps is not None else '--'} | MG {mg if mg is not None else '--'} | NIC {nic} | Sangrado {indicador(valores.get('sangrado'))} | Placa {indicador(valores.get('placa'))}"
                )
            if pieza.get("nota"):
                lineas.append(pieza["nota"])
        lineas += [f"Motivo: {fila.motivo}", fila.observaciones or ""]
        return generar_pdf("Periodontograma", lineas)
