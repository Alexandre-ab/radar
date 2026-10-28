# RADAR — Veille technique & aide à la décision (Hivemind)

**Binôme : Alexandre & Mohamed**

RADAR est un outil en ligne de commande qui automatise une veille technique pour notre client **Hivemind**, de la collecte des informations jusqu'à la décision. Il collecte des infos datées depuis 8 sources gratuites, les note avec un barème explicable, les archive avec des étiquettes, compare deux options techniques avec de vrais chiffres GitHub, puis rédige un rapport de 2 pages dont chaque lien vient de nos données.

Question tranchée : **la mémoire d'Hivemind reste-t-elle en fichiers `.md`, ou passe-t-on à SQLite ?**

---

## Accès direct aux livrables évalués

| Livrable | Contenu |
| --- | --- |
| [`radar.config.yaml`](./radar.config.yaml) | Le plan de veille : 3 axes, mots-clés, 8 sources, barème de score, étiquettes, seuil, décision et textes du rapport. Tout ce que RADAR surveille est écrit ici, nulle part ailleurs. |
| [`data/items.json`](./data/items.json) | L'archive : **72 fiches**, **35 retenues**, **37 écartées**, 0 champ `null`. Chaque fiche a les 9 champs de la fiche du kit. |
| [`decision.md`](./decision.md) | Question A : garder les `.md` **69/80 — 86 %** contre SQLite (`better-sqlite3`) **60/80 — 75 %**, sur 7 critères pondérés, chaque note avec son chiffre, sa source et sa date. |
| [`rapport.md`](./rapport.md) | Le rapport de 2 pages : synthèse de veille (3 tendances, dont 1 sur la data et 1 écartée) et note de recommandation. 20 liens, tous vérifiés en HTTP 200 le 2026-10-28. |

---

## Prérequis et installation

- **Python 3.9 ou plus**, avec la bibliothèque standard et **PyYAML** :

  ```bash
  python3 -m pip install pyyaml
  ```

- **GitHub CLI connecté** à un compte (utilisé par `collect` et `decide`) :

  ```bash
  gh auth status
  ```

  Avec `gh api`, GitHub autorise 5 000 requêtes par heure ; sans connexion, seulement 60.

- Un accès Internet pour `collect`, `decide` et `report --verifier-liens`. Les autres commandes et les tests fonctionnent hors ligne.

---

## Reproduire l'évaluation

Depuis le dossier du dépôt, sur Mac ou Linux : `./radar <commande>`. Sous Windows : `.\radar <commande>` (lanceur [`radar.cmd`](./radar.cmd)).

1. **Collecter** les infos des 8 sources dans `data/items.json` :

   ```bash
   ./radar collect
   ```

   4 connecteurs : versions GitHub via `gh api`, recherche Hacker News (API Algolia), failles npm via l'API OSV, et une page web sans flux RSS (la Usage Policy d'Anthropic) suivie par son empreinte `SHA-256`, rangée dans [`data/pages.json`](./data/pages.json). Une info n'est gardée que si elle a une url, une date de publication réelle et un mot-clé de la config. Une source en panne n'arrête pas les autres.

2. **Noter et trier** chaque info, puis afficher le classement :

   ```bash
   ./radar score
   ./radar score --top 15
   ```

   Barème déterministe et explicable de **10 règles**, toutes écrites dans la config : les 6 du kit (catégorie de la source, fraîcheur, auteur identifié, source ou méthode citée, recoupement, biais d'intérêt) et 4 règles ajoutées (effet de mode, contenu généré, comparatif d'éditeur, version de test). Chaque point est affiché avec sa raison. Une info est `retenue` si sa note atteint le **seuil de 4**, sinon `ecartee`. La commande pose aussi les **7 étiquettes**.

3. **Rechercher** dans l'archive, sans rien écrire sur le disque :

   ```bash
   ./radar search sqlite --retenues
   ./radar search securite --retenues
   ./radar search cgu-ia
   ```

   Recherche dans le titre et les étiquettes, sans tenir compte des majuscules, triée par fiabilité puis par date.

4. **Décider** entre les 2 options et écrire `decision.md` :

   ```bash
   ./radar decide
   ```

   Chiffres bruts relevés en direct avec `gh api` (date de création, versions, contributeurs, commits sur 90 jours, licence), puis matrice pondérée sur les 7 critères du kit. La licence est éliminatoire : une note de 1 élimine l'option.

5. **Rédiger le rapport** `rapport.md` :

   ```bash
   ./radar report
   ./radar report --verifier-liens
   ```

   Triple garde-fou contre les liens inventés : chaque url d'une tendance doit exister dans `data/items.json` ; avant d'écrire, toutes les urls du texte sont comparées aux urls autorisées ; avec `--verifier-liens`, chaque lien est ouvert et le rapport n'est pas écrit si l'un d'eux ne répond pas.

`collect` et `score` mettent à jour `data/items.json`. Pour revenir à l'état évalué : `git checkout -- data/items.json decision.md`.

