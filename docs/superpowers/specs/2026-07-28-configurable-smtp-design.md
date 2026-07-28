# Envoi d'emails via un service SMTP configurable (Brevo) — Design

## Contexte

L'envoi d'emails (alertes de logement, confirmations d'email) passe aujourd'hui
exclusivement par le compte Gmail personnel du propriétaire du dépôt, via SMTP
(`smtp.gmail.com:465`, authentifié avec `GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD`). Deux
inconvénients à mesure que l'usage grandit (notamment via le formulaire public, qui peut
faire envoyer jusqu'à 3 emails de confirmation par soumission anonyme, voir la section
« Risque à connaître » du README) : le compte Gmail personnel supporte tout le trafic
(spam potentiel, limites d'envoi Gmail), et rien ne distingue le bot du compte personnel
en cas d'abus.

Ce document remplace l'envoi Gmail-en-dur par un envoi SMTP **configurable**, pointé vers
un service d'emails transactionnels gratuit dédié (Brevo, 300 emails/jour gratuits à vie,
sans besoin de nom de domaine personnel pour démarrer). Le protocole reste SMTP standard
(`smtplib`, déjà utilisé) — seuls l'hôte, le port, les identifiants et l'adresse
d'expéditeur deviennent des variables au lieu d'être en dur.

## Objectif

`check_logement.py` et `add_search.py` envoient leurs emails (alertes et confirmations)
via un serveur SMTP dont l'hôte/port/identifiants/expéditeur sont lus depuis des
variables d'environnement, sans changement de comportement métier (mêmes emails, mêmes
destinataires, même contenu). Fonctionne avec Brevo dès la config initiale ; reste
compatible avec n'importe quel autre fournisseur SMTP (y compris Gmail, si l'utilisateur
préfère y revenir) en changeant simplement les valeurs des secrets.

## Décisions de conception (issues du brainstorming)

- **Fournisseur** : Brevo (SMTP relay `smtp-relay.brevo.com`), choisi pour son plan
  gratuit généreux (300/jour) et l'absence de prérequis de domaine personnel.
- **Remplacement net des secrets**, pas de rétrocompatibilité avec
  `GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD` : ces deux secrets sont supprimés et remplacés par
  `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `FROM_EMAIL`. Le choix explicite
  de l'utilisateur était la clarté à long terme plutôt que la compatibilité ascendante
  (un seul remplacement de secrets à faire, une fois, au moment de la bascule).
- **`FROM_EMAIL` distinct de `SMTP_USER`** : chez Brevo, l'identifiant de connexion SMTP
  (souvent une chaîne générique liée au compte) et l'adresse d'expéditeur affichée
  (`From:`, doit être une adresse vérifiée côté Brevo) sont deux choses différentes —
  contrairement à Gmail où adresse de connexion et adresse d'expéditeur sont la même
  chose. `FROM_EMAIL` est donc une variable à part, obligatoire.

## Hors scope (assumé)

- Pas de bascule automatique/detection de fournisseur — l'utilisateur configure
  explicitement les 5 variables SMTP.
- Pas de support de l'API HTTP de Brevo (uniquement leur relais SMTP) — reste dans le
  même paradigme `smtplib` déjà en place, pas de nouvelle dépendance.
- Pas de retry ni de file d'attente en cas d'échec d'envoi — comportement actuel
  inchangé (un échec d'envoi est loggé, l'email suivant est quand même tenté).

## 1. `send_email()` dans `check_logement.py`

Signature actuelle :

```python
def send_email(
    subject: str, body: str, to_addrs: list[str], smtp_user: str, smtp_password: str
) -> None:
```

Nouvelle signature :

```python
def send_email(
    subject: str,
    body: str,
    to_addrs: list[str],
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    from_email: str,
) -> None:
```

Comportement :
- `msg["From"] = from_email` (au lieu de `smtp_user`).
- Connexion : si `smtp_port == 465` → `smtplib.SMTP_SSL(smtp_host, smtp_port, ...)` (mode
  implicite SSL, identique au comportement Gmail actuel, pour rester compatible si
  quelqu'un repointe vers Gmail) ; sinon → `smtplib.SMTP(smtp_host, smtp_port, ...)` puis
  `server.starttls()` (mode recommandé par Brevo sur le port 587, le port par défaut
  qu'on documentera).
- `server.login(smtp_user, smtp_password)` inchangé.
- `server.sendmail(from_email, to_addrs, msg.as_string())` — l'enveloppe utilise
  `from_email` au lieu de `smtp_user`.

## 2. Lecture des variables d'environnement

### `check_logement.py` — `main()`

Remplace :
```python
    smtp_user = _require_env("GMAIL_ADDRESS")
    smtp_password = _require_env("GMAIL_APP_PASSWORD")
