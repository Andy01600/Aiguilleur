"""
Fonctions utilitaires partagées entre les modules Magouilleuse.
"""

import json
import re
import functools
import urllib.request
from collections.abc import Callable
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
    # Zone A — Besançon, Bordeaux, Clermont-Ferrand, Dijon, Grenoble, Limoges, Lyon, Poitiers
    "25": "A", "39": "A", "70": "A", "90": "A",              # Besançon
    "24": "A", "33": "A", "40": "A", "47": "A", "64": "A",   # Bordeaux
    "03": "A", "15": "A", "43": "A", "63": "A",              # Clermont-Ferrand
    "21": "A", "58": "A", "71": "A", "89": "A",              # Dijon
    "07": "A", "26": "A", "38": "A", "73": "A", "74": "A",   # Grenoble
    "19": "A", "23": "A", "87": "A",                         # Limoges
    "01": "A", "42": "A", "69": "A",                         # Lyon
    "16": "A", "17": "A", "79": "A", "86": "A",              # Poitiers
    # Zone B — Aix-Marseille, Amiens, Caen, Lille, Nancy-Metz, Nantes, Nice,
    #          Orléans-Tours, Reims, Rennes, Rouen, Strasbourg, Corse
    "04": "B", "05": "B", "13": "B",                         # Aix-Marseille
    "02": "B", "60": "B", "80": "B",                         # Amiens
    "14": "B", "50": "B", "61": "B",                         # Caen
    "59": "B", "62": "B",                                    # Lille
    "54": "B", "55": "B", "57": "B", "88": "B",              # Nancy-Metz
    "44": "B", "49": "B", "53": "B", "72": "B", "85": "B",   # Nantes
    "06": "B", "83": "B", "84": "B",                         # Nice
    "18": "B", "28": "B", "36": "B", "37": "B", "41": "B", "45": "B",  # Orléans-Tours
    "08": "B", "10": "B", "51": "B", "52": "B",              # Reims
    "22": "B", "29": "B", "35": "B", "56": "B",              # Rennes
    "27": "B", "76": "B",                                    # Rouen
    "67": "B", "68": "B",                                    # Strasbourg
    "2A": "B", "2B": "B",                                    # Corse
    # Zone C — Créteil, Montpellier, Paris, Toulouse, Versailles
    "77": "C", "93": "C", "94": "C",                         # Créteil
    "11": "C", "30": "C", "34": "C", "48": "C", "66": "C",   # Montpellier
    "75": "C",                                               # Paris
    "09": "C", "12": "C", "31": "C", "32": "C", "46": "C",
    "65": "C", "81": "C", "82": "C",                         # Toulouse
    "78": "C", "91": "C", "92": "C", "95": "C",              # Versailles
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


# Type alias pour les fonctions de distance interchangeables
DistanceFn = Callable[[str, str, dict[str, tuple[float, float]]], float | None]


def distance_route_estimee(
    adresse1: str,
    adresse2: str,
    centroides: dict[str, tuple[float, float]],
) -> float | None:
    """Haversine × 1.3 — approximation de la distance routière."""
    d = distance_entre_adresses(adresse1, adresse2, centroides)
    return d * 1.3 if d is not None else None


# ---------------------------------------------------------------------------
# OSRM — distances routières réelles
# ---------------------------------------------------------------------------

