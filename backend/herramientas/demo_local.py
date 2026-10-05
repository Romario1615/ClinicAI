"""Consulta el estado local sin imprimir secretos ni modificar datos."""

import argparse
import json

from sqlalchemy import create_engine, text

from app.nucleo.configuracion import Configuracion


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configuracion", action="store_true")
    opciones = parser.parse_args()
    try:
        configuracion = Configuracion()
    except ValueError:
        print("Configuracion invalida. Revise los nombres y valores de .env.")
        return 1
    if configuracion.entorno.value != "local":
        print("Este comando requiere ENTORNO=local.")
        return 1
    datos: dict[str, object] = {
        "entorno": configuracion.entorno.value,
        "llm": configuracion.proveedor_llm,
        "whatsapp": configuracion.modo_whatsapp,
        "calendario": configuracion.modo_calendario,
    }
    if not opciones.configuracion:
        motor = create_engine(configuracion.url_base_datos_sincrona)
        try:
            with motor.connect() as conexion:
                filas = conexion.execute(text(
                    "SELECT id, nombre FROM clinica WHERE nombre LIKE :marca "
                    "ORDER BY nombre DESC"
                ), {"marca": "%[SINTETICO]%"}).all()
                datos["clinicas"] = [{"id": str(f.id), "nombre": f.nombre} for f in filas]
        finally:
            motor.dispose()
    print(json.dumps(datos, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
