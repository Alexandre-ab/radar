# Décision · A · La mémoire d'Hivemind reste-t-elle en fichiers .md, ou passe-t-on à SQLite ?

_Écrit par « radar decide » le 2026-10-28 à partir de radar.config.yaml (rubrique « decision ») et de data/items.json ; chiffres bruts relevés en direct avec gh api. Ce fichier est réécrit à chaque lancement : modifiez la config, pas ce fichier._

## 1. La question et le contexte

A · La mémoire d'Hivemind reste-t-elle en fichiers .md, ou passe-t-on à SQLite ?

Hivemind garde aujourd'hui sa mémoire dans des fichiers .md. L'alternative étudiée est une base SQLite locale, via la bibliothèque better-sqlite3.

Besoins du client (ils fixent nos poids) :

- Hivemind reste local
- 0 € d'abonnement en plus
- 1 seul développeur
- prochaine livraison dans 2 sprints

## 2. Les options comparées

| | Option | Dépôt GitHub |
|---|---|---|
| 1 | Garder les fichiers .md (statu quo) | [Alexandre-ab/radar](https://github.com/Alexandre-ab/radar) |
| 2 | Passer à SQLite local (better-sqlite3) | [WiseLibs/better-sqlite3](https://github.com/WiseLibs/better-sqlite3) |

## 3. Ce que dit la veille

23 info(s) de items.json touchent la question (10 retenue(s)), les 15 plus fiables :

| Fiabilité | Statut | Publiée le | Info | Source |
|---|---|---|---|---|
| 6 | retenue | 2026-08-05 | [better-sqlite3 v13.0.3](https://github.com/WiseLibs/better-sqlite3/releases/tag/v13.0.3) | Dépôt GitHub officiel |
| 6 | retenue | 2026-07-29 | [better-sqlite3 v13.0.2](https://github.com/WiseLibs/better-sqlite3/releases/tag/v13.0.2) | Dépôt GitHub officiel |
| 6 | retenue | 2026-07-21 | [better-sqlite3 v13.0.1](https://github.com/WiseLibs/better-sqlite3/releases/tag/v13.0.1) | Dépôt GitHub officiel |
| 6 | retenue | 2026-07-21 | [better-sqlite3 v13.0.0](https://github.com/WiseLibs/better-sqlite3/releases/tag/v13.0.0) | Dépôt GitHub officiel |
| 6 | retenue | 2026-07-15 | [better-sqlite3 v12.12.0](https://github.com/WiseLibs/better-sqlite3/releases/tag/v12.12.0) | Dépôt GitHub officiel |
| 6 | retenue | 2026-07-03 | [better-sqlite3 v12.11.2](https://github.com/WiseLibs/better-sqlite3/releases/tag/v12.11.2) | Dépôt GitHub officiel |
| 6 | retenue | 2026-06-15 | [better-sqlite3 v12.11.1](https://github.com/WiseLibs/better-sqlite3/releases/tag/v12.11.1) | Dépôt GitHub officiel |
| 6 | retenue | 2026-06-14 | [better-sqlite3 v12.11.0](https://github.com/WiseLibs/better-sqlite3/releases/tag/v12.11.0) | Dépôt GitHub officiel |
| 6 | retenue | 2026-06-13 | [better-sqlite3 v12.10.1](https://github.com/WiseLibs/better-sqlite3/releases/tag/v12.10.1) | Dépôt GitHub officiel |
| 6 | retenue | 2026-05-12 | [better-sqlite3 v12.10.0](https://github.com/WiseLibs/better-sqlite3/releases/tag/v12.10.0) | Dépôt GitHub officiel |
| 1 | ecartee | 2026-10-27 | [Show HN: Markdown is 40× more token-efficient with SQLite](https://www.withnative.ai/research-and-posts/markdown-context-benchmark) | Hacker News |
| 1 | ecartee | 2026-09-22 | [Show HN: I built a macOS Quick Look app for Markdown, SQLite, ZIP, and 300 more](https://quicklookpro.com/) | Hacker News |
| 1 | ecartee | 2026-08-16 | [Show HN: Local-first note taking web app powered by SQLite WASM – notem](https://notem.pages.dev/) | Hacker News |
| 1 | ecartee | 2026-07-29 | [Show HN: Kedge – Full-stack cloud with forkable VM snapshots and global SQLite](https://kedge.dev/) | Hacker News |
| 0 | ecartee | 2026-10-23 | [Show HN: Mdt – save tokens reading changes to Markdown](https://github.com/markdowntool/mdt) | Hacker News |

## 4. Chiffres bruts (gh api, relevés le 2026-10-28)

| Chiffre | Garder les fichiers .md (statu quo) | Passer à SQLite local (better-sqlite3) |
|---|---|---|
| Dépôt | [Alexandre-ab/radar](https://github.com/Alexandre-ab/radar) | [WiseLibs/better-sqlite3](https://github.com/WiseLibs/better-sqlite3) |
| Créé le | 2026-10-28 | 2016-09-07 |
| Versions publiées (releases) | 0 | 130 |
| Dernière version | aucune | v13.0.3 (2026-08-05) |
| Contributeurs | 1 | 69 |
| Commits sur 90 jours | 6 | 3 |
| Licence | aucune licence déclarée (license: null) | MIT |
| Étoiles | 0 | 7531 |
| Issues ouvertes | 0 | 76 |
| Dernier push | 2026-10-28 | 2026-08-10 |
| Archivé | non | non |

## 5. Matrice de décision (poids 1 à 3, notes 1 à 5)

| Critère | Poids | Garder les fichiers .md (statu quo) | Passer à SQLite local (better-sqlite3) |
|---|---|---|---|
| Maturité | 2 | 3 / 5 → 6 | 5 / 5 → 10 |
| Dynamisme | 1 | 2 / 5 → 2 | 3 / 5 → 3 |
| Licence (éliminatoire si ≤ 1) | 3 | 5 / 5 → 15 | 5 / 5 → 15 |
| Maintenance | 2 | 3 / 5 → 6 | 4 / 5 → 8 |
| Coût total | 3 | 5 / 5 → 15 | 3 / 5 → 9 |
| Apprentissage | 3 | 5 / 5 → 15 | 3 / 5 → 9 |
| Réversibilité | 2 | 5 / 5 → 10 | 3 / 5 → 6 |
| **Total pondéré** | **16** | **69 / 80 (86 %)** | **60 / 80 (75 %)** |

**Option la mieux notée : « Garder les fichiers .md (statu quo) », 69 / 80 (86 %), +9 points d'écart.**

### Justification de chaque note

**Maturité** (poids 2)

- Garder les fichiers .md (statu quo) : 3 / 5. Dépôt créé le 2026-10-28, 0 release GitHub ; stockage en fichiers texte sans bibliothèque ([source](https://github.com/Alexandre-ab/radar), consultée le 2026-10-28)
- Passer à SQLite local (better-sqlite3) : 5 / 5. Créé le 2016-09-07, 130 releases, dernière v13.0.3 du 2026-08-05 ([source](https://github.com/WiseLibs/better-sqlite3/releases), consultée le 2026-10-28)

**Dynamisme** (poids 1)

- Garder les fichiers .md (statu quo) : 2 / 5. 6 commits sur 90 jours, 1 contributeur ([source](https://github.com/Alexandre-ab/radar/commits/main), consultée le 2026-10-28)
- Passer à SQLite local (better-sqlite3) : 3 / 5. 3 commits sur 90 jours, mais 69 contributeurs et 7 531 étoiles ([source](https://github.com/WiseLibs/better-sqlite3), consultée le 2026-10-28)

**Licence** (poids 3)

- Garder les fichiers .md (statu quo) : 5 / 5. Aucune bibliothèque tierce ajoutée ; dépôt sans licence déclarée (license: null), code de l'équipe ([source](https://github.com/Alexandre-ab/radar), consultée le 2026-10-28)
- Passer à SQLite local (better-sqlite3) : 5 / 5. Licence MIT : usage libre et gratuit ([source](https://github.com/WiseLibs/better-sqlite3/blob/master/LICENSE), consultée le 2026-10-28)

**Maintenance** (poids 2)

- Garder les fichiers .md (statu quo) : 3 / 5. 1 seul contributeur : toute la maintenance repose sur l'équipe ([source](https://github.com/Alexandre-ab/radar), consultée le 2026-10-28)
- Passer à SQLite local (better-sqlite3) : 4 / 5. Dernier push le 2026-08-10, 76 issues ouvertes, 0 faille connue dans la base OSV (npm) ([source](https://osv.dev/list?q=better-sqlite3&ecosystem=npm), consultée le 2026-10-28)

**Coût total** (poids 3)

- Garder les fichiers .md (statu quo) : 5 / 5. 0 € et 0 migration : rien à changer ([source](https://github.com/Alexandre-ab/radar), consultée le 2026-10-28)
- Passer à SQLite local (better-sqlite3) : 3 / 5. 0 € de licence, mais Node.js ≥ 22 et un module natif (node-addon-api) exigés, plus une migration à écrire ([source](https://github.com/WiseLibs/better-sqlite3/blob/master/package.json), consultée le 2026-10-28)

**Apprentissage** (poids 3)

- Garder les fichiers .md (statu quo) : 5 / 5. Rien à apprendre : lecture et écriture de fichiers texte ([source](https://github.com/Alexandre-ab/radar), consultée le 2026-10-28)
- Passer à SQLite local (better-sqlite3) : 3 / 5. API synchrone documentée (docs/api.md), mais SQL et schéma de base à concevoir ([source](https://github.com/WiseLibs/better-sqlite3/blob/master/docs/api.md), consultée le 2026-10-28)

**Réversibilité** (poids 2)

- Garder les fichiers .md (statu quo) : 5 / 5. Fichiers .md lisibles et versionnés dans git : aucun verrou ([source](https://github.com/Alexandre-ab/radar), consultée le 2026-10-28)
- Passer à SQLite local (better-sqlite3) : 3 / 5. La base tient dans un fichier local, mais revenir aux .md demande un export à écrire ; module natif à recompiler (docs/compilation.md) ([source](https://github.com/WiseLibs/better-sqlite3/blob/master/docs/compilation.md), consultée le 2026-10-28)

## 6. Impact

### Garder les fichiers .md (statu quo)

- **Périmètre** : Aucun changement de code : la mémoire reste dans les fichiers .md.
- **Budget** : 0 € : aucune dépendance ni abonnement ajouté.
- **Délais** : 0 sprint : rien à migrer, les 2 sprints restent pour les fonctionnalités.
- **Anticipation** : Si la mémoire grossit, prévoir un index de recherche sur les fichiers avant de changer de stockage.

### Passer à SQLite local (better-sqlite3)

- **Périmètre** : Réécrire la couche de stockage et un script de migration des fichiers .md vers la base.
- **Budget** : 0 € de licence (MIT) ; le coût est le temps du seul développeur.
- **Délais** : Estimation à valider : au moins 1 des 2 sprints pour la migration et ses tests.
- **Anticipation** : Recherches plus rapides si la mémoire grossit ; suivre les versions de Node.js (≥ 22 exigé).
