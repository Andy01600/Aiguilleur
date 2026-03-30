"""
Module 2 — Affectation des équipes aux compétitions FTC France.

Algorithme en 3 tours :
  Tour 1 : garantit qu'aucune équipe ne reste sans compétition
  Tour 2 : affecte les 2ᵉ compétitions pour les équipes qui le souhaitent
  Tour 3 : affecte les 3ᵉ compétitions

Système de priorité (sur-souscription) :
  1. Score = distance vers la meilleure alternative viable
     → plus l'alternative est loin, plus l'équipe a besoin de CETTE compétition
  2. Tie-break : horodatage du formulaire (premier inscrit)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from utils.helpers import (
    PENALITE_VACANCES_KM,
    adresse_vers_zone,
    charger_centroides,
    charger_vacances,
    distance_entre_adresses,
    est_en_vacances,
    extraire_code_postal,
)


# ---------------------------------------------------------------------------
# Structures de données
# ---------------------------------------------------------------------------

@dataclass
class Equipe:
    numero: int
    nom: str
    adresse: str
    code_postal: str | None
    zone: str | None
    horodatage: datetime | None
    nb_souhaite: int
    voeux: list[str]                     # voeux uniques et non vides, dans l'ordre
    affectations: list[str] = field(default_factory=list)


@dataclass
class Competition:
    nom: str
    adresse: str
    capacite: int
    date_competition: date | None
    places_restantes: int
    equipes_affectees: list[int] = field(default_factory=list)


@dataclass
class AffectationResult:
    tour: int
    nouvelles_affectations: dict[int, str]   # {numero_equipe: nom_competition}
    non_affectees: list[int]                 # équipes sans compétition ce tour
    alertes: list[str]
    metriques: dict[str, float]


# ---------------------------------------------------------------------------
# Validation des données
# ---------------------------------------------------------------------------

COLONNES_VOEUX = ["numero_equipe", "nb_competitions_souhaitees", "voeu_1"]
COLONNES_COMPETITIONS = ["nom_competition", "adresse", "capacite_max"]


def valider_voeux(
    voeux_df: pd.DataFrame,
    competitions_df: pd.DataFrame,
) -> list[str]:
    """
    Valide le fichier des vœux. Retourne une liste de messages d'avertissement.
    Ne bloque pas le traitement.
    """
    alertes: list[str] = []
    noms_comps_valides = set(competitions_df["nom_competition"].str.strip())

    for _, ligne in voeux_df.iterrows():
        num = ligne.get("numero_equipe", "?")

        # Récupérer tous les voeux non vides
        voeux = _extraire_voeux(ligne)

        # Vérifier le minimum de 3 voeux
        if len(voeux) < 3:
            alertes.append(
                f"Équipe {num} : seulement {len(voeux)} vœu(x) rempli(s), "
                "minimum 3 attendus."
            )

        # Vérifier les doublons
        if len(voeux) != len(set(voeux)):
            doublons = [v for v in voeux if voeux.count(v) > 1]
            alertes.append(
                f"Équipe {num} : vœux dupliqués détectés ({', '.join(set(doublons))}) "
                "— les doublons seront ignorés."
            )

        # Vérifier que nb_competitions_souhaitees <= nb voeux
        nb = int(ligne.get("nb_competitions_souhaitees", 1))
        if nb > len(set(voeux)):
            alertes.append(
                f"Équipe {num} : souhaite {nb} compétition(s) mais n'a que "
                f"{len(set(voeux))} vœu(x) distinct(s)."
            )

        # Vérifier que les noms de compétitions existent
        for v in voeux:
            if v.strip() not in noms_comps_valides:
                alertes.append(
                    f"Équipe {num} : compétition inconnue « {v} ». "
                    f"Compétitions disponibles : {', '.join(sorted(noms_comps_valides))}"
                )

    return alertes


def _extraire_voeux(ligne: pd.Series) -> list[str]:
    """Extrait les vœux non vides et non dupliqués d'une ligne du DataFrame."""
    voeux = []
    vus = set()
    for i in range(1, 7):  # voeu_1 à voeu_6
        col = f"voeu_{i}"
        if col in ligne.index:
            v = str(ligne[col]).strip() if pd.notna(ligne[col]) else ""
            if v and v not in vus:
                voeux.append(v)
                vus.add(v)
    return voeux


# ---------------------------------------------------------------------------
# Construction des objets métier
# ---------------------------------------------------------------------------

