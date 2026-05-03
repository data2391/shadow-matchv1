#!/usr/bin/env bash
# ================================================================
#  SHADOW-MATCH v2 + OMNI-RECO v2.1 — Setup venv Linux/macOS
#  Usage : chmod +x setup_venv.sh && ./setup_venv.sh
#  Prérequis : Python 3.10 (ou 3.11) installé
# ================================================================

set -e

VENV_DIR=".venv"

echo
echo " ============================================"
echo "  SHADOW-MATCH + OMNI-RECO v2.1  SETUP"
echo " ============================================"
echo

# — Vérification Python —
PYTHON_BIN="python3.10"
if ! command -v "$PYTHON_BIN" &>/dev/null; then
    PYTHON_BIN="python3.11"
fi
if ! command -v "$PYTHON_BIN" &>/dev/null; then
    PYTHON_BIN="python3"
fi

PY_VER=$("$PYTHON_BIN" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "[INFO] Python détecté : $PYTHON_BIN ($PY_VER)"

if [[ "$PY_VER" != "3.10" && "$PY_VER" != "3.11" ]]; then
    echo "[AVERTISSEMENT] mediapipe==0.10.9 nécessite Python 3.10 ou 3.11."
    echo "                Ton Python est $PY_VER — risque d'incompatibilité."
    read -rp "Continuer quand même ? [o/N] " reply
    [[ "$reply" =~ ^[oOyY]$ ]] || exit 1
fi

# — Création du venv —
if [ ! -d "$VENV_DIR" ]; then
    echo "[1/4] Création du venv dans $VENV_DIR..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
else
    echo "[1/4] Venv déjà existant — réutilisation."
fi

# — Activation —
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# — Pip —
echo "[2/4] Mise à jour pip..."
pip install --upgrade pip setuptools wheel -q

# — Dépendances —
echo "[3/4] Installation requirements.txt..."
pip install -r requirements.txt

# — Playwright —
echo "[4/4] Installation navigateurs Playwright..."
playwright install chromium

echo
echo " ============================================"
echo "  SETUP TERMINÉ avec succès !"
echo
echo "  Pour activer le venv manuellement :"
echo "    source .venv/bin/activate"
echo
echo "  Pour lancer shadow-match :"
echo "    ./run.sh --image photo.jpg"
echo "    ./run.sh --web"
echo
echo "  Pour lancer l'API OMNI-RECO v2 :"
echo "    ./run_api.sh"
echo " ============================================"
echo
