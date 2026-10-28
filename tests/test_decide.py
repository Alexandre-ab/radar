"""Tests de la brique 5 (radar decide → decision.md), sans réseau (gh api simulé)
et sans toucher aux vrais fichiers du projet.

Lancer depuis le dossier radar :  python3 -m unittest discover -s tests -v
"""
import argparse
import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
import urllib.parse
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import radar  # noqa: E402

VRAIS_FICHIERS = [Path(radar.FICHIER_ITEMS), Path(radar.FICHIER_PAGES),
                  Path(radar.FICHIER_CONFIG), Path(radar.FICHIER_DECISION)]
empreintes_avant = {}

REF = date(2026, 10, 28)


def empreinte(chemin):
    return hashlib.sha256(chemin.read_bytes()).hexdigest() if chemin.exists() else None


def setUpModule():
    for chemin in VRAIS_FICHIERS:
        empreintes_avant[chemin] = empreinte(chemin)


def tearDownModule():
    # Garde-fou : les tests ne doivent jamais réécrire les vrais fichiers du projet.
    for chemin in VRAIS_FICHIERS:
        if empreinte(chemin) != empreintes_avant[chemin]:
            raise AssertionError(f"{chemin} a été modifié par les tests !")


def note(valeur, chiffre="un chiffre vérifié", source="https://exemple.org/source", jour="2026-10-27"):
    return {"note": valeur, "chiffre": chiffre, "source": source, "date": jour}


def critere(poids, note_a, note_b, **autres):
    valeurs = {"poids": poids, "notes": {"option_a": note(note_a), "option_b": note(note_b)}}
    valeurs.update(autres)
    return valeurs


DECISION = {
    "question": "Garder l'outil A ou passer à l'outil B ?",
    "contexte": "Le contexte de la question.",
    "besoins": ["rester local", "0 € en plus"],
    "commits_sur_jours": 90,
    "infos_max": 2,
    "filtre": {"si": [{"titre_contient": ["outil-b", "stockage"]}]},
    "options": {
        "option_a": {"nom": "Garder l'outil A", "depot": "exemple/outil-a",
                     "impact": {"perimetre": "Rien ne change.", "budget": "0 €"}},
        "option_b": {"nom": "Passer à l'outil B", "depot": "exemple/outil-b"},
    },
    "criteres": {
        "maturite": critere(2, 3, 5, libelle="Maturité"),
        "dynamisme": critere(1, 2, 3),
        "licence": critere(3, 5, 5, libelle="Licence", note_eliminatoire=1),
        "maintenance": critere(2, 3, 4),
        "cout_total": critere(3, 5, 3, libelle="Coût total"),
        "apprentissage": critere(3, 5, 3),
        "reversibilite": critere(2, 5, 3),
    },
}
# Totaux attendus : A = 6+2+15+6+15+15+10 = 69 ; B = 10+3+15+8+9+9+6 = 60 ; maximum = 16 × 5 = 80.


def decision_ok(**modifs):
    decision = copy.deepcopy(DECISION)
    decision.update(modifs)
    return decision


def config_ok(decision=None):
    return {"sources": [{"type": "releases", "depot": "exemple/outil-b", "nom": "Dépôt GitHub officiel",
                         "categorie": "officielle", "type_veille": "technologique"}],
            "decision": decision if decision is not None else decision_ok()}


