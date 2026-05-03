@echo off
REM Lance shadow-match depuis le venv Windows
REM Usage : run.bat --image photo.jpg
REM         run.bat --web

if not exist ".venv\Scripts\activate.bat" (
    echo [ERREUR] Venv absent. Lance setup_venv.bat d'abord.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
python main.py %*
