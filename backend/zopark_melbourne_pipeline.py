
import sys
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, roc_auc_score

# ---------------------------------------------------------------
# Parametres
# ---------------------------------------------------------------

GRANULARITE_MIN = 30


MAX_EVENEMENTS = 2_000_000
CHUNK_SIZE = 500_000


MOIS_TEST = [11, 12]

# Graine fixe = resultats reproductibles d'une execution a l'autre.
GRAINE = 42


COLS_ARRIVEE = ["ArrivalTime", "Arrival Time", "arrivaltime"]
COLS_DEPART = ["DepartureTime", "Departure Time", "departuretime"]
COLS_PRESENT = ["Vehicle Present", "VehiclePresent", "vehiclepresent"]
COLS_SIGN = ["Sign", "sign"]
COLS_MARKER = ["StreetMarker", "Street Marker", "streetmarker"]
COLS_AREA = ["Area", "area", "AreaName"]


def trouver_colonne(df_cols, candidats):
    for c in candidats:
        if c in df_cols:
            return c
    return None


def charger_donnees(chemin):

    print(f"Lecture de {chemin} par morceaux de {CHUNK_SIZE} lignes...")
    morceaux = []
    total = 0
    for chunk in pd.read_csv(chemin, chunksize=CHUNK_SIZE, low_memory=False):
        cols = chunk.columns
        c_arr = trouver_colonne(cols, COLS_ARRIVEE)
        c_dep = trouver_colonne(cols, COLS_DEPART)
        c_pres = trouver_colonne(cols, COLS_PRESENT)
        c_sign = trouver_colonne(cols, COLS_SIGN)
        c_mark = trouver_colonne(cols, COLS_MARKER)
        c_area = trouver_colonne(cols, COLS_AREA)

        # Sans arrivee ni depart, il n'y a rien a apprendre : on s'arrete net.
        if c_arr is None or c_dep is None:
            raise ValueError(
                f"Colonnes arrivee/depart introuvables. Colonnes du fichier : {list(cols)}"
            )

        garder = [c for c in [c_arr, c_dep, c_pres, c_sign, c_mark, c_area] if c]
        chunk = chunk[garder].rename(columns={
            c_arr: "arrivee", c_dep: "depart",
            **({c_pres: "present"} if c_pres else {}),
            **({c_sign: "sign"} if c_sign else {}),
            **({c_mark: "place"} if c_mark else {}),
            **({c_area: "zone"} if c_area else {}),
        })
        morceaux.append(chunk)
        total += len(chunk)
        print(f"  {total} lignes chargees...", end="\r")
        if MAX_EVENEMENTS and total >= MAX_EVENEMENTS:
            break
    df = pd.concat(morceaux, ignore_index=True)
    if MAX_EVENEMENTS:
        df = df.head(MAX_EVENEMENTS)
    print(f"\n{len(df)} evenements charges.")
    return df


def nettoyer(df):
    """
    Les capteurs de rue sont imparfaits, et la ville de Melbourne documente
    elle-meme ses anomalies. On corrige les trois cas connus avant d'apprendre
    quoi que ce soit : sinon le modele apprend les bugs des capteurs.
    """
    n0 = len(df)

    # Piege classique : Melbourne ecrit les dates a l'americaine (mois/jour).
    # Lu comme jour/mois, le 03/11 devient une autre date et tout se decale.
    FMT = "%m/%d/%Y %I:%M:%S %p"
    arr_brut, dep_brut = df["arrivee"].astype(str), df["depart"].astype(str)
    df["arrivee"] = pd.to_datetime(arr_brut, format=FMT, errors="coerce")
    df["depart"] = pd.to_datetime(dep_brut, format=FMT, errors="coerce")

    # Si plus de la moitie des dates echouent, c'est qu'une autre annee du
    # dataset utilise un autre format : on laisse pandas deviner.
    if df["arrivee"].isna().mean() > 0.5:
        df["arrivee"] = pd.to_datetime(arr_brut, errors="coerce")
        df["depart"] = pd.to_datetime(dep_brut, errors="coerce")

    df = df.dropna(subset=["arrivee", "depart"])

    # Une voiture qui repart avant d'arriver : capteur defaillant, on jette.
    df = df[df["depart"] > df["arrivee"]]

    # Plus de 7 jours sur une place a duree limitee : la session n'a jamais
    # ete refermee par le capteur. Ces lignes fausseraient tout.
    df = df[(df["depart"] - df["arrivee"]) <= pd.Timedelta(days=7)]

    # Le champ presence est parfois booleen, parfois du texte selon l'annee.
    if "present" in df.columns:
        df["present"] = (
            df["present"].astype(str).str.strip().str.lower()
            .isin(["true", "1", "yes", "vrai"])
        )
    else:
        df["present"] = True

    print(f"Nettoyage : {n0} -> {len(df)} evenements ({n0 - len(df)} retires).")
    return df


