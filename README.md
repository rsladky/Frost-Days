# Frost-Days ❄️

Calcul du **nombre de jours de gel** pour une commune française et une plage de
dates, à partir des données climatologiques quotidiennes de Météo-France
(open data, [data.gouv.fr](https://www.data.gouv.fr/datasets/donnees-climatologiques-de-base-quotidiennes)).

Un **jour de gel** est défini comme un jour où la température minimale (`TN`) a été
inférieure ou égale à **0 °C**.

## Fonctionnalités

Pour une commune + un département + une plage de dates, l'application calcule :

1. Le **nombre total** de jours de gel sur la plage.
2. Le **nombre moyen** de jours de gel par année.
3. Pour **chaque jour de l'année** (hors 29 février) : le nombre de fois où ce
   jour a été un jour de gel, en valeur **absolue** et **relative**
   (ex. « le 31 mars a gelé 3 fois sur 10 ans, soit 30 % du temps »).

Le volume total dépasse 100 millions de lignes : rien n'est précalculé. Seul le
fichier du **département demandé** est téléchargé (puis mis en cache localement),
ce qui permet de répondre en temps réel.

## Architecture

```
frost_days/
├── config.py      # constantes, seuils, URLs, chemins de cache
├── communes.py    # référentiel des communes + résolution lat/lon
├── stations.py    # liste des stations, distance Haversine + KDTree
├── weather.py     # téléchargement/cache des fichiers Météo-France, chargement de TN
├── frost.py       # cœur métier : sélection de station + statistiques de gel
└── cli.py         # interface en ligne de commande
app/streamlit_app.py   # interface graphique (Streamlit + Plotly)
notebooks/exploration.ipynb  # statistiques descriptives / contrôle qualité
tests/test_frost.py    # tests unitaires
```

### Choix de la station

Les stations du département sont classées par distance (**Haversine**, plus
précis ; **KDTree** disponible pour un premier tri rapide). On retient la
**station valide la plus proche** : la première dont le taux de valeurs
manquantes de `TN` sur la plage demandée est **≤ 35 %**.

## Installation

Le projet utilise [`uv`](https://docs.astral.sh/uv/) :

```bash
uv sync --extra dev
```

## Utilisation

### Ligne de commande

```bash
uv run frost-days --commune "Paris" --departement 75 --debut 2014-01-01 --fin 2023-12-31
```

### Interface graphique

```bash
uv run streamlit run app/streamlit_app.py
```

### Tests

```bash
uv run pytest
```

## Données

- **Météo-France** — données quotidiennes RR-T-Vent par département
  (`Q_{dept}_previous-…_RR-T-Vent.csv.gz`, séparateur `;`). Colonne utilisée :
  `TN` (température minimale, en °C).
- **Référentiel des communes** — `communes-et-villes-de-france` (parquet), pour
  obtenir les coordonnées GPS. Quelques communes sans GPS sont complétées via un
  dictionnaire de secours (`config.missing_cities_lat_lon`).

Les URLs réelles sont résolues dynamiquement via l'API data.gouv (les noms de
fichiers évoluent dans le temps), avec repli sur des URLs codées en dur.

## Période de référence

Le défi cible la période **2014-2023** (10 ans), mais toute plage de dates
disponible dans les données est acceptée.
