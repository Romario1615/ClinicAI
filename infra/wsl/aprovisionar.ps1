# ---------------------------------------------------------------------------
#  Aprovisiona la infraestructura local: distribucion WSL2 en D: con Docker
#  Engine y el plugin Compose.
#
#  Motivo (ADR-0002): Docker Desktop no es viable en este equipo porque el
#  disco C: no tiene espacio y no permite instalarse en otro volumen; y
#  pgvector no se puede compilar de forma nativa por falta de MSVC.
#
#  Es idempotente: si la distribucion ya existe, no la recrea.
#  No borra nada.  No toca el PostgreSQL de Odoo ni MSSQLSERVER.
#
#  Uso:
#    .\infra\wsl\aprovisionar.ps1
#    .\infra\wsl\aprovisionar.ps1 -Verificar     # solo comprueba el estado
# ---------------------------------------------------------------------------

[CmdletBinding()]
param(
    [string]$NombreDistribucion = 'clinica',
    [string]$Distribucion       = 'Ubuntu-24.04',
    [string]$Ubicacion          = 'D:\wsl\clinica',
    [string]$UsuarioLinux       = 'clinica',
    # Carpeta de descarga de la imagen.  En D: a proposito: `wsl --install`
    # descarga en el directorio temporal de C:, y este equipo no tiene
    # espacio ahi (riesgo R-01).
    [string]$CarpetaImagenes    = 'D:\wsl\imagenes',
    # Tamano maximo del disco virtual.  Disperso: solo ocupa lo que usa.
    [string]$TamanoVhd          = '40GB',
    # Usa `wsl --install` en lugar de descargar e importar.  Mas simple, pero
    # requiere espacio libre en C: para la descarga.
    [switch]$UsarInstalador,
    [switch]$Verificar
)

$ErrorActionPreference = 'Stop'

function Escribir-Paso  { param($m) Write-Host "`n==> $m" -ForegroundColor Cyan }
function Escribir-Ok    { param($m) Write-Host "    $m" -ForegroundColor Green }
function Escribir-Aviso { param($m) Write-Host "    $m" -ForegroundColor Yellow }
function Escribir-Fallo { param($m) Write-Host "    $m" -ForegroundColor Red }
function Escribir-Info  { param($m) Write-Host "    $m" -ForegroundColor DarkGray }

# wsl.exe emite UTF-16LE; sin esta limpieza la salida llega con bytes nulos
# intercalados y ninguna comparacion de cadenas funciona.
function Invocar-Wsl {
    param([string[]]$Argumentos)
    $salida = & wsl.exe @Argumentos 2>&1
    return ($salida | ForEach-Object { $_ -replace "`0", '' })
}

function Obtener-Distribuciones {
    $salida = Invocar-Wsl @('--list', '--quiet')
    return $salida | Where-Object { $_.Trim() -ne '' } | ForEach-Object { $_.Trim() }
}

function Probar-Distribucion {
    param([string]$Nombre)
    return (Obtener-Distribuciones) -contains $Nombre
}

# ---------------------------------------------------------------------------
#  0. Comprobaciones previas
# ---------------------------------------------------------------------------
Escribir-Paso 'Comprobaciones previas'

$versionWsl = (Invocar-Wsl @('--version')) -join ' '
if (-not $versionWsl) {
    Escribir-Fallo 'WSL no esta disponible en este sistema.'
    Escribir-Info  'Instale WSL2 con: wsl --install --no-distribution'
    exit 1
}
Escribir-Ok 'WSL disponible'

# El disco virtual es disperso, pero la descarga y la descompresion necesitan
# margen real.
$discoD = Get-PSDrive -Name D -ErrorAction SilentlyContinue
if (-not $discoD) {
    Escribir-Fallo 'No se encuentra el disco D:. Este proyecto lo requiere (ADR-0003).'
    exit 1
}
$libreD = [math]::Round($discoD.Free / 1GB, 2)
if ($libreD -lt 8) {
    Escribir-Fallo "Disco D: con solo $libreD GB libres. Se necesitan al menos 8 GB."
    exit 1
}
Escribir-Ok "Disco D: $libreD GB libres"

