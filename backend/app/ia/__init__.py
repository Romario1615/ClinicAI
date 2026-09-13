"""Capa de IA: proveedores, recuperacion, saneamiento y herramientas.

La frontera que gobierna este paquete: **el agente no escribe en la base de
datos y no toma decisiones clinicas** (CLAUDE.md, reglas 4 y 5). Lo unico que
puede invocar son las herramientas de `app/ia/herramientas/`, que pasan por la
capa de servicios con el principal y el ambito del solicitante.
"""
