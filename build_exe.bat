@echo off
setlocal EnableDelayedExpansion
REM ==========================================================================
REM  ZoPark - construction de ZoPark.exe (v2, structure app/backend/data)
REM
REM  A PLACER ET LANCER A LA RACINE DU PROJET, a cote de app\, backend\, data\
REM
REM      <racine>\
REM          build_exe.bat  launcher.py  zopark.spec  warmup.py   <- le kit
REM          backend\zopark_api.py, geo.py, requirements.txt
REM          data\halifax_bundle.json
REM          app\pubspec.yaml (projet Flutter)
REM
REM  Resultat : dist\ZoPark.exe
REM ==========================================================================

echo.
echo === [0/5] Verification de la structure ==================================
if not exist backend\zopark_api.py (
    echo ERREUR : backend\zopark_api.py introuvable. Ce script doit etre
    echo lance depuis la RACINE du projet, a cote de app\, backend\, data\.
    goto :fail
)
if not exist backend\geo.py (
    echo ERREUR : backend\geo.py introuvable.
    goto :fail
)
if not exist data\halifax_bundle.json (
    echo ERREUR : data\halifax_bundle.json introuvable.
    echo Genere-le avec : python tools\build_from_xls.py --src data --out data
    goto :fail
)
echo Structure OK.

echo.
echo === [1/5] Application web Flutter =======================================
if exist app\pubspec.yaml (
    where flutter >nul 2>nul
    if errorlevel 1 (
        echo ERREUR : flutter n'est pas dans le PATH.
        goto :fail
    )
    pushd app
    call flutter build web --release
    if errorlevel 1 ( popd & goto :fail )
    popd
    robocopy app\build\web webapp /MIR >nul
    if errorlevel 8 goto :fail
    echo Build Flutter copie dans webapp\
) else (
    echo Pas de app\pubspec.yaml : on utilise webapp\ tel quel.
)
if not exist webapp\index.html (
    echo ERREUR : webapp\index.html introuvable.
    goto :fail
)

echo.
echo === [2/5] Modele appris (optionnel) =====================================
if exist backend\zopark_melbourne_rf.pkl (
    echo Modele appris trouve dans backend\ : il sera embarque.
) else if exist zopark_melbourne_rf.pkl (
    echo Modele appris trouve a la racine : il sera embarque.
) else (
    echo Pas de zopark_melbourne_rf.pkl : la grille parametrique du bundle servira.
)

echo.
echo === [3/5] Environnement Python ==========================================
if not exist .venv (
    python -m venv .venv
    if errorlevel 1 goto :fail
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r backend\requirements.txt pyinstaller
if errorlevel 1 goto :fail

echo.
echo === [4/5] Graphe routier (pour un exe autonome hors ligne) ==============
python warmup.py
if errorlevel 1 goto :fail

echo.
echo === [5/5] PyInstaller ====================================================
pyinstaller --clean --noconfirm zopark.spec
if errorlevel 1 goto :fail

echo.
echo ==========================================================================
echo  TERMINE : dist\ZoPark.exe
echo  Premier double-clic : 15 a 40 s d'extraction avant la console (onefile).
echo  SmartScreen peut afficher un avertissement : "Informations
echo  complementaires" puis "Executer quand meme" (exe non signe, normal).
echo ==========================================================================
exit /b 0

:fail
echo.
echo *** ECHEC — voir le message ci-dessus. ***
exit /b 1
