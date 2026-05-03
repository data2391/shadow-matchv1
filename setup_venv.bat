@echo off
REM ================================================================
REM  SHADOW-MATCH v2 + OMNI-RECO v2.1 — Setup venv Windows
REM  Usage : double-clic sur setup_venv.bat
REM  Prérequis : Python 3.10 installé et dans le PATH
REM ================================================================

SETLOCAL

set VENV_DIR=.venv
set PYTHON_MIN=3.10

echo.
echo  ============================================
echo   SHADOW-MATCH + OMNI-RECO v2.1  SETUP
echo  ============================================
echo.

REM — Vérification Python 3.10 —
python --version 2>&1 | findstr /C:"3.10" /C:"3.11" >nul
if errorlevel 1 (
    echo [ERREUR] Python 3.10 ou 3.11 requis pour mediapipe.
    echo          Télécharge : https://www.python.org/downloads/release/python-31011/
    pause
    exit /b 1
)

REM — Création du venv si absent —
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [1/4] Création du venv Python dans %VENV_DIR%...
    python -m venv %VENV_DIR%
    if errorlevel 1 (
        echo [ERREUR] Impossible de créer le venv.
        pause
        exit /b 1
    )
) else (
    echo [1/4] Venv déjà existant — réutilisation.
)

REM — Mise à jour pip —
echo [2/4] Mise à jour pip...
call %VENV_DIR%\Scripts\activate.bat
python -m pip install --upgrade pip setuptools wheel --quiet

REM — Installation des dépendances —
echo [3/4] Installation requirements.txt dans le venv...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERREUR] pip install a échoué. Vérifie ta connexion ou les versions.
    pause
    exit /b 1
)

REM — Playwright (navigateurs pour scraping Yandex) —
echo [4/4] Installation des navigateurs Playwright...
playwright install chromium

echo.
echo  ============================================
echo   SETUP TERMINé avec succès !
echo.
echo   Pour lancer shadow-match :
echo     run.bat --image photo.jpg
echo     run.bat --web
echo.
echo   Pour lancer l'API OMNI-RECO v2 :
echo     run_api.bat
echo  ============================================
echo.
pause
