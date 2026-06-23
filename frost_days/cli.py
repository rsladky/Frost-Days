"""Interface en ligne de commande pour Frost-Days."""

from __future__ import annotations

import argparse
import sys

from frost_days import config
from frost_days.frost import NoReliableStationError, compute_stats


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="frost-days",
        description="Calcule le nombre de jours de gel pour une commune et une plage de dates.",
    )
    parser.add_argument("--commune", required=True, help="Nom de la commune (ex. \"Paris\").")
    parser.add_argument("--departement", required=True, help="Code département (ex. 75).")
    parser.add_argument("--debut", default=config.PERIOD_START, help="Date de début AAAA-MM-JJ.")
    parser.add_argument("--fin", default=config.PERIOD_END, help="Date de fin AAAA-MM-JJ.")
    parser.add_argument(
        "--method",
        choices=["haversine", "kdtree"],
        default="haversine",
        help="Méthode de calcul de distance station-commune.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Nombre de jours de l'année les plus gélifs à afficher.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        stats = compute_stats(
            args.commune,
            args.departement,
            args.debut,
            args.fin,
            method=args.method,
        )
    except (LookupError, ValueError, NoReliableStationError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1

    print(f"\nCommune : {stats.commune} ({stats.departement})")
    print(f"Plage   : {stats.start.date()} → {stats.end.date()}")
    print(
        f"Station : {stats.station_name} (#{stats.station_id}) "
        f"à {stats.distance_km:.1f} km — {stats.missing_ratio:.0%} de valeurs manquantes"
    )
    print("-" * 60)
    print(f"Jours de gel (total)        : {stats.total_frost_days}")
    print(f"Jours de gel (moyenne/an)   : {stats.avg_frost_days_per_year:.1f}")

    print("\nJours de gel par année :")
    for year, count in stats.frost_days_per_year.items():
        print(f"  {year} : {count}")

    print(f"\nTop {args.top} des jours de l'année les plus gélifs :")
    top = stats.per_day_of_year.sort_values(
        ["freq_relative", "count_gel"], ascending=False
    ).head(args.top)
    for mmdd, row in top.iterrows():
        freq = row["freq_relative"]
        freq_str = f"{freq:.0%}" if freq == freq else "n/a"  # NaN-safe
        print(
            f"  {mmdd} : {int(row['count_gel'])} gel(s) "
            f"sur {int(row['n_annees_observees'])} an(s) observé(s) ({freq_str})"
        )
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
