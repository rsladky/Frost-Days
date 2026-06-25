"""Validation du pipeline Frost-Days contre les exports de référence fournis.

Pour chaque commune de ``data/validation/validation/*_short.csv`` :

1. SÉLECTION  — la station retenue par mon code == la station de référence ?
2. PIPELINE   — les valeurs TN que je charge == celles de la référence (jours communs) ?
3. DÉFINITION — ma règle de gel (TN ≤ 0) reproduit la colonne ``frost_day`` ?
4. TOTAL      — mon total de jours de gel == celui de la référence ?

Usage : uv run python scripts/validate.py
"""

from __future__ import annotations

import glob
import os
import re

import pandas as pd

from frost_days.communes import get_commune_coords
from frost_days.frost import is_frost, select_station
from frost_days.weather import load_station_tn

VALIDATION_DIR = "data/validation/validation"
CITY_REF = os.path.join(VALIDATION_DIR, "city_df_short.csv")
TOL = 0.05  # tolérance °C pour comparer les TN (arrondis d'export)
REF_SUFFIX = "_short.csv"


def parse_filename(path: str) -> tuple[str, str]:
    """'Digne-les-Bains_04_short.csv' -> ('Digne-les-Bains', '04')."""
    base = os.path.basename(path).replace(REF_SUFFIX, "")
    m = re.match(r"^(.*)_(\w{2,3})$", base)
    return m.group(1), m.group(2)


def dept_of(num_poste: str) -> str:
    """Département d'une station à partir de son NUM_POSTE (8 chiffres)."""
    return str(num_poste).zfill(8)[:2]


def resolve_city(city_df: pd.DataFrame, label: str, dept: str) -> pd.Series | None:
    """Retrouve la commune dans city_df (nom exact, sinon 'commence par')."""
    same_dept = city_df[city_df["dep_code"].astype(str).str.zfill(2) == dept]
    exact = same_dept[same_dept["name"].str.lower() == label.lower()]
    if not exact.empty:
        return exact.iloc[0]
    starts = same_dept[same_dept["name"].str.lower().str.startswith(label.lower())]
    return starts.iloc[0] if not starts.empty else None


def check_city(path: str, city_df: pd.DataFrame) -> dict:
    commune, dept = parse_filename(path)
    ref = pd.read_csv(path, parse_dates=["date"])
    ref_station = str(ref.station_id.iloc[0]).zfill(8)
    ref_name = ref.station_name.iloc[0]
    start, end = ref.date.min(), ref.date.max()
    ref_total = int(ref.frost_day.sum())

    result = {
        "commune": commune,
        "dept": dept,
        "ref_station": ref_station,
        "ref_name": ref_name,
        "range": f"{start.date()}→{end.date()}",
        "ref_total": ref_total,
    }

    # --- 3. DÉFINITION : ma règle de gel reproduit-elle frost_day ? -----------
    ref_tn = pd.Series(ref.tmin.to_numpy(), index=pd.DatetimeIndex(ref.date))
    mine_flags = is_frost(ref_tn).to_numpy()
    result["def_mismatch"] = int((mine_flags != ref.frost_day.to_numpy()).sum())

    # --- 1. SÉLECTION : ma station la plus proche valide ----------------------
    # On part des coordonnées exactes utilisées par la référence (city_df) pour
    # comparer la sélection à périmètre identique.
    try:
        city = resolve_city(city_df, commune, dept)
        if city is not None:
            lat, lon = float(city["lat"]), float(city["lon"])
        else:
            # Commune absente de l'échantillon city_df : on résout via le code.
            lat, lon = get_commune_coords(commune, dept)
        _, info = select_station(dept, lat, lon, start, end)
        result["my_station"] = info["station_id"]
        result["my_name"] = info["station_name"]
        result["my_dist"] = info["distance_km"]
        result["station_match"] = info["station_id"] == ref_station
    except Exception as exc:  # noqa: BLE001 - on veut un rapport, pas un crash
        result["my_station"] = f"ERREUR: {exc}"
        result["station_match"] = False

    # --- 2. PIPELINE : mes TN == TN de référence (jours communs) -------------
    try:
        mine = load_station_tn(dept_of(ref_station), ref_station, start, end)
        joined = pd.DataFrame({"ref": ref_tn, "mine": mine}).dropna()
        diff = (joined["ref"] - joined["mine"]).abs()
        result["pipeline_common_days"] = len(joined)
        result["pipeline_max_diff"] = float(diff.max()) if len(joined) else float("nan")
        result["pipeline_ok"] = bool(len(joined) and (diff <= TOL).all())
    except Exception as exc:  # noqa: BLE001
        result["pipeline_ok"] = False
        result["pipeline_err"] = str(exc)

    # --- 4. TOTAL : mon total de gel sur la station de référence --------------
    # Calculé sur les jours fournis par la référence, avec MES valeurs TN.
    try:
        mine = load_station_tn(dept_of(ref_station), ref_station, start, end)
        aligned = mine.reindex(pd.DatetimeIndex(ref.date))
        result["my_total"] = int(is_frost(aligned).sum())
        result["total_match"] = result["my_total"] == ref_total
    except Exception:  # noqa: BLE001
        result["my_total"] = None
        result["total_match"] = False

    return result


def main() -> int:
    files = sorted(glob.glob(os.path.join(VALIDATION_DIR, "*_[0-9][0-9]" + REF_SUFFIX)))
    if not files:
        print(f"Aucun fichier de validation dans {VALIDATION_DIR}")
        return 1

    city_df = pd.read_csv(CITY_REF)
    rows = [check_city(f, city_df) for f in files]
    all_ok = True

    for r in rows:
        print(f"\n=== {r['commune']} ({r['dept']}) — {r['range']} ===")
        print(f"  Référence : {r['ref_name']} #{r['ref_station']} | total gel = {r['ref_total']}")

        ok_def = r["def_mismatch"] == 0
        print(f"  [{'OK ' if ok_def else 'KO '}] Définition gel : {r['def_mismatch']} écart(s) vs frost_day")

        ok_sel = r.get("station_match", False)
        print(
            f"  [{'OK ' if ok_sel else 'KO '}] Sélection station : {r.get('my_name', '?')} "
            f"#{r.get('my_station', '?')}"
            + (f" à {r['my_dist']:.2f} km" if "my_dist" in r else "")
        )

        ok_pipe = r.get("pipeline_ok", False)
        print(
            f"  [{'OK ' if ok_pipe else 'KO '}] Pipeline TN : "
            f"{r.get('pipeline_common_days', 0)} jours communs, "
            f"écart max = {r.get('pipeline_max_diff', float('nan')):.3f} °C"
            + (f" ({r['pipeline_err']})" if "pipeline_err" in r else "")
        )

        ok_tot = r.get("total_match", False)
        print(f"  [{'OK ' if ok_tot else 'KO '}] Total gel : moi = {r.get('my_total')} vs réf = {r['ref_total']}")

        all_ok = all_ok and ok_def and ok_sel and ok_pipe and ok_tot

    print("\n" + "=" * 60)
    print("RÉSULTAT GLOBAL :", "✅ TOUT EST VALIDE" if all_ok else "❌ DES ÉCARTS SUBSISTENT")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
