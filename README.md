# ZoPark v9 — Halifax

Application Flutter Web, modèle d'occupation, itinéraire A\* pondéré.
Le pipeline Melbourne est inclus, prêt à être entraîné.

## Ce qu'il y a dedans

```
backend/
  zopark_api.py                 API FastAPI : OSMnx + A* pondéré + inférence
  zopark_melbourne_pipeline.py  pipeline de ton ami, INTACT (SHA-256 vérifié)
  train_melbourne.py            entraîne et exporte le modèle
  geo.py                        géométrie sans dépendance native
app/                            application Flutter
tools/build_from_xls.py         génère halifax_bundle.json depuis les .xls
data/                           les 3 exports .xls + le bundle déjà généré
```

## Démarrage rapide — l'app seule

Le bundle est déjà généré dans `data/`, tu n'as rien à recalculer.

```bash
cd ~/Downloads
rm -rf zopark_app/lib zopark_app/assets
cp -r zopark_v9/app/lib    zopark_app/lib
cp -r zopark_v9/app/assets zopark_app/assets
cp    zopark_v9/app/pubspec.yaml zopark_app/pubspec.yaml

cd zopark_app && flutter pub get && flutter run -d chrome
```

## L'A\* pondéré

Il est dans `backend/zopark_api.py`, méthode `ZoParkRouter.route()`. C'est la
logique d'origine de `zopark_rooter.py` :

```python
cout = distance * (1 + alpha * occupation)
```

`alpha = 0` donne le plus court chemin. Au-dessus, les rues que le modèle juge
saturées sont pénalisées. L'heuristique haversine est admissible, donc A\*
reste optimal.

L'endpoint `/route` renvoie **les deux tracés** — `classic` (alpha 0) et
`zopark` (alpha 2,5) — plus un drapeau `routes_identical` quand ils se
superposent. L'app affiche le gris et le bleu côte à côte.

Trois corrections par rapport à la version d'origine :

- Les extrémités du tracé sont raccordées aux vraies coordonnées.
  `nearest_nodes` accroche à une intersection, parfois à 100 m de la place.
- Rayon du graphe porté de 4 à 6 km — l'ouest de la péninsule en sortait.
- `alpha` ramené de 8 à 2,5 : à 8, le détour faisait 2,2 km pour 1,2 km direct.

```bash
cd backend
pip install -r requirements.txt
uvicorn zopark_api:app --port 8000
```

Compte 3 à 4 minutes au premier lancement, le temps de télécharger le réseau
routier. Il est ensuite mis en cache.

## Activer le modèle Melbourne

1. Télécharger « On-street Car Parking Sensor Data - 2019 » sur
   <https://data.melbourne.vic.gov.au>
2. Entraîner :

```bash
cd backend
python train_melbourne.py /chemin/vers/melbourne_2019.csv
```

3. Relancer `uvicorn`. Le backend détecte le `.pkl` seul :

```
[INIT] modele appris charge : zopark_melbourne_rf.pkl     <- Melbourne actif
[INIT] pas de zopark_melbourne_rf.pkl — grille ...        <- mode paramétrique
```

Le script affiche l'AUC du Random Forest **et celle de la baseline moyenne
jour/heure**. Si l'écart est sous 0,02, il te le signale : la moyenne
historique suffirait, et c'est un résultat honnête à présenter.

## Les deux modes

| | Sans `.pkl` | Avec Melbourne |
|---|---|---|
| Nature | paramétrique | **appris sur capteurs réels** |
| Vérité terrain | aucune | oui, mesurée |
| Scores distincts (391 places) | **222** | 7 |

Melbourne apporte la légitimité scientifique, le paramétrique la finesse
spatiale. Ses cinq variables sont temporelles : à Halifax, durée × zone
tarifaire ne donne que 7 combinaisons, donc des groupes qui basculent ensemble.

Montre les deux et explique pourquoi ils diffèrent. Un jury retient ça mieux
qu'un chiffre isolé.

## Périmètre — à dire avant qu'on te le demande

L'app couvre **le stationnement réglementé du centre-ville** : 176 bornes de
paiement et 215 places réservées aux personnes handicapées. C'est l'intégralité
de ce que HRM publie.

Le stationnement gratuit sur rue n'est recensé dans aucun jeu de données
municipal — il n'apparaît donc pas.

Les 176 bornes sont des **machines**, réparties sur 73 emplacements. Le point
marque la borne, pas la place. La capacité de 8 places par borne est une
estimation, HRM ne publie pas ce chiffre. Et aucune donnée ne précise les
heures d'application du tarif : à 21 h, une place affichée « payante » est
probablement gratuite.

---




## Zoom

La molette zoome désormais — il manquait `scrollWheelVelocity`, sans lequel
flutter_map ignore la molette sur le web. Deux boutons + et − ont été ajoutés
en haut à droite, plus fiables sur pavé tactile.

## Régénérer la couche d'interdiction

```bash
python tools/add_restrictions.py --src data --bundle data/halifax_bundle.json
cp data/halifax_bundle.json app/assets/data/
```
