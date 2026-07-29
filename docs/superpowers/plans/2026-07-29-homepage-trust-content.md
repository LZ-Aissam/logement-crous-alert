# Contenu de confiance sur la page d'accueil — Plan

Spec : `docs/superpowers/specs/2026-07-29-homepage-trust-content-design.md`

Fichier concerné : `public/index.html` uniquement.

## Tâche 1 — Bandeau de confiance

- Supprimer le bloc existant `<section class="py-4">` à 2 items
  (`index.html:199-216`).
- Insérer un nouveau bandeau de 4 items juste après `</header>` (ligne 142)
  et avant `<section class="py-4">` "Le constat" (ligne 149) : grille
  `row g-4`, 4 colonnes `col-6 col-md-3`, icône Bootstrap Icons + titre
  gras + sous-ligne, contenu exact listé dans la spec (tableau des 4
  items : `bi-gift`/100% gratuit, `bi-shield-check`/Email protégé,
  `bi-clock-history`/Vérifié 24h/24, `bi-x-circle`/Désinscription en 1
  clic).
- Vérification : `python -m http.server 8765 --directory public`, ouvrir
  `/index.html`, contrôler que le bandeau s'affiche entre le hero et "Le
  constat", en desktop et en largeur mobile (redimensionner la fenêtre).

## Tâche 2 — Section "Pourquoi ce site existe"

- Insérer une nouvelle `<section>` juste avant la section FAQ
  (avant la ligne 353 actuelle), style cohérent avec les sections
  voisines (`section-eyebrow` + `h2` + paragraphe, pas de nouvelle
  classe CSS).
- Texte exact = citation validée dans la spec, section 2.
- Vérification : même serveur local, contrôler visuellement l'insertion
  entre la dernière section de contenu et la FAQ.

## Tâche 3 — Non-régression

- `pytest` → doit rester à 177 passed.
- `npm test` → doit rester à 72 pass.
- Revalidation visuelle rapide des 4 autres pages HTML (nav/footer
  inchangés, donc pas de régression attendue, simple contrôle).

## Commit

- Un seul commit couvrant les deux tâches (même fichier, changement
  cohérent) : `git add public/index.html` puis message `feat: ajouter
  bandeau de confiance et section "pourquoi ce site existe"`.
- Push sur `master` après validation visuelle.
