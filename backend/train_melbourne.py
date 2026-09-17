#!/usr/bin/env python3
"""
Entraine le modele Melbourne et l'exporte pour l'API ZoPark.

Le pipeline de reference (zopark_melbourne_pipeline.py) n'est PAS modifie :
ce script l'importe et reutilise ses fonctions telles quelles. Il ajoute
seulement ce qui lui manque pour servir en production — la sauvegarde du
modele entraine et de ses metriques.

Usage :
    python train_melbourne.py chemin/vers/melbourne_2019.csv

Sorties :
    zopark_melbourne_rf.pkl       modele serialise
    zopark_melbourne_metrics.json metriques et importance des variables
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, roc_auc_score

PIPELINE_FILE = os.environ.get("ZOPARK_PIPELINE", "zopark_melbourne_pipeline.py")
MODEL_OUT = "zopark_melbourne_rf.pkl"
METRICS_OUT = "zopark_melbourne_metrics.json"


def load_pipeline():
    """Charge le module de ton ami sans y toucher."""
    if not os.path.exists(PIPELINE_FILE):
        sys.exit(
            f"Introuvable : {PIPELINE_FILE}\n"
            "Renomme le fichier en 'zopark_melbourne_pipeline.py' "
            "(sans espace ni parentheses) et place-le dans ce dossier."
        )
    spec = importlib.util.spec_from_file_location("melbourne_pipeline", PIPELINE_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)

    mp = load_pipeline()
    print(f"Pipeline charge : {PIPELINE_FILE}")
    print(f"  granularite = {mp.GRANULARITE_MIN} min, "
          f"max evenements = {mp.MAX_EVENEMENTS}")

    # --- Chaine d'origine, fonctions inchangees --------------------------
    df = mp.charger_donnees(sys.argv[1])
    df = mp.nettoyer(df)
    snaps = mp.evenements_vers_snapshots(df)
    snaps = mp.construire_features(snaps)

    features = ["heure_sin", "heure_cos", "jour_semaine", "est_weekend", "duree_max"]

    masque_test = snaps["mois"].isin(mp.MOIS_TEST)
    if masque_test.sum() == 0 or (~masque_test).sum() == 0:
        print("Split temporel vide — repli sur un split aleatoire 80/20.")
        from sklearn.model_selection import train_test_split

        X_train, X_test, y_train, y_test = train_test_split(
            snaps[features], snaps["occupee"], test_size=0.2, random_state=mp.GRAINE
        )
        split = "aleatoire 80/20"
    else:
        X_train = snaps.loc[~masque_test, features]
        y_train = snaps.loc[~masque_test, "occupee"]
        X_test = snaps.loc[masque_test, features]
        y_test = snaps.loc[masque_test, "occupee"]
        split = f"temporel, mois {mp.MOIS_TEST} en test"

    print(f"\nSplit : {split}")
    print(f"  entrainement {len(X_train)} | test {len(X_test)}")
    print(f"  taux d'occupation reel dans le test : {y_test.mean():.2%}")

    # --- Baseline de reference : moyenne historique par (jour, heure) ----
    heures_train = snaps.loc[X_train.index, "heure"]
    table = (
        pd.DataFrame(
            {"jour": X_train["jour_semaine"].values,
             "heure": heures_train.values,
             "occ": y_train.values}
        )
        .groupby(["jour", "heure"])["occ"]
        .mean()
    )
    cles = list(zip(X_test["jour_semaine"], snaps.loc[X_test.index, "heure"]))
    proba_base = np.array([table.get(k, y_train.mean()) for k in cles])
    auc_base = roc_auc_score(y_test, proba_base)

    # --- Random Forest, memes hyperparametres que le pipeline ------------
    print("\nEntrainement du Random Forest...")
    rf = RandomForestClassifier(
        n_estimators=100, max_depth=15, n_jobs=-1, random_state=mp.GRAINE
    )
    rf.fit(X_train, y_train)

    proba = rf.predict_proba(X_test)[:, 1]
    acc = accuracy_score(y_test, rf.predict(X_test))
    auc = roc_auc_score(y_test, proba)

    print("-" * 52)
    print(f"  Baseline (moyenne jour/heure)  AUC = {auc_base:.3f}")
    print(f"  Random Forest                  AUC = {auc:.3f}  precision = {acc:.2%}")
    gain = auc - auc_base
    print(f"  Gain sur la baseline           {gain:+.3f}")
    if gain < 0.02:
        print("  -> Gain marginal : la moyenne historique suffirait pour une V1.")
        print("     C'est un resultat honnete, a dire tel quel en soutenance.")
    print("-" * 52)

    print("\nImportance des variables :")
    for f, imp in sorted(zip(features, rf.feature_importances_), key=lambda t: -t[1]):
        print(f"  {f:<15} {imp * 100:5.1f}%")

    joblib.dump(rf, MODEL_OUT)

    metrics = {
        "source": "City of Melbourne — On-street Car Parking Sensor Data",
        "ground_truth": True,
        "split": split,
        "train_rows": int(len(X_train)),
        "test_rows": int(len(X_test)),
        "test_occupancy_rate": round(float(y_test.mean()), 4),
        "features": features,
        "auc_baseline_hour_day": round(float(auc_base), 4),
        "auc_random_forest": round(float(auc), 4),
        "auc_gain": round(float(gain), 4),
        "accuracy": round(float(acc), 4),
        "feature_importance": {
            f: round(float(i), 4) for f, i in zip(features, rf.feature_importances_)
        },
        "proba_min": round(float(proba.min()), 4),
        "proba_max": round(float(proba.max()), 4),
    }
    with open(METRICS_OUT, "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)

    print(f"\nEcrit : {MODEL_OUT} et {METRICS_OUT}")
    print("Copie les deux dans backend/ puis relance uvicorn.")


if __name__ == "__main__":
    main()
