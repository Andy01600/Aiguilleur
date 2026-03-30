"""
Fonctions utilitaires partagées entre les modules Magouilleuse.
"""

import json
import re
import functools
from datetime import date
from io import BytesIO
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Coefficient de compacité (pénalité pour les "trous" entre compétitions)
LAMBDA_DEFAULT: float = 0.1

# Pénalité en km ajoutée à la distance d'une alternative qui tombe pendant
# les vacances de la zone de l'équipe (tie-break affectation)
PENALITE_VACANCES_KM: float = 200.0

# Jours fériés pertinents pour la saison FTC (novembre–janvier)
# Format : (mois, jour)
JOURS_FERIES_SAISON = [(11, 1), (11, 11), (12, 25), (1, 1)]

# Table département → zone de vacances scolaires
# Source : Éducation Nationale
ZONE_PAR_DEPARTEMENT: dict[str, str] = {
    # Zone A
    "01": "A", "03": "A", "07": "A", "15": "A", "21": "A", "25": "A",
    "26": "A", "33": "A", "38": "A", "39": "A", "42": "A", "43": "A",
    "47": "A", "58": "A", "63": "A", "69": "A", "70": "A", "71": "A",
    "73": "A", "74": "A", "79": "A", "86": "A", "87": "A",
    # Zone B
    "02": "B", "06": "B", "08": "B", "10": "B", "13": "B", "14": "B",
    "16": "B", "17": "B", "18": "B", "22": "B", "23": "B", "24": "B",
    "29": "B", "35": "B", "36": "B", "37": "B", "40": "B", "41": "B",
    "44": "B", "49": "B", "50": "B", "51": "B", "52": "B", "53": "B",
    "54": "B", "55": "B", "56": "B", "57": "B", "59": "B", "60": "B",
    "61": "B", "62": "B", "67": "B", "68": "B", "72": "B", "76": "B",
    "80": "B", "83": "B", "85": "B",
    # Zone C
    "04": "C", "05": "C", "09": "C", "11": "C", "12": "C", "19": "C",
    "30": "C", "31": "C", "32": "C", "34": "C", "45": "C", "46": "C",
    "48": "C", "64": "C", "65": "C", "66": "C", "75": "C", "77": "C",
    "78": "C", "81": "C", "82": "C", "84": "C", "89": "C", "91": "C",
    "92": "C", "93": "C", "94": "C", "95": "C",
}

# ---------------------------------------------------------------------------
# Résolution adresse → code postal → département → zone
# ---------------------------------------------------------------------------

def extraire_code_postal(adresse: str) -> str | None:
    """Extrait le premier code postal (5 chiffres) d'une adresse complète."""
    match = re.search(r'\b(\d{5})\b', adresse)
    return match.group(1) if match else None


def code_postal_vers_departement(code_postal: str) -> str:
    """
    Convertit un code postal en numéro de département.
    Gère les cas particuliers : Corse (20xxx → 2A ou 2B), DOM (97x).
    """
    cp = str(code_postal).zfill(5)
    if cp.startswith("97"):
        return cp[:3]
    if cp.startswith("20"):
        # Corse : 20000-20190 et 20700 → 2A, reste → 2B
        num = int(cp)
        if num <= 20190 or num >= 20700:
            return "2A"
        return "2B"
    return cp[:2]


def departement_vers_zone(departement: str) -> str | None:
    """Retourne la zone de vacances (A, B ou C) pour un département, ou None."""
    return ZONE_PAR_DEPARTEMENT.get(str(departement).zfill(2))


def adresse_vers_zone(adresse: str) -> str | None:
    """Chaîne complète : adresse → zone de vacances scolaires."""
    cp = extraire_code_postal(adresse)
    if cp is None:
        return None
    dept = code_postal_vers_departement(cp)
    return departement_vers_zone(dept)


# ---------------------------------------------------------------------------
# Coordonnées GPS — centroïdes codes postaux
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def charger_centroides(filepath: str = "data/centroides_cp.csv") -> dict[str, tuple[float, float]]:
    """
    Charge le CSV La Poste des centroïdes et retourne {code_postal: (lat, lon)}.
    Plusieurs communes peuvent partager un même CP : on fait la moyenne.
    """
    chemin = Path(filepath)
    if not chemin.exists():
        raise FileNotFoundError(
            f"Fichier centroïdes introuvable : {filepath}\n"
            "Téléchargez-le depuis : "
            "https://datanova.laposte.fr/datasets/laposte-hexasmal"
        )
    df = pd.read_csv(
        chemin,
        usecols=["code_postal", "latitude", "longitude"],
        dtype={"code_postal": str},
        encoding="utf-8",
    )
    df["code_postal"] = df["code_postal"].str.zfill(5)
    df = df.dropna(subset=["latitude", "longitude"])
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df = df.dropna(subset=["latitude", "longitude"])
    moyennes = df.groupby("code_postal")[["latitude", "longitude"]].mean()
    return {cp: (row["latitude"], row["longitude"]) for cp, row in moyennes.iterrows()}


