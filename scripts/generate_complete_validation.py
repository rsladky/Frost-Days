"""Génère le dossier `validation/` (consigne V2 de l'enseignant) :

1. Les 6 fichiers météo complets (`*_complete.csv`, ~4000 lignes/commune sur
   2013-2024) — mêmes communes que la validation, mais sans tronquer la série.
2. `city_df_complete.csv` — les ~35 000 communes de France avec la station de
   référence (la plus proche **valide**, même règle que ``select_station`` :
   ≤ 35 % de valeurs manquantes sur la fenêtre).
3. `stations_df_complete.csv` — le référentiel national des stations
   utilisées (NUM_POSTE, nom, coordonnées, altitude).

Calcule la complétude de toutes les stations françaises *une seule fois*
(par département) puis réutilise ce résultat pour les ~35 000 communes,
plutôt que de rappeler ``select_station`` (qui recharge les séries TN à
chaque appel) commune par commune.

Usage : uv run python scripts/generate_complete_validation.py
"""

from __future__ import annotations

import glob
import os
import time

import numpy as np
import pandas as pd

from frost_days import config
from frost_days.communes import load_communes
from frost_days.frost import is_frost, select_station
from frost_days.stations import candidate_departments, haversine
from frost_days.weather import load_department_tn, normalize_dept

from validate import CITY_REF, REF_SUFFIX, VALIDATION_DIR, dept_of, parse_filename, resolve_city

OUT_DIR = "validation"
WINDOW_START = pd.Timestamp("2013-01-01")
WINDOW_END = pd.Timestamp("2024-12-31")
EXPECTED_DAYS = (WINDOW_END - WINDOW_START).days + 1

WEATHER_OUTPUT_COLUMNS = [
    "station_id",
    "station_name",
    "latitude",
    "longitude",
    "alti",
    "date",
    "tmin",
    "frost_day",
    "year",
    "month",
    "day",
]

CITY_OUTPUT_COLUMNS = [
    "insee_code",
    "name",
    "dep_code",
    "dep_name",
    "lat",
    "lon",
    "closest_station_name",
    "closest_station_num_poste",
    "station_dept",
]

STATION_OUTPUT_COLUMNS = ["station_id", "station_name", "latitude", "longitude", "alti"]


# --- 1. Fichiers météo complets des 6 communes de validation -----------------


def generate_commune_weather_files() -> None:
    files = sorted(glob.glob(os.path.join(VALIDATION_DIR, "*_[0-9][0-9]" + REF_SUFFIX)))
    city_df = pd.read_csv(CITY_REF)

    for path in files:
        commune, dept = parse_filename(path)
        ref = pd.read_csv(path, nrows=1)
        ref_station = str(ref.station_id.iloc[0]).zfill(8)

        city = resolve_city(city_df, commune, dept)
        if city is not None:
            lat, lon = float(city["lat"]), float(city["lon"])
        else:
            from frost_days.communes import get_commune_coords

            lat, lon = get_commune_coords(commune, dept)

        tn, info = select_station(dept, lat, lon, WINDOW_START, WINDOW_END)
        station_id = info["station_id"]
        match = station_id == ref_station

        meta = _station_metadata(station_id)
        out = _build_weather_dataframe(tn, station_id, meta)

        os.makedirs(OUT_DIR, exist_ok=True)
        out_path = os.path.join(OUT_DIR, f"{commune}_{dept}_complete.csv")
        out.to_csv(out_path, index=False)

        print(
            f"  {commune} ({dept}) : station {station_id} "
            f"(réf={ref_station}) [{'OK' if match else 'KO'}] -> {out_path} "
            f"({len(out)} lignes)"
        )


def _station_metadata(station_id: str) -> dict:
    dept_station = dept_of(station_id)
    df = load_department_tn(dept_station)
    row = df[df[config.COL_STATION] == str(station_id)].iloc[0]
    raw = pd.read_csv(
        f"data/cache/Q_{dept_station}_previous_RR-T-Vent.csv.gz",
        sep=config.CSV_SEP,
        usecols=[config.COL_STATION, "ALTI"],
        dtype={config.COL_STATION: "string"},
        compression="gzip",
    )
    alti_row = raw[raw[config.COL_STATION] == str(station_id)]
    alti = float(alti_row["ALTI"].iloc[0]) if not alti_row.empty else float("nan")
    return {
        "station_name": str(row[config.COL_NAME]),
        "latitude": float(row[config.COL_LAT]),
        "longitude": float(row[config.COL_LON]),
        "alti": alti,
    }


