# Alerte disponibilité logement CROUS Brest — Design

## Contexte

L'utilisateur cherche un logement étudiant CROUS à Brest via
`https://trouverunlogement.lescrous.fr/tools/47/search?bounds=-4.5689169_48.4595521_-4.4278311_48.3572972&locationName=Brest+%2829200%29`.
Actuellement 0 logement disponible sur cette zone. Il veut être alerté par email dès
qu'un logement apparaît, sans dépendre de son PC (hébergement gratuit 24h/24).

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
- **`check_logement.py`** (racine du dépôt) :
  1. Télécharge la page de recherche (URL en constante ou variable d'env `SEARCH_URL`).
  2. Extrait et parse le JSON `data-url="/api/fr/search/47"` embarqué.
  3. Charge `seen.json` (liste des IDs déjà connus) depuis le dépôt. Absent au premier
     run → traité comme liste vide.
  4. Calcule les IDs présents dans `items` mais absents de `seen.json` → "nouveaux
     logements" (au tout premier run, tous les logements présents comptent comme
     nouveaux — cf. décision utilisateur).
  5. S'il y a au moins un nouveau logement : envoie un email (SMTP Gmail, TLS) au
     destinataire configuré, avec pour chaque nouveau logement : résidence, adresse,
     libellé (ex. "T1 meublé"), loyer si présent, lien vers la page de recherche.
  6. Écrit `seen.json` avec l'ensemble à jour des IDs (que des nouveaux logements
     soient trouvés ou non, tant que le fetch a réussi).
  7. En cas d'erreur (page inaccessible, structure JSON absente/changée) : log clair
     sur stderr et sortie en erreur (exit code ≠ 0) — pas d'email envoyé, pas de
     `seen.json` corrompu (on n'écrase pas l'existant si le parsing échoue).
- **`.github/workflows/check.yml`** : workflow planifié (`schedule: cron: '*/10 * * * *'`),
  installe Python 3.12, exécute `check_logement.py`, puis commit + push `seen.json`
  s'il a changé (bot commit, message court type `chore: update seen listings`).
  Utilise `secrets.GMAIL_ADDRESS`, `secrets.GMAIL_APP_PASSWORD`, `secrets.ALERT_EMAIL`.
- **Secrets GitHub** à configurer manuellement par l'utilisateur après création du
  dépôt (mot de passe d'application Google, pas le mot de passe principal) :
  `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `ALERT_EMAIL`.

## Hors périmètre

- Pas de notification Windows locale (incompatible avec l'hébergement cloud choisi).
- Pas de multi-recherche / multi-ville — une seule URL de recherche pour l'instant.
- Pas d'interface web ; configuration uniquement via Secrets GitHub.

## Tests

- Test manuel local du script (sans secrets email réels au départ, ou avec un compte
  Gmail de test) contre l'URL réelle, en vérifiant :
  - Détection correcte de `total.value` et `items` actuels (0 aujourd'hui).
  - Comportement correct avec `seen.json` absent (premier run → alerte si items non
    vide).
  - Comportement idempotent : un deuxième run sans changement n'envoie pas d'email.
  - Gestion d'erreur si l'URL est injoignable (simulation avec mauvaise URL).
