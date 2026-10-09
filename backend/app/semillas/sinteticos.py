"""Generacion de datos sinteticos para desarrollo y pruebas.

**Nunca datos reales de pacientes** (regla 6 de CLAUDE.md).  Todo lo que
genera este modulo es ficticio:

* Los nombres vienen de Faker con localizacion `es_ES`, y cada paciente lleva
  el marcador de sinteticos en su registro.
* Los documentos de identidad empiezan por `9` y siguen un patron que no
  corresponde a ninguna cedula ecuatoriana valida: el digito verificador no
  cuadra a proposito, para que no puedan confundirse con datos reales ni
  usarse en ningun tramite.
* Los telefonos usan el rango `+593 99 000 xxxx`, reservado para pruebas en
  este proyecto.
* Los correos usan el dominio `example.invalid`, reservado por la RFC 2606 y
  que por definicion no existe.

La salvaguarda
--------------
`cargar_datos_sinteticos` se **niega** a ejecutarse con `ENTORNO=produccion`.
No es un aviso: lanza una excepcion.  Un script de semillas ejecutado por
error contra la base de produccion insertaria pacientes ficticios entre los
reales, y separarlos despues seria un trabajo manual sobre datos clinicos.
"""

from __future__ import annotations

import hashlib
import random
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from faker import Faker
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita, EstadoCita, OrigenCita
from app.modulos.organizacion.modelos import (
    Clinica,
    ConfiguracionClinica,
    Consultorio,
    Descanso,
    Especialidad,
    Feriado,
    HorarioAtencion,
    Sede,
    Servicio,
)
from app.modulos.pacientes.modelos import (
    Consentimiento,
    Paciente,
    RelacionAsistencial,
    TipoConsentimiento,
)
from app.modulos.profesionales.modelos import (
    AgendaPlantilla,
    Profesional,
    ProfesionalSede,
    ProfesionalServicio,
)
from app.modulos.usuarios.modelos import AmbitoAsignacion, Rol, Usuario, UsuarioRol
from app.nucleo.autorizacion import TipoAmbito
from app.nucleo.configuracion import Configuracion
from app.nucleo.reloj import Reloj, RelojSistema
from app.nucleo.seguridad import hashear_contrasena

# Marcador visible en cualquier volcado de la base de datos.  Si alguien ve
# esto en produccion, sabe de inmediato que hay datos de prueba mezclados.
MARCA_SINTETICO = "[SINTETICO]"

# Dominio reservado por la RFC 2606: no existe y nunca existira.
DOMINIO_PRUEBAS = "example.invalid"

# Rango de telefonos reservado para este proyecto.
PREFIJO_TELEFONO_PRUEBAS = "+593990000"

# Contrasena de los usuarios sinteticos.  Se imprime al terminar la carga.
#
# Es un valor fijo y conocido A PROPOSITO: son cuentas de desarrollo en una
# base de datos local que ya esta detras de la sesion de Windows.  Generar una
# aleatoria por usuario obligaria a copiarla de la salida en cada recarga, y
# el desarrollador acabaria poniendo "123456".  La salvaguarda de entorno es
# lo que impide que estas cuentas existan en produccion.
CONTRASENA_SINTETICA = "DesarrolloLocal2026"
SEMILLA_PREDETERMINADA = 20260415

# Convencion ISO: 1 = lunes, 5 = viernes, 6 = sabado.
ULTIMO_DIA_LABORABLE = 5
# Hora local del descanso de almuerzo, que no admite citas.
HORA_ALMUERZO = 13
# Cada cuantos pacientes se genera uno con identidad verificada.
UNO_DE_CADA_VERIFICADOS = 4
# Consultorios por sede; el ultimo es de procedimientos.
CONSULTORIOS_POR_SEDE = 3

ESPECIALIDADES = (
    ("Medicina General", "MG"),
    ("Dermatologia", "DERM"),
    ("Pediatria", "PED"),
    ("Odontologia", "ODO"),
)

