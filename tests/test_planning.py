"""
Tests unitaires — Module 1 : Planification du calendrier.
"""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.planning import (
    SamediCandidat,
    calculer_nb_trous,
    calculer_score_total,
    generer_planning,
    planning_vers_dataframe,
    recherche_exhaustive,
    scorer_samedi,
)
from utils.helpers import (
    charger_vacances,
    est_en_vacances,
    est_jour_ferie,
    samedis_dans_fenetre,
)

# ---------------------------------------------------------------------------
# Fixture : vacances scolaires 2025-2026 (fichier réel)
# ---------------------------------------------------------------------------

@pytest.fixture
def vacances_25_26():
    return charger_vacances("2025_2026")


@pytest.fixture
def vacances_26_27():
    return charger_vacances("2026_2027")


# ---------------------------------------------------------------------------
# Tests utils/helpers — fonctions de base
# ---------------------------------------------------------------------------

class TestEstJourFerie:
    def test_toussaint(self):
        assert est_jour_ferie(date(2026, 11, 1))

    def test_armistice(self):
        assert est_jour_ferie(date(2026, 11, 11))

    def test_noel(self):
        assert est_jour_ferie(date(2026, 12, 25))

    def test_jour_an(self):
        assert est_jour_ferie(date(2027, 1, 1))

    def test_non_ferie(self):
        assert not est_jour_ferie(date(2026, 11, 8))


class TestSamedisInFenetre:
    def test_compte_samedis(self):
        # Novembre 2026 : samedis 7, 14, 21, 28
        samedis = samedis_dans_fenetre(date(2026, 11, 1), date(2026, 11, 30))
        assert len(samedis) == 4
        assert all(d.weekday() == 5 for d in samedis)

    def test_fenetre_vide(self):
        # Pas de samedi dans une semaine hors samedi
        samedis = samedis_dans_fenetre(date(2026, 11, 1), date(2026, 11, 6))
        assert len(samedis) == 0

    def test_inclut_bornes(self):
        # 1er novembre 2025 est un samedi
        samedis = samedis_dans_fenetre(date(2025, 11, 1), date(2025, 11, 1))
        assert len(samedis) == 1
        assert samedis[0] == date(2025, 11, 1)


class TestEstEnVacances:
    def test_toussaint_zone_a(self, vacances_25_26):
        # Toussaint 2025 : 18 oct – 3 nov (toutes zones)
        assert est_en_vacances(date(2025, 10, 25), "A", vacances_25_26)

    def test_hors_vacances(self, vacances_25_26):
        # Mi-novembre : plus de vacances
        assert not est_en_vacances(date(2025, 11, 15), "A", vacances_25_26)

    def test_noel_toutes_zones(self, vacances_25_26):
        assert est_en_vacances(date(2025, 12, 25), "A", vacances_25_26)
        assert est_en_vacances(date(2025, 12, 25), "B", vacances_25_26)
        assert est_en_vacances(date(2025, 12, 25), "C", vacances_25_26)


# ---------------------------------------------------------------------------
# Tests scoring
# ---------------------------------------------------------------------------

class TestScorerSamedi:
    def test_hors_vacances(self, vacances_25_26):
        # Un samedi de novembre hors vacances → score 0
        score, zones = scorer_samedi(date(2025, 11, 15), vacances_25_26)
        assert score == 0.0
        assert zones == []

    def test_pendant_noel_toutes_zones(self, vacances_25_26):
        # Noël : toutes zones en vacances, sans équipes = 3 zones
        score, zones = scorer_samedi(date(2025, 12, 27), vacances_25_26)
        assert score == 3.0
        assert set(zones) == {"A", "B", "C"}

    def test_avec_equipes_par_zone(self, vacances_25_26):
        # Pendant vacances A uniquement, 10 équipes en zone A
        equipes_par_zone = {"A": 10, "B": 5, "C": 8}
        score, zones = scorer_samedi(
            date(2026, 2, 14),  # vacances zone A et B
            vacances_25_26,
            equipes_par_zone=equipes_par_zone,
        )
        assert score == 15.0  # 10 (A) + 5 (B)
        assert "A" in zones
        assert "B" in zones


# ---------------------------------------------------------------------------
# Tests calcul nb_trous
# ---------------------------------------------------------------------------

class TestCalculerNbTrous:
    def test_aucun_trou(self):
        # 3 samedis consécutifs
        dates = [date(2026, 11, 7), date(2026, 11, 14), date(2026, 11, 21)]
        assert calculer_nb_trous(dates) == 0

    def test_un_trou(self):
        # s1, s3 (s2 manque)
        dates = [date(2026, 11, 7), date(2026, 11, 21)]
        assert calculer_nb_trous(dates) == 1

    def test_deux_trous(self):
        dates = [date(2026, 11, 7), date(2026, 11, 28)]
        assert calculer_nb_trous(dates) == 2

    def test_une_seule_date(self):
        assert calculer_nb_trous([date(2026, 11, 7)]) == 0


