# Alerte disponibilité logement CROUS — Design

## Contexte

L'utilisateur cherche un logement étudiant CROUS, en commençant par Brest via
`https://trouverunlogement.lescrous.fr/tools/47/search?bounds=-4.5689169_48.4595521_-4.4278311_48.3572972&locationName=Brest+%2829200%29`.
Actuellement 0 logement disponible sur cette zone. Il veut être alerté par email dès
qu'un logement apparaît, sans dépendre de son PC (hébergement gratuit 24h/24), et
pouvoir surveiller **plusieurs recherches en parallèle** (autres villes et/ou autres
filtres : type de logement, prix, etc.) sans dupliquer le code.

Le site lescrous.fr encode déjà tous les critères de recherche (ville, bounds
géographiques, type de logement, prix...) dans l'URL de la page lorsqu'on applique des
filtres dans l'interface web. Le paramétrage se fait donc simplement en fournissant
plusieurs URLs, une par recherche voulue — pas besoin de modéliser les filtres
individuellement côté script.

## Découverte technique

Le site (SvelteKit) intègre le résultat de recherche côté serveur dans le HTML de la
page, dans un tag :
`<script type="application/json" data-sveltekit-fetched data-url="/api/fr/search/47" ...>`

Ce tag contient `{"body": "<json string>"}` où le JSON désérialisé a la forme :
```json
{"results": {"total": {"value": N, "relation": "eq"}, "page": 0, "pageSize": 24, "items": [...]}}
```

Chaque item a un champ `id` unique. C'est plus fiable que de deviner le format exact
de l'API interne (POST) qui a été testé mais renvoie des résultats non filtrés sans le
bon format de `bounds` (non reverse-engineered). On scrape donc directement la page
HTML publique avec l'URL fournie par l'utilisateur.

## Architecture

- **Dépôt GitHub public** nommé par l'utilisateur (proposé : `logement-crous-alert`).
  Public pour bénéficier des minutes GitHub Actions illimitées et gratuites (aucune
  donnée sensible commitée — seulement des IDs de logements ; les identifiants email
  restent dans les Secrets chiffrés du dépôt).
- **`searches.json`** (racine du dépôt, versionné, modifiable directement par
  l'utilisateur sans toucher au code) : liste nommée des recherches à surveiller.
  ```json
  [
    {"name": "Brest",  "url": "https://trouverunlogement.lescrous.fr/tools/47/search?bounds=...&locationName=Brest+%2829200%29"},
    {"name": "Rennes", "url": "https://trouverunlogement.lescrous.fr/tools/..."}
  ]
  ```
  Ajouter/retirer une ville ou un filtre = ajouter/retirer une entrée dans ce fichier
  (l'utilisateur copie l'URL depuis son navigateur après avoir réglé les filtres sur le
  site). Aucune redéploiement ni modif de code nécessaire.
- **`check_logement.py`** (racine du dépôt) :
  1. Charge `searches.json`.
  2. Charge `seen.json` — dict `{nom_recherche: [ids déjà connus]}` — depuis le dépôt.
     Absent, ou nom de recherche absent → traité comme liste vide pour cette recherche
     (permet d'ajouter une nouvelle recherche à tout moment sans tout réinitialiser).
  3. Pour chaque recherche de `searches.json` :
     a. Télécharge la page (l'URL telle quelle).
     b. Extrait et parse le JSON `data-url="/api/fr/search/47"` embarqué.
     c. Calcule les IDs présents dans `items` mais absents de `seen.json[nom]` →
        "nouveaux logements" pour cette recherche (au tout premier run pour un nom
        donné, tous les logements présents comptent comme nouveaux — cf. décision
        utilisateur).
     d. Si une recherche échoue (page injoignable, JSON absent/changé) : log clair sur
        stderr, on continue avec les autres recherches (une recherche cassée ne doit
        pas bloquer les autres), et on ne touche pas à `seen.json[nom]` pour celle-ci.
  4. S'il y a au moins un nouveau logement toutes recherches confondues : envoie **un
     seul email** récapitulatif (SMTP Gmail, TLS), organisé par section = nom de la
     recherche, listant pour chaque nouveau logement : résidence, adresse, libellé
     (ex. "T1 meublé"), loyer si présent, lien vers la page de recherche concernée.
  5. Écrit `seen.json` mis à jour (uniquement les recherches qui ont réussi).
  6. Si toutes les recherches échouent : exit code ≠ 0, pas d'email, pas d'écriture de
     `seen.json`.
- **`.github/workflows/check.yml`** : workflow planifié (`schedule: cron: '*/10 * * * *'`),
  installe Python 3.12, exécute `check_logement.py`, puis commit + push `seen.json`
  s'il a changé (bot commit, message court type `chore: update seen listings`).
  Utilise `secrets.GMAIL_ADDRESS`, `secrets.GMAIL_APP_PASSWORD`, `secrets.ALERT_EMAIL`.
- **Secrets GitHub** à configurer manuellement par l'utilisateur après création du
  dépôt (mot de passe d'application Google, pas le mot de passe principal) :
  `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `ALERT_EMAIL`.

## Hors périmètre

- Pas de notification Windows locale (incompatible avec l'hébergement cloud choisi).
- Pas de modélisation des filtres (ville, type, prix...) dans le code — ils passent
  entièrement par l'URL fournie dans `searches.json`.
- Pas d'interface web ; configuration uniquement via `searches.json` (recherches) et
  Secrets GitHub (identifiants email).

## Tests

- Test manuel local du script (sans secrets email réels au départ, ou avec un compte
  Gmail de test) avec `searches.json` contenant au moins la recherche Brest réelle et
  une recherche fictive de test, en vérifiant :
  - Détection correcte de `total.value` et `items` actuels pour chaque recherche.
  - Comportement correct avec `seen.json` absent (premier run → alerte si items non
    vide, pour chaque recherche).
  - Ajout d'une nouvelle recherche dans `searches.json` en cours de route → traitée
    comme un premier run pour elle seule, sans affecter les autres.
  - Comportement idempotent : un deuxième run sans changement n'envoie pas d'email.
  - Une recherche cassée (mauvaise URL) n'empêche pas les autres de fonctionner, et
    produit un log d'erreur clair.
