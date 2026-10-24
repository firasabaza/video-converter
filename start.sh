#!/usr/bin/env bash
# Lance le convertisseur vidéo et ouvre l'interface dans le navigateur.
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
exec uv run --no-dev video-converter "$@"
