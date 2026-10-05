"""Plantillas de los mensajes salientes.

La regla que gobierna este modulo
---------------------------------
**Ningun mensaje incluye diagnostico, medicamento ni motivo de consulta**
(CLAUDE.md, regla 10). El motivo es concreto y no es de cumplimiento
normativo: la pantalla bloqueada de un telefono es un canal publico. Un
recordatorio que diga «su cita de oncologia» lo lee quien pase por al lado en
el autobus.

Lo que un mensaje puede decir es: que hay una cita, cuando, donde y con quien.
Para lo demas, se pide al paciente que entre al sistema o que llame.

Como se hace cumplir
--------------------
1. Las plantillas se definen aqui como **texto con huecos nombrados**, no se
   componen en el codigo que envia. Todo el texto saliente esta en un solo
   archivo y se puede leer entero de una sentada.
2. `variables_permitidas` declara que huecos admite cada plantilla. Rellenar
   una plantilla con una variable no declarada es un error, no un aviso.
3. Una prueba recorre **todas** las plantillas y verifica que ninguna
   contiene, ni admite, un hueco de contenido clinico.

Sobre WhatsApp
--------------
La Cloud API solo permite iniciar conversacion con **plantillas aprobadas por
Meta**. El `nombre_meta` es el identificador de esa plantilla aprobada; el
texto de aqui es lo que se le envio a Meta para aprobar y lo que se usa en
modo sandbox. Si divergen, el envio real fallara con un error del proveedor,
y por eso conviene que el texto viva aqui y no en un panel.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.modulos.outbox.modelos import TipoMensajeOutbox

# ---------------------------------------------------------------------------
#  Variables prohibidas
# ---------------------------------------------------------------------------
# Un hueco que se llame asi no puede existir en ninguna plantilla. La lista es
# deliberadamente amplia: prefiere el falso positivo -- que se corrige
# renombrando -- a dejar pasar contenido clinico a un canal publico.
VARIABLES_PROHIBIDAS: frozenset[str] = frozenset(
    {
        "diagnostico",
        "diagnosticos",
        "medicamento",
        "medicamentos",
        "dosis",
        "tratamiento",
        "receta",
        "motivo_consulta",
        "sintoma",
        "sintomas",
        "alergia",
        "alergias",
        "antecedente",
        "antecedentes",
        "resultado",
        "resultados",
        "examen",
        "analisis",
        "nota_clinica",
        "evolucion",
    }
)

_HUECO = re.compile(r"\{(\w+)\}")


@dataclass(frozen=True, slots=True)
class Plantilla:
    """Una plantilla de mensaje saliente."""

    tipo: TipoMensajeOutbox
    # Identificador de la plantilla aprobada en Meta. Vacio para los canales
    # que no lo necesitan (correo, calendario, interno).
    nombre_meta: str
    texto: str
    variables_permitidas: frozenset[str] = field(default_factory=frozenset)
    # Cierto si el mensaje puede iniciar una conversacion. En WhatsApp, fuera
    # de la ventana de 24 horas solo las plantillas aprobadas pueden hacerlo.
    inicia_conversacion: bool = True

    def __post_init__(self) -> None:
        huecos = set(_HUECO.findall(self.texto))
        declaradas = set(self.variables_permitidas)

        if huecos - declaradas:
            raise ValueError(
                f"La plantilla {self.tipo.value} usa huecos no declarados: "
                f"{sorted(huecos - declaradas)}"
            )
        if declaradas - huecos:
            # Una variable declarada y no usada suele ser un renombrado a
            # medias, y deja la plantilla aceptando datos que no muestra.
            raise ValueError(
                f"La plantilla {self.tipo.value} declara huecos que no usa: "
                f"{sorted(declaradas - huecos)}"
            )

        prohibidas = declaradas & VARIABLES_PROHIBIDAS
        if prohibidas:
            raise ValueError(
                f"La plantilla {self.tipo.value} admite variables clinicas: "
                f"{sorted(prohibidas)}. Ningun mensaje puede llevar diagnostico, "
                "medicamento ni motivo de consulta (CLAUDE.md, regla 10)."
            )

    def redactar(self, **variables: object) -> str:
        """Rellena la plantilla.

        Una variable no declarada es un error y no se ignora en silencio:
        ignorarla permitiria que quien anada un dato clinico al diccionario
        creyera que se esta enviando, o -- peor -- que se enviara si alguien
        anade el hueco despues.
        """
        sobrantes = set(variables) - set(self.variables_permitidas)
        if sobrantes:
            raise ValueError(
                f"La plantilla {self.tipo.value} no admite estas variables: {sorted(sobrantes)}."
            )
        faltantes = set(self.variables_permitidas) - set(variables)
        if faltantes:
            raise ValueError(
                f"Faltan variables para la plantilla {self.tipo.value}: {sorted(faltantes)}."
            )
        return self.texto.format(**variables)


# ---------------------------------------------------------------------------
#  Catalogo
# ---------------------------------------------------------------------------
# Todo el texto que sale de este sistema hacia un paciente esta aqui.
#
# Se escribe en usted y sin tecnicismos. Quien lo recibe puede tener 80 anos y
# estar leyendolo en la pantalla de bloqueo.
PLANTILLAS: dict[TipoMensajeOutbox, Plantilla] = {
    TipoMensajeOutbox.CITA_CONFIRMACION: Plantilla(
        tipo=TipoMensajeOutbox.CITA_CONFIRMACION,
        nombre_meta="cita_confirmacion",
        texto=(
            "Hola {nombre}. Su cita en {clinica} quedo agendada para el {fecha} a las "
            "{hora}, en {sede}, con {profesional}.\n\n"
            "Si no puede asistir, responda CANCELAR o llame al {telefono_clinica}."
        ),
        variables_permitidas=frozenset(
            {"nombre", "clinica", "fecha", "hora", "sede", "profesional", "telefono_clinica"}
        ),
    ),
    TipoMensajeOutbox.CITA_RECORDATORIO_DIA_ANTES: Plantilla(
        tipo=TipoMensajeOutbox.CITA_RECORDATORIO_DIA_ANTES,
        nombre_meta="cita_recordatorio_dia",
        texto=(
            "Hola {nombre}. Le recordamos su cita de manana {fecha} a las {hora} en "
            "{sede}, con {profesional}.\n\n"
            "Responda CONFIRMAR para confirmar su asistencia, o CANCELAR si no podra ir."
        ),
        variables_permitidas=frozenset({"nombre", "fecha", "hora", "sede", "profesional"}),
    ),
    TipoMensajeOutbox.CITA_RECORDATORIO_HORAS_ANTES: Plantilla(
        tipo=TipoMensajeOutbox.CITA_RECORDATORIO_HORAS_ANTES,
        nombre_meta="cita_recordatorio_horas",
        texto=(
            "Hola {nombre}. Su cita es hoy a las {hora} en {sede}. Le esperamos unos minutos antes."
        ),
        variables_permitidas=frozenset({"nombre", "hora", "sede"}),
    ),
    TipoMensajeOutbox.CITA_CANCELACION: Plantilla(
        tipo=TipoMensajeOutbox.CITA_CANCELACION,
        nombre_meta="cita_cancelacion",
        texto=(
            "Hola {nombre}. Su cita del {fecha} a las {hora} en {sede} quedo cancelada.\n\n"
            "Para agendar otra, responda a este mensaje o llame al {telefono_clinica}."
        ),
        variables_permitidas=frozenset({"nombre", "fecha", "hora", "sede", "telefono_clinica"}),
    ),
    TipoMensajeOutbox.CITA_REPROGRAMACION: Plantilla(
        tipo=TipoMensajeOutbox.CITA_REPROGRAMACION,
        nombre_meta="cita_reprogramacion",
        texto=(
            "Hola {nombre}. Su cita se movio al {fecha} a las {hora}, en {sede}, con "
            "{profesional}.\n\n"
            "Si ese horario no le sirve, responda a este mensaje."
        ),
        variables_permitidas=frozenset({"nombre", "fecha", "hora", "sede", "profesional"}),
    ),
    TipoMensajeOutbox.OFERTA_TURNO: Plantilla(
        tipo=TipoMensajeOutbox.OFERTA_TURNO,
        nombre_meta="oferta_turno",
        texto=(
            "Hola {nombre}. Se libero un turno el {fecha} a las {hora} en {sede}, con "
            "{profesional}.\n\n"
            "Responda SI para tomarlo. La oferta vence a las {vence_hora}; despues se "
            "ofrecera a otra persona."
        ),
        variables_permitidas=frozenset(
            {"nombre", "fecha", "hora", "sede", "profesional", "vence_hora"}
        ),
    ),
    TipoMensajeOutbox.OFERTA_EXPIRADA: Plantilla(
        tipo=TipoMensajeOutbox.OFERTA_EXPIRADA,
        nombre_meta="oferta_expirada",
        texto=(
            "Hola {nombre}. El turno que le ofrecimos ya no esta disponible. "
            "Sigue en la lista de espera y le avisaremos cuando se libere otro."
        ),
        variables_permitidas=frozenset({"nombre"}),
    ),
    TipoMensajeOutbox.OFERTA_PERDIDA: Plantilla(
        tipo=TipoMensajeOutbox.OFERTA_PERDIDA,
        nombre_meta="oferta_perdida",
        texto=(
            "Hola {nombre}. Ese turno acaba de tomarlo otra persona. "
            "Sigue en la lista y le avisaremos en cuanto se libere otro."
        ),
        variables_permitidas=frozenset({"nombre"}),
    ),
    TipoMensajeOutbox.TOMA_RECORDATORIO: Plantilla(
        tipo=TipoMensajeOutbox.TOMA_RECORDATORIO,
        nombre_meta="toma_recordatorio",
        # NO dice que medicamento. Es el caso mas tentador de todos -- seria
        # mas util -- y el mas grave: el nombre de un medicamento en una
        # pantalla de bloqueo revela la condicion de quien lo toma.
        texto=(
            "Hola {nombre}. Es hora de una de las tomas que le indico su profesional.\n\n"
            "Responda TOMADA cuando la haya hecho. Puede ver el detalle en {enlace}."
        ),
        variables_permitidas=frozenset({"nombre", "enlace"}),
    ),
    TipoMensajeOutbox.TOMA_SEGUIMIENTO: Plantilla(
        tipo=TipoMensajeOutbox.TOMA_SEGUIMIENTO,
        nombre_meta="toma_seguimiento",
        texto=(
            "Hola {nombre}. Vimos que quedaron tomas sin registrar esta semana.\n\n"
            "Si tuvo alguna dificultad, responda a este mensaje y le contactara el "
            "personal de {clinica}."
        ),
        variables_permitidas=frozenset({"nombre", "clinica"}),
    ),
    TipoMensajeOutbox.VERIFICACION_CORREO: Plantilla(
        tipo=TipoMensajeOutbox.VERIFICACION_CORREO,
        nombre_meta="",
        texto=(
            "Hola {nombre}. Para activar su acceso a {clinica}, abra este enlace: "
            "{enlace}\n\n"
            "El enlace caduca en {horas} horas. Si no solicito este acceso, ignore este "
            "mensaje."
        ),
        variables_permitidas=frozenset({"nombre", "clinica", "enlace", "horas"}),
    ),
    TipoMensajeOutbox.RECUPERACION_CONTRASENA: Plantilla(
        tipo=TipoMensajeOutbox.RECUPERACION_CONTRASENA,
        nombre_meta="",
        texto=(
            "Hola {nombre}. Recibimos una solicitud para restablecer su contrasena: "
            "{enlace}\n\n"
            "El enlace caduca en {horas} horas y solo se puede usar una vez. Si no fue "
            "usted, ignore este mensaje: su contrasena no ha cambiado."
        ),
        variables_permitidas=frozenset({"nombre", "enlace", "horas"}),
    ),
    TipoMensajeOutbox.RESUMEN_DIARIO_PROFESIONAL: Plantilla(
        tipo=TipoMensajeOutbox.RESUMEN_DIARIO_PROFESIONAL,
        nombre_meta="",
        # Va a un profesional, no a un paciente, y aun asi no lleva contenido
        # clinico: es un mensaje de canal externo y la pantalla de bloqueo de
        # un profesional tambien es publica.
        texto=(
            "Buenos dias {nombre}. Hoy tiene {citas} citas en {sede}, de {hora_inicio} a "
            "{hora_fin}.\n\n"
            "Detalle en {enlace}."
        ),
        variables_permitidas=frozenset(
            {"nombre", "citas", "sede", "hora_inicio", "hora_fin", "enlace"}
        ),
        inicia_conversacion=True,
    ),
    TipoMensajeOutbox.CAMBIO_AGENDA_PROFESIONAL: Plantilla(
        tipo=TipoMensajeOutbox.CAMBIO_AGENDA_PROFESIONAL,
        nombre_meta="",
        texto=(
            "Hola {nombre}. Hubo un cambio en su agenda del {fecha}. Puede revisarlo en {enlace}."
        ),
        variables_permitidas=frozenset({"nombre", "fecha", "enlace"}),
    ),
    # Promocion de campana. El texto de la oferta lo escribe y aprueba el
    # personal; nunca lleva datos del paciente mas alla del nombre. En Meta la
    # plantilla de marketing aprobada lleva cabecera de imagen y dos
    # parametros de cuerpo, en orden alfabetico: nombre, texto_promocion.
    TipoMensajeOutbox.PROMOCION: Plantilla(
        tipo=TipoMensajeOutbox.PROMOCION,
        nombre_meta="promocion_clinica",
        texto=(
            "Hola {nombre}. {texto_promocion} "
            "Si no desea recibir más ofertas, responda BAJA PROMOCIONES."
        ),
        variables_permitidas=frozenset({"nombre", "texto_promocion"}),
    ),
    # Seguimiento de un plan: invita a agendar la siguiente cita. No nombra
    # el tratamiento, la pieza ni el procedimiento (regla 10): la pantalla
    # bloqueada del telefono es un canal publico.
    TipoMensajeOutbox.SEGUIMIENTO_TRATAMIENTO: Plantilla(
        tipo=TipoMensajeOutbox.SEGUIMIENTO_TRATAMIENTO,
        nombre_meta="seguimiento_cita",
        texto=(
            "Hola {nombre}. En {clinica} queremos ayudarle a agendar su próxima cita. "
            "Responda a este mensaje para ver horarios disponibles."
        ),
        variables_permitidas=frozenset({"nombre", "clinica"}),
    ),
    TipoMensajeOutbox.ALERTA_PERSONAL: Plantilla(
        tipo=TipoMensajeOutbox.ALERTA_PERSONAL,
        nombre_meta="",
        texto="Aviso del sistema de {clinica}: {resumen}. Detalle en {enlace}.",
        variables_permitidas=frozenset({"clinica", "resumen", "enlace"}),
    ),
}


def obtener(tipo: TipoMensajeOutbox) -> Plantilla:
    """Plantilla de un tipo de mensaje.

    Lanza si no existe, en lugar de devolver una generica: enviar un mensaje
    con una plantilla que no corresponde es peor que no enviarlo, porque el
    paciente recibe informacion que no encaja con su situacion.
    """
    plantilla = PLANTILLAS.get(tipo)
    if plantilla is None:
        raise KeyError(
            f"No hay plantilla para {tipo.value}. Anadala en app/mensajeria/plantillas.py "
            "antes de encolar mensajes de ese tipo."
        )
    return plantilla


def tipos_sin_plantilla() -> list[TipoMensajeOutbox]:
    """Tipos del catalogo que todavia no tienen plantilla.

    Existe para que una prueba pueda listarlos y para que el hueco sea visible
    en lugar de aparecer como un fallo en tiempo de envio.
    """
    return [tipo for tipo in TipoMensajeOutbox if tipo not in PLANTILLAS]


__all__ = [
    "PLANTILLAS",
    "VARIABLES_PROHIBIDAS",
    "Plantilla",
    "obtener",
    "tipos_sin_plantilla",
]
