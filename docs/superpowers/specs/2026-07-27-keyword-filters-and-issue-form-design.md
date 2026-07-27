# Filtrage par mots-clés + ajout de recherche via formulaire GitHub — Design

## Contexte

Le projet surveille déjà une recherche CROUS (ville + zone géographique) via
`searches.json` et alerte par email à chaque nouveau logement (voir
`2026-07-27-logement-alert-design.md`). L'utilisateur veut maintenant :

1. Pouvoir filtrer plus finement qu'au niveau de la ville : ne recevoir une alerte que
   si le logement correspond en plus à un ou plusieurs mots-clés (nom de résidence,
   type de logement — ex. "Kergoat", "studio", "chambre grand confort").
2. Pouvoir ajouter une nouvelle recherche (ville + mots-clés + email) sans éditer
   `searches.json` à la main, via une interface sur GitHub, pour éviter les fautes de
   frappe et les erreurs de format JSON.

Ce document **met à jour** deux points du design précédent :
- "Pas de modélisation des filtres... dans le code" → remplacé par un filtrage par
  mots-clés simple, en plus (pas à la place) du filtrage géographique par URL.
- "Pas d'interface web" → remplacé par un formulaire GitHub natif (Issue Form), qui
  n'est pas une page web à héberger séparément (pas de nouveau serveur, pas de risque
  de jeton d'accès exposé côté client).

## Limite technique assumée (importante)

Le site trouverunlogement.lescrous.fr est un outil de recherche de logements
**disponibles**, pas un annuaire exhaustif des résidences CROUS d'une ville. Il n'existe
aucune API/page listant "toutes les résidences et tous les types de logements d'une
ville" indépendamment de la disponibilité actuelle. Conséquence assumée : la liste des
résidences/types "suggérée" au moment d'ajouter une recherche ne peut être construite
qu'à partir de ce qui est **actuellement disponible** dans la zone — qui peut être vide
(c'est le cas de Brest au moment de l'écriture de ce document). Le système fait donc du
**meilleur effort avec avertissement**, jamais du rejet strict : un mot-clé qui ne
correspond à rien de disponible aujourd'hui est signalé mais accepté quand même (il
pourrait être valide pour de futures disponibilités).

## 1. Filtrage par mots-clés dans `check_logement.py`

- `searches.json` gagne un champ optionnel `keywords` (liste de chaînes) par recherche.
  ```json
  {
    "name": "Brest Kergoat studio",
    "url": "https://trouverunlogement.lescrous.fr/tools/47/search?bounds=...",
    "keywords": ["Kergoat", "studio"],
    "emails": ["theaissam@gmail.com"]
  }
  ```
- Nouvelle fonction `_item_matches_keywords(item, keywords) -> bool` : si `keywords` est
  absent/vide, retourne toujours `True` (comportement actuel inchangé — tout ce qui est
  dans la zone). Sinon, retourne `True` si **au moins un** mot-clé (comparaison
  insensible à la casse, sous-chaîne) apparaît dans la concaténation de : le libellé du
  logement (`item.label`), le nom de la résidence (`residence.label`), l'adresse de la
  résidence (`residence.address`).
- Dans `main()`, juste après avoir extrait `items` du résultat parsé et avant le calcul
  des nouveaux logements (`find_new_items`), on filtre :
  `items = [i for i in items if _item_matches_keywords(i, search.get("keywords"))]`.
  Ainsi, un logement qui ne matche pas les mots-clés de cette recherche n'est jamais
  compté dans `seen.json[nom]`, n'est jamais candidat à une alerte, et n'affecte pas le
  compteur `total` affiché dans les logs (`len(items)` reflète déjà le sous-ensemble
  filtré).

## 2. Ajout d'une recherche via formulaire GitHub (Issue Form)

### Formulaire (`.github/ISSUE_TEMPLATE/new-search.yml`)

Champs :
- **Nom de la recherche** (texte, requis) — identifiant unique, ex. "Brest Kergoat".
- **Ville** (texte, requis) — ex. "Brest" ou "Brest 29200". Géocodée automatiquement.
- **Mots-clés** (texte, optionnel) — séparés par des virgules, ex. "Kergoat, studio".
  Laisser vide = pas de filtre, toute la ville.
- **Email(s) de notification** (texte, optionnel) — séparés par des virgules. Laisser
  vide = utilise `ALERT_EMAIL` par défaut.

Le formulaire applique automatiquement le label `new-search` à l'issue créée.

### Script `add_search.py`

Fonctions principales :
- `geocode_city(city: str) -> tuple[float, float]` : appelle l'API publique et gratuite
  du gouvernement français (`https://api-adresse.data.gouv.fr/search/`,
  `type=municipality`) pour obtenir `(lon, lat)` du centre-ville. Lève `GeocodeError` si
  aucune commune ne correspond ou en cas d'erreur réseau.
