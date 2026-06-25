"""Génère le fichier météo COMPLET (« le reste ») pour les 6 communes de validation.

Les exports fournis par l'enseignant (`*_short.csv`) ne couvrent que la
première portion de la série de la station retenue. Ce script utilise le programme
(sélection de station + règle de gel) pour reproduire ces fichiers et produire la
suite manquante, sur une fenêtre fixe 2013-01-01 → 2024-12-31 (clippée à la
disponibilité réelle de la station).

Usage : uv run python scripts/generate_validation.py
"""

from __future__ import annotations

import glob
import os

import pandas as pd

from frost_days.frost import is_frost, select_station
from frost_days.weather import load_department_tn

from validate import VALIDATION_DIR, CITY_REF, REF_SUFFIX, dept_of, parse_filename, resolve_city

OUT_DIR = "data/validation/generated"
WINDOW_START = pd.Timestamp("2013-01-01")
WINDOW_END = pd.Timestamp("2024-12-31")

OUTPUT_COLUMNS = [
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


def station_metadata(station_id: str) -> dict:
    """Nom/lat/lon/alti d'une station, lus dans le fichier de son département."""
    dept_station = dept_of(station_id)
    df = load_department_tn(dept_station)
    row = df[df["NUM_POSTE"] == str(station_id)].iloc[0]
    # ALTI n'est pas chargée par load_department_tn (colonnes restreintes) :
    # on la relit directement depuis le .csv.gz mis en cache.
    from frost_days import config

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
        "station_name": str(row["NOM_USUEL"]),
        "latitude": float(row["LAT"]),
        "longitude": float(row["LON"]),
        "alti": alti,
    }


def build_full_dataframe(tn: pd.Series, station_id: str, meta: dict) -> pd.DataFrame:
    """Construit le DataFrame de sortie au format des fichiers de référence."""
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
    return out[OUTPUT_COLUMNS].sort_values("date").reset_index(drop=True)


def check_overlap(generated: pd.DataFrame, ref_path: str) -> dict:
    """Compare le DataFrame généré au fichier de référence sur leur partie commune."""
    ref = pd.read_csv(ref_path)
    merged = generated.merge(ref[["date", "tmin", "frost_day"]], on="date", how="inner", suffixes=("_gen", "_ref"))
    diff = (merged["tmin_gen"] - merged["tmin_ref"]).abs()
    frost_mismatch = (merged["frost_day_gen"] != merged["frost_day_ref"]).sum()
    return {
        "overlap_rows": len(merged),
        "ref_rows": len(ref),
        "max_tmin_diff": float(diff.max()) if len(merged) else float("nan"),
        "frost_mismatch": int(frost_mismatch),
    }


def generate_one(path: str, city_df: pd.DataFrame) -> dict:
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

    meta = station_metadata(station_id)
    generated = build_full_dataframe(tn, station_id, meta)

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"{commune}_{dept}_weather_data.csv")
    generated.to_csv(out_path, index=False)

    overlap = check_overlap(generated, path)

    return {
        "commune": commune,
        "dept": dept,
        "station_id": station_id,
        "ref_station": ref_station,
        "station_match": match,
        "rows": len(generated),
        "range": f"{generated['date'].iloc[0]}→{generated['date'].iloc[-1]}" if len(generated) else "—",
        "total_frost": int(generated["frost_day"].sum()),
        "out_path": out_path,
        **overlap,
    }


def main() -> int:
    files = sorted(glob.glob(os.path.join(VALIDATION_DIR, "*_[0-9][0-9]" + REF_SUFFIX)))
    if not files:
        print(f"Aucun fichier de validation dans {VALIDATION_DIR}")
        return 1

    city_df = pd.read_csv(CITY_REF)
    all_ok = True

    for f in files:
        r = generate_one(f, city_df)
        print(f"\n=== {r['commune']} ({r['dept']}) ===")
        print(f"  Station retenue : {r['station_id']}  (réf = {r['ref_station']})  "
              f"[{'OK' if r['station_match'] else 'KO'}]")
        print(f"  Fichier généré  : {r['out_path']}  ({r['rows']} lignes, {r['range']})")
        print(f"  Total gel (2013→2024) : {r['total_frost']}")
        ok_overlap = r["overlap_rows"] > 0 and r["max_tmin_diff"] <= 0.05 and r["frost_mismatch"] == 0
        print(
            f"  Recouvrement avec l'export de référence : {r['overlap_rows']}/{r['ref_rows']} lignes, "
            f"écart tmin max = {r['max_tmin_diff']:.3f} °C, frost_day écarts = {r['frost_mismatch']} "
            f"[{'OK' if ok_overlap else 'KO'}]"
        )
        all_ok = all_ok and r["station_match"] and ok_overlap

    print("\n" + "=" * 60)
    print("RÉSULTAT GLOBAL :", "✅ GÉNÉRATION VALIDE" if all_ok else "❌ DES ÉCARTS SUBSISTENT")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
