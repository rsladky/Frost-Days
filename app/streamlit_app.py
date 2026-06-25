"""Interface graphique Streamlit pour Frost-Days."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit.components.v1 import html as st_html
from concurrent.futures import ThreadPoolExecutor, as_completed

from frost_days import config
from frost_days.frost import NoReliableStationError, compute_stats

try:
    import folium
except Exception:  # pragma: no cover - optional dependency for UI
    folium = None

st.set_page_config(page_title="Frost-Days ❄️", page_icon="❄️", layout="wide")

# --- Palette « givre / dark mode » partagée entre CSS, Plotly et folium --------
ACCENT = "#4cc9f0"
ACCENT_2 = "#38bdf8"
BG = "#0e1117"
CARD_BG = "#1a1f2e"
BORDER = "#2a3142"
TEXT = "#e6edf3"
COLORWAY = ["#4cc9f0", "#38bdf8", "#3b82f6", "#818cf8", "#22d3ee"]

CUSTOM_CSS = f"""
<style>
/* --- Keyframes : dégradé animé, apparition, neige -------------------------- */
@keyframes gradientShift {{
    0% {{ background-position: 0% 50%; }}
    50% {{ background-position: 100% 50%; }}
    100% {{ background-position: 0% 50%; }}
}}
@keyframes fadeUp {{
    from {{ opacity: 0; transform: translateY(14px); }}
    to {{ opacity: 1; transform: translateY(0); }}
}}
@keyframes floatSnow {{
    0%   {{ transform: translate(0, -10vh) translateX(0); opacity: 0; }}
    10%  {{ opacity: .85; }}
    90%  {{ opacity: .6; }}
    100% {{ transform: translate(0, 110vh) translateX(20px); opacity: 0; }}
}}

/* Le contenu applicatif passe au-dessus de la neige */
.block-container {{
    padding-top: 1.2rem;
    position: relative;
    z-index: 1;
}}

/* Neige : conteneur plein écran, ne capte aucun clic */
.snow-layer {{
    position: fixed;
    inset: 0;
    overflow: hidden;
    pointer-events: none;
    z-index: 0;
}}
.snow-layer .flake {{
    position: absolute;
    top: -10px;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: radial-gradient(circle, {ACCENT} 0%, rgba(76,201,240,0) 70%);
    animation-name: floatSnow;
    animation-timing-function: linear;
    animation-iteration-count: infinite;
}}

/* --- Hero ------------------------------------------------------------------ */
.hero {{
    background: linear-gradient(135deg, {BG} 0%, {CARD_BG} 100%);
    border: 1px solid {BORDER};
    border-radius: 16px;
    padding: 1.6rem 2rem;
    margin-bottom: 1.4rem;
    animation: fadeUp .6s ease both;
}}
.hero h1 {{
    margin: 0;
    font-size: 2.1rem;
    font-weight: 800;
    background: linear-gradient(90deg, {ACCENT} 0%, {ACCENT_2} 50%, #818cf8 100%, {ACCENT} 150%);
    background-size: 200% auto;
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    animation: gradientShift 6s ease infinite;
}}
.hero p {{
    margin: .4rem 0 0;
    color: #9aa7b8;
    font-size: .95rem;
}}

/* --- Apparition en cascade des sections ------------------------------------ */
[data-testid="stMetric"],
[data-testid="stPlotlyChart"],
[data-testid="stDataFrame"],
.kpi-card,
.info-card,
h2, h3 {{
    animation: fadeUp .5s ease both;
}}

/* --- Cartes métriques (st.metric) ------------------------------------------ */
[data-testid="stMetric"] {{
    background: {CARD_BG};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 1rem 1.2rem;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.25);
    transition: transform .2s ease, box-shadow .2s ease;
}}
[data-testid="stMetric"]:hover {{
    transform: translateY(-4px);
    box-shadow: 0 8px 24px rgba(76, 201, 240, .18);
}}
[data-testid="stMetricValue"] {{
    color: {ACCENT};
}}

