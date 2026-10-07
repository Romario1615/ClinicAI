"""El limite clinico del agente (CLAUDE.md, regla 5).

Dos capas, y conviene no confundirlas
-------------------------------------
**La garantia es estructural.**  No existe ninguna herramienta que cree o
modifique una receta, una dosis, una via, una frecuencia o un tratamiento.  El
agente no puede hacerlo porque no hay por donde: el registro expone ocho
herramientas y ninguna toca contenido clinico.  Esa es la proteccion real, y
hay una prueba que enumera el registro para que siga siendo cierta.

**Este catalogo es la segunda capa**, y sirve para otra cosa: para que el
agente *reconozca* que le estan pidiendo algo clinico y derive a una persona
en lugar de improvisar una respuesta.  Sin el, el modelo podria contestar «no
tengo esa herramienta» a quien dice que le sienta mal un medicamento, y esa
respuesta es peor que inutil.

Por que la deteccion se inclina a derivar
-----------------------------------------
Una lista de expresiones no clasifica intenciones con fiabilidad, y no se
pretende.  Esta calibrada para equivocarse hacia la derivacion: prefiere
mandar a una persona una consulta que era administrativa a resolver sola una
que era clinica.  El coste del primer error lo paga el personal con su tiempo;
el del segundo lo paga un paciente.

Lo que este modulo **no** hace
------------------------------
No decide si algo es urgente ni interpreta sintomas.  Clasificar una reaccion
adversa como grave o leve es un juicio clinico, y hacerlo aqui seria
exactamente lo que la regla 5 prohibe.  Todo lo que cae en el catalogo sale
por el mismo sitio: `handoff_to_human`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from app.ia.saneamiento import normalizar


class MotivoDerivacion(StrEnum):
    """Por que una peticion sale del alcance del agente.

    El motivo viaja a la auditoria y al aviso que ve el personal: no es lo
    mismo atender primero a quien describe una reaccion adversa que a quien
    pregunta por una factura.
    """

    DECISION_CLINICA = "DECISION_CLINICA"
    MEDICACION = "MEDICACION"
    REACCION_ADVERSA = "REACCION_ADVERSA"
    SINTOMA_O_DIAGNOSTICO = "SINTOMA_O_DIAGNOSTICO"
    URGENCIA_DECLARADA = "URGENCIA_DECLARADA"
    DATOS_DE_TERCERO = "DATOS_DE_TERCERO"
    SIN_FUENTE_APROBADA = "SIN_FUENTE_APROBADA"
    NO_COMPRENDIDO = "NO_COMPRENDIDO"
    PETICION_DEL_PACIENTE = "PETICION_DEL_PACIENTE"


@dataclass(frozen=True, slots=True)
class Senal:
    """Una expresion que obliga a derivar, con el motivo que le corresponde."""

    nombre: str
    expresion: re.Pattern[str]
    motivo: MotivoDerivacion
    # Por que esta en la lista. Se lee cuando alguien quiere quitarla.
    razon: str


def _s(nombre: str, expresion: str, motivo: MotivoDerivacion, razon: str) -> Senal:
    return Senal(nombre, re.compile(expresion), motivo, razon)


# El catalogo. Las expresiones se aplican sobre el texto ya normalizado:
# minusculas y sin tildes, asi que aqui no se escriben acentos.
SENALES: Final[tuple[Senal, ...]] = (
    # --- Medicacion y dosis ---
    _s(
        "cambio_de_dosis",
        r"\b(cambi\w*|sub\w*|baj\w*|aument\w*|reduc\w*|ajust\w*|modific\w*)\b"
        r"[^.]{0,40}\b(dosis|miligramos|mg|pastillas?|gotas?|unidades)\b",
        MotivoDerivacion.MEDICACION,
        "Ajustar una dosis es una decision clinica con consecuencias directas.",
    ),
    _s(
        "suspension",
        r"\b(dej\w+ de tomar|suspend\w*|par\w+ de tomar|ya no tom\w*|retir\w*)\b"
        r"[^.]{0,40}\b(medicament\w*|pastilla|tratamiento|receta)\b",
        MotivoDerivacion.MEDICACION,
        "Suspender medicacion sin criterio profesional puede ser peligroso.",
    ),
    _s(
        "toma_olvidada",
        r"\b(olvid\w*|se me paso|no tome)\b[^.]{0,40}\b(dosis|toma|pastilla|medicament\w*)\b",
        MotivoDerivacion.MEDICACION,
        "Se me olvido una toma pide una indicacion que solo da un profesional; "
        "sugerir duplicar la siguiente esta explicitamente prohibido.",
    ),
    _s(
        "receta_nueva",
        r"\b(recet\w*|prescrib\w*|mand\w*|indic\w*)\b[^.]{0,30}\b"
        r"(medicament\w*|antibiotic\w*|pastilla|jarabe|inyeccion)\b",
        MotivoDerivacion.MEDICACION,
        "Prescribir es un acto medico. El agente no crea ni modifica recetas.",
    ),
    # --- Reacciones adversas ---
    _s(
        "reaccion_adversa",
        r"\b(me (cayo|sento|hizo) mal|reaccion|alergi\w*|efecto secundario|"
        r"sarpullido|me brot\w*|intoxic\w*)\b",
        MotivoDerivacion.REACCION_ADVERSA,
        "Interpretar una reaccion adversa es un juicio clinico. Se deriva siempre, "
        "sin clasificar gravedad: clasificarla ya seria interpretarla.",
    ),
    # --- Sintomas y diagnostico ---
    _s(
        "pide_diagnostico",
        r"\b(que (tengo|sera|me pasa)|es grave|sera (grave|cancer|covid)|"
        r"diagnostic\w*|que enfermedad)\b",
        MotivoDerivacion.SINTOMA_O_DIAGNOSTICO,
        "Diagnosticar esta prohibido, y responder que no puede sin derivar deja "
        "sola a una persona preocupada.",
    ),
    _s(
        "describe_sintomas",
        r"\b(me duele|tengo (dolor|fiebre|sangrado|mareo)|no puedo (respirar|caminar)|"
        r"vomit\w*|desmay\w*|convuls\w*)\b",
        MotivoDerivacion.SINTOMA_O_DIAGNOSTICO,
        "Un sintoma descrito por escrito necesita valoracion, no una respuesta automatica.",
    ),
    # --- Urgencia ---
    _s(
        "urgencia",
        r"\b(urgent\w*|emergencia|socorro)\b",
        MotivoDerivacion.URGENCIA_DECLARADA,
        "Quien declara una urgencia no puede quedarse esperando a que un agente "
        "termine un flujo de reserva.",
    ),
    # --- Datos de terceros ---
    _s(
        "datos_de_tercero",
        # «para mi madre» es la forma mas comun al pedir cita por otro, y es la
        # que se escapaba cuando la expresion solo contemplaba «de mi madre».
        r"\b((de|para|a) mi (madre|padre|hij\w+|esposo|esposa|hermano|hermana|abuel\w+)|"
        r"a nombre de otra persona|(de|para) un familiar)\b",
        MotivoDerivacion.DATOS_DE_TERCERO,
        "Un telefono no acredita representacion. La vinculacion la verifica una "
        "persona, no el agente.",
    ),
)


# Lo que se le dice al paciente. Nunca menciona medicamentos ni sintomas
# concretos: es un mensaje de WhatsApp y puede leerlo quien tenga el telefono
# delante (CLAUDE.md, regla 10).
_EXPLICACION: Final[dict[MotivoDerivacion, str]] = {
    MotivoDerivacion.DECISION_CLINICA: (
        "Esto necesita que lo vea un profesional. Le paso con el personal de la clinica."
    ),
    MotivoDerivacion.MEDICACION: (
        "Sobre su tratamiento solo le puede responder un profesional. "
        "Le paso con el personal de la clinica."
    ),
    MotivoDerivacion.REACCION_ADVERSA: (
        "Voy a pasarle ahora con el personal de la clinica para que le atiendan."
    ),
    MotivoDerivacion.SINTOMA_O_DIAGNOSTICO: (
        "Eso tiene que valorarlo un profesional. Le paso con el personal de la clinica."
    ),
    MotivoDerivacion.URGENCIA_DECLARADA: (
        "Le paso de inmediato con el personal de la clinica. "
        "Si se trata de una emergencia, acuda al servicio de urgencias mas cercano."
    ),
    MotivoDerivacion.DATOS_DE_TERCERO: (
        "Para gestionar la cita de otra persona necesito confirmarlo con el personal "
        "de la clinica. Le paso con ellos."
    ),
    MotivoDerivacion.SIN_FUENTE_APROBADA: (
        "No tengo informacion aprobada sobre eso. Le paso con el personal de la clinica."
    ),
    MotivoDerivacion.NO_COMPRENDIDO: (
        "Prefiero no arriesgarme a entenderle mal. Le paso con el personal de la clinica."
    ),
    MotivoDerivacion.PETICION_DEL_PACIENTE: (
        "Por supuesto. Le paso con el personal de la clinica."
    ),
}


@dataclass(frozen=True, slots=True)
class Evaluacion:
    """Resultado de mirar un texto en busca de senales de derivacion."""

    deriva: bool
    motivo: MotivoDerivacion | None = None
    senal: str | None = None

    @property
    def razon_legible(self) -> str:
        if not self.deriva or self.motivo is None:
            return ""
        return _EXPLICACION[self.motivo]


def evaluar(texto: str | None) -> Evaluacion:
    """Indica si un texto del paciente debe salir del alcance del agente.

    Devuelve la **primera** senal que coincide, en el orden del catalogo.  Ese
    orden no es casual: medicacion y reaccion adversa van antes que sintoma,
    porque un mensaje que menciona ambas cosas se atiende mejor con el motivo
    mas especifico.
    """
    if not texto or not texto.strip():
        return Evaluacion(deriva=False)

    normalizado = normalizar(texto)
    for senal in SENALES:
        if senal.expresion.search(normalizado):
            return Evaluacion(deriva=True, motivo=senal.motivo, senal=senal.nombre)
    return Evaluacion(deriva=False)


def explicar(motivo: MotivoDerivacion) -> str:
    """Texto para el paciente correspondiente a un motivo de derivacion."""
    return _EXPLICACION[motivo]