def extraire_duree_max(sign):
    """
    Le panneau de rue devient un nombre exploitable.
    "2P MTR M-SAT 7:30-18:30" -> 2, c'est-a-dire 2 heures maximum.

    C'est la variable qui rend le transfert possible : Halifax affiche
    exactement le meme type de signalisation sur ses places.
    """
    if not isinstance(sign, str):
        return -1
    s = sign.upper().strip()
    for token in s.split():
        if token.endswith("P") and token[:-1].isdigit():
            return int(token[:-1])
        if token == "1/2P":
            return 0.5
    return -1  # panneau absent ou illisible


def evenements_vers_snapshots(df):
    """
    C'est ici que naissent les etiquettes, et c'est le coeur de la methode.

    Le CSV brut ne contient AUCUNE colonne "occupee". Il contient des
    sessions : telle voiture est arrivee a 9h10 et repartie a 11h05.
    Un modele ne peut rien faire d'une session.

    On decoupe donc chaque session sur une grille de 30 min. Une session de
    deux heures produit quatre lignes, chacune etiquetee 1 (occupee).
    Resultat : (place, moment) -> 0 ou 1. C'est le label supervise.
    """
    print(f"Transformation evenements -> snapshots ({GRANULARITE_MIN} min)...")
    pas = f"{GRANULARITE_MIN}min"

    # On elargit legerement : arrivee arrondie vers le bas, depart vers le
    # haut, pour qu'une session courte occupe au moins une tranche entiere.
    debut = df["arrivee"].dt.floor(pas)
    fin = df["depart"].dt.ceil(pas)
    n_pas = ((fin - debut) / pd.Timedelta(minutes=GRANULARITE_MIN)).astype(int).clip(lower=1)

    df["duree_max"] = df["sign"].map(extraire_duree_max) if "sign" in df.columns else -1

    # Une boucle Python sur des millions de sessions prendrait des heures.
    # np.repeat duplique chaque ligne autant de fois qu'elle a de tranches,
    # et les offsets donnent l'horodatage de chacune. Tout est vectorise.
    idx = np.repeat(df.index.values, n_pas.values)
    offsets = np.concatenate([np.arange(n) for n in n_pas.values])
    snaps = pd.DataFrame({
        "timestamp": debut.loc[idx].values
        + offsets * pd.Timedelta(minutes=GRANULARITE_MIN),
        "occupee": df["present"].loc[idx].astype(int).values,
        "duree_max": df["duree_max"].loc[idx].values,
    })
    if "place" in df.columns:
        snaps["place"] = df["place"].loc[idx].values

    # Deux sessions peuvent se chevaucher sur la meme tranche (une voiture
    # part, une autre arrive). Dans le doute, la place compte comme occupee.
    cles = ["place", "timestamp"] if "place" in snaps.columns else ["timestamp"]
    snaps = snaps.groupby(cles, as_index=False).agg(
        occupee=("occupee", "max"), duree_max=("duree_max", "first")
    )
    print(f"{len(snaps)} snapshots generes.")
    return snaps


def construire_features(snaps):
    """
    Regle qu'on s'est fixee : on n'utilise que des variables dont Halifax
    dispose aussi. Pas d'identifiant de place australien, pas de zone
    tarifaire locale — sinon le modele serait inutilisable ailleurs.
    """
    snaps["heure"] = snaps["timestamp"].dt.hour
    snaps["jour_semaine"] = snaps["timestamp"].dt.dayofweek
    snaps["est_weekend"] = (snaps["jour_semaine"] >= 5).astype(int)
    snaps["mois"] = snaps["timestamp"].dt.month

    
    snaps["heure_sin"] = np.sin(2 * np.pi * snaps["heure"] / 24)
    snaps["heure_cos"] = np.cos(2 * np.pi * snaps["heure"] / 24)
    return snaps


