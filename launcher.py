#!/usr/bin/env python3
"""
ZoPark — lanceur tout-en-un (v2, adapte a la structure du projet :
app/, backend/, data/, tools/, avec ce fichier a la RACINE).

Un seul processus fait tout :
  1. demarre l'API FastAPI (backend/zopark_api.py) sur http://127.0.0.1:8000 ;
  2. sert le build web Flutter (webapp/) sur la MEME origine — pas de CORS,
     et le baseUrl code en dur dans routing_api.dart reste valable ;
  3. ouvre le navigateur une fois le serveur pret.

Empaquete par PyInstaller (zopark.spec), il devient un unique ZoPark.exe.

Notes :
  - sys._MEIPASS : dossier temporaire (LECTURE SEULE) ou PyInstaller extrait
    les donnees embarquees (webapp/, halifax_bundle.json, graphe, modele).
  - Les caches (halifax_graph.graphml) vont dans un dossier INSCRIPTIBLE :
    a cote de l'exe si possible, sinon %LOCALAPPDATA%\\ZoPark.
  - multiprocessing.freeze_support() est OBLIGATOIRE : joblib/loky peut
    relancer l'executable pour ses workers.
"""

from __future__ import annotations

import multiprocessing
import os
import shutil
import socket
import sys
import threading
import time
import webbrowser

# Port fixe : routing_api.dart appelle http://127.0.0.1:8000 en dur.
PORT = 8000


def resource_dir() -> str:
    """Dossier des ressources embarquees (lecture seule sous PyInstaller)."""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def writable_dir() -> str:
    if getattr(sys, "frozen", False):
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    probe = os.path.join(base, ".zopark_probe")
    try:
        with open(probe, "w"):
            pass
        os.remove(probe)
        return base
    except OSError:
        alt = os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "ZoPark"
        )
        os.makedirs(alt, exist_ok=True)
        return alt


def first_existing(*paths: str) -> str | None:
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def open_browser_when_ready() -> None:
    import urllib.request

    url = f"http://127.0.0.1:{PORT}/"
    for _ in range(180):
        try:
            urllib.request.urlopen(url, timeout=1)
            break
        except Exception:
            time.sleep(1)
    webbrowser.open(url)


def main() -> None:
    res = resource_dir()
    work = writable_dir()
    os.chdir(work)  # GRAPH_CACHE ("halifax_graph.graphml") s'ecrira ici

    # En mode developpement (python launcher.py depuis la racine du projet),
    # zopark_api.py et geo.py vivent dans backend/. Dans l'exe, PyInstaller
    # les a deja collectes comme modules — ce chemin n'existe alors pas.
    backend = os.path.join(res, "backend")
    if os.path.isdir(backend):
        sys.path.insert(0, backend)

    print("=" * 60)
    print("  ZoPark — Halifax")
    print(f"  ressources : {res}")
    print(f"  caches     : {work}")
    print("=" * 60)

    # Graphe routier pre-telecharge embarque -> copie vers le dossier
    # inscriptible : le premier lancement fonctionne HORS LIGNE.
    bundled_graph = first_existing(
        os.path.join(res, "halifax_graph.graphml"),
        os.path.join(res, "backend", "halifax_graph.graphml"),
    )
    local_graph = os.path.join(work, "halifax_graph.graphml")
    if bundled_graph and not os.path.exists(local_graph):
        print("[PREP] copie du graphe routier embarque...")
        shutil.copy2(bundled_graph, local_graph)

    # Donnees : dans l'exe elles sont a la racine de _MEIPASS ; en mode
    # developpement elles sont dans data/ et backend/. On couvre les deux.
    bundle = first_existing(
        os.path.join(res, "halifax_bundle.json"),
        os.path.join(res, "data", "halifax_bundle.json"),
    )
    if bundle:
        os.environ.setdefault("ZOPARK_BUNDLE", bundle)
    else:
        print("[PREP] ATTENTION : halifax_bundle.json introuvable.")

    for env, name in (
        ("ZOPARK_MODEL", "zopark_melbourne_rf.pkl"),
        ("ZOPARK_METRICS", "zopark_melbourne_metrics.json"),
    ):
        p = first_existing(
            os.path.join(res, name),
            os.path.join(res, "backend", name),
        )
        if p:
            os.environ.setdefault(env, p)

    if not port_free(PORT):
        print(f"\nERREUR : le port {PORT} est deja occupe.")
        print("Ferme l'autre instance de ZoPark (ou le serveur uvicorn) et relance.")
        input("\nAppuie sur Entree pour quitter...")
        sys.exit(1)

    import zopark_api  # importe geo.py au passage

    # Filet de securite : zopark_api.py utilise datetime.now() sans jamais
    # importer datetime. On injecte le symbole si le fichier n'est pas corrige.
    if not hasattr(zopark_api, "datetime"):
        from datetime import datetime as _dt

        zopark_api.datetime = _dt
        print("[FIX] symbole datetime injecte dans zopark_api "
              "(ajoute `from datetime import datetime` a backend/zopark_api.py).")

    # Sert le build web Flutter sur la meme origine que l'API. Monte a la
    # racine EN DERNIER : /health, /availability et /route gardent la priorite.
    webapp = first_existing(
        os.path.join(res, "webapp"),
        os.path.join(res, "app", "build", "web"),
    )
    if webapp and os.path.isdir(webapp):
        from fastapi.staticfiles import StaticFiles

        zopark_api.app.mount(
            "/", StaticFiles(directory=webapp, html=True), name="webapp"
        )
        print(f"[WEB] application servie depuis {webapp}")
    else:
        print("[WEB] build web introuvable — API seule (pas d'interface).")

    threading.Thread(target=open_browser_when_ready, daemon=True).start()

    print(f"\nOuverture de http://127.0.0.1:{PORT}/ dans le navigateur...")
    print("Laisse cette fenetre ouverte pendant la demonstration.")
    print("Ferme-la (ou Ctrl+C) pour arreter ZoPark.\n")

    import uvicorn

    uvicorn.run(zopark_api.app, host="127.0.0.1", port=PORT, log_level="info")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
