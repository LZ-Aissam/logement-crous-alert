# Recap ville/mots-cles sur la page de desinscription

## Contexte

`desabonnement.html` affiche deja un recap ("Se desinscrire de la recherche
"X" pour l'adresse Y ?" + encart de confirmation), mais uniquement le nom
de la recherche et l'email. La ville et les mots-cles existent bien par
recherche (`searches.json`, champs `city` et `keywords`), mais le lien de
desinscription genere dans les emails d'alerte
(`check_logement.py:build_unsubscribe_url`) ne les transporte pas dans
l'URL. Objectif : les afficher dans l'encart de confirmation quand ils
sont disponibles.

## 1. `check_logement.py`

`build_unsubscribe_url(search_name, email)` devient
`build_unsubscribe_url(search_name, email, city=None, keywords=None)`.
Quand `city` est fourni, ajoute `&city=<urlencode(city)>` a la query
string. Quand `keywords` (liste) est fourni et non vide, ajoute
`&keywords=<urlencode(", ".join(keywords))>`. Sans ces arguments,
le comportement et l'URL generee restent strictement identiques a
aujourd'hui (retrocompatible avec les tests existants et les liens deja
envoyes dans les emails passes).

Site d'appel (`check_logement.py` boucle principale, actuellement
`unsubscribe_url = build_unsubscribe_url(name, recipient)`) : passer
`search.get("city")` et `search.get("keywords")`.

## 2. `public/desabonnement.html`

Lire les nouveaux parametres `city` et `keywords` dans
`URLSearchParams`. Dans l'encart `#confirm-step` (deja present, sous
"Recherche" / "Email"), ajouter deux lignes conditionnelles (affichees
seulement si le parametre est present et non vide) :

```
Ville : <strong>{city}</strong>
Mots-cles : <strong>{keywords}</strong>
```

Aucun changement a l'appel `fetch` existant (`unsubscribe.js` n'a pas
besoin de city/keywords pour traiter la desinscription, qui fonctionne
deja par nom+email).

## Portee

- Fichiers modifies : `check_logement.py`, `public/desabonnement.html`.
- Tests ajoutes : `tests/test_check_logement.py` (nouveaux cas pour
  `build_unsubscribe_url` avec city/keywords).
- Pas de changement a `search_criteria.py` / `_criteria.js` (aucune
  logique de parsing de criteres modifiee, la regle de parite ne
  s'applique pas).
- Pas de changement aux fonctions Netlify.

## Verification

- `pytest` : nouveaux tests verts, 177 tests existants toujours verts.
- Verification visuelle locale : ouvrir
  `desabonnement.html?search=Brest&email=x%40example.com&token=x&city=Rennes&keywords=studio%2C%20kergoat`
  et confirmer que Ville et Mots-cles apparaissent dans l'encart apres
  clic sur "Se desinscrire". Verifier aussi qu'en l'absence de ces deux
  parametres (lien existant sans city/keywords), l'encart reste
  identique a aujourd'hui (pas de lignes vides).