# Catalogo de servicios.  Cada entrada es una tupla con el nombre, la
# especialidad a la que pertenece, la duracion en minutos, el tiempo de
# preparacion y el precio.
#
# Las duraciones y preparaciones son multiplos de 15 a proposito, para que
# encajen con la granularidad de las franjas y no se pierda capacidad por el
# redondeo (ver `granularidad_incompatible` en el motor de disponibilidad).
SERVICIOS = (
    ("Consulta general", "Medicina General", 30, 0, 25.00),
    ("Control de seguimiento", "Medicina General", 15, 0, 15.00),
    ("Consulta dermatologica", "Dermatologia", 30, 15, 45.00),
    ("Crioterapia", "Dermatologia", 45, 15, 80.00),
    ("Consulta pediatrica", "Pediatria", 30, 0, 35.00),
    ("Control de nino sano", "Pediatria", 30, 0, 30.00),
    ("Profilaxis dental", "Odontologia", 45, 15, 40.00),
    ("Consulta odontologica", "Odontologia", 30, 15, 30.00),
)


@dataclass(slots=True)
class ResumenSinteticos:
    """Que se creo, para poder revisarlo e iniciar sesion."""

    clinica_id: uuid.UUID | None = None
    sedes: int = 0
    especialidades: int = 0
    servicios: int = 0
    profesionales: int = 0
    pacientes: int = 0
    # Consentimientos de comunicacion otorgados y vigentes.  Se informa porque
    # es la cifra que decide a cuantos pacientes puede escribir el sistema: con
    # cero, ningun recordatorio sale y el flujo de mensajeria no se puede
    # ejercitar ni demostrar.
    consentimientos_vigentes: int = 0
    consentimientos_revocados: int = 0
    citas: int = 0
    # Citas descartadas por colisionar con otra ya generada.  Se informa
    # porque un numero alto indica que la agenda sintetica esta saturada y
    # conviene ampliar el rango de fechas o reducir la cantidad pedida.
    colisiones_descartadas: int = 0
    usuarios: list[tuple[str, str]] = field(default_factory=list)

    def describir(self) -> str:
        lineas = [
            "Datos sinteticos cargados:",
            f"  Sedes:          {self.sedes}",
            f"  Especialidades: {self.especialidades}",
            f"  Servicios:      {self.servicios}",
            f"  Profesionales:  {self.profesionales}",
            f"  Pacientes:      {self.pacientes}",
            f"  Consentimientos vigentes: {self.consentimientos_vigentes}"
            f" (revocados: {self.consentimientos_revocados})",
            f"  Citas:          {self.citas}",
            f"  Colisiones descartadas: {self.colisiones_descartadas}",
            "",
            "Usuarios para iniciar sesion:",
        ]
        for correo, rol in self.usuarios:
            lineas.append(f"  {correo:<44} rol: {rol}")
        lineas.extend(
            [
                "",
                f"Contrasena de todos: {CONTRASENA_SINTETICA}",
                "",
                "Son cuentas de DESARROLLO con datos ficticios. El arranque en",
                "ENTORNO=produccion rechaza esta carga.",
            ]
        )
        return "\n".join(lineas)


def _documento_sintetico(indice: int) -> str:
    """Documento que no puede ser una cedula ecuatoriana valida.

    Las cedulas ecuatorianas tienen diez digitos y los dos primeros
    corresponden a una provincia entre 01 y 24.  Empezar por 99 las hace
    invalidas por construccion, asi que estos numeros no pueden confundirse
    con datos reales ni servir para ningun tramite.
    """
    return f"99{indice:08d}"


def _telefono_sintetico(indice: int) -> str:
    return f"{PREFIJO_TELEFONO_PRUEBAS}{indice:04d}"


def _hash_texto_sintetico(version: str) -> str:
    """Hash del texto de consentimiento sintetico.

    No es el hash de ningun texto legal real. Existe porque el modelo exige 64
    caracteres hexadecimales -- guarda el hash del texto aceptado para poder
    responder «que acepte exactamente» ante una reclamacion --, y un valor
    derivado de la version es mas honesto que 64 ceros: deja claro que
    corresponde a un texto concreto, aunque sea ficticio.
    """
    return hashlib.sha256(f"consentimiento-sintetico:{version}".encode()).hexdigest()


