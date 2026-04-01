"""
Magouilleuse — Outil de planification FTC France
Interface Streamlit principale.
"""

import sys
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

# Ajouter la racine au PYTHONPATH pour les imports relatifs
sys.path.insert(0, str(Path(__file__).parent))

from modules.affectation import lancer_affectation
from modules.planning import (
    generer_planning,
    planning_vers_dataframe,
    planning_vers_fichier_competitions,
)
from utils.helpers import (
    PENALITE_VACANCES_KM,
    ZONE_PAR_DEPARTEMENT,
    charger_vacances,
    exporter_excel,
    lire_fichier,
    samedis_dans_fenetre,
)

# ---------------------------------------------------------------------------
# Configuration Streamlit
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Magouilleuse — FTC France",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Sidebar — sélection du module
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🤖 Magouilleuse")
    st.caption("Outil de planification FTC France")
    st.divider()
    page = st.radio(
        "Module",
        ["🏠 Accueil", "📅 Planification", "🏆 Affectation"],
        label_visibility="collapsed",
    )

# ---------------------------------------------------------------------------
# Page Accueil
# ---------------------------------------------------------------------------

def page_accueil():
    st.title("🤖 Magouilleuse — Planification FTC France")
    st.markdown(
        """
        Bienvenue dans **Magouilleuse**, l'outil de planification des compétitions
        **FIRST Tech Challenge (FTC) France** pour la saison 2025-2026 / 2026-2027.

        ---

        ## Modules disponibles

        ### 📅 Module 1 — Planification
        Génère un calendrier de compétitions qui minimise les conflits avec les
        vacances scolaires françaises et maximise les samedis consécutifs.

        ### 🏆 Module 2 — Affectation
        Répartit les équipes dans les compétitions selon leurs vœux, en respectant
        les capacités et en priorisant les équipes qui ont le moins d'alternatives.

        ---
        ## Fichiers templates
        """
    )

    col1, col2, col3, col4 = st.columns(4)
    templates = {
        "Équipes": "data/templates/equipes_2025_2026.csv",
        "Compétitions": "data/templates/competitions_2026_2027.csv",
        "Compétitions avec dates": "data/templates/competitions_avec_dates_template.csv",
        "Vœux": "data/templates/voeux_2025_2026.csv",
    }
    for (nom, chemin), col in zip(templates.items(), [col1, col2, col3, col4]):
        p = Path(chemin)
        if p.exists():
            with col:
                with open(p, "rb") as f:
                    st.download_button(
                        label=f"📥 Template {nom}",
                        data=f.read(),
                        file_name=p.name,
                        mime="text/csv",
                    )



# ---------------------------------------------------------------------------
# Page Planification (Module 1)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _charger_geojson_departements():
    """Charge le GeoJSON simplifié des départements français (mis en cache)."""
    import json, urllib.request
    url = (
        "https://raw.githubusercontent.com/gregoiredavid/"
        "france-geojson/master/departements-version-simplifiee.geojson"
    )
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read())


def _afficher_reference_vacances(saison: str):
    """Expander pleine largeur avec choroplèthe par zone et tableau des dates."""
    try:
        vacances = charger_vacances(saison)
    except FileNotFoundError:
        return

    MOIS_FR = ["", "jan.", "fév.", "mars", "avr.", "mai", "juin",
               "juil.", "août", "sep.", "oct.", "nov.", "déc."]

    def fmt_periode(debut, fin):
        return f"Du {debut.day} {MOIS_FR[debut.month]} au {fin.day} {MOIS_FR[fin.month]} {fin.year}"

    with st.expander("📚 Référence — Zones & vacances scolaires", expanded=False):
        col_carte, col_tableau = st.columns([1, 1])

        with col_carte:
            import plotly.express as px
            try:
                geojson = _charger_geojson_departements()
                df_zones = pd.DataFrame([
                    {"code": code, "Zone": f"Zone {zone}"}
                    for code, zone in ZONE_PAR_DEPARTEMENT.items()
                ])
                fig = px.choropleth(
                    df_zones,
                    geojson=geojson,
                    locations="code",
                    featureidkey="properties.code",
                    color="Zone",
                    color_discrete_map={
                        "Zone A": "#95a5a6",
                        "Zone B": "#2c3e50",
                        "Zone C": "#e67e22",
                    },
                    category_orders={"Zone": ["Zone A", "Zone B", "Zone C"]},
                )
                fig.update_geos(fitbounds="locations", visible=False)
                fig.update_layout(
                    margin=dict(l=0, r=0, t=0, b=0),
                    height=350,
                    legend=dict(title="", orientation="v"),
                )
                st.plotly_chart(fig, use_container_width=True)
            except Exception:
                st.caption("Carte non disponible (connexion internet requise).")

        with col_tableau:
            NOMS_PERIODES = ["Toussaint", "Noël", "Hiver", "Printemps"]
            lignes = []
            nb_periodes = max(len(v) for v in vacances.values())
            for i in range(nb_periodes):
                row = {"Période": NOMS_PERIODES[i] if i < len(NOMS_PERIODES) else f"Période {i + 1}"}
                for zone in ["A", "B", "C"]:
                    periodes = vacances.get(zone, [])
                    row[f"Zone {zone}"] = fmt_periode(*periodes[i]) if i < len(periodes) else "—"
                lignes.append(row)
            st.dataframe(pd.DataFrame(lignes), use_container_width=True, hide_index=True)

