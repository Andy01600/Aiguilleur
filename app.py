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

from modules.affectation import (
    construire_competitions,
    construire_equipes,
    lancer_affectation,
    resultats_vers_dataframes,
)
from modules.planning import (
    generer_planning,
    planning_vers_dataframe,
    planning_vers_fichier_competitions,
    planning_vers_plotly,
)
from utils.helpers import (
    PENALITE_VACANCES_KM,
    charger_vacances,
    exporter_excel,
    lire_fichier,
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

    col1, col2, col3 = st.columns(3)
    templates = {
        "Équipes": "data/templates/equipes_2025_2026.csv",
        "Compétitions": "data/templates/competitions_2026_2027.csv",
        "Vœux": "data/templates/voeux_2025_2026.csv",
    }
    for (nom, chemin), col in zip(templates.items(), [col1, col2, col3]):
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

    st.divider()
    st.markdown(
        """
        ### Format des fichiers

        **Équipes** (`CSV/Excel`) : `numero_equipe`, `nom_equipe`, `adresse`

        **Compétitions** (`CSV/Excel`) : `nom_competition`, `adresse`, `capacite_max`,
        `date_forcee` *(optionnel, format YYYY-MM-DD)*

        **Vœux** (`CSV/Excel`) : `numero_equipe`, `horodatage` *(optionnel)*,
        `voeu_1` à `voeu_6` *(minimum 3 remplis)*, `nb_competitions_souhaitees`
        """
    )


# ---------------------------------------------------------------------------
# Page Planification (Module 1)
# ---------------------------------------------------------------------------

def page_planification():
    st.title("📅 Module 1 — Planification des compétitions")

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

        saison = st.selectbox(
            "Saison vacances scolaires",
            ["2026_2027", "2025_2026"],
            help="Sélectionnez la saison pour le calendrier des vacances.",
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

            # Alertes
            for alerte in result.alertes:
                if alerte.startswith("⚠️") or alerte.startswith("🔴"):
                    st.error(alerte)
                elif alerte.startswith("🟠"):
                    st.warning(alerte)
                else:
                    st.info(alerte)

            if not result.dates:
                return

            # Métriques
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("Score vacances", f"{result.score_vacances:.0f}")
            col_m2.metric("Samedis creux", result.nb_trous)
            col_m3.metric("Score total", f"{result.score_total:.2f}")

            # Graphique Plotly
            try:
                vacances = charger_vacances(saison)
            except FileNotFoundError:
                vacances = None
            fig = planning_vers_plotly(result, vacances)
            st.plotly_chart(fig, use_container_width=True)

            # Tableau des résultats
            df_planning = planning_vers_dataframe(result)
            st.dataframe(df_planning, use_container_width=True)

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
                data=df_comps_avec_dates.to_csv(index=False).encode("utf-8"),
                file_name="competitions_avec_dates.csv",
                mime="text/csv",
                help="Ce fichier peut être utilisé directement comme entrée du Module Affectation.",
            )


# ---------------------------------------------------------------------------
# Page Affectation (Module 2)
# ---------------------------------------------------------------------------

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
    dernier = resultats[-1]

    # Alertes
    for res in resultats:
        for a in res.alertes:
            if "⚠️" in a or "🔴" in a:
                st.error(a)
            else:
                st.warning(a)

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

    # Onglets par compétition
    st.subheader("Résultats par compétition")

    # Reconstruire les structures internes pour l'affichage
    try:
        from modules.affectation import construire_equipes as _ce, construire_competitions as _cc, lancer_affectation as _la
        # Relancer silencieusement pour avoir les objets Equipe et Competition complets
        import copy as _copy
        voeux_enrichi = voeux_df.copy()
        if equipes_df is not None:
            adresses = equipes_df.set_index("numero_equipe")["adresse"].to_dict()
            noms_eq = equipes_df.set_index("numero_equipe")["nom_equipe"].to_dict()
            voeux_enrichi["adresse"] = voeux_enrichi["numero_equipe"].map(adresses).fillna("")
            voeux_enrichi["nom_equipe"] = voeux_enrichi["numero_equipe"].map(noms_eq).fillna(
                voeux_enrichi["numero_equipe"].astype(str)
            )
        equipes_obj = _ce(voeux_enrichi)
        competitions_obj = _cc(competitions_df)

        # Appliquer les affectations
        for res in resultats:
            for num, nom_comp in res.nouvelles_affectations.items():
                if num in equipes_obj and nom_comp in competitions_obj:
                    if nom_comp not in equipes_obj[num].affectations:
                        equipes_obj[num].affectations.append(nom_comp)
                    if num not in competitions_obj[nom_comp].equipes_affectees:
                        competitions_obj[nom_comp].equipes_affectees.append(num)
                        competitions_obj[nom_comp].places_restantes -= 1

        sheets = resultats_vers_dataframes(resultats, equipes_obj, competitions_obj)
    except Exception:
        sheets = {}

    # Afficher un onglet par compétition
    noms_comps = list(competitions_df["nom_competition"])
    if noms_comps and sheets:
        onglets = st.tabs(noms_comps + ["Non affectées", "Résumé global"])
        for i, nom_comp in enumerate(noms_comps):
            with onglets[i]:
                df_comp = sheets.get(nom_comp[:31], pd.DataFrame())
                capacite = int(competitions_df[competitions_df["nom_competition"] == nom_comp]["capacite_max"].iloc[0])
                nb_aff = len(df_comp)
                st.metric(
                    "Équipes affectées",
                    f"{nb_aff} / {capacite}",
                    delta=f"{round(nb_aff/capacite*100)}% de remplissage" if capacite else "",
                )
                if not df_comp.empty:
                    st.dataframe(df_comp, use_container_width=True)
                else:
                    st.info("Aucune équipe affectée.")

        with onglets[-2]:
            df_non = sheets.get("Non_affectées", pd.DataFrame())
            if df_non.empty:
                st.success("Toutes les équipes ont au moins une compétition ! ✅")
            else:
                st.error(f"{len(df_non)} équipe(s) sans compétition.")
                st.dataframe(df_non, use_container_width=True)

        with onglets[-1]:
            df_resume = sheets.get("Résumé", pd.DataFrame())
            st.dataframe(df_resume, use_container_width=True)

    # Export Excel
    if sheets:
        excel_bytes = exporter_excel(sheets)
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
