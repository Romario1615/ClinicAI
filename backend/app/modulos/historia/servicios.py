"""Servicios de historia clinica, recetas y adherencia.

Esta es la capa que mas reglas de seguridad clinica concentra. Las que
importan, y por que:

**La IA no llega aqui.** Ninguna herramienta del agente invoca este modulo.
No crea ni modifica recetas, no ajusta dosis, no suspende tratamientos y no
interpreta reacciones. Todo eso deriva a `handoff_to_human` (CLAUDE.md,
regla 5). La restriccion no es una instruccion al modelo: la capacidad no
existe, porque `AgentTools` no expone estas operaciones.

**Corregir una nota crea una version, nunca reescribe.** Y exige motivo. Sin
el, ante una reclamacion no se puede explicar por que cambio una nota
clinica.

**Modificar una receta cancela las tomas futuras pendientes, no las
pasadas.** Las pasadas son el registro de lo que ocurrio; reescribirlo
falsearia el historico de adherencia, que es justo lo que un profesional mira
para decidir si el tratamiento funciona.

**El calendario de tomas se genera solo al confirmar.** Y lo genera este
servicio a partir de la frecuencia indicada; no calcula dosis ni decide
horarios clinicos, solo reparte en el tiempo lo que el profesional escribio.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.mensajeria.recordatorios import ServicioRecordatorios
from app.modulos.agenda.modelos import Cita
from app.modulos.historia.modelos import (
    AlertaAdherencia,
    Diagnostico,
    EstadoReceta,
    EstadoToma,
    NotaEvolucion,
    Receta,
    RecetaMedicamento,
    SeveridadAlerta,
    Toma,
)
from app.modulos.historia.repositorio import RepositorioHistoria
from app.modulos.profesionales.modelos import DelegacionFirma
from app.nucleo.auditoria import AccionAuditada, EntradaAuditoria, construir_entrada
from app.nucleo.autorizacion import NivelSensibilidad, Principal
from app.nucleo.errores import (
    ConflictoEstado,
    MotivoModificacionRequerido,
    OperacionClinicaNoPermitida,
    PermisoDenegado,
    RecetaNoConfirmada,
    RecursoNoEncontrado,
    ReglaNegocioViolada,
)
from app.nucleo.errores_bd import traducir_o_propagar
from app.nucleo.reloj import Reloj

# Techo del calendario que se genera de una vez. Una pauta de "cada hora
# durante un ano" produciria 8.760 filas; el limite las acota y obliga a
# revisar la pauta en lugar de llenar la tabla en silencio.
MAXIMO_TOMAS_POR_MEDICAMENTO = 400
LONGITUD_MINIMA_MOTIVO_RECETA = 5

# Umbrales de la alerta de adherencia. Son operativos, no clinicos: no dicen
# si el tratamiento funciona, solo cuando avisar a quien lo indico.
UMBRAL_ATENCION = 0.25
UMBRAL_URGENTE = 0.50
MINIMO_TOMAS_PARA_ALERTAR = 4


@dataclass(frozen=True, slots=True)
class DatosMedicamento:
    """Una linea de receta, ya validada por Pydantic."""

    nombre: str
    dosis: str
    via: str
    cuando_sea_necesario: bool = False
    frecuencia_horas: int | None = None
    duracion_dias: int | None = None
    hora_primera_toma: str | None = None
    concentracion: str | None = None
    forma: str | None = None
    instrucciones: str | None = None


@dataclass(frozen=True, slots=True)
class DatosNota:
    paciente_id: uuid.UUID
    profesional_id: uuid.UUID | None
    tipo: str
    nivel_sensibilidad: str = "N2"
    motivo_consulta: str | None = None
    subjetivo: str | None = None
    objetivo: str | None = None
    analisis: str | None = None
    plan: str | None = None
    signos_vitales: dict[str, object] | None = None
    cita_id: uuid.UUID | None = None
    diagnosticos: tuple[tuple[str | None, str, bool, bool], ...] = ()


@dataclass(frozen=True, slots=True)
class ResultadoClinico:
    """Lo escrito mas la auditoria que hay que confirmar con ello."""

    nota: NotaEvolucion | None = None
    receta: Receta | None = None
    tomas_generadas: int = 0
    tomas_canceladas: int = 0
    auditoria: tuple[EntradaAuditoria, ...] = field(default_factory=tuple)


class ServicioHistoria:
    """Escritura y lectura de la historia clinica."""

    def __init__(
        self,
        sesion: AsyncSession,
        repositorio: RepositorioHistoria,
        reloj: Reloj,
        *,
        zona_por_defecto: str = "America/Guayaquil",
    ) -> None:
        self._sesion = sesion
        self._repo = repositorio
        self._reloj = reloj
        self._zona = zona_por_defecto

    def ahora(self) -> datetime:
        """Instante actual segun el reloj inyectado.

        Se expone para que las rutas puedan pasarlo al repositorio sin tocar
        el reloj privado del servicio ni llamar a `datetime.now()`, que el
        linter prohibe fuera de `reloj.py` (ADR-0010).
        """
        return self._reloj.ahora()

    # ==================================================================
    #  Notas
    # ==================================================================
    async def crear_nota(self, datos: DatosNota, *, principal: Principal) -> ResultadoClinico:
        """Crea la primera version de una nota.

        `raiz_id` lo rellena un disparador con el propio identificador: la
        aplicacion no lo conoce antes de insertar.
        """
        self._exigir(principal, "historia_clinica.escribir")
        nivel = self._nivel_nota(datos.nivel_sensibilidad, principal)
        autor = self._autor(principal, datos.profesional_id)
        await self._exigir_relacion(principal, datos.paciente_id)

        if principal.clinica_id is None:
            raise PermisoDenegado("La sesion no tiene clinica asociada.")
        if datos.cita_id is not None:
            await self._exigir_cita_del_paciente(datos.cita_id, datos.paciente_id, principal)

        ahora = self._reloj.ahora()
        nota = NotaEvolucion(
            clinica_id=principal.clinica_id,
            paciente_id=datos.paciente_id,
            profesional_id=autor,
            cita_id=datos.cita_id,
            version=1,
            vigente=True,
            tipo=datos.tipo,
            nivel_sensibilidad=nivel.value,
            motivo_consulta=datos.motivo_consulta,
            subjetivo=datos.subjetivo,
            objetivo=datos.objetivo,
            analisis=datos.analisis,
            plan=datos.plan,
            signos_vitales=datos.signos_vitales,
            creado_por=principal.actor_id,
        )
        self._sesion.add(nota)
        await self._flush()

        self._anadir_diagnosticos(nota, datos.diagnosticos, principal)
        await self._flush()

        return ResultadoClinico(
            nota=nota,
            auditoria=(
                construir_entrada(
                    accion=AccionAuditada.NOTA_CREADA,
                    principal=principal,
                    ahora=ahora,
                    entidad_tipo="nota_evolucion",
                    entidad_id=nota.id,
                    paciente_id=nota.paciente_id,
                    nivel_sensibilidad=nivel,
                ),
            ),
        )

    async def versionar_nota(
        self,
        raiz_id: uuid.UUID,
        datos: DatosNota,
        *,
        principal: Principal,
        motivo: str,
    ) -> ResultadoClinico:
        """Crea la version siguiente de una nota.

        La anterior no se toca salvo para marcarla como no vigente, que es la
        unica modificacion que el disparador permite. Su contenido queda
        intacto y sigue siendo consultable.
        """
        self._exigir(principal, "historia_clinica.escribir")
        autor = self._autor(principal, datos.profesional_id)

        motivo_limpio = motivo.strip()
        if not motivo_limpio:
            # Sin motivo, ante una reclamacion no se puede explicar por que
            # cambio una nota clinica.
            raise MotivoModificacionRequerido(
                "Para corregir una nota clinica hay que indicar el motivo del cambio."
            )

        ahora = self._reloj.ahora()
        actual = await self._repo.obtener_version_vigente(raiz_id, principal=principal, ahora=ahora)
        if actual is None:
            raise RecursoNoEncontrado("La nota solicitada no existe.")

        await self._exigir_relacion(principal, actual.paciente_id)
        nivel = self._nivel_nota(
            datos.nivel_sensibilidad,
            principal,
            anterior=NivelSensibilidad(actual.nivel_sensibilidad),
        )

        # Se marca la anterior antes de insertar la nueva: el indice unico
        # parcial solo admite una vigente, y hacerlo al reves lo violaria.
        actual.vigente = False
        await self._flush()

        nueva = NotaEvolucion(
            clinica_id=actual.clinica_id,
            paciente_id=actual.paciente_id,
            profesional_id=autor,
            cita_id=actual.cita_id,
            raiz_id=actual.raiz_id,
            version=actual.version + 1,
            vigente=True,
            motivo_modificacion=motivo_limpio,
            tipo=datos.tipo,
            nivel_sensibilidad=nivel.value,
            motivo_consulta=datos.motivo_consulta,
            subjetivo=datos.subjetivo,
            objetivo=datos.objetivo,
            analisis=datos.analisis,
            plan=datos.plan,
            signos_vitales=datos.signos_vitales,
            creado_por=principal.actor_id,
        )
        self._sesion.add(nueva)
        await self._flush()

        self._anadir_diagnosticos(nueva, datos.diagnosticos, principal)
        await self._flush()

        return ResultadoClinico(
            nota=nueva,
            auditoria=(
                construir_entrada(
                    accion=AccionAuditada.NOTA_VERSIONADA,
                    principal=principal,
                    ahora=ahora,
                    entidad_tipo="nota_evolucion",
                    entidad_id=nueva.id,
                    paciente_id=nueva.paciente_id,
                    nivel_sensibilidad=nivel,
                    motivo=motivo_limpio,
                    version_anterior=actual.version,
                ),
            ),
        )

    async def leer_historia(
        self,
        paciente_id: uuid.UUID,
        *,
        principal: Principal,
        incluir_historico: bool = False,
        especialidades: frozenset[uuid.UUID] | None = None,
    ) -> tuple[list[NotaEvolucion], tuple[EntradaAuditoria, ...]]:
        """Lee la historia y **devuelve la auditoria de esa lectura**.

        Leer una historia clinica se audita siempre. Es la unica forma de
        responder a «quien vio mis datos», y el acceso por curiosidad -- el
        caso mas frecuente en una clinica -- no deja otro rastro.
        """
        self._exigir(principal, "historia_clinica.leer")
        await self._exigir_relacion(principal, paciente_id)

        ahora = self._reloj.ahora()
        notas = await self._repo.listar_notas(
            principal=principal,
            paciente_id=paciente_id,
            ahora=ahora,
            incluir_historico=incluir_historico,
            especialidades=especialidades,
        )
        entrada = construir_entrada(
            accion=AccionAuditada.HISTORIA_CONSULTADA,
            principal=principal,
            ahora=ahora,
            entidad_tipo="paciente",
            entidad_id=paciente_id,
            paciente_id=paciente_id,
            nivel_sensibilidad=(
                NivelSensibilidad.CLINICO_SENSIBLE
                if any(
                    n.nivel_sensibilidad == NivelSensibilidad.CLINICO_SENSIBLE.value for n in notas
                )
                else NivelSensibilidad.CLINICO
            ),
            # La clave es `versiones_devueltas` y no `notas_devueltas`: el
            # validador de auditoria rechaza toda clave que se parezca a un
            # campo sensible, y «notas» lo es. El validador no puede saber
            # que aqui es un recuento, y prefiere el falso positivo -- que
            # se corrige renombrando -- a dejar pasar contenido clinico.
            versiones_devueltas=len(notas),
            incluye_historico=incluir_historico,
            especialidades_revisadas=sorted(str(e) for e in especialidades or ()),
        )
        return notas, (entrada,)

    @staticmethod
    def _nivel_nota(
        solicitado: str,
        principal: Principal,
        *,
        anterior: NivelSensibilidad | None = None,
    ) -> NivelSensibilidad:
        """Valida N3 y evita que una correccion rebaje sensibilidad."""
        nivel = NivelSensibilidad(solicitado)
        if anterior == NivelSensibilidad.CLINICO_SENSIBLE:
            nivel = NivelSensibilidad.CLINICO_SENSIBLE
        if nivel == NivelSensibilidad.CLINICO_SENSIBLE and not principal.tiene_permiso(
            "historia_clinica.leer_sensible"
        ):
            raise PermisoDenegado(
                "Se requiere permiso clínico sensible para registrar una nota N3."
            )
        return nivel

    @staticmethod
    def _nivel_receta(solicitado: str, principal: Principal) -> NivelSensibilidad:
        nivel = NivelSensibilidad(solicitado)
        if nivel == NivelSensibilidad.CLINICO_SENSIBLE and not principal.tiene_permiso(
            "historia_clinica.leer_sensible"
        ):
            raise PermisoDenegado(
                "Se requiere permiso clínico sensible para registrar una receta N3."
            )
        return nivel

    # ==================================================================
    #  Recetas
    # ==================================================================
    async def crear_receta(
        self,
        *,
        principal: Principal,
        paciente_id: uuid.UUID,
        profesional_id: uuid.UUID,
        medicamentos: list[DatosMedicamento],
        indicaciones_generales: str | None = None,
        nota_id: uuid.UUID | None = None,
        nivel_sensibilidad: str = "N2",
    ) -> ResultadoClinico:
        """Crea una receta en **borrador**.

        Nunca confirmada de entrada. La confirmacion es un acto distinto, del
        profesional, y es la que convierte un texto en una indicacion vigente
        con recordatorios.
        """
        self._exigir(principal, "receta.crear")
        profesional_id, delegada = await self._firma(principal, profesional_id)
        await self._exigir_relacion(principal, paciente_id)

        if not medicamentos:
            raise ReglaNegocioViolada("Una receta necesita al menos un medicamento.")
        if principal.clinica_id is None:
            raise PermisoDenegado("La sesion no tiene clinica asociada.")
        nivel = self._nivel_receta(nivel_sensibilidad, principal)

        ahora = self._reloj.ahora()
        receta = Receta(
            clinica_id=principal.clinica_id,
            paciente_id=paciente_id,
            profesional_id=profesional_id,
            nota_id=nota_id,
            estado=EstadoReceta.BORRADOR.value,
            indicaciones_generales=indicaciones_generales,
            nivel_sensibilidad=nivel.value,
            creado_por=principal.actor_id,
        )
        self._sesion.add(receta)
        await self._flush()

        for medicamento in medicamentos:
            self._sesion.add(
                RecetaMedicamento(
                    receta_id=receta.id,
                    nombre=medicamento.nombre,
                    concentracion=medicamento.concentracion,
                    forma=medicamento.forma,
                    dosis=medicamento.dosis,
                    via=medicamento.via,
                    cuando_sea_necesario=medicamento.cuando_sea_necesario,
                    frecuencia_horas=medicamento.frecuencia_horas,
                    duracion_dias=medicamento.duracion_dias,
                    hora_primera_toma=medicamento.hora_primera_toma,
                    instrucciones=medicamento.instrucciones,
                    creado_por=principal.actor_id,
                )
            )
        await self._flush()

        return ResultadoClinico(
            receta=receta,
            auditoria=(
                construir_entrada(
                    accion=AccionAuditada.RECETA_CREADA,
                    principal=principal,
                    ahora=ahora,
                    entidad_tipo="receta",
                    entidad_id=receta.id,
                    paciente_id=paciente_id,
                    nivel_sensibilidad=nivel,
                    lineas=len(medicamentos),
                    firma_delegada=delegada,
                ),
            ),
        )

    async def confirmar_receta(
        self, receta_id: uuid.UUID, *, principal: Principal, profesional_id: uuid.UUID
    ) -> ResultadoClinico:
        """Confirma la receta y genera el calendario de tomas.

        Es el unico camino que crea tomas. Un disparador de la base lo
        respalda: insertar una toma de una receta sin confirmar se rechaza.
        """
        self._exigir(principal, "receta.confirmar")
        profesional_id, delegada = await self._firma(principal, profesional_id)

        ahora = self._reloj.ahora()
        receta = await self._repo.obtener_receta(
            receta_id, principal=principal, ahora=ahora, bloquear=True
        )
        if receta is None:
            raise RecursoNoEncontrado("La receta solicitada no existe.")

        if receta.estado != EstadoReceta.BORRADOR.value:
            raise ConflictoEstado(
                f"Solo se confirma una receta en borrador (estado actual: {receta.estado})."
            )

        receta.estado = EstadoReceta.CONFIRMADA.value
        receta.confirmada_en = ahora
        receta.confirmada_por = profesional_id
        receta.actualizado_por = principal.actor_id
        await self._flush()

        generadas = await self._generar_tomas(receta, desde=ahora)
        await ServicioRecordatorios(self._sesion, self._reloj).programar_tomas(receta.id)

        return ResultadoClinico(
            receta=receta,
            tomas_generadas=generadas,
            auditoria=(
                construir_entrada(
                    accion=AccionAuditada.RECETA_CONFIRMADA,
                    principal=principal,
                    ahora=ahora,
                    entidad_tipo="receta",
                    entidad_id=receta.id,
                    paciente_id=receta.paciente_id,
                    nivel_sensibilidad=NivelSensibilidad(receta.nivel_sensibilidad),
                    firma_delegada=delegada,
                    profesional_firmante=str(profesional_id),
                ),
                construir_entrada(
                    accion=AccionAuditada.TOMAS_GENERADAS,
                    principal=principal,
                    ahora=ahora,
                    entidad_tipo="receta",
                    entidad_id=receta.id,
                    paciente_id=receta.paciente_id,
                    cantidad=generadas,
                ),
            ),
        )

    async def suspender_receta(
        self, receta_id: uuid.UUID, *, principal: Principal, motivo: str
    ) -> ResultadoClinico:
        """Suspende la receta y cancela sus tomas futuras pendientes.

        Las pasadas no se tocan: son el registro de lo que ocurrio, y
        reescribirlo falsearia el historico de adherencia que el profesional
        mira para decidir si el tratamiento funciona.
        """
        self._exigir(principal, "receta.confirmar")

        motivo_limpio = motivo.strip()
        if not motivo_limpio:
            raise ReglaNegocioViolada("Para suspender una receta hay que indicar el motivo.")

        ahora = self._reloj.ahora()
        receta = await self._repo.obtener_receta(
            receta_id, principal=principal, ahora=ahora, bloquear=True
        )
        if receta is None:
            raise RecursoNoEncontrado("La receta solicitada no existe.")
        if receta.estado == EstadoReceta.SUSPENDIDA.value:
            raise ConflictoEstado("La receta ya esta suspendida.")

        receta.estado = EstadoReceta.SUSPENDIDA.value
        receta.suspendida_en = ahora
        receta.motivo_suspension = motivo_limpio
        receta.actualizado_por = principal.actor_id

        canceladas = await self._cancelar_tomas_futuras(receta_id, desde=ahora)
        await ServicioRecordatorios(self._sesion, self._reloj).cancelar_tomas_receta(
            receta_id, motivo=motivo_limpio
        )
        await self._flush()

        return ResultadoClinico(
            receta=receta,
            tomas_canceladas=canceladas,
            auditoria=(
                construir_entrada(
                    accion=AccionAuditada.RECETA_SUSPENDIDA,
                    principal=principal,
                    ahora=ahora,
                    entidad_tipo="receta",
                    entidad_id=receta.id,
                    paciente_id=receta.paciente_id,
                    nivel_sensibilidad=NivelSensibilidad(receta.nivel_sensibilidad),
                    motivo=motivo_limpio,
                ),
                construir_entrada(
                    accion=AccionAuditada.TOMAS_CANCELADAS,
                    principal=principal,
                    ahora=ahora,
                    entidad_tipo="receta",
                    entidad_id=receta.id,
                    paciente_id=receta.paciente_id,
                    cantidad=canceladas,
                ),
            ),
        )

    async def versionar_receta(
        self,
        receta_id: uuid.UUID,
        *,
        principal: Principal,
        profesional_id: uuid.UUID,
        motivo: str,
        indicaciones_generales: str | None,
        medicamentos: list[DatosMedicamento],
    ) -> ResultadoClinico:
        """Sustituye una receta vigente con una versión firmada en una transacción.

        Conserva la receta y sus tomas anteriores. Solo cancela las tomas
        futuras pendientes, crea el nuevo calendario y cancela/reprograma sus
        recordatorios en la misma transacción HTTP.
        """
        self._exigir(principal, "receta.crear")
        self._exigir(principal, "receta.confirmar")
        firmante, delegada = await self._firma(principal, profesional_id)
        motivo_limpio = motivo.strip()
        if len(motivo_limpio) < LONGITUD_MINIMA_MOTIVO_RECETA:
            raise ReglaNegocioViolada("Explique el motivo del cambio de receta.")
        if not medicamentos:
            raise ReglaNegocioViolada("Una receta necesita al menos un medicamento.")

        ahora = self._reloj.ahora()
        anterior = await self._repo.obtener_receta(
            receta_id, principal=principal, ahora=ahora, bloquear=True
        )
        if anterior is None:
            raise RecursoNoEncontrado("La receta solicitada no existe.")
        if anterior.estado != EstadoReceta.CONFIRMADA.value:
            raise ConflictoEstado(
                "Solo se puede crear una versión nueva de una receta confirmada "
                f"(estado actual: {anterior.estado})."
            )
        await self._exigir_relacion(principal, anterior.paciente_id)

        anterior.estado = EstadoReceta.SUSPENDIDA.value
        anterior.suspendida_en = ahora
        anterior.motivo_suspension = motivo_limpio
        anterior.actualizado_por = principal.actor_id
        canceladas = await self._cancelar_tomas_futuras(anterior.id, desde=ahora)
        await ServicioRecordatorios(self._sesion, self._reloj).cancelar_tomas_receta(
            anterior.id, motivo=f"Receta sustituida: {motivo_limpio}"
        )
        await self._flush()

        nueva = Receta(
            clinica_id=anterior.clinica_id,
            paciente_id=anterior.paciente_id,
            profesional_id=firmante,
            nota_id=anterior.nota_id,
            receta_anterior_id=anterior.id,
            estado=EstadoReceta.BORRADOR.value,
            indicaciones_generales=indicaciones_generales,
            nivel_sensibilidad=anterior.nivel_sensibilidad,
            creado_por=principal.actor_id,
            actualizado_por=principal.actor_id,
        )
        self._sesion.add(nueva)
        await self._flush()

        for medicamento in medicamentos:
            self._sesion.add(
                RecetaMedicamento(
                    receta_id=nueva.id,
                    nombre=medicamento.nombre,
                    concentracion=medicamento.concentracion,
                    forma=medicamento.forma,
                    dosis=medicamento.dosis,
                    via=medicamento.via,
                    cuando_sea_necesario=medicamento.cuando_sea_necesario,
                    frecuencia_horas=medicamento.frecuencia_horas,
                    duracion_dias=medicamento.duracion_dias,
                    hora_primera_toma=medicamento.hora_primera_toma,
                    instrucciones=medicamento.instrucciones,
                    creado_por=principal.actor_id,
                )
            )
        await self._flush()
        nueva.estado = EstadoReceta.CONFIRMADA.value
        nueva.confirmada_en = ahora
        nueva.confirmada_por = firmante
        await self._flush()
        generadas = await self._generar_tomas(nueva, desde=ahora)
        await ServicioRecordatorios(self._sesion, self._reloj).programar_tomas(nueva.id)

        return ResultadoClinico(
            receta=nueva,
            tomas_canceladas=canceladas,
            tomas_generadas=generadas,
            auditoria=(
                construir_entrada(
                    accion=AccionAuditada.RECETA_MODIFICADA,
                    principal=principal,
                    ahora=ahora,
                    entidad_tipo="receta",
                    entidad_id=anterior.id,
                    paciente_id=anterior.paciente_id,
                    nivel_sensibilidad=NivelSensibilidad(anterior.nivel_sensibilidad),
                    motivo=motivo_limpio,
                    version_nueva_id=str(nueva.id),
                    tomas_canceladas=canceladas,
                    firma_delegada=delegada,
                ),
                construir_entrada(
                    accion=AccionAuditada.TOMAS_CANCELADAS,
                    principal=principal,
                    ahora=ahora,
                    entidad_tipo="receta",
                    entidad_id=anterior.id,
                    paciente_id=anterior.paciente_id,
                    cantidad=canceladas,
                ),
                construir_entrada(
                    accion=AccionAuditada.RECETA_CONFIRMADA,
                    principal=principal,
                    ahora=ahora,
                    entidad_tipo="receta",
                    entidad_id=nueva.id,
                    paciente_id=nueva.paciente_id,
                    nivel_sensibilidad=NivelSensibilidad(nueva.nivel_sensibilidad),
                    profesional_firmante=str(firmante),
                    firma_delegada=delegada,
                ),
                construir_entrada(
                    accion=AccionAuditada.TOMAS_GENERADAS,
                    principal=principal,
                    ahora=ahora,
                    entidad_tipo="receta",
                    entidad_id=nueva.id,
                    paciente_id=nueva.paciente_id,
                    cantidad=generadas,
                ),
            ),
        )

    # ==================================================================
    #  Tomas
    # ==================================================================
    async def registrar_toma(
        self,
        toma_id: uuid.UUID,
        *,
        principal: Principal,
        tomada: bool,
        nota_paciente: str | None = None,
    ) -> ResultadoClinico:
        """Registra que una toma se hizo o no.

        Lo puede hacer el propio paciente por WhatsApp o el personal. **No se
        permite registrar una toma futura**: marcar como tomada una dosis que
        todavia no toca produce un registro de adherencia falso, y ese
        registro es lo que un profesional mira para decidir.
        """
        ahora = self._reloj.ahora()
        toma = await self._sesion.get(Toma, toma_id, with_for_update=True)
        if toma is None:
            raise RecursoNoEncontrado("La toma solicitada no existe.")

        if not principal.ambito.cubre_paciente(toma.paciente_id):
            raise RecursoNoEncontrado("La toma solicitada no existe.")

        if toma.estado != EstadoToma.PENDIENTE.value:
            raise ConflictoEstado(f"Esta toma ya se registro como {toma.estado}.")

        if toma.programada_en > ahora:
            raise ReglaNegocioViolada("No se puede registrar una toma cuya hora todavia no llego.")

        toma.estado = EstadoToma.TOMADA.value if tomada else EstadoToma.OMITIDA.value
        toma.registrada_en = ahora
        toma.registrada_por_tipo = principal.actor_tipo.value
        toma.registrada_por_id = principal.actor_id
        toma.nota_paciente = (nota_paciente or "").strip() or None
        await ServicioRecordatorios(self._sesion, self._reloj).cancelar_toma(
            toma.id,
            motivo="Toma registrada" if tomada else "Toma marcada como omitida",
        )
        await self._flush()

        return ResultadoClinico(
            auditoria=(
                construir_entrada(
                    accion=AccionAuditada.TOMA_REGISTRADA,
                    principal=principal,
                    ahora=ahora,
                    entidad_tipo="toma",
                    entidad_id=toma.id,
                    paciente_id=toma.paciente_id,
                    tomada=tomada,
                ),
            ),
        )

    async def evaluar_adherencia(
        self,
        receta_id: uuid.UUID,
        *,
        principal: Principal,
        dias: int = 7,
    ) -> AlertaAdherencia | None:
        """Crea una alerta si el patron de omisiones lo justifica.

        **No interpreta nada clinicamente.** Cuenta tomas omitidas sobre
        esperadas y compara con un umbral operativo. No concluye que el
        tratamiento haya fallado ni sugiere cambiarlo: eso lo lee el
        profesional (CLAUDE.md, regla 5).

        Devuelve `None` cuando no hay suficientes tomas para decir nada. Con
        dos tomas, una omision da el 50 % y produciria una alerta por un dato
        sin valor.
        """
        ahora = self._reloj.ahora()
        receta = await self._repo.obtener_receta(receta_id, principal=principal, ahora=ahora)
        if receta is None:
            raise RecursoNoEncontrado("La receta solicitada no existe.")
        if receta.estado != EstadoReceta.CONFIRMADA.value:
            raise RecetaNoConfirmada("Solo se evalua la adherencia de una receta confirmada.")

        desde = ahora - timedelta(days=dias)
        esperadas, omitidas = await self._repo.contar_tomas(receta_id, desde=desde, hasta=ahora)

        if esperadas < MINIMO_TOMAS_PARA_ALERTAR:
            return None

        proporcion = omitidas / esperadas
        if proporcion < UMBRAL_ATENCION:
            return None

        # Una sola alerta abierta por receta: repetirla cada dia convertiria
        # el aviso en ruido y el profesional dejaria de mirarlo. El indice
        # unico parcial lo respalda.
        if await self._repo.alerta_abierta(receta_id) is not None:
            return None

        alerta = AlertaAdherencia(
            clinica_id=receta.clinica_id,
            paciente_id=receta.paciente_id,
            receta_id=receta.id,
            profesional_id=receta.profesional_id,
            severidad=(
                SeveridadAlerta.URGENTE.value
                if proporcion >= UMBRAL_URGENTE
                else SeveridadAlerta.ATENCION.value
            ),
            tomas_omitidas=omitidas,
            tomas_esperadas=esperadas,
            periodo_desde=desde,
            periodo_hasta=ahora,
        )
        self._sesion.add(alerta)
        await self._flush()
        return alerta

    async def atender_alerta_adherencia(
        self, alerta_id: uuid.UUID, *, principal: Principal, nota: str | None = None
    ) -> ResultadoClinico:
        if "alerta_adherencia.atender" not in principal.permisos:
            raise PermisoDenegado("No tiene permiso para atender alertas de adherencia.")
        ahora = self._reloj.ahora()
        alerta = await self._repo.obtener_alerta(
            alerta_id, principal=principal, ahora=ahora, bloquear=True
        )
        if alerta is None:
            raise RecursoNoEncontrado("La alerta solicitada no existe.")
        if alerta.atendida_en is not None:
            raise ConflictoEstado("Esta alerta ya fue atendida.")
        alerta.atendida_en = ahora
        alerta.atendida_por = principal.actor_id
        alerta.nota_profesional = (nota or "").strip() or None
        await self._flush()
        return ResultadoClinico(
            auditoria=(
                construir_entrada(
                    accion=AccionAuditada.ALERTA_ADHERENCIA_ATENDIDA,
                    principal=principal,
                    ahora=ahora,
                    entidad_tipo="alerta_adherencia",
                    entidad_id=alerta.id,
                    paciente_id=alerta.paciente_id,
                ),
            ),
        )

    # ==================================================================
    #  Auxiliares
    # ==================================================================
    async def _generar_tomas(self, receta: Receta, *, desde: datetime) -> int:
        """Reparte en el tiempo lo que el profesional indico.

        No decide horarios clinicos: toma la frecuencia y la duracion escritas
        y calcula los instantes. La primera toma va a la hora indicada del
        primer dia, o a la hora siguiente en punto si no se indico ninguna.

        Los PRN se saltan sin error: no es un caso excepcional, es la mitad de
        las recetas. El disparador de la base lo rechazaria de todas formas.
        """
        medicamentos = await self._repo.medicamentos_de(receta.id)
        zona = ZoneInfo(self._zona)
        total = 0

        for medicamento in medicamentos:
            if medicamento.cuando_sea_necesario or medicamento.frecuencia_horas is None:
                continue

            inicio = self._primera_toma(medicamento, desde=desde, zona=zona)
            duracion = medicamento.duracion_dias or 1
            cuantas = (duracion * 24) // medicamento.frecuencia_horas
            if cuantas <= 0:
                continue
            if cuantas > MAXIMO_TOMAS_POR_MEDICAMENTO:
                raise ReglaNegocioViolada(
                    f"La pauta de «{medicamento.nombre}» generaria {cuantas} tomas, "
                    f"por encima del maximo de {MAXIMO_TOMAS_POR_MEDICAMENTO}. "
                    "Revise la frecuencia y la duracion."
                )

            for indice in range(cuantas):
                self._sesion.add(
                    Toma(
                        receta_medicamento_id=medicamento.id,
                        paciente_id=receta.paciente_id,
                        programada_en=inicio
                        + timedelta(hours=medicamento.frecuencia_horas * indice),
                    )
                )
                total += 1

        await self._flush()
        return total

    def _primera_toma(
        self, medicamento: RecetaMedicamento, *, desde: datetime, zona: ZoneInfo
    ) -> datetime:
        """Instante de la primera toma, en UTC.

        Si el profesional indico hora local, se usa esa del dia siguiente o
        del mismo dia segun si ya paso. Si no, la siguiente hora en punto: es
        mas facil de recordar que "dentro de 37 minutos".
        """
        if not medicamento.hora_primera_toma:
            return (desde + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

        horas, _, minutos = medicamento.hora_primera_toma.partition(":")
        local = desde.astimezone(zona).replace(
            hour=int(horas), minute=int(minutos or 0), second=0, microsecond=0
        )
        if local <= desde.astimezone(zona):
            local = local + timedelta(days=1)
        return local.astimezone(UTC)

    async def _cancelar_tomas_futuras(self, receta_id: uuid.UUID, *, desde: datetime) -> int:
        tomas = await self._repo.tomas_futuras_pendientes(receta_id, desde=desde)
        for toma in tomas:
            toma.estado = EstadoToma.CANCELADA.value
        return len(tomas)

    def _anadir_diagnosticos(
        self,
        nota: NotaEvolucion,
        diagnosticos: tuple[tuple[str | None, str, bool, bool], ...],
        principal: Principal,
    ) -> None:
        if diagnosticos and not principal.tiene_permiso("diagnostico.registrar"):
            raise PermisoDenegado("No tiene permiso para registrar diagnosticos.")
        for codigo, descripcion, principal_dx, presuntivo in diagnosticos:
            self._sesion.add(
                Diagnostico(
                    nota_id=nota.id,
                    codigo_cie10=codigo,
                    descripcion=descripcion,
                    principal=principal_dx,
                    presuntivo=presuntivo,
                    creado_por=principal.actor_id,
                )
            )

    def _exigir(self, principal: Principal, permiso: str) -> None:
        if principal.es_agente:
            # Defensa en profundidad. El agente no llega aqui porque sus
            # herramientas no exponen estas operaciones (ADR-0014), pero si
            # alguien anadiera una, este control la detiene.
            raise OperacionClinicaNoPermitida(
                "El asistente automatico no escribe ni interpreta informacion clinica."
            )
        if not principal.tiene_permiso(permiso):
            raise PermisoDenegado("No tiene permiso para esta operacion clinica.")

    @staticmethod
    def _autor(principal: Principal, declarado: uuid.UUID | None) -> uuid.UUID:
        """El autor de una nota es quien la escribe, nunca un dato del cliente.

        Antes se tomaba `profesional_id` del cuerpo: un profesional podia firmar
        una nota a nombre de otro. Solo un profesional escribe notas, y su
        identificador sale de la sesion.
        """
        if principal.profesional_id is None:
            raise PermisoDenegado("Solo un profesional puede escribir notas clinicas.")
        if declarado is not None and declarado != principal.profesional_id:
            raise PermisoDenegado("No puede registrar una nota a nombre de otro profesional.")
        return principal.profesional_id

    async def _firma(self, principal: Principal, firmante: uuid.UUID) -> tuple[uuid.UUID, bool]:
        """Quien firma una receta: el propio profesional, o otro por delegacion.

        Firmar por otro solo vale con una delegacion registrada por la
        administracion, vigente ahora y de esa persona hacia quien actua. Sin
        ella, 403. Devuelve el firmante y si la firma es delegada (se audita).
        """
        if principal.profesional_id is None:
            raise PermisoDenegado("Solo un profesional firma recetas.")
        if firmante == principal.profesional_id:
            return firmante, False
        ahora = self._reloj.ahora()
        vigente = (
            await self._sesion.execute(
                select(DelegacionFirma.id).where(
                    DelegacionFirma.clinica_id == principal.clinica_id,
                    DelegacionFirma.delegante_id == firmante,
                    DelegacionFirma.delegado_id == principal.profesional_id,
                    DelegacionFirma.revocada_en.is_(None),
                    DelegacionFirma.vigente_desde <= ahora,
                    DelegacionFirma.vigente_hasta > ahora,
                )
            )
        ).first()
        if vigente is None:
            raise PermisoDenegado(
                "No tiene una delegacion vigente para firmar a nombre de ese profesional."
            )
        return firmante, True

    async def _exigir_cita_del_paciente(
        self, cita_id: uuid.UUID, paciente_id: uuid.UUID, principal: Principal
    ) -> None:
        cita = (
            await self._sesion.execute(
                select(Cita.id).where(
                    Cita.id == cita_id,
                    Cita.paciente_id == paciente_id,
                    Cita.clinica_id == principal.clinica_id,
                )
            )
        ).scalar_one_or_none()
        if cita is None:
            raise RecursoNoEncontrado("La cita indicada no existe para este paciente.")

    async def _exigir_relacion(self, principal: Principal, paciente_id: uuid.UUID) -> None:
        """Comprueba el vinculo asistencial cuando el principal es profesional.

        No aplica a quien no es profesional: un auditor revisando accesos no
        tiene relaciones asistenciales, y su acceso se controla por permiso y
        por auditoria.
        """
        if principal.profesional_id is None:
            return
        existe = await self._repo.tiene_relacion_asistencial(
            paciente_id=paciente_id,
            profesional_id=principal.profesional_id,
            ahora=self._reloj.ahora(),
        )
        if not existe:
            raise RecursoNoEncontrado("El paciente solicitado no existe.")

    async def _flush(self) -> None:
        try:
            await self._sesion.flush()
        except SQLAlchemyError as exc:
            await self._sesion.rollback()
            raise traducir_o_propagar(exc) from exc


__all__ = [
    "MAXIMO_TOMAS_POR_MEDICAMENTO",
    "DatosMedicamento",
    "DatosNota",
    "ResultadoClinico",
    "ServicioHistoria",
]
