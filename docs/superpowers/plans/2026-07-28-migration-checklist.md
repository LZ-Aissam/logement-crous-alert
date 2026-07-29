# Checklist de migration

Etapes d'exploitation, a faire dans l'ordre. A partir de l'etape 4 (deploiement),
le robot lit les donnees depuis le depot prive : toute recherche non recreee la-bas
(y compris Brest et Rennes) cesse d'etre surveillee des ce moment, pas seulement
apres la suppression des anciens fichiers a l'etape 5.

- [ ] 1. Creer le depot prive `LZ-Aissam/logement-crous-alert-data` avec trois
      fichiers : `searches.json` contenant `[]`, `pending_searches.json` et
      `seen.json` contenant `{}`.
- [ ] 2. Creer un PAT fine-grained limite a ce seul depot, permission
      Contents read/write. Le poser en secret `DATA_REPO_PAT` sur le depot public
      (Settings > Secrets > Actions) **et** en variable d'environnement Netlify.
- [ ] 3. Creer le widget Turnstile sur dash.cloudflare.com pour le domaine du site.
      Poser la secret key en variable d'environnement Netlify
      `TURNSTILE_SECRET_KEY`, et remplacer la cle de test
      `1x00000000000000000000AA` dans `public/index.html` par la vraie site key.
- [ ] 4. Deployer (merge sur master + deploiement Netlify).
- [ ] 5. Supprimer `searches.json`, `pending_searches.json` et `seen.json` du depot
      public. Pour purger aussi l'historique : `git filter-repo --invert-paths
      --path searches.json --path pending_searches.json --path seen.json` puis
      force-push. Rappel : cela ne depublie pas retroactivement les adresses deja
      exposees.
- [ ] 6. Supprimer le secret `ALERT_EMAIL` du depot public.
- [ ] 7. Verifier de bout en bout : soumettre une recherche de test via le
      formulaire, confirmer l'email, verifier que l'entree apparait dans le depot
      prive avec son bloc `criteria`, resoumettre la meme chose et verifier le
      refus en 409, puis supprimer l'entree de test.

Les recherches `Brest` et `Rennes` cessent d'etre surveillees des l'etape 4
(deploiement), pas seulement a l'etape 5. La personne abonnee a `Brest` cesse de
recevoir ses alertes a partir de ce moment.
