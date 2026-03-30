# SPECS.md — Spécifications détaillées de Magouilleuse

> Document de référence pour le développement de l'outil de planification FTC France.
> Mis à jour le 2026-03-29.

---

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Contexte métier](#2-contexte-métier)
3. [Module 1 — Planification du calendrier](#3-module-1--planification-du-calendrier)
4. [Module 2 — Affectation des équipes](#4-module-2--affectation-des-équipes)
5. [Interface utilisateur](#5-interface-utilisateur)
6. [Formats de données](#6-formats-de-données)
7. [Résolution automatique adresse → zone / coordonnées](#7-résolution-automatique-adresse--zone--coordonnées)
8. [Contraintes et règles métier](#8-contraintes-et-règles-métier)

---

## 1. Vue d'ensemble

**Magouilleuse** est une application web Python/Streamlit en deux modules **indépendants** :

```
[Fichiers CSV/Excel en entrée]
        │
        ▼
┌───────────────────┐     ┌──────────────────────┐
│  MODULE 1         │     │  MODULE 2             │
│  Planification    │     │  Affectation          │
│  des compétitions │     │  des équipes          │
└───────────────────┘     └──────────────────────┘
        │                           │
        ▼                           ▼
[Calendrier optimal]       [Listes équipes/compétitions]
```

Les deux modules sont **utilisables séparément** : un utilisateur peut lancer uniquement le Module 1 pour générer un planning, ou uniquement le Module 2 si le planning est déjà connu.

---

## 2. Contexte métier

### Compétition FIRST Tech Challenge

- Chaque compétition se déroule sur **1 journée, un samedi**
- **Une seule compétition par samedi** (jamais deux compétitions le même jour)
- Une équipe peut participer à **1, 2 ou 3 compétitions** dans la saison
- **Priorité absolue** : chaque équipe doit faire **au moins 1 compétition**
- Les équipes souhaitant une 2ème ou 3ème compétition sont traitées après que toutes les équipes aient leur 1ère

### Dimensionnement

| Saison | Équipes | Compétitions |
|--------|---------|--------------|
| 2025-2026 | ~100 équipes | À déterminer |
| 2026-2027 | ~110 équipes | 6 compétitions |

> Les données réelles de la saison 2025-2026 serviront de jeu de données de test.

### Vacances scolaires françaises

Les vacances scolaires françaises sont **zonées** en 3 zones. La zone est déterminée automatiquement depuis l'adresse (voir Section 7).

| Zone | Académies principales |
|------|-----------------------|
| A    | Besançon, Bordeaux, Clermont-Ferrand, Dijon, Grenoble, Limoges, Lyon, Poitiers |
| B    | Aix-Marseille, Amiens, Caen, Lille, Nancy-Metz, Nantes, Nice, Orléans-Tours, Reims, Rennes, Rouen, Strasbourg |
| C    | Créteil, Montpellier, Paris, Toulouse, Versailles |

> Règle critique : une compétition planifiée pendant les vacances de zone B n'impacte **que** les équipes de zone B inscrites à cette compétition.

### Saison FTC France 2025-2026

La saison FTC se déroule typiquement d'**octobre à février**.
Les compétitions régionales ont lieu entre **novembre et janvier**.
Le **championnat national** est hors scope de cet outil.

---

## 3. Module 1 — Planification du calendrier

### 3.1 Objectif

Proposer un calendrier de compétitions qui :
1. **Minimise le nombre d'équipes impactées par les vacances scolaires**
2. **Maximise les compétitions consécutives** (samedis enchaînés, pas d'écart inutile)

### 3.2 Entrées

| Champ | Type | Description |
|-------|------|-------------|
| `competitions` | fichier | Fichier Excel/CSV — nom, adresse complète, capacité max |
| `equipes` | fichier | Fichier Excel/CSV — numéro, nom, adresse complète (optionnel en V1) |
| `fenetre_debut` | date | Date de début de la fenêtre de planification |
| `fenetre_fin` | date | Date de fin de la fenêtre de planification |

> **Note V1 :** Si le fichier équipes n'est pas fourni, l'algorithme minimise le nombre de samedis qui tombent dans des vacances scolaires (toutes zones confondues).

### 3.3 Sorties

- Liste des dates proposées pour chaque compétition, triées chronologiquement
- Score d'impact de chaque date (nb d'équipes potentiellement impactées)
- Visualisation calendrier interactif (Plotly)
- Export Excel avec le planning final

### 3.4 Algorithme

**Étape 1 : Générer les candidats**

```
1. Lister tous les samedis dans [fenetre_debut, fenetre_fin]
2. Exclure les samedis tombant sur un jour férié national
3. Pour chaque samedi S, calculer :
   score_vacances(S) = Σ nb_equipes_zone_X  pour toute zone X telle que S ∈ vacances_zone_X
```

**Étape 2 : Sélectionner les N meilleures dates**

```
Contraintes strictes :
  - Une seule compétition par samedi
  - Espacement minimum : 1 semaine (samedis consécutifs autorisés)

Objectif d'optimisation (dans cet ordre de priorité) :
  1. Minimiser le score_vacances total (somme des impacts sur toutes les dates choisies)
  2. Maximiser la compacité : préférer des blocs de samedis consécutifs
     → pénaliser les "trous" (samedis libres entre deux compétitions)
```

**Formule de score composite pour un ensemble de dates D :**

```python
score_total(D) = Σ score_vacances(d)  +  λ * nb_trous(D)

# nb_trous(D) = nombre de samedis libres entre la 1ère et dernière compétition
# λ = coefficient de pondération (réglable, défaut = 0.1)
# L'objectif est de minimiser score_total
```

**Implémentation :** Recherche exhaustive si N ≤ 10 compétitions dans une fenêtre ≤ 20 samedis, sinon algorithme glouton (greedy) avec backtracking léger.

### 3.5 Jours fériés à exclure (saison nov–jan)

- 1er novembre (Toussaint)
- 11 novembre (Armistice)
- 25 décembre (Noël)
- 1er janvier (Jour de l'an)

### 3.6 Cas limites

- Aucun samedi ne peut éviter toutes les vacances → prendre le meilleur compromis et alerter l'utilisateur avec le score d'impact.
- Fenêtre trop courte pour N compétitions avec espacement 1 semaine → alerter et proposer d'élargir la fenêtre.

---

## 4. Module 2 — Affectation des équipes

### 4.1 Objectif

Répartir les équipes dans les compétitions selon leurs vœux, en :
1. Garantissant qu'**aucune équipe ne reste sans compétition** (priorité absolue)
2. Maximisant la satisfaction des vœux
3. En cas d'égalité : priorisant la **proximité géographique** (km) puis l'**ordre d'inscription**

### 4.2 Entrées

| Champ | Type | Description |
|-------|------|-------------|
| `voeux` | fichier | Fichier Excel/CSV des vœux (issu du Forms) |
| `competitions` | fichier | Fichier Excel/CSV des compétitions avec dates et capacités |

> Le fichier vœux est généré depuis un **Google Forms ou Microsoft Forms** rempli par les équipes, exporté en Excel et importé directement dans Magouilleuse.

### 4.3 Sorties

- **Tour 1** : Affectation de chaque équipe à sa 1ère compétition
- **Tour 2** : Affectation des 2ème compétitions pour les équipes qui le souhaitent
- **Tour 3** : Affectation des 3ème compétitions
- **Résumé par compétition** : liste des équipes, taux de remplissage
- **Métriques** : taux de satisfaction vœu n°1, satisfaction globale
- **Équipes non affectées** : liste avec raison (si applicable)

### 4.4 Algorithme

**Tour 1 — Garantir 1 compétition par équipe**

```
Phase 1.1 : Affectation prioritaire par vœu n°1
  Pour chaque compétition C (triée par nb de demandes décroissant) :
    Collecter toutes les équipes ayant C en vœu n°1
    Si nb demandes ≤ capacité(C) : affecter tout le monde
    Sinon (sursouscription) : départager selon l'ordre de priorité ci-dessous

Phase 1.2 : Traiter les équipes non affectées au tour 1.1
  Pour chaque équipe non affectée :
    Essayer vœu n°2, puis vœu n°3
    En dernier recours : affecter à la compétition avec le plus de places restantes

Phase 1.3 : Vérification
  Toutes les équipes ont au moins 1 compétition
  Aucune compétition ne dépasse sa capacité
```

**Ordre de priorité en cas de sursouscription :**

```
1. Équipes pour qui c'est le seul vœu (nb_competitions_souhaitees = 1)
   → Elles n'ont pas d'alternative, donc prioritaires
2. Équipes les plus proches géographiquement de la compétition
   → Distance calculée depuis le code postal de l'équipe et de la compétition
3. Ordre d'inscription (date/heure de soumission du Forms)
   → Si disponible dans le fichier Excel exporté
```

**Tours 2 & 3 — Équipes multi-compétitions**

```
- Ne commencer qu'après la complétion du Tour 1
- Recalculer les places restantes
- Même algorithme de priorité
- Contrainte : une équipe ne peut pas aller deux fois à la même compétition
- Contrainte : si le Module 1 a été utilisé, vérifier que les dates ne se chevauchent pas
  (normalement impossible car 1 compétition/samedi, mais à vérifier si dates manuelles)
```

### 4.5 Métriques de qualité

```
Taux satisfaction vœu n°1  = nb équipes ayant obtenu vœu 1 / nb total équipes
Taux satisfaction global   = nb équipes dans leur liste de vœux / nb total équipes
Taux remplissage           = nb équipes affectées / capacité max  (par compétition)
```

---

## 5. Interface utilisateur

### 5.1 Structure de l'application Streamlit

```
Page d'accueil (sélection du module)
├── 📅 Module 1 — Planification des compétitions
│   ├── Upload fichier compétitions (CSV/Excel)
│   ├── Upload fichier équipes (CSV/Excel) — optionnel
│   ├── Sélection fenêtre de dates (date_début / date_fin)
│   ├── Bouton "Générer le planning"
│   ├── Affichage calendrier interactif (Plotly)
│   ├── Affichage score d'impact par date
│   └── Bouton "Télécharger le planning (Excel)"
│
└── 🏆 Module 2 — Affectation des équipes
    ├── Upload fichier vœux (Excel issu du Forms)
    ├── Upload fichier compétitions (CSV/Excel, avec dates si connues)
    ├── Bouton "Lancer l'affectation — Tour 1"
    ├── Affichage résultats Tour 1 (tableau + métriques)
    ├── Bouton "Lancer Tour 2" (si des équipes veulent 2+ compétitions)
    ├── Bouton "Lancer Tour 3" (si applicable)
    ├── Vue résumé par compétition
    └── Bouton "Télécharger les affectations (Excel)"
```

### 5.2 Expérience utilisateur

- Interface entièrement en **français**
- Les deux modules sont accessibles **indépendamment** depuis la page d'accueil
- Messages d'erreur clairs si les fichiers sont mal formatés
- Prévisualisation des données uploadées avant traitement (tableau éditable)
- Indicateurs visuels : 🟢 OK, 🟠 Attention, 🔴 Problème
- Aide contextuelle (tooltip) sur chaque champ
- Résolution automatique adresse → zone de vacances + coordonnées GPS (visible par l'utilisateur pour vérification)

---

## 6. Formats de données

### 6.1 Fichier équipes

**Format : CSV ou Excel (.xlsx)**
**Source : export manuel ou liste gérée par le PM**

| Colonne | Type | Obligatoire | Description |
|---------|------|-------------|-------------|
| `numero_equipe` | int | Oui | Numéro officiel FTC (ex: 12345) |
| `nom_equipe` | str | Oui | Nom de l'équipe |
| `adresse` | str | Oui | Adresse complète (rue, code postal, ville) |

> La zone de vacances et les coordonnées GPS sont **calculées automatiquement** depuis l'adresse (voir Section 7).

### 6.2 Fichier vœux (entrée Module 2)

**Format : Excel (.xlsx)**
**Source : export Google Forms ou Microsoft Forms**

| Colonne | Type | Obligatoire | Description |
|---------|------|-------------|-------------|
| `numero_equipe` | int | Oui | Numéro officiel FTC |
| `horodatage` | datetime | Non | Date/heure de soumission (pour tie-break) |
| `voeu_1` | str | Oui | Nom exact de la compétition (vœu 1) |
| `voeu_2` | str | Non | Vœu 2 |
| `voeu_3` | str | Non | Vœu 3 |
| `nb_competitions_souhaitees` | int | Oui | 1, 2 ou 3 |

> Le nom des colonnes dans le Forms doit correspondre exactement à ce tableau. Un template de Forms sera fourni.

### 6.3 Fichier compétitions

**Format : CSV ou Excel (.xlsx)**
**Source : saisie par le PM**

| Colonne | Type | Obligatoire | Description |
|---------|------|-------------|-------------|
| `nom_competition` | str | Oui | Nom unique de la compétition |
| `adresse` | str | Oui | Adresse complète du lieu (rue, code postal, ville) |
| `capacite_max` | int | Oui | Nombre maximum d'équipes |
| `date_forcee` | date | Non | Si la date est déjà fixée (format YYYY-MM-DD) |

> La zone de vacances et les coordonnées GPS sont **calculées automatiquement** depuis l'adresse.

### 6.4 Sorties Excel

Le fichier Excel exporté contient :

| Feuille | Contenu |
|---------|---------|
| `Résumé` | Vue globale : dates, compétitions, nb équipes, taux de remplissage |
| `Planning` | Calendrier visuel (une ligne = un samedi) |
| `[Nom compétition]` | Une feuille par compétition avec la liste des équipes affectées |
| `Non_affectées` | Équipes sans compétition (si applicable) |
| `Métriques` | Taux de satisfaction, remplissage, scores d'impact |

---

## 7. Résolution automatique adresse → zone / coordonnées

### 7.1 Principe

L'utilisateur saisit uniquement une **adresse complète** (ex: `"12 rue de la Paix, 75001 Paris"`).
L'application extrait automatiquement :
1. Le **code postal** → le **numéro de département**
2. Le département → la **zone de vacances scolaires** (table statique)
3. Le code postal → les **coordonnées GPS approximatives** (centroïde du code postal)

### 7.2 Table département → zone de vacances

```python
ZONE_PAR_DEPARTEMENT = {
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
    # DOM-TOM (hors scope, à traiter manuellement si nécessaire)
}
```

> Cette table sera affinée et validée lors du développement. Source : Éducation Nationale.

### 7.3 Coordonnées GPS depuis le code postal

**Approche :** Utiliser une table statique des centroïdes de codes postaux français (fichier CSV inclus dans le projet, ~36 000 lignes, source : La Poste / data.gouv.fr).

- Pas d'API externe nécessaire → fonctionne **offline**
- Précision suffisante pour calculer des distances inter-équipes/compétitions (à ±10 km)

**Calcul de distance :** Formule de Haversine (distance orthodromique) — pas besoin de Google Maps.

```python
from math import radians, cos, sin, asin, sqrt

def haversine(lat1, lon1, lat2, lon2) -> float:
    """Retourne la distance en km entre deux points GPS."""
    R = 6371  # rayon de la Terre en km
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return 2 * R * asin(sqrt(a))
```

---

## 8. Contraintes et règles métier

### Règles absolues (non négociables)

1. **Chaque équipe doit avoir au minimum 1 compétition** — priorité absolue.
2. **La capacité max d'une compétition ne peut pas être dépassée.**
3. **Une équipe ne peut pas participer deux fois à la même compétition.**
4. **Les compétitions ont lieu un samedi** (jamais un dimanche ou jour de semaine).
5. **Une seule compétition par samedi** (jamais deux compétitions le même week-end).

### Règles de planification (Module 1)

- Espacement minimum entre deux compétitions : **1 semaine** (samedis consécutifs OK).
- Objectif secondaire : **maximiser les blocs consécutifs** (minimiser les trous entre compétitions).
- Un samedi en vacances scolaires **peut** être utilisé si nécessaire (pénalité, pas interdiction).
- Les jours fériés nationaux sont traités comme des vacances toutes zones.

### Règles de priorité en affectation (Module 2)

En cas de sursouscription, dans cet ordre :

1. Équipes avec `nb_competitions_souhaitees = 1` et ce vœu est leur unique option
2. Équipes les plus proches géographiquement de la compétition (distance Haversine)
3. Ordre d'inscription (horodatage du Forms)

### Workflows indépendants

- Le **Module 2 peut fonctionner sans le Module 1** : les dates peuvent être saisies manuellement dans le fichier compétitions (`date_forcee`), ou ignorées si seule l'affectation est nécessaire.
- Le **Module 1 peut fonctionner sans le fichier équipes** (mode dégradé : minimise les conflits toutes zones confondues).
