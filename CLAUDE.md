# CLAUDE.md — Aiguilleur (FTC France Planning Tool)

> Ce fichier est la source de vérité pour Claude Code sur ce projet.
> Il est mis à jour automatiquement au fur et à mesure de l'avancement.

---

## Contexte du projet

**Nom du projet :** Aiguilleur
**Objectif :** Outil de planification des événements FIRST Tech Challenge (FTC) en France.
**Responsable :** Programme Manager FTC France
**Saison cible :** 2025-2026

Le projet se décompose en deux modules indépendants mais liés :
1. **Module Planning** — Génère un calendrier d'événements qui minimise les conflits avec les vacances scolaires françaises.
2. **Module Affectation** — Répartit les équipes dans les événements selon leurs vœux, en respectant les capacités et les priorités.

---

## Stack technique

- **Langage :** Python 3.11+
- **Interface :** Streamlit (web app locale ou déployée sur Streamlit Cloud)
- **Librairies principales :**
  - `streamlit` — interface utilisateur
  - `pandas` — manipulation des données
  - `openpyxl` — export Excel
  - `pulp` ou `scipy.optimize` — optimisation linéaire (étape 1 & 2)
  - `plotly` — visualisation du planning
- **Format des entrées :** CSV ou Excel (.xlsx)
- **Format des sorties :** Excel (.xlsx) + affichage dans l'interface

---

## Structure du projet

```
Aiguilleur/
├── CLAUDE.md               ← ce fichier
├── SPECS.md                ← spécifications détaillées
├── requirements.txt        ← dépendances Python
├── app.py                  ← point d'entrée Streamlit
├── data/
│   ├── centroides_cp.csv   ← centroïdes codes postaux (La Poste / data.gouv.fr)
│   ├── templates/          ← fichiers CSV/Excel modèles à remplir
│   ├── vacances/           ← calendrier des vacances scolaires par zone
│   ├── test/               ← jeu de test (ancien scénario : Clermont, Lyon)
│   └── test_26-06/         ← jeu de test courant (compét restructurées + dates 2027)
├── modules/
│   ├── planning.py         ← Module 1 : optimisation du calendrier
│   └── affectation.py      ← Module 2 : affectation des équipes
├── utils/
│   └── helpers.py          ← fonctions utilitaires partagées
└── tests/
    ├── test_planning.py
    └── test_affectation.py
```

---

## Règles de développement

- **Toujours** lire SPECS.md avant de modifier un algorithme.
- Les algorithmes d'optimisation sont dans `modules/`, l'interface Streamlit dans `app.py`.
- Chaque module doit fonctionner de manière **standalone** (sans Streamlit) pour faciliter les tests.
- Les fichiers de données ne sont **jamais** committés (ajouter `data/input/` dans `.gitignore`).
- Toujours exporter les résultats en Excel avec une feuille par événement + une feuille résumé.
- Le code doit être commenté en **français**.

---

## État d'avancement