def _build_weather_dataframe(tn: pd.Series, station_id: str, meta: dict) -> pd.DataFrame:
    dates = pd.DatetimeIndex(tn.index)
    out = pd.DataFrame(
        {
            "station_id": str(station_id).zfill(8),
            "station_name": meta["station_name"],
            "latitude": meta["latitude"],
            "longitude": meta["longitude"],
            "alti": meta["alti"],
            "date": dates.strftime("%Y-%m-%d"),
            "tmin": tn.to_numpy(),
        }
    )
    out["frost_day"] = is_frost(tn).to_numpy()
    out["year"] = dates.year
    out["month"] = dates.month
    out["day"] = dates.day
    return out[WEATHER_OUTPUT_COLUMNS].sort_values("date").reset_index(drop=True)


# --- 2 & 3. Référentiels nationaux : stations et communes --------------------


def build_national_station_tables(depts: list[str]) -> tuple[pd.DataFrame, pd.Series]:
    """Construit (stations_master, missing_ratio_par_station) sur tous les départements.

    ``stations_master`` : NUM_POSTE, NOM_USUEL, LAT, LON, ALTI, _dept.
    ``missing_ratio`` : Series indexée par NUM_POSTE, taux de TN manquant sur la
    fenêtre [WINDOW_START, WINDOW_END] (1.0 si la station n'a aucune donnée
    dans la fenêtre)."""
    station_frames = []
    ratio_frames = []

    for dept in depts:
        t0 = time.time()
        try:
            df = load_department_tn(dept)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{dept}] ignoré (téléchargement impossible: {exc})")
            continue

        meta = (
            df[[config.COL_STATION, config.COL_NAME, config.COL_LAT, config.COL_LON]]
            .dropna(subset=[config.COL_LAT, config.COL_LON])
            .drop_duplicates(subset=[config.COL_STATION])
            .reset_index(drop=True)
        )
        meta["_dept"] = dept

        # Altitude : pas chargée par load_department_tn (colonnes restreintes).
        raw_alti = pd.read_csv(
            f"data/cache/Q_{dept}_previous_RR-T-Vent.csv.gz",
            sep=config.CSV_SEP,
            usecols=[config.COL_STATION, "ALTI"],
            dtype={config.COL_STATION: "string"},
            compression="gzip",
        ).drop_duplicates(subset=[config.COL_STATION])
        meta = meta.merge(raw_alti, on=config.COL_STATION, how="left")

        window = df[(df[config.COL_DATE] >= WINDOW_START) & (df[config.COL_DATE] <= WINDOW_END)]
        available = window.groupby(config.COL_STATION)[config.COL_TN].count()
        ratio = 1.0 - (available.reindex(meta[config.COL_STATION]).fillna(0) / EXPECTED_DAYS)
        ratio.index = meta[config.COL_STATION].to_numpy()
        ratio = ratio.clip(lower=0.0, upper=1.0)

        station_frames.append(meta)
        ratio_frames.append(ratio)
        print(f"  [{dept}] {len(meta)} stations ({time.time()-t0:.1f}s)")

    stations_master = pd.concat(station_frames, ignore_index=True)
    missing_ratio = pd.concat(ratio_frames)
    missing_ratio = missing_ratio[~missing_ratio.index.duplicated(keep="first")]
    return stations_master, missing_ratio


def closest_valid_station_per_commune(
    communes: pd.DataFrame,
    stations_by_dept: dict[str, pd.DataFrame],
    missing_ratio: pd.Series,
) -> pd.DataFrame:
    """Pour chaque commune, la station valide la plus proche (≤ 35% manquants),
    avec repli sur la station la plus proche si aucune n'est valide (comme
    ``select_station``)."""
    names = []
    nums = []
    depts_out = []

    for row in communes.itertuples(index=False):
        candidate_depts = set(candidate_departments(row.lat, row.lon))
        candidate_depts.add(row.dep_code)
        frames = [stations_by_dept[d] for d in candidate_depts if d in stations_by_dept]
        if not frames:
            names.append(None)
            nums.append(None)
            depts_out.append(None)
            continue
        cand = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]

        dist = haversine(row.lat, row.lon, cand[config.COL_LAT].to_numpy(), cand[config.COL_LON].to_numpy())
        order = np.argsort(dist)[: config.MAX_CANDIDATE_STATIONS]

        chosen = None
        for idx in order:
            station_id = cand[config.COL_STATION].iat[idx]
            ratio = missing_ratio.get(station_id, 1.0)
            if ratio <= config.MAX_MISSING_RATIO:
                chosen = idx
                break
        if chosen is None:
            chosen = order[0]

        names.append(cand[config.COL_NAME].iat[chosen])
        nums.append(cand[config.COL_STATION].iat[chosen])
        depts_out.append(cand["_dept"].iat[chosen])

    out = communes.copy()
    out["closest_station_name"] = names
    out["closest_station_num_poste"] = nums
    out["station_dept"] = depts_out
    return out


