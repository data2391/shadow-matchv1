#!/usr/bin/env bash
# Lance l'API OMNI-RECO v2.1 depuis le venv Linux/macOS
# Accès : http://localhost:8000  |  Swagger : http://localhost:8000/docs

if [ ! -d ".venv" ]; then
    echo "[ERREUR] Venv absent. Lance ./setup_venv.sh d'abord."
    exit 1
fi

source .venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
