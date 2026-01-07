@echo off
echo ========================================
echo REPRISE GENERATION RESUMES
echo ========================================
echo.

cd /d "%~dp0"

echo Chunks deja traites:
python -c "import json; p=json.load(open('summary_generation_progress.json')); print(f'  -> {p[\"total_processed\"]} chunks traites')" 2>nul || echo   -> Aucun chunk traite

echo.
echo Lancement de la generation...
echo (Ctrl+C pour arreter - progression sauvegardee)
echo.

python ..\..\utils\generate_all_summaries.py

pause
