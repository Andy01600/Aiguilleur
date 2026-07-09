# L'Aiguilleur — Outil de planification FTC France

Outil de planification des événements **FIRST Tech Challenge (FTC) en France**, saison 2026-2027.

**Accès en ligne :** [https://aiguilleur.streamlit.app/](https://aiguilleur.streamlit.app/)

---

## Modules

### Module 1 — Planification
Génère un calendrier d'événements qui minimise les conflits avec les vacances scolaires françaises.

### Module 2 — Affectation
Répartit les équipes dans les événements selon leurs vœux, en respectant les capacités et les priorités. Algorithme Gale-Shapley (stable matching) avec critères géographiques et vacances scolaires. Distances réelles via OSRM ou Haversine.

---

## Stack technique

- Python 3.11+ / Streamlit
- Optimisation : PuLP
- Visualisation : Plotly
- Export : Excel (.xlsx)
