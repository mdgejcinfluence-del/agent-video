#!/usr/bin/env bash
# Installe tout ce dont l'agent a besoin (serveur Linux ou GitHub Actions). Aucun service payant.
set -euo pipefail
cd "$(dirname "$0")"
SUDO=""; [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null && SUDO="sudo"
if ! command -v ffmpeg >/dev/null; then
  $SUDO apt-get update -qq && $SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ffmpeg
fi
python3 -m pip install -q --upgrade pip
python3 -m pip install -q -r requirements.txt
python3 -m playwright install --with-deps chromium-headless-shell
echo "Installation terminée. Vérifie avec : python3 run.py doctor"
