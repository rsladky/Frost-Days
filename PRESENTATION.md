# Frost-Days — Guide de présentation & de vérification

Document destiné à **présenter le projet à l'oral** et à **prouver que le code est correct**.

---

## 1. Le problème en une phrase

> À partir des données météo open data de Météo-France, compter les **jours de gel**
> (jour où la température minimale `TN < 0 °C`) pour une **commune**, un **département**
> et une **plage de dates**, et en sortir des statistiques.

Trois sorties demandées :
1. **Total** de jours de gel sur la plage.
2. **Moyenne** de jours de gel par an.
3. Pour **chaque jour de l'année** (hors 29 février) : combien de fois il a gelé,
   en valeur **absolue** et **relative** (ex. « le 31 mars : 4 gels sur 9 ans = 44 % »).

La difficulté : le jeu de données complet fait **> 100 millions de lignes**. On ne peut
pas tout précalculer → il faut répondre **en temps réel**.

---

## 2. L'idée clé à mettre en avant

> **On ne télécharge jamais tout. On ne récupère que les fichiers des départements concernés.**

Météo-France publie un fichier `.csv.gz` **par département** (~4 Mo pour Paris).
Quand l'utilisateur demande « Paris, 75 », on récupère le fichier du 75 (et, pour une
commune en bordure, ceux des départements voisins proches), on les met en **cache
local**, et on calcule. C'est ce qui rend l'appli rapide malgré le volume total.

---

## 3. Le déroulé d'une requête (fil narratif pour l'oral)

C'est le meilleur plan pour présenter : suivre une requête de bout en bout.

```
Utilisateur : "Paris", "75", 2014-01-01 → 2023-12-31
        │
        ▼
1. communes.py   → trouve les coordonnées GPS de Paris (lat, lon)
        │           (référentiel des communes ; dictionnaire de secours si GPS manquant)
        ▼
2. stations.py   → départements candidats = 75 + voisins dans un rayon de 40 km
        │           weather.py télécharge (ou lit du cache) leurs fichiers météo
        │           (URLs résolues via l'API data.gouv)
        ▼
3. stations.py   → liste les stations de ces départements, triées par distance (Haversine)
        │
        ▼
4. frost.py      → parcourt les stations de la plus proche à la plus lointaine,
        │           garde la 1re station avec ≤ 35 % de valeurs manquantes
        │           (ici : LUXEMBOURG, 1,7 km, 3 % de manquants)
        ▼
5. frost.py      → calcule les 3 statistiques sur la série TN de cette station
        │
        ▼
   Résultat : total = 106, moyenne = 10,6/an, fréquences par jour de l'année
```

### Rôle de chaque module (`frost_days/`)

| Module        | Responsabilité |
|---------------|----------------|
| `config.py`   | Toutes les constantes : seuil 0 °C, seuil 35 %, URLs, chemins de cache, dictionnaire des communes sans GPS. |
| `datagouv.py` | Briques communes : normaliser un nom (sans accents), résoudre une URL via l'API data.gouv, télécharger un fichier. |
| `communes.py` | Charger le référentiel des communes, donner les coordonnées GPS d'une commune. |
| `weather.py`  | Télécharger/mettre en cache le fichier météo d'un département, en extraire la série `TN` d'une station. |
| `stations.py` | Distance **Haversine** (et option **KDTree**), classement des stations par distance. |
| `frost.py`    | **Cœur métier** : choisir la station, calculer les 3 statistiques. |
| `cli.py`      | Lancer le calcul en ligne de commande. |
| `app/streamlit_app.py` | Interface graphique (formulaire + graphiques + carte). |

---

## 4. Les choix techniques à défendre (questions probables du jury)

- **« Pourquoi ne pas tout précalculer ? »**
  100M+ lignes : inutile et impossible à maintenir. Téléchargement **à la demande par
  département** + **cache** = réponse en temps réel.

- **« Pourquoi Haversine ? »**
  Distance à vol d'oiseau précise sur une sphère (la Terre). KDTree est aussi disponible
  (`--method kdtree`) : il est beaucoup plus rapide pour un premier tri, mais on recalcule
  la distance exacte en Haversine pour l'affichage. → conforme à l'énoncé.