/* --- Hover-lift sur graphes et tableaux ------------------------------------ */
[data-testid="stPlotlyChart"], [data-testid="stDataFrame"] {{
    border-radius: 10px;
    border: 1px solid {BORDER};
    transition: transform .2s ease, box-shadow .2s ease;
}}
[data-testid="stPlotlyChart"]:hover, [data-testid="stDataFrame"]:hover {{
    transform: translateY(-4px);
    box-shadow: 0 8px 24px rgba(76, 201, 240, .14);
}}

/* --- Cartes KPI / info custom (HTML injecté) ------------------------------- */
.kpi-row {{
    display: flex;
    gap: 1rem;
    margin-bottom: 1rem;
}}
.kpi-card {{
    flex: 1;
    background: {CARD_BG};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 1rem 1.2rem;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.25);
    transition: transform .2s ease, box-shadow .2s ease;
}}
.kpi-card:hover {{
    transform: translateY(-4px);
    box-shadow: 0 8px 24px rgba(76, 201, 240, .18);
}}
.kpi-card .kpi-label {{
    color: #9aa7b8;
    font-size: .85rem;
    margin-bottom: .3rem;
}}
.kpi-card .kpi-value {{
    color: {ACCENT};
    font-size: 1.8rem;
    font-weight: 700;
}}
.info-card {{
    background: {CARD_BG};
    border: 1px solid {BORDER};
    border-left: 4px solid {ACCENT};
    border-radius: 10px;
    padding: .8rem 1.1rem;
    margin-bottom: 1rem;
    color: {TEXT};
}}

/* --- Onglets ---------------------------------------------------------------- */
[data-testid="stTabs"] button[data-baseweb="tab"] {{
    color: {TEXT};
}}
[data-testid="stTabs"] button[aria-selected="true"] {{
    color: {ACCENT};
    border-bottom-color: {ACCENT} !important;
}}

/* --- Sidebar ----------------------------------------------------------------- */
[data-testid="stSidebar"] {{
    background: {CARD_BG};
    border-right: 1px solid {BORDER};
}}

/* --- Boutons primaires -------------------------------------------------------- */
button[kind="primary"] {{
    background: linear-gradient(90deg, {ACCENT} 0%, {ACCENT_2} 100%);
    border: none;
    border-radius: 8px;
    font-weight: 600;
    transition: filter 0.15s ease-in-out, transform .15s ease;
}}
button[kind="primary"]:hover {{
    filter: brightness(1.15);
    transform: translateY(-2px);
}}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def _snow_html(n: int = 35) -> str:
    """Génère quelques flocons CSS discrets qui tombent en fond de page."""
    import random

    flakes = []
    for _ in range(n):
        left = random.uniform(0, 100)
        size = random.uniform(3, 7)
        duration = random.uniform(8, 18)
        delay = random.uniform(-15, 0)
        opacity = random.uniform(0.3, 0.8)
        flakes.append(
            f'<span class="flake" style="left:{left}vw; width:{size}px; height:{size}px; '
            f"animation-duration:{duration}s; animation-delay:{delay}s; "
            f'opacity:{opacity};"></span>'
        )
    return f'<div class="snow-layer">{"".join(flakes)}</div>'


# Neige injectée une seule fois, en tout début de page.
st.markdown(_snow_html(), unsafe_allow_html=True)


