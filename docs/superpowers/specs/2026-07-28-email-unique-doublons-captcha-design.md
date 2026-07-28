# Email unique, anti-doublon, captcha et sortie des données du dépôt public

Date : 2026-07-28

## Problème

Le formulaire public de `logement-crous-alert` accepte aujourd'hui jusqu'à trois
adresses email par recherche, ne détecte aucun doublon, et n'a pour toute
protection qu'un honeypot et un rate limit en mémoire. Trois changements sont
demandés : une seule adresse par recherche, un refus des doublons, et un captcha.

En instruisant ces demandes, un quatrième problème est apparu, plus grave que les
trois autres : **`searches.json` est commité dans un dépôt GitHub public et
contient les adresses email des inscrits en clair.** Rendre l'email obligatoire
revient à publier l'adresse de chaque personne qui utilise le formulaire, dans un
dépôt que les robots à spam moissonnent.

L'échappatoire évidente est fermée : `check.yml` tourne en cron `*/5 * * * *`, soit
environ 8 600 exécutions par mois. Les dépôts publics disposent de minutes GitHub
Actions illimitées, les dépôts privés sont plafonnés à 2 000 minutes par mois sur le
plan Free. Passer le dépôt en privé arrêterait le robot ou le rendrait payant. Le
dépôt doit rester public, donc les données doivent en sortir.

## Périmètre

Dans le périmètre :

1. Sortir les données d'abonnés du dépôt public vers un dépôt privé dédié.
2. Rendre l'email obligatoire et unique, et supprimer le destinataire de repli.
3. Refuser les doublons (même adresse, mêmes critères) avec un retour immédiat.
4. Ajouter Cloudflare Turnstile au formulaire public.

Hors périmètre : les filtres de recherche avancés (branche
`worktree-advanced-search-filters`, déjà terminée), et toute refonte de l'interface.

Connu et laissé de côté : `unsubscribe.py` supprime une recherche de `searches.json`
sans retirer la clé correspondante de `seen.json`, qui accumule donc des clés
orphelines. Sans conséquence fonctionnelle — la lecture se fait par nom de recherche —
et sans rapport avec les quatre sujets ci-dessus.

## Décisions

| Sujet | Décision |
|---|---|
| Emplacement des données | Dépôt privé séparé, `logement-crous-alert-data` |
| Email | Obligatoire partout, une seule adresse par recherche |
| `ALERT_EMAIL` | Supprimé, y compris le repli qu'il alimentait |
| Critère de doublon | Même adresse **et** mêmes critères de recherche |
| Retour à l'utilisateur | Immédiat, dans le formulaire, avant création de l'Issue |
| Captcha | Cloudflare Turnstile |
| Données existantes | Non migrées : les fichiers repartent vides |

## 1. Sortie des données du dépôt public

### Nouveau dépôt

`LZ-Aissam/logement-crous-alert-data`, privé, contenant uniquement
`searches.json`, `pending_searches.json` et `seen.json`. Aucun workflow n'y tourne,
donc il ne consomme aucune minute Actions : les minutes sont facturées au dépôt qui
exécute le workflow, et celui-ci reste le dépôt public.

Les trois fichiers démarrent vides : `[]`, `{}` et `{}`. Les recherches existantes
(`Brest`, `Rennes`) ne sont pas reprises.

### Côté Python

Les chemins sont déjà centralisés dans trois constantes et tout le code passe par
elles. Elles deviennent relatives à un répertoire configurable :

```python
DATA_DIR = Path(os.environ.get("DATA_DIR", "."))
SEARCHES_PATH = DATA_DIR / "searches.json"
SEEN_PATH = DATA_DIR / "seen.json"
PENDING_SEARCHES_PATH = DATA_DIR / "pending_searches.json"
```

La valeur par défaut `.` préserve le comportement actuel pour les tests et l'usage
local. `check_logement.py:22-23` et `add_search.py:141` sont les seuls points à
modifier.

### Côté workflows

Les quatre workflows (`add-search`, `check`, `confirm-email`, `unsubscribe`) gagnent
un second checkout :

```yaml
- uses: actions/checkout@v4
  with:
    repository: LZ-Aissam/logement-crous-alert-data
    token: ${{ secrets.DATA_REPO_PAT }}
    path: data
```

L'étape Python reçoit `DATA_DIR: data`, et l'étape de commit s'exécute avec
`working-directory: data`. Aucun appel d'API n'est nécessaire dans les workflows.

### Côté fonction Netlify

C'est le seul composant qui a besoin de l'API GitHub : le contrôle de doublon lit
`searches.json` et `pending_searches.json` via l'API Contents, authentifié par
`DATA_REPO_PAT`. Deux appels par soumission, sur une limite de 5 000 par heure.

### Limite reconnue

Purger l'historique git ne dépublie pas rétroactivement les adresses déjà exposées :
elles ont pu être moissonnées, mises en cache ou archivées. Réécrire l'historique
réduit l'exposition future sans l'annuler.

