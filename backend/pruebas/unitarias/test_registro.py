"""Pruebas de la redaccion de datos sensibles en los registros.

Verifican el requisito RNF-14.  Los logs son una fuga en potencia: se copian
a agregadores, se comparten al depurar y se conservan mas tiempo que los
datos operativos.  La estrategia no es confiar en que nadie registre datos
sensibles, sino eliminarlos antes de escribir.
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator

import pytest
import structlog

from app.nucleo.registro import (
    MARCA_REDACTADO,
    campos_sensibles_en,
    comprobar_texto_sin_datos_sensibles,
    configurar_registro,
    obtener_logger,
    procesador_redaccion,
)

pytestmark = [pytest.mark.unitaria, pytest.mark.seguridad]


def _redactar(evento: dict[str, object]) -> dict[str, object]:
    return dict(procesador_redaccion(None, "info", evento))  # type: ignore[arg-type]


class TestCamposSensibles:
    @pytest.mark.parametrize(
        "campo",
        [
            "nombre",
            "apellido",
            "numero_documento",
            "telefono",
            "telefono_whatsapp",
            "correo",
            "diagnostico",
            "diagnosticos",
            "motivo_consulta",
            "medicamento_nombre",
            "dosis",
            "alergias",
            "nota",
            "contenido",
            "mensaje",
            "contrasena",
            "token",
            "access_token",
            "authorization",
            "secreto_2fa",
        ],
    )
    def test_los_campos_sensibles_se_redactan(self, campo: str) -> None:
        evento = {"event": "algo ocurrio", campo: "valor-real-sensible"}
        assert _redactar(evento)[campo] == MARCA_REDACTADO

    @pytest.mark.parametrize(
        "campo",
        [
            "paciente_id",
            "profesional_id",
            "usuario_id",
            "cita_id",
            "clinica_id",
            "sede_id",
            "documento_id",
            "receta_id",
            "correlacion_id",
        ],
    )
    def test_los_identificadores_si_se_registran(self, campo: str) -> None:
        """Se registra a quien se refiere el evento, no sus datos.

        Sin identificadores no se puede depurar nada; con datos personales se
        filtra informacion.  Los identificadores son el punto medio.
        """
        identificador = "3f2b7c1e-0000-4000-8000-000000000001"
        evento = {"event": "consulta", campo: identificador}
        assert _redactar(evento)[campo] == identificador

    def test_el_prefijo_no_burla_la_redaccion(self) -> None:
        """`nombre_paciente` y `paciente_nombre` quedan cubiertos."""
        evento = {
            "event": "x",
            "nombre_paciente": "Juan",
            "paciente_nombre": "Juan",
            "nombre_del_medicamento": "algo",
        }
        redactado = _redactar(evento)
        assert redactado["nombre_paciente"] == MARCA_REDACTADO
        assert redactado["paciente_nombre"] == MARCA_REDACTADO
        assert redactado["nombre_del_medicamento"] == MARCA_REDACTADO

    def test_deteccion_de_campos_sensibles(self) -> None:
        detectados = campos_sensibles_en(["paciente_id", "nombre", "cita_id", "diagnostico"])
        assert set(detectados) == {"nombre", "diagnostico"}


class TestPatronesDeContenido:
    """Segunda linea de defensa: datos sensibles dentro de texto libre.

    Es el caso de un mensaje de excepcion de base de datos que incluye los
    valores de la fila que provoco el error.
    """

    def test_cedula_en_texto_libre_se_redacta(self) -> None:
        evento = {"event": "fallo la insercion", "detalle_tecnico": "duplicado 0912345678"}
        assert "0912345678" not in str(_redactar(evento))

    def test_correo_en_texto_libre_se_redacta(self) -> None:
        evento = {"event": "x", "detalle_tecnico": "usuario paciente@example.com no existe"}
        assert "paciente@example.com" not in str(_redactar(evento))

    def test_telefono_ecuatoriano_se_redacta(self) -> None:
        for telefono in ("+593987654321", "0987654321"):
            evento = {"event": "x", "detalle_tecnico": f"numero {telefono}"}
            assert telefono not in str(_redactar(evento))

    def test_cabecera_bearer_se_redacta(self) -> None:
        evento = {
            "event": "x",
            "detalle_tecnico": "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc.def",
        }
        resultado = str(_redactar(evento))
        assert "eyJhbGciOiJIUzI1NiJ9" not in resultado

    def test_cadena_de_conexion_con_credencial_se_redacta(self) -> None:
        evento = {
            "event": "fallo de conexion",
            "detalle_tecnico": "postgresql://clinica:contrasenaReal@pg:5432/clinica",
        }
        assert "contrasenaReal" not in str(_redactar(evento))

    def test_clave_privada_pegada_por_error_se_redacta(self) -> None:
        clave = (
            "-----BEGIN PRIVATE KEY-----\n"
            "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQ\n"
            "-----END PRIVATE KEY-----"
        )
        evento = {"event": "x", "detalle_tecnico": clave}
        resultado = str(_redactar(evento))
        assert "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQ" not in resultado

    def test_el_mensaje_del_evento_tambien_se_procesa(self) -> None:
        """El propio mensaje puede llevar datos interpolados."""
        evento = {"event": "no se encontro al paciente con cedula 0912345678"}
        assert "0912345678" not in str(_redactar(evento))

    def test_el_mensaje_no_se_redacta_por_completo(self) -> None:
        """Sin el mensaje no se puede depurar nada."""
        evento = {"event": "fallo al confirmar la cita"}
        assert _redactar(evento)["event"] == "fallo al confirmar la cita"


class TestEstructurasAnidadas:
    def test_diccionario_anidado_se_redacta(self) -> None:
        evento = {
            "event": "x",
            "datos": {"paciente_id": "abc", "nombre": "Juan", "telefono": "0987654321"},
        }
        datos = _redactar(evento)["datos"]
        assert isinstance(datos, dict)
        assert datos["paciente_id"] == "abc"
        assert datos["nombre"] == MARCA_REDACTADO
        assert datos["telefono"] == MARCA_REDACTADO

    def test_lista_de_diccionarios_se_redacta(self) -> None:
        evento = {
            "event": "x",
            "pacientes": [
                {"paciente_id": "1", "nombre": "Ana"},
                {"paciente_id": "2", "nombre": "Luis"},
            ],
        }
        resultado = str(_redactar(evento))
        assert "Ana" not in resultado
        assert "Luis" not in resultado

    def test_lista_larga_se_recorta(self) -> None:
        """Mil pacientes en un log no aportan y multiplican la fuga."""
        evento = {"event": "x", "identificadores": [f"id-{i}" for i in range(100)]}
        resultado = _redactar(evento)["identificadores"]
        assert isinstance(resultado, list)
        assert len(resultado) == 21
        assert "80 elementos mas" in str(resultado[-1])

    def test_estructura_muy_profunda_no_bloquea(self) -> None:
        """Una estructura ciclica o muy profunda no debe colgar el registro."""
        profundo: dict[str, object] = {"nivel": 0}
        actual = profundo
        for i in range(1, 30):
            siguiente: dict[str, object] = {"nivel": i}
            actual["hijo"] = siguiente
            actual = siguiente
        resultado = str(_redactar({"event": "x", "datos": profundo}))
        assert "demasiado-profunda" in resultado

    def test_texto_muy_largo_se_trunca(self) -> None:
        evento = {"event": "x", "detalle_tecnico": "a" * 5000}
        resultado = _redactar(evento)["detalle_tecnico"]
        assert isinstance(resultado, str)
        assert "[truncado]" in resultado
        assert len(resultado) < 5000


class TestComprobadorDePruebas:
    """La utilidad que usan las pruebas de fugas en logs."""

    def test_detecta_datos_sensibles(self) -> None:
        hallazgos = comprobar_texto_sin_datos_sensibles(
            "el paciente 0912345678 escribio a medico@example.com"
        )
        assert "[documento]" in hallazgos
        assert "[correo]" in hallazgos

    def test_texto_limpio_no_produce_hallazgos(self) -> None:
        texto = '{"event": "cita confirmada", "cita_id": "3f2b7c1e-0000-4000-8000-000000000001"}'
        assert comprobar_texto_sin_datos_sensibles(texto) == []

    def test_un_uuid_no_se_confunde_con_una_cedula(self) -> None:
        """Los identificadores del sistema no deben dar falsos positivos."""
        texto = "cita_id=3f2b7c1e-0000-4000-8000-000000000001"
        assert comprobar_texto_sin_datos_sensibles(texto) == []


# ===========================================================================
#  La configuracion real, extremo a extremo
# ===========================================================================
class TestConfiguracionReal:
    """Emite lineas con la configuracion de verdad y mira lo que sale.

    Estas pruebas existen por un fallo concreto: `configurar_registro` usaba
    un factory de structlog incompatible con `add_logger_name`, y **toda**
    linea de registro lanzaba `AttributeError`. La suite estaba en verde
    porque todas las pruebas invocaban el procesador de redaccion de forma
    aislada y ninguna llamaba a la configuracion y despues emitia.

    La leccion es general: probar las piezas no prueba el cableado.
    """

    @pytest.fixture(autouse=True)
    def _restaurar_registro(self) -> Iterator[None]:
        """Devuelve el registro global a su estado previo.

        `configurar_registro` toca estado global de `logging` y de structlog;
        sin restaurarlo, estas pruebas cambiarian el comportamiento de las
        demas segun el orden de ejecucion.
        """
        raiz = logging.getLogger()
        manejadores = list(raiz.handlers)
        nivel = raiz.level
        configuracion_previa = structlog.get_config()
        try:
            yield
        finally:
            raiz.handlers = manejadores
            raiz.setLevel(nivel)
            structlog.configure(**configuracion_previa)

    @staticmethod
    def _capturar(salida: io.StringIO) -> list[dict[str, object]]:
        lineas = [linea for linea in salida.getvalue().splitlines() if linea.strip()]
        return [json.loads(linea) for linea in lineas]

    def test_una_linea_se_emite_sin_lanzar(self) -> None:
        """El fallo original: `AttributeError` en cada linea."""
        salida = io.StringIO()
        configurar_registro(nivel="INFO", formato="json", redactar=True)
        logging.getLogger().handlers[0].setStream(salida)  # type: ignore[attr-defined]

        obtener_logger("prueba").info("evento.de.prueba", identificador="abc")

        eventos = self._capturar(salida)
        assert len(eventos) == 1
        assert eventos[0]["event"] == "evento.de.prueba"
        assert eventos[0]["logger"] == "prueba"
        assert eventos[0]["level"] == "info"

    def test_la_redaccion_se_aplica_de_verdad(self) -> None:
        """No basta con que el procesador funcione: tiene que estar montado."""
        salida = io.StringIO()
        configurar_registro(nivel="INFO", formato="json", redactar=True)
        logging.getLogger().handlers[0].setStream(salida)  # type: ignore[attr-defined]

        obtener_logger("prueba").warning(
            "acceso", telefono="0999999999", nombre="Nombre De Prueba", cita_id="abc-123"
        )

        evento = self._capturar(salida)[0]
        assert evento["telefono"] == MARCA_REDACTADO
        assert evento["nombre"] == MARCA_REDACTADO
        # Un identificador si se registra: es lo que permite investigar.
        assert evento["cita_id"] == "abc-123"

    def test_los_registros_de_otras_librerias_tambien_se_redactan(self) -> None:
        """SQLAlchemy escribe sentencias con sus parametros enlazados.

        Esos parametros son nombres, documentos y telefonos de pacientes. Si
        salieran por un camino distinto al de structlog, la promesa de este
        modulo seria falsa justo donde mas importa.
        """
        salida = io.StringIO()
        configurar_registro(nivel="INFO", formato="json", redactar=True)
        logging.getLogger().handlers[0].setStream(salida)  # type: ignore[attr-defined]

        logging.getLogger("sqlalchemy.engine").warning(
            "SELECT * FROM paciente WHERE correo = 'persona@example.invalid'"
        )

        evento = self._capturar(salida)[0]
        assert evento["logger"] == "sqlalchemy.engine"
        assert "persona@example.invalid" not in json.dumps(evento)

    def test_una_excepcion_se_registra_con_su_traza(self) -> None:
        salida = io.StringIO()
        configurar_registro(nivel="INFO", formato="json", redactar=True)
        logging.getLogger().handlers[0].setStream(salida)  # type: ignore[attr-defined]

        try:
            raise RuntimeError("fallo simulado")
        except RuntimeError:
            obtener_logger("prueba").exception("error.simulado")

        evento = self._capturar(salida)[0]
        assert evento["event"] == "error.simulado"
        assert "RuntimeError" in str(evento.get("exception", ""))

    def test_el_nivel_filtra(self) -> None:
        salida = io.StringIO()
        configurar_registro(nivel="WARNING", formato="json", redactar=True)
        logging.getLogger().handlers[0].setStream(salida)  # type: ignore[attr-defined]

        registro = obtener_logger("prueba")
        registro.debug("no.deberia.salir")
        registro.warning("si.sale")

        eventos = self._capturar(salida)
        assert [e["event"] for e in eventos] == ["si.sale"]

    def test_configurar_dos_veces_no_duplica_las_lineas(self) -> None:
        """Una linea duplicada en una investigacion se lee como dos accesos."""
        salida = io.StringIO()
        configurar_registro(nivel="INFO", formato="json", redactar=True)
        configurar_registro(nivel="INFO", formato="json", redactar=True)
        logging.getLogger().handlers[0].setStream(salida)  # type: ignore[attr-defined]

        obtener_logger("prueba").info("evento.unico")

        assert len(self._capturar(salida)) == 1

    def test_un_nivel_desconocido_falla_al_arrancar(self) -> None:
        """`logging.getLevelName` devolveria "Level X" en lugar de fallar.

        Eso acaba en un filtro que no filtra nada, y en un sistema clinico un
        filtro de registro que no filtra puede significar escribir consultas
        SQL con datos de pacientes en produccion.
        """
        with pytest.raises(ValueError, match="Nivel de registro desconocido"):
            configurar_registro(nivel="VERBOSO")