- **« Comment choisir LA station ? »**
  La **plus proche** dont les données sont **suffisamment complètes** : on écarte toute
  station avec **> 35 % de valeurs manquantes** sur la plage demandée (règle de l'énoncé).

- **« Et les communes sans coordonnées GPS ? »**
  Dictionnaire de secours fourni dans l'énoncé (`config.missing_cities_lat_lon`), utilisé
  en repli quand le référentiel n'a pas la position.

- **« Pourquoi exclure le 29 février ? »**
  Il n'existe qu'une année sur 4 → statistique non comparable aux autres jours (demandé par l'énoncé).

- **« Pourquoi les URLs sont résolues dynamiquement ? »**
  Le nom des fichiers Météo-France change avec le temps (`previous-1950-2024` aujourd'hui,
  `…-2025` demain). On interroge l'API data.gouv pour trouver le bon fichier, avec une
  URL de repli codée en dur si l'API est indisponible.

- **Performance** : lecture pandas avec colonnes restreintes (`usecols`) + types explicites,
  et **cache mémoire** (`lru_cache`) pour ne pas relire le fichier entre le tri des stations
  et le calcul du gel.

---

## 5. Comment VÉRIFIER qu'il n'y a pas d'erreur

Cinq niveaux de vérification, du plus automatique au plus convaincant à l'oral.

### Niveau 1 — Tests unitaires automatiques
```bash
uv run pytest -q
```
Attendu : **26 passed**. Ces tests vérifient la logique pure, sans réseau, et se
répartissent en deux fichiers :

**`tests/test_frost.py` (8 tests) — le cœur métier :**
- le seuil de gel (`0.0` gèle, `0.1` non, `NaN` non) ;
- le calcul du taux de valeurs manquantes (NaN comptés comme manquants) ;
- la fréquence relative par jour et **l'exclusion du 29 février** ;
- l'exclusion des années sans donnée du dénominateur de la fréquence.

**`tests/test_stations.py` (18 tests) — les algorithmes Haversine & KDTree :**
- **Haversine, exactitude** : distances réelles connues (Paris→Lyon ≈ 392 km,
  Paris→Marseille ≈ 661 km, Paris→Londres ≈ 343 km), **symétrie** `d(A,B)=d(B,A)`,
  distance nulle sur un même point, **version vectorisée** = appels scalaires,
  borne physique (antipodes ≈ 20 015 km).
- **Classement Haversine** : ordre conforme aux distances, colonne `distance_km`
  triée croissante, station la plus proche correctement identifiée.
- **KDTree vs Haversine** : même station la plus proche, même ordre complet sur un
  jeu sans ambiguïté, même ensemble de stations renvoyé, et `distance_km` identique
  par station entre les deux méthodes.
- **Pourquoi Haversine par défaut** (2 tests, voir §5 bis) : sur une quasi-égalité,
  Haversine choisit la station réellement la plus proche, là où KDTree (euclidien en
  degrés) peut se tromper.
- **Cas limites** : DataFrame vide, une seule station.

### Niveau 2 — Exécution réelle (résultats plausibles)
```bash
uv run frost-days --commune "Paris" --departement 75 --debut 2014-01-01 --fin 2023-12-31
```
On regarde si les résultats ont du **sens physique** :
- la station retenue est **proche** (Luxembourg, 1,7 km) et **peu lacunaire** (3 %) ;
- ~11 jours de gel/an à Paris : crédible (centre-ville, îlot de chaleur) ;
- les jours les plus gélifs tombent **en hiver** (janvier/février), pas en été.

### Niveau 3 — Cross-check indépendant (LE plus convaincant) ✅
On recompte le même chiffre **à la main** depuis le CSV brut, et on compare à la sortie du code :

```bash
uv run python -c "
import pandas as pd
from frost_days.weather import load_department_tn
from frost_days.frost import compute_stats
from frost_days import config

stats = compute_stats('Paris', '75', '2014-01-01', '2023-12-31')
df = load_department_tn('75')
sub = df[df[config.COL_STATION]==stats.station_id]
manuel_total = int(((sub[config.COL_DATE].dt.year.between(2014,2023)) & (sub[config.COL_TN]<0)).sum())
print('Code  :', stats.total_frost_days)
print('Manuel:', manuel_total)
assert stats.total_frost_days == manuel_total, 'INCOHÉRENCE !'
print('OK : les deux calculs concordent.')
"
```
Résultat vérifié : **Code = 106, Manuel = 106** → le code compte exactement comme un
calcul indépendant. C'est la meilleure preuve à montrer au jury.

### Niveau 4 — Contrôle qualité des données (notebook)
```bash
uv run jupyter lab notebooks/exploration.ipynb
```
Le notebook vérifie :
- l'**unité de `TN`** (valeurs entre ~ −30 et +30 → bien des °C décimaux, le seuil `< 0` s'applique tel quel) ;
- le **taux de valeurs manquantes** par station ;
- la **saisonnalité** du gel (courbe concentrée en hiver).

### Niveau 5 — Validation contre les exports de référence (fournie) ✅✅
Les exports de référence (`validation.zip`) donnent, pour 6 communes, la station retenue
et le `frost_day` quotidien (vérité terrain). Le script compare automatiquement :

```bash
uv run python scripts/validate.py
```

Il vérifie 4 choses par commune : **sélection de la station**, **valeurs `TN`**,
**définition du gel**, **total de jours de gel**. Résultat : **les 6 communes sont 100 %
valides**.

| Commune | Station (réf = mienne) | Pipeline `TN` | Total gel |
|---|---|---|---|
| Asnières-sur-Saône (01) | AZE #71016001 *(dépt 71)* | écart max 0,000 °C | 190 = 190 |
| Digne-les-Bains (04) | DIGNE LES BAINS #04070009 | 0,000 °C | 549 = 549 |
| Espinchal (63) | MARCENAT #15114002 *(dépt 15)* | 0,000 °C | 617 = 617 |
| Marseille (13) | MARSEILLE #13055029 | 0,000 °C | 49 = 49 |
| Montfalcon (38) | ST-CHRISTOPHE #26298001 *(dépt 26)* | 0,000 °C | 229 = 229 |
| Paris (75) | LUXEMBOURG #75106001 | 0,000 °C | 79 = 79 |

**Au-delà de la vérification : régénérer la donnée complète.** Les exports fournis
ne couvrent qu'une première portion de chaque série (`*_weather_data_half.csv`). Le
script `scripts/generate_validation.py` réutilise le pipeline (`select_station`,
`is_frost`) pour produire le **fichier complet 2013-2024** de chaque commune dans
`data/validation/generated/`, en vérifiant que la portion commune avec l'export
partiel est strictement identique (écart `tmin` max `0,000 °C`, 0 écart sur
`frost_day`) avant d'écrire « le reste » de la série :

```bash
uv run python scripts/generate_validation.py
```

Deux points clés découverts grâce à ces données et à mentionner à l'oral :
1. **Définition du gel** : la référence compte un gel uniquement quand `TN < 0`
   (strict), pas `≤ 0` comme l'écrit l'énoncé. Le code s'aligne sur la référence.
2. **Stations inter-départements** : 3 communes sur 6 ont leur station la plus proche
   dans un **département voisin** (bordure). Le code cherche donc dans le département
   de la commune **et** les départements proches (rayon 40 km), ce qui reproduit
   exactement la station de référence.

---

## 5 bis. Haversine vs KDTree : le test qui marque des points 🎯

Deux tests de `tests/test_stations.py` démontrent **pourquoi l'énoncé recommande Haversine**.

On prend deux stations à distance quasi égale de Paris, mais dans des **directions
différentes** :
- **Le Bourget** (48.9694, 2.4414) — plein **nord** ;
- **Orly** (48.7233, 2.3794) — plein **est**.

Or **un degré de longitude est plus court qu'un degré de latitude** (facteur
≈ cos(latitude) ≈ 0,66 à Paris). Conséquence :

