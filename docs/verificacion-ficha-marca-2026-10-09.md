# Verificación de ficha, roles y marca — 2026-10-09

## 1. Solicitud y alcance

Ficha e historial con todas las herramientas autorizadas disponibles desde el
alta. Aclaración expresa del propietario: todos los roles consultan; recepción
y asistencia no registran información clínica; edición según especialidad.
Portada con el logo existente, nombre mayor y celeste turquesa, conservando
la imagen original y el estilo de vidrio.

## 2. Funciones implementadas

Selector compartido de evolución, recetas, indicaciones, documentos/PDF,
odontograma, periodontograma/placa, planes, faciograma e imágenes. El selector
informa consulta o registro y elige el área compatible. Historia usa el
periodontograma completo; las colecciones vacías no fabrican contenido.

El profesional puede iniciar explícitamente una atención sin cita. Se crea
solo su relación asistencial propia auditada; después registra cada evaluación.
Los seis manuales de Ayuda incluyen recorridos distintos para cada rol.

## 3. Archivos principales

- `compartido/herramientas-paciente.component.ts`: selector y primera atención.
- `ficha-paciente`, `atencion-paciente`, `historia-clinica` y componentes
  clínicos: navegación, contexto y controles de edición.
- `pacientes/servicios.py` y `rutas.py`: inicio sin cita con ámbito y auditoría.
- `autorizacion.py`, servicios de usuarios y filtros clínicos: consulta N2
  compartida y registro limitado al profesional.
- `historia/servicios.py` y Medicamentos: registro de tomas y alertas solo
  por el profesional responsable; consulta del resto del personal.
- `marca`, acceso, logo SVG, fondos y estilos globales: identidad visual.
- `ayuda/manuales.py`, README, seguridad, arquitectura y ADR-0026: documentación.

## 4. Decisiones de acceso

[ADR-0026](decisiones/0026-historial-compartido-y-registro-por-especialidad.md)
actualiza la lectura de roles y áreas. El ámbito mantiene clínica, pacientes
y especialidades autorizados. N3 no se concede automáticamente. La consulta
sin cita no se transforma en escritura por compartir una clínica.

## 5. Datos de prueba

Solo pacientes, cuentas y texto sintéticos. Las pruebas API usan transacciones
reversibles y conteos acotados a sus entidades. Los recorridos de navegador
usan la base de desarrollo sintética; los registros de documentos conservan
sus versiones. No se borran historiales ni se usan datos reales.

## 6. Pruebas de interfaz

```powershell
cd frontend
npx.cmd ng test --no-watch --coverage
npm.cmd run lint
npm.cmd run build
```

**777/777**, 104 archivos, 115,16 s. Cobertura: sentencias 85,09 %, ramas
71,95 %, funciones 80,87 % y líneas 87,60 %. Lint y compilación de producción
aprobados; paquete inicial 468,69 kB, sin aviso de presupuesto.

Registros: `tmp/qa-20261007/ficha-frontend-final.log`, `ficha-lint-final.log`
y `ficha-build-final.log`. Las primeras cinco incidencias eran fixtures sin
especialidad propia: se corrigieron los perfiles dentales/estéticos y los
proveedores de anamnesis. No se retiraron pruebas ni se rebajó cobertura.

## 7. Pruebas de API y dominio

Las suites ejecutadas cubren historia, odontología, periodontograma, documentos,
especialidades, aislamiento, la nueva consulta por roles, usuarios, plataforma,
imágenes, manuales, autorización y el servicio de historia.

Comando final, desde `backend`:

```powershell
.venv/Scripts/python.exe -m pytest pruebas/api/test_historia_api.py pruebas/api/test_odontologia_api.py pruebas/api/test_periodontograma_api.py pruebas/api/test_registros_paciente_api.py pruebas/api/test_especialidades_historia_api.py pruebas/api/test_aislamiento_especialistas_api.py pruebas/api/test_consulta_historia_roles_api.py pruebas/api/test_usuarios_api.py pruebas/api/test_plataforma_api.py pruebas/api/test_imagenes_api.py pruebas/api/test_ayuda_api.py pruebas/integracion/test_servicio_historia.py pruebas/unitarias/test_autorizacion.py pruebas/unitarias/test_ayuda_manuales.py -q
```

**257/257** en 363,62 s, sin cobertura global nueva. El bloque previo aprobó
210 pruebas y la comprobación específica de tomas/servicio aprobó 82. La
nueva política prueba ausencia de autenticación, seis roles, colecciones
vacías, contenido N2, exclusión N3, auditoría, especialidad ajena, clínica
ajena, pacientes fuera del ámbito, validación e idempotencia del inicio.
Después de ampliar las aserciones de resumen clínico y contenido compartido,
la corrida final de política/manuales aprobó **76/76** en 47,02 s.
Registros: `ficha-backend-final.log` y `ficha-politica-final.log`.

El último ajuste mantiene la especialidad propia en ámbitos parciales sin
abrir las otras áreas. Regresión final de política, usuarios, aislamiento y
manuales: **103/103** en 61,40 s (`ficha-ambitos-cierre.log`). Mypy repetido
tras ese ajuste: 255 archivos aprobados. La prueba comprueba lectura propia
y rechazo 403 de una especialidad ajena no asignada.

## 8. Navegador real

```powershell
cd pruebas-e2e
$env:URL_API = 'http://127.0.0.1:8020/api/v1'
npx.cmd playwright test escenarios/22-ficha-compartida-marca.spec.ts escenarios/15-pantallas-trabajo.spec.ts escenarios/17-registros-y-documentos.spec.ts escenarios/20-acceso-formularios.spec.ts --project=chromium --workers=1
```

