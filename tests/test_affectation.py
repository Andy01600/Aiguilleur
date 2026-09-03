"""
Tests unitaires — Module 2 : Affectation des équipes.
"""

import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.affectation import (
    AffectationResult,
    Evenement,
    Equipe,
    _extraire_voeux,
    _trouver_fallback,
    calculer_score_alternative,
    cle_priorite,
    construire_evenements,
    construire_equipes,
    executer_tour,
    lancer_affectation,
    valider_voeux,
)

# ---------------------------------------------------------------------------
# Fixtures — données synthétiques minimales
# ---------------------------------------------------------------------------

# Centroïdes factices (quelques CP réels pour les tests de distance)
CENTROIDES_TEST = {
    "44000": (47.218, -1.554),   # Nantes
    "75011": (48.858, 2.378),    # Paris
    "06560": (43.616, 7.058),    # Valbonne
    "69003": (45.749, 4.853),    # Lyon
    "63000": (45.777, 3.087),    # Clermont-Ferrand
    "76500": (49.279, 1.018),    # Elbeuf (Normandie)
    "35800": (48.636, -2.052),   # Dinard (Bretagne)
}


def faire_evenements_df(lignes: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(lignes)


def faire_voeux_df(lignes: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(lignes)


@pytest.fixture
def evenements_simples():
    return {
        "Nantes": Evenement(
            nom="Nantes", adresse="44000 Nantes", capacite=3,
            date_evenement=date(2026, 11, 14),
            places_restantes=3,
        ),
        "Paris": Evenement(
            nom="Paris", adresse="75011 Paris", capacite=3,
            date_evenement=date(2026, 11, 21),
            places_restantes=3,
        ),
        "Lyon": Evenement(
            nom="Lyon", adresse="69003 Lyon", capacite=3,
            date_evenement=date(2026, 11, 28),
            places_restantes=3,
        ),
    }


# ---------------------------------------------------------------------------
# Tests extraction des vœux
# ---------------------------------------------------------------------------

class TestExtraireVoeux:
    def test_trois_voeux_remplis(self):
        ligne = pd.Series({"voeu_1": "Nantes", "voeu_2": "Paris", "voeu_3": "Lyon"})
        assert _extraire_voeux(ligne) == ["Nantes", "Paris", "Lyon"]

    def test_deduplication(self):
        ligne = pd.Series({"voeu_1": "Nantes", "voeu_2": "Nantes", "voeu_3": "Lyon"})
        voeux = _extraire_voeux(ligne)
        assert voeux.count("Nantes") == 1

    def test_voeux_vides_ignores(self):
        ligne = pd.Series({
            "voeu_1": "Nantes", "voeu_2": float("nan"), "voeu_3": "", "voeu_4": "Paris"
        })
        voeux = _extraire_voeux(ligne)
        assert voeux == ["Nantes", "Paris"]


# ---------------------------------------------------------------------------
# Tests validation des vœux
# ---------------------------------------------------------------------------

class TestValiderVoeux:
    def test_doublon_detecte(self):
        voeux_df = faire_voeux_df([{
            "numero_equipe": 33407,
            "voeu_1": "Nantes",
            "voeu_2": "Nantes",
            "voeu_3": "Paris",
            "nb_evenements_souhaitees": 2,
        }])
        comps_df = faire_evenements_df([
            {"nom_evenement": "Nantes", "adresse": "44000 Nantes", "capacite_max": 10},
            {"nom_evenement": "Paris", "adresse": "75011 Paris", "capacite_max": 10},
        ])
        alertes = valider_voeux(voeux_df, comps_df)
        assert any("dupliqués" in a for a in alertes)

    def test_moins_de_3_voeux(self):
        voeux_df = faire_voeux_df([{
            "numero_equipe": 123,
            "voeu_1": "Nantes",
            "voeu_2": float("nan"),
            "voeu_3": float("nan"),
            "nb_evenements_souhaitees": 1,
        }])
        comps_df = faire_evenements_df([
            {"nom_evenement": "Nantes", "adresse": "44000 Nantes", "capacite_max": 10},
        ])
        alertes = valider_voeux(voeux_df, comps_df)
        assert any("minimum 3" in a for a in alertes)

    def test_evenement_inconnu(self):
        voeux_df = faire_voeux_df([{
            "numero_equipe": 123,
            "voeu_1": "Événement Inconnu",
            "voeu_2": "Nantes",
            "voeu_3": "Paris",
            "nb_evenements_souhaitees": 1,
        }])
        comps_df = faire_evenements_df([
            {"nom_evenement": "Nantes", "adresse": "44000 Nantes", "capacite_max": 10},
            {"nom_evenement": "Paris", "adresse": "75011 Paris", "capacite_max": 10},
        ])
        alertes = valider_voeux(voeux_df, comps_df)
        assert any("inconnu" in a for a in alertes)

    def test_voeux_valides_sans_alerte(self):
        voeux_df = faire_voeux_df([{
            "numero_equipe": 123,
            "voeu_1": "Nantes",
            "voeu_2": "Paris",
            "voeu_3": "Lyon",
            "nb_evenements_souhaitees": 1,
        }])
        comps_df = faire_evenements_df([
            {"nom_evenement": "Nantes", "adresse": "44000 Nantes", "capacite_max": 10},
            {"nom_evenement": "Paris", "adresse": "75011 Paris", "capacite_max": 10},
            {"nom_evenement": "Lyon", "adresse": "69003 Lyon", "capacite_max": 10},
        ])
        alertes = valider_voeux(voeux_df, comps_df)
        assert alertes == []


# ---------------------------------------------------------------------------
# Tests système de priorité
# ---------------------------------------------------------------------------

class TestClePriorite:
    """
    Tests du tuple (isolation, vacances, -ratio_penibilite, dist_cible, horodatage).
    Indices : 0=isolation, 1=vacances, 2=-ratio, 3=dist_cible, 4=horodatage
    """

    def test_tuple_structure_5_elements(self, evenements_simples):
        """Le tuple de priorité contient bien 5 éléments."""
        eq = Equipe(
            numero=1, nom="TestEq", adresse="44000 Nantes",
            code_postal="44000", zone="B",
            horodatage=datetime(2026, 9, 1, 9, 0),
            nb_souhaite=1, voeux=["Nantes"],
        )
        comp = evenements_simples["Nantes"]
        cle = cle_priorite(eq, comp, evenements_simples, CENTROIDES_TEST, vacances=None)
        assert len(cle) == 5

    def test_penibilite_infinie_sans_repli(self):
        """Équipe seul événement existant → aucun repli → ratio = +∞."""
        comps_une_seule = {
            "Nantes": Evenement(
                nom="Nantes", adresse="44000 Nantes", capacite=3,
                date_evenement=date(2026, 11, 14), places_restantes=3,
            ),
        }
        eq = Equipe(
            numero=1, nom="TestEq", adresse="44000 Nantes",
            code_postal="44000", zone="B",
            horodatage=datetime(2026, 9, 1, 9, 0),
            nb_souhaite=1, voeux=["Nantes"],
        )
        cle = cle_priorite(eq, comps_une_seule["Nantes"], comps_une_seule, CENTROIDES_TEST, vacances=None)
        assert cle[2] == float("-inf")  # -ratio = -inf → priorité max

    def test_ratio_penibilite_prioritaire_sur_distance(self, evenements_simples):
        """Équipe avec ratio de repli plus élevé passe devant, même si plus loin."""
        # Bretagne: dist Nantes ≈ 100 km, repli Paris ≈ 340 km → ratio ≈ 3.4
        eq_bretagne = Equipe(
            numero=10, nom="Bretagne", adresse="35800 Dinard",
            code_postal="35800", zone="B",
            horodatage=datetime(2026, 9, 1, 9, 0),
            nb_souhaite=2, voeux=["Nantes", "Paris"],
        )
        # NantesLocale: dist Nantes ≈ 0 km → ratio = +∞ (dist_cible < 1 km)
        eq_nantes = Equipe(
            numero=20, nom="NantesLocale", adresse="44000 Nantes",
            code_postal="44000", zone="B",
            horodatage=datetime(2026, 9, 1, 9, 0),
            nb_souhaite=2, voeux=["Nantes", "Lyon"],
        )
        comp_nantes = evenements_simples["Nantes"]
        cle_b = cle_priorite(eq_bretagne, comp_nantes, evenements_simples, CENTROIDES_TEST, vacances=None)
        cle_n = cle_priorite(eq_nantes, comp_nantes, evenements_simples, CENTROIDES_TEST, vacances=None)
        # NantesLocale a ratio +∞ (sur place) → -ratio = -inf → passe devant Bretagne
        assert cle_n[2] < cle_b[2]  # -inf < -3.4
        assert cle_n < cle_b  # NantesLocale prioritaire globalement

    def test_horodatage_tiebreak(self, evenements_simples):
        """À critères 1-4 égaux, le premier inscrit passe."""
        eq_tot = Equipe(
            numero=1, nom="Tôt", adresse="44000 Nantes",
            code_postal="44000", zone="B",
            horodatage=datetime(2026, 9, 1, 8, 0),
            nb_souhaite=2, voeux=["Nantes", "Paris"],
        )
        eq_tard = Equipe(
            numero=2, nom="Tard", adresse="44000 Nantes",
            code_postal="44000", zone="B",
            horodatage=datetime(2026, 9, 1, 10, 0),
            nb_souhaite=2, voeux=["Nantes", "Paris"],
        )
        comp = evenements_simples["Nantes"]
        cle_tot = cle_priorite(eq_tot, comp, evenements_simples, CENTROIDES_TEST, vacances=None)
        cle_tard = cle_priorite(eq_tard, comp, evenements_simples, CENTROIDES_TEST, vacances=None)
        # Même adresse, mêmes vœux → critères 1-4 identiques, horodatage décide
        assert cle_tot[:4] == cle_tard[:4]  # 4 premiers critères identiques
        assert cle_tot[4] < cle_tard[4]  # tôt < tard → tôt plus prioritaire
        assert cle_tot < cle_tard  # tri global : tôt passe avant tard


# ---------------------------------------------------------------------------
# Tests executer_tour
# ---------------------------------------------------------------------------

class TestExecuterTour:
    def _equipes_dict(self, nb: int, voeux_par_eq: list[list[str]], comp_nom: str) -> dict:
        equipes = {}
        for i in range(nb):
            num = i + 1
            equipes[num] = Equipe(
                numero=num,
                nom=f"Equipe{num}",
                adresse="44000 Nantes",
                code_postal="44000",
                zone="B",
                horodatage=datetime(2026, 9, 1, 9 + i, 0),
                nb_souhaite=1,
                voeux=voeux_par_eq[i] if i < len(voeux_par_eq) else [comp_nom],
            )
        return equipes

    def test_tous_affectes_si_capacite_suffisante(self):
        """3 équipes, capacité 3 → toutes affectées à leur vœu 1."""
        equipes = self._equipes_dict(3, [["Nantes", "Paris", "Lyon"]] * 3, "Nantes")
        evenements = {
            "Nantes": Evenement("Nantes", "44000 Nantes", 3, None, 3),
            "Paris": Evenement("Paris", "75011 Paris", 3, None, 3),
            "Lyon": Evenement("Lyon", "69003 Lyon", 3, None, 3),
        }
        result = executer_tour(1, equipes, evenements, CENTROIDES_TEST, None)
        assert len(result.non_affectees) == 0
        assert len(result.nouvelles_affectations) == 3
        for num in [1, 2, 3]:
            assert result.nouvelles_affectations[num] == "Nantes"

    def test_sursouscription_respecte_capacite(self):
        """5 équipes veulent Nantes (capacité 2) → exactement 2 affectées."""
        voeux = [["Nantes", "Paris", "Lyon"]] * 5
        equipes = self._equipes_dict(5, voeux, "Nantes")
        evenements = {
            "Nantes": Evenement("Nantes", "44000 Nantes", 2, None, 2),
            "Paris": Evenement("Paris", "75011 Paris", 5, None, 5),
            "Lyon": Evenement("Lyon", "69003 Lyon", 5, None, 5),
        }
        result = executer_tour(1, equipes, evenements, CENTROIDES_TEST, None)
        assert evenements["Nantes"].places_restantes == 0
        # 3 déplacés vers voeu_2 (Paris)
        total_aff = len(result.nouvelles_affectations)
        assert total_aff == 5

    def test_toutes_equipes_affectees_tour1(self):
        """Invariant : après Tour 1, toutes les équipes ont exactement 1 événement."""
        voeux = [
            ["Nantes", "Paris", "Lyon"],
            ["Nantes", "Lyon", "Paris"],
            ["Nantes", "Paris", "Lyon"],
            ["Paris", "Nantes", "Lyon"],
            ["Lyon", "Nantes", "Paris"],
        ]
        equipes = self._equipes_dict(5, voeux, "Nantes")
        evenements = {
            "Nantes": Evenement("Nantes", "44000 Nantes", 2, None, 2),
            "Paris": Evenement("Paris", "75011 Paris", 2, None, 2),
            "Lyon": Evenement("Lyon", "69003 Lyon", 5, None, 5),
        }
        result = executer_tour(1, equipes, evenements, CENTROIDES_TEST, None)
        assert result.non_affectees == []
        for num, eq in equipes.items():
            assert len(eq.affectations) == 1, f"Équipe {num} sans affectation !"

    def test_capacite_jamais_depassee(self):
        """La capacité des événements ne doit jamais être dépassée."""
        voeux = [["Nantes", "Paris", "Lyon"]] * 10
        equipes = self._equipes_dict(10, voeux, "Nantes")
        evenements = {
            "Nantes": Evenement("Nantes", "44000 Nantes", 3, None, 3),
            "Paris": Evenement("Paris", "75011 Paris", 4, None, 4),
            "Lyon": Evenement("Lyon", "69003 Lyon", 10, None, 10),
        }
        executer_tour(1, equipes, evenements, CENTROIDES_TEST, None)
        for nom, comp in evenements.items():
            assert comp.places_restantes >= 0, f"{nom} dépasse sa capacité !"

    def test_pas_de_doublon_tour2(self):
        """Tour 2 : une équipe ne doit pas aller deux fois à le même événement."""
        equipes = {
            1: Equipe(
                numero=1, nom="TestEq", adresse="44000 Nantes",
                code_postal="44000", zone="B",
                horodatage=datetime(2026, 9, 1, 9, 0),
                nb_souhaite=2, voeux=["Nantes", "Paris", "Lyon"],
                affectations=["Nantes"],  # déjà affecté à Nantes au Tour 1
            )
        }
        evenements = {
            "Nantes": Evenement("Nantes", "44000 Nantes", 5, None, 4),
            "Paris": Evenement("Paris", "75011 Paris", 5, None, 5),
            "Lyon": Evenement("Lyon", "69003 Lyon", 5, None, 5),
        }
        result = executer_tour(2, equipes, evenements, CENTROIDES_TEST, None)
        if 1 in result.nouvelles_affectations:
            assert result.nouvelles_affectations[1] != "Nantes"


# ---------------------------------------------------------------------------
# Tests intégration — lancer_affectation avec templates CSV
# ---------------------------------------------------------------------------

class TestLancerAffectationIntegration:
    def test_toutes_equipes_ont_evenement(self):
        """Après Tour 1, aucune équipe ne doit être sans événement."""
        voeux_df = pd.read_csv("data/templates/voeux_2025_2026.csv", sep=";")
        comps_df = pd.read_csv("data/templates/evenements_2026_2027.csv", sep=";")
        equipes_df = pd.read_csv("data/templates/equipes_2025_2026.csv", sep=";")

        resultats, _ = lancer_affectation(
            voeux_df=voeux_df,
            evenements_df=comps_df,
            equipes_df=equipes_df,
            saison_vacances="2026_2027",
            nb_tours=1,
        )
        tour1 = resultats[0]
        assert tour1.non_affectees == [], (
            f"Équipes sans événement : {tour1.non_affectees}"
        )

    def test_capacite_jamais_depassee_integration(self):
        """La capacité de chaque événement ne doit jamais être dépassée."""
        voeux_df = pd.read_csv("data/templates/voeux_2025_2026.csv", sep=";")
        comps_df = pd.read_csv("data/templates/evenements_2026_2027.csv", sep=";")
        equipes_df = pd.read_csv("data/templates/equipes_2025_2026.csv", sep=";")

        resultats, _ = lancer_affectation(
            voeux_df=voeux_df,
            evenements_df=comps_df,
            equipes_df=equipes_df,
            saison_vacances="2026_2027",
            nb_tours=3,
        )
        # Reconstruire pour vérifier les places
        from modules.affectation import construire_evenements as _cc, construire_equipes as _ce

        voeux_enrichi = voeux_df.copy()
        adresses = equipes_df.set_index("numero_equipe")["adresse"].to_dict()
        noms_eq = equipes_df.set_index("numero_equipe")["nom_equipe"].to_dict()
        voeux_enrichi["adresse"] = voeux_enrichi["numero_equipe"].map(adresses).fillna("")
        voeux_enrichi["nom_equipe"] = voeux_enrichi["numero_equipe"].map(noms_eq).fillna("")

        equipes = _ce(voeux_enrichi)
        evenements = _cc(comps_df)

        for res in resultats:
            for num, nom_comp in res.nouvelles_affectations.items():
                evenements[nom_comp].places_restantes -= 1

        for nom, comp in evenements.items():
            assert comp.places_restantes >= 0, f"{nom} dépasse sa capacité !"

    def test_doublon_voeux_gere_integration(self):
        """Une équipe avec vœu dupliqué doit générer un warning dans lancer_affectation."""
        voeux_df = faire_voeux_df([{
            "numero_equipe": 99999,
            "voeu_1": "Régionale Pays de la Loire",
            "voeu_2": "Régionale Pays de la Loire",  # doublon intentionnel
            "voeu_3": "Régionale Lyon",
            "nb_evenements_souhaitees": 1,
        }])
        comps_df = pd.read_csv("data/templates/evenements_2026_2027.csv", sep=";")

        _, alertes = lancer_affectation(
            voeux_df=voeux_df,
            evenements_df=comps_df,
            saison_vacances="2026_2027",
            nb_tours=1,
        )
        doublons_warns = [a for a in alertes if "dupliqués" in a.lower() or "doublon" in a.lower()]
        assert len(doublons_warns) > 0, "Aucun warning pour les vœux dupliqués !"

    def test_metriques_cohérentes(self):
        """Les taux de satisfaction doivent être entre 0 et 100."""
        voeux_df = pd.read_csv("data/templates/voeux_2025_2026.csv", sep=";")
        comps_df = pd.read_csv("data/templates/evenements_2026_2027.csv", sep=";")
        equipes_df = pd.read_csv("data/templates/equipes_2025_2026.csv", sep=";")

        resultats, _ = lancer_affectation(
            voeux_df=voeux_df,
            evenements_df=comps_df,
            equipes_df=equipes_df,
            saison_vacances="2026_2027",
            nb_tours=1,
        )
        metriques = resultats[0].metriques
        assert 0 <= metriques.get("taux_voeu_1", 0) <= 100
        assert 0 <= metriques.get("taux_satisfaction", 0) <= 100


# ---------------------------------------------------------------------------
# Tests calculer_score_alternative
# ---------------------------------------------------------------------------

class TestCalculerScoreAlternative:
    def test_sans_adresse_retourne_inf(self, evenements_simples):
        """Équipe sans adresse → score infini (priorité maximale)."""
        eq = Equipe(
            numero=99, nom="SansAdresse", adresse="",
            code_postal=None, zone=None, horodatage=None,
            nb_souhaite=1, voeux=["Nantes", "Paris"],
        )
        score = calculer_score_alternative(
            eq, evenements_simples["Nantes"], evenements_simples, CENTROIDES_TEST, None
        )
        assert score == float("inf")

    def test_aucune_alternative_retourne_inf(self, evenements_simples):
        """Équipe avec un seul vœu (l'événement cible) → score infini."""
        eq = Equipe(
            numero=1, nom="MonoVoeu", adresse="44000 Nantes",
            code_postal="44000", zone="B",
            horodatage=datetime(2026, 9, 1, 9, 0),
            nb_souhaite=1, voeux=["Nantes"],
        )
        score = calculer_score_alternative(
            eq, evenements_simples["Nantes"], evenements_simples, CENTROIDES_TEST, None
        )
        assert score == float("inf")

    def test_alternative_pleine_non_comptee(self, evenements_simples):
        """Alternative avec 0 places restantes ne compte pas."""
        evenements_simples["Paris"].places_restantes = 0
        eq = Equipe(
            numero=1, nom="TestEq", adresse="44000 Nantes",
            code_postal="44000", zone="B",
            horodatage=datetime(2026, 9, 1, 9, 0),
            nb_souhaite=2, voeux=["Nantes", "Paris"],
        )
        score = calculer_score_alternative(
            eq, evenements_simples["Nantes"], evenements_simples, CENTROIDES_TEST, None
        )
        assert score == float("inf")

    def test_penalite_vacances_augmente_score(self, evenements_simples):
        """Alternative en vacances → score effectif augmenté de PENALITE_VACANCES_KM."""
        vacances_fictives = {
            "B": [(date(2026, 11, 8), date(2026, 11, 30))],
            "A": [],
            "C": [],
        }
        eq = Equipe(
            numero=1, nom="TestEq", adresse="44000 Nantes",
            code_postal="44000", zone="B",
            horodatage=datetime(2026, 9, 1, 9, 0),
            nb_souhaite=2, voeux=["Nantes", "Paris"],
        )
        score_sans = calculer_score_alternative(
            eq, evenements_simples["Nantes"], evenements_simples, CENTROIDES_TEST, None
        )
        score_avec = calculer_score_alternative(
            eq, evenements_simples["Nantes"], evenements_simples, CENTROIDES_TEST,
            vacances_fictives,
        )
        from utils.helpers import PENALITE_VACANCES_KM
        assert score_avec == pytest.approx(score_sans + PENALITE_VACANCES_KM)


# ---------------------------------------------------------------------------
# Tests multi-tours
# ---------------------------------------------------------------------------

class TestMultiTours:
    def _make_equipe(self, num, nb_souhaite, voeux, heure=9):
        return Equipe(
            numero=num, nom=f"Eq{num}", adresse="44000 Nantes",
            code_postal="44000", zone="B",
            horodatage=datetime(2026, 9, 1, heure, 0),
            nb_souhaite=nb_souhaite, voeux=voeux,
        )

    def _make_evenements(self):
        return {
            "Nantes": Evenement("Nantes", "44000 Nantes", 5, None, 5),
            "Paris": Evenement("Paris", "75011 Paris", 5, None, 5),
            "Lyon": Evenement("Lyon", "69003 Lyon", 5, None, 5),
        }

    def test_nb_souhaite_1_pas_de_2eme_affectation(self):
        """Équipe nb_souhaite=1 ne doit pas obtenir de 2ème événement au Tour 2."""
        equipes = {1: self._make_equipe(1, nb_souhaite=1, voeux=["Nantes", "Paris", "Lyon"])}
        comps = self._make_evenements()
        executer_tour(1, equipes, comps, CENTROIDES_TEST, None)
        executer_tour(2, equipes, comps, CENTROIDES_TEST, None)
        assert len(equipes[1].affectations) == 1

    def test_nb_souhaite_2_obtient_2_affectations(self):
        """Équipe nb_souhaite=2 doit obtenir exactement 2 affectations après 2 tours."""
        equipes = {1: self._make_equipe(1, nb_souhaite=2, voeux=["Nantes", "Paris", "Lyon"])}
        comps = self._make_evenements()
        executer_tour(1, equipes, comps, CENTROIDES_TEST, None)
        executer_tour(2, equipes, comps, CENTROIDES_TEST, None)
        assert len(equipes[1].affectations) == 2
        assert len(set(equipes[1].affectations)) == 2

    def test_affectations_distinctes_apres_tour2(self):
        """Après Tour 2, aucune équipe ne doit avoir deux fois le même événement."""
        equipes = {
            i: self._make_equipe(i, nb_souhaite=2, voeux=["Nantes", "Paris", "Lyon"], heure=9+i)
            for i in range(1, 4)
        }
        comps = self._make_evenements()
        executer_tour(1, equipes, comps, CENTROIDES_TEST, None)
        executer_tour(2, equipes, comps, CENTROIDES_TEST, None)
        for num, eq in equipes.items():
            assert len(eq.affectations) == len(set(eq.affectations)), \
                f"Équipe {num} a des doublons : {eq.affectations}"

    def test_integration_3_tours_remplissage(self):
        """Sur les données réelles, 3 tours remplissent tous les événements."""
        voeux_df = pd.read_csv("data/templates/voeux_2025_2026.csv", sep=";")
        comps_df = pd.read_csv("data/templates/evenements_2026_2027.csv", sep=";")
        equipes_df = pd.read_csv("data/templates/equipes_2025_2026.csv", sep=";")
        resultats, alertes = lancer_affectation(
            voeux_df=voeux_df, evenements_df=comps_df, equipes_df=equipes_df,
            saison_vacances="2026_2027", nb_tours=3,
        )
        assert resultats[0].non_affectees == []
        warnings_capacite = [a for a in alertes if "dépasse" in a]
        assert warnings_capacite == []
        for cle, val in resultats[0].metriques.items():
            if cle.startswith("remplissage_"):
                assert val > 0, f"Événement {cle} non remplie au Tour 1"


# ---------------------------------------------------------------------------
# Tests régression — bugs corrigés le 2026-03-31
# ---------------------------------------------------------------------------

class TestRegressionBugs:
    """Régressions pour les bugs corrigés le 2026-03-31."""

    def test_sursouscription_pas_de_double_affectation(self):
        """Régression bug #1 : sursouscription Phase A ne doit pas donner 2 affectations."""
        equipes = {
            i: Equipe(
                numero=i, nom=f"Eq{i}", adresse="44000 Nantes",
                code_postal="44000", zone="B",
                horodatage=datetime(2026, 9, 1, 8+i, 0),
                nb_souhaite=1, voeux=["Nantes", "Paris", "Lyon"],
            )
            for i in range(1, 6)  # 5 équipes veulent toutes Nantes (cap 2)
        }
        evenements = {
            "Nantes": Evenement("Nantes", "44000 Nantes", 2, None, 2),
            "Paris": Evenement("Paris", "75011 Paris", 5, None, 5),
            "Lyon": Evenement("Lyon", "69003 Lyon", 5, None, 5),
        }
        executer_tour(1, equipes, evenements, CENTROIDES_TEST, None)
        for num, eq in equipes.items():
            assert len(eq.affectations) == 1, \
                f"Équipe {num} a {len(eq.affectations)} affectations : {eq.affectations}"

    def test_places_restantes_jamais_negatif_sursouscription(self):
        """Régression bug #1 : places_restantes ne doit pas être négatif après sursouscription."""
        equipes = {
            i: Equipe(
                numero=i, nom=f"Eq{i}", adresse="44000 Nantes",
                code_postal="44000", zone="B",
                horodatage=datetime(2026, 9, 1, 8+i, 0),
                nb_souhaite=1, voeux=["Nantes", "Paris", "Lyon"],
            )
            for i in range(1, 10)  # 9 équipes, capacités : 2 + 3 + 3 = 8
        }
        evenements = {
            "Nantes": Evenement("Nantes", "44000 Nantes", 2, None, 2),
            "Paris": Evenement("Paris", "75011 Paris", 3, None, 3),
            "Lyon": Evenement("Lyon", "69003 Lyon", 3, None, 3),
        }
        executer_tour(1, equipes, evenements, CENTROIDES_TEST, None)
        for nom, comp in evenements.items():
            assert comp.places_restantes >= 0, \
                f"{nom} : places_restantes = {comp.places_restantes}"

    def test_doublon_detecte_dans_voeux_bruts(self):
        """Régression bug #2 : doublon détecté sur vœux bruts même après déduplication."""
        voeux_df = pd.DataFrame([{
            "numero_equipe": 1,
            "voeu_1": "Nantes", "voeu_2": "Nantes", "voeu_3": "Paris",
            "nb_evenements_souhaitees": 1,
        }])
        comps_df = pd.DataFrame([
            {"nom_evenement": "Nantes", "adresse": "44000 Nantes", "capacite_max": 10},
            {"nom_evenement": "Paris", "adresse": "75011 Paris", "capacite_max": 10},
        ])
        alertes = valider_voeux(voeux_df, comps_df)
        assert any("dupliqués" in a for a in alertes), \
            "Le warning doublon doit être émis même si _extraire_voeux déduplique"


# ---------------------------------------------------------------------------
# Fallback Tour 1 — événement encore ouvert le plus proche
# ---------------------------------------------------------------------------

class TestTrouverFallback:
    """Le fallback privilégie la proximité, pas le nombre de places libres."""

    def _equipe(self, adresse, affectations=()):
        return Equipe(
            numero=1, nom="Test", adresse=adresse, code_postal=None, zone=None,
            horodatage=None, nb_souhaite=1, voeux=[], affectations=list(affectations),
        )

    def test_prend_le_plus_proche_meme_avec_une_seule_place(self):
        """Lyon : 1 place à 0 km bat 20 places à 600 km."""
        evenements = {
            "Lyon": Evenement("Lyon", "69003 Lyon", 24, None, 1),
            "Nantes": Evenement("Nantes", "44000 Nantes", 24, None, 20),
        }
        eq = self._equipe("69003 Lyon")
        assert _trouver_fallback(eq, evenements, CENTROIDES_TEST) == "Lyon"

    def test_ignore_les_evenements_complets(self):
        """Le plus proche étant complet, on retient le suivant le plus proche."""
        evenements = {
            "Lyon": Evenement("Lyon", "69003 Lyon", 24, None, 0),
            "Clermont": Evenement("Clermont", "63000 Clermont-Ferrand", 24, None, 1),
            "Nantes": Evenement("Nantes", "44000 Nantes", 24, None, 20),
        }
        eq = self._equipe("69003 Lyon")
        assert _trouver_fallback(eq, evenements, CENTROIDES_TEST) == "Clermont"

    def test_ignore_les_evenements_deja_affectes(self):
        """Un événement déjà obtenu n'est pas proposé une seconde fois."""
        evenements = {
            "Lyon": Evenement("Lyon", "69003 Lyon", 24, None, 5),
            "Clermont": Evenement("Clermont", "63000 Clermont-Ferrand", 24, None, 1),
        }
        eq = self._equipe("69003 Lyon", affectations=["Lyon"])
        assert _trouver_fallback(eq, evenements, CENTROIDES_TEST) == "Clermont"

    def test_sans_adresse_retombe_sur_le_plus_de_places(self):
        """Distance non calculable → départage par places restantes."""
        evenements = {
            "Lyon": Evenement("Lyon", "69003 Lyon", 24, None, 1),
            "Nantes": Evenement("Nantes", "44000 Nantes", 24, None, 20),
        }
        eq = self._equipe("")
        assert _trouver_fallback(eq, evenements, CENTROIDES_TEST) == "Nantes"

    def test_distance_egale_departage_par_places(self):
        """À distance identique, l'événement le moins tendu est retenu."""
        evenements = {
            "A": Evenement("A", "69003 Lyon", 24, None, 2),
            "B": Evenement("B", "69003 Lyon", 24, None, 9),
        }
        eq = self._equipe("69003 Lyon")
        assert _trouver_fallback(eq, evenements, CENTROIDES_TEST) == "B"

    def test_aucune_place_disponible(self):
        """Tous les événements complets → aucun fallback possible."""
        evenements = {
            "Lyon": Evenement("Lyon", "69003 Lyon", 24, None, 0),
            "Nantes": Evenement("Nantes", "44000 Nantes", 24, None, 0),
        }
        eq = self._equipe("69003 Lyon")
        assert _trouver_fallback(eq, evenements, CENTROIDES_TEST) is None