def construire_equipes(
    voeux_df: pd.DataFrame,
) -> dict[int, Equipe]:
    """Construit le dictionnaire {numero: Equipe} depuis le DataFrame des vœux."""
    equipes: dict[int, Equipe] = {}
    for _, ligne in voeux_df.iterrows():
        num = int(ligne["numero_equipe"])
        horodatage = None
        if "horodatage" in ligne.index and pd.notna(ligne["horodatage"]):
            try:
                horodatage = pd.to_datetime(ligne["horodatage"]).to_pydatetime()
            except Exception:
                pass

        adresse = str(ligne.get("adresse", "")).strip() if "adresse" in ligne.index else ""
        voeux = _extraire_voeux(ligne)

        equipes[num] = Equipe(
            numero=num,
            nom=str(ligne.get("nom_equipe", f"Équipe {num}")).strip(),
            adresse=adresse,
            code_postal=extraire_code_postal(adresse) if adresse else None,
            zone=adresse_vers_zone(adresse) if adresse else None,
            horodatage=horodatage,
            nb_souhaite=int(ligne.get("nb_competitions_souhaitees", 1)),
            voeux=voeux,
        )
    return equipes


def construire_competitions(
    competitions_df: pd.DataFrame,
    saison_vacances: str = "2026_2027",
) -> dict[str, Competition]:
    """Construit le dictionnaire {nom: Competition} depuis le DataFrame."""
    competitions: dict[str, Competition] = {}
    for _, ligne in competitions_df.iterrows():
        nom = str(ligne["nom_competition"]).strip()
        capacite = int(ligne["capacite_max"])

        date_comp = None
        if "date_forcee" in ligne.index and pd.notna(ligne.get("date_forcee")):
            try:
                date_comp = pd.to_datetime(ligne["date_forcee"]).date()
            except Exception:
                pass

        competitions[nom] = Competition(
            nom=nom,
            adresse=str(ligne["adresse"]).strip(),
            capacite=capacite,
            date_competition=date_comp,
            places_restantes=capacite,
        )
    return competitions


# ---------------------------------------------------------------------------
# Calcul de priorité
# ---------------------------------------------------------------------------

def calculer_score_alternative(
    equipe: Equipe,
    competition_cible: Competition,
    competitions: dict[str, Competition],
    centroides: dict,
    vacances: dict | None,
    penalite_km: float = PENALITE_VACANCES_KM,
) -> float:
    """
    Calcule le score d'alternative de l'équipe pour la compétition cible.
    Plus le score est élevé, plus l'équipe a besoin de la compétition cible.

    Retourne : distance effective vers la meilleure alternative disponible.
    Si aucune alternative → +∞ (priorité maximale).
    """
    if not equipe.adresse:
        return float("inf")

    alternatives = [
        nom for nom in equipe.voeux
        if nom != competition_cible.nom
        and nom in competitions
        and competitions[nom].places_restantes > 0
    ]

    if not alternatives:
        return float("inf")

    distances_effectives = []
    for nom_alt in alternatives:
        comp_alt = competitions[nom_alt]
        dist = distance_entre_adresses(equipe.adresse, comp_alt.adresse, centroides)
        if dist is None:
            dist = float("inf")

        # Pénalité si l'alternative tombe pendant les vacances de la zone de l'équipe
        penalite = 0.0
        if (
            vacances is not None
            and equipe.zone is not None
            and comp_alt.date_competition is not None
            and est_en_vacances(comp_alt.date_competition, equipe.zone, vacances)
        ):
            penalite = penalite_km

        distances_effectives.append(dist + penalite)

    return min(distances_effectives)


def cle_priorite(
    equipe: Equipe,
    competition: Competition,
    competitions: dict[str, Competition],
    centroides: dict,
    vacances: dict | None,
    penalite_km: float = PENALITE_VACANCES_KM,
) -> tuple:
    """
    Retourne une clé de tri pour l'équipe (ordre croissant = priorité décroissante).
    On trie en ordre DÉCROISSANT de score_alternative donc on renvoie le négatif.
    Tie-break : horodatage croissant (premier inscrit prioritaire).
    """
    score = calculer_score_alternative(
        equipe, competition, competitions, centroides, vacances, penalite_km
    )
    # Score négatif → sort ascending = plus grand score en premier
    horodatage_key = equipe.horodatage or datetime.max
    return (-score, horodatage_key)