def _afficher_calendrier_planning(result, competitions_df):
    """Affiche le calendrier des compétitions avec coloration par impact vacances."""
    if not result.dates:
        return

    comps_index = competitions_df.set_index("nom_competition")

    date_to_info = {}
    for det in result.detail_par_date:
        nom = det["competition"]
        sv = det["score_vacances"]
        cap = int(comps_index.loc[nom, "capacite_max"]) if nom in comps_index.index else 24
        nb_imp = len(det.get("equipes_impactees", []))
        if nb_imp == 0:
            color, bg, tc = "#27ae60", "#d5f5e3", "#1a5c33"
        elif nb_imp < cap / 2:
            color, bg, tc = "#e67e22", "#fde8d0", "#7d3c00"
        else:
            color, bg, tc = "#e74c3c", "#fadbd8", "#7b241c"
        date_to_info[det["date"]] = (nom, color, bg, tc, nb_imp)

    all_sats = samedis_dans_fenetre(min(result.dates), max(result.dates))

    from collections import defaultdict
    mois_to_sats = defaultdict(list)
    for s in all_sats:
        mois_to_sats[(s.year, s.month)].append(s)

    MOIS_FR = ["", "Jan.", "Fév.", "Mar.", "Avr.", "Mai", "Juin",
               "Juil.", "Août", "Sep.", "Oct.", "Nov.", "Déc."]

    html = ['<div style="font-family:sans-serif;padding:4px 0;">']
    for (annee, mois), sats in sorted(mois_to_sats.items()):
        html.append(
            f'<div style="margin-bottom:16px;">'
            f'<span style="font-size:13px;font-weight:600;color:#555;'
            f'text-transform:uppercase;letter-spacing:1px;">{MOIS_FR[mois]} {annee}</span>'
            f'<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:8px;">'
        )
        for s in sats:
            date_fr = s.strftime("%d/%m")
            if s in date_to_info:
                nom, color, bg, tc, nb_imp = date_to_info[s]
                label = nom.replace("Régionale ", "")
                imp_str = (
                    f'<span style="font-size:11px;opacity:0.75;">⚠️ {nb_imp} éq. impactée(s)</span>'
                    if nb_imp > 0 else
                    '<span style="font-size:11px;opacity:0.75;">✅ Aucune équipe impactée</span>'
                )
                html.append(
                    f'<div style="background:{bg};border-left:4px solid {color};'
                    f'border-radius:6px;padding:8px 12px;color:{tc};'
                    f'font-size:13px;min-width:130px;max-width:200px;">'
                    f'<strong>{date_fr}</strong><br>'
                    f'<span style="font-size:12px;">{label}</span><br>'
                    f'{imp_str}</div>'
                )
            else:
                html.append(
                    f'<div style="background:#ecf0f1;border-left:4px solid #bdc3c7;'
                    f'border-radius:6px;padding:8px 12px;color:#95a5a6;'
                    f'font-size:13px;min-width:80px;">'
                    f'<strong>{date_fr}</strong><br>'
                    f'<span style="font-size:12px;font-style:italic;">Creux</span></div>'
                )
        html.append('</div></div>')

    html.append(
        '<div style="display:flex;gap:20px;margin-top:4px;font-size:12px;'
        'color:#555;flex-wrap:wrap;">'
        '<span><span style="display:inline-block;width:10px;height:10px;'
        'background:#d5f5e3;border-left:3px solid #27ae60;margin-right:5px;'
        'vertical-align:middle;"></span>Aucun impact</span>'
        '<span><span style="display:inline-block;width:10px;height:10px;'
        'background:#fde8d0;border-left:3px solid #e67e22;margin-right:5px;'
        'vertical-align:middle;"></span>Impact &lt; ½ capacité</span>'
        '<span><span style="display:inline-block;width:10px;height:10px;'
        'background:#fadbd8;border-left:3px solid #e74c3c;margin-right:5px;'
        'vertical-align:middle;"></span>Impact ≥ ½ capacité</span>'
        '<span><span style="display:inline-block;width:10px;height:10px;'
        'background:#ecf0f1;border-left:3px solid #bdc3c7;margin-right:5px;'
        'vertical-align:middle;"></span>Samedi creux</span>'
        '</div></div>'
    )
    st.markdown("".join(html), unsafe_allow_html=True)


