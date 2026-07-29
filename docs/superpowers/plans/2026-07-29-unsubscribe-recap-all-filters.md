# Recap complet des filtres desinscription — Plan

Spec : `docs/superpowers/specs/2026-07-29-unsubscribe-recap-all-filters-design.md`

## Tâche 1 — Corriger le bug city + étendre `build_unsubscribe_url`

- Signature (`check_logement.py:211`) : ajouter `max_price=None,
  min_area=None, occupation_modes=None, prm=False, equipments=None`.
- Ajouter les fragments de query correspondants (voir spec section 1),
  chacun seulement si la valeur est fournie/non-vide/`True`.
- Corriger le site d'appel (`check_logement.py:~511`) pour lire
  `search.get("criteria", {})` : `city`, `maxPrice`, `minArea`,
  `occupationModes`, `prm`, `equipments` ; garder
  `search.get("keywords")` inchange (racine, correct).
- Ajouter dans `tests/test_check_logement.py` des tests pour chaque
  nouveau parametre (au moins un cas combinant tous les parametres),
  suivant le meme pattern que les tests `test_build_unsubscribe_url_*`
  existants.
- Vérification : `pytest tests/test_check_logement.py -k unsubscribe_url -v`
  → tous verts.

## Tâche 2 — Affichage dans `desabonnement.html`

- Lire `maxPrice`, `minArea`, `occupationModes`, `prm`, `equipments`
  via `URLSearchParams`.
- Ajouter dans `#confirm-step`, sous Ville/Mots-cles, les lignes
  conditionnelles listees dans la spec section 2 (Prix maximum, Surface
  minimum, Type de cohabitation avec mapping FR, Équipements, Logement
  PMR).
- Vérification : `python -m http.server 8765 --directory public`,
  tester une URL avec tous les parametres remplis, puis une URL sans
  aucun (retrocompatibilite : encart identique a la version
  ville/mots-cles seule).

## Tâche 3 — Non-régression

- `pytest` → tous verts (179 existants + nouveaux).
- `npm test` → 72 pass (aucun changement JS backend).

## Commit

- `git add check_logement.py tests/test_check_logement.py public/desabonnement.html`
- Message : `fix: corriger la lecture de city + afficher tous les filtres
  dans le recap de desinscription`.
- Push sur `master` après validation visuelle.
