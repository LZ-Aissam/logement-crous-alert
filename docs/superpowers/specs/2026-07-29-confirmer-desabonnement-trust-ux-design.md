# Confiance sur confirmer.html + confirmation en 2 etapes sur desabonnement.html

## Contexte

Suite à l'ajout du bandeau de confiance et de la section narrative sur
`index.html`, l'utilisateur veut le même type de réassurance sur
`confirmer.html`, et en plus une vraie étape de confirmation avant la
désinscription sur `desabonnement.html` (actuellement un seul clic déclenche
l'appel API sans confirmation intermédiaire).

## 1. `confirmer.html` — badges de confiance

Sous le `<p id="intro">` (ligne 40), avant le bouton `#confirm-button`
(ligne 47), insérer une ligne compacte de 3 badges (icône Bootstrap Icons +
texte court), en `d-flex flex-wrap gap-3` avec `small text-secondary` :

- `bi-shield-check` — Email jamais partagé
- `bi-lightning-charge` — Activation immédiate
- `bi-x-circle` — Désinscription possible à tout moment

Ces faits sont déjà vrais et documentés (`mentions-legales.html`, FAQ de
`index.html`). Aucun changement au script JS de la page.

## 2. `desabonnement.html` — confirmation en 2 étapes

Comportement actuel (`public/desabonnement.html:65-109`) : le bouton
`#unsubscribe-button` appelle directement `/.netlify/functions/unsubscribe`
au clic.

Nouveau comportement :

1. Le recap existant (`intro.textContent`, ligne 80) reste inchangé
   ("Se désinscrire de la recherche "X" pour l'adresse Y ?").
2. Un nouveau bloc HTML `#confirm-step`, caché par défaut (`d-none`), est
   ajouté après le bouton `#unsubscribe-button` : un encart bordé
   (`class="border rounded p-3 mt-3"`) contenant :
   - le recap reformaté en gras : `Recherche : <strong>X</strong>` /
     `Email : <strong>Y</strong>` (deux lignes ou un `<div>` par champ) ;
   - une phrase d'avertissement : "Tu ne recevras plus aucune alerte pour
     cette recherche." ;
   - un bouton `#confirm-unsubscribe-button` (`btn btn-danger`) : "Oui, me
     désabonner" ;
   - un lien/bouton `#cancel-unsubscribe-button` (`btn btn-link`) :
     "Annuler".
3. Le clic sur `#unsubscribe-button` ne fait plus l'appel API : il masque
   `#unsubscribe-button` et affiche `#confirm-step` (retire `d-none`).
4. Le clic sur `#cancel-unsubscribe-button` masque `#confirm-step` et
   réaffiche `#unsubscribe-button` (aucun appel réseau).
5. Le clic sur `#confirm-unsubscribe-button` déclenche exactement l'appel
   API existant (même fetch, même gestion d'erreur/succès qu'aujourd'hui),
   avec désactivation du bouton pendant l'appel comme c'est déjà le cas.
6. Si le lien est invalide (`!search || !email || !token`, ligne 75), le
   comportement actuel est inchangé : bouton désactivé, message d'erreur,
   `#confirm-step` n'apparaît jamais.

## Portée

- Fichiers modifiés : `public/confirmer.html`, `public/desabonnement.html`
  uniquement.
- Aucune modification des fonctions Netlify (`unsubscribe.js`,
  `confirm-email.js`) : le contrat API ne change pas.
- Aucune nouvelle dépendance.

## Vérification

- `python -m http.server 8765 --directory public`, tester
  `desabonnement.html?search=Test&email=test%40example.com&token=x` :
  cliquer "Se désinscrire" doit afficher l'encart de confirmation sans
  appel réseau (vérifiable via l'onglet réseau), "Annuler" doit le
  refermer, "Oui, me désabonner" doit déclencher l'appel existant (échoue
  proprement en local faute de vraie fonction Netlify, comportement déjà
  attendu).
- `pytest` et `npm test` doivent rester verts (aucun changement
  Python/JS backend).
