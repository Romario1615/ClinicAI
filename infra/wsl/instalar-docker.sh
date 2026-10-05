#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  Instala Docker Engine y el plugin Compose dentro de la distribucion WSL.
#
#  Se ejecuta como root desde aprovisionar.ps1.  Es idempotente: volver a
#  ejecutarlo no rompe nada ni reinstala lo ya presente.
#
#  Se instala Docker ENGINE desde el repositorio oficial, no docker.io de
#  Ubuntu ni Docker Desktop:
#    - docker.io suele ir varias versiones por detras.
#    - Docker Desktop no es viable en este equipo (ADR-0002).
# ---------------------------------------------------------------------------
set -euo pipefail

USUARIO_OBJETIVO="${1:-clinica}"

log()   { printf '\033[36m[docker]\033[0m %s\n' "$*"; }
aviso() { printf '\033[33m[docker]\033[0m %s\n' "$*"; }
error() { printf '\033[31m[docker]\033[0m %s\n' "$*" >&2; }

if [[ "$(id -u)" -ne 0 ]]; then
    error "Este script debe ejecutarse como root."
    exit 1
fi

# --- 1. Paquetes base ------------------------------------------------------
log "Actualizando indices de paquetes..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq

log "Instalando dependencias..."
apt-get install -y -qq --no-install-recommends \
    ca-certificates curl gnupg lsb-release locales tzdata

# --- 2. Locale es_ES.UTF-8 -------------------------------------------------
# PostgreSQL se inicializa con --locale=es_ES.UTF-8 para que la ordenacion y
# la busqueda textual en espanol se comporten bien.  El locale debe existir
# en el contenedor, no aqui, pero generarlo tambien en el host evita avisos
# ruidosos en psql y en los scripts.
if ! locale -a 2>/dev/null | grep -qi '^es_ES.utf8$'; then
    log "Generando locale es_ES.UTF-8..."
    sed -i 's/^# *es_ES.UTF-8 UTF-8/es_ES.UTF-8 UTF-8/' /etc/locale.gen
    locale-gen >/dev/null
fi

# --- 3. Repositorio oficial de Docker --------------------------------------
if [[ ! -f /etc/apt/keyrings/docker.asc ]]; then
    log "Anadiendo la clave GPG de Docker..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
else
    log "Clave GPG de Docker ya presente."
fi

CODENAME="$(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")"
ARQ="$(dpkg --print-architecture)"
LISTA=/etc/apt/sources.list.d/docker.list
LINEA="deb [arch=${ARQ} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${CODENAME} stable"

if [[ ! -f "$LISTA" ]] || ! grep -qF "$LINEA" "$LISTA"; then
    log "Configurando el repositorio de Docker para ${CODENAME}/${ARQ}..."
    echo "$LINEA" > "$LISTA"
    apt-get update -qq
else
    log "Repositorio de Docker ya configurado."
fi

# --- 4. Docker Engine ------------------------------------------------------
if [[ ! -x /usr/bin/docker || ! -x /usr/bin/dockerd ]]; then
    log "Instalando Docker Engine, CLI, containerd y el plugin Compose..."
    apt-get install -y -qq \
        docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
else
    log "Docker Engine ya instalado: $(/usr/bin/docker --version)"
fi

# --- 5. Usuario sin privilegios en el grupo docker -------------------------
# Se evita tener que usar sudo en cada comando desde PowerShell.
if id "$USUARIO_OBJETIVO" >/dev/null 2>&1; then
    if ! id -nG "$USUARIO_OBJETIVO" | tr ' ' '\n' | grep -qx docker; then
        log "Anadiendo '$USUARIO_OBJETIVO' al grupo docker..."
        usermod -aG docker "$USUARIO_OBJETIVO"
    else
        log "'$USUARIO_OBJETIVO' ya pertenece al grupo docker."
    fi
else
    aviso "El usuario '$USUARIO_OBJETIVO' no existe; se omite el grupo docker."
fi

# --- 6. Arranque del demonio ----------------------------------------------
# WSL2 usa systemd desde la version 0.67.6.  Si esta disponible, se habilita
# el servicio para que Docker arranque solo al iniciar la distribucion.
if [[ -d /run/systemd/system ]]; then
    log "systemd detectado: habilitando docker.service..."
    systemctl enable --now docker >/dev/null 2>&1 || true
    systemctl enable --now containerd >/dev/null 2>&1 || true
else
    aviso "systemd no activo en esta sesion."
    aviso "Se habilitara en /etc/wsl.conf; requiere reiniciar la distribucion."
fi

# Asegura systemd para los proximos arranques
if [[ ! -f /etc/wsl.conf ]] || ! grep -q 'systemd=true' /etc/wsl.conf; then
    log "Habilitando systemd en /etc/wsl.conf..."
    {
        echo '[boot]'
        echo 'systemd=true'
    } >> /etc/wsl.conf
fi

# --- 7. Limites de registro del demonio -----------------------------------
# Sin esto, los logs de los contenedores pueden crecer sin freno y el disco
# D: de este equipo no tiene margen de sobra.
if [[ ! -f /etc/docker/daemon.json ]]; then
    log "Configurando limites de registro del demonio..."
    mkdir -p /etc/docker
    cat > /etc/docker/daemon.json <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
JSON
    systemctl restart docker >/dev/null 2>&1 || true
fi

# --- 8. Verificacion -------------------------------------------------------
log "Verificando la instalacion..."
/usr/bin/docker --version
/usr/bin/docker compose version

if /usr/bin/docker info >/dev/null 2>&1; then
    log "El demonio de Docker responde correctamente."
else
    aviso "El demonio aun no responde."
    aviso "Ejecute:  wsl --shutdown   y vuelva a abrir la distribucion."
fi

log "Listo."
