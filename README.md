# Alerte logement CROUS

Surveille une ou plusieurs recherches sur trouverunlogement.lescrous.fr et envoie un
email dès qu'un nouveau logement correspondant apparaît. Tourne gratuitement 24h/24 via
GitHub Actions — pas besoin de garder un PC allumé. Formulaire public sans compte
requis (Netlify), avec confirmation email et désinscription en un clic.

## Fonctionnement côté utilisateur

1. L'utilisateur remplit le formulaire sur la page d'accueil (ville, et en option
   prix maximum, surface minimum, type de cohabitation, PMR, équipements, mots-clés)
   et coche la case de consentement RGPD.
2. Un email de confirmation lui est envoyé (double opt-in) : tant qu'il ne clique pas
   sur le lien, aucune alerte n'est envoyée. Le lien expire au bout de 10 minutes.
3. Une fois confirmée, la recherche devient active : le bot vérifie le site du CROUS
   toutes les ~5 minutes et envoie un email dès qu'un logement neuf correspond aux
   critères.
4. Chaque email d'alerte contient un lien de désinscription personnalisé, propre à
   cette recherche.

## Critères de recherche supportés

- **Ville / lieu d'étude** — obligatoire, avec autocomplétion (ville, résidence,
  école...) sur le formulaire public.
- **Prix maximum**, **surface minimum**, **type de cohabitation** (individuel,
  couple, colocation), **logement adapté PMR**, **équipements** (douche, évier +
  plaque, frigo, micro-onde, wc) — filtrés directement par le site du CROUS.