def _appel_osrm_route(lat1: float, lon1: float, lat2: float, lon2: float) -> float | None:
    """Appel individuel OSRM route. Retourne la distance en km ou None."""
    url = (
        f"http://router.project-osrm.org/route/v1/driving/"
        f"{lon1},{lat1};{lon2},{lat2}?overview=false"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        if data.get("code") == "Ok" and data.get("routes"):
            return data["routes"][0]["distance"] / 1000.0
    except Exception:
        pass
    return None


def _construire_matrice_osrm(
    coords: list[tuple[float, float]],
    indices_sources: list[int],
    indices_destinations: list[int],
) -> list[list[float | None]] | None:
    """
    Appel OSRM Table API pour une matrice rectangulaire.
    coords : liste de (lat, lon) pour tous les points.
    Retourne matrice [sources × destinations] en km, ou None si échec.
    """
    if not coords or not indices_sources or not indices_destinations:
        return None
    coords_str = ";".join(f"{lon},{lat}" for lat, lon in coords)
    sources_str = ";".join(str(i) for i in indices_sources)
    destinations_str = ";".join(str(i) for i in indices_destinations)
    url = (
        f"http://router.project-osrm.org/table/v1/driving/{coords_str}"
        f"?sources={sources_str}&destinations={destinations_str}&annotations=distance"
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read())
        if data.get("code") != "Ok":
            return None
        raw = data["distances"]
        return [
            [cell / 1000.0 if cell is not None else None for cell in row]
            for row in raw
        ]
    except Exception:
        return None


def creer_fn_distance_osrm(
    centroides: dict[str, tuple[float, float]],
    adresses_equipes: list[str] | None = None,
    adresses_competitions: list[str] | None = None,
) -> DistanceFn:
    """
    Crée une fonction distance utilisant OSRM (Table API + fallback route).

    Si adresses_equipes et adresses_competitions sont fournis, tente d'abord
    un appel matriciel (Table API) pour pré-calculer toutes les distances.
    Sinon, ou en cas d'échec, fait des appels individuels avec cache.
    """
    cache: dict[tuple[str, str], float | None] = {}

    # Pré-calcul matriciel si les adresses sont connues
    if adresses_equipes and adresses_competitions:
        # Extraire les CP uniques
        cps_equipes = []
        for adr in adresses_equipes:
            cp = extraire_code_postal(adr)
            if cp and coordonnees_code_postal(cp, centroides):
                cps_equipes.append(cp)
        cps_comps = []
        for adr in adresses_competitions:
            cp = extraire_code_postal(adr)
            if cp and coordonnees_code_postal(cp, centroides):
                cps_comps.append(cp)

        cps_equipes = list(dict.fromkeys(cps_equipes))  # déduplique, conserve l'ordre
        cps_comps = list(dict.fromkeys(cps_comps))

        if cps_equipes and cps_comps:
            # Construire la liste de coordonnées : d'abord équipes, puis compétitions
            tous_cps = cps_equipes + cps_comps
            coords = [coordonnees_code_postal(cp, centroides) for cp in tous_cps]
            idx_src = list(range(len(cps_equipes)))
            idx_dst = list(range(len(cps_equipes), len(tous_cps)))

            matrice = _construire_matrice_osrm(coords, idx_src, idx_dst)
            if matrice is not None:
                for i, cp_eq in enumerate(cps_equipes):
                    for j, cp_co in enumerate(cps_comps):
                        cache[(cp_eq, cp_co)] = matrice[i][j]
                        cache[(cp_co, cp_eq)] = matrice[i][j]

    def fn_distance(adresse1: str, adresse2: str, centroides_: dict) -> float | None:
        cp1 = extraire_code_postal(adresse1)
        cp2 = extraire_code_postal(adresse2)
        if cp1 is None or cp2 is None:
            return None

        cle = (cp1, cp2)
        if cle in cache:
            return cache[cle]

        # Appel individuel OSRM
        c1 = coordonnees_code_postal(cp1, centroides_)
        c2 = coordonnees_code_postal(cp2, centroides_)
        if c1 is None or c2 is None:
            return None

        dist = _appel_osrm_route(c1[0], c1[1], c2[0], c2[1])
        if dist is None:
            # Fallback : route estimée (×1.3)
            dist_hav = haversine(c1[0], c1[1], c2[0], c2[1])
            dist = dist_hav * 1.3

        cache[cle] = dist
        cache[(cp2, cp1)] = dist
        return dist

    return fn_distance


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
        # Forcer le point-virgule comme séparateur.
        # Les adresses contiennent des virgules : le point-virgule évite toute ambiguïté.
        df = pd.read_csv(source, encoding="utf-8", sep=";")
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
