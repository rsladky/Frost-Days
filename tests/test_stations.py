"""Tests des algorithmes de distance et de classement des stations.

Ces tests prouvent le bon fonctionnement de :
- ``haversine`` (distance à vol d'oiseau sur la sphère terrestre) ;
- ``rank_by_distance`` avec les deux méthodes ``haversine`` et ``kdtree``.

Aucun accès réseau : on fournit directement un DataFrame de stations synthétiques.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from frost_days import config
from frost_days.stations import haversine, rank_by_distance

# Point de référence : centre de Paris.
PARIS = (48.8566, 2.3522)

# Distances "terrain" connues (km), pour caler la précision de Haversine.
LYON = (45.7640, 4.8357)
MARSEILLE = (43.2965, 5.3698)
LONDON = (51.5074, -0.1278)


def make_stations(rows: list[tuple[str, str, float, float]]) -> pd.DataFrame:
    """Construit un DataFrame de stations au format attendu par le code."""
    return pd.DataFrame(
        rows,
        columns=[config.COL_STATION, config.COL_NAME, config.COL_LAT, config.COL_LON],
    )


# Jeu de stations autour de Paris, distances nettement séparées => l'ordre est le
# même pour Haversine et KDTree (pas de quasi-égalité où les deux pourraient diverger) :
#   PROCHE < LUXEMBOURG < ORLY < LYON < MARSEILLE
STATIONS = make_stations(
    [
        ("00000001", "PROCHE", 48.8600, 2.3500),      # ~0,4 km
        ("00000002", "LUXEMBOURG", 48.8448, 2.3385),  # ~1,7 km
        ("00000003", "ORLY", 48.7233, 2.3794),        # ~15 km
        ("00000004", "LYON", *LYON),                  # ~392 km
        ("00000005", "MARSEILLE", *MARSEILLE),        # ~661 km
    ]
)


# ---------------------------------------------------------------------------
# Haversine : exactitude, symétrie, vectorisation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "a, b, expected_km, tol",
    [
        (PARIS, LYON, 392, 5),
        (PARIS, MARSEILLE, 661, 8),
        (PARIS, LONDON, 343, 5),
    ],
)
def test_haversine_known_distances(a, b, expected_km, tol):
    """Distances réelles connues entre grandes villes (référence ~ km)."""
    assert haversine(a[0], a[1], b[0], b[1]) == pytest.approx(expected_km, abs=tol)


def test_haversine_symmetric():
    """d(A, B) == d(B, A)."""
    d1 = haversine(PARIS[0], PARIS[1], LYON[0], LYON[1])
    d2 = haversine(LYON[0], LYON[1], PARIS[0], PARIS[1])
    assert d1 == pytest.approx(d2)


def test_haversine_zero_on_same_point():
    assert haversine(*PARIS, PARIS[0], PARIS[1]) == pytest.approx(0.0, abs=1e-9)


def test_haversine_vectorized_matches_scalar():
    """L'appel vectorisé (arrays) donne les mêmes valeurs que les appels scalaires."""
    lats = np.array([LYON[0], MARSEILLE[0], LONDON[0]])
    lons = np.array([LYON[1], MARSEILLE[1], LONDON[1]])
    vect = haversine(PARIS[0], PARIS[1], lats, lons)
    scal = np.array([haversine(PARIS[0], PARIS[1], la, lo) for la, lo in zip(lats, lons)])
    assert vect.shape == (3,)
    np.testing.assert_allclose(vect, scal)


def test_haversine_never_exceeds_half_earth_circumference():
    """Borne physique : deux points sur Terre sont à ≤ ~20 015 km l'un de l'autre."""
    # Antipodes approximatifs.
    d = haversine(0.0, 0.0, 0.0, 180.0)
    assert d == pytest.approx(20015, abs=10)


# ---------------------------------------------------------------------------
# rank_by_distance — méthode Haversine
# ---------------------------------------------------------------------------

def test_haversine_ranking_order():
    """Le classement Haversine respecte l'ordre de distance attendu."""
    ranked = rank_by_distance(STATIONS, *PARIS, method="haversine")
    assert ranked[config.COL_NAME].tolist() == [
        "PROCHE",
        "LUXEMBOURG",
        "ORLY",
        "LYON",
        "MARSEILLE",
    ]


def test_haversine_ranking_distances_sorted():
    """La colonne distance_km est triée par ordre croissant."""
    ranked = rank_by_distance(STATIONS, *PARIS, method="haversine")
    distances = ranked["distance_km"].to_numpy()
    assert np.all(np.diff(distances) >= 0)


def test_nearest_station_is_proche():
    """La station la plus proche du centre de Paris est bien 'PROCHE' (~0,5 km)."""
    ranked = rank_by_distance(STATIONS, *PARIS, method="haversine")
    assert ranked.iloc[0][config.COL_NAME] == "PROCHE"
    assert ranked.iloc[0]["distance_km"] < 1.0