class FauxGitHub:
    """Répond aux appels de gh_api comme l'API GitHub, page par page."""

    def __init__(self):
        self.depots = {
            "exemple/outil-a": {"repo": {"html_url": "https://github.com/exemple/outil-a", "private": True,
                                         "created_at": "2026-10-28T09:18:21Z", "license": None,
                                         "stargazers_count": 0, "open_issues_count": 0,
                                         "pushed_at": "2026-10-28T11:17:31Z", "archived": False},
                                "releases": [], "contributors": None, "commits": [{"sha": str(i)} for i in range(6)]},
            "exemple/outil-b": {"repo": {"html_url": "https://github.com/exemple/outil-b", "private": False,
                                         "created_at": "2016-09-07T16:48:37Z",
                                         "license": {"key": "mit", "spdx_id": "MIT"},
                                         "stargazers_count": 7531, "open_issues_count": 76,
                                         "pushed_at": "2026-08-10T03:10:10Z", "archived": False},
                                "releases": ([{"tag_name": "v2.0.0-brouillon", "draft": True, "published_at": None}]
                                             + [{"tag_name": f"v1.{i}", "draft": False,
                                                 "published_at": f"2026-08-{(i % 28) + 1:02d}T00:00:00Z"} for i in range(130)]),
                                "contributors": [{"login": f"c{i}"} for i in range(69)],
                                "commits": [{"sha": str(i)} for i in range(3)]},
        }
        self.appels = []

    def __call__(self, chemin):
        self.appels.append(chemin)
        adresse = urllib.parse.urlsplit(chemin)
        morceaux = adresse.path.split("/")         # repos / propriétaire / nom [/ liste]
        depot = self.depots["/".join(morceaux[1:3])]
        if len(morceaux) == 3:
            return depot["repo"]
        liste = depot[morceaux[3]]
        if liste is None:
            return None                            # réponse vide (HTTP 204)
        parametres = urllib.parse.parse_qs(adresse.query)
        page, par_page = int(parametres["page"][0]), int(parametres["per_page"][0])
        return liste[(page - 1) * par_page: page * par_page]


def fiche(titre, fiabilite, publie_le="2026-10-27", statut="retenue", url=None, source="Hacker News"):
    return {"titre": titre, "url": url or f"https://exemple.org/{abs(hash(titre))}", "publie_le": publie_le,
            "collecte_le": "2026-10-28", "source": source, "type_veille": "technologique",
            "etiquettes": [], "fiabilite": fiabilite, "statut": statut}


# --- Validation de la rubrique decision ------------------------------------