# ---------------------------------------------------------------------------
# Tests recherche_exhaustive
# ---------------------------------------------------------------------------

class TestRechercheExhaustive:
    def test_selectionne_meilleur(self, vacances_25_26):
        """Doit choisir les samedis hors vacances."""
        # Nov 15 et Nov 22 : hors vacances. Nov 1 : vacances (toutes zones)
        candidats = [
            SamediCandidat(date(2025, 11, 1), 3.0, ["A", "B", "C"]),  # Toussaint !
            SamediCandidat(date(2025, 11, 15), 0.0, []),
            SamediCandidat(date(2025, 11, 22), 0.0, []),
        ]
        dates = recherche_exhaustive(candidats, n=2, dates_forcees=[])
        assert date(2025, 11, 15) in dates
        assert date(2025, 11, 22) in dates
        assert date(2025, 11, 1) not in dates

    def test_dates_forcees_respectees(self):
        candidats = [
            SamediCandidat(date(2026, 11, 7), 0.0, []),
            SamediCandidat(date(2026, 11, 14), 0.0, []),
        ]
        dates_forcees = [date(2026, 11, 21)]
        dates = recherche_exhaustive(candidats, n=2, dates_forcees=dates_forcees)
        assert date(2026, 11, 21) in dates
        assert len(dates) == 2

    def test_trop_peu_candidats(self):
        candidats = [SamediCandidat(date(2026, 11, 7), 0.0, [])]
        with pytest.raises(ValueError):
            recherche_exhaustive(candidats, n=3, dates_forcees=[])


# ---------------------------------------------------------------------------
# Tests intégration — generer_planning avec templates CSV
# ---------------------------------------------------------------------------

class TestGenererPlanningIntegration:
    def test_planning_6_competitions(self):
        """Test avec le template réel des 6 compétitions."""
        import pandas as pd

        competitions_df = pd.read_csv("data/templates/competitions_2026_2027.csv")
        result = generer_planning(
            competitions_df=competitions_df,
            equipes_df=None,
            fenetre_debut=date(2026, 11, 1),
            fenetre_fin=date(2027, 1, 31),
            saison_vacances="2026_2027",
        )
        assert len(result.dates) == 6
        assert all(d.weekday() == 5 for d in result.dates)
        assert len(set(result.dates)) == 6  # toutes uniques

    def test_planning_exclut_feries(self):
        """Le 1er novembre (Toussaint) ne doit pas être sélectionné."""
        import pandas as pd

        competitions_df = pd.read_csv("data/templates/competitions_2026_2027.csv")
        result = generer_planning(
            competitions_df=competitions_df,
            equipes_df=None,
            fenetre_debut=date(2026, 11, 1),
            fenetre_fin=date(2027, 1, 31),
            saison_vacances="2026_2027",
        )
        # 1er novembre 2026 est un dimanche donc pas candidat de toute façon
        # mais on vérifie qu'aucun jour férié n'est dans les résultats
        from utils.helpers import est_jour_ferie
        for d in result.dates:
            assert not est_jour_ferie(d), f"{d} est un jour férié !"

    def test_planning_avec_equipes(self):
        """Avec le fichier équipes, le scoring doit être basé sur les nb d'équipes."""
        import pandas as pd

        competitions_df = pd.read_csv("data/templates/competitions_2026_2027.csv")
        equipes_df = pd.read_csv("data/templates/equipes_2025_2026.csv")
        result = generer_planning(
            competitions_df=competitions_df,
            equipes_df=equipes_df,
            fenetre_debut=date(2026, 11, 1),
            fenetre_fin=date(2027, 1, 31),
            saison_vacances="2026_2027",
        )
        assert len(result.dates) == 6

    def test_planning_vers_dataframe(self):
        """Le DataFrame exporté doit avoir les bonnes colonnes."""
        import pandas as pd

        competitions_df = pd.read_csv("data/templates/competitions_2026_2027.csv")
        result = generer_planning(
            competitions_df=competitions_df,
            equipes_df=None,
            fenetre_debut=date(2026, 11, 1),
            fenetre_fin=date(2027, 1, 31),
            saison_vacances="2026_2027",
        )
        df = planning_vers_dataframe(result)
        assert "Date" in df.columns
        assert "Compétition" in df.columns
        assert len(df) == 6
