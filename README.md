# 🌧️ Pluviométrie

Petite application web (Python / Streamlit) qui affiche la **pluie** et la **température** des derniers jours pour un code postal français, à partir des données ouvertes de Météo-France.

## Fonctionnalités

- Saisie d'un code postal → choix de la commune → station météo la plus proche
- Période réglable (30 derniers jours par défaut, jusqu'à 365)
- **Pluie** : cumul, nombre de jours de pluie (≥ 1 mm), jour le plus pluvieux, graphique jour par jour
- **Température** : moyenne, min et max relevées, graphique min / moyenne / max par jour
  (si la station ne mesure que la pluie, la station la plus proche mesurant la température est utilisée)
- Tableau détaillé jour par jour

## Sources de données

Données ouvertes, sans clé API :

- [API Découpage administratif](https://geo.api.gouv.fr) : code postal → commune, département, coordonnées
- [Données climatologiques de base – quotidiennes](https://www.data.gouv.fr/datasets/donnees-climatologiques-de-base-quotidiennes) (Météo-France, data.gouv.fr) : seul le fichier récent du département est téléchargé (2 dernières années, mis à jour chaque jour)

Les données sont mises en cache en mémoire (3 h pour les relevés, 24 h pour le reste).

## Lancer en local

Prérequis : [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run streamlit run app.py
```

L'application s'ouvre sur http://localhost:8501.

## Déployer sur un serveur (Docker Compose)

```bash
git clone https://github.com/nicolas-burel/pluviometrie.git
cd pluviometrie
docker compose up -d --build
```

L'application écoute sur `127.0.0.1:8501` (accessible uniquement depuis le serveur). Pour l'exposer, passer par un reverse proxy (Nginx, Caddy, Traefik…) avec HTTPS.
Streamlit utilise des **WebSockets** : le proxy doit les laisser passer (avec Nginx : en-têtes `Upgrade` et `Connection`).

Pour tester sans reverse proxy, remplacer dans `compose.yaml` `"127.0.0.1:8501:8501"` par `"8501:8501"`.

### Mettre à jour

```bash
git pull
docker compose up -d --build
```

## Structure

```
app.py            # toute l'application (données + interface Streamlit)
pyproject.toml    # dépendances
uv.lock           # versions exactes des dépendances
Dockerfile        # image Docker (basée sur l'image officielle uv)
compose.yaml      # lancement avec Docker Compose
```

## Limites

- Les valeurs sont celles de la station Météo-France la plus proche, pas exactement de la commune.
- Les relevés ont environ un jour de décalage.
- Le premier chargement d'un département prend quelques secondes (téléchargement du fichier).