API temporal con el mismo código y base sintética, sin recargador,
`LIMITE_LOGIN_POR_MINUTO=200`; el fixture dirige también el navegador a ella.
El límite de la aplicación de trabajo no se cambia. Sin reintentos.

Se verifica portada/axe, seis roles en un paciente nuevo, primera nota sin
cita y consulta posterior desde asistencia, todas las secciones del menú,
formularios, CRUD administrativo, presupuesto/cotización/receta/faciograma,
PDF reales y entrega documental sandbox: **17/17** en 5,4 min.
Registro `ficha-marca-regresion-e2e-final.log`.

Regresión adicional de autorización e historia/medicación: **16/16** en
1,6 min, incluyendo ventanas SOAP/recetas/033 con axe, versiones históricas,
PRN, alerta atendida por el responsable y cierre de plan. Registro
`ficha-roles-clinica-e2e-final.log`. Total: **33 recorridos aprobados** en
estas dos baterías, sin atribuir una ejecución nueva de toda la suite E2E.
El cierre de autorización con la comprobación del menú de Usuarios repitió
**5/5** en 13,7 s (`ficha-autorizacion-cierre.log`).

## 9. Tamaños, espacio y accesibilidad

Portada: 1440 × 900, 1280 × 600, 1024 × 768, 768 × 1024, 390 × 844 y
320 × 568. Logo cargado, nombre de al menos 32 px, seis accesos dentro de
pantalla y sin desborde horizontal. Axe WCAG A/AA sin infracciones en la portada.
El selector se comprueba también a 390 × 844; formularios con acciones fijas
y desplazamiento interior. Las secciones del menú se recorren en escritorio
y móvil mediante el escenario 15 existente.

## 10. Presentación y recursos

Logo SVG original con degradado celeste/menta, marca destacada y acento
`#086c7f`. Fotografía `acceso-equipo.png` conservada. Los colores semánticos,
el foco, movimiento reducido y contraste permanecen. El brillo máximo de la
acción principal se limita a 6 %; contraste calculado 5,36:1 contra blanco.

Capturas locales: `portada-clinicai-turquesa.png` y
`ficha-paciente-herramientas.png`, en la carpeta de registros ignorada por Git.

## 11. Seguridad revisada

Se detectó que registrar una toma aceptaba permiso de lectura. Ahora el
endpoint y el servicio exigen escritura y profesional responsable, con
clínica, paciente, sensibilidad y relación comprobados. Atender una alerta
clínica recibe el mismo límite. La interfaz oculta las mutaciones a personal
de consulta y no ofrece las tomas de otro responsable para edición.

Sin permisos nuevos para IA ni rutas clínicas de escritura en sus herramientas.
La consulta clínica mantiene auditoría. Se conserva el historial append-only.

## 12. Análisis estático y secretos

Ruff, formato y mypy del backend aprobados; mypy revisa 255 archivos. Bandit
se ejecutó con `-r app -ll -q`, aprobado sin hallazgos de nivel medio/alto. Gitleaks del
índice visual aprobado, con salida redactada. La comprobación del bloque
clínico se conserva en `ficha-clinica-gitleaks-indice.log` y su informe JSON.

## 13. Migración y reversión

`20261009_038`, detrás de `20261009_037`. Modifica permisos de los seis roles
base y retira carga clínica de imágenes a asistencia. Conserva cada asignación
anterior en `respaldo_consulta_roles_20261009`. No modifica registros clínicos.

Aplicación y reversión ejecutadas en la base sintética: `downgrade 20261009_037`
restaura exactamente las asignaciones previas; `upgrade head` restaura los
permisos nuevos y deja `038` activa. Se comparan rol y código del permiso,
porque eliminar y recrear la capacidad nueva puede generar otro UUID.

## 14. Configuración local y staging

Aplicación de trabajo: frontend 4200 y API 8000 sobre `main`. La API 8020 se
se usó únicamente para la batería de navegador y quedó detenida al terminar.
Frontend 4200 y `/salud/listo` de API 8000 responden 200 después del cierre.
Staging no se desplegó en esta revisión; aplicar `upgrade head`, asignar ámbitos
y renovar sesiones antes de revisar la nueva política en ese entorno.

## 15. Proveedores y credenciales

No se incorporaron credenciales ni se invocaron proveedores clínicos o modelos
externos. WhatsApp documental se verifica en sandbox; no acredita entregas
reales de Meta. Las validaciones pendientes constan en preparación para producción.

## 16. Despliegue, rollback y restauración

Compilar frontend y actualizar backend junto con la migración `038`.
Para rollback de este bloque: detener mutaciones, volver al código anterior,
`alembic downgrade 20261009_037` y renovar sesiones. La migración `037` de
WhatsApp permanece. Los registros clínicos y asignaciones asistenciales ya
auditados se conservan. No se realizó otra restauración de backups; su
procedimiento previo sigue en `docs/deployment.md`.

## 17. Limitaciones y pendientes

Roles personalizados sin la capacidad compartida conservan la política
anterior. N3/Formulario 033 requieren permiso sensible. No hay evaluaciones
clínicas automáticas al dar de alta. No se repitió CI remoto, DAST ni la batería
global de proveedores; la evidencia es local y acotada al bloque modificado.

Las primeras corridas de navegador alcanzaron el límite de login, coincidieron
con recargas de desarrollo y usaban lectura como prueba de vínculo de escritura.
La corrida final usa API temporal estable; el caso facial inicia su propia
atención explícita. La prueba de primera nota completa una sección SOAP válida.

## 18. Estado y coordinación

Trabajo en `main`, con el bloque visual confirmado como `6bb579b`. La política
clínica y su evidencia se confirman por separado al cerrar las pruebas. No se
modifican ramas ajenas ni archivos preexistentes fuera de esta tarea.
Los requisitos pendientes de producción no cambian por esta revisión local.
