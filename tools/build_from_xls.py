#!/usr/bin/env python3
"""
ZoPark — Construction du jeu de donnees a partir des trois exports .xls.

    python tools/build_from_xls.py --src data --out data

Entrees (les seules necessaires) :
    accessible_parking__1_.xls   306 places reservees, coordonnees WGS84
    pay_stations.xls             176 bornes, tarif horaire et duree maximale
    pay_zones__2_.xls             10 libelles de zones tarifaires

Sortie :
    halifax_bundle.json          places + grille d'occupation 7 jours x 24 h

NATURE DU MODELE D'OCCUPATION — a lire avant de presenter le projet
-------------------------------------------------------------------
Ce n'est PAS un modele appris. Aucun des fichiers sources ne contient
d'occupation mesuree : il n'existe donc aucune etiquette a apprendre, et
tout apprentissage supervise est impossible.

C'est un modele PARAMETRIQUE : une fonction ecrite a la main, dont chaque
terme est justifie ci-dessous. Deux categories de termes :

  1. Fondes sur les donnees. Le terme tarifaire vient de rate_per_hour, fixe
     par HRM. Une municipalite tarife plus cher la ou la pression est forte :
     c'est un signal de demande produit par l'autorite qui connait le terrain.
     Le terme de duree vient de max_hours et time_limit.

  2. Hypotheses. Le cycle horaire et l'effet week-end sont des regularites
     de comportement urbain admises, mais non mesurees ici. Ce sont des
     hypotheses assumees, pas des resultats.

Pour transformer ceci en vrai modele appris, il faut des mesures
d'occupation. Deux voies : les capteurs de Melbourne (donnees ouvertes), ou
un comptage manuel sur quelques rues d'Halifax.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone

import pandas as pd

SCHEMA_VERSION = 9
MODEL_VERSION = "parametric-v2"

# Grand Parade, centre-ville — reference de distance
DOWNTOWN_LAT, DOWNTOWN_LON = 44.6488, -63.5752

# Tarif de reference. Les zones au-dessus sont jugees plus disputees par HRM.
BASE_RATE = 2.0

TIME_LIMIT_TO_HOURS = {"MIN30": 0.5, "HR1": 1.0, "HR2": 2.0, "HR3": 3.0}
HOURS_TO_RULE = {0.5: "min30", 1.0: "hour1", 2.0: "hour2", 3.0: "hour3"}


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p = math.pi / 180.0
    a = (
        math.sin((lat2 - lat1) * p / 2) ** 2
        + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    )
    return 2 * 6371000.0 * math.asin(math.sqrt(a))


def title(value) -> str:
    return " ".join(w.capitalize() for w in str(value or "").strip().split())


# --------------------------------------------------------------------------
# Lecture
# --------------------------------------------------------------------------
def load_accessible(path: str) -> list[dict]:
    df = pd.read_excel(path)
    out = []
    for r in df.itertuples():
        hours = TIME_LIMIT_TO_HOURS.get(str(r.time_limit).strip().upper())
        out.append(
            {
                "id": f"AP-{r.spot_id}",
                "kind": "accessible",
                "street": title(r.street),
                "fromStreet": title(r.from_street) or None,
                "toStreet": title(r.to_street) or None,
                "lat": round(float(r.lat), 7),
                "lon": round(float(r.lon), 7),
                "capacity": max(1, int(r.num_spots)),
                "status": "installed" if str(r.status).upper() == "INS" else "pending",
                "direction": str(r.direction).strip().upper() or None,
                "payZone": None,
                "ratePerHour": None,
                "maxHours": hours,
                "permitRequired": bool(r.permit_required),
                "fineIfNoPermit": int(r.fine_if_no_permit),
                "demandFactor": 1.0,
                "rule": {
                    "ruleType": HOURS_TO_RULE.get(hours, "unknown"),
                    "maxMinutes": int(hours * 60) if hours else None,
                },
                "source": "HRM Accessible Parking Spots",
            }
        )
    print(f"  places accessibles : {len(out)}")
    return out


def load_pay_stations(path: str) -> list[dict]:
    df = pd.read_excel(path)
    out = []
    for r in df.itertuples():
        hours = float(r.max_hours)
        rate = float(r.rate_per_hour)
        out.append(
            {
                "id": f"PS-{r.station_id}",
                "kind": "paid",
                "street": title(r.specific_location),
                "fromStreet": None,
                "toStreet": None,
                "lat": round(float(r.lat), 7),
                "lon": round(float(r.lon), 7),
                # Estimation : HRM ne publie pas le nombre de places par borne.
                # Signale comme estime dans meta et dans l'interface.
                "capacity": 8,
                "status": "installed",
                "direction": None,
                "payZone": str(r.pay_zone).strip(),
                "ratePerHour": rate,
                "maxHours": hours,
                "permitRequired": False,
                "fineIfNoPermit": None,
                # Signal de demande issu de la tarification municipale.
                "demandFactor": round(rate / BASE_RATE, 3),
                "rule": {
                    "ruleType": HOURS_TO_RULE.get(hours, "unknown"),
                    "maxMinutes": int(hours * 60),
                },
                "source": "HRM Parking Pay Stations",
            }
        )
    print(f"  bornes de paiement : {len(out)}")
    return out


def load_zones(path: str) -> list[dict]:
    df = pd.read_excel(path)
    col = "Parking Pay Zone"
    out = []
    for value in df[col]:
        label = str(value).strip()          # "ZONE D"
        code = label.replace("ZONE", "").strip().upper()
        out.append({"code": code, "label": label.title()})
    print(f"  zones tarifaires   : {len(out)}")
    return out


# --------------------------------------------------------------------------
# Modele parametrique d'occupation
# --------------------------------------------------------------------------
def occupancy(spot: dict, isoweekday: int, hour: int, neighbours: int) -> float:
    """P(place occupee), dans [0.02, 0.98].

    Chaque terme est annote FONDE (issu des donnees) ou HYPOTHESE.
    Remplacable en bloc par un modele appris : meme signature, memes bornes.
    """
    z = -0.90

    # HYPOTHESE — cycle journalier : creux nocturne, pointes midi et fin
    # d'apres-midi. Regularite admise du comportement urbain, non mesuree ici.
    z += 1.50 * math.exp(-((hour - 11.5) ** 2) / 12.0)
    z += 1.20 * math.exp(-((hour - 17.0) ** 2) / 8.0)
    if hour < 7 or hour >= 22:
        z -= 1.60

    # HYPOTHESE — la demande de fin de semaine est plus tardive et plus faible.
    if isoweekday >= 6:
        z -= 0.50
        if 19 <= hour <= 23:
            z += 0.55

    # FONDE — tarif horaire HRM. 2 $/h = reference, 3 $/h = secteur que la
    # ville juge 50 % plus dispute. Seul signal spatial disponible.
    z += 1.30 * (spot["demandFactor"] - 1.0)

    # FONDE — duree maximale courte = rotation elevee = plus de chances
    # qu'une place se libere. max_hours et time_limit viennent des fichiers.
    hours = spot.get("maxHours")
    if hours:
        z -= 0.22 * (3.0 - min(hours, 3.0))

    # FONDE — distance au centre-ville, calculee sur les coordonnees reelles.
    z += 1.00 * math.exp(-spot["_dist_downtown_m"] / 1400.0)

    # FONDE — densite locale de places, comptee sur les coordonnees reelles.
    z += 0.028 * min(neighbours, 30)

    # HYPOTHESE — les places reservees tournent moins que les places tarifees.
    z += 0.30 if spot["kind"] == "paid" else -0.25

    # FONDE — une place large a plus de chances d'offrir un espace libre.
    z -= 0.06 * min(spot["capacity"], 8)

    p = 1.0 / (1.0 + math.exp(-z))
    return round(min(0.98, max(0.02, p)), 4)


def build_grid(spots: list[dict]) -> dict:
    density = {}
    for a in spots:
        density[a["id"]] = sum(
            1
            for b in spots
            if a["id"] != b["id"]
            and haversine_m(a["lat"], a["lon"], b["lat"], b["lon"]) <= 150
        )

    grid = {}
    for spot in spots:
        days = []
        for isoweekday in range(1, 8):
            days.append(
                [occupancy(spot, isoweekday, h, density[spot["id"]]) for h in range(24)]
            )
        grid[spot["id"]] = days
    return grid


# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data")
    ap.add_argument("--out", default="data")
    args = ap.parse_args()

    print("Lecture :")
    spots = load_accessible(os.path.join(args.src, "accessible_parking__1_.xls"))
    spots += load_pay_stations(os.path.join(args.src, "pay_stations.xls"))
    zones = load_zones(os.path.join(args.src, "pay_zones__2_.xls"))

    for s in spots:
        s["_dist_downtown_m"] = round(
            haversine_m(s["lat"], s["lon"], DOWNTOWN_LAT, DOWNTOWN_LON), 1
        )

    outside = [
        s["id"] for s in spots
        if not (44.4 <= s["lat"] <= 45.0 and -64.2 <= s["lon"] <= -63.2)
    ]
    if outside:
        print(f"  ATTENTION {len(outside)} places hors des limites d'Halifax")

    print("\nGeneration de la couche d'occupation...")
    grid = build_grid(spots)
    installed = [s for s in spots if s["status"] == "installed"]
    print(f"  {len(spots) * 7 * 24} valeurs ({len(spots)} places x 7 j x 24 h)")

    for s in spots:
        s.pop("_dist_downtown_m", None)

    payload = {
        "meta": {
            "schema_version": str(SCHEMA_VERSION),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model_version": MODEL_VERSION,
            "model_is_learned": "false",
            "occupancy_is_ground_truth": "false",
            "model_note": "Modele parametrique. Termes tarifaires, de duree, "
                          "de distance et de densite fondes sur les donnees ; "
                          "cycle horaire et effet week-end poses en hypothese.",
            "capacity_is_estimated": "true pour kind=paid",
            "attribution": "Halifax Regional Municipality",
            "rate_base": str(BASE_RATE),
            "count_spots": str(len(spots)),
            "count_installed": str(len(installed)),
        },
        "payZones": zones,
        "spots": spots,
        "occupancy": grid,
    }

    out_path = os.path.join(args.out, "halifax_bundle.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    print(f"\nEcrit : {out_path} ({os.path.getsize(out_path)/1024:.0f} Ko)")
    print(f"  {len(installed)} places installees seront affichables")


if __name__ == "__main__":
    main()
