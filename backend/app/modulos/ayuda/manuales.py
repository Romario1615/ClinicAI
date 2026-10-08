"""Contenido de los manuales de ayuda.

Un manual por rol, y por que asi
--------------------------------
La tarea 11.1 del backlog pide un manual **independiente** para cada rol del
sistema y para cada rol personalizado de una clinica, y prohibe reutilizar un
manual generico. El motivo es practico: un manual comun obliga a cada persona
a separar lo que le toca de lo que no, y en una recepcion con prisa eso
significa que no se lee.

* Los **seis roles del sistema** tienen un manual escrito para su trabajo:
  introduccion, responsabilidades, secciones con pasos y limites propios. Una
  prueba comprueba que ningun titulo ni ningun paso se repite entre manuales.
* Los **roles personalizados** no se conocen de antemano (los crea cada
  clinica), asi que su manual se compone con el catalogo `CAPACIDADES`, cuyo
  texto tampoco coincide con el de los roles del sistema, y con su nombre,
  descripcion y permisos reales.

El manual nunca describe lo que el rol no puede usar
----------------------------------------------------
Cada seccion declara los permisos que exige (`requiere`: todos; `alguno`: al
menos uno) y, si hace falta, un rol (`rol`). El servicio solo entrega las
secciones cuyos requisitos cumplen **a la vez** el rol y la sesion: si una
clinica retira un permiso, la seccion desaparece del manual en la siguiente
consulta. Los requisitos reproducen los guardias de cada pantalla
(`frontend/src/app/app.routes.ts`) y las condiciones de cada boton; una
prueba unitaria comprueba que cada ruta citada existe.

El texto es contenido de ayuda (N0): no contiene datos de pacientes ni
clinicos, ni indicaciones clinicas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final


@dataclass(frozen=True, slots=True)
class Seccion:
    """Una tarea del manual: para que sirve, como se hace y que no hace."""

    clave: str
    titulo: str
    ruta: str | None
    proposito: str
    pasos: tuple[str, ...]
    limites: tuple[str, ...] = ()
    # Permisos que hacen falta todos.
    requiere: frozenset[str] = field(default_factory=frozenset)
    # Permisos de los que basta uno (los guardias con varios permisos).
    alguno: frozenset[str] = field(default_factory=frozenset)
    # Rol necesario cuando la pantalla no depende de un permiso sino del rol
    # (el portal de plataforma del superadministrador).
    rol: str | None = None

    def aplica(self, permisos: frozenset[str], roles: frozenset[str]) -> bool:
        """La seccion describe algo que este rol puede hacer de verdad."""
        if self.rol is not None and self.rol not in roles:
            return False
        if not self.requiere <= permisos:
            return False
        return not self.alguno or bool(self.alguno & permisos)

    @property
    def permisos(self) -> frozenset[str]:
        """Todos los permisos que menciona la seccion."""
        return self.requiere | self.alguno


@dataclass(frozen=True, slots=True)
class ManualSistema:
    """Manual escrito para un rol base del sistema."""

    rol: str
    titulo: str
    introduccion: str
    responsabilidades: tuple[str, ...]
    limites: tuple[str, ...]
    secciones: tuple[Seccion, ...]


def _s(
    clave: str,
    titulo: str,
    ruta: str | None,
    proposito: str,
    pasos: tuple[str, ...],
    limites: tuple[str, ...] = (),
    *,
    requiere: tuple[str, ...] = (),
    alguno: tuple[str, ...] = (),
    rol: str | None = None,
) -> Seccion:
    return Seccion(
        clave=clave,
        titulo=titulo,
        ruta=ruta,
        proposito=proposito,
        pasos=pasos,
        limites=limites,
        requiere=frozenset(requiere),
        alguno=frozenset(alguno),
        rol=rol,
    )


# ---------------------------------------------------------------------------
#  Recepcion
# ---------------------------------------------------------------------------
_RECEPCION = ManualSistema(
    rol="recepcion",
    titulo="Manual de Recepción",
    introduccion=(
        "Recepción es la puerta de entrada de la clínica: agenda, registra a las personas que "
        "llegan, mantiene sus datos de contacto y cobra. Trabaja con información administrativa; "
        "la historia clínica, las recetas y las imágenes clínicas no forman parte de este rol."
    ),
    responsabilidades=(
        "Que cada cita quede reservada, confirmada o liberada a tiempo.",
        "Que la llegada de cada paciente se registre en el momento en que entra.",
        "Que los datos de contacto y los consentimientos de comunicación estén al día.",
        "Que los abonos y comprobantes queden registrados el mismo día.",
    ),
    limites=(
        "No lee ni escribe historia clínica, recetas, odontograma ni radiografías.",
        "No configura horarios, feriados ni bloqueos: lo hace la administración desde Configuración.",
        "No emite facturas electrónicas: el sistema no está conectado al SRI.",
    ),
    secciones=(
        _s(
            "recepcion.agente-ficha",
            "Coordinar turnos con el agente de una persona",
            "/pacientes",
            "Acompañar la atención administrativa manteniendo una única ficha como contexto.",
            (
                "En Pacientes, abra Ver ficha y pulse Agente del paciente para consultar sus citas y cobros autorizados.",
                "En Más gestiones, configure sede, servicio, responsable y fechas si necesita buscar un horario; elija un turno ofrecido.",
                "Compruebe el nombre de la persona, el horario y el motivo antes de pulsar Confirmar acción; Descartar conserva la agenda.",
            ),
            ("Este apoyo de recepción no muestra resúmenes clínicos ni ejecuta prescripciones.",),
            requiere=("paciente.leer_administrativo",),
        ),
        _s(
            "recepcion.fotos-administrativas",
            "Adjuntar identificación y respaldos de recepción",
            "/pacientes",
            "Registrar fotografías administrativas junto con los datos de atención.",
            (
                "Al dar de alta a una persona, elija su foto de perfil o use Tomar foto en un dispositivo compatible.",
                "Antes de confirmar una reserva, adjunte sus imágenes administrativas; en una serie quedan en la primera cita.",
                "Para consultar los respaldos de una cita, abra su detalle y pulse Fotos y adjuntos.",
            ),
            (
                "Recepción conserva fotografías administrativas; las mediciones e imágenes clínicas requieren permisos asistenciales.",
                "Si falla la carga, el aviso informa que la reserva ya existe: reintente Guardar para completar solo las fotografías.",
            ),
            requiere=("paciente.crear", "cita.crear"),
        ),
        _s(
            "recepcion.analitica",
            "Anticipar el trabajo de la recepción",
            "/analitica",
            "Examinar demanda y ausencias de los turnos que recepción puede gestionar.",
            (
                "Entre en Analítica IA y elija historial, horizonte y sede permitida.",
                "Consulte Descriptivo para los volúmenes registrados y Predictivo para las estimaciones de futuras fechas.",
                "En Prescriptivo revise propuestas de contacto y confirme cualquier acción en Agenda con la persona responsable.",
            ),
            (
                "Falta historial significa que todavía no hay datos suficientes para estimar; los días no observados no se inventan.",
            ),
            requiere=("dashboard.leer",),
        ),
        _s(
            "recepcion.atencion-documentos",
            "Preparar la atención y autorizar el canal documental",
            "/pacientes",
            "Mantener el contexto administrativo y el consentimiento específico de entrega.",
            (
                "Abra la ficha, entre en Atención y seleccione la cita para comprobar sede, servicio y especialista.",
                "En Contacto y consentimientos, registre Documentos por WhatsApp únicamente si el paciente lo autoriza y compruebe su teléfono.",
                "Use Pagos de esta cita para consultar sus cargos; el presupuesto lo emite el profesional en su acceso clínico.",
            ),
            ("Recepción no consulta el mapa facial ni emite recetas o documentos clínicos.",),
            requiere=("paciente.leer_administrativo", "paciente.editar", "agenda.leer"),
        ),
        _s(
            "recepcion.turno",
            "Empezar el turno desde el Panel",
            "/panel",
            "Ver de un vistazo lo que tiene plazo hoy antes de atender al primer paciente.",
            (
                "Entre en Panel y revise el bloque de tareas de hoy: turnos por vencer, citas sin "
                "confirmar y llamadas pendientes.",
                "Abra la campana de la cabecera; cada aviso lleva directamente a la pantalla donde "
                "se resuelve.",
                "Si la clínica tiene varias sedes, filtre por la suya para no ver el trabajo de otra.",
            ),
            ("Las cifras del panel son agregados: no muestran nombres de pacientes.",),
            requiere=("dashboard.leer",),
        ),
        _s(
            "recepcion.reservar",
            "Reservar una cita en un hueco libre",
            "/agenda",
            "Dar una cita con la disponibilidad real del profesional, sin riesgo de doble reserva.",
            (
                "En Agenda, elija sede, especialidad, servicio y profesional para ver solo los huecos "
                "que encajan.",
                "Pulse un hueco libre; el sistema lo retiene unos minutos mientras completa la reserva.",
                "Busque al paciente por nombre, apellido o documento; si no existe, regístrelo antes.",
                "Confirme la cita y compruebe que aparece en el calendario del día.",
            ),
            (
                "Si otra persona toma el mismo hueco a la vez, la base de datos rechaza la segunda "
                "reserva: elija otro hueco.",
                "Un hueco retenido y no confirmado vence solo y vuelve a quedar libre.",
            ),
            requiere=("agenda.leer", "cita.crear"),
        ),
        _s(
            "recepcion.llegada",
            "Registrar la llegada y la inasistencia",
            "/agenda",
            "Que el profesional sepa quién está esperando y que la espera real se mida.",
            (
                "Cuando el paciente se presente, abra su cita en Agenda y registre la llegada.",
                "Si la hora pasa sin que llegue, marque la cita como inasistencia en lugar de "
                "cancelarla.",
            ),
            (
                "Una cita con llegada registrada ya no puede marcarse como inasistencia.",
                "Iniciar la atención lo hace el equipo clínico, no Recepción.",
            ),
            requiere=("agenda.leer", "cita.registrar_llegada", "cita.marcar_inasistencia"),
        ),
        _s(
            "recepcion.cambios",
            "Reprogramar o cancelar a petición del paciente",
            "/agenda",
            "Mover o liberar un turno conservando el historial de lo que pasó.",
            (
                "Abra la cita en Agenda y elija Reprogramar para llevarla a otro hueco disponible.",
                "Para cancelar, escriba el motivo: es obligatorio y queda en el historial de la cita.",
                "Tras cancelar, revise Lista de espera: el hueco liberado puede ofrecerse a quien "
                "espera.",
            ),
            (
                "La cita conserva su identificador al reprogramarse; el horario anterior queda registrado.",
            ),
            requiere=("agenda.leer", "cita.reprogramar", "cita.cancelar"),
        ),
        _s(
            "recepcion.pacientes",
            "Registrar y actualizar pacientes",
            "/pacientes",
            "Tener una ficha administrativa única y correcta por persona.",
            (
                "Antes de registrar, busque en Pacientes por documento: evita fichas duplicadas.",
                "Registre nombre, documento, fecha de nacimiento y un teléfono de contacto.",
                "Para corregir un dato, abra la ficha y edítela; el cambio queda auditado.",
            ),
            (
                "Un teléfono no identifica a una persona: varios pacientes pueden compartirlo.",
                "Use solo datos que el paciente haya entregado; nunca invente un documento.",
            ),
            requiere=("paciente.leer_administrativo", "paciente.crear", "paciente.editar"),
        ),
        _s(
            "recepcion.consentimientos",
            "Consentimientos para recibir mensajes",
            "/pacientes",
            "Registrar si el paciente acepta recordatorios y avisos automáticos.",
            (
                "Abra la ficha del paciente y vaya a sus consentimientos de comunicación.",
                "Registre la aceptación o la revocación tal como la expresó el paciente, con la fecha.",
            ),
            (
                "Sin consentimiento no salen avisos automáticos: las ofertas de lista de espera "
                "aparecen como llamadas que hay que hacer en persona.",
                "Estos consentimientos son de comunicación; no sustituyen un consentimiento "
                "informado clínico.",
            ),
            requiere=("paciente.leer_administrativo", "consentimiento.gestionar"),
        ),
        _s(
            "recepcion.espera",
            "Lista de espera y llamadas pendientes",
            "/lista-espera",
            "Recuperar turnos cancelados para quien necesita adelantar su cita.",
            (
                "Anote al paciente indicando profesional, rango de fechas, días y franja que le sirven.",
                "Cuando el sistema ofrezca un hueco a alguien sin consentimiento de mensajes, llámele "
                "antes de que la oferta venza.",
                "Si acepta, la cita anterior se reagenda en el mismo paso; si el hueco ya se ocupó, "
                "la anterior se conserva.",
            ),
            (
                "Una oferta vencida vuelve a la cola: nadie pierde su cita original por no contestar.",
            ),
            requiere=("lista_espera.gestionar",),
        ),
        _s(
            "recepcion.mensajes",
            "Mensajes derivados a una persona",
            "/conversaciones",
            "Saber qué conversaciones de WhatsApp pidieron atención humana.",
            (
                "Revise Atención de mensajes cuando la insignia del menú muestre pendientes.",
                "Use la información para llamar o atender al paciente por el canal habitual.",
            ),
            (
                "La bandeja es de lectura: responder desde aquí requiere conectar el proveedor real "
                "de WhatsApp.",
            ),
            requiere=("conversacion.leer",),
        ),
        _s(
            "recepcion.cobros",
            "Registrar abonos y comprobantes",
            "/pagos",
            "Llevar el saldo de cada cita al día, con su respaldo.",
            (
                "En Pagos, ubique el cargo de la cita y registre el abono con su método.",
                "Adjunte el comprobante (PDF, JPEG, PNG o WebP); se guarda cifrado.",
                "Filtre los saldos vencidos para saber a quién recordar un pago pendiente.",
            ),
            ("Un comprobante con contenido activo o de tipo no admitido se rechaza.",),
            requiere=("pago.leer", "pago.registrar"),
        ),
        _s(
            "recepcion.validar",
            "Validar o rechazar un comprobante",
            "/pagos",
            "Confirmar que el dinero declarado llegó antes de darlo por pagado.",
            (
                "Abra el pago en revisión y compare el comprobante con el ingreso real.",
                "Valide o rechace; al rechazar, el monto reservado se libera y el saldo vuelve a "
                "quedar pendiente.",
            ),
            requiere=("pago.leer", "pago.validar"),
        ),
        _s(
            "recepcion.exportar",
            "Exportar resúmenes del día",
            "/agenda",
            "Entregar a la administración conteos diarios sin exponer pacientes.",
            (
                "En Agenda, exporte el resumen CSV por fecha y estado de las citas.",
                "En Pagos, exporte el resumen por fecha, estado y método.",
            ),
            (
                "Los archivos solo contienen conteos y sumas; ninguna fila identifica a un paciente.",
            ),
            requiere=("agenda.leer", "pago.leer", "reporte.exportar"),
        ),
        _s(
            "recepcion.consultas",
            "Responder dudas con documentos aprobados",
            "/conocimiento",
            "Contestar preguntas frecuentes (preparación, horarios, políticas) sin improvisar.",
            (
                "Busque en Conocimiento o pregunte al Asistente; las respuestas salen solo de "
                "documentos aprobados.",
                "Si no hay un documento aprobado, dígalo así y derive la consulta a quien corresponda.",
            ),
            requiere=("conocimiento.leer",),
        ),
    ),
)


# ---------------------------------------------------------------------------
#  Profesional
# ---------------------------------------------------------------------------
_PROFESIONAL = ManualSistema(
    rol="profesional",
    titulo="Manual del Profesional",
    introduccion=(
        "El profesional atiende y decide. Lee y escribe la historia clínica de sus pacientes, "
        "registra hallazgos, planes y recetas, y aprueba el conocimiento de su especialidad. El "
        "acceso clínico exige relación asistencial con el paciente: tener el permiso no abre "
        "todas las historias."
    ),
    responsabilidades=(
        "Registrar cada atención en la historia, con su versión y autoría.",
        "Confirmar personalmente cada receta antes de que genere tomas.",
        "Atender las alertas de adherencia de sus pacientes.",
        "Revisar y aprobar los documentos clínicos que respondan a pacientes.",
    ),
    limites=(
        "La IA no crea, modifica ni suspende recetas, dosis ni diagnósticos: son decisiones suyas.",
        "Sin relación asistencial no hay acceso clínico, salvo un acceso de emergencia declarado.",
        "La firma electrónica con validez jurídica todavía no está implementada.",
    ),
    secciones=(
        _s(
            "profesional.agente-ficha",
            "Apoyarse en el agente mientras revisa el expediente",
            "/pacientes",
            "Consultar la información autorizada y gestionar la agenda sin abandonar el historial.",
            (
                "Desde la ficha de la persona atendida, mantenga abierta Historia y recetas y despliegue Agente del paciente.",
                "Use Resumen clínico para revisar lo registrado dentro de su especialidad y relación asistencial; Protocolos consulta únicamente documentos aprobados y vigentes.",
                "Escoja una cita propia de esta ficha antes de preparar cambios; revise la propuesta y confirme expresamente la operación.",
            ),
            (
                "El resumen clínico se procesa localmente: no se incorpora al contexto del modelo externo.",
                "Las decisiones sobre diagnósticos, medicamentos y tratamientos siguen bajo su responsabilidad profesional.",
            ),
            requiere=("paciente.leer_administrativo",),
        ),
        _s(
            "profesional.periodontograma",
            "Medir y conservar controles periodontales",
            "/pacientes",
            "El profesional dental documenta seis sitios por pieza sin alterar controles anteriores.",
            (
                "Abra la ficha del paciente, seleccione la cita de atención y elija Periodontograma en las herramientas de su especialidad dental.",
                "Pulse Nuevo examen, confirme la fecha y la sede, y seleccione una pieza permanente para abrir sus seis sitios vestibulares y palatinos o linguales.",
                "Ingrese profundidad, margen gingival firmado, sangrado, placa y supuración; marque Sin evaluar cuando no haya medición. El NIC se calcula como profundidad más margen.",
                "Registre movilidad, furcación, ausencia o implante según corresponda; pulse Aplicar pieza, escriba el motivo y guarde el examen.",
                "Para corregir su último control, abra Corregir / anular y conserve el motivo; Anular control conserva el original con una nueva versión.",
                "Elija otro control en Comparar con para los sitios comunes y use Descargar PDF para conservar el registro completo.",
            ),
            (
                "Periodontograma e índice de placa pertenecen a odontología; el facegrama se ofrece en salud estética según los módulos concedidos.",
                "El margen es positivo apical y negativo coronal. Los colores ordenan profundidades y no emiten un diagnóstico.",
                "Solo el autor corrige un control vigente; N3 necesita permiso sensible y no se puede rebajar al corregir.",
            ),
            requiere=("paciente.leer_administrativo", "odontograma.escribir"),
        ),
        _s(
            "profesional.fotos-registro",
            "Conservar evidencia visual de la consulta",
            "/historia-clinica",
            "Asociar fotografías a la versión clínica que realmente documentan.",
            (
                "En el editor de evolución, receta propia o evaluación, seleccione archivos JPEG, PNG o WebP o capture desde la cámara del dispositivo.",
                "Revise la vista previa y añada una descripción antes de guardar; cada imagen debe ocupar como máximo 10 MB.",
                "En el registro guardado abra Fotos y adjuntos para ampliar sus imágenes; no adjunte evidencia a controles periodontales ya corregidos.",
            ),
            (
                "Las imágenes mantienen clínica, paciente, especialidad y sensibilidad del registro; una fotografía no amplía el acceso del profesional.",
            ),
            requiere=("historia_clinica.leer", "imagen_clinica.cargar"),
        ),
        _s(
            "profesional.analitica-local",
            "Revisar la evolución operativa de su consulta",
            "/analitica",
            "Separar observaciones, estimaciones y propuestas administrativas de su ámbito profesional.",
            (
                "Desde Analítica IA, examine los gráficos de atención y espera de sus turnos autorizados.",
                "En la vista predictiva abra Datos y metodología para comprobar las fechas de evaluación y el error frente a la referencia.",
                "Use las sugerencias administrativas como preparación de una revisión propia; ningún gráfico cambia un tratamiento ni indica una dosis.",
            ),
            (
                "El entrenamiento necesita al menos 56 días de historia y 42 observaciones válidas; una banda empírica representa errores observados, no certeza clínica.",
            ),
            requiere=("dashboard.leer",),
        ),
        _s(
            "profesional.ficha-integral",
            "Trabajar desde la atención de origen",
            "/pacientes",
            "Reunir la atención clínica en la ficha conservando sede y especialidad.",
            (
                "Abra la ficha del paciente desde su cita o desde Pacientes y elija Atención y documentos.",
                "Compruebe la especialidad indicada bajo su rol al elegir el acceso local y junto a su nombre en la sesión; corresponde a su perfil profesional.",
                "Seleccione la cita de referencia: sus notas nuevas y documentos conservarán esa cita y sede.",
                "Pulse Elegir qué registrar: odontología muestra Odontograma y Periodoncia; salud estética muestra Faciograma. Evolución, documentos y recetas dependen de sus permisos.",
            ),
            (
                "Cambiar de cita recarga el espacio clínico; una especialidad no asignada permanece restringida.",
            ),
            requiere=("historia_clinica.leer", "agenda.leer"),
        ),
        _s(
            "profesional.facial",
            "Registrar y versionar el faciograma",
            "/pacientes",
            "Documentar evaluación y seguimiento estético sobre un rostro frontal.",
            (
                "En el acceso local, elija su especialidad y pulse Profesional de salud; cada cuenta conserva su perfil y sus permisos. En producción ingrese con su cuenta asignada.",
                "Seleccione la cita de referencia para conservar sede y especialidad; la selección se mantiene al pasar a Atención y documentos o Documentos y PDF.",
                "En una ficha de salud estética, elija Faciograma: pulse directamente una zona de la ilustración para abrir su evaluación; indique observación, estado y procedimiento registrado por usted.",
                "Pulse Actualizar zona, indique el motivo y Guardar versión; editar conserva las versiones anteriores. Solo el autor edita y anula su evaluación.",
                "Descargue el PDF para obtener las observaciones y una página con el mapa de las 23 zonas.",
            ),
            (
                "El gráfico documenta zonas; no indica puntos de inyección ni propone tratamientos.",
                "El autor modifica sus registros; el contenido N3 requiere permiso sensible.",
            ),
            requiere=("historia_clinica.leer", "historia_clinica.escribir"),
        ),
        _s(
            "profesional.emision-documental",
            "Emitir PDFs y solicitar entrega privada",
            "/pacientes",
            "Preparar presupuestos, cotizaciones y copias de recetas confirmadas.",
            (
                "En la ficha del paciente, abra Documentos y PDF y pulse Crear documento; complete conceptos, cantidades, precios, moneda y vigencia del presupuesto o cotización.",
                "Para una receta, seleccione Receta confirmada; su pauta y firmante se copian del registro confirmado, sin editar medicamentos en el documento.",
                "Guarde la versión y use Descargar PDF; desde Planes también puede guardar un presupuesto y descargar su archivo.",
                "Antes de Enviar por WhatsApp, revise teléfono y consentimiento Documentos por WhatsApp; confirme el destinatario en la ventana.",
                "Consulte la entrega en Mensajes: sandbox registra una simulación; con proveedor configurado, el paciente recibe un enlace privado con vigencia de siete días.",
            ),
            (
                "El enlace exige fecha de nacimiento registrada o cuatro caracteres del documento si falta esa fecha; caduca y se bloquea tras cinco fallos.",
                "Editar o anular invalida los enlaces anteriores. Los registros faciales y documentos N3 se entregan presencialmente.",
                "El PDF no sustituye una factura ni incorpora firma electrónica certificada.",
            ),
            requiere=("historia_clinica.leer", "historia_clinica.escribir", "receta.leer"),
        ),
        _s(
            "profesional.jornada",
            "Su jornada en la Agenda",
            "/agenda",
            "Seguir el recorrido de cada paciente desde la llegada hasta el cierre de la atención.",
            (
                "En Agenda, filtre por su nombre para ver solo sus citas del día.",
                "Cuando el paciente pase al consultorio, inicie la atención: así se mide la espera real.",
                "Al terminar, marque la cita como completada.",
            ),
            ("Solo se puede iniciar la atención de una cita con llegada registrada.",),
            requiere=("agenda.leer", "cita.iniciar_atencion", "cita.completar"),
        ),
        _s(
            "profesional.historia",
            "Abrir la historia clínica de un paciente",
            "/historia-clinica",
            "Consultar antecedentes, alergias, notas e imágenes antes de atender.",
            (
                "En Historia clínica, elija al paciente; el resumen muestra alergias y antecedentes "
                "activos primero.",
                "Si el sistema indica que no tiene acceso clínico, es que no consta relación "
                "asistencial con esa persona.",
                "Revise desde su especialidad; las notas, imágenes, planes y formularios de otras áreas requieren un ámbito concedido expresamente.",
            ),
            (
                "Cada lectura de la historia queda registrada en la auditoría.",
                "Compartir paciente o especialidad permite consultar lo autorizado; las notas y el Formulario 033 de un colega conservan su autor y no admiten su corrección.",
            ),
            requiere=("historia_clinica.leer",),
        ),
        _s(
            "profesional.notas",
            "Escribir y corregir notas de evolución",
            "/historia-clinica",
            "Dejar constancia de la atención sin borrar nunca lo anterior.",
            (
                "Escriba la nota de evolución de la consulta y guárdela.",
                "Para corregir, cree una nueva versión e indique el motivo; la versión anterior se "
                "conserva con su autor y fecha.",
                "Registre alergias y antecedentes desde el resumen clínico; una alergia duplicada "
                "activa se rechaza.",
            ),
            ("Las notas no se borran: la historia es de solo anexión.",),
            requiere=("historia_clinica.leer", "historia_clinica.escribir"),
        ),
        _s(
            "profesional.sensible",
            "Información de sensibilidad alta (N3)",
            "/historia-clinica",
            "Proteger lo que exige más reserva dentro de la propia historia.",
            (
                "Al escribir una nota, antecedente o plan, márquelo como N3 si su contenido lo exige.",
                "Solo quien tiene el permiso de lectura sensible verá esos registros; la auditoría "
                "los marca como acceso reforzado.",
            ),
            ("Una corrección no puede bajar el nivel de un registro N3.",),
            requiere=("historia_clinica.leer", "historia_clinica.leer_sensible"),
        ),
        _s(
            "profesional.odontograma",
            "Registrar hallazgos en el odontograma",
            "/historia-clinica",
            "Mantener el mapa dental FDI del paciente con historial por pieza y cara.",
            (
                "Abra el odontograma y elija la pieza; con el teclado, recorra sus caras con las flechas.",
                "Registre el hallazgo con Enter o desde el formulario alternativo.",
                "Consulte el historial de la pieza para ver los cambios y procedimientos anteriores.",
            ),
            (
                "Si otra persona guardó antes, el sistema avisa del conflicto en vez de sobrescribir.",
            ),
            requiere=("odontograma.leer", "odontograma.escribir"),
        ),
        _s(
            "profesional.planes",
            "Planes de tratamiento y presupuesto",
            "/historia-clinica",
            "Proponer un plan por fases, presupuestarlo y agendar sus procedimientos.",
            (
                "Cree el plan con sus procedimientos y piezas, o parta de una plantilla.",
                "Propóngalo y genere la vista de presupuesto para imprimir o guardar en PDF.",
                "Registre la constancia del documento firmado en la clínica cuando el paciente acepte.",
                "Desde el plan, agende cada procedimiento de la siguiente fase.",
            ),
            (
                "Un procedimiento no admite dos citas activas a la vez.",
                "La firma electrónica del presupuesto todavía no está disponible.",
            ),
            requiere=("plan_tratamiento.leer", "plan_tratamiento.escribir"),
        ),
        _s(
            "profesional.imagenes",
            "Radiografías y fotos clínicas",
            "/historia-clinica",
            "Guardar y comparar imágenes por tipo y por pieza.",
            (
                "En la galería del paciente, cargue la imagen e indique su tipo y la pieza si aplica.",
                "Filtre por tipo o pieza y compare dos imágenes lado a lado.",
                "Para anular una imagen, indique el motivo: no se elimina, queda anulada.",
            ),
            ("En producción, las cargas se rechazan si el antivirus no está disponible.",),
            requiere=("imagen_clinica.leer", "imagen_clinica.cargar"),
        ),
        _s(
            "profesional.recetas",
            "Recetas y calendario de tomas",
            "/historia-clinica",
            "Prescribir con un calendario de tomas que solo nace de su confirmación.",
            (
                "Cree la receta con medicamento, dosis, vía y frecuencia.",
                "Confírmela usted: solo una receta confirmada genera el calendario de tomas.",
                "Confirme, sustituya o suspenda únicamente sus recetas o aquellas cuya firma le haya sido delegada; la sustitución conserva al responsable original.",
                "Para cambiarla, cree una nueva versión; las tomas futuras pendientes se cancelan y "
                "se reprograman con la nueva confirmación.",
            ),
            (
                "Los medicamentos «cuando sea necesario» no se convierten en horarios fijos.",
                "Firmar por otro profesional exige una delegación vigente registrada por la "
                "administración.",
            ),
            requiere=("receta.leer", "receta.crear", "receta.confirmar"),
        ),
        _s(
            "profesional.adherencia",
            "Seguimiento de medicación y alertas",
            "/medicamentos",
            "Ver si sus pacientes siguen el tratamiento y actuar sobre las alertas.",
            (
                "En Medicación y adherencia, revise las tomas registradas y omitidas por receta.",
                "Atienda las alertas abiertas: el sistema mantiene una sola por receta.",
                "Programe un control posterior cuando el caso lo requiera.",
            ),
            (
                "Una alerta indica omisiones registradas; no clasifica la gravedad ni sugiere conducta.",
            ),
            requiere=("receta.leer", "adherencia.leer", "alerta_adherencia.atender"),
        ),
        _s(
            "profesional.anamnesis",
            "Anamnesis y Formulario 033",
            "/historia-clinica",
            "Capturar la anamnesis configurada por la clínica y el formulario de las secciones A a P.",
            (
                "Abra los formularios de anamnesis desde el resumen clínico y responda las preguntas "
                "publicadas.",
                "En el Formulario 033, vincule cita, nota u odontograma solo cuando corresponda.",
                "Imprima la copia A4 desde el propio formulario; la exportación queda auditada.",
            ),
            (
                "El diseño del formulario no está cotejado con el anexo oficial: no se afirma validez "
                "jurídica.",
            ),
            requiere=("historia_clinica.leer", "historia_clinica.escribir"),
        ),
        _s(
            "profesional.emergencia",
            "Acceso clínico de emergencia",
            "/historia-clinica",
            "Atender a un paciente sin relación asistencial previa cuando no puede esperar.",
            (
                "Si la historia indica que no tiene acceso clínico, solicite el acceso de emergencia.",
                "Escriba el motivo con claridad: lo revisará la administración.",
            ),
            (
                "El acceso dura 30 minutos y queda auditado.",
                "La administración recibe un aviso dentro de la plataforma para revisarlo.",
            ),
            requiere=("historia_clinica.leer", "acceso_emergencia.solicitar"),
        ),
        _s(
            "profesional.documentos",
            "Cargar y aprobar documentos de conocimiento",
            "/conocimiento",
            "Que las respuestas a pacientes salgan solo de textos revisados por usted.",
            (
                "Cargue el documento en texto, Word o PDF; queda en borrador.",
                "Revíselo y apruébelo; solo entonces es recuperable por el asistente y el agente.",
                "Para modificar un documento aprobado, devuélvalo primero a borrador y apruebe la "
                "nueva versión.",
            ),
            ("El texto de un documento es dato citado: no puede dar órdenes al agente.",),
            requiere=("conocimiento.leer", "conocimiento.cargar", "conocimiento.aprobar"),
        ),
        _s(
            "profesional.asistente",
            "El asistente del equipo",
            "/asistente",
            "Encontrar rápido citas, resúmenes y documentos aprobados.",
            (
                "Pida, por ejemplo, sus citas de hoy o el resumen de un paciente con quien tiene "
                "relación asistencial.",
                "Siga los enlaces de la respuesta para actuar en la pantalla correspondiente.",
            ),
            ("El asistente no toma decisiones clínicas; solo crea borradores.",),
            alguno=("agenda.leer", "conocimiento.leer", "historia_clinica.leer"),
        ),
    ),
)


# ---------------------------------------------------------------------------
#  Asistente clinico
# ---------------------------------------------------------------------------
_ASISTENTE = ManualSistema(
    rol="asistente",
    titulo="Manual del Asistente clínico",
    introduccion=(
        "El asistente prepara el sillón, acompaña el recorrido del paciente, toma radiografías y "
        "fotos y sigue la medicación. Consulta el odontograma y el plan para preparar cada "
        "procedimiento, pero no los modifica ni lee las notas de evolución."
    ),
    responsabilidades=(
        "Que el paciente avance por el recorrido sin esperas invisibles.",
        "Que cada imagen quede cargada en la ficha correcta y con su pieza.",
        "Que las tomas y las alertas de medicación tengan seguimiento.",
    ),
    limites=(
        "No lee notas de evolución ni escribe en la historia clínica.",
        "No registra hallazgos en el odontograma ni modifica planes.",
        "No cambia horarios, dosis ni medicamentos: eso es del profesional.",
    ),
    secciones=(
        _s(
            "asistente.agente-ficha",
            "Preparar la atención con apoyo del agente contextual",
            "/pacientes",
            "Ayudar al responsable con consultas permitidas sobre la persona que está atendiendo.",
            (
                "Abra la ficha asignada y active el panel Agente del paciente para conservar visible el recorrido de atención.",
                "Consulte el resumen disponible o las citas según las autorizaciones de su cuenta; si una función no aparece, solicite al responsable revisarla.",
                "Ante un cambio administrativo permitido, lea la propuesta completa y elija confirmarla o descartarla; una sesión nueva pierde los borradores pendientes.",
            ),
            (
                "El panel no otorga herramientas dentales o estéticas de otra especialidad ni permite cambiar registros de otro autor.",
            ),
            requiere=("paciente.leer_administrativo",),
        ),
        _s(
            "asistente.periodoncia-lectura",
            "Preparar la consulta con el control dental disponible",
            "/pacientes",
            "Consultar mediciones dentales de su ámbito como apoyo al especialista.",
            (
                "Busque al paciente en Pacientes y abra las herramientas que su especialidad habilita.",
                "Si está concedida Periodoncia, seleccione el control periodontal y cambie entre las vistas vestibular y palatina o lingual.",
                "Consulte tabla, historial y PDF para preparar la revisión con el autor; la ausencia de un valor significa que no fue evaluado.",
            ),
            (
                "El asistente consulta el periodontograma y el plan; los botones para registrar, corregir o anular requieren permiso de escritura del profesional.",
            ),
            requiere=("paciente.leer_administrativo", "odontograma.leer"),
        ),
        _s(
            "asistente.fotos-perfil",
            "Fotografiar la identificación al preparar la atención",
            "/pacientes",
            "Mantener una identificación visual administrativa sin editar mediciones clínicas.",
            (
                "En el alta de paciente, use Elegir foto para un archivo de identificación o Tomar foto para una cámara compatible.",
                "Confirme que la vista previa corresponde a la persona seleccionada y guarde la ficha.",
                "Las evidencias asistenciales generales se registran en Imágenes clínicas cuando su módulo y relación asistencial lo permiten.",
            ),
            (
                "Una fotografía de perfil es administrativa; no sustituye el consentimiento ni acredita la identidad por sí sola.",
            ),
            requiere=("paciente.crear",),
        ),
        _s(
            "asistente.contexto",
            "Comprobar la atención asignada antes del seguimiento",
            "/pacientes",
            "Identificar la cita correcta antes de acompañar una indicación confirmada.",
            (
                "En la ficha, use Atención y compruebe el especialista y la sede de la cita elegida.",
                "Revise Recetas con su permiso de lectura; para corregir una pauta o emitir su PDF solicite intervención del profesional firmante.",
            ),
            (
                "Asistencia no puede editar el faciograma, presupuestos clínicos ni las dosis de una receta.",
            ),
            requiere=("paciente.leer_administrativo", "agenda.leer", "receta.leer"),
        ),
        _s(
            "asistente.recorrido",
            "Acompañar el recorrido del paciente",
            "/agenda",
            "Mover al paciente de la sala al sillón y cerrar la atención a tiempo.",
            (
                "Registre la llegada si Recepción no lo hizo y avise al profesional.",
                "Al pasar al sillón, inicie la atención; al despedir al paciente, marque la cita "
                "como completada.",
            ),
            ("Sin llegada registrada no se puede iniciar la atención.",),
            requiere=(
                "agenda.leer",
                "cita.registrar_llegada",
                "cita.iniciar_atencion",
                "cita.completar",
            ),
        ),
        _s(
            "asistente.citas",
            "Dar o mover citas de seguimiento",
            "/agenda",
            "Agendar el siguiente control antes de que el paciente se vaya.",
            (
                "Desde Agenda, busque un hueco del profesional que indicó el control.",
                "Para mover una cita existente, use Reprogramar: no cancele y cree otra.",
            ),
            requiere=("agenda.leer", "cita.crear", "cita.reprogramar"),
        ),
        _s(
            "asistente.imagenes",
            "Cargar radiografías y fotos",
            "/historia-clinica",
            "Dejar la imagen disponible para el profesional en la ficha correcta.",
            (
                "Abra la galería del paciente y cargue la imagen con su tipo.",
                "Indique la pieza dental cuando la imagen sea de una pieza concreta.",
                "Compruebe en la galería que la imagen quedó en el paciente correcto.",
            ),
            (
                "Solo verá pacientes con los que conste relación asistencial.",
                "La imagen se guarda cifrada y sin metadatos de la cámara.",
            ),
            requiere=("imagen_clinica.leer", "imagen_clinica.cargar"),
        ),
        _s(
            "asistente.preparar",
            "Preparar el sillón con el odontograma y el plan",
            "/historia-clinica",
            "Saber qué procedimiento toca y en qué piezas antes de que entre el paciente.",
            (
                "Consulte el odontograma del paciente para ubicar las piezas del día.",
                "Revise el plan de tratamiento y la fase vigente para preparar el material.",
            ),
            (
                "La consulta es de solo lectura: cualquier hallazgo nuevo lo registra el profesional.",
            ),
            requiere=("odontograma.leer", "plan_tratamiento.leer"),
        ),
        _s(
            "asistente.medicacion",
            "Registrar tomas y atender alertas",
            "/medicamentos",
            "Acompañar la adherencia sin intervenir en la prescripción.",
            (
                "En Medicación y adherencia, marque cada toma como registrada u omitida según lo "
                "informado.",
                "Atienda las alertas abiertas y derive al profesional lo que requiera su criterio.",
            ),
            (
                "No sugiera duplicar una toma omitida ni interprete reacciones: derive al profesional.",
            ),
            requiere=("receta.leer", "adherencia.leer", "alerta_adherencia.atender"),
        ),
        _s(
            "asistente.fichas",
            "Datos de contacto del paciente",
            "/pacientes",
            "Corregir teléfono o datos administrativos que el paciente actualiza en el sillón.",
            (
                "Busque al paciente en Pacientes y abra su ficha.",
                "Actualice el dato y guarde; si la persona es nueva, regístrela.",
            ),
            requiere=("paciente.leer_administrativo", "paciente.crear", "paciente.editar"),
        ),
        _s(
            "asistente.espera",
            "Ofrecer huecos a quien espera",
            "/lista-espera",
            "Aprovechar un sillón que queda libre por una cancelación.",
            (
                "Consulte Lista de espera cuando se libere un turno del profesional.",
                "Si una oferta figura como llamada pendiente, llame al paciente antes de que venza.",
            ),
            requiere=("lista_espera.gestionar",),
        ),
        _s(
            "asistente.reportes",
            "Reportes de tratamiento de los pacientes",
            "/conversaciones",
            "Ver los problemas con el tratamiento que los pacientes reportaron por mensaje.",
            (
                "En Atención de mensajes, revise los reportes de tratamiento pendientes.",
                "Confirme la revisión cuando el profesional ya esté informado.",
            ),
            ("Confirmar la revisión no clasifica la gravedad ni el resultado clínico.",),
            requiere=("conversacion.leer", "alerta_adherencia.atender"),
        ),
    ),
)


# ---------------------------------------------------------------------------
#  Administracion de clinica
# ---------------------------------------------------------------------------
_ADMINISTRADOR = ManualSistema(
    rol="administrador_clinica",
    titulo="Manual de Administración de la clínica",
    introduccion=(
        "La administración configura la clínica y su equipo: perfil, sedes, catálogo, horarios, "
        "cuentas, roles e integraciones. Supervisa la operación con el panel y revisa los accesos "
        "de emergencia. Por diseño, no tiene acceso al contenido de la historia clínica."
    ),
    responsabilidades=(
        "Que cada persona tenga exactamente los accesos que su trabajo necesita.",
        "Que horarios, feriados y bloqueos reflejen la disponibilidad real.",
        "Que las credenciales de las integraciones estén vigentes y bajo custodia.",
        "Revisar cada acceso de emergencia que se declare.",
    ),
    limites=(
        "Sin acceso al contenido clínico: separar administración y clínica es deliberado.",
        "Su rol exige segundo factor; sin él, ninguna operación se completa.",
        "Guardar una credencial no demuestra que el servicio externo esté conectado.",
    ),
    secciones=(
        _s(
            "administrador.agente-ficha",
            "Supervisar gestiones del agente desde una ficha",
            "/pacientes",
            "Coordinar operaciones de la clínica con confirmación humana y permisos vigentes.",
            (
                "Localice al paciente desde el listado y despliegue su agente para verificar exclusivamente las citas y pagos de esa ficha.",
                "Para una reserva nueva, complete el contexto de búsqueda y seleccione uno de los horarios que devuelve la agenda interna.",
                "Autorice la propuesta después de revisar paciente, horario y motivo; si cambian sus accesos, abra una conversación nueva.",
            ),
            (
                "Administración utiliza datos operativos; este panel no agrega lectura clínica a su rol.",
                "Funciones locales indica que todavía no se ha configurado un proveedor conversacional para la clínica.",
            ),
            requiere=("paciente.leer_administrativo",),
        ),
        _s(
            "administrador.aprendizaje",
            "Supervisar indicadores y aprendizaje de la clínica",
            "/analitica",
            "Dirigir revisiones operativas con series calculadas de registros autorizados.",
            (
                "Seleccione un rango de 90, 180 o 365 días y un horizonte de 7, 14 o 30 días en Analítica IA.",
                "Descriptivo muestra datos observados; Predictivo informa modelo, observaciones y error; Prescriptivo presenta acciones administrativas para revisión humana.",
                "Compare el error del modelo con la referencia y trate En evaluación como un resultado experimental.",
                "Actualice regularmente el análisis para capturar pagos pendientes, alertas y otros estados; los días sin captura permanecen desconocidos y un cambio de ámbito inicia una serie distinta.",
            ),
            (
                "Los algoritmos se ajustan localmente sin claves de proveedor y no ejecutan recomendaciones.",
                "Cobros y gastos se muestran solo con permiso financiero; los filtros por especialidad no atribuyen gastos generales a un especialista.",
            ),
            requiere=("dashboard.leer",),
        ),
        _s(
            "administrador.respaldos",
            "Completar registros de gestión con fotografías",
            "/gastos",
            "Conservar respaldos de gastos y referencias visuales del catálogo y del equipo.",
            (
                "En Registrar gasto agregue fotografías del comprobante y describa su contenido antes de confirmar.",
                "Desde la tabla de gastos abra Fotos y adjuntos para ampliar o retirar una imagen con un motivo de ocho caracteres como mínimo.",
                "En los formularios de personal, servicios, especialidades y consultorios utilice el selector de fotografías para acompañar el registro administrativo.",
            ),
            (
                "Se admiten hasta veinte imágenes vigentes por registro; la retirada conserva trazabilidad y no elimina el historial del gasto.",
            ),
            requiere=("gasto.leer", "gasto.registrar"),
        ),
        _s(
            "administracion.crud-cuentas",
            "Actualizar identidad y retirar acceso del personal",
            "/usuarios",
            "Mantener las cuentas locales sin perder su historial de actividad.",
            (
                "Busque la persona en Usuarios y use Editar datos para corregir nombre, apellido o correo.",
                "Para una baja utilice Desactivar; Reactivar restaura el acceso con sus roles existentes.",
                "Revise la asignación de roles y el perfil profesional cuando cambie una función; editar la cuenta revoca sus sesiones abiertas.",
            ),
            (
                "Una cuenta de otra clínica o de superadministración no es editable desde esta pantalla.",
            ),
            requiere=("usuario.leer", "usuario.editar", "usuario.desactivar"),
        ),
        _s(
            "administracion.estetica",
            "Habilitar el módulo de seguimiento facial",
            "/catalogo",
            "Asignar herramientas clínicas a la especialidad estética correspondiente.",
            (
                "En Catálogo, abra Módulos de historia de la especialidad y habilite Faciograma.",
                "Vincule al especialista con su perfil y roles; configure las sedes que puede atender.",
                "En Automatizaciones revise el flujo de documentos y en Integraciones configure WhatsApp cuando disponga de una cuenta del proveedor.",
            ),
            (
                "La activación del módulo no concede por sí misma acceso a pacientes ni permisos de escritura clínica.",
            ),
            requiere=("especialidad.gestionar", "configuracion.escribir"),
        ),
        _s(
            "administracion.perfil",
            "Perfil de la clínica",
            "/configuracion",
            "Mantener nombre, identificación fiscal, contacto, idioma, moneda y zona horaria.",
            (
                "En Configuración, abra el perfil de la clínica y corrija el dato.",
                "Revise la zona horaria con cuidado: de ella depende cómo se muestran todas las horas.",
            ),
            requiere=("configuracion.escribir", "clinica.escribir"),
        ),
        _s(
            "administracion.integraciones",
            "Integraciones y credenciales",
            "/configuracion",
            "Configurar Anthropic, WhatsApp Cloud API, Google Calendar y correo saliente.",
            (
                "En Configuración, elija la integración y escriba su clave o token.",
                "Guarde: la clave se cifra en el servidor y la pantalla solo indica si existe.",
                "Para rotarla, escriba la nueva; la anterior no se copia al historial.",
            ),
            (
                "Mientras falte la credencial real, el sistema usa el adaptador de pruebas y lo declara.",
                "Ninguna respuesta de la API devuelve el valor de una clave.",
            ),
            requiere=("configuracion.escribir",),
        ),
        _s(
            "administracion.cuentas",
            "Crear cuentas y asignar roles",
            "/usuarios",
            "Dar acceso al personal nuevo con el rol y las sedes que le corresponden.",
            (
                "En Usuarios y roles, cree la cuenta con correo y una contraseña inicial.",
                "Asigne el rol y limite las sedes si la persona no trabaja en todas.",
                "Para un profesional, vincule la cuenta a su ficha del equipo clínico.",
                "Compruebe Especialidad / área en Personal; el selector Perfil profesional muestra la especialidad de cada ficha. Un perfil sin registros clínicos permite cambiarla desde Profesionales.",
            ),
            (
                "La persona deberá cambiar la contraseña inicial en su primer ingreso.",
                "Cambiar roles revoca las sesiones abiertas de esa cuenta.",
            ),
            requiere=("usuario.leer", "usuario.crear", "rol.asignar"),
        ),
        _s(
            "administracion.roles",
            "Roles propios de la clínica",
            "/usuarios",
            "Crear un rol a la medida de un puesto que no encaja en los roles base.",
            (
                "En Usuarios y roles, cree el rol con un nombre claro y una descripción del puesto.",
                "Marque solo los permisos que el puesto necesita; la matriz muestra qué abre cada uno.",
            ),
            (
                "No puede conceder permisos que usted no tiene ni permisos asistenciales.",
                "Cada rol propio recibe automáticamente su manual en Ayuda.",
            ),
            requiere=("usuario.leer", "rol.asignar"),
        ),
        _s(
            "administracion.estado",
            "Desactivar o reactivar una cuenta",
            "/usuarios",
            "Cortar el acceso de quien deja la clínica sin borrar su rastro.",
            (
                "Busque la cuenta y desactívela; sus sesiones activas se revocan al instante.",
                "Si vuelve, reactívela y revise sus roles antes de avisarle.",
            ),
            requiere=("usuario.leer", "usuario.editar", "usuario.desactivar"),
        ),
        _s(
            "administracion.equipo",
            "Equipo clínico y delegaciones de firma",
            "/equipo",
            "Mantener las fichas de los profesionales y quién firma por quién.",
            (
                "En Equipo clínico, cree o edite la ficha con especialidad, sedes y sede principal.",
                "En Delegaciones de firma, registre periodo y motivo cuando un profesional firme "
                "recetas a nombre de otro.",
            ),
            (
                "Sin delegación vigente, cada profesional firma solo sus propias recetas.",
                "Una delegación no concede acceso a notas de otras especialidades. La especialidad de un perfil con historia se conserva; para otra área cree un perfil distinto.",
            ),
            requiere=("profesional.gestionar",),
        ),
        _s(
            "administracion.catalogo",
            "Especialidades y servicios",
            "/catalogo",
            "Definir qué ofrece la clínica, cuánto dura y cuánto cuesta.",
            (
                "En Catálogo, cree la especialidad y luego sus servicios.",
                "Configure duración, preparación, precio, moneda, pago previo y tipo de consultorio.",
                "Para dejar de ofrecer algo, desactívelo; no se borra lo que ya tiene historia.",
            ),
            ("No se puede desactivar una especialidad que aún tiene servicios activos.",),
            requiere=("agenda.leer", "especialidad.gestionar", "servicio.gestionar"),
        ),
        _s(
            "administracion.horarios",
            "Horarios, feriados y disponibilidad del equipo",
            "/configuracion",
            "Que la agenda solo ofrezca huecos en los que de verdad se atiende.",
            (
                "Defina las franjas semanales de cada sede, con sus pausas.",
                "Registre los feriados de la sede o de toda la clínica.",
                "Para un profesional con horario propio, cree sus franjas con vigencia y duración de cita.",
            ),
            ("Los periodos superpuestos se rechazan.",),
            requiere=("configuracion.escribir", "agenda.configurar"),
        ),
        _s(
            "administracion.bloqueos",
            "Vacaciones, ausencias y mantenimientos",
            "/configuracion",
            "Cerrar huecos de un profesional, consultorio o sede por un motivo operativo.",
            (
                "En Configuración, registre el bloqueo con su alcance, fechas y motivo.",
                "Si hay citas activas en ese tramo, el sistema lo avisa: confirme solo tras decidir "
                "qué hacer con ellas.",
            ),
            ("El aviso de citas afectadas no muestra datos de pacientes.",),
            requiere=("configuracion.escribir", "bloqueo.gestionar"),
        ),
        _s(
            "administracion.sedes",
            "Sedes y consultorios",
            "/configuracion",
            "Mantener los datos operativos de cada sede y sus consultorios.",
            (
                "Desde Configuración, abra Sedes y edite los datos de la sede.",
                "En Catálogo, cree o desactive los consultorios de cada sede.",
            ),
            requiere=("configuracion.escribir", "sede.gestionar"),
        ),
        _s(
            "administracion.anamnesis",
            "Diseñar formularios de anamnesis",
            "/configuracion",
            "Adaptar las preguntas de anamnesis a la práctica de la clínica.",
            (
                "Cree un borrador, agregue sus preguntas y publíquelo.",
                "Para cambiar un formulario publicado, cree una versión nueva: lo ya respondido no se "
                "altera.",
            ),
            ("Este diseñador no sustituye el Formulario MSP 033.",),
            requiere=("configuracion.escribir",),
        ),
        _s(
            "administracion.automatizaciones",
            "Automatizaciones de la clínica",
            "/automatizaciones",
            "Encender o apagar los flujos automáticos de la clínica.",
            (
                "En Automatizaciones, revise qué flujos están activos y qué hace cada uno.",
                "Apague un flujo si la clínica no debe usarlo; el cambio solo afecta a esta clínica.",
            ),
            requiere=("configuracion.escribir",),
        ),
        _s(
            "administracion.panel",
            "Panel, resumen local y análisis con IA",
            "/panel",
            "Seguir la operación y pedir un análisis cuando haga falta.",
            (
                "Elija periodo y filtros; las cifras se calculan con la zona horaria de la sede.",
                "Genere el resumen local: es determinista y no sale del servidor.",
                "Si la integración de Anthropic está configurada, pida el análisis con IA.",
            ),
            (
                "Al análisis con IA solo viajan métricas agregadas, nunca nombres ni adherencia "
                "clínica.",
            ),
            requiere=("dashboard.leer", "configuracion.escribir"),
        ),
        _s(
            "administracion.emergencias",
            "Revisar accesos de emergencia",
            "/seguridad",
            "Confirmar que cada acceso clínico de emergencia estuvo justificado.",
            (
                "Abra Seguridad clínica cuando la insignia indique avisos pendientes.",
                "Lea el motivo declarado y registre la revisión.",
            ),
            requiere=("auditoria.leer",),
        ),
        _s(
            "administracion.conocimiento",
            "Publicar y archivar documentos",
            "/conocimiento",
            "Mantener vigente la base de conocimiento de la clínica.",
            (
                "Revise los borradores cargados y apruebe los que estén listos.",
                "Archive lo que ya no aplica: deja de responderse de inmediato.",
            ),
            requiere=("conocimiento.leer", "conocimiento.aprobar", "conocimiento.archivar"),
        ),
        _s(
            "administracion.campanas",
            "Campañas de promociones",
            "/promociones",
            "Preparar y autorizar campañas para pacientes.",
            (
                "Cree la campaña con su texto e imagen.",
                "Apruébela solo tras revisar que no menciona diagnósticos ni tratamientos.",
            ),
            ("Nunca se segmenta por atributos clínicos.",),
            requiere=("promocion.gestionar", "promocion.aprobar"),
        ),
        _s(
            "administracion.gastos",
            "Libro de gastos y flujo de caja",
            "/gastos",
            "Registrar cada salida de dinero y ver el resultado de caja del periodo.",
            (
                "En Gastos y caja, registre el gasto con fecha, sede, categoría, importe y método.",
                "Si un gasto se registró mal, anúlelo con el motivo y registre el correcto.",
                "Elija el periodo para comparar pagos confirmados con gastos, por día y por categoría.",
            ),
            (
                "Un gasto no se edita ni se borra: la base de datos solo admite su anulación.",
                "El resultado es de caja, no contable: no incluye devengos ni impuestos.",
            ),
            requiere=("gasto.leer", "gasto.registrar", "pago.leer"),
        ),
        _s(
            "administracion.conciliar",
            "Conciliar cargos y vencimientos",
            "/pagos",
            "Fijar el total pactado y la fecha de vencimiento de los cargos.",
            (
                "En Pagos, abra el cargo y concilie el total pactado.",
                "Fije la fecha de vencimiento cuando corresponda.",
            ),
            ("El total y la fecha solo pueden fijarse una vez; la base de datos rechaza cambios.",),
            requiere=("pago.leer", "pago.validar"),
        ),
    ),
)


# ---------------------------------------------------------------------------
#  Auditor
# ---------------------------------------------------------------------------
_AUDITOR = ManualSistema(
    rol="auditor",
    titulo="Manual de Auditoría",
    introduccion=(
        "El auditor verifica sin intervenir. Consulta la operación, los accesos y los pagos para "
        "comprobar que se cumplen las políticas de la clínica, y no tiene permisos de escritura. "
        "Puede saber qué registros clínicos existen, pero no leer su contenido."
    ),
    responsabilidades=(
        "Revisar los accesos de emergencia y su justificación.",
        "Comprobar que los accesos del personal corresponden a su función.",
        "Contrastar los resúmenes de agenda y pagos con lo informado.",
    ),
    limites=(
        "No modifica datos: su rol es de solo lectura.",
        "No lee el contenido de la historia clínica.",
        "Su rol exige segundo factor.",
    ),
    secciones=(
        _s(
            "auditor.agente-ficha",
            "Examinar consultas del agente sin alterar la agenda",
            "/pacientes",
            "Revisar los datos administrativos del expediente dentro del ámbito de auditoría.",
            (
                "Entre en una ficha autorizada y active su agente para solicitar Mis citas o Mis pagos, conservando el contexto de esa persona.",
                "Compruebe la selección de cita y los estados devueltos; los controles de reserva, cancelación o reprogramación requieren permisos adicionales.",
                "Consulte Auditoría para contrastar la apertura y las consultas del agente con el operador responsable.",
            ),
            (
                "No obtiene el contenido del historial ni del resumen clínico por tener permiso de auditoría.",
            ),
            requiere=("paciente.leer_administrativo",),
        ),
        _s(
            "auditor.evidencia-analitica",
            "Contrastar el origen de las estimaciones operativas",
            "/analitica",
            "Inspeccionar series agregadas y evidencia temporal sin acceder al contenido clínico.",
            (
                "Abra Analítica IA dentro de su sede y compruebe las definiciones de cada indicador visible.",
                "Expanda Datos y metodología y contraste los valores observados con las tablas de evaluación y pronóstico.",
                "Registre si el modelo fue evaluado localmente, es experimental o carece de historial; las recomendaciones quedan sujetas a una persona autorizada.",
            ),
            (
                "Los gráficos de aprendizaje no conceden lectura del periodontograma, recetas o fotos clínicas al auditor.",
            ),
            requiere=("dashboard.leer",),
        ),
        _s(
            "auditor.fotos-gastos",
            "Consultar los respaldos visuales del libro de gastos",
            "/gastos",
            "Revisar evidencia administrativa manteniendo sus límites de lectura.",
            (
                "Localice el gasto por fecha y categoría y pulse Fotos y adjuntos en su fila.",
                "Amplíe las imágenes autorizadas y compruebe su descripción; solicite el rastro de retirada para investigar una evidencia anulada.",
            ),
            ("El permiso de lectura del gasto no permite adjuntar ni retirar comprobantes.",),
            requiere=("gasto.leer",),
        ),
        _s(
            "auditoria.trazabilidad-registros",
            "Revisar bajas y emisiones documentales",
            "/usuarios",
            "Comprobar accesos administrativos y solicitar trazabilidad sin consultar contenido clínico.",
            (
                "En Usuarios, contraste las cuentas inactivas y los roles conservados con las bajas autorizadas por la clínica.",
                "Solicite al responsable el informe de auditoría de creación, anulación y entrega documental para contrastar autores y fechas sin incluir contenido de la historia.",
            ),
            (
                "La descarga clínica de PDFs y el gráfico facial no se habilitan para el rol auditor.",
            ),
            requiere=("auditoria.leer",),
        ),
        _s(
            "auditoria.emergencias",
            "Verificar los accesos de emergencia",
            "/seguridad",
            "Comprobar que cada acceso excepcional tuvo motivo y fue revisado.",
            (
                "En Seguridad clínica, recorra los accesos temporales utilizados.",
                "Contraste el motivo declarado con la revisión registrada por la administración.",
            ),
            requiere=("auditoria.leer",),
        ),
        _s(
            "auditoria.accesos",
            "Contrastar cuentas y roles",
            "/usuarios",
            "Confirmar que nadie conserva accesos que ya no necesita.",
            (
                "En Usuarios y roles, revise los roles y sedes de cada cuenta activa.",
                "Use la matriz de accesos para ver qué abre cada permiso.",
            ),
            ("Los cambios los hace la administración; usted documenta el hallazgo.",),
            requiere=("usuario.leer",),
        ),
        _s(
            "auditoria.indicadores",
            "Indicadores agregados",
            "/panel",
            "Observar tendencias de citas, inasistencias, espera y recuperación de turnos.",
            (
                "Ajuste el periodo y la sede para comparar cortes equivalentes.",
                "Lea las tasas junto a su conteo: una tasa sin denominador engaña.",
            ),
            ("La ocupación porcentual no se calcula sin horarios como denominador.",),
            requiere=("dashboard.leer",),
        ),
        _s(
            "auditoria.agenda",
            "Agenda en modo consulta",
            "/agenda",
            "Ver la actividad agendada y exportar sus conteos.",
            (
                "Consulte la vista de lista con los filtros del periodo auditado.",
                "Exporte el resumen CSV por fecha y estado.",
            ),
            requiere=("agenda.leer", "reporte.exportar"),
        ),
        _s(
            "auditoria.pagos",
            "Pagos y resumen financiero",
            "/pagos",
            "Contrastar estados de pago y comprobantes con lo informado.",
            (
                "Revise pagos por estado y el historial inmutable de cada uno.",
                "Exporte el resumen financiero por fecha, estado y método.",
            ),
            ("Cada descarga de comprobante queda auditada.",),
            requiere=("pago.leer", "reporte.exportar"),
        ),
        _s(
            "auditoria.caja",
            "Contrastar el flujo de caja",
            "/gastos",
            "Comprobar que los egresos registrados cuadran con los cobros del periodo.",
            (
                "En Gastos y caja, fije el periodo auditado y revise el resultado por día.",
                "Incluya los gastos anulados para ver cada corrección con su motivo.",
            ),
            ("Usted consulta; registrar o anular gastos corresponde a la administración.",),
            requiere=("gasto.leer", "pago.leer"),
        ),
        _s(
            "auditoria.automatizaciones",
            "Estado de las automatizaciones",
            "/automatizaciones",
            "Saber qué flujos automáticos están activos en la clínica.",
            (
                "Consulte la lista de flujos y su estado; la activación la cambia la administración.",
            ),
            requiere=("auditoria.leer",),
        ),
        _s(
            "auditoria.mensajes",
            "Bandeja de mensajes derivados",
            "/conversaciones",
            "Verificar que las derivaciones a una persona se atienden.",
            ("Revise los pendientes y su antigüedad en Atención de mensajes.",),
            requiere=("conversacion.leer",),
        ),
        _s(
            "auditoria.fuentes",
            "Fuentes de las respuestas",
            "/conocimiento",
            "Comprobar qué documentos están aprobados y vigentes.",
            ("Revise en Conocimiento el estado y la versión de cada documento.",),
            requiere=("conocimiento.leer",),
        ),
    ),
)


# ---------------------------------------------------------------------------
#  Superadministrador
# ---------------------------------------------------------------------------
_SUPERADMINISTRADOR = ManualSistema(
    rol="superadministrador",
    titulo="Manual de Superadministración",
    introduccion=(
        "El superadministrador opera la plataforma: registra clínicas con su sede principal y su "
        "primera cuenta de administración, agrega sucursales y asigna personal a cada clínica. "
        "No tiene acceso clínico y cada cambio de acceso queda auditado."
    ),
    responsabilidades=(
        "Dar de alta clínicas completas y coherentes en una sola operación.",
        "Asignar a cada persona la clínica, los roles y las sedes que le corresponden.",
        "Custodiar su propia cuenta: es la de mayor alcance del sistema.",
    ),
    limites=(
        "Sin acceso al contenido clínico de ninguna clínica.",
        "Su rol exige segundo factor.",
        "El acceso local de demostración no es un procedimiento para cuentas de producción.",
    ),
    secciones=(
        _s(
            "superadministrador.agente-ficha",
            "Comprobar el apoyo contextual en la clínica activa",
            "/pacientes",
            "Verificar el funcionamiento operativo del agente sin ampliar el acceso entre clínicas.",
            (
                "Seleccione una ficha accesible de la clínica de su sesión y abra Agente del paciente para probar las consultas permitidas.",
                "Revise el indicador de configuración del proveedor y contraste sus operaciones de agenda con los datos de esa clínica.",
                "Confirme cada propuesta administrativa expresamente; abrir el panel de otra persona inicia una conversación separada.",
            ),
            (
                "La administración global no concede acceso clínico ni permite reutilizar la sesión del agente de otro operador.",
            ),
            requiere=("paciente.leer_administrativo",),
        ),
        _s(
            "superadministrador.identidad-visual",
            "Registrar la imagen administrativa de una organización",
            "/plataforma/clinicas",
            "Acompañar el alta de clínica con sus referencias visuales.",
            (
                "Desde Plataforma abra Nueva clínica y complete la organización y su sede principal.",
                "Añada logo o fotografías de las instalaciones, compruebe las vistas previas y confirme la creación.",
                "Si una fotografía falla, conserve el aviso y reintente su carga sin crear otra clínica.",
            ),
            (
                "El acceso de plataforma no concede lectura de fotos de pacientes ni mediciones de una especialidad.",
            ),
            rol="superadministrador",
        ),
        _s(
            "superadministrador.analitica-plataforma",
            "Revisar el análisis desde la organización asignada",
            "/analitica",
            "Controlar la disponibilidad del análisis de la clínica activa sin mezclar organizaciones.",
            (
                "Entre en Analítica IA usando la organización autorizada de la sesión y verifique el corte y la zona horaria del resultado.",
                "Compruebe que cada gráfico declara su definición y que los indicadores aún sin historia muestran un estado de datos insuficientes.",
                "Configure los permisos administrativos del cliente desde Plataforma si necesita conceder o retirar acceso a estos módulos.",
            ),
            (
                "La analítica no es un panel global que combine datos de todas las clínicas del servidor.",
            ),
            requiere=("dashboard.leer",),
        ),
        _s(
            "plataforma.crud",
            "Editar organizaciones y gestionar bajas de cuentas",
            "/plataforma/clinicas",
            "Completar el mantenimiento global conservando referencias e historial.",
            (
                "En Organizaciones registradas, use Editar clínica para ajustar perfil, contacto, zona horaria, moneda e identificación fiscal.",
                "Desactivar clínica corta sus sesiones e impide nuevos ingresos; Reactivar clínica vuelve a permitir el acceso a sus cuentas activas.",
                "En Accesos del personal, Editar usuario actualiza su identidad; Desactivar usuario retira su acceso y Reactivar usuario lo restablece.",
                "Clínica y módulos permite reasignar organización, perfil profesional, roles y sedes; guardar sustituye los accesos anteriores.",
            ),
            (
                "La organización de superadministración y sus cuentas están protegidas frente a estas bajas.",
                "Ninguna baja elimina citas, historias, pagos ni autorías anteriores.",
            ),
            rol="superadministrador",
        ),
        _s(
            "plataforma.alta",
            "Registrar una clínica",
            "/plataforma/clinicas",
            "Crear la clínica, su sede principal y su cuenta de administración de una vez.",
            (
                "En Clínicas, use Registrar una clínica y complete los datos de la organización.",
                "Indique la sede principal y su zona horaria.",
                "Cree la cuenta de administración: deberá cambiar la contraseña al entrar.",
            ),
            ("Si un dato falla, no se crea nada: la operación es una sola transacción.",),
            rol="superadministrador",
        ),
        _s(
            "plataforma.sucursales",
            "Agregar sucursales",
            "/plataforma/clinicas",
            "Sumar sedes a una clínica existente.",
            (
                "Elija la clínica y agregue la sede con sus datos.",
                "Deje la zona horaria heredada salvo que la sede esté en otra.",
            ),
            rol="superadministrador",
        ),
        _s(
            "plataforma.personal",
            "Asignar personal a una clínica",
            "/plataforma/clinicas",
            "Dar acceso a una cuenta nueva o existente con roles y sedes.",
            (
                "En Accesos del personal, elija la persona o cree su cuenta.",
                "Asigne roles y limite las sedes cuando no deba ver todas.",
            ),
            ("El cambio reemplaza los roles anteriores y revoca las sesiones abiertas.",),
            rol="superadministrador",
        ),
        _s(
            "plataforma.configuracion",
            "Configuración de una clínica",
            "/configuracion",
            "Ayudar a una clínica con su perfil, integraciones y horarios.",
            (
                "Entre en Configuración con la clínica de su sesión.",
                "Haga solo los cambios acordados con la administración de la clínica.",
            ),
            requiere=("configuracion.escribir",),
        ),
        _s(
            "plataforma.revision",
            "Revisiones de seguridad",
            "/seguridad",
            "Atender los avisos de acceso de emergencia de la clínica en sesión.",
            ("Revise los avisos pendientes y deje constancia de la revisión.",),
            requiere=("auditoria.leer",),
        ),
    ),
)


MANUALES_SISTEMA: Final[dict[str, ManualSistema]] = {
    manual.rol: manual
    for manual in (
        _RECEPCION,
        _PROFESIONAL,
        _ASISTENTE,
        _ADMINISTRADOR,
        _AUDITOR,
        _SUPERADMINISTRADOR,
    )
}


# ---------------------------------------------------------------------------
#  Roles personalizados
# ---------------------------------------------------------------------------
# Catalogo de capacidades para componer el manual de un rol creado por una
# clinica. Redaccion neutra y distinta de la de los manuales del sistema: el
# manual de un rol propio se arma con las capacidades que su lista de
# permisos habilita, y con nada mas.
CAPACIDADES: Final[tuple[Seccion, ...]] = (
    _s(
        "capacidad.agente-contextual",
        "Utilizar apoyo acotado a un expediente",
        "/pacientes",
        "Asistir las consultas de una sola persona con las capacidades efectivas de la cuenta.",
        (
            "En una ficha habilitada, abra el agente contextual y utilice las consultas disponibles según su rol personalizado.",
            "Cuando exista una propuesta de cambio, examine sus datos antes de aprobarla; el servidor vuelve a validar sus autorizaciones.",
            "Si aparece un error de carga, use Reintentar gestión; una propuesta vence cinco minutos después de prepararse.",
        ),
        (
            "Los permisos de esta cuenta y la especialidad determinan los datos accesibles; el mensaje escrito no puede ampliarlos.",
        ),
        requiere=("paciente.leer_administrativo",),
    ),
    _s(
        "capacidad.analitica-local",
        "Analizar observaciones y pronósticos del ámbito",
        "/analitica",
        "Estudiar indicadores autorizados con modelos locales y evaluación cronológica.",
        (
            "Defina historial y horizonte antes de alternar entre los tres tipos de análisis.",
            "Compruebe muestras, cortes temporales y error antes de usar cualquier estimación.",
            "Revise las propuestas en el módulo original; cada sugerencia requiere intervención humana.",
        ),
        (
            "Los estados diarios se capturan al consultar el análisis y no se reconstruyen para días sin observación.",
        ),
        requiere=("dashboard.leer",),
    ),
    _s(
        "capacidad.periodontograma",
        "Capturar el examen periodontal de seis sitios",
        "/pacientes",
        "Registrar un examen dental versionado cuando la especialidad y los permisos lo habilitan.",
        (
            "Desde la ficha seleccione atención y abra Periodontograma si figura entre sus herramientas concedidas.",
            "Complete las mediciones por pieza, aplique sus cambios e indique un motivo para confirmar el examen.",
            "Use corrección para una nueva versión, comparación para sitios comunes y PDF para exportar.",
        ),
        (
            "La edición pertenece al autor y al módulo de periodoncia, y no está disponible en salud estética.",
        ),
        requiere=("paciente.leer_administrativo", "odontograma.escribir"),
    ),
    _s(
        "capacidad.panel",
        "Seguimiento operativo",
        "/panel",
        "Consultar indicadores agregados de la operación de la clínica.",
        (
            "Desde Panel, ajuste periodo, sede y estado para el corte que necesita.",
            "Use las tareas de hoy como lista de pendientes con plazo.",
        ),
        requiere=("dashboard.leer",),
    ),
    _s(
        "capacidad.agenda",
        "Consulta de la agenda",
        "/agenda",
        "Ver citas en vista de día, semana, mes o lista.",
        ("Cambie de vista y aplique los filtros de sede, especialidad, servicio y profesional.",),
        requiere=("agenda.leer",),
    ),
    _s(
        "capacidad.citas",
        "Alta de citas",
        "/agenda",
        "Reservar sobre huecos calculados con la disponibilidad real.",
        ("Elija un hueco libre, asocie al paciente y confirme dentro del tiempo de retención.",),
        ("El motor de base de datos impide reservar dos veces el mismo turno.",),
        requiere=("agenda.leer", "cita.crear"),
    ),
    _s(
        "capacidad.mover",
        "Cambios de cita",
        "/agenda",
        "Reprogramar o anular citas existentes.",
        (
            "Use Reprogramar para cambiar el horario sin perder el historial.",
            "Al anular, deje un motivo: el sistema lo exige.",
        ),
        alguno=("cita.reprogramar", "cita.cancelar"),
        requiere=("agenda.leer",),
    ),
    _s(
        "capacidad.recorrido",
        "Recorrido en la clínica",
        "/agenda",
        "Marcar llegada, inicio de atención, finalización o inasistencia.",
        ("Abra la cita y elija la transición que corresponda al momento real.",),
        alguno=(
            "cita.registrar_llegada",
            "cita.iniciar_atencion",
            "cita.completar",
            "cita.marcar_inasistencia",
        ),
        requiere=("agenda.leer",),
    ),
    _s(
        "capacidad.pacientes",
        "Fichas administrativas",
        "/pacientes",
        "Buscar personas por nombre, apellido o documento y consultar su ficha.",
        ("Abra la ficha desde el buscador de la cabecera o desde Pacientes.",),
        requiere=("paciente.leer_administrativo",),
    ),
    _s(
        "capacidad.pacientes_alta",
        "Alta y corrección de pacientes",
        "/pacientes",
        "Mantener los datos administrativos correctos.",
        ("Registre o edite la ficha; cada cambio deja rastro en la auditoría.",),
        requiere=("paciente.leer_administrativo",),
        alguno=("paciente.crear", "paciente.editar"),
    ),
    _s(
        "capacidad.consentimiento",
        "Preferencias de comunicación",
        "/pacientes",
        "Anotar si la persona acepta o revoca mensajes automáticos.",
        ("Desde la ficha, registre el consentimiento con la fecha en que se expresó.",),
        requiere=("paciente.leer_administrativo", "consentimiento.gestionar"),
    ),
    _s(
        "capacidad.espera",
        "Cola de espera",
        "/lista-espera",
        "Gestionar quién espera un hueco y las ofertas que requieren llamada.",
        ("Anote preferencias de fecha y franja, y llame a tiempo cuando la oferta lo indique.",),
        requiere=("lista_espera.gestionar",),
    ),
    _s(
        "capacidad.historia",
        "Lectura clínica",
        "/historia-clinica",
        "Consultar la historia de pacientes con relación asistencial.",
        ("Elija al paciente; el sistema solo abre lo que su relación asistencial permite.",),
        requiere=("historia_clinica.leer",),
    ),
    _s(
        "capacidad.medicacion",
        "Seguimiento de la medicación",
        "/medicamentos",
        "Ver recetas y el registro de tomas.",
        ("Revise tomas registradas y omitidas; las alertas abiertas aparecen primero.",),
        requiere=("receta.leer",),
    ),
    _s(
        "capacidad.conocimiento",
        "Documentos de referencia",
        "/conocimiento",
        "Consultar la base de conocimiento aprobada de la clínica.",
        ("Filtre por estado y versión para trabajar siempre con lo vigente.",),
        requiere=("conocimiento.leer",),
    ),
    _s(
        "capacidad.conocimiento_carga",
        "Borradores de conocimiento",
        "/conocimiento",
        "Subir textos para que alguien con permiso los revise y apruebe.",
        ("Cargue el archivo; quedará en borrador hasta su aprobación.",),
        requiere=("conocimiento.leer", "conocimiento.cargar"),
    ),
    _s(
        "capacidad.mensajes",
        "Derivaciones de WhatsApp",
        "/conversaciones",
        "Ver las conversaciones que pidieron una persona.",
        ("Consulte la bandeja y atienda por el canal que la clínica tenga establecido.",),
        requiere=("conversacion.leer",),
    ),
    _s(
        "capacidad.cobros",
        "Caja y saldos",
        "/pagos",
        "Consultar cargos, abonos y saldos de las citas.",
        ("Filtre por estado o por saldo vencido según la tarea.",),
        requiere=("pago.leer",),
    ),
    _s(
        "capacidad.cobros_registro",
        "Registro de abonos",
        "/pagos",
        "Anotar pagos y adjuntar su comprobante.",
        ("Registre el abono con su método y suba el comprobante en un formato admitido.",),
        requiere=("pago.leer", "pago.registrar"),
    ),
    _s(
        "capacidad.gastos",
        "Egresos de la clínica",
        "/gastos",
        "Consultar el libro de gastos dentro de las sedes del rol.",
        ("Filtre por periodo, sede o categoría; active los anulados para ver correcciones.",),
        requiere=("gasto.leer",),
    ),
    _s(
        "capacidad.gastos_registro",
        "Registro de egresos",
        "/gastos",
        "Anotar salidas de dinero y anular las erróneas con motivo.",
        (
            "Registre el egreso con su comprobante a mano; si se equivoca, anúlelo y vuelva a anotarlo.",
        ),
        requiere=("gasto.leer", "gasto.registrar"),
    ),
    _s(
        "capacidad.equipo",
        "Fichas del equipo",
        "/equipo",
        "Mantener los perfiles profesionales y las delegaciones de firma.",
        ("Edite especialidad, sedes y contacto; registre delegaciones con periodo y motivo.",),
        requiere=("profesional.gestionar",),
    ),
    _s(
        "capacidad.usuarios",
        "Directorio de cuentas",
        "/usuarios",
        "Consultar cuentas, roles y la matriz de accesos.",
        ("Use la matriz para entender qué habilita cada permiso.",),
        requiere=("usuario.leer",),
    ),
    _s(
        "capacidad.promociones",
        "Borradores de campañas",
        "/promociones",
        "Preparar campañas para que se autoricen.",
        ("Redacte la campaña sin datos clínicos y envíela a revisión.",),
        requiere=("promocion.gestionar",),
    ),
    _s(
        "capacidad.seguridad",
        "Supervisión de accesos excepcionales",
        "/seguridad",
        "Revisar los accesos clínicos de emergencia.",
        ("Lea el motivo y registre la revisión de cada aviso.",),
        requiere=("auditoria.leer",),
    ),
    _s(
        "capacidad.configuracion",
        "Ajustes de la clínica",
        "/configuracion",
        "Cambiar perfil, integraciones y formularios propios.",
        ("Haga un cambio cada vez y compruebe su efecto antes del siguiente.",),
        requiere=("configuracion.escribir",),
    ),
    _s(
        "capacidad.asistente",
        "Consultas al asistente interno",
        "/asistente",
        "Pedir información de las pantallas que el rol ya puede abrir.",
        ("Escriba la consulta en lenguaje natural y siga el enlace de la respuesta.",),
        alguno=("agenda.leer", "conocimiento.leer", "historia_clinica.leer"),
    ),
)

# Lo que un rol personalizado NO hace, en palabras de la tarea. Se anuncia
# cuando falta el permiso: saber lo que no se puede ahorra intentos que van a
# terminar en un 403.
NEGACIONES: Final[tuple[tuple[str, str], ...]] = (
    ("historia_clinica.leer", "No consulta el contenido de la historia clínica."),
    ("cita.crear", "No reserva citas nuevas."),
    ("paciente.editar", "No modifica datos de pacientes."),
    ("pago.registrar", "No registra pagos."),
    ("configuracion.escribir", "No cambia la configuración de la clínica."),
    ("rol.asignar", "No asigna roles ni accesos."),
)

LIMITES_COMUNES_PERSONALIZADO: Final[tuple[str, ...]] = (
    "Las secciones de este manual salen de los permisos del rol; si la clínica los cambia, el "
    "manual cambia con ellos.",
    "Cada pantalla vuelve a comprobar el permiso y el ámbito en el servidor.",
)
