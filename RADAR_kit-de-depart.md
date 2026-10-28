# RADAR · kit de départ

**Placez ce fichier dans votre dossier `radar` :** votre IA pourra le lire. Pas de code ici, c'est votre IA qui code. Pour chaque brique, attendez que la notion ait été présentée avant de lancer le prompt.

## 1. Les prompts, brique par brique

À copier dans Claude Code, Codex CLI ou Antigravity, depuis le dossier `radar`.

**Prompt 1 · Brique 2, la collecte (10h05)**

```text
Lis RADAR_kit-de-depart.md (parties 2, 3 et 4). Crée un outil en ligne de commande « radar », en Node.js ou en Python (choisis le plus simple pour nous).
- La commande « radar collect » lit radar.config.yaml (notre plan de veille, déjà écrit) et enregistre les infos dans data/items.json.
- Chaque info respecte la fiche de la partie 3 : jamais d'info sans url ni date de publication.
- Rien n'est écrit en dur dans le code : les sources et les mots-clés viennent de la config.
- Commence par UNE source qui marche (les versions de Claude Code via gh api), puis on ajoutera les autres.
- Explique-nous en 5 lignes comment le lancer.
```

**Prompt 2 · Brique 3, le tri (11h12)**

```text
Ajoute la commande « radar score ». Elle remplit le champ « fiabilite » de chaque info de data/items.json, selon des règles écrites dans radar.config.yaml (rubrique « regles_score »), pas dans le code.
Chaque source de la config a un champ « categorie » : officielle, institution, communaute ou social. Les règles de base :
- categorie officielle +3, institution +2, communaute +1, social 0
- publiée il y a moins de 6 mois +1
- auteur identifié +1 ; source ou méthode citée +1
- une autre source indépendante dit pareil +1
- lien affilié, « partenaire », ou l'auteur vend le produit -2
Affiche un top 10 trié par score, avec la source, la date et les règles qui ont donné les points.
```

Ajoutez ensuite dans la config au moins une règle à vous, qui repère un autre biais : effet de mode, benchmark d'éditeur ou contenu généré.

**Prompt 3 · Brique 4, l'archive (11h57)**

```text
Complète chaque info de data/items.json :
- « type_veille » (technologique, concurrentielle, reglementaire ou securite) : il vient de la source, indiqué dans radar.config.yaml.
- « etiquettes » : uniquement celles de la liste « etiquettes » de radar.config.yaml.
- « statut » : « retenue » si la fiabilité atteint le « seuil » de radar.config.yaml, sinon « ecartee ».
Ajoute la commande « radar search <mot> » qui retrouve les infos contenant ce mot (titre ou étiquettes) et les affiche avec leur url et leur date.
```

**Prompt 4 · Brique 5, la décision (14h00)**

D'abord, ajoutez à votre plan les dépôts et mots-clés de vos 2 options, et relancez `radar collect`.

```text
Lis RADAR_kit-de-depart.md, partie 5. Notre question est la <A, B ou C>, notre alternative est <votre alternative>.
Ajoute la commande « radar decide » :
- Elle filtre les infos de data/items.json qui touchent cette question.
- Elle va chercher avec gh api les chiffres bruts de chaque option : date de création, versions, contributeurs, commits sur 90 jours, licence. Pour « ne rien changer », la source est le dépôt d'Hivemind et ses dépendances actuelles.
- Elle écrit decision.md : la matrice des 2 options sur 7 critères (maturité, dynamisme, licence, maintenance, coût total, apprentissage, réversibilité), avec les poids (1 à 3) et les notes (1 à 5) que NOUS écrivons dans radar.config.yaml (rubrique « decision »), chaque note avec son chiffre et l'url datée de sa source.
- Elle calcule le total pondéré et ajoute une section « Impact » vide (périmètre, budget, délais) que nous remplirons.
```

**Prompt 5 · Brique 6, le rapport (15h05)**

```text
Lis RADAR_kit-de-depart.md, partie 6. Ajoute la commande « radar report » : elle écrit rapport.md avec la structure des 2 pages, les sources datées (urls de data/items.json uniquement) et la matrice de decision.md.
Ensuite, aide-nous à rédiger les textes (tendances, recommandation, risques, prochaine étape) à partir de ces seules sources. N'invente aucune source.
```

Puis ouvrez chaque lien du rapport : il existe, et il dit bien ce que le rapport affirme. Une source inventée = 0 sur tout le bloc Rapport.

## 2. Le modèle du plan de veille : `radar.config.yaml` (brique 1, 9h32)

À remplir par vous. Tout ce que RADAR surveille est écrit ici, nulle part ailleurs. Cet exemple couvre 3 types de veille : technologique, sécurité, réglementaire.

