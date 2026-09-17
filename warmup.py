#!/usr/bin/env python3
"""
Pre-telecharge le graphe routier d'Halifax AVANT l'empaquetage.

Sans cette etape, ZoPark.exe telechargerait le reseau via OSMnx au premier
lancement : plusieurs minutes, et Internet obligatoire le jour de la
soutenance. Avec halifax_graph.graphml embarque, le premier lancement est
immediat et hors ligne.

A lancer depuis la RACINE du projet (build_exe.bat s'en charge).
Les constantes DOIVENT rester identiques a celles de backend/zopark_api.py.
"""

from __future__ import annotations

import os
import sys

# = CENTER et GRAPH_RADIUS_M de backend/zopark_api.py — ne pas diverger.
CENTER = (44.6476, -63.5728)
GRAPH_RADIUS_M = 6000
GRAPH_CACHE = "halifax_graph.graphml"
API_FILE = os.path.join("backend", "zopark_api.py")


def check_constants() -> None:
    """Alerte si zopark_api.py a change de centre ou de rayon."""
    try:
        with open(API_FILE, encoding="utf-8") as fh:
            src = fh.read()
    except OSError:
        print(f"ATTENTION : {API_FILE} introuvable, verification sautee.")
        return
    if "44.6476" not in src or "-63.5728" not in src:
        print("ATTENTION : CENTER de warmup.py ne correspond plus a zopark_api.py")
    if f"GRAPH_RADIUS_M = {GRAPH_RADIUS_M}" not in src:
        print("ATTENTION : GRAPH_RADIUS_M de warmup.py ne correspond plus "
              "a zopark_api.py")


def main() -> None:
    check_constants()

    if os.path.exists(GRAPH_CACHE):
        size = os.path.getsize(GRAPH_CACHE) / 1024 / 1024
        print(f"Graphe deja present : {GRAPH_CACHE} ({size:.1f} Mo) — rien a faire.")
        return

    print("Telechargement du reseau routier d'Halifax via OSMnx...")
    print("(une seule fois ; quelques minutes selon la connexion)")
    import osmnx as ox

    graph = ox.graph_from_point(CENTER, dist=GRAPH_RADIUS_M, network_type="drive")
    ox.save_graphml(graph, GRAPH_CACHE)
    size = os.path.getsize(GRAPH_CACHE) / 1024 / 1024
    print(
        f"OK : {GRAPH_CACHE} ({size:.1f} Mo, "
        f"{graph.number_of_nodes()} intersections, {graph.number_of_edges()} rues)"
    )


if __name__ == "__main__":
    sys.exit(main())
