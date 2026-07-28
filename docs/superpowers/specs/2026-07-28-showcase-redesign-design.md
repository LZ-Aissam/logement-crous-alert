# Refonte "page vitrine" des pages publiques — Design

## Contexte

Les 3 pages publiques (`public/index.html`, `public/confirmer.html`,
`public/desabonnement.html`) sont aujourd'hui des formulaires bruts sans style — un
`<h1>`, un formulaire, rien pour expliquer à un visiteur qui découvre le site ce que
c'est, pourquoi ça existe, et pourquoi il devrait s'en servir. Ce document habille ces
trois pages avec une identité visuelle distinctive et, pour `index.html`, une vraie
page vitrine (hero, problème, solution, formulaire) avec des illustrations de
personnages.

## Direction visuelle

**Concept : le tampon d'urgence.** L'administration française tamponne tout
(dossiers, avis, constats) — ce site existe parce que cette administration est lente
alors qu'un logement CROUS peut disparaître en quelques minutes. Le fil visuel
détourne l'esthétique du tampon/avis officiel pour signaler l'urgence : un badge rond
légèrement penché ("URGENT" / une horloge), réutilisé comme signature du site (hero,
section formulaire, messages de succès).

**Palette** (extraite du vrai thème CSS de crous-rennes.fr, `:root` de
`wp-content/themes/crous/style.css` — ce sont les couleurs officielles CROUS, pas des
couleurs inventées) :

```css
--color-red: #e01020;        /* rouge CROUS — CTA, tampon d'urgence, accents forts */
--color-orange: #ff732c;     /* orange secondaire — petits badges */
--color-greenwater: #34c4b5; /* teal clair — fonds/illustrations section solution */
--front-greenwater: #006a6f; /* teal foncé — texte/CTA sur fond clair, section solution */
--color-grey: #e8e8e8;       /* gris clair — filets et bordures façon formulaire */
--ink: #16191b;              /* quasi-noir — texte */
--paper: #ffffff;            /* fond blanc, comme le vrai site CROUS */
```

**Typographie** : le vrai site CROUS utilise "Marianne" (police officielle de l'État
français), non disponible facilement sans l'auto-héberger — remplacée par une police
d'affichage chargée depuis Google Fonts pour les gros titres (**Archivo Black**,
condensée et massive, façon avis administratif placardé), et une pile système
(`system-ui, sans-serif`) pour le corps de texte (pas de dépendance externe
supplémentaire, cohérent avec le reste du site). C'est la seule ressource externe
chargée par ces pages.

**Personnages** : formes géométriques plates (têtes en cercle, corps en rectangles
arrondis) dans la palette ci-dessus — un·e étudiant·e stressé·e penché·e sur son
téléphone (hero), un·e étudiant·e soulagé·e avec des clés (section solution). SVG
dessiné à la main, fichiers séparés référencés en `<img>` (pas de duplication du SVG
dans chaque page, pas de librairie d'icônes externe).

**Mouvement** : minimal et déliberé — une légère animation d'entrée du tampon (rotation
+ échelle qui se stabilise) au chargement du hero, un `transform` léger au survol du
bouton principal. Respecte `prefers-reduced-motion`. Pas d'animations au scroll
(`IntersectionObserver`) : la page reste courte, ce n'est pas nécessaire.

## Structure de fichiers

```
public/
  styles.css                        # nouveau — tokens partagés + composants communs
  illustrations/
    etudiant-stresse.svg            # nouveau — personnage hero
    etudiant-soulage.svg            # nouveau — personnage section solution
  index.html                        # refonte complète (vitrine + formulaire existant)
  confirmer.html                    # restylé (identité visuelle, structure inchangée)
  desabonnement.html                # restylé (identité visuelle, structure inchangée)
```

`styles.css` est chargé par les 3 pages via `<link rel="stylesheet" href="/styles.css">`
— évite de dupliquer les tokens/composants trois fois, reste 100% statique (pas de
build, juste un fichier CSS de plus servi par Netlify comme les autres).

**Aucun changement de logique JavaScript** : le comportement de soumission des
formulaires (fetch vers les fonctions Netlify, gestion honeypot, messages
succès/erreur) reste identique sur les 3 pages — seul l'habillage visuel et, pour
`index.html`, le contenu autour du formulaire, changent.

