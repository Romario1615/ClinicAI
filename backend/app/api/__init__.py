"""Ensamblaje HTTP: middleware, traduccion de errores y registro de rutas.

Es la unica capa que conoce FastAPI ademas de los `rutas.py` de cada modulo.
Los servicios y repositorios no importan nada de aqui: eso es lo que permite
que el worker de tareas y el agente de IA reutilicen la misma logica sin
levantar un servidor web.
"""
