# Alerte logement CROUS

Surveille une ou plusieurs recherches sur trouverunlogement.lescrous.fr et envoie un
email dès qu'un nouveau logement apparaît. Tourne gratuitement 24h/24 via GitHub
Actions — pas besoin de garder un PC allumé.

## Mise en place

1. **Le dépôt GitHub doit être public.** C'est ce qui permet d'avoir des minutes
   GitHub Actions illimitées et gratuites — sur un dépôt privé, les minutes sont
   limitées et le bot finirait par s'arrêter tout seul en cours de mois.

2. **Créer un mot de passe d'application Google** (nécessite la validation en 2 étapes
   activée sur le compte Gmail utilisé pour envoyer les emails) :
   https://myaccount.google.com/apppasswords — génère un mot de passe pour "Mail",
   copie-le (16 caractères sans espaces).

3. **Configurer les secrets du dépôt GitHub** : Settings > Secrets and variables >
   Actions > New repository secret, ajouter :
   - `GMAIL_ADDRESS` : l'adresse Gmail utilisée pour envoyer (ex: theaissam@gmail.com)
   - `GMAIL_APP_PASSWORD` : le mot de passe d'application généré à l'étape 2
   - `ALERT_EMAIL` : l'email destinataire par défaut, utilisé pour toute recherche
     dans `searches.json` qui n'a pas son propre champ `emails`

4. **Éditer `searches.json`** pour ajouter/retirer des recherches. Pour obtenir l'URL
   d'une recherche : va sur trouverunlogement.lescrous.fr, règle les filtres voulus
   (ville, type de logement, prix...) dans l'interface, puis copie l'URL de la barre
   d'adresse. Champ `emails` optionnel (liste de destinataires spécifiques à cette
   recherche) ; s'il est absent, `ALERT_EMAIL` est utilisé.

   Attention : au tout premier passage pour une recherche donnée, tous les logements
   actuellement listés seront considérés comme "nouveaux" et déclencheront un email
   immédiatement. Si tu ajoutes une recherche qui a déjà des résultats, attends-toi à
   recevoir un email avec tout le lot dès le premier run — c'est voulu, pas un bug.

5. **Activer le workflow** : l'onglet Actions du dépôt doit afficher "Check CROUS
   housing". Il se déclenche automatiquement toutes les ~10 minutes une fois poussé
   sur la branche par défaut. Pour un premier test immédiat sans attendre : onglet
   Actions > "Check CROUS housing" > "Run workflow".

## Développement local

```bash
pip install -r requirements-dev.txt
python -m pytest -v
```

Pour lancer le script en local (nécessite les 3 variables d'environnement ci-dessus) :

En bash / macOS / Linux :

```bash
export GMAIL_ADDRESS=... GMAIL_APP_PASSWORD=... ALERT_EMAIL=...
python check_logement.py
```

En PowerShell (Windows) :

```powershell
$env:GMAIL_ADDRESS = "..."
$env:GMAIL_APP_PASSWORD = "..."
$env:ALERT_EMAIL = "..."
python check_logement.py
```

## À savoir

Le bot commit et push automatiquement `seen.json` à chaque run (toutes les ~10 minutes)
dès qu'un changement est détecté. Il est donc normal de voir de temps en temps des
commits automatiques signés "logement-alert-bot" dans l'historique du dépôt — ce n'est
pas un problème.
