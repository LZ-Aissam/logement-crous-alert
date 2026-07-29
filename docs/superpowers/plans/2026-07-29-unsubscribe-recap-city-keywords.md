# Recap ville/mots-cles desinscription — Plan

Spec : `docs/superpowers/specs/2026-07-29-unsubscribe-recap-city-keywords-design.md`

## Tâche 1 — `build_unsubscribe_url` accepte city/keywords

- Modifier la signature (`check_logement.py:211`) :
  `build_unsubscribe_url(search_name, email, city=None, keywords=None)`.
- Ajouter `&city=<urlencode>` a la query si `city` truthy, et
  `&keywords=<urlencode(", ".join(keywords))>` si `keywords` truthy.
- Mettre a jour l'appel ligne ~501 :
  `build_unsubscribe_url(name, recipient, search.get("city"), search.get("keywords"))`.
- Ajouter dans `tests/test_check_logement.py` (a la suite des tests
  existants `test_build_unsubscribe_url_*`) deux nouveaux tests :
  un avec `city` seul, un avec `city` + `keywords`, verifiant l'URL
  exacte generee (meme pattern que les tests existants avec
  `UNSUBSCRIBE_BASE_URL`).
- Verification : `pytest tests/test_check_logement.py -k unsubscribe_url -v`
  → tous verts (existants + nouveaux).

## Tâche 2 — Affichage dans `desabonnement.html`

- Lire `city` et `keywords` via `URLSearchParams` (a cote de `search`,
  `email`, `token` existants).
- Dans le bloc `#confirm-step`, sous les lignes `Recherche`/`Email`,
  ajouter deux `<div>` conditionnels (non affiches si valeur absente/vide) :
  `Ville : <strong id="confirm-city"></strong>` et
  `Mots-cles : <strong id="confirm-keywords"></strong>`, chacun dans un
  conteneur avec `d-none` par defaut, retire uniquement si la valeur est
  presente.
- Verification : `python -m http.server 8765 --directory public`, ouvrir
  `desabonnement.html?search=Brest&email=x%40example.com&token=x&city=Rennes&keywords=studio%2C%20kergoat`,
  cliquer "Se desinscrire", verifier Ville et Mots-cles affiches ;
  puis ouvrir la meme URL sans `city`/`keywords` et verifier que ces
  deux lignes n'apparaissent pas.

## Tâche 3 — Non-régression

- `pytest` → 177 + nouveaux tests, tous verts.
- `npm test` → 72 pass (aucun changement JS backend).

## Commit

- Un commit couvrant les deux fichiers + tests :
  `git add check_logement.py tests/test_check_logement.py public/desabonnement.html`,
  message `feat: afficher ville et mots-cles dans le recap de desinscription`.
- Push sur `master` après validation.