```yaml
axes:      [cli-ia, securite, cgu-ia]          # 3 à 5 thèmes, au moins 3 types de veille
mots_cles: ["claude code", "codex", "MCP"]     # ce qui déclenche une capture
ignorer:   ["crypto", "NFT"]                   # ce qu'on décide de ne PAS surveiller
sources:                                        # au moins 5, de 3 types différents
  - { type: releases, depot: anthropics/claude-code, type_veille: technologique }
  - { type: releases, depot: openai/codex, type_veille: technologique }
  - { type: hackernews, requete: "claude code", type_veille: technologique }
  - { type: failles, paquet: express, ecosysteme: npm, type_veille: securite }
  - { type: page, url: "<url des CGU d'un éditeur d'IA>", type_veille: reglementaire }
frequence: { failles: quotidien, tendances: hebdo }
livrable:  "top 10 du lundi + alerte si faille"
```

Le champ `categorie` de chaque source s'ajoute à la brique 3, `etiquettes` et `seuil` à la brique 4, `decision` à la brique 5.

## 3. La fiche d'une info (dans `data/items.json`)

```json
{
  "titre": "Claude Code v2.1.309",
  "url": "https://github.com/anthropics/claude-code/releases/tag/v2.1.309",
  "publie_le": "2026-10-22",
  "collecte_le": "2026-10-27",
  "source": "Dépôt GitHub officiel",
  "type_veille": null,
  "etiquettes": null,
  "fiabilite": null,
  "statut": null
}
```

`fiabilite` se remplit à la brique 3 ; `type_veille`, `etiquettes` et `statut` à la brique 4.

## 4. Des requêtes qui marchent déjà

Montrez-les à votre IA comme exemples. Pour GitHub, passez toujours par `gh api`, connecté à votre compte (`gh auth status`) : 5 000 requêtes/h ; sans connexion, c'est 60/h pour toute la salle.

**Les versions d'un dépôt GitHub :**

```powershell
gh api "repos/anthropics/claude-code/releases?per_page=10" --jq ".[] | {tag: .tag_name, date: .published_at, url: .html_url}"
```

**Hacker News** (ouvrable dans le navigateur) :

```text
https://hn.algolia.com/api/v1/search_by_date?query=claude%20code&tags=story
```

**Les failles connues d'un paquet npm** (base OSV) :

```powershell
Invoke-RestMethod -Method Post -Uri https://api.osv.dev/v1/query -Body '{"package":{"name":"express","ecosystem":"npm"},"version":"4.17.1"}'
```

Sur Mac ou Linux : `curl -s -X POST https://api.osv.dev/v1/query -d '{"package":{"name":"express","ecosystem":"npm"},"version":"4.17.1"}'`

**Un flux Atom** : ajoutez `/releases.atom` à l'adresse d'un dépôt, par exemple `https://github.com/openai/codex/releases.atom`.

## 5. L'après-midi : votre question (13h32)

Chaque binôme choisit UNE question et UNE alternative. On compare toujours 2 options : ne rien changer (la solution actuelle d'Hivemind) ou l'alternative.

- **A · La mémoire :** la mémoire d'Hivemind reste-t-elle en fichiers .md, ou passe-t-on à une base (SQLite, ou une base vectorielle) ?
- **B · La connexion :** on continue à piloter les IA en ligne de commande, ou on passe par un protocole standard (MCP, ou Agent Client Protocol) ?
- **C · La livraison :** Hivemind reste une appli web locale, ou devient une appli de bureau (Electron, ou Tauri) ?

**Besoins du client** (ils fixent vos poids) : Hivemind reste local, 0 € d'abonnement en plus, 1 développeur, prochaine livraison dans 2 sprints.

## 6. Le format du rapport (brique 6)

**Page 1 · Synthèse de veille** (une tendance = plusieurs infos datées qui vont dans le même sens ; la data = le stockage et l'usage des données)
1. Vos sources, avec leur date : doc officielle, institutions, études.
2. 3 tendances liées à Hivemind, dont au moins 1 sur la data.
3. Pour chacune : l'impact attendu, ce qu'elle permet d'anticiper, sa compatibilité avec le budget et la technique.
4. Pour chacune : retenue ou écartée, et pourquoi.

**Page 2 · Note de recommandation**
1. La question et le contexte.
2. Les options et la matrice.
3. La recommandation, en une phrase.
4. L'impact : périmètre, budget, délais.
5. Les risques et le plan B.
6. La prochaine étape, avec une date.

## 7. La soutenance (16h05, 7 min par binôme)

4 min de démo en live : votre plan, puis `radar collect`, `score`, `search`, `decide`, `report`, puis `decision.md` et `rapport.md` à l'écran, et votre recommandation en une phrase. Ensuite 3 min de questions : un mot à retrouver, une note de la matrice, un lien du rapport, et une objection pour chacun. Note /20 : binôme /16 + chacun /4.
