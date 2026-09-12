"""Mensajeria saliente y entrante: outbox, plantillas y adaptadores de canal.

Vive fuera de `app/modulos/` porque no es un modulo de negocio: es
infraestructura que atraviesa agenda, lista de espera, historia clinica y
usuarios.  El modelo de datos del outbox si esta en `app/modulos/outbox/`,
junto al resto de modelos, porque Alembic los necesita a todos en un mismo
sitio.
"""