- `build_search_url(lon: float, lat: float, location_label: str) -> str` : construit
  l'URL CROUS avec une zone de taille fixe (mêmes demi-étendues que celle utilisée pour
  Brest : ~0,051° de latitude, ~0,071° de longitude de part et d'autre du centre),
  suffisante pour couvrir une ville française typique. Documenté comme limite connue :
  pour une très grande ville, l'utilisateur peut élargir la zone en éditant l'URL dans
  `searches.json` après coup.
- `parse_issue_form_body(body: str) -> dict[str, str | None]` : parse le format markdown
  généré par GitHub pour les issue forms (sections `### <Label exact>` suivies de la
  valeur, ou `_No response_` si un champ optionnel est laissé vide → `None`).
- `discover_filters(items: list[dict]) -> tuple[list[str], list[str]]` : à partir des
  logements actuellement renvoyés pour la zone, retourne `(noms_residences_distincts,
  libelles_distincts)` triés — le "meilleur effort" mentionné plus haut. Retourne des
  listes vides si `items` est vide.
- `main()` (CLI) : lit le numéro d'issue et le corps de l'issue (variables d'env
  passées par le workflow), orchestre : parse → géocode → construit l'URL → fetch/parse
  la zone (réutilise `check_logement.fetch_html`/`parse_search_results`) → découvre les
  filtres disponibles → valide (avertissement seulement, jamais de rejet) les mots-clés
  soumis contre la liste découverte → vérifie que le nom n'existe pas déjà dans
  `searches.json` (sinon erreur, fichier non modifié) → ajoute l'entrée → sauvegarde
  `searches.json` → écrit un message de résultat (succès avec résumé + filtres
  découverts, ou échec avec raison) sur stdout, et sort avec un code de sortie 0/1 en
  conséquence.

### Workflow (`.github/workflows/add-search.yml`)

- Déclenché sur `issues: [opened]`, condition : le label `new-search` est présent.
- Permissions : `contents: write` (pour commit/push `searches.json`) et `issues: write`
  (pour commenter/fermer l'issue).
- Étapes : checkout, setup Python, installe les dépendances, exécute `add_search.py` en
  lui passant le numéro et le corps de l'issue, puis :
  - Si succès : commit + push `searches.json`, poste un commentaire de confirmation
    (reprenant le message stdout du script) via `gh issue comment`, ferme l'issue via
    `gh issue close`.
  - Si échec (géocodage impossible, nom déjà pris, erreur de parsing) : poste un
    commentaire d'erreur explicite via `gh issue comment`, **laisse l'issue ouverte**
    pour que l'utilisateur corrige et resoumette (nouvelle issue, ou commentaire —
    hors périmètre de traiter les commentaires de suivi automatiquement : l'utilisateur
    ouvre une nouvelle issue corrigée).

## Hors périmètre

- Pas de modification/suppression de recherche via formulaire — reste manuel dans
  `searches.json` (rare, simple à faire à la main).
- Pas de vraie validation stricte des mots-clés (impossible à garantir vu la limite
  technique ci-dessus) — avertissement uniquement.
- Pas de champ pour ajuster la taille de la zone géographique dans le formulaire — taille
  fixe, ajustable ensuite à la main dans `searches.json` si besoin.
- Pas de traitement automatique des commentaires de suivi sur une issue existante —
  chaque tentative d'ajout est une nouvelle issue.

## 3. Confirmation d'email par formulaire (protection anti-abus)

### Contexte du changement

Le but explicite de l'utilisateur est que **n'importe qui** puisse utiliser le
formulaire pour créer sa propre recherche, reçue sur **sa propre adresse email** — ce
n'est pas un outil réservé au propriétaire du dépôt. Une revue finale du code a
correctement signalé que, sans garde-fou, rien n'empêche une personne A de soumettre le
formulaire en indiquant l'adresse email d'une personne B (qui n'a rien demandé) : le
robot enverrait alors des emails automatiques répétés depuis le compte Gmail du
propriétaire vers un tiers non consentant — un risque réel d'abus/spam avec l'identité
du propriétaire.

Décision utilisateur : chaque adresse email doit être **confirmée** (preuve que son
propriétaire consent) avant de recevoir la moindre alerte. Comme le dépôt n'a aucun
serveur (seulement GitHub Pages/Actions, gratuits), la confirmation ne peut pas être un
simple lien cliquable classique. Mécanisme retenu, cohérent avec l'architecture
existante (tout sur GitHub, gratuit) : un **second formulaire GitHub** ("Confirmer mon
email"), pré-rempli via un lien dans l'email de confirmation avec un code unique. La
personne à confirmer doit avoir (ou créer) un compte GitHub pour soumettre ce
formulaire — limite acceptée explicitement par l'utilisateur.

Décision utilisateur sur l'activation : tant qu'**aucun** email soumis pour une
recherche n'est confirmé, cette recherche reste **en attente** (aucune alerte envoyée,
même pas à un email par défaut). Dès qu'**un** des emails soumis se confirme, la
recherche devient active avec cet email comme destinataire ; si d'autres emails de la
même recherche se confirment plus tard, ils s'ajoutent à la liste des destinataires
actifs.

Ce mécanisme concerne uniquement le flux du formulaire public. Si l'utilisateur
(propriétaire du dépôt) édite `searches.json` à la main (comme fait précédemment pour
la recherche "Brest"), aucune confirmation n'est requise — il a un accès direct et de
confiance au fichier. De même, une recherche sans champ `emails` (utilisant
`ALERT_EMAIL` par défaut, le secret du propriétaire) n'a besoin d'aucune confirmation :
le propriétaire se fait confiance à lui-même.

### Nouveaux fichiers de données

- **`pending_searches.json`** : dict `{nom_recherche: {"search": {...entrée searches.json
  sans "emails"...}, "pending_emails": {"<token>": "<email>", ...}}}`. Contient les
  recherches créées via le formulaire mais dont aucun email n'est encore confirmé (ou
  dont certains emails restent à confirmer même après activation partielle).

