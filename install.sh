#!/usr/bin/env bash
# Installation du convertisseur vidéo sur macOS et Linux.
# Installe FFmpeg et uv si besoin, puis les dépendances Python.
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

install_ffmpeg() {
  case "$(uname -s)" in
    Darwin)
      if ! command -v brew >/dev/null; then
        echo "Homebrew est nécessaire pour installer FFmpeg : https://brew.sh"
        echo 'Installez-le avec : /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        exit 1
      fi
      brew install ffmpeg ;;
    Linux)
      if command -v apt-get >/dev/null; then
        sudo apt-get update && sudo apt-get install -y ffmpeg
      elif command -v dnf >/dev/null; then
        # Le paquet « ffmpeg » complet (x264, x265, NVENC…) vient de RPM Fusion sur Fedora.
        sudo dnf install -y ffmpeg || sudo dnf install -y ffmpeg-free
      elif command -v pacman >/dev/null; then
        sudo pacman -S --needed --noconfirm ffmpeg
      elif command -v zypper >/dev/null; then
        sudo zypper install -y ffmpeg
      else
        echo "Gestionnaire de paquets non reconnu : installez FFmpeg manuellement puis relancez ce script."
        exit 1
      fi ;;
    *) echo "Système non pris en charge par ce script (utilisez install.bat sous Windows)."; exit 1 ;;
  esac
}

say "FFmpeg"
if command -v ffmpeg >/dev/null; then
  ffmpeg -hide_banner -version | head -1
else
  install_ffmpeg
fi

say "uv (gestionnaire Python)"
if ! command -v uv >/dev/null; then
  if [ "$(uname -s)" = Darwin ] && command -v brew >/dev/null; then
    brew install uv
  else
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi
fi
uv --version

say "Dépendances Python"
uv sync --no-dev

say "Accélération matérielle détectée"
uv run --no-dev video-converter encoders

chmod +x start.sh start.command 2>/dev/null || true
say "Installation terminée"
echo "Lancez l'application avec : ./start.sh   (sur macOS, double-cliquez aussi sur start.command)"