class TestLireDecision(unittest.TestCase):

    def erreur(self, decision):
        with self.assertRaises(SystemExit) as e:
            radar.lire_decision(config_ok(decision))
        return str(e.exception.code)

    def test_vraie_config_du_projet_valide(self):
        # Lecture seule du vrai radar.config.yaml.
        decision = radar.lire_decision(radar.charger_config())
        self.assertEqual(len(decision["options"]), radar.NOMBRE_OPTIONS)
        for nom in radar.CRITERES_KIT:
            self.assertIn(nom, decision["criteres"])

    def test_config_de_test_valide(self):
        self.assertEqual(radar.lire_decision(config_ok())["question"], DECISION["question"])

    def test_rubrique_absente(self):
        with self.assertRaises(SystemExit) as e:
            radar.lire_decision({"sources": []})
        self.assertIn("« decision » est absente", str(e.exception.code))

    def test_champs_generaux(self):
        for modif, attendu in [({"question": ""}, "« question » doit être un texte"),
                               ({"contexte": 3}, "« contexte » doit être un texte"),
                               ({"besoins": []}, "« besoins » doit être la liste"),
                               ({"commits_sur_jours": 0}, "« commits_sur_jours »"),
                               ({"commits_sur_jours": "90"}, "« commits_sur_jours »"),
                               ({"infos_max": 0}, "« infos_max »"),
                               ({"filtre": None}, "« filtre » doit contenir « si: »"),
                               ({"filtre": {"si": [{"mots": ["x"]}]}}, "filtre : cas n°1 : condition « mots » inconnue")]:
            with self.subTest(modif=modif):
                self.assertIn(attendu, self.erreur(decision_ok(**modif)))

    def test_exactement_deux_options(self):
        une = {"option_a": DECISION["options"]["option_a"]}
        trois = dict(DECISION["options"], option_c={"nom": "C", "depot": "exemple/c"})
        for options in (une, trois, None):
            with self.subTest(options=options):
                self.assertIn("exactement 2 options", self.erreur(decision_ok(options=options)))

    def test_option_mal_ecrite(self):
        for modif, attendu in [({"nom": ""}, "« nom » doit être un texte"),
                               ({"depot": "outil-b"}, "« depot » doit s'écrire propriétaire/nom"),
                               ({"depot": "https://github.com/exemple/outil-b"}, "« depot » doit s'écrire"),
                               ({"impact": "rien"}, "impact : doit contenir"),
                               ({"impact": {"risques": "x"}}, "« risques » inconnu"),
                               ({"impact": {"budget": ""}}, "impact › budget : doit être un texte")]:
            with self.subTest(modif=modif):
                decision = decision_ok()
                decision["options"]["option_b"].update(modif)
                self.assertIn(f"options › option_b", self.erreur(decision))
                self.assertIn(attendu, self.erreur(decision))

    def test_critere_du_kit_absent(self):
        for nom in radar.CRITERES_KIT:
            with self.subTest(nom=nom):
                decision = decision_ok()
                del decision["criteres"][nom]
                self.assertIn(f"le critère « {nom} » du kit est absent", self.erreur(decision))

    def test_critere_inconnu_refuse(self):
        for nom in ("popularite", "Maturite", "cout total"):   # hors liste, ou mal orthographié
            with self.subTest(nom=nom):
                decision = decision_ok()
                decision["criteres"][nom] = critere(2, 5, 1)
                message = self.erreur(decision)
                self.assertIn(f"critère « {nom} » inconnu (possibles : maturite, dynamisme, licence, maintenance, "
                              "cout_total, apprentissage, reversibilite)", message)

    def test_critere_inconnu_n_entre_pas_dans_les_totaux(self):
        # Sans la validation, ce critère changerait le gagnant : on vérifie qu'on n'y arrive jamais.
        decision = decision_ok()
        decision["criteres"]["popularite"] = critere(3, 1, 5)
        with self.assertRaises(SystemExit):
            radar.lire_decision(config_ok(decision))

    def test_poids_hors_echelle(self):
        for poids in (0, 4, True, "2", 2.5):
            with self.subTest(poids=poids):
                decision = decision_ok()
                decision["criteres"]["maturite"]["poids"] = poids
                self.assertIn("criteres › maturite : « poids » doit être un entier de 1 à 3", self.erreur(decision))

    def test_note_mal_ecrite(self):
        for modif, attendu in [({"note": 0}, "« note » doit être un entier de 1 à 5"),
                               ({"note": 6}, "« note » doit être un entier de 1 à 5"),
                               ({"note": "5"}, "« note » doit être un entier de 1 à 5"),
                               ({"chiffre": ""}, "« chiffre » doit donner le chiffre réel"),
                               ({"source": "github.com/exemple"}, "« source » doit être une url"),
                               ({"date": "hier"}, "« date » = jour de consultation"),
                               ({"date": date(2026, 10, 27)}, "entre guillemets"),   # YAML sans guillemets
                               ({"date": (date.today() + timedelta(days=2)).isoformat()}, "pas dans le futur")]:
            with self.subTest(modif=modif):
                decision = decision_ok()
                decision["criteres"]["licence"]["notes"]["option_a"].update(modif)
                self.assertIn("criteres › licence › option_a", self.erreur(decision))
                self.assertIn(attendu, self.erreur(decision))

    def test_notes_et_options_doivent_correspondre(self):
        decision = decision_ok()
        del decision["criteres"]["dynamisme"]["notes"]["option_b"]
        decision["criteres"]["dynamisme"]["notes"]["option_z"] = note(3)
        message = self.erreur(decision)
        self.assertIn("criteres › dynamisme : pas de note pour l'option « option_b »", message)
        self.assertIn("criteres › dynamisme : option « option_z » inconnue", message)

    def test_note_eliminatoire_hors_echelle(self):
        decision = decision_ok()
        decision["criteres"]["licence"]["note_eliminatoire"] = 0
        self.assertIn("« note_eliminatoire » doit être une note de 1 à 5", self.erreur(decision))

    def test_toutes_les_erreurs_listees_ensemble(self):
        decision = decision_ok(question="", commits_sur_jours=0)
        message = self.erreur(decision)
        self.assertIn("« question »", message)
        self.assertIn("« commits_sur_jours »", message)