# ---------------------------------------------------------------------------
# rank_by_distance — méthode KDTree
# ---------------------------------------------------------------------------

def test_kdtree_finds_same_nearest_station():
    """KDTree et Haversine désignent la même station la plus proche."""
    hav = rank_by_distance(STATIONS, *PARIS, method="haversine")
    kdt = rank_by_distance(STATIONS, *PARIS, method="kdtree")
    assert kdt.iloc[0][config.COL_STATION] == hav.iloc[0][config.COL_STATION]


def test_kdtree_full_order_matches_haversine():
    """Sur un jeu sans ambiguïté, KDTree retrouve l'ordre exact de Haversine."""
    hav = rank_by_distance(STATIONS, *PARIS, method="haversine")
    kdt = rank_by_distance(STATIONS, *PARIS, method="kdtree")
    assert (
        kdt[config.COL_STATION].tolist() == hav[config.COL_STATION].tolist()
    )


def test_both_methods_return_same_stations():
    """Les deux méthodes renvoient le même ENSEMBLE de stations (aucune perte)."""
    hav = rank_by_distance(STATIONS, *PARIS, method="haversine")
    kdt = rank_by_distance(STATIONS, *PARIS, method="kdtree")
    assert set(kdt[config.COL_STATION]) == set(hav[config.COL_STATION])
    assert len(kdt) == len(STATIONS)


def test_distance_km_identical_per_station_across_methods():
    """Pour une station donnée, la distance_km affichée est la même quelle que
    soit la méthode (KDTree recalcule bien la vraie distance Haversine)."""
    hav = rank_by_distance(STATIONS, *PARIS, method="haversine").set_index(config.COL_STATION)
    kdt = rank_by_distance(STATIONS, *PARIS, method="kdtree").set_index(config.COL_STATION)
    for station_id in hav.index:
        assert hav.loc[station_id, "distance_km"] == pytest.approx(
            kdt.loc[station_id, "distance_km"]
        )


# ---------------------------------------------------------------------------
# Haversine vs KDTree : pourquoi l'énoncé recommande Haversine
# ---------------------------------------------------------------------------

# Deux stations à distance quasi égale de Paris mais dans des directions différentes.
# BOURGET est plus au nord, ORLY plus à l'est. Un degré de longitude est plus court
# qu'un degré de latitude (facteur cos(latitude) ≈ 0,66 à Paris), donc :
#   - Haversine (vraie distance) : BOURGET est LA PLUS PROCHE (~14,1 km < ~14,9 km) ;
#   - KDTree (distance euclidienne en degrés bruts) : classe ORLY en premier, à tort.
CLOSE_PAIR = make_stations(
    [
        ("00000010", "ORLY", 48.7233, 2.3794),
        ("00000011", "BOURGET", 48.9694, 2.4414),
    ]
)


def test_haversine_picks_truly_closest_on_near_tie():
    """Sur une quasi-égalité, Haversine désigne la station réellement la plus proche."""
    ranked = rank_by_distance(CLOSE_PAIR, *PARIS, method="haversine")
    # Vérité terrain : BOURGET est bien à une distance plus courte qu'ORLY.
    d_orly = haversine(*PARIS, 48.7233, 2.3794)
    d_bourget = haversine(*PARIS, 48.9694, 2.4414)
    assert d_bourget < d_orly
    assert ranked.iloc[0][config.COL_NAME] == "BOURGET"


def test_kdtree_can_diverge_from_haversine_on_near_tie():
    """KDTree (euclidien en degrés) peut se tromper sur une quasi-égalité.

    Ce test documente la limite de KDTree et justifie le choix de Haversine par
    défaut : ici KDTree place ORLY en premier alors que BOURGET est plus proche."""
    kdt = rank_by_distance(CLOSE_PAIR, *PARIS, method="kdtree")
    hav = rank_by_distance(CLOSE_PAIR, *PARIS, method="haversine")
    assert kdt.iloc[0][config.COL_NAME] == "ORLY"      # choix euclidien (degrés)
    assert hav.iloc[0][config.COL_NAME] == "BOURGET"   # choix géographiquement correct


# ---------------------------------------------------------------------------
# Cas limites
# ---------------------------------------------------------------------------

def test_empty_stations_returns_empty_with_distance_column():
    empty = make_stations([])
    for method in ("haversine", "kdtree"):
        out = rank_by_distance(empty, *PARIS, method=method)
        assert out.empty
        assert "distance_km" in out.columns


def test_single_station():
    one = make_stations([("00000001", "SEULE", 48.0, 2.0)])
    for method in ("haversine", "kdtree"):
        out = rank_by_distance(one, *PARIS, method=method)
        assert len(out) == 1
        assert out.iloc[0][config.COL_NAME] == "SEULE"
        assert out.iloc[0]["distance_km"] > 0
