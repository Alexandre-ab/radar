# AGENTS.md — Radar

> Lu au démarrage par Claude Code (via CLAUDE.md), Codex (directement) et Antigravity (via GEMINI.md).
> Les humains le remplissent, les agents le lisent. Garde-le court : moins de 150 lignes.

## Le projet

- Objectif : RADAR, un outil de veille en ligne de commande (collect, score, search, decide, report)
  qui aide notre binôme à éclairer une décision technique pour le client Hivemind, avec des sources datées.
- Stack : Python 3.9 (bibliothèque standard) + PyYAML ; GitHub via `gh api` ; plan de veille dans
  `radar.config.yaml`, données dans `data/`, livrables `decision.md` et `rapport.md`.
- Lancer en local : `./radar collect`, puis `./radar score`, `./radar search <mot>`, `./radar decide`,
  `./radar report` (Windows : `.\radar …`).
- Tester : `python3 -m unittest discover -s tests -v` (aucun appel réseau) ; revue : `./revue`.

## Conventions

- Python 3.9 + PyYAML, aucune autre dépendance sans demander.
- Rien en dur dans `radar.py` : sources, mots-clés, règles, décision et rapport viennent de
  `radar.config.yaml` (vérifié par `TestRienEnDurDansRadarPy`).
- Aucun lien inventé : chaque url d'un livrable vient de `data/items.json` ou de la rubrique `decision`.
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

## Revue (quand on vous demande « fais la revue »)

Lancée par l'humain, ou par `./revue` (Codex en lecture seule, verdict dans `revues/`).

1. Lisez la passation la plus récente de `radar/passations/` écrite par un AUTRE agent que vous
   (l'agent est dans le titre), ou celle qu'on vous nomme, puis `radar/decisions`.
2. Relisez : `git status`, `git diff`, `git diff --cached`, `git log -3 --oneline`,
   et les fichiers non suivis cités par la passation.
3. Vérifiez, sans rien modifier :
   - syntaxe (n'écrit aucun cache) :
     `python3 -c "import ast,sys; [ast.parse(open(f,encoding='utf-8').read(),f) for f in sys.argv[1:]]" radar.py tests/*.py`
   - tests : `python3 -m unittest discover -s tests -v`. Lancé par `./revue` : ne les relancez pas
     (le bac à sable read-only interdit les dossiers temporaires), lisez le fichier `revues/…-tests.txt` indiqué ;
   - données : `python3 -m json.tool data/items.json > /dev/null`, et `git diff --stat -- data/items.json`
     doit être vide, sauf si la passation dit qu'une collecte a été lancée ;
   - rien en dur : aucune source ni aucun mot-clé de `radar.config.yaml` écrit dans `radar.py` ;
   - chaque point de la rubrique « Fait » de la passation est vrai.
4. Interdit pendant une revue : modifier un fichier du dépôt, lancer `./radar collect`, committer, pousser.
5. Répondez dans cet ordre :
   - **première ligne exactement** `VERDICT : COMMIT OK` ou `VERDICT : COMMIT NON` ;
   - les problèmes, du plus grave au moins grave, avec `fichier:ligne` ;
   - les cas que les tests ne couvrent pas ;
   - les actions pour l'agent suivant.
6. Écrivez votre passation, avec `revue` dans le titre.

## Équipe (qui fait quoi)

Antigravity dirige, Claude Code code, Codex teste. Le chef envoie ses consignes par Herdr :
elles commencent par « Tâche du chef ».

- **Antigravity (`agy`), le chef** : découpe le travail, donne les tâches, vérifie, rend compte
  à l'humain. Il ne modifie aucun fichier.
- **Claude Code, le codeur** (nom Herdr : `codeur`) : écrit le code (`radar.py`, `radar`,
  `radar.config.yaml`, `decision.md`). Il ne modifie pas `tests/`.
- **Codex, le testeur** (nom Herdr : `testeur`) : écrit et lance les tests, dans `tests/` uniquement.
  Il ne corrige jamais le code de l'application : il signale le bug au chef.
- Un seul agent modifie les fichiers à la fois.
- Personne ne committe ni ne pousse sans l'accord de l'humain (le hook pre-commit relance les tests).
- Quand vous répondez au chef, terminez par un bloc **RÉSUMÉ** : fichiers touchés, résultat, questions.
- Commande de test : `python3 -m unittest discover -s tests -v`.
