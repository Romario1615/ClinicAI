# Arranque repetible de la demostracion: conserva .env y procesos existentes.
[CmdletBinding()]
param([switch]$SinInfra, [switch]$CargarDatos)

$ErrorActionPreference = 'Stop'
$raizDemo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$backendDemo = Join-Path $raizDemo 'backend'
$frontendDemo = Join-Path $raizDemo 'frontend'
$pythonDemo = Join-Path $backendDemo '.venv\Scripts\python.exe'
$ngDemo = Join-Path $frontendDemo 'node_modules\@angular\cli\bin\ng.js'
$logsDemo = Join-Path $raizDemo 'tmp\demo-local'

if (-not (Test-Path -LiteralPath (Join-Path $raizDemo '.env'))) { throw 'Falta .env. Complete la configuracion indicada en README.md.' }
if (-not (Test-Path -LiteralPath $pythonDemo)) { throw 'Falta backend/.venv. Instale las dependencias del backend segun README.md.' }
if (-not (Test-Path -LiteralPath $ngDemo)) { throw 'Faltan dependencias del frontend. Ejecute npm ci en frontend.' }
$nodeDemo = (Get-Command node -ErrorAction Stop).Source
New-Item -ItemType Directory -Force -Path $logsDemo | Out-Null

Push-Location $backendDemo
try {
    $configuracionDemo = & $pythonDemo -m herramientas.demo_local --configuracion
    if ($LASTEXITCODE -ne 0) { throw ($configuracionDemo -join ' ') }
    $configuracionDemo = $configuracionDemo | ConvertFrom-Json
} finally { Pop-Location }

if (-not $SinInfra) {
    & (Join-Path $PSScriptRoot 'mantener-wsl.ps1') -SegundoPlano
    & (Join-Path $PSScriptRoot 'infra-arriba.ps1')
}
Push-Location $backendDemo
try {
    & $pythonDemo -m herramientas.esperar_bd --segundos 40
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL o Redis no estan disponibles.' }
    & $pythonDemo -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron aplicar las migraciones.' }
    if ($CargarDatos) {
        & $pythonDemo -m app.semillas.cargar
        if ($LASTEXITCODE -ne 0) { throw 'No se pudieron cargar las semillas sinteticas.' }
    }
    $datosDemo = & $pythonDemo -m herramientas.demo_local
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo consultar la clinica sintetica.' }
    $datosDemo = $datosDemo | ConvertFrom-Json
} finally { Pop-Location }

function Test-UrlDemo([string]$Url) {
    try { return (Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 }
    catch { return $false }
}
function Test-ApiActualDemo {
    try {
        $specDemo = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/openapi.json' -TimeoutSec 3
        $rutasDemo = @($specDemo.paths.PSObject.Properties.Name)
        return (
            $rutasDemo -contains '/api/v1/historia/adherencia/alertas' -and
            $rutasDemo -contains '/api/v1/conversaciones' -and
            $rutasDemo -contains '/api/v1/conversaciones/pendientes/cuenta' -and
            $rutasDemo -contains '/api/v1/plataforma/clinicas'
        )
    } catch { return $false }
}
function Esperar-UrlDemo([string]$Url, [System.Diagnostics.Process]$Proceso) {
    $finDemo = (Get-Date).AddSeconds(50)
    do {
        if (Test-UrlDemo $Url) { return }
        if ($Proceso.HasExited) { throw "El proceso termino. Consulte los registros en $logsDemo." }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $finDemo)
    throw "No responde $Url. Consulte los registros en $logsDemo."
}

if (-not (Test-ApiActualDemo)) {
    if (Test-UrlDemo 'http://127.0.0.1:8000/salud/listo') {
        throw 'La API del puerto 8000 responde, pero ejecuta una version anterior sin las rutas actuales de ClinicAI. Detenga la instancia anterior y vuelva a ejecutar infra/scripts/demo-local.ps1.'
    }
    if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { throw 'El puerto 8000 esta ocupado por un servicio que no esta listo.' }
    $apiDemo = Start-Process -FilePath $pythonDemo -ArgumentList '-m','uvicorn','app.main:crear_aplicacion','--factory','--host','127.0.0.1','--port','8000' -WorkingDirectory $backendDemo -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logsDemo 'api.log') -RedirectStandardError (Join-Path $logsDemo 'api-error.log')
    Esperar-UrlDemo 'http://127.0.0.1:8000/salud/listo' $apiDemo
    if (-not (Test-ApiActualDemo)) { throw "La API inicio pero no publica las rutas actuales. Consulte $logsDemo\api-error.log." }
}
if (-not (Test-UrlDemo 'http://localhost:4200')) {
    if (Get-NetTCPConnection -LocalPort 4200 -State Listen -ErrorAction SilentlyContinue) { throw 'El puerto 4200 esta ocupado por otro servicio.' }
    $webDemo = Start-Process -FilePath $nodeDemo -ArgumentList ('"{0}"' -f $ngDemo),'serve','--host','localhost','--port','4200' -WorkingDirectory $frontendDemo -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logsDemo 'frontend.log') -RedirectStandardError (Join-Path $logsDemo 'frontend-error.log')
    Esperar-UrlDemo 'http://localhost:4200' $webDemo
}

if ($configuracionDemo.whatsapp -eq 'sandbox' -and $configuracionDemo.calendario -eq 'sandbox') {
    $workerDemo = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -match 'herramientas.worker_local|arq app.tareas.worker.ConfiguracionWorker' -and $_.CommandLine -like "*$raizDemo*" }
    if (-not $workerDemo) {
        $workerDemo = Start-Process -FilePath $pythonDemo -ArgumentList '-m','herramientas.worker_local' -WorkingDirectory $backendDemo -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logsDemo 'worker.log') -RedirectStandardError (Join-Path $logsDemo 'worker-error.log')
        Start-Sleep -Seconds 2
        if ($workerDemo.HasExited) { throw "El worker no arranco. Consulte $logsDemo\worker-error.log." }
    }
    Write-Host 'Worker local activo; WhatsApp y calendario en sandbox.'
} else {
    Write-Host 'Worker no iniciado: los proveedores configurados no estan ambos en sandbox.'
}
Write-Host 'Aplicacion: http://localhost:4200'
Write-Host 'API: http://127.0.0.1:8000/documentacion'
Write-Host "Modelo configurado: $($configuracionDemo.llm). El agente permite elegir simulador local."
Write-Host "Registros: $logsDemo"
foreach ($clinicaDemo in $datosDemo.clinicas) { Write-Host "$($clinicaDemo.nombre): $($clinicaDemo.id)" }
if (-not $datosDemo.clinicas) { Write-Host 'No hay clinicas sinteticas. Repita con -CargarDatos para crear la demostracion.' }
