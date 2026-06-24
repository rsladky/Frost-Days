"""Interface graphique Streamlit pour Frost-Days."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit.components.v1 import html as st_html

from frost_days import config
from frost_days.frost import NoReliableStationError, compute_stats

try:
    import folium
except Exception:  # pragma: no cover - optional dependency for UI
    folium = None

st.set_page_config(page_title="Frost-Days ❄️", page_icon="❄️", layout="wide")

st.title("❄️ Frost-Days — Jours de gel par commune")
st.caption(
    "Données : Météo-France (climatologie quotidienne, data.gouv.fr). "
    "Un jour de gel = température minimale TN < 0 °C."
)


@st.cache_data(show_spinner=False)
def _run(commune: str, departement: str, debut: dt.date, fin: dt.date, method: str):
    """Appel mis en cache du calcul des statistiques."""
    stats = compute_stats(
        commune,
        departement,
        pd.Timestamp(debut),
        pd.Timestamp(fin),
        method=method,
    )
    # On renvoie des objets sérialisables pour le cache de Streamlit.
    return {
        "station_name": stats.station_name,
        "station_id": stats.station_id,
        "distance_km": stats.distance_km,
        "missing_ratio": stats.missing_ratio,
        "total": stats.total_frost_days,
        "avg": stats.avg_frost_days_per_year,
        "per_year": stats.frost_days_per_year.reset_index(),
        "per_day": stats.per_day_of_year.reset_index(),
    }


with st.sidebar:
    st.header("Paramètres")
    commune = st.text_input("Commune", value="Paris")
    departement = st.text_input("Département", value="75")
    col_a, col_b = st.columns(2)
    debut = col_a.date_input(
        "Début", value=dt.date(2014, 1, 1), min_value=dt.date(1950, 1, 1)
    )
    fin = col_b.date_input(
        "Fin", value=dt.date(2023, 12, 31), min_value=dt.date(1950, 1, 1)
    )
    method = st.selectbox("Méthode de distance", ["haversine", "kdtree"], index=0)
    go = st.button("Calculer", type="primary", use_container_width=True)

tab1, tab2 = st.tabs(["Commune unique", "Plusieurs communes"])

with tab1:
    if go:
        if fin < debut:
            st.error("La date de fin doit être postérieure à la date de début.")
            st.stop()

        try:
            with st.spinner("Téléchargement des données et calcul…"):
                res = _run(commune, departement, debut, fin, method)
        except (LookupError, ValueError, NoReliableStationError) as exc:
            st.error(str(exc))
            st.stop()

        st.success(
            f"Station retenue : **{res['station_name']}** (#{res['station_id']}) — "
            f"{res['distance_km']:.1f} km, {res['missing_ratio']:.0%} de valeurs manquantes."
        )

        c1, c2 = st.columns(2)
        c1.metric("Jours de gel (total)", res["total"])
        c2.metric("Jours de gel (moyenne / an)", f"{res['avg']:.1f}")

        # --- Jours de gel par année -------------------------------------------------
        st.subheader("Jours de gel par année")
        per_year = res["per_year"].rename(columns={"year": "Année", "TN": "Jours de gel"})
        per_year.columns = ["Année", "Jours de gel"]
        fig_year = px.bar(per_year, x="Année", y="Jours de gel", text="Jours de gel")
        fig_year.update_traces(textposition="outside")
        st.plotly_chart(fig_year, use_container_width=True)

        # --- Saisonnalité par jour de l'année --------------------------------------
        st.subheader("Fréquence de gel par jour de l'année (hors 29 février)")
        per_day = res["per_day"].rename(
            columns={
                "mmdd": "Jour",
                "count_gel": "Nb de gels",
                "n_annees_observees": "Années observées",
                "freq_relative": "Fréquence",
            }
        )
        per_day["Date"] = pd.to_datetime("2001-" + per_day["Jour"], format="%Y-%m-%d")
        per_day = per_day.sort_values("Date")
        fig_day = px.line(
            per_day,
            x="Date",
            y="Fréquence",
            hover_data=["Jour", "Nb de gels", "Années observées"],
        )
        fig_day.update_yaxes(tickformat=".0%", title="Fréquence de gel")
        fig_day.update_xaxes(dtick="M1", tickformat="%b", title="Mois")
        st.plotly_chart(fig_day, use_container_width=True)

        # --- Tableau détaillé -------------------------------------------------------
        st.subheader("Détail par jour de l'année")
        table = per_day[["Jour", "Nb de gels", "Années observées", "Fréquence"]].copy()
        table["Fréquence"] = (table["Fréquence"] * 100).round(1)
        st.dataframe(
            table.rename(columns={"Fréquence": "Fréquence (%)"}),
            use_container_width=True,
            hide_index=True,
        )

        # --- Carte interactive (commune + station retenue) ---------------------
        try:
            if folium is None:
                st.warning("Installez 'folium' pour afficher la carte : pip install folium")
            else:
                from frost_days.communes import get_commune_coords
                from frost_days.stations import list_stations

                lat_commune, lon_commune = get_commune_coords(commune, departement)
                stations = list_stations(departement)
                # Rechercher la station retenue dans la liste des stations
                match = stations[stations[config.COL_STATION].astype(str) == str(res["station_id"]) ]
                if not match.empty:
                    st_lat = float(match.iloc[0][config.COL_LAT])
                    st_lon = float(match.iloc[0][config.COL_LON])
                else:
                    # Repli : prendre la première station si l'id est introuvable
                    row = stations.iloc[0]
                    st_lat = float(row[config.COL_LAT])
                    st_lon = float(row[config.COL_LON])

                m = folium.Map(location=[lat_commune, lon_commune], zoom_start=10)
                folium.Marker(
                    [lat_commune, lon_commune], popup=f"Commune: {commune}",
                    icon=folium.Icon(color="blue"), tooltip=commune
                ).add_to(m)
                folium.Marker(
                    [st_lat, st_lon], popup=f"Station: {res['station_name']}",
                    icon=folium.Icon(color="red"), tooltip=res['station_name']
                ).add_to(m)

                st.subheader("Carte — commune et station retenue")
                st_html(m._repr_html_(), height=450)
        except Exception as exc:  # pragma: no cover - best-effort UI feature
            st.warning(f"Impossible d'afficher la carte: {exc}")

    else:
        st.info("Renseignez une commune, un département et une plage de dates, puis cliquez sur **Calculer**.")

with tab2:
    multi_communes = st.text_area(
        "Liste de communes (une par ligne, format: Commune,Département)",
        value="",
        placeholder="Exemple:\nParis,75\nLille,59\nBrest,29",
        help="Saisissez une ligne par commune avec son département (numéro ou code).",
    )
    multi_go = st.button("Afficher plusieurs sur la carte", use_container_width=True)

    # --- Recherche multiple et carte pour plusieurs communes --------------------
    if multi_go:
        if folium is None:
            st.warning("Installez 'folium' pour afficher la carte : pip install folium")
        else:
            from frost_days.communes import get_commune_coords
            from frost_days.stations import list_stations

            lines = [ln.strip() for ln in multi_communes.splitlines() if ln.strip()]
            if not lines:
                st.error("Aucune commune renseignée — utilisez le format 'Commune,Département' par ligne.")
            else:
                points = []
                errors = []
                for ln in lines:
                    try:
                        if "," in ln:
                            name, dept = [p.strip() for p in ln.split(",", 1)]
                        elif ";" in ln:
                            name, dept = [p.strip() for p in ln.split(";", 1)]
                        else:
                            raise ValueError("Format invalide — attendre 'Commune,Département'.")

                        # Réutiliser la même plage de dates et méthode que pour la recherche simple
                        try:
                            res = _run(name, dept, debut, fin, method)
                        except Exception as exc:
                            raise RuntimeError(f"Erreur pour {name} ({dept}): {exc}")

                        lat_commune, lon_commune = get_commune_coords(name, dept)
                        stations = list_stations(dept)
                        match = stations[stations[config.COL_STATION].astype(str) == str(res["station_id"]) ]
                        if not match.empty:
                            st_lat = float(match.iloc[0][config.COL_LAT])
                            st_lon = float(match.iloc[0][config.COL_LON])
                        else:
                            row = stations.iloc[0]
                            st_lat = float(row[config.COL_LAT])
                            st_lon = float(row[config.COL_LON])

                        points.append({
                            "commune": name,
                            "departement": dept,
                            "commune_lat": lat_commune,
                            "commune_lon": lon_commune,
                            "station_name": res["station_name"],
                            "station_id": res["station_id"],
                            "station_lat": st_lat,
                            "station_lon": st_lon,
                            "total": res.get("total"),
                            "avg": res.get("avg"),
                            "per_year": res.get("per_year"),
                            "per_day": res.get("per_day"),
                        })
                    except Exception as exc:
                        errors.append(str(exc))

                if errors:
                    for e in errors:
                        st.warning(e)

                if points:
                    # --- Graphiques comparatifs ---------------------------------
                    try:
                        totals_df = pd.DataFrame(
                            [
                                {"Commune": p["commune"], "Total": p.get("total", None), "Avg": p.get("avg", None)}
                                for p in points
                            ]
                        )
                        st.subheader("Comparaison entre communes")
                        fig_tot = px.bar(totals_df, x="Commune", y="Total", text="Total")
                        fig_tot.update_traces(textposition="outside")
                        st.plotly_chart(fig_tot, use_container_width=True)

                        # Série temporelle par année pour chaque commune
                        frames = []
                        for p in points:
                            df = p.get("per_year")
                            if df is None or df.empty:
                                continue
                            df_copy = df.copy()
                            # Normaliser les noms de colonnes
                            if "year" in df_copy.columns:
                                ycol = "year"
                            elif "Année" in df_copy.columns:
                                ycol = "Année"
                            else:
                                ycol = df_copy.columns[0]

                            if "TN" in df_copy.columns:
                                tcol = "TN"
                            elif "Jours de gel" in df_copy.columns:
                                tcol = "Jours de gel"
                            else:
                                tcol = [c for c in df_copy.columns if c != ycol][0]

                            df_copy = df_copy.rename(columns={ycol: "Année", tcol: "Jours de gel"})
                            df_copy["Commune"] = p["commune"]
                            frames.append(df_copy[["Année", "Jours de gel", "Commune"]])

                        if frames:
                            df_year = pd.concat(frames, ignore_index=True)
                            fig_comp = px.line(df_year, x="Année", y="Jours de gel", color="Commune", markers=True)
                            st.subheader("Évolution annuelle des jours de gel — comparaison")
                            st.plotly_chart(fig_comp, use_container_width=True)
                    except Exception as exc:  # pragma: no cover - best-effort UI feature
                        st.warning(f"Impossible de tracer les graphiques comparatifs: {exc}")

                    # Centrer la carte sur la moyenne des communes
                    avg_lat = sum(p["commune_lat"] for p in points) / len(points)
                    avg_lon = sum(p["commune_lon"] for p in points) / len(points)
                    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=6)

                    for p in points:
                        folium.Marker(
                            [p["commune_lat"], p["commune_lon"]],
                            popup=f"Commune: {p['commune']} ({p['departement']})",
                            icon=folium.Icon(color="blue"),
                            tooltip=p["commune"],
                        ).add_to(m)
                        folium.Marker(
                            [p["station_lat"], p["station_lon"]],
                            popup=f"Station: {p['station_name']} (#{p['station_id']})",
                            icon=folium.Icon(color="red", icon="info-sign"),
                            tooltip=p["station_name"],
                        ).add_to(m)

                    st.subheader("Carte — plusieurs communes et leurs stations")
                    st_html(m._repr_html_(), height=550)
    else:
        st.info("Renseignez une commune, un département et une plage de dates, puis cliquez sur **Calculer**.")
