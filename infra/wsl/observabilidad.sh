#!/usr/bin/env bash
set -euo pipefail

raiz="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
ip_windows="$(ip route show default | awk 'NR == 1 { print $3 }')"

if [[ -z "$ip_windows" ]]; then
  echo "No se pudo descubrir la puerta de enlace de Windows desde WSL." >&2
  exit 1
fi

export WINDOWS_HOST_IP="$ip_windows"
cd "$raiz"
exec docker compose \
  --env-file .env \
  -f infra/compose/docker-compose.dev.yml \
  --profile observabilidad \
  "$@"
