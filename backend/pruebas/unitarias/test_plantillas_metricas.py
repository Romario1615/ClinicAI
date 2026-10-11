"""El catálogo de métricas no conserva instancias ni datos de una clínica."""

import pytest

from app import main

pytestmark = pytest.mark.unitaria


def test_catalogo_se_calcula_una_vez_y_solo_contiene_plantillas(monkeypatch):
    original = main._registrar_rutas
    llamadas = []

    def registrar(mapa):
        llamadas.append(True)
        original(mapa)

    main._plantillas_metricas.cache_clear()
    monkeypatch.setattr(main, "_registrar_rutas", registrar)
    try:
        primera = main._plantillas_metricas()
        segunda = main._plantillas_metricas()
        assert primera is segunda
        assert len(llamadas) == 1
        assert all(isinstance(p, str) for p in primera)
        assert "/api/v1/pacientes/{paciente_id}" in primera
        assert "/api/v1/publico/documentos/{token}/acceso" in primera
        assert "/salud/listo" in primera
        assert "/metrics" not in primera
    finally:
        main._plantillas_metricas.cache_clear()