# ---------------------------------------------------------------------------
# Algorithme d'affectation — un tour
# ---------------------------------------------------------------------------

def _affecter_a_competition(
    equipe: Equipe,
    nom_competition: str,
    competitions: dict[str, Competition],
) -> None:
    """Enregistre l'affectation et décrémente les places restantes."""
    competitions[nom_competition].places_restantes -= 1
    competitions[nom_competition].equipes_affectees.append(equipe.numero)
    equipe.affectations.append(nom_competition)


def executer_tour(
    tour_num: int,
    equipes: dict[int, Equipe],
    competitions: dict[str, Competition],
    centroides: dict,
    vacances: dict | None,
    penalite_km: float = PENALITE_VACANCES_KM,
) -> AffectationResult:
    """
    Exécute un tour d'affectation.

    Tour 1 : toutes les équipes (garantit 1 compétition chacune)
    Tour 2 : équipes souhaitant ≥ 2 compétitions
    Tour 3 : équipes souhaitant ≥ 3 compétitions
    """
    alertes: list[str] = []
    nouvelles_affectations: dict[int, str] = {}

    # Équipes éligibles pour ce tour
    if tour_num == 1:
        eligibles = {num: eq for num, eq in equipes.items()}
    else:
        eligibles = {
            num: eq
            for num, eq in equipes.items()
            if eq.nb_souhaite >= tour_num
        }

    # -----------------------------------------------------------------------
    # Phase A : Affecter par vœu de rang `tour_num` (voeu_1 pour tour 1, etc.)
    # -----------------------------------------------------------------------
    # Regrouper les demandeurs par compétition pour leur vœu de rang `tour_num`
    demandeurs_par_comp: dict[str, list[Equipe]] = {nom: [] for nom in competitions}

    for equipe in eligibles.values():
        # Trouver le prochain vœu non encore satisfait
        voeux_restants = [
            v for v in equipe.voeux
            if v not in equipe.affectations
        ]
        if not voeux_restants:
            continue
        voeu_principal = voeux_restants[0]
        if voeu_principal in demandeurs_par_comp:
            demandeurs_par_comp[voeu_principal].append(equipe)

    # Trier les compétitions par demande décroissante (plus sur-souscrites d'abord)
    comps_triees = sorted(
        competitions.keys(),
        key=lambda nom: len(demandeurs_par_comp[nom]),
        reverse=True,
    )

    non_affectes_phase_a: list[Equipe] = []

    for nom_comp in comps_triees:
        comp = competitions[nom_comp]
        demandeurs = demandeurs_par_comp[nom_comp]
        if not demandeurs:
            continue

        if len(demandeurs) <= comp.places_restantes:
            # Tout le monde passe
            for eq in demandeurs:
                _affecter_a_competition(eq, nom_comp, competitions)
                nouvelles_affectations[eq.numero] = nom_comp
        else:
            # Sur-souscription : trier par priorité
            demandeurs_tries = sorted(
                demandeurs,
                key=lambda eq: cle_priorite(eq, comp, competitions, centroides, vacances, penalite_km),
            )
            for eq in demandeurs_tries[: comp.places_restantes]:
                _affecter_a_competition(eq, nom_comp, competitions)
                nouvelles_affectations[eq.numero] = nom_comp
            for eq in demandeurs_tries[comp.places_restantes:]:
                non_affectes_phase_a.append(eq)

    # -----------------------------------------------------------------------
    # Phase B : Traiter les non-affectés (vœux suivants ou fallback)
    # -----------------------------------------------------------------------
    non_affectes_final: list[int] = []

    for equipe in non_affectes_phase_a:
        voeux_restants = [
            v for v in equipe.voeux
            if v not in equipe.affectations and v in competitions
        ]

        affecte = False
        for voeu in voeux_restants:
            comp = competitions[voeu]
            if comp.places_restantes > 0:
                _affecter_a_competition(equipe, voeu, competitions)
                nouvelles_affectations[equipe.numero] = voeu
                affecte = True
                break

        if not affecte:
            if tour_num == 1:
                # Fallback obligatoire pour le Tour 1 : compétition avec le plus de places
                comp_fallback = _trouver_fallback(equipe, competitions, centroides)
                if comp_fallback:
                    _affecter_a_competition(equipe, comp_fallback, competitions)
                    nouvelles_affectations[equipe.numero] = comp_fallback
                    alertes.append(
                        f"Équipe {equipe.numero} ({equipe.nom}) affectée en fallback "
                        f"à « {comp_fallback} » (aucun vœu disponible)."
                    )
                else:
                    non_affectes_final.append(equipe.numero)
                    alertes.append(
                        f"⚠️ Impossible d'affecter l'équipe {equipe.numero} "
                        f"({equipe.nom}) : toutes les compétitions sont pleines !"
                    )
            else:
                # Tours 2 & 3 : pas d'obligation, on signale juste
                non_affectes_final.append(equipe.numero)

    # -----------------------------------------------------------------------
    # Vérification finale (Tour 1 uniquement)
    # -----------------------------------------------------------------------
    if tour_num == 1:
        for num, eq in equipes.items():
            if not eq.affectations:
                if num not in non_affectes_final:
                    non_affectes_final.append(num)
                    alertes.append(
                        f"⚠️ Équipe {num} ({eq.nom}) sans compétition après le Tour 1 !"
                    )
        for nom, comp in competitions.items():
            if comp.places_restantes < 0:
                alertes.append(
                    f"🔴 Erreur : compétition « {nom} » dépasse sa capacité "
                    f"(places restantes : {comp.places_restantes}) !"
                )

    # -----------------------------------------------------------------------
    # Métriques
    # -----------------------------------------------------------------------
    metriques = _calculer_metriques(tour_num, equipes, competitions, nouvelles_affectations)

    return AffectationResult(
        tour=tour_num,
        nouvelles_affectations=nouvelles_affectations,
        non_affectees=non_affectes_final,
        alertes=alertes,
        metriques=metriques,
    )


