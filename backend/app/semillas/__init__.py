"""Semillas: catalogos del sistema y datos sinteticos.

Se distinguen dos cosas que nunca deben mezclarse:

* **Catalogos del sistema** (`catalogos.py`): permisos y roles base.  Son
  parte del funcionamiento, no datos de prueba.  Se cargan en TODOS los
  entornos, produccion incluida, y su carga es idempotente.

* **Datos sinteticos** (`sinteticos.py`): clinica, profesionales, pacientes y
  citas de ejemplo.  Son SIEMPRE ficticios, generados con Faker en espanol, y
  el cargador se niega a ejecutarse con `ENTORNO=produccion`.

Nunca se usan datos reales de pacientes en desarrollo, pruebas ni
demostraciones (regla 6 de CLAUDE.md).
"""
