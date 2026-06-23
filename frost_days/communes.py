"""Référentiel des communes : chargement et résolution des coordonnées GPS."""

from __future__ import annotations

from functools import lru_cache

import pandas as pd

from frost_days import config
from frost_days.datagouv import download, normalize, resolve_resource_url


def _commune_file() -> "Path":  # type: ignore[name-defined]
    """Télécharge (1×) le référentiel parquet des communes et renvoie son chemin."""
    from pathlib import Path  # local pour garder le module léger à l'import

    url = (
        resolve_resource_url(
            config.COMMUNES_DATASET_SLUG, config.COMMUNES_PARQUET_MARKER
        )
        or config.COMMUNES_PARQUET_URL
    )
    dest: Path = config.COMMUNES_DIR / "communes.parquet"
    return download(url, dest)


@lru_cache(maxsize=1)
def load_communes() -> pd.DataFrame:
    """Charge le référentiel des communes (mis en cache mémoire).

    Conserve les colonnes utiles et ajoute une clé normalisée de recherche."""
    path = _commune_file()
    cols = [
        config.COM_NAME,
        config.COM_DEPT,
        config.COM_LAT,
        config.COM_LON,
        config.COM_LAT_FALLBACK,
        config.COM_LON_FALLBACK,
    ]
    df = pd.read_parquet(path, columns=cols)
    df[config.COM_DEPT] = df[config.COM_DEPT].astype(str).str.strip()
    df["_key"] = df[config.COM_NAME].map(normalize)
    return df


def _fallback_coords(name: str) -> tuple[float, float] | None:
    """Coordonnées de secours pour les communes sans GPS (dict de l'énoncé)."""
    key = normalize(name)
    for city, (lat, lon) in config.missing_cities_lat_lon.items():
        if normalize(city) == key:
            return float(lat), float(lon)
    return None


def get_commune_coords(name: str, departement: str) -> tuple[float, float]:
    """Retourne (lat, lon) pour une commune d'un département donné.

    Priorité : coordonnées du centre, puis de la mairie, puis dictionnaire de
    secours. Lève ``LookupError`` si la commune est introuvable et
    ``ValueError`` si elle existe mais n'a aucune coordonnée exploitable."""
    dept = str(departement).strip().zfill(2) if str(departement).strip().isdigit() else str(departement).strip()
    df = load_communes()
    key = normalize(name)

    match = df[(df["_key"] == key) & (df[config.COM_DEPT] == dept)]
    if match.empty:
        # Repli direct sur le dictionnaire avant d'abandonner.
        fb = _fallback_coords(name)
        if fb is not None:
            return fb
        raise LookupError(
            f"Commune « {name} » introuvable dans le département {dept}."
        )

    row = match.iloc[0]
    for lat_col, lon_col in (
        (config.COM_LAT, config.COM_LON),
        (config.COM_LAT_FALLBACK, config.COM_LON_FALLBACK),
    ):
        lat, lon = row[lat_col], row[lon_col]
        if pd.notna(lat) and pd.notna(lon):
            return float(lat), float(lon)

    fb = _fallback_coords(name)
    if fb is not None:
        return fb
    raise ValueError(
        f"Commune « {name} » ({dept}) trouvée mais sans coordonnées GPS."
    )


def list_communes(departement: str) -> list[str]:
    """Liste triée des noms de communes d'un département (pour l'UI)."""
    dept = str(departement).strip().zfill(2) if str(departement).strip().isdigit() else str(departement).strip()
    df = load_communes()
    names = df.loc[df[config.COM_DEPT] == dept, config.COM_NAME]
    return sorted(names.unique().tolist())
