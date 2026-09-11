# ---------------------------------------------------------------------------
#  Variables de entorno de desarrollo.
#
#  Dirige TODA cache y artefacto al disco D:.  El disco C: de este equipo
#  tiene muy poco espacio libre (riesgo R-01, ADR-0003) y las herramientas de
#  la pila escriben ahi por defecto.
#
#  Uso:   . .\infra\scripts\entorno-dev.ps1
#         (con el punto inicial, para que las variables persistan en la sesion)
# ---------------------------------------------------------------------------

[CmdletBinding()]
param(
    # Fija las variables en el perfil del usuario para que persistan entre
    # sesiones.  Sin este modificador, solo afectan a la sesion actual.
    [switch]$Persistente
)

$ErrorActionPreference = 'Stop'

$rutas = [ordered]@{
    PIP_CACHE_DIR            = 'D:\cache\pip'
    UV_CACHE_DIR             = 'D:\cache\uv'
    PLAYWRIGHT_BROWSERS_PATH = 'D:\playwright-browsers'
    RUTA_CACHE_EMBEDDINGS    = 'D:\cache\fastembed'
    # fastembed y huggingface tienen sus propias variables; se fijan las tres
    # porque cual se respeta depende de la version de la libreria.
    HF_HOME                  = 'D:\cache\huggingface'
    FASTEMBED_CACHE_PATH     = 'D:\cache\fastembed'
    # npm ya estaba en D: en este equipo; se reafirma por si se reinstala.
    NPM_CONFIG_CACHE         = 'D:\npm-cache'
}

Write-Host "Configurando cache de desarrollo fuera de C:" -ForegroundColor Cyan

foreach ($clave in $rutas.Keys) {
    $valor = $rutas[$clave]

    if (-not (Test-Path -LiteralPath $valor)) {
        New-Item -ItemType Directory -Force -Path $valor | Out-Null
        Write-Host "  creado   $valor"
    }

    Set-Item -Path "Env:$clave" -Value $valor

    if ($Persistente) {
        [Environment]::SetEnvironmentVariable($clave, $valor, 'User')
    }

    Write-Host ("  {0,-26} = {1}" -f $clave, $valor) -ForegroundColor DarkGray
}

# --- Comprobacion de espacio en disco -------------------------------------
# Se avisa de forma visible porque quedarse sin espacio en C: rompe Windows,
# no solo este proyecto.
$c = Get-PSDrive -Name C -ErrorAction SilentlyContinue
$d = Get-PSDrive -Name D -ErrorAction SilentlyContinue

if ($c) {
    $libreC = [math]::Round($c.Free / 1GB, 2)
    Write-Host ""
    if ($libreC -lt 2) {
        Write-Host "ADVERTENCIA: disco C: con solo $libreC GB libres." -ForegroundColor Red
        Write-Host "  Windows puede fallar por falta de espacio. Libere espacio en C:." -ForegroundColor Red
        Write-Host "  Este proyecto ya escribe todo en D:, pero el sistema operativo no." -ForegroundColor DarkYellow
    } else {
        Write-Host "Disco C: $libreC GB libres." -ForegroundColor Green
    }
}

if ($d) {
    $libreD = [math]::Round($d.Free / 1GB, 2)
    if ($libreD -lt 10) {
        Write-Host "ADVERTENCIA: disco D: con solo $libreD GB libres." -ForegroundColor Red
        Write-Host "  La infraestructura de contenedores necesita margen." -ForegroundColor DarkYellow
    } else {
        Write-Host "Disco D: $libreD GB libres." -ForegroundColor Green
    }
}

if ($Persistente) {
    Write-Host ""
    Write-Host "Variables guardadas en el perfil del usuario." -ForegroundColor Green
    Write-Host "Abra una terminal nueva para que otras aplicaciones las vean." -ForegroundColor DarkGray
}