def evaluer(nom, y_test, y_pred, y_proba):
    
    acc = accuracy_score(y_test, y_pred)
    auc = roc_auc_score(y_test, y_proba)
    print(f"  {nom:<28} precision = {acc:6.2%}   AUC = {auc:.3f}")
    return acc, auc


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    df = charger_donnees(sys.argv[1])
    df = nettoyer(df)
    snaps = evenements_vers_snapshots(df)
    snaps = construire_features(snaps)

    # Les cinq variables d'entree du modele. Toutes transferables a Halifax.
    features = ["heure_sin", "heure_cos", "jour_semaine", "est_weekend", "duree_max"]

    # Split temporel : le modele apprend sur janvier-octobre et se fait
    # juger sur novembre-decembre, qu'il n'a jamais vus.
    masque_test = snaps["mois"].isin(MOIS_TEST)
    X_train, y_train = snaps.loc[~masque_test, features], snaps.loc[~masque_test, "occupee"]
    X_test, y_test = snaps.loc[masque_test, features], snaps.loc[masque_test, "occupee"]

    # Filet de securite si l'extrait charge ne couvre pas ces deux mois.
    if len(X_test) == 0 or len(X_train) == 0:
        print("ATTENTION : le split temporel est vide (dataset ne couvrant pas "
              f"les mois {MOIS_TEST}). Split aleatoire 80/20 utilise a la place.")
        from sklearn.model_selection import train_test_split
        X_train, X_test, y_train, y_test = train_test_split(
            snaps[features], snaps["occupee"], test_size=0.2, random_state=GRAINE
        )

    print(f"\nEntrainement : {len(X_train)} exemples | Test : {len(X_test)} exemples")
    print(f"Taux d'occupation dans le test : {y_test.mean():.2%}\n")
    print("Resultats :")

    # La demarche est volontairement graduelle : on part du plus bete et on
    # ne complique que si ca rapporte. Un modele sophistique qui ne bat pas
    # une moyenne ne merite pas d'etre mis en production.

    # Niveau 0 : repondre toujours la meme chose. Le plancher absolu.
    maj = int(y_train.mean() >= 0.5)
    evaluer("Baseline (classe majoritaire)", y_test,
            np.full(len(y_test), maj), np.full(len(y_test), y_train.mean()))

    # Niveau 1 : la moyenne historique par creneau. C'est ce que ferait
    # n'importe qui sans machine learning, et c'est le vrai concurrent.
    table = (
        pd.concat([X_train[["jour_semaine"]], y_train,
                   snaps.loc[X_train.index, "heure"]], axis=1)
        .groupby(["jour_semaine", "heure"])["occupee"].mean()
    )
    cle_test = list(zip(X_test["jour_semaine"], snaps.loc[X_test.index, "heure"]))
    proba_hist = np.array([table.get(k, y_train.mean()) for k in cle_test])
    evaluer("Baseline (moyenne heure/jour)", y_test,
            (proba_hist >= 0.5).astype(int), proba_hist)

    # Niveau 2 : un modele lineaire. Simple, rapide, mais il ne peut tracer
    # que des frontieres droites entre "libre" et "occupee".
    lr = LogisticRegression(max_iter=1000)
    lr.fit(X_train, y_train)
    evaluer("Regression logistique", y_test,
            lr.predict(X_test), lr.predict_proba(X_test)[:, 1])

    # Niveau 3 : la foret aleatoire. 100 arbres qui votent, chacun entraine
    # sur un echantillon different. Elle capture les effets croises du type
    # "samedi 14h ne ressemble pas a mardi 14h", ce que le lineaire rate.
    # Profondeur limitee a 15 pour eviter d'apprendre le bruit par coeur.
    rf = RandomForestClassifier(
        n_estimators=100, max_depth=15, n_jobs=-1, random_state=GRAINE
    )
    rf.fit(X_train, y_train)
    evaluer("Random Forest", y_test,
            rf.predict(X_test), rf.predict_proba(X_test)[:, 1])

    # Quelles variables comptent vraiment ? Utile pour montrer que le modele
    # s'appuie sur des signaux plausibles et pas sur du hasard.
    print("\nImportance des features (Random Forest) :")
    for f, imp in sorted(zip(features, rf.feature_importances_),
                         key=lambda x: -x[1]):
        print(f"  {f:<15} {imp:.3f}")

    print("\nInterpretation :")
    print("- Si le Random Forest bat nettement la baseline heure/jour,")
    print("  les features transferables capturent un vrai signal -> bon pour ZoPark.")
    print("- Sinon, la moyenne historique suffit pour la V1 (et c'est OK a dire au prof).")


if __name__ == "__main__":
    main()