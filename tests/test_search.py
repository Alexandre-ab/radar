"""Tests de la brique 4 (étiquettes, statut, radar search), sans réseau
et sans toucher aux vrais fichiers de data/.

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
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest import mock

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import radar  # noqa: E402

VRAIS_FICHIERS = [Path(radar.FICHIER_ITEMS), Path(radar.FICHIER_PAGES), Path(radar.FICHIER_CONFIG)]
empreintes_avant = {}

REF = date(2026, 10, 28)
SUJETS = ["claude code", "codex", "MCP", "express"]


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


SOURCES = [
    {"type": "releases", "depot": "anthropics/claude-code", "nom": "Dépôt GitHub officiel",
     "categorie": "officielle", "type_veille": "technologique", "produit": "Claude Code"},
    {"type": "hackernews", "requete": "claude code", "nom": "Hacker News",
     "categorie": "communaute", "type_veille": "technologique"},
    {"type": "failles", "paquet": "express", "ecosysteme": "npm", "nom": "Base OSV",
     "categorie": "institution", "type_veille": "securite"},
]

REGLES = {
    "categorie": {"officielle": 3, "institution": 2, "communaute": 1, "social": 0},
    "fraicheur": {"jours": 183, "points": 1},
    "auteur_identifie": {"points": 1, "si": [{"sources": ["Dépôt GitHub officiel"]}]},
    "source_ou_methode_citee": {"points": 1, "si": [{"sources": ["Base OSV"]}]},
    "recoupee": {"points": 1, "sujets": SUJETS},
    "biais_interet": {"points": -2, "si": [{"titre_contient": ["Show HN"]}]},
    "version_de_test": {"points": -1, "si": [{"titre_contient": ["alpha", "beta", "-rc"]}]},
}

ETIQUETTES = {
    "cli-ia": {"si": [{"titre_contient": ["claude code", "codex"]}]},
    "claude-code": {"si": [{"titre_contient": ["claude code"]}]},
    "codex": {"si": [{"titre_contient": ["codex"]}]},
    "securite": {"si": [{"types_veille": ["securite"]}, {"titre_contient": ["leak", "XSS"]}]},
    "communaute": {"si": [{"categories": ["communaute", "social"]}]},
}


def config_ok(**modifs):
    config = {"mots_cles": SUJETS, "ignorer": ["crypto"], "sources": copy.deepcopy(SOURCES),
              "regles_score": copy.deepcopy(REGLES), "seuil": 4, "etiquettes": copy.deepcopy(ETIQUETTES)}
    config.update(modifs)
    return config


def fiche(titre, source="Hacker News", url="https://exemple.org/a", publie_le="2026-10-27", **modifs):
    valeurs = {"titre": titre, "url": url, "publie_le": publie_le, "collecte_le": "2026-10-28",
               "source": source, "type_veille": "technologique",
               "etiquettes": None, "fiabilite": None, "statut": None}
    valeurs.update(modifs)
    return valeurs


class DossierTemporaire(unittest.TestCase):
    """Config, items.json et pages.json dans un dossier temporaire ; réseau interdit ; date figée."""

    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        self.items = self.dossier / "data" / "items.json"
        self.config = self.dossier / "radar.config.yaml"
        for nom, valeur in [("DOSSIER", self.dossier), ("FICHIER_CONFIG", self.config),
                            ("FICHIER_ITEMS", self.items), ("FICHIER_PAGES", self.dossier / "data" / "pages.json")]:
            self.patcher(radar, nom, valeur)
        self.patcher(radar, "aujourdhui", return_value=REF)
        self.patcher(radar.subprocess, "run", side_effect=AssertionError("appel à gh interdit"))
        self.patcher(radar.urllib.request, "urlopen", side_effect=AssertionError("appel réseau interdit"))
        self.ecrire_config(config_ok())

    def patcher(self, cible, nom, valeur=mock.DEFAULT, **options):
        patch = mock.patch.object(cible, nom, valeur, **options)
        objet = patch.start()
        self.addCleanup(patch.stop)
        return objet

    def ecrire_config(self, config):
        # sort_keys=False : l'ordre des règles et des étiquettes est celui de la config.
        self.config.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def ecrire_items(self, items):
        self.items.parent.mkdir(parents=True, exist_ok=True)
        self.items.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")

    def lire_items(self):
        return json.loads(self.items.read_text(encoding="utf-8"))

    def capturer(self, fonction, *args):
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            fonction(*args)
        return sortie.getvalue()


# --- La fiche : etiquettes et statut -----------------------------------------

class TestFicheBrique4(unittest.TestCase):

    def test_etiquettes_acceptees(self):
        for valeur in (None, [], ["cli-ia"], ["cli-ia", "codex"]):
            with self.subTest(valeur=valeur):
                self.assertTrue(radar.fiche_valide(fiche("x", etiquettes=valeur)))

    def test_etiquettes_refusees(self):
        for valeur in ("cli-ia", [""], ["  "], [1], ["ok", None], {"cli-ia": True}):
            with self.subTest(valeur=valeur):
                self.assertFalse(radar.fiche_valide(fiche("x", etiquettes=valeur)))

    def test_statut(self):
        for valeur in (None, "retenue", "ecartee"):
            with self.subTest(valeur=valeur):
                self.assertTrue(radar.fiche_valide(fiche("x", statut=valeur)))
        for valeur in ("Retenue", "écartée", "", True, 1):
            with self.subTest(valeur=valeur):
                self.assertFalse(radar.fiche_valide(fiche("x", statut=valeur)))


# --- La configuration : seuil, etiquettes, type_veille ----------------------

class TestLireArchivage(unittest.TestCase):

    def erreur(self, config):
        with self.assertRaises(SystemExit) as e:
            radar.lire_archivage(config)
        return str(e.exception.code)

    def test_vraie_config_du_projet_valide(self):
        # Lecture seule du vrai radar.config.yaml.
        seuil, etiquettes, type_veille_par_source = radar.lire_archivage(radar.charger_config())
        self.assertTrue(radar.est_entier(seuil))
        self.assertGreaterEqual(len(etiquettes), 1)
        self.assertTrue(set(type_veille_par_source.values()) <= set(radar.TYPES_VEILLE))

    def test_etiquettes_du_vrai_items_json_toutes_declarees(self):
        # Lecture seule : chaque étiquette déjà posée appartient à la liste de la config.
        declarees = set(radar.lire_archivage(radar.charger_config())[1])
        if radar.FICHIER_ITEMS.exists():
            for item in json.loads(radar.FICHIER_ITEMS.read_text(encoding="utf-8")):
                self.assertTrue(set(item["etiquettes"] or []) <= declarees, item["titre"])

    def test_config_de_test_valide(self):
        seuil, etiquettes, type_veille_par_source = radar.lire_archivage(config_ok())
        self.assertEqual(seuil, 4)
        self.assertEqual(list(etiquettes), list(ETIQUETTES))
        self.assertEqual(type_veille_par_source, {"Dépôt GitHub officiel": "technologique",
                                                  "Hacker News": "technologique", "Base OSV": "securite"})

    def test_seuil_invalide(self):
        for valeur in (None, True, "4", 4.5):
            with self.subTest(valeur=valeur):
                self.assertIn("« seuil » doit être un nombre entier", self.erreur(config_ok(seuil=valeur)))

    def test_rubrique_etiquettes_absente_ou_vide(self):
        for valeur in (None, {}, ["cli-ia", "codex"]):
            with self.subTest(valeur=valeur):
                self.assertIn("« etiquettes » est absente ou vide", self.erreur(config_ok(etiquettes=valeur)))

    def test_etiquette_mal_ecrite(self):
        for etiquette, attendu in [(None, "doit contenir « si: »"),
                                   ({"si": []}, "« si » doit contenir au moins un cas"),
                                   ({"si": [{"mots": ["x"]}]}, "condition « mots » inconnue"),
                                   ({"si": [{"types_veille": ["tech"]}]}, "« types_veille » n'accepte que"),
                                   ({"si": [{"titre_contient": "codex"}]}, "doit être une liste de textes")]:
            with self.subTest(etiquette=etiquette):
                etiquettes = copy.deepcopy(ETIQUETTES)
                etiquettes["codex"] = etiquette
                self.assertIn("etiquettes › codex", self.erreur(config_ok(etiquettes=etiquettes)))
                self.assertIn(attendu, self.erreur(config_ok(etiquettes=etiquettes)))

    def test_type_veille_de_source_manquant_ou_incoherent(self):
        sources = copy.deepcopy(SOURCES)
        del sources[1]["type_veille"]
        self.assertIn("source « Hacker News » : type_veille « None » manquant", self.erreur(config_ok(sources=sources)))
        sources = copy.deepcopy(SOURCES) + [dict(SOURCES[0], depot="openai/codex", type_veille="concurrentielle")]
        self.assertIn("deux sources s'appellent « Dépôt GitHub officiel » mais n'ont pas le même type_veille",
                      self.erreur(config_ok(sources=sources)))


# --- L'attribution des étiquettes --------------------------------------------

class TestAttribuerEtiquettes(unittest.TestCase):

    def test_ordre_de_la_config_et_plusieurs_etiquettes(self):
        une = fiche("Cindy runs Claude Code and Codex as harnesses")
        self.assertEqual(radar.attribuer_etiquettes(une, ETIQUETTES, "communaute"),
                         ["cli-ia", "claude-code", "codex", "communaute"])

    def test_aucune_etiquette(self):
        self.assertEqual(radar.attribuer_etiquettes(fiche("Mes voyages"), ETIQUETTES, "officielle"), [])

    def test_types_veille_et_categories(self):
        faille = fiche("express · GHSA-1 : open redirect", source="Base OSV", type_veille="securite")
        self.assertEqual(radar.attribuer_etiquettes(faille, ETIQUETTES, "institution"), ["securite"])
        self.assertEqual(radar.attribuer_etiquettes(fiche("Weir: catch credential leaks"), ETIQUETTES, "communaute"),
                         ["securite", "communaute"])

    def test_seulement_des_etiquettes_declarees(self):
        une = fiche("Claude Code, Codex, MCP et une faille XSS")
        self.assertTrue(set(radar.attribuer_etiquettes(une, ETIQUETTES, "social")) <= set(ETIQUETTES))


# --- collect pose les étiquettes ----------------------------------------------

class TestCollectPoseLesEtiquettes(DossierTemporaire):

    def test_nouvelles_fiches_etiquetees_anciennes_inchangees(self):
        ancienne = fiche("Claude Code v1", source="Dépôt GitHub officiel", url="https://github.com/r/v1")
        self.ecrire_items([ancienne])
        config = config_ok(sources=[SOURCES[0]])
        self.ecrire_config(config)
        release = {"tag_name": "v2", "html_url": "https://github.com/r/v2",
                   "published_at": "2026-10-27T10:00:00Z", "body": ""}
        self.patcher(radar, "gh_api", return_value=[release])
        self.capturer(radar.commande_collect, None)
        par_url = {i["url"]: i for i in self.lire_items()}
        self.assertEqual(par_url["https://github.com/r/v2"]["etiquettes"], ["cli-ia", "claude-code"])
        self.assertIsNone(par_url["https://github.com/r/v1"]["etiquettes"])  # score s'en chargera
        self.assertIsNone(par_url["https://github.com/r/v2"]["statut"])      # posé par score

    def test_etiquettes_mal_ecrites_arretent_collect_avant_le_reseau(self):
        self.ecrire_config(config_ok(etiquettes={"codex": {"si": [{"mots": ["codex"]}]}}))
        faux_gh = self.patcher(radar, "gh_api", return_value=[])
        with self.assertRaises(SystemExit) as e:
            self.capturer(radar.commande_collect, None)
        self.assertIn("les étiquettes ne peuvent pas être posées", str(e.exception.code))
        faux_gh.assert_not_called()


# --- score pose étiquettes, statut et type_veille ----------------------------

class TestScorePoseArchivage(DossierTemporaire):

    ITEMS = [
        fiche("Claude Code v2.1.312", source="Dépôt GitHub officiel", url="https://github.com/r/312",
              publie_le="2026-10-27"),                                           # 3+1+1+1 = 6
        fiche("Codex CLI rust-v0.166.0-alpha.5", source="Dépôt GitHub officiel", url="https://github.com/o/a5",
              publie_le="2026-10-28"),                                           # 3+1+1-1 = 4 (pas recoupée)
        fiche("DeltaDB now has a Claude Code plugin", url="https://delta.dev/a"),  # 1+1+1 = 3
        fiche("express · GHSA-1 : XSS", source="Base OSV", url="https://osv.dev/1",
              publie_le="2024-09-10", type_veille=None),                         # 2+1 = 3
    ]

    def lancer(self, top=10):
        return self.capturer(radar.commande_score, argparse.Namespace(top=top))

    def test_plus_aucun_null_apres_score(self):
        self.ecrire_items(self.ITEMS)
        sortie = self.lancer()
        for item in self.lire_items():
            self.assertTrue(all(item[champ] is not None for champ in radar.CHAMPS_FICHE), item)
            self.assertTrue(radar.fiche_valide(item))
        self.assertNotIn("gardent un champ vide", sortie)

    def test_statut_selon_le_seuil(self):
        self.ecrire_items(self.ITEMS)
        self.lancer()
        self.assertEqual([(i["fiabilite"], i["statut"]) for i in self.lire_items()],
                         [(6, "retenue"), (4, "retenue"), (3, "ecartee"), (3, "ecartee")])  # 4 = seuil atteint

    def test_seuil_atteint_compte_comme_retenue(self):
        self.ecrire_items(self.ITEMS)
        self.ecrire_config(config_ok(seuil=3))
        self.lancer()
        self.assertEqual([i["statut"] for i in self.lire_items()], ["retenue", "retenue", "retenue", "retenue"])
        self.ecrire_config(config_ok(seuil=5))
        self.lancer()
        self.assertEqual([i["statut"] for i in self.lire_items()], ["retenue", "ecartee", "ecartee", "ecartee"])

    def test_version_de_test_retire_un_point(self):
        self.ecrire_items(self.ITEMS)
        sortie = self.lancer()
        self.assertIn("      -1  version de test (« alpha » dans le titre)", sortie)

    def test_etiquettes_et_type_veille_recalcules(self):
        ancienne = dict(self.ITEMS[2], etiquettes=["etiquette-supprimee"], statut="retenue")
        self.ecrire_items([self.ITEMS[0], ancienne, self.ITEMS[3]])
        self.lancer()
        items = self.lire_items()
        self.assertEqual(items[0]["etiquettes"], ["cli-ia", "claude-code"])
        self.assertEqual(items[1]["etiquettes"], ["cli-ia", "claude-code", "communaute"])  # l'ancienne a disparu
        self.assertEqual(items[1]["statut"], "ecartee")
        self.assertEqual(items[2]["type_veille"], "securite")       # repris de la source
        self.assertEqual(items[2]["etiquettes"], ["securite"])      # grâce à types_veille

    def test_affichage_et_bilan(self):
        self.ecrire_items(self.ITEMS)
        sortie = self.lancer()
        self.assertIn("    retenue · étiquettes : cli-ia, claude-code", sortie)
        self.assertIn("    ecartee · étiquettes : securite", sortie)
        self.assertIn("étiquettes et statut posés : 2 retenues, 2 écartées (seuil : 4)", sortie)

    def test_seuil_absent_rien_n_est_ecrit(self):
        self.ecrire_items(self.ITEMS)
        avant = self.items.read_text(encoding="utf-8")
        config = config_ok()
        del config["seuil"]
        self.ecrire_config(config)
        with self.assertRaises(SystemExit):
            self.lancer()
        self.assertEqual(self.items.read_text(encoding="utf-8"), avant)


# --- radar search -------------------------------------------------------------

class TestSearch(DossierTemporaire):

    ITEMS = [
        fiche("Codex CLI rust-v0.165.0", source="Dépôt GitHub officiel", url="https://github.com/o/165",
              publie_le="2026-10-27", etiquettes=["cli-ia", "codex"], fiabilite=6, statut="retenue"),
        fiche("Codex CLI rust-v0.166.0-alpha.5", source="Dépôt GitHub officiel", url="https://github.com/o/a5",
              publie_le="2026-10-28", etiquettes=["cli-ia", "codex"], fiabilite=5, statut="retenue"),
        fiche("Paradev: one workspace for Claude Code, Codex", url="https://paradev.com",
              publie_le="2026-10-26", etiquettes=["cli-ia", "claude-code", "codex"], fiabilite=3, statut="ecartee"),
        fiche("Weir - catch credential leaks", url="https://github.com/w/weir",
              publie_le="2026-10-27", etiquettes=["securite"], fiabilite=0, statut="ecartee"),
        fiche("Codex plugin pas encore noté", url="https://exemple.org/n", publie_le="2026-10-28"),
        fiche("Release v1.2.3 de codex", url="https://exemple.org/v", publie_le="2026-10-25",
              etiquettes=["cli-ia"], fiabilite=6, statut="retenue"),
    ]

    def chercher(self, *mots, retenues=False):
        return self.capturer(radar.commande_search, argparse.Namespace(mot=list(mots), retenues=retenues))

    def titres(self, sortie):
        lignes = sortie.splitlines()
        return [ligne.split(". ", 1)[1] for ligne in lignes if ligne[:3].strip().rstrip(".").isdigit()]

    def test_titre_sans_tenir_compte_des_majuscules_et_tri(self):
        self.ecrire_items(self.ITEMS)
        sortie = self.chercher("CODEX")
        # score décroissant, puis date décroissante ; non notée en dernier
        self.assertEqual(self.titres(sortie), ["Codex CLI rust-v0.165.0", "Release v1.2.3 de codex",
                                               "Codex CLI rust-v0.166.0-alpha.5",
                                               "Paradev: one workspace for Claude Code, Codex",
                                               "Codex plugin pas encore noté"])
        self.assertIn("🔎 5 info(s) contiennent « CODEX » (titre ou étiquettes)", sortie)

    def test_recherche_dans_les_etiquettes(self):
        self.ecrire_items(self.ITEMS)
        self.assertEqual(self.titres(self.chercher("securite")), ["Weir - catch credential leaks"])
        self.assertEqual(self.titres(self.chercher("claude-code")),
                         ["Paradev: one workspace for Claude Code, Codex"])

    def test_plusieurs_mots_forment_une_expression(self):
        self.ecrire_items(self.ITEMS)
        self.assertEqual(self.titres(self.chercher("claude", "code")),
                         ["Paradev: one workspace for Claude Code, Codex"])

    def test_option_retenues(self):
        self.ecrire_items(self.ITEMS)
        sortie = self.chercher("codex", retenues=True)
        self.assertEqual(self.titres(sortie), ["Codex CLI rust-v0.165.0", "Release v1.2.3 de codex",
                                               "Codex CLI rust-v0.166.0-alpha.5"])
        self.assertIn("retenues seulement", sortie)
        self.assertIn("(2 info(s) écartée(s) ou non notée(s) masquée(s) par --retenues)", sortie)

    def test_affichage_complet(self):
        self.ecrire_items(self.ITEMS)
        sortie = self.chercher("weir")
        self.assertIn(" 1. Weir - catch credential leaks", sortie)
        self.assertIn("    0 point · ecartee · étiquettes : securite", sortie)
        self.assertIn("    Hacker News · publiée le 2026-10-27", sortie)
        self.assertIn("    https://github.com/w/weir", sortie)

    def test_info_pas_encore_notee(self):
        self.ecrire_items(self.ITEMS)
        sortie = self.chercher("pas encore")
        self.assertIn("pas encore notée · statut à calculer (radar score) · étiquettes à calculer", sortie)

    def test_aucun_resultat(self):
        self.ecrire_items(self.ITEMS)
        sortie = self.chercher("kubernetes")
        self.assertIn("Aucune info ne contient « kubernetes » dans son titre ou ses étiquettes.", sortie)

    def test_mot_vide(self):
        self.ecrire_items(self.ITEMS)
        with self.assertRaises(SystemExit) as e:
            self.chercher("  ")
        self.assertIn("Donnez un mot à chercher", str(e.exception.code))

    def test_search_n_ecrit_rien_et_n_a_pas_besoin_de_la_config(self):
        self.ecrire_items(self.ITEMS)
        avant = self.items.read_bytes()
        self.config.unlink()
        self.chercher("codex")
        self.assertEqual(self.items.read_bytes(), avant)

    def test_ligne_de_commande(self):
        appel = self.patcher(radar, "commande_search")
        with mock.patch.object(sys, "argv", ["radar", "search", "claude", "code", "--retenues"]):
            radar.main()
        args = appel.call_args.args[0]
        self.assertEqual((args.mot, args.retenues), (["claude", "code"], True))


class TestRienEnDurDansRadarPy(unittest.TestCase):
    """Règle d'AGENTS.md : aucune source ni aucun mot-clé de radar.config.yaml écrit dans
    radar.py, y compris dans les docstrings, commentaires et messages d'aide."""

    def test_aucune_valeur_de_la_config_dans_radar_py(self):
        config = yaml.safe_load(Path(radar.FICHIER_CONFIG).read_text(encoding="utf-8"))  # lecture seule
        interdites = {mot for mot in config["mots_cles"]}
        for source in config["sources"]:
            interdites |= {str(source[champ]) for champ in ("depot", "url", "paquet", "nom", "produit", "requete", "version")
                           if champ in source}
        # Brique 5 : les valeurs de la rubrique decision (pas les noms des 7 critères du kit,
        # qui sont le schéma, ni leurs libellés d'affichage).
        decision = config["decision"]
        interdites |= {decision["question"], decision.get("contexte", "")} | set(decision["besoins"]) - {""}
        for cas in decision["filtre"]["si"]:
            for valeurs in cas.values():
                interdites |= set(valeurs)
        for ident, option in decision["options"].items():
            interdites |= {ident, option["nom"], option["depot"]} | set((option.get("impact") or {}).values())
        for critere in decision["criteres"].values():
            for note in critere["notes"].values():
                interdites |= {note["chiffre"], note["source"]}
        interdites.discard("")
        self.assertTrue(interdites)  # la config a bien été lue
        lignes = Path(radar.__file__).read_text(encoding="utf-8").splitlines()
        # Recherche stricte : sous-chaîne, majuscules et minuscules confondues.
        trouvees = [f"radar.py:{numero} « {valeur} » : {ligne.strip()}"
                    for numero, ligne in enumerate(lignes, 1)
                    for valeur in sorted(interdites) if valeur.lower() in ligne.lower()]
        self.assertEqual(trouvees, [], "valeurs de radar.config.yaml écrites dans radar.py :\n" + "\n".join(trouvees))


if __name__ == "__main__":
    unittest.main()
