# AGENTS.md — Radar

> Lu au démarrage par Claude Code (via CLAUDE.md), Codex (directement) et Antigravity (via GEMINI.md).
> Les humains le remplissent, les agents le lisent. Garde-le court : moins de 150 lignes.

## Le projet

- Objectif : <une phrase : ce que fait le projet, pour qui>
- Stack : <ex. Node 22, Express, SQLite>
- Lancer en local : `<ex. npm run dev>`
- Tester : `<ex. npm test>`

## Conventions

- <ex. JavaScript moderne, modules ES, pas de dépendance sans demander>
- Commits courts, en français, un sujet par commit.
- Jamais de secret dans le code ni dans les commits (.env, clés API, tokens).

## Mémoire partagée entre agents (obligatoire)

Plusieurs agents travaillent sur ce projet (Claude Code, Codex, Antigravity), souvent en parallèle,
chacun dans son propre worktree Git. Vous ne vous souvenez de rien d'une session à l'autre :
la mémoire commune est dans l'outil MCP **basic-memory**.

Toutes les notes de ce projet vont dans le dossier **`radar/`** de basic-memory, et nulle part ailleurs.

### Au démarrage de chaque tâche

1. Cherchez dans basic-memory les notes du dossier `radar/passations/` et lisez les 3 plus récentes.
2. Lisez la note `radar/decisions` si elle existe.
3. Si une passation concerne votre tâche, reprenez exactement là où elle s'arrête.
   Dites à l'humain, en une ligne, ce que vous avez repris et de quelle passation.

### Pendant la tâche

- Une décision qui engage la suite (choix d'une bibliothèque, format de données, contrainte découverte) :
  ajoutez-la à la note `radar/decisions` avec la date, la décision et la raison.
- Ne recopiez pas de code dans la mémoire : citez les chemins de fichiers.

### À la fin de chaque tâche, ou avant de vous arrêter

Écrivez une note de passation dans `radar/passations/`,
avec pour titre `AAAA-MM-JJ-HHMM-<agent>-<tâche-en-3-mots>`, et ces rubriques :

- **Besoin** : ce que l'humain a demandé, avec ses mots.
- **Fait** : ce qui marche maintenant, et comment vous l'avez vérifié.
- **Reste à faire** : les prochaines étapes, dans l'ordre.
- **Pour qui** : l'agent conseillé pour la suite (Claude, Codex, Antigravity) ou « n'importe lequel ».
- **Fichiers touchés** : les chemins.
- **Pièges** : ce qui a coincé, ce qu'il ne faut pas refaire.
- **Branche / worktree** : le nom de la branche.

### Règles

- Jamais de secret (mot de passe, clé, token) dans la mémoire.
- Si une note contredit le code, le code a raison : corrigez la note.
- Une information stable, valable pour tout le projet : proposez à l'humain de l'ajouter
  à ce fichier AGENTS.md plutôt que de la laisser en mémoire.
