# Recap complet des filtres sur la page de desinscription

## Contexte

Extension de `docs/superpowers/specs/2026-07-29-unsubscribe-recap-city-keywords-design.md`
: en plus de ville/mots-cles, afficher tous les autres filtres optionnels
qu'un etudiant peut renseigner (prix max, surface min, type de
cohabitation, equipements, PMR).

**Bug decouvert au passage** : la commit precedente lit `search.get("city")`
dans `check_logement.py`, mais l'entree reelle dans `searches.json`
(construite par `add_search.py:428`, `entry = {"name": name, "url": url,
"criteria": criteria}`) ne stocke `city` que dans `search["criteria"]["city"]`,
normalise en minuscules par `normalize_city()`. `search.get("city")`
renvoie donc toujours `None` en production. `search.get("keywords")` est
correct : c'est bien une cle a la racine (`add_search.py:430`,
`entry["keywords"] = keywords`, valeurs brutes non normalisees).

## 1. `check_logement.py`

Corriger le site d'appel pour lire depuis `search.get("criteria", {})` :
`city`, `maxPrice`, `minArea`, `occupationModes`, `prm`, `equipments`.
`keywords` continue de venir de la racine (`search.get("keywords")`,
inchange).

Etendre `build_unsubscribe_url` avec 4 nouveaux parametres optionnels :
`max_price: int | None`, `min_area: int | None`,
`occupation_modes: list[str] | None`, `prm: bool = False`,
`equipments: list[str] | None = None`. Chacun ajoute un parametre a la
query string seulement s'il est fourni/non-vide/`True` :
- `maxPrice=<int>`
- `minArea=<int>`
- `occupationModes=<urlencode(",".join(...))>` (valeurs brutes :
  `alone`, `couple`, `house_sharing`)
- `prm=1` (uniquement si `True` ; omis si `False`/`None`)
- `equipments=<urlencode(",".join(...))>` (valeurs deja en francais,
  ex. `Douche`, `Frigo`)

Retrocompatible : sans ces arguments, l'URL generee reste strictement
identique a aujourd'hui.

## 2. `public/desabonnement.html`

Lire les nouveaux parametres. Dans l'encart `#confirm-step`, ajouter
sous les lignes Ville/Mots-cles, chacune conditionnelle (masquee si
absente) :
- `Prix maximum : <strong>{maxPrice} €</strong>`
- `Surface minimum : <strong>{minArea} m²</strong>`
- `Type de cohabitation : <strong>{labels}</strong>` — mapper les valeurs
  brutes vers le francais avec un petit dictionnaire JS local :
  `{alone: "Individuel", couple: "Couple", house_sharing: "Colocation"}`,
  join(", ") pour l'affichage.
- `Équipements : <strong>{equipments}</strong>` (deja en francais, join
  tel quel).
- `Logement PMR : <strong>Oui</strong>` (uniquement si `prm=1` present ;
  pas de ligne sinon, pas de "Non" affiche).

## Portée

- Fichiers modifies : `check_logement.py`, `tests/test_check_logement.py`,
  `public/desabonnement.html`.
- Pas de changement a `search_criteria.py` / `_criteria.js` / aux
  fonctions Netlify.

## Vérification

- `pytest` : nouveaux tests pour `build_unsubscribe_url` (max_price,
  min_area, occupation_modes, prm, equipments) + verification que le
  site d'appel lit bien `criteria.city` et pas `search.city`.
- Verification visuelle locale avec une URL de test incluant tous les
  parametres, puis avec aucun (retrocompatibilite).
