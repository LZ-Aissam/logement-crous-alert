# Lien de désinscription dans les emails d'alerte — Design

## Contexte

Une fois une recherche active dans `searches.json`, il n'existe aucun moyen pour un
destinataire de s'en désinscrire lui-même : il faudrait éditer `searches.json` à la
main sur GitHub. C'est une limite déjà documentée dans le README (« pas de tableau de
bord pour gérer ses propres recherches après coup »). Ce document ajoute un lien de
désinscription en pied de chaque email d'alerte, en réutilisant le pattern déjà en
place pour la confirmation d'email et la création de recherche (voir
`2026-07-28-netlify-public-form-design.md`) : jeton dans l'URL → Issue GitHub → workflow
Actions → mise à jour de `searches.json`, avec une façade Netlify optionnelle pour ne
pas exiger de compte GitHub.

## Objectif

Chaque email d'alerte envoyé par `check_logement.py` contient un lien qui, une fois
cliqué (et confirmé par un clic explicite sur la page), retire l'adresse email
destinataire de la recherche concernée — et seulement celle-ci. Fonctionne sans compte
GitHub si le déploiement Netlify est configuré (comme pour la confirmation), sinon via
Issue GitHub comme repli.

## Décisions de conception (issues du brainstorming)

- **Portée** : désinscription **par recherche**, pas globale — cohérent avec le fait que
  chaque email d'alerte concerne une seule recherche.
- **Dernier email d'une recherche** : la recherche entière est **supprimée** de
  `searches.json` (pas de repli sur `ALERT_EMAIL`) — une recherche sans destinataire
  restant n'a plus de raison d'exister.