## 2. Email obligatoire et unique

Sans adresse, une alerte n'a pas de destinataire et la recherche n'a pas de raison
d'exister. L'email devient donc obligatoire dans les deux chemins de création.

**Formulaire public** : `type="email"` et `required`, libellé « Email de
notification » sans mention de plafond. La fonction Netlify refuse une valeur vide
et refuse une valeur contenant une virgule.

**Issue GitHub** : `add_search.py` refuse une soumission sans email. Le plafond passe
de trois adresses à une (`add_search.py:297`).

**Libellé partagé** : `FIELD_EMAILS` passe de `"Email(s) de notification - optionnel"`
à `"Email de notification"`, modifié simultanément dans `add_search.py`,
`netlify/functions/create-search.js` et `.github/ISSUE_TEMPLATE/new-search.yml`. Le
test de parité existant verrouille cette égalité.

**Suppression du repli.** `check_logement.py:258` s'écrit aujourd'hui :

```python
recipients = search.get("emails") or [default_email]
```

Ce repli est un vestige de l'époque où l'outil était mono-utilisateur. Depuis
l'ouverture du formulaire public, il envoie silencieusement à l'exploitant du service
les alertes de toute recherche dépourvue d'adresse. Il est supprimé : une entrée sans
destinataire est un bug, pas un cas nominal. Le robot logue
`[ERROR] <nom> : aucun destinataire, recherche ignorée` et passe à la suivante.

`ALERT_EMAIL` disparaît du `_require_env` de `check_logement.py:244`, du
`check.yml:37`, et le secret peut être effacé.

Le stockage reste une liste d'adresses : seule la validation à l'entrée change.

### Interaction avec la désinscription

`unsubscribe.py` supprime déjà la recherche entière quand son dernier destinataire se
désinscrit (`unsubscribe.py:84-90`). Aucune recherche ne peut donc se retrouver sans
destinataire par ce chemin, et la suppression du repli n'introduit pas de recherche
orpheline qui logerait une erreur toutes les cinq minutes.

Une seule retouche est nécessaire : la branche `unsubscribe.py:58-68` traite le cas
d'une entrée sans clé `emails` et son commentaire explique qu'elle « repose sur le
repli `ALERT_EMAIL` ». Ce commentaire devient faux. Le comportement, lui, reste bon —
supprimer l'entrée est le bon nettoyage pour ce qui est désormais une anomalie. Seul
le commentaire est à réécrire.

Conséquence utile : après désinscription, l'entrée disparaît, donc se réinscrire aux
mêmes critères redevient possible sans être bloqué par le contrôle de doublon.

## 3. Détection des doublons

### Le problème à résoudre

La fonction Netlify ne dispose que des champs bruts du formulaire, tandis que
`searches.json` ne stocke que l'URL CROUS construite — et cette URL est fabriquée par
`add_search.py`, en Python, après la création de l'Issue. La fonction ne peut donc pas
comparer sans dupliquer la construction d'URL, ce qui dériverait.

### Solution : stocker les critères bruts

Chaque entrée gagne un bloc `criteria` :

```json
{
  "name": "Rennes",
  "url": "https://trouverunlogement.lescrous.fr/tools/47/search?...",
  "emails": ["x@y.fr"],
  "criteria": {
    "extent": "-1.75415_48.161999_-1.61315_48.059799",
    "city": "rennes",
    "maxPrice": 500,
    "minArea": 18,
    "occupationModes": ["alone"],
    "prm": false
  }
}
```

### Normalisation

Ces règles doivent être identiques en Python et en JavaScript :

| Champ | Règle |
|---|---|
| `extent` | la chaîne déjà validée par `EXTENT_RE`, telle quelle |
| `city` | `trim`, minuscules, espaces internes réduits à un seul |
| `maxPrice`, `minArea` | entier, ou `null` si absent |
| `occupationModes` | valeurs API (`alone`, `couple`, `house_sharing`), dédupliquées, triées |
| `prm` | booléen |

### Règle de comparaison

Deux recherches sont identiques si **leur zone correspond et leurs quatre filtres
correspondent**.

La zone se compare ainsi : si les deux entrées ont un `extent`, on compare les
`extent` ; sinon on compare les `city` normalisées. Comparer l'`extent` plutôt que
l'URL évite un faux négatif — deux personnes qui sélectionnent la même suggestion
d'autocomplétion mais dont le libellé de lieu diffère produisent des URL différentes
pour une zone rigoureusement identique.

Il y a doublon quand les critères correspondent **et** que l'adresse figure déjà dans
les `emails` de cette entrée. La recherche porte sur `searches.json` **et**
`pending_searches.json`, faute de quoi on pourrait se réinscrire pendant qu'une
confirmation est en attente.

Une entrée dépourvue de bloc `criteria` ne peut jamais correspondre. Les fichiers
repartant vides, ce cas ne devrait pas se présenter ; la garde est défensive.

