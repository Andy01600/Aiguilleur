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
| Table département → zone vacances | ⬜ À intégrer | Dans utils/helpers.py |
| Table centroïdes codes postaux | ⬜ À télécharger | Source : data.gouv.fr (La Poste) |
| Structure du projet | ⬜ À créer | |
| Module 1 — Planification | ⬜ À développer | 6 compétitions, fenêtre nov–jan, consécutifs favorisés |
| Module 2 — Affectation | ⬜ À développer | 110 équipes, 3 tours, tie-break géographique |
| Interface Streamlit | ⬜ À développer | Modules indépendants en page d'accueil |
| Jeu de données test | ⬜ À préparer | Données réelles saison 2025-2026 |
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

---

## Contacts & ressources

- Calendrier vacances scolaires officiel : https://www.education.gouv.fr/les-dates-des-vacances-scolaires
- Documentation FIRST Tech Challenge : https://www.firstinspires.org/robotics/ftc
