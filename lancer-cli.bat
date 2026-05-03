@echo off
chcp 65001 >nul
if not exist ".venv\Scripts\activate.bat" (
    echo  [ERREUR] Venv absent — lance installer-shadow-match.bat d'abord.
    pause & exit /b 1
)
call .venv\Scripts\activate.bat
python main.py %*