def load_all_communes_for_city_df() -> pd.DataFrame:
    """Référentiel complet des communes avec coordonnées résolues (centre puis mairie)."""
    cols = [
        "code_insee",
        config.COM_NAME,
        config.COM_DEPT,
        "dep_nom",
        config.COM_LAT,
        config.COM_LON,
        config.COM_LAT_FALLBACK,
        config.COM_LON_FALLBACK,
    ]
    try:
        df = pd.read_parquet(config.COMMUNES_DIR / "communes.parquet", columns=cols)
    except ImportError:
        df = pd.read_csv(config.COMMUNES_DIR / "communes.csv.gz", usecols=cols)

    df[config.COM_DEPT] = df[config.COM_DEPT].astype(str).str.strip()
    lat = df[config.COM_LAT].fillna(df[config.COM_LAT_FALLBACK])
    lon = df[config.COM_LON].fillna(df[config.COM_LON_FALLBACK])

    out = pd.DataFrame(
        {
            "insee_code": df["code_insee"],
            "name": df[config.COM_NAME],
            "dep_code": df[config.COM_DEPT],
            "dep_name": df["dep_nom"],
            "lat": lat,
            "lon": lon,
        }
    )
    return out.dropna(subset=["lat", "lon"]).reset_index(drop=True)


def main() -> None:
    print("=== 1. Fichiers météo complets des 6 communes de validation ===")
    generate_commune_weather_files()

    print("\n=== 2. Référentiel national des stations (toutes données déjà en cache) ===")
    all_depts = sorted(load_communes()[config.COM_DEPT].dropna().unique().tolist())
    stations_master, missing_ratio = build_national_station_tables(all_depts)

    os.makedirs(OUT_DIR, exist_ok=True)
    # ``stations_master`` couvre tout l'historique Météo-France (depuis 1950, des
    # milliers de stations fermées depuis) : on ne publie que celles actives sur
    # la fenêtre étudiée (≥ 1 valeur TN sur 2013-2024), sinon le référentiel est
    # ~3x trop gros par rapport à ce qu'attend la consigne (~3000 lignes).
    active = stations_master[config.COL_STATION].map(missing_ratio).fillna(1.0) < 1.0
    stations_out = (
        stations_master.loc[active]
        .rename(
            columns={
                config.COL_STATION: "station_id",
                config.COL_NAME: "station_name",
                config.COL_LAT: "latitude",
                config.COL_LON: "longitude",
                "ALTI": "alti",
            }
        )[STATION_OUTPUT_COLUMNS]
        .drop_duplicates(subset=["station_id"])
        .sort_values("station_id")
        .reset_index(drop=True)
    )
    stations_path = os.path.join(OUT_DIR, "stations_df_complete.csv")
    stations_out.to_csv(stations_path, index=False)
    print(f"  {len(stations_out)} stations actives 2013-2024 (sur {len(stations_master)} au total) -> {stations_path}")

    print("\n=== 3. city_df_complete.csv (toutes les communes de France) ===")
    communes = load_all_communes_for_city_df()
    stations_by_dept = {d: g.reset_index(drop=True) for d, g in stations_master.groupby("_dept")}
    t0 = time.time()
    city_df = closest_valid_station_per_commune(communes, stations_by_dept, missing_ratio)
    print(f"  {len(city_df)} communes traitées en {time.time()-t0:.1f}s")

    city_path = os.path.join(OUT_DIR, "city_df_complete.csv")
    city_df[CITY_OUTPUT_COLUMNS].to_csv(city_path, index=False)
    print(f"  -> {city_path}")


if __name__ == "__main__":
    main()
