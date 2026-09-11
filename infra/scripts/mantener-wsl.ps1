# ---------------------------------------------------------------------------
#  Mantiene viva la distribucion WSL mientras se trabaja.
#
#  El problema
#  -----------
#  WSL2 apaga la maquina virtual poco despues de que termine el ultimo proceso
#  conectado a ella.  Con herramientas que invocan comandos cortos
#  (`wsl -d clinica -- docker ps`, un `pytest` de diez segundos) la
#  distribucion se apaga entre invocaciones y se lleva los contenedores con
#  ella.
#
#  El sintoma es desconcertante y parece un problema de red: PostgreSQL
#  responde, y a los treinta segundos la misma conexion falla con
#  "connection was closed in the middle of operation" o con un tiempo limite
#  agotado.  En el registro del contenedor se ve un apagado limpio seguido de
#  un arranque, sin ningun error.
#
#  `vmIdleTimeout=-1` en .wslconfig deberia evitarlo, pero en la version
#  probada (WSL 2.7.10) no basta.
#
#  La solucion
#  -----------
#  Mantener un proceso vivo dentro de la distribucion.  Mientras exista, WSL
#  no apaga la maquina virtual.
#
#  Uso:
#    # En una terminal aparte, y dejarla abierta mientras se trabaja:
#    .\infra\scripts\mantener-wsl.ps1
#
#    # O en segundo plano, sin ocupar una terminal:
#    .\infra\scripts\mantener-wsl.ps1 -SegundoPlano
#
#    # Comprobar si ya hay un anclaje activo:
#    .\infra\scripts\mantener-wsl.ps1 -Estado
#
#    # Detener el anclaje:
#    .\infra\scripts\mantener-wsl.ps1 -Detener
# ---------------------------------------------------------------------------

[CmdletBinding()]
param(
    [string]$NombreDistribucion = 'clinica',
    [switch]$SegundoPlano,
    [switch]$Estado,
    [switch]$Detener
)

$ErrorActionPreference = 'Stop'
$MarcaProceso = 'clinica-anclaje-wsl'

function Escribir-Info  { param($m) Write-Host "    $m" -ForegroundColor DarkGray }
function Escribir-Ok    { param($m) Write-Host "    $m" -ForegroundColor Green }
function Escribir-Aviso { param($m) Write-Host "    $m" -ForegroundColor Yellow }

function Obtener-Anclaje {
    # Se busca por la marca en la linea de comandos del proceso.
    Get-CimInstance Win32_Process -Filter "Name = 'wsl.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -like "*$MarcaProceso*" }
}

# ---------------------------------------------------------------------------
if ($Estado) {
    $anclaje = Obtener-Anclaje
    if ($anclaje) {
        Escribir-Ok "Anclaje activo (PID $($anclaje.ProcessId))."
    } else {
        Escribir-Aviso 'Sin anclaje activo. La distribucion puede apagarse sola.'
    }

    $enMarcha = (& wsl.exe --list --running --quiet 2>&1) |
        ForEach-Object { ($_ -replace "`0", '').Trim() }
    if ($enMarcha -contains $NombreDistribucion) {
        Escribir-Ok "La distribucion '$NombreDistribucion' esta en marcha."
    } else {
        Escribir-Aviso "La distribucion '$NombreDistribucion' NO esta en marcha."
    }
    exit 0
}

if ($Detener) {
    $anclaje = Obtener-Anclaje
    if (-not $anclaje) {
        Escribir-Aviso 'No hay anclaje que detener.'
        exit 0
    }
    foreach ($proceso in $anclaje) {
        Stop-Process -Id $proceso.ProcessId -Force -ErrorAction SilentlyContinue
        Escribir-Ok "Anclaje detenido (PID $($proceso.ProcessId))."
    }
    Escribir-Info 'La distribucion se apagara sola cuando WSL lo decida.'
    exit 0
}

# ---------------------------------------------------------------------------
$distros = (& wsl.exe --list --quiet 2>&1) |
    ForEach-Object { ($_ -replace "`0", '').Trim() }
if ($distros -notcontains $NombreDistribucion) {
    Write-Host "La distribucion '$NombreDistribucion' no existe." -ForegroundColor Red
    Escribir-Info 'Ejecute primero:  .\infra\wsl\aprovisionar.ps1'
    exit 1
}

if (Obtener-Anclaje) {
    Escribir-Ok 'Ya hay un anclaje activo; no se crea otro.'
    exit 0
}

# El comando incluye la marca para poder localizarlo despues.  `sleep
# infinity` no consume CPU: solo existe para que WSL cuente un proceso vivo.
$orden = "# $MarcaProceso`nexec sleep infinity"

if ($SegundoPlano) {
    Write-Host "Anclando la distribucion '$NombreDistribucion' en segundo plano..." -ForegroundColor Cyan
    $proceso = Start-Process -FilePath 'wsl.exe' `
        -ArgumentList @('-d', $NombreDistribucion, '--', 'bash', '-lc', $orden) `
        -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 2
    if ($proceso.HasExited) {
        Write-Host 'El anclaje termino de inmediato; revise la distribucion.' -ForegroundColor Red
        exit 1
    }
    Escribir-Ok "Anclaje activo (PID $($proceso.Id))."
    Escribir-Info 'Para detenerlo:  .\infra\scripts\mantener-wsl.ps1 -Detener'
} else {
    Write-Host "Anclando la distribucion '$NombreDistribucion'." -ForegroundColor Cyan
    Escribir-Info 'Deje esta terminal abierta mientras trabaja.'
    Escribir-Info 'Ctrl+C para soltar el anclaje.'
    & wsl.exe -d $NombreDistribucion -- bash -lc $orden
}
