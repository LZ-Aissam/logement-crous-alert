# Alerte logement CROUS

Surveille une ou plusieurs recherches sur trouverunlogement.lescrous.fr et envoie un
email dès qu'un nouveau logement apparaît. Tourne gratuitement 24h/24 via GitHub
Actions — pas besoin de garder un PC allumé.

## Mise en place

1. **Créer un mot de passe d'application Google** (nécessite la validation en 2 étapes
   activée sur le compte Gmail utilisé pour envoyer les emails) :
   https://myaccount.google.com/apppasswords — génère un mot de passe pour "Mail",
   copie-le (16 caractères sans espaces).

2. **Configurer les secrets du dépôt GitHub** : Settings > Secrets and variables >
   Actions > New repository secret, ajouter :
   - `GMAIL_ADDRESS` : l'adresse Gmail utilisée pour envoyer (ex: theaissam@gmail.com)
   - `GMAIL_APP_PASSWORD` : le mot de passe d'application généré à l'étape 1
   - `ALERT_EMAIL` : l'email destinataire par défaut, utilisé pour toute recherche
     dans `searches.json` qui n'a pas son propre champ `emails`

3. **Éditer `searches.json`** pour ajouter/retirer des recherches. Pour obtenir l'URL
   d'une recherche : va sur trouverunlogement.lescrous.fr, règle les filtres voulus
   (ville, type de logement, prix...) dans l'interface, puis copie l'URL de la barre
   d'adresse. Champ `emails` optionnel (liste de destinataires spécifiques à cette
   recherche) ; s'il est absent, `ALERT_EMAIL` est utilisé.

4. **Activer le workflow** : l'onglet Actions du dépôt doit afficher "Check CROUS
   housing". Il se déclenche automatiquement toutes les ~10 minutes une fois poussé
   sur la branche par défaut. Pour un premier test immédiat sans attendre : onglet
   Actions > "Check CROUS housing" > "Run workflow".

## Développement local

```bash
pip install -r requirements-dev.txt
python -m pytest -v
```

Pour lancer le script en local (nécessite les 3 variables d'environnement ci-dessus) :

```bash
export GMAIL_ADDRESS=... GMAIL_APP_PASSWORD=... ALERT_EMAIL=...
python check_logement.py
```
