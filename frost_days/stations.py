"""Stations météo : liste par département et classement par distance à une commune."""

from __future__ import annotations

import numpy as np
import pandas as pd

from frost_days import config
from frost_days.weather import load_department_tn

EARTH_RADIUS_KM = 6371.0088


def haversine(lat1: float, lon1: float, lat2, lon2):
    """Distance(s) Haversine en km. ``lat2``/``lon2`` peuvent être des arrays."""
    lat1, lon1 = np.radians(lat1), np.radians(lon1)
    lat2, lon2 = np.radians(lat2), np.radians(lon2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def list_stations(departement: str | int) -> pd.DataFrame:
    """Stations uniques du département : NUM_POSTE, NOM_USUEL, LAT, LON, _dept.

    On ne garde que les stations dont les coordonnées sont renseignées. La colonne
    ``_dept`` mémorise le département d'origine (utile quand on combine plusieurs
    départements : elle indique dans quel fichier lire la série TN de la station)."""
    from frost_days.weather import normalize_dept

    dept = normalize_dept(departement)
    df = load_department_tn(dept)
    stations = (
        df[[config.COL_STATION, config.COL_NAME, config.COL_LAT, config.COL_LON]]
        .dropna(subset=[config.COL_LAT, config.COL_LON])
        .drop_duplicates(subset=[config.COL_STATION])
        .reset_index(drop=True)
    )
    stations["_dept"] = dept
    return stations


def candidate_departments(
    lat: float, lon: float, radius_km: float = config.NEIGHBOR_RADIUS_KM
) -> list[str]:
    """Départements à explorer autour d'une commune (approche pilotée par les données).

    On retient tout département possédant au moins une commune dans ``radius_km``
    autour du point : le département de la commune et, pour les communes en bordure,
    les départements voisins — afin de ne pas rater une station limitrophe plus proche.
    """
    from frost_days.communes import load_communes  # import différé (évite un cycle)

    communes = load_communes()
    dist = haversine(
        lat,
        lon,
        communes[config.COM_LAT].to_numpy(),
        communes[config.COM_LON].to_numpy(),
    )
    near = communes.loc[dist <= radius_km, config.COM_DEPT]
    return sorted(d for d in near.dropna().unique())


def list_stations_multi(departements) -> pd.DataFrame:
    """Stations uniques sur plusieurs départements (concaténation, sans doublon)."""
    frames = [list_stations(d) for d in departements]
    if not frames:
        return pd.DataFrame(
            columns=[config.COL_STATION, config.COL_NAME, config.COL_LAT, config.COL_LON, "_dept"]
        )
    return (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset=[config.COL_STATION])
        .reset_index(drop=True)
    )


def rank_by_distance(
    stations: pd.DataFrame,
    lat: float,
    lon: float,
    method: str = "haversine",
) -> pd.DataFrame:
    """Renvoie les stations triées par distance croissante (colonne ``distance_km``).

    ``method`` :
    - ``"haversine"`` (défaut) : précis, recommandé par l'énoncé.
    - ``"kdtree"`` : pré-tri rapide (scipy) sur les coordonnées en degrés, puis
      distance Haversine recalculée pour les colonnes finales.
    """
    if stations.empty:
        return stations.assign(distance_km=pd.Series(dtype="float64"))

    lats = stations[config.COL_LAT].to_numpy()
    lons = stations[config.COL_LON].to_numpy()

    if method == "kdtree":
        from scipy.spatial import cKDTree

        tree = cKDTree(np.column_stack([lats, lons]))
        # Tri par voisinage approximatif (degrés), puis distance réelle exacte.
        order = tree.query([lat, lon], k=len(stations))[1]
        order = np.atleast_1d(order)
        ranked = stations.iloc[order].copy()
        ranked["distance_km"] = haversine(
            lat, lon, ranked[config.COL_LAT].to_numpy(), ranked[config.COL_LON].to_numpy()
        )
        return ranked.reset_index(drop=True)

    distances = haversine(lat, lon, lats, lons)
    ranked = stations.copy()
    ranked["distance_km"] = distances
    return ranked.sort_values("distance_km").reset_index(drop=True)
