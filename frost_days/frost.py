"""Cœur métier : sélection de la station et statistiques de jours de gel."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from frost_days import config
from frost_days.stations import list_stations, rank_by_distance
from frost_days.weather import load_station_tn, normalize_dept


class NoReliableStationError(RuntimeError):
    """Aucune station ne respecte le seuil de complétude sur la plage demandée."""


@dataclass
class FrostStats:
    """Résultat complet d'une requête de jours de gel."""

    commune: str
    departement: str
    start: pd.Timestamp
    end: pd.Timestamp
    station_id: str
    station_name: str
    distance_km: float
    missing_ratio: float
    total_frost_days: int
    avg_frost_days_per_year: float
    frost_days_per_year: pd.Series      # index = année, valeur = nb de jours de gel
    per_day_of_year: pd.DataFrame       # index = "MM-DD", cols count/observed/freq


def is_frost(tn: pd.Series) -> pd.Series:
    """Masque booléen des jours de gel (TN <= 0). Les NaN comptent comme False."""
    return tn <= config.FROST_THRESHOLD


def missing_ratio(tn: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> float:
    """Part de jours manquants de TN sur [start, end] (jours attendus = calendrier)."""
    expected = (end.normalize() - start.normalize()).days + 1
    if expected <= 0:
        return 1.0
    available = int(tn.notna().sum())
    return max(0.0, 1.0 - available / expected)


def select_station(
    departement: str | int,
    lat: float,
    lon: float,
    start: pd.Timestamp,
    end: pd.Timestamp,
    method: str = "haversine",
) -> tuple[pd.Series, dict]:
    """Retourne (série TN de la station retenue, infos station).

    Parcourt les stations par distance croissante et retient la première dont le
    taux de valeurs manquantes est ≤ ``MAX_MISSING_RATIO``."""
    dept = normalize_dept(departement)
    stations = rank_by_distance(list_stations(dept), lat, lon, method=method)

    best_partial = None  # meilleure station vue, même si trop incomplète
    for _, st in stations.head(config.MAX_CANDIDATE_STATIONS).iterrows():
        tn = load_station_tn(dept, st[config.COL_STATION], start, end)
        ratio = missing_ratio(tn, start, end)
        info = {
            "station_id": str(st[config.COL_STATION]),
            "station_name": str(st[config.COL_NAME]),
            "distance_km": float(st["distance_km"]),
            "missing_ratio": ratio,
        }
        if ratio <= config.MAX_MISSING_RATIO:
            return tn, info
        if best_partial is None:
            best_partial = (tn, info)

    raise NoReliableStationError(
        "Aucune station fiable (≤ "
        f"{config.MAX_MISSING_RATIO:.0%} de valeurs manquantes) trouvée pour "
        f"cette commune sur la plage demandée."
        + (
            f" Station la plus proche : {best_partial[1]['station_name']} "
            f"({best_partial[1]['missing_ratio']:.0%} de manquants)."
            if best_partial
            else ""
        )
    )


def _per_day_of_year(tn: pd.Series) -> pd.DataFrame:
    """Stats par jour de l'année (hors 29 février).

    Pour chaque "MM-DD" : nb d'années de gel (absolu), nb d'années observées, et
    fréquence relative = gel / années observées."""
    df = pd.DataFrame({"tn": tn.to_numpy()}, index=pd.DatetimeIndex(tn.index))
    df["mmdd"] = df.index.strftime("%m-%d")
    df["year"] = df.index.year
    df = df[df["mmdd"] != "02-29"]            # 29 février non pertinent
    df["frost"] = df["tn"] <= config.FROST_THRESHOLD
    df["observed"] = df["tn"].notna()

    grouped = df.groupby("mmdd")
    out = pd.DataFrame(
        {
            "count_gel": grouped["frost"].sum().astype(int),
            "n_annees_observees": grouped["observed"].sum().astype(int),
        }
    )
    out["freq_relative"] = (
        out["count_gel"] / out["n_annees_observees"].replace(0, pd.NA)
    ).astype("float64")
    return out.sort_index()


def compute_stats(
    commune: str,
    departement: str | int,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    *,
    lat: float | None = None,
    lon: float | None = None,
    method: str = "haversine",
) -> FrostStats:
    """Calcule toutes les statistiques de jours de gel pour une commune.

    Si ``lat``/``lon`` ne sont pas fournis, ils sont résolus via le référentiel
    des communes (import différé pour garder ce module testable isolément)."""
    start = pd.Timestamp(start)
    end = pd.Timestamp(end)
    if end < start:
        raise ValueError("La date de fin doit être postérieure à la date de début.")

    if lat is None or lon is None:
        from frost_days.communes import get_commune_coords

        lat, lon = get_commune_coords(commune, departement)

    tn, info = select_station(departement, lat, lon, start, end, method=method)

    frost_mask = is_frost(tn)
    total = int(frost_mask.sum())

    per_year = frost_mask.groupby(tn.index.year).sum().astype(int)
    per_year.index.name = "year"
    avg_per_year = float(per_year.mean()) if not per_year.empty else 0.0

    return FrostStats(
        commune=commune,
        departement=normalize_dept(departement),
        start=start,
        end=end,
        station_id=info["station_id"],
        station_name=info["station_name"],
        distance_km=info["distance_km"],
        missing_ratio=info["missing_ratio"],
        total_frost_days=total,
        avg_frost_days_per_year=avg_per_year,
        frost_days_per_year=per_year,
        per_day_of_year=_per_day_of_year(tn),
    )