## `public/index.html` — structure de contenu

### 1. Hero

- Badge tampon (pivoté ~-8°) : "URGENT" avec une petite icône horloge
- Titre (Archivo Black) : "Les logements CROUS disparaissent en quelques minutes."
- Sous-titre : "Toi, tu ne peux pas rafraîchir la page toute la journée. Ce robot le
  fait pour toi, gratuitement, et t'alerte par email dès qu'un logement correspond à
  ta recherche."
- Bouton : "Créer mon alerte" → ancre `#formulaire`, scroll fluide
- Illustration : étudiant·e stressé·e avec téléphone

### 2. Le constat

Encadré façon "constat administratif" (filets fins, libellé façon numéro de dossier) :

> Sur trouverunlogement.lescrous.fr, les nouvelles disponibilités partent presque
> instantanément. Le temps de te connecter, de chercher, de comparer — c'est déjà
> trop tard. Il faudrait surveiller le site en permanence, ce que personne n'a le
> temps de faire.

### 3. Comment ça marche

Étapes numérotées (1/2/3 — légitime ici, c'est une vraie séquence temporelle) :

1. **Tu crées ta recherche** — ville, mots-clés optionnels, email
2. **Le robot vérifie toutes les 5 minutes** — gratuitement, 24h/24, sans que tu aies
   rien à faire
3. **Tu reçois une alerte email** dès qu'un logement correspond — tu n'as plus qu'à
   foncer le réserver

Illustration : étudiant·e soulagé·e avec des clés.

### 4. Pourquoi lui faire confiance (bref, pas une section à part entière)

Liste courte de réassurance, intégrée juste avant le formulaire : gratuit, pas besoin
de compte GitHub, confirmation email obligatoire (anti-abus), code source ouvert.

### 5. Formulaire (ancre `#formulaire`)

Le formulaire existant (`name`, `city`, `keywords`, `emails`, honeypot, bouton), avec
les mêmes champs/comportement, juste restylé pour matcher l'identité (labels,
`input`/`button`, encadré résultat).

## `public/confirmer.html` et `public/desabonnement.html`

Traitement plus léger, cohérent mais pas narratif — ce sont des pages d'action
ponctuelle, pas des pages qu'on visite pour se convaincre :

- Même palette/typo/`styles.css`
- Petit badge tampon en accent près du titre (pas de grande illustration de
  personnage)
- Carte centrée, filets fins façon formulaire administratif
- Structure/logique JS inchangée

## Accessibilité et responsive

- Contraste texte/fond vérifié pour chaque paire de couleurs utilisée (le rouge CROUS
  `#e01020` et le teal foncé `#006a6f` sur blanc passent WCAG AA pour le texte ; le
  teal clair `#34c4b5` est réservé aux fonds/illustrations, jamais utilisé comme
  couleur de texte sur blanc).
- Focus clavier visible sur tous les éléments interactifs (formulaire, bouton hero).
- `prefers-reduced-motion: reduce` désactive l'animation d'entrée du tampon.
- Responsive jusqu'à 320px de large : le hero passe illustration/texte en colonne
  unique sous ~700px.

## Hors scope (assumé)

- Pas de framework CSS (Tailwind/Bootstrap) — CSS écrit à la main, cohérent avec le
  reste du site (pas de build, pas de dépendance supplémentaire lourde).
- Pas de réplique exacte de la police "Marianne" (nécessiterait l'auto-héberger) —
  substitution par une police d'affichage Google Fonts pour les titres uniquement.
- Pas de dark mode — hors scope, non demandé.
- Pas de nouvelles animations au scroll — la page reste courte et lisible sans.
- Pas de tests automatisés pour ces pages statiques — aucun test n'existe déjà pour
  `public/*.html` dans ce projet ; la vérification se fait par capture d'écran
  navigateur à plusieurs largeurs, comme pour les pages existantes.

## Vérification

Pas de suite de tests à écrire (convention existante du projet pour les pages
statiques). Vérification manuelle via capture d'écran navigateur : desktop (~1280px),
tablette (~768px), mobile (~375px), pour les 3 pages, plus vérification que le
formulaire fonctionne toujours (soumission réelle, comme lors des vérifications
précédentes du projet).
