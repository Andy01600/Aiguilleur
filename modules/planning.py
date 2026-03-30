"""
Module 1 — Planification du calendrier des compétitions FTC France.

Sélectionne les N meilleures dates (samedis) dans une fenêtre donnée en
minimisant les conflits avec les vacances scolaires et en maximisant
la compacité (samedis consécutifs).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go

from utils.helpers import (
    LAMBDA_DEFAULT,
    adresse_vers_zone,
    charger_vacances,
    est_en_vacances,
    est_jour_ferie,
    samedis_dans_fenetre,
)

# ---------------------------------------------------------------------------
# Structures de données
# ---------------------------------------------------------------------------

@dataclass
class SamediCandidat:
    date: date
    score_vacances: float   # nombre pondéré d'équipes impactées (ou zones si pas d'équipes)
    zones_impactees: list[str]


@dataclass
class PlanningResult:
    competitions: list[str]         # noms dans l'ordre des dates
    dates: list[date]               # dates choisies, triées
    score_total: float
    score_vacances: float
    nb_trous: int
    detail_par_date: list[dict]     # [{date, competition, score_vacances, zones}]
    alertes: list[str]


# ---------------------------------------------------------------------------
# Algorithme de scoring
# ---------------------------------------------------------------------------

def scorer_samedi(
    d: date,
    vacances: dict,
    equipes_par_zone: dict[str, int] | None = None,
) -> tuple[float, list[str]]:
    """
    Calcule le score de conflit pour un samedi.

    Si equipes_par_zone est fourni : somme les équipes impactées par zone.
    Sinon (mode dégradé sans fichier équipes) : compte le nombre de zones en vacances.

    Retourne (score, [zones_impactees]).
    """
    zones_impactees = [
        zone for zone in ["A", "B", "C"]
        if est_en_vacances(d, zone, vacances)
    ]
    if equipes_par_zone:
        score = sum(equipes_par_zone.get(z, 0) for z in zones_impactees)
    else:
        score = float(len(zones_impactees))
    return score, zones_impactees


def calculer_nb_trous(dates: list[date]) -> int:
    """
    Compte les samedis libres (trous) entre la 1ère et la dernière compétition.
    Exemple : [s1, s3, s5] → 2 trous (s2 et s4 sont libres).
    """
    if len(dates) < 2:
        return 0
    dates_triees = sorted(dates)
    debut = dates_triees[0]
    fin = dates_triees[-1]
    # Nombre total de samedis dans l'intervalle
    total_samedis = 0
    d = debut
    while d <= fin:
        if d.weekday() == 5:
            total_samedis += 1
        d += timedelta(days=1)
    return total_samedis - len(dates)


def calculer_score_total(
    dates: list[date],
    scores_par_date: dict[date, float],
    lambda_: float = LAMBDA_DEFAULT,
) -> float:
    """score_total = Σ score_vacances(d) + λ × nb_trous"""
    somme_vacances = sum(scores_par_date.get(d, 0.0) for d in dates)
    trous = calculer_nb_trous(dates)
    return somme_vacances + lambda_ * trous


# ---------------------------------------------------------------------------
# Algorithme de sélection des dates
# ---------------------------------------------------------------------------

def recherche_exhaustive(
    candidats: list[SamediCandidat],
    n: int,
    dates_forcees: list[date],
    lambda_: float = LAMBDA_DEFAULT,
) -> list[date]:
    """
    Cherche la combinaison de n dates minimisant le score total.
    Les dates forcées sont toujours incluses.
    """
    scores = {c.date: c.score_vacances for c in candidats}

    # Retirer les dates forcées des candidats libres
    dates_libres = [c for c in candidats if c.date not in dates_forcees]
    n_libre = n - len(dates_forcees)

    if n_libre < 0:
        raise ValueError(
            f"{len(dates_forcees)} dates forcées pour {n} compétitions : "
            "trop de dates forcées."
        )
    if n_libre > len(dates_libres):
        raise ValueError(
            f"Pas assez de samedis disponibles ({len(dates_libres)}) "
            f"pour placer {n_libre} compétition(s) supplémentaire(s)."
        )

    meilleur_score = float("inf")
    meilleure_combinaison: list[date] = []

    for combo in itertools.combinations(dates_libres, n_libre):
        dates_combo = dates_forcees + [c.date for c in combo]
        score = calculer_score_total(dates_combo, scores, lambda_)
        if score < meilleur_score:
            meilleur_score = score
            meilleure_combinaison = sorted(dates_combo)

    return meilleure_combinaison


# ---------------------------------------------------------------------------
# Point d'entrée principal
# ---------------------------------------------------------------------------

def generer_planning(
    competitions_df: pd.DataFrame,
    equipes_df: pd.DataFrame | None,
    fenetre_debut: date,
    fenetre_fin: date,
    lambda_: float = LAMBDA_DEFAULT,
    saison_vacances: str = "2026_2027",
) -> PlanningResult:
    """
    Génère un planning optimal pour les compétitions FTC France.

    Paramètres
    ----------
    competitions_df : colonnes attendues — nom_competition, adresse, capacite_max,
                      date_forcee (optionnel)
    equipes_df      : colonnes attendues — numero_equipe, nom_equipe, adresse
                      (None = mode dégradé, scoring par zones uniquement)
    fenetre_debut   : premier samedi éligible
    fenetre_fin     : dernier samedi éligible
    lambda_         : coefficient de pénalité pour les trous
    saison_vacances : identifiant de la saison ("2025_2026" ou "2026_2027")
    """
    alertes: list[str] = []
    n = len(competitions_df)

    # --- Charger le calendrier des vacances ---
    vacances = charger_vacances(saison_vacances)

    # --- Compter les équipes par zone (optionnel) ---
    equipes_par_zone: dict[str, int] | None = None
    if equipes_df is not None and not equipes_df.empty:
        equipes_par_zone = {"A": 0, "B": 0, "C": 0}
        for adresse in equipes_df["adresse"]:
            zone = adresse_vers_zone(str(adresse))
            if zone in equipes_par_zone:
                equipes_par_zone[zone] += 1
            else:
                alertes.append(
                    f"Zone non déterminée pour l'adresse : {adresse}"
                )

    # --- Extraire les dates forcées ---
    dates_forcees: list[date] = []
    if "date_forcee" in competitions_df.columns:
        for val in competitions_df["date_forcee"].dropna():
            try:
                d = pd.to_datetime(val).date()
                if d.weekday() != 5:
                    alertes.append(
                        f"La date forcée {d} n'est pas un samedi — ignorée."
                    )
                else:
                    dates_forcees.append(d)
            except Exception:
                pass

    # --- Générer les samedis candidats ---
    tous_samedis = samedis_dans_fenetre(fenetre_debut, fenetre_fin)
    candidats: list[SamediCandidat] = []
    for s in tous_samedis:
        if est_jour_ferie(s):
            alertes.append(f"Samedi {s} exclu (jour férié).")
            continue
        if s in dates_forcees:
            continue  # sera ajouté directement
        score, zones = scorer_samedi(s, vacances, equipes_par_zone)
        candidats.append(SamediCandidat(date=s, score_vacances=score, zones_impactees=zones))

    # Ajouter les scores des dates forcées
    scores_forces = {}
    for d in dates_forcees:
        score, _ = scorer_samedi(d, vacances, equipes_par_zone)
        scores_forces[d] = score

    # Vérifier la faisabilité
    n_libre = n - len(dates_forcees)
    if len(candidats) < n_libre:
        alertes.append(
            f"⚠️ Fenêtre trop courte : {len(candidats)} samedi(s) disponible(s) "
            f"pour {n_libre} compétition(s) à planifier. "
            "Élargissez la fenêtre de dates."
        )
        if len(candidats) == 0:
            return PlanningResult(
                competitions=list(competitions_df["nom_competition"]),
                dates=[],
                score_total=float("inf"),
                score_vacances=float("inf"),
                nb_trous=0,
                detail_par_date=[],
                alertes=alertes,
            )

    # Choisir l'algorithme selon la taille du problème
    if len(candidats) <= 20 and n_libre <= 10:
        dates_choisies = recherche_exhaustive(candidats, n, dates_forcees, lambda_)
    else:
        # Fallback glouton : prendre les n_libre meilleurs + dates forcées
        candidats_tries = sorted(candidats, key=lambda c: c.score_vacances)
        dates_choisies = sorted(
            dates_forcees + [c.date for c in candidats_tries[:n_libre]]
        )
        alertes.append(
            "Algorithme glouton utilisé (fenêtre > 20 samedis ou > 10 compétitions)."
        )

    # --- Construire le résultat ---
    # Associer compétitions ← dates
    noms_competitions = list(competitions_df["nom_competition"])
    # Mettre d'abord les compétitions à date forcée, puis les autres
    comps_forcees = []
    comps_libres = []
    if "date_forcee" in competitions_df.columns:
        for _, row in competitions_df.iterrows():
            if pd.notna(row.get("date_forcee")):
                comps_forcees.append(row["nom_competition"])
            else:
                comps_libres.append(row["nom_competition"])
    else:
        comps_libres = noms_competitions[:]

    # Dates forcées → compétitions forcées (ordre d'apparition)
    # Dates libres → autres compétitions (ordre chronologique)
    dates_libres_choisies = [d for d in dates_choisies if d not in dates_forcees]

    planning: list[tuple[date, str]] = []
    for d, nom in zip(dates_forcees, comps_forcees):
        planning.append((d, nom))
    for d, nom in zip(dates_libres_choisies, comps_libres):
        planning.append((d, nom))
    planning.sort(key=lambda x: x[0])

    # Scores
    scores_par_date = {c.date: c.score_vacances for c in candidats}
    scores_par_date.update(scores_forces)

    detail: list[dict] = []
    score_vac_total = 0.0
    for d, nom in planning:
        sv = scores_par_date.get(d, 0.0)
        _, zones = scorer_samedi(d, vacances, equipes_par_zone)
        score_vac_total += sv
        detail.append({
            "date": d,
            "competition": nom,
            "score_vacances": sv,
            "zones_impactees": zones,
        })

    nb_trous = calculer_nb_trous([d for d, _ in planning])
    score_tot = score_vac_total + lambda_ * nb_trous

    # Alertes de qualité
    if score_vac_total > 0:
        alertes.append(
            f"🟠 Score d'impact vacances : {score_vac_total:.0f} "
            f"({'équipes' if equipes_par_zone else 'zones'} potentiellement impactées)."
        )
    if nb_trous > 0:
        alertes.append(f"🟠 {nb_trous} samedi(s) creux entre les compétitions.")

    return PlanningResult(
        competitions=[nom for _, nom in planning],
        dates=[d for d, _ in planning],
        score_total=score_tot,
        score_vacances=score_vac_total,
        nb_trous=nb_trous,
        detail_par_date=detail,
        alertes=alertes,
    )


# ---------------------------------------------------------------------------
# Visualisation Plotly
# ---------------------------------------------------------------------------

def planning_vers_plotly(
    result: PlanningResult,
    vacances: dict | None = None,
) -> go.Figure:
    """
    Génère un graphique Plotly du calendrier.
    Barres verticales colorées par score d'impact, bandes de vacances en fond.
    """
    if not result.dates:
        fig = go.Figure()
        fig.update_layout(title="Aucune date sélectionnée")
        return fig

    # Couleur selon score vacances
    def couleur(score: float) -> str:
        if score == 0:
            return "#2ecc71"   # vert
        if score <= 5:
            return "#f39c12"   # orange
        return "#e74c3c"       # rouge

    # Barres des compétitions
    fig = go.Figure()
    for detail in result.detail_par_date:
        fig.add_trace(go.Bar(
            x=[detail["date"].isoformat()],
            y=[1],
            name=detail["competition"],
            marker_color=couleur(detail["score_vacances"]),
            text=detail["competition"],
            textposition="inside",
            hovertemplate=(
                f"<b>{detail['competition']}</b><br>"
                f"Date : {detail['date']}<br>"
                f"Score vacances : {detail['score_vacances']:.0f}<br>"
                f"Zones impactées : {', '.join(detail['zones_impactees']) or 'aucune'}"
                "<extra></extra>"
            ),
            showlegend=False,
        ))

    # Bandes de vacances en arrière-plan
    if vacances:
        import plotly.colors as pc
        couleurs_zones = {"A": "rgba(52, 152, 219, 0.15)", "B": "rgba(231, 76, 60, 0.15)", "C": "rgba(46, 204, 113, 0.15)"}
        for zone, periodes in vacances.items():
            for debut, fin in periodes:
                fig.add_vrect(
                    x0=debut.isoformat(),
                    x1=fin.isoformat(),
                    fillcolor=couleurs_zones.get(zone, "rgba(0,0,0,0.1)"),
                    opacity=1,
                    layer="below",
                    line_width=0,
                    annotation_text=f"Vac. {zone}",
                    annotation_position="top left",
                )

    fig.update_layout(
        title="Planning des compétitions FTC France",
        xaxis_title="Date",
        yaxis_visible=False,
        barmode="overlay",
        height=300,
        margin={"t": 60, "b": 40, "l": 20, "r": 20},
        plot_bgcolor="white",
    )
    return fig


# ---------------------------------------------------------------------------
# Résumé exportable
# ---------------------------------------------------------------------------

def planning_vers_dataframe(result: PlanningResult) -> pd.DataFrame:
    """Convertit le résultat en DataFrame pour affichage et export Excel."""
    lignes = []
    for detail in result.detail_par_date:
        lignes.append({
            "Date": detail["date"].strftime("%d/%m/%Y"),
            "Jour": detail["date"].strftime("%A").capitalize(),
            "Compétition": detail["competition"],
            "Score impact vacances": detail["score_vacances"],
            "Zones impactées": ", ".join(detail["zones_impactees"]) or "Aucune",
        })
    return pd.DataFrame(lignes)
