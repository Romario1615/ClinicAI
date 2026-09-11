# ---------------------------------------------------------------------------
#  Levanta la infraestructura de datos (PostgreSQL + pgvector y Redis).
#
#  Ejecuta docker compose DENTRO de la distribucion WSL y traduce las rutas
#  de Windows a rutas de Linux, para que se pueda trabajar desde PowerShell
#  sin entrar a WSL a mano.
#
#  Uso:
#    .\infra\scripts\infra-arriba.ps1              # entorno de desarrollo
#    .\infra\scripts\infra-arriba.ps1 -Pruebas     # entorno de pruebas
#    .\infra\scripts\infra-arriba.ps1 -Recrear     # recrea los contenedores
# ---------------------------------------------------------------------------

[CmdletBinding()]
param(
    [string]$NombreDistribucion = 'clinica',
    [switch]$Pruebas,
    [switch]$Recrear,
    # Segundos maximos de espera a que los servicios queden saludables
    [int]$TiempoEsperaSegundos = 180
)

$ErrorActionPreference = 'Stop'
$raizProyecto = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

function Escribir-Paso  { param($m) Write-Host "`n==> $m" -ForegroundColor Cyan }
function Escribir-Ok    { param($m) Write-Host "    $m" -ForegroundColor Green }
function Escribir-Aviso { param($m) Write-Host "    $m" -ForegroundColor Yellow }
function Escribir-Fallo { param($m) Write-Host "    $m" -ForegroundColor Red }
function Escribir-Info  { param($m) Write-Host "    $m" -ForegroundColor DarkGray }

# Traduce D:\Sistema IA de Clinicas  ->  /mnt/d/Sistema IA de Clinicas
function Convertir-RutaLinux {
    param([string]$RutaWindows)
    $completa = (Resolve-Path -LiteralPath $RutaWindows).Path
    $unidad   = $completa.Substring(0, 1).ToLower()
    $resto    = $completa.Substring(2) -replace '\\', '/'
    return "/mnt/$unidad$resto"
}

# ---------------------------------------------------------------------------
#  Ejecucion de comandos nativos
# ---------------------------------------------------------------------------
# En Windows PowerShell 5.1, con $ErrorActionPreference = 'Stop', toda linea
# que un ejecutable nativo escriba en stderr se convierte en un
# NativeCommandError que aborta el script.  Docker escribe su progreso normal
# en stderr, de modo que un comando correcto parecia fallar.
#
# Esta funcion baja la preferencia solo durante la llamada nativa y devuelve
# el codigo de salida real, que es la senal fiable.
function Invocar-Nativo {
    param([string[]]$Argumentos)
    $anterior = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & wsl.exe @Argumentos
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $anterior
    }
}

function Invocar-EnWsl {
    param([string]$Orden, [switch]$SinSalida)
    if ($SinSalida) {
        & wsl.exe -d $NombreDistribucion -- bash -lc $Orden 2>&1 | Out-Null
        return $LASTEXITCODE
    }
    $salida = & wsl.exe -d $NombreDistribucion -- bash -lc $Orden 2>&1
    return ($salida | ForEach-Object { $_ -replace "`0", '' })
}

$entorno  = if ($Pruebas) { 'pruebas' } else { 'desarrollo' }
$archivo  = if ($Pruebas) { 'docker-compose.test.yml' } else { 'docker-compose.dev.yml' }
$proyecto = if ($Pruebas) { 'clinica-test' } else { 'clinica-dev' }

Write-Host "Infraestructura de $entorno" -ForegroundColor White

# ---------------------------------------------------------------------------
#  1. Comprobaciones previas
# ---------------------------------------------------------------------------
Escribir-Paso 'Comprobaciones previas'

