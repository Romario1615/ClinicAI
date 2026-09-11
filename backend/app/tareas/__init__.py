"""Trabajos en segundo plano.

Son procesos aparte del servidor web. Comparten los servicios y repositorios
de `app/modulos/`, y no importan nada de `app/api/`: la logica de negocio no
puede depender de que exista una peticion HTTP.

Que garantiza la durabilidad
----------------------------
No es Redis. ARQ solo planifica y ejecuta; la fuente de verdad de todo envio
saliente es el outbox en PostgreSQL (ADR-0008). Si Redis se vacia, no se
pierde ningun mensaje: el siguiente barrido vuelve a encontrarlo pendiente.

Lo que si se pierde al vaciar Redis es el *calendario* de ejecucion, y por eso
los trabajos periodicos se declaran en el propio worker como `cron`, no se
programan de forma dinamica.
"""
