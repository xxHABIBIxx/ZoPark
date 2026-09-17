# -*- mode: python ; coding: utf-8 -*-
"""
Spec PyInstaller de ZoPark — v2, adaptee a la structure du projet :

    <racine>\
        launcher.py  zopark.spec  warmup.py  build_exe.bat   <- le kit
        backend\   zopark_api.py, geo.py, requirements.txt,
                   zopark_melbourne_rf.pkl (optionnel)
        data\      halifax_bundle.json
        app\       projet Flutter
        webapp\    build web copie par build_exe.bat
        halifax_graph.graphml   (cree par warmup.py)

Mode ONEFILE : un seul dist\ZoPark.exe. Windows extrait ~400 Mo a chaque
lancement -> 15 a 40 s avant la console. Variante ONEDIR en fin de fichier.
"""

import os

from PyInstaller.utils.hooks import collect_all

datas = [
    ("webapp", "webapp"),
    (os.path.join("data", "halifax_bundle.json"), "."),
]

# Fichiers optionnels : cherches a la racine ET dans backend\.
for name in (
    "halifax_graph.graphml",
    "zopark_melbourne_rf.pkl",
    "zopark_melbourne_metrics.json",
):
    src = next(
        (p for p in (name, os.path.join("backend", name)) if os.path.exists(p)),
        None,
    )
    if src:
        datas.append((src, "."))

binaries = []
hiddenimports = ["zopark_api", "geo", "joblib"]

# La pile geospatiale embarque des donnees hors Python (grilles pyproj,
# DLL GEOS de shapely...) : collect_all est la maniere sure de tout avoir.
for pkg in ("osmnx", "sklearn", "pyproj", "shapely", "networkx"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# uvicorn charge ses backends dynamiquement : PyInstaller ne les voit pas.
hiddenimports += [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
]

a = Analysis(
    ["launcher.py"],
    pathex=[".", "backend"],  # <- c'est ici que zopark_api.py et geo.py sont trouves
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

# ----- ONEFILE : un seul ZoPark.exe ---------------------------------------
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="ZoPark",
    console=True,   # garder la console : les logs [INIT] rassurent en demo
    upx=False,      # UPX + DLL scientifiques = faux positifs antivirus
)

# ----- Variante ONEDIR (demarrage instantane, dossier au lieu d'un exe) ---
# Commenter le bloc EXE ci-dessus, decommenter ci-dessous, relancer
# pyinstaller. Resultat : dist\ZoPark\ (lancer ZoPark.exe dedans).
#
# exe = EXE(
#     pyz,
#     a.scripts,
#     name="ZoPark",
#     exclude_binaries=True,
#     console=True,
#     upx=False,
# )
# coll = COLLECT(exe, a.binaries, a.datas, name="ZoPark", upx=False)
