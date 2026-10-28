# Rapport de veille · A · La mémoire d'Hivemind reste-t-elle en fichiers .md, ou passe-t-on à SQLite ?

_Écrit par « radar report » le 2026-10-28 à partir de radar.config.yaml (rubriques « rapport » et « decision ») et de data/items.json. Chaque lien vient de items.json ou de la décision ; détail des notes et de leurs sources dans decision.md._

## Page 1 · Synthèse de veille

### 1. Nos sources retenues

| Source | Catégorie | Type de veille | Infos retenues | Publiées entre | Info retenue la plus récente |
|---|---|---|---|---|---|
| Dépôt GitHub officiel | officielle | technologique | 30 | 2026-05-12 et 2026-10-28 | [Codex CLI rust-v0.166.0-alpha.5](https://github.com/openai/codex/releases/tag/rust-v0.166.0-alpha.5) |
| Hacker News | communaute | technologique | 2 | 2026-10-27 et 2026-10-28 | [Claude Chalk, a mod that lets Claude Code colour its own replies](https://github.com/adamkdean/claude-chalk) |
| Base OSV (failles connues) | institution | securite | 2 | 2024-03-25 et 2024-09-10 | [express · GHSA-qw6h-vgh9-j6wx : express vulnerable to XSS via response.redirect()](https://osv.dev/vulnerability/GHSA-qw6h-vgh9-j6wx) |
| Anthropic · Usage Policy | officielle | reglementaire | 1 | 2026-10-28 et 2026-10-28 | [Usage Policy \ Anthropic (version du 2026-10-28)](https://www.anthropic.com/legal/aup#empreinte-effb4dccd621) |

35 infos retenues sur 72 collectées (fiabilité au moins égale au seuil de 4, calculée par « radar score »).

### 2. Les 3 tendances

#### Tendance 1 · Les assistants de code en ligne de commande publient des versions à un rythme très rapide (technologique)

**Ce que montrent les infos** : Les 10 dernières versions de Claude Code relevées par radar ont été publiées en 10 jours, du 18 au 27 octobre 2026. Du 23 au 28 octobre, Codex CLI a publié 2 versions stables (0.164.0 le 23 octobre, 0.165.0 le 27 octobre) et 8 pré-versions.

5 infos datées qui vont dans ce sens :

- 2026-10-18 · [Claude Code v2.1.303](https://github.com/anthropics/claude-code/releases/tag/v2.1.303) · Dépôt GitHub officiel · fiabilité 6 (retenue)
- 2026-10-22 · [Claude Code v2.1.308](https://github.com/anthropics/claude-code/releases/tag/v2.1.308) · Dépôt GitHub officiel · fiabilité 6 (retenue)
- 2026-10-23 · [Codex CLI rust-v0.164.0](https://github.com/openai/codex/releases/tag/rust-v0.164.0) · Dépôt GitHub officiel · fiabilité 6 (retenue)
- 2026-10-27 · [Claude Code v2.1.312](https://github.com/anthropics/claude-code/releases/tag/v2.1.312) · Dépôt GitHub officiel · fiabilité 6 (retenue)
- 2026-10-27 · [Codex CLI rust-v0.165.0](https://github.com/openai/codex/releases/tag/rust-v0.165.0) · Dépôt GitHub officiel · fiabilité 6 (retenue)

- **Impact attendu** : Hivemind pilote ces outils en ligne de commande : leurs options et leurs sorties peuvent changer d'une version à l'autre, presque chaque jour.
- **Ce qu'elle permet d'anticiper** : Sur 12 mois, à ce rythme (environ une version par jour pour Claude Code), il faut figer les versions utilisées par Hivemind et tester chaque montée de version avant de l'adopter.
- **Compatibilité budget** : Compatible : suivre ces versions ne coûte rien, les dépôts sont publics et collectés par radar.
- **Compatibilité technique** : Compatible : un seul développeur est alerté par « radar collect », mais chaque montée de version demande un test.
- **Retenue**, pourquoi : Sources officielles (dépôts GitHub des éditeurs), fiabilité 6, faits datés et vérifiables.

#### Tendance 2 · Le stockage local en SQLite est mûr, et la communauté le combine avec Markdown pour la mémoire des agents IA (technologique, tendance « data »)

**Ce que montrent les infos** : better-sqlite3 a publié 10 versions en moins de 3 mois, de la v12.10.0 (12 mai 2026) à la v13.0.3 (5 août 2026), en passant par la v13.0.0 (21 juillet). Côté communauté, l'éditeur Native affirme, sur son propre banc d'essai, que des agents consomment 40 fois moins de tokens quand Markdown est rangé dans SQLite (présenté sur Hacker News le 27 octobre 2026), et LLMSchema exporte le schéma d'une base en Markdown compact pour les agents IA (présenté le 8 octobre 2026).

5 infos datées qui vont dans ce sens :

- 2026-05-12 · [better-sqlite3 v12.10.0](https://github.com/WiseLibs/better-sqlite3/releases/tag/v12.10.0) · Dépôt GitHub officiel · fiabilité 6 (retenue)
- 2026-07-21 · [better-sqlite3 v13.0.0](https://github.com/WiseLibs/better-sqlite3/releases/tag/v13.0.0) · Dépôt GitHub officiel · fiabilité 6 (retenue)
- 2026-08-05 · [better-sqlite3 v13.0.3](https://github.com/WiseLibs/better-sqlite3/releases/tag/v13.0.3) · Dépôt GitHub officiel · fiabilité 6 (retenue)
- 2026-10-08 · [Show HN: LLMSchema – Dump your database schema as compact Markdown for AI agents](https://github.com/tordrt/LLMSchema) · Hacker News · fiabilité 0 (ecartee)
- 2026-10-27 · [Show HN: Markdown is 40× more token-efficient with SQLite](https://www.withnative.ai/research-and-posts/markdown-context-benchmark) · Hacker News · fiabilité 1 (ecartee)

- **Impact attendu** : La mémoire d'Hivemind en fichiers .md n'est pas menacée à court terme, mais SQLite devient une option crédible si la mémoire grossit et que la recherche dans les fichiers ralentit.
- **Ce qu'elle permet d'anticiper** : Sur 12 mois : suivre les retours d'expérience indépendants sur la mémoire des agents en SQLite, et garder des fichiers .md simples à importer dans une base.
- **Compatibilité budget** : Compatible : better-sqlite3 est sous licence MIT, 0 € d'abonnement.
- **Compatibilité technique** : Compatible avec un Hivemind local, mais better-sqlite3 exige Node.js 22 ou plus et un module natif ; une migration prendrait au moins un des 2 sprints du seul développeur (notre estimation, decision.md).
- **Retenue**, pourquoi : Appuyée par une source officielle (10 versions de better-sqlite3 retenues, fiabilité 6) ; les 2 infos communautaires sont écartées (« Show HN », dont un banc d'essai d'éditeur) et servent seulement de signal.

#### Tendance 3 · Les outils qui pilotent plusieurs agents de code depuis un même endroit se multiplient (concurrentielle)

**Ce que montrent les infos** : Les 26 et 27 octobre 2026, 4 projets présentés sur Hacker News proposent de piloter Claude Code ou Codex depuis un même outil : Cindy (agents interchangeables), Paradev (un espace de travail pour plusieurs agents), CleanCode (Claude Code et Codex sur un même canevas) et Aigent-OS (un « harness » pour Claude Code).

4 infos datées qui vont dans ce sens :

- 2026-10-26 · [Paradev: One workspace for Claude Code, Codex, and any coding agent](https://paradev.com) · Hacker News · fiabilité 3 (ecartee)
- 2026-10-27 · [Cindy, Open-source agent that runs Claude Code and Codex as swappable harnesses](https://github.com/makecindy/cindy) · Hacker News · fiabilité 4 (retenue)
- 2026-10-27 · [Show HN: CleanCode – Claude Code and Codex collaborating on one canvas](https://github.com/chen-985211/cleancode) · Hacker News · fiabilité 2 (ecartee)
- 2026-10-27 · [Show HN: Aigent-OS, a Claude Code harness that clears and resumes](https://github.com/wrg32786/aigent-os) · Hacker News · fiabilité 2 (ecartee)

- **Impact attendu** : Ces projets recoupent le rôle d'Hivemind, piloter des IA en ligne de commande : si l'un d'eux s'impose, il deviendra un concurrent direct ou une brique à réutiliser.
- **Ce qu'elle permet d'anticiper** : Sur 12 mois : repérer ceux qui gagnent des utilisateurs (étoiles, versions publiées) avant de s'en inspirer ou de s'en démarquer.
- **Compatibilité budget** : Compatible : les observer ne coûte rien ; Cindy se présente comme open source.
- **Compatibilité technique** : Sans effet aujourd'hui : aucune intégration n'est envisagée dans Hivemind.
- **Écartée**, pourquoi : Une seule info retenue (Cindy, fiabilité 4) ; les 3 autres sont écartées (fiabilité 2 à 3 : deux « Show HN » et un site sans auteur identifié). Le signal est trop faible pour agir : on le garde sous surveillance.

### 3. Ce qu'il faut continuer à surveiller

- Le rythme des versions de Claude Code et de Codex CLI, et les changements qui touchent leur pilotage en ligne de commande.
- Les retours d'expérience indépendants sur la mémoire des agents en SQLite, au-delà des bancs d'essai d'éditeurs.
- Les outils qui pilotent plusieurs agents (Cindy, Paradev…) : étoiles et versions publiées dans les prochains mois.
- La politique d'usage d'Anthropic, suivie par radar : sa page annonce une nouvelle version en vigueur le 12 novembre 2026. ([Usage Policy \ Anthropic (version du 2026-10-28)](https://www.anthropic.com/legal/aup#empreinte-effb4dccd621))

<div style="page-break-after: always;"></div>

## Page 2 · Note de recommandation

### 1. La question et le contexte

A · La mémoire d'Hivemind reste-t-elle en fichiers .md, ou passe-t-on à SQLite ?

Hivemind garde aujourd'hui sa mémoire dans des fichiers .md. L'alternative étudiée est une base SQLite locale, via la bibliothèque better-sqlite3.

Besoins du client : Hivemind reste local ; 0 € d'abonnement en plus ; 1 seul développeur ; prochaine livraison dans 2 sprints.

### 2. Les options et la matrice

| | Option | Dépôt GitHub |
|---|---|---|
| 1 | Garder les fichiers .md (statu quo) | [Alexandre-ab/radar](https://github.com/Alexandre-ab/radar) |
| 2 | Passer à SQLite local (better-sqlite3) | [WiseLibs/better-sqlite3](https://github.com/WiseLibs/better-sqlite3) |

Matrice de décision (poids 1 à 3, notes 1 à 5) :

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

Chaque note est justifiée par un chiffre réel, sa source et sa date dans decision.md.

### 3. La recommandation

> **Nous recommandons de garder la mémoire d'Hivemind en fichiers .md pour les 2 prochains sprints, et de ne passer à SQLite que si la recherche dans ces fichiers devient trop lente.**

### 4. L'impact

Option retenue : Garder les fichiers .md (statu quo).

- **Périmètre** : Aucun changement de code : la mémoire reste dans les fichiers .md.
- **Budget** : 0 € : aucune dépendance ni abonnement ajouté.
- **Délais** : 0 sprint : rien à migrer, les 2 sprints restent pour les fonctionnalités.

### 5. Les risques et le plan B

- La recherche dans les fichiers .md ralentit à mesure que la mémoire grossit.
- Tout repose sur un seul développeur (1 contributeur sur le dépôt de référence).
- Les assistants pilotés évoluent très vite (10 versions de Claude Code en 10 jours) : une nouvelle version peut casser leur pilotage.

**Plan B** : Basculer vers SQLite (better-sqlite3, licence MIT) dès qu'un seuil que nous proposons est franchi : une recherche dans la mémoire qui dépasse 1 seconde, ou plus de 10 000 fichiers .md. Les fichiers .md restent la source et sont importés dans la base par un script : le retour arrière reste possible.

### 6. La prochaine étape

**Le 2026-11-04** : Mesurer le temps de recherche dans la mémoire .md actuelle d'Hivemind et valider avec le client le seuil de bascule vers SQLite.
