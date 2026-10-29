"""Pluviométrie des derniers jours par code postal.

Sources (open data, sans clé API) :
- geo.api.gouv.fr : code postal -> commune, département, coordonnées
- data.gouv.fr : "Données climatologiques de base - quotidiennes" (Météo-France),
  uniquement le fichier récent (2 dernières années, mis à jour chaque jour)

Lancer : streamlit run app.py
"""
import re
from datetime import date

import altair as alt
import numpy as np
import pandas as pd
import requests
import streamlit as st

GEO_API = "https://geo.api.gouv.fr/communes"
DATASET_API = "https://www.data.gouv.fr/api/2/datasets/6569b51ae64326786e4e8e1a/resources/"
# RR = pluie (mm), TN / TX = température min / max du jour (°C)
COLONNES = ["NUM_POSTE", "NOM_USUEL", "LAT", "LON", "AAAAMMJJ", "RR", "TN", "TX"]


@st.cache_data(ttl=86400)
def chercher_communes(code_postal):
    r = requests.get(GEO_API, params={"codePostal": code_postal,
                                      "fields": "nom,codeDepartement,centre"}, timeout=10)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=86400)
def url_fichier_recent(dep):
    """URL du fichier pluie/température/vent du département couvrant l'année en cours."""
    page = DATASET_API + "?page_size=100&type=main"
    while page:
        data = requests.get(page, timeout=30).json()
        for res in data["data"]:
            titre = res["title"]
            annees = [int(a) for a in re.findall(r"\d{4}", titre)]
            if (f"departement_{dep}_" in titre and "RR-T-Vent" in titre
                    and annees and max(annees) >= date.today().year):
                return res["url"]
        page = data.get("next_page")
    raise RuntimeError(f"Fichier récent introuvable pour le département {dep}")


@st.cache_data(ttl=3 * 3600, show_spinner=False)  # le fichier est mis à jour quotidiennement
def charger_departement(dep):
    """Relevés quotidiens (pluie, températures) des stations du département."""
    df = pd.read_csv(url_fichier_recent(dep), sep=";", usecols=COLONNES, dtype={"NUM_POSTE": str})
    df["date"] = pd.to_datetime(df["AAAAMMJJ"].astype(str), format="%Y%m%d")
    return df.drop(columns="AAAAMMJJ")


def stations_proches(df, lat, lon, n=5):
    """Les n stations de df les plus proches du point (lat, lon)."""
    stations = (df.groupby(["NUM_POSTE", "NOM_USUEL"])
                       .agg(LAT=("LAT", "first"), LON=("LON", "first"), fin=("date", "max"))
                       .reset_index())
    la1, lo1, la2, lo2 = map(np.radians, [lat, lon, stations.LAT, stations.LON])
    a = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    stations["km"] = 6371 * 2 * np.arcsin(np.sqrt(a))
    return stations.nsmallest(n, "km")


def axe_jours(**options):
    """Axe des dates (format jj/mm). Un axe temporel s'étire sur toute la largeur."""
    return alt.X("yearmonthdate(date):T", title=None,
                 axis=alt.Axis(format="%d/%m", labelAngle=-45), **options)


INFO_DATE = alt.Tooltip("date:T", title="Date", format="%d/%m/%Y")
BARRE = alt.RelativeBandSize(0.8)  # chaque barre occupe 80 % de la largeur d'un jour


# --- Interface ---------------------------------------------------------------
st.set_page_config(page_title="Pluviométrie", page_icon="🌧️")
st.title("🌧️ Pluviométrie récente")

col1, col2 = st.columns(2)
cp = col1.text_input("Code postal", max_chars=5)
nb_jours = col2.number_input("Nombre de jours", 1, 365, 15)
if not re.fullmatch(r"\d{5}", cp or ""):
    st.stop()

communes = chercher_communes(cp)
if not communes:
    st.error("Aucune commune trouvée pour ce code postal.")
    st.stop()

commune = st.selectbox("Commune", communes, format_func=lambda c: c["nom"])
lon, lat = commune["centre"]["coordinates"]
dep = commune["codeDepartement"]
dep = "20" if dep in ("2A", "2B") else dep  # Météo-France regroupe la Corse en "20"

with st.spinner(f"Chargement des relevés Météo-France ({dep})…"):
    df = charger_departement(dep)

depuis = pd.Timestamp(date.today()) - pd.Timedelta(days=nb_jours)
periode = df[df.date >= depuis]
avec_pluie = periode.dropna(subset=["RR"])
avec_temp = periode.dropna(subset=["TN", "TX"])

