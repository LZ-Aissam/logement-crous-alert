# Formulaire public sans compte GitHub (Netlify) — Design

## Contexte

La création d'une recherche (voir `2026-07-27-keyword-filters-and-issue-form-design.md`)
et sa confirmation par email (voir `2026-07-27-logement-alert-design.md` et les tâches
9-12 du plan associé) passent aujourd'hui par des GitHub Issue Forms. Ça fonctionne,
mais ça impose à tout visiteur voulant créer sa propre recherche (ou confirmer son
email) de **posséder un compte GitHub**. Le projet est pensé pour un public plus large
que l'auteur (n'importe qui peut vouloir surveiller un logement CROUS) — cette barrière
d'entrée est en contradiction avec cet objectif.

Ce document ajoute une **façade publique** (page web + formulaire, hébergée sur
Netlify) devant le backend GitHub existant, pour que la création de recherche et la
confirmation d'email ne nécessitent plus de compte GitHub, tout en réutilisant le
backend Python/Actions **sans le modifier** (à une exception près, voir section 3).

## Objectif

Un visiteur peut, sans jamais se créer de compte GitHub :
1. Remplir un formulaire web pour créer une recherche (nom, ville, mots-clés optionnel,
   email(s) optionnel).
2. Recevoir un email de confirmation et cliquer un lien qui ouvre une page web (pas une
   création d'Issue GitHub) pour confirmer son adresse.

Le formulaire GitHub existant continue de fonctionner à l'identique pour qui préfère
l'utiliser directement (pas de suppression, juste une alternative en plus).

## Hors scope (assumé)

- Pas de compte utilisateur, pas de tableau de bord pour gérer/supprimer ses propres
  recherches après coup — identique à la limite actuelle du système Issue Form.
- Pas de suivi temps réel (polling) du traitement côté page Netlify — voir section 2,
  le lien vers l'Issue GitHub publique sert de suivi.
- Pas de protection anti-bot forte (captcha) — honeypot + rate-limit best-effort
  seulement (section 4), décision explicite pour rester simple et gratuit.
- Le rate-limit par IP est **best-effort**, pas garanti : les Netlify Functions sont
  éphémères, un compteur en mémoire de process peut être réinitialisé à tout moment
  (cold start, plusieurs instances). Suffisant contre le spam naïf, pas contre un
  attaquant déterminé.

## 1. Architecture

```
Visiteur (aucun compte GitHub requis)
   │
   ▼
Page statique Netlify (nouvelle-recherche.html / confirmer.html)
   │  POST (fetch)
   ▼
Netlify Function (JS)
   │  1. rejette si honeypot rempli (silencieusement, faux succès)
   │  2. rejette si rate-limit dépassé
   │  3. appelle l'API GitHub (POST /repos/{repo}/issues) avec un PAT
   │     stocké en variable d'environnement Netlify (jamais exposé au navigateur)
   ▼
Issue GitHub créée — même titre/corps que ce que produirait le Issue Form
   │
   ▼
Workflows GitHub Actions existants (add-search.yml / confirm-email.yml) — INCHANGÉS
   (add_search.py / confirm_email.py traitent l'Issue exactement comme aujourd'hui)
```

Les Netlify Functions ne dupliquent aucune logique métier (géocodage, doublons,
validation email, tokens) : elles se contentent d'ouvrir l'Issue à la place du
visiteur, avec le même format de corps que le Issue Form GitHub produit déjà. Tout le
reste du pipeline (parsing, activation, envoi d'email) est déjà testé et ne change pas.

**Identité des Issues créées** : comme GitHub n'a pas de notion de « créer une Issue au
nom de quelqu'un d'autre » sans OAuth complet côté visiteur (hors scope), toutes les
Issues créées via Netlify apparaîtront comme créées par le compte propriétaire du PAT
(le tien), pas par le visiteur d'origine. Le contenu du formulaire (soumis par le
visiteur) est fidèlement transmis ; seule l'attribution GitHub de l'Issue elle-même
reflète le PAT, pas le visiteur. Assumé et documenté, pas un bug.

## 2. Pages et feedback

### `public/nouvelle-recherche.html`

Mêmes champs que `.github/ISSUE_TEMPLATE/new-search.yml` : nom, ville, mots-clés
(optionnel), email(s) (optionnel, max 3 — limite déjà appliquée côté `add_search.py`),
plus un champ honeypot caché (`website`, masqué en CSS, jamais rempli par un humain).

Soumission → `POST /.netlify/functions/create-search` → la fonction construit un corps
d'Issue identique au format que produit le Issue Form (mêmes libellés de champs que
`FIELD_NAME`/`FIELD_CITY`/`FIELD_KEYWORDS`/`FIELD_EMAILS` dans `add_search.py`, puisque
c'est ce texte que `parse_issue_form_body` va reparser) et crée l'Issue avec le titre
`"[Nouvelle recherche] {nom}"` et le label `new-search`.

### `public/confirmer.html?code=XXXX`

C'est la page que le lien de l'email de confirmation ouvre (remplace l'actuel
`https://github.com/{repo}/issues/new?template=confirm-email.yml&code=...`). Affiche un
bouton **« Confirmer mon email »** que l'utilisateur doit cliquer explicitement — **pas**
de confirmation automatique au chargement de la page. C'est volontaire : certains
scanners antivirus/proxys d'entreprise « pré-cliquent » les liens dans les emails pour
les scanner, ce qui déclencherait une confirmation sans action humaine réelle si la
page confirmait sur un simple GET.

Clic → `POST /.netlify/functions/confirm-email` avec `{ code }` → la fonction crée
l'Issue `"[Confirmation email]"` avec le label `confirm-email` et le corps
`"### Code de confirmation\n\n{code}"` (même format que le Issue Form).

### Feedback sans compte GitHub

Le dépôt étant public, **voir** une Issue ne nécessite pas de compte (seule sa
*création* en demande un). Donc chaque fonction Netlify renvoie au navigateur l'URL de
l'Issue qu'elle vient de créer, et la page affiche un lien **« Suivre le traitement
ici »** vers cette Issue — le visiteur y voit le commentaire du bot (succès, doublon,
ville introuvable, code invalide, etc.) exactement comme aujourd'hui, sans se créer de
compte. Pas de système de polling/relais à construire : réutilisation directe du
mécanisme existant.

## 3. Changement backend (le seul)

`add_search.py` :

- `build_confirmation_url(token)` lit une variable d'environnement
  `CONFIRMATION_BASE_URL` (nouveau secret repo GitHub). Si définie, retourne
  `f"{CONFIRMATION_BASE_URL}?code={urllib.parse.quote(token)}"` (pointe vers
  `confirmer.html` sur Netlify). Si absente, comportement actuel inchangé (fallback sur
  l'URL de création d'Issue GitHub) — rien ne casse tant que Netlify n'est pas déployé
  ou configuré.
- `build_confirmation_email_body` : la phrase « Si c'est bien toi, confirme en cliquant
  sur ce lien (necessite un compte GitHub, gratuit) » devient « Si c'est bien toi,
  confirme en cliquant sur ce lien : » (sans mention de compte GitHub) — cette mention
  serait fausse dès que `CONFIRMATION_BASE_URL` pointe vers Netlify, et il n'y a pas de
  moyen simple de savoir depuis cette fonction laquelle des deux URLs a été générée sans
  lui faire porter une responsabilité qui ne la concerne pas ; le texte générique reste
  correct dans les deux cas.

Aucun autre fichier Python ne change. Aucun workflow GitHub Actions ne change.

## 4. Anti-abus

- **Honeypot** : champ caché `website` sur les deux formulaires (masqué en CSS, pas en
  `display:none` seul — utiliser une technique qui trompe aussi les bots qui filtrent
  ce cas simple, ex. positionnement hors écran). Non vide en réception → réponse HTTP de
  succès factice, aucune Issue créée, aucun appel à l'API GitHub.
- **Rate-limit** : compteur en mémoire par IP dans chaque fonction (ex. 5
  soumissions/heure), partagé via un module commun `_github.js`. Best-effort (voir
  section « Hors scope »).
- **Validation minimale côté fonction** avant l'appel GitHub : champs requis présents
  et non vides (nom, ville pour create-search ; code pour confirm-email). La validation
  métier réelle (format email, géocodage, doublon de nom) reste entièrement déléguée à
  `add_search.py`/`confirm_email.py` — pas dupliquée en JS.

## 5. Erreurs

- Honeypot déclenché → succès silencieux (pas d'indice donné au bot).
- Rate-limit dépassé → HTTP 429, message « Trop de tentatives, réessaie dans une
  heure ».
- Champ requis manquant → HTTP 400, message précisant le champ.
- Erreur API GitHub (token invalide, timeout, rate-limit GitHub) → HTTP 502, message
  générique « Une erreur est survenue, réessaie dans quelques minutes » — pas de retry
  automatique ni de file d'attente (hors scope, faible volume attendu).

## 6. Structure de fichiers

```
netlify.toml                     # publish = "public", functions = "netlify/functions"
netlify/
  functions/
    create-search.js
    confirm-email.js
    _github.js                   # helper partagé : appel API GitHub, rate-limit, honeypot check
public/
  nouvelle-recherche.html
  confirmer.html
```

## 7. Tests

- **JS (`node:test`, module intégré à Node — aucune dépendance ajoutée)** : pour
  `create-search.js` et `confirm-email.js`, avec `fetch` vers l'API GitHub mocké —
  vérifie que le honeypot rejette silencieusement, que le rate-limit bloque après le
  seuil, qu'un payload valide déclenche un appel `POST /repos/{repo}/issues` avec le
  bon `title`/`body`/`labels`.
- **Python** : étendre le test existant de `build_confirmation_url` pour couvrir les
  deux cas — `CONFIRMATION_BASE_URL` défini (retourne l'URL Netlify) et absent (retourne
  l'URL GitHub actuelle, comportement inchangé).

## 8. Déploiement (à documenter dans le README)

1. Créer un compte Netlify, lier le dépôt GitHub, publier (`public/` en publish
   directory, `netlify/functions/` en dossier de fonctions).
2. Créer un PAT GitHub *fine-grained*, scope **Issues: Read and write** sur ce seul
   dépôt (pas de scope plus large).
3. Configurer les variables d'environnement Netlify : `GITHUB_PAT`,
   `GITHUB_REPOSITORY` (`LZ-Aissam/logement-crous-alert`).
4. Ajouter le secret GitHub `CONFIRMATION_BASE_URL` (ex.
   `https://<ton-site>.netlify.app/confirmer.html`) pour que `add-search.yml` le passe
   en variable d'environnement à `add_search.py`.
5. Présenté comme alternative optionnelle : le Issue Form GitHub direct continue de
   fonctionner pour qui préfère l'utiliser.
