# Alerte logement CROUS

Surveille une ou plusieurs recherches sur trouverunlogement.lescrous.fr et envoie un
email dès qu'un nouveau logement apparaît. Tourne gratuitement 24h/24 via GitHub
Actions — pas besoin de garder un PC allumé.

## Mise en place

1. **Le dépôt GitHub doit être public.** C'est ce qui permet d'avoir des minutes
   GitHub Actions illimitées et gratuites — sur un dépôt privé, les minutes sont
   limitées et le bot finirait par s'arrêter tout seul en cours de mois.

2. **Créer un compte Brevo** (gratuit, 300 emails/jour) sur https://www.brevo.com/ pour
   l'envoi des emails — évite de faire transiter tout le trafic (alertes, confirmations)
   par ton compte Gmail personnel :
   - Dans Brevo, va dans **Settings > SMTP & API > SMTP** pour récupérer ton identifiant
     SMTP et générer une clé SMTP (mot de passe).
   - Vérifie une adresse d'expéditeur (**Settings > Senders & IP > Senders**, ajoute et
     valide l'adresse que tu veux voir comme expéditeur des emails) — c'est cette adresse
     qui sera utilisée comme `FROM_EMAIL` ci-dessous.

3. **Configurer les secrets du dépôt GitHub** : Settings > Secrets and variables >
   Actions > New repository secret, ajouter :
   - `SMTP_HOST` : l'hôte SMTP de Brevo, `smtp-relay.brevo.com`
   - `SMTP_PORT` : `587`
   - `SMTP_USER` : ton identifiant SMTP Brevo (récupéré à l'étape 2)
   - `SMTP_PASSWORD` : ta clé SMTP Brevo (générée à l'étape 2, pas ton mot de passe de
     compte Brevo)
   - `FROM_EMAIL` : l'adresse expéditeur vérifiée dans Brevo à l'étape 2 — distincte de
     `SMTP_USER`, qui sert uniquement à l'authentification
   - `UNSUBSCRIBE_SECRET` : une chaine aleatoire (ex. generee avec
     `python -c "import secrets; print(secrets.token_urlsafe(32))"`), utilisee pour
     signer les liens de desinscription dans les emails d'alerte. Optionnel : sans ce
     secret, les emails sont envoyes normalement, simplement sans lien de
     desinscription.

4. **Éditer `searches.json`** pour ajouter/retirer des recherches (ou passer par une
   Issue GitHub, voir plus bas, si tu préfères ne pas toucher au fichier à la main).
   Une fois la migration vers le dépôt de données privé effectuée (voir plus bas), ce
   fichier vit dans ce dépôt privé, pas ici.
   Pour obtenir l'URL d'une recherche : va sur trouverunlogement.lescrous.fr, règle les
   filtres voulus (ville, type de logement, prix...) dans l'interface, puis copie l'URL
   de la barre d'adresse. Champ `emails` obligatoire (liste avec une seule adresse) :
   sans lui, le bot ignore cette recherche à chaque exécution et logue une erreur,
   faute de destinataire — aucune alerte n'est jamais envoyée.

   Attention : au tout premier passage pour une recherche donnée, tous les logements
   actuellement listés seront considérés comme "nouveaux" et déclencheront un email
   immédiatement. Si tu ajoutes une recherche qui a déjà des résultats, attends-toi à
   recevoir un email avec tout le lot dès le premier run — c'est voulu, pas un bug.

   Champ `keywords` optionnel (liste de mots-clés) : si présent, un logement doit être
   à la fois dans la zone de la recherche ET correspondre à au moins un des mots-clés
   pour déclencher une alerte (comparaison insensible à la casse, sur le libellé du
   logement, le nom de la résidence, et l'adresse). Si le champ est absent, tous les
   logements de la zone déclenchent une alerte comme avant. Exemple :

   ```json
   [
     {
       "name": "Brest Kergoat",
       "url": "https://trouverunlogement.lescrous.fr/tools/47/search?bounds=...",
       "keywords": ["Kergoat", "studio"],
       "emails": ["toi@example.com"]
     }
   ]
   ```

   Ici, une annonce ne déclenchera un email que si elle est dans la zone de Brest ET
   que "Kergoat" ou "studio" apparaît dans son libellé, le nom de la résidence, ou son
   adresse.

5. **Activer le workflow** : l'onglet Actions du dépôt doit afficher "Check CROUS
   housing". Il se déclenche automatiquement toutes les ~5 minutes une fois poussé
   sur la branche par défaut. Pour un premier test immédiat sans attendre : onglet
   Actions > "Check CROUS housing" > "Run workflow".

## Ajouter une recherche via une Issue GitHub

Pas envie de modifier `searches.json` à la main ? Tu peux ajouter une nouvelle
recherche en ouvrant une Issue :

1. Sur la page du dépôt, clique sur "New issue".
2. Choisis le modèle "Nouvelle recherche de logement".
3. Remplis les champs :
   - **Nom de la recherche** : un nom court et unique (ex. "Brest", "Rennes Kergoat").
   - **Ville** : la ville à surveiller (ex. "Brest" ou "Brest 29200").
   - **Mots-clés** (optionnel) : séparés par des virgules, voir la section `keywords`
     ci-dessus.
   - **Email de notification** (obligatoire) : une seule adresse. Elle recevra un
     email de confirmation a valider avant de recevoir des alertes.
   - **Zone géographique précise** (optionnel) : normalement laissé vide pour une
     Issue manuelle — rempli automatiquement par le formulaire public quand une
     suggestion est sélectionnée.
   - **Prix maximum** (optionnel) : en euros.
   - **Surface minimum en m²** (optionnel).
   - **Type de cohabitation** (optionnel) : `individuel`, `couple`, `colocation`,
     séparés par des virgules.
   - **Logement adapté PMR** (optionnel) : écris `oui` pour filtrer sur
     l'accessibilité PMR.
4. Soumets l'issue.

À noter : la zone de recherche créée via ce formulaire a une **taille fixe** (environ
11 km × 10 km) centrée sur la ville. Pour une très grande ville (Paris, Lyon,
Marseille...), cette zone peut ne pas couvrir toute l'agglomération — le `bounds` de
l'URL générée peut être élargi à la main dans `searches.json` par la suite si besoin
(dans le dépôt de données privé une fois la migration effectuée, voir plus bas).

Un bot prend ensuite le relais automatiquement : il géocode la ville, construit l'URL
de recherche correspondante, puis crée la recherche en attente de confirmation email (voir
la section suivante), et commente l'issue avec un résumé de ce qui a été créé. Si tout
s'est bien passé, l'issue est fermée automatiquement. Si quelque chose a coincé (ville
introuvable, nom déjà utilisé...), le bot commente en expliquant le problème et laisse
l'issue ouverte — corrige simplement les champs et rouvre une nouvelle issue.

À noter : s'il n'y a actuellement aucun logement disponible dans la ville demandée, le
bot ne peut pas te proposer de vrais noms de résidences ou de types de logement pour
vérifier l'orthographe de tes mots-clés. Il crée quand même la recherche normalement,
juste sans cette vérification — tu ne sauras pas si un mot-clé est mal orthographié tant
qu'aucun logement de la zone n'est disponible pour le vérifier, et même dans ce cas, rien
ne t'avertira explicitement d'un mot-clé qui ne matche jamais. Pense à vérifier de temps
en temps sur le site du CROUS si un logement qui te semble pertinent n'a pas déclenché d'alerte.

### Confirmation d'email obligatoire

Une seule adresse email est obligatoire pour créer une recherche. Elle n'est **pas
activée tout de suite** : la recherche est créée **en attente** (stockée dans
`pending_searches.json`, pas encore dans `searches.json`) et n'envoie aucune alerte
pour l'instant.

Un email de confirmation est envoyé à cette adresse, avec un lien à cliquer pour
confirmer. Par défaut ce lien ouvre une nouvelle Issue GitHub pré-remplie avec un
code de confirmation unique (nécessite un compte GitHub, gratuit) — sauf si le
formulaire public Netlify est configuré (voir plus bas), auquel cas le lien ouvre
une simple page web, sans compte requis.

Dès que l'adresse confirme, la recherche devient active dans `searches.json`, avec
cette adresse comme seul destinataire.

Cette étape existe pour une seule raison : empêcher que quelqu'un renseigne l'adresse
email d'un inconnu et lui fasse recevoir, sans son accord, des emails automatiques
depuis l'adresse d'expéditeur configurée pour ce dépôt.

### Se désinscrire d'une recherche

Chaque email d'alerte contient, en pied de message, un lien de désinscription
personnalisé (nom de la recherche, adresse email et jeton de sécurité). En cliquant
dessus, tu retires ton adresse de **cette recherche précise** — les autres recherches
auxquelles tu es éventuellement abonné ne sont pas affectées. Si tu étais la dernière
adresse inscrite sur cette recherche, elle est supprimée entièrement.

Comme pour la confirmation d'email, ce lien ouvre soit une Issue GitHub pré-remplie
(compte GitHub requis), soit une simple page web si le formulaire public Netlify est
configuré (voir plus bas) — le bot choisit automatiquement le bon format selon la
configuration du dépôt, rien à faire de ton côté.

Ce lien n'apparaît dans l'email que si le secret `UNSUBSCRIBE_SECRET` est configuré
(voir étape 3 ci-dessus) ; sans lui, les emails d'alerte fonctionnent comme avant,
simplement sans lien de désinscription.

## Formulaire public sans compte GitHub (optionnel, via Netlify)

Par défaut, créer une recherche ou confirmer un email nécessite un compte GitHub (pour
soumettre les Issue Forms ci-dessus). Pour ouvrir ça à n'importe qui sans compte, tu
peux déployer les pages `public/index.html` (nouvelle recherche), `public/confirmer.html`
et `public/desabonnement.html` sur Netlify — elles créent les mêmes Issues GitHub à ta
place, via trois Netlify Functions (`netlify/functions/create-search.js`,
`confirm-email.js` et `unsubscribe.js`). Le backend Python et les
workflows GitHub Actions ne changent pas : ils traitent ces Issues exactement comme si
elles avaient été soumises à la main.

Le champ "Ville, résidence ou lieu d'étude" propose des suggestions en direct (ville,
résidence, école...) via le même service que le site CROUS officiel — sélectionner une
suggestion cible précisément le bon endroit plutôt qu'une zone approximative autour
d'une ville. Seuls les lieux situés en France sont proposés (DOM-TOM inclus, ils ont
leurs propres CROUS). Les filtres prix/surface/cohabitation/PMR sont transmis tels quels au
site CROUS, qui applique le filtrage lui-même avant que le robot ne récupère les
résultats.

Le formulaire est protégé par Cloudflare Turnstile et refuse une inscription en
double : la même adresse ne peut pas s'abonner deux fois à une recherche aux
critères identiques.

Les données d'abonnés (`searches.json`, `pending_searches.json`, `seen.json`) ne
vivent pas dans ce dépôt public mais dans un dépôt privé dédié, pour que les
adresses email des inscrits ne soient pas publiées. Les workflows y accèdent via le
secret `DATA_REPO_PAT`.

La checklist complète pour effectuer cette migration (créer le dépôt privé, poser
les secrets, déployer, nettoyer l'ancien dépôt public) est dans
`docs/superpowers/plans/2026-07-28-migration-checklist.md`.

1. Crée un compte Netlify et lie-le à ce dépôt GitHub (Netlify détecte automatiquement
   `netlify.toml` : `public/` comme dossier publié, `netlify/functions/` comme dossier
   de fonctions).
2. Crée un token GitHub *fine-grained* (Settings > Developer settings > Personal access
   tokens > Fine-grained tokens), limité à **ce seul dépôt**, avec la permission
   **Issues: Read and write** uniquement (rien d'autre).
3. Dans les paramètres du site Netlify (Site configuration > Environment variables),
   ajoute :
   - `GITHUB_PAT` : le token créé à l'étape 2
   - `GITHUB_REPOSITORY` : `LZ-Aissam/logement-crous-alert`
   - `TURNSTILE_SECRET_KEY` : la secret key de ton widget Cloudflare Turnstile (voir
     la checklist de migration pour la création du widget) — sans elle, toute
     soumission du formulaire est refusée.
   - `DATA_REPO_PAT` : le même type de token fine-grained que `GITHUB_PAT`, mais
     limité au dépôt de données privé, avec la permission **Contents: Read and
     write** — sans lui, la détection de doublon est silencieusement inactive (elle
     échoue ouvert, voir plus bas).
4. Ajoute ces secrets sur le dépôt GitHub (Settings > Secrets and variables > Actions) :
   - `CONFIRMATION_BASE_URL` : l'URL de la page de confirmation sur ton site Netlify,
     ex. `https://ton-site.netlify.app/confirmer.html`
   - `UNSUBSCRIBE_BASE_URL` (optionnel, nécessite `UNSUBSCRIBE_SECRET` déjà configuré à
     l'étape 3 de la mise en place) : l'URL de la page de désinscription, ex.
     `https://ton-site.netlify.app/desabonnement.html`

   Sans ces secrets, les liens de confirmation et de désinscription continuent de
   pointer vers GitHub comme avant — rien ne casse si tu ne déploies jamais Netlify.
5. Le formulaire GitHub direct (section ci-dessus) continue de fonctionner en
   parallèle : c'est une alternative, pas un remplacement.

**Limite assumée** : Cloudflare Turnstile est la vraie protection anti-abus ; le
honeypot et la limite de 5 requêtes/heure par IP restent en place comme garde-fous
gratuits supplémentaires, sans garantie forte à eux seuls. Comme pour le formulaire
GitHub actuel, il n'y a pas de compte utilisateur ni de tableau de bord pour gérer ses propres
recherches après coup.

**Risque à connaître** : ce formulaire public est aussi un relais d'envoi d'emails
depuis ton compte d'envoi d'emails — n'importe quel visiteur anonyme peut faire envoyer un
email de confirmation à une adresse de son choix par soumission, avant toute
confirmation de sa part. En cas d'abus constaté, la mitigation la plus rapide est de
révoquer le token `GITHUB_PAT` dans les variables d'environnement Netlify : ça coupe
immédiatement le formulaire public, sans toucher au formulaire GitHub classique
ci-dessus (qui, lui, exige un compte GitHub pour soumettre).

## Développement local

```bash
pip install -r requirements-dev.txt
python -m pytest -v
```

Pour lancer le script en local (nécessite les 5 variables d'environnement ci-dessus) :

En bash / macOS / Linux :

```bash
export SMTP_HOST=... SMTP_PORT=587 SMTP_USER=... SMTP_PASSWORD=... FROM_EMAIL=...
python check_logement.py
```

En PowerShell (Windows) :

```powershell
$env:SMTP_HOST = "..."
$env:SMTP_PORT = "587"
$env:SMTP_USER = "..."
$env:SMTP_PASSWORD = "..."
$env:FROM_EMAIL = "..."
python check_logement.py
```

## À savoir

Le bot commit et push automatiquement `seen.json` à chaque run (toutes les ~5 minutes)
dès qu'un changement est détecté. Une fois la migration vers le dépôt de données privé
effectuée (voir plus haut), ces commits automatiques signés "logement-alert-bot"
apparaissent dans l'historique du dépôt privé, pas dans celui-ci — c'est normal, pas un
problème.