- **Email groupé → email individuel** : `check_logement.py` envoie désormais **un email
  par destinataire** (au lieu d'un seul email avec tous les destinataires en `À`), pour
  que chaque lien de désinscription soit personnalisé. Bénéfice secondaire : les
  destinataires d'une même recherche ne voient plus les adresses des autres.
- **Jeton stateless (HMAC)**, pas de nouvel état stocké — voir section 1.

## Hors scope (assumé)

- Pas de page de gestion générale des recherches — uniquement un lien de désinscription
  ciblé par email/recherche, comme pour la confirmation.
- Pas d'expiration de jeton : le jeton reste valide tant que le secret n'est pas changé
  et que la recherche n'est pas renommée (voir « Limite connue » ci-dessous).
- Pas de undo — une fois désinscrit, il faut recréer la recherche via le formulaire
  habituel pour se réabonner.

## 1. Architecture

```
check_logement.py (nouvel envoi individuel)
   │  pour chaque (recherche, email) :
   │  token = HMAC-SHA256(UNSUBSCRIBE_SECRET, "{nom_recherche}|{email en minuscules}")
   │  lien = UNSUBSCRIBE_BASE_URL?search=...&email=...&token=...
   │         (ou, si UNSUBSCRIBE_BASE_URL absent : Issue GitHub pré-remplie)
   ▼
Email d'alerte individuel avec lien de désinscription en pied de message
   │
   ▼
Visiteur clique le lien
   │
   ├── Netlify configuré ──▶ public/desabonnement.html (bouton "Se désinscrire", pas
   │                          d'action automatique au chargement) ──▶ POST
   │                          /.netlify/functions/unsubscribe ──▶ crée une Issue GitHub
   │                          (même honeypot/rate-limit/pattern que confirm-email.js)
   │
   └── Sinon ──▶ github.com/{repo}/issues/new?template=unsubscribe.yml&search=...
                  &email=...&token=... (compte GitHub requis, comme avant Netlify)
   ▼
Issue GitHub créée (label "unsubscribe")
   ▼
Workflow unsubscribe.yml (déclenché sur l'ouverture de l'Issue)
   ▼
unsubscribe.py : recalcule le jeton attendu et le compare (temps constant) à celui
   soumis ; si valide, retire l'email de searches.json (ou supprime la recherche si
   c'était le dernier email) ; commit + push + ferme l'Issue — même pattern que
   confirm_email.py / confirm-email.yml
```

Le jeton HMAC est **stateless** : aucun fichier ne stocke de token, contrairement à
`pending_searches.json` pour la confirmation. Il est recalculé à la volée à l'émission
(par `check_logement.py`) et à la vérification (par `unsubscribe.py`), à partir du même
secret `UNSUBSCRIBE_SECRET` (nouveau secret repo GitHub, une chaîne aléatoire).

**Limite connue** : le jeton est calculé à partir du **nom** de la recherche. Si une
recherche est renommée manuellement dans `searches.json` après l'envoi d'un email
d'alerte, les liens de désinscription déjà envoyés pour l'ancien nom deviennent
invalides (l'utilisateur devra attendre la prochaine alerte, qui contiendra un lien à
jour). Cas rare, assumé.

## 2. `check_logement.py`

- `main()` boucle maintenant sur chaque email de `recipients` individuellement au lieu
  d'appeler `send_email` une fois avec la liste complète : un appel SMTP par
  destinataire (au plus 3 par recherche, négligeable en volume).
- Nouvelle fonction `build_unsubscribe_url(search_name: str, email: str) -> str` :
  - `token = hmac.new(UNSUBSCRIBE_SECRET.encode(), f"{search_name}|{email.lower()}".encode(), hashlib.sha256).hexdigest()`
  - Si `UNSUBSCRIBE_BASE_URL` (variable d'env) est définie : retourne
    `f"{UNSUBSCRIBE_BASE_URL}?search={quote(search_name)}&email={quote(email)}&token={token}"`.
  - Sinon : retourne l'URL de création d'Issue GitHub pré-remplie (
    `?template=unsubscribe.yml&search=...&email=...&token=...`), sur le modèle de
    `build_confirmation_url`.
  - Si `UNSUBSCRIBE_SECRET` n'est pas défini du tout (pas encore configuré), le lien de
    désinscription est **omis** de l'email (pas d'erreur, alerte quand même envoyée) —
    pour que l'activation de cette fonctionnalité soit, comme Netlify, strictement
    optionnelle et rétrocompatible.
- `format_email_body` prend le lien de désinscription en paramètre optionnel et
  l'ajoute en pied de message si présent : `"\nPour ne plus recevoir ces alertes : {url}"`.

## 3. `unsubscribe.py` (nouveau, miroir de `confirm_email.py`)

- Lit `ISSUE_BODY`, parse les champs `Nom de la recherche`, `Email`, `Jeton` via
  `parse_issue_form_body` (réutilisé depuis `add_search.py`).
- Recalcule le jeton attendu avec `UNSUBSCRIBE_SECRET` et compare avec
  `hmac.compare_digest` (temps constant, évite les attaques par timing).
- Jeton invalide → message d'erreur, code de sortie 1 (l'Issue reste ouverte avec un
  commentaire d'erreur, comme les autres workflows).
- Jeton valide → cherche la recherche par nom (insensible à la casse) dans
  `searches.json`, retire l'email (insensible à la casse) de `emails` :
  - Si `emails` devient vide → la recherche entière est retirée de la liste.
  - Sinon → la recherche est gardée avec la liste `emails` mise à jour.
  - Recherche introuvable (déjà supprimée, ou email déjà retiré) → message informatif,
    pas une erreur fatale (idempotent en cas de double clic).
- Sauvegarde `searches.json` via `clog.save_searches`.

## 4. Issue Form et workflow

`.github/ISSUE_TEMPLATE/unsubscribe.yml` (miroir de `confirm-email.yml`) : trois champs
`Nom de la recherche` / `Email` / `Jeton`, tous pré-remplis via les paramètres de l'URL
(`?search=&email=&token=`), label `unsubscribe`.

`.github/workflows/unsubscribe.yml` : déclenché sur `issues: opened` avec le label
`unsubscribe`, appelle `unsubscribe.py`, commente le résultat, commit+push
`searches.json` si succès, ferme l'Issue — copie exacte de la structure de
`confirm-email.yml`.

`check.yml` passe les nouvelles variables à `check_logement.py` : `UNSUBSCRIBE_SECRET`,
`UNSUBSCRIBE_BASE_URL`, et `GITHUB_REPOSITORY: ${{ github.repository }}` (nécessaire au
repli Issue GitHub quand `UNSUBSCRIBE_BASE_URL` n'est pas défini — pas encore passé
aujourd'hui puisque `check_logement.py` n'en avait pas besoin). `unsubscribe.yml` passe
`UNSUBSCRIBE_SECRET` à `unsubscribe.py`.

## 5. Façade Netlify (optionnelle, comme pour la confirmation)

### `public/desabonnement.html?search=...&email=...&token=...`

Affiche « Se désinscrire de la recherche « {search} » pour {email} ? » et un bouton
**« Se désinscrire »** explicite (pas d'action automatique au chargement — même
précaution anti-scanner qu'sur `confirmer.html`). Clic →
`POST /.netlify/functions/unsubscribe` avec `{ search, email, token, website }` (champ
honeypot) → la fonction crée l'Issue `"[Désinscription]"` avec le label `unsubscribe` et
un corps `"### Nom de la recherche\n\n{search}\n\n### Email\n\n{email}\n\n### Jeton\n\n{token}\n"`
(même format que produirait le Issue Form).

### `netlify/functions/unsubscribe.js`

Même structure que `confirm-email.js` : rejette si honeypot rempli (succès silencieux),
rejette si rate-limit dépassé (429), valide que les trois champs sont présents et non
vides (400), crée l'Issue via `_github.js` (502 en cas d'échec API GitHub).

## 6. Erreurs

- Lien de désinscription absent de l'email si `UNSUBSCRIBE_SECRET` n'est pas configuré
  (pas d'erreur, juste pas de lien) — comportement rétrocompatible.
- Jeton invalide/falsifié → Issue reste ouverte, commentaire d'erreur explicite, pas de
  modification de `searches.json`.
- Recherche/email déjà retiré (double clic, lien réutilisé) → commentaire informatif
  « déjà désinscrit ou recherche introuvable », pas un échec bloquant.
- Honeypot / rate-limit / erreur API GitHub côté Netlify → identique à `confirm-email.js`
  (section 4 de `2026-07-28-netlify-public-form-design.md`).

## 7. Tests

- **Python** (`tests/test_unsubscribe.py`, nouveau) : jeton valide retire l'email
  attendu ; jeton invalide ne modifie rien et retourne une erreur ; retirer le dernier
  email supprime la recherche entière ; retirer un email d'une recherche qui en a
  d'autres la garde ; recherche/email introuvable est idempotent (pas d'erreur fatale).
- **Python** (`tests/test_check_logement.py`, étendu) : `build_unsubscribe_url` avec/sans
  `UNSUBSCRIBE_BASE_URL` défini ; `main()` envoie désormais un email par destinataire
  (mock `send_email`, vérifier le nombre d'appels et les destinataires uniques par appel).
- **JS** (`netlify/functions/__tests__/unsubscribe.test.js`, nouveau, même pattern que
  `confirm-email.test.js`) : honeypot, rate-limit, payload valide crée l'Issue avec le
  bon `title`/`body`/`labels`, champs manquants retournent 400.

## 8. Structure de fichiers (nouveaux/modifiés)

```
check_logement.py                          # modifié : envoi individuel + lien desinscription
unsubscribe.py                             # nouveau
.github/ISSUE_TEMPLATE/unsubscribe.yml     # nouveau
.github/workflows/unsubscribe.yml          # nouveau
.github/workflows/check.yml                # modifié : + UNSUBSCRIBE_SECRET, UNSUBSCRIBE_BASE_URL
netlify/functions/unsubscribe.js           # nouveau
netlify/functions/__tests__/unsubscribe.test.js  # nouveau
public/desabonnement.html                  # nouveau
tests/test_unsubscribe.py                  # nouveau
```

## 9. Déploiement (à documenter dans le README)

1. Ajouter le secret GitHub `UNSUBSCRIBE_SECRET` (chaîne aléatoire, ex. générée avec
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`).
2. Optionnel, si la façade Netlify est utilisée : ajouter le secret GitHub
   `UNSUBSCRIBE_BASE_URL` (ex. `https://<ton-site>.netlify.app/desabonnement.html`).
3. Sans ces secrets, comportement inchangé : pas de lien de désinscription dans les
   emails, rien ne casse.
