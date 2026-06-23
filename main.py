import pandas as pd
from frost_days.weather import load_department_tn
from frost_days.frost import compute_stats
from frost_days import config


def func():
    stats = compute_stats("Paris", "75", "2014-01-01", "2023-12-31")
    df = load_department_tn("75")
    sub = df[df[config.COL_STATION] == stats.station_id]
    manuel_total = int(
        (
            (sub[config.COL_DATE].dt.year.between(2014, 2023))
            & (sub[config.COL_TN] <= 0)
        ).sum()
    )
    print("Code  :", stats.total_frost_days)
    print("Manuel:", manuel_total)
    assert stats.total_frost_days == manuel_total, "INCOHÉRENCE !"
    print("OK : les deux calculs concordent.")


if __name__ == "__main__":
    func()
