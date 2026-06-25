"""Accès aux données météo Météo-France : téléchargement, cache et chargement de TN."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from frost_days import config
from frost_days.datagouv import download, resolve_resource_url


def normalize_dept(departement: str | int) -> str:
    """Normalise un code département (« 1 » -> « 01 », « 75 » -> « 75 », « 2A »)."""
    dept = str(departement).strip().upper()
    if dept.isdigit() and len(dept) < 2:
        dept = dept.zfill(2)
    return dept


# Météo-France publie encore la Corse sous l'ancien code commun « 20 » (un seul
# fichier pour 2A + 2B), alors que le référentiel des communes utilise 2A/2B.
_CORSICA_LEGACY_CODE = {"2A": "20", "2B": "20"}


def department_url(dept: str) -> str:
    """Résout l'URL du fichier quotidien « previous » du département.

    Le nom de fichier évoluant dans le temps, on interroge l'API data.gouv et on
    retient la ressource correspondant au département + période « previous ».
    Repli sur le gabarit codé en dur si l'API est injoignable."""
    file_dept = _CORSICA_LEGACY_CODE.get(dept, dept)
    marker = f"Q_{file_dept}{config.METEO_PREVIOUS_MARKER}"
    url = resolve_resource_url(
        config.METEO_DATASET_SLUG, marker, config.METEO_RRTVENT_MARKER
    )
    if url:
        return url
    return config.METEO_BASE_URL + config.METEO_PREVIOUS_TEMPLATE.format(dept=file_dept)


def download_department(departement: str | int) -> Path:
    """Télécharge (si absent du cache) le fichier .csv.gz du département."""
    config.ensure_dirs()
    dept = normalize_dept(departement)
    dest = config.CACHE_DIR / f"Q_{dept}_previous_RR-T-Vent.csv.gz"
    return download(department_url(dept), dest)


@lru_cache(maxsize=4)
def load_department_tn(departement: str | int) -> pd.DataFrame:
    """Charge tout l'historique TN d'un département (colonnes restreintes).

    Renvoie un DataFrame avec NUM_POSTE, NOM_USUEL, LAT, LON, DATE (datetime) et
    TN (float). Mis en cache mémoire car réutilisé pour le tri des stations puis
    le calcul du gel."""
    path = download_department(departement)
    usecols = [
        config.COL_STATION,
        config.COL_NAME,
        config.COL_LAT,
        config.COL_LON,
        config.COL_DATE,
        config.COL_TN,
    ]
    df = pd.read_csv(
        path,
        sep=config.CSV_SEP,
        usecols=usecols,
        dtype={
            config.COL_STATION: "string",
            config.COL_NAME: "string",
            config.COL_LAT: "float64",
            config.COL_LON: "float64",
            config.COL_TN: "float64",
        },
        compression="gzip",
    )
    df[config.COL_DATE] = pd.to_datetime(
        df[config.COL_DATE], format="%Y%m%d", errors="coerce"
    )
    return df


def load_station_tn(
    departement: str | int,
    num_poste: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.Series:
    """Série TN d'une station sur [start, end], indexée par date (jours bruts)."""
    df = load_department_tn(departement)
    mask = (
        (df[config.COL_STATION] == str(num_poste))
        & (df[config.COL_DATE] >= start)
        & (df[config.COL_DATE] <= end)
    )
    sub = df.loc[mask, [config.COL_DATE, config.COL_TN]].sort_values(config.COL_DATE)
    return pd.Series(
        sub[config.COL_TN].to_numpy(),
        index=pd.DatetimeIndex(sub[config.COL_DATE]),
        name=config.COL_TN,
    )
