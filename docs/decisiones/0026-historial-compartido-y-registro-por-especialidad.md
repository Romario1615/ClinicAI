# ADR-0026 — Consulta compartida y registro por especialidad

Fecha: 2026-10-09. Estado: aceptado por el propietario mediante aclaración expresa.

## Contexto

El propietario pide herramientas disponibles desde el alta del paciente, tanto
en la ficha como en Historia clínica. Confirma que todos los roles consultan,
recepción y asistencia no introducen contenido clínico y cada profesional
registra únicamente con su especialidad. Esta decisión actualiza la restricción
de lectura administrativa documentada en ADR-0022 y la lectura entre áreas.

## Decisión

- Los seis roles base reciben `historia_clinica.consultar_compartida` y los
  permisos de lectura N2 de historia, recetas, imágenes, odontograma y planes.
  La consulta no necesita una cita ni una relación asistencial previa.
- Los filtros de clínica, paciente, especialidad autorizada y sensibilidad
  siguen aplicándose en SQL. El comodín de especialidades sirve para observar
  otras áreas; no acredita para registrar en ellas.
- Recepción, asistencia, administración, auditoría y plataforma consultan.
  La asistencia pierde la carga de imágenes clínicas. Registrar tomas y
  atender alertas clínicas exige escritura clínica y profesional responsable.
  Los permisos administrativos de datos de identificación, agenda y pagos
  mantienen su alcance independiente.
- La escritura requiere perfil activo, permiso específico, especialidad propia,
  relación asistencial y los controles de autoría existentes. Odontograma y
  periodontograma pertenecen a Odontología; faciograma a las áreas estéticas
  compatibles configuradas. Las correcciones conservan sus versiones.
- **Comenzar atención sin cita** crea, por decisión explícita del profesional,
  una relación asistencial propia auditada e idempotente. No crea citas,
  notas, tratamientos ni mediciones. El motivo es obligatorio.
- Con cita, **Iniciar atención** en Agenda crea el vínculo del profesional
  asignado después de registrar la llegada. La apertura de la ficha y la
  consulta del historial no conceden escritura. El vínculo se audita en la
  misma transacción y se reutiliza si ya existe uno permanente vigente.
- El alta prepara secciones vacías mediante las rutas existentes. No se
  inventan registros para representar disponibilidad ni se confunde falta
  de medición con cero.
- Si el paciente no tiene odontograma guardado, la plantilla propone dentición
  temporal antes de los 6 años, mixta de 6 a 12 y permanente desde los 13.
  Es una sugerencia de presentación basada en la edad disponible, no un dato
  clínico persistido; el profesional puede cambiarla antes de guardar. Si ya
  existe una versión, se respeta la dentición guardada.
- N3 y Formulario 033 siguen exigiendo `historia_clinica.leer_sensible`.
  La consulta compartida no concede ese permiso. El agente IA no recibe esta
  capacidad ni acceso a nuevas operaciones clínicas.
- Los roles personalizados conservan sus asignaciones actuales; administración
  puede delegar estas lecturas si las posee y asigna un ámbito explícito.

## Implementación y consecuencias

Migración `20261009_038`, detrás de `20261009_037`: modifica solo los roles
base globales y conserva cada asignación previa en una tabla de respaldo
para reversión exacta. No modifica historia clínica ni cuentas.

El selector compartido enlaza ficha e historial, indica **Solo consulta** o
**Consultar y registrar** y selecciona el área compatible de cada herramienta.
Las secciones aparecen vacías antes de su primera evaluación. Los seis
manuales de Ayuda explican recorridos diferentes para cada rol.

La consulta clínica disponible para personal administrativo es un cambio
deliberado de política. La clínica debe asignar ámbitos concretos a sus cuentas;
el comodín permite todos los pacientes de esa clínica, nunca otra clínica.
Las validaciones jurídicas y de proveedores pendientes siguen documentadas
en preparación para producción; esta decisión no las resuelve.

## Evidencia y reversión

[Informe de implementación y pruebas](../verificacion-ficha-marca-2026-10-09.md).
Para revertir este bloque, detener las mutaciones, volver al código anterior y
ejecutar `alembic downgrade 20261009_037`. La reversión restaura las
asignaciones previas, conserva los registros clínicos y no revierte la
migración de WhatsApp `037`. Renovar las sesiones tras cambiar permisos.