# --- La matrice : totaux et critères éliminatoires --------------------------

class TestEvaluerOptions(unittest.TestCase):

    def test_totaux_ponderes_sur_le_maximum(self):
        resultats = radar.evaluer_options(decision_ok())
        self.assertEqual(resultats["option_a"], {"total": 69, "maximum": 80, "pourcentage": 86, "eliminee_par": []})
        self.assertEqual(resultats["option_b"], {"total": 60, "maximum": 80, "pourcentage": 75, "eliminee_par": []})
        self.assertEqual(radar.meilleure_option(resultats), "option_a")

    def test_option_eliminee_par_un_critere_eliminatoire(self):
        decision = decision_ok()
        decision["criteres"]["licence"]["notes"]["option_a"]["note"] = 1    # 1 ≤ note_eliminatoire
        decision["criteres"]["cout_total"]["notes"]["option_b"]["note"] = 1  # B baisse : A = 57, B = 54
        resultats = radar.evaluer_options(decision)
        self.assertGreater(resultats["option_a"]["total"], resultats["option_b"]["total"])
        self.assertEqual(resultats["option_a"]["eliminee_par"], ["licence"])
        self.assertEqual(radar.meilleure_option(resultats), "option_b")     # A éliminée malgré un meilleur total
        lignes = radar.conclusion(decision, resultats, "option_b")
        self.assertIn("⛔ « Garder l'outil A » est éliminée : note éliminatoire en Licence", lignes)

    def test_au_dessus_de_la_note_eliminatoire_pas_eliminee(self):
        decision = decision_ok()
        decision["criteres"]["licence"]["notes"]["option_a"]["note"] = 2
        self.assertEqual(radar.evaluer_options(decision)["option_a"]["eliminee_par"], [])

    def test_egalite_et_toutes_eliminees(self):
        decision = decision_ok()
        for nom in decision["criteres"]:
            decision["criteres"][nom]["notes"]["option_b"] = dict(decision["criteres"][nom]["notes"]["option_a"])
        resultats = radar.evaluer_options(decision)
        self.assertIsNone(radar.meilleure_option(resultats))
        self.assertIn("Égalité : la matrice ne départage pas les options.", radar.conclusion(decision, resultats, None))
        for ident in ("option_a", "option_b"):
            decision["criteres"]["licence"]["notes"][ident]["note"] = 1
        resultats = radar.evaluer_options(decision)
        self.assertIsNone(radar.meilleure_option(resultats))
        self.assertIn("Aucune option ne passe les critères éliminatoires.", radar.conclusion(decision, resultats, None))

    def test_conclusion_avec_ecart(self):
        resultats = radar.evaluer_options(decision_ok())
        self.assertEqual(radar.conclusion(decision_ok(), resultats, "option_a"),
                         ["Option la mieux notée : « Garder l'outil A », 69 / 80 (86 %), +9 points d'écart."])


# --- Les chiffres bruts gh api ---------------------------------------------

