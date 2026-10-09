# Verificación integral de formularios y consultas — 2026-10-09

## 1. Solicitud

Probar formularios, consultas y lógica de negocio, corregir los fallos y
conservar evidencia reproducible. Se mantienen las decisiones de ADR-0026
sobre consulta compartida y edición clínica por especialidad.

## 2. Inventario

**66 formularios en 45 plantillas**, incluidos filtros y chats. Todas tienen
suite de componente. [Matriz de formularios y consultas](matriz-formularios-consultas.md).
Las acciones clínicas que usan botones también se recorren en API y navegador.

## 3. Reglas verificadas

Datos requeridos y límites, permisos y ámbito, guardado/consulta posterior,
rechazos sin mutaciones, reintentos e idempotencia, paginación y filtros,
historial de versiones, precisión monetaria, archivos privados, PDF,
anti doble reserva y restricciones de seguridad del agente.

## 4. Correcciones

- Alembic conserva el respaldo de permisos de la revisión 038 durante
  autogenerate/check; su downgrade sigue siendo quien gestiona la tabla.
- Los formularios administrativos bloquean envíos adicionales durante el guardado.
- Cambio de contraseña valida longitud, contraseña inicial y confirmación;
  conserva la sesión al fallar y la cierra después del cambio confirmado.
- Chat: validación del envío por teclado/formulario, composición de texto y
  región accesible que reúne mensajes y controles.
- El simulador muestra los horarios recibidos y su derivación en el área de acciones.
- «Confirmar cita» confirma únicamente la reserva de la memoria del canal;
  no se interpreta como una nueva búsqueda. Las dos barreras clínicas preceden
  la operación, incluso con baja confianza del clasificador.
- Gastos rechaza más de dos decimales sin redondear silenciosamente.
- Catálogo conserva el mensaje específico cuando el registro se guardó pero
  sus fotos requieren reintento, en lugar de ocultarlo con un error genérico.
- Las descripciones de los seis roles coinciden con ADR-0026. La recarga local
  de catálogos actualizó solo seis descripciones: ningún permiso ni asignación.
- La prueba de ficha reconoce el historial integrado y verifica consulta y
  trazabilidad, conforme a la política actual; no espera el texto anterior.

## 5. Archivos

`backend/alembic/env.py`, `app/ia/conversacion.py`, semillas, fixtures API,
pruebas de formularios/consultas y filtro Alembic;
chat compartido, Agente demo, Gastos, Catálogo, Usuarios, Equipo, configuración,
Delegaciones y cambio de contraseña; suites de componente y escenarios 03/23.
README, matriz, plan de pruebas, limitaciones y preparación para producción.

## 6. Diseño y permisos

No se amplían permisos ni se cambia el formato de la historia clínica. El
servidor conserva la autorización y los filtros SQL. El bloqueo de la interfaz
complementa la idempotencia y las restricciones de PostgreSQL.

## 7. Entorno

PostgreSQL y Redis reales locales. Bases temporales separadas para navegador y
backend; cuatro trabajadores backend con una base y Redis propios. IA/embeddings
mock, WhatsApp/calendario sandbox. El navegador usa API 8020 y app 4200, sin
recargador en la API temporal. El límite de acceso elevado solo se aplica a ella.

## 8. Backend

Comando habitual reproducible, desde `backend`, con una base de pruebas migrada:

```powershell
.venv/Scripts/python.exe -m pytest --cov=app --cov-report=term -q
```

La ejecución de esta revisión usa además `-p qa_worker -n 4 --dist=loadfile`;
el complemento temporal asigna bases y Redis independientes antes de importar
las fixtures. No se ejecuta `-n 4` contra una base compartida.

**2220 aprobadas, tres omitidas**, 1231,90 s (20 min 31 s), cobertura global
**88,89 %** (mínimo 80 %). Las tres omitidas llaman a Anthropic real y requieren
`PRUEBAS_LLM_REAL=1`; no se omitió ninguna prueba local por fallar.

La repetición anterior aprobó 2204 y omitió las mismas tres, en 1099,45 s
(88,64 %). Se repitió completa después del arreglo de confirmación y de sus
16 casos adicionales, para que el resultado final incluya el código definitivo.

## 9. Interfaz

```powershell
cd frontend
$env:VITEST_MAX_WORKERS='3'
npx.cmd ng test --no-watch --coverage
```

Se limita el número de trabajadores sin elevar timeouts ni rebajar aserciones
o umbrales. **817/817 en 107 archivos**, 200,74 s.

| Cobertura | Resultado |
|---|---:|
| Sentencias | 85,28 % |
| Ramas | 72,56 % |
| Funciones | 81,12 % |
| Líneas | 87,74 % |

## 10. Navegador

```powershell
cd pruebas-e2e
$env:URL_API='http://127.0.0.1:8020/api/v1'
$env:PLAYWRIGHT_BROWSERS_PATH='D:/playwright-browsers'
npx.cmd playwright test --project=chromium --workers=1
```

Sin reintentos. Incluye seis roles, accesibilidad axe, escritorio/móvil,
CRUD, documentos, herramientas clínicas, agentes, caja y persistencia por API.
**90/90 en 23 archivos**, 21,0 min, sin reintentos. Los seis roles completan
axe y las secciones del menú; no hay desplazamiento de página en escritorio
ni desbordamiento móvil en el recorrido automático. Se comprueban también
historias y herramientas vacías, registro por especialidad, primera atención
sin cita, imágenes privadas, PDF y gastos con consulta posterior.

## 11. Incidencias de las corridas iniciales