$distros = (& wsl.exe --list --quiet 2>&1) | ForEach-Object { ($_ -replace "`0", '').Trim() }
if ($distros -notcontains $NombreDistribucion) {
    Escribir-Fallo "La distribucion '$NombreDistribucion' no existe."
    Escribir-Info  'Ejecute primero:  .\infra\wsl\aprovisionar.ps1'
    exit 1
}
Escribir-Ok "Distribucion '$NombreDistribucion' disponible"

$estadoDemonio = (Invocar-EnWsl 'docker info >/dev/null 2>&1 && echo ACTIVO || echo INACTIVO') -join ''
if ($estadoDemonio -notmatch 'ACTIVO') {
    Escribir-Aviso 'El demonio de Docker no responde; intentando arrancarlo...'
    & wsl.exe -d $NombreDistribucion -u root -- bash -lc 'systemctl start docker 2>/dev/null || service docker start 2>/dev/null' | Out-Null
    Start-Sleep -Seconds 5
    $estadoDemonio = (Invocar-EnWsl 'docker info >/dev/null 2>&1 && echo ACTIVO || echo INACTIVO') -join ''
    if ($estadoDemonio -notmatch 'ACTIVO') {
        Escribir-Fallo 'No se pudo arrancar el demonio de Docker.'
        Escribir-Info  'Pruebe:  wsl --shutdown   y vuelva a ejecutar este script.'
        exit 1
    }
}
Escribir-Ok 'Demonio de Docker activo'

# El compose de desarrollo exige POSTGRES_CONTRASENA: es deliberado que falle
# de forma clara en lugar de arrancar con una credencial por defecto.
$rutaEnv = Join-Path $raizProyecto '.env'
if (-not $Pruebas) {
    if (-not (Test-Path -LiteralPath $rutaEnv)) {
        Escribir-Fallo 'No existe el archivo .env'
        Escribir-Info  'Ejecute:  Copy-Item .env.example .env   y complete los valores.'
        Escribir-Info  'Genere la contrasena con:'
        Escribir-Info  '  python -c "import secrets; print(secrets.token_urlsafe(24))"'
        exit 1
    }
    $contenidoEnv = Get-Content -LiteralPath $rutaEnv -Raw
    if ($contenidoEnv -match '(?m)^POSTGRES_CONTRASENA=\s*$' -or
        $contenidoEnv -match '(?m)^POSTGRES_CONTRASENA=<') {
        Escribir-Fallo 'POSTGRES_CONTRASENA no esta definida en .env'
        Escribir-Info  'Genere una con:  python -c "import secrets; print(secrets.token_urlsafe(24))"'
        exit 1
    }
    Escribir-Ok 'Archivo .env presente con contrasena definida'
}

# ---------------------------------------------------------------------------
#  2. Levantar los servicios
# ---------------------------------------------------------------------------
Escribir-Paso 'Levantando servicios'

$rutaCompose = Convertir-RutaLinux (Join-Path $raizProyecto "infra\compose\$archivo")
$rutaEnvWsl  = Convertir-RutaLinux $raizProyecto

$argsCompose = "-f '$rutaCompose' -p $proyecto"
if (-not $Pruebas) {
    $argsCompose = "--env-file '$rutaEnvWsl/.env' $argsCompose"
}

$argsArriba = 'up -d --wait'
if ($Recrear) { $argsArriba = 'up -d --wait --force-recreate' }

Escribir-Info "docker compose $argsCompose $argsArriba"

# --wait hace que compose espere a que los healthcheck pasen.  El healthcheck
# de PostgreSQL no se limita a que el puerto responda: verifica que la
# extension pgvector exista (ver docker-compose.dev.yml).
$codigoSalida = Invocar-Nativo @('-d', $NombreDistribucion, '--', 'bash', '-lc', "docker compose $argsCompose $argsArriba --timeout $TiempoEsperaSegundos")

if ($codigoSalida -ne 0) {
    Escribir-Fallo "docker compose fallo con codigo $codigoSalida"
    Escribir-Info  'Registros de los ultimos intentos:'
    Invocar-Nativo @('-d', $NombreDistribucion, '--', 'bash', '-lc', "docker compose $argsCompose logs --tail 40") | Out-Null
    exit 1
}
Escribir-Ok 'Servicios levantados y saludables'