| Étape | Statut | Notes |
|-------|--------|-------|
| Spécifications | ✅ Finalisées | Voir SPECS.md — toutes les questions répondues |
| Table département → zone vacances | ✅ Intégrée | Dans utils/helpers.py |
| Table centroïdes codes postaux | ✅ Intégrée | utils/helpers.py via data.gouv.fr |
| Structure du projet | ✅ Créée | Tous les modules et répertoires en place |
| Module 1 — Planification | ✅ Développé | modules/planning.py — algorithme glouton + Plotly |
| Module 2 — Affectation | ✅ Développé | modules/affectation.py — 3 tours, tie-break géographique |
| Interface Streamlit | ✅ Développée | app.py — sidebar, 3 pages, upload/export |
| Templates CSV | ✅ Créés | 4 templates téléchargeables depuis la page Accueil |
| Normalisation noms événements | ✅ Implémentée | NFD + strip + lower dans lancer_affectation() |
| Diagnostic correspondance noms | ✅ Implémenté | Expander dans Module 2, affiche repr() des noms |
| Debug algorithme Phase A | ✅ Implémenté | Traces [DEBUG Tn] dans executer_tour(), expander dédié |
| Jeu de données test | ✅ Régénéré (2026-06-26) | data/test_26-06/ : 112 équipes Confirmées/Très probables depuis Database_2026_2027.xlsx (géocodage par département). Ancien jeu conservé dans data/test/ |
| Tests | ✅ Effectués | Tests manuels sur Streamlit Cloud avec jeu de données réel. Suite unitaire dans tests/ (pytest non installé sur la machine locale : Python 3.9 système, voir la note d'exécution sous 3.9) |
| Déploiement Streamlit Cloud | ⬜ Optionnel | |

---

## Décisions techniques importantes

| Date | Décision | Justification |
|------|----------|---------------|
| 2026-03-29 | Streamlit choisi comme interface | Accessible sans installation, Python natif, déployable facilement |
| 2026-03-29 | PuLP pour l'optimisation | Librairie LP open-source mature, suffisante pour les volumes FTC France |
| 2026-03-29 | Modules 1 & 2 indépendants | L'utilisateur peut utiliser chaque module séparément |
| 2026-03-29 | Adresse complète suffit en entrée | Code postal → département → zone via table statique. Coordonnées GPS via table code postaux (data.gouv.fr). Pas d'API externe. |
| 2026-03-29 | Distance Haversine pour tie-break | Pas besoin de Google Maps, calcul offline depuis centroïdes de codes postaux |
| 2026-03-29 | 1 événement/samedi, consécutifs favorisés | Règle métier confirmée par le PM |
| 2026-03-29 | Priorité tie-break : unicité vœu > proximité > horodatage Forms | Règle métier confirmée par le PM |
| 2026-03-31 | Normalisation souple des noms d'événements | Les CSV/Forms peuvent introduire des variantes d'encodage (NFD/NFC), espaces insécables, accents manquants. La correspondance exacte échoue silencieusement → normaliser via NFD + strip + lower avant d'associer vœux et événements. |
| 2026-03-31 | Diagnostic repr() dans l'interface | Pour détecter les caractères invisibles (U+200B, U+00A0, etc.) dans les noms d'événements, le diagnostic affiche le repr() Python de chaque nom. Activé via un expander dans le Module 2. |
| 2026-03-31 | Debug Phase A activé par défaut | Les traces [DEBUG Tn] dans executer_tour() sont toujours émises et filtrées dans l'interface (expander "🐛 Debug algorithme"). Permet de diagnostiquer 0 demandeur sans toucher au code. |
| 2026-03-31 | Template evenements_avec_dates_template.csv | Fichier modèle avec les 5 événements 2026-2027 et leurs dates réelles, téléchargeable depuis la page Accueil. Garantit que les noms correspondent exactement aux vœux. |
| 2026-03-31 | Fix bug CRITIQUE : double affectation Phase A | `comp.places_restantes` décrémenté pendant la boucle d'affectation, puis relu comme indice de slice → équipes déjà affectées repassaient en Phase B et obtenaient une 2e affectation. Fix : snapshot `nb_places = comp.places_restantes` avant la boucle (affectation.py ~l.397). |
| 2026-03-31 | Fix bug : détection doublons inopérante dans valider_voeux | `valider_voeux` appelait `_extraire_voeux` (qui déduplique) puis cherchait des doublons dans la liste déjà dédupliquée → jamais trouvés. Fix : extraction séparée `voeux_bruts` avant déduplication (affectation.py ~l.102). |
| 2026-04-01 | Refonte critères de priorité dans cle_priorite() | L'ancien `score_alternative` mêlait les critères et l'horodatage prenait le dessus trop tôt. Nouvelle clé : (1) isolation >300 km, (2) conflit vacances, (3) distance à l'événement cible, (4) horodatage. Fonctions helpers : `_distance_min_evenements`, `_evenement_la_plus_proche`, constante `SEUIL_ISOLATION_KM=300`. |
| 2026-04-04 | Critère 3bis — pénibilité du repli dans cle_priorite() | Problème : l'équipe la plus proche gagne toujours le voeu 1, même si son repli est confortable, tandis qu'une équipe à peine plus loin se retrouve envoyée très loin. Solution : ajouter un critère de départage entre distance (3) et horodatage (4). Pénibilité = ratio distance(équipe → repli) / distance(équipe → cible). Un ratio élevé signifie que le repli coûte proportionnellement cher. Le repli objectif = événement viable la plus proche, excluant l'événement disputé et les événements en conflit vacances SAUF si l'équipe a voté pour un événement tombant dans la même période de vacances (signal de disponibilité). Si dist_cible < 1 km, pénibilité = +∞. Ne modifie pas l'algo existant, s'insère dans le tuple de `cle_priorite()`. |
| 2026-06-26 | Ordre RÉEL de cle_priorite() (clarification) | Dans le code actuel, la pénibilité du repli est placée AVANT la distance, pas comme simple tie-break post-distance. Tuple = (1) isolation >300 km, (2) conflit vacances, (3) **pénibilité du repli (ratio, DESC)**, (4) distance cible (départage), (5) horodatage. C'est donc un critère **primaire**. Comportement analysé en profondeur (équipes 32688/32921, voir analyses session) et **validé par le PM : à conserver tel quel**. Limite assumée : le ratio peut sous-prioriser une équipe géographiquement isolée dont le repli est proche *en proportion* (ex. 32688, loin de tout, jugée peu prioritaire). Levier retenu pour les débordements = augmenter `capacite_max` de l'événement saturé, **PAS** changer l'algo. |
| 2026-06-26 | Mode d'affectation par défaut = Gale-Shapley | L'app propose glouton / Gale-Shapley / displacement ; le défaut est **Gale-Shapley** (matching stable, "recommandé"). Les résultats diffèrent du mode glouton (ex. 32688 → La Boisse en GS vs Île-de-France en glouton). À garder en tête pour reproduire un run. |
| 2026-06-26 | Jeu de test régénéré depuis la base réelle + restructuration événements | data/test_26-06/ généré depuis Database_2026_2027.xlsx (112 équipes Confirmées + Très probables). Géocodage adresse via colonne Département pour désambiguïser les villes homonymes (corrige 5 CP erronés). 25 établissements sans n° d'équipe → numéros provisoires 90001+. Événements 2026-2027 restructurées : Régionale Clermont → "Régionale de Neuville", Régionale Lyon → "Régionale de la Boisse" ; vœux renommés en conséquence (mapping confirmé PM). Dates ajoutées (samedis janv-févr 2027). Capacités ajustées par le PM (Pays de la Loire/Nantes monté à 23). |
| 2026-09-02 | Fallback Tour 1 : proximité avant places restantes | `_trouver_fallback()` retournait l'événement avec le plus de places restantes (proximité en simple tie-break). Une équipe n'obtenant aucun de ses 3 vœux subissait donc à la fois l'écart maximal à ses préférences **et** un trajet potentiellement très long. Nouvelle règle (décidée par le PM) : parmi les événements ayant au moins une place libre, retenir **le plus proche** ; tie-break = le plus de places restantes ; adresse inconnue (distance non calculable) = retour au plus de places restantes. Aucun impact sur data/test_26-06/ (0 fallback, satisfaction 100 %). 6 tests ajoutés : `TestTrouverFallback` dans tests/test_affectation.py. |

---

## Contacts & ressources

- Calendrier vacances scolaires officiel : https://www.education.gouv.fr/les-dates-des-vacances-scolaires
- Documentation FIRST Tech Challenge : https://www.firstinspires.org/robotics/ftc
