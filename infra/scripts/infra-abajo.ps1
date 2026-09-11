# ---------------------------------------------------------------------------
#  Detiene la infraestructura de datos.
#
#  Por defecto CONSERVA los datos: solo para los contenedores.  Borrar los
#  volumenes exige el modificador -BorrarDatos y una confirmacion explicita,
#  porque en desarrollo tambien hay trabajo que se pierde.
#
#  Uso:
#    .\infra\scripts\infra-abajo.ps1                  # detiene, conserva datos
#    .\infra\scripts\infra-abajo.ps1 -Pruebas         # entorno de pruebas
#    .\infra\scripts\infra-abajo.ps1 -BorrarDatos     # borra los volumenes
# ---------------------------------------------------------------------------

[CmdletBinding()]
param(
    [string]$NombreDistribucion = 'clinica',
    [switch]$Pruebas,
    [switch]$BorrarDatos,
    # Omite la confirmacion.  Solo para scripts de CI.
    [switch]$SinConfirmar
)

$ErrorActionPreference = 'Stop'
$raizProyecto = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

function Escribir-Paso  { param($m) Write-Host "`n==> $m" -ForegroundColor Cyan }
function Escribir-Ok    { param($m) Write-Host "    $m" -ForegroundColor Green }
function Escribir-Aviso { param($m) Write-Host "    $m" -ForegroundColor Yellow }
function Escribir-Info  { param($m) Write-Host "    $m" -ForegroundColor DarkGray }

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

$entorno  = if ($Pruebas) { 'pruebas' } else { 'desarrollo' }
$archivo  = if ($Pruebas) { 'docker-compose.test.yml' } else { 'docker-compose.dev.yml' }
$proyecto = if ($Pruebas) { 'clinica-test' } else { 'clinica-dev' }

$distros = (& wsl.exe --list --quiet 2>&1) | ForEach-Object { ($_ -replace "`0", '').Trim() }
if ($distros -notcontains $NombreDistribucion) {
    Escribir-Aviso "La distribucion '$NombreDistribucion' no existe; nada que detener."
    exit 0
}

$rutaCompose = Convertir-RutaLinux (Join-Path $raizProyecto "infra\compose\$archivo")
$argsCompose = "-f '$rutaCompose' -p $proyecto"

# El compose de desarrollo declara POSTGRES_CONTRASENA como variable
# obligatoria, asi que tambien hay que pasar el archivo de entorno para
# detener: sin el, la interpolacion falla antes de llegar a `down`.
if (-not $Pruebas) {
    $rutaEnv = Join-Path $raizProyecto '.env'
    if (Test-Path -LiteralPath $rutaEnv) {
        $rutaEnvWsl = Convertir-RutaLinux $raizProyecto
        $argsCompose = "--env-file '$rutaEnvWsl/.env' $argsCompose"
    } else {
        # Sin .env no se puede interpolar.  Se usa un valor de relleno: para
        # `down` la contrasena es irrelevante, solo hace falta que la
        # interpolacion no aborte.
        Escribir-Aviso 'No hay .env; se usa un valor de relleno solo para interpolar.'
        $argsCompose = "-f '$rutaCompose' -p $proyecto"
        $env:POSTGRES_CONTRASENA = 'relleno-para-detener'
    }
}

# ---------------------------------------------------------------------------
#  Confirmacion antes de destruir datos
# ---------------------------------------------------------------------------
if ($BorrarDatos -and -not $SinConfirmar) {
    Write-Host ''
    Write-Host "Se van a BORRAR los volumenes del entorno de $entorno." -ForegroundColor Red
    if (-not $Pruebas) {
        Write-Host 'Esto elimina la base de datos de desarrollo completa:' -ForegroundColor Red
        Write-Host '  pacientes sinteticos, citas, documentos y embeddings.' -ForegroundColor Red
        Write-Host 'Habra que volver a aplicar migraciones y cargar semillas.' -ForegroundColor DarkYellow
    }
    Write-Host ''
    $respuesta = Read-Host "Escriba BORRAR para confirmar"
    if ($respuesta -ne 'BORRAR') {
        Write-Host 'Cancelado. No se ha borrado nada.' -ForegroundColor Green
        exit 0
    }
}

# ---------------------------------------------------------------------------
#  Detener
# ---------------------------------------------------------------------------
Escribir-Paso "Deteniendo la infraestructura de $entorno"

$estadoDemonio = (& wsl.exe -d $NombreDistribucion -- bash -lc 'docker info >/dev/null 2>&1 && echo ACTIVO || echo INACTIVO' 2>&1) -join ''
if ($estadoDemonio -notmatch 'ACTIVO') {
    Escribir-Aviso 'El demonio de Docker no esta activo; nada que detener.'
    exit 0
}

if ($BorrarDatos) {
    Escribir-Info 'docker compose down --volumes'
    $codigoSalida = Invocar-Nativo @('-d', $NombreDistribucion, '--', 'bash', '-lc', "docker compose $argsCompose down --volumes --remove-orphans")
} else {
    Escribir-Info 'docker compose down  (los volumenes se conservan)'
    $codigoSalida = Invocar-Nativo @('-d', $NombreDistribucion, '--', 'bash', '-lc', "docker compose $argsCompose down --remove-orphans")
}

if ($codigoSalida -ne 0) {
    Escribir-Aviso "docker compose devolvio el codigo $codigoSalida"
} else {
    Escribir-Ok 'Detenida'
}

if ($BorrarDatos) {
    Escribir-Info 'Volumenes eliminados. El proximo arranque inicializara la base de cero.'
} else {
    Escribir-Info 'Los datos se conservan en los volumenes de Docker.'
}

Write-Host ''
Write-Host 'Para liberar tambien la memoria que retiene WSL:' -ForegroundColor Cyan
Write-Host '  wsl --shutdown'