$discoC = Get-PSDrive -Name C -ErrorAction SilentlyContinue
if ($discoC) {
    $libreC = [math]::Round($discoC.Free / 1GB, 2)
    if ($libreC -lt 2) {
        Escribir-Aviso "Disco C: con solo $libreC GB libres."
        Escribir-Info  'La distribucion se instala en D:, pero WSL escribe algo de estado en C:.'
        Escribir-Info  'Se recomienda liberar espacio en C: (riesgo R-01).'
    }
}

# ---------------------------------------------------------------------------
#  Modo verificacion
# ---------------------------------------------------------------------------
if ($Verificar) {
    Escribir-Paso 'Estado de la infraestructura'

    if (Probar-Distribucion $NombreDistribucion) {
        Escribir-Ok "Distribucion '$NombreDistribucion' presente"
        $docker  = (Invocar-Wsl @('-d', $NombreDistribucion, '--', 'bash', '-lc', 'docker --version 2>/dev/null || echo AUSENTE')) -join ''
        $compose = (Invocar-Wsl @('-d', $NombreDistribucion, '--', 'bash', '-lc', 'docker compose version --short 2>/dev/null || echo AUSENTE')) -join ''
        $demonio = (Invocar-Wsl @('-d', $NombreDistribucion, '--', 'bash', '-lc', 'docker info >/dev/null 2>&1 && echo ACTIVO || echo INACTIVO')) -join ''

        if ($docker  -match 'AUSENTE') { Escribir-Fallo 'Docker: no instalado' }  else { Escribir-Ok "Docker: $docker" }
        if ($compose -match 'AUSENTE') { Escribir-Fallo 'Compose: no instalado' } else { Escribir-Ok "Compose: $compose" }
        if ($demonio -match 'ACTIVO')  { Escribir-Ok 'Demonio: activo' }          else { Escribir-Aviso 'Demonio: inactivo (pruebe: wsl --shutdown)' }
    } else {
        Escribir-Fallo "Distribucion '$NombreDistribucion' no existe."
        Escribir-Info  'Ejecute este script sin -Verificar para crearla.'
    }
    exit 0
}

# ---------------------------------------------------------------------------
#  1. Distribucion WSL en D:
# ---------------------------------------------------------------------------
Escribir-Paso "Distribucion WSL '$NombreDistribucion'"

