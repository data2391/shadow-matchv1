@echo off
REM Lance l'API OMNI-RECO v2.1 depuis le venv Windows
REM Accès : http://localhost:8000  |  Swagger : http://localhost:8000/docs

if not exist ".venv\Scripts\activate.bat" (
    echo [ERREUR] Venv absent. Lance setup_venv.bat d'abord.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