def _trouver_fallback(
    equipe: Equipe,
    competitions: dict[str, Competition],
    centroides: dict,
) -> str | None:
    """
    Fallback Tour 1 : renvoie la compétition avec le plus de places restantes.
    Tie-break : la plus proche géographiquement.
    """
    candidates = [
        comp for comp in competitions.values()
        if comp.places_restantes > 0
        and comp.nom not in equipe.affectations
    ]
    if not candidates:
        return None

    max_places = max(c.places_restantes for c in candidates)
    avec_max = [c for c in candidates if c.places_restantes == max_places]

    if len(avec_max) == 1 or not equipe.adresse:
        return avec_max[0].nom

    # Tie-break géographique
    def dist_comp(comp: Competition) -> float:
        d = distance_entre_adresses(equipe.adresse, comp.adresse, centroides)
        return d if d is not None else float("inf")

    return min(avec_max, key=dist_comp).nom


def _calculer_metriques(
    tour_num: int,
    equipes: dict[int, Equipe],
    competitions: dict[str, Competition],
    nouvelles_affectations: dict[int, str],
) -> dict[str, float]:
    """Calcule les métriques de qualité pour le tour courant."""
    metriques: dict[str, float] = {}

    if tour_num == 1:
        total = len(equipes)
        voeu1_ok = sum(
            1 for num, nom_comp in nouvelles_affectations.items()
            if equipes[num].voeux and nom_comp == equipes[num].voeux[0]
        )
        dans_voeux = sum(
            1 for num, nom_comp in nouvelles_affectations.items()
            if nom_comp in equipes[num].voeux
        )
        metriques["taux_voeu_1"] = round(voeu1_ok / total * 100, 1) if total else 0.0
        metriques["taux_satisfaction"] = round(dans_voeux / total * 100, 1) if total else 0.0

    metriques["nb_affectations_tour"] = float(len(nouvelles_affectations))

    for nom, comp in competitions.items():
        cle = f"remplissage_{nom[:20]}"
        metriques[cle] = round(
            (comp.capacite - comp.places_restantes) / comp.capacite * 100, 1
        ) if comp.capacite else 0.0

    return metriques


# ---------------------------------------------------------------------------
# Point d'entrée principal
# ---------------------------------------------------------------------------

