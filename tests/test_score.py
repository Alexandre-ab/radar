"""Tests de la brique score, sans réseau et sans toucher aux vrais fichiers de data/.

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
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import radar  # noqa: E402

VRAIS_FICHIERS = [Path(radar.FICHIER_ITEMS), Path(radar.FICHIER_PAGES), Path(radar.FICHIER_CONFIG)]
empreintes_avant = {}

REF = date(2026, 10, 28)  # « aujourd'hui » figé pour des tests reproductibles
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
    {"type": "releases", "depot": "anthropics/claude-code", "nom": "Dépôt GitHub officiel", "categorie": "officielle"},
    {"type": "releases", "depot": "openai/codex", "nom": "Dépôt GitHub officiel", "categorie": "officielle"},
    {"type": "hackernews", "requete": "claude code", "nom": "Hacker News", "categorie": "communaute"},
    {"type": "failles", "paquet": "express", "ecosysteme": "npm", "nom": "Base OSV", "categorie": "institution"},
    {"type": "page", "url": "https://exemple.org/cgu", "nom": "Forum", "categorie": "social"},
]

REGLES = {
    "categorie": {"officielle": 3, "institution": 2, "communaute": 1, "social": 0},
    "fraicheur": {"libelle": "récente", "jours": 183, "points": 1},
    "auteur_identifie": {"libelle": "auteur identifié", "points": 1,
                         "si": [{"sources": ["Dépôt GitHub officiel", "Base OSV"]}, {"domaines": ["github.com"]}]},
    "source_ou_methode_citee": {"libelle": "source ou méthode citée", "points": 1,
                                "si": [{"sources": ["Base OSV"]}, {"titre_contient": ["study"]}]},
    "recoupee": {"libelle": "recoupée", "points": 1, "sujets": SUJETS},
    "biais_interet": {"libelle": "biais d'intérêt", "points": -2,
                      "si": [{"titre_contient": ["Show HN", "partenaire"]}, {"url_contient": ["utm_", "?ref="]}]},
    "effet_de_mode": {"libelle": "effet de mode", "points": -1,
                      "si": [{"titre_contient": ["game changer"]},
                             {"categories": ["communaute", "social"], "titre_sans": SUJETS}]},
}


def config_ok(**modifs):
    config = {"mots_cles": SUJETS, "sources": copy.deepcopy(SOURCES), "regles_score": copy.deepcopy(REGLES)}
    config.update(modifs)
    return config


def fiche(titre, source="Hacker News", url="https://exemple.org/a", publie_le="2026-10-27", **modifs):
    valeurs = {"titre": titre, "url": url, "publie_le": publie_le, "collecte_le": "2026-10-28",
               "source": source, "type_veille": "technologique",
               "etiquettes": None, "fiabilite": None, "statut": None}
    valeurs.update(modifs)
    return valeurs


def scorer(une_fiche, items=None, regles=None, ref=REF):
    regles = regles or REGLES
    _, categorie_par_source = radar.lire_regles(config_ok(regles_score=regles))
    recoupements = radar.calculer_recoupements(items or [une_fiche], regles["recoupee"]["sujets"])
    return radar.scorer(une_fiche, regles, categorie_par_source, recoupements, ref)


def phrases(raisons):
    return [phrase for _, phrase in raisons]


# --- La fiche : fiabilite ----------------------------------------------------

class TestFiabiliteDansLaFiche(unittest.TestCase):

    def test_null_ou_entier_accepte(self):
        for valeur in (None, 0, 6, -1):
            with self.subTest(valeur=valeur):
                self.assertTrue(radar.fiche_valide(fiche("Claude Code", fiabilite=valeur)))

    def test_booleen_texte_ou_decimal_refuse(self):
        for valeur in (True, False, "3", 2.5, [3]):
            with self.subTest(valeur=valeur):
                self.assertFalse(radar.fiche_valide(fiche("Claude Code", fiabilite=valeur)))


# --- La configuration : categorie et regles_score ----------------------------

class TestLireRegles(unittest.TestCase):

    def erreur(self, config):
        with self.assertRaises(SystemExit) as e:
            radar.lire_regles(config)
        return str(e.exception.code)

    def test_vraie_config_du_projet_valide(self):
        # Lecture seule du vrai radar.config.yaml : il doit passer la validation.
        regles, categorie_par_source = radar.lire_regles(radar.charger_config())
        for nom in radar.REGLES_OBLIGATOIRES:
            self.assertIn(nom, regles)
        self.assertGreater(len(regles), len(radar.REGLES_OBLIGATOIRES))  # au moins une règle à nous
        self.assertEqual(set(categorie_par_source.values()) - set(radar.CATEGORIES), set())

    def test_config_de_test_valide(self):
        regles, categorie_par_source = radar.lire_regles(config_ok())
        self.assertEqual(list(regles), list(REGLES))
        self.assertEqual(categorie_par_source, {"Dépôt GitHub officiel": "officielle", "Hacker News": "communaute",
                                                "Base OSV": "institution", "Forum": "social"})

    def test_regles_score_absente(self):
        config = config_ok()
        del config["regles_score"]
        self.assertIn("« regles_score » est absente", self.erreur(config))

    def test_regle_obligatoire_absente(self):
        for nom in radar.REGLES_OBLIGATOIRES:
            with self.subTest(nom=nom):
                regles = copy.deepcopy(REGLES)
                del regles[nom]
                self.assertIn(f"la règle « {nom} » est absente", self.erreur(config_ok(regles_score=regles)))

    def test_points_de_categorie(self):
        for modif, attendu in [({"social": None}, "points de « social » manquants"),
                               ({"social": True}, "points de « social » manquants"),
                               ({"social": "0"}, "points de « social » manquants"),
                               ({"blog": 1}, "catégorie « blog » inconnue")]:
            with self.subTest(modif=modif):
                regles = copy.deepcopy(REGLES)
                regles["categorie"].update(modif)
                if modif.get("social", 0) is None:
                    del regles["categorie"]["social"]
                self.assertIn(attendu, self.erreur(config_ok(regles_score=regles)))

    def test_points_non_entiers(self):
        for valeur in (True, "1", 1.5, None):
            with self.subTest(valeur=valeur):
                regles = copy.deepcopy(REGLES)
                regles["biais_interet"]["points"] = valeur
                self.assertIn("biais_interet : « points » doit être un nombre entier",
                              self.erreur(config_ok(regles_score=regles)))

    def test_fraicheur_jours_invalide(self):
        for valeur in (0, -5, "183", True):
            with self.subTest(valeur=valeur):
                regles = copy.deepcopy(REGLES)
                regles["fraicheur"]["jours"] = valeur
                self.assertIn("« jours » doit être un nombre entier positif", self.erreur(config_ok(regles_score=regles)))

    def test_recoupee_sans_sujets(self):
        for valeur in ([], "claude code", [""], None):
            with self.subTest(valeur=valeur):
                regles = copy.deepcopy(REGLES)
                regles["recoupee"]["sujets"] = valeur
                self.assertIn("« sujets » doit être une liste de textes", self.erreur(config_ok(regles_score=regles)))

    def test_cas_mal_ecrits(self):
        for si, attendu in [([], "« si » doit contenir au moins un cas"),
                            (None, "« si » doit contenir au moins un cas"),
                            ([{}], "cas n°1 vide"),
                            ([{"auteurs": ["x"]}], "condition « auteurs » inconnue"),
                            ([{"titre_contient": "Show HN"}], "« titre_contient » doit être une liste de textes"),
                            ([{"sources": ["A"]}, {"categories": ["blog"]}], "cas n°2 : « categories » n'accepte que")]:
            with self.subTest(si=si):
                regles = copy.deepcopy(REGLES)
                regles["biais_interet"]["si"] = si
                self.assertIn(attendu, self.erreur(config_ok(regles_score=regles)))

    def test_categorie_de_source_manquante_ou_inconnue(self):
        for valeur in (None, "officiel", ""):
            with self.subTest(valeur=valeur):
                sources = copy.deepcopy(SOURCES)
                sources[2]["categorie"] = valeur
                self.assertIn("source « Hacker News » : categorie", self.erreur(config_ok(sources=sources)))

    def test_meme_nom_categories_differentes(self):
        sources = copy.deepcopy(SOURCES)
        sources[1]["categorie"] = "communaute"
        self.assertIn("deux sources s'appellent « Dépôt GitHub officiel » mais n'ont pas la même categorie",
                      self.erreur(config_ok(sources=sources)))

    def test_toutes_les_erreurs_listees_ensemble(self):
        regles = copy.deepcopy(REGLES)
        regles["fraicheur"]["jours"] = 0
        regles["recoupee"]["sujets"] = []
        message = self.erreur(config_ok(regles_score=regles))
        self.assertIn("fraicheur", message)
        self.assertIn("recoupee", message)

    def test_un_seul_cas_ecrit_sans_liste(self):
        regles = copy.deepcopy(REGLES)
        regles["biais_interet"]["si"] = {"titre_contient": ["Show HN"]}
        radar.lire_regles(config_ok(regles_score=regles))  # accepté
        _, raisons = scorer(fiche("Show HN: mon outil Claude Code"), regles=regles)
        self.assertIn("biais d'intérêt (« Show HN » dans le titre)", phrases(raisons))


# --- Les conditions d'une règle à cas ----------------------------------------

class TestConditions(unittest.TestCase):

    def vraie(self, condition, valeurs, une_fiche, categorie="communaute"):
        return radar.condition_vraie(condition, valeurs, une_fiche, categorie)

    def test_sources(self):
        self.assertEqual(self.vraie("sources", ["Hacker News"], fiche("x")), "source « Hacker News »")
        self.assertIsNone(self.vraie("sources", ["Base OSV"], fiche("x")))

    def test_categories(self):
        self.assertEqual(self.vraie("categories", ["communaute"], fiche("x")), "source communaute")
        self.assertIsNone(self.vraie("categories", ["officielle"], fiche("x")))

    def test_domaines_et_sous_domaines(self):
        self.assertEqual(self.vraie("domaines", ["github.com"], fiche("x", url="https://github.com/a/b")), "site github.com")
        self.assertEqual(self.vraie("domaines", ["github.com"], fiche("x", url="https://www.GitHub.com/a")), "site github.com")
        self.assertIsNone(self.vraie("domaines", ["github.com"], fiche("x", url="https://notgithub.com/a")))
        self.assertIsNone(self.vraie("domaines", ["github.com"], fiche("x", url="https://exemple.org/github.com")))

    def test_url_contient(self):
        une = fiche("x", url="https://blog.exemple.org/a?utm_source=hn")
        self.assertEqual(self.vraie("url_contient", ["utm_"], une), "« utm_ » dans l'url")
        self.assertIsNone(self.vraie("url_contient", ["affiliate"], une))

    def test_titre_contient_sans_tenir_compte_des_majuscules(self):
        self.assertEqual(self.vraie("titre_contient", ["Show HN"], fiche("show hn: outil")), "« Show HN » dans le titre")
        self.assertIsNone(self.vraie("titre_contient", ["Show HN"], fiche("Ask HN: question")))

    def test_titre_sans(self):
        self.assertIsNone(self.vraie("titre_sans", SUJETS, fiche("Un plugin Claude Code")))
        self.assertIn("titre sans « claude code »", self.vraie("titre_sans", SUJETS, fiche("Mes voyages")))

    def test_conditions_d_un_cas_reliees_par_et(self):
        regle = {"si": [{"categories": ["communaute"], "titre_sans": SUJETS}]}
        self.assertIsNotNone(radar.explication_regle(regle, fiche("Mes voyages"), "communaute"))
        self.assertIsNone(radar.explication_regle(regle, fiche("Mes voyages"), "officielle"))  # 1 condition fausse
        self.assertIsNone(radar.explication_regle(regle, fiche("Claude Code"), "communaute"))

    def test_cas_relies_par_ou(self):
        regle = REGLES["biais_interet"]
        self.assertEqual(radar.explication_regle(regle, fiche("Show HN: x"), "communaute"), "« Show HN » dans le titre")
        self.assertEqual(radar.explication_regle(regle, fiche("x", url="https://a.org/?ref=moi"), "communaute"),
                         "« ?ref= » dans l'url")
        self.assertIsNone(radar.explication_regle(regle, fiche("x"), "communaute"))


# --- Le calcul du score -----------------------------------------------------

class TestScorer(unittest.TestCase):

    def test_points_de_categorie(self):
        for source, points in [("Dépôt GitHub officiel", 3), ("Base OSV", 2), ("Hacker News", 1), ("Forum", 0)]:
            with self.subTest(source=source):
                _, raisons = scorer(fiche("x", source=source, publie_le="2020-01-01"))
                self.assertEqual(raisons[0][0], points)

    def test_source_absente_du_plan(self):
        total, raisons = scorer(fiche("x", source="Blog inconnu", publie_le="2020-01-01"))
        self.assertEqual(raisons[0], (0, "catégorie inconnue : source absente du plan de veille"))
        self.assertEqual(total, sum(p for p, _ in raisons))

    def test_fraicheur_limite_de_183_jours(self):
        for age, attendu in [(0, True), (1, True), (182, True), (183, False), (400, False)]:
            with self.subTest(age=age):
                _, raisons = scorer(fiche("Claude Code", source="Forum", publie_le=(REF - timedelta(days=age)).isoformat()))
                self.assertEqual(any(p.startswith("récente") for p in phrases(raisons)), attendu)

    def test_fraicheur_phrase_lisible(self):
        for age, attendu in [(0, "récente : publiée aujourd'hui (moins de 183 jours)"),
                             (1, "récente : publiée il y a 1 jour (moins de 183 jours)"),
                             (12, "récente : publiée il y a 12 jours (moins de 183 jours)")]:
            with self.subTest(age=age):
                _, raisons = scorer(fiche("x", publie_le=(REF - timedelta(days=age)).isoformat()))
                self.assertIn(attendu, phrases(raisons))

    def test_recoupee_par_une_autre_source(self):
        hn = fiche("DeltaDB now has a Claude Code plugin", url="https://delta.dev/a")
        github = fiche("Claude Code v2.1.312", source="Dépôt GitHub officiel", url="https://github.com/r/1")
        osv = fiche("express · GHSA-1 : XSS", source="Base OSV", url="https://osv.dev/1")
        items = [hn, github, osv]
        _, raisons = scorer(hn, items)
        self.assertIn((1, "recoupée par Dépôt GitHub officiel"), raisons)
        _, raisons = scorer(github, items)
        self.assertIn((1, "recoupée par Hacker News"), raisons)
        _, raisons = scorer(osv, items)
        self.assertFalse(any(p.startswith("recoupée") for p in phrases(raisons)))  # « express » : seule source

    def test_pas_de_recoupement_par_la_meme_source(self):
        a = fiche("Claude Code v1", source="Dépôt GitHub officiel", url="https://github.com/r/1")
        b = fiche("Claude Code v2", source="Dépôt GitHub officiel", url="https://github.com/r/2")
        _, raisons = scorer(a, [a, b])
        self.assertFalse(any(p.startswith("recoupée") for p in phrases(raisons)))

    def test_recoupement_sans_tenir_compte_des_majuscules(self):
        a = fiche("New MCP server", url="https://a.org")
        b = fiche("mcp release", source="Dépôt GitHub officiel", url="https://github.com/r/1")
        _, raisons = scorer(a, [a, b])
        self.assertIn((1, "recoupée par Dépôt GitHub officiel"), raisons)

    def test_biais_interet(self):
        _, raisons = scorer(fiche("Show HN: I built Trvlrr, home for all your travels", url="https://trvlrr.app/"))
        self.assertIn((-2, "biais d'intérêt (« Show HN » dans le titre)"), raisons)
        _, raisons = scorer(fiche("Un outil Claude Code", url="https://blog.org/a?utm_source=hn"))
        self.assertIn((-2, "biais d'intérêt (« utm_ » dans l'url)"), raisons)

    def test_effet_de_mode_seulement_pour_communaute_et_social(self):
        _, raisons = scorer(fiche("Mes voyages"))  # Hacker News, aucun sujet dans le titre
        self.assertTrue(any(p == -1 and s.startswith("effet de mode") for p, s in raisons))
        _, raisons = scorer(fiche("Usage Policy", source="Dépôt GitHub officiel"))  # officielle : pas concernée
        self.assertFalse(any(s.startswith("effet de mode") for s in phrases(raisons)))
        _, raisons = scorer(fiche("This Claude Code trick is a game changer"))
        self.assertIn((-1, "effet de mode (« game changer » dans le titre)"), raisons)

    def test_exemple_complet_et_ordre_de_la_config(self):
        une = fiche("Show HN: I built Trvlrr, home for all your travels", url="https://trvlrr.app/")
        total, raisons = scorer(une)
        self.assertEqual([p for p, _ in raisons], [1, 1, -2, -1])
        self.assertEqual(total, -1)
        self.assertEqual(phrases(raisons)[:2], ["source communaute",
                                                "récente : publiée il y a 1 jour (moins de 183 jours)"])

    def test_une_regle_ajoutee_dans_la_config_suffit(self):
        regles = copy.deepcopy(REGLES)
        regles["contenu_genere"] = {"libelle": "contenu généré", "points": -1,
                                    "si": [{"titre_contient": ["written by claude"]}]}
        _, raisons = scorer(fiche("Imp, an LLM server, Written by Claude Code"), regles=regles)
        self.assertIn((-1, "contenu généré (« written by claude » dans le titre)"), raisons)

    def test_libelle_par_defaut(self):
        regles = copy.deepcopy(REGLES)
        del regles["biais_interet"]["libelle"]
        _, raisons = scorer(fiche("Show HN: x"), regles=regles)
        self.assertIn("biais interet (« Show HN » dans le titre)", phrases(raisons))


# --- La commande score de bout en bout ---------------------------------------

class TestCommandeScore(unittest.TestCase):
    """radar score dans un dossier temporaire ; aucun appel réseau n'est permis."""

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
        self.config.write_text(yaml.safe_dump(config_ok(), allow_unicode=True), encoding="utf-8")

    def patcher(self, cible, nom, valeur=mock.DEFAULT, **options):
        patch = mock.patch.object(cible, nom, valeur, **options)
        patch.start()
        self.addCleanup(patch.stop)

    def ecrire_items(self, items):
        self.items.parent.mkdir(parents=True, exist_ok=True)
        self.items.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")

    def lancer(self, top=10):
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            radar.commande_score(argparse.Namespace(top=top))
        return sortie.getvalue()

    def lire_items(self):
        return json.loads(self.items.read_text(encoding="utf-8"))

    ITEMS = [
        fiche("Show HN: I built Trvlrr", url="https://trvlrr.app/", publie_le="2026-10-28"),
        fiche("Claude Code v2.1.311", source="Dépôt GitHub officiel", url="https://github.com/r/311", publie_le="2026-10-26"),
        fiche("Claude Code v2.1.312", source="Dépôt GitHub officiel", url="https://github.com/r/312", publie_le="2026-10-27"),
        fiche("DeltaDB now has a Claude Code plugin", url="https://delta.dev/blog", publie_le="2026-10-28"),
        fiche("express · GHSA-1 : XSS", source="Base OSV", url="https://osv.dev/1", publie_le="2024-09-10"),
    ]

    def test_fiabilite_enregistree_et_reste_de_la_fiche_inchange(self):
        self.ecrire_items(self.ITEMS)
        self.lancer()
        items = self.lire_items()
        self.assertEqual([i["fiabilite"] for i in items], [-1, 6, 6, 3, 4])
        for avant, apres in zip(self.ITEMS, items):
            self.assertEqual({k: v for k, v in apres.items() if k != "fiabilite"},
                             {k: v for k, v in avant.items() if k != "fiabilite"})
            self.assertTrue(radar.fiche_valide(apres))

    def test_top_trie_par_score_puis_date(self):
        self.ecrire_items(self.ITEMS)
        sortie = self.lancer()
        ordre = [ligne.split(" · ", 1)[1] for ligne in sortie.splitlines() if ligne[:3].strip().rstrip(".").isdigit()]
        self.assertEqual(ordre, ["Claude Code v2.1.312", "Claude Code v2.1.311", "express · GHSA-1 : XSS",
                                 "DeltaDB now has a Claude Code plugin", "Show HN: I built Trvlrr"])

    def test_affichage_lisible(self):
        self.ecrire_items(self.ITEMS)
        sortie = self.lancer()
        self.assertIn(" 1. 6 points · Claude Code v2.1.312", sortie)
        self.assertIn("    Dépôt GitHub officiel · publiée le 2026-10-27", sortie)
        self.assertIn("      +3  source officielle", sortie)
        self.assertIn("      +1  recoupée par Hacker News", sortie)
        self.assertIn("      -2  biais d'intérêt (« Show HN » dans le titre)", sortie)
        self.assertIn(" 5. -1 point · Show HN: I built Trvlrr", sortie)
        self.assertIn("fiabilite enregistrée pour 5 infos", sortie)

    def test_option_top(self):
        self.ecrire_items(self.ITEMS)
        sortie = self.lancer(top=2)
        self.assertIn("Top 2 sur 5 infos", sortie)
        self.assertIn(" 2. ", sortie)
        self.assertNotIn(" 3. ", sortie)
        self.assertEqual(len([i for i in self.lire_items() if i["fiabilite"] is not None]), 5)  # tout est noté

    def test_deux_lancements_meme_resultat(self):
        self.ecrire_items(self.ITEMS)
        self.lancer()
        premier = self.items.read_text(encoding="utf-8")
        self.lancer()
        self.assertEqual(self.items.read_text(encoding="utf-8"), premier)

    def test_source_absente_du_plan_signalee(self):
        self.ecrire_items(self.ITEMS + [fiche("Un blog", source="Blog perso", url="https://blog.org/1")])
        sortie = self.lancer()
        self.assertIn("Sources absentes du plan (catégorie inconnue, 0 point) : Blog perso", sortie)

    def test_aucune_info(self):
        sortie = self.lancer()
        self.assertIn("lancez d'abord « radar collect »", sortie)
        self.assertFalse(self.items.exists())

    def test_config_invalide_rien_n_est_ecrit(self):
        self.ecrire_items(self.ITEMS)
        avant = self.items.read_text(encoding="utf-8")
        config = config_ok()
        del config["regles_score"]["recoupee"]
        self.config.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
        with self.assertRaises(SystemExit):
            self.lancer()
        self.assertEqual(self.items.read_text(encoding="utf-8"), avant)


class TestOptionTop(unittest.TestCase):

    def test_entier_positif(self):
        self.assertEqual(radar.entier_positif("5"), 5)
        for texte in ("0", "-1", "abc", "2.5"):
            with self.subTest(texte=texte):
                with self.assertRaises(argparse.ArgumentTypeError):
                    radar.entier_positif(texte)


if __name__ == "__main__":
    unittest.main()
