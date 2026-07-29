# Confiance + confirmation en 2 etapes — Plan

Spec : `docs/superpowers/specs/2026-07-29-confirmer-desabonnement-trust-ux-design.md`

## Tâche 1 — Badges de confiance sur `confirmer.html`

- Insérer une ligne `d-flex flex-wrap gap-3 small text-secondary mt-2` avec
  3 badges (icône + texte, contenu exact dans la spec) entre `<p id="intro">`
  (ligne 40) et le honeypot (ligne 42).
- Vérification : `python -m http.server 8765 --directory public`, ouvrir
  `/confirmer.html?code=x`, contrôler l'affichage des 3 badges.

## Tâche 2 — Confirmation en 2 étapes sur `desabonnement.html`

- Ajouter le bloc `#confirm-step` (`d-none` par défaut) après le bouton
  `#unsubscribe-button` (ligne 47), structure exacte dans la spec section 2
  (recap en gras, phrase d'avertissement, bouton `#confirm-unsubscribe-button`
  `btn btn-danger`, lien `#cancel-unsubscribe-button`).
- Modifier le script (lignes 65-109) :
  - le listener de `#unsubscribe-button` masque ce bouton et affiche
    `#confirm-step`, sans appel réseau ;
  - nouveau listener sur `#cancel-unsubscribe-button` : masque
    `#confirm-step`, réaffiche `#unsubscribe-button` ;
  - nouveau listener sur `#confirm-unsubscribe-button` : reprend l'appel
    fetch existant (même logique succès/erreur, même désactivation de
    bouton pendant l'appel).
  - cas lien invalide (ligne 75) inchangé.
- Vérification : même serveur local, ouvrir
  `/desabonnement.html?search=Test&email=test%40example.com&token=x` :
  "Se désinscrire" affiche l'encart sans requête réseau (onglet Réseau des
  DevTools), "Annuler" le referme, "Oui, me désabonner" déclenche l'appel
  existant.

## Tâche 3 — Non-régression

- `pytest` → 177 passed.
- `npm test` → 72 pass.

## Commit

- Un commit couvrant les deux fichiers : `git add public/confirmer.html
  public/desabonnement.html`, message `feat: confirmation en 2 etapes pour
  la desinscription + confiance sur confirmer.html`.
- Push sur `master` après validation visuelle.
