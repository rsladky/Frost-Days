"""Tests unitaires du cœur métier (sans accès réseau)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from frost_days import config
from frost_days.frost import (
    _per_day_of_year,
    is_frost,
    missing_ratio,
)


def make_tn(dates, values) -> pd.Series:
    return pd.Series(values, index=pd.DatetimeIndex(dates), name="TN")


# --- is_frost : seuil à 0 °C ---------------------------------------------------

def test_is_frost_threshold():
    tn = make_tn(
        ["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-04"],
        [-5.0, 0.0, 0.1, np.nan],
    )
    mask = is_frost(tn)
    # Seuil STRICT (TN < 0) : 0.0 n'est PAS un gel, NaN non plus.
    assert mask.tolist() == [True, False, False, False]


def test_is_frost_count():
    tn = make_tn(pd.date_range("2020-01-01", periods=5), [-1, -2, 3, 0, 10])
    # -1 et -2 gèlent ; 0 ne gèle pas (seuil strict).
    assert int(is_frost(tn).sum()) == 2


# --- missing_ratio -------------------------------------------------------------

def test_missing_ratio_complete():
    idx = pd.date_range("2020-01-01", "2020-01-31")
    tn = make_tn(idx, [1.0] * len(idx))
    start, end = pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-31")
    assert missing_ratio(tn, start, end) == 0.0


def test_missing_ratio_half_missing():
    # 31 jours attendus, 15 présents -> ~51 % manquants
    idx = pd.date_range("2020-01-01", periods=15)
    tn = make_tn(idx, [1.0] * 15)
    start, end = pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-31")
    ratio = missing_ratio(tn, start, end)
    assert ratio == pytest.approx(1 - 15 / 31)
    assert ratio > config.MAX_MISSING_RATIO


def test_missing_ratio_counts_nan_as_missing():
    idx = pd.date_range("2020-01-01", "2020-01-10")
    tn = make_tn(idx, [1.0] * 5 + [np.nan] * 5)
    start, end = pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-10")
    assert missing_ratio(tn, start, end) == pytest.approx(0.5)


# --- _per_day_of_year ----------------------------------------------------------

def test_per_day_of_year_relative_frequency():
    # 31 mars sur 4 ans : gel en 2014 et 2016, pas en 2015/2017 -> 2/4 = 50 %
    dates = [f"{y}-03-31" for y in (2014, 2015, 2016, 2017)]
    tn = make_tn(dates, [-1.0, 2.0, -0.5, 5.0])
    out = _per_day_of_year(tn)
    assert out.loc["03-31", "count_gel"] == 2
    assert out.loc["03-31", "n_annees_observees"] == 4
    assert out.loc["03-31", "freq_relative"] == pytest.approx(0.5)


def test_per_day_of_year_excludes_feb_29():
    dates = ["2020-02-29", "2020-02-28", "2021-02-28"]
    tn = make_tn(dates, [-1.0, -1.0, -1.0])
    out = _per_day_of_year(tn)
    assert "02-29" not in out.index
    assert "02-28" in out.index


def test_per_day_of_year_missing_year_excluded_from_denominator():
    # 3 années dans l'index mais une valeur NaN -> 2 années observées
    dates = ["2014-01-15", "2015-01-15", "2016-01-15"]
    tn = make_tn(dates, [-2.0, np.nan, -3.0])
    out = _per_day_of_year(tn)
    assert out.loc["01-15", "n_annees_observees"] == 2
    assert out.loc["01-15", "count_gel"] == 2
    assert out.loc["01-15", "freq_relative"] == pytest.approx(1.0)
