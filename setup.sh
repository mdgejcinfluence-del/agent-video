#!/usr/bin/env bash
# Installe tout ce dont l'agent a besoin (serveur Linux ou GitHub Actions). Aucun service payant.
#
# Chaque étape qui dépend du réseau a une durée maximale, recommence une fois, et a une solution de rechange :
# le 11/11/2026, les miroirs de paquets d'Ubuntu ne répondaient plus depuis les machines de GitHub
# (« Temporary failure resolving »), et l'installation restait bloquée. L'agent ne doit pas dépendre d'eux.
set -euo pipefail
cd "$(dirname "$0")"
SUDO=""; [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null && SUDO="sudo"
APT_OPTS="-o Acquire::Retries=1 -o Acquire::http::Timeout=15 -o Acquire::https::Timeout=15 -o DPkg::Lock::Timeout=60"
OUTILS="$HOME/.cache/agent-video/bin"          # ffmpeg et ffprobe autonomes (run.py ajoute ce dossier au PATH)
export PATH="$OUTILS:$PATH"
[ -n "${GITHUB_PATH:-}" ] && echo "$OUTILS" >> "$GITHUB_PATH"

essayer() {            # essayer N commande… : recommence une commande qui échoue
  local n=$1 i; shift
  for i in $(seq 1 "$n"); do
    if "$@"; then return 0; fi
    if [ "$i" -lt "$n" ]; then echo "… échec, nouvel essai dans $((i * 10)) s : $*"; sleep $((i * 10)); fi
  done
  return 1
}
outils_video() { command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null; }
ffmpeg_paquet() {      # par le gestionnaire de paquets : au plus 90 s pour la liste, 3 min pour l'installation
  command -v apt-get >/dev/null || return 1
  $SUDO timeout 90 apt-get $APT_OPTS update -qq || true
  $SUDO env DEBIAN_FRONTEND=noninteractive timeout 180 apt-get $APT_OPTS install -y -qq ffmpeg && outils_video
}
ffmpeg_autonome() {    # deux programmes sans aucune dépendance, téléchargés une fois puis gardés en cache
  local arch tmp url
  case "$(uname -m)" in x86_64) arch="amd64 linux64" ;; aarch64 | arm64) arch="arm64 linuxarm64" ;; *) return 1 ;; esac
  tmp=$(mktemp -d)
  for url in "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-${arch% *}-static.tar.xz" \
             "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-${arch#* }-gpl.tar.xz"; do
    echo "ffmpeg autonome : $url"
    if timeout 300 curl -fsSL --retry 1 --connect-timeout 15 -o "$tmp/f.tar.xz" "$url" && tar -xJf "$tmp/f.tar.xz" -C "$tmp"; then
      mkdir -p "$OUTILS"
      find "$tmp" -type f \( -name ffmpeg -o -name ffprobe \) -exec cp -f {} "$OUTILS/" \;
      chmod +x "$OUTILS/ffmpeg" "$OUTILS/ffprobe" 2>/dev/null || true
      if "$OUTILS/ffmpeg" -version >/dev/null 2>&1 && "$OUTILS/ffprobe" -version >/dev/null 2>&1; then rm -rf "$tmp"; return 0; fi
    fi
    rm -rf "$tmp"/* "$OUTILS/ffmpeg" "$OUTILS/ffprobe"
  done
  rm -rf "$tmp"; return 1
}
navigateur_demarre() {
  timeout 60 python3 -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(); b.new_page().close(); b.close()" >/dev/null 2>&1
}

# 1. ffmpeg et ffprobe. Sur GitHub : la version autonome d'abord (elle reste en cache d'un réveil à l'autre,
#    donc plus aucun téléchargement ensuite). Sur un serveur : le paquet du système d'abord.
if ! outils_video; then
  if [ "${GITHUB_ACTIONS:-}" = "true" ]; then ffmpeg_autonome || ffmpeg_paquet; else ffmpeg_paquet || ffmpeg_autonome; fi
  outils_video || { echo "Impossible d'installer ffmpeg."; exit 1; }
fi
echo "ffmpeg : $(command -v ffmpeg) — $(ffmpeg -version | head -1 | cut -c1-60)"

# 2. Les bibliothèques Python.
python3 -m pip install -q --upgrade pip || true
essayer 2 timeout 300 python3 -m pip install -q -r requirements.txt

# 3. Le navigateur de rendu : téléchargé une fois (rien à faire s'il est en cache), puis on vérifie qu'il démarre.
#    Ses bibliothèques système ne sont installées que s'il ne démarre pas : la plupart des machines les ont déjà.
essayer 2 timeout 300 python3 -m playwright install chromium-headless-shell
if navigateur_demarre; then
  echo "navigateur de rendu : il démarre, rien d'autre à installer"
else
  echo "navigateur de rendu : il ne démarre pas encore, installation de ses bibliothèques système"
  essayer 2 timeout 300 python3 -m playwright install-deps chromium-headless-shell
  navigateur_demarre || { echo "Le navigateur de rendu ne démarre toujours pas."; exit 1; }
fi
echo "Installation terminée. Vérifie avec : python3 run.py doctor"
