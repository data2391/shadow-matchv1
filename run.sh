#!/usr/bin/env bash
# Lance shadow-match depuis le venv Linux/macOS
# Usage : ./run.sh --image photo.jpg
#         ./run.sh --web

if [ ! -d ".venv" ]; then
    echo "[ERREUR] Venv absent. Lance ./setup_venv.sh d'abord."
    exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python main.py "$@"