---

## Tests unitaires

**215 tests**, sans aucun appel réseau, dans [`tests/`](./tests/) :

```bash
python3 -m unittest discover -s tests -v
```

- **Rien n'est écrit en dur** : `TestRienEnDurDansRadarPy` lit toutes les valeurs métier de `radar.config.yaml` (mots-clés, sources, décision, rapport) et vérifie qu'aucune n'apparaît dans [`radar.py`](./radar.py), même dans un commentaire ou un message d'aide.
- **Les vrais fichiers sont protégés** : les tests travaillent dans un dossier temporaire, simulent GitHub et les API, et vérifient à la fin que `data/items.json`, `data/pages.json`, `radar.config.yaml`, `decision.md` et `rapport.md` n'ont pas changé.
- **Chaque règle est couverte** : fiche valide (9 champs, url, dates), filtres, barème, étiquettes et statut, recherche, totaux de la matrice et critère éliminatoire, et refus de toute url absente de nos données dans le rapport.

Un hook git ([`.githooks/pre-commit`](./.githooks/pre-commit)) relance les tests avant chaque commit et le refuse si un test échoue (activation : `git config core.hooksPath .githooks`).

---

## Les 6 briques du référentiel

| Brique | Exigences couvertes | Fichiers |
| --- | --- | --- |
| **1 · Plan de veille** | 3 axes, mots-clés et mots ignorés, 8 sources de 4 types, 3 types de veille (technologique, sécurité, réglementaire), fréquence et livrable | [`radar.config.yaml`](./radar.config.yaml) |
| **2 · Collecte** | `radar collect`, fiche à 9 champs, jamais d'info sans url ni date de publication, déduplication par url, aucune source en dur | [`radar.py`](./radar.py), [`data/items.json`](./data/items.json), [`data/pages.json`](./data/pages.json) |
| **3 · Tri** | `radar score`, catégorie de chaque source, barème du kit + 4 règles ajoutées, top classé avec le détail des points | [`radar.config.yaml`](./radar.config.yaml) (`regles_score`), [`data/items.json`](./data/items.json) |
| **4 · Archive** | `type_veille`, 7 étiquettes issues de la config, statut `retenue` / `ecartee` selon le seuil, `radar search <mot>` | [`radar.config.yaml`](./radar.config.yaml) (`etiquettes`, `seuil`), [`data/items.json`](./data/items.json) |
| **5 · Décision** | `radar decide`, chiffres `gh api` en direct, 7 critères, poids de 1 à 3, notes de 1 à 5 avec chiffre et url datée, total pondéré, impact | [`decision.md`](./decision.md), [`radar.config.yaml`](./radar.config.yaml) (`decision`) |
| **6 · Rapport** | `radar report`, 2 pages au format du kit, 3 tendances dont 1 sur la data, urls issues de `data/items.json` uniquement, 20/20 liens en HTTP 200 | [`rapport.md`](./rapport.md), [`radar.config.yaml`](./radar.config.yaml) (`rapport`) |

---

## Décision et recommandation au client

**Contexte** : Hivemind reste local, 0 € d'abonnement en plus, 1 seul développeur, prochaine livraison dans 2 sprints.

| Option | Total pondéré |
| --- | --- |
| Garder les fichiers `.md` (statu quo) | **69 / 80 (86 %)** |
| Passer à SQLite local (`better-sqlite3`) | 60 / 80 (75 %) |

> **Nous recommandons de garder la mémoire d'Hivemind en fichiers .md pour les 2 prochains sprints, et de ne passer à SQLite que si la recherche dans ces fichiers devient trop lente.**

- **Plan B** : basculer vers SQLite si une recherche dans la mémoire dépasse **1 seconde**, ou au-delà de **10 000 fichiers** `.md`.
- **Prochaine étape** : le **2026-11-04**, mesurer le temps de recherche dans la mémoire actuelle et valider ce seuil avec le client.

Le détail des notes et de leurs sources est dans [`decision.md`](./decision.md), l'argumentaire complet dans [`rapport.md`](./rapport.md).

---

## Structure du dépôt

```text
radar/
├── radar                   lanceur Mac / Linux  (./radar collect)
├── radar.cmd               lanceur Windows      (.\radar collect)
├── radar.py                le moteur : les 5 commandes (Python 3.9 + PyYAML)
├── radar.config.yaml       le plan de veille, le barème, la décision et les textes du rapport
├── data/
│   ├── items.json          l'archive des 72 fiches
│   └── pages.json          l'empreinte SHA-256 de la page suivie sans flux RSS
├── decision.md             livrable de la brique 5 (écrit par ./radar decide)
├── rapport.md              livrable de la brique 6 (écrit par ./radar report)
├── tests/                  215 tests : collect, score, search, decide, report
├── .githooks/pre-commit    relance les tests avant chaque commit
└── RADAR_kit-de-depart.md  le kit et le format attendu
```