def page_planification():
    st.title("📅 Module 1 — Planification des compétitions")

    col_sais, _ = st.columns([1, 2])
    with col_sais:
        saison = st.selectbox(
            "Saison vacances scolaires",
            ["2026_2027", "2025_2026"],
            help="Sélectionnez la saison pour le calendrier des vacances.",
        )
    _afficher_reference_vacances(saison)

    st.divider()

    col_inputs, col_resultats = st.columns([1, 2])

    with col_inputs:
        st.subheader("Paramètres")

        fichier_comps = st.file_uploader(
            "Fichier compétitions (CSV/Excel)",
            type=["csv", "xlsx"],
            key="planning_comps",
        )
        fichier_equipes = st.file_uploader(
            "Fichier équipes (optionnel — améliore le scoring)",
            type=["csv", "xlsx"],
            key="planning_equipes",
        )

        col_d1, col_d2 = st.columns(2)
        with col_d1:
            debut = st.date_input(
                "Début de fenêtre",
                value=date(2026, 11, 1),
                min_value=date(2025, 9, 1),
                max_value=date(2027, 6, 30),
            )
        with col_d2:
            fin = st.date_input(
                "Fin de fenêtre",
                value=date(2027, 1, 31),
                min_value=date(2025, 9, 1),
                max_value=date(2027, 6, 30),
            )

        lambda_val = st.slider(
            "Pénalité trous (λ)",
            min_value=0.0,
            max_value=1.0,
            value=0.1,
            step=0.05,
            help="Coefficient de pénalité pour les samedis libres entre compétitions.",
        )

        lancer = st.button("🚀 Générer le planning", type="primary", use_container_width=True)

    with col_resultats:
        if not fichier_comps and not lancer:
            st.info("Chargez un fichier de compétitions et cliquez sur « Générer ».")
            return

        # Lecture des fichiers
        try:
            if fichier_comps:
                competitions_df = lire_fichier(
                    fichier_comps,
                    ["nom_competition", "adresse", "capacite_max"],
                    "fichier compétitions",
                )
                st.subheader("Compétitions chargées")
                st.dataframe(competitions_df, use_container_width=True)
        except ValueError as e:
            st.error(str(e))
            return

        equipes_df = None
        if fichier_equipes:
            try:
                equipes_df = lire_fichier(
                    fichier_equipes,
                    ["numero_equipe", "nom_equipe", "adresse"],
                    "fichier équipes",
                )
            except ValueError as e:
                st.warning(f"Fichier équipes ignoré : {e}")

        if lancer and fichier_comps:
            with st.spinner("Calcul du planning en cours…"):
                try:
                    result = generer_planning(
                        competitions_df=competitions_df,
                        equipes_df=equipes_df,
                        fenetre_debut=debut,
                        fenetre_fin=fin,
                        lambda_=lambda_val,
                        saison_vacances=saison,
                    )
                except Exception as e:
                    st.error(f"Erreur lors de la génération : {e}")
                    return

            # Alertes (hors "Zone non déterminée" regroupées en expander)
            alertes_zone = [a for a in result.alertes if "Zone non déterminée" in a]
            autres_alertes = [a for a in result.alertes if "Zone non déterminée" not in a]
            for alerte in autres_alertes:
                if alerte.startswith("⚠️") or alerte.startswith("🔴"):
                    st.error(alerte)
                elif alerte.startswith("🟠"):
                    st.warning(alerte)
                else:
                    st.info(alerte)
            if alertes_zone:
                with st.expander(f"⚠️ {len(alertes_zone)} adresse(s) sans zone détectée", expanded=False):
                    for a in alertes_zone:
                        st.caption(a)

            if not result.dates:
                return

            # Calendrier
            st.subheader("Calendrier")
            _afficher_calendrier_planning(result, competitions_df)

            # Tableau des résultats
            st.subheader("Détail")
            df_planning = planning_vers_dataframe(result)
            st.dataframe(df_planning, use_container_width=True)

            # Détail des équipes potentiellement impactées par compétition
            equipes_chargees = equipes_df is not None and not equipes_df.empty
            has_impactes = equipes_chargees and any(
                d.get("equipes_impactees") for d in result.detail_par_date
            )
            if equipes_chargees:
                label_expander = (
                    "🔍 Équipes potentiellement impactées par compétition"
                    if has_impactes
                    else "✅ Aucune équipe impactée par les vacances"
                )
                with st.expander(label_expander, expanded=has_impactes):
                    for det in result.detail_par_date:
                        equipes_imp = det.get("equipes_impactees", [])
                        date_str = det["date"].strftime("%d/%m/%Y")
                        if equipes_imp:
                            zones_str = ", ".join(det["zones_impactees"])
                            st.markdown(
                                f"**{det['competition']}** ({date_str}) "
                                f"— zones {zones_str} en vacances "
                                f"— **{len(equipes_imp)} équipe(s) impactée(s)**"
                            )
                            st.dataframe(
                                pd.DataFrame(equipes_imp),
                                use_container_width=True,
                                hide_index=True,
                            )
                        else:
                            st.markdown(
                                f"**{det['competition']}** ({date_str}) — ✅ Aucune équipe impactée"
                            )

            # Export Excel (vue lisible)
            sheets = {
                "Planning": df_planning,
                "Compétitions": competitions_df,
            }
            excel_bytes = exporter_excel(sheets)
            st.download_button(
                label="📥 Télécharger le planning (Excel)",
                data=excel_bytes,
                file_name="planning_ftc_france.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

            # Export CSV compatible Module 2
            df_comps_avec_dates = planning_vers_fichier_competitions(result, competitions_df)
            st.download_button(
                label="📥 Télécharger le fichier compétitions pour le Module 2 (CSV)",
                data=df_comps_avec_dates.to_csv(index=False, sep=";").encode("utf-8"),
                file_name="competitions_avec_dates.csv",
                mime="text/csv",
                help="Ce fichier peut être utilisé directement comme entrée du Module Affectation.",
            )


# ---------------------------------------------------------------------------
# Page Affectation (Module 2)
# ---------------------------------------------------------------------------

def _diagnostiquer_noms(voeux_df: pd.DataFrame, competitions_df: pd.DataFrame) -> None:
    """
    Affiche un diagnostic de correspondance entre les noms de compétitions
    dans le fichier compétitions et dans les vœux.
    Révèle les caractères invisibles, différences d'encodage, etc.
    """
    import unicodedata as _uc
    import re as _re

    def _normaliser(s: str) -> str:
        s = _uc.normalize("NFD", s)
        s = "".join(c for c in s if _uc.category(c) != "Mn")
        s = _re.sub(r"[\s\-_']+", " ", s)
        return s.strip().lower()

    noms_comps = [str(n).strip() for n in competitions_df["nom_competition"] if pd.notna(n)]
    voeu_cols = [c for c in voeux_df.columns if c.startswith("voeu_")]

    # Compter les voeux par compétition (exact match sur la valeur brute)
    voeux_plats = []
    for _, row in voeux_df.iterrows():
        for c in voeu_cols:
            v = str(row.get(c, "")).strip() if pd.notna(row.get(c)) else ""
            if v:
                voeux_plats.append(v)

    voeux_uniques = sorted(set(voeux_plats))

    # Table compétitions
    st.markdown("**Noms de compétitions (fichier compétitions) :**")
    rows_comp = []
    for nom in noms_comps:
        exact_count = sum(1 for v in voeux_plats if v == nom)
        rows_comp.append({
            "Nom affiché": nom,
            "repr()": repr(nom),
            "Nb vœux exacts": exact_count,
            "Normalisé": _normaliser(nom),
        })
    st.dataframe(pd.DataFrame(rows_comp), use_container_width=True)

    # Noms de compétitions présents dans les vœux mais pas dans le fichier
    noms_comps_set = set(noms_comps)
    noms_comps_norm = {_normaliser(n): n for n in noms_comps}
    inconnus = []
    for v in voeux_uniques:
        if v not in noms_comps_set:
            match_norm = noms_comps_norm.get(_normaliser(v))
            inconnus.append({
                "Vœu non reconnu": v,
                "repr()": repr(v),
                "Correspondance normalisée": match_norm or "❌ Aucune",
            })
    if inconnus:
        st.warning(f"⚠️ {len(inconnus)} valeur(s) de vœux sans correspondance exacte dans le fichier compétitions :")
        st.dataframe(pd.DataFrame(inconnus), use_container_width=True)
    else:
        st.success("✅ Tous les noms de vœux correspondent exactement à une compétition.")


def page_affectation():
    st.title("🏆 Module 2 — Affectation des équipes")

    # Initialiser le state
    if "affectation_resultats" not in st.session_state:
        st.session_state.affectation_resultats = []
    if "affectation_equipes" not in st.session_state:
        st.session_state.affectation_equipes = None
    if "affectation_competitions" not in st.session_state:
        st.session_state.affectation_competitions = None
    if "affectation_tour_actuel" not in st.session_state:
        st.session_state.affectation_tour_actuel = 0

    col_inputs, col_resultats = st.columns([1, 2])

    with col_inputs:
        st.subheader("Fichiers")

        fichier_voeux = st.file_uploader(
            "Fichier vœux (Excel/CSV issu du Forms)",
            type=["csv", "xlsx"],
            key="aff_voeux",
        )
        fichier_comps = st.file_uploader(
            "Fichier compétitions (avec dates si connues)",
            type=["csv", "xlsx"],
            key="aff_comps",
        )
        fichier_equipes = st.file_uploader(
            "Fichier équipes (pour les adresses — optionnel si dans les vœux)",
            type=["csv", "xlsx"],
            key="aff_equipes",
        )

        saison = st.selectbox(
            "Saison",
            ["2026_2027", "2025_2026"],
            key="aff_saison",
        )
        penalite = st.slider(
            "Pénalité vacances (km)",
            min_value=0,
            max_value=500,
            value=int(PENALITE_VACANCES_KM),
            step=50,
            help="Distance ajoutée à une alternative qui tombe pendant les vacances de l'équipe.",
        )

        st.divider()

        # Boutons séquentiels
        col_t1, col_t2, col_t3 = st.columns(3)
        btn_t1 = col_t1.button("Tour 1", type="primary", use_container_width=True)
        btn_t2 = col_t2.button(
            "Tour 2",
            type="secondary",
            use_container_width=True,
            disabled=st.session_state.affectation_tour_actuel < 1,
        )
        btn_t3 = col_t3.button(
            "Tour 3",
            type="secondary",
            use_container_width=True,
            disabled=st.session_state.affectation_tour_actuel < 2,
        )

        btn_reset = st.button("🔄 Réinitialiser", use_container_width=True)
        if btn_reset:
            st.session_state.affectation_resultats = []
            st.session_state.affectation_equipes = None
            st.session_state.affectation_competitions = None
            st.session_state.affectation_tour_actuel = 0
            st.rerun()

    with col_resultats:
        if not fichier_voeux or not fichier_comps:
            st.info("Chargez les fichiers vœux et compétitions, puis lancez le Tour 1.")
            return

        # Lecture des fichiers
        try:
            voeux_df = lire_fichier(
                fichier_voeux,
                ["numero_equipe", "nb_competitions_souhaitees", "voeu_1"],
                "fichier vœux",
            )
            competitions_df = lire_fichier(
                fichier_comps,
                ["nom_competition", "adresse", "capacite_max"],
                "fichier compétitions",
            )
        except ValueError as e:
            st.error(str(e))
            return

        equipes_df = None
        if fichier_equipes:
            try:
                equipes_df = lire_fichier(
                    fichier_equipes,
                    ["numero_equipe", "nom_equipe", "adresse"],
                    "fichier équipes",
                )
            except ValueError as e:
                st.warning(f"Fichier équipes ignoré : {e}")

        # Prévisualisation
        with st.expander("📋 Prévisualisation des données", expanded=False):
            st.subheader("Vœux")
            st.dataframe(voeux_df.head(10), use_container_width=True)
            st.subheader("Compétitions")
            st.dataframe(competitions_df, use_container_width=True)

        # Diagnostic correspondance noms
        with st.expander("🔍 Diagnostic correspondance noms compétitions", expanded=False):
            _diagnostiquer_noms(voeux_df, competitions_df)

        # Tour 1
        if btn_t1:
            with st.spinner("Calcul du Tour 1…"):
                try:
                    resultats, alertes_val = lancer_affectation(
                        voeux_df=voeux_df,
                        competitions_df=competitions_df,
                        equipes_df=equipes_df,
                        saison_vacances=saison,
                        penalite_km=float(penalite),
                        nb_tours=1,
                    )
                    st.session_state.affectation_resultats = resultats
                    # Reconstruire pour les tours suivants
                    st.session_state.affectation_voeux_df = voeux_df
                    st.session_state.affectation_competitions_df = competitions_df
                    st.session_state.affectation_equipes_df = equipes_df
                    st.session_state.affectation_saison = saison
                    st.session_state.affectation_penalite = penalite
                    st.session_state.affectation_tour_actuel = 1
                    for a in alertes_val:
                        st.warning(a)
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur Tour 1 : {e}")
                    return

        # Tours 2 et 3 (relancer avec plus de tours)
        if btn_t2 and st.session_state.affectation_tour_actuel >= 1:
            with st.spinner("Calcul du Tour 2…"):
                try:
                    resultats, _ = lancer_affectation(
                        voeux_df=st.session_state.affectation_voeux_df,
                        competitions_df=st.session_state.affectation_competitions_df,
                        equipes_df=st.session_state.affectation_equipes_df,
                        saison_vacances=st.session_state.affectation_saison,
                        penalite_km=float(st.session_state.affectation_penalite),
                        nb_tours=2,
                    )
                    st.session_state.affectation_resultats = resultats
                    st.session_state.affectation_tour_actuel = 2
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur Tour 2 : {e}")
                    return

        if btn_t3 and st.session_state.affectation_tour_actuel >= 2:
            with st.spinner("Calcul du Tour 3…"):
                try:
                    resultats, _ = lancer_affectation(
                        voeux_df=st.session_state.affectation_voeux_df,
                        competitions_df=st.session_state.affectation_competitions_df,
                        equipes_df=st.session_state.affectation_equipes_df,
                        saison_vacances=st.session_state.affectation_saison,
                        penalite_km=float(st.session_state.affectation_penalite),
                        nb_tours=3,
                    )
                    st.session_state.affectation_resultats = resultats
                    st.session_state.affectation_tour_actuel = 3
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur Tour 3 : {e}")
                    return

        # Affichage des résultats
        if st.session_state.affectation_resultats:
            _afficher_resultats_affectation(
                st.session_state.affectation_resultats,
                voeux_df,
                competitions_df,
                equipes_df,
                saison,
            )


def _afficher_resultats_affectation(
    resultats,
    voeux_df,
    competitions_df,
    equipes_df,
    saison,
):
    """Affiche les résultats de l'affectation."""

    # Alertes de l'algorithme
    alertes_debug = []
    for res in resultats:
        for a in res.alertes:
            if a.startswith("[DEBUG"):
                alertes_debug.append(a)
            elif "⚠️" in a or "🔴" in a:
                st.error(a)
            else:
                st.warning(a)

    if alertes_debug:
        with st.expander(f"🐛 Debug algorithme ({len(alertes_debug)} entrées)", expanded=True):
            for a in alertes_debug:
                st.code(a)

    # Métriques Tour 1
    res_t1 = resultats[0]
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric(
        "Taux vœu n°1 (Tour 1)",
        f"{res_t1.metriques.get('taux_voeu_1', 0):.1f}%",
    )
    col_m2.metric(
        "Taux satisfaction (Tour 1)",
        f"{res_t1.metriques.get('taux_satisfaction', 0):.1f}%",
    )
    total_aff = sum(len(r.nouvelles_affectations) for r in resultats)
    col_m3.metric("Total affectations", total_aff)

    # -----------------------------------------------------------------------
    # Agrégation directe depuis nouvelles_affectations (sans reconstruction)
    # Clé : nom_comp stripped → liste (tour, num_equipe)
    # -----------------------------------------------------------------------
    aff_par_comp: dict[str, list[tuple[int, int]]] = {}
    for res in resultats:
        for num, nom_comp in res.nouvelles_affectations.items():
            cle = str(nom_comp).strip()
            if cle not in aff_par_comp:
                aff_par_comp[cle] = []
            aff_par_comp[cle].append((res.tour, int(num)))

    tous_nums_affectes: set[int] = {
        num for paires in aff_par_comp.values() for (_, num) in paires
    }

    # -----------------------------------------------------------------------
    # Table de référence : num_equipe → {nom, adresse, voeux}
    # -----------------------------------------------------------------------
    info_equipes: dict[int, dict] = {}
    voeu_cols = [c for c in voeux_df.columns if c.startswith("voeu_")]
    for _, row in voeux_df.iterrows():
        num = int(row["numero_equipe"])
        voeux_liste = [
            str(row[c]).strip()
            for c in voeu_cols
            if pd.notna(row.get(c)) and str(row.get(c, "")).strip()
        ]
        info_equipes[num] = {
            "nom": str(row.get("nom_equipe", f"Équipe {num}")).strip()
                   if pd.notna(row.get("nom_equipe")) else f"Équipe {num}",
            "adresse": str(row.get("adresse", "")).strip()
                       if pd.notna(row.get("adresse")) else "",
            "voeux": voeux_liste,
        }
    if equipes_df is not None:
        for _, row in equipes_df.iterrows():
            num = int(row["numero_equipe"])
            info_equipes.setdefault(num, {"nom": "", "adresse": "", "voeux": []})
            info_equipes[num]["nom"] = str(row["nom_equipe"]).strip()
            info_equipes[num]["adresse"] = str(row["adresse"]).strip()

    # -----------------------------------------------------------------------
    # Équipes n'ayant pas obtenu leur 1er vœu au Tour 1
    # -----------------------------------------------------------------------
    lignes_pas_voeu1: list[dict] = []
    for num, nom_comp_aff in res_t1.nouvelles_affectations.items():
        info = info_equipes.get(int(num), {})
        voeux_eq = info.get("voeux", [])
        voeu1 = voeux_eq[0] if voeux_eq else ""
        if nom_comp_aff.lower().strip() != voeu1.lower().strip():
            # Trouver le rang réel du vœu attribué
            voeu_rang: int | str = "Fallback"
            for j, v in enumerate(voeux_eq, 1):
                if v.lower().strip() == nom_comp_aff.lower().strip():
                    voeu_rang = j
                    break
            lignes_pas_voeu1.append({
                "Numéro équipe": int(num),
                "Nom équipe": info.get("nom", f"Équipe {num}"),
                "Vœu n°1 souhaité": voeu1,
                "Compétition obtenue": nom_comp_aff,
                "Rang vœu obtenu": voeu_rang,
            })

    if lignes_pas_voeu1:
        label_t1 = f"⚠️ {len(lignes_pas_voeu1)} équipe(s) n'ont pas obtenu leur 1er vœu au Tour 1"
        with st.expander(label_t1, expanded=True):
            st.dataframe(
                pd.DataFrame(lignes_pas_voeu1).sort_values("Numéro équipe"),
                use_container_width=True,
                hide_index=True,
            )
    else:
        st.success("✅ Toutes les équipes ont obtenu leur 1er vœu au Tour 1.")

    # -----------------------------------------------------------------------
    # Diagnostic : compétitions sans affectation malgré des vœux
    # -----------------------------------------------------------------------
    noms_comps_valides = [
        str(n).strip() for n in competitions_df["nom_competition"] if pd.notna(n)
    ]
    comps_sans_aff = [n for n in noms_comps_valides if n not in aff_par_comp]
    if comps_sans_aff:
        # Vérifier si des équipes les avaient en vœux
        for nom_vide in comps_sans_aff:
            equipes_avec_ce_voeu = [
                int(row["numero_equipe"])
                for _, row in voeux_df.iterrows()
                if any(
                    str(row.get(c, "")).strip() == nom_vide
                    for c in voeu_cols
                )
            ]
            if equipes_avec_ce_voeu:
                st.warning(
                    f"⚠️ **{nom_vide}** : 0 équipe affectée alors que "
                    f"{len(equipes_avec_ce_voeu)} équipe(s) l'avaient en vœu. "
                    "Vérifiez que le nom de compétition dans les vœux correspond "
                    "exactement à celui du fichier compétitions."
                )

    # -----------------------------------------------------------------------
    # Onglets par compétition
    # -----------------------------------------------------------------------
    st.subheader("Résultats par compétition")

    if not noms_comps_valides:
        st.info("Aucune compétition trouvée dans le fichier.")
        return

    onglets = st.tabs(noms_comps_valides + ["Non affectées", "Résumé global"])
    sheets_export: dict[str, pd.DataFrame] = {}

    for i, nom_comp in enumerate(noms_comps_valides):
        with onglets[i]:
            equipes_ici = aff_par_comp.get(nom_comp, [])
            nb_aff = len(equipes_ici)

            mask = competitions_df["nom_competition"].str.strip() == nom_comp
            cap_vals = competitions_df.loc[mask, "capacite_max"]
            capacite = int(cap_vals.iloc[0]) if len(cap_vals) > 0 and pd.notna(cap_vals.iloc[0]) else 24

            st.metric(
                "Équipes affectées",
                f"{nb_aff} / {capacite}",
                delta=f"{round(nb_aff / capacite * 100)}% de remplissage" if capacite else "",
            )

            if equipes_ici:
                lignes = []
                nom_comp_lower = nom_comp.lower()
                for tour, num in sorted(equipes_ici, key=lambda x: (x[0], x[1])):
                    info = info_equipes.get(num, {})
                    voeux_eq = info.get("voeux", [])
                    # Correspondance souple (case-insensitive) pour voeu_rang
                    voeu_rang: int | str = "Fallback"
                    for j, v in enumerate(voeux_eq, 1):
                        if v.lower().strip() == nom_comp_lower:
                            voeu_rang = j
                            break
                    lignes.append({
                        "Numéro équipe": num,
                        "Nom équipe": info.get("nom", f"Équipe {num}"),
                        "Adresse": info.get("adresse", ""),
                        "Vœu n°": voeu_rang,
                        "Tour": tour,
                    })
                df_comp = pd.DataFrame(lignes)
                st.dataframe(df_comp, use_container_width=True)
                sheets_export[nom_comp[:31]] = df_comp
            else:
                st.info("Aucune équipe affectée.")
                sheets_export[nom_comp[:31]] = pd.DataFrame()

    # Onglet Non affectées
    with onglets[-2]:
        tous_nums = {int(row["numero_equipe"]) for _, row in voeux_df.iterrows()}
        non_aff_nums = tous_nums - tous_nums_affectes
        if not non_aff_nums:
            st.success("Toutes les équipes ont au moins une compétition ! ✅")
        else:
            st.error(f"{len(non_aff_nums)} équipe(s) sans compétition.")
            lignes_non = []
            for num in sorted(non_aff_nums):
                info = info_equipes.get(num, {})
                lignes_non.append({
                    "Numéro équipe": num,
                    "Nom équipe": info.get("nom", f"Équipe {num}"),
                    "Adresse": info.get("adresse", ""),
                })
            df_non = pd.DataFrame(lignes_non)
            st.dataframe(df_non, use_container_width=True)
            sheets_export["Non_affectées"] = df_non

    # Onglet Résumé global
    with onglets[-1]:
        lignes_resume = []
        for nom_comp_r, paires in sorted(aff_par_comp.items()):
            for tour, num in sorted(paires, key=lambda x: (x[0], x[1])):
                info = info_equipes.get(num, {})
                lignes_resume.append({
                    "Numéro équipe": num,
                    "Nom équipe": info.get("nom", f"Équipe {num}"),
                    "Tour": tour,
                    "Compétition": nom_comp_r,
                })
        df_resume = pd.DataFrame(lignes_resume)
        sheets_export["Résumé"] = df_resume
        st.dataframe(df_resume, use_container_width=True)

    # Export Excel
    if sheets_export:
        excel_bytes = exporter_excel(sheets_export)
        st.download_button(
            label="📥 Télécharger les affectations (Excel)",
            data=excel_bytes,
            file_name="affectations_ftc_france.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


# ---------------------------------------------------------------------------
# Routage principal
# ---------------------------------------------------------------------------

if page == "🏠 Accueil":
    page_accueil()
elif page == "📅 Planification":
    page_planification()
elif page == "🏆 Affectation":
    page_affectation()