La primera interfaz tuvo timeouts de inicialización al compartir recursos con
la batería backend. Se repite con menos trabajadores. El primer navegador
obtuvo 86 aprobadas y tres fallos entre 89 pruebas, en 20,7 min. Detectó
horarios sin botones en el simulador, una región de chat ausente y una aserción
antigua de ficha administrativa. Las regresiones nuevas de chat se ejecutaron
fallando antes de las correcciones.

La primera batería completa de backend obtuvo 2180 aprobadas, 23 fallos,
un error y tres omitidas (87,80 %). Las pruebas de roles/plataforma/usuarios
dependían de los catálogos sembrados en desarrollo: ahora los cargan en su
transacción reversible. La comprobación antigua de semillas negaba toda
lectura clínica a recepción; se actualiza a ADR-0026 y verifica además que
los cinco roles no profesionales carecen de escritura y lectura sensible.
La prueba nueva de paginación usaba una fixture inexistente; ahora utiliza el
paciente ajeno preparado por la suite API. Los módulos afectados aprobaron
**90/90** en la repetición enfocada.

En la repetición de navegador apareció la interpretación incorrecta de
«Confirmar cita». Las regresiones de confirmación se ejecutaron antes del
arreglo: cinco fallaron y cuatro pasaron. La prueba de gastos corrigió su
selector para incluir el asterisco del campo obligatorio; no se cambió la
interfaz para satisfacer el selector. Ese recorrido aprobó posteriormente.

## 12. Análisis estático

Ruff y formato aprobados (469 archivos), mypy aprobado (255 archivos),
Bandit `-ll` sin hallazgos medianos/altos y lint Angular aprobado. Compilación
de producción aprobada, sin avisos de presupuesto: paquete inicial 468,69 kB,
129,44 kB estimados de transferencia.

## 13. Migraciones

No hay una revisión nueva. Se comprueba creación de bases desde cero, esquema
sin diferencias inesperadas y downgrade 038 → 037 → upgrade head en una base
temporal. El respaldo 038 queda excluido expresamente de autogenerate; otras
tablas desconocidas siguen detectándose.

Ambas bases nuevas alcanzaron `20261009_038`. El ciclo de reversión y el
`alembic check` posterior aprobaron. Se conservan los avisos existentes sobre
orden cíclico de claves foráneas, columnas calculadas y comparación de la
clase de operador trigram; no se atribuye a `check` una validación de esos
objetos que Alembic no compara.

## 14. Secretos y vulnerabilidades

No se usan datos reales ni credenciales externas. Los diez commits locales
anteriores a este bloque pasaron Gitleaks. El índice de interfaz y el índice
del cierre backend/documentación también aprobaron el análisis, sin hallazgos:

```powershell
git diff --cached | gitleaks stdin --redact --report-format json --report-path ...
```

`npm audit --audit-level=high --json` obtuvo cero vulnerabilidades en frontend.
Se exportó el lock Python con `uv export --frozen --no-emit-project --no-hashes
--extra dev --extra llm` y se auditó con `pip-audit --strict --desc --disable-pip
--no-deps -r ...`: ninguna vulnerabilidad conocida. El extra opcional
`embeddings` no forma parte de esa exportación; E-12 continúa documentado.
No se ejecutaron Trivy, DAST ni un pipeline remoto nuevo en esta revisión.

## 15. Staging y producción

Estas pruebas acreditan el entorno local. Staging/producción requieren sus
credenciales, TLS, límites de acceso normales, almacenamiento privado, copia
de seguridad y pruebas de integración con los proveedores contratados.
No se realiza un despliegue en esta revisión.

## 16. Rollback

Revertir los commits del bloque devuelve validaciones/presentación anteriores;
no hay una migración adicional que revertir. El downgrade de 038 conserva el
procedimiento documentado de restauración de permisos y no borra historia.

## 17. Restauración y limpieza

Las fixtures API revierten transacciones; la concurrencia usa entidades
sintéticas propias. Los recorridos de navegador escriben solo en su base
temporal. Se detiene la API 8020 y se eliminan exclusivamente las bases
registradas de esta revisión al terminar; la aplicación de trabajo permanece.

**Limpieza comprobada:** API 8020 detenida y seis bases propias eliminadas.
Se retiraron cuatro objetos cifrados creados por los recorridos, a partir de
las claves de su base y excluyendo referencias de desarrollo; cada archivo
se resolvió dentro del almacén y del repositorio, sin borrado recursivo.
La guía E2E ahora configura también un almacén local exclusivo.
`http://localhost:4200/acceso` y `http://127.0.0.1:8000/salud/listo`
responden **200**. El frontend escucha en IPv6 local (`::1`); se verifica por
`localhost`. No se deja una segunda aplicación de trabajo.

## 18. Límites y preparación

No se comprueban envíos reales, cámaras físicas ni aceptación clínica por
especialistas. El navegador cubre recorridos representativos; no todas las
combinaciones posibles de entradas. Las pruebas de componente/API complementan
esos recorridos. **El bloque local queda comprobado con las tres baterías
completas aprobadas y su entorno temporal retirado.** Las condiciones externas
de producción de E-1/E-2 y el despliegue supervisado continúan pendientes.

Cambios guardados por bloques en `main`: interfaz `721d734`, seguido del
cierre backend, consultas y documentación. No se publican los commits
anteriores pendientes. Logs e informes JSON locales de esta ejecución:
`tmp/qa-20261009-formularios/` (ignorado por Git). El inventario de 45 plantillas,
66 formularios y sus 91 enlaces se comprobó antes del cierre.
