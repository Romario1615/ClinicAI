# Respuesta a incidentes

> **Estado:** procedimiento escrito, **no ensayado**. Ningún simulacro se ha
> ejecutado y no hay guardia definida. Un procedimiento que nadie ha practicado
> falla la primera vez que se usa, que es siempre el peor momento.
>
> Los pasos técnicos que aquí se citan —restauración, rollback de esquema— sí
> están verificados; ver [`backup-and-restore.md`](backup-and-restore.md).

---

## 1. Antes de nada: los tres datos que hay que tener a mano

Cuando empieza un incidente, lo que se pierde primero es el tiempo buscando
dónde mirar.

| Dato | Dónde |
|---|---|
| `correlacion_id` | Viene en el cuerpo de todo error de la API. Es la clave para encontrar la traza exacta |
| Estado del servicio | `GET /salud/vivo` y `GET /salud/listo` |
| Última migración aplicada | `uv run alembic current` |

---

## 2. Clasificación

La gravedad no la fija la dificultad técnica, sino el daño al paciente.

| Nivel | Definición | Ejemplos |
|---|---|---|
| **G1 — Daño a un paciente** | Alguien puede recibir atención incorrecta, o no recibirla | Dos pacientes citados a la misma hora; historia de un paciente visible para quien no debe; recordatorios de medicación que no salen |
| **G2 — Datos comprometidos** | Acceso indebido, confirmado o probable | `TOKEN_REUTILIZADO` repetido; `EXPORTACION_TITULAR` no justificada; volcado de respaldo en claro |
| **G3 — Servicio caído** | El sistema no responde, sin pérdida de datos | La API no arranca; PostgreSQL inaccesible |
| **G4 — Degradación** | Funciona peor, nadie se ha dado cuenta | Redis caído y el límite de tasa fallando abierto (E‑11); un canal del outbox en sandbox |

**Un G4 que dura se convierte en G1.** El outbox parado es degradación durante
una hora y una cita perdida al día siguiente.

---

## 3. Lo primero, siempre

1. **Anotar la hora y qué se vio.** No de memoria: en el momento.
2. **No reiniciar por reflejo.** Un reinicio borra el estado que explica la
   causa. Si hay que reiniciar, capturar antes registros y `alembic current`.
3. **No tocar la base de datos a mano.** Un `UPDATE` directo durante un
   incidente es cómo un incidente recuperable se vuelve irreversible. La
   historia clínica es append‑only: lo que se escriba mal no se borra.
4. **Decidir si hay que parar.** Ante un G1, **parar el servicio es correcto**.
   Una clínica puede trabajar una hora en papel; no puede deshacer una atención
   dada con datos equivocados.

---

## 4. Guías por tipo

### 4.1 Dos pacientes a la misma hora (G1)

No debería ocurrir: lo impide una restricción de exclusión del motor. Si ocurre,
**la restricción no está**.

```sql
select conname from pg_constraint where contype = 'x';
-- Deben aparecer: cita_sin_solape_profesional, cita_sin_solape_consultorio
```

Si faltan, lo más probable es una restauración incompleta o una migración a
medias. **Parar el servicio**: mientras no estén, cada reserva puede duplicar
otra. Restaurar según [`backup-and-restore.md`](backup-and-restore.md) y
comprobar el recuento **antes** de volver a abrir.

### 4.2 Un paciente ve datos de otro (G1 + G2)

1. **Parar el servicio.** No hay diagnóstico que justifique seguir sirviendo.
2. Buscar en auditoría quién accedió a qué: `paciente_id`, `actor_id`, ventana.
3. La auditoría registra **referencias, no contenido**: dice que se accedió, no
   qué se leyó. Para el alcance hay que reconstruirlo del identificador.
4. No restaurar todavía: una restauración borra la evidencia de qué ocurrió.
5. Esto **es notificable** bajo la LOPDP. La obligación, los plazos y el
   destinatario los determina el asesor jurídico de la clínica; este documento
   no los fija (E‑2).

### 4.3 Los recordatorios no salen (G4 → G1)

```sql
select estado, count(*), min(creado_en) from outbox_mensaje group by estado;
```

* `PENDIENTE` creciendo con fechas viejas → el worker no corre. Arrancarlo.
* `FALLIDO` > 0 → agotaron reintentos. Mirar el último error de cada uno.
* Todo `ENTREGADO` pero nadie recibe nada → **canal en sandbox**. Revisar
  `outbox.canal_en_sandbox` en el arranque (E‑16). En producción esto significa
  que el sistema lleva marcando como entregado lo que nunca salió.

### 4.4 La API no arranca (G3)

```bash
uv run alembic current    # ¿coincide con el código desplegado?
```

* Migración a medias → `alembic upgrade head`, o `downgrade -1` y desplegar la
  versión anterior. El rollback de esquema **está verificado**: cada migración
  se prueba con `upgrade → downgrade -1 → upgrade`.
* `arranque.base_datos_inaccesible` → es PostgreSQL, no la aplicación.
* Falta una variable de entorno → el arranque falla explícitamente en lugar de
  arrancar a medias, que es deliberado.

### 4.5 Sospecha de credencial comprometida (G2)

1. **Rotar el secreto primero**, investigar después. El orden importa.
2. `TOKEN_REUTILIZADO` revoca la familia de sesiones automáticamente; confirmar
   que ocurrió.
3. Si es la firma del webhook de WhatsApp: rotar en Meta y en el entorno. Hasta
   entonces, todo mensaje entrante es sospechoso.
4. Si es `CLAVE_RESPALDO`: **los respaldos anteriores siguen cifrados con la
   clave antigua**. No se borran; se conserva la clave antigua en custodia y se
   vuelve a cifrar con la nueva cuando haya tiempo.

### 4.6 El agente hizo algo que no debía (G1 o G2)

1. La demostración solo existe en `local`; en producción **no hay agente**
   todavía (E‑23). Si aparece actividad de agente en producción, eso ya es el
   incidente.
2. Buscar en auditoría `actor_tipo = 'AGENTE_IA'` y `origen = 'DEMO_LOCAL'`:
   están separados de la actividad real precisamente para esto.
3. `HERRAMIENTA_DENEGADA` repetida con nombres inventados sugiere que alguien
   está probando qué hay detrás del modelo.

---

## 5. Después

1. **Escribir qué pasó el mismo día.** Al día siguiente ya se recuerda mal.
2. Sin culpables: lo que hay que corregir es el sistema que lo permitió.
3. **Una prueba que falle con el fallo.** Es lo único que impide que vuelva.
   Cada limitación de `known-limitations.md` salió de algo que se descubrió;
   la prueba es lo que lo mantiene descubierto.
4. Si reveló una limitación nueva, añadirla a `known-limitations.md` **aunque no
   se vaya a arreglar ahora**.

---

## 6. Lo que falta para que esto sea real

| Pendiente | Sin ello |
|---|---|
| **Guardia definida** | Nadie recibe la alerta a las 3 de la mañana |
| **Simulacro ejecutado** | El procedimiento falla la primera vez que se usa |
| **Vías de contacto** | Se pierde el tiempo buscando a quién llamar |
| **Criterio de notificación legal** | Ante un G2 nadie sabe si hay que notificar, a quién ni en cuánto tiempo (E‑2) |
| **Alertas conectadas** | [`monitoring.md`](monitoring.md) define qué vigilar; nada lo vigila |

**El más importante es el simulacro.** Restaurar un respaldo por primera vez
durante un incidente real, con la clínica parada, es cuando se descubre que
falta la clave.