class TestChiffresDepot(unittest.TestCase):

    def setUp(self):
        self.github = FauxGitHub()
        patch = mock.patch.object(radar, "gh_api", side_effect=self.github)
        patch.start()
        self.addCleanup(patch.stop)

    def test_depot_actif_avec_licence_et_plusieurs_pages(self):
        c = radar.chiffres_depot("exemple/outil-b", 90)
        self.assertEqual(c["releases"], 130)                      # 2 pages, brouillon exclu
        self.assertEqual(c["contributeurs"], 69)
        self.assertEqual(c["commits_recents"], 3)
        self.assertEqual(c["licence"], "MIT")
        self.assertEqual(c["cree_le"], "2016-09-07")
        self.assertEqual(c["dernier_push"], "2026-08-10")
        self.assertEqual((c["etoiles"], c["issues_ouvertes"], c["archive"], c["prive"]), (7531, 76, False, False))
        self.assertEqual(c["derniere_version"][1], "2026-08-28")   # la plus récente publiée
        releases = [a for a in self.github.appels if "/releases" in a]
        self.assertEqual(releases, ["repos/exemple/outil-b/releases?per_page=100&page=1",
                                    "repos/exemple/outil-b/releases?per_page=100&page=2"])

    def test_depot_sans_licence_ni_release_ni_contributeur(self):
        c = radar.chiffres_depot("exemple/outil-a", 90)
        self.assertIsNone(c["licence"])            # license: null
        self.assertEqual(c["releases"], 0)
        self.assertIsNone(c["derniere_version"])
        self.assertEqual(c["contributeurs"], 0)    # réponse vide (204)
        self.assertEqual(c["commits_recents"], 6)
        self.assertTrue(c["prive"])

    def test_fenetre_des_commits(self):
        radar.chiffres_depot("exemple/outil-a", 30)
        [appel] = [a for a in self.github.appels if "/commits" in a]
        depuis = urllib.parse.parse_qs(urllib.parse.urlsplit(appel).query)["since"][0]
        ecart = datetime.now(timezone.utc) - datetime.strptime(depuis, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        self.assertAlmostEqual(ecart.total_seconds(), 30 * 86400, delta=120)
        self.assertTrue(appel.startswith("repos/exemple/outil-a/commits?since="))

    def test_reponse_inattendue(self):
        with mock.patch.object(radar, "gh_api", return_value=["pas un dépôt"]):
            with self.assertRaises(radar.ErreurSource):
                radar.chiffres_depot("exemple/outil-a", 90)


class TestGhApiReponseVide(unittest.TestCase):

    def test_reponse_vide_donne_none(self):
        reponse = radar.subprocess.CompletedProcess(args=[], returncode=0, stdout="\n", stderr="")
        with mock.patch.object(radar.subprocess, "run", return_value=reponse):
            self.assertIsNone(radar.gh_api("repos/exemple/vide/contributors"))


# --- Les infos de veille liées à la question --------------------------------

class TestInfosDeLaQuestion(unittest.TestCase):

    def test_filtre_et_tri(self):
        items = [fiche("Un outil-B plus rapide", 3, "2026-10-20"),
                 fiche("Rien à voir", 6),
                 fiche("outil-b v2.0", 6, "2026-10-01", source="Dépôt GitHub officiel"),
                 fiche("Stockage local : retour d'expérience", None, "2026-10-27", statut=None),
                 fiche("outil-b v2.1", 6, "2026-10-15", source="Dépôt GitHub officiel")]
        infos = radar.infos_de_la_question(items, DECISION, {})
        self.assertEqual([i["titre"] for i in infos], ["outil-b v2.1", "outil-b v2.0", "Un outil-B plus rapide",
                                                       "Stockage local : retour d'expérience"])


# --- La commande decide de bout en bout --------------------------------------

class TestCommandeDecide(unittest.TestCase):

    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        self.items = self.dossier / "data" / "items.json"
        self.config = self.dossier / "radar.config.yaml"
        self.decision = self.dossier / "decision.md"
        for nom, valeur in [("DOSSIER", self.dossier), ("FICHIER_CONFIG", self.config),
                            ("FICHIER_ITEMS", self.items), ("FICHIER_PAGES", self.dossier / "data" / "pages.json"),
                            ("FICHIER_DECISION", self.decision)]:
            self.patcher(radar, nom, valeur)
        self.patcher(radar, "aujourdhui", return_value=REF)
        self.patcher(radar.subprocess, "run", side_effect=AssertionError("vrai gh interdit"))
        self.patcher(radar.urllib.request, "urlopen", side_effect=AssertionError("appel réseau interdit"))
        self.github = FauxGitHub()
        self.patcher(radar, "gh_api", side_effect=self.github)
        self.ecrire_config(config_ok())
        self.items.parent.mkdir(parents=True)
        self.items.write_text(json.dumps([
            fiche("outil-b v2.1", 6, "2026-10-15", url="https://github.com/exemple/outil-b/releases/v2.1",
                  source="Dépôt GitHub officiel"),
            fiche("Show HN: outil-B | stockage", 2, "2026-10-27", statut="ecartee", url="https://exemple.org/show"),
            fiche("Stockage [local] | fichiers", 4, "2026-10-26", url="https://exemple.org/local"),
            fiche("Hors sujet", 6),
        ], ensure_ascii=False), encoding="utf-8")

    def patcher(self, cible, nom, valeur=mock.DEFAULT, **options):
        patch = mock.patch.object(cible, nom, valeur, **options)
        objet = patch.start()
        self.addCleanup(patch.stop)
        return objet

    def ecrire_config(self, config):
        self.config.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def lancer(self):
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            radar.commande_decide(argparse.Namespace())
        return sortie.getvalue(), self.decision.read_text(encoding="utf-8")

    def test_les_six_sections(self):
        _, md = self.lancer()
        for titre in ("# Décision · Garder l'outil A ou passer à l'outil B ?", "## 1. La question et le contexte",
                      "## 2. Les options comparées", "## 3. Ce que dit la veille",
                      "## 4. Chiffres bruts (gh api, relevés le 2026-10-28)",
                      "## 5. Matrice de décision (poids 1 à 3, notes 1 à 5)",
                      "### Justification de chaque note", "## 6. Impact"):
            self.assertIn(titre, md)
        self.assertLess(md.index("## 1."), md.index("## 6."))

    def test_contexte_besoins_et_options(self):
        _, md = self.lancer()
        self.assertIn("Le contexte de la question.", md)
        self.assertIn("- rester local\n- 0 € en plus", md)
        self.assertIn("| 1 | Garder l'outil A | [exemple/outil-a](https://github.com/exemple/outil-a) |", md)
        self.assertIn("| 2 | Passer à l'outil B | [exemple/outil-b](https://github.com/exemple/outil-b) |", md)

    def test_veille_filtree_triee_et_limitee(self):
        _, md = self.lancer()
        self.assertIn("3 info(s) de items.json touchent la question (2 retenue(s)), les 2 plus fiables :", md)
        self.assertIn("| 6 | retenue | 2026-10-15 | [outil-b v2.1](https://github.com/exemple/outil-b/releases/v2.1) "
                      "| Dépôt GitHub officiel |", md)
        # « | » échappé (sinon il couperait la case du tableau), crochets remplacés dans le lien
        self.assertIn("| 4 | retenue | 2026-10-26 | [Stockage (local) \\| fichiers](https://exemple.org/local) |", md)
        self.assertNotIn("Show HN", md)       # 3e : au-delà de infos_max
        self.assertNotIn("Hors sujet", md)    # ne touche pas la question

    def test_chiffres_bruts(self):
        _, md = self.lancer()
        self.assertIn("| Dépôt | [exemple/outil-a](https://github.com/exemple/outil-a) (dépôt privé) | "
                      "[exemple/outil-b](https://github.com/exemple/outil-b) |", md)
        self.assertIn("| Créé le | 2026-10-28 | 2016-09-07 |", md)
        self.assertIn("| Versions publiées (releases) | 0 | 130 |", md)
        self.assertIn("| Dernière version | aucune | v1.27 (2026-08-28) |", md)
        self.assertIn("| Contributeurs | 0 | 69 |", md)
        self.assertIn("| Commits sur 90 jours | 6 | 3 |", md)
        self.assertIn("| Licence | aucune licence déclarée (license: null) | MIT |", md)

    def test_matrice_totaux_et_justifications(self):
        _, md = self.lancer()
        self.assertIn("| Maturité | 2 | 3 / 5 → 6 | 5 / 5 → 10 |", md)
        self.assertIn("| Licence (éliminatoire si ≤ 1) | 3 | 5 / 5 → 15 | 5 / 5 → 15 |", md)
        self.assertIn("| Coût total | 3 | 5 / 5 → 15 | 3 / 5 → 9 |", md)
        self.assertIn("| dynamisme | 1 | 2 / 5 → 2 | 3 / 5 → 3 |", md)   # libellé par défaut
        self.assertIn("| **Total pondéré** | **16** | **69 / 80 (86 %)** | **60 / 80 (75 %)** |", md)
        self.assertIn("**Option la mieux notée : « Garder l'outil A », 69 / 80 (86 %), +9 points d'écart.**", md)
        self.assertIn("- Garder l'outil A : 3 / 5. un chiffre vérifié ([source](https://exemple.org/source), "
                      "consultée le 2026-10-27)", md)

    def test_impact_rempli_ou_a_remplir(self):
        _, md = self.lancer()
        impact = md[md.index("## 6. Impact"):]
        self.assertIn("### Garder l'outil A\n\n- **Périmètre** : Rien ne change.\n- **Budget** : 0 €\n"
                      "- **Délais** : _à remplir_\n- **Anticipation** : _à remplir_", impact)
        self.assertIn("### Passer à l'outil B\n\n- **Périmètre** : _à remplir_", impact)

    def test_resume_dans_le_terminal(self):
        sortie, _ = self.lancer()
        self.assertIn("⚖️  Garder l'outil A ou passer à l'outil B ?", sortie)
        self.assertIn("   Garder l'outil A : 69 / 80 (86 %)", sortie)
        self.assertIn("      exemple/outil-b · créé le 2016-09-07, 130 release(s), 69 contributeur(s), "
                      "3 commit(s) sur 90 j, licence MIT", sortie)
        self.assertIn("licence non déclarée", sortie)
        self.assertIn("   → Option la mieux notée : « Garder l'outil A »", sortie)
        self.assertIn("   🔎 3 info(s) de veille touchent la question (2 retenue(s))", sortie)
        self.assertIn("✅ decision.md écrit", sortie)

    def test_panne_gh_pour_une_option(self):
        del self.github.depots["exemple/outil-a"]

        def avec_panne(chemin):
            if "outil-a" in chemin:
                raise radar.ErreurSource("gh api a échoué : HTTP 404")
            return self.github(chemin)
        self.patcher(radar, "gh_api", side_effect=avec_panne)
        sortie, md = self.lancer()
        self.assertIn("❌ exemple/outil-a : gh api a échoué : HTTP 404", sortie)
        self.assertIn("| Dépôt | ❌ gh api a échoué : HTTP 404 | [exemple/outil-b]", md)
        self.assertIn("| Créé le | indisponible | 2016-09-07 |", md)
        self.assertIn("| **Total pondéré** |", md)   # la matrice reste calculée

    def test_items_inchanges_et_sans_items(self):
        avant = self.items.read_bytes()
        self.lancer()
        self.assertEqual(self.items.read_bytes(), avant)
        self.items.unlink()
        sortie, md = self.lancer()
        self.assertIn("0 info(s) de items.json touchent la question", md)
        self.assertIn("lancez « radar collect » puis « radar score »", md)

    def test_config_invalide_rien_n_est_ecrit(self):
        decision = decision_ok()
        del decision["criteres"]["licence"]
        self.ecrire_config(config_ok(decision))
        with self.assertRaises(SystemExit):
            self.lancer()
        self.assertFalse(self.decision.exists())
        self.assertEqual(self.github.appels, [])   # aucun appel gh avant validation

    def test_ligne_de_commande(self):
        appel = self.patcher(radar, "commande_decide")
        with mock.patch.object(sys, "argv", ["radar", "decide"]):
            radar.main()
        appel.assert_called_once()


if __name__ == "__main__":
    unittest.main()
