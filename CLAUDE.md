# CLAUDE.md — Magouilleuse (FTC France Planning Tool)

> Ce fichier est la source de vérité pour Claude Code sur ce projet.
> Il est mis à jour automatiquement au fur et à mesure de l'avancement.

---

## Contexte du projet

**Nom du projet :** Magouilleuse
**Objectif :** Outil de planification des compétitions FIRST Tech Challenge (FTC) en France.
**Responsable :** Programme Manager FTC France
**Saison cible :** 2025-2026

Le projet se décompose en deux modules indépendants mais liés :
1. **Module Planning** — Génère un calendrier de compétitions qui minimise les conflits avec les vacances scolaires françaises.
2. **Module Affectation** — Répartit les équipes dans les compétitions selon leurs vœux, en respectant les capacités et les priorités.

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
Magouilleuse/
├── CLAUDE.md               ← ce fichier
├── SPECS.md                ← spécifications détaillées
├── requirements.txt        ← dépendances Python
├── app.py                  ← point d'entrée Streamlit
├── data/
│   ├── templates/          ← fichiers CSV/Excel modèles à remplir
│   └── vacances/           ← calendrier des vacances scolaires par zone
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
- Toujours exporter les résultats en Excel avec une feuille par compétition + une feuille résumé.
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
| Normalisation noms compétitions | ✅ Implémentée | NFD + strip + lower dans lancer_affectation() |
| Diagnostic correspondance noms | ✅ Implémenté | Expander dans Module 2, affiche repr() des noms |
| Debug algorithme Phase A | ✅ Implémenté | Traces [DEBUG Tn] dans executer_tour(), expander dédié |
| Jeu de données test | 🔄 En cours | Templates avec données réelles 2026-2027 créés |
| Tests | ⬜ À écrire | |
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
| 2026-03-29 | 1 compétition/samedi, consécutifs favorisés | Règle métier confirmée par le PM |
| 2026-03-29 | Priorité tie-break : unicité vœu > proximité > horodatage Forms | Règle métier confirmée par le PM |
| 2026-03-31 | Normalisation souple des noms de compétitions | Les CSV/Forms peuvent introduire des variantes d'encodage (NFD/NFC), espaces insécables, accents manquants. La correspondance exacte échoue silencieusement → normaliser via NFD + strip + lower avant d'associer vœux et compétitions. |
| 2026-03-31 | Diagnostic repr() dans l'interface | Pour détecter les caractères invisibles (U+200B, U+00A0, etc.) dans les noms de compétitions, le diagnostic affiche le repr() Python de chaque nom. Activé via un expander dans le Module 2. |
| 2026-03-31 | Debug Phase A activé par défaut | Les traces [DEBUG Tn] dans executer_tour() sont toujours émises et filtrées dans l'interface (expander "🐛 Debug algorithme"). Permet de diagnostiquer 0 demandeur sans toucher au code. |
| 2026-03-31 | Template competitions_avec_dates_template.csv | Fichier modèle avec les 5 compétitions 2026-2027 et leurs dates réelles, téléchargeable depuis la page Accueil. Garantit que les noms correspondent exactement aux vœux. |
| 2026-03-31 | Fix bug CRITIQUE : double affectation Phase A | `comp.places_restantes` décrémenté pendant la boucle d'affectation, puis relu comme indice de slice → équipes déjà affectées repassaient en Phase B et obtenaient une 2e affectation. Fix : snapshot `nb_places = comp.places_restantes` avant la boucle (affectation.py ~l.397). |
| 2026-03-31 | Fix bug : détection doublons inopérante dans valider_voeux | `valider_voeux` appelait `_extraire_voeux` (qui déduplique) puis cherchait des doublons dans la liste déjà dédupliquée → jamais trouvés. Fix : extraction séparée `voeux_bruts` avant déduplication (affectation.py ~l.102). |
| 2026-04-01 | Refonte critères de priorité dans cle_priorite() | L'ancien `score_alternative` mêlait les critères et l'horodatage prenait le dessus trop tôt. Nouvelle clé : (1) isolation >300 km, (2) conflit vacances, (3) distance à la compétition cible, (4) horodatage. Fonctions helpers : `_distance_min_competitions`, `_competition_la_plus_proche`, constante `SEUIL_ISOLATION_KM=300`. |
| 2026-04-04 | Critère 3bis — pénibilité du repli dans cle_priorite() | Problème : l'équipe la plus proche gagne toujours le voeu 1, même si son repli est confortable, tandis qu'une équipe à peine plus loin se retrouve envoyée très loin. Solution : ajouter un critère de départage entre distance (3) et horodatage (4). Pénibilité = ratio distance(équipe → repli) / distance(équipe → cible). Un ratio élevé signifie que le repli coûte proportionnellement cher. Le repli objectif = compétition viable la plus proche, excluant la compétition disputée et les compétitions en conflit vacances SAUF si l'équipe a voté pour une compétition tombant dans la même période de vacances (signal de disponibilité). Si dist_cible < 1 km, pénibilité = +∞. Ne modifie pas l'algo existant, s'insère dans le tuple de `cle_priorite()`. |

---

## Contacts & ressources

- Calendrier vacances scolaires officiel : https://www.education.gouv.fr/les-dates-des-vacances-scolaires
- Documentation FIRST Tech Challenge : https://www.firstinspires.org/robotics/ftc
