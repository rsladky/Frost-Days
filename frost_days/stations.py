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
    """Stations uniques du département : NUM_POSTE, NOM_USUEL, LAT, LON.

    On ne garde que les stations dont les coordonnées sont renseignées."""
    df = load_department_tn(departement)
    stations = (
        df[[config.COL_STATION, config.COL_NAME, config.COL_LAT, config.COL_LON]]
        .dropna(subset=[config.COL_LAT, config.COL_LON])
        .drop_duplicates(subset=[config.COL_STATION])
        .reset_index(drop=True)
    )
    return stations


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