def lancer_affectation(
    voeux_df: pd.DataFrame,
    competitions_df: pd.DataFrame,
    equipes_df: pd.DataFrame | None = None,
    saison_vacances: str = "2026_2027",
    penalite_km: float = PENALITE_VACANCES_KM,
    nb_tours: int = 3,
) -> tuple[list[AffectationResult], list[str]]:
    """
    Lance l'affectation complète (jusqu'à nb_tours tours).

    Si equipes_df est fourni, les adresses y sont lues (utile quand le fichier
    vœux ne contient pas d'adresse, car issu du Forms).

    Retourne (liste de AffectationResult, alertes de validation).
    """
    # Enrichir le DataFrame des vœux avec les adresses si dispo
    if equipes_df is not None:
        voeux_df = voeux_df.copy()
        adresses = equipes_df.set_index("numero_equipe")["adresse"].to_dict()
        noms = equipes_df.set_index("numero_equipe")["nom_equipe"].to_dict()
        voeux_df["adresse"] = voeux_df["numero_equipe"].map(adresses).fillna("")
        voeux_df["nom_equipe"] = voeux_df["numero_equipe"].map(noms).fillna(
            voeux_df["numero_equipe"].astype(str)
        )

    alertes_validation = valider_voeux(voeux_df, competitions_df)

    centroides = charger_centroides()
    vacances: dict | None = None
    try:
        vacances = charger_vacances(saison_vacances)
    except FileNotFoundError:
        alertes_validation.append(
            f"⚠️ Calendrier vacances « {saison_vacances} » introuvable. "
            "La pénalité vacances ne sera pas appliquée."
        )

    equipes = construire_equipes(voeux_df)
    competitions = construire_competitions(competitions_df, saison_vacances)

    # Vérification capacité globale
    total_capacite = sum(c.capacite for c in competitions.values())
    if len(equipes) > total_capacite:
        alertes_validation.append(
            f"⚠️ Capacité totale ({total_capacite}) inférieure au nombre d'équipes "
            f"({len(equipes)}). Certaines équipes ne pourront pas être placées."
        )

    resultats: list[AffectationResult] = []
    for tour in range(1, nb_tours + 1):
        resultat = executer_tour(
            tour_num=tour,
            equipes=equipes,
            competitions=competitions,
            centroides=centroides,
            vacances=vacances,
            penalite_km=penalite_km,
        )
        resultats.append(resultat)
        # Arrêter si aucune nouvelle affectation au tour précédent
        if not resultat.nouvelles_affectations and tour > 1:
            break

    return resultats, alertes_validation


# ---------------------------------------------------------------------------
# Export des résultats
# ---------------------------------------------------------------------------

def resultats_vers_dataframes(
    resultats: list[AffectationResult],
    equipes: dict[int, "Equipe"],
    competitions: dict[str, "Competition"],
) -> dict[str, pd.DataFrame]:
    """
    Génère les DataFrames pour l'export Excel multi-feuilles :
    - "Résumé" : toutes les affectations par équipe
    - "Par compétition" : une entrée par compétition
    - Un onglet par compétition
    - "Non_affectées"
    - "Métriques"
    """
    sheets: dict[str, pd.DataFrame] = {}

    # Résumé global
    lignes_resume = []
    for num, eq in equipes.items():
        for i, nom_comp in enumerate(eq.affectations, 1):
            lignes_resume.append({
                "Numéro équipe": num,
                "Nom équipe": eq.nom,
                "Tour": i,
                "Compétition": nom_comp,
            })
    sheets["Résumé"] = pd.DataFrame(lignes_resume)

    # Par compétition
    for nom_comp, comp in competitions.items():
        lignes_comp = []
        for num in comp.equipes_affectees:
            eq = equipes.get(num)
            rang = (eq.affectations.index(nom_comp) + 1) if eq and nom_comp in eq.affectations else "?"
            voeu_rang = "?"
            if eq and nom_comp in eq.voeux:
                voeu_rang = eq.voeux.index(nom_comp) + 1
            elif eq and nom_comp in eq.affectations and nom_comp not in eq.voeux:
                voeu_rang = "Fallback"
            lignes_comp.append({
                "Numéro équipe": num,
                "Nom équipe": eq.nom if eq else "?",
                "Adresse": eq.adresse if eq else "?",
                "Vœu n°": voeu_rang,
                "Tour": rang,
            })
        nom_feuille = nom_comp[:31]
        sheets[nom_feuille] = pd.DataFrame(lignes_comp)

    # Équipes non affectées (après tous les tours)
    non_affectees = [
        {"Numéro équipe": num, "Nom équipe": eq.nom, "Adresse": eq.adresse}
        for num, eq in equipes.items()
        if not eq.affectations
    ]
    sheets["Non_affectées"] = pd.DataFrame(non_affectees)

    # Métriques agrégées
    lignes_metriques: list[dict] = []
    for res in resultats:
        lignes_metriques.append({"Tour": res.tour, **res.metriques})
    sheets["Métriques"] = pd.DataFrame(lignes_metriques)

    return sheets
