# Filtres de recherche avancés (autocomplétion + prix/surface/cohabitation/PMR) — Design

## Contexte

Le formulaire de création de recherche (page d'accueil + Issue GitHub) ne permet
aujourd'hui de préciser qu'une ville, des mots-clés libres, et des emails. Le vrai site
trouverunlogement.lescrous.fr propose bien plus : un champ "Ville, résidence ou lieu
d'étude" avec suggestions en direct, un prix maximum, une surface minimum, un type de
cohabitation (Individuel / Couple / Colocation), et un filtre d'accessibilité PMR. Ce
document ajoute ces mêmes filtres à notre formulaire.

**Recherche effectuée sur le vrai site** (pas de supposition — vérifié par inspection du
formulaire HTML et par tests réels des paramètres) :

- Champ `location` (id `PlaceAutocomplete`) — libellé **"Ville, résidence ou lieu
  d'étude"**. L'autocomplétion appelle en réalité
  `https://trouverunlogement.lescrous.fr/photon/api?q=<texte>&limit=18&lang=fr&osm_tag=...`
  — un proxy vers **Photon**, un géocodeur libre basé sur OpenStreetMap. Chaque
  suggestion renvoyée contient un champ `extent` — vérifié : pour "Brest", `extent`
  vaut `[-4.5689169, 48.4595521, -4.4278311, 48.3572972]`, **exactement** les mêmes
  valeurs que le `bounds` déjà codé en dur pour la recherche "Brest" dans
  `searches.json` (format `ouest_nord_est_sud`, identique à ce que
  `build_search_url()` produit déjà). Utiliser `extent` élimine le besoin de calculer
  une zone de taille fixe autour d'un point — Photon donne la vraie zone de la
  ville/résidence/école choisie.
- `maxPrice` (nombre), `minArea` (nombre), `occupationMode` (paramètre répétable,
  valeurs `alone`/`couple`/`house_sharing`), `prm` (`true`/absent) — **vérifié par test
  réel** : ajouter `&maxPrice=1` à une URL de recherche existante fait passer le nombre
  de résultats de 3 à 0 ; `&minArea=50` aussi. Ces filtres sont appliqués **côté
  serveur CROUS**, avant même que notre `check_logement.py` ne récupère la page.

## Objectif

Le formulaire (page d'accueil + Issue GitHub) permet de préciser, en plus des champs
existants :
1. Une ville/résidence/lieu d'étude choisie via autocomplétion en direct (avec repli
   sur la saisie libre + géocodage actuel si rien n'est sélectionné, ou si le
   JavaScript/l'autocomplétion n'est pas utilisé — chemin Issue GitHub).
2. Un prix maximum (optionnel).
3. Une surface minimum en m² (optionnelle).
4. Un ou plusieurs types de cohabitation (optionnel).
5. Un filtre "logement adapté PMR" (optionnel).

## Décision de conception : aucun changement dans `check_logement.py`

Puisque ces 4 filtres (prix, surface, cohabitation, PMR) sont appliqués côté serveur
CROUS via de simples paramètres d'URL, il suffit de les ajouter à l'URL construite et
stockée dans `searches.json` — le pipeline de vérification périodique
(`check_logement.py`) n'a besoin d'aucune modification, il continue de fetcher l'URL
stockée et de parser le HTML exactement comme aujourd'hui.

## 1. Autocomplétion — `public/index.html`

Le champ "Ville" devient un combobox avec suggestions :

- Input texte + une `<ul>` de suggestions positionnée dessous (`role="listbox"`,
  options `role="option"`, navigation clavier haut/bas/entrée/échap, cohérent avec les
  pratiques d'accessibilité standard pour un combobox ARIA).
- À la frappe (debounce ~300ms, minimum 2 caractères), appelle :
  ```
  https://trouverunlogement.lescrous.fr/photon/api?q=<texte>&limit=8&lang=fr
    &osm_tag=amenity:college&osm_tag=amenity:library&osm_tag=amenity:school
    &osm_tag=amenity:university&osm_tag=place:country&osm_tag=place:region
    &osm_tag=place:state&osm_tag=place:city&osm_tag=place:town
    &osm_tag=place:village&osm_tag=place:house&osm_tag=landuse:residential
  ```
  (mêmes paramètres que ceux observés sur le vrai site, proxy CROUS choisi
  explicitement par l'utilisateur plutôt que l'API Photon publique directe).
- Chaque suggestion affiche `properties.name` + contexte (`properties.postcode`,
  `properties.state` si présents), ex. "Brest (29200) — Bretagne".
- À la sélection d'une suggestion : le champ visible se remplit avec le nom, et un
  champ caché (`extent`) est rempli avec
  `${extent[0]}_${extent[1]}_${extent[2]}_${extent[3]}` (format `ouest_nord_est_sud`,
  cohérent avec `bounds` existant).
- Si l'utilisateur tape du texte et soumet **sans** sélectionner de suggestion, le
  champ caché `extent` reste vide — le backend retombe sur le géocodage actuel
  (`api-adresse.data.gouv.fr` + zone de taille fixe), comportement inchangé.
- Erreur réseau sur l'appel Photon (proxy CROUS indisponible) → la liste de
  suggestions reste vide silencieusement, l'utilisateur peut toujours taper et
  soumettre en texte libre (repli sur géocodage, comme ci-dessus) — jamais bloquant.

## 2. Nouveaux champs de filtre — `public/index.html`

Ajoutés au formulaire, tous optionnels, sous les champs existants et avant le bouton
de soumission :
- **Prix maximum** (`input type="number" min="0" step="1"`, nom `maxPrice`)
- **Surface minimum en m²** (`input type="number" min="0" step="1"`, nom `minArea`)
- **Type de cohabitation** (3 cases à cocher : Individuel/`alone`,
  Couple/`couple`, Colocation/`house_sharing`, nom `occupationMode`)
- **Logement adapté PMR** (1 case à cocher, nom `prm`)

## 3. Payload envoyé à la fonction Netlify — `netlify/functions/create-search.js`

Le JSON envoyé par `index.html` s'enrichit de :
```json
{
  "name": "...", "city": "...", "keywords": "...", "emails": "...", "website": "",
  "extent": "ouest_nord_est_sud ou vide",
  "maxPrice": "400 ou vide",
  "minArea": "15 ou vide",
  "occupationMode": "alone,house_sharing ou vide",
  "prm": "true ou vide"
}
```
`buildIssueBody()` gagne 5 nouvelles sections (`FIELD_EXTENT`, `FIELD_MAX_PRICE`,
`FIELD_MIN_AREA`, `FIELD_OCCUPATION_MODE`, `FIELD_PRM`), avec les mêmes libellés que
les constantes Python (voir section 4) — même convention de test de cohérence
inter-fichiers déjà utilisée pour `create-search.js`/`confirm-email.js`/`unsubscribe.js`
(`tests/test_add_search.py`). Validation minimale côté fonction : `maxPrice`/`minArea`
doivent être des nombres positifs s'ils sont fournis (sinon HTTP 400) ; le reste de la
validation métier (format de `extent`, valeurs valides d'`occupationMode`) reste
délégué à `add_search.py`, comme pour tous les autres champs.

## 4. `add_search.py`

Nouvelles constantes de champ (miroir des futurs libellés du formulaire Issue GitHub,
section 5) :
```python
FIELD_EXTENT = "Zone geographique precise (rempli automatiquement) - optionnel"
FIELD_MAX_PRICE = "Prix maximum - optionnel"
FIELD_MIN_AREA = "Surface minimum en m2 - optionnel"
FIELD_OCCUPATION_MODE = "Type de cohabitation (individuel, couple, colocation) - optionnel"
FIELD_PRM = "Logement adapte PMR - optionnel"
```

`build_search_url()` gagne des paramètres optionnels :
```python
def build_search_url(
    lon: float,
    lat: float,
    location_label: str,
    extent: str | None = None,
    max_price: int | None = None,
    min_area: int | None = None,
    occupation_modes: list[str] | None = None,
    prm: bool = False,
) -> str:
```
- Si `extent` est fourni et valide (4 nombres séparés par `_`, regex de validation),
  il remplace le calcul de `bounds` par zone fixe. Sinon, comportement actuel inchangé
  (zone fixe autour du point géocodé).
- `max_price`/`min_area`, s'ils sont fournis, sont ajoutés en `&maxPrice=`/`&minArea=`.
- Chaque mode de cohabitation valide (`alone`/`couple`/`house_sharing`) ajoute un
  `&occupationMode=...` répété.
- `prm=True` ajoute `&prm=true`.

`main()` parse les 5 nouveaux champs depuis l'Issue :
- `extent` : validé par regex ; invalide ou absent → `None` (repli sur géocodage).
- `max_price`/`min_area` : doivent être des entiers positifs si fournis ; valeur
  invalide → erreur claire (`ERROR: prix maximum invalide : ...`), pas de crash.
- `occupation_modes` : le champ formulaire contient des libellés français
  ("Individuel, Colocation") séparés par virgules (même convention CSV que
  `keywords`/`emails`) ; conversion vers les valeurs API via un mapping
  `{"individuel": "alone", "couple": "couple", "colocation": "house_sharing"}` ;
  valeur non reconnue → ignorée silencieusement plutôt que de faire échouer toute la
  recherche (comportement tolérant, cohérent avec le traitement existant des
  mots-clés).
- `prm` : toute valeur non vide (autre que `_No response_`) est traitée comme `True`.

## 5. Formulaire Issue GitHub — `.github/ISSUE_TEMPLATE/new-search.yml`

5 nouveaux champs `type: input`, tous `required: false`, avec les mêmes libellés que
les constantes Python ci-dessus. Le champ "Zone géographique précise" reste utilisable
manuellement en théorie (un utilisateur avancé pourrait coller un `bounds` connu), mais
sa description précise qu'il est normalement rempli automatiquement par le formulaire
public — pas une saisie attendue pour un envoi manuel d'Issue.

## 6. Erreurs

- Prix/surface non numériques → message d'erreur clair, recherche non créée (pas de
  crash, cohérent avec la validation existante des emails).
- `extent` malformé → ignoré silencieusement, repli sur géocodage (pas d'erreur
  bloquante, cohérent avec le principe "l'autocomplétion est un confort, pas un
  prérequis").
- Type de cohabitation non reconnu → ignoré silencieusement pour cette valeur, le
  reste de la recherche continue.
- Panne de l'API Photon (proxy CROUS) → aucun impact côté backend (c'est un appel
  100% frontend) ; côté frontend, liste de suggestions vide, saisie libre toujours
  possible.

## 7. Hors scope (assumé)

- Pas de "voir plus de filtres" (le vrai site en a d'autres derrière un bouton
  supplémentaire, ex. type de logement, équipements précis) — seuls les 5 filtres
  explicitement demandés sont ajoutés.
- Pas de carte interactive pour affiner la zone.
- Pas de valeur par défaut suggérée pour prix/surface (champs vides = pas de filtre,
  comme sur le vrai site où `value="0"` signifie "pas de limite").

## 8. Tests

- **Python** (`tests/test_add_search.py`) : `build_search_url` avec/sans `extent`
  (vérifie que `extent` valide remplace le calcul de zone fixe, qu'un `extent`
  invalide retombe sur le calcul existant) ; avec/sans chaque filtre optionnel ;
  `main()` avec des valeurs de prix/surface invalides (erreur claire) ; mapping des
  libellés de cohabitation français vers les valeurs API ; nouveau test de cohérence
  `test_field_label_constants_match_issue_form_yaml` étendu aux 5 nouveaux champs.
- **JS** (`netlify/functions/__tests__/create-search.test.js`) : `buildIssueBody`
  inclut les 5 nouvelles sections avec les bons libellés ; validation `maxPrice`/
  `minArea` non numériques → 400.
- Pas de test automatisé pour le JS d'autocomplétion côté page statique (convention
  déjà établie pour `public/*.html` dans ce projet — vérification manuelle par
  capture d'écran/navigateur).

## 9. Documentation

README : nouvelle sous-section décrivant les filtres disponibles dans le formulaire
(prix, surface, cohabitation, PMR) et le fonctionnement de l'autocomplétion, plus la
mention du champ "Zone géographique précise" dans la liste des champs du formulaire
Issue GitHub.
