"""Division de documentos en fragmentos.

Por que merece pruebas propias
------------------------------
Un error aqui **no falla**: degrada la recuperacion en silencio. Fragmentos
que empiezan a media frase puntuan peor en la busqueda textual, y una
instruccion partida por la mitad produce una respuesta incompleta sobre una
preparacion de examen -- «no comer nada» en un fragmento y «puede beber agua»
en otro.

Es logica pura, asi que se prueba aparte y con casos concretos.
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from app.modulos.conocimiento.fragmentacion import (
    MINIMO_UTIL,
    fragmentar,
    normalizar_texto,
)

pytestmark = pytest.mark.unitaria

PARRAFO = (
    "Preparacion para el examen de sangre. No comer nada desde las 22:00 de la "
    "noche anterior. Puede beber agua sin limite. Debe suspender el ejercicio "
    "intenso 24 horas antes. Traiga la orden medica y su documento."
)


# ---------------------------------------------------------------------------
#  Normalizacion
# ---------------------------------------------------------------------------
def test_un_salto_simple_dentro_del_parrafo_se_convierte_en_espacio() -> None:
    """Los PDF parten las frases con saltos que no son separaciones reales.

    Dejarlos hace que el corte por frase falle y que la busqueda textual
    indexe palabras partidas.
    """
    assert normalizar_texto("No comer\nnada desde las 22:00") == ("No comer nada desde las 22:00")


def test_el_salto_doble_se_conserva_porque_marca_parrafo() -> None:
    """Es el mejor punto de corte que hay, y perderlo empeora los fragmentos."""
    assert "\n\n" in normalizar_texto("Titulo\n\nContenido del parrafo")


def test_los_retornos_de_windows_se_normalizan() -> None:
    assert normalizar_texto("uno\r\n\r\ndos") == "uno\n\ndos"


def test_los_espacios_multiples_se_colapsan() -> None:
    assert normalizar_texto("uno     dos\t\tthree") == "uno dos three"


# ---------------------------------------------------------------------------
#  Fragmentacion
# ---------------------------------------------------------------------------
def test_un_texto_vacio_no_produce_fragmentos() -> None:
    assert fragmentar("") == []
    assert fragmentar("   \n\n   ") == []


def test_un_texto_corto_produce_un_solo_fragmento() -> None:
    fragmentos = fragmentar(PARRAFO, tamano=900, solape=150)
    assert len(fragmentos) == 1
    assert fragmentos[0].indice == 0


def test_los_indices_son_consecutivos_desde_cero() -> None:
    """El indice forma parte de la clave unica del fragmento.

    Un hueco o un salto rompe la restriccion al reingerir.
    """
    fragmentos = fragmentar(PARRAFO * 5, tamano=200, solape=40)
    assert [f.indice for f in fragmentos] == list(range(len(fragmentos)))


def test_se_corta_por_parrafo_antes_que_por_frase() -> None:
    """Dos parrafos distintos no se mezclan si cada uno se sostiene solo.

    El segundo tiene que superar `MINIMO_UTIL`: uno mas corto se fusiona con el
    anterior a proposito, porque un fragmento de dos lineas sueltas no responde
    nada. Que el corte por parrafo exista no significa que produzca fragmentos
    inutiles.
    """
    segundo = (
        "Horario de atencion del laboratorio: de lunes a viernes de 07:00 a "
        "11:00, sin necesidad de cita previa para los examenes de rutina."
    )
    assert len(segundo) > MINIMO_UTIL
    texto = PARRAFO + "\n\n" + segundo

    fragmentos = fragmentar(texto, tamano=250, solape=0)
    assert len(fragmentos) >= 2
    assert "Horario de atencion" not in fragmentos[0].contenido


def test_una_frase_mas_larga_que_el_tamano_se_corta_igualmente() -> None:
    """Ocurre con tablas y listas pegadas de un PDF.

    Aqui si hay que cortar a lo bruto: la alternativa seria un fragmento que
    supera el tamano y desborda el contexto.
    """
    larga = "palabra " * 200  # sin puntuacion: una sola «frase»
    fragmentos = fragmentar(larga, tamano=100, solape=0)
    assert len(fragmentos) > 1
    assert all(len(f.contenido) <= 200 for f in fragmentos)


def test_el_solape_arrastra_el_final_del_fragmento_anterior() -> None:
    """Es lo que evita que una instruccion partida quede irrecuperable.

    El fragmento que empieza con «Puede beber agua» lleva delante el «No comer
    nada desde las 22:00» que le daba sentido.
    """
    fragmentos = fragmentar(PARRAFO, tamano=120, solape=40)
    assert len(fragmentos) > 1
    for anterior, siguiente in pairwise(fragmentos):
        # El principio del siguiente aparece en algun punto del anterior.
        inicio = siguiente.contenido.split()[0]
        assert inicio in anterior.contenido


def test_el_solape_no_empieza_a_mitad_de_palabra() -> None:
    """Un fragmento que empieza por «…iones previas» confunde a la busqueda.

    Y a quien lo lee al revisar por que el agente respondio algo.
    """
    fragmentos = fragmentar(PARRAFO, tamano=120, solape=40)
    for fragmento in fragmentos[1:]:
        primera = fragmento.contenido.split()[0]
        # La primera palabra del solape debe aparecer completa en el original.
        assert primera in PARRAFO


def test_sin_solape_los_fragmentos_no_se_repiten() -> None:
    fragmentos = fragmentar(PARRAFO, tamano=120, solape=0)
    contenidos = [f.contenido for f in fragmentos]
    assert len(contenidos) == len(set(contenidos))


def test_un_titulo_suelto_se_fusiona_con_su_parrafo() -> None:
    """«## Preparacion» recuperado por si solo no responde nada.

    Unido al parrafo que encabeza, si.
    """
    texto = f"## Preparacion\n\n{PARRAFO}"
    fragmentos = fragmentar(texto, tamano=900, solape=0)
    assert len(fragmentos) == 1
    assert "Preparacion" in fragmentos[0].contenido


def test_un_ultimo_trozo_corto_se_pega_al_anterior() -> None:
    """No queda suelto: un fragmento de diez caracteres no responde nada."""
    texto = f"{PARRAFO}\n\nFin."
    fragmentos = fragmentar(texto, tamano=900, solape=0)
    assert all(len(f.contenido) >= MINIMO_UTIL for f in fragmentos)
    assert "Fin." in fragmentos[-1].contenido


def test_un_texto_entero_mas_corto_que_el_minimo_se_conserva() -> None:
    """No se descarta: un documento corto sigue siendo documentacion."""
    fragmentos = fragmentar("Horario: 08:00 a 17:00.", tamano=900, solape=0)
    assert len(fragmentos) == 1
    assert fragmentos[0].contenido == "Horario: 08:00 a 17:00."


# ---------------------------------------------------------------------------
#  Parametros invalidos
# ---------------------------------------------------------------------------
def test_un_tamano_no_positivo_se_rechaza() -> None:
    with pytest.raises(ValueError, match="positivo"):
        fragmentar(PARRAFO, tamano=0)


def test_un_solape_mayor_o_igual_que_el_tamano_se_rechaza() -> None:
    """Con solape >= tamano el bucle no avanzaria.

    Se rechaza en lugar de corregirlo en silencio: un solape mal configurado
    produciria fragmentos casi identicos y nadie sabria por que.
    """
    with pytest.raises(ValueError, match="menor que el tamano"):
        fragmentar(PARRAFO, tamano=100, solape=100)
    with pytest.raises(ValueError, match="menor que el tamano"):
        fragmentar(PARRAFO, tamano=100, solape=150)


def test_un_solape_negativo_se_rechaza() -> None:
    with pytest.raises(ValueError, match="no negativo"):
        fragmentar(PARRAFO, tamano=100, solape=-1)


# ---------------------------------------------------------------------------
#  Estimacion de tokens
# ---------------------------------------------------------------------------
def test_la_estimacion_de_tokens_nunca_es_cero() -> None:
    """Un cero en el panel pareceria un fragmento vacio.

    La estimacion es aproximada -- ~4 caracteres por token en espanol -- y solo
    sirve para dar idea del tamano, pero no puede mentir en el limite.
    """
    fragmentos = fragmentar("Hola.", tamano=900, solape=0)
    assert fragmentos[0].tokens_aproximados >= 1
