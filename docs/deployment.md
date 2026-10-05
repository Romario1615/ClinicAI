# Despliegue

> Procedimientos local, staging, producción, rollback y restauración.
> **Estado:** el procedimiento local está automatizado y verificado. Staging y producción
> están documentados pero **no ejecutados**: no existe entorno de alojamiento definido
> (bloqueo B‑4 en [`production-readiness.md`](production-readiness.md)).

---

## 1. Entornos

| Entorno | `ENTORNO` | Datos | Proveedores externos |
|---|---|---|---|
| Local | `local` | Sintéticos | Sandbox y mocks |
| Desarrollo | `desarrollo` | Sintéticos | Sandbox |
| Preproducción | `preproduccion` | Sintéticos con volumen realista | Sandbox de WhatsApp, calendario de prueba |
| Producción | `produccion` | Reales | Reales |

### Comprobación de arranque

El backend **se niega a arrancar** si `ENTORNO=produccion` y detecta cualquiera de:

* `DEPURACION=true`
* `FRONTEND_MODO_SIMULADO=true`
* `WHATSAPP_VALIDAR_FIRMA=false`
* `MODO_WHATSAPP=sandbox` o `MODO_CALENDARIO=sandbox`
* `ORIGENES_CORS` con comodín
* Un secreto con valor de ejemplo o vacío
* `CLAVE_SECRETA` con menos de 32 caracteres

No es un aviso: el proceso termina con código de error. La alternativa —arrancar con una
advertencia en el log— produce clínicas que creen estar enviando recordatorios y no lo
están.

---

## 2. Despliegue local (Windows con WSL2)

### Por qué WSL2 y no Docker Desktop

En este equipo Docker Desktop no es instalable (disco C: sin espacio) y `pgvector` no se
puede compilar de forma nativa (sin MSVC). Razonamiento completo en
[ADR‑0002](decisiones/0002-infraestructura-local-wsl2-docker.md).

### Primera vez

```powershell
# 1. Cachés y artefactos fuera de C:  (ADR-0003)
.\infra\scripts\entorno-dev.ps1 -Persistente

# 2. Distribución WSL2 en D: con Docker Engine
#    Descarga la imagen de Ubuntu directamente a D: y la importa, para no
#    usar el directorio temporal de C:.
.\infra\wsl\aprovisionar.ps1

#    Comprobar el estado en cualquier momento:
.\infra\wsl\aprovisionar.ps1 -Verificar

# 3. Configuración
Copy-Item .env.example .env
#    Generar los secretos (no reutilizar valores de ejemplo):
python -c "import secrets; print(secrets.token_urlsafe(64))"                     # CLAVE_SECRETA
python -c "import secrets; print(secrets.token_urlsafe(24))"                     # POSTGRES_CONTRASENA
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # CLAVE_CIFRADO_DATOS

# 4. Anclar la distribucion WSL (IMPRESCINDIBLE, ver la nota siguiente)
.\infra\scripts\mantener-wsl.ps1 -SegundoPlano

# 5. Infraestructura de datos
.\infra\scripts\infra-arriba.ps1

# 6. Backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install uv
uv sync --frozen
uv run alembic upgrade head
uv run python -m app.semillas.cargar_sinteticos
uv run uvicorn app.main:crear_aplicacion --factory --reload
uv run arq app.tareas.worker.ConfiguracionWorker   # trabajos periodicos

# 7. Frontend (otra terminal)
cd frontend
npm ci
npm start
```


### Por que hay que anclar la distribucion WSL

WSL2 apaga la maquina virtual poco despues de que termine el ultimo proceso
conectado a ella. Con comandos cortos —un `docker ps`, un `pytest` de diez
segundos— la distribucion se apaga entre invocaciones y **se lleva los
contenedores con ella**.

El sintoma parece un problema de red y no lo es:

* una conexion a PostgreSQL funciona y, medio minuto despues, la misma
  conexion falla con `connection timeout expired` o con
  `connection was closed in the middle of operation`;
* el socket TCP conecta, porque el proxy de Docker acepta en cuanto el
  contenedor existe, pero PostgreSQL todavia se esta inicializando y no
  responde al protocolo;