def _style_fig(fig):
    """Applique le thème sombre/givre partagé à une figure Plotly."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=COLORWAY,
        font=dict(color=TEXT),
        margin=dict(l=40, r=20, t=40, b=40),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(gridcolor=BORDER, zerolinecolor=BORDER)
    fig.update_yaxes(gridcolor=BORDER, zerolinecolor=BORDER)
    fig.update_layout(transition_duration=400)
    return fig


def _kpi_row(items: list[tuple[str, str, float]], height: int = 130) -> None:
    """Affiche une rangée de cartes KPI avec valeurs animées (0 -> cible).

    `items` est une liste de (label, texte_affiché, valeur_numérique_cible).
    """
    cards = "".join(
        f'<div class="kpi-card"><div class="kpi-label">{label}</div>'
        f'<div class="kpi-value" data-target="{target}" data-suffix="{suffix}">0</div></div>'
        for label, suffix, target in items
    )
    script = """
    <script>
    const cards = window.parent.document.querySelectorAll('.kpi-value[data-target]');
    cards.forEach((el) => {
        if (el.dataset.animated) return;
        el.dataset.animated = "1";
        const target = parseFloat(el.dataset.target);
        const suffix = el.dataset.suffix || "";
        const duration = 900;
        const start = performance.now();
        function step(now) {
            const progress = Math.min((now - start) / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3);
            const value = target * eased;
            el.textContent = (Number.isInteger(target) ? Math.round(value) : value.toFixed(1)) + suffix;
            if (progress < 1) requestAnimationFrame(step);
        }
        requestAnimationFrame(step);
    });
    </script>
    """
    st.markdown(f'<div class="kpi-row">{cards}</div>', unsafe_allow_html=True)
    st_html(script, height=0)


# --- Hero -------------------------------------------------------------------
st.markdown(
    """
    <div class="hero">
        <h1>❄️ Frost-Days — Jours de gel par commune</h1>
        <p>Données : Météo-France (climatologie quotidienne, data.gouv.fr).
        Un jour de gel = température minimale TN &lt; 0 °C.</p>
    </div>
    """,
    unsafe_allow_html=True,
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
    st.header("Navigation")
    page = st.radio(
        "Mode",
        ["❄️ Commune unique", "🗺️ Plusieurs communes"],
        label_visibility="collapsed",
    )

if page == "❄️ Commune unique":
    st.subheader("Paramètres — commune unique")
    p1, p2 = st.columns(2)
    commune = p1.text_input("Commune", value="Paris")
    departement = p2.text_input("Département", value="75")
    p3, p4, p5 = st.columns([1, 1, 1])
    debut = p3.date_input(
        "Début", value=dt.date(2014, 1, 1), min_value=dt.date(1950, 1, 1)
    )
    fin = p4.date_input(
        "Fin", value=dt.date(2023, 12, 31), min_value=dt.date(1950, 1, 1)
    )
    method = p5.selectbox("Méthode de distance", ["haversine", "kdtree"], index=0)
    go = st.button("Calculer", type="primary", use_container_width=True)

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

        st.markdown(
            f'<div class="info-card">📍 Station retenue : <strong>{res["station_name"]}</strong> '
            f'(#{res["station_id"]}) — {res["distance_km"]:.1f} km, '
            f'{res["missing_ratio"]:.0%} de valeurs manquantes.</div>',
            unsafe_allow_html=True,
        )

        _kpi_row(
            [
                ("Jours de gel (total)", "", float(res["total"])),
                ("Jours de gel (moyenne / an)", "", round(float(res["avg"]), 1)),
                ("Distance à la station", " km", round(float(res["distance_km"]), 1)),
            ]
        )

        # --- Jours de gel par année & saisonnalité — côte à côte -------------------
        per_year = res["per_year"].rename(columns={"year": "Année", "TN": "Jours de gel"})
        per_year.columns = ["Année", "Jours de gel"]
        fig_year = px.bar(per_year, x="Année", y="Jours de gel", text="Jours de gel")
        fig_year.update_traces(textposition="outside", marker_color=ACCENT)

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
        fig_day.update_traces(line_color=ACCENT_2)

        g1, g2 = st.columns(2)
        with g1:
            st.subheader("Jours de gel par année")
            st.plotly_chart(_style_fig(fig_year), use_container_width=True)
        with g2:
            st.subheader("Fréquence de gel par jour (hors 29 fév.)")
            st.plotly_chart(_style_fig(fig_day), use_container_width=True)

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

                m = folium.Map(
                    location=[lat_commune, lon_commune],
                    zoom_start=10,
                    tiles="CartoDB positron",
                )
                folium.Marker(
                    [lat_commune, lon_commune], popup=f"Commune: {commune}",
                    icon=folium.Icon(color="cadetblue"), tooltip=commune
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

elif page == "🗺️ Plusieurs communes":
    st.subheader("Paramètres — plusieurs communes")
    multi_communes = st.text_area(
        "Liste de communes (une par ligne, format: Commune,Département)",
        value="",
        placeholder="Exemple:\nParis,75\nLille,59\nBrest,29",
        help="Saisissez une ligne par commune avec son département (numéro ou code).",
    )
    d1, d2, d3 = st.columns([1, 1, 1])
    debut = d1.date_input(
        "Début", value=dt.date(2014, 1, 1), min_value=dt.date(1950, 1, 1), key="multi_debut"
    )
    fin = d2.date_input(
        "Fin", value=dt.date(2023, 12, 31), min_value=dt.date(1950, 1, 1), key="multi_fin"
    )
    method = d3.selectbox(
        "Méthode de distance", ["haversine", "kdtree"], index=0, key="multi_method"
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
                # Paralléliser les appels coûteux à `_run` pour plusieurs communes
                points = []
                errors = []
                parsed = []
                for ln in lines:
                    try:
                        if "," in ln:
                            name, dept = [p.strip() for p in ln.split(",", 1)]
                        elif ";" in ln:
                            name, dept = [p.strip() for p in ln.split(";", 1)]
                        else:
                            raise ValueError("Format invalide — attendre 'Commune,Département'.")
                        parsed.append((ln, name, dept))
                    except Exception as exc:
                        errors.append(str(exc))

                max_workers = min(8, max(1, len(parsed)))
                futures = {}
                with ThreadPoolExecutor(max_workers=max_workers) as exe:
                    for ln, name, dept in parsed:
                        futures[exe.submit(_run, name, dept, debut, fin, method)] = (ln, name, dept)

                    for fut in as_completed(futures):
                        ln, name, dept = futures[fut]
                        try:
                            res = fut.result()
                        except Exception as exc:
                            errors.append(f"Erreur pour {ln}: {exc}")
                            continue

                        try:
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
                            errors.append(f"Erreur post-traitement pour {ln}: {exc}")

                if errors:
                    for e in errors:
                        st.warning(e)

                if points:
                    st.markdown(
                        f'<div class="info-card">📊 {len(points)} commune(s) analysée(s) '
                        f"avec succès"
                        f"{f' — {len(errors)} erreur(s)' if errors else ''}.</div>",
                        unsafe_allow_html=True,
                    )
                    avg_total = sum(p.get("total") or 0 for p in points) / len(points)
                    max_total = max((p.get("total") or 0 for p in points), default=0)
                    _kpi_row(
                        [
                            ("Communes analysées", "", float(len(points))),
                            ("Moyenne jours de gel (total)", "", round(avg_total, 1)),
                            ("Maximum jours de gel (total)", "", float(max_total)),
                        ]
                    )

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
                        fig_tot.update_traces(textposition="outside", marker_color=ACCENT)
                        st.plotly_chart(_style_fig(fig_tot), use_container_width=True)

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
                            st.plotly_chart(_style_fig(fig_comp), use_container_width=True)
                    except Exception as exc:  # pragma: no cover - best-effort UI feature
                        st.warning(f"Impossible de tracer les graphiques comparatifs: {exc}")

                    # Centrer la carte sur la moyenne des communes
                    avg_lat = sum(p["commune_lat"] for p in points) / len(points)
                    avg_lon = sum(p["commune_lon"] for p in points) / len(points)
                    m = folium.Map(
                        location=[avg_lat, avg_lon],
                        zoom_start=6,
                        tiles="CartoDB positron",
                    )

                    for p in points:
                        folium.Marker(
                            [p["commune_lat"], p["commune_lon"]],
                            popup=f"Commune: {p['commune']} ({p['departement']})",
                            icon=folium.Icon(color="cadetblue"),
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