| Méthode | Distance utilisée | Station classée 1re | Correct ? |
|---------|-------------------|---------------------|-----------|
| **Haversine** | vraie distance sphérique (km) | **Le Bourget** (~14,1 km) | ✅ oui |
| **KDTree** | euclidienne sur degrés bruts | **Orly** (~0,136 en degrés) | ❌ non |

- `test_haversine_picks_truly_closest_on_near_tie` prouve que Haversine retient bien
  Le Bourget, et vérifie au passage que `d(Bourget) < d(Orly)`.
- `test_kdtree_can_diverge_from_haversine_on_near_tie` **documente** la limite de
  KDTree : il place Orly en premier, à tort.

À dire à l'oral : *« KDTree reste utile comme pré-tri très rapide, mais sur les
quasi-égalités il peut se tromper car il ignore la courbure et l'anisotropie des
degrés. C'est pourquoi le calcul final et le classement par défaut utilisent
Haversine. »*

Pour l'illustrer en direct :
```bash
uv run pytest tests/test_stations.py -k near_tie -v
```

---

## 6. Limites assumées (à mentionner, ça fait sérieux)

- On retient **une seule** station (la plus proche valide), on ne combine pas plusieurs stations.
- La recherche inter-départements se fait dans un **rayon de 40 km** : une station
  pertinente au-delà (zone très peu équipée) pourrait être manquée.
- La moyenne par an inclut les **années partielles** telles quelles si la plage ne couvre
  pas des années entières.

---

## 7. Commandes utiles (anti-sèche)

```bash
uv sync --extra dev                       # installer l'environnement
uv run pytest -q                          # tests unitaires
uv run python scripts/validate.py         # validation contre les données de référence
uv run frost-days --commune "Lyon" --departement 69 --debut 2014-01-01 --fin 2023-12-31
uv run frost-days --commune "Paris" --departement 75 --method kdtree   # autre méthode de distance
uv run streamlit run app/streamlit_app.py # interface graphique
```
