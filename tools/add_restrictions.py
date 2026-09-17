#!/usr/bin/env python3
"""
Ajoute la couche des restrictions de stationnement au bundle Halifax.

    python tools/add_restrictions.py --src data --bundle data/halifax_bundle.json

Source : Commuter_Permit_Parking_Streets*.geojson — 321 troncons ou le
stationnement exige un permis. Sans permis, s'y garer expose a une amende.

CE QUE CETTE COUCHE DIT, ET CE QU'ELLE NE DIT PAS
-------------------------------------------------
Elle dit : ce troncon est soumis a un permis de stationnement.
Elle ne dit PAS a quelles heures. HRM ne publie aucune plage horaire dans ce
jeu de donnees. Une rue a permis peut etre libre le dimanche ou la nuit.

Elle ne recense pas non plus les interdictions ponctuelles : bornes
d'incendie, entrees charretieres, arrets d'autobus, zones de livraison.
Aucun jeu de donnees municipal ne les publie. L'absence de trace rouge ne
signifie donc jamais que le stationnement est autorise.

Le panneau sur place fait foi. L'interface doit le dire.
"""

from __future__ import annotations

import argparse
import glob
import json
import os


def read_features(src: str, pattern: str) -> list[dict]:
    hits = sorted(glob.glob(os.path.join(src, pattern)))
    if not hits:
        return []
    with open(hits[0], encoding="utf-8-sig") as fh:
        return json.load(fh).get("features", [])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data")
    ap.add_argument("--bundle", default="data/halifax_bundle.json")
    args = ap.parse_args()

    features = read_features(args.src, "Commuter_Permit_Parking_Streets*.geojson")
    if not features:
        raise SystemExit("Commuter_Permit_Parking_Streets*.geojson introuvable")

    restrictions = []
    for f in features:
        geom = f.get("geometry")
        if not geom or geom.get("type") != "LineString":
            continue
        p = f["properties"]
        restrictions.append(
            {
                "id": p.get("PPID") or f"PP-{p.get('OBJECTID')}",
                # COMMUTER = Y : un permis de navetteur y est accepte.
                # COMMUTER = N : permis de residant seulement, plus restrictif.
                "commuterAllowed": (p.get("COMMUTER") or "N").upper() == "Y",
                # GeoJSON ordonne [lon, lat] ; on stocke [lat, lon] pour Dart.
                "points": [[c[1], c[0]] for c in geom["coordinates"]],
            }
        )

    with open(args.bundle, encoding="utf-8") as fh:
        bundle = json.load(fh)

    bundle["restrictions"] = restrictions
    bundle["meta"]["restriction_source"] = "HRM Commuter Permit Parking Streets"
    bundle["meta"]["restriction_hours_published"] = "false"

    with open(args.bundle, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, separators=(",", ":"))

    commuter = sum(1 for r in restrictions if r["commuterAllowed"])
    print(f"troncons a permis ajoutes : {len(restrictions)}")
    print(f"  permis de navetteur accepte : {commuter}")
    print(f"  permis de residant seulement : {len(restrictions) - commuter}")
    print(f"bundle : {os.path.getsize(args.bundle)/1024:.0f} Ko")


if __name__ == "__main__":
    main()
