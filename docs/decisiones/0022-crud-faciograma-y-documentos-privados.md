# ADR-0022 — Gestión de registros, faciograma y documentos privados

* **Estado:** aceptada
* **Fecha:** 2026-10-07
* **Relacionada con:** [ADR-0008](0008-outbox-transaccional.md),
  [ADR-0011](0011-historia-clinica-append-only.md)

## Contexto

El usuario solicita CRUD de clínicas y usuarios, atención desde la ficha según
la cita, un mapa facial para estética y PDFs de presupuestos, cotizaciones y
recetas que puedan compartirse por WhatsApp. Se conserva la separación entre
administración y atención clínica y el historial de los registros.

## Decisión

1. Clínicas y cuentas se crean, consultan y editan; la baja es desactivación
   reversible. Desactivar una clínica o cuenta revoca sesiones y bloquea el
   acceso. La plataforma gestiona clínicas; administración gestiona cuentas de
   su clínica. Las cuentas de superadministración están protegidas.
2. La ficha incluye **Atención y documentos**, **Faciograma** y **Documentos y PDF**.
   Las dos últimas tienen acceso directo y atajos desde el resumen; la cita
   seleccionada se conserva al cambiar entre las tres pestañas. Elegir una cita fija sede y
   especialidad; el backend valida ambas contra la cita autorizada del paciente.
   La historia completa conserva sus permisos, relación asistencial y módulos.
   Agenda y Pagos reciben el contexto de la cita.
3. El **faciograma** es un SVG propio de 23 zonas anatómicas orientativas. Cada
   zona admite observación, procedimiento escrito por el profesional y estado
   observado, planificado o realizado. No calcula puntos de inyección, dosis ni
   recomendaciones. Se habilita por especialidad desde Catálogo; estética,
   dermatología y cirugía plástica lo reciben por omisión.
4. `registro_paciente` conserva versiones de faciogramas, presupuestos y
   cotizaciones. Corregir exige motivo y crea una versión; anular crea otra.
   PostgreSQL impide editar el contenido o borrar una fila y valida la cadena.
   N3 se conserva al corregir. Solo el autor puede corregir o anular. El filtro
   de sede, especialidad y sensibilidad se aplica antes de paginar.
5. El PDF se construye localmente con texto y vectores, sin recursos remotos.
   Presupuestos/cotizaciones tienen partidas, moneda, vigencia y cálculo decimal
   con redondeo por partida. Los planes propuestos o aceptados pueden generar
   un presupuesto persistido; excluyen procedimientos cancelados. El PDF del
   faciograma añade el mapa gráfico. No son facturas ni firmas certificadas.
6. Una receta PDF solo procede de una receta confirmada existente: copia el
   firmante y la pauta registrados. No admite cambiar medicamentos desde el
   editor de documentos. Suspender la receta invalida su descarga y sus enlaces.
   Su clasificación conserva N3 si lo tiene la receta o se solicita para la
   copia; emitir una receta N2 como documento N3 no reduce esa protección.
7. WhatsApp envía una notificación genérica con enlace privado, nunca el PDF
   clínico como adjunto abierto. Requiere `DOCUMENTOS_WHATSAPP` vigente y
   confirmación explícita del destinatario. Enlaces de 1 a 30 días, token aleatorio
   almacenado con hash y copia cifrada para reintentos, verificación de nacimiento
   o últimos cuatro caracteres del documento cuando no hay nacimiento, límite
   por IP y bloqueo tras cinco errores. Una nueva versión, anulación, caducidad
   o desactivación de la clínica invalida el enlace. N3 y faciogramas se entregan
   de forma presencial desde la descarga autorizada.
8. El outbox deduplica solicitudes y el worker comprueba consentimiento y
   vigencia inmediatamente antes de entregar. Sin proveedor configurado se
   informa **sandbox**. No se ha verificado Meta con credenciales reales.

## Consecuencias

Las acciones clínicas dejan trazabilidad y no dependen de un proveedor para
crear o descargar PDFs. La revisión jurídica de consentimientos y documentos
sigue pendiente (E-2). Revocar consentimiento impide nuevos envíos pendientes;
un enlace ya entregado conserva su plazo mientras el registro siga vigente.
No hay una interfaz de revocación individual de enlaces. Las descargas ya
realizadas por el destinatario no se pueden retirar.
