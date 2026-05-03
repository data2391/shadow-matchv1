@echo off
chcp 65001 >nul
SETLOCAL ENABLEDELAYEDEXPANSION

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║   SHADOW-MATCH + OMNI-RECO v2.1  —  SETUP  ║
echo  ╚══════════════════════════════════════════════╝
echo.

:: ════════════════════════════════════════════════════════════
:: ETAPE 1 — Chercher Python 3.10
:: ════════════════════════════════════════════════════════════
echo [1/5] Recherche de Python 3.10...

set PYTHON_BIN=

:: Essai py launcher (méthode la plus fiable sous Windows)
py -3.10 --version >nul 2>&1
if not errorlevel 1 (
    set PYTHON_BIN=py -3.10
    echo       Trouvé via py launcher.
    goto :found_python
)

:: Essai python3.10 direct
python3.10 --version >nul 2>&1
if not errorlevel 1 (
    set PYTHON_BIN=python3.10
    echo       Trouvé : python3.10
    goto :found_python
)

:: Python 3.10 introuvable → installation via winget
echo       Python 3.10 introuvable. Installation via winget...
winget install -e --id Python.Python.3.10 --silent --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo.
    echo  [ERREUR] winget a échoué.
    echo  Installe manuellement : https://www.python.org/downloads/release/python-31011/
    echo  Puis relance ce fichier.
    pause
    exit /b 1
)
:: Rafraîchir le PATH après install
refreshenv >nul 2>&1
py -3.10 --version >nul 2>&1
if not errorlevel 1 (
    set PYTHON_BIN=py -3.10
    echo       Python 3.10 installé avec succès.
    goto :found_python
)
echo  [ERREUR] Impossible de trouver Python 3.10 même après installation.
echo  Redémarre l'invite de commandes et relance ce fichier.
pause
exit /b 1

:found_python
for /f "tokens=*" %%V in ('!PYTHON_BIN! --version 2^>^&1') do echo       Version : %%V

:: ════════════════════════════════════════════════════════════
:: ETAPE 2 — Créer le venv
:: ════════════════════════════════════════════════════════════
echo.
echo [2/5] Création du venv (.venv)...
if exist ".venv\Scripts\activate.bat" (
    echo       Venv existant — réutilisation.
) else (
    !PYTHON_BIN! -m venv .venv
    if errorlevel 1 (
        echo  [ERREUR] Impossible de créer le venv.
        pause & exit /b 1
    )
    echo       Venv créé.
)

:: ════════════════════════════════════════════════════════════
:: ETAPE 3 — Installer les dépendances
:: ════════════════════════════════════════════════════════════
echo.
echo [3/5] Installation des dépendances (requirements.txt)...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip setuptools wheel -q
pip install -r requirements.txt
if errorlevel 1 (
    echo  [ERREUR] pip install échoué. Vérifie ta connexion.
    pause & exit /b 1
)
echo       Dépendances installées.

:: Playwright — navigateurs
echo.
echo [4/5] Installation du navigateur Playwright (Chromium)...
playwright install chromium
echo       Chromium installé.

:: ════════════════════════════════════════════════════════════
:: ETAPE 4 — Test rapide
:: ════════════════════════════════════════════════════════════
echo.
echo [5/5] Test d'import des modules clés...
python -c "import cv2, numpy, insightface, mediapipe, fastapi; print('  OK — tous les modules importés.')"
if errorlevel 1 (
    echo  [AVERTISSEMENT] Certains modules n'ont pas pu être importés.
    echo  Vérifie les erreurs ci-dessus.
)

:: ════════════════════════════════════════════════════════════
:: ETAPE 5 — Générer lancer-cli.bat et lancer-gui.bat
:: ════════════════════════════════════════════════════════════
echo.
echo  Génération des raccourcis de lancement...

(
echo @echo off
echo chcp 65001 ^>nul
echo call "%~dp0.venv\Scripts\activate.bat"
echo python "%~dp0main.py" %%*
) > lancer-cli.bat

(
echo @echo off
echo chcp 65001 ^>nul
echo call "%~dp0.venv\Scripts\activate.bat"
echo start http://localhost:8080
echo python "%~dp0main.py" --web
) > lancer-gui.bat

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║   SETUP TERMINÉ — prêt à utiliser !         ║
echo  ║                                              ║
echo  ║   lancer-cli.bat --image photo.jpg           ║
echo  ║   lancer-cli.bat --help                      ║
echo  ║   lancer-gui.bat  → dashboard web            ║
echo  ╚══════════════════════════════════════════════╝
echo.
pause