### Où vivent les contrôles

**Fonction Netlify** : contrôle rapide, répond `409` avant de créer l'Issue. Si la
lecture GitHub échoue, la fonction **laisse passer** en loguant l'erreur — une panne
d'API ne doit pas bloquer toutes les inscriptions.

**`add_search.py`** : refait le contrôle et fait autorité. Il rattrape le cas où la
fonction a laissé passer, ainsi que deux soumissions simultanées portant sur les mêmes
critères. En cas de doublon, l'Issue échoue avec l'erreur dans le log Actions, comme
c'est déjà le cas pour un nom de recherche en double.

### Messages

| Code | Message |
|---|---|
| `409` | Tu es déjà abonné à cette recherche avec cette adresse. |
| `400` | L'email de notification est obligatoire. |
| `400` | Une seule adresse email par recherche. |

## 4. Captcha : Cloudflare Turnstile

Retenu pour trois raisons : gratuit et illimité, invisible dans la majorité des cas
(pas d'énigme visuelle à résoudre, contrairement à hCaptcha), et sans envoi de données
à des fins publicitaires, contrairement à reCAPTCHA.

**Front** : le script Cloudflare en `async defer` et un
`<div class="cf-turnstile" data-sitekey="...">` au-dessus du bouton d'envoi. La site
key est publique par conception et peut vivre en clair dans le HTML. À la soumission,
le jeton est lu dans `form["cf-turnstile-response"].value` et joint au payload.

**Fonction** : `POST` vers `https://challenges.cloudflare.com/turnstile/v0/siteverify`
avec `secret`, `response` et `remoteip`, puis vérification du champ `success`.

**Ordre des contrôles** :

```
honeypot → rate limit → Turnstile → champs requis → doublon
```

Turnstile passe avant la lecture GitHub pour qu'un bot ne consomme jamais d'appel API.
Honeypot et rate limit restent devant parce qu'ils sont gratuits.

**Réinitialisation obligatoire.** Le jeton Turnstile est à usage unique. Après tout
refus (doublon, email manquant, erreur serveur), le front doit appeler
`turnstile.reset()` — sans quoi la deuxième tentative de l'utilisateur échoue
systématiquement avec un jeton déjà consommé.

**Développement local** : les clés de test Cloudflare, qui réussissent toujours,
permettent de garder le formulaire utilisable sur `localhost` sans compte.

**Le rate limit existant est conservé tel quel.** Il vit en mémoire dans la fonction
Netlify (`_github.js:7-24`), donc il se remet à zéro à chaque démarrage à froid et ne
couvre qu'une instance : c'est une protection faible. Turnstile devient la vraie
défense ; le rate limit reste utile comme garde-fou gratuit contre les rafales, et le
rendre persistant ne vaut pas la dépendance supplémentaire.

## Secrets

| Secret | Emplacement | Statut |
|---|---|---|
| `DATA_REPO_PAT` | dépôt public + Netlify | nouveau, fine-grained, Contents read/write sur le seul dépôt de données |
| `TURNSTILE_SECRET_KEY` | Netlify | nouveau |
| `ALERT_EMAIL` | dépôt public | supprimé |

Le PAT devient un point de panne unique : s'il expire, le robot s'arrête. C'est le
coût assumé de la sortie des données du dépôt public.

## Tests

**JavaScript** (`node:test`, style existant) :

- vérification Turnstile réussie, refusée, et API injoignable ;
- doublon trouvé dans `searches.json`, trouvé dans `pending_searches.json`, absent,
  et entrée sans bloc `criteria` ;
- email manquant, multiple, invalide ;
- une soumission piégée par le honeypot ne déclenche aucun appel `siteverify` ;
- lecture GitHub en échec : la soumission passe malgré tout.

**Python** :

- email requis dans les deux chemins de création ;
- plafond d'une seule adresse ;
- bloc `criteria` correctement écrit dans l'entrée ;
- doublon (adresse + critères) refusé ;
- résolution de `DATA_DIR`, avec et sans variable d'environnement ;
- une recherche sans destinataire est ignorée avec une erreur, et non redirigée ;
- test de parité `FIELD_*` mis à jour pour `FIELD_EMAILS`.

Les tests existants qui posent `ALERT_EMAIL` sont nettoyés.

## Ordre de migration

1. Créer le dépôt privé avec les trois fichiers vides.
2. Créer le PAT fine-grained et le poser en secret des deux côtés.
3. Créer le widget Turnstile et poser `TURNSTILE_SECRET_KEY` sur Netlify.
4. Livrer le code.
5. Supprimer les trois fichiers de données du dépôt public, historique compris.
6. Supprimer le secret `ALERT_EMAIL`.

Les recherches `Brest` et `Rennes` cessent d'être surveillées à l'étape 5. La personne
abonnée à `Brest` cesse de recevoir ses alertes ; l'avertir relève d'une décision
distincte de cette spécification.
