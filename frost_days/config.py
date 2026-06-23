"""Constantes et chemins de configuration du projet Frost-Days."""

from __future__ import annotations

from pathlib import Path

# --- Période de référence du défi (début 2014 -> fin 2023, soit 10 ans) ---
PERIOD_START = "2014-01-01"
PERIOD_END = "2023-12-31"

# --- Règles métier ---
# Jour de gel : température minimale TN <= 0 °C.
FROST_THRESHOLD = 0.0
# Une station avec plus de 35 % de valeurs manquantes sur la période n'est pas utilisée.
MAX_MISSING_RATIO = 0.35
# Nombre maximum de stations candidates inspectées (par distance croissante).
MAX_CANDIDATE_STATIONS = 15

# --- Colonnes utiles dans les fichiers Météo-France QUOT RR-T-Vent ---
CSV_SEP = ";"
COL_STATION = "NUM_POSTE"
COL_NAME = "NOM_USUEL"
COL_LAT = "LAT"
COL_LON = "LON"
COL_ALTI = "ALTI"
COL_DATE = "AAAAMMJJ"
COL_TN = "TN"

# --- Sources de données (data.gouv.fr / Météo-France) ---
# Fichiers quotidiens par département. Le fichier "previous" (1950 -> année N-1)
# couvre la période cible 2014-2023. Le suffixe d'année évolue dans le temps
# (ex. "previous-1950-2024"), c'est pourquoi weather.py résout l'URL réelle via
# l'API data.gouv et n'utilise ce gabarit qu'en repli.
METEO_BASE_URL = (
    "https://object.files.data.gouv.fr/meteofrance/data/synchro_ftp/BASE/QUOT/"
)
# Gabarit de repli ; {dept} = code département (ex. "01", "75", "971").
METEO_PREVIOUS_TEMPLATE = "Q_{dept}_previous-1950-2024_RR-T-Vent.csv.gz"
# Sous-chaîne stable utilisée pour repérer la bonne ressource dans l'API.
METEO_PREVIOUS_MARKER = "_previous-"
METEO_RRTVENT_MARKER = "RR-T-Vent.csv.gz"

# Slugs des datasets data.gouv (résolution des URLs réelles via l'API).
METEO_DATASET_SLUG = "donnees-climatologiques-de-base-quotidiennes"
COMMUNES_DATASET_SLUG = "communes-et-villes-de-france-en-csv-excel-json-parquet-et-feather"

DATAGOUV_API = "https://www.data.gouv.fr/api/1/datasets/{slug}/"

# Référentiel communes (parquet hébergé sur data.gouv) — URL de repli ; communes.py
# résout en priorité la ressource parquet la plus récente via l'API data.gouv.
COMMUNES_PARQUET_URL = (
    "https://static.data.gouv.fr/resources/"
    "communes-et-villes-de-france-en-csv-excel-json-parquet-et-feather/"
    "20260617-160519/communes-france-2026.parquet"
)
COMMUNES_PARQUET_MARKER = ".parquet"

# Colonnes du référentiel communes.
COM_NAME = "nom_standard"
COM_NAME_NOACCENT = "nom_sans_accent"
COM_DEPT = "dep_code"
COM_LAT = "latitude_centre"
COM_LON = "longitude_centre"
COM_LAT_FALLBACK = "latitude_mairie"
COM_LON_FALLBACK = "longitude_mairie"

# --- Chemins locaux ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"          # fichiers météo .csv.gz par département
COMMUNES_DIR = DATA_DIR / "communes"    # référentiel des communes


def ensure_dirs() -> None:
    """Crée les répertoires de cache s'ils n'existent pas."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    COMMUNES_DIR.mkdir(parents=True, exist_ok=True)


# Coordonnées de secours pour les communes sans GPS dans le référentiel (fourni par l'énoncé).
missing_cities_lat_lon: dict[str, list[float]] = {
    "Marseille": [43.295, 5.372],
    "Paris": [48.866, 2.333],
    "Culey": [48.755, 5.266],
    "Les Hauts-Talican": [49.3436, 2.0193],
    "Lyon": [45.75, 4.85],
    "Bihorel": [49.4542, 1.1162],
    "Saint-Lucien": [48.6480, 1.6229],
    "L'Oie": [46.7982, -1.1302],
    "Sainte-Florence": [46.7965, -1.1520],
}