if (Probar-Distribucion $NombreDistribucion) {
    Escribir-Ok 'Ya existe; no se recrea.'
    Escribir-Info "Para empezar de cero, primero:  wsl --unregister $NombreDistribucion"
} else {
    if (-not (Test-Path -LiteralPath $Ubicacion)) {
        New-Item -ItemType Directory -Force -Path $Ubicacion | Out-Null
    }

    if ($UsarInstalador) {
        # Camino simple. Requiere espacio libre en C: porque `wsl --install`
        # descarga la imagen en el directorio temporal del sistema.
        Escribir-Info "Instalando $Distribucion con 'wsl --install'"
        Escribir-Aviso 'Este camino descarga en el directorio temporal de C:.'

        & wsl.exe --install $Distribucion `
            --name     $NombreDistribucion `
            --location $Ubicacion `
            --vhd-size $TamanoVhd `
            --no-launch

        if ($LASTEXITCODE -ne 0) {
            Escribir-Fallo "La instalacion fallo con codigo $LASTEXITCODE."
            Escribir-Info  'Si el fallo es por falta de espacio en C:, reintente sin'
            Escribir-Info  '-UsarInstalador para descargar e importar desde D:.'
            exit 1
        }
    } else {
        # Camino por defecto: descargar la imagen a D: e importarla.
        #
        # Motivo: `wsl --install` descarga en el temporal de C:, y este equipo
        # tiene menos de 500 MB libres ahi.  Descargar a D: e importar deja
        # C: intacto, que es lo unico responsable con el disco del sistema en
        # ese estado (riesgo R-01).
        if (-not (Test-Path -LiteralPath $CarpetaImagenes)) {
            New-Item -ItemType Directory -Force -Path $CarpetaImagenes | Out-Null
        }

        Escribir-Info 'Resolviendo la URL de la imagen desde el manifiesto oficial de WSL...'

        $urlImagen = $null
        try {
            $manifiesto = Invoke-WebRequest -UseBasicParsing -TimeoutSec 30 `
                -Uri 'https://raw.githubusercontent.com/microsoft/WSL/master/distributions/DistributionInfo.json'
            $datos = $manifiesto.Content | ConvertFrom-Json

            foreach ($familia in $datos.ModernDistributions.PSObject.Properties.Name) {
                foreach ($entrada in $datos.ModernDistributions.$familia) {
                    if ($entrada.Name -eq $Distribucion) {
                        $urlImagen = $entrada.Amd64Url.Url
                        $hashEsperado = $entrada.Amd64Url.Sha256
                        break
                    }
                }
                if ($urlImagen) { break }
            }
        } catch {
            Escribir-Fallo "No se pudo leer el manifiesto: $($_.Exception.Message)"
            exit 1
        }

        if (-not $urlImagen) {
            Escribir-Fallo "El manifiesto no contiene la distribucion '$Distribucion'."
            Escribir-Info  'Distribuciones validas: Ubuntu-24.04, Ubuntu-22.04, Ubuntu-26.04'
            exit 1
        }

        $nombreArchivo = Split-Path -Leaf $urlImagen
        $rutaImagen    = Join-Path $CarpetaImagenes $nombreArchivo
        Escribir-Ok "Imagen: $nombreArchivo"

        # Se comprueba la integridad ANTES de decidir si hay que descargar.
        # Un archivo presente no significa un archivo completo: un intento
        # interrumpido deja un parcial que parece valido por su tamano.
        $imagenValida = $false
        if ((Test-Path -LiteralPath $rutaImagen) -and $hashEsperado) {
            $mb = [math]::Round((Get-Item -LiteralPath $rutaImagen).Length / 1MB, 1)
            Escribir-Info "Hay una imagen local de $mb MB; verificando integridad..."
            $hashLocal = (Get-FileHash -LiteralPath $rutaImagen -Algorithm SHA256).Hash.ToLower()
            if ($hashLocal -eq $hashEsperado.ToLower()) {
                Escribir-Ok 'Imagen local completa y valida; no se vuelve a bajar.'
                $imagenValida = $true
            } else {
                Escribir-Aviso 'La imagen local esta incompleta; se reanuda la descarga.'
            }
        }

        if (-not $imagenValida) {
            Escribir-Info "Descargando a $rutaImagen (unos 373 MB)..."

            # Se usa curl.exe, no Invoke-WebRequest.
            #
            # Invoke-WebRequest en Windows PowerShell 5.1 acumula la respuesta
            # completa en memoria antes de escribirla, incluso con -OutFile.
            # Con una imagen de 373 MB y poca memoria libre eso provoca
            # paginacion y deja el archivo de destino en 0 bytes hasta el
            # final.  curl escribe en streaming y admite reanudacion.
            #
            # curl.exe viene con Windows 10 y posteriores; se comprueba antes.
            $curl = (Get-Command curl.exe -ErrorAction SilentlyContinue)
            if (-not $curl) {
                Escribir-Fallo 'No se encuentra curl.exe, necesario para la descarga.'
                Escribir-Info  'Descargue manualmente la imagen y coloquela en:'
                Escribir-Info  "  $rutaImagen"
                Escribir-Info  "  desde $urlImagen"
                exit 1
            }

            # -C - reanuda si hay un archivo parcial de un intento anterior.
            # --fail hace que un 404 devuelva error en lugar de guardar la
            # pagina de error como si fuera la imagen.
            & curl.exe --location --fail --show-error `
                --retry 3 --retry-delay 5 `
                --continue-at - `
                --output $rutaImagen `
                $urlImagen

            if ($LASTEXITCODE -ne 0) {
                Escribir-Fallo "Fallo la descarga (curl devolvio $LASTEXITCODE)."
                Escribir-Info  'El archivo parcial se conserva; reintente para reanudar.'
                exit 1
            }

            $mb = [math]::Round((Get-Item -LiteralPath $rutaImagen).Length / 1MB, 1)
            Escribir-Ok "Descargada ($mb MB)"
        }

        # Verificacion de integridad tras la descarga.  Una imagen corrupta
        # produce fallos confusos horas mas tarde, dentro de apt o del propio
        # kernel, y cuesta mucho mas diagnosticar entonces.
        if (-not $imagenValida) {
            if ($hashEsperado) {
                Escribir-Info 'Verificando la suma SHA256...'
                $hashReal = (Get-FileHash -LiteralPath $rutaImagen -Algorithm SHA256).Hash.ToLower()
                if ($hashReal -ne $hashEsperado.ToLower()) {
                    Escribir-Fallo 'La suma SHA256 no coincide tras la descarga completa.'
                    Escribir-Info  "  esperado: $($hashEsperado.ToLower())"
                    Escribir-Info  "  obtenido: $hashReal"
                    Escribir-Info  'Se descarta la imagen; vuelva a ejecutar el script.'
                    Remove-Item -LiteralPath $rutaImagen -Force -ErrorAction SilentlyContinue
                    exit 1
                }
                Escribir-Ok 'Suma SHA256 correcta'
            } else {
                Escribir-Aviso 'El manifiesto no publica suma de verificacion; se omite.'
            }
        }

        Escribir-Info "Importando en $Ubicacion ..."
        & wsl.exe --import $NombreDistribucion $Ubicacion $rutaImagen --version 2

        if ($LASTEXITCODE -ne 0) {
            Escribir-Fallo "La importacion fallo con codigo $LASTEXITCODE."
            exit 1
        }
    }

    Start-Sleep -Seconds 3
    if (-not (Probar-Distribucion $NombreDistribucion)) {
        Escribir-Fallo 'La distribucion no aparece tras la instalacion.'
        exit 1
    }
    Escribir-Ok 'Distribucion instalada'
}

# ---------------------------------------------------------------------------
#  2. Usuario sin privilegios
# ---------------------------------------------------------------------------
Escribir-Paso "Usuario '$UsuarioLinux'"

$existeUsuario = (Invocar-Wsl @('-d', $NombreDistribucion, '-u', 'root', '--', 'bash', '-lc', "id -u $UsuarioLinux >/dev/null 2>&1 && echo SI || echo NO")) -join ''

if ($existeUsuario -match 'SI') {
    Escribir-Ok 'Ya existe'
} else {
    # Sin contrasena: el acceso a la distribucion ya esta controlado por la
    # sesion de Windows.  Una contrasena aqui no anade seguridad real y
    # obligaria a pedirla por consola, que no es automatizable.
    $guion = @"
set -e
useradd -m -s /bin/bash $UsuarioLinux
usermod -aG sudo $UsuarioLinux
passwd -d $UsuarioLinux
echo '$UsuarioLinux ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/90-$UsuarioLinux
chmod 0440 /etc/sudoers.d/90-$UsuarioLinux
grep -q '^default=' /etc/wsl.conf 2>/dev/null || printf '[user]\ndefault=$UsuarioLinux\n' >> /etc/wsl.conf
"@
    $guion = $guion -replace "`r`n", "`n"
    Invocar-Wsl @('-d', $NombreDistribucion, '-u', 'root', '--', 'bash', '-lc', $guion) | Out-Null

    if ($LASTEXITCODE -ne 0) {
        Escribir-Fallo 'No se pudo crear el usuario.'
        exit 1
    }
    Escribir-Ok 'Usuario creado y establecido como predeterminado'
}

# ---------------------------------------------------------------------------
#  3. Limites de recursos de WSL
# ---------------------------------------------------------------------------
Escribir-Paso 'Limites de recursos (.wslconfig)'

$rutaWslConfig = Join-Path $env:USERPROFILE '.wslconfig'

if (Test-Path -LiteralPath $rutaWslConfig) {
    Escribir-Aviso 'Ya existe un .wslconfig; no se sobrescribe.'
    Escribir-Info  "Revise $rutaWslConfig y compare con infra/wsl/wslconfig.ejemplo"
} else {
    # El equipo tiene 13.9 GB de RAM y ~2.8 GB libres con MSSQLSERVER activo
    # (riesgo R-02).  Sin limite, WSL reclama hasta el 50 % de la memoria y
    # deja el escritorio inutilizable.
    $plantilla = Join-Path $PSScriptRoot 'wslconfig.ejemplo'
    if (Test-Path -LiteralPath $plantilla) {
        Copy-Item -LiteralPath $plantilla -Destination $rutaWslConfig
        Escribir-Ok "Creado $rutaWslConfig (4 GB de RAM, 4 CPU)"
        Escribir-Info 'Se aplica tras: wsl --shutdown'
    } else {
        Escribir-Aviso 'No se encuentra la plantilla wslconfig.ejemplo; se omite.'
    }
}

# ---------------------------------------------------------------------------
#  4. Docker Engine
# ---------------------------------------------------------------------------
Escribir-Paso 'Docker Engine y plugin Compose'

$guionInstalador = Join-Path $PSScriptRoot 'instalar-docker.sh'
if (-not (Test-Path -LiteralPath $guionInstalador)) {
    Escribir-Fallo "No se encuentra $guionInstalador"
    exit 1
}

# Se copia el guion dentro de la distribucion en lugar de ejecutarlo desde
# /mnt/d: asi los finales de linea y los permisos quedan bajo control y no
# depende de como Windows haya guardado el archivo.
$contenidoGuion = (Get-Content -LiteralPath $guionInstalador -Raw) -replace "`r`n", "`n"
$guionBase64    = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($contenidoGuion))

Escribir-Info 'Instalando dentro de la distribucion (puede tardar unos minutos)...'

$ordenInstalacion = "echo '$guionBase64' | base64 -d > /tmp/instalar-docker.sh && chmod +x /tmp/instalar-docker.sh && bash /tmp/instalar-docker.sh $UsuarioLinux"
& wsl.exe -d $NombreDistribucion -u root -- bash -lc $ordenInstalacion

if ($LASTEXITCODE -ne 0) {
    Escribir-Fallo "La instalacion de Docker fallo con codigo $LASTEXITCODE."
    Escribir-Info  'Revise la salida anterior. Causa habitual: sin acceso a la red.'
    exit 1
}

# ---------------------------------------------------------------------------
#  5. Reinicio para aplicar systemd y la pertenencia al grupo docker
# ---------------------------------------------------------------------------
Escribir-Paso 'Reiniciando la distribucion'
Escribir-Info 'Necesario para que systemd y el grupo docker surtan efecto.'

& wsl.exe --shutdown
Start-Sleep -Seconds 6

# ---------------------------------------------------------------------------
#  6. Verificacion final
# ---------------------------------------------------------------------------
Escribir-Paso 'Verificacion'

$docker  = (Invocar-Wsl @('-d', $NombreDistribucion, '--', 'bash', '-lc', 'docker --version 2>/dev/null || echo AUSENTE')) -join ''
$compose = (Invocar-Wsl @('-d', $NombreDistribucion, '--', 'bash', '-lc', 'docker compose version --short 2>/dev/null || echo AUSENTE')) -join ''
$demonio = (Invocar-Wsl @('-d', $NombreDistribucion, '--', 'bash', '-lc', 'docker info >/dev/null 2>&1 && echo ACTIVO || echo INACTIVO')) -join ''
$sinSudo = (Invocar-Wsl @('-d', $NombreDistribucion, '-u', $UsuarioLinux, '--', 'bash', '-lc', 'docker ps >/dev/null 2>&1 && echo SI || echo NO')) -join ''

$todoBien = $true

if ($docker -match 'AUSENTE') { Escribir-Fallo 'Docker: NO instalado'; $todoBien = $false }
else                          { Escribir-Ok "Docker: $docker" }

if ($compose -match 'AUSENTE') { Escribir-Fallo 'Compose: NO instalado'; $todoBien = $false }
else                           { Escribir-Ok "Compose: v$compose" }

if ($demonio -match 'ACTIVO') {
    Escribir-Ok 'Demonio: activo'
} else {
    Escribir-Aviso 'Demonio: inactivo.'
    Escribir-Info  "Pruebe: wsl -d $NombreDistribucion -u root -- service docker start"
    $todoBien = $false
}

if ($sinSudo -match 'SI') { Escribir-Ok "Usuario '$UsuarioLinux': puede usar Docker sin sudo" }
else                      { Escribir-Aviso "Usuario '$UsuarioLinux': aun necesita sudo para Docker" }

Write-Host ''
if ($todoBien) {
    Write-Host 'Aprovisionamiento completado.' -ForegroundColor Green
    Write-Host ''
    Write-Host 'Siguiente paso:' -ForegroundColor Cyan
    Write-Host '  1. Copy-Item .env.example .env   y complete los valores'
    Write-Host '  2. .\infra\scripts\infra-arriba.ps1'
} else {
    Write-Host 'Aprovisionamiento incompleto. Revise los errores anteriores.' -ForegroundColor Yellow
    exit 1
}