# ---------------------------------------------------------------------------
#  3. Verificacion de extensiones
# ---------------------------------------------------------------------------
Escribir-Paso 'Verificando extensiones de PostgreSQL'

$contenedorPg = if ($Pruebas) { 'clinica-pg-test' } else { 'clinica-pg' }
$usuarioPg    = if ($Pruebas) { 'clinica_pruebas' } else { 'clinica' }
$bdPg         = if ($Pruebas) { 'clinica_pruebas' } else { 'clinica' }

if (-not $Pruebas) {
    # Se leen del .env por si el usuario cambio los valores por defecto
    $lineas = Get-Content -LiteralPath $rutaEnv
    foreach ($linea in $lineas) {
        if ($linea -match '^POSTGRES_USUARIO=(.+)$') { $usuarioPg = $Matches[1].Trim() }
        if ($linea -match '^POSTGRES_BD=(.+)$')      { $bdPg      = $Matches[1].Trim() }
    }
}

# La consulta viaja codificada en base64.
#
# Motivo: una sentencia SQL pasa por tres niveles de interpretacion de
# comillas (PowerShell -> wsl.exe -> bash) y cualquier comilla simple del SQL
# rompe alguno de ellos.  El intento directo producia un comando vacio y el
# error "command not found".  Codificar elimina el problema de raiz.
$consulta = "SELECT extname, extversion FROM pg_extension ORDER BY extname;"
$consultaB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($consulta))
$orden = (
    "echo $consultaB64 | base64 -d | " +
    "docker exec -i $contenedorPg psql -U $usuarioPg -d $bdPg -tAF' '"
)
$extensiones = Invocar-EnWsl $orden

$requeridas = @('vector', 'btree_gist', 'pg_trgm', 'pgcrypto', 'unaccent')
$presentes = @{}
foreach ($linea in $extensiones) {
    $partes = $linea.Trim() -split '\s+'
    if ($partes.Count -ge 2) { $presentes[$partes[0]] = $partes[1] }
}

$faltantes = @()
foreach ($req in $requeridas) {
    if ($presentes.ContainsKey($req)) {
        Escribir-Ok ("{0,-12} {1}" -f $req, $presentes[$req])
    } else {
        Escribir-Fallo "$req : AUSENTE"
        $faltantes += $req
    }
}

if ($faltantes.Count -gt 0) {
    Escribir-Fallo "Faltan extensiones: $($faltantes -join ', ')"
    Escribir-Info  'El volumen puede haberse creado antes de anadir el script de inicializacion.'
    Escribir-Info  'Para recrear desde cero (BORRA los datos de desarrollo):'
    Escribir-Info  "  .\infra\scripts\infra-abajo.ps1 -BorrarDatos"
    exit 1
}

# ---------------------------------------------------------------------------
#  4. Resumen
# ---------------------------------------------------------------------------
Escribir-Paso 'Resumen'

$puertoPg    = if ($Pruebas) { 5433 } else { 5432 }
$puertoRedis = if ($Pruebas) { 6380 } else { 6379 }

$estado = Invocar-EnWsl "docker compose $argsCompose ps --format table"
$estado | Where-Object { $_.Trim() -ne '' } | ForEach-Object { Escribir-Info $_ }

Write-Host ''
Write-Host "PostgreSQL  localhost:$puertoPg    base '$bdPg'  usuario '$usuarioPg'" -ForegroundColor Green
Write-Host "Redis       localhost:$puertoRedis" -ForegroundColor Green
Write-Host ''
Write-Host 'Consola de PostgreSQL:' -ForegroundColor Cyan
Write-Host "  wsl -d $NombreDistribucion -- docker exec -it $contenedorPg psql -U $usuarioPg -d $bdPg"