proches = stations_proches(avec_pluie, lat, lon)
if proches.empty:
    st.warning("Aucune station avec des relevés sur cette période.")
    st.stop()

station = st.selectbox(
    "Station météo",
    proches.to_dict("records"),
    format_func=lambda s: f"{s['NOM_USUEL']} – {s['km']:.1f} km (dernier relevé {s['fin']:%d/%m})",
)

pluie = avec_pluie[avec_pluie.NUM_POSTE == station["NUM_POSTE"]].set_index("date")["RR"].sort_index()

# --- Pluie ---
st.subheader("🌧️ Pluie")
c1, c2, c3 = st.columns(3)
c1.metric("Cumul", f"{pluie.sum():.1f} mm")
c2.metric("Jours de pluie (≥ 1 mm)", int((pluie >= 1).sum()))
c3.metric("Jour le plus pluvieux", f"{pluie.max():.1f} mm", pluie.idxmax().strftime("%d/%m"),
          delta_color="off")

graph = pluie.rename("mm").reset_index()
st.altair_chart(
    alt.Chart(graph).mark_bar(width=BARRE).encode(
        x=axe_jours(),
        y=alt.Y("mm:Q", title="Pluie (mm)"),
        tooltip=[INFO_DATE, alt.Tooltip("mm:Q", title="Pluie (mm)")],
    ),
    use_container_width=True,  # toute la largeur de la page
)
st.caption(f"{len(pluie)} jours relevés sur {nb_jours} – dernier relevé le {pluie.index.max():%d/%m/%Y}.")

# --- Température ---
st.subheader("🌡️ Température")
temps = pd.DataFrame()
if station["NUM_POSTE"] in set(avec_temp.NUM_POSTE):
    num_temp = station["NUM_POSTE"]
elif not avec_temp.empty:
    # Beaucoup de stations ne mesurent que la pluie : on prend la plus proche qui mesure la température
    st_temp = stations_proches(avec_temp, lat, lon, n=1).iloc[0]
    num_temp = st_temp["NUM_POSTE"]
    st.caption(f"Cette station ne mesure pas la température : relevés de "
               f"{st_temp['NOM_USUEL']} ({st_temp['km']:.1f} km).")
else:
    st.info("Aucune station du département ne mesure la température sur cette période.")

if not avec_temp.empty:
    temps = avec_temp[avec_temp.NUM_POSTE == num_temp].set_index("date")[["TN", "TX"]].sort_index()
    temps["TM"] = (temps.TN + temps.TX) / 2  # moyenne journalière (convention Météo-France)

    c1, c2, c3 = st.columns(3)
    c1.metric("Moyenne", f"{temps.TM.mean():.1f} °C")
    c2.metric("Min relevée", f"{temps.TN.min():.1f} °C", temps.TN.idxmin().strftime("%d/%m"),
              delta_color="off")
    c3.metric("Max relevée", f"{temps.TX.max():.1f} °C", temps.TX.idxmax().strftime("%d/%m"),
              delta_color="off")

    graph = temps.reset_index()
    base = alt.Chart(graph).encode(
        tooltip=[INFO_DATE,
                 alt.Tooltip("TN:Q", title="Min (°C)"),
                 alt.Tooltip("TM:Q", title="Moyenne (°C)", format=".1f"),
                 alt.Tooltip("TX:Q", title="Max (°C)")],
    )
    plage = base.mark_bar(width=BARRE, opacity=0.35, color="#f28e2b").encode(
        x=axe_jours(), y=alt.Y("TN:Q", title="°C", scale=alt.Scale(zero=False)), y2="TX:Q")
    # bandPosition=0.5 : point de la moyenne au milieu de la barre du jour
    moyenne = base.mark_line(point=True, color="#d62728").encode(
        x=axe_jours(bandPosition=0.5), y="TM:Q")
    st.altair_chart(plage + moyenne, use_container_width=True)
    st.caption("Barre : de la min à la max du jour – ligne : moyenne.")

# --- Détail ---
with st.expander("Détail jour par jour"):
    detail = pd.concat([pluie.rename("Pluie (mm)"),
                        temps.reindex(columns=["TN", "TM", "TX"]).rename(columns={"TN": "Min (°C)", "TM": "Moy. (°C)", "TX": "Max (°C)"})],
                       axis=1).sort_index(ascending=False)
    detail.index = detail.index.strftime("%d/%m/%Y")
    st.dataframe(detail.round(1))

st.caption("Source : Météo-France via data.gouv.fr")