### Modifications à `add_search.py`

- Génère un token aléatoire et sûr (`secrets.token_urlsafe`) par email soumis.
- Ne construit **pas** immédiatement l'entrée finale dans `searches.json` si des emails
  ont été soumis : place la recherche dans `pending_searches.json` avec un token par
  email, envoie un email de confirmation à chaque adresse (réutilise
  `check_logement.send_email`) contenant un lien vers le second formulaire pré-rempli
  avec le token (`https://github.com/<owner>/<repo>/issues/new?template=confirm-email.yml&code=<token>`,
  construit à partir de la variable d'environnement `GITHUB_REPOSITORY` fournie
  automatiquement par GitHub Actions).
- Si aucun email n'est soumis (champ laissé vide) : comportement inchangé — recherche
  créée immédiatement, active, avec `ALERT_EMAIL` par défaut (aucune confirmation
  nécessaire).
- La vérification du nom déjà pris doit aussi regarder dans `pending_searches.json`, pas
  seulement dans `searches.json`.
- Le message de résultat posté sur l'issue explique clairement : la recherche est en
  attente, un email de confirmation a été envoyé à chaque adresse, rien ne sera activé
  sans confirmation.

### Nouveau script `confirm_email.py`

- `main()` : lit le code soumis via le second formulaire (variable d'env `ISSUE_BODY`,
  même mécanisme de parsing que pour `add_search.py`). Cherche ce token dans
  `pending_searches.json`. Si trouvé : retire le token de `pending_emails` de
  l'entrée correspondante ; si la recherche n'existe pas encore dans `searches.json`,
  l'y ajoute avec `emails: [cet_email]` (première confirmation → activation) ; si elle y
  existe déjà, ajoute cet email à sa liste `emails` existante (confirmations
  suivantes) ; si `pending_emails` de l'entrée est maintenant vide, retire l'entrée de
  `pending_searches.json`. Si le token n'existe nulle part : message d'erreur clair,
  code de sortie 1, aucun fichier modifié.

### Nouveau formulaire et workflow

- `.github/ISSUE_TEMPLATE/confirm-email.yml` : un seul champ requis, "Code de
  confirmation" (`id: code`), label `confirm-email`.
- `.github/workflows/confirm-email.yml` : même structure que `add-search.yml` (checkout,
  setup Python, exécute `confirm_email.py`, commit/push si succès, commente et ferme ou
  laisse ouvert selon le résultat), déclenché sur `issues: opened` avec le label
  `confirm-email`.

### Limite assumée

Pas d'expiration des tokens de confirmation (peut rester en attente indéfiniment) —
acceptable vu l'échelle du projet ; nettoyage manuel possible en éditant
`pending_searches.json` si besoin.

## Tests

- Tests unitaires pour `_item_matches_keywords` (absence de mots-clés → tout passe ;
  correspondance résidence ; correspondance libellé ; correspondance adresse ; aucune
  correspondance ; casse différente).
- Test d'intégration `main()` : une recherche avec `keywords` ne filtre que les
  logements correspondants dans `seen.json` et les emails envoyés.
- Tests unitaires pour `geocode_city`, `build_search_url`, `parse_issue_form_body`
  (plusieurs cas : tous champs remplis, champs optionnels vides/`_No response_`),
  `discover_filters` (liste vide, doublons, plusieurs résidences).
- Test d'intégration pour `add_search.py` `main()` : succès (ajoute l'entrée, message de
  succès, code 0), nom déjà pris (fichier inchangé, code 1), ville introuvable (fichier
  inchangé, code 1).
- Test d'intégration pour `add_search.py` avec emails soumis : la recherche part dans
  `pending_searches.json` (pas dans `searches.json`), un email de confirmation est
  envoyé par adresse, un token distinct par email. Recherche sans email soumis :
  comportement inchangé (activation immédiate, pas de fichier pending touché).
  Nom déjà pris dans `pending_searches.json` (pas seulement `searches.json`) → rejeté.
- Tests pour `confirm_email.py` : token valide → première confirmation (recherche
  déplacée vers `searches.json` avec le bon email), confirmation suivante pour la même
  recherche (email ajouté à la liste existante, pas de doublon de recherche), dernier
  email confirmé retire l'entrée de `pending_searches.json`, token invalide/inconnu →
  erreur claire, code 1, aucun fichier modifié.
