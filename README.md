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

4. **Éditer `searches.json`** pour ajouter/retirer des recherches (ou passer par une
   Issue GitHub, voir plus bas, si tu préfères ne pas toucher au fichier à la main).
   Pour obtenir l'URL d'une recherche : va sur trouverunlogement.lescrous.fr, règle les
   filtres voulus (ville, type de logement, prix...) dans l'interface, puis copie l'URL
   de la barre d'adresse. Champ `emails` optionnel (liste de destinataires spécifiques à
   cette recherche) ; s'il est absent, `ALERT_EMAIL` est utilisé.

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
   - **Email(s) de notification** (optionnel) : séparés par des virgules ; laisse vide
     pour utiliser `ALERT_EMAIL`.
4. Soumets l'issue.

À noter : la zone de recherche créée via ce formulaire a une **taille fixe** (environ
11 km × 10 km) centrée sur la ville. Pour une très grande ville (Paris, Lyon,
Marseille...), cette zone peut ne pas couvrir toute l'agglomération — le `bounds` de
l'URL générée peut être élargi à la main dans `searches.json` par la suite si besoin.

Un bot prend ensuite le relais automatiquement : il géocode la ville, construit l'URL
de recherche correspondante, puis crée la recherche (immédiatement, ou en attente de
confirmation si tu as renseigné un email — voir la section suivante), et commente
l'issue avec un résumé de ce qui a été créé. Si tout s'est bien passé, l'issue est fermée
automatiquement. Si quelque chose a coincé (ville introuvable, nom déjà utilisé...), le
bot commente en expliquant le problème et laisse l'issue ouverte — corrige simplement
les champs et rouvre une nouvelle issue.

À noter : s'il n'y a actuellement aucun logement disponible dans la ville demandée, le
bot ne peut pas te proposer de vrais noms de résidences ou de types de logement pour
vérifier l'orthographe de tes mots-clés. Il crée quand même la recherche normalement,
juste sans cette vérification — tu ne sauras pas si un mot-clé est mal orthographié tant
qu'aucun logement de la zone n'est disponible pour le vérifier, et même dans ce cas, rien
ne t'avertira explicitement d'un mot-clé qui ne matche jamais. Pense à vérifier de temps
en temps sur le site du CROUS si un logement qui te semble pertinent n'a pas déclenché d'alerte.

### Confirmation d'email obligatoire

Si tu renseignes une ou plusieurs adresses dans le champ **Email(s) de notification**,
la recherche n'est **pas activée tout de suite**. Elle est créée **en attente**
(stockée dans `pending_searches.json`, pas encore dans `searches.json`) et n'envoie
aucune alerte pour l'instant.

Un email de confirmation est envoyé à chaque adresse renseignée, avec un lien vers un
second formulaire ("Confirmer mon email"). Ce lien ouvre une nouvelle Issue
pré-remplie avec un code de confirmation unique ; soumettre cette issue nécessite un
compte GitHub (gratuit).

Dès qu'**une seule** des adresses confirme, la recherche devient active dans
`searches.json`, avec cette adresse comme destinataire. Les autres adresses peuvent
confirmer plus tard, chacune depuis son propre lien, et sont ajoutées à la liste des
destinataires au fur et à mesure.

Si le champ email est laissé vide, la recherche est activée immédiatement avec
`ALERT_EMAIL` comme destinataire — pas de confirmation nécessaire dans ce cas, puisque
c'est l'adresse du propriétaire du dépôt lui-même.

Cette étape existe pour une seule raison : empêcher que quelqu'un renseigne l'adresse
email d'un inconnu et lui fasse recevoir, sans son accord, des emails automatiques
depuis le compte Gmail du propriétaire du dépôt.

**Attention, ces données restent publiques :** les adresses email que tu soumets
finissent dans les fichiers du dépôt (`searches.json`, `pending_searches.json`), qui
est public — ne mets pas d'adresse que tu ne veux pas voir apparaître publiquement sur
GitHub, y compris dans l'historique Git une fois l'adresse retirée du fichier courant.
(Les codes de confirmation eux-mêmes ne sont jamais stockés en clair — seule leur
empreinte cryptographique l'est.)

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

Le bot commit et push automatiquement `seen.json` à chaque run (toutes les ~5 minutes)
dès qu'un changement est détecté. Il est donc normal de voir de temps en temps des
commits automatiques signés "logement-alert-bot" dans l'historique du dépôt — ce n'est
pas un problème.
