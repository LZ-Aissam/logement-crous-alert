# Checklist de migration

Etapes d'exploitation, a faire dans l'ordre. A partir de l'etape 4 (deploiement),
le robot lit les donnees depuis le depot prive : toute recherche non recreee la-bas
(y compris Brest et Rennes) cesse d'etre surveillee des ce moment, pas seulement
apres la suppression des anciens fichiers a l'etape 5.

- [x] 1. Creer le depot prive `LZ-Aissam/logement-crous-alert-data` avec trois
      fichiers : `searches.json` contenant `[]`, `pending_searches.json` et
      `seen.json` contenant `{}`. Fait le 2026-07-29.
- [x] 2. Creer un PAT fine-grained limite a ce seul depot, permission
      Contents read/write. Le poser en secret `DATA_REPO_PAT` sur le depot public
      (Settings > Secrets > Actions) **et** en variable d'environnement Netlify.
      Fait le 2026-07-29, acces verifie (lecture de `searches.json` via l'API
      GitHub avec le PAT, HTTP 200).
- [x] 3. Creer le widget Turnstile sur dash.cloudflare.com pour le domaine du site.
      Poser la secret key en variable d'environnement Netlify
      `TURNSTILE_SECRET_KEY`, et remplacer la cle de test
      `1x00000000000000000000AA` dans `public/index.html` par la vraie site key.
      Fait le 2026-07-29. **Piege rencontre** : le widget avait ete cree avec le
      hostname `logementcrousalert.netlify.app` (sans tirets) alors que le vrai
      site est `logement-crous-alert.netlify.app` (avec tirets) -> erreur
      Turnstile 110200 "domaine non autorise" ("Impossible de se connecter au
      site web" cote utilisateur). Corrige en editant le hostname du widget sur
      dash.cloudflare.com.
- [x] 4. Deployer (merge sur master + deploiement Netlify). Fait le 2026-07-29
      (`c2cd758`, puis push).
- [x] 5. Supprimer `searches.json`, `pending_searches.json` et `seen.json` du depot
      public. Pour purger aussi l'historique : `git filter-repo --invert-paths
      --path searches.json --path pending_searches.json --path seen.json` puis
      force-push. Rappel : cela ne depublie pas retroactivement les adresses deja
      exposees. Fait le 2026-07-29 (fichiers supprimes + historique purge et
      force-push, `ce1f278` -> `a309e6a` apres filter-repo).
- [x] 6. Supprimer le secret `ALERT_EMAIL` du depot public. Fait le 2026-07-29.
- [ ] 7. Verifier de bout en bout : soumettre une recherche de test via le
      formulaire, confirmer l'email, verifier que l'entree apparait dans le depot
      prive avec son bloc `criteria`, resoumettre la meme chose et verifier le
      refus en 409, puis supprimer l'entree de test. **Pas encore fait** : le
      widget Turnstile bloquait la soumission (voir etape 3) ; l'utilisateur a
      confirme le 2026-07-29 que ca fonctionne maintenant apres la correction du
      hostname, mais le cycle complet (soumission -> confirmation email ->
      verification dans le depot prive -> test du 409 -> suppression) n'a pas
      encore ete execute.

Les recherches `Brest` et `Rennes` cessent d'etre surveillees des l'etape 4
(deploiement), pas seulement a l'etape 5. La personne abonnee a `Brest` cesse de
recevoir ses alertes a partir de ce moment.