def _correo_sintetico(nombre: str, indice: int | str) -> str:
    """Construye una direccion de correo a partir de un nombre.

    Las tildes y la enye se transliteran, no se descartan: Faker en espanol
    genera nombres como "Jose Manuel" con acento, y un correo con caracteres
    no ASCII es valido segun la norma pero falla en la practica con muchos
    clientes y validadores.  Un primer intento solo sustituia la enye y dejaba
    correos como "jose.manuel@..." con la e acentuada intacta.

    `NFKD` separa cada letra de su acento y el filtro de categoria descarta
    los acentos sueltos, con lo que la letra base sobrevive.
    """
    normalizado = unicodedata.normalize("NFKD", nombre.lower())
    sin_acentos = "".join(c for c in normalizado if not unicodedata.combining(c))
    base = sin_acentos.replace(" ", ".")
    base = "".join(c for c in base if c.isascii() and (c.isalnum() or c == "."))
    # Dos puntos seguidos, o un punto al principio o al final, hacen invalida
    # la direccion.
    while ".." in base:
        base = base.replace("..", ".")
    base = base.strip(".")
    return f"{base}.{indice}@{DOMINIO_PRUEBAS}"


async def cargar_datos_sinteticos(  # noqa: PLR0912, PLR0915
    sesion: AsyncSession,
    configuracion: Configuracion,
    *,
    cantidad_pacientes: int = 60,
    cantidad_citas: int = 200,
    semilla: int = SEMILLA_PREDETERMINADA,
    reloj: Reloj | None = None,
) -> ResumenSinteticos:
    """Crea una clinica completa con datos ficticios.

    `semilla` fija el generador aleatorio y `reloj` fija el instante de
    referencia: con ambos valores iguales se producen los mismos datos.
    Importa para poder reproducir un problema encontrado en desarrollo y para
    que las capturas de la interfaz no cambien en cada recarga.

    Sobre su longitud: el linter senala que la funcion es larga, y se silencia
    a proposito.  Es un guion secuencial -- organizacion, catalogo, personal,
    pacientes, citas -- donde cada paso depende del anterior.  Dividirlo en
    cinco funciones obligaria a pasarse una docena de objetos entre ellas y a
    devolver tuplas de seis elementos, y el resultado se leeria peor que el
    guion de arriba abajo con sus secciones marcadas.
    """
    # =====================================================================
    #  Salvaguarda de entorno
    # =====================================================================
    if configuracion.entorno.es_produccion:
        raise RuntimeError(
            "La carga de datos sinteticos esta bloqueada con "
            "ENTORNO=produccion.\n"
            "Insertar pacientes ficticios entre los reales obligaria a "
            "separarlos despues a mano, sobre datos clinicos.\n"
            "Si de verdad necesita datos de ejemplo, use el entorno de "
            "preproduccion."
        )

    faker = Faker("es_ES")
    Faker.seed(semilla)
    aleatorio = random.Random(semilla)  # noqa: S311

    resumen = ResumenSinteticos()
    ahora = (reloj or RelojSistema()).ahora()

    # =====================================================================
    #  Clinica y sedes
    # =====================================================================
    # La identificacion fiscal deriva de la semilla y no es un valor fijo.
    #
    # Con un valor fijo, la segunda carga chocaba con la restriccion unica y
    # producia un IntegrityError opaco.  Derivarla de la semilla permite
    # generar varias clinicas de prueba independientes -- lo que necesitan las
    # pruebas de integracion -- y hace que repetir la misma semilla sea un
    # error detectable con un mensaje util.
    identificacion = f"99{semilla % 10**9:09d}001"

    existente = (
        await sesion.execute(select(Clinica).where(Clinica.identificacion_fiscal == identificacion))
    ).scalar_one_or_none()
    if existente is not None:
        # El mensaje se compone por lineas en lugar de con secuencias de
        # escape: es mas legible y no depende de como se editara el archivo.
        raise RuntimeError(
            "\n".join(
                [
                    f"Ya existe una clinica sintetica con la semilla {semilla} "
                    f"(identificacion {identificacion}).",
                    "",
                    "Para recargar desde cero:",
                    "  .\\infra\\scripts\\infra-abajo.ps1 -BorrarDatos",
                    "  .\\infra\\scripts\\infra-arriba.ps1",
                    "  uv run alembic upgrade head",
                    "  uv run python -m app.semillas.cargar",
                    "",
                    "Para anadir otra clinica de prueba, use --semilla con otro valor.",
                ]
            )
        )

    clinica = Clinica(
        nombre=f"Clinica Demostracion {semilla} {MARCA_SINTETICO}",
        identificacion_fiscal=identificacion,
        zona_horaria=configuracion.zona_horaria_por_defecto,
        telefono=_telefono_sintetico(1),
        correo=f"contacto@{DOMINIO_PRUEBAS}",
    )
    sesion.add(clinica)
    await sesion.flush()
    resumen.clinica_id = clinica.id
    # La clinica sintetica tiene el agente de WhatsApp encendido para poder
    # demostrarlo con el adaptador sandbox. En una clinica real esta apagado
    # hasta que la administracion lo encienda (ADR-0025).
    sesion.add(
        ConfiguracionClinica(
            clinica_id=clinica.id,
            clave="integracion.agente_whatsapp",
            valor={"habilitada": True, "ajustes": {}, "secretos_cifrados": {}},
        )
    )

    sedes: list[Sede] = []
    for nombre_sede, antelacion in (("Sede Norte", 60), ("Sede Centro", 120)):
        sede = Sede(
            clinica_id=clinica.id,
            nombre=f"{nombre_sede} {MARCA_SINTETICO}",
            direccion=f"{faker.street_address()} (ficticia)",
            telefono=_telefono_sintetico(len(sedes) + 2),
            minutos_antelacion_minima=antelacion,
        )
        sesion.add(sede)
        sedes.append(sede)
    await sesion.flush()
    resumen.sedes = len(sedes)

    # Consultorios y horarios por sede.
    for sede in sedes:
        for numero in range(1, CONSULTORIOS_POR_SEDE + 1):
            sesion.add(
                Consultorio(
                    sede_id=sede.id,
                    nombre=f"Consultorio {numero}",
                    tipo=("CONSULTA" if numero < CONSULTORIOS_POR_SEDE else "PROCEDIMIENTOS"),
                )
            )
        # Lunes a viernes de 08:00 a 17:00, con descanso de 13:00 a 14:00.
        for dia in range(1, 6):
            horario = HorarioAtencion(
                propietario_tipo="SEDE",
                propietario_id=sede.id,
                dia_semana=dia,
                hora_inicio=time(8, 0),
                hora_fin=time(17, 0),
                granularidad_minutos=15,
            )
            sesion.add(horario)
            await sesion.flush()
            sesion.add(
                Descanso(
                    horario_atencion_id=horario.id,
                    hora_inicio=time(13, 0),
                    hora_fin=time(14, 0),
                    motivo="Almuerzo",
                )
            )
        # Sabado por la manana.
        sesion.add(
            HorarioAtencion(
                propietario_tipo="SEDE",
                propietario_id=sede.id,
                dia_semana=6,
                hora_inicio=time(8, 0),
                hora_fin=time(12, 0),
                granularidad_minutos=15,
            )
        )
    await sesion.flush()

    # Feriados ecuatorianos recurrentes.
    for mes, dia, nombre in (
        (1, 1, "Ano Nuevo"),
        (5, 1, "Dia del Trabajo"),
        (8, 10, "Primer Grito de Independencia"),
        (12, 25, "Navidad"),
    ):
        sesion.add(
            Feriado(
                clinica_id=clinica.id,
                fecha=date(2026, mes, dia),
                nombre=nombre,
                recurrente_anual=True,
            )
        )

    # =====================================================================
    #  Especialidades y servicios
    # =====================================================================
    especialidades: dict[str, Especialidad] = {}
    for nombre, codigo in ESPECIALIDADES:
        especialidad = Especialidad(clinica_id=clinica.id, nombre=nombre, codigo=codigo)
        sesion.add(especialidad)
        especialidades[nombre] = especialidad
    await sesion.flush()
    resumen.especialidades = len(especialidades)

    servicios: list[Servicio] = []
    for nombre, especialidad_nombre, duracion, preparacion, precio in SERVICIOS:
        servicio = Servicio(
            clinica_id=clinica.id,
            especialidad_id=especialidades[especialidad_nombre].id,
            nombre=nombre,
            duracion_minutos=duracion,
            minutos_preparacion=preparacion,
            precio=precio,
            instrucciones_preparacion=("Acuda quince minutos antes con su documento de identidad."),
        )
        sesion.add(servicio)
        servicios.append(servicio)
    await sesion.flush()
    resumen.servicios = len(servicios)

    # =====================================================================
    #  Roles, usuarios y profesionales
    # =====================================================================
    roles = {
        r.codigo: r
        for r in (await sesion.execute(select(Rol).where(Rol.clinica_id.is_(None)))).scalars()
    }
    if not roles:
        raise RuntimeError(
            "No hay roles del sistema en la base de datos.\n"
            "Cargue primero los catalogos: "
            "python -m app.semillas.cargar --solo-catalogos"
        )

    hash_contrasena = hashear_contrasena(CONTRASENA_SINTETICA)

    async def crear_usuario(
        nombre: str,
        apellido: str,
        codigo_rol: str,
        *,
        indice: int,
        sedes_del_ambito: list[Sede] | None = None,
    ) -> Usuario:
        """Crea un usuario con su rol y ambito.

        El ambito es explicito: un `usuario_rol` sin ambito no da acceso a
        nada, asi que omitirlo produciria usuarios que no pueden trabajar.
        """
        usuario = Usuario(
            clinica_id=clinica.id,
            correo=_correo_sintetico(
                f"{nombre} {apellido}",
                indice if semilla == SEMILLA_PREDETERMINADA else f"s{semilla}.{indice}",
            ),
            hash_contrasena=hash_contrasena,
            nombre=nombre,
            apellido=f"{apellido} {MARCA_SINTETICO}",
            telefono=_telefono_sintetico(indice),
            correo_verificado_en=ahora,
        )
        sesion.add(usuario)
        await sesion.flush()

        asignacion = UsuarioRol(usuario_id=usuario.id, rol_id=roles[codigo_rol].id)
        sesion.add(asignacion)
        await sesion.flush()

        objetivo = sedes_del_ambito if sedes_del_ambito is not None else sedes
        for sede in objetivo:
            sesion.add(
                AmbitoAsignacion(
                    usuario_rol_id=asignacion.id,
                    tipo=TipoAmbito.SEDE.value,
                    valor_id=sede.id,
                    incluir=True,
                )
            )
        # Comodines de especialidad, profesional y paciente dentro de esas
        # sedes.
        #
        # El de ESPECIALIDAD no es opcional y su ausencia no es un detalle:
        # sin el, el conjunto de especialidades del principal queda vacio, y
        # vacio significa ningun acceso. El resultado es un usuario que entra,
        # ve su sede y sus pacientes, y no puede agendar nada porque la lista
        # de servicios le llega vacia -- sin ningun error que lo explique.
        for tipo in (
            TipoAmbito.ESPECIALIDAD.value,
            TipoAmbito.PROFESIONAL.value,
            TipoAmbito.PACIENTE.value,
        ):
            sesion.add(
                AmbitoAsignacion(
                    usuario_rol_id=asignacion.id,
                    tipo=tipo,
                    valor_id=None,
                    incluir=True,
                )
            )
        await sesion.flush()

        resumen.usuarios.append((usuario.correo, codigo_rol))
        return usuario

    # Un usuario por rol administrativo.
    await crear_usuario("Sofia", "Plataforma", "superadministrador", indice=9)
    await crear_usuario("Ana", "Administradora", "administrador_clinica", indice=10)
    await crear_usuario("Rita", "Recepcion", "recepcion", indice=11, sedes_del_ambito=[sedes[0]])
    await crear_usuario("Alba", "Asistente", "asistente", indice=12)
    await crear_usuario("Aldo", "Auditor", "auditor", indice=13)

    # Profesionales: dos por especialidad.
    profesionales: list[Profesional] = []
    indice_usuario = 20
    for nombre_especialidad, _ in ESPECIALIDADES:
        for numero in range(2):
            nombre = faker.first_name()
            apellido = faker.last_name()
            usuario = await crear_usuario(nombre, apellido, "profesional", indice=indice_usuario)
            indice_usuario += 1

            profesional = Profesional(
                clinica_id=clinica.id,
                usuario_id=usuario.id,
                especialidad_id=especialidades[nombre_especialidad].id,
                nombre=nombre,
                apellido=f"{apellido} {MARCA_SINTETICO}",
                numero_registro_profesional=f"REG-{indice_usuario:05d}",
                telefono_whatsapp=_telefono_sintetico(indice_usuario),
                correo_calendario=usuario.correo,
                minutos_preparacion_propio=0,
            )
            sesion.add(profesional)
            await sesion.flush()
            profesionales.append(profesional)

            # Sede principal alterna entre las dos.
            sede_principal = sedes[numero % len(sedes)]
            sesion.add(
                ProfesionalSede(
                    profesional_id=profesional.id,
                    sede_id=sede_principal.id,
                    principal=True,
                )
            )

            # Plantilla de agenda: lunes a viernes, media jornada alterna.
            hora_inicio = "08:00" if numero == 0 else "12:00"
            hora_fin = "13:00" if numero == 0 else "17:00"
            for dia in range(1, 6):
                sesion.add(
                    AgendaPlantilla(
                        profesional_id=profesional.id,
                        sede_id=sede_principal.id,
                        dia_semana=dia,
                        hora_inicio=hora_inicio,
                        hora_fin=hora_fin,
                        granularidad_minutos=15,
                    )
                )

            # Servicios de su especialidad.
            for servicio in servicios:
                if servicio.especialidad_id == profesional.especialidad_id:
                    sesion.add(
                        ProfesionalServicio(profesional_id=profesional.id, servicio_id=servicio.id)
                    )
    await sesion.flush()
    resumen.profesionales = len(profesionales)

    # =====================================================================
    #  Pacientes
    # =====================================================================
    pacientes: list[Paciente] = []
    for indice in range(cantidad_pacientes):
        nombre = faker.first_name()
        apellido = faker.last_name()
        paciente = Paciente(
            clinica_id=clinica.id,
            tipo_documento="CEDULA",
            numero_documento=_documento_sintetico(indice),
            nombre=nombre,
            apellido=f"{apellido} {MARCA_SINTETICO}",
            fecha_nacimiento=faker.date_of_birth(minimum_age=1, maximum_age=90),
            sexo=aleatorio.choice(["F", "M", "OTRO"]),
            telefono_whatsapp=_telefono_sintetico(1000 + indice),
            correo=_correo_sintetico(f"{nombre} {apellido}", 1000 + indice),
            direccion=f"{faker.street_address()} (ficticia)",
            # La mayoria sin verificar: es el estado real de una clinica que
            # empieza, y obliga a que el flujo de verificacion se ejercite.
            nivel_verificacion=("DOCUMENTO" if indice % 4 == 0 else "NO_VERIFICADO"),
            verificado_en=ahora if indice % 4 == 0 else None,
        )
        sesion.add(paciente)
        pacientes.append(paciente)
    await sesion.flush()
    resumen.pacientes = len(pacientes)

    # =====================================================================
    #  Consentimientos de comunicacion
    # =====================================================================
    # Sin esta seccion, los 60 pacientes sinteticos tenian numero de WhatsApp y
    # ningun consentimiento, asi que `ServicioOutbox.encolar` los rechazaba a
    # todos: el flujo de mensajeria no se podia ejercitar ni demostrar sobre
    # los datos de desarrollo.
    #
    # El reparto es deliberado y cubre los tres caminos que el codigo
    # distingue, para que ninguno quede sin datos con los que ejercerlo:
    #
    #   * la mayoria acepta comunicacion de citas;
    #   * una parte acepta ademas recordatorios de medicacion, que es un
    #     consentimiento DISTINTO (aceptar avisos de cita no es aceptar que le
    #     escriban sobre su medicacion);
    #   * uno de cada nueve no acepta nada, para que el camino de rechazo
    #     tenga a quien rechazar;
    #   * uno de cada once lo revoco, que es el caso del paciente que respondio
    #     BAJA por WhatsApp.
    #
    # El texto del consentimiento es sintetico y su version lo dice. El hash NO
    # es el de ningun texto legal real: cuando exista uno revisado
    # juridicamente (limitacion E-2), esta version debe sustituirse.
    version_texto = "sintetica-v0"
    texto_hash = _hash_texto_sintetico(version_texto)
    vigentes = 0
    revocados = 0

    for indice, paciente in enumerate(pacientes):
        if indice % 9 == 0:
            # Sin consentimiento: no se crea fila. La ausencia de fila y una
            # fila con `otorgado=False` no son lo mismo, y el codigo distingue.
            continue

        revocado = indice % 11 == 0
        tipos = [TipoConsentimiento.COMUNICACION_WHATSAPP]
        if indice % 3 == 0:
            tipos.append(TipoConsentimiento.RECORDATORIOS_MEDICACION)

        for tipo in tipos:
            sesion.add(
                Consentimiento(
                    paciente_id=paciente.id,
                    tipo=tipo.value,
                    otorgado=True,
                    version_texto=version_texto,
                    texto_hash=texto_hash,
                    canal="PANEL",
                    otorgado_en=ahora - timedelta(days=30),
                    # La revocacion no borra la fila: hay que poder demostrar
                    # que hubo consentimiento mientras se enviaron mensajes.
                    revocado_en=(ahora - timedelta(days=2)) if revocado else None,
                    evidencia={"origen": "semilla sintetica", "marca": MARCA_SINTETICO},
                )
            )
            if revocado:
                revocados += 1
            else:
                vigentes += 1

    await sesion.flush()
    resumen.consentimientos_vigentes = vigentes
    resumen.consentimientos_revocados = revocados

    # =====================================================================
    #  Citas
    # =====================================================================
    # Se generan en dias laborables dentro del horario, y se descartan las que
    # colisionan: la restriccion de exclusion las rechazaria de todas formas,
    # y capturar el rechazo es mas simple que calcular huecos aqui.
    servicios_por_especialidad: dict[uuid.UUID, list[Servicio]] = {}
    for servicio in servicios:
        servicios_por_especialidad.setdefault(servicio.especialidad_id, []).append(servicio)

    estados_posibles = (
        (EstadoCita.CONFIRMED, 0.55),
        (EstadoCita.COMPLETED, 0.25),
        (EstadoCita.CANCELLED, 0.12),
        (EstadoCita.NO_SHOW, 0.08),
    )
    estados = [e for e, _ in estados_posibles]
    pesos = [p for _, p in estados_posibles]

    creadas = 0
    colisiones = 0
    intentos = 0
    limite_intentos = cantidad_citas * 6

    while creadas < cantidad_citas and intentos < limite_intentos:
        intentos += 1
        profesional = aleatorio.choice(profesionales)
        opciones = servicios_por_especialidad.get(profesional.especialidad_id, [])
        if not opciones:
            continue
        servicio = aleatorio.choice(opciones)
        paciente = aleatorio.choice(pacientes)

        # Entre 30 dias atras y 30 adelante, en dia laborable.
        #
        # La variable se llama `fecha_cita` y no `dia`: en los bucles de
        # arriba `dia` es el numero ISO del dia de la semana, y reutilizar el
        # nombre para una fecha hacia que el tipo cambiara a media funcion.
        desplazamiento = aleatorio.randint(-30, 30)
        fecha_cita = (ahora + timedelta(days=desplazamiento)).date()
        if fecha_cita.isoweekday() > ULTIMO_DIA_LABORABLE:
            continue

        # Hora dentro de la jornada, alineada a 15 minutos.
        hora = aleatorio.randint(8, 16)
        minuto = aleatorio.choice([0, 15, 30, 45])
        if hora == HORA_ALMUERZO:
            continue

        inicio = datetime.combine(
            fecha_cita, time(hora, minuto), tzinfo=ZoneInfo(clinica.zona_horaria)
        )

        # El estado depende de si la cita ya paso: una cita futura no puede
        # estar completada ni ser una inasistencia.
        if inicio > ahora:
            estado = EstadoCita.CONFIRMED
        else:
            estado = aleatorio.choices(estados, weights=pesos, k=1)[0]

        sede_id = sedes[0].id
        fila_sede = (
            (
                await sesion.execute(
                    select(ProfesionalSede).where(ProfesionalSede.profesional_id == profesional.id)
                )
            )
            .scalars()
            .first()
        )
        if fila_sede is not None:
            sede_id = fila_sede.sede_id

        cita = Cita(
            clinica_id=clinica.id,
            sede_id=sede_id,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            servicio_id=servicio.id,
            inicio=inicio,
            duracion_minutos=servicio.duracion_minutos,
            minutos_preparacion=servicio.minutos_preparacion,
            estado=estado.value,
            origen=aleatorio.choice([OrigenCita.PANEL.value, OrigenCita.WHATSAPP.value]),
            motivo_cancelacion=(
                "El paciente reprogramo por telefono" if estado is EstadoCita.CANCELLED else None
            ),
            confirmada_en=ahora if estado is not EstadoCita.CANCELLED else None,
            completada_en=ahora if estado is EstadoCita.COMPLETED else None,
            cancelada_en=ahora if estado is EstadoCita.CANCELLED else None,
        )
        # =================================================================
        #  Punto de guardado por cita
        # =================================================================
        #  Si la cita colisiona con otra ya generada, se deshace SOLO ella y
        #  el bucle prueba otro horario.  Sin el punto de guardado, el rechazo
        #  invalidaria la transaccion completa y se perderia todo lo insertado
        #  antes: la clinica, los profesionales y los pacientes.
        #
        #  El `add` va DENTRO del punto de guardado.  Hacerlo fuera fue un
        #  error: al deshacerse el punto, el objeto seguia pendiente en la
        #  sesion y el siguiente `flush` volvia a intentar insertarlo, con lo
        #  que la sesion quedaba en un estado del que no salia
        #  ("Can't operate on closed transaction").
        punto = await sesion.begin_nested()
        try:
            sesion.add(cita)
            await sesion.flush()
        except IntegrityError:
            # Colision con una cita ya generada.  Es el resultado esperado de
            # elegir horas al azar, y la restriccion de exclusion es
            # precisamente lo que lo impide: se descarta y se prueba otra.
            #
            # Se captura IntegrityError y no Exception a proposito: un error
            # de conexion o de esquema debe propagarse, no confundirse con una
            # colision y hacer que el bucle gire hasta agotar los intentos.
            # El rollback del punto de guardado ya expulsa de la sesion los
            # objetos que se anadieron dentro.  Llamar a `expunge` despues
            # falla con "is not present in this Session": por eso el `add` va
            # dentro del punto y no hay que limpiar nada a mano.
            await punto.rollback()
            colisiones += 1
            continue
        else:
            await punto.commit()

        creadas += 1

        # Relacion asistencial: es lo que permitira al profesional leer la
        # historia de ese paciente.  Se crea a partir de la cita, que es el
        # vinculo real.
        existe = (
            await sesion.execute(
                select(RelacionAsistencial).where(
                    RelacionAsistencial.paciente_id == paciente.id,
                    RelacionAsistencial.profesional_id == profesional.id,
                )
            )
        ).scalar_one_or_none()
        if existe is None:
            sesion.add(
                RelacionAsistencial(
                    paciente_id=paciente.id,
                    profesional_id=profesional.id,
                    origen="CITA",
                    cita_id=cita.id,
                )
            )

    await sesion.flush()
    resumen.citas = creadas
    resumen.colisiones_descartadas = colisiones

    return resumen
