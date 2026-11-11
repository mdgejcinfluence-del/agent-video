#!/usr/bin/env bash
# Installe tout ce dont l'agent a besoin (serveur Linux ou GitHub Actions). Aucun service payant.
# Chaque étape qui dépend du réseau a une durée maximale et recommence une fois : un miroir en panne ne doit pas
# bloquer l'agent pendant une heure (vu le 11/11/2026 : résolution de noms en panne sur une machine de GitHub).
set -euo pipefail
cd "$(dirname "$0")"
SUDO=""; [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null && SUDO="sudo"
APT_OPTS="-o Acquire::Retries=2 -o Acquire::http::Timeout=15 -o Acquire::https::Timeout=15 -o DPkg::Lock::Timeout=90"

essayer() {            # essayer N commande… : recommence une commande qui échoue
  local n=$1 i; shift
  for i in $(seq 1 "$n"); do
    if "$@"; then return 0; fi
    if [ "$i" -lt "$n" ]; then echo "… échec, nouvel essai dans $((i * 15)) s : $*"; sleep $((i * 15)); fi
  done
  return 1
}
apt_installer() {      # au plus 2 min pour la liste des paquets, 4 min pour l'installation
  $SUDO timeout 120 apt-get $APT_OPTS update -qq || true
  $SUDO env DEBIAN_FRONTEND=noninteractive timeout 240 apt-get $APT_OPTS install -y -qq "$@"
}
navigateur_demarre() {
  timeout 60 python3 -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(); b.new_page().close(); b.close()" >/dev/null 2>&1
}

if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
  essayer 2 apt_installer ffmpeg
fi
python3 -m pip install -q --upgrade pip || true
essayer 2 timeout 300 python3 -m pip install -q -r requirements.txt

# Navigateur de rendu : téléchargé une fois (rien à faire s'il est déjà en cache), puis on vérifie qu'il démarre.
# Les bibliothèques système ne sont installées que s'il ne démarre pas : la plupart des machines les ont déjà,
# et cela évite de dépendre des miroirs de paquets à chaque réveil.
essayer 2 timeout 300 python3 -m playwright install chromium-headless-shell
if ! navigateur_demarre; then
  echo "Le navigateur ne démarre pas encore : installation de ses bibliothèques système."
  essayer 2 timeout 420 python3 -m playwright install-deps chromium-headless-shell
  navigateur_demarre || { echo "Le navigateur de rendu ne démarre toujours pas."; exit 1; }
fi
echo "Installation terminée. Vérifie avec : python3 run.py doctor"
