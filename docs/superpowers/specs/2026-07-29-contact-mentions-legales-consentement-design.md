# Page Contact, Mentions légales et case de consentement — Design

## Contexte

Le site public (`public/`, servi statiquement par Netlify) n'a ni page de contact,
ni mentions légales, ni case de consentement explicite dans le formulaire
d'inscription. Le formulaire n'affiche qu'une phrase d'aide ("Tu recevras un email
de confirmation à valider avant les alertes.").

L'utilisateur a demandé d'ajouter ces trois éléments, en s'inspirant de la
structure d'un autre site (`logementcrous.basatechno.fr`) — un projet Next.js sans
rapport avec ce dépôt (aucune trace de son code ici), utilisé uniquement comme
référence d'inspiration, pas comme source à répliquer techniquement.

## Périmètre

- Deux nouvelles pages statiques : `public/contact.html`, `public/mentions-legales.html`.
- Un footer commun (liens Contact / Mentions légales) ajouté aux 5 pages du site
  (`index.html`, `confirmer.html`, `desabonnement.html`, `contact.html`,
  `mentions-legales.html`) — aujourd'hui seul `index.html` a un footer.
- Une case à cocher de consentement, obligatoire, ajoutée au formulaire
  d'inscription dans `index.html`.

Hors périmètre : aucun changement backend (Netlify functions, scripts Python).
La case de consentement est une validation front-end uniquement — la preuve de
consentement réelle reste le double opt-in par email déjà en place.

## Pages

### `public/contact.html`

Même gabarit que `confirmer.html`/`desabonnement.html` : nav avec lien retour vers
`index.html`, `<main>` avec une card centrée.

Contenu : un titre, une phrase d'intro, et un bouton `mailto:logementcrousalert@gmail.com`.
Pas de formulaire, pas de JS.

### `public/mentions-legales.html`

Même gabarit. Contenu, en sections :

- **Éditeur** — projet indépendant et non commercial, non affilié au CROUS ;
  contact `logementcrousalert@gmail.com` ; code source public sur GitHub
  (`LZ-Aissam/logement-crous-alert`).
- **Hébergement** — Netlify, Inc. (site et fonctions), GitHub, Inc. (exécution des
  vérifications automatisées via GitHub Actions).
- **Données personnelles** — seule donnée collectée : l'adresse email fournie
  volontairement à l'inscription ; double opt-in (email de confirmation à
  valider) ; désinscription en un clic depuis chaque email d'alerte ; pas de
  revente ni de partage à des tiers.
- **Cookies et traceurs** — aucun cookie de mesure d'audience ; Cloudflare
  Turnstile (anti-robot) et Google Fonts sont chargés depuis des services tiers
  lors de la visite.

Reste volontairement pseudonyme : pas de nom réel ni d'adresse postale, cohérent
avec un projet personnel non commercial.

## Footer commun

Le footer actuel d'`index.html` :

```html
<footer class="py-4 text-center text-secondary small">
  <div class="container">Alerte Logement CROUS, projet indépendant non affilié au CROUS.</div>
</footer>
```

devient, sur les 5 pages :

```html
<footer class="py-4 text-center text-secondary small">
  <div class="container">
    Alerte Logement CROUS, projet indépendant non affilié au CROUS.
    <div class="mt-1">
      <a href="contact.html" class="text-secondary">Contact</a>
      <span class="mx-2">·</span>
      <a href="mentions-legales.html" class="text-secondary">Mentions légales</a>
    </div>
  </div>
</footer>
```

`confirmer.html` et `desabonnement.html` n'ont actuellement aucun footer ; il est
ajouté pour la cohérence de navigation.

## Case de consentement (`index.html`)

Ajoutée dans le formulaire, juste avant le widget Turnstile, en `form-check` requis :

```html
<div class="mb-3">
  <div class="form-check">
    <input class="form-check-input" type="checkbox" id="consent" name="consent" required>
    <label class="form-check-label" for="consent">
      J'accepte de recevoir les alertes logement par email à l'adresse indiquée
      ci-dessus, conformément aux <a href="mentions-legales.html" target="_blank">mentions légales</a>.
    </label>
  </div>
</div>
```

`required` s'appuie sur la validation HTML5 déjà en place côté client
(`form.checkValidity()` / `form.reportValidity()` dans le gestionnaire `submit`,
voir `public/index.html` lignes ~364-369). Aucune valeur n'est ajoutée au
`payload` envoyé à `/.netlify/functions/create-search` : cette case ne fait que
bloquer la soumission tant qu'elle n'est pas cochée, elle n'est pas une donnée
métier.

## Tests

Pas de nouveaux tests automatisés : ce sont des pages statiques sans logique, et
la case à cocher réutilise un mécanisme de validation déjà couvert
implicitement (même pattern que les champs `required` existants, jamais testé
unitairement côté JS front — cohérent avec l'existant).

Vérification manuelle prévue après implémentation : servir `public/` localement
(`python -m http.server 8765 --directory public`) et vérifier à l'œil que :
- les liens Contact / Mentions légales fonctionnent depuis les 5 pages,
- le bouton mailto s'ouvre correctement,
- la case à cocher bloque bien la soumission du formulaire tant qu'elle n'est
  pas cochée (message de validation HTML5 natif).
