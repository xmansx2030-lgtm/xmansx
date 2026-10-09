#!/usr/bin/env bash
set -Eeuo pipefail

# Isolated GitHub Linux runners only; never restart a developer/production daemon.
if [[ "${GITHUB_ACTIONS:-}" != "true" || "${RUNNER_OS:-}" != "Linux" ]]; then
  echo "Docker mirror setup is restricted to GitHub Linux CI." >&2
  exit 2
fi
if [[ -n "$(docker ps --quiet)" ]]; then
  echo "Configure the CI mirror before starting any containers." >&2
  exit 2
fi

# Google-managed cache for public Docker Official Images, with Docker Hub fallback.
# Preserve the runner's other daemon settings and existing file permissions.
sudo python3 - <<'PY'
import json
from pathlib import Path
path = Path("/etc/docker/daemon.json")
config = json.loads(path.read_text()) if path.exists() else {}
config["registry-mirrors"] = list(dict.fromkeys([
    "https://mirror.gcr.io", *config.get("registry-mirrors", [])
]))
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(config, indent=2) + "\n")
PY
sudo systemctl restart docker
docker info --format '{{json .RegistryConfig.Mirrors}}'
