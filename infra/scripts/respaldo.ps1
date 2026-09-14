<#
.SINOPSIS
    Crea un respaldo cifrado de la base de datos clinica.

.DESCRIPCION
    Ejecuta `pg_dump` en formato personalizado dentro del contenedor y cifra el
    resultado antes de que toque el disco del anfitrion.

    Por que cifrado y no un volcado plano
    -------------------------------------
    Un volcado de esta base contiene historia clinica. Un archivo sin cifrar en
    una carpeta de respaldos es una copia completa de datos de salud sin
    ninguno de los controles de acceso del sistema: ni permisos, ni ambito, ni
    auditoria de quien lo abre.

    La clave NO vive aqui ni en el repositorio. Se toma de la variable de
    entorno `CLAVE_RESPALDO`, que el operador provee desde su gestor de
    secretos. Sin ella el script se niega a ejecutarse: producir un respaldo
    sin cifrar "solo por esta vez" es justo como acaban existiendo.

.PARAMETER Destino
    Carpeta donde dejar el archivo. Por defecto `D:\respaldos-clinica`.

.PARAMETER Distro
    Distribucion WSL donde corre Docker. Por defecto `clinica`.

.EJEMPLO
    $env:CLAVE_RESPALDO = (Read-Host -AsSecureString | ConvertFrom-SecureString -AsPlainText)
    .\infra\scripts\respaldo.ps1
#>
[CmdletBinding()]
param(
    [string]$Destino = 'D:\respaldos-clinica',
    [string]$Distro = 'clinica',
    [string]$Contenedor = 'clinica-pg',
    [string]$Usuario = 'clinica',
    [string]$BaseDatos = 'clinica'
)

$ErrorActionPreference = 'Stop'

if (-not $env:CLAVE_RESPALDO) {
    throw @'
Falta CLAVE_RESPALDO.

Un volcado de esta base es una copia completa de historia clinica. Sin cifrar
no tiene ninguno de los controles del sistema: ni permisos, ni ambito, ni
registro de quien lo abre. El script no produce respaldos en claro.

Defina la variable desde su gestor de secretos antes de ejecutarlo.
'@
}

if (-not (Test-Path $Destino)) {
    New-Item -ItemType Directory -Path $Destino -Force | Out-Null
}

$marca = Get-Date -Format 'yyyyMMdd-HHmmss'
$nombre = "clinica-$marca.dump.enc"
$ruta = Join-Path $Destino $nombre

Write-Host "Volcando $BaseDatos desde $Contenedor..."

# El volcado y el cifrado se encadenan en una sola tuberia: asi el texto en
# claro nunca se escribe en disco, ni siquiera de forma temporal.
#
# `-Fc` (formato personalizado) permite restaurar tablas sueltas y comprime por
# su cuenta. `pbkdf2` con muchas iteraciones encarece un ataque por diccionario
# contra la clave.
$comando = @"
set -o pipefail
docker exec -e PGPASSWORD="`$PGPASSWORD" $Contenedor pg_dump -U $Usuario -d $BaseDatos -Fc |
  openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -pass env:CLAVE_RESPALDO
"@

$env:WSLENV = 'CLAVE_RESPALDO:PGPASSWORD'
wsl -d $Distro -- bash -lc $comando | Set-Content -Path $ruta -Encoding Byte

$tamano = (Get-Item $ruta).Length
if ($tamano -lt 1024) {
    Remove-Item $ruta -Force
    throw "El respaldo resulto vacio o truncado ($tamano bytes). No se conserva un archivo inservible."
}

Write-Host "Respaldo: $ruta ($([math]::Round($tamano / 1MB, 2)) MB)"
Write-Host ''
Write-Host 'Este respaldo NO cuenta como valido hasta restaurarlo.' -ForegroundColor Yellow
Write-Host 'Ejecute: .\infra\scripts\restaurar.ps1 -Archivo "' -NoNewline -ForegroundColor Yellow
Write-Host "$ruta`" -Verificar" -ForegroundColor Yellow