- **Mots-clés** — filtrés côté bot : un logement doit être dans la zone ET
  correspondre à au moins un mot-clé (recherche insensible à la casse sur le
  libellé, la résidence et l'adresse).

La logique de ces critères est dupliquée entre `search_criteria.py` (bot Python) et
`netlify/functions/_criteria.js` (formulaire public) — toute modification de l'un doit
être répercutée dans l'autre (voir `CLAUDE.md`).

## Pages du site (`public/`)

- **index.html** — page d'accueil : formulaire de création de recherche, tip de
  recherche, explication du fonctionnement, FAQ.
- **confirmer.html** — validation du code de confirmation reçu par email.
- **desabonnement.html** — désinscription d'une recherche via lien signé.
- **contact.html** — coordonnées de contact.
- **mentions-legales.html** — éditeur, hébergement, données personnelles (RGPD),
  cookies et traceurs.

Pas de framework ni de build step : chaque page est un fichier HTML autonome, nav et
footer identiques recopiés à la main dans les 5 fichiers.

## Mettre en place sa propre instance

1. **Le dépôt GitHub doit être public.** C'est ce qui permet d'avoir des minutes
   GitHub Actions illimitées et gratuites — sur un dépôt privé, les minutes sont
   limitées et le bot finirait par s'arrêter tout seul en cours de mois. Les données
   des abonnés (adresses email, recherches) ne sont pas concernées : elles vivent
   dans un dépôt privé séparé (voir étape 4), jamais dans ce dépôt-ci.

2. **Créer un compte Brevo** (gratuit, 300 emails/jour) sur https://www.brevo.com/
   pour l'envoi des emails :
   - **Settings > SMTP & API > SMTP** pour récupérer l'identifiant SMTP et générer
     une clé SMTP (mot de passe).
   - **Settings > Senders & IP > Senders** pour vérifier une adresse d'expéditeur —
     c'est cette adresse qui sera utilisée comme `FROM_EMAIL` ci-dessous.

3. **Créer un dépôt privé dédié aux données** (ex. `logement-crous-alert-data`) avec
   trois fichiers : `searches.json` contenant `[]`, `pending_searches.json` et
   `seen.json` contenant `{}`. Générer un PAT fine-grained limité à ce seul dépôt,
   permission Contents (Read and write). Le nom de ce dépôt (`owner/nom-du-depot`)
   est écrit en dur dans les quatre workflows sous `.github/workflows/` (`repository:
   LZ-Aissam/logement-crous-alert-data`) — à modifier dans chacun pour pointer vers
   ton propre dépôt de données.

4. **Configurer les secrets du dépôt GitHub public** (Settings > Secrets and
   variables > Actions) :
   - `SMTP_HOST` : `smtp-relay.brevo.com`
   - `SMTP_PORT` : `587`
   - `SMTP_USER` : identifiant SMTP Brevo (étape 2)
   - `SMTP_PASSWORD` : clé SMTP Brevo (étape 2, pas le mot de passe du compte Brevo)
   - `FROM_EMAIL` : adresse expéditeur vérifiée dans Brevo (étape 2)
   - `UNSUBSCRIBE_SECRET` : chaîne aléatoire (ex. générée avec
     `python -c "import secrets; print(secrets.token_urlsafe(32))"`), utilisée pour
     signer les liens de désinscription. Optionnel : sans lui, les alertes partent
     normalement, simplement sans lien de désinscription.
   - `DATA_REPO_PAT` : le PAT créé à l'étape 3.
   - `CONFIRMATION_BASE_URL` et `UNSUBSCRIBE_BASE_URL` : voir étape 7, à poser une
     fois l'URL Netlify connue. Sans eux, les liens de confirmation et de
     désinscription pointent vers une Issue GitHub pré-remplie au lieu d'une page
     web — rien ne casse si Netlify n'est jamais déployé.

5. **Créer le widget Cloudflare Turnstile** sur dash.cloudflare.com pour le domaine du
   site, et remplacer la clé de test `1x00000000000000000000AA` dans
   `public/index.html` par la vraie site key.

6. **Déployer sur Netlify** (formulaire public sans compte GitHub requis) : lier ce
   dépôt à un compte Netlify (`netlify.toml` est détecté automatiquement — `public/`
   comme dossier publié, `netlify/functions/` comme dossier de fonctions), puis dans
   Site configuration > Environment variables :
   - `GITHUB_PAT` : token fine-grained limité à ce dépôt, permission **Issues: Read
     and write** uniquement.
   - `GITHUB_REPOSITORY` : `owner/nom-du-depot-public`
   - `TURNSTILE_SECRET_KEY` : secret key du widget créé à l'étape 5.
   - `DATA_REPO_PAT` : même PAT qu'à l'étape 3 (sert à la détection de doublon ;
     sans lui, la détection échoue ouvert, silencieusement).
   - `DATA_REPO` : `owner/nom-du-depot-de-donnees` (étape 3) — sans cette variable,
     le code retombe par défaut sur le dépôt de données du mainteneur d'origine,
     donc à définir explicitement pour ta propre instance.

7. **Poser sur le dépôt GitHub** (secrets de l'étape 4) une fois l'URL Netlify
   connue :
   - `CONFIRMATION_BASE_URL` : `https://ton-site.netlify.app/confirmer.html`
   - `UNSUBSCRIBE_BASE_URL` (nécessite `UNSUBSCRIBE_SECRET` posé à l'étape 4) :
     `https://ton-site.netlify.app/desabonnement.html`

8. **Activer le workflow** : l'onglet Actions du dépôt doit afficher "Check CROUS
   housing", déclenché automatiquement toutes les ~5 minutes une fois poussé sur la
   branche par défaut. Pour un premier test immédiat : Actions > "Check CROUS
   housing" > "Run workflow".

## Ajouter une recherche sans passer par le formulaire public

Une Issue GitHub (modèle "Nouvelle recherche de logement") fonctionne en parallèle du
formulaire public — utile pour un usage sans déploiement Netlify, ou en secours. Champs
disponibles : nom, ville, mots-clés, email, zone géographique précise, prix maximum,
surface minimum, type de cohabitation, PMR, équipements. Un bot traite l'issue
automatiquement (géocodage, création en attente de confirmation, commentaire de
résumé, fermeture de l'issue).

À noter : la zone créée via ce formulaire a une taille fixe (~11 km × 10 km) centrée
sur la ville — pour une grande agglomération (Paris, Lyon, Marseille...), le `bounds`
généré peut ne pas couvrir toute la zone et doit être élargi à la main dans
`searches.json` (dépôt de données privé) si besoin.

## Limites connues

- **Anti-abus** : Cloudflare Turnstile est la vraie protection ; honeypot et limite de
  5 requêtes/heure par IP restent des garde-fous gratuits supplémentaires, sans
  garantie forte à eux seuls.
- **Relais email** : le formulaire public fait envoyer un email de confirmation à
  n'importe quelle adresse choisie par un visiteur anonyme, avant toute confirmation
  de sa part. En cas d'abus, la mitigation la plus rapide est de révoquer le token
  `GITHUB_PAT` dans les variables d'environnement Netlify — ça coupe le formulaire
  public sans toucher au formulaire GitHub (qui exige un compte pour soumettre).
- **Pas de compte utilisateur** : aucun tableau de bord pour gérer ses recherches
  après coup, uniquement les liens de confirmation/désinscription envoyés par email.
- **Mots-clés mal orthographiés** : rien n'avertit explicitement si un mot-clé ne
  matche jamais un logement réel.

## Développement local

```bash
pip install -r requirements-dev.txt
pytest -v
npm test
python -m http.server 8765 --directory public   # prévisualiser le site
```

Pour lancer le script en local (nécessite les 5 variables SMTP/`FROM_EMAIL`
ci-dessus) :

```bash
export SMTP_HOST=... SMTP_PORT=587 SMTP_USER=... SMTP_PASSWORD=... FROM_EMAIL=...
python check_logement.py
```

En PowerShell :

```powershell
$env:SMTP_HOST = "..."; $env:SMTP_PORT = "587"; $env:SMTP_USER = "..."
$env:SMTP_PASSWORD = "..."; $env:FROM_EMAIL = "..."
python check_logement.py
```

## À savoir

Le bot commit et push automatiquement `seen.json` dans le dépôt de données privé à
chaque run (toutes les ~5 minutes) dès qu'un changement est détecté — ces commits
signés "logement-alert-bot" n'apparaissent pas dans l'historique de ce dépôt public,
c'est normal.
