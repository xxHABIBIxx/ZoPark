# ZoPark — fabriquer ZoPark.exe (v2, adapte a ton projet)

Ce kit s'installe SANS rien deplacer dans ton projet : les 4 fichiers vont
a la racine, a cote de app\, backend\, data\ et tools\.

## Ou mettre les fichiers

    zopark_v9\                        <- ton dossier existant
        app\                          (inchange)
        backend\                      (inchange)
        data\                         (inchange)
        tools\                        (inchange)
        README.md                     (le tien, inchange)
        launcher.py                   <- AJOUTER (ce kit)
        zopark.spec                   <- AJOUTER
        warmup.py                     <- AJOUTER
        build_exe.bat                 <- AJOUTER

## Etapes

1. Copier les 4 fichiers du kit a la racine, comme ci-dessus.
2. Corriger le bug dans backend\zopark_api.py : ajouter en tete de fichier,
   avec les autres imports :

       from datetime import datetime

   (Le fichier utilise datetime.now() sans jamais l'importer ; sans ce
   correctif l'API repond 500 et l'app bascule en trace a vol d'oiseau.
   Le lanceur injecte un correctif de secours, mais corrige la source.)
3. Si tu as entraine le modele Melbourne, placer zopark_melbourne_rf.pkl et
   zopark_melbourne_metrics.json dans backend\. Sinon, rien a faire : l'API
   utilisera la grille parametrique de data\halifax_bundle.json, comme prevu.
4. Double-cliquer sur build_exe.bat (Python 3.11/3.12 et Flutter requis sur
   CETTE machine, plus Internet pour le telechargement unique du graphe).
   Compter 10 a 20 minutes la premiere fois.
5. Recuperer dist\ZoPark.exe : c'est l'executable final, autonome. La
   machine qui l'execute n'a besoin de rien (ni Python, ni Flutter, ni
   Internet).

## Le jour J

Double-clic sur ZoPark.exe. En mode onefile, Windows extrait l'archive a
chaque lancement : 15 a 40 s avant la console, puis les logs [INIT]
defilent et le navigateur s'ouvre seul sur la carte. Laisser la console
ouverte ; la fermer arrete tout.

Tester une premiere fois sur la machine de la soutenance : SmartScreen
affichera « Windows a protege votre ordinateur » (exe non signe) — cliquer
« Informations complementaires » puis « Executer quand meme ».

Si le demarrage onefile parait trop lent, la variante « onedir » (dossier
dist\ZoPark\ avec demarrage quasi instantane) est prete en commentaire a la
fin de zopark.spec.

## Ce que le lanceur regle pour toi

Le port est fixe a 8000 parce que routing_api.dart appelle
http://127.0.0.1:8000 en dur ; l'app web est servie sur la MEME origine que
l'API, donc pas de CORS. Les donnees embarquees sont transmises a
zopark_api.py via ses variables d'environnement existantes (ZOPARK_BUNDLE,
ZOPARK_MODEL, ZOPARK_METRICS) : ton backend n'est pas modifie. Le cache
halifax_graph.graphml est ecrit a cote de l'exe, ou dans
%LOCALAPPDATA%\ZoPark si le dossier est en lecture seule.

## Depannage

Carte affichee mais « Serveur de routage injoignable » : regarder la
console — si [INIT] ECHEC apparait, le message donne la cause. Antivirus
qui supprime l'exe : ajouter une exclusion (faux positif connu des exe
PyInstaller non signes). Module manquant a l'execution : ajouter son nom a
hiddenimports dans zopark.spec et relancer build_exe.bat.