* en el registro del contenedor se ve un apagado limpio seguido de un
  arranque, sin ningun error.

Durante el desarrollo esto provocaba que la suite de integracion pasara
27 de 27 en una ejecucion y fallara 7 pruebas en la siguiente, sin ningun
cambio de codigo.

`vmIdleTimeout=-1` en `.wslconfig` deberia evitarlo, pero en la version
probada (WSL 2.7.10) no basta. La solucion que si funciona es mantener un
proceso vivo dentro de la distribucion:

```powershell
.\infra\scripts\mantener-wsl.ps1 -SegundoPlano   # anclar
.\infra\scripts\mantener-wsl.ps1 -Estado         # comprobar
.\infra\scripts\mantener-wsl.ps1 -Detener        # soltar
```

Con el anclaje activo: 27 de 27 en tres ejecuciones consecutivas y cero
reinicios del contenedor.

### Antes de cualquier operacion sobre la base de datos

Comprobar que el puerto esta abierto **no sirve**: hay que comprobar que la
base de datos responde una consulta. Esa es la unica senal fiable de que esta
lista, y es lo que hace esta herramienta:

```powershell
cd backend
uv run python -m herramientas.esperar_bd        # espera y verifica extensiones
uv run alembic upgrade head
```

Tambien verifica que existan `vector`, `btree_gist`, `pg_trgm` y `pgcrypto`:
un PostgreSQL sano sin esas extensiones no sirve para este sistema.

### Uso diario

```powershell
.\infra\scripts\mantener-wsl.ps1 -SegundoPlano   # anclar la distribucion
.\infra\scripts\infra-arriba.ps1                 # levantar PostgreSQL y Redis
.\infra\scripts\infra-abajo.ps1                  # detener, conservando datos
.\infra\scripts\mantener-wsl.ps1 -Detener        # soltar el anclaje
wsl --shutdown                                     # liberar la memoria de WSL
```

### Imágenes clínicas: MinIO y antivirus (opcional)

MinIO y ClamAV están en el perfil `archivos` de `docker-compose.dev.yml` y no arrancan con
`infra-arriba.ps1`: ClamAV ocupa ~1 GB de RAM. Para probar el almacén S3 y el antivirus:

```bash
# dentro de WSL, en infra/compose
docker compose -f docker-compose.dev.yml --profile archivos up -d minio clamav
```

Y en `.env`: `ALMACENAMIENTO_ARCHIVOS=s3`, `S3_ENDPOINT=http://127.0.0.1:9000`,
`S3_CLAVE_ACCESO` / `S3_CLAVE_SECRETA` (mínimo 3 y 8 caracteres, inventados para desarrollo,
nunca los de producción) y `ANTIVIRUS_HABILITADO=true`. El bucket se crea al primer uso. Las
imágenes llegan cifradas por la aplicación: el bucket nunca ve una imagen en claro.

En producción el antivirus es obligatorio: la configuración no arranca sin él.

### Infraestructura de pruebas

Puertos distintos (5433 y 6380) y sin persistencia, para que la suite de integración no
dependa de la base de desarrollo ni la contamine:

```powershell
.\infra\scripts\infra-arriba.ps1 -Pruebas
cd backend; uv run pytest -m "integracion or api" -q
.\infra\scripts\infra-abajo.ps1 -Pruebas
```

### Empezar de cero

```powershell
# Borra los volúmenes. Pide confirmación escribiendo BORRAR.
.\infra\scripts\infra-abajo.ps1 -BorrarDatos
.\infra\scripts\infra-arriba.ps1
cd backend; uv run alembic upgrade head; uv run python -m app.semillas.cargar_sinteticos
```

### Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `docker: command not found` | Docker no instalado en la distribución | `.\infra\wsl\aprovisionar.ps1` |
| El demonio no responde | systemd no arrancó | `wsl --shutdown` y volver a levantar |
| `POSTGRES_CONTRASENA debe definirse` | Falta en `.env` | Generarla y añadirla |
| Falta la extensión `vector` | El volumen se creó antes del script de inicialización | `infra-abajo.ps1 -BorrarDatos` y volver a levantar |
| El equipo se ralentiza | WSL retiene memoria | Revisar `%USERPROFILE%\.wslconfig`; `wsl --shutdown` |
| La conexion a la base falla de forma intermitente | WSL se apaga entre comandos y reinicia los contenedores | `.\infra\scripts\mantener-wsl.ps1 -SegundoPlano` |
| `connection timeout expired` justo tras levantar | PostgreSQL aun se inicializa; el proxy ya acepta el TCP | `uv run python -m herramientas.esperar_bd` |
| La conexion se cuelga sin fallar | `localhost` resuelve a `::1` y WSL no relaya IPv6 | Usar `127.0.0.1` en `POSTGRES_HOST` |
| La descarga de la imagen falla | Sin espacio o sin red | La imagen va a `D:\wsl\imagenes`; comprobar espacio en D: |

---

## 3. Staging y producción

> **No ejecutado.** Procedimiento propuesto, pendiente de que exista entorno.

### Requisitos previos

| Requisito | Estado |
|---|---|
| Servidor con Docker y Compose, o Kubernetes | **pendiente** |
| Dominio y certificado TLS válido | **pendiente** — Meta exige HTTPS público para el webhook |
| Gestor de secretos | **pendiente** |
| PostgreSQL 16 con `pgvector` gestionado o en contenedor con volumen persistente | **pendiente** |
| Redis con persistencia | **pendiente** |
| Almacenamiento de objetos para documentos | **pendiente** |
| Respaldos automáticos con cifrado | **pendiente** |
| Credenciales de WhatsApp y Google | **pendiente** (bloqueos B‑2 y B‑3) |
| **Revisión jurídica** | **pendiente** (bloqueo B‑1) |

### Secuencia de despliegue

```bash
# 1. Etiquetar la versión
git tag -a v0.x.0 -m "descripcion" && git push origin v0.x.0

# 2. El pipeline construye y publica las imágenes con la etiqueta del commit
#    Nunca se despliega `latest`: impide saber qué está corriendo y hace
#    imposible un rollback determinista.

# 3. Respaldo previo OBLIGATORIO
./infra/scripts/respaldar.sh --entorno produccion --etiqueta "pre-v0.x.0"

# 4. Migraciones. Se aplican ANTES de cambiar la imagen de la aplicación, y
#    deben ser compatibles con la versión anterior (ver más abajo).
docker compose -f infra/compose/docker-compose.prod.yml run --rm backend \
    alembic upgrade head

# 5. Despliegue con solapamiento, sin cortar el servicio
docker compose -f infra/compose/docker-compose.prod.yml up -d --no-deps backend worker
docker compose -f infra/compose/docker-compose.prod.yml up -d --no-deps frontend

# 6. Smoke test
./infra/scripts/smoke-test.sh https://<dominio>

# 7. Vigilar durante 15 minutos: tasa de error, latencia P95, cola del outbox
```

### Regla de migraciones compatibles

Toda migración debe funcionar con la versión **anterior** de la aplicación en ejecución,
porque durante el despliegue coexisten ambas. En la práctica:

* Añadir columna: siempre con valor por defecto o admitiendo nulos.
* Eliminar columna: dos despliegues. Primero se deja de usar en el código; en el
  siguiente se elimina.
* Renombrar: nunca directamente. Añadir la nueva, escribir en ambas, migrar datos,
  dejar de usar la vieja, eliminarla.
* Restricción nueva: primero `NOT VALID`, corregir los datos, después validar.

Esta regla es lo que hace posible el rollback del paso siguiente.

---

## 4. Rollback

> **No probado.** Debe ejecutarse en preproducción antes de considerarlo válido
> (tarea 10.8 del backlog).

### Rollback de aplicación (primera opción, minutos)

```bash
# Volver a la etiqueta anterior de la imagen
export VERSION_ANTERIOR=v0.(x-1).0
docker compose -f infra/compose/docker-compose.prod.yml up -d --no-deps backend worker frontend
./infra/scripts/smoke-test.sh https://<dominio>
```

Funciona sin tocar la base de datos **si** la migración cumplió la regla de
compatibilidad. Es el camino preferido: rápido y sin riesgo de pérdida de datos.