```
par :
```python
    smtp_host = _require_env("SMTP_HOST")
    smtp_port = int(_require_env("SMTP_PORT"))
    smtp_user = _require_env("SMTP_USER")
    smtp_password = _require_env("SMTP_PASSWORD")
    from_email = _require_env("FROM_EMAIL")
```
Chaque appel à `send_email(...)` dans la boucle par destinataire passe les 3 nouveaux
paramètres en plus (`smtp_host`, `smtp_port`, `from_email`).

### `add_search.py` — `main()` (branche « emails fournis »)

Même remplacement pour `smtp_user`/`smtp_password`, plus lecture de `smtp_host`,
`smtp_port`, `from_email`, passés à l'appel existant à `clog.send_email(...)`.

## 3. Secrets GitHub et workflows

`.github/workflows/check.yml` et `.github/workflows/add-search.yml` : dans le bloc `env:`
de l'étape qui exécute le script Python, remplacer `GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD`
par :
```yaml
SMTP_HOST: ${{ secrets.SMTP_HOST }}
SMTP_PORT: ${{ secrets.SMTP_PORT }}
SMTP_USER: ${{ secrets.SMTP_USER }}
SMTP_PASSWORD: ${{ secrets.SMTP_PASSWORD }}
FROM_EMAIL: ${{ secrets.FROM_EMAIL }}
```
`ALERT_EMAIL` et les autres secrets existants (`UNSUBSCRIBE_SECRET`, etc.) ne changent
pas.

## 4. Erreurs

- Un des 5 secrets SMTP manquant → `_require_env` échoue immédiatement (comportement
  identique à aujourd'hui avec `GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD` manquants : le run
  s'arrête en erreur avant tout envoi). Pas de valeur par défaut silencieuse — un mauvais
  réglage SMTP doit être visible tout de suite, pas produire des échecs d'envoi silencieux
  plus tard dans la boucle.
- `SMTP_PORT` non numérique → `int(...)` lève `ValueError`, non rattrapée
  spécifiquement : le run échoue avec une trace claire (comportement acceptable pour une
  erreur de configuration, pas une erreur runtime normale).
- Échec de connexion/authentification SMTP (mauvais mot de passe, host injoignable) :
  comportement inchangé — l'exception remonte à l'appelant (`main()`), qui logue déjà
  chaque échec d'envoi par destinataire sans bloquer les autres recherches/destinataires
  (voir la boucle par destinataire de `check_logement.py`).

## 5. Tests

- `tests/test_check_logement.py` : le test existant `test_send_email_logs_in_and_sends`
  est étendu pour passer `smtp_host`/`smtp_port`/`from_email` et vérifier que
  `_FakeSMTP.instances[0].host`/`.port` reflètent les valeurs passées (pas
  `smtp.gmail.com`/`465` en dur), et que le message `From:` utilise `from_email`. Ajouter
  un test pour le choix SSL vs STARTTLS (port `465` → `SMTP_SSL` utilisé ; port `587` →
  `SMTP` + `starttls()` appelé — le double de `_FakeSMTP` devra pouvoir distinguer les
  deux classes/chemins). Les tests `main()` existants qui définissaient
  `GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD` via `monkeypatch.setenv` sont mis à jour pour
  définir les 5 nouvelles variables à la place.
- `tests/test_add_search.py` : même mise à jour pour les tests qui définissent
  `GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD`.

## 6. Documentation (README)

- Étape 2 de « Mise en place » (actuellement « Créer un mot de passe d'application
  Google ») remplacée par des instructions Brevo : créer un compte Brevo gratuit,
  récupérer les identifiants SMTP (Settings > SMTP & API > SMTP), vérifier une adresse
  d'expéditeur.
- Étape 3 (liste des secrets) : remplacer `GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD` par les 5
  nouvelles variables, avec une note expliquant la distinction `SMTP_USER` (connexion) vs
  `FROM_EMAIL` (expéditeur affiché, doit être vérifié côté Brevo).
- Section « Développement local » : les exemples `export`/`$env:` sont mis à jour avec
  les 5 nouvelles variables au lieu de 2.