def coordonnees_code_postal(
    code_postal: str,
    centroides: dict[str, tuple[float, float]],
) -> tuple[float, float] | None:
    """Retourne (lat, lon) pour un code postal, ou None si inconnu."""
    return centroides.get(str(code_postal).zfill(5))


# ---------------------------------------------------------------------------
# Distance Haversine
# ---------------------------------------------------------------------------

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Retourne la distance en km entre deux points GPS (formule Haversine)."""
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(a))


def distance_entre_adresses(
    adresse1: str,
    adresse2: str,
    centroides: dict[str, tuple[float, float]],
) -> float | None:
    """
    Calcule la distance en km entre deux adresses françaises.
    Retourne None si l'un des codes postaux est introuvable dans les centroïdes.
    """
    cp1 = extraire_code_postal(adresse1)
    cp2 = extraire_code_postal(adresse2)
    if cp1 is None or cp2 is None:
        return None
    coords1 = coordonnees_code_postal(cp1, centroides)
    coords2 = coordonnees_code_postal(cp2, centroides)
    if coords1 is None or coords2 is None:
        return None
    return haversine(coords1[0], coords1[1], coords2[0], coords2[1])


# ---------------------------------------------------------------------------
# Calendrier des vacances scolaires
# ---------------------------------------------------------------------------

def charger_vacances(
    saison: str = "2026_2027",
    dossier: str = "data/vacances",
) -> dict[str, list[tuple[date, date]]]:
    """
    Charge le JSON des vacances scolaires pour la saison donnée.
    Retourne {'A': [(debut, fin), ...], 'B': [...], 'C': [...]}.
    """
    fichier = Path(dossier) / f"vacances_{saison}.json"
    if not fichier.exists():
        raise FileNotFoundError(f"Fichier vacances introuvable : {fichier}")
    with open(fichier, encoding="utf-8") as f:
        data = json.load(f)
    resultat: dict[str, list[tuple[date, date]]] = {}
    for zone, periodes in data.items():
        resultat[zone] = [
            (date.fromisoformat(debut), date.fromisoformat(fin))
            for debut, fin in periodes
        ]
    return resultat


def est_en_vacances(d: date, zone: str, vacances: dict[str, list[tuple[date, date]]]) -> bool:
    """Retourne True si la date d tombe dans une période de vacances de la zone."""
    for debut, fin in vacances.get(zone, []):
        if debut <= d <= fin:
            return True
    return False


def est_jour_ferie(d: date) -> bool:
    """Retourne True si la date est un jour férié national exclu de la planification."""
    return (d.month, d.day) in JOURS_FERIES_SAISON


def samedis_dans_fenetre(debut: date, fin: date) -> list[date]:
    """Retourne la liste de tous les samedis (weekday==5) dans [debut, fin]."""
    from datetime import timedelta
    jours = (fin - debut).days + 1
    return [
        debut + timedelta(days=i)
        for i in range(jours)
        if (debut + timedelta(days=i)).weekday() == 5
    ]


# ---------------------------------------------------------------------------
# Lecture et validation de fichiers
# ---------------------------------------------------------------------------

def lire_fichier(
    source,
    colonnes_requises: list[str],
    nom_fichier: str = "fichier",
) -> pd.DataFrame:
    """
    Lit un fichier CSV ou Excel (chemin ou objet fichier Streamlit).
    Vérifie que les colonnes requises sont présentes.
    Lève ValueError avec un message en français si ce n'est pas le cas.
    """
    if hasattr(source, "name"):
        nom = source.name.lower()
    else:
        nom = str(source).lower()

    if nom.endswith(".csv"):
        # Forcer la virgule comme séparateur (standard CSV).
        # sep=None + engine="python" peut se tromper quand les adresses
        # contiennent des virgules, même entre guillemets.
        try:
            df = pd.read_csv(source, encoding="utf-8", sep=",")
        except Exception:
            df = pd.read_csv(source, encoding="utf-8", sep=None, engine="python")
    elif nom.endswith((".xlsx", ".xls")):
        df = pd.read_excel(source)
    else:
        raise ValueError(f"Format non supporté pour {nom_fichier} : utilisez CSV ou Excel (.xlsx).")

    # Normaliser les noms de colonnes
    df.columns = [str(c).strip() for c in df.columns]

    manquantes = [c for c in colonnes_requises if c not in df.columns]
    if manquantes:
        raise ValueError(
            f"Colonnes manquantes dans {nom_fichier} : {', '.join(manquantes)}\n"
            f"Colonnes trouvées : {', '.join(df.columns)}"
        )
    return df


# ---------------------------------------------------------------------------
# Export Excel multi-feuilles
# ---------------------------------------------------------------------------

def exporter_excel(sheets: dict[str, pd.DataFrame]) -> bytes:
    """
    Génère un fichier Excel avec une feuille par entrée du dictionnaire.
    Retourne les bytes du fichier pour le téléchargement Streamlit.
    """
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for nom_feuille, df in sheets.items():
            # Excel limite les noms de feuilles à 31 caractères
            nom_court = nom_feuille[:31]
            df.to_excel(writer, sheet_name=nom_court, index=False)
    return buffer.getvalue()