### Rollback de migración (segunda opción)

```bash
# Solo si la migración es incompatible y NO hay pérdida de datos al revertir
docker compose ... run --rm backend alembic downgrade -1
```

**Antes de ejecutarlo**, comprobar si la reversión destruye datos. Una migración que
eliminó una columna no puede devolver su contenido. En ese caso el camino es la
restauración desde respaldo, no el `downgrade`.

### Restauración completa (último recurso)

Implica pérdida de los datos posteriores al respaldo. Procedimiento en
[`backup-and-restore.md`](backup-and-restore.md).

### Criterios para decidir el rollback

Se revierte si en los 15 minutos posteriores al despliegue se observa:

* Tasa de error superior al 2 % en las rutas de autenticación o de agenda.
* Latencia P95 de creación de cita por encima de 3 s.
* Cualquier error de integridad de datos.
* La cola del outbox creciendo sin drenar.
* Fallo del smoke test.

---

## 5. Variables de entorno

El catálogo completo, con su propósito y cómo generar cada secreto, está en
[`.env.example`](../.env.example). Resumen de lo obligatorio por entorno:

| Variable | Local | Producción |
|---|---|---|
| `ENTORNO` | `local` | `produccion` |
| `DEPURACION` | `true` | **`false`** |
| `CLAVE_SECRETA` | generada | **del gestor de secretos** |
| `CLAVE_CIFRADO_DATOS` | generada | **del gestor de secretos** |
| `POSTGRES_*` | contenedor local | instancia gestionada |
| `REDIS_*` | contenedor local | instancia gestionada |
| `MODO_WHATSAPP` | `sandbox` | **`cloud_api`** |
| `MODO_CALENDARIO` | `sandbox` | **`google`** |
| `MODO_CORREO` | `consola` | **`smtp`** |
| `PROVEEDOR_LLM` | `mock` | `anthropic` |
| `ORIGENES_CORS` | `http://localhost:4200` | dominio explícito, sin comodín |
| `ANTIVIRUS_HABILITADO` | `false` | **`true`** |

En producción, **ningún secreto se pasa por archivo `.env`**: se inyecta desde el gestor
de secretos del entorno.

---

## 6. Rotación de secretos

| Secreto | Frecuencia | Procedimiento |
|---|---|---|
| `CLAVE_SECRETA` | 90 días o ante sospecha | Rotar invalida todas las sesiones. Avisar antes; no hacerlo en horario de consulta |
| `CLAVE_CIFRADO_DATOS` | 180 días | **Requiere recifrar los tokens OAuth almacenados.** Existe un procedimiento de doble clave: descifrar con la vieja, cifrar con la nueva, por lotes |
| `POSTGRES_CONTRASENA` | 90 días | Cambiar en la base, después en el gestor de secretos, después reiniciar la aplicación |
| `WHATSAPP_TOKEN_ACCESO` | Según Meta | Generar token de larga duración; el token temporal caduca en 24 h |
| `GOOGLE_CLIENT_SECRET` | Ante sospecha | Rotar en Google Cloud; **obliga a reconectar todos los calendarios** |

---

## 7. Lista de verificación previa a producción

Ninguna casilla está marcada todavía. El estado real está en
[`production-readiness.md`](production-readiness.md).

- [ ] Pipeline de CI completo en verde
- [ ] Cobertura por encima del umbral
- [ ] Sin vulnerabilidades críticas o altas sin plan
- [ ] `gitleaks` limpio sobre todo el historial
- [ ] Migraciones aplicables y reversibles
- [ ] Respaldo **restaurado** en una instancia limpia
- [ ] Rollback ejecutado en preproducción
- [ ] Pruebas de carga con los objetivos de RNF‑01…RNF‑04 cumplidos
- [ ] Pruebas de recuperación ante caída de cada dependencia
- [ ] Los 21 escenarios de aceptación en verde
- [ ] **Verificación contra WhatsApp y Google reales en preproducción**
- [ ] Monitoreo y alertas activos
- [ ] **Revisión jurídica completada**
- [ ] Decisiones de la clínica sobre retención y consentimientos registradas